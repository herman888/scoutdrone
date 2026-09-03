"""
Messaging Service

Business logic for the messaging system including:
- Creating and managing conversations
- Sending and retrieving messages
- Marking messages as read
- Auto-creating conversations
"""
import logging
from datetime import datetime, timezone
from typing import List, Optional
from uuid import UUID

import sentry_sdk
from sqlalchemy import select, func, and_, or_, desc
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlmodel import col

from Backend.models.message import Conversation, Message, MessageType
from Backend.models.tenant import Tenant
from Backend.models.user import User
from Backend.models.enums import UserType
from Backend.models.property import Property

logger = logging.getLogger(__name__)


class MessagingService:
    """Service class for messaging management"""
    
    @staticmethod
    async def get_or_create_conversation(
        landlord_id: UUID,
        tenant_id: int,
        session: AsyncSession
    ) -> Conversation:
        """
        Get or create a conversation between a landlord and tenant.
        
        Args:
            landlord_id: UUID of the landlord
            tenant_id: ID of the tenant
            session: Database session
            
        Returns:
            Conversation object with tenant relationship eagerly loaded
        """
        try:
            # Check if conversation already exists - eagerly load tenant and user relationships
            stmt = (
                select(Conversation)
                .where(
                    and_(
                        col(Conversation.landlord_id) == landlord_id,
                        col(Conversation.tenant_id) == tenant_id
                    )
                )
                .options(
                    selectinload(getattr(Conversation, "tenant")).selectinload(getattr(Tenant, "user"))
                )
            )
            result = await session.execute(stmt)
            conversation = result.scalar_one_or_none()
            
            if conversation:
                return conversation
            
            # Create new conversation
            conversation = Conversation(
                landlord_id=landlord_id,
                tenant_id=tenant_id
            )
            session.add(conversation)
            await session.commit()
            
            # Refresh with eager loading
            await session.refresh(
                conversation,
                attribute_names=['tenant']
            )
            
            # Ensure tenant.user is also loaded
            stmt = (
                select(Conversation)
                .where(col(Conversation.id) == conversation.id)
                .options(
                    selectinload(getattr(Conversation, "tenant")).selectinload(getattr(Tenant, "user"))
                )
            )
            result = await session.execute(stmt)
            conversation = result.scalar_one()
            
            logger.info(f"Created conversation {conversation.id} between landlord {landlord_id} and tenant {tenant_id}")
            return conversation
            
        except IntegrityError as e:
            # Handle race condition: if two requests create conversation simultaneously
            await session.rollback()
            error_str = str(e).lower()
            if "unique constraint" in error_str or "duplicate key" in error_str:
                # Conversation was created by another request, fetch it with eager loading
                logger.info(f"Conversation already exists (race condition), fetching existing conversation")
                stmt = (
                    select(Conversation)
                    .where(
                        and_(
                            col(Conversation.landlord_id) == landlord_id,
                            col(Conversation.tenant_id) == tenant_id
                        )
                    )
                    .options(
                        selectinload(getattr(Conversation, "tenant")).selectinload(getattr(Tenant, "user"))
                    )
                )
                result = await session.execute(stmt)
                conversation = result.scalar_one_or_none()
                if conversation:
                    return conversation
            # Re-raise if we can't recover
            logger.error(f"IntegrityError creating conversation: {str(e)}", exc_info=True)
            sentry_sdk.capture_exception(e)
            raise
        except Exception as e:
            await session.rollback()
            logger.error(f"Error creating conversation: {str(e)}", exc_info=True)
            sentry_sdk.capture_exception(e)
            raise
    
    @staticmethod
    async def list_conversations(
        user_id: UUID,
        user_type: str,
        session: AsyncSession
    ) -> List[Conversation]:
        """
        List all conversations for a user (landlord or tenant).
        
        Args:
            user_id: UUID of the current user
            user_type: Type of user (LANDLORD, TENANT, etc.)
            session: Database session
            
        Returns:
            List of Conversation objects
        """
        try:
            if user_type in (UserType.LANDLORD.value, UserType.ADMIN.value):
                # Landlords see conversations where they are the landlord
                stmt = (
                    select(Conversation)
                    .where(col(Conversation.landlord_id) == user_id)
                    .options(
                        selectinload(getattr(Conversation, "tenant")).selectinload(getattr(Tenant, "user")),
                        selectinload(getattr(Conversation, "messages"))
                    )
                    .order_by(desc(col(Conversation.updated_at)))
                )
            else:
                # Tenants see conversations where they are the tenant
                stmt = (
                    select(Conversation)
                    .join(Tenant, col(Conversation.tenant_id) == col(Tenant.id))
                    .where(col(Tenant.user_id) == user_id)
                    .options(
                        selectinload(getattr(Conversation, "tenant")).selectinload(getattr(Tenant, "user")),
                        selectinload(getattr(Conversation, "landlord")),
                        selectinload(getattr(Conversation, "messages"))
                    )
                    .order_by(desc(col(Conversation.updated_at)))
                )
            
            result = await session.execute(stmt)
            conversations = result.scalars().all()
            
            return list(conversations)
            
        except Exception as e:
            logger.error(f"Error listing conversations: {str(e)}", exc_info=True)
            sentry_sdk.capture_exception(e)
            raise
    
    @staticmethod
    async def get_conversation(
        conversation_id: UUID,
        user_id: UUID,
        user_type: str,
        session: AsyncSession
    ) -> Optional[Conversation]:
        """
        Get a specific conversation by ID, ensuring user has access.
        
        Args:
            conversation_id: UUID of the conversation
            user_id: UUID of the current user
            user_type: Type of user
            session: Database session
            
        Returns:
            Conversation object or None if not found/unauthorized
        """
        try:
            stmt = (
                select(Conversation)
                .where(col(Conversation.id) == conversation_id)
                .options(
                    selectinload(getattr(Conversation, "tenant")).selectinload(getattr(Tenant, "user")),
                    selectinload(getattr(Conversation, "landlord")),
                    selectinload(getattr(Conversation, "messages"))
                )
            )
            result = await session.execute(stmt)
            conversation = result.scalar_one_or_none()
            
            if not conversation:
                return None
            
            # Verify access
            if user_type == UserType.LANDLORD or user_type == UserType.ADMIN:
                if conversation.landlord_id != user_id:
                    return None
            else:
                # For tenants, check if they are the tenant in this conversation
                if not conversation.tenant or conversation.tenant.user_id != user_id:
                    return None
            
            return conversation
            
        except Exception as e:
            logger.error(f"Error getting conversation: {str(e)}", exc_info=True)
            sentry_sdk.capture_exception(e)
            raise
    
    @staticmethod
    async def send_message(
        conversation_id: Optional[UUID],
        tenant_id: Optional[int],
        sender_id: UUID,
        content: str,
        message_type: str,
        user_type: str,
        session: AsyncSession
    ) -> Message:
        """
        Send a message in a conversation.
        
        Args:
            conversation_id: UUID of the conversation (optional if creating new)
            tenant_id: ID of the tenant (required if creating new conversation)
            sender_id: UUID of the message sender
            content: Message content
            message_type: Type of message
            user_type: Type of user sending the message
            session: Database session
            
        Returns:
            Created Message object
        """
        try:
            # Get or create conversation
            if conversation_id:
                conversation = await MessagingService.get_conversation(
                    conversation_id, sender_id, user_type, session
                )
                if not conversation:
                    raise ValueError("Conversation not found or access denied")
            else:
                if not tenant_id:
                    raise ValueError("tenant_id is required when creating a new conversation")
                
                # For landlords, use their user_id as landlord_id
                # For tenants, we need to find their landlord
                if user_type == UserType.LANDLORD or user_type == UserType.ADMIN:
                    landlord_id = sender_id
                else:
                    # Find the tenant's landlord through their property
                    tenant_stmt = select(Tenant).where(col(Tenant.id) == tenant_id)
                    tenant_result = await session.execute(tenant_stmt)
                    tenant = tenant_result.scalar_one_or_none()
                    
                    if not tenant or not tenant.current_property_id:
                        raise ValueError("Tenant not found or has no property")
                    
                    property_stmt = select(Property).where(col(Property.id) == tenant.current_property_id)
                    property_result = await session.execute(property_stmt)
                    property_obj = property_result.scalar_one_or_none()
                    
                    if not property_obj:
                        raise ValueError("Property not found")
                    
                    landlord_id = property_obj.user_id
                
                conversation = await MessagingService.get_or_create_conversation(
                    landlord_id, tenant_id, session
                )
            
            # Validate and convert message_type to enum
            try:
                validated_message_type = MessageType(message_type)
            except ValueError:
                raise ValueError(f"Invalid message_type: {message_type}. Must be one of {[e.value for e in MessageType]}")
            
            # Create message
            message = Message(
                conversation_id=conversation.id,
                sender_id=sender_id,
                content=content,
                message_type=validated_message_type.value
            )
            
            session.add(message)
            await session.commit()
            await session.refresh(message)
            
            logger.info(f"Created message {message.id} in conversation {conversation.id}")
            return message
            
        except Exception as e:
            await session.rollback()
            logger.error(f"Error sending message: {str(e)}", exc_info=True)
            sentry_sdk.capture_exception(e)
            raise
    
    @staticmethod
    async def list_messages(
        conversation_id: UUID,
        user_id: UUID,
        user_type: str,
        session: AsyncSession,
        limit: int = 50,
        before_id: Optional[UUID] = None
    ) -> tuple[List[Message], bool]:
        """
        List messages in a conversation.
        
        Args:
            conversation_id: UUID of the conversation
            user_id: UUID of the current user
            user_type: Type of user
            session: Database session
            limit: Maximum number of messages to return
            before_id: Return messages before this message ID (for pagination)
            
        Returns:
            Tuple of (list of messages, has_more flag)
        """
        try:
            # Verify conversation access
            conversation = await MessagingService.get_conversation(
                conversation_id, user_id, user_type, session
            )
            if not conversation:
                raise ValueError("Conversation not found or access denied")
            
            # Build query with eager loading for sender
            stmt = (
                select(Message)
                .where(col(Message.conversation_id) == conversation_id)
                .options(selectinload(getattr(Message, "sender")))
                .order_by(desc(col(Message.created_at)))
                .limit(limit + 1)  # Fetch one extra to check if there are more
            )
            
            if before_id:
                stmt = stmt.where(col(Message.id) < before_id)
            
            result = await session.execute(stmt)
            messages = result.scalars().all()
            
            has_more = len(messages) > limit
            if has_more:
                messages = messages[:limit]
            
            # Reverse to get chronological order
            messages = list(reversed(messages))
            
            return messages, has_more
            
        except Exception as e:
            logger.error(f"Error listing messages: {str(e)}", exc_info=True)
            sentry_sdk.capture_exception(e)
            raise
    
    @staticmethod
    async def mark_message_as_read(
        message_id: UUID,
        user_id: UUID,
        user_type: str,
        session: AsyncSession
    ) -> Optional[Message]:
        """
        Mark a message as read.
        
        Args:
            message_id: UUID of the message
            user_id: UUID of the user marking it as read
            user_type: Type of user (for authorization check)
            session: Database session
            
        Returns:
            Updated Message object or None if not found/unauthorized
        """
        try:
            # Get message with conversation relationship
            stmt = (
                select(Message)
                .where(col(Message.id) == message_id)
                .options(
                    selectinload(getattr(Message, "conversation"))
                    .selectinload(getattr(Conversation, "tenant"))
                    .selectinload(getattr(Tenant, "user"))
                )
            )
            result = await session.execute(stmt)
            message = result.scalar_one_or_none()
            
            if not message:
                return None
            
            # Verify user has access to the conversation
            conversation = message.conversation
            if not conversation:
                return None
            
            # Check authorization
            if user_type == UserType.LANDLORD or user_type == UserType.ADMIN:
                if conversation.landlord_id != user_id:
                    return None  # Unauthorized
            else:
                # For tenants, check if they are the tenant in this conversation
                if not conversation.tenant or conversation.tenant.user_id != user_id:
                    return None  # Unauthorized
            
            # Don't mark sender's own messages as read
            if message.sender_id == user_id:
                return message
            
            # Mark as read
            message.is_read = True
            message.read_at = datetime.now(timezone.utc)
            
            await session.commit()
            await session.refresh(message)
            
            return message
            
        except Exception as e:
            await session.rollback()
            logger.error(f"Error marking message as read: {str(e)}", exc_info=True)
            sentry_sdk.capture_exception(e)
            raise
    
    @staticmethod
    async def mark_conversation_messages_as_read(
        conversation_id: UUID,
        user_id: UUID,
        user_type: str,
        session: AsyncSession
    ) -> int:
        """
        Mark all unread messages in a conversation as read.
        
        Args:
            conversation_id: UUID of the conversation
            user_id: UUID of the user marking messages as read
            user_type: Type of user (for authorization check)
            session: Database session
            
        Returns:
            Number of messages marked as read (0 if unauthorized or not found)
        """
        try:
            # Get conversation with tenant relationship to verify access
            stmt = (
                select(Conversation)
                .where(col(Conversation.id) == conversation_id)
                .options(
                    selectinload(getattr(Conversation, "tenant")).selectinload(getattr(Tenant, "user"))
                )
            )
            result = await session.execute(stmt)
            conversation = result.scalar_one_or_none()
            
            if not conversation:
                return 0
            
            # Verify user has access to this conversation
            if user_type in (UserType.LANDLORD.value, UserType.ADMIN.value):
                if conversation.landlord_id != user_id:
                    return 0  # Unauthorized
            else:
                # For tenants, check if they are the tenant in this conversation
                if not conversation.tenant or conversation.tenant.user_id != user_id:
                    return 0  # Unauthorized
            
            # Mark all unread messages as read (excluding sender's own messages) using bulk update
            from sqlalchemy import update
            
            update_stmt = (
                update(Message)
                .where(
                    and_(
                        col(Message.conversation_id) == conversation_id,
                        col(Message.sender_id) != user_id,
                        col(Message.is_read) == False
                    )
                )
                .values(is_read=True, read_at=datetime.now(timezone.utc))
            )
            result = await session.execute(update_stmt)
            
            await session.commit()
            
            return result.rowcount
            
        except Exception as e:
            await session.rollback()
            logger.error(f"Error marking conversation messages as read: {str(e)}", exc_info=True)
            sentry_sdk.capture_exception(e)
            raise

    @staticmethod
    async def get_message_by_id(
        message_id: UUID,
        session: AsyncSession
    ) -> Optional[Message]:
        """
        Get a message by ID.
        
        Args:
            message_id: UUID of the message
            session: Database session
            
        Returns:
            Message object or None if not found
        """
        try:
            stmt = select(Message).where(col(Message.id) == message_id)
            result = await session.execute(stmt)
            return result.scalar_one_or_none()
        except Exception as e:
            logger.error(f"Error getting message by ID: {str(e)}", exc_info=True)
            sentry_sdk.capture_exception(e)
            raise

    @staticmethod
    async def delete_message(
        message_id: UUID,
        session: AsyncSession
    ) -> None:
        """
        Delete a message.
        
        Args:
            message_id: UUID of the message to delete
            session: Database session
        """
        try:
            stmt = select(Message).where(col(Message.id) == message_id)
            result = await session.execute(stmt)
            message = result.scalar_one_or_none()
            
            if message:
                await session.delete(message)
                await session.commit()
                logger.info(f"Deleted message {message_id}")
        except Exception as e:
            await session.rollback()
            logger.error(f"Error deleting message: {str(e)}", exc_info=True)
            sentry_sdk.capture_exception(e)
            raise

