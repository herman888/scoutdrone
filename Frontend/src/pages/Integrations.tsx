import React, { memo, useState, useEffect, useCallback } from 'react';
import * as Sentry from '@sentry/react';
import { toast } from 'react-toastify';
import { useQueryClient } from '@tanstack/react-query';
import IntegrationsSkeleton from '../components/ui/skeletons/IntegrationsSkeleton';
import StripeConnectCard from '../components/integrations/StripeConnectCard';
import QuickBooksCard from '../components/integrations/QuickBooksCard';
import PlaceholderCard from '../components/integrations/PlaceholderCard';
import ConfirmationModal from '../components/integrations/ConfirmationModal';
import { useQuickBooksIntegrationV2 } from '../hooks/useQuickBooksQueries';
import { useSubscriptionGuard } from '../hooks/useSubscriptionGuard';

/**
 * Integrations page component - TanStack Query powered
 *
 * Features:
 * - TanStack Query for data fetching, caching, and background refetching
 * - Clean separation of concerns with custom hooks
 * - Automatic retry and error handling
 * - OAuth callback handling via sessionStorage
 * - Subscription guard for premium features
 */
const Integrations: React.FC = memo(() => {
  // Subscription guard for premium features
  const guardAction = useSubscriptionGuard({ featureName: 'connecting to QuickBooks' });

  // QuickBooks integration state and actions
  const {
    status,
    isStatusLoading,
    isStatusError,
    statusError,
    autoSyncEnabled,
    connect,
    isConnecting,
    disconnect,
    isDisconnecting,
    isSyncing,
    isAnyOperationInProgress,
    refetchStatus,
  } = useQuickBooksIntegrationV2();

  // Query client for cache invalidation
  const queryClient = useQueryClient();
  
  // Local UI state for confirmation modal
  const [showConfirmDisconnect, setShowConfirmDisconnect] = useState(false);

  // Handle Stripe Connect redirect status
  useEffect(() => {
    const urlParams = new URLSearchParams(window.location.search);
    const connectStatus = urlParams.get('connect');
    
    if (connectStatus === 'success') {
      toast.success('Stripe Connect setup step completed! Verifying your information...');
      // Refresh Stripe Connect status to show updated state
      queryClient.invalidateQueries({ queryKey: ['connect', 'status'] });
      // Clean up URL
      window.history.replaceState({}, '', '/integrations');
    } else if (connectStatus === 'refresh') {
      toast.info('Please continue your Stripe Connect setup.');
      // Refresh status
      queryClient.invalidateQueries({ queryKey: ['connect', 'status'] });
      // Clean up URL
      window.history.replaceState({}, '', '/integrations');
    }
  }, [queryClient]);

  // Handle OAuth callback messages from QuickBooksCallback page
  useEffect(() => {
    const handleOAuthCallback = () => {
      // Check for OAuth errors
      const storedError = sessionStorage.getItem('qb_oauth_error');
      if (storedError) {
        try {
          const { error, errorDescription } = JSON.parse(storedError);
          toast.error(`QuickBooks authorization failed: ${errorDescription || error || 'Unknown error'}`);
          sessionStorage.removeItem('qb_oauth_error');
          refetchStatus();
          return;
        } catch (e) {
          sessionStorage.removeItem('qb_oauth_error');
        }
      }

      // Check for OAuth success
      const storedSuccess = sessionStorage.getItem('qb_oauth_success');
      if (storedSuccess) {
        try {
          const successData = JSON.parse(storedSuccess);
          toast.success(
            `Successfully connected to QuickBooks${successData.company_name ? ` (${successData.company_name})` : ''}!`
          );
          sessionStorage.removeItem('qb_oauth_success');
          refetchStatus();
        } catch (e) {
          sessionStorage.removeItem('qb_oauth_success');
        }
      }
    };

    handleOAuthCallback();
  }, [refetchStatus]);

  // Wrap connect with subscription guard
  const guardedConnect = useCallback(() => {
    const guardedFn = guardAction(() => connect());
    guardedFn();
  }, [guardAction, connect]);

  // Disconnect handlers
  const handleDisconnect = useCallback(() => {
    setShowConfirmDisconnect(true);
  }, []);

  const handleConfirmDisconnect = useCallback(() => {
    setShowConfirmDisconnect(false);
    disconnect();
  }, [disconnect]);

  const handleCancelDisconnect = useCallback(() => {
    setShowConfirmDisconnect(false);
  }, []);

  // Build operation state for QuickBooksCard (backward compatibility)
  const operationState = isConnecting
    ? { type: 'loading' as const, operation: 'Connecting' }
    : isDisconnecting
      ? { type: 'loading' as const, operation: 'Disconnecting' }
      : isSyncing
        ? { type: 'syncing' as const, operation: 'all' as const }
        : isStatusError
          ? { type: 'error' as const, message: statusError?.message || 'An error occurred' }
          : { type: 'idle' as const };

  // Show skeleton during initial load only (not during background refetches)
  if (isStatusLoading && !status) {
    return (
      <Sentry.ErrorBoundary
        fallback={({ error, resetError }) => (
          <div className="p-4 text-center">
            <h2 className="text-xl font-semibold text-red-600 mb-2">
              Something went wrong loading integrations
            </h2>
            <p className="text-gray-600 dark:text-gray-400 mb-4">
              {error instanceof Error ? error.message : 'An unexpected error occurred'}
            </p>
            <button
              onClick={resetError}
              className="px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700"
            >
              Try again
            </button>
          </div>
        )}
        beforeCapture={(scope) => {
          scope.setTag('component', 'Integrations');
          scope.setTag('page', 'integrations');
        }}
      >
        <IntegrationsSkeleton showPlaceholder={true} />
      </Sentry.ErrorBoundary>
    );
  }

  return (
    <Sentry.ErrorBoundary
      fallback={({ error, resetError }) => (
        <div className="p-4 text-center">
          <h2 className="text-xl font-semibold text-red-600 mb-2">
            Something went wrong loading integrations
          </h2>
          <p className="text-gray-600 dark:text-gray-400 mb-4">
            {error instanceof Error ? error.message : 'An unexpected error occurred'}
          </p>
          <button
            onClick={resetError}
            className="px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700"
          >
            Try again
          </button>
        </div>
      )}
      beforeCapture={(scope) => {
        scope.setTag('component', 'Integrations');
        scope.setTag('page', 'integrations');
        scope.setContext('integrationState', {
          quickBooksConnected: status?.connected || false,
          autoSyncEnabled,
          isAnyOperationInProgress,
        });
      }}
    >
      <div className="dark-panel -m-4 h-[calc(100%+2rem)] overflow-hidden flex flex-col" role="main">
        <div className="p-6 pb-20 flex-1 flex flex-col min-h-0 overflow-hidden">
          {/* Integration Cards Container */}
          <div
            className="flex-1 flex flex-col min-h-0 space-y-6"
            role="region"
            aria-label="Integration status and actions"
          >
            {/* Stripe Connect Card - Top Priority */}
            <div className="flex-shrink-0">
              <StripeConnectCard />
            </div>

            {/* QuickBooks Card */}
            <div className="flex-shrink-0">
              <QuickBooksCard
                status={status}
                operationState={operationState}
                onConnect={guardedConnect}
                onDisconnect={handleDisconnect}
                disabled={false}
              />
            </div>

            {/* Placeholder Card - fills remaining space */}
            <div className="flex-1 min-h-0">
              <PlaceholderCard className="h-full flex flex-col justify-center" />
            </div>
          </div>
        </div>

        {/* Confirmation Modal for Disconnect */}
        <ConfirmationModal
          isOpen={showConfirmDisconnect}
          onClose={handleCancelDisconnect}
          onConfirm={handleConfirmDisconnect}
          title="Disconnect from QuickBooks"
          message="Are you sure you want to disconnect from QuickBooks? This will stop syncing your accounting data and you'll need to reconnect to resume synchronization."
          confirmText="Disconnect"
          cancelText="Cancel"
          variant="danger"
          isLoading={isDisconnecting}
        />
      </div>
    </Sentry.ErrorBoundary>
  );
});

Integrations.displayName = 'Integrations';

export default Integrations;
