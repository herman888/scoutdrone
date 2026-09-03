/**
 * React Query hooks for managing conversations
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { fetchConversations, createConversation, type Conversation } from '@/utils/api/messages';
import * as Sentry from '@sentry/react';

// Query keys for conversations
export const conversationsKeys = {
  all: ['conversations'] as const,
  lists: () => [...conversationsKeys.all, 'list'] as const,
  list: () => [...conversationsKeys.lists()] as const,
  details: () => [...conversationsKeys.all, 'detail'] as const,
  detail: (id: string) => [...conversationsKeys.details(), id] as const,
};

/**
 * Hook to fetch all conversations for the current user
 */
export const useConversations = () => {
  // Only fetch conversations if user is authenticated (token exists)
  const isAuthenticated = !!localStorage.getItem('token');
  
  return useQuery({
    queryKey: conversationsKeys.list(),
    queryFn: fetchConversations,
    enabled: isAuthenticated, // Don't run query on login page
    staleTime: 30000, // Consider fresh for 30 seconds
    refetchOnWindowFocus: true,
    retry: 2,
    meta: {
      errorMessage: 'Failed to load conversations',
    },
  });
};

/**
 * Hook to create a new conversation
 */
export const useCreateConversation = () => {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: createConversation,
    onSuccess: (newConversation) => {
      // Add new conversation to the list
      queryClient.setQueryData<Conversation[]>(
        conversationsKeys.list(),
        (old) => [newConversation, ...(old || [])]
      );

      Sentry.addBreadcrumb({
        category: 'messaging',
        message: 'Conversation created',
        level: 'info',
        data: { conversationId: newConversation.id },
      });
    },
    onError: (error) => {
      Sentry.captureException(error, {
        tags: {
          component: 'useCreateConversation',
          action: 'create_conversation',
        },
      });
    },
  });
};

/**
 * Get total unread count across all conversations
 */
export const useUnreadCount = () => {
  const { data: conversations } = useConversations();
  
  return conversations?.reduce((total, conv) => total + conv.unread_count, 0) || 0;
};

