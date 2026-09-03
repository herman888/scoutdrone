"""
Unit tests for MessagingService.

Tests the core business logic for conversation and message management.
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


@pytest.fixture
def mock_message(mock_conversation, mock_landlord):
    """Create a mock message."""
    return Message(
        id=uuid4(),
        conversation_id=mock_conversation.id,
        sender_id=mock_landlord.id,
        content="Test message",
        message_type=MessageType.DIRECT.value,
        is_read=False,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc)
    )


class TestGetOrCreateConversation:
    """Tests for get_or_create_conversation function."""
    
    @pytest.mark.asyncio
    async def test_get_existing_conversation(self, mock_db_session, mock_conversation):
        """Test retrieving an existing conversation."""
        landlord_id = mock_conversation.landlord_id
        tenant_id = mock_conversation.tenant_id
        
        # Mock database query
        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = mock_conversation
        mock_db_session.execute = AsyncMock(return_value=mock_result)
        
        result = await MessagingService.get_or_create_conversation(
            landlord_id, tenant_id, mock_db_session
        )
        
        assert result.id == mock_conversation.id
        assert result.landlord_id == landlord_id
        assert result.tenant_id == tenant_id
        mock_db_session.add.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_create_new_conversation(self, mock_db_session):
        """Test creating a new conversation when none exists."""
        landlord_id = uuid4()
        tenant_id = 1
        
        # Create a properly structured mock conversation
        from Backend.models.message import Conversation
        mock_conversation = Conversation(
            landlord_id=landlord_id,
            tenant_id=tenant_id
        )
        
        # Mock tenant relationship
        mock_tenant = Mock()
        mock_tenant.user = Mock()
        mock_tenant.user.first_name = "John"
        mock_tenant.user.last_name = "Doe"
        mock_conversation.tenant = mock_tenant
        
        # Mock the two database queries:
        # 1. First query returns None (no existing conversation)
        mock_result_none = Mock()
        mock_result_none.scalar_one_or_none.return_value = None
        
        # 2. Second query returns the created conversation (after refresh)
        mock_result_conversation = Mock()
        mock_result_conversation.scalar_one.return_value = mock_conversation
        
        # Set up execute to return different results for each call
        mock_db_session.execute = AsyncMock(side_effect=[mock_result_none, mock_result_conversation])
        mock_db_session.add = Mock()
        mock_db_session.commit = AsyncMock()
        mock_db_session.refresh = AsyncMock()
        
        result = await MessagingService.get_or_create_conversation(
            landlord_id, tenant_id, mock_db_session
        )
        
        assert mock_db_session.add.called
        assert mock_db_session.commit.called
        assert result.landlord_id == landlord_id
        assert result.tenant_id == tenant_id


class TestSendMessage:
    """Tests for send_message function."""
    
    @pytest.mark.asyncio
    async def test_send_message_existing_conversation(
        self, mock_db_session, mock_conversation, mock_landlord
    ):
        """Test sending a message in an existing conversation."""
        # Mock get_conversation
        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = mock_conversation
        mock_db_session.execute = AsyncMock(return_value=mock_result)
        mock_db_session.add = Mock()
        mock_db_session.commit = AsyncMock()
        mock_db_session.refresh = AsyncMock()
        
        # Patch get_conversation to return our mock
        with patch.object(
            MessagingService, 'get_conversation',
            return_value=mock_conversation
        ):
            result = await MessagingService.send_message(
                conversation_id=mock_conversation.id,
                tenant_id=None,
                sender_id=mock_landlord.id,
                content="Hello",
                message_type=MessageType.DIRECT.value,
                user_type=UserType.LANDLORD,
                session=mock_db_session
            )
        
        assert mock_db_session.add.called
        assert mock_db_session.commit.called
        assert result.content == "Hello"
        assert result.conversation_id == mock_conversation.id


class TestMarkMessageAsRead:
    """Tests for mark_message_as_read function."""
    
    @pytest.mark.asyncio
    async def test_mark_message_as_read_success(
        self, mock_db_session, mock_message, mock_landlord
    ):
        """Test successfully marking a message as read."""
        reader_id = uuid4()  # Different from sender
        
        # Mock message query
        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = mock_message
        mock_db_session.execute = AsyncMock(return_value=mock_result)
        mock_db_session.commit = AsyncMock()
        mock_db_session.refresh = AsyncMock()
        
        # Mock conversation with tenant for authorization check
        mock_conversation = Conversation(
            id=uuid4(),
            landlord_id=mock_landlord.id,
            tenant_id=1
        )
        mock_tenant = Tenant(id=1, user_id=reader_id)
        mock_tenant.user = User(id=reader_id, email="reader@test.com", user_type=UserType.TENANT)
        mock_conversation.tenant = mock_tenant
        mock_message.conversation = mock_conversation
        
        # Mock execute to return message with conversation
        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = mock_message
        mock_db_session.execute = AsyncMock(return_value=mock_result)
        
        result = await MessagingService.mark_message_as_read(
            mock_message.id, reader_id, UserType.TENANT, mock_db_session
        )
        
        assert result.is_read is True
        assert result.read_at is not None
        assert mock_db_session.commit.called
    
    @pytest.mark.asyncio
    async def test_mark_own_message_as_read_no_change(
        self, mock_db_session, mock_message, mock_landlord
    ):
        """Test that marking your own message as read doesn't change it."""
        sender_id = mock_message.sender_id
        
        # Mock message query
        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = mock_message
        mock_db_session.execute = AsyncMock(return_value=mock_result)
        mock_db_session.commit = AsyncMock()
        mock_db_session.refresh = AsyncMock()
        
        # Mock conversation for authorization check
        mock_conversation = Conversation(
            id=uuid4(),
            landlord_id=mock_landlord.id,
            tenant_id=1
        )
        mock_tenant = Tenant(id=1, user_id=uuid4())
        mock_tenant.user = User(id=mock_tenant.user_id, email="tenant@test.com")
        mock_conversation.tenant = mock_tenant
        mock_message.conversation = mock_conversation
        
        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = mock_message
        mock_db_session.execute = AsyncMock(return_value=mock_result)
        
        result = await MessagingService.mark_message_as_read(
            mock_message.id, sender_id, UserType.LANDLORD, mock_db_session
        )
        
        # Should return the message but not mark it as read (sender's own message)
        assert result.id == mock_message.id
        # The message should remain unread (or unchanged) since it's the sender's own message


class TestListConversations:
    """Tests for list_conversations function."""
    
    @pytest.mark.asyncio
    async def test_list_conversations_landlord(
        self, mock_db_session, mock_conversation, mock_landlord
    ):
        """Test listing conversations for a landlord."""
        # Mock query result
        mock_result = Mock()
        mock_result.scalars.return_value.all.return_value = [mock_conversation]
        mock_db_session.execute = AsyncMock(return_value=mock_result)
        
        result = await MessagingService.list_conversations(
            mock_landlord.id, UserType.LANDLORD, mock_db_session
        )
        
        assert len(result) == 1
        assert result[0].id == mock_conversation.id
    
    @pytest.mark.asyncio
    async def test_list_conversations_tenant(
        self, mock_db_session, mock_conversation, mock_tenant
    ):
        """Test listing conversations for a tenant."""
        # Mock tenant user
        tenant_user = User(
            id=mock_tenant.user_id,
            email="tenant@test.com",
            user_type=UserType.TENANT
        )
        mock_tenant.user = tenant_user
        
        # Mock query result
        mock_result = Mock()
        mock_result.scalars.return_value.all.return_value = [mock_conversation]
        mock_db_session.execute = AsyncMock(return_value=mock_result)
        
        result = await MessagingService.list_conversations(
            tenant_user.id, UserType.TENANT, mock_db_session
        )
        
        assert len(result) == 1
        assert result[0].id == mock_conversation.id

