/**
 * Real-time messaging hook using Supabase Realtime
 * 
 * Subscribes to message events and updates React Query cache directly
 * instead of invalidating (more efficient, instant updates)
 */

import { useEffect, useRef, useContext } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { RealtimeChannel, type RealtimePostgresChangesPayload } from '@supabase/supabase-js';
import * as Sentry from '@sentry/react';
import { supabase } from '../supabaseClient';
import { AuthContext } from '../contexts/AuthContext';
import { messagesKeys } from './useMessages';
import { conversationsKeys } from './useConversations';
import type { Message, MessageListResponse, Conversation } from '@/utils/api/messages';

/**
 * Hook for real-time message updates using Supabase Realtime.
 * 
 * Directly updates React Query cache for instant UI updates without refetching.
 */
export const useMessagesRealtime = () => {
  const queryClient = useQueryClient();
  const authContext = useContext(AuthContext);
  const channelRef = useRef<RealtimeChannel | null>(null);
  const isUnsubscribingRef = useRef(false);

  useEffect(() => {
    // Reset flag when effect runs
    isUnsubscribingRef.current = false;

    // Only subscribe if user is authenticated
    if (!authContext?.isAuthenticated || !authContext?.user?.id) {
      return;
    }

    const userId = authContext.user.id;

    // Create a unique channel name for this user's message subscriptions
    const channelName = `landlord-messages-realtime-${userId}`;

    // Set up Supabase Realtime subscription for messages table
    const channel = supabase
      .channel(channelName)
      .on(
        'postgres_changes',
        {
          event: 'INSERT',
          schema: 'public',
          table: 'messages',
        },
        (payload: RealtimePostgresChangesPayload<Message>) => {
          const newMessage = payload.new as Message;
          
          if (!newMessage || !newMessage.id) return;
          
          // Skip messages from the current user - they're handled by optimistic updates
          // This prevents duplicate messages when sending
          if (newMessage.sender_id === userId) {
            if (import.meta.env.MODE === 'development') {
              console.log('[MessagesRealtime] Skipping own message (handled by optimistic update), id:', newMessage.id);
            }
            return;
          }
          
          if (import.meta.env.MODE === 'development') {
            console.log('[MessagesRealtime] New message received from other user, id:', newMessage.id);
          }

          // Directly update messages cache for this conversation
          queryClient.setQueryData<MessageListResponse>(
            messagesKeys.list(newMessage.conversation_id),
            (old) => {
              if (!old) return old;
              
              // Check if message already exists (prevent duplicates)
              const exists = old.messages.some(msg => msg.id === newMessage.id);
              if (exists) {
                if (import.meta.env.MODE === 'development') {
                  console.log('[MessagesRealtime] Message already exists, skipping');
                }
                return old;
              }
              
              return {
                messages: [...old.messages, newMessage],
                total: old.total + 1,
                has_more: old.has_more,
              };
            }
          );

          // Update conversation list (last message, timestamp, unread count)
          queryClient.setQueryData<Conversation[]>(
            conversationsKeys.list(),
            (old) => {
              if (!old) return old;
              
              return old.map(conv => {
                if (conv.id === newMessage.conversation_id) {
                  // If message is from someone else, increment unread count
                  const isOwnMessage = newMessage.sender_id === userId;
                  
                  return {
                    ...conv,
                    last_message: newMessage,
                    updated_at: newMessage.created_at,
                    unread_count: isOwnMessage ? conv.unread_count : conv.unread_count + 1,
                  };
                }
                return conv;
              }).sort((a, b) => 
                new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime()
              );
            }
          );

          Sentry.addBreadcrumb({
            category: 'realtime',
            message: 'Message created',
            level: 'info',
            data: { messageId: newMessage.id, conversationId: newMessage.conversation_id },
          });
        }
      )
      .on(
        'postgres_changes',
        {
          event: 'DELETE',
          schema: 'public',
          table: 'messages',
        },
        (payload: RealtimePostgresChangesPayload<Message>) => {
          const deletedMessage = payload.old as Message;
          const deletedId = deletedMessage?.id;
          const conversationId = deletedMessage?.conversation_id;
          
          if (!deletedId || !conversationId) return;
          
          if (import.meta.env.MODE === 'development') {
            console.log('[MessagesRealtime] Message deleted, id:', deletedId);
          }

          // Remove deleted message from React Query cache
          queryClient.setQueryData<MessageListResponse>(
            messagesKeys.list(conversationId),
            (old) => old
              ? {
                  messages: old.messages.filter(msg => msg.id !== deletedId),
                  total: Math.max(0, old.total - 1),
                  has_more: old.has_more
                }
              : old
          );

          Sentry.addBreadcrumb({
            category: 'realtime',
            message: 'Message deleted',
            level: 'info',
            data: { messageId: deletedId, conversationId },
          });
        }
      )
      .on(
        'postgres_changes',
        {
          event: 'UPDATE',
          schema: 'public',
          table: 'messages',
        },
        (payload: RealtimePostgresChangesPayload<Message>) => {
          const updatedMessage = payload.new as Message;
          
          if (!updatedMessage || !updatedMessage.id) return;
          
          if (import.meta.env.MODE === 'development') {
            console.log('[MessagesRealtime] Message updated, id:', updatedMessage.id);
          }

          // Update message in cache
          queryClient.setQueryData<MessageListResponse>(
            messagesKeys.list(updatedMessage.conversation_id),
            (old) => {
              if (!old) return old;
              
              return {
                messages: old.messages.map(msg => 
                  msg.id === updatedMessage.id ? updatedMessage : msg
                ),
                total: old.total,
                has_more: old.has_more,
              };
            }
          );

          Sentry.addBreadcrumb({
            category: 'realtime',
            message: 'Message updated',
            level: 'info',
            data: { messageId: updatedMessage.id },
          });
        }
      )
      .subscribe((status: string) => {
        if (status === 'SUBSCRIBED') {
          if (import.meta.env.MODE === 'development') {
            console.log('[MessagesRealtime] Successfully subscribed to messages');
          }
        } else if (status === 'CHANNEL_ERROR') {
          console.error('[MessagesRealtime] Channel error');
          Sentry.captureMessage('Supabase Realtime channel error for messages', {
            level: 'error',
            tags: { component: 'useMessagesRealtime' },
          });
        } else if (status === 'TIMED_OUT') {
          console.error('[MessagesRealtime] Connection timed out');
        } else if (status === 'CLOSED') {
          if (!isUnsubscribingRef.current && import.meta.env.MODE === 'development') {
            console.warn('[MessagesRealtime] Channel closed unexpectedly');
          }
        }
      });

    channelRef.current = channel;

    // Cleanup function
    return () => {
      isUnsubscribingRef.current = true;
      if (channelRef.current) {
        if (import.meta.env.MODE === 'development') {
          console.log('[MessagesRealtime] Unsubscribing from messages');
        }
        supabase.removeChannel(channelRef.current);
        channelRef.current = null;
      }
    };
  }, [authContext?.isAuthenticated, authContext?.user?.id, queryClient]);
};

