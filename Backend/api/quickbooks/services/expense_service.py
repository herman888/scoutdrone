import logging
from typing import Dict, Any, Optional, Tuple
from datetime import datetime, UTC

from sqlmodel import select, col

from decimal import Decimal
from ....models.property import Property
from ....models.accounting.expense import Expense
from ..schemas.expense import ExpenseSchema
from .base_service import BaseQuickBooksService, SyncAction, SyncPreview
from .account_mapping_service import AccountMappingService

logger = logging.getLogger(__name__)


class ExpenseService(BaseQuickBooksService):
    """Service for QuickBooks Expense/Purchase operations."""

    async def sync_expenses(self) -> Dict[str, Any]:
        """Perform bidirectional expense synchronization."""
        return await self.sync_expenses_internal()

    async def sync_single_expense_from_quickbooks(self, qb_expense_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Sync a single expense/purchase from QuickBooks webhook event.

        This is more efficient than a full sync when processing webhooks,
        as it only processes the specific entity that changed.

        Args:
            qb_expense_data: The Purchase object from QuickBooks API

        Returns:
            Dict with sync result (synced_count, errors)
        """
        await self.initialize()

        qb_expense_id = qb_expense_data.get("Id")
        if not qb_expense_id:
            return {"synced_count": 0, "errors": ["Expense data missing ID"]}

        try:
            # Check if expense already exists in our system
            existing_expense = await self.session.scalar(
                select(Expense).where(col(Expense.quickbooks_id) == qb_expense_id)
            )

            if existing_expense:
                # Update existing expense
                return await self._update_single_expense(existing_expense, qb_expense_data)
            else:
                # Create new expense
                return await self._create_single_expense(qb_expense_data)

        except Exception as e:
            error_msg = f"Error syncing single expense {qb_expense_id}: {str(e)}"
            logger.error(error_msg, exc_info=True)
            return {"synced_count": 0, "errors": [error_msg]}

    async def _update_single_expense(self, expense: Expense, qb_expense_data: Dict[str, Any]) -> Dict[str, Any]:
        """Update an existing expense with QuickBooks data."""
        try:            
            # Parse TotalAmt (includes subtotal + tax)
            total_amt = Decimal(str(qb_expense_data.get("TotalAmt", 0)))
            
            # Parse expense date
            expense_date = expense.expense_date
            txn_date = qb_expense_data.get("TxnDate")
            if txn_date and isinstance(txn_date, str):
                try:
                    expense_date = datetime.fromisoformat(txn_date)
                except (ValueError, TypeError):
                    pass
            
            # Update fields from QB data
            expense.subtotal_amount = total_amt - expense.total_tax_amount
            expense.expense_date = expense_date
            expense.description = qb_expense_data.get("PrivateNote", expense.description)
            expense.last_synced_at = datetime.now(UTC)

            self.session.add(expense)
            await self.session.commit()

            logger.info(f"Updated expense {expense.id} from QB purchase {qb_expense_data.get('Id')}")
            return {"synced_count": 1, "errors": []}

        except Exception as e:
            error_msg = f"Error updating expense: {str(e)}"
            logger.error(error_msg, exc_info=True)
            return {"synced_count": 0, "errors": [error_msg]}

    async def _create_single_expense(self, qb_expense_data: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new expense from QuickBooks data."""
        qb_expense_id = qb_expense_data.get("Id")

        try:
            # Get tax account mappings for this user
            mapping_service = AccountMappingService(self.user, self.session)
            tax_mappings = await mapping_service.get_tax_account_id_mapping()

            # Create the expense (no property assignment for QB-synced expenses)
            new_expense, tax_details = ExpenseSchema.from_quickbooks(
                qb_expense_data,
                user_property=None,  # No property for QB-synced expenses
                tax_account_mapping=tax_mappings
            )
            # Set the landlord_id after creation
            new_expense.landlord_id = self.user.id
            
            self.session.add(new_expense)
            await self.session.flush()

            # Add tax details
            for tax_detail in tax_details:
                tax_detail.expense_id = new_expense.id
                self.session.add(tax_detail)

            await self.session.commit()

            logger.info(f"Created expense from QB purchase {qb_expense_id}")
            return {"synced_count": 1, "errors": []}

        except Exception as e:
            error_msg = f"Error creating expense from QB {qb_expense_id}: {str(e)}"
            logger.error(error_msg, exc_info=True)
            return {"synced_count": 0, "errors": [error_msg]}

    async def preview_expenses(self) -> SyncPreview:
        """Preview what would happen during expense synchronization."""
        # Create a preview-mode service
        preview_service = ExpenseService(self.user, self.session, preview_mode=True)
        await preview_service.initialize()
        await preview_service.sync_expenses_internal()
        return preview_service._generate_preview()

    async def sync_expenses_internal(self) -> Dict[str, Any]:
        """Perform bidirectional expense synchronization."""
        await self.initialize()

        all_errors = []
        pulled_count = 0
        pushed_count = 0

        try:
            # Pull expenses from QuickBooks
            pull_result = await self._pull_expenses_from_quickbooks()
            pulled_count = pull_result.get("synced_count", 0)
            all_errors.extend(pull_result.get("errors", []))

            # Push expenses to QuickBooks
            push_result = await self._push_expenses_to_quickbooks()
            pushed_count = push_result.get("pushed_count", 0)
            all_errors.extend(push_result.get("errors", []))

            total_synced = pulled_count + pushed_count

            # Update integration sync time on success
            if total_synced > 0 and len(all_errors) == 0:
                await self._update_integration_sync_time()

            self._log_operation(
                operation="sync_expenses",
                level="info" if len(all_errors) == 0 else "warning",
                synced_count=total_synced,
                pulled_count=pulled_count,
                pushed_count=pushed_count,
                error_count=len(all_errors)
            )

            return self._create_sync_result(
                synced_count=total_synced,
                pulled_count=pulled_count,
                pushed_count=pushed_count,
                errors=all_errors
            )

        except Exception as e:
            logger.error(f"Error in expense sync for user {self.user.id}: {e}", exc_info=True)
            return self._create_sync_result(errors=[f"Expense sync failed: {str(e)}"])

    async def _pull_expenses_from_quickbooks(self) -> Dict[str, Any]:
        """Pull expenses from QuickBooks and sync to local database."""
        new_expenses_count = 0
        errors = []

        try:
            # Get purchases from QuickBooks (expenses are typically recorded as Purchase entities)
            purchases_response = await self.client.list_purchases(max_results=100)

            if not purchases_response or "QueryResponse" not in purchases_response:
                return {"synced_count": 0, "errors": ["No purchases found in QuickBooks"]}

            qb_purchases = purchases_response["QueryResponse"].get("Purchase", [])
            if not qb_purchases:
                return {"synced_count": 0, "errors": []}

            # Get existing expense IDs to avoid duplicates
            qb_purchase_ids = [purchase.get("Id") for purchase in qb_purchases if purchase.get("Id")]
            existing_ids_result = await self.session.execute(
                select(Expense.quickbooks_id).where(col(Expense.quickbooks_id).in_(qb_purchase_ids))
            )
            existing_ids = {row[0] for row in existing_ids_result}

            # NOTE: We no longer force expenses to a specific property
            # Expenses synced from QuickBooks will have property_id = NULL
            # Users can manually assign them to properties in the UI later

            # Get dynamic tax account mapping (account IDs, not names!)
            # This fixes the "No tax details found" warning
            tax_account_mapping = await self._get_or_cache_tax_account_mapping()

            for qb_purchase in qb_purchases:
                qb_purchase_id = qb_purchase.get("Id")
                if not qb_purchase_id or qb_purchase_id in existing_ids:
                    continue

                try:
                    # Create Brikli expense from QuickBooks data with tax details
                    # Note: property_id will be NULL - users assign properties manually
                    new_expense, tax_details = ExpenseSchema.from_quickbooks(qb_purchase, None, tax_account_mapping)

                    # In preview mode, collect item for preview
                    if self.preview_mode:
                        warnings = []
                        total_amount = new_expense.subtotal_amount + new_expense.total_tax_amount

                        # Only warn about missing tax if it's a significant purchase (>$100)
                        # Small purchases might legitimately be tax-exempt
                        if len(tax_details) == 0 and total_amount > 100:
                            warnings.append("No tax details found - verify if this expense should have tax")

                        # Build tax details for display
                        tax_info = []
                        for td in tax_details:
                            tax_info.append({
                                "name": td.tax_name,
                                "rate": float(td.tax_rate) if td.tax_rate else 0,
                                "amount": float(td.tax_amount) if td.tax_amount else 0
                            })

                        self._add_preview_item(
                            entity_type="expense",
                            entity_id=qb_purchase_id,
                            entity_name=new_expense.description or f"QB Purchase {qb_purchase_id}",
                            action=SyncAction.CREATE,
                            details={
                                "amount": float(total_amount),
                                "subtotal": float(new_expense.subtotal_amount),
                                "tax_amount": float(new_expense.total_tax_amount),
                                "category": new_expense.category,
                                "date": new_expense.expense_date.isoformat() if new_expense.expense_date else None,
                                "tax_details_count": len(tax_details),
                                "tax_details": tax_info,  # Pass full tax breakdown
                                "payment_method": new_expense.payment_method.value if new_expense.payment_method else None
                            },
                            warnings=warnings
                        )
                    else:
                        # Set landlord_id so the expense can be queried without property
                        new_expense.landlord_id = self.user.id

                        # Execute the actual creation
                        self.session.add(new_expense)

                        # Add tax details if any
                        for tax_detail in tax_details:
                            tax_detail.expense_id = new_expense.id
                            self.session.add(tax_detail)

                        logger.info(f"Synced expense {qb_purchase_id} from QuickBooks with {len(tax_details)} tax details")

                    new_expenses_count += 1

                except Exception as e:
                    error_msg = f"Error processing purchase {qb_purchase_id}: {str(e)}"
                    errors.append(error_msg)
                    logger.error(error_msg, exc_info=True)

            if new_expenses_count > 0 and self._should_execute_action():
                await self.session.commit()

        except Exception as e:
            logger.error(f"Error pulling expenses from QuickBooks: {e}", exc_info=True)
            errors.append(f"Pull expenses failed: {str(e)}")

        return {"synced_count": new_expenses_count, "errors": errors}

    async def _push_expenses_to_quickbooks(self) -> Dict[str, Any]:
        """Push unsynced Brikli expenses to QuickBooks."""
        pushed_count = 0
        errors = []

        try:
            # Get user's properties to filter expenses
            property_ids_result = await self.session.execute(
                select(Property.id).where(col(Property.user_id) == self.user.id)
            )
            property_ids = [row[0] for row in property_ids_result]

            if not property_ids:
                return {"pushed_count": 0, "errors": ["No properties found for user"]}

            # Find expenses that haven't been synced to QuickBooks
            unsynced_expenses = await self.session.scalars(
                select(Expense).where(
                    col(Expense.property_id).in_(property_ids),
                    col(Expense.quickbooks_id).is_(None)
                ).limit(50)  # Limit to avoid timeout
            )
            unsynced_expenses_list = list(unsynced_expenses)

            if not unsynced_expenses_list:
                return {"pushed_count": 0, "errors": []}

            # Cache default accounts to avoid multiple API calls
            paid_from_account_id, expense_account_id = await self._get_or_cache_default_accounts()

            # Cache tax account mapping for tax line creation
            tax_account_mapping = await self._get_or_cache_tax_account_mapping()

            api_call_count = 0  # Track API calls for throttling
            COMMIT_BATCH_SIZE = 10  # Commit every N items

            for idx, expense in enumerate(unsynced_expenses_list):
                try:
                    # Build QuickBooks expense data with tax support
                    expense_data = ExpenseSchema.to_quickbooks(
                        expense,
                        paid_from_account_id,
                        expense_account_id,
                        tax_account_mapping
                    )

                    # In preview mode, collect item for preview
                    if self.preview_mode:
                        warnings: list[str] = []
                        validation_errors = ExpenseSchema.validate_for_quickbooks(expense)
                        if validation_errors:
                            warnings.extend([str(msg) for msg in validation_errors.values()])

                        self._add_preview_item(
                            entity_type="expense",
                            entity_id=str(expense.id),
                            entity_name=expense.description or f"Expense {expense.id}",
                            action=SyncAction.CREATE,
                            details={
                                "amount": float(expense.subtotal_amount + expense.total_tax_amount),
                                "category": expense.category,
                                "date": expense.expense_date.isoformat() if expense.expense_date else None,
                                "payment_method": expense.payment_method.value if expense.payment_method else None,
                                "destination": "QuickBooks"
                            },
                            warnings=warnings
                        )
                        pushed_count += 1
                    else:
                        # Create expense in QuickBooks with retry
                        async def create_operation():
                            return await self.client.create_purchase(expense_data)

                        response = await self._retry_operation(
                            create_operation,
                            f"create_expense_{expense.id}",
                            max_retries=2
                        )

                        if response and "Purchase" in response:
                            qb_expense = response["Purchase"]
                            qb_expense_id = qb_expense.get("Id")

                            if qb_expense_id:
                                expense.quickbooks_id = qb_expense_id
                                expense.last_synced_at = datetime.now(UTC)
                                self.session.add(expense)
                                pushed_count += 1
                                api_call_count += 1
                                logger.info(f"Successfully pushed expense {expense.id} to QuickBooks with ID {qb_expense_id}")
                                
                                # Throttle API calls to respect rate limits
                                await self._throttle_api_call(api_call_count)
                            else:
                                errors.append(f"Expense {expense.id}: QuickBooks response missing ID")
                        else:
                            errors.append(f"Expense {expense.id}: Invalid QuickBooks response")

                    # Batch commit every COMMIT_BATCH_SIZE items
                    if (idx + 1) % COMMIT_BATCH_SIZE == 0 and pushed_count > 0 and self._should_execute_action():
                        await self.session.commit()
                        logger.info(f"Committed batch progress: {pushed_count} expenses synced so far")

                except Exception as e:
                    error_msg = f"Error pushing expense {expense.id}: {str(e)}"
                    errors.append(error_msg)
                    logger.error(error_msg, exc_info=True)

            # Final commit for remaining items (only in non-preview mode)
            if pushed_count > 0 and self._should_execute_action():
                await self.session.commit()

        except Exception as e:
            logger.error(f"Error pushing expenses to QuickBooks: {e}", exc_info=True)
            errors.append(f"Push expenses failed: {str(e)}")

        return {"pushed_count": pushed_count, "errors": errors}

    async def _get_default_accounts(self) -> Tuple[str, str]:
        """Get default accounts for expenses."""
        # Check integration metadata for cached accounts
        paid_from = await self._get_cached_metadata("default_paid_from_account_id")
        expense_account = await self._get_cached_metadata("default_expense_account_id")

        if paid_from and expense_account:
            return paid_from, expense_account

        try:
            # Get accounts from QuickBooks
            accounts_response = await self.client.list_accounts(max_results=100)

            if accounts_response and "QueryResponse" in accounts_response:
                accounts = accounts_response["QueryResponse"].get("Account", [])

                paid_from_account_id = "1"  # Default fallback
                expense_account_id = "1"   # Default fallback

                for account in accounts:
                    account_type = account.get("AccountType", "").upper()
                    account_subtype = account.get("AccountSubType", "").upper()

                    # Look for bank/checking account for "paid from"
                    if account_type == "BANK" or account_subtype == "CHECKING":
                        paid_from_account_id = account.get("Id", "1")

                    # Look for expense account
                    elif account_type == "EXPENSE":
                        expense_account_id = account.get("Id", "1")

                # Cache the accounts
                await self._cache_metadata("default_paid_from_account_id", paid_from_account_id)
                await self._cache_metadata("default_expense_account_id", expense_account_id)

                return paid_from_account_id, expense_account_id

        except Exception as e:
            logger.error(f"Error getting default accounts: {e}")

        return "1", "1"

    async def _get_or_cache_user_property(self) -> Optional[Property]:
        """Get or cache user's first property."""
        async def fetch_property():
            return await self.session.scalar(
                select(Property).where(col(Property.user_id) == self.user.id).limit(1)
            )

        return await self._get_or_cache_quickbooks_data("user_property", fetch_property)

    async def _get_or_cache_default_accounts(self) -> Tuple[str, str]:
        """Get or cache default accounts to avoid multiple API calls."""
        cached_accounts = self._get_session_cache("default_accounts")
        if cached_accounts:
            return cached_accounts

        accounts = await self._get_default_accounts()
        self._set_session_cache("default_accounts", accounts)
        return accounts

    async def _get_or_cache_tax_accounts(self) -> Dict[str, str]:
        """
        Get or cache tax account mapping for PUSH operations (Brikli → QB).

        Returns Dict[tax_code, qb_account_id], e.g.:
        {"GST": "123", "HST": "124", "PST": "125", "QST": "126"}

        This enables proper tax line creation when pushing expenses to QuickBooks.
        """
        cached_tax_accounts = self._get_session_cache("tax_account_mapping")
        if cached_tax_accounts:
            return cached_tax_accounts

        try:
            # Use AccountMappingService to get dynamic mappings from database
            mapping_service = AccountMappingService(self.user, self.session)
            tax_accounts = await mapping_service.get_tax_account_id_mapping()

            # If no mappings found, try auto-detection
            if not tax_accounts:
                logger.info("No tax account mappings found, attempting auto-detection")
                await mapping_service.save_auto_detected_mappings()
                tax_accounts = await mapping_service.get_tax_account_id_mapping()

            self._set_session_cache("tax_account_mapping", tax_accounts)
            return tax_accounts

        except Exception as e:
            logger.warning(f"Failed to get tax account mappings: {e}. Tax lines will be skipped.")
            tax_accounts = {}
            self._set_session_cache("tax_account_mapping", tax_accounts)
            return tax_accounts

    async def _get_or_cache_tax_account_mapping(self) -> Dict[str, str]:
        """
        Get or cache REVERSE tax account mapping for PULL operations (QB → Brikli).

        Returns Dict[qb_account_id, tax_code], e.g.:
        {"123": "GST", "124": "HST", "125": "PST", "126": "QST"}

        This enables proper tax line detection when pulling expenses from QuickBooks.
        This is the KEY FIX for the "No tax details found" warning.
        """
        cached_reverse_mapping = self._get_session_cache("reverse_tax_mapping")
        if cached_reverse_mapping:
            return cached_reverse_mapping

        try:
            # Use AccountMappingService to get dynamic reverse mappings
            mapping_service = AccountMappingService(self.user, self.session)
            reverse_mapping = await mapping_service.get_reverse_tax_mapping()

            # If no mappings found, try auto-detection first
            if not reverse_mapping:
                logger.info("No tax account mappings found for pull, attempting auto-detection")
                await mapping_service.save_auto_detected_mappings()
                reverse_mapping = await mapping_service.get_reverse_tax_mapping()

            if reverse_mapping:
                logger.info(f"Using reverse tax mapping with {len(reverse_mapping)} account(s): {list(reverse_mapping.keys())}")
            else:
                logger.warning("No tax account mappings available. Tax details will not be detected.")

            self._set_session_cache("reverse_tax_mapping", reverse_mapping)
            return reverse_mapping

        except Exception as e:
            logger.warning(f"Failed to get reverse tax account mappings: {e}. Tax details will not be detected.")
            reverse_mapping = {}
            self._set_session_cache("reverse_tax_mapping", reverse_mapping)
            return reverse_mapping

    async def create_expense_in_quickbooks(self, expense_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Create a single expense in QuickBooks.

        Args:
            expense_data: Dictionary containing expense details from Brikli

        Returns:
            Dictionary with success status, message, and QuickBooks ID if successful
        """
        await self.initialize()

        try:
            # Get default accounts
            paid_from_account_id, expense_account_id = await self._get_default_accounts()

            # Validate expense data (basic validation)
            if not expense_data.get("total_amount") or float(expense_data["total_amount"]) <= 0:
                return {
                    "success": False,
                    "message": "Invalid expense amount",
                    "quickbooks_id": None
                }

            # Build QuickBooks expense data
            total_amount = float(expense_data.get("total_amount", 0))
            tx_date = expense_data.get("expense_date", datetime.now().strftime('%Y-%m-%d'))
            description = expense_data.get("description", "Expense from Brikli")

            purchase_data = {
                "Purchase": {
                    "AccountRef": {
                        "value": str(paid_from_account_id)
                    },
                    "PaymentType": "Cash",  # Default payment type
                    "TxnDate": tx_date,
                    "Line": [
                        {
                            "Id": "1",
                            "Amount": total_amount,
                            "DetailType": "AccountBasedExpenseLineDetail",
                            "AccountBasedExpenseLineDetail": {
                                "AccountRef": {
                                    "value": str(expense_account_id)
                                }
                            },
                            "Description": description
                        }
                    ],
                    "PrivateNote": description
                }
            }

            # Create expense in QuickBooks with retry
            async def create_operation():
                return await self.client.create_purchase(purchase_data)

            response = await self._retry_operation(
                create_operation,
                f"create_single_expense_{expense_data.get('id', 'unknown')}",
                max_retries=2
            )

            if response and "Purchase" in response:
                purchase = response["Purchase"]
                quickbooks_id = purchase.get("Id")

                if quickbooks_id:
                    self._log_operation(
                        operation="create_expense",
                        level="info",
                        status="success",
                        quickbooks_id=quickbooks_id,
                        expense_amount=expense_data.get("total_amount"),
                        expense_category=expense_data.get("category")
                    )
                    return {
                        "success": True,
                        "message": "Expense created in QuickBooks successfully",
                        "quickbooks_id": quickbooks_id
                    }

            # Failed to get valid response
            self._log_operation(
                operation="create_expense",
                level="warning",
                status="failed",
                error="Invalid response from QuickBooks",
                expense_amount=expense_data.get("total_amount")
            )
            return {
                "success": False,
                "message": "Failed to create expense: Invalid response from QuickBooks",
                "quickbooks_id": None
            }

        except Exception as e:
            logger.error(f"Error creating expense in QuickBooks: {e}", exc_info=True)

            self._log_operation(
                operation="create_expense",
                level="error",
                status="failed",
                error=str(e),
                expense_amount=expense_data.get("total_amount")
            )

            return {
                "success": False,
                "message": f"QuickBooks service error: {str(e)}",
                "quickbooks_id": None
            }