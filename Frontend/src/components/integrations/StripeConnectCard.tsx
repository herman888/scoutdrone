import React, { memo, useMemo, useState, useCallback } from 'react';
import { toast } from 'react-toastify';
import * as DropdownMenu from '@radix-ui/react-dropdown-menu';
import { useQueryClient } from '@tanstack/react-query';
import { 
  useConnectAccountState,
  useConnectStatus,
  useStartOnboarding, 
  useRefreshOnboardingLink,
  useStripeDashboardLink,
} from '../../hooks/useConnectStatus';
import { useSubscriptionGuard } from '../../hooks/useSubscriptionGuard';
import { apiRequest } from '../../utils/api/core';

/**
 * Stripe Connect integration card component
 *
 * Displays connection status and provides actions for:
 * - Setting up Stripe Connect for payment collection
 * - Managing payout settings
 * - Viewing transaction dashboard
 */
const StripeConnectCard: React.FC = memo(() => {
  const queryClient = useQueryClient();
  const { isLoading, error, onboardingStatus, isFullyOnboarded } = useConnectAccountState();
  const { data: connectData, refetch: refetchConnectStatus } = useConnectStatus();
  const startOnboarding = useStartOnboarding();
  const refreshLink = useRefreshOnboardingLink();
  const dashboardLink = useStripeDashboardLink();
  const guardAction = useSubscriptionGuard({ featureName: 'payment collection' });
  
  const [isRedirecting, setIsRedirecting] = useState(false);
  const [isDisconnecting, setIsDisconnecting] = useState(false);

  // Handlers
  const handleStartOnboarding = guardAction(useCallback(async () => {
    try {
      setIsRedirecting(true);
      const result = await startOnboarding.mutateAsync();
      window.location.href = result.onboarding_url;
    } catch (err) {
      setIsRedirecting(false);
      toast.error('Failed to start setup. Please try again.');
      console.error('Onboarding error:', err);
    }
  }, [startOnboarding]));

  const handleContinueSetup = guardAction(useCallback(async () => {
    try {
      setIsRedirecting(true);
      const result = await refreshLink.mutateAsync();
      window.location.href = result.onboarding_url;
    } catch (err) {
      setIsRedirecting(false);
      toast.error('Failed to get setup link. Please try again.');
      console.error('Refresh link error:', err);
    }
  }, [refreshLink]));

  const handleOpenDashboard = useCallback(async () => {
    try {
      const result = await dashboardLink.mutateAsync();
      window.open(result.dashboard_url, '_blank', 'noopener,noreferrer');
    } catch (err) {
      toast.error('Failed to open dashboard. Please try again.');
      console.error('Dashboard link error:', err);
    }
  }, [dashboardLink]);

  const handleDisconnect = useCallback(async () => {
    console.log('handleDisconnect called');
    
    if (!window.confirm(
      'Are you sure you want to disconnect from Stripe Connect?\n\n' +
      'This will:\n' +
      '• Disable payment collection on invoices and rent\n' +
      '• Stop all future payments\n' +
      '• Preserve your historical transaction data\n\n' +
      'You can reconnect later if needed.'
    )) {
      return;
    }

    try {
      setIsDisconnecting(true);
      
      await apiRequest('/rent-payments/connect/disconnect', {
        method: 'DELETE',
      });

      toast.success('Successfully disconnected from Stripe Connect');
      
      // Refresh the Connect status without full page reload
      await queryClient.invalidateQueries({ 
        queryKey: ['connect', 'status'],
        refetchType: 'active'
      });
      
      // Manually trigger refetch to ensure it happens
      await refetchConnectStatus();
      
    } catch (err: any) {
      console.error('Disconnect error:', err);
      
      // More detailed error messaging
      let errorMessage = 'Failed to disconnect. Please try again.';
      
      if (err?.response?.status === 404) {
        errorMessage = 'No Stripe Connect account found. It may already be disconnected.';
        // Still refresh the UI state
        await queryClient.invalidateQueries({ queryKey: ['connect', 'status'] });
      } else if (err?.message) {
        errorMessage = err.message;
      }
      
      toast.error(errorMessage);
    } finally {
      setIsDisconnecting(false);
    }
  }, [queryClient, refetchConnectStatus]);

  // Generate unique IDs for accessibility
  const statusId = useMemo(
    () => `stripe-status-${Math.random().toString(36).substring(2, 9)}`,
    []
  );

  // Determine connection state
  const isConnected = onboardingStatus === 'active' && isFullyOnboarded;
  const isPending = onboardingStatus === 'pending_verification';
  const isIncomplete = onboardingStatus === 'incomplete';
  const needsAction = connectData?.needs_action ?? false;
  const isPastDue = (connectData?.requirements_past_due?.length ?? 0) > 0;

  // Connection status badge
  const getStatusBadge = () => {
    if (isLoading) {
      return (
        <span className="inline-flex items-center px-3 py-1 rounded-full text-sm font-medium bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-300">
          <i className="fas fa-spinner fa-spin mr-2" aria-hidden="true" />
          Loading...
        </span>
      );
    }

    if (error) {
      return (
        <span className="inline-flex items-center px-3 py-1 rounded-full text-sm font-medium bg-red-100 dark:bg-red-900/30 text-red-800 dark:text-red-200">
          <i className="fas fa-exclamation-circle mr-2" aria-hidden="true" />
          Error
        </span>
      );
    }

    if (needsAction && isPastDue) {
      return (
        <span className="inline-flex items-center px-3 py-1 rounded-full text-sm font-medium bg-red-100 dark:bg-red-900/30 text-red-800 dark:text-red-200">
          <i className="fas fa-exclamation-triangle mr-2" aria-hidden="true" />
          Action Required
        </span>
      );
    }

    if (needsAction) {
      return (
        <span className="inline-flex items-center px-3 py-1 rounded-full text-sm font-medium bg-amber-100 dark:bg-amber-900/30 text-amber-800 dark:text-amber-200">
          <i className="fas fa-info-circle mr-2" aria-hidden="true" />
          Action Needed
        </span>
      );
    }

    if (isConnected) {
      return (
        <span className="inline-flex items-center px-3 py-1 rounded-full text-sm font-medium bg-emerald-100 dark:bg-emerald-900/30 text-emerald-800 dark:text-emerald-200">
          <span className="relative flex h-2 w-2 mr-2">
            <span className="animate-ping absolute inline-flex h-2 w-2 rounded-full bg-emerald-400 opacity-75" />
            <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500" />
          </span>
          Connected
        </span>
      );
    }

    if (isPending) {
      return (
        <span className="inline-flex items-center px-3 py-1 rounded-full text-sm font-medium bg-blue-100 dark:bg-blue-900/30 text-blue-800 dark:text-blue-200">
          <i className="fas fa-clock mr-2" aria-hidden="true" />
          Pending
        </span>
      );
    }

    if (isIncomplete) {
      // Show "Setting Up" for initial onboarding, "Incomplete" for abandoned setups
      const isActiveSetup = needsAction && !isConnected;
      return (
        <span className={`inline-flex items-center px-3 py-1 rounded-full text-sm font-medium ${
          isActiveSetup 
            ? 'bg-blue-100 dark:bg-blue-900/30 text-blue-800 dark:text-blue-200'
            : 'bg-amber-100 dark:bg-amber-900/30 text-amber-800 dark:text-amber-200'
        }`}>
          <i className={`fas ${isActiveSetup ? 'fa-circle-notch fa-spin' : 'fa-pause-circle'} mr-2`} aria-hidden="true" />
          {isActiveSetup ? 'Setting Up' : 'Incomplete'}
        </span>
      );
    }

    return (
      <span className="inline-flex items-center px-3 py-1 rounded-full text-sm font-medium bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-300">
        <i className="fas fa-circle mr-2" aria-hidden="true" />
        Not Connected
      </span>
    );
  };

  // Action button
  const getActionButton = () => {
    const isButtonDisabled = isLoading || isRedirecting || startOnboarding.isPending || refreshLink.isPending;

    if (needsAction) {
      // Differentiate between initial setup and additional actions
      const isInitialSetup = !isConnected && onboardingStatus === 'incomplete';
      const buttonColor = isPastDue 
        ? 'bg-red-600 hover:bg-red-700 focus:ring-red-500'
        : isInitialSetup
          ? 'bg-blue-600 hover:bg-blue-700 focus:ring-blue-500'
          : 'bg-amber-600 hover:bg-amber-700 focus:ring-amber-500';
      const buttonText = isPastDue 
        ? 'Complete Verification' 
        : isInitialSetup
          ? 'Continue Setup'
          : 'Review Information';

      return (
        <button
          type="button"
          onClick={handleContinueSetup}
          disabled={isButtonDisabled}
          className={`inline-flex items-center justify-center px-4 py-2 border border-transparent text-sm font-medium rounded-md text-white ${buttonColor} focus:outline-none focus:ring-2 focus:ring-offset-2 disabled:opacity-50 disabled:cursor-not-allowed transition-colors`}
        >
          {isButtonDisabled ? (
            <>
              <i className="fas fa-spinner fa-spin mr-2" aria-hidden="true" />
              Loading...
            </>
          ) : (
            <>
              <i className={`fas ${isInitialSetup ? 'fa-arrow-right' : 'fa-info-circle'} mr-2`} aria-hidden="true" />
              {buttonText}
            </>
          )}
        </button>
      );
    }

    if (isConnected) {
      return (
        <button
          type="button"
          onClick={handleOpenDashboard}
          disabled={dashboardLink.isPending}
          className="inline-flex items-center justify-center px-4 py-2 dark-divider border text-sm font-medium rounded-md text-gray-700 dark:text-gray-200 dark-input hover:bg-gray-50 dark:hover:bg-gray-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
        >
          {dashboardLink.isPending ? (
            <>
              <i className="fas fa-spinner fa-spin mr-2" aria-hidden="true" />
              Loading...
            </>
          ) : (
            <>
              <i className="fas fa-chart-line mr-2" aria-hidden="true" />
              View Dashboard
            </>
          )}
        </button>
      );
    }

    if (isIncomplete || isPending) {
      return (
        <button
          type="button"
          onClick={handleContinueSetup}
          disabled={isButtonDisabled}
          className="inline-flex items-center justify-center px-4 py-2 border border-transparent text-sm font-medium rounded-md text-white bg-amber-600 hover:bg-amber-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-amber-500 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
        >
          {isButtonDisabled ? (
            <>
              <i className="fas fa-spinner fa-spin mr-2" aria-hidden="true" />
              Loading...
            </>
          ) : (
            <>
              <i className="fas fa-arrow-right mr-2" aria-hidden="true" />
              Continue Setup
            </>
          )}
        </button>
      );
    }

    return (
      <button
        type="button"
        onClick={handleStartOnboarding}
        disabled={isButtonDisabled}
        className="inline-flex items-center justify-center px-4 py-2 border border-transparent text-sm font-medium rounded-md text-white bg-blue-600 hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
      >
        {isButtonDisabled ? (
          <>
            <i className="fas fa-spinner fa-spin mr-2" aria-hidden="true" />
            Setting up...
          </>
        ) : (
          <>
            <i className="fas fa-plug mr-2" aria-hidden="true" />
            Connect
          </>
        )}
      </button>
    );
  };

  return (
    <article
      className="dark-panel dark-shadow rounded-lg dark-divider border overflow-hidden"
      aria-labelledby="stripe-heading"
      aria-describedby={`stripe-description ${statusId}`}
    >
      <div className="p-6 flex items-center justify-between">
        {/* Left: Logo and description */}
        <div className="flex items-center space-x-6">
          <svg viewBox="0 0 60 25" xmlns="http://www.w3.org/2000/svg" className="h-8" role="img" aria-label="Stripe logo">
            <path fill="#635BFF" d="M59.64 14.28h-8.06c.19 1.93 1.6 2.55 3.2 2.55 1.64 0 2.96-.37 4.05-.95v3.32a8.33 8.33 0 0 1-4.56 1.1c-4.01 0-6.83-2.5-6.83-7.48 0-4.19 2.39-7.52 6.3-7.52 3.92 0 5.96 3.28 5.96 7.5 0 .4-.04 1.26-.06 1.48zm-5.92-5.62c-1.03 0-2.17.73-2.17 2.58h4.25c0-1.85-1.07-2.58-2.08-2.58zM40.95 20.3c-1.44 0-2.32-.6-2.9-1.04l-.02 4.63-4.12.87V5.57h3.76l.08 1.02a4.7 4.7 0 0 1 3.23-1.29c2.9 0 5.62 2.6 5.62 7.4 0 5.23-2.7 7.6-5.65 7.6zM40 8.95c-.95 0-1.54.34-1.97.81l.02 6.12c.4.44.98.78 1.95.78 1.52 0 2.54-1.65 2.54-3.87 0-2.15-1.04-3.84-2.54-3.84zM28.24 5.57h4.13v14.44h-4.13V5.57zm0-4.7L32.37 0v3.36l-4.13.88V.88zm-4.32 9.35v9.79H19.8V5.57h3.7l.12 1.22c1-1.77 3.07-1.41 3.62-1.22v3.79c-.52-.17-2.29-.43-3.32.86zm-8.55 4.72c0 2.43 2.6 1.68 3.12 1.46v3.36c-.55.3-1.54.54-2.89.54a4.15 4.15 0 0 1-4.27-4.24l.01-13.17 4.02-.86v3.54h3.14V9.1h-3.13v5.85zm-4.91.7c0 2.97-2.31 4.66-5.73 4.66a11.2 11.2 0 0 1-4.46-.93v-3.93c1.38.75 3.1 1.31 4.46 1.31.92 0 1.53-.24 1.53-1C6.26 13.77 0 14.51 0 9.95 0 7.04 2.28 5.3 5.62 5.3c1.36 0 2.72.2 4.09.75v3.88a9.23 9.23 0 0 0-4.09-1.12c-.75 0-1.36.25-1.36.85 0 1.9 6.25 1.17 6.25 5.71z"/>
          </svg>
          <div>
            <h3 id="stripe-heading" className="text-lg font-semibold text-gray-800 dark:text-gray-100">
              Stripe Connect
            </h3>
            <p id="stripe-description" className="text-xs text-gray-500 mt-0.5">
              Accept payments on invoices and rent with direct deposits to your bank
            </p>
            {isConnected && (
              <p className="text-xs text-emerald-600 dark:text-emerald-400 mt-1 flex items-center">
                <i className="fas fa-check-circle mr-1" aria-hidden="true" />
                Online payments enabled
              </p>
            )}
            {needsAction && !isConnected && onboardingStatus === 'incomplete' && (
              <p className="text-xs mt-1 flex items-center text-blue-600 dark:text-blue-400">
                <i className="fas fa-info-circle mr-1" aria-hidden="true" />
                Complete setup in 2-3 minutes to start accepting payments
              </p>
            )}
            {needsAction && (isConnected || onboardingStatus !== 'incomplete') && (
              <p className={`text-xs mt-1 flex items-center ${isPastDue ? 'text-red-600 dark:text-red-400' : 'text-amber-600 dark:text-amber-400'}`}>
                <i className="fas fa-exclamation-circle mr-1" aria-hidden="true" />
                {isPastDue ? 'Additional documents required' : 'Additional information needed'}
              </p>
            )}
          </div>
        </div>

        {/* Right: Status badge and action button */}
        <div className="flex items-center space-x-6">
          <div id={statusId} className="min-w-[120px] flex justify-center">
            {getStatusBadge()}
          </div>
          <div className="flex items-center space-x-3">
            {getActionButton()}
            
            {/* Settings button - always visible when connected or needs action */}
            {(isConnected || needsAction || isIncomplete) && (
              <DropdownMenu.Root>
                <DropdownMenu.Trigger asChild>
                  <button
                    type="button"
                    className="p-2 text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-full focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500 transition-colors"
                    aria-label="Stripe Connect settings"
                  >
                    <i className="fas fa-cog text-lg" aria-hidden="true" />
                  </button>
                </DropdownMenu.Trigger>

                <DropdownMenu.Portal>
                  <DropdownMenu.Content
                    className="min-w-[14rem] bg-white dark:bg-gray-800 rounded-lg shadow-lg border border-gray-200 dark:border-gray-700 py-1 z-[9999]"
                    sideOffset={5}
                    align="end"
                    collisionPadding={10}
                  >
                    {isConnected && (
                      <DropdownMenu.Item
                        onSelect={handleOpenDashboard}
                        className="flex items-center px-4 py-2 text-sm text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700 cursor-pointer outline-none transition-colors"
                      >
                        <i className="fas fa-chart-line mr-3 w-4" aria-hidden="true" />
                        View Dashboard
                      </DropdownMenu.Item>
                    )}
                    
                    {(needsAction || isIncomplete) && (
                      <DropdownMenu.Item
                        onSelect={handleContinueSetup}
                        className="flex items-center px-4 py-2 text-sm text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700 cursor-pointer outline-none transition-colors"
                      >
                        <i className="fas fa-arrow-right mr-3 w-4" aria-hidden="true" />
                        Continue Setup
                      </DropdownMenu.Item>
                    )}
                    
                    <DropdownMenu.Separator className="h-px bg-gray-200 dark:bg-gray-700 my-1" />
                    
                    <DropdownMenu.Item
                      onSelect={handleDisconnect}
                      disabled={isDisconnecting}
                      className="flex items-center px-4 py-2 text-sm text-red-600 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-900/20 cursor-pointer outline-none transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                      {isDisconnecting ? (
                        <>
                          <i className="fas fa-spinner fa-spin mr-3 w-4" aria-hidden="true" />
                          Disconnecting...
                        </>
                      ) : (
                        <>
                          <i className="fas fa-unlink mr-3 w-4" aria-hidden="true" />
                          Disconnect
                        </>
                      )}
                    </DropdownMenu.Item>
                  </DropdownMenu.Content>
                </DropdownMenu.Portal>
              </DropdownMenu.Root>
            )}
          </div>
        </div>
      </div>
    </article>
  );
});

StripeConnectCard.displayName = 'StripeConnectCard';

export default StripeConnectCard;
