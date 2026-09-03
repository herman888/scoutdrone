"""
Authorization tests for messaging service.

Tests that verify proper authorization checks prevent unauthorized access.
"""
from datetime import datetime, timezone
import pytest
from unittest.mock import AsyncMock, Mock
from uuid import UUID, uuid4

from Backend.api.messages.service import MessagingService
from Backend.models.message import Conversation, Message, MessageType
from Backend.models.tenant import Tenant
from Backend.models.user import User
from Backend.models.enums import UserType

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
    tenant_user = User(
        id=uuid4(),
        email="tenant@test.com",
        user_type=UserType.TENANT
    )
    return Tenant(
        id=1,
        email="tenant@test.com",
        first_name="Jane",
        last_name="Tenant",
        user_id=tenant_user.id
    )


@pytest.fixture
def mock_conversation(mock_landlord, mock_tenant):
    """Create a mock conversation."""
    mock_tenant.user = User(id=mock_tenant.user_id, email="tenant@test.com", user_type=UserType.TENANT)
    conv = Conversation(
        id=uuid4(),
        landlord_id=mock_landlord.id,
        tenant_id=mock_tenant.id,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc)
    )
    conv.tenant = mock_tenant
    return conv


class TestMarkMessageAsReadAuthorization:
    """Tests for authorization in mark_message_as_read."""
    
    @pytest.mark.asyncio
    async def test_mark_message_as_read_unauthorized_landlord(
        self, mock_db_session, mock_conversation, mock_landlord
    ):
        """Test that landlord cannot mark messages in another landlord's conversation."""
        other_landlord_id = uuid4()
        message = Message(
            id=uuid4(),
            conversation_id=mock_conversation.id,
            sender_id=uuid4(),
            content="Test message",
            message_type=MessageType.DIRECT.value,
            created_at=datetime.now(timezone.utc)
        )
        message.conversation = mock_conversation
        
        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = message
        mock_db_session.execute = AsyncMock(return_value=mock_result)
        
        result = await MessagingService.mark_message_as_read(
            message.id, other_landlord_id, UserType.LANDLORD, mock_db_session
        )
        
        # Should return None (unauthorized)
        assert result is None
        mock_db_session.commit.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_mark_message_as_read_unauthorized_tenant(
        self, mock_db_session, mock_conversation
    ):
        """Test that tenant cannot mark messages in another tenant's conversation."""
        other_tenant_id = uuid4()
        message = Message(
            id=uuid4(),
            conversation_id=mock_conversation.id,
            sender_id=uuid4(),
            content="Test message",
            message_type=MessageType.DIRECT.value,
            created_at=datetime.now(timezone.utc)
        )
        message.conversation = mock_conversation
        
        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = message
        mock_db_session.execute = AsyncMock(return_value=mock_result)
        
        result = await MessagingService.mark_message_as_read(
            message.id, other_tenant_id, UserType.TENANT, mock_db_session
        )
        
        # Should return None (unauthorized)
        assert result is None
        mock_db_session.commit.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_mark_message_as_read_authorized_landlord(
        self, mock_db_session, mock_conversation, mock_landlord
    ):
        """Test that landlord can mark messages in their own conversation."""
        message = Message(
            id=uuid4(),
            conversation_id=mock_conversation.id,
            sender_id=uuid4(),  # Different from landlord
            content="Test message",
            message_type=MessageType.DIRECT.value,
            is_read=False,
            created_at=datetime.now(timezone.utc)
        )
        message.conversation = mock_conversation
        
        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = message
        mock_db_session.execute = AsyncMock(return_value=mock_result)
        mock_db_session.commit = AsyncMock()
        mock_db_session.refresh = AsyncMock()
        
        result = await MessagingService.mark_message_as_read(
            message.id, mock_landlord.id, UserType.LANDLORD, mock_db_session
        )
        
        # Should succeed
        assert result is not None
        assert result.is_read is True
        mock_db_session.commit.assert_called()


class TestMarkConversationMessagesAsReadAuthorization:
    """Tests for authorization in mark_conversation_messages_as_read."""
    
    @pytest.mark.asyncio
    async def test_mark_conversation_messages_as_read_unauthorized_landlord(
        self, mock_db_session, mock_conversation
    ):
        """Test that landlord cannot mark messages in another landlord's conversation."""
        other_landlord_id = uuid4()
        
        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = mock_conversation
        mock_db_session.execute = AsyncMock(return_value=mock_result)
        
        count = await MessagingService.mark_conversation_messages_as_read(
            mock_conversation.id, other_landlord_id, UserType.LANDLORD, mock_db_session
        )
        
        # Should return 0 (unauthorized)
        assert count == 0
        mock_db_session.commit.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_mark_conversation_messages_as_read_unauthorized_tenant(
        self, mock_db_session, mock_conversation
    ):
        """Test that tenant cannot mark messages in another tenant's conversation."""
        other_tenant_id = uuid4()
        
        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = mock_conversation
        mock_db_session.execute = AsyncMock(return_value=mock_result)
        
        count = await MessagingService.mark_conversation_messages_as_read(
            mock_conversation.id, other_tenant_id, UserType.TENANT, mock_db_session
        )
        
        # Should return 0 (unauthorized)
        assert count == 0
        mock_db_session.commit.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_mark_conversation_messages_as_read_authorized_landlord(
        self, mock_db_session, mock_conversation, mock_landlord
    ):
        """Test that landlord can mark messages in their own conversation."""
        # Mock conversation lookup result (authorization check)
        mock_result_conv = Mock()
        mock_result_conv.scalar_one_or_none.return_value = mock_conversation
        
        # Mock UPDATE statement result (bulk mark as read)
        mock_result_update = Mock()
        mock_result_update.rowcount = 2  # 2 messages marked as read
        
        mock_db_session.execute = AsyncMock(side_effect=[
            mock_result_conv,
            mock_result_update
        ])
        mock_db_session.commit = AsyncMock()
        
        count = await MessagingService.mark_conversation_messages_as_read(
            mock_conversation.id, mock_landlord.id, UserType.LANDLORD, mock_db_session
        )
        
        # Should succeed
        assert count == 2
        mock_db_session.commit.assert_called()

