"""
Database models for messaging between landlords and tenants
"""
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Optional
from uuid import UUID as PythonUUID, uuid4

from sqlalchemy import Column, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlmodel import Field, Relationship, SQLModel

from Backend.utils.datetime_utils import create_audit_datetime

if TYPE_CHECKING:
    from Backend.models.user import User
    from Backend.models.tenant import Tenant


class MessageType(str, Enum):
    """Type of message"""
    DIRECT = "DIRECT"
    ANNOUNCEMENT = "ANNOUNCEMENT"
    SYSTEM = "SYSTEM"


class Conversation(SQLModel, table=True):
    """
    Conversation model representing a messaging thread between a landlord and tenant.
    Each conversation is unique per landlord-tenant pair.
    """
    __tablename__ = "conversations"  # type: ignore
    __table_args__ = (
        Index("ix_conversations_landlord_id", "landlord_id"),
        Index("ix_conversations_tenant_id", "tenant_id"),
        Index("ix_conversations_landlord_tenant", "landlord_id", "tenant_id", unique=True),
    )

    id: PythonUUID = Field(
        default_factory=uuid4,
        sa_column=Column(PG_UUID(as_uuid=True), primary_key=True)
    )

    # Landlord (property owner) who owns this conversation
    landlord_id: PythonUUID = Field(
        sa_column=Column(
            PG_UUID(as_uuid=True),
            ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            index=True
        ),
        description="Landlord (property owner) user ID"
    )

    # Tenant participating in this conversation
    tenant_id: int = Field(
        sa_column=Column(
            ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
            index=True
        ),
        description="Tenant ID"
    )

    # Timestamps
    created_at: datetime = Field(
        default_factory=create_audit_datetime,
        sa_column=Column(DateTime(timezone=True), nullable=False),
        description="When the conversation was created"
    )
    updated_at: datetime = Field(
        default_factory=create_audit_datetime,
        sa_column=Column(
            DateTime(timezone=True),
            nullable=False,
            onupdate=create_audit_datetime
        ),
        description="Last message timestamp"
    )

    # Relationships
    landlord: Optional["User"] = Relationship(
        sa_relationship_kwargs={"foreign_keys": "[Conversation.landlord_id]"}
    )
    tenant: Optional["Tenant"] = Relationship()
    messages: list["Message"] = Relationship(
        back_populates="conversation",
        sa_relationship_kwargs={"cascade": "all, delete-orphan", "order_by": "Message.created_at"}
    )


class Message(SQLModel, table=True):
    """
    Message model representing individual messages within a conversation.
    """
    __tablename__ = "messages"  # type: ignore
    __table_args__ = (
        Index("ix_messages_conversation_id", "conversation_id"),
        Index("ix_messages_sender_id", "sender_id"),
        Index("ix_messages_created_at", "created_at"),
    )

    id: PythonUUID = Field(
        default_factory=uuid4,
        sa_column=Column(PG_UUID(as_uuid=True), primary_key=True)
    )

    # Conversation this message belongs to
    conversation_id: PythonUUID = Field(
        sa_column=Column(
            PG_UUID(as_uuid=True),
            ForeignKey("conversations.id", ondelete="CASCADE"),
            nullable=False,
            index=True
        ),
        description="Conversation ID"
    )

    # Sender of the message (user_id from users table)
    sender_id: PythonUUID = Field(
        sa_column=Column(
            PG_UUID(as_uuid=True),
            ForeignKey("users.id", ondelete="SET NULL"),
            nullable=False,
            index=True
        ),
        description="User ID of the message sender"
    )

    # Message content
    content: str = Field(
        sa_column=Column(Text, nullable=False),
        description="Message content"
    )

    # Message type
    message_type: str = Field(
        default=MessageType.DIRECT.value,
        sa_column=Column(String(50), nullable=False),
        description="Type of message (DIRECT, ANNOUNCEMENT, SYSTEM)"
    )

    # Read status tracking
    is_read: bool = Field(
        default=False,
        description="Whether the message has been read by the recipient"
    )
    read_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
        description="When the message was read"
    )

    # Timestamps
    created_at: datetime = Field(
        default_factory=create_audit_datetime,
        sa_column=Column(DateTime(timezone=True), nullable=False, index=True),
        description="When the message was created"
    )
    updated_at: datetime = Field(
        default_factory=create_audit_datetime,
        sa_column=Column(
            DateTime(timezone=True),
            nullable=False,
            onupdate=create_audit_datetime
        ),
        description="Last update timestamp"
    )

    # Relationships
    conversation: Optional["Conversation"] = Relationship(back_populates="messages")
    sender: Optional["User"] = Relationship(
        sa_relationship_kwargs={"foreign_keys": "[Message.sender_id]"}
    )

