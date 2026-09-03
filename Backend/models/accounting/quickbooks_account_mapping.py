"""
QuickBooks Account Mapping model for storing user's QB account ID mappings.

This model stores the mapping between Brikli tax types (GST, HST, PST, QST)
and the actual QuickBooks account IDs from the user's Chart of Accounts.

This fixes the "No tax details found" warning caused by the previous
implementation using account names instead of IDs.
"""
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Column, DateTime, ForeignKey, Index, String, Integer, UniqueConstraint
from sqlmodel import Field, Relationship, SQLModel

from Backend.utils.datetime_utils import create_audit_datetime

if TYPE_CHECKING:
    from Backend.models.accounting.integration import Integration


class QuickBooksAccountMapping(SQLModel, table=True):
    """
    Maps Brikli tax types and account categories to QuickBooks account IDs.

    This allows proper tax line detection when syncing expenses from QuickBooks,
    fixing the issue where tax details were never detected because the code
    was comparing account names (e.g., "GST/HST Paid on Purchases") against
    numeric account IDs (e.g., "123").
    """

    __tablename__ = "quickbooks_account_mappings"
    __table_args__ = (
        UniqueConstraint(
            "integration_id", "mapping_type", "brikli_key",
            name="uq_qb_mapping_integration_type_key"
        ),
        Index("ix_qb_account_mapping_integration", "integration_id"),
        Index("ix_qb_account_mapping_type", "mapping_type"),
    )

    id: Optional[int] = Field(default=None, primary_key=True)

    # Foreign key to the user's QuickBooks integration
    integration_id: int = Field(
        sa_column=Column(
            Integer,
            ForeignKey("integrations.id", ondelete="CASCADE"),
            nullable=False,
            index=True
        ),
        description="Reference to the user's QuickBooks integration"
    )

    # Type of mapping: tax_account, expense_account, income_account, bank_account
    mapping_type: str = Field(
        sa_column=Column(String(50), nullable=False),
        description="Type of account mapping (tax_account, expense_account, etc.)"
    )

    # Brikli side identifier
    brikli_key: str = Field(
        sa_column=Column(String(100), nullable=False),
        description="Brikli identifier (e.g., 'GST', 'PST', 'HST', 'QST', 'default_expense')"
    )

    # QuickBooks side - the actual account ID
    quickbooks_account_id: str = Field(
        sa_column=Column(String(64), nullable=False),
        description="The numeric QuickBooks account ID"
    )

    # QuickBooks account name for display purposes
    quickbooks_account_name: str = Field(
        sa_column=Column(String(255), nullable=False),
        description="Human-readable QuickBooks account name"
    )

    # Optional account type for filtering
    quickbooks_account_type: Optional[str] = Field(
        default=None,
        sa_column=Column(String(100), nullable=True),
        description="QuickBooks account type (e.g., 'Expense', 'OtherCurrentAsset')"
    )

    # Audit timestamps
    created_at: datetime = Field(
        default_factory=create_audit_datetime,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    updated_at: datetime = Field(
        default_factory=create_audit_datetime,
        sa_column=Column(
            DateTime(timezone=True),
            nullable=False,
            onupdate=create_audit_datetime
        ),
    )

    # Relationship to integration (optional, for eager loading)
    integration: Optional["Integration"] = Relationship(
        back_populates="account_mappings"
    )

    def __repr__(self) -> str:
        return (
            f"<QuickBooksAccountMapping("
            f"id={self.id}, "
            f"type={self.mapping_type}, "
            f"key={self.brikli_key}, "
            f"qb_id={self.quickbooks_account_id}"
            f")>"
        )
