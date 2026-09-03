"""
Extended unit tests for MessagingService.

Additional tests to increase coverage for edge cases and error scenarios.
"""
from datetime import datetime, timezone
import pytest
from unittest.mock import AsyncMock, Mock, patch
from uuid import UUID, uuid4

from Backend.api.messages.service import MessagingService
from Backend.models.message import Conversation, Message, MessageType
from Backend.models.tenant import Tenant
from Backend.models.user import User
from Backend.models.enums import UserType
from Backend.models.property import Property

pytestmark = pytest.mark.unit


@pytest.fixture
def mock_landlord():
    """Create a mock landlord user."""
    return User(
        id=uuid4(),
        email="landlord@test.com",
        first_name="John",
        last_name="Landlord",
        user_type=UserType.LANDLORD
    )


@pytest.fixture
def mock_tenant():
    """Create a mock tenant."""
    return Tenant(
        id=1,
        email="tenant@test.com",
        first_name="Jane",
        last_name="Tenant",
        user_id=uuid4()
    )


@pytest.fixture
def mock_conversation(mock_landlord, mock_tenant):
    """Create a mock conversation."""
    return Conversation(
        id=uuid4(),
        landlord_id=mock_landlord.id,
        tenant_id=mock_tenant.id,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc)
    )


class TestGetConversation:
    """Tests for get_conversation function."""
    
    @pytest.mark.asyncio
    async def test_get_conversation_landlord_success(
        self, mock_db_session, mock_conversation, mock_landlord, mock_tenant
    ):
        """Test landlord successfully getting their conversation."""
        mock_tenant.user = User(id=mock_tenant.user_id, email="tenant@test.com")
        mock_conversation.tenant = mock_tenant
        
        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = mock_conversation
        mock_db_session.execute = AsyncMock(return_value=mock_result)
        
        result = await MessagingService.get_conversation(
            mock_conversation.id, mock_landlord.id, UserType.LANDLORD, mock_db_session
        )
        
        assert result is not None
        assert result.id == mock_conversation.id
    
    @pytest.mark.asyncio
    async def test_get_conversation_unauthorized_landlord(
        self, mock_db_session, mock_conversation
    ):
        """Test landlord cannot access another landlord's conversation."""
        other_landlord_id = uuid4()
        mock_tenant = Tenant(id=1, user_id=uuid4())
        mock_tenant.user = User(id=mock_tenant.user_id, email="tenant@test.com")
        mock_conversation.tenant = mock_tenant
        
        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = mock_conversation
        mock_db_session.execute = AsyncMock(return_value=mock_result)
        
        result = await MessagingService.get_conversation(
            mock_conversation.id, other_landlord_id, UserType.LANDLORD, mock_db_session
        )
        
        assert result is None
    
    @pytest.mark.asyncio
    async def test_get_conversation_not_found(self, mock_db_session):
        """Test getting non-existent conversation."""
        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db_session.execute = AsyncMock(return_value=mock_result)
        
        result = await MessagingService.get_conversation(
            uuid4(), uuid4(), UserType.LANDLORD, mock_db_session
        )
        
        assert result is None


class TestListMessages:
    """Tests for list_messages function."""
    
    @pytest.mark.asyncio
    async def test_list_messages_success(
        self, mock_db_session, mock_conversation, mock_landlord
    ):
        """Test successfully listing messages."""
        mock_message = Message(
            id=uuid4(),
            conversation_id=mock_conversation.id,
            sender_id=mock_landlord.id,
            content="Test message",
            message_type=MessageType.DIRECT.value,
            created_at=datetime.now(timezone.utc)
        )
        
        with patch.object(
            MessagingService, 'get_conversation',
            return_value=mock_conversation
        ):
            mock_result = Mock()
            mock_result.scalars.return_value.all.return_value = [mock_message]
            mock_db_session.execute = AsyncMock(return_value=mock_result)
            
            messages, has_more = await MessagingService.list_messages(
                mock_conversation.id,
                mock_landlord.id,
                UserType.LANDLORD,
                mock_db_session,
                limit=50
            )
            
            assert len(messages) == 1
            assert messages[0].id == mock_message.id
            assert has_more is False
    
    @pytest.mark.asyncio
    async def test_list_messages_with_pagination(
        self, mock_db_session, mock_conversation, mock_landlord
    ):
        """Test listing messages with pagination."""
        messages = [
            Message(
                id=uuid4(),
                conversation_id=mock_conversation.id,
                sender_id=mock_landlord.id,
                content=f"Message {i}",
                message_type=MessageType.DIRECT.value,
                created_at=datetime.now(timezone.utc)
            )
            for i in range(51)
        ]
        
        with patch.object(
            MessagingService, 'get_conversation',
            return_value=mock_conversation
        ):
            mock_result = Mock()
            mock_result.scalars.return_value.all.return_value = messages
            mock_db_session.execute = AsyncMock(return_value=mock_result)
            
            result_messages, has_more = await MessagingService.list_messages(
                mock_conversation.id,
                mock_landlord.id,
                UserType.LANDLORD,
                mock_db_session,
                limit=50
            )
            
            assert len(result_messages) == 50
            assert has_more is True
    
    @pytest.mark.asyncio
    async def test_list_messages_conversation_not_found(
        self, mock_db_session, mock_landlord
    ):
        """Test listing messages for non-existent conversation."""
        with patch.object(
            MessagingService, 'get_conversation',
            return_value=None
        ):
            with pytest.raises(ValueError, match="Conversation not found"):
                await MessagingService.list_messages(
                    uuid4(),
                    mock_landlord.id,
                    UserType.LANDLORD,
                    mock_db_session
                )


class TestSendMessageNewConversation:
    """Tests for send_message when creating new conversation."""
    
    @pytest.mark.asyncio
    async def test_send_message_landlord_new_conversation(
        self, mock_db_session, mock_landlord, mock_tenant
    ):
        """Test landlord sending first message to tenant (creates conversation)."""
        new_conversation = Conversation(
            id=uuid4(),
            landlord_id=mock_landlord.id,
            tenant_id=mock_tenant.id
        )
        
        with patch.object(
            MessagingService, 'get_or_create_conversation',
            return_value=new_conversation
        ):
            mock_db_session.add = Mock()
            mock_db_session.commit = AsyncMock()
            mock_db_session.refresh = AsyncMock()
            
            result = await MessagingService.send_message(
                conversation_id=None,
                tenant_id=mock_tenant.id,
                sender_id=mock_landlord.id,
                content="First message",
                message_type=MessageType.DIRECT.value,
                user_type=UserType.LANDLORD,
                session=mock_db_session
            )
            
            assert result.content == "First message"
            assert result.conversation_id == new_conversation.id
    
    @pytest.mark.asyncio
    async def test_send_message_missing_tenant_id(self, mock_db_session, mock_landlord):
        """Test sending message without tenant_id when creating new conversation."""
        with pytest.raises(ValueError, match="tenant_id is required"):
            await MessagingService.send_message(
                conversation_id=None,
                tenant_id=None,
                sender_id=mock_landlord.id,
                content="Test",
                message_type=MessageType.DIRECT.value,
                user_type=UserType.LANDLORD,
                session=mock_db_session
            )
    
    @pytest.mark.asyncio
    async def test_send_message_conversation_not_found(
        self, mock_db_session, mock_landlord
    ):
        """Test sending message to non-existent conversation."""
        with patch.object(
            MessagingService, 'get_conversation',
            return_value=None
        ):
            with pytest.raises(ValueError, match="Conversation not found"):
                await MessagingService.send_message(
                    conversation_id=uuid4(),
                    tenant_id=None,
                    sender_id=mock_landlord.id,
                    content="Test",
                    message_type=MessageType.DIRECT.value,
                    user_type=UserType.LANDLORD,
                    session=mock_db_session
                )


class TestMarkConversationMessagesAsRead:
    """Tests for mark_conversation_messages_as_read function."""
    
    @pytest.mark.asyncio
    async def test_mark_conversation_messages_as_read_success(
        self, mock_db_session, mock_conversation
    ):
        """Test marking all messages in conversation as read."""
        reader_id = uuid4()
        unread_messages = [
            Message(
                id=uuid4(),
                conversation_id=mock_conversation.id,
                sender_id=uuid4(),
                content="Unread message",
                message_type=MessageType.DIRECT.value,
                is_read=False
            )
            for _ in range(3)
        ]
        
        mock_result_conv = Mock()
        mock_result_conv.scalar_one_or_none.return_value = mock_conversation
        mock_result_messages = Mock()
        mock_result_messages.scalars.return_value.all.return_value = unread_messages
        
        mock_db_session.commit = AsyncMock()
        
        # Mock tenant for authorization check
        mock_tenant = Tenant(id=1, user_id=reader_id)
        mock_tenant.user = User(id=reader_id, email="reader@test.com", user_type=UserType.TENANT)
        mock_conversation.tenant = mock_tenant
        
        # Update mock to return conversation with tenant
        mock_result_conv = Mock()
        mock_result_conv.scalar_one_or_none.return_value = mock_conversation
        
        # Mock UPDATE statement result (bulk mark as read)
        mock_result_update = Mock()
        mock_result_update.rowcount = 3  # 3 messages marked as read
        
        mock_db_session.execute = AsyncMock(side_effect=[
            mock_result_conv,
            mock_result_update
        ])
        
        count = await MessagingService.mark_conversation_messages_as_read(
            mock_conversation.id, reader_id, UserType.TENANT, mock_db_session
        )
        
        assert count == 3
    
    @pytest.mark.asyncio
    async def test_mark_conversation_messages_as_read_no_conversation(
        self, mock_db_session
    ):
        """Test marking messages when conversation doesn't exist."""
        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db_session.execute = AsyncMock(return_value=mock_result)
        
        count = await MessagingService.mark_conversation_messages_as_read(
            uuid4(), uuid4(), UserType.LANDLORD, mock_db_session
        )
        
        assert count == 0
    
    @pytest.mark.asyncio
    async def test_mark_conversation_messages_as_read_excludes_own_messages(
        self, mock_db_session, mock_conversation, mock_landlord
    ):
        """Test that own messages are not marked as read."""
        # Mock conversation lookup result (authorization check)
        mock_result_conv = Mock()
        mock_result_conv.scalar_one_or_none.return_value = mock_conversation
        
        # Mock UPDATE statement result (bulk mark as read)
        # The UPDATE query excludes sender's own messages (sender_id != user_id)
        # So only 1 message from "other" sender is marked as read
        mock_result_update = Mock()
        mock_result_update.rowcount = 1  # Only 1 message marked (excludes own messages)
        
        mock_db_session.execute = AsyncMock(side_effect=[
            mock_result_conv,
            mock_result_update
        ])
        mock_db_session.commit = AsyncMock()
        
        count = await MessagingService.mark_conversation_messages_as_read(
            mock_conversation.id, mock_landlord.id, UserType.LANDLORD, mock_db_session
        )
        
        assert count == 1


class TestDuplicateConversationHandling:
    """Tests for handling duplicate conversation creation (race conditions)."""
    
    @pytest.mark.asyncio
    async def test_get_or_create_conversation_handles_duplicate_on_integrity_error(
        self, mock_db_session, mock_landlord
    ):
        """Test that IntegrityError from duplicate conversation is handled gracefully."""
        from sqlalchemy.exc import IntegrityError
        
        tenant_id = 1
        existing_conversation = Conversation(
            id=uuid4(),
            landlord_id=mock_landlord.id,
            tenant_id=tenant_id
        )
        
        # First call: no conversation exists
        mock_result_empty = Mock()
        mock_result_empty.scalar_one_or_none.return_value = None
        # Second call: IntegrityError on commit (race condition)
        # Third call: conversation now exists
        mock_result_existing = Mock()
        mock_result_existing.scalar_one_or_none.return_value = existing_conversation
        
        mock_db_session.execute = AsyncMock(side_effect=[
            mock_result_empty,  # First check - no conversation
            mock_result_existing  # After IntegrityError - conversation exists
        ])
        mock_db_session.commit = AsyncMock(side_effect=IntegrityError("unique constraint", None, None))
        mock_db_session.rollback = AsyncMock()
        
        result = await MessagingService.get_or_create_conversation(
            mock_landlord.id, tenant_id, mock_db_session
        )
        
        # Should return the existing conversation
        assert result.id == existing_conversation.id
        assert mock_db_session.rollback.called


class TestErrorHandling:
    """Tests for error handling scenarios."""
    
    @pytest.mark.asyncio
    async def test_get_or_create_conversation_rollback_on_error(self, mock_db_session):
        """Test that errors trigger rollback."""
        landlord_id = uuid4()
        tenant_id = 1
        
        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db_session.execute = AsyncMock(return_value=mock_result)
        mock_db_session.add = Mock()
        mock_db_session.commit = AsyncMock(side_effect=Exception("DB Error"))
        mock_db_session.rollback = AsyncMock()
        
        with pytest.raises(Exception):
            await MessagingService.get_or_create_conversation(
                landlord_id, tenant_id, mock_db_session
            )
        
        assert mock_db_session.rollback.called
    
    @pytest.mark.asyncio
    async def test_send_message_rollback_on_error(
        self, mock_db_session, mock_conversation, mock_landlord
    ):
        """Test that send_message rolls back on error."""
        with patch.object(
            MessagingService, 'get_conversation',
            return_value=mock_conversation
        ):
            mock_db_session.add = Mock()
            mock_db_session.commit = AsyncMock(side_effect=Exception("DB Error"))
            mock_db_session.rollback = AsyncMock()
            
            with pytest.raises(Exception):
                await MessagingService.send_message(
                    conversation_id=mock_conversation.id,
                    tenant_id=None,
                    sender_id=mock_landlord.id,
                    content="Test",
                    message_type=MessageType.DIRECT.value,
                    user_type=UserType.LANDLORD,
                    session=mock_db_session
                )
            
            assert mock_db_session.rollback.called

