import React, { memo, useMemo, useState, useCallback } from 'react';
import { QuickBooksCardProps } from '../../types/integrations';
import { useQuickBooksSettings } from '../../hooks/useQuickBooksQueries';
import QuickBooksSyncWizard from './QuickBooksSyncWizard';
import QuickBooksSettings from './QuickBooksSettings';

/**
 * QuickBooks integration card component
 *
 * Displays connection status and provides actions for:
 * - Connecting/disconnecting from QuickBooks
 * - Syncing data (manual or auto-sync indicator)
 * - Accessing settings
 */
const QuickBooksCard: React.FC<QuickBooksCardProps> = memo(({
  status,
  operationState,
  onConnect,
  onDisconnect,
  disabled = false
}) => {
  const isConnected = status?.connected ?? false;
  const isLoading = operationState.type === 'loading';
  const isSyncing = operationState.type === 'syncing';
  const isAnyOperationInProgress = isLoading || isSyncing;

  // Modal state
  const [showSyncPreview, setShowSyncPreview] = useState(false);
  const [showSettings, setShowSettings] = useState(false);

  // Fetch settings using TanStack Query (only when connected)
  const { data: settingsData, refetch: refetchSettings } = useQuickBooksSettings(isConnected);
  const autoSyncEnabled = settingsData?.settings?.auto_sync_enabled ?? true;

  // Handlers
  const handleSettingsClose = useCallback(() => {
    setShowSettings(false);
    // Refetch settings in case they changed
    refetchSettings();
  }, [refetchSettings]);

  const handleAutoSyncChange = useCallback((_enabled: boolean) => {
    // Settings are automatically refetched via TanStack Query invalidation
    // This callback is kept for backward compatibility with QuickBooksSettings
  }, []);

  // Generate unique IDs for accessibility
  const connectionStatusId = useMemo(
    () => `quickbooks-status-${Math.random().toString(36).substring(2, 9)}`,
    []
  );
  const connectionDateId = useMemo(
    () => `quickbooks-date-${Math.random().toString(36).substring(2, 9)}`,
    []
  );

  // Determine loading state text based on operation
  const getLoadingText = (): string => {
    if (operationState.type === 'loading') {
      return operationState.operation ? `${operationState.operation}...` : 'Loading...';
    }
    if (operationState.type === 'syncing') {
      switch (operationState.operation) {
        case 'payments': return 'Syncing Payments...';
        case 'invoices': return 'Syncing Invoices...';
        case 'expenses': return 'Syncing Expenses...';
        case 'all': return 'Syncing All Data...';
        case 'initial': return 'Initial Sync...';
        default: return 'Syncing...';
      }
    }
    return '';
  };

  // Disabled/Coming Soon state
  if (disabled) {
    return (
      <article
        className="dark-panel dark-shadow rounded-lg dark-divider border overflow-hidden"
        aria-labelledby="quickbooks-heading"
        aria-describedby="quickbooks-description"
      >
        <div className="p-6 flex items-center justify-between">
          <div className="flex items-center space-x-6">
            <img
              src="/Intuit_QuickBooks_logo.svg"
              alt="Intuit QuickBooks integration logo"
              loading="lazy"
              className="h-8 dark:invert dark:hue-rotate-180"
              role="img"
            />
            <div>
              <h3 id="quickbooks-heading" className="text-lg font-semibold text-gray-800 dark:text-gray-100">
                Intuit QuickBooks
              </h3>
              <p id="quickbooks-description" className="text-xs text-gray-500 mt-0.5">
                Sync Tenants, Invoices, Payments, Expenses with QuickBooks
              </p>
            </div>
          </div>

          <div className="flex items-center space-x-6">
            <div className="min-w-[120px] flex justify-center">
              <span className="inline-flex items-center px-3 py-1 rounded-full text-sm font-medium bg-yellow-100 dark:bg-yellow-900/30 text-yellow-800 dark:text-yellow-200">
                <i className="fas fa-clock mr-2" aria-hidden="true" />
                Coming Soon
              </span>
            </div>
            <div>
              <button
                type="button"
                disabled
                className="inline-flex items-center justify-center px-4 py-2 dark-divider border text-sm font-medium rounded-md text-gray-500 dark:text-gray-400 dark-input cursor-not-allowed"
              >
                <i className="fas fa-tools mr-2" aria-hidden="true" />
                In Development
              </button>
            </div>
          </div>
        </div>
      </article>
    );
  }

  return (
    <article
      className="dark-panel dark-shadow rounded-lg dark-divider border overflow-hidden"
      aria-labelledby="quickbooks-heading"
      aria-describedby={`quickbooks-description ${connectionStatusId} ${isConnected && status?.connected_at ? connectionDateId : ''}`}
    >
      <div className="p-6 flex items-center justify-between">
        {/* Left: Logo and description */}
        <div className="flex items-center space-x-6">
          <img
            src="/Intuit_QuickBooks_logo.svg"
            alt="Intuit QuickBooks integration logo"
            loading="lazy"
            className="h-8"
            role="img"
          />
          <div>
            <h3 id="quickbooks-heading" className="text-lg font-semibold text-gray-800 dark:text-gray-100">
              Intuit QuickBooks
            </h3>
            <p id="quickbooks-description" className="text-xs text-gray-500 mt-0.5">
              Sync Tenants, Invoices, Payments, Expenses with QuickBooks
            </p>
          </div>
        </div>

        {/* Right: Status and actions */}
        <div className="flex items-center space-x-6">
          {/* Connection Status Badge */}
          <div className="min-w-[120px]">
            {isConnected ? (
              <div className="flex flex-col items-center">
                <span
                  className="inline-flex items-center px-3 py-1 rounded-full text-sm font-medium bg-green-100 dark:bg-green-900/30 text-green-800 dark:text-green-200"
                  role="status"
                  aria-label="QuickBooks integration status"
                  id={connectionStatusId}
                >
                  <i className="fas fa-check-circle mr-2" aria-hidden="true" />
                  Connected
                </span>
                {status?.connected_at && (
                  <p className="text-xs text-gray-500 dark:text-gray-400 mt-1 text-center" id={connectionDateId}>
                    <span className="sr-only">Connected on: </span>
                    On: {new Date(status.connected_at).toLocaleDateString()}
                  </p>
                )}
              </div>
            ) : (
              <div className="flex justify-center">
                <span
                  className="inline-flex items-center px-3 py-1 rounded-full text-sm font-medium bg-gray-100 dark:bg-gray-900/30 text-gray-800 dark:text-gray-200"
                  role="status"
                  aria-label="QuickBooks integration status"
                  id={connectionStatusId}
                >
                  <i className="fas fa-times-circle mr-2" aria-hidden="true" />
                  Not Connected
                </span>
              </div>
            )}
          </div>

          {/* Action Buttons */}
          <div>
            {isConnected ? (
              <div className="flex items-center space-x-3">
                {autoSyncEnabled ? (
                  // Auto-Sync On indicator
                  <div className="inline-flex items-center justify-center px-4 py-2 border-2 border-emerald-500 dark:border-emerald-400 text-sm font-medium rounded-md text-emerald-600 dark:text-emerald-400 bg-transparent">
                    <span className="relative flex h-2 w-2 mr-2">
                      <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75" />
                      <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500" />
                    </span>
                    Auto-Sync On
                  </div>
                ) : (
                  // Manual Sync button
                  <button
                    type="button"
                    onClick={() => setShowSyncPreview(true)}
                    disabled={isAnyOperationInProgress}
                    className="inline-flex items-center justify-center px-4 py-2 border border-transparent text-sm font-medium rounded-md text-white bg-blue-600 hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500 dark:focus:ring-offset-gray-900 disabled:opacity-50 transition-colors"
                  >
                    {isSyncing ? (
                      <>
                        <i className="fas fa-spinner fa-spin mr-2" aria-hidden="true" />
                        Syncing...
                      </>
                    ) : (
                      <>
                        <i className="fas fa-sync mr-2" aria-hidden="true" />
                        Sync
                      </>
                    )}
                  </button>
                )}

                {/* Settings button */}
                <button
                  type="button"
                  onClick={() => setShowSettings(true)}
                  disabled={isAnyOperationInProgress}
                  className="p-2 text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-full focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500 dark:focus:ring-offset-gray-900 disabled:opacity-50 transition-colors"
                  aria-label="Configure QuickBooks settings"
                >
                  <i className="fas fa-cog text-lg" aria-hidden="true" />
                </button>
              </div>
            ) : (
              // Connect button
              <button
                type="button"
                onClick={onConnect}
                disabled={isAnyOperationInProgress}
                className="inline-flex items-center justify-center px-4 py-2 border border-transparent text-sm font-medium rounded-md shadow-sm text-white bg-blue-600 hover:bg-blue-700 focus:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500 dark:focus:ring-offset-gray-900 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                aria-describedby={connectionStatusId}
                aria-label={isLoading ? 'Connecting to QuickBooks' : 'Connect to QuickBooks integration'}
              >
                {isLoading ? (
                  <>
                    <i className="fas fa-spinner fa-spin mr-2" aria-hidden="true" />
                    <span>{getLoadingText()}</span>
                    <span className="sr-only">Please wait</span>
                  </>
                ) : (
                  <>
                    <i className="fas fa-plug mr-2" aria-hidden="true" />
                    Connect
                  </>
                )}
              </button>
            )}
          </div>
        </div>
      </div>

      {/* Progressive Sync Wizard */}
      <QuickBooksSyncWizard
        isOpen={showSyncPreview}
        onClose={() => setShowSyncPreview(false)}
        onSyncComplete={() => {
          setShowSyncPreview(false);
        }}
      />

      {/* Settings Modal */}
      <QuickBooksSettings
        isOpen={showSettings}
        onClose={handleSettingsClose}
        onDisconnect={onDisconnect}
        onAutoSyncChange={handleAutoSyncChange}
      />
    </article>
  );
});

QuickBooksCard.displayName = 'QuickBooksCard';

export default QuickBooksCard;
