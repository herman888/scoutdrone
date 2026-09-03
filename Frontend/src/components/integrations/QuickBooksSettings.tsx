import React, { useState, useEffect, useCallback, useRef, memo } from 'react';
import * as Sentry from '@sentry/react';
import { toast } from 'react-toastify';
import {
  QuickBooksSettings as SettingsType,
  QuickBooksConnectionHealth,
  DEFAULT_QUICKBOOKS_SETTINGS,
} from '../../types/integrations';
import {
  getQuickBooksSettings,
  updateQuickBooksSettings,
} from '../../utils/api/quickbooks';

// Import existing account mapping component for Advanced section
import QuickBooksAccountMapping from './QuickBooksAccountMapping';

interface QuickBooksSettingsProps {
  isOpen: boolean;
  onClose: () => void;
  onSettingsUpdated?: () => void;
  onDisconnect?: () => void;
  onAutoSyncChange?: (enabled: boolean) => void;
}

/**
 * QuickBooks Settings Modal
 *
 * Allows users to configure:
 * - Auto-sync behavior (webhook-triggered sync)
 * - Entity sync scope (Customers, Invoices, Payments, Expenses)
 * - Notification preferences
 * - Advanced: Tax account mappings (collapsible)
 */
const QuickBooksSettings: React.FC<QuickBooksSettingsProps> = memo(({
  isOpen,
  onClose,
  onSettingsUpdated,
  onDisconnect,
  onAutoSyncChange,
}) => {
  // Settings state
  const [settings, setSettings] = useState<SettingsType>(DEFAULT_QUICKBOOKS_SETTINGS);
  const [connectionHealth, setConnectionHealth] = useState<QuickBooksConnectionHealth | null>(null);

  // UI state - start with loading false, only show spinner on initial fetch
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [showAccountMapping, setShowAccountMapping] = useState(false);
  const [hasChanges, setHasChanges] = useState(false);

  // Track if we've done the initial load to avoid flicker on subsequent opens
  const hasLoadedRef = useRef(false);
  const isLoadingRef = useRef(false);

  // Load settings when modal opens
  const loadSettings = useCallback(async (showSpinner = true) => {
    // Prevent concurrent loads
    if (isLoadingRef.current) return;
    isLoadingRef.current = true;

    if (showSpinner) setLoading(true);
    setError(null);

    try {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const response: any = await getQuickBooksSettings();

      if (response?.settings) {
        setSettings({
          auto_sync_enabled: response.settings.auto_sync_enabled ?? true,
          sync_customers: response.settings.sync_customers ?? true,
          sync_invoices: response.settings.sync_invoices ?? true,
          sync_payments: response.settings.sync_payments ?? true,
          sync_expenses: response.settings.sync_expenses ?? true,
          notify_on_sync: response.settings.notify_on_sync ?? true,
        });

        if (response.connection_health) {
          setConnectionHealth({
            last_sync_at: response.connection_health.last_sync_at ?? null,
            error_count: response.connection_health.error_count ?? 0,
            last_error: response.connection_health.last_error ?? null,
          });
        }
        setHasChanges(false);
        hasLoadedRef.current = true;
      }
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'Failed to load settings';
      setError(errorMessage);
      Sentry.captureException(err, {
        tags: { component: 'QuickBooksSettings', action: 'loadSettings' },
      });
    } finally {
      setLoading(false);
      isLoadingRef.current = false;
    }
  }, []);

  // Load on open - only show spinner on first load
  useEffect(() => {
    if (isOpen) {
      loadSettings(!hasLoadedRef.current);
    }
  }, [isOpen, loadSettings]);

  // Reset state when modal closes
  useEffect(() => {
    if (!isOpen) {
      setShowAdvanced(false);
      setError(null);
    }
  }, [isOpen]);

  // Handle checkbox changes with functional setState
  const handleSettingChange = (key: keyof SettingsType) => {
    setSettings(prev => ({
      ...prev,
      [key]: !prev[key],
    }));
    setHasChanges(true);
  };

  // Save settings
  const handleSave = async () => {
    setSaving(true);

    try {
      await updateQuickBooksSettings(settings);

      // Success - notify parent immediately with current settings value
      toast.success('Settings saved successfully');
      onAutoSyncChange?.(settings.auto_sync_enabled);
      onSettingsUpdated?.();
      setHasChanges(false);
      onClose();
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'Failed to save settings';
      toast.error(errorMessage);
      Sentry.captureException(err, {
        tags: { component: 'QuickBooksSettings', action: 'saveSettings' },
      });
    } finally {
      setSaving(false);
    }
  };

  // Format date for display
  const formatDate = (dateStr: string | null): string => {
    if (!dateStr) return 'Never';
    try {
      const date = new Date(dateStr);
      return date.toLocaleDateString('en-US', {
        month: 'short',
        day: 'numeric',
        year: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
      });
    } catch {
      return 'Unknown';
    }
  };

  if (!isOpen) return null;

  return (
    <>
      <div className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50">
        <div
          className="bg-white dark:bg-gray-800 rounded-lg shadow-xl w-full max-w-2xl mx-4 max-h-[90vh] overflow-hidden flex flex-col"
          role="dialog"
          aria-modal="true"
          aria-labelledby="settings-title"
        >
          {/* Header */}
          <div className="px-6 py-4 border-b border-gray-200 dark:border-gray-700">
            <div className="flex items-center justify-between">
              <h2
                id="settings-title"
                className="text-xl font-semibold text-gray-900 dark:text-gray-100"
              >
                QuickBooks Settings
              </h2>
              <button
                onClick={onClose}
                className="text-gray-400 hover:text-gray-500 dark:hover:text-gray-300"
                aria-label="Close"
              >
                <svg className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>
            <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
              Configure how QuickBooks syncs with your Brikli account.
            </p>
          </div>

          {/* Content */}
          <div className="flex-1 overflow-y-auto px-6 py-4">
            {loading ? (
              <div className="flex items-center justify-center py-12">
                <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600" />
                <span className="ml-2 text-gray-500 dark:text-gray-400">Loading settings...</span>
              </div>
            ) : error ? (
              <div className="text-center py-8">
                <p className="text-red-600 dark:text-red-400 mb-4">{error}</p>
                <button
                  onClick={() => loadSettings()}
                  className="px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700"
                >
                  Retry
                </button>
              </div>
            ) : (
              <div className="space-y-6">
                {/* Auto-Sync Section */}
                <div>
                  <h3 className="text-base font-medium text-gray-900 dark:text-gray-100 mb-3">
                    <i className="fas fa-sync-alt mr-2 text-blue-600" aria-hidden="true" />
                    Auto-Sync
                  </h3>

                  {/* Main auto-sync toggle */}
                  <div className="flex items-center justify-between p-4 bg-gray-50 dark:bg-gray-700/50 rounded-lg">
                    <div>
                      <label
                        htmlFor="auto_sync_enabled"
                        className="block text-sm font-medium text-gray-900 dark:text-gray-100 cursor-pointer"
                      >
                        Enable automatic sync
                      </label>
                      <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">
                        Automatically sync data when changes occur in QuickBooks (via webhooks)
                      </p>
                    </div>
                    <button
                      id="auto_sync_enabled"
                      type="button"
                      role="switch"
                      aria-checked={settings.auto_sync_enabled}
                      onClick={() => handleSettingChange('auto_sync_enabled')}
                      className={`relative inline-flex h-6 w-11 flex-shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 dark:focus:ring-offset-gray-800 ${
                        settings.auto_sync_enabled ? 'bg-blue-600' : 'bg-gray-300 dark:bg-gray-600'
                      }`}
                    >
                      <span
                        className={`pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow ring-0 transition duration-200 ease-in-out ${
                          settings.auto_sync_enabled ? 'translate-x-5' : 'translate-x-0'
                        }`}
                      />
                    </button>
                  </div>

                  {/* Entity type toggle buttons in a row */}
                  <div className={`mt-3 ${!settings.auto_sync_enabled ? 'opacity-50' : ''}`}>
                    <p className="text-xs text-gray-500 dark:text-gray-400 mb-2">
                      Select which data types to sync automatically:
                    </p>

                    <div className="grid grid-cols-4 gap-2">
                      {[
                        { key: 'sync_customers' as const, label: 'Customers', icon: 'fa-users' },
                        { key: 'sync_invoices' as const, label: 'Invoices', icon: 'fa-file-invoice' },
                        { key: 'sync_payments' as const, label: 'Payments', icon: 'fa-credit-card' },
                        { key: 'sync_expenses' as const, label: 'Expenses', icon: 'fa-receipt' },
                      ].map(({ key, label, icon }) => (
                        <button
                          key={key}
                          type="button"
                          onClick={() => settings.auto_sync_enabled && handleSettingChange(key)}
                          disabled={!settings.auto_sync_enabled}
                          className={`flex flex-col items-center justify-center gap-1 px-2 py-2.5 rounded-lg border text-xs font-medium transition-all ${
                            settings[key]
                              ? 'bg-blue-50 dark:bg-blue-900/30 border-blue-300 dark:border-blue-700 text-blue-700 dark:text-blue-300'
                              : 'bg-gray-50 dark:bg-gray-700/50 border-gray-200 dark:border-gray-600 text-gray-500 dark:text-gray-400'
                          } ${
                            settings.auto_sync_enabled
                              ? 'hover:border-blue-400 dark:hover:border-blue-600 cursor-pointer'
                              : 'cursor-not-allowed'
                          }`}
                        >
                          <i className={`fas ${icon} text-sm`} aria-hidden="true" />
                          <span>{label}</span>
                        </button>
                      ))}
                    </div>
                  </div>
                </div>

                {/* Notifications Section */}
                <div className="border-t border-gray-200 dark:border-gray-700 pt-6">
                  <h3 className="text-base font-medium text-gray-900 dark:text-gray-100 mb-3">
                    <i className="fas fa-bell mr-2 text-blue-600" aria-hidden="true" />
                    Notifications
                  </h3>

                  <div className="flex items-center justify-between p-4 bg-gray-50 dark:bg-gray-700/50 rounded-lg">
                    <div>
                      <label
                        htmlFor="notify_on_sync"
                        className="block text-sm font-medium text-gray-900 dark:text-gray-100 cursor-pointer"
                      >
                        Notify on sync events
                      </label>
                      <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">
                        Receive in-app notifications when data is synced from QuickBooks
                      </p>
                    </div>
                    <button
                      id="notify_on_sync"
                      type="button"
                      role="switch"
                      aria-checked={settings.notify_on_sync}
                      onClick={() => handleSettingChange('notify_on_sync')}
                      className={`relative inline-flex h-6 w-11 flex-shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 dark:focus:ring-offset-gray-800 ${
                        settings.notify_on_sync ? 'bg-blue-600' : 'bg-gray-300 dark:bg-gray-600'
                      }`}
                    >
                      <span
                        className={`pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow ring-0 transition duration-200 ease-in-out ${
                          settings.notify_on_sync ? 'translate-x-5' : 'translate-x-0'
                        }`}
                      />
                    </button>
                  </div>
                </div>

                {/* Connection Status Section */}
                {connectionHealth && (
                  <div className="border-t border-gray-200 dark:border-gray-700 pt-6">
                    <h3 className="text-base font-medium text-gray-900 dark:text-gray-100 mb-3">
                      <i className="fas fa-heartbeat mr-2 text-blue-600" aria-hidden="true" />
                      Connection Status
                    </h3>

                    <div className="p-4 bg-gray-50 dark:bg-gray-700/50 rounded-lg space-y-2">
                      <div className="flex justify-between text-sm">
                        <span className="text-gray-500 dark:text-gray-400">Last Sync</span>
                        <span className="text-gray-900 dark:text-gray-100">
                          {formatDate(connectionHealth.last_sync_at)}
                        </span>
                      </div>

                      {connectionHealth.error_count > 0 && (
                        <div className="flex justify-between text-sm">
                          <span className="text-gray-500 dark:text-gray-400">Recent Errors</span>
                          <span className="text-amber-600 dark:text-amber-400">
                            {connectionHealth.error_count}
                          </span>
                        </div>
                      )}

                      {connectionHealth.last_error && (
                        <div className="mt-2 p-2 bg-red-50 dark:bg-red-900/20 rounded text-xs text-red-700 dark:text-red-300">
                          <span className="font-medium">Last error:</span>{' '}
                          {connectionHealth.last_error.length > 100
                            ? `${connectionHealth.last_error.substring(0, 100)}...`
                            : connectionHealth.last_error}
                        </div>
                      )}
                    </div>
                  </div>
                )}

                {/* Advanced Section (Collapsible) */}
                <div className="border-t border-gray-200 dark:border-gray-700 pt-6">
                  <button
                    type="button"
                    onClick={() => setShowAdvanced(!showAdvanced)}
                    className="flex items-center justify-between w-full text-left"
                  >
                    <h3 className="text-base font-medium text-gray-900 dark:text-gray-100">
                      <i className="fas fa-cog mr-2 text-gray-400" aria-hidden="true" />
                      Advanced Settings
                    </h3>
                    <i
                      className={`fas fa-chevron-${showAdvanced ? 'up' : 'down'} text-gray-400`}
                      aria-hidden="true"
                    />
                  </button>

                  {showAdvanced && (
                    <div className="mt-4">
                      <p className="text-sm text-gray-500 dark:text-gray-400 mb-3">
                        Configure how tax accounts are mapped between QuickBooks and Brikli.
                      </p>
                      <button
                        type="button"
                        onClick={() => setShowAccountMapping(true)}
                        className="w-full flex items-center justify-center gap-2 px-4 py-3 bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300 rounded-lg border border-gray-200 dark:border-gray-600 hover:bg-gray-200 dark:hover:bg-gray-600 transition-colors"
                      >
                        <i className="fas fa-link" aria-hidden="true" />
                        Configure Tax Account Mappings
                      </button>
                    </div>
                  )}
                </div>

                {/* Disconnect Section */}
                {onDisconnect && (
                  <div className="border-t border-gray-200 dark:border-gray-700 pt-6">
                    <h3 className="text-base font-medium text-gray-900 dark:text-gray-100 mb-3">
                      <i className="fas fa-unlink mr-2 text-red-500" aria-hidden="true" />
                      Disconnect Integration
                    </h3>

                    <div className="p-4 bg-red-50 dark:bg-red-900/20 rounded-lg border border-red-200 dark:border-red-800">
                      <p className="text-sm text-red-700 dark:text-red-300 mb-4">
                        Disconnecting will stop all automatic syncing between QuickBooks and Brikli.
                        Your existing data will be preserved, but no new changes will sync.
                      </p>
                      <button
                        type="button"
                        onClick={() => {
                          onClose();
                          onDisconnect();
                        }}
                        className="w-full flex items-center justify-center gap-2 px-4 py-2.5 bg-red-600 hover:bg-red-700 text-white rounded-lg font-medium transition-colors"
                      >
                        <i className="fas fa-unlink" aria-hidden="true" />
                        Disconnect QuickBooks
                      </button>
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>

          {/* Footer */}
          <div className="px-6 py-4 border-t border-gray-200 dark:border-gray-700 flex justify-between">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-md transition-colors"
            >
              Cancel
            </button>

            <button
              type="button"
              onClick={handleSave}
              disabled={saving || loading || !hasChanges}
              className="px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2 transition-colors"
            >
              {saving ? (
                <>
                  <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white" />
                  <span>Saving...</span>
                </>
              ) : (
                <span>Save Settings</span>
              )}
            </button>
          </div>
        </div>
      </div>

      {/* Account Mapping Modal (nested) */}
      <QuickBooksAccountMapping
        isOpen={showAccountMapping}
        onClose={() => setShowAccountMapping(false)}
        onMappingsUpdated={() => {
          // Optionally refresh or notify
        }}
      />
    </>
  );
});

QuickBooksSettings.displayName = 'QuickBooksSettings';

export default QuickBooksSettings;
