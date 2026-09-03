"""
Messaging API Router

RESTful API endpoints for messaging between landlords and tenants:
- GET /messages/conversations - List conversations
- POST /messages/conversations - Create a new conversation
- GET /messages/conversations/{id}/messages - Get messages in a conversation
- POST /messages/messages - Send a message
- PUT /messages/messages/{id}/read - Mark message as read
- PUT /messages/conversations/{id}/read - Mark all messages in conversation as read
"""
import logging
from typing import List, Optional
from uuid import UUID

import sentry_sdk
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from Backend.api.auth import get_current_user
from Backend.database import get_session
from Backend.models.user import User
from Backend.models.message import Message

from .schemas import (
    ConversationResponse,
    ConversationListResponse,
    ConversationCreate,
    MessageResponse,
    MessageListResponse,
    MessageCreate,
    MessageUpdate,
    AnnouncementCreate,
)
from .service import MessagingService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/messages", tags=["Messages"])


# ========================================================================
# CONVERSATION ENDPOINTS
# ========================================================================

@router.get("/conversations", response_model=List[ConversationResponse])
async def list_conversations(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """
    List all conversations for the current user.
    
    For landlords: Returns conversations with all their tenants.
    For tenants: Returns their conversation with their landlord.
    """
    try:
        conversations = await MessagingService.list_conversations(
            current_user.id,
            current_user.user_type,
            session
        )
        
        # Enrich conversations with tenant/landlord info and unread counts
        # Relationships are eagerly loaded by the service, safe to access directly
        enriched_conversations = []
        for conv in conversations:
            # Get tenant info
            tenant_name = None
            tenant_email = None
            tenant_avatar_url = None
            if conv.tenant:
                # Try user info first (for tenants with portal access)
                if conv.tenant.user:
                    tenant_name = f"{conv.tenant.user.first_name or ''} {conv.tenant.user.last_name or ''}".strip() or conv.tenant.user.email
                    tenant_email = conv.tenant.user.email
                    tenant_avatar_url = conv.tenant.user.profile_image_url
                else:
                    # Fallback to tenant record
                    tenant_name = f"{conv.tenant.first_name or ''} {conv.tenant.last_name or ''}".strip() or conv.tenant.email
                    tenant_email = conv.tenant.email
                    tenant_avatar_url = conv.tenant.profile_image_url
            
            # Get landlord info
            landlord_name = None
            landlord_email = None
            landlord_avatar_url = None
            if conv.landlord:
                landlord_name = f"{conv.landlord.first_name or ''} {conv.landlord.last_name or ''}".strip() or conv.landlord.email
                landlord_email = conv.landlord.email
                landlord_avatar_url = conv.landlord.profile_image_url
            
            # Get last message
            last_message = None
            messages = conv.messages or []
            if messages:
                last_msg = sorted(messages, key=lambda m: m.created_at, reverse=True)[0]
                last_message = MessageResponse(
                    id=last_msg.id,
                    conversation_id=last_msg.conversation_id,
                    sender_id=last_msg.sender_id,
                    content=last_msg.content,
                    message_type=last_msg.message_type,
                    is_read=last_msg.is_read,
                    read_at=last_msg.read_at,
                    created_at=last_msg.created_at,
                    updated_at=last_msg.updated_at,
                    sender_name=None,
                    sender_email=None
                )
            
            # Count unread messages (excluding sender's own messages)
            unread_count = sum(
                1 for msg in messages
                if not msg.is_read and msg.sender_id != current_user.id
            )
            
            enriched_conversations.append(ConversationResponse(
                id=conv.id,
                landlord_id=conv.landlord_id,
                tenant_id=conv.tenant_id,
                created_at=conv.created_at,
                updated_at=conv.updated_at,
                tenant_name=tenant_name,
                tenant_email=tenant_email,
                tenant_avatar_url=tenant_avatar_url,
                landlord_name=landlord_name,
                landlord_email=landlord_email,
                landlord_avatar_url=landlord_avatar_url,
                last_message=last_message,
                unread_count=unread_count
            ))
        
        return enriched_conversations
        
    except Exception as e:
        logger.error(f"Error listing conversations: {str(e)}", exc_info=True)
        sentry_sdk.capture_exception(e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to list conversations"
        )


@router.post("/conversations", response_model=ConversationResponse, status_code=status.HTTP_201_CREATED)
async def create_conversation(
    conversation_data: ConversationCreate,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """
    Create a new conversation with a tenant (landlords only).
    """
    try:
        # Only landlords can create conversations
        if current_user.user_type not in ["LANDLORD", "ADMIN"]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only landlords can create conversations"
            )
        
        conversation = await MessagingService.get_or_create_conversation(
            current_user.id,
            conversation_data.tenant_id,
            session
        )
        
        # Enrich response
        tenant_name = None
        tenant_email = None
        tenant_avatar_url = None
        if conversation.tenant:
            if conversation.tenant.user:
                tenant_name = f"{conversation.tenant.user.first_name or ''} {conversation.tenant.user.last_name or ''}".strip() or conversation.tenant.user.email
                tenant_email = conversation.tenant.user.email
                tenant_avatar_url = conversation.tenant.user.profile_image_url
            else:
                tenant_name = f"{conversation.tenant.first_name or ''} {conversation.tenant.last_name or ''}".strip() or conversation.tenant.email
                tenant_email = conversation.tenant.email
                tenant_avatar_url = conversation.tenant.profile_image_url
        
        landlord_name = f"{current_user.first_name or ''} {current_user.last_name or ''}".strip() or current_user.email
        landlord_avatar_url = current_user.profile_image_url
        
        return ConversationResponse(
            id=conversation.id,
            landlord_id=conversation.landlord_id,
            tenant_id=conversation.tenant_id,
            created_at=conversation.created_at,
            updated_at=conversation.updated_at,
            tenant_name=tenant_name,
            tenant_email=tenant_email,
            tenant_avatar_url=tenant_avatar_url,
            landlord_name=landlord_name,
            landlord_email=current_user.email,
            landlord_avatar_url=landlord_avatar_url,
            last_message=None,
            unread_count=0
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating conversation: {str(e)}", exc_info=True)
        sentry_sdk.capture_exception(e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create conversation"
        )


# ========================================================================
# MESSAGE ENDPOINTS
# ========================================================================

@router.get("/conversations/{conversation_id}/messages", response_model=MessageListResponse)
async def list_messages(
    conversation_id: UUID,
    limit: int = Query(default=50, ge=1, le=100),
    before_id: Optional[UUID] = Query(default=None, description="Get messages before this message ID"),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """
    List messages in a conversation with pagination.
    """
    try:
        messages, has_more = await MessagingService.list_messages(
            conversation_id,
            current_user.id,
            current_user.user_type,
            session,
            limit=limit,
            before_id=before_id
        )
        
        # Mark conversation messages as read when viewing
        await MessagingService.mark_conversation_messages_as_read(
            conversation_id,
            current_user.id,
            current_user.user_type,
            session
        )
        
        # Enrich messages with sender info
        enriched_messages = []
        for msg in messages:
            sender_name = None
            sender_email = None
            if msg.sender:
                sender_name = f"{msg.sender.first_name or ''} {msg.sender.last_name or ''}".strip() or msg.sender.email
                sender_email = msg.sender.email
            
            enriched_messages.append(MessageResponse(
                id=msg.id,
                conversation_id=msg.conversation_id,
                sender_id=msg.sender_id,
                content=msg.content,
                message_type=msg.message_type,
                is_read=msg.is_read,
                read_at=msg.read_at,
                created_at=msg.created_at,
                updated_at=msg.updated_at,
                sender_name=sender_name,
                sender_email=sender_email
            ))
        
        return MessageListResponse(
            messages=enriched_messages,
            total=len(enriched_messages),
            has_more=has_more
        )
        
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Error listing messages: {str(e)}", exc_info=True)
        sentry_sdk.capture_exception(e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to list messages"
        )


@router.post("/messages", response_model=MessageResponse, status_code=status.HTTP_201_CREATED)
async def send_message(
    message_data: MessageCreate,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """
    Send a message in a conversation.
    If conversation_id is not provided, a new conversation will be created.
    """
    try:
        message = await MessagingService.send_message(
            conversation_id=message_data.conversation_id,
            tenant_id=message_data.tenant_id,
            sender_id=current_user.id,
            content=message_data.content,
            message_type=message_data.message_type,
            user_type=current_user.user_type,
            session=session
        )
        
        # Enrich response
        sender_name = f"{current_user.first_name or ''} {current_user.last_name or ''}".strip() or current_user.email
        
        return MessageResponse(
            id=message.id,
            conversation_id=message.conversation_id,
            sender_id=message.sender_id,
            content=message.content,
            message_type=message.message_type,
            is_read=message.is_read,
            read_at=message.read_at,
            created_at=message.created_at,
            updated_at=message.updated_at,
            sender_name=sender_name,
            sender_email=current_user.email
        )
        
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Error sending message: {str(e)}", exc_info=True)
        sentry_sdk.capture_exception(e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to send message"
        )


@router.put("/messages/{message_id}/read", response_model=MessageResponse)
async def mark_message_as_read(
    message_id: UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """
    Mark a specific message as read.
    """
    try:
        message = await MessagingService.mark_message_as_read(
            message_id,
            current_user.id,
            current_user.user_type,
            session
        )
        
        if not message:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Message not found"
            )
        
        # Enrich response
        sender_name = None
        sender_email = None
        if message.sender:
            sender_name = f"{message.sender.first_name or ''} {message.sender.last_name or ''}".strip() or message.sender.email
            sender_email = message.sender.email
        
        return MessageResponse(
            id=message.id,
            conversation_id=message.conversation_id,
            sender_id=message.sender_id,
            content=message.content,
            message_type=message.message_type,
            is_read=message.is_read,
            read_at=message.read_at,
            created_at=message.created_at,
            updated_at=message.updated_at,
            sender_name=sender_name,
            sender_email=sender_email
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error marking message as read: {str(e)}", exc_info=True)
        sentry_sdk.capture_exception(e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to mark message as read"
        )


@router.put("/conversations/{conversation_id}/read", response_model=dict)
async def mark_conversation_as_read(
    conversation_id: UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """
    Mark all messages in a conversation as read.
    """
    try:
        # Verify user has access to the conversation before proceeding
        conversation = await MessagingService.get_conversation(
            conversation_id, current_user.id, current_user.user_type, session
        )
        if not conversation:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Conversation not found or access denied"
            )
        
        count = await MessagingService.mark_conversation_messages_as_read(
            conversation_id,
            current_user.id,
            current_user.user_type,
            session
        )
        
        return {
            "conversation_id": str(conversation_id),
            "messages_marked_read": count
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error marking conversation as read: {str(e)}", exc_info=True)
        sentry_sdk.capture_exception(e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to mark conversation as read"
        )


@router.delete("/messages/{message_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_message(
    message_id: UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """
    Delete a message. Only the sender can delete their own messages.
    """
    try:
        # Get the message
        message = await MessagingService.get_message_by_id(message_id, session)
        
        if not message:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Message not found"
            )
        
        # Verify user is the sender
        if message.sender_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You can only delete your own messages"
            )
        
        # Delete the message
        await MessagingService.delete_message(message_id, session)
        
        return None
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting message: {str(e)}", exc_info=True)
        sentry_sdk.capture_exception(e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete message"
        )


# ========================================================================
# ANNOUNCEMENT ENDPOINTS (Future feature)
# ========================================================================

@router.post("/announcements", response_model=dict, status_code=status.HTTP_201_CREATED)
async def send_announcement(
    announcement_data: AnnouncementCreate,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """
    Send an announcement to tenants (landlords only).
    This is a placeholder for future announcement functionality.
    """
    # Only landlords can send announcements
    if current_user.user_type not in ["LANDLORD", "ADMIN"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only landlords can send announcements"
        )
    
    # TODO: Implement announcement functionality
    return {
        "message": "Announcement functionality coming soon",
        "content": announcement_data.content,
        "recipient_type": announcement_data.recipient_type
    }

