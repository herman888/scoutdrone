"""
Messaging API Schemas

Pydantic models for request/response validation in the messaging API.
"""
from datetime import datetime
from typing import Optional, List
from uuid import UUID

from pydantic import BaseModel, Field


# ========================================================================
# CONVERSATION SCHEMAS
# ========================================================================

class ConversationResponse(BaseModel):
    """Response model for a conversation"""
    id: UUID
    landlord_id: UUID
    tenant_id: int
    created_at: datetime
    updated_at: datetime
    
    # Enriched fields
    tenant_name: Optional[str] = None
    tenant_email: Optional[str] = None
    tenant_avatar_url: Optional[str] = None
    landlord_name: Optional[str] = None
    landlord_email: Optional[str] = None
    landlord_avatar_url: Optional[str] = None
    last_message: Optional["MessageResponse"] = None
    unread_count: int = 0
    
    class Config:
        from_attributes = True


class ConversationCreate(BaseModel):
    """Request model for creating a conversation"""
    tenant_id: int = Field(..., description="Tenant ID to start conversation with")


# ========================================================================
# MESSAGE SCHEMAS
# ========================================================================

class MessageResponse(BaseModel):
    """Response model for a message"""
    id: UUID
    conversation_id: UUID
    sender_id: UUID
    content: str
    message_type: str
    is_read: bool
    read_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    
    # Enriched fields
    sender_name: Optional[str] = None
    sender_email: Optional[str] = None
    
    class Config:
        from_attributes = True


class MessageCreate(BaseModel):
    """Request model for creating a message"""
    conversation_id: Optional[UUID] = Field(None, description="Conversation ID (optional if creating new conversation)")
    tenant_id: Optional[int] = Field(None, description="Tenant ID (required if creating new conversation)")
    content: str = Field(..., min_length=1, max_length=10000, description="Message content")
    message_type: str = Field(default="DIRECT", description="Message type: DIRECT, ANNOUNCEMENT, or SYSTEM")


class MessageUpdate(BaseModel):
    """Request model for updating a message (e.g., marking as read)"""
    is_read: Optional[bool] = None


class AnnouncementCreate(BaseModel):
    """Request model for creating an announcement"""
    content: str = Field(..., min_length=1, max_length=10000, description="Announcement content")
    recipient_type: Optional[str] = Field(None, description="Recipient type filter: 'all', 'tenants', or specific tenant_id")


# ========================================================================
# LIST RESPONSES
# ========================================================================

class ConversationListResponse(BaseModel):
    """Response model for a list of conversations"""
    conversations: List[ConversationResponse]
    total: int


class MessageListResponse(BaseModel):
    """Response model for a list of messages"""
    messages: List[MessageResponse]
    total: int
    has_more: bool = False

