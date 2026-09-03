from typing import Dict, Any, Optional, Tuple, List
from datetime import datetime, UTC
from decimal import Decimal
import logging

from Backend.models.accounting.expense import Expense, ExpenseTaxDetail
from Backend.models.accounting.payment import PaymentMethod
from Backend.models.property import Property

logger = logging.getLogger(__name__)


class ExpenseSchema:
    """Schema for transforming between Brikli Expense and QuickBooks Purchase."""

    # Payment method mapping for expenses (QuickBooks Purchase PaymentType)
    PAYMENT_TYPE_MAPPING = {
        "Cash": PaymentMethod.CASH,
        "Check": PaymentMethod.CHECK,
        "CreditCard": PaymentMethod.CREDIT_CARD,
        "Other": PaymentMethod.OTHER,
    }

    # Reverse mapping for Brikli to QuickBooks
    REVERSE_PAYMENT_TYPE_MAPPING = {
        PaymentMethod.CASH: "Cash",
        PaymentMethod.CHECK: "Check",
        PaymentMethod.CREDIT_CARD: "CreditCard",
        PaymentMethod.DEBIT_CARD: "CreditCard",  # Map to closest equivalent
        PaymentMethod.BANK_TRANSFER: "Other",
        PaymentMethod.WIRE_TRANSFER: "Other",
        PaymentMethod.DIRECT_DEPOSIT: "Other",
        PaymentMethod.INTERAC_E_TRANSFER: "Other",
        PaymentMethod.BANK_DRAFT: "Check",
        PaymentMethod.PAYPAL: "Other",
        PaymentMethod.INTERNAL_TRANSFER: "Other",
        PaymentMethod.OTHER: "Other",
    }

    # Common Canadian expense categories
    CATEGORY_MAPPING = {
        "maintenance": "Repairs and Maintenance",
        "utilities": "Utilities",
        "taxes": "Property Tax",
        "insurance": "Insurance",
        "office": "Office Expenses",
        "legal": "Legal and Professional Fees",
        "advertising": "Advertising",
        "supplies": "Supplies",
        "travel": "Travel",
        "other": "Other Business Expenses",
        "QuickBooks Import": "QuickBooks Import",
    }

    # QuickBooks account name to Brikli category mapping
    QB_ACCOUNT_TO_CATEGORY = {
        # Maintenance related
        "repair": "maintenance",
        "maintenance": "maintenance",
        "landscaping": "maintenance",
        "cleaning": "maintenance",
        "janitorial": "maintenance",
        "plumbing": "maintenance",
        "electrical": "maintenance",
        "hvac": "maintenance",
        "painting": "maintenance",
        
        # Utilities
        "utilities": "utilities",
        "electric": "utilities",
        "gas": "utilities",
        "water": "utilities",
        "sewer": "utilities",
        "internet": "utilities",
        "cable": "utilities",
        "phone": "utilities",
        
        # Taxes
        "tax": "taxes",
        "property tax": "taxes",
        "real estate tax": "taxes",
        
        # Insurance
        "insurance": "insurance",
        
        # Office & Admin
        "office": "office",
        "supplies": "supplies",
        "admin": "office",
        
        # Legal & Professional
        "legal": "legal",
        "attorney": "legal",
        "professional": "legal",
        "consulting": "legal",
        "accounting": "legal",
        
        # Advertising & Marketing
        "advertising": "advertising",
        "marketing": "advertising",
        
        # Travel
        "travel": "travel",
        "mileage": "travel",
    }

    @staticmethod
    def _detect_category(account_names: List[str], description: str) -> str:
        """
        Intelligently detect expense category from QuickBooks account names and description.
        
        Args:
            account_names: List of QuickBooks account names (lowercased)
            description: Expense description
            
        Returns:
            Detected Brikli category string
        """
        # First, try to match account names
        for account_name in account_names:
            for qb_keyword, brikli_category in ExpenseSchema.QB_ACCOUNT_TO_CATEGORY.items():
                if qb_keyword in account_name:
                    return brikli_category
        
        # Fallback: try to match description
        description_lower = description.lower()
        for qb_keyword, brikli_category in ExpenseSchema.QB_ACCOUNT_TO_CATEGORY.items():
            if qb_keyword in description_lower:
                return brikli_category
        
        # Last resort: check if description contains any Brikli category keywords
        for brikli_cat in ExpenseSchema.CATEGORY_MAPPING.keys():
            if brikli_cat != "QuickBooks Import" and brikli_cat in description_lower:
                return brikli_cat
        
        # Default to "other" instead of "QuickBooks Import"
        return "other"

    @staticmethod
    def to_quickbooks(
        expense: Expense,
        paid_from_account_id: str,
        expense_account_id: str,
        tax_account_mapping: Optional[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        """Transform Brikli Expense to QuickBooks Purchase format."""
        tx_date = expense.expense_date.strftime('%Y-%m-%d') if expense.expense_date else datetime.now().strftime('%Y-%m-%d')
        description = expense.description or "Expense from Brikli"

        # Map payment method with validation for QuickBooks
        VALID_QB_PAYMENT_TYPES = {"Cash", "Check", "CreditCard"}
        payment_type = ExpenseSchema.REVERSE_PAYMENT_TYPE_MAPPING.get(
            expense.payment_method, "Cash"
        )
        # Ensure it's a valid QuickBooks payment type
        if payment_type not in VALID_QB_PAYMENT_TYPES:
            payment_type = "Cash"  # Default to Cash if invalid

        # Start with the main expense line
        lines = []
        line_id = 1

        # Main expense line (subtotal)
        main_line = {
            "Id": str(line_id),
            "Amount": float(expense.subtotal_amount),
            "DetailType": "AccountBasedExpenseLineDetail",
            "AccountBasedExpenseLineDetail": {
                "AccountRef": {
                    "value": str(expense_account_id)
                }
            },
            "Description": f"{ExpenseSchema.CATEGORY_MAPPING.get(expense.category, expense.category)}: {description}"
        }
        lines.append(main_line)
        line_id += 1

        # Add tax lines if taxes exist and mapping is provided
        if expense.taxes and tax_account_mapping:
            for tax_detail in expense.taxes:
                if tax_detail.tax_amount > 0:
                    tax_account_id = tax_account_mapping.get(tax_detail.tax_name)
                    # Validate account ID is numeric (not an account name)
                    if tax_account_id and tax_account_id.isdigit():
                        tax_line = {
                            "Id": str(line_id),
                            "Amount": float(tax_detail.tax_amount),
                            "DetailType": "AccountBasedExpenseLineDetail",
                            "AccountBasedExpenseLineDetail": {
                                "AccountRef": {
                                    "value": str(tax_account_id)
                                }
                            },
                            "Description": f"{tax_detail.tax_name} ({tax_detail.tax_rate}%)"
                        }
                        lines.append(tax_line)
                        line_id += 1

        # Calculate total amount
        total_amount = float(expense.subtotal_amount + expense.total_tax_amount)

        # Enhanced private note with more context
        note_parts = [description]
        if expense.category:
            note_parts.append(f"Category: {expense.category}")
        if expense.receipt_url:
            note_parts.append(f"Receipt: {expense.receipt_url}")

        expense_data = {
            "AccountRef": {
                "value": str(paid_from_account_id)
            },
            "PaymentType": payment_type,
            "TxnDate": tx_date,
            "TotalAmt": total_amount,
            "Line": lines,
            "PrivateNote": " | ".join(note_parts)
        }

        return expense_data

    @staticmethod
    def from_quickbooks(qb_purchase: Dict[str, Any], user_property: Optional[Property] = None, tax_account_mapping: Optional[Dict[str, str]] = None) -> Tuple[Expense, List[ExpenseTaxDetail]]:
        """
        Transform QuickBooks Purchase to Brikli Expense with tax details.

        Args:
            qb_purchase: The QuickBooks Purchase object
            user_property: Optional property to associate with the expense.
                          If None, expense is created without property assignment
                          (user can assign later in the UI).
            tax_account_mapping: REVERSE mapping of QB account ID → tax code
                                 e.g., {"123": "GST", "124": "HST", ...}
                                 This is used to identify which line items are tax lines.

        Returns:
            Tuple of (Expense, List[ExpenseTaxDetail])
        """
        qb_purchase_id = qb_purchase.get("Id")
        if not qb_purchase_id:
            raise ValueError("QuickBooks purchase missing required 'Id' field")

        # Parse lines to get expense amounts and descriptions
        lines = qb_purchase.get("Line", [])
        subtotal_amount = Decimal("0")
        total_tax_amount = Decimal("0")
        description_parts = []
        tax_details: list[dict] = []
        account_names = []  # Collect account names for category detection

        # First, extract tax info from TxnTaxDetail (the CORRECT way QB stores calculated taxes)
        # This handles taxes applied via TaxCodeRef on lines (like "HST ON (13%)")
        txn_tax_detail = qb_purchase.get("TxnTaxDetail", {})

        # Debug logging - only enabled when needed
        # logger.debug(f"Purchase {qb_purchase_id} TxnTaxDetail: {txn_tax_detail}")

        if txn_tax_detail:
            # Get total tax from the summary
            total_tax_from_detail = txn_tax_detail.get("TotalTax")
            if total_tax_from_detail is not None:
                total_tax_amount = Decimal(str(total_tax_from_detail))

            # Parse individual tax lines for detailed breakdown
            tax_lines = txn_tax_detail.get("TaxLine", [])
            for tax_line in tax_lines:
                if tax_line.get("DetailType") == "TaxLineDetail":
                    tax_line_detail = tax_line.get("TaxLineDetail", {})
                    tax_rate_ref = tax_line_detail.get("TaxRateRef", {})
                    tax_amount = Decimal(str(tax_line.get("Amount", 0)))
                    tax_percent = Decimal(str(tax_line_detail.get("TaxPercent", 0)))

                    # Skip zero-amount tax lines (e.g., "Exempt" or "Zero-rated")
                    if tax_amount == 0 and tax_percent == 0:
                        continue

                    # Get tax name - TaxRateRef may only have 'value', not 'name'
                    # If no name, derive from percent (13% is typically HST in Ontario)
                    tax_name = tax_rate_ref.get("name")
                    if not tax_name:
                        # Derive tax type from percentage
                        if tax_percent == 13:
                            tax_name = "HST"
                        elif tax_percent == 5:
                            tax_name = "GST"
                        elif tax_percent in (Decimal("7"), Decimal("8"), Decimal("9.975")):
                            tax_name = "PST" if tax_percent != Decimal("9.975") else "QST"
                        else:
                            tax_name = f"Tax ({tax_percent}%)"

                    # Normalize tax name to standard Canadian codes
                    normalized_name = ExpenseSchema._normalize_tax_name(tax_name)

                    tax_details.append({
                        "tax_name": normalized_name,
                        "tax_rate": tax_percent,
                        "tax_amount": tax_amount
                    })
                    # Debug logging - only enabled when needed
                    # logger.debug(f"Purchase {qb_purchase_id}: Extracted tax {normalized_name} @ {tax_percent}% = ${tax_amount}")

        # tax_account_mapping is the REVERSE mapping (QB account ID → tax code)
        # Used as fallback for older-style expenses with separate tax account lines
        reverse_tax_mapping = tax_account_mapping or {}

        for line in lines:
            if line.get("DetailType") == "AccountBasedExpenseLineDetail":
                line_amount = Decimal(str(line.get("Amount", 0)))
                line_desc = line.get("Description", "")
                account_ref = line.get("AccountBasedExpenseLineDetail", {}).get("AccountRef", {})
                account_id = account_ref.get("value")
                account_name = account_ref.get("name", "")  # Get account name for category mapping

                # Check if this is a tax line (fallback for manual tax account lines)
                # Only use this if we didn't already get tax from TxnTaxDetail
                if not tax_details and account_id and account_id in reverse_tax_mapping:
                    tax_name = reverse_tax_mapping[account_id]
                    total_tax_amount += line_amount

                    # Extract tax rate from description if available (e.g., "GST (5%)")
                    tax_rate = Decimal("0")
                    if "(" in line_desc and "%)" in line_desc:
                        try:
                            rate_str = line_desc.split("(")[1].split("%)")[0]
                            tax_rate = Decimal(rate_str)
                        except (IndexError, ValueError):
                            pass

                    tax_details.append({
                        "tax_name": tax_name,
                        "tax_rate": tax_rate,
                        "tax_amount": line_amount
                    })
                    # Skip to the next line to avoid double-counting in subtotal
                    continue

                # This is a regular expense line
                subtotal_amount += line_amount
                if line_desc:
                    description_parts.append(line_desc)
                if account_name:
                    account_names.append(account_name.lower())

        description = " | ".join(description_parts) if description_parts else f"Purchase synced from QuickBooks. QB ID: {qb_purchase_id}"

        # Parse expense date
        expense_date = datetime.now(UTC)
        txn_date = qb_purchase.get("TxnDate")
        if txn_date and isinstance(txn_date, str):
            try:
                expense_date = datetime.fromisoformat(txn_date)
            except (ValueError, TypeError):
                pass

        # Map payment type back to PaymentMethod
        qb_payment_type = qb_purchase.get("PaymentType", "Cash")
        payment_method = ExpenseSchema.PAYMENT_TYPE_MAPPING.get(qb_payment_type, PaymentMethod.OTHER)

        # Improved category detection using account names and description
        category = ExpenseSchema._detect_category(account_names, description)

        expense = Expense(
            category=category,
            description=description,
            expense_date=expense_date,
            subtotal_amount=subtotal_amount,
            total_tax_amount=total_tax_amount,
            payment_method=payment_method,
            property_id=user_property.id if user_property else None,
            quickbooks_id=qb_purchase_id,
            last_synced_at=datetime.now(UTC)
        )

        # Create ExpenseTaxDetail objects
        tax_detail_objects = []
        for tax_info in tax_details:
            tax_detail_objects.append(ExpenseTaxDetail(
                tax_name=tax_info["tax_name"],
                tax_rate=tax_info["tax_rate"],
                tax_amount=tax_info["tax_amount"]
            ))

        return expense, tax_detail_objects

    @staticmethod
    def _normalize_tax_name(tax_rate_name: str) -> str:
        """
        Normalize QuickBooks tax rate names to standard Canadian tax codes.

        QuickBooks returns tax rate names like "HST ON", "GST", "PST BC", etc.
        This normalizes them to standard codes: GST, HST, PST, QST.

        Args:
            tax_rate_name: The tax rate name from QuickBooks (e.g., "HST ON", "GST/HST")

        Returns:
            Normalized tax code (GST, HST, PST, or QST), or original name if not recognized
        """
        name_upper = tax_rate_name.upper().strip()

        # Check for HST (includes provincial variants like "HST ON", "HST NB", etc.)
        if "HST" in name_upper:
            return "HST"

        # Check for GST (includes "GST/HST" which should map to GST if HST not present)
        if "GST" in name_upper:
            return "GST"

        # Check for QST (Quebec Sales Tax, also known as TVQ)
        if "QST" in name_upper or "TVQ" in name_upper:
            return "QST"

        # Check for PST (Provincial Sales Tax - BC, SK, MB)
        if "PST" in name_upper:
            return "PST"

        # Return original name if not a recognized Canadian tax
        return tax_rate_name

    @staticmethod
    def create_list_query(max_results: int = 100, start_position: int = 1) -> Dict[str, Any]:
        """Create query parameters for listing purchases."""
        return {
            "query": f"SELECT * FROM Purchase STARTPOSITION {start_position} MAXRESULTS {max_results}"
        }

    @staticmethod
    def extract_line_details(qb_purchase: Dict[str, Any]) -> Tuple[Decimal, str]:
        """Extract amount and description from QuickBooks purchase lines."""
        lines = qb_purchase.get("Line", [])
        total_amount = Decimal("0")
        description_parts = []

        for line in lines:
            if line.get("DetailType") == "AccountBasedExpenseLineDetail":
                line_amount = Decimal(str(line.get("Amount", 0)))
                total_amount += line_amount

                line_desc = line.get("Description", "")
                if line_desc:
                    description_parts.append(line_desc)

        description = " | ".join(description_parts) if description_parts else "QuickBooks Purchase"

        return total_amount, description

    @staticmethod
    def prepare_expense_data_for_creation(expense: Expense) -> Dict[str, Any]:
        """Prepare expense data from Brikli expense for QuickBooks creation."""
        return {
            "id": str(expense.id),
            "expense_date": expense.expense_date.strftime('%Y-%m-%d') if expense.expense_date else None,
            "description": expense.description or "Expense from Brikli",
            "total_amount": float(expense.subtotal_amount + expense.total_tax_amount),
            "tax_amount": float(expense.total_tax_amount),
            "category": expense.category or "General Expense"
        }

    @staticmethod
    def to_quickbooks_update(
        expense: Expense,
        qb_purchase_id: str,
        sync_token: str,
        paid_from_account_id: str,
        expense_account_id: str,
        tax_account_mapping: Optional[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        """Transform Brikli Expense to QuickBooks Purchase update format."""
        # Generate the full expense data using existing method
        expense_data = ExpenseSchema.to_quickbooks(
            expense, paid_from_account_id, expense_account_id, tax_account_mapping
        )

        # Add required fields for update
        expense_data["Id"] = qb_purchase_id
        expense_data["SyncToken"] = sync_token

        return expense_data

    @staticmethod
    def needs_update(qb_purchase: Dict[str, Any], expense: Expense) -> bool:
        """Check if QuickBooks purchase needs to be updated with Brikli expense data."""
        # Compare total amounts
        current_total = Decimal(str(qb_purchase.get("TotalAmt", 0)))
        expected_total = expense.subtotal_amount + expense.total_tax_amount

        # Compare payment type
        current_payment_type = qb_purchase.get("PaymentType", "Cash")
        expected_payment_type = ExpenseSchema.REVERSE_PAYMENT_TYPE_MAPPING.get(expense.payment_method, "Cash")

        # Compare date
        current_date = None
        txn_date = qb_purchase.get("TxnDate")
        if txn_date:
            try:
                current_date = datetime.fromisoformat(txn_date) if isinstance(txn_date, str) else txn_date
            except (ValueError, TypeError):
                pass

        # Compare descriptions in private note
        current_note = qb_purchase.get("PrivateNote", "")
        expected_desc = expense.description or "Expense from Brikli"

        return (
            current_total != expected_total or
            current_payment_type != expected_payment_type or
            (current_date and expense.expense_date and current_date.date() != expense.expense_date.date()) or
            (expected_desc not in current_note and "Expense from Brikli" not in current_note)
        )

    @staticmethod
    def validate_for_quickbooks(expense: Expense) -> Dict[str, str]:
        """
        Validate expense data for QuickBooks sync and return any issues.

        Returns:
            Dict with validation errors, empty if valid
        """
        errors = {}

        # Check required fields
        if not expense.subtotal_amount or expense.subtotal_amount <= 0:
            errors["subtotal_amount"] = "Expense subtotal must be greater than zero"

        if not expense.expense_date:
            errors["expense_date"] = "Expense date is required"

        if not expense.category:
            errors["category"] = "Expense category is required"

        # Validate payment method
        if expense.payment_method not in ExpenseSchema.REVERSE_PAYMENT_TYPE_MAPPING:
            errors["payment_method"] = f"Unsupported payment method: {expense.payment_method}"

        # Validate tax details
        if expense.taxes:
            calculated_tax = sum(tax.tax_amount for tax in expense.taxes)
            if abs(calculated_tax - expense.total_tax_amount) > Decimal("0.01"):
                errors["taxes"] = "Tax detail amounts don't match total tax amount"

        return errors

    @staticmethod
    def get_canadian_tax_accounts() -> Dict[str, str]:
        """
        Return default Canadian tax account names for common taxes.

        Note: These would need to be mapped to actual QuickBooks account IDs
        based on the user's chart of accounts.
        """
        return {
            "GST": "GST/HST Paid on Purchases",
            "PST": "PST Paid on Purchases",
            "HST": "GST/HST Paid on Purchases",
            "QST": "QST Paid on Purchases",  # Quebec Sales Tax
        }