/**
 * React Query hooks for managing messages within conversations
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useContext } from 'react';
import { AuthContext } from '../contexts/AuthContext';
import { 
  fetchMessages, 
  sendMessage, 
  markConversationAsRead,
  deleteMessage,
  type Message,
  type MessageListResponse,
  type Conversation
} from '@/utils/api/messages';
import { conversationsKeys } from './useConversations';
import * as Sentry from '@sentry/react';

// Query keys for messages
export const messagesKeys = {
  all: ['messages'] as const,
  lists: () => [...messagesKeys.all, 'list'] as const,
  list: (conversationId: string) => [...messagesKeys.lists(), conversationId] as const,
};

/**
 * Hook to fetch messages for a specific conversation
 */
export const useMessages = (conversationId: string | null, enabled = true) => {
  return useQuery({
    queryKey: messagesKeys.list(conversationId || ''),
    queryFn: () => fetchMessages(conversationId!, { limit: 50 }),
    enabled: !!conversationId && enabled,
    staleTime: 10000, // Consider fresh for 10 seconds
    refetchOnWindowFocus: true,
    retry: 2,
    meta: {
      errorMessage: 'Failed to load messages',
    },
  });
};

/**
 * Hook to send a message with optimistic updates
 */
export const useSendMessage = (conversationId: string | null) => {
  const queryClient = useQueryClient();
  const authContext = useContext(AuthContext);
  const currentUserId = authContext?.user?.id;

  return useMutation({
    mutationFn: async (newMessageData: Parameters<typeof sendMessage>[0]) => {
      // Guard clause: Ensure user is authenticated
      if (!currentUserId) {
        throw new Error("User must be authenticated to send messages");
      }
      return sendMessage(newMessageData);
    },
    onMutate: async (newMessageData: Parameters<typeof sendMessage>[0]) => {
      if (!conversationId || !currentUserId) return;

      // Cancel outgoing refetches
      await queryClient.cancelQueries({ queryKey: messagesKeys.list(conversationId) });

      // Snapshot the previous value
      const previousMessages = queryClient.getQueryData<MessageListResponse>(
        messagesKeys.list(conversationId)
      );

      // Optimistically update to the new value with actual user ID
      const optimisticMessage: Message = {
        id: `temp-${Date.now()}`,
        conversation_id: conversationId,
        sender_id: currentUserId, // Use actual user ID for correct message alignment
        content: newMessageData.content,
        message_type: newMessageData.message_type || 'DIRECT',
        is_read: false,
        read_at: null,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
        sender_name: null,
        sender_email: null,
      };

      queryClient.setQueryData<MessageListResponse>(
        messagesKeys.list(conversationId),
        (old) => ({
          messages: [...(old?.messages || []), optimisticMessage],
          total: (old?.total || 0) + 1,
          has_more: old?.has_more || false,
        })
      );

      if (import.meta.env.MODE === 'development') {
        console.log('[useSendMessage] Optimistic update added with temp ID:', optimisticMessage.id);
      }
      return { previousMessages, optimisticMessage };
    },
    onSuccess: (data, _variables, context) => {
      if (!conversationId) return;

      if (import.meta.env.MODE === 'development') {
        console.log('[useSendMessage] Message sent successfully, replacing temp ID:', context?.optimisticMessage.id, 'with real ID:', data.id);
      }

      // Replace optimistic message with real one
      queryClient.setQueryData<MessageListResponse>(
        messagesKeys.list(conversationId),
        (old) => ({
          messages: (old?.messages || []).map((msg) =>
            msg.id === context?.optimisticMessage.id ? data : msg
          ),
          total: old?.total || 0,
          has_more: old?.has_more || false,
        })
      );

      // Update conversation's last message and timestamp
      queryClient.setQueryData<Conversation[]>(
        conversationsKeys.list(),
        (old) =>
          old?.map((conv) =>
            conv.id === conversationId
              ? { ...conv, last_message: data, updated_at: data.created_at }
              : conv
          )
      );

      Sentry.addBreadcrumb({
        category: 'messaging',
        message: 'Message sent',
        level: 'info',
        data: { messageId: data.id, conversationId },
      });
    },
    onError: (error, _variables, context) => {
      if (!conversationId) return;

      // Rollback on error
      if (context?.previousMessages) {
        queryClient.setQueryData(messagesKeys.list(conversationId), context.previousMessages);
      }

      Sentry.captureException(error, {
        tags: {
          component: 'useSendMessage',
          action: 'send_message',
          conversationId,
        },
      });
    },
    // Note: No onSettled refetch needed - we have optimistic updates + real-time updates
    // Refetching here causes duplicate messages and glitches
  });
};

/**
 * Hook to mark conversation messages as read
 */
export const useMarkConversationAsRead = () => {
  const queryClient = useQueryClient();
  const authContext = useContext(AuthContext);
  const currentUserId = authContext?.user?.id || 'unknown';

  return useMutation({
    mutationFn: markConversationAsRead,
    onSuccess: (_data, conversationId) => {
      // Update all messages in this conversation to read (except own messages)
      queryClient.setQueryData<MessageListResponse>(
        messagesKeys.list(conversationId),
        (old) => ({
          messages:
            old?.messages.map((msg) =>
              msg.sender_id !== currentUserId
                ? { ...msg, is_read: true, read_at: new Date().toISOString() }
                : msg
            ) || [],
          total: old?.total || 0,
          has_more: old?.has_more || false,
        })
      );

      // Update conversation's unread count to 0
      queryClient.setQueryData<Conversation[]>(
        conversationsKeys.list(),
        (old) =>
          old?.map((conv) =>
            conv.id === conversationId ? { ...conv, unread_count: 0 } : conv
          )
      );
    },
    onError: (error) => {
      Sentry.captureException(error, {
        tags: {
          component: 'useMarkConversationAsRead',
          action: 'mark_read',
        },
      });
    },
  });
};

/**
 * Hook to delete a message
 */
export const useDeleteMessage = (conversationId: string | null) => {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: deleteMessage,
    onMutate: async (messageId) => {
      if (!conversationId) return;

      // Cancel outgoing refetches
      await queryClient.cancelQueries({ queryKey: messagesKeys.list(conversationId) });

      // Snapshot previous value
      const previousMessages = queryClient.getQueryData<MessageListResponse>(
        messagesKeys.list(conversationId)
      );

      // Optimistically remove message
      queryClient.setQueryData<MessageListResponse>(
        messagesKeys.list(conversationId),
        (old) => ({
          messages: (old?.messages || []).filter((msg) => msg.id !== messageId),
          total: Math.max(0, (old?.total || 1) - 1),
          has_more: old?.has_more || false,
        })
      );

      return { previousMessages };
    },
    onError: (error, _messageId, context) => {
      if (!conversationId) return;

      // Rollback on error
      if (context?.previousMessages) {
        queryClient.setQueryData(messagesKeys.list(conversationId), context.previousMessages);
      }

      Sentry.captureException(error, {
        tags: {
          component: 'useDeleteMessage',
          action: 'delete_message',
          conversationId,
        },
      });
    },
  });
};

