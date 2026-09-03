"""
Comprehensive API tests for messaging router endpoints.

Tests all router endpoints with various scenarios using synchronous TestClient.
"""
import pytest
from datetime import datetime, timezone
from uuid import uuid4
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, MagicMock, patch

from Backend.api.app import app
from Backend.models.user import User
from Backend.models.enums import UserType
from Backend.api.auth import get_current_user
from Backend.database import get_session

# Mark all tests in this module as unit tests
pytestmark = pytest.mark.unit

@pytest.fixture(autouse=True)
def clear_dependency_overrides():
    """Ensure dependency overrides are cleared after each test."""
    yield
    app.dependency_overrides.clear()

# Create a custom TestClient that sets the proper host header
class TestClientWithHost(TestClient):
    def request(self, method: str, url, **kwargs):
        headers = kwargs.get("headers") or {}
        if "host" not in {k.lower() for k in headers.keys()}:
            headers["Host"] = "localhost"
        kwargs["headers"] = headers
        return super().request(method, url, **kwargs)

def create_test_user(user_id=None, email="test@example.com", user_type="LANDLORD"):
    """Helper function to create a properly initialized test user."""
    now = datetime.now(timezone.utc)
    return User(
        id=user_id or uuid4(),
        email=email,
        first_name="Test",
        last_name="User",
        user_type=user_type,
        is_active=True,
        created_at=now,
        updated_at=now,
        is_email_verified=True
    )


class TestConversationEndpoints:
    """Tests for conversation-related endpoints."""
    
    def test_list_conversations_success(self):
        """Test successfully listing conversations."""
        mock_user = create_test_user()
        mock_session = AsyncMock()
        
        app.dependency_overrides[get_current_user] = lambda: mock_user
        app.dependency_overrides[get_session] = lambda: mock_session
        
        with patch('Backend.api.messages.router.MessagingService.list_conversations', new_callable=AsyncMock) as mock_list:
            mock_list.return_value = []
            
            client = TestClientWithHost(app)
            response = client.get("/api/messages/conversations")
            
            assert response.status_code == 200
            data = response.json()
            assert isinstance(data, list)
    
    def test_list_conversations_unauthorized(self):
        """Test listing conversations without authentication."""
        client = TestClientWithHost(app)
        response = client.get("/api/messages/conversations")
        assert response.status_code == 403
    
    def test_create_conversation_missing_tenant_id(self):
        """Test creating conversation without tenant_id."""
        mock_user = create_test_user()
        mock_session = AsyncMock()
        
        app.dependency_overrides[get_current_user] = lambda: mock_user
        app.dependency_overrides[get_session] = lambda: mock_session
        
        client = TestClientWithHost(app)
        response = client.post(
            "/api/messages/conversations",
            json={}
        )
        assert response.status_code in [400, 422]
    
    def test_create_conversation_unauthorized(self):
        """Test creating conversation without authentication."""
        client = TestClientWithHost(app)
        response = client.post(
            "/api/messages/conversations",
            json={"tenant_id": 1}
        )
        assert response.status_code == 403


class TestMessageEndpoints:
    """Tests for message-related endpoints."""
    
    def test_send_message_empty_content(self):
        """Test sending message with empty content."""
        mock_user = create_test_user()
        mock_session = AsyncMock()
        
        app.dependency_overrides[get_current_user] = lambda: mock_user
        app.dependency_overrides[get_session] = lambda: mock_session
        
        client = TestClientWithHost(app)
        response = client.post(
            "/api/messages/messages",
            json={
                "content": "",
                "message_type": "DIRECT"
            }
        )
        assert response.status_code in [400, 422]
    
    def test_send_message_missing_content(self):
        """Test sending message without content field."""
        mock_user = create_test_user()
        mock_session = AsyncMock()
        
        app.dependency_overrides[get_current_user] = lambda: mock_user
        app.dependency_overrides[get_session] = lambda: mock_session
        
        client = TestClientWithHost(app)
        response = client.post(
            "/api/messages/messages",
            json={
                "message_type": "DIRECT"
            }
        )
        assert response.status_code in [400, 422]
    
    def test_send_message_invalid_conversation_id(self):
        """Test sending message with invalid conversation_id."""
        mock_user = create_test_user()
        mock_session = AsyncMock()
        
        app.dependency_overrides[get_current_user] = lambda: mock_user
        app.dependency_overrides[get_session] = lambda: mock_session
        
        fake_id = str(uuid4())
        
        with patch('Backend.api.messages.router.MessagingService.send_message', new_callable=AsyncMock) as mock_send:
            mock_send.side_effect = Exception("Invalid conversation")
            
            client = TestClientWithHost(app)
            response = client.post(
                "/api/messages/messages",
                json={
                    "conversation_id": fake_id,
                    "content": "Test",
                    "message_type": "DIRECT"
                }
            )
            assert response.status_code in [400, 404, 500]
    
    def test_send_message_unauthorized(self):
        """Test sending message without authentication."""
        client = TestClientWithHost(app)
        response = client.post(
            "/api/messages/messages",
            json={
                "content": "Test",
                "message_type": "DIRECT"
            }
        )
        assert response.status_code == 403


class TestListMessagesEndpoint:
    """Tests for listing messages endpoint."""
    
    def test_list_messages_invalid_conversation(self):
        """Test listing messages for non-existent conversation."""
        mock_user = create_test_user()
        mock_session = AsyncMock()
        
        app.dependency_overrides[get_current_user] = lambda: mock_user
        app.dependency_overrides[get_session] = lambda: mock_session
        
        fake_id = str(uuid4())
        
        with patch('Backend.api.messages.router.MessagingService.list_messages', new_callable=AsyncMock) as mock_list:
            mock_list.side_effect = Exception("Conversation not found")
            
            client = TestClientWithHost(app)
            response = client.get(
                f"/api/messages/conversations/{fake_id}/messages"
            )
            assert response.status_code in [404, 400, 500]
    
    def test_list_messages_unauthorized(self):
        """Test listing messages without authentication."""
        fake_id = str(uuid4())
        client = TestClientWithHost(app)
        response = client.get(
            f"/api/messages/conversations/{fake_id}/messages"
        )
        assert response.status_code == 403


class TestMarkAsReadEndpoints:
    """Tests for mark as read endpoints."""
    
    def test_mark_message_as_read_not_found(self):
        """Test marking non-existent message as read."""
        mock_user = create_test_user()
        mock_session = AsyncMock()
        
        app.dependency_overrides[get_current_user] = lambda: mock_user
        app.dependency_overrides[get_session] = lambda: mock_session
        
        fake_id = str(uuid4())
        
        with patch('Backend.api.messages.router.MessagingService.mark_message_as_read', new_callable=AsyncMock) as mock_mark:
            mock_mark.side_effect = Exception("Message not found")
            
            client = TestClientWithHost(app)
            response = client.put(f"/api/messages/messages/{fake_id}/read")
            assert response.status_code in [404, 400, 500]
    
    def test_mark_conversation_as_read_invalid_id(self):
        """Test marking messages in non-existent conversation."""
        mock_user = create_test_user()
        mock_session = AsyncMock()
        
        app.dependency_overrides[get_current_user] = lambda: mock_user
        app.dependency_overrides[get_session] = lambda: mock_session
        
        fake_id = str(uuid4())
        
        client = TestClientWithHost(app)
        response = client.put(
            f"/api/messages/conversations/{fake_id}/read"
        )
        # Should return error for non-existent conversation
        assert response.status_code in [404, 400, 500]
    
    def test_mark_message_as_read_unauthorized(self):
        """Test marking message as read without authentication."""
        fake_id = str(uuid4())
        client = TestClientWithHost(app)
        response = client.put(
            f"/api/messages/messages/{fake_id}/read"
        )
        assert response.status_code == 403


class TestAnnouncementEndpoint:
    """Tests for announcement endpoint."""
    
    def test_send_announcement_unauthorized(self):
        """Test sending announcement without authentication."""
        client = TestClientWithHost(app)
        response = client.post(
            "/api/messages/announcements",
            json={
                "content": "Test",
                "recipient_type": "all"
            }
        )
        assert response.status_code == 403
