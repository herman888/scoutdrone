/**
 * Messaging API Functions
 * 
 * API client for messaging between tenants and landlords
 */

import { apiRequest } from './core';

// ========================================================================
// TYPE DEFINITIONS
// ========================================================================

export interface Conversation {
  id: string;
  landlord_id: string;
  tenant_id: number;
  created_at: string;
  updated_at: string;
  tenant_name?: string | null;
  tenant_email?: string | null;
  tenant_avatar_url?: string | null;
  landlord_name?: string | null;
  landlord_email?: string | null;
  landlord_avatar_url?: string | null;
  last_message?: Message | null;
  unread_count: number;
}

export interface Message {
  id: string;
  conversation_id: string;
  sender_id: string;
  content: string;
  message_type: string;
  is_read: boolean;
  read_at: string | null;
  created_at: string;
  updated_at: string;
  sender_name?: string | null;
  sender_email?: string | null;
}

export interface MessageListResponse {
  messages: Message[];
  total: number;
  has_more: boolean;
}

// ========================================================================
// API FUNCTIONS
// ========================================================================

/**
 * Fetch all conversations for the current user
 */
export const fetchConversations = async (): Promise<Conversation[]> => {
  return apiRequest<Conversation[]>('/messages/conversations');
};

/**
 * Create a new conversation with a tenant
 */
export const createConversation = async (conversationData: {
  tenant_id: number;
}): Promise<Conversation> => {
  return apiRequest<Conversation>('/messages/conversations', {
    method: 'POST',
    body: JSON.stringify(conversationData),
  });
};

/**
 * Fetch messages in a conversation
 */
export const fetchMessages = async (
  conversationId: string,
  params?: { limit?: number; before_id?: string }
): Promise<MessageListResponse> => {
  const queryParams = new URLSearchParams();
  if (params?.limit) queryParams.append('limit', params.limit.toString());
  if (params?.before_id) queryParams.append('before_id', params.before_id);
  
  const queryString = queryParams.toString();
  const url = `/messages/conversations/${conversationId}/messages${queryString ? `?${queryString}` : ''}`;
  
  return apiRequest<MessageListResponse>(url);
};

/**
 * Send a message
 */
export const sendMessage = async (messageData: {
  conversation_id?: string;
  tenant_id?: number;
  content: string;
  message_type?: string;
}): Promise<Message> => {
  return apiRequest<Message>('/messages/messages', {
    method: 'POST',
    body: JSON.stringify({
      ...messageData,
      message_type: messageData.message_type || 'DIRECT',
    }),
  });
};

/**
 * Mark a message as read
 */
export const markMessageAsRead = async (messageId: string): Promise<Message> => {
  return apiRequest<Message>(`/messages/messages/${messageId}/read`, {
    method: 'PUT',
  });
};

/**
 * Mark all messages in a conversation as read
 */
export const markConversationAsRead = async (conversationId: string): Promise<{ conversation_id: string; messages_marked_read: number }> => {
  return apiRequest(`/messages/conversations/${conversationId}/read`, {
    method: 'PUT',
  });
};

/**
 * Delete a message
 */
export const deleteMessage = async (messageId: string): Promise<void> => {
  await apiRequest(`/messages/messages/${messageId}`, {
    method: 'DELETE',
  });
};

/**
 * Send announcement to all tenants
 */
export const sendAnnouncement = async (content: string, recipientType?: string): Promise<void> => {
  const queryParams = new URLSearchParams();
  if (recipientType) queryParams.append('recipient_type', recipientType);
  
  const queryString = queryParams.toString();
  return apiRequest(`/messages/announcements${queryString ? '?' + queryString : ''}`, {
    method: 'POST',
    body: JSON.stringify({ content }),
  });
};

