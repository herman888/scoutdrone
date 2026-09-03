"""
Account Mapping Service for QuickBooks Integration.

This service manages the mapping between Brikli tax types (GST, HST, PST, QST)
and QuickBooks account IDs. It provides:
- Auto-detection of tax accounts from QuickBooks Chart of Accounts
- Manual mapping configuration
- Cached lookups for efficient sync operations

This is the key service that fixes the "No tax details found" warning
by providing actual account IDs instead of account names.
"""
import logging
from typing import Dict, Any, Optional, List

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select, col

from ....models.user import User
from ....models.accounting.integration import Integration
from ....models.accounting.quickbooks_account_mapping import QuickBooksAccountMapping
from .base_service import BaseQuickBooksService

logger = logging.getLogger(__name__)


# Canadian tax account detection patterns
# These patterns match common QuickBooks account names for Canadian taxes
CANADIAN_TAX_ACCOUNT_PATTERNS = {
    "GST": [
        "gst",
        "goods and services tax",
        "gst paid",
        "gst/hst paid",
        "gst on purchases",
        "gst/hst on purchases",
        "input tax credit",
        "itc"
    ],
    "HST": [
        "hst",
        "harmonized sales tax",
        "hst paid",
        "gst/hst paid",
        "hst on purchases",
        "gst/hst on purchases"
    ],
    "PST": [
        "pst",
        "provincial sales tax",
        "pst paid",
        "pst on purchases",
        "bc pst",
        "sk pst",
        "mb pst"
    ],
    "QST": [
        "qst",
        "quebec sales tax",
        "tvq",
        "qst paid",
        "qst on purchases"
    ]
}

# Valid QuickBooks account types for tax accounts (paid on purchases)
TAX_ACCOUNT_TYPES = ["Expense", "OtherCurrentAsset", "OtherExpense"]


class AccountMappingService(BaseQuickBooksService):
    """
    Service for managing QuickBooks account mappings.

    Provides functionality to:
    - Fetch all accounts from QuickBooks Chart of Accounts
    - Auto-detect Canadian tax accounts based on name patterns
    - Save/update/delete account mappings
    - Get tax account ID mappings for use in sync operations
    """

    async def fetch_all_accounts_from_qb(self) -> List[Dict[str, Any]]:
        """
        Fetch all accounts from QuickBooks Chart of Accounts.

        OPTIMIZATION: Uses session-level caching to avoid repeated API calls
        within the same sync session.

        Returns:
            List of account dictionaries with Id, Name, AccountType, etc.
        """
        await self.initialize()

        async def fetch_accounts():
            try:
                # Fetch accounts from QuickBooks
                response = await self._retry_operation(
                    lambda: self.client.list_accounts(max_results=500),
                    "fetch_accounts"
                )

                if not response or "QueryResponse" not in response:
                    logger.warning("No accounts found in QuickBooks response")
                    return []

                accounts = response["QueryResponse"].get("Account", [])
                logger.info(f"Fetched {len(accounts)} accounts from QuickBooks")

                return accounts

            except Exception as e:
                logger.error(f"Error fetching accounts from QuickBooks: {e}")
                raise

        # Use session cache to avoid repeated API calls
        return await self._get_or_cache_quickbooks_data("all_qb_accounts", fetch_accounts)

    async def get_tax_accounts(self) -> List[Dict[str, Any]]:
        """
        Get accounts that could be used for tax tracking.

        Filters accounts to only include expense-type accounts
        that are commonly used for tax paid on purchases.

        Returns:
            List of account dictionaries suitable for tax mapping
        """
        all_accounts = await self.fetch_all_accounts_from_qb()

        # Filter to accounts that could be used for tax tracking
        tax_eligible_accounts = [
            {
                "id": account.get("Id"),
                "name": account.get("Name"),
                "account_type": account.get("AccountType"),
                "fully_qualified_name": account.get("FullyQualifiedName"),
                "active": account.get("Active", True)
            }
            for account in all_accounts
            if account.get("AccountType") in TAX_ACCOUNT_TYPES
            and account.get("Active", True)
        ]

        logger.info(f"Found {len(tax_eligible_accounts)} tax-eligible accounts")
        return tax_eligible_accounts

    async def auto_detect_tax_accounts(self) -> Dict[str, Dict[str, Any]]:
        """
        Auto-detect Canadian tax accounts by matching name patterns.

        Scans the QuickBooks Chart of Accounts and attempts to match
        accounts to Canadian tax types (GST, HST, PST, QST) based on
        common naming patterns.

        Returns:
            Dict mapping tax codes to detected accounts:
            {
                "GST": {"id": "123", "name": "GST/HST Paid on Purchases", ...},
                "HST": {"id": "123", "name": "GST/HST Paid on Purchases", ...},
                ...
            }
        """
        await self.initialize()

        all_accounts = await self.fetch_all_accounts_from_qb()
        detected_mappings: Dict[str, Dict[str, Any]] = {}

        for account in all_accounts:
            account_name = account.get("Name", "").lower()
            account_type = account.get("AccountType", "")
            account_id = account.get("Id")

            # Only consider expense-type accounts
            if account_type not in TAX_ACCOUNT_TYPES:
                continue

            # Skip inactive accounts
            if not account.get("Active", True):
                continue

            # Try to match against each tax type's patterns
            for tax_code, patterns in CANADIAN_TAX_ACCOUNT_PATTERNS.items():
                # Skip if we already have a mapping for this tax code
                if tax_code in detected_mappings:
                    continue

                for pattern in patterns:
                    if pattern in account_name:
                        detected_mappings[tax_code] = {
                            "id": account_id,
                            "name": account.get("Name"),
                            "account_type": account_type,
                            "matched_pattern": pattern
                        }
                        logger.info(
                            f"Auto-detected {tax_code} account: "
                            f"{account.get('Name')} (ID: {account_id}) "
                            f"matched pattern '{pattern}'"
                        )
                        break

        logger.info(f"Auto-detected {len(detected_mappings)} tax account mappings")
        return detected_mappings

    async def save_auto_detected_mappings(self) -> List[QuickBooksAccountMapping]:
        """
        Auto-detect tax accounts and save them to the database.

        Returns:
            List of saved QuickBooksAccountMapping objects
        """
        await self.initialize()

        detected = await self.auto_detect_tax_accounts()
        saved_mappings: List[QuickBooksAccountMapping] = []

        for tax_code, account_info in detected.items():
            mapping = await self.save_account_mapping(
                mapping_type="tax_account",
                brikli_key=tax_code,
                quickbooks_account_id=account_info["id"],
                quickbooks_account_name=account_info["name"],
                quickbooks_account_type=account_info.get("account_type")
            )
            saved_mappings.append(mapping)

        return saved_mappings

    async def save_account_mapping(
        self,
        mapping_type: str,
        brikli_key: str,
        quickbooks_account_id: str,
        quickbooks_account_name: str,
        quickbooks_account_type: Optional[str] = None
    ) -> QuickBooksAccountMapping:
        """
        Save or update an account mapping.

        Args:
            mapping_type: Type of mapping (tax_account, expense_account, etc.)
            brikli_key: Brikli identifier (GST, PST, etc.)
            quickbooks_account_id: The numeric QuickBooks account ID
            quickbooks_account_name: Human-readable account name
            quickbooks_account_type: Optional QuickBooks account type

        Returns:
            The saved QuickBooksAccountMapping object
        """
        await self.initialize()

        # Check if mapping already exists
        existing = await self.session.scalar(
            select(QuickBooksAccountMapping).where(
                col(QuickBooksAccountMapping.integration_id) == self.integration_id,
                col(QuickBooksAccountMapping.mapping_type) == mapping_type,
                col(QuickBooksAccountMapping.brikli_key) == brikli_key
            )
        )

        if existing:
            # Update existing mapping
            existing.quickbooks_account_id = quickbooks_account_id
            existing.quickbooks_account_name = quickbooks_account_name
            existing.quickbooks_account_type = quickbooks_account_type
            self.session.add(existing)
            await self.session.commit()
            await self.session.refresh(existing)
            logger.info(
                f"Updated account mapping: {mapping_type}/{brikli_key} -> {quickbooks_account_id}"
            )
            return existing

        # Create new mapping
        mapping = QuickBooksAccountMapping(
            integration_id=self.integration_id,
            mapping_type=mapping_type,
            brikli_key=brikli_key,
            quickbooks_account_id=quickbooks_account_id,
            quickbooks_account_name=quickbooks_account_name,
            quickbooks_account_type=quickbooks_account_type
        )
        self.session.add(mapping)
        await self.session.commit()
        await self.session.refresh(mapping)

        logger.info(
            f"Created account mapping: {mapping_type}/{brikli_key} -> {quickbooks_account_id}"
        )
        return mapping

    async def delete_account_mapping(self, mapping_id: int) -> bool:
        """
        Delete an account mapping by ID.

        Args:
            mapping_id: The ID of the mapping to delete

        Returns:
            True if deleted, False if not found
        """
        await self.initialize()

        mapping = await self.session.scalar(
            select(QuickBooksAccountMapping).where(
                col(QuickBooksAccountMapping.id) == mapping_id,
                col(QuickBooksAccountMapping.integration_id) == self.integration_id
            )
        )

        if not mapping:
            return False

        await self.session.delete(mapping)
        await self.session.commit()

        logger.info(f"Deleted account mapping ID: {mapping_id}")
        return True

    async def get_all_mappings(self) -> List[QuickBooksAccountMapping]:
        """
        Get all account mappings for the user's integration.

        Returns:
            List of QuickBooksAccountMapping objects
        """
        await self.initialize()

        result = await self.session.scalars(
            select(QuickBooksAccountMapping).where(
                col(QuickBooksAccountMapping.integration_id) == self.integration_id
            ).order_by(
                col(QuickBooksAccountMapping.mapping_type),
                col(QuickBooksAccountMapping.brikli_key)
            )
        )
        return list(result.all())

    async def get_tax_account_id_mapping(self) -> Dict[str, str]:
        """
        Get tax account mappings as a dict of tax_code -> QuickBooks account ID.

        THIS IS THE KEY METHOD that fixes "No tax details found".

        Returns:
            Dict like {"GST": "123", "HST": "124", "PST": "125", "QST": "126"}
            where the values are actual QuickBooks account IDs.
        """
        await self.initialize()

        result = await self.session.scalars(
            select(QuickBooksAccountMapping).where(
                col(QuickBooksAccountMapping.integration_id) == self.integration_id,
                col(QuickBooksAccountMapping.mapping_type) == "tax_account"
            )
        )

        mappings = {
            mapping.brikli_key: mapping.quickbooks_account_id
            for mapping in result.all()
        }

        logger.debug(f"Retrieved tax account ID mapping: {mappings}")
        return mappings

    async def get_reverse_tax_mapping(self) -> Dict[str, str]:
        """
        Get reverse tax mapping: QuickBooks account ID -> tax code.

        This is used when pulling expenses from QuickBooks to identify
        which line items are tax lines.

        Returns:
            Dict like {"123": "GST", "124": "HST", "125": "PST", "126": "QST"}
        """
        forward_mapping = await self.get_tax_account_id_mapping()
        return {v: k for k, v in forward_mapping.items()}

    @property
    def client(self):
        """Access to the IntuitClient for QuickBooks API calls."""
        if not self._client:
            raise RuntimeError("Service not initialized. Call initialize() first.")
        return self._client
