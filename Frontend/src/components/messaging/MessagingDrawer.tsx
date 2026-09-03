import React, { useState, useRef, useEffect, useMemo, useCallback } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useMessaging } from '../../contexts/MessagingContext';
import { useConversations, useCreateConversation } from '../../hooks/useConversations';
import { useMessages, useSendMessage, useMarkConversationAsRead, useDeleteMessage, messagesKeys } from '../../hooks/useMessages';
import { useMessagesRealtime } from '../../hooks/useMessagesRealtime';
import { fetchMessages, type Conversation, type MessageListResponse } from '../../utils/api/messages';
import { fetchTenants } from '../../utils/api/tenants';
import type { EnrichedTenant } from '../../types/tenant';
import * as Sentry from '@sentry/react';

const MessagingDrawer: React.FC = () => {
  const { isDrawerOpen, closeDrawer, selectedTenantId } = useMessaging();
  const queryClient = useQueryClient();
  const [selectedConversation, setSelectedConversation] = useState<Conversation | null>(null);
  const [messageText, setMessageText] = useState('');
  const [searchTerm, setSearchTerm] = useState('');
  const [showTenantSelector, setShowTenantSelector] = useState(false);
  const [tenantSearchTerm, setTenantSearchTerm] = useState('');
  const [isLoadingMore, setIsLoadingMore] = useState(false);
  const [hoveredMessageId, setHoveredMessageId] = useState<string | null>(null);
  const [deleteConfirmId, setDeleteConfirmId] = useState<string | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const drawerRef = useRef<HTMLDivElement>(null);
  const messagesContainerRef = useRef<HTMLDivElement>(null);

  // Fetch conversations using React Query
  const { data: conversations = [], isLoading: loadingConversations } = useConversations();

  // Fetch tenants for selector - prefetch when drawer opens for instant response when clicking plus
  const { data: allTenants = [], isLoading: loadingTenants } = useQuery<EnrichedTenant[]>({
    queryKey: ['tenants'],
    queryFn: () => fetchTenants(),
    staleTime: 10 * 60 * 1000, // 10 minutes - data stays fresh
    gcTime: 30 * 60 * 1000, // 30 minutes - keep in cache (formerly cacheTime)
    enabled: isDrawerOpen, // Prefetch as soon as drawer opens for instant response
    refetchOnWindowFocus: false, // Don't refetch on window focus
  });

  // Fetch messages for selected conversation
  const { data: messagesData, isLoading: loadingMessages } = useMessages(
    selectedConversation?.id || null,
    !!selectedConversation
  );

  // Send message mutation
  const sendMessageMutation = useSendMessage(selectedConversation?.id || null);

  // Mark as read mutation
  const markAsReadMutation = useMarkConversationAsRead();

  // Delete message mutation
  const deleteMessageMutation = useDeleteMessage(selectedConversation?.id || null);

  // Create conversation mutation
  const createConversationMutation = useCreateConversation();

  // Enable real-time updates
  useMessagesRealtime();

  // Get existing tenant IDs for tenant selector - memoized to prevent unnecessary recalculations
  const existingTenantIds = useMemo(
    () => conversations.map(conv => conv.tenant_id),
    [conversations]
  );

  // Filter available tenants - only show tenants with portal access (user_id set)
  const availableTenants = useMemo(() => {
    return allTenants
      .filter((tenant: EnrichedTenant) => !existingTenantIds.includes(tenant.id))
      .filter((tenant: EnrichedTenant) => !!tenant.user_id) // Only tenants with portal access
      .filter((tenant: EnrichedTenant) => {
        if (!tenantSearchTerm) return true;
        const name = tenant.tenant_type === 'Company' 
          ? tenant.company_name 
          : `${tenant.first_name} ${tenant.last_name}`;
        return name?.toLowerCase().includes(tenantSearchTerm.toLowerCase());
      });
  }, [allTenants, existingTenantIds, tenantSearchTerm]);

  const getTenantName = useCallback((tenant: EnrichedTenant) => {
    return tenant.tenant_type === 'Company'
      ? tenant.company_name || 'Company'
      : `${tenant.first_name || ''} ${tenant.last_name || ''}`.trim() || 'Tenant';
  }, []);

  const getTenantInitials = useCallback((tenant: EnrichedTenant) => {
    const name = tenant.tenant_type === 'Company'
      ? tenant.company_name || 'Company'
      : `${tenant.first_name || ''} ${tenant.last_name || ''}`.trim() || 'Tenant';
    return name.split(' ').map((n: string) => n[0]).join('').toUpperCase().slice(0, 2);
  }, []);

  const messages = messagesData?.messages || [];
  const hasMore = messagesData?.has_more || false;

  // Close drawer when clicking outside
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (drawerRef.current && !drawerRef.current.contains(event.target as Node)) {
        closeDrawer();
      }
    };

    if (isDrawerOpen) {
      document.addEventListener('mousedown', handleClickOutside);
    }

    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, [isDrawerOpen, closeDrawer]);

  // Close on escape key
  useEffect(() => {
    const handleEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        closeDrawer();
      }
    };

    if (isDrawerOpen) {
      document.addEventListener('keydown', handleEscape);
    }

    return () => {
      document.removeEventListener('keydown', handleEscape);
    };
  }, [isDrawerOpen, closeDrawer]);

  // Scroll to bottom of messages
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  // Mark as read when selecting conversation
  useEffect(() => {
    if (selectedConversation && selectedConversation.unread_count > 0) {
      markAsReadMutation.mutate(selectedConversation.id);
    }
  }, [selectedConversation?.id]);

  // If a tenant ID is provided, auto-select that conversation or create it
  useEffect(() => {
    if (selectedTenantId && conversations.length > 0) {
      const conv = conversations.find(c => c.tenant_id === selectedTenantId);
      if (conv) {
        setSelectedConversation(conv);
      } else {
        // Create new conversation
        handleCreateConversation(selectedTenantId);
      }
    }
  }, [selectedTenantId, conversations]);

  const handleCreateConversation = useCallback(async (tenantId: number, tenantName?: string) => {
    try {
      const newConversation = await createConversationMutation.mutateAsync({ tenant_id: tenantId });
      setSelectedConversation(newConversation);
      setShowTenantSelector(false);
      setTenantSearchTerm('');
      if (tenantName) {
        Sentry.addBreadcrumb({
          category: 'messaging',
          message: `Started conversation with ${tenantName}`,
          level: 'info',
        });
      }
    } catch (error) {
      console.error('Error creating conversation:', error);
      Sentry.captureException(error, {
        tags: { component: 'MessagingDrawer', action: 'create_conversation' },
      });
    }
  }, [createConversationMutation]);

  const handleSendMessage = useCallback(async (e: React.FormEvent) => {
    e.preventDefault();
    if (!messageText.trim() || !selectedConversation) return;

    try {
      await sendMessageMutation.mutateAsync({
        conversation_id: selectedConversation.id,
        content: messageText,
        message_type: 'DIRECT',
      });
      setMessageText('');
    } catch (error) {
      console.error('Error sending message:', error);
      Sentry.captureException(error, {
        tags: { component: 'MessagingDrawer', action: 'send_message' },
      });
    }
  }, [messageText, selectedConversation, sendMessageMutation]);

  const handleDeleteMessage = useCallback(async (messageId: string) => {
    try {
      await deleteMessageMutation.mutateAsync(messageId);
      setDeleteConfirmId(null);
    } catch (error) {
      console.error('Error deleting message:', error);
      // Error is already captured by the mutation
    }
  }, [deleteMessageMutation]);

  const handleLoadMore = useCallback(async () => {
    if (!selectedConversation || isLoadingMore || !hasMore || messages.length === 0) return;

    setIsLoadingMore(true);
    const container = messagesContainerRef.current;
    const oldScrollHeight = container?.scrollHeight || 0;

    try {
      const oldestMessage = messages[0];
      const olderMessages = await fetchMessages(selectedConversation.id, {
        limit: 50,
        before_id: oldestMessage.id,
      });

      if (olderMessages.messages.length > 0) {
        queryClient.setQueryData<MessageListResponse>(
          messagesKeys.list(selectedConversation.id),
          (old) => ({
            messages: [...olderMessages.messages, ...(old?.messages || [])],
            total: olderMessages.total,
            has_more: olderMessages.has_more,
          })
        );

        // Maintain scroll position after prepending messages
        setTimeout(() => {
          if (container) {
            const newScrollHeight = container.scrollHeight;
            container.scrollTop = newScrollHeight - oldScrollHeight;
          }
        }, 0);
      }
    } catch (error) {
      console.error('Error loading more messages:', error);
      Sentry.captureException(error, {
        tags: { component: 'MessagingDrawer', action: 'load_more' },
      });
    } finally {
      setIsLoadingMore(false);
    }
  }, [selectedConversation, isLoadingMore, hasMore, messages, queryClient]);

  const formatMessageTime = useCallback((dateString: string) => {
    const date = new Date(dateString);
    const now = new Date();

    if (date.toDateString() === now.toDateString()) {
      return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    }

    if (date.getFullYear() === now.getFullYear()) {
      return date.toLocaleDateString([], { month: 'short', day: 'numeric' });
    }

    return date.toLocaleDateString();
  }, []);

  const filteredConversations = useMemo(
    () => conversations.filter(conv =>
      conv.tenant_name?.toLowerCase().includes(searchTerm.toLowerCase())
    ),
    [conversations, searchTerm]
  );

  return (
    <>
      {/* Hide reCAPTCHA badge and custom notice when drawer is open */}
      {isDrawerOpen && (
        <style>{`
          .grecaptcha-badge,
          .recaptcha-notice {
            visibility: hidden !important;
            opacity: 0 !important;
            pointer-events: none !important;
          }
        `}</style>
      )}

      {/* Backdrop */}
      <div
        className={`fixed inset-0 bg-black/30 z-40 transition-opacity duration-300 ${
          isDrawerOpen ? 'opacity-100' : 'opacity-0 pointer-events-none'
        }`}
        aria-hidden="true"
      />

      {/* Delete Confirmation Dialog */}
      {deleteConfirmId && (
        <div 
          className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4" 
          style={{ zIndex: 60 }}
          onClick={(e) => {
            e.stopPropagation();
            setDeleteConfirmId(null);
          }}
        >
          <div 
            className="bg-white dark:bg-gray-800 rounded-lg shadow-xl max-w-sm w-full p-6"
            onClick={(e) => e.stopPropagation()}
          >
            <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-2">Delete Message?</h3>
            <p className="text-sm text-gray-600 dark:text-gray-400 mb-6">
              This message will be permanently deleted. This action cannot be undone.
            </p>
            <div className="flex gap-3 justify-end">
              <button
                type="button"
                onClick={() => setDeleteConfirmId(null)}
                className="px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-300 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-600 transition-colors"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={() => handleDeleteMessage(deleteConfirmId)}
                disabled={deleteMessageMutation.isPending}
                className="px-4 py-2 text-sm font-medium text-white bg-red-600 rounded-lg hover:bg-red-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
              >
                {deleteMessageMutation.isPending ? 'Deleting...' : 'Delete'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Drawer */}
      <div
        ref={drawerRef}
        className={`fixed top-0 right-0 h-full w-full sm:w-[480px] bg-white dark:bg-gray-800 shadow-2xl z-50 transform transition-transform duration-300 ease-in-out ${
          isDrawerOpen ? 'translate-x-0' : 'translate-x-full'
        }`}
      >
        <div className="flex flex-col h-full">
          {/* Header */}
          <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200 dark:border-gray-700">
            <div className="flex items-center gap-3">
              <button
                onClick={(e) => {
                  e.preventDefault();
                  e.stopPropagation();
                  closeDrawer();
                }}
                type="button"
                className="p-2 text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg transition-colors"
                aria-label="Close messages"
              >
                <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
              <h2 className="text-xl font-semibold text-gray-900 dark:text-gray-100">
                Messages
              </h2>
            </div>
            <button
              onClick={(e) => {
                e.preventDefault();
                e.stopPropagation();
                setShowTenantSelector(true);
              }}
              type="button"
              className="p-2 text-green-600 hover:text-green-700 dark:text-green-500 dark:hover:text-green-400 hover:bg-green-50 dark:hover:bg-green-900/20 rounded-lg transition-colors"
              aria-label="New conversation"
              title="Start a new conversation"
            >
              <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M12 4v16m8-8H4" />
              </svg>
            </button>
          </div>

          {/* Content */}
          <div className="flex-1 flex overflow-hidden">
            {/* Conversation List or Tenant Selector */}
            <div className={`${selectedConversation ? 'hidden' : 'flex'} flex-col w-full`}>
              {showTenantSelector ? (
                <>
                  {/* Tenant Selector Header */}
                  <div className="px-6 py-4 border-b border-gray-200 dark:border-gray-700">
                    <div className="flex items-center gap-3 mb-3">
                    <button
                      onClick={(e) => {
                        e.preventDefault();
                        e.stopPropagation();
                        setShowTenantSelector(false);
                        setTenantSearchTerm('');
                      }}
                      type="button"
                      className="p-1 text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg transition-colors"
                    >
                        <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
                        </svg>
                      </button>
                      <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100">
                        New Conversation
                      </h3>
                    </div>
                    <p className="text-sm text-gray-500 dark:text-gray-400 mb-3">
                      Select a tenant to start messaging
                    </p>
                    <div className="relative">
                      <input
                        type="text"
                        placeholder="Search tenants..."
                        value={tenantSearchTerm}
                        onChange={(e) => setTenantSearchTerm(e.target.value)}
                        className="w-full pl-10 pr-3 py-2 text-sm border border-gray-300 dark:border-gray-600 rounded-lg bg-gray-50 dark:bg-gray-700 text-gray-900 dark:text-gray-100 placeholder-gray-500 dark:placeholder-gray-400 focus:ring-2 focus:ring-green-500 focus:border-transparent"
                        autoFocus
                      />
                      <svg className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
                      </svg>
                    </div>
                  </div>

                  {/* Tenant List */}
                  <div className="flex-1 overflow-y-auto">
                    {loadingTenants ? (
                      <div className="flex items-center justify-center h-32">
                        <div className="w-8 h-8 border-4 border-green-200 border-t-green-600 rounded-full animate-spin" />
                      </div>
                    ) : availableTenants.length > 0 ? (
                      <div className="divide-y divide-gray-100 dark:divide-gray-700">
                        {availableTenants.map((tenant: EnrichedTenant) => (
                          <button
                            key={tenant.id}
                            onClick={(e) => {
                              e.preventDefault();
                              e.stopPropagation();
                              handleCreateConversation(tenant.id, getTenantName(tenant));
                            }}
                            type="button"
                            className="w-full px-6 py-3 flex items-center gap-3 hover:bg-gray-50 dark:hover:bg-gray-700/50 transition-colors"
                          >
                            <div className="flex-shrink-0 w-10 h-10 rounded-full overflow-hidden bg-gradient-to-br from-green-500 to-green-600 flex items-center justify-center">
                              {tenant.profile_image_url ? (
                                <img
                                  src={tenant.profile_image_url}
                                  alt={getTenantName(tenant)}
                                  className="w-full h-full object-cover"
                                />
                              ) : (
                                <span className="text-white font-medium text-sm">
                                  {getTenantInitials(tenant)}
                                </span>
                              )}
                            </div>
                            <div className="flex-1 text-left">
                              <p className="text-sm font-medium text-gray-900 dark:text-gray-100">
                                {getTenantName(tenant)}
                              </p>
                              {tenant.email && (
                                <p className="text-xs text-gray-500 dark:text-gray-400">
                                  {tenant.email}
                                </p>
                              )}
                            </div>
                          </button>
                        ))}
                      </div>
                    ) : (
                      <div className="flex flex-col items-center justify-center h-32 px-6 text-center">
                        <p className="text-sm text-gray-500 dark:text-gray-400">
                          {tenantSearchTerm
                            ? 'No tenants found matching your search'
                            : existingTenantIds.length > 0
                            ? 'All your tenants already have conversations'
                            : 'No tenants available'}
                        </p>
                      </div>
                    )}
                  </div>
                </>
              ) : (
                <>
                  {/* Search Conversations */}
                  <div className="p-4 border-b border-gray-200 dark:border-gray-700">
                <div className="relative">
                  <input
                    type="text"
                    placeholder="Search conversations..."
                    value={searchTerm}
                    onChange={(e) => setSearchTerm(e.target.value)}
                    className="w-full pl-9 pr-3 py-2 text-sm border border-gray-300 dark:border-gray-600 rounded-lg bg-gray-50 dark:bg-gray-700 text-gray-900 dark:text-gray-100 placeholder-gray-500 dark:placeholder-gray-400 focus:ring-2 focus:ring-green-500 focus:border-transparent"
                  />
                  <svg className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
                  </svg>
                </div>
              </div>

              {/* Conversation Items */}
              <div className="flex-1 overflow-y-auto">
                {loadingConversations ? (
                  <div className="flex items-center justify-center h-32">
                    <div className="w-8 h-8 border-4 border-green-200 border-t-green-600 rounded-full animate-spin" />
                  </div>
                ) : filteredConversations.length > 0 ? (
                  filteredConversations.map((conversation) => (
                    <button
                      key={conversation.id}
                      onClick={(e) => {
                        e.preventDefault();
                        e.stopPropagation();
                        setSelectedConversation(conversation);
                      }}
                      type="button"
                      className={`w-full p-3 flex items-start gap-3 hover:bg-gray-50 dark:hover:bg-gray-700/50 transition-colors border-b border-gray-100 dark:border-gray-700/50 ${
                        selectedConversation?.id === conversation.id ? 'bg-green-50 dark:bg-green-900/20' : ''
                      }`}
                    >
                      <div className="flex-shrink-0 w-10 h-10 rounded-full overflow-hidden bg-gradient-to-br from-green-500 to-green-600 flex items-center justify-center">
                        {conversation.tenant_avatar_url ? (
                          <img
                            src={conversation.tenant_avatar_url}
                            alt={conversation.tenant_name || 'Tenant'}
                            className="w-full h-full object-cover"
                          />
                        ) : (
                          <span className="text-white font-medium text-sm">
                            {conversation.tenant_name?.split(' ').map(n => n[0]).join('').toUpperCase() || 'T'}
                          </span>
                        )}
                      </div>
                      <div className="flex-1 min-w-0 text-left">
                        <div className="flex items-center justify-between">
                          <p className="text-sm font-medium text-gray-900 dark:text-gray-100 truncate">
                            {conversation.tenant_name || 'Tenant'}
                          </p>
                          {conversation.last_message && (
                            <span className="text-xs text-gray-500 dark:text-gray-400">
                              {formatMessageTime(conversation.last_message.created_at)}
                            </span>
                          )}
                        </div>
                        <p className="text-sm text-gray-500 dark:text-gray-400 truncate">
                          {conversation.last_message?.content || 'No messages yet'}
                        </p>
                      </div>
                      {conversation.unread_count > 0 && (
                        <span className="flex-shrink-0 w-5 h-5 bg-green-500 text-white text-xs font-bold rounded-full flex items-center justify-center">
                          {conversation.unread_count}
                        </span>
                      )}
                    </button>
                  ))
                ) : (
                  <div className="flex flex-col items-center justify-center h-full px-8 py-16 text-center">
                    <div className="relative mb-6">
                      <div className="w-20 h-20 bg-gradient-to-br from-green-500 to-green-600 rounded-full flex items-center justify-center shadow-lg">
                        <svg className="w-10 h-10 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                          <path strokeLinecap="round" strokeLinejoin="round" d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
                        </svg>
                      </div>
                      <div className="absolute -bottom-1 -right-1 w-7 h-7 bg-white dark:bg-gray-800 rounded-full flex items-center justify-center shadow-md">
                        <div className="w-5 h-5 bg-green-100 dark:bg-green-900 rounded-full flex items-center justify-center">
                          <svg className="w-3 h-3 text-green-600 dark:text-green-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={3}>
                            <path strokeLinecap="round" strokeLinejoin="round" d="M12 4v16m8-8H4" />
                          </svg>
                        </div>
                      </div>
                    </div>
                    <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-2">
                      No conversations yet
                    </h3>
                    <p className="text-sm text-gray-500 dark:text-gray-400 mb-6 max-w-xs">
                      Start messaging your tenants to keep everyone in the loop
                    </p>
                    <button
                      onClick={(e) => {
                        e.preventDefault();
                        e.stopPropagation();
                        setShowTenantSelector(true);
                      }}
                      type="button"
                      className="inline-flex items-center gap-2 px-5 py-2.5 bg-green-600 hover:bg-green-700 text-white font-medium rounded-lg transition-colors shadow-sm"
                    >
                      <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                        <path strokeLinecap="round" strokeLinejoin="round" d="M12 4v16m8-8H4" />
                      </svg>
                      Start a conversation
                    </button>
                  </div>
                )}
              </div>
                </>
              )}
            </div>

            {/* Message Thread */}
            <div className={`${selectedConversation ? 'flex' : 'hidden'} flex-col w-full`}>
              {selectedConversation ? (
                <>
                  {/* Thread Header */}
                  <div className="flex items-center gap-3 px-4 py-3 border-b border-gray-200 dark:border-gray-700">
                    <button
                      onClick={(e) => {
                        e.preventDefault();
                        e.stopPropagation();
                        setSelectedConversation(null);
                      }}
                      type="button"
                      className="p-1 text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200"
                    >
                      <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
                      </svg>
                    </button>
                    <div className="flex-shrink-0 w-8 h-8 rounded-full overflow-hidden bg-gradient-to-br from-green-500 to-green-600 flex items-center justify-center">
                      {selectedConversation.tenant_avatar_url ? (
                        <img
                          src={selectedConversation.tenant_avatar_url}
                          alt={selectedConversation.tenant_name || 'Tenant'}
                          className="w-full h-full object-cover"
                        />
                      ) : (
                        <span className="text-white font-medium text-xs">
                          {selectedConversation.tenant_name?.split(' ').map(n => n[0]).join('').toUpperCase() || 'T'}
                        </span>
                      )}
                    </div>
                    <div>
                      <p className="text-sm font-medium text-gray-900 dark:text-gray-100">
                        {selectedConversation.tenant_name || 'Tenant'}
                      </p>
                      {selectedConversation.tenant_email && (
                        <p className="text-xs text-gray-500 dark:text-gray-400">
                          {selectedConversation.tenant_email}
                        </p>
                      )}
                    </div>
                  </div>

                  {/* Messages */}
                  <div ref={messagesContainerRef} className="flex-1 overflow-y-auto p-4 space-y-3">
                    {loadingMessages ? (
                      <div className="flex items-center justify-center h-full">
                        <div className="w-8 h-8 border-4 border-green-200 border-t-green-600 rounded-full animate-spin" />
                      </div>
                    ) : messages.length > 0 ? (
                      <>
                        {/* Load More Button */}
                        {hasMore && (
                          <div className="flex justify-center mb-4">
                            <button
                              type="button"
                              onClick={handleLoadMore}
                              disabled={isLoadingMore}
                              className="px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-300 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-600 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                            >
                              {isLoadingMore ? (
                                <span className="flex items-center gap-2">
                                  <div className="w-4 h-4 border-2 border-gray-300 border-t-green-600 rounded-full animate-spin" />
                                  Loading...
                                </span>
                              ) : (
                                'Load earlier messages'
                              )}
                            </button>
                          </div>
                        )}
                        {messages.map((message) => {
                        const isOwn = message.sender_id === selectedConversation.landlord_id;
                        return (
                          <div
                            key={message.id}
                            className={`flex ${isOwn ? 'justify-end' : 'justify-start'}`}
                          >
                            <div
                              className={`relative max-w-[85%] ${isOwn ? 'pl-10' : ''}`}
                              onMouseEnter={() => isOwn && setHoveredMessageId(message.id)}
                              onMouseLeave={() => isOwn && setHoveredMessageId(null)}
                            >
                              {/* Delete button for own messages */}
                              {isOwn && (
                                <button
                                  type="button"
                                  onClick={() => setDeleteConfirmId(message.id)}
                                  className={`absolute left-0 top-1/2 -translate-y-1/2 p-1.5 text-red-600 hover:bg-red-50 dark:hover:bg-red-900/20 rounded-lg transition-opacity cursor-pointer ${
                                    hoveredMessageId === message.id ? 'opacity-100' : 'opacity-0 pointer-events-none'
                                  }`}
                                  title="Delete message"
                                >
                                  <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                                    <path strokeLinecap="round" strokeLinejoin="round" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                                  </svg>
                                </button>
                              )}
                              
                              {/* Message bubble */}
                              <div
                                className={`rounded-2xl px-4 py-2 ${
                                  isOwn
                                    ? 'bg-green-600 text-white'
                                    : 'bg-gray-100 dark:bg-gray-700 text-gray-900 dark:text-gray-100'
                                }`}
                              >
                                <p className="text-sm break-words">{message.content}</p>
                                <p className={`text-xs mt-1 text-right ${isOwn ? 'text-green-200' : 'text-gray-500 dark:text-gray-400'}`}>
                                  {formatMessageTime(message.created_at)}
                                </p>
                              </div>
                            </div>
                          </div>
                        );
                      })}
                      </>
                    ) : (
                      <div className="flex flex-col items-center justify-center h-full text-center">
                        <p className="text-sm text-gray-500 dark:text-gray-400">
                          No messages yet. Start the conversation!
                        </p>
                      </div>
                    )}
                    <div ref={messagesEndRef} />
                  </div>

                  {/* Message Input */}
                  <form onSubmit={handleSendMessage} className="p-3 border-t border-gray-200 dark:border-gray-700">
                    <div className="flex items-center gap-2">
                      <input
                        type="text"
                        value={messageText}
                        onChange={(e) => setMessageText(e.target.value)}
                        placeholder="Type a message..."
                        className="flex-1 px-4 py-2 text-sm border border-gray-300 dark:border-gray-600 rounded-full bg-gray-50 dark:bg-gray-700 text-gray-900 dark:text-gray-100 placeholder-gray-500 dark:placeholder-gray-400 focus:ring-2 focus:ring-green-500 focus:border-transparent"
                      />
                      <button
                        type="submit"
                        disabled={!messageText.trim() || sendMessageMutation.isPending}
                        className="p-2 bg-green-600 text-white rounded-full hover:bg-green-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                      >
                        {sendMessageMutation.isPending ? (
                          <div className="w-5 h-5 border-2 border-white border-t-transparent rounded-full animate-spin" />
                        ) : (
                          <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8" />
                          </svg>
                        )}
                      </button>
                    </div>
                  </form>
                </>
              ) : (
                <div className="flex flex-col items-center justify-center h-full px-8 text-center">
                  <div className="w-20 h-20 bg-gray-100 dark:bg-gray-700 rounded-full flex items-center justify-center mb-4">
                    <svg className="w-10 h-10 text-gray-400 dark:text-gray-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
                    </svg>
                  </div>
                  <h3 className="text-lg font-medium text-gray-900 dark:text-gray-100 mb-2">
                    Select a conversation
                  </h3>
                  <p className="text-sm text-gray-500 dark:text-gray-400">
                    Choose a conversation from the list to view and send messages
                  </p>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    </>
  );
};

export default MessagingDrawer;
