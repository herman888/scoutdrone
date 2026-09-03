import React, { useState, useEffect, useCallback, memo } from 'react';
import * as Sentry from '@sentry/react';
import { toast } from 'react-toastify';
import {
  AccountMapping,
  QuickBooksAccount,
  CanadianTaxType,
  CANADIAN_TAX_TYPES,
} from '../../types/integrations';
import {
  getAccountMappings,
  getTaxEligibleAccounts,
  saveAccountMapping,
  autoDetectAccountMappings,
  deleteAccountMapping,
} from '../../utils/api/quickbooks';

interface QuickBooksAccountMappingProps {
  isOpen: boolean;
  onClose: () => void;
  onMappingsUpdated?: () => void;
}

/**
 * QuickBooks Account Mapping Component
 *
 * Allows users to configure mappings between Canadian tax types (GST, HST, PST, QST)
 * and their QuickBooks accounts. This fixes the "No tax details found" warning
 * by enabling proper tax line detection during expense sync.
 */
const QuickBooksAccountMapping: React.FC<QuickBooksAccountMappingProps> = memo(({
  isOpen,
  onClose,
  onMappingsUpdated,
}) => {
  const [mappings, setMappings] = useState<AccountMapping[]>([]);
  const [accounts, setAccounts] = useState<QuickBooksAccount[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [autoDetecting, setAutoDetecting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Track selected accounts for each tax type
  const [selectedAccounts, setSelectedAccounts] = useState<Record<CanadianTaxType, string>>({
    GST: '',
    HST: '',
    PST: '',
    QST: '',
  });

  // Load existing mappings and available accounts
  const loadData = useCallback(async () => {
    setLoading(true);
    setError(null);

    try {
      const [mappingsResult, accountsResult] = await Promise.all([
        getAccountMappings(),
        getTaxEligibleAccounts(),
      ]);

      if (mappingsResult) {
        setMappings(mappingsResult);

        // Initialize selected accounts from existing mappings
        const initialSelections: Record<CanadianTaxType, string> = {
          GST: '',
          HST: '',
          PST: '',
          QST: '',
        };

        mappingsResult.forEach((mapping: AccountMapping) => {
          if (mapping.mapping_type === 'tax_account' &&
              CANADIAN_TAX_TYPES.includes(mapping.brikli_key as CanadianTaxType)) {
            initialSelections[mapping.brikli_key as CanadianTaxType] = mapping.quickbooks_account_id;
          }
        });

        setSelectedAccounts(initialSelections);
      }

      if (accountsResult) {
        setAccounts(accountsResult);
      }
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'Failed to load account data';
      setError(errorMessage);
      Sentry.captureException(err, {
        tags: {
          component: 'QuickBooksAccountMapping',
          action: 'loadData',
        },
      });
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (isOpen) {
      loadData();
    }
  }, [isOpen, loadData]);

  // Handle account selection change
  const handleAccountChange = (taxType: CanadianTaxType, accountId: string) => {
    setSelectedAccounts(prev => ({
      ...prev,
      [taxType]: accountId,
    }));
  };

  // Save a single mapping
  const handleSaveMapping = async (taxType: CanadianTaxType) => {
    const accountId = selectedAccounts[taxType];

    if (!accountId) {
      // If no account selected, delete the existing mapping
      const existingMapping = mappings.find(
        m => m.mapping_type === 'tax_account' && m.brikli_key === taxType
      );

      if (existingMapping) {
        setSaving(true);
        try {
          await deleteAccountMapping(existingMapping.id);
          toast.success(`${taxType} mapping removed`);
          await loadData();
          onMappingsUpdated?.();
        } catch (err) {
          toast.error(`Failed to remove ${taxType} mapping`);
          Sentry.captureException(err);
        } finally {
          setSaving(false);
        }
      }
      return;
    }

    setSaving(true);
    try {
      const account = accounts.find(a => a.id === accountId);

      await saveAccountMapping({
        mapping_type: 'tax_account',
        brikli_key: taxType,
        quickbooks_account_id: accountId,
        quickbooks_account_name: account?.name || 'Unknown Account',
        quickbooks_account_type: account?.account_type,
      });

      toast.success(`${taxType} account mapping saved`);
      await loadData();
      onMappingsUpdated?.();
    } catch (err) {
      toast.error(`Failed to save ${taxType} mapping`);
      Sentry.captureException(err, {
        tags: {
          component: 'QuickBooksAccountMapping',
          action: 'saveMapping',
          taxType,
        },
      });
    } finally {
      setSaving(false);
    }
  };

  // Auto-detect tax accounts
  const handleAutoDetect = async () => {
    setAutoDetecting(true);
    try {
      const result = await autoDetectAccountMappings();

      if (result?.saved?.length > 0) {
        toast.success(
          `Auto-detected ${result.saved.length} tax account(s)`,
          { autoClose: 4000 }
        );
        await loadData();
        onMappingsUpdated?.();
      } else {
        toast.warn(
          'No tax accounts could be detected. Please configure them manually.',
          { autoClose: 5000 }
        );
      }
    } catch (err) {
      toast.error('Failed to auto-detect tax accounts');
      Sentry.captureException(err, {
        tags: {
          component: 'QuickBooksAccountMapping',
          action: 'autoDetect',
        },
      });
    } finally {
      setAutoDetecting(false);
    }
  };

  // Save all mappings
  const handleSaveAll = async () => {
    setSaving(true);
    try {
      let savedCount = 0;

      for (const taxType of CANADIAN_TAX_TYPES) {
        const accountId = selectedAccounts[taxType];
        if (accountId) {
          const account = accounts.find(a => a.id === accountId);
          await saveAccountMapping({
            mapping_type: 'tax_account',
            brikli_key: taxType,
            quickbooks_account_id: accountId,
            quickbooks_account_name: account?.name || 'Unknown Account',
            quickbooks_account_type: account?.account_type,
          });
          savedCount++;
        }
      }

      if (savedCount > 0) {
        toast.success(`Saved ${savedCount} tax account mapping(s)`);
        await loadData();
        onMappingsUpdated?.();
      } else {
        toast.info('No mappings to save');
      }
    } catch (err) {
      toast.error('Failed to save mappings');
      Sentry.captureException(err);
    } finally {
      setSaving(false);
    }
  };

  // Get the current mapping for a tax type
  const getMappingForTaxType = (taxType: CanadianTaxType): AccountMapping | undefined => {
    return mappings.find(
      m => m.mapping_type === 'tax_account' && m.brikli_key === taxType
    );
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50">
      <div
        className="bg-white dark:bg-gray-800 rounded-lg shadow-xl w-full max-w-2xl mx-4 max-h-[90vh] overflow-hidden flex flex-col"
        role="dialog"
        aria-modal="true"
        aria-labelledby="account-mapping-title"
      >
        {/* Header */}
        <div className="px-6 py-4 border-b border-gray-200 dark:border-gray-700">
          <div className="flex items-center justify-between">
            <h2
              id="account-mapping-title"
              className="text-xl font-semibold text-gray-900 dark:text-gray-100"
            >
              Tax Account Mapping
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
            Map your Canadian tax types to QuickBooks accounts for proper tax tracking during expense sync.
          </p>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto px-6 py-4">
          {loading ? (
            <div className="flex items-center justify-center py-12">
              <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600" />
              <span className="ml-2 text-gray-500 dark:text-gray-400">Loading accounts...</span>
            </div>
          ) : error ? (
            <div className="text-center py-8">
              <p className="text-red-600 dark:text-red-400 mb-4">{error}</p>
              <button
                onClick={loadData}
                className="px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700"
              >
                Retry
              </button>
            </div>
          ) : (
            <>
              {/* Auto-detect button */}
              <div className="mb-6">
                <button
                  onClick={handleAutoDetect}
                  disabled={autoDetecting || saving}
                  className="w-full flex items-center justify-center gap-2 px-4 py-3 bg-green-50 dark:bg-green-900/20 text-green-700 dark:text-green-400 rounded-lg border border-green-200 dark:border-green-800 hover:bg-green-100 dark:hover:bg-green-900/30 disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  {autoDetecting ? (
                    <>
                      <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-green-600" />
                      <span>Detecting...</span>
                    </>
                  ) : (
                    <>
                      <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
                      </svg>
                      <span>Auto-Detect Tax Accounts</span>
                    </>
                  )}
                </button>
                <p className="mt-2 text-xs text-gray-500 dark:text-gray-400 text-center">
                  Automatically find accounts matching GST, HST, PST, or QST patterns
                </p>
              </div>

              {/* Tax type mappings */}
              <div className="space-y-4">
                {CANADIAN_TAX_TYPES.map(taxType => {
                  const currentMapping = getMappingForTaxType(taxType);

                  return (
                    <div
                      key={taxType}
                      className="flex items-center gap-4 p-4 bg-gray-50 dark:bg-gray-700/50 rounded-lg"
                    >
                      <div className="flex-shrink-0 w-24">
                        <span className="font-medium text-gray-900 dark:text-gray-100">
                          {taxType}
                        </span>
                        {currentMapping && (
                          <span className="block text-xs text-green-600 dark:text-green-400 mt-0.5">
                            Mapped
                          </span>
                        )}
                      </div>

                      <div className="flex-1">
                        <select
                          value={selectedAccounts[taxType]}
                          onChange={(e) => handleAccountChange(taxType, e.target.value)}
                          className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                        >
                          <option value="">-- Select Account --</option>
                          {accounts.map(account => (
                            <option key={account.id} value={account.id}>
                              {account.name} ({account.account_type})
                            </option>
                          ))}
                        </select>
                      </div>

                      <button
                        onClick={() => handleSaveMapping(taxType)}
                        disabled={saving || autoDetecting}
                        className="px-3 py-2 bg-blue-600 text-white text-sm rounded-md hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed"
                      >
                        Save
                      </button>
                    </div>
                  );
                })}
              </div>

              {/* Info section */}
              <div className="mt-6 p-4 bg-blue-50 dark:bg-blue-900/20 rounded-lg">
                <h3 className="text-sm font-medium text-blue-800 dark:text-blue-300 mb-2">
                  Why configure tax mappings?
                </h3>
                <p className="text-sm text-blue-700 dark:text-blue-400">
                  When you sync expenses from QuickBooks, Brikli needs to know which accounts
                  represent tax payments (GST, HST, PST, QST). Without these mappings, you may
                  see the "No tax details found" warning and tax amounts won't be properly tracked.
                </p>
              </div>
            </>
          )}
        </div>

        {/* Footer */}
        <div className="px-6 py-4 border-t border-gray-200 dark:border-gray-700 flex justify-between">
          <button
            onClick={onClose}
            className="px-4 py-2 text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-md"
          >
            Cancel
          </button>

          <button
            onClick={handleSaveAll}
            disabled={saving || autoDetecting || loading}
            className="px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
          >
            {saving ? (
              <>
                <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white" />
                <span>Saving...</span>
              </>
            ) : (
              <span>Save All Mappings</span>
            )}
          </button>
        </div>
      </div>
    </div>
  );
});

QuickBooksAccountMapping.displayName = 'QuickBooksAccountMapping';

export default QuickBooksAccountMapping;
