"""
Unit tests for QuickBooks ExpenseSchema class.

Tests data transformation between Brikli Expense and QuickBooks Purchase formats.
"""

import pytest
from uuid import uuid4
from datetime import datetime, UTC
from decimal import Decimal

from Backend.api.quickbooks.schemas.expense import ExpenseSchema
from Backend.models.accounting.expense import Expense
from Backend.models.accounting.payment import PaymentMethod
from Backend.models.property import Property, PropertyType
from Backend.models.enums import PropertyStatus

# Mark all tests in this module as unit tests
pytestmark = pytest.mark.unit

# Fixed datetime for deterministic testing
FIXED_DATETIME = datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC)


def create_test_expense(**kwargs):
    """Helper function to create a test expense with default values."""
    defaults = {
        "description": "Test Expense",
        "expense_date": FIXED_DATETIME,
        "subtotal_amount": Decimal("100.00"),
        "total_tax_amount": Decimal("0.00"),
        "category": "maintenance",
        "payment_method": PaymentMethod.CREDIT_CARD,
        "property_id": 1,
        "created_at": FIXED_DATETIME,
        "updated_at": FIXED_DATETIME
    }
    defaults.update(kwargs)
    return Expense(**defaults)


def create_test_property(**kwargs):
    """Helper function to create a test property."""
    defaults = {
        "id": 1,
        "user_id": uuid4(),
        "name": "Test Property",
        "property_type": PropertyType.RESIDENTIAL,
        "status": PropertyStatus.ACTIVE,
        "street_address": "123 Test St",
        "city": "Test City",
        "state": "CA",
        "zip_code": "12345",
        "created_at": FIXED_DATETIME,
        "updated_at": FIXED_DATETIME
    }
    defaults.update(kwargs)
    return Property(**defaults)


class TestExpenseValidation:
    """Test expense validation for QuickBooks sync."""

    def test_validate_expense_valid(self):
        """Test validation of valid expense."""
        expense = create_test_expense(
            description="Office supplies",
            subtotal_amount=Decimal("150.00"),
            expense_date=FIXED_DATETIME,
            category="office"
        )

        errors = ExpenseSchema.validate_for_quickbooks(expense)
        assert errors == {}

    def test_validate_expense_zero_amount(self):
        """Test validation with zero amount."""
        expense = create_test_expense(subtotal_amount=Decimal("0.00"))

        errors = ExpenseSchema.validate_for_quickbooks(expense)
        assert "subtotal_amount" in errors

    def test_validate_expense_negative_amount(self):
        """Test validation with negative amount."""
        expense = create_test_expense(subtotal_amount=Decimal("-50.00"))

        errors = ExpenseSchema.validate_for_quickbooks(expense)
        assert "subtotal_amount" in errors

    def test_validate_expense_missing_date(self):
        """Test validation with missing expense date."""
        expense = create_test_expense(expense_date=None)

        errors = ExpenseSchema.validate_for_quickbooks(expense)
        assert "expense_date" in errors

    def test_validate_expense_missing_category(self):
        """Test validation with missing category."""
        expense = create_test_expense(category=None)

        errors = ExpenseSchema.validate_for_quickbooks(expense)
        assert "category" in errors

    def test_validate_expense_large_amount(self):
        """Test validation with very large amount - should be valid."""
        expense = create_test_expense(subtotal_amount=Decimal("1000000.00"))

        errors = ExpenseSchema.validate_for_quickbooks(expense)
        # Large amounts are valid, no specific limit
        assert errors == {}


class TestToQuickBooksPurchase:
    """Test conversion from Expense to QuickBooks Purchase format."""

    def test_to_quickbooks_purchase_basic(self):
        """Test basic expense to QuickBooks purchase conversion."""
        expense = create_test_expense(
            description="Office supplies",
            subtotal_amount=Decimal("150.75"),
            expense_date=FIXED_DATETIME,
            category="office",
            payment_method=PaymentMethod.CREDIT_CARD
        )

        # to_quickbooks(expense, paid_from_account_id, expense_account_id, tax_account_mapping=None)
        result = ExpenseSchema.to_quickbooks(expense, "1", "2")

        assert "TxnDate" in result
        assert result["TxnDate"] == "2024-06-01"
        assert "Line" in result
        assert len(result["Line"]) >= 1
        assert result["AccountRef"]["value"] == "1"
        assert result["PaymentType"] == "CreditCard"

    def test_to_quickbooks_with_tax(self):
        """Test expense to QuickBooks conversion with tax."""
        expense = create_test_expense(
            description="Supplies with tax",
            subtotal_amount=Decimal("100.00"),
            total_tax_amount=Decimal("13.00"),
            expense_date=FIXED_DATETIME,
            category="office",
            payment_method=PaymentMethod.CREDIT_CARD
        )

        result = ExpenseSchema.to_quickbooks(expense, "1", "2")

        # Total should include tax
        assert result["TotalAmt"] == 113.00

    def test_to_quickbooks_update_includes_id_and_sync_token(self):
        """Test update format includes required QB fields."""
        expense = create_test_expense()

        # to_quickbooks_update(expense, qb_purchase_id, sync_token, paid_from_account_id, expense_account_id)
        result = ExpenseSchema.to_quickbooks_update(expense, "qb123", "5", "1", "2")

        assert result["Id"] == "qb123"
        assert result["SyncToken"] == "5"
        assert result["AccountRef"]["value"] == "1"

    def test_to_quickbooks_payment_method_mapping(self):
        """Test payment method is properly mapped."""
        test_cases = [
            (PaymentMethod.CREDIT_CARD, "CreditCard"),
            (PaymentMethod.CASH, "Cash"),
            (PaymentMethod.CHECK, "Check"),
        ]

        for brikli_method, expected_qb_method in test_cases:
            expense = create_test_expense(payment_method=brikli_method)
            result = ExpenseSchema.to_quickbooks(expense, "1", "2")
            assert result["PaymentType"] == expected_qb_method

    def test_to_quickbooks_other_payment_types_default_to_cash(self):
        """Test non-standard payment types default to valid QB type."""
        # BANK_TRANSFER maps to "Other" which is invalid for QB, so it falls back to "Cash"
        expense = create_test_expense(payment_method=PaymentMethod.BANK_TRANSFER)
        result = ExpenseSchema.to_quickbooks(expense, "1", "2")
        # BANK_TRANSFER maps to "Other" which is invalid, defaults to "Cash"
        assert result["PaymentType"] == "Cash"

    def test_to_quickbooks_line_description_includes_category(self):
        """Test that line description includes category."""
        expense = create_test_expense(
            description="Fix plumbing",
            category="maintenance"
        )

        result = ExpenseSchema.to_quickbooks(expense, "1", "2")

        line = result["Line"][0]
        # Category is mapped and included in description
        assert "Repairs and Maintenance" in line["Description"] or "Fix plumbing" in line["Description"]


class TestFromQuickBooksPurchase:
    """Test conversion from QuickBooks Purchase to Expense format."""

    def test_from_quickbooks_purchase_basic(self):
        """Test basic QuickBooks purchase to expense conversion."""
        qb_purchase = {
            "Id": "123",
            "TxnDate": "2024-06-01",
            "TotalAmt": 150.00,
            "PrivateNote": "Office supplies",
            "Line": [{
                "DetailType": "AccountBasedExpenseLineDetail",
                "Amount": 150.00,
                "Description": "Office supplies",
                "AccountBasedExpenseLineDetail": {
                    "AccountRef": {"value": "1", "name": "Office Expenses"}
                }
            }],
            "PaymentType": "CreditCard"
        }
        property_obj = create_test_property()

        expense, tax_details = ExpenseSchema.from_quickbooks(qb_purchase, property_obj)

        assert expense.quickbooks_id == "123"
        assert expense.property_id == property_obj.id
        assert "Office supplies" in expense.description
        assert expense.payment_method == PaymentMethod.CREDIT_CARD
        assert isinstance(tax_details, list)

    def test_from_quickbooks_purchase_payment_method_mapping(self):
        """Test payment method mapping from QuickBooks."""
        test_cases = [
            ("CreditCard", PaymentMethod.CREDIT_CARD),
            ("Check", PaymentMethod.CHECK),
            ("Cash", PaymentMethod.CASH),
            ("Other", PaymentMethod.OTHER)
        ]

        for qb_method, expected_method in test_cases:
            qb_purchase = {
                "Id": "123",
                "TxnDate": "2024-06-01",
                "TotalAmt": 100.00,
                "PaymentType": qb_method,
                "Line": [{
                    "DetailType": "AccountBasedExpenseLineDetail",
                    "Amount": 100.00
                }]
            }
            property_obj = create_test_property()

            expense, _ = ExpenseSchema.from_quickbooks(qb_purchase, property_obj)
            assert expense.payment_method == expected_method

    def test_from_quickbooks_purchase_missing_fields(self):
        """Test conversion with missing optional fields."""
        qb_purchase = {
            "Id": "123",
            "TotalAmt": 100.00,
            "Line": [{
                "DetailType": "AccountBasedExpenseLineDetail",
                "Amount": 100.00
            }]
        }
        property_obj = create_test_property()

        expense, _ = ExpenseSchema.from_quickbooks(qb_purchase, property_obj)

        assert expense.quickbooks_id == "123"
        assert expense.expense_date is not None
        assert expense.description is not None

    def test_from_quickbooks_purchase_multiple_lines(self):
        """Test conversion with multiple line items."""
        qb_purchase = {
            "Id": "123",
            "TxnDate": "2024-06-01",
            "TotalAmt": 300.00,
            "Line": [
                {
                    "DetailType": "AccountBasedExpenseLineDetail",
                    "Amount": 150.00,
                    "Description": "Office supplies - paper"
                },
                {
                    "DetailType": "AccountBasedExpenseLineDetail",
                    "Amount": 150.00,
                    "Description": "Office supplies - pens"
                }
            ]
        }
        property_obj = create_test_property()

        expense, _ = ExpenseSchema.from_quickbooks(qb_purchase, property_obj)

        assert expense.subtotal_amount + expense.total_tax_amount == Decimal("300.00")

    def test_from_quickbooks_without_property(self):
        """Test conversion without property (QB-synced expense)."""
        qb_purchase = {
            "Id": "123",
            "TxnDate": "2024-06-01",
            "TotalAmt": 100.00,
            "Line": [{
                "DetailType": "AccountBasedExpenseLineDetail",
                "Amount": 100.00
            }]
        }

        expense, _ = ExpenseSchema.from_quickbooks(qb_purchase, None)

        assert expense.quickbooks_id == "123"
        assert expense.property_id is None

    def test_from_quickbooks_with_tax_detail(self):
        """Test conversion extracts tax information from TxnTaxDetail."""
        qb_purchase = {
            "Id": "123",
            "TxnDate": "2024-06-01",
            "TotalAmt": 113.00,
            "Line": [{
                "DetailType": "AccountBasedExpenseLineDetail",
                "Amount": 100.00
            }],
            "TxnTaxDetail": {
                "TotalTax": 13.00,
                "TaxLine": [
                    {
                        "Amount": 13.00,
                        "DetailType": "TaxLineDetail",
                        "TaxLineDetail": {
                            "TaxRateRef": {"value": "1", "name": "HST ON"},
                            "PercentBased": True,
                            "TaxPercent": 13
                        }
                    }
                ]
            }
        }
        property_obj = create_test_property()

        expense, tax_details = ExpenseSchema.from_quickbooks(qb_purchase, property_obj)

        assert expense.total_tax_amount == Decimal("13.00")
        assert len(tax_details) == 1
        # tax_details are ExpenseTaxDetail objects with tax_amount field
        assert tax_details[0].tax_amount == Decimal("13.00")
        assert tax_details[0].tax_name == "HST"  # Normalized

    def test_from_quickbooks_missing_id_raises(self):
        """Test that missing ID raises ValueError."""
        qb_purchase = {
            "TotalAmt": 100.00,
            "Line": [{"DetailType": "AccountBasedExpenseLineDetail", "Amount": 100.00}]
        }

        with pytest.raises(ValueError, match="missing required 'Id' field"):
            ExpenseSchema.from_quickbooks(qb_purchase, None)


class TestExtractLineDetails:
    """Test line details extraction."""

    def test_extract_line_details_single_line(self):
        """Test extracting details from single line."""
        qb_purchase = {
            "Line": [{
                "DetailType": "AccountBasedExpenseLineDetail",
                "Amount": 100.00,
                "Description": "Test description"
            }]
        }

        amount, description = ExpenseSchema.extract_line_details(qb_purchase)

        assert amount == Decimal("100.00")
        assert description == "Test description"

    def test_extract_line_details_multiple_lines(self):
        """Test extracting details from multiple lines."""
        qb_purchase = {
            "Line": [
                {
                    "DetailType": "AccountBasedExpenseLineDetail",
                    "Amount": 50.00,
                    "Description": "Item 1"
                },
                {
                    "DetailType": "AccountBasedExpenseLineDetail",
                    "Amount": 75.00,
                    "Description": "Item 2"
                }
            ]
        }

        amount, description = ExpenseSchema.extract_line_details(qb_purchase)

        assert amount == Decimal("125.00")
        # Description joins multiple items
        assert "Item 1" in description and "Item 2" in description

    def test_extract_line_details_no_lines(self):
        """Test extracting details with no lines."""
        qb_purchase = {"Line": []}

        amount, description = ExpenseSchema.extract_line_details(qb_purchase)

        assert amount == Decimal("0")
        assert description == "QuickBooks Purchase"  # Default description

    def test_extract_line_details_only_counts_expense_lines(self):
        """Test that only AccountBasedExpenseLineDetail lines are counted."""
        qb_purchase = {
            "Line": [
                {
                    "DetailType": "AccountBasedExpenseLineDetail",
                    "Amount": 100.00,
                    "Description": "Item"
                },
                {
                    "DetailType": "SalesItemLineDetail",  # Different type
                    "Amount": 50.00
                }
            ]
        }

        amount, description = ExpenseSchema.extract_line_details(qb_purchase)

        # Should only count the AccountBasedExpenseLineDetail line
        assert amount == Decimal("100.00")


class TestNeedsUpdate:
    """Test expense update detection."""

    def test_needs_update_when_amount_changed(self):
        """Test update needed when amount differs."""
        qb_purchase = {
            "TotalAmt": 100.00,
            "TxnDate": "2024-06-01",
            "PaymentType": "CreditCard",
            "PrivateNote": "Test Expense"
        }
        expense = create_test_expense(
            subtotal_amount=Decimal("150.00"),
            total_tax_amount=Decimal("0.00")
        )

        assert ExpenseSchema.needs_update(qb_purchase, expense) is True

    def test_needs_update_when_date_changed(self):
        """Test update needed when date differs."""
        qb_purchase = {
            "TotalAmt": 100.00,
            "TxnDate": "2024-05-01",  # Different date
            "PaymentType": "CreditCard",
            "PrivateNote": "Test Expense"
        }
        expense = create_test_expense(
            subtotal_amount=Decimal("100.00"),
            total_tax_amount=Decimal("0.00")
        )

        assert ExpenseSchema.needs_update(qb_purchase, expense) is True

    def test_needs_update_when_payment_type_changed(self):
        """Test update needed when payment type differs."""
        qb_purchase = {
            "TotalAmt": 100.00,
            "TxnDate": "2024-06-01",
            "PaymentType": "Check",  # Different from CreditCard
            "PrivateNote": "Test Expense"
        }
        expense = create_test_expense(
            subtotal_amount=Decimal("100.00"),
            total_tax_amount=Decimal("0.00"),
            payment_method=PaymentMethod.CREDIT_CARD
        )

        assert ExpenseSchema.needs_update(qb_purchase, expense) is True

    def test_needs_update_when_no_changes(self):
        """Test no update needed when data matches."""
        qb_purchase = {
            "TotalAmt": 100.00,
            "TxnDate": "2024-06-01",
            "PaymentType": "CreditCard",
            "PrivateNote": "Test Expense"  # Matches expense.description
        }
        expense = create_test_expense(
            subtotal_amount=Decimal("100.00"),
            total_tax_amount=Decimal("0.00"),
            expense_date=FIXED_DATETIME,
            description="Test Expense",
            payment_method=PaymentMethod.CREDIT_CARD
        )

        result = ExpenseSchema.needs_update(qb_purchase, expense)
        assert result is False


class TestCreateListQuery:
    """Test query generation."""

    def test_create_list_query_default(self):
        """Test default list query."""
        query = ExpenseSchema.create_list_query()

        assert "query" in query
        assert "Purchase" in query["query"]
        assert "MAXRESULTS 100" in query["query"]
        assert "STARTPOSITION 1" in query["query"]

    def test_create_list_query_custom_params(self):
        """Test list query with custom parameters."""
        query = ExpenseSchema.create_list_query(max_results=50, start_position=10)

        assert "MAXRESULTS 50" in query["query"]
        assert "STARTPOSITION 10" in query["query"]


class TestCanadianTaxAccounts:
    """Test Canadian tax account mapping."""

    def test_get_canadian_tax_accounts(self):
        """Test getting Canadian tax account mapping."""
        accounts = ExpenseSchema.get_canadian_tax_accounts()

        assert isinstance(accounts, dict)
        assert "GST" in accounts
        assert "HST" in accounts
        assert "PST" in accounts
        assert "QST" in accounts

    def test_normalize_tax_name_hst(self):
        """Test HST normalization."""
        assert ExpenseSchema._normalize_tax_name("HST ON") == "HST"
        assert ExpenseSchema._normalize_tax_name("HST NB") == "HST"
        assert ExpenseSchema._normalize_tax_name("hst") == "HST"

    def test_normalize_tax_name_gst(self):
        """Test GST normalization."""
        assert ExpenseSchema._normalize_tax_name("GST") == "GST"
        # GST/HST contains HST, so it normalizes to HST (HST checked first in the code)
        assert ExpenseSchema._normalize_tax_name("GST/HST") == "HST"

    def test_normalize_tax_name_pst(self):
        """Test PST normalization."""
        assert ExpenseSchema._normalize_tax_name("PST BC") == "PST"
        assert ExpenseSchema._normalize_tax_name("PST SK") == "PST"

    def test_normalize_tax_name_qst(self):
        """Test QST normalization."""
        assert ExpenseSchema._normalize_tax_name("QST") == "QST"
        assert ExpenseSchema._normalize_tax_name("TVQ") == "QST"

    def test_normalize_tax_name_unknown(self):
        """Test unknown tax name is returned as-is."""
        assert ExpenseSchema._normalize_tax_name("Some Other Tax") == "Some Other Tax"


class TestCategoryDetection:
    """Test automatic category detection from QuickBooks data."""

    def test_detect_category_from_account_names_maintenance(self):
        """Test maintenance category detection from account names."""
        # Account names should be lowercase for matching
        category = ExpenseSchema._detect_category(["repairs and maintenance"], "Plumbing fix")
        assert category == "maintenance"

    def test_detect_category_from_account_names_utilities(self):
        """Test utilities category detection from account names."""
        category = ExpenseSchema._detect_category(["utilities"], "Electric bill")
        assert category == "utilities"

    def test_detect_category_from_account_names_insurance(self):
        """Test insurance category detection."""
        category = ExpenseSchema._detect_category(["insurance expense"], "Annual premium")
        assert category == "insurance"

    def test_detect_category_from_description(self):
        """Test category detection from description when account not matched."""
        # "plumbing" is a keyword that maps to maintenance
        category = ExpenseSchema._detect_category(["general expenses"], "plumbing repair for kitchen sink")
        assert category == "maintenance"

    def test_detect_category_default(self):
        """Test default category when nothing matches."""
        category = ExpenseSchema._detect_category([], "Random purchase")
        assert category == "other"

    def test_detect_category_multiple_accounts(self):
        """Test category detection with multiple account names."""
        # First matching account wins
        category = ExpenseSchema._detect_category(
            ["general expenses", "repair costs", "other"],
            "Some description"
        )
        assert category == "maintenance"  # "repair" matches maintenance


class TestPrepareExpenseDataForCreation:
    """Test expense data preparation for QuickBooks creation."""

    def test_prepare_expense_data_basic(self):
        """Test basic expense data preparation."""
        expense = create_test_expense(
            description="Office supplies",
            subtotal_amount=Decimal("100.00"),
            total_tax_amount=Decimal("13.00"),
            category="office"
        )

        result = ExpenseSchema.prepare_expense_data_for_creation(expense)

        assert result["description"] == "Office supplies"
        assert result["total_amount"] == 113.00
        assert result["tax_amount"] == 13.00
        assert result["category"] == "office"

    def test_prepare_expense_data_missing_description(self):
        """Test expense data with missing description gets default."""
        expense = create_test_expense(description=None)

        result = ExpenseSchema.prepare_expense_data_for_creation(expense)

        assert result["description"] == "Expense from Brikli"

    def test_prepare_expense_data_missing_category(self):
        """Test expense data with missing category gets default."""
        expense = create_test_expense(category=None)

        result = ExpenseSchema.prepare_expense_data_for_creation(expense)

        assert result["category"] == "General Expense"


class TestToQuickBooksWithTaxMapping:
    """Test expense to QuickBooks conversion with tax account mapping."""

    def test_to_quickbooks_with_tax_lines(self):
        """Test expense with tax details gets proper tax lines."""
        from Backend.models.accounting.expense import ExpenseTaxDetail

        expense = create_test_expense(
            description="Expense with tax",
            subtotal_amount=Decimal("100.00"),
            total_tax_amount=Decimal("13.00"),
            category="office",
            payment_method=PaymentMethod.CREDIT_CARD
        )
        # Add taxes list
        expense.taxes = [
            ExpenseTaxDetail(
                tax_name="HST",
                tax_rate=Decimal("13.00"),
                tax_amount=Decimal("13.00")
            )
        ]

        # Tax mapping with valid numeric account IDs
        tax_mapping = {"HST": "123"}

        result = ExpenseSchema.to_quickbooks(expense, "1", "2", tax_mapping)

        # Should have 2 lines: main expense + tax
        assert len(result["Line"]) == 2
        assert result["TotalAmt"] == 113.00

    def test_to_quickbooks_skips_invalid_tax_account_ids(self):
        """Test that non-numeric tax account IDs are skipped."""
        from Backend.models.accounting.expense import ExpenseTaxDetail

        expense = create_test_expense(
            description="Expense with tax",
            subtotal_amount=Decimal("100.00"),
            total_tax_amount=Decimal("5.00")
        )
        expense.taxes = [
            ExpenseTaxDetail(
                tax_name="GST",
                tax_rate=Decimal("5.00"),
                tax_amount=Decimal("5.00")
            )
        ]

        # Tax mapping with non-numeric account ID (invalid)
        tax_mapping = {"GST": "not-a-number"}

        result = ExpenseSchema.to_quickbooks(expense, "1", "2", tax_mapping)

        # Should only have main line since tax account ID is invalid
        assert len(result["Line"]) == 1

    def test_to_quickbooks_skips_zero_tax_amount(self):
        """Test that zero tax amounts don't create tax lines."""
        from Backend.models.accounting.expense import ExpenseTaxDetail

        expense = create_test_expense(
            description="Expense with zero tax",
            subtotal_amount=Decimal("100.00"),
            total_tax_amount=Decimal("0.00")
        )
        expense.taxes = [
            ExpenseTaxDetail(
                tax_name="GST",
                tax_rate=Decimal("5.00"),
                tax_amount=Decimal("0.00")  # Zero tax amount
            )
        ]

        tax_mapping = {"GST": "123"}

        result = ExpenseSchema.to_quickbooks(expense, "1", "2", tax_mapping)

        # Should only have main line since tax amount is zero
        assert len(result["Line"]) == 1

    def test_to_quickbooks_with_receipt_url_in_note(self):
        """Test that receipt URL is included in private note."""
        expense = create_test_expense(
            description="Expense with receipt",
            receipt_url="https://storage.example.com/receipts/123.pdf"
        )

        result = ExpenseSchema.to_quickbooks(expense, "1", "2")

        assert "Receipt:" in result["PrivateNote"]
        assert "https://storage.example.com/receipts/123.pdf" in result["PrivateNote"]


class TestFromQuickBooksWithFallbackTaxMapping:
    """Test expense from QuickBooks with fallback tax account mapping."""

    def test_from_quickbooks_with_tax_line_fallback(self):
        """Test tax extraction from line items when TxnTaxDetail is empty."""
        qb_purchase = {
            "Id": "123",
            "TxnDate": "2024-06-01",
            "TotalAmt": 105.00,
            "Line": [
                {
                    "DetailType": "AccountBasedExpenseLineDetail",
                    "Amount": 100.00,
                    "Description": "Main expense",
                    "AccountBasedExpenseLineDetail": {
                        "AccountRef": {"value": "1", "name": "Office Expenses"}
                    }
                },
                {
                    "DetailType": "AccountBasedExpenseLineDetail",
                    "Amount": 5.00,
                    "Description": "GST (5%)",
                    "AccountBasedExpenseLineDetail": {
                        "AccountRef": {"value": "999", "name": "GST Paid"}  # Tax account
                    }
                }
            ]
        }

        # Reverse tax mapping (account ID → tax code)
        tax_account_mapping = {"999": "GST"}

        expense, tax_details = ExpenseSchema.from_quickbooks(
            qb_purchase, None, tax_account_mapping
        )

        assert expense.subtotal_amount == Decimal("100.00")
        assert expense.total_tax_amount == Decimal("5.00")
        assert len(tax_details) == 1
        assert tax_details[0].tax_name == "GST"
        assert tax_details[0].tax_rate == Decimal("5")

    def test_from_quickbooks_derives_tax_name_from_percent(self):
        """Test tax name derivation from percentage when name missing."""
        qb_purchase = {
            "Id": "123",
            "TxnDate": "2024-06-01",
            "TotalAmt": 113.00,
            "Line": [{
                "DetailType": "AccountBasedExpenseLineDetail",
                "Amount": 100.00
            }],
            "TxnTaxDetail": {
                "TotalTax": 13.00,
                "TaxLine": [
                    {
                        "Amount": 13.00,
                        "DetailType": "TaxLineDetail",
                        "TaxLineDetail": {
                            "TaxRateRef": {"value": "1"},  # No name
                            "TaxPercent": 13
                        }
                    }
                ]
            }
        }

        expense, tax_details = ExpenseSchema.from_quickbooks(qb_purchase, None)

        assert len(tax_details) == 1
        assert tax_details[0].tax_name == "HST"  # 13% derives to HST

    def test_from_quickbooks_derives_gst_from_5_percent(self):
        """Test 5% tax rate derives to GST."""
        qb_purchase = {
            "Id": "123",
            "TotalAmt": 105.00,
            "Line": [{
                "DetailType": "AccountBasedExpenseLineDetail",
                "Amount": 100.00
            }],
            "TxnTaxDetail": {
                "TotalTax": 5.00,
                "TaxLine": [
                    {
                        "Amount": 5.00,
                        "DetailType": "TaxLineDetail",
                        "TaxLineDetail": {
                            "TaxRateRef": {"value": "1"},
                            "TaxPercent": 5
                        }
                    }
                ]
            }
        }

        expense, tax_details = ExpenseSchema.from_quickbooks(qb_purchase, None)

        assert tax_details[0].tax_name == "GST"

    def test_from_quickbooks_skips_zero_tax_lines(self):
        """Test that zero amount and percent tax lines are skipped."""
        qb_purchase = {
            "Id": "123",
            "TotalAmt": 100.00,
            "Line": [{
                "DetailType": "AccountBasedExpenseLineDetail",
                "Amount": 100.00
            }],
            "TxnTaxDetail": {
                "TotalTax": 0.00,
                "TaxLine": [
                    {
                        "Amount": 0.00,
                        "DetailType": "TaxLineDetail",
                        "TaxLineDetail": {
                            "TaxRateRef": {"value": "1", "name": "Exempt"},
                            "TaxPercent": 0
                        }
                    }
                ]
            }
        }

        expense, tax_details = ExpenseSchema.from_quickbooks(qb_purchase, None)

        assert len(tax_details) == 0
        assert expense.total_tax_amount == Decimal("0")


class TestNeedsUpdateEdgeCases:
    """Test edge cases for update detection."""

    def test_needs_update_handles_invalid_date(self):
        """Test update detection handles invalid date gracefully."""
        qb_purchase = {
            "TotalAmt": 100.00,
            "TxnDate": "invalid-date",
            "PaymentType": "CreditCard",
            "PrivateNote": "Test Expense"
        }
        expense = create_test_expense(
            subtotal_amount=Decimal("100.00"),
            total_tax_amount=Decimal("0.00")
        )

        # Should not raise
        result = ExpenseSchema.needs_update(qb_purchase, expense)
        assert isinstance(result, bool)

    def test_needs_update_handles_missing_date(self):
        """Test update detection handles missing date gracefully."""
        qb_purchase = {
            "TotalAmt": 100.00,
            "PaymentType": "CreditCard",
            "PrivateNote": "Test Expense"
            # No TxnDate
        }
        expense = create_test_expense(
            subtotal_amount=Decimal("100.00"),
            total_tax_amount=Decimal("0.00")
        )

        # Should not raise
        result = ExpenseSchema.needs_update(qb_purchase, expense)
        assert isinstance(result, bool)


class TestTaxValidation:
    """Test tax detail validation in validation method."""

    def test_validate_expense_with_mismatched_tax_totals(self):
        """Test validation when tax details don't match total."""
        from Backend.models.accounting.expense import ExpenseTaxDetail

        expense = create_test_expense(
            subtotal_amount=Decimal("100.00"),
            total_tax_amount=Decimal("13.00")  # Says 13
        )
        expense.taxes = [
            ExpenseTaxDetail(
                tax_name="HST",
                tax_rate=Decimal("13.00"),
                tax_amount=Decimal("10.00")  # But only 10 in details
            )
        ]

        errors = ExpenseSchema.validate_for_quickbooks(expense)

        assert "taxes" in errors


class TestCategoryMappingConstants:
    """Test category mapping constants."""

    def test_category_mapping_exists(self):
        """Test that category mapping contains expected keys."""
        mapping = ExpenseSchema.CATEGORY_MAPPING

        assert "maintenance" in mapping
        assert "utilities" in mapping
        assert "taxes" in mapping
        assert "insurance" in mapping

    def test_qb_account_to_category_mapping_exists(self):
        """Test that QB account to category mapping has expected entries."""
        mapping = ExpenseSchema.QB_ACCOUNT_TO_CATEGORY

        assert "repair" in mapping
        assert "utilities" in mapping
        assert "insurance" in mapping
        assert "legal" in mapping

    def test_payment_type_mapping_exists(self):
        """Test payment type mappings exist and are correct."""
        assert ExpenseSchema.PAYMENT_TYPE_MAPPING["Cash"] == PaymentMethod.CASH
        assert ExpenseSchema.PAYMENT_TYPE_MAPPING["Check"] == PaymentMethod.CHECK
        assert ExpenseSchema.PAYMENT_TYPE_MAPPING["CreditCard"] == PaymentMethod.CREDIT_CARD

    def test_reverse_payment_type_mapping_exists(self):
        """Test reverse payment type mappings exist and are correct."""
        assert ExpenseSchema.REVERSE_PAYMENT_TYPE_MAPPING[PaymentMethod.CASH] == "Cash"
        assert ExpenseSchema.REVERSE_PAYMENT_TYPE_MAPPING[PaymentMethod.CHECK] == "Check"
        assert ExpenseSchema.REVERSE_PAYMENT_TYPE_MAPPING[PaymentMethod.CREDIT_CARD] == "CreditCard"
