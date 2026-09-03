/**
 * InvoicePaymentsBanner Component
 * 
 * Prompts users to set up Stripe Connect for invoice payment collection.
 * Similar to OnlinePaymentsBanner but specifically for invoice payments.
 */

import React, { useState, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { toast } from 'react-toastify';
import { 
  useConnectAccountState,
  useConnectStatus,
  useStartOnboarding, 
  useRefreshOnboardingLink,
  useStripeDashboardLink,
} from '../../hooks/useConnectStatus';
import { useSubscriptionGuard } from '../../hooks/useSubscriptionGuard';

// =============================================================================
// Banner States
// =============================================================================

interface BannerProps {
  onDismiss?: () => void;
}

/**
 * Not Started State - Encourage landlord to set up payment collection for invoices
 */
const NotStartedBanner: React.FC<BannerProps> = ({ onDismiss }) => {
  const navigate = useNavigate();
  const startOnboarding = useStartOnboarding();
  const guardAction = useSubscriptionGuard({ featureName: 'invoice payment collection' });
  const [isRedirecting, setIsRedirecting] = useState(false);

  const handleSetup = guardAction(useCallback(async () => {
    try {
      setIsRedirecting(true);
      const result = await startOnboarding.mutateAsync();
      // Redirect to Stripe hosted onboarding
      window.location.href = result.onboarding_url;
    } catch (error) {
      setIsRedirecting(false);
      toast.error('Failed to start setup. Please try again.');
      console.error('Onboarding error:', error);
    }
  }, [startOnboarding]));

  const handleGoToIntegrations = useCallback(() => {
    navigate('/integrations');
  }, [navigate]);

  return (
    <div className="bg-gradient-to-r from-blue-50 to-indigo-50 dark:from-blue-900/20 dark:to-indigo-900/20 border border-blue-200 dark:border-blue-700/50 rounded-lg p-4 mb-4">
      <div className="flex items-start justify-between">
        <div className="flex items-start space-x-3">
          <div className="flex-shrink-0">
            <div className="w-10 h-10 rounded-full bg-blue-100 dark:bg-blue-800/50 flex items-center justify-center">
              <i className="fas fa-file-invoice-dollar text-blue-600 dark:text-blue-400 text-lg" />
            </div>
          </div>
          <div className="flex-1">
            <h3 className="text-sm font-semibold text-blue-900 dark:text-blue-100">
              Accept Invoice Payments Online
            </h3>
            <p className="mt-1 text-sm text-blue-700 dark:text-blue-300">
              Set up Stripe Connect to collect payments on your invoices with branded payment pages.
            </p>
            <div className="mt-2 flex items-center space-x-4 text-xs text-blue-600 dark:text-blue-400">
              <span className="flex items-center">
                <i className="fas fa-check mr-1" />
                Optional payment collection
              </span>
              <span className="flex items-center">
                <i className="fas fa-check mr-1" />
                Branded invoice emails
              </span>
              <span className="flex items-center">
                <i className="fas fa-check mr-1" />
                Automatic reminders
              </span>
            </div>
          </div>
        </div>
        <div className="flex items-center space-x-2">
          <button
            onClick={handleGoToIntegrations}
            className="inline-flex items-center px-3 py-2 border border-blue-300 dark:border-blue-600 text-sm font-medium rounded-md text-blue-700 dark:text-blue-300 bg-white dark:bg-gray-800 hover:bg-blue-50 dark:hover:bg-blue-900/30 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500 transition-colors"
          >
            View Integration
          </button>
          <button
            onClick={handleSetup}
            disabled={startOnboarding.isPending || isRedirecting}
            className="inline-flex items-center px-4 py-2 border border-transparent text-sm font-medium rounded-md text-white bg-blue-600 hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            {startOnboarding.isPending || isRedirecting ? (
              <>
                <i className="fas fa-spinner fa-spin mr-2" />
                Setting up...
              </>
            ) : (
              <>
                Set Up Now
                <i className="fas fa-arrow-right ml-2" />
              </>
            )}
          </button>
          {onDismiss && (
            <button
              onClick={onDismiss}
              className="text-blue-500 hover:text-blue-700 dark:text-blue-400 dark:hover:text-blue-300 p-2"
              title="Dismiss for now"
            >
              <i className="fas fa-times" />
            </button>
          )}
        </div>
      </div>
    </div>
  );
};

/**
 * Incomplete State - Landlord started but didn't finish onboarding
 */
const IncompleteBanner: React.FC = () => {
  const refreshLink = useRefreshOnboardingLink();
  const guardAction = useSubscriptionGuard({ featureName: 'invoice payment collection' });
  const [isRedirecting, setIsRedirecting] = useState(false);

  const handleContinue = guardAction(useCallback(async () => {
    try {
      setIsRedirecting(true);
      const result = await refreshLink.mutateAsync();
      window.location.href = result.onboarding_url;
    } catch (error) {
      setIsRedirecting(false);
      toast.error('Failed to get setup link. Please try again.');
      console.error('Refresh link error:', error);
    }
  }, [refreshLink]));

  return (
    <div className="bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-700/50 rounded-lg p-4 mb-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center space-x-3">
          <div className="flex-shrink-0">
            <div className="w-10 h-10 rounded-full bg-amber-100 dark:bg-amber-800/50 flex items-center justify-center">
              <i className="fas fa-exclamation-circle text-amber-600 dark:text-amber-400 text-lg" />
            </div>
          </div>
          <div>
            <h3 className="text-sm font-semibold text-amber-900 dark:text-amber-100">
              Complete Payment Setup
            </h3>
            <p className="mt-1 text-sm text-amber-700 dark:text-amber-300">
              Finish verifying your identity to enable invoice payment collection.
            </p>
          </div>
        </div>
        <button
          onClick={handleContinue}
          disabled={refreshLink.isPending || isRedirecting}
          className="inline-flex items-center px-4 py-2 border border-transparent text-sm font-medium rounded-md text-white bg-amber-600 hover:bg-amber-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-amber-500 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
        >
          {refreshLink.isPending || isRedirecting ? (
            <>
              <i className="fas fa-spinner fa-spin mr-2" />
              Loading...
            </>
          ) : (
            <>
              Continue Setup
              <i className="fas fa-arrow-right ml-2" />
            </>
          )}
        </button>
      </div>
    </div>
  );
};

/**
 * Active State - Minimal, non-intrusive status indicator
 */
const ActiveBanner: React.FC = () => {
  const dashboardLink = useStripeDashboardLink();

  const handleOpenDashboard = useCallback(async () => {
    try {
      const result = await dashboardLink.mutateAsync();
      window.open(result.dashboard_url, '_blank', 'noopener,noreferrer');
    } catch (error) {
      toast.error('Failed to open dashboard. Please try again.');
      console.error('Dashboard link error:', error);
    }
  }, [dashboardLink]);

  return (
    <div className="bg-gray-50 dark:bg-gray-800/50 border border-gray-200 dark:border-gray-700 rounded-lg p-4 mb-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center space-x-3">
          <div className="flex items-center space-x-2">
            <span className="relative flex h-2 w-2">
              <span className="animate-ping absolute inline-flex h-2 w-2 rounded-full bg-emerald-400 opacity-75" />
              <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500" />
            </span>
            <span className="text-sm font-medium text-gray-700 dark:text-gray-300">
              Online Payments Active
            </span>
          </div>
        </div>
        <button
          onClick={handleOpenDashboard}
          disabled={dashboardLink.isPending}
          className="inline-flex items-center text-sm text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-200 transition-colors"
        >
          {dashboardLink.isPending ? (
            <i className="fas fa-spinner fa-spin" />
          ) : (
            <>
              Manage Payouts
              <i className="fas fa-external-link-alt ml-1 text-xs" />
            </>
          )}
        </button>
      </div>
    </div>
  );
};

// =============================================================================
// Main Component
// =============================================================================

interface InvoicePaymentsBannerProps {
  /** Whether the banner can be dismissed (only for not_started state) */
  dismissible?: boolean;
}

const InvoicePaymentsBanner: React.FC<InvoicePaymentsBannerProps> = ({ 
  dismissible = true,
}) => {
  const { isLoading, error, onboardingStatus } = useConnectAccountState();
  const { data: connectData } = useConnectStatus();
  const [isDismissed, setIsDismissed] = useState(false);

  // Check session storage for dismissal (resets on new session)
  const sessionKey = 'brikli_invoice_payments_banner_dismissed';
  const wasDismissedThisSession = typeof window !== 'undefined' 
    ? sessionStorage.getItem(sessionKey) === 'true' 
    : false;

  const handleDismiss = useCallback(() => {
    setIsDismissed(true);
    if (typeof window !== 'undefined') {
      sessionStorage.setItem(sessionKey, 'true');
    }
  }, []);

  // Don't show while loading
  if (isLoading) {
    return null;
  }

  // Don't show on error (fail silently)
  if (error) {
    return null;
  }

  // Show active banner when fully connected
  if (onboardingStatus === 'active' && !connectData?.needs_action) {
    return <ActiveBanner />;
  }

  // Handle dismissed state (only for not_started)
  if ((isDismissed || wasDismissedThisSession) && onboardingStatus === 'not_started') {
    return null;
  }

  // Only show banner for not_started and incomplete states
  // For active users with issues, they'll see warnings elsewhere
  switch (onboardingStatus) {
    case 'not_started':
      return <NotStartedBanner onDismiss={dismissible ? handleDismiss : undefined} />;
    case 'incomplete':
      return <IncompleteBanner />;
    default:
      return null;
  }
};

export default InvoicePaymentsBanner;
