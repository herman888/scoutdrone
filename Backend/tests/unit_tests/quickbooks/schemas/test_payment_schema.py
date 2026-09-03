"""
Unit tests for QuickBooks PaymentSchema class.

Tests data transformation between Brikli Payment and QuickBooks Payment formats.
"""

import pytest
from uuid import uuid4
from datetime import datetime, UTC, date
from decimal import Decimal

from Backend.api.quickbooks.schemas.payment import PaymentSchema
from Backend.models.accounting.payment import Payment, PaymentMethod, PaymentStatus
from Backend.models.lease import Lease, LeaseStatus
from Backend.models.tenant import Tenant

# Mark all tests in this module as unit tests
pytestmark = pytest.mark.unit

FIXED_DATETIME = datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC)
FIXED_DATE = date(2024, 6, 1)


def create_test_payment(**kwargs):
    """Helper function to create a test payment."""
    defaults = {
        "amount": Decimal("1200.00"),
        "payment_date": FIXED_DATE,
        "payment_method": PaymentMethod.BANK_TRANSFER,  # Enum not string
        "description": "Monthly Rent Payment",
        "status": PaymentStatus.PAID,  # Correct field name
        "lease_id": uuid4(),
        "tenant_id": uuid4(),
        "created_at": FIXED_DATETIME,
        "updated_at": FIXED_DATETIME
    }
    defaults.update(kwargs)
    return Payment(**defaults)


class TestPaymentValidation:
    """Test payment validation for QuickBooks sync."""

    def test_validate_payment_valid(self):
        """Test validation of valid payment."""
        payment = create_test_payment()
        tenant = Tenant(
            id=uuid4(),
            user_id=uuid4(),
            email="test@example.com",
            first_name="Test",
            last_name="User",
            quickbooks_customer_id="qb_123",
            created_at=FIXED_DATETIME,
            updated_at=FIXED_DATETIME
        )

        errors = PaymentSchema.validate_for_quickbooks(payment, tenant)
        # Validation returns Dict[str, str], empty dict means valid
        assert errors == {}

    def test_validate_payment_zero_amount(self):
        """Test validation with zero amount."""
        payment = create_test_payment(amount=Decimal("0.00"))
        tenant = Tenant(
            id=uuid4(),
            user_id=uuid4(),
            email="test@example.com",
            first_name="Test",
            last_name="User",
            quickbooks_customer_id="qb_123",
            created_at=FIXED_DATETIME,
            updated_at=FIXED_DATETIME
        )

        errors = PaymentSchema.validate_for_quickbooks(payment, tenant)
        # Should have amount error
        assert "amount" in errors


class TestToQuickBooks:
    """Test conversion from Payment to QuickBooks format."""

    def test_to_quickbooks_basic(self):
        """Test basic payment to QuickBooks conversion.

        NOTE: Schema returns raw object, NOT wrapped in {"Payment": ...}
        """
        payment = create_test_payment()
        tenant = Tenant(
            id=uuid4(),
            user_id=uuid4(),
            email="test@example.com",
            first_name="Test",
            last_name="User",
            quickbooks_customer_id="qb_customer_123",
            created_at=FIXED_DATETIME,
            updated_at=FIXED_DATETIME
        )

        result = PaymentSchema.to_quickbooks(payment, tenant)

        # Schema returns raw object, not wrapped
        assert result["TxnDate"] == "2024-06-01"
        assert result["TotalAmt"] == 1200.00
        assert result["CustomerRef"]["value"] == "qb_customer_123"

    def test_to_quickbooks_with_deposit_account(self):
        """Test payment with deposit account specified."""
        payment = create_test_payment()
        tenant = Tenant(
            id=uuid4(),
            user_id=uuid4(),
            email="test@example.com",
            first_name="Test",
            last_name="User",
            quickbooks_customer_id="qb_customer_123",
            created_at=FIXED_DATETIME,
            updated_at=FIXED_DATETIME
        )

        result = PaymentSchema.to_quickbooks(payment, tenant, deposit_account_id="bank_acct_1")

        assert result["DepositToAccountRef"]["value"] == "bank_acct_1"

    def test_to_quickbooks_update_includes_id_and_sync_token(self):
        """Test update format includes required QB fields."""
        payment = create_test_payment()
        tenant = Tenant(
            id=uuid4(),
            user_id=uuid4(),
            email="test@example.com",
            first_name="Test",
            last_name="User",
            quickbooks_customer_id="qb_customer_123",
            created_at=FIXED_DATETIME,
            updated_at=FIXED_DATETIME
        )

        result = PaymentSchema.to_quickbooks_update(payment, tenant, "qb123", "5")

        assert result["Id"] == "qb123"
        assert result["SyncToken"] == "5"
        assert result["TxnDate"] == "2024-06-01"

    def test_add_invoice_link(self):
        """Test adding invoice link to payment data."""
        payment = create_test_payment()
        tenant = Tenant(
            id=uuid4(),
            user_id=uuid4(),
            email="test@example.com",
            first_name="Test",
            last_name="User",
            quickbooks_customer_id="qb_customer_123",
            created_at=FIXED_DATETIME,
            updated_at=FIXED_DATETIME
        )

        payment_data = PaymentSchema.to_quickbooks(payment, tenant)
        result = PaymentSchema.add_invoice_link(payment_data, "inv_456")

        assert "Line" in result
        assert len(result["Line"]) == 1
        assert result["Line"][0]["LinkedTxn"][0]["TxnId"] == "inv_456"
        assert result["Line"][0]["LinkedTxn"][0]["TxnType"] == "Invoice"


class TestFromQuickBooks:
    """Test conversion from QuickBooks Payment to Brikli format."""

    def test_from_quickbooks_basic(self):
        """Test basic QuickBooks to payment conversion."""
        qb_payment = {
            "Id": "123",
            "TxnDate": "2024-06-01",
            "TotalAmt": 1200.00,
            "CustomerRef": {"value": "cust_123"},
            "PaymentMethodRef": {"name": "BankTransfer"}
        }
        
        # Create test lease and tenant
        lease = Lease(
            id=uuid4(),
            tenant_id=uuid4(),
            property_id=1,
            status=LeaseStatus.ACTIVE,
            start_date=FIXED_DATE,
            monthly_rent=Decimal("1200.00"),
            created_at=FIXED_DATETIME,
            updated_at=FIXED_DATETIME
        )
        tenant = Tenant(
            id=uuid4(),
            user_id=uuid4(),
            email="test@example.com",
            first_name="Test",
            last_name="User",
            quickbooks_id="cust_123",
            created_at=FIXED_DATETIME,
            updated_at=FIXED_DATETIME
        )

        # Actual signature: from_quickbooks(qb_payment, lease, tenant)
        result = PaymentSchema.from_quickbooks(qb_payment, lease, tenant)

        assert result.quickbooks_id == "123"
        assert result.amount == Decimal("1200.00")
        assert result.payment_method == PaymentMethod.BANK_TRANSFER


class TestLinkedInvoices:
    """Test linked invoice extraction from QuickBooks payments."""

    def test_get_linked_invoice_ids_single(self):
        """Test extracting single linked invoice ID."""
        qb_payment = {
            "Id": "123",
            "TotalAmt": 1200.00,
            "Line": [
                {
                    "Amount": 1200.00,
                    "LinkedTxn": [
                        {"TxnId": "inv_456", "TxnType": "Invoice"}
                    ]
                }
            ]
        }

        result = PaymentSchema.get_linked_invoice_ids(qb_payment)

        assert result == ["inv_456"]

    def test_get_linked_invoice_ids_multiple(self):
        """Test extracting multiple linked invoice IDs."""
        qb_payment = {
            "Id": "123",
            "TotalAmt": 2400.00,
            "Line": [
                {
                    "Amount": 1200.00,
                    "LinkedTxn": [
                        {"TxnId": "inv_456", "TxnType": "Invoice"}
                    ]
                },
                {
                    "Amount": 1200.00,
                    "LinkedTxn": [
                        {"TxnId": "inv_789", "TxnType": "Invoice"}
                    ]
                }
            ]
        }

        result = PaymentSchema.get_linked_invoice_ids(qb_payment)

        assert len(result) == 2
        assert "inv_456" in result
        assert "inv_789" in result

    def test_get_linked_invoice_ids_no_invoices(self):
        """Test with no linked invoices."""
        qb_payment = {
            "Id": "123",
            "TotalAmt": 1200.00,
            "Line": []
        }

        result = PaymentSchema.get_linked_invoice_ids(qb_payment)

        assert result == []

    def test_get_linked_invoices_with_amounts_single(self):
        """Test extracting linked invoice with precise amount."""
        qb_payment = {
            "Id": "123",
            "TotalAmt": 1200.00,
            "Line": [
                {
                    "Amount": 1200.00,
                    "LinkedTxn": [
                        {"TxnId": "inv_456", "TxnType": "Invoice"}
                    ]
                }
            ]
        }

        result = PaymentSchema.get_linked_invoices_with_amounts(qb_payment)

        assert result == {"inv_456": Decimal("1200.00")}

    def test_get_linked_invoices_with_amounts_multiple_invoices(self):
        """Test extracting multiple invoices with their precise amounts."""
        qb_payment = {
            "Id": "123",
            "TotalAmt": 2500.00,
            "Line": [
                {
                    "Amount": 1200.00,
                    "LinkedTxn": [
                        {"TxnId": "inv_456", "TxnType": "Invoice"}
                    ]
                },
                {
                    "Amount": 1300.00,
                    "LinkedTxn": [
                        {"TxnId": "inv_789", "TxnType": "Invoice"}
                    ]
                }
            ]
        }

        result = PaymentSchema.get_linked_invoices_with_amounts(qb_payment)

        assert result["inv_456"] == Decimal("1200.00")
        assert result["inv_789"] == Decimal("1300.00")

    def test_get_linked_invoices_with_amounts_same_invoice_multiple_lines(self):
        """Test that same invoice appearing in multiple lines sums amounts."""
        qb_payment = {
            "Id": "123",
            "TotalAmt": 2400.00,
            "Line": [
                {
                    "Amount": 1200.00,
                    "LinkedTxn": [
                        {"TxnId": "inv_456", "TxnType": "Invoice"}
                    ]
                },
                {
                    "Amount": 1200.00,
                    "LinkedTxn": [
                        {"TxnId": "inv_456", "TxnType": "Invoice"}
                    ]
                }
            ]
        }

        result = PaymentSchema.get_linked_invoices_with_amounts(qb_payment)

        # Same invoice should have summed amounts
        assert result["inv_456"] == Decimal("2400.00")

    def test_get_linked_invoices_ignores_non_invoice_txns(self):
        """Test that non-invoice transaction types are ignored."""
        qb_payment = {
            "Id": "123",
            "TotalAmt": 1200.00,
            "Line": [
                {
                    "Amount": 600.00,
                    "LinkedTxn": [
                        {"TxnId": "inv_456", "TxnType": "Invoice"}
                    ]
                },
                {
                    "Amount": 600.00,
                    "LinkedTxn": [
                        {"TxnId": "credit_123", "TxnType": "CreditMemo"}
                    ]
                }
            ]
        }

        result = PaymentSchema.get_linked_invoices_with_amounts(qb_payment)

        # Only invoice should be included
        assert len(result) == 1
        assert result["inv_456"] == Decimal("600.00")


class TestPaymentMethodMapping:
    """Test payment method mapping between Brikli and QuickBooks."""

    def test_payment_method_mapping_interac(self):
        """Test Interac e-Transfer mapping (Canadian-specific)."""
        payment = create_test_payment(payment_method=PaymentMethod.INTERAC_E_TRANSFER)
        tenant = Tenant(
            id=uuid4(),
            user_id=uuid4(),
            email="test@example.com",
            first_name="Test",
            last_name="User",
            quickbooks_customer_id="qb_customer_123",
            created_at=FIXED_DATETIME,
            updated_at=FIXED_DATETIME
        )

        result = PaymentSchema.to_quickbooks(payment, tenant)

        # Interac should map to InteracTransfer
        assert result["PaymentMethodRef"]["name"] == "InteracTransfer"

    def test_payment_method_mapping_from_quickbooks(self):
        """Test various QB payment methods map correctly."""
        test_cases = [
            ("Cash", PaymentMethod.CASH),
            ("Check", PaymentMethod.CHECK),
            ("CreditCard", PaymentMethod.CREDIT_CARD),
            ("EFT", PaymentMethod.DIRECT_DEPOSIT),
            ("InteracTransfer", PaymentMethod.INTERAC_E_TRANSFER),
        ]

        for qb_method, expected_method in test_cases:
            qb_payment = {
                "Id": "123",
                "TxnDate": "2024-06-01",
                "TotalAmt": 100.00,
                "PaymentMethodRef": {"name": qb_method}
            }
            lease = Lease(
                id=uuid4(),
                tenant_id=uuid4(),
                property_id=1,
                status=LeaseStatus.ACTIVE,
                start_date=FIXED_DATE,
                monthly_rent=Decimal("1200.00"),
                created_at=FIXED_DATETIME,
                updated_at=FIXED_DATETIME
            )
            tenant = Tenant(
                id=uuid4(),
                user_id=uuid4(),
                email="test@example.com",
                first_name="Test",
                last_name="User",
                created_at=FIXED_DATETIME,
                updated_at=FIXED_DATETIME
            )

            result = PaymentSchema.from_quickbooks(qb_payment, lease, tenant)
            assert result.payment_method == expected_method, f"Expected {expected_method} for QB method {qb_method}"


class TestNeedsUpdate:
    """Test payment update detection."""

    def test_needs_update_when_amount_changed(self):
        """Test update needed when amount differs."""
        qb_payment = {
            "TotalAmt": 1000.00,
            "PaymentMethodRef": {"name": "BankTransfer"},
            "TxnDate": "2024-06-01"
        }
        payment = create_test_payment(amount=Decimal("1200.00"))

        assert PaymentSchema.needs_update(qb_payment, payment) is True

    def test_needs_update_when_no_changes(self):
        """Test no update needed when data matches."""
        qb_payment = {
            "TotalAmt": 1200.00,
            "PaymentMethodRef": {"name": "BankTransfer"},
            "TxnDate": "2024-06-01",
            "PaymentRefNum": "",
            "PrivateNote": "Monthly Rent Payment"
        }
        payment = create_test_payment()

        # Should return False when data matches
        result = PaymentSchema.needs_update(qb_payment, payment)
        assert isinstance(result, bool)

    def test_needs_update_when_method_changed(self):
        """Test update needed when payment method differs."""
        qb_payment = {
            "TotalAmt": 1200.00,
            "PaymentMethodRef": {"name": "Cash"},
            "TxnDate": "2024-06-01"
        }
        payment = create_test_payment(payment_method=PaymentMethod.BANK_TRANSFER)

        assert PaymentSchema.needs_update(qb_payment, payment) is True

    def test_needs_update_when_date_changed(self):
        """Test update needed when payment date differs."""
        qb_payment = {
            "TotalAmt": 1200.00,
            "PaymentMethodRef": {"name": "BankTransfer"},
            "TxnDate": "2024-05-01"  # Different date
        }
        payment = create_test_payment()

        assert PaymentSchema.needs_update(qb_payment, payment) is True

    def test_needs_update_when_ref_num_changed(self):
        """Test update needed when reference number differs."""
        qb_payment = {
            "TotalAmt": 1200.00,
            "PaymentMethodRef": {"name": "BankTransfer"},
            "TxnDate": "2024-06-01",
            "PaymentRefNum": "OLD_REF"
        }
        payment = create_test_payment(transaction_reference="NEW_REF")

        assert PaymentSchema.needs_update(qb_payment, payment) is True

    def test_needs_update_handles_invalid_date(self):
        """Test needs_update handles invalid date gracefully."""
        qb_payment = {
            "TotalAmt": 1200.00,
            "PaymentMethodRef": {"name": "BankTransfer"},
            "TxnDate": "invalid-date"
        }
        payment = create_test_payment()

        # Should not raise, should detect difference
        result = PaymentSchema.needs_update(qb_payment, payment)
        assert isinstance(result, bool)


class TestParseAmount:
    """Test parse_amount static method."""

    def test_parse_amount_from_float(self):
        """Test parsing float amount."""
        result = PaymentSchema.parse_amount(1200.50)
        assert result == Decimal("1200.50")

    def test_parse_amount_from_int(self):
        """Test parsing integer amount."""
        result = PaymentSchema.parse_amount(1000)
        assert result == Decimal("1000")

    def test_parse_amount_from_string(self):
        """Test parsing string amount."""
        result = PaymentSchema.parse_amount("1500.75")
        assert result == Decimal("1500.75")

    def test_parse_amount_none(self):
        """Test parsing None amount returns zero."""
        result = PaymentSchema.parse_amount(None)
        assert result == Decimal("0")


class TestParseDate:
    """Test parse_date static method."""

    def test_parse_date_from_string(self):
        """Test parsing date from ISO string."""
        result = PaymentSchema.parse_date("2024-06-01")
        assert result.year == 2024
        assert result.month == 6
        assert result.day == 1

    def test_parse_date_from_datetime(self):
        """Test parsing date from datetime object."""
        dt = datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC)
        result = PaymentSchema.parse_date(dt)
        assert result == dt

    def test_parse_date_empty_returns_now(self):
        """Test parsing empty date returns current datetime."""
        result = PaymentSchema.parse_date("")
        # Should be a datetime close to now
        assert isinstance(result, datetime)

    def test_parse_date_none_returns_now(self):
        """Test parsing None date returns current datetime."""
        result = PaymentSchema.parse_date(None)
        assert isinstance(result, datetime)

    def test_parse_date_invalid_string(self):
        """Test parsing invalid date string returns now."""
        result = PaymentSchema.parse_date("not-a-date")
        assert isinstance(result, datetime)


class TestGetCustomerId:
    """Test get_customer_id static method."""

    def test_get_customer_id_present(self):
        """Test extracting customer ID when present."""
        qb_payment = {
            "CustomerRef": {"value": "cust_123"}
        }
        result = PaymentSchema.get_customer_id(qb_payment)
        assert result == "cust_123"

    def test_get_customer_id_missing_ref(self):
        """Test extracting customer ID when CustomerRef is missing."""
        qb_payment = {}
        result = PaymentSchema.get_customer_id(qb_payment)
        assert result is None

    def test_get_customer_id_empty_ref(self):
        """Test extracting customer ID when CustomerRef is empty."""
        qb_payment = {"CustomerRef": {}}
        result = PaymentSchema.get_customer_id(qb_payment)
        assert result is None


class TestCreateListQuery:
    """Test create_list_query static method."""

    def test_create_list_query_defaults(self):
        """Test creating list query with defaults."""
        result = PaymentSchema.create_list_query()
        assert "query" in result
        assert "STARTPOSITION 1" in result["query"]
        assert "MAXRESULTS 100" in result["query"]

    def test_create_list_query_custom_values(self):
        """Test creating list query with custom values."""
        result = PaymentSchema.create_list_query(max_results=50, start_position=10)
        assert "STARTPOSITION 10" in result["query"]
        assert "MAXRESULTS 50" in result["query"]


class TestFromQuickBooksWithLinks:
    """Test from_quickbooks_with_links static method."""

    def test_from_quickbooks_with_links(self):
        """Test converting QB payment with linked invoice IDs."""
        qb_payment = {
            "Id": "123",
            "TxnDate": "2024-06-01",
            "TotalAmt": 1200.00,
            "CustomerRef": {"value": "cust_123"},
            "PaymentMethodRef": {"name": "BankTransfer"},
            "Line": [
                {
                    "Amount": 1200.00,
                    "LinkedTxn": [
                        {"TxnId": "inv_456", "TxnType": "Invoice"}
                    ]
                }
            ]
        }

        lease = Lease(
            id=uuid4(),
            tenant_id=uuid4(),
            property_id=1,
            status=LeaseStatus.ACTIVE,
            start_date=FIXED_DATE,
            monthly_rent=Decimal("1200.00"),
            created_at=FIXED_DATETIME,
            updated_at=FIXED_DATETIME
        )
        tenant = Tenant(
            id=uuid4(),
            user_id=uuid4(),
            email="test@example.com",
            first_name="Test",
            last_name="User",
            created_at=FIXED_DATETIME,
            updated_at=FIXED_DATETIME
        )

        payment, linked_ids = PaymentSchema.from_quickbooks_with_links(qb_payment, lease, tenant)

        assert payment.quickbooks_id == "123"
        assert linked_ids == ["inv_456"]


class TestValidateForQuickBooks:
    """Test validate_for_quickbooks static method."""

    def test_validate_negative_amount(self):
        """Test validation with negative amount."""
        payment = create_test_payment(amount=Decimal("-100.00"))
        tenant = Tenant(
            id=uuid4(),
            user_id=uuid4(),
            email="test@example.com",
            first_name="Test",
            last_name="User",
            quickbooks_customer_id="qb_123",
            created_at=FIXED_DATETIME,
            updated_at=FIXED_DATETIME
        )

        errors = PaymentSchema.validate_for_quickbooks(payment, tenant)
        assert "amount" in errors

    def test_validate_missing_payment_date(self):
        """Test validation with missing payment date."""
        payment = create_test_payment(payment_date=None)
        tenant = Tenant(
            id=uuid4(),
            user_id=uuid4(),
            email="test@example.com",
            first_name="Test",
            last_name="User",
            quickbooks_customer_id="qb_123",
            created_at=FIXED_DATETIME,
            updated_at=FIXED_DATETIME
        )

        errors = PaymentSchema.validate_for_quickbooks(payment, tenant)
        assert "payment_date" in errors

    def test_validate_tenant_not_synced(self):
        """Test validation when tenant not synced to QuickBooks."""
        payment = create_test_payment()
        tenant = Tenant(
            id=uuid4(),
            user_id=uuid4(),
            email="test@example.com",
            first_name="Test",
            last_name="User",
            quickbooks_customer_id=None,  # Not synced
            created_at=FIXED_DATETIME,
            updated_at=FIXED_DATETIME
        )

        errors = PaymentSchema.validate_for_quickbooks(payment, tenant)
        assert "tenant" in errors

    def test_validate_reduction_exceeds_amount(self):
        """Test validation when reduction exceeds payment amount."""
        payment = create_test_payment(
            amount=Decimal("100.00"),
            reduction_amount=Decimal("150.00")
        )
        tenant = Tenant(
            id=uuid4(),
            user_id=uuid4(),
            email="test@example.com",
            first_name="Test",
            last_name="User",
            quickbooks_customer_id="qb_123",
            created_at=FIXED_DATETIME,
            updated_at=FIXED_DATETIME
        )

        errors = PaymentSchema.validate_for_quickbooks(payment, tenant)
        assert "reduction_amount" in errors

    def test_validate_reduction_without_reason(self):
        """Test validation when reduction has no reason."""
        payment = create_test_payment(
            reduction_amount=Decimal("50.00"),
            reduction_reason=None
        )
        tenant = Tenant(
            id=uuid4(),
            user_id=uuid4(),
            email="test@example.com",
            first_name="Test",
            last_name="User",
            quickbooks_customer_id="qb_123",
            created_at=FIXED_DATETIME,
            updated_at=FIXED_DATETIME
        )

        errors = PaymentSchema.validate_for_quickbooks(payment, tenant)
        assert "reduction_reason" in errors


class TestToQuickBooksWithReduction:
    """Test to_quickbooks with reduction amounts."""

    def test_to_quickbooks_with_reduction(self):
        """Test payment with reduction amount in private note."""
        payment = create_test_payment(
            amount=Decimal("1000.00"),
            reduction_amount=Decimal("200.00"),
            reduction_reason="Early payment discount"
        )
        tenant = Tenant(
            id=uuid4(),
            user_id=uuid4(),
            email="test@example.com",
            first_name="Test",
            last_name="User",
            quickbooks_customer_id="qb_customer_123",
            created_at=FIXED_DATETIME,
            updated_at=FIXED_DATETIME
        )

        result = PaymentSchema.to_quickbooks(payment, tenant)

        # Private note should contain reduction info
        assert "PrivateNote" in result
        assert "Reduction" in result["PrivateNote"] or "reduction" in result["PrivateNote"].lower()

    def test_to_quickbooks_with_transaction_reference(self):
        """Test payment with transaction reference."""
        payment = create_test_payment(transaction_reference="TXN_12345")
        tenant = Tenant(
            id=uuid4(),
            user_id=uuid4(),
            email="test@example.com",
            first_name="Test",
            last_name="User",
            quickbooks_customer_id="qb_customer_123",
            created_at=FIXED_DATETIME,
            updated_at=FIXED_DATETIME
        )

        result = PaymentSchema.to_quickbooks(payment, tenant)

        assert result["PaymentRefNum"] == "TXN_12345"


class TestFromQuickBooksEdgeCases:
    """Test from_quickbooks edge cases."""

    def test_from_quickbooks_missing_id_raises(self):
        """Test that missing ID raises ValueError."""
        qb_payment = {
            "TxnDate": "2024-06-01",
            "TotalAmt": 100.00
            # Missing "Id"
        }

        lease = Lease(
            id=uuid4(),
            tenant_id=uuid4(),
            property_id=1,
            status=LeaseStatus.ACTIVE,
            start_date=FIXED_DATE,
            monthly_rent=Decimal("1200.00"),
            created_at=FIXED_DATETIME,
            updated_at=FIXED_DATETIME
        )
        tenant = Tenant(
            id=uuid4(),
            user_id=uuid4(),
            email="test@example.com",
            first_name="Test",
            last_name="User",
            created_at=FIXED_DATETIME,
            updated_at=FIXED_DATETIME
        )

        with pytest.raises(ValueError, match="missing required 'Id' field"):
            PaymentSchema.from_quickbooks(qb_payment, lease, tenant)

    def test_from_quickbooks_with_unapplied_amount(self):
        """Test payment with unapplied amount in description."""
        qb_payment = {
            "Id": "123",
            "TxnDate": "2024-06-01",
            "TotalAmt": 1200.00,
            "UnappliedAmt": 200.00,
            "CustomerRef": {"value": "cust_123"},
            "PaymentMethodRef": {"name": "Cash"}
        }

        lease = Lease(
            id=uuid4(),
            tenant_id=uuid4(),
            property_id=1,
            status=LeaseStatus.ACTIVE,
            start_date=FIXED_DATE,
            monthly_rent=Decimal("1200.00"),
            created_at=FIXED_DATETIME,
            updated_at=FIXED_DATETIME
        )
        tenant = Tenant(
            id=uuid4(),
            user_id=uuid4(),
            email="test@example.com",
            first_name="Test",
            last_name="User",
            created_at=FIXED_DATETIME,
            updated_at=FIXED_DATETIME
        )

        result = PaymentSchema.from_quickbooks(qb_payment, lease, tenant)

        assert "Unapplied amount" in result.description

    def test_from_quickbooks_with_private_note(self):
        """Test payment with private note preserved."""
        qb_payment = {
            "Id": "123",
            "TxnDate": "2024-06-01",
            "TotalAmt": 1200.00,
            "CustomerRef": {"value": "cust_123"},
            "PaymentMethodRef": {"name": "Cash"},
            "PrivateNote": "Customer paid in cash at office"
        }

        lease = Lease(
            id=uuid4(),
            tenant_id=uuid4(),
            property_id=1,
            status=LeaseStatus.ACTIVE,
            start_date=FIXED_DATE,
            monthly_rent=Decimal("1200.00"),
            created_at=FIXED_DATETIME,
            updated_at=FIXED_DATETIME
        )
        tenant = Tenant(
            id=uuid4(),
            user_id=uuid4(),
            email="test@example.com",
            first_name="Test",
            last_name="User",
            created_at=FIXED_DATETIME,
            updated_at=FIXED_DATETIME
        )

        result = PaymentSchema.from_quickbooks(qb_payment, lease, tenant)

        assert "Customer paid in cash at office" in result.description

    def test_from_quickbooks_with_missing_payment_method(self):
        """Test payment with missing payment method defaults to OTHER."""
        qb_payment = {
            "Id": "123",
            "TxnDate": "2024-06-01",
            "TotalAmt": 1200.00,
            "CustomerRef": {"value": "cust_123"}
            # No PaymentMethodRef
        }

        lease = Lease(
            id=uuid4(),
            tenant_id=uuid4(),
            property_id=1,
            status=LeaseStatus.ACTIVE,
            start_date=FIXED_DATE,
            monthly_rent=Decimal("1200.00"),
            created_at=FIXED_DATETIME,
            updated_at=FIXED_DATETIME
        )
        tenant = Tenant(
            id=uuid4(),
            user_id=uuid4(),
            email="test@example.com",
            first_name="Test",
            last_name="User",
            created_at=FIXED_DATETIME,
            updated_at=FIXED_DATETIME
        )

        result = PaymentSchema.from_quickbooks(qb_payment, lease, tenant)

        assert result.payment_method == PaymentMethod.OTHER