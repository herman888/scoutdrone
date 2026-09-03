/**
 * QuickBooks Integration TanStack Query Hooks
 *
 * Custom hooks for QuickBooks integration data fetching and mutations.
 * Uses TanStack Query for caching, background refetching, and optimistic updates.
 */

import {
  useQuery,
  useMutation,
  useQueryClient,
  type UseQueryResult,
  type UseMutationResult,
} from '@tanstack/react-query';
import { toast } from 'react-toastify';
import * as Sentry from '@sentry/react';
import {
  getQuickBooksStatus,
  connectToQuickBooks,
  disconnectQuickBooks,
  syncAllQuickBooksData,
  getQuickBooksSettings,
  updateQuickBooksSettings,
} from '../utils/api/quickbooks';
import type {
  QuickBooksStatus,
  QuickBooksSyncResponse,
  QuickBooksConnectResponse,
  QuickBooksSettings,
  QuickBooksSettingsResponse,
  QuickBooksSettingsUpdate,
} from '../types/integrations';

// ============================================================================
// Query Keys - Centralized key management for cache invalidation
// ============================================================================

export const quickBooksKeys = {
  all: ['quickbooks'] as const,
  status: () => [...quickBooksKeys.all, 'status'] as const,
  settings: () => [...quickBooksKeys.all, 'settings'] as const,
  accounts: () => [...quickBooksKeys.all, 'accounts'] as const,
  accountMappings: () => [...quickBooksKeys.all, 'account-mappings'] as const,
};

// ============================================================================
// Query Hooks
// ============================================================================

/**
 * Hook to fetch QuickBooks connection status
 * Automatically refetches on window focus and at regular intervals when connected
 */
export function useQuickBooksStatus(): UseQueryResult<QuickBooksStatus, Error> {
  return useQuery({
    queryKey: quickBooksKeys.status(),
    queryFn: getQuickBooksStatus,
    staleTime: 30 * 1000, // 30 seconds - status can change frequently
    refetchOnWindowFocus: true,
    refetchInterval: (query) => {
      // Refetch every 5 minutes if connected to catch webhook updates
      return query.state.data?.connected ? 5 * 60 * 1000 : false;
    },
    retry: 2,
    meta: {
      errorMessage: 'Failed to load QuickBooks status',
    },
  });
}

/**
 * Hook to fetch QuickBooks settings
 * Only fetches when connected (enabled by status)
 */
export function useQuickBooksSettings(
  isConnected: boolean
): UseQueryResult<QuickBooksSettingsResponse, Error> {
  return useQuery({
    queryKey: quickBooksKeys.settings(),
    queryFn: async () => {
      const response = await getQuickBooksSettings();
      return response as QuickBooksSettingsResponse;
    },
    enabled: isConnected,
    staleTime: 2 * 60 * 1000, // 2 minutes
    retry: 1,
  });
}

// ============================================================================
// Mutation Hooks
// ============================================================================

/**
 * Hook to initiate QuickBooks OAuth connection
 * Handles redirect to QuickBooks authorization page
 */
export function useConnectQuickBooks(): UseMutationResult<
  QuickBooksConnectResponse,
  Error,
  void
> {
  return useMutation({
    mutationFn: connectToQuickBooks,
    onSuccess: (response) => {
      if (response?.redirect_url) {
        // Announce navigation to screen readers
        const announcement = document.createElement('div');
        announcement.setAttribute('aria-live', 'assertive');
        announcement.setAttribute('aria-atomic', 'true');
        announcement.className = 'sr-only';
        announcement.textContent = 'Redirecting to QuickBooks for authentication';
        document.body.appendChild(announcement);

        setTimeout(() => {
          document.body.removeChild(announcement);
          window.location.href = response.redirect_url!;
        }, 100);
      } else {
        throw new Error('No redirect URL received from server.');
      }
    },
    onError: (error) => {
      const message = error.message || 'Failed to initiate QuickBooks connection.';
      toast.error(message);
      Sentry.captureException(error, {
        tags: { component: 'QuickBooks', action: 'connect' },
      });
    },
  });
}

/**
 * Hook to disconnect from QuickBooks
 * Invalidates all QuickBooks-related queries on success
 */
export function useDisconnectQuickBooks(): UseMutationResult<void, Error, void> {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: disconnectQuickBooks,
    onSuccess: () => {
      toast.success('Successfully disconnected from QuickBooks.');
      // Invalidate all QuickBooks data
      queryClient.invalidateQueries({ queryKey: quickBooksKeys.all });
    },
    onError: (error) => {
      const message = error.message || 'Failed to disconnect from QuickBooks.';
      toast.error(message);
      Sentry.captureException(error, {
        tags: { component: 'QuickBooks', action: 'disconnect' },
      });
    },
  });
}

/**
 * Hook to sync all QuickBooks data
 * Refetches status on success to update last_sync timestamp
 */
export function useSyncAllQuickBooks(): UseMutationResult<
  QuickBooksSyncResponse,
  Error,
  void
> {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: syncAllQuickBooksData,
    onMutate: () => {
      toast.info('Starting sync with QuickBooks...');
    },
    onSuccess: (result) => {
      if (result?.success) {
        const message = result.message || 'Sync completed successfully';
        toast.success(message);
      } else {
        const errorMessage = result?.message || 'Sync completed with issues';
        toast.warning(errorMessage);
      }
      // Refresh status to get updated last_sync timestamp
      queryClient.invalidateQueries({ queryKey: quickBooksKeys.status() });
    },
    onError: (error) => {
      const message = error.message || 'Failed to sync with QuickBooks.';
      toast.error(message);
      Sentry.captureException(error, {
        tags: { component: 'QuickBooks', action: 'syncAll' },
      });
    },
  });
}

/**
 * Hook to update QuickBooks settings
 * Optimistically updates the cache for instant UI feedback
 */
export function useUpdateQuickBooksSettings(): UseMutationResult<
  QuickBooksSettingsResponse,
  Error,
  QuickBooksSettingsUpdate
> {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (settings: QuickBooksSettingsUpdate) => {
      const response = await updateQuickBooksSettings(settings);
      return response as QuickBooksSettingsResponse;
    },
    // Optimistic update
    onMutate: async (newSettings) => {
      // Cancel outgoing refetches
      await queryClient.cancelQueries({ queryKey: quickBooksKeys.settings() });

      // Snapshot previous value
      const previousSettings = queryClient.getQueryData<QuickBooksSettingsResponse>(
        quickBooksKeys.settings()
      );

      // Optimistically update
      if (previousSettings) {
        queryClient.setQueryData<QuickBooksSettingsResponse>(
          quickBooksKeys.settings(),
          {
            ...previousSettings,
            settings: {
              ...previousSettings.settings,
              ...newSettings,
            },
          }
        );
      }

      return { previousSettings };
    },
    onSuccess: () => {
      toast.success('Settings saved successfully');
    },
    onError: (error, _variables, context) => {
      // Rollback on error
      if (context?.previousSettings) {
        queryClient.setQueryData(quickBooksKeys.settings(), context.previousSettings);
      }
      const message = error.message || 'Failed to save settings.';
      toast.error(message);
      Sentry.captureException(error, {
        tags: { component: 'QuickBooksSettings', action: 'update' },
      });
    },
    onSettled: () => {
      // Refetch to ensure consistency
      queryClient.invalidateQueries({ queryKey: quickBooksKeys.settings() });
    },
  });
}

// ============================================================================
// Combined Hook for Integration Page
// ============================================================================

export interface UseQuickBooksIntegrationReturn {
  // Status
  status: QuickBooksStatus | null;
  isStatusLoading: boolean;
  isStatusError: boolean;
  statusError: Error | null;

  // Settings
  settings: QuickBooksSettings | null;
  isSettingsLoading: boolean;
  autoSyncEnabled: boolean;

  // Connection actions
  connect: () => void;
  isConnecting: boolean;
  disconnect: () => void;
  isDisconnecting: boolean;

  // Sync actions
  syncAll: () => void;
  isSyncing: boolean;

  // Settings actions
  updateSettings: (settings: QuickBooksSettingsUpdate) => void;
  isUpdatingSettings: boolean;

  // Utilities
  refetchStatus: () => void;
  isAnyOperationInProgress: boolean;
}

/**
 * Comprehensive hook combining all QuickBooks integration functionality
 * Provides a clean interface for the Integrations page
 */
export function useQuickBooksIntegrationV2(): UseQuickBooksIntegrationReturn {
  const queryClient = useQueryClient();

  // Queries
  const statusQuery = useQuickBooksStatus();
  const isConnected = statusQuery.data?.connected ?? false;
  const settingsQuery = useQuickBooksSettings(isConnected);

  // Mutations
  const connectMutation = useConnectQuickBooks();
  const disconnectMutation = useDisconnectQuickBooks();
  const syncAllMutation = useSyncAllQuickBooks();
  const updateSettingsMutation = useUpdateQuickBooksSettings();

  // Derived state
  const isAnyOperationInProgress =
    connectMutation.isPending ||
    disconnectMutation.isPending ||
    syncAllMutation.isPending ||
    updateSettingsMutation.isPending;

  const autoSyncEnabled = settingsQuery.data?.settings?.auto_sync_enabled ?? true;

  return {
    // Status
    status: statusQuery.data ?? null,
    isStatusLoading: statusQuery.isLoading,
    isStatusError: statusQuery.isError,
    statusError: statusQuery.error,

    // Settings
    settings: settingsQuery.data?.settings ?? null,
    isSettingsLoading: settingsQuery.isLoading,
    autoSyncEnabled,

    // Connection actions
    connect: () => connectMutation.mutate(),
    isConnecting: connectMutation.isPending,
    disconnect: () => disconnectMutation.mutate(),
    isDisconnecting: disconnectMutation.isPending,

    // Sync actions
    syncAll: () => syncAllMutation.mutate(),
    isSyncing: syncAllMutation.isPending,

    // Settings actions
    updateSettings: (settings) => updateSettingsMutation.mutate(settings),
    isUpdatingSettings: updateSettingsMutation.isPending,

    // Utilities
    refetchStatus: () => queryClient.invalidateQueries({ queryKey: quickBooksKeys.status() }),
    isAnyOperationInProgress,
  };
}
