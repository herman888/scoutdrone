import React, { useState, useEffect, useCallback, memo, useMemo } from 'react';
import { toast } from 'react-toastify';
import * as Sentry from '@sentry/react';
import {
  previewQuickBooksSync,
  applyQuickBooksSync,
} from '../../utils/api/quickbooks';

// Types
interface TaxDetail {
  name: string;
  rate: number;
  amount: number;
}

interface SyncItem {
  entity_type: string;
  entity_id: string;
  entity_name: string;
  action: string;
  details: {
    amount?: number;
    subtotal?: number;
    tax_amount?: number;
    date?: string;
    destination?: string;
    tax_details?: TaxDetail[];
    tax_details_count?: number;
    category?: string;
    qb_customer_id?: string;
    qb_display_name?: string;
    [key: string]: unknown;
  };
  warnings: string[];
}

interface SyncPreview {
  items: SyncItem[];
  summary: {
    create: number;
    update: number;
    skip: number;
    error: number;
    total: number;
  };
  warnings: string[];
}

interface QuickBooksSyncWizardProps {
  isOpen: boolean;
  onClose: () => void;
  onSyncComplete?: () => void;
}

type WizardStep = 'loading' | 'customers' | 'transactions' | 'complete' | 'error';
type TransactionFilter = 'all' | 'expense' | 'invoice' | 'payment';

// Helper to categorize items
const categorizeItems = (items: SyncItem[]) => {
  const customersToSync: SyncItem[] = [];
  const customerUpdates: SyncItem[] = [];
  const expenses: SyncItem[] = [];
  const invoices: SyncItem[] = [];
  const payments: SyncItem[] = [];

  items.forEach((item) => {
    if (item.entity_type === 'customer_create' || item.entity_type === 'customer_link') {
      customersToSync.push(item);
    } else if (item.entity_type === 'customer_update') {
      customerUpdates.push(item);
    } else if (item.entity_type === 'expense') {
      expenses.push(item);
    } else if (item.entity_type === 'invoice') {
      invoices.push(item);
    } else if (item.entity_type === 'payment') {
      payments.push(item);
    }
  });

  return {
    customers: customersToSync,
    customerUpdates,
    expenses,
    invoices,
    payments
  };
};

// Unique key for each item
const getItemKey = (item: SyncItem) => `${item.entity_type}-${item.entity_id}`;

// Format date for display
const formatDate = (dateStr: string | undefined): string => {
  if (!dateStr) return '';
  try {
    const date = new Date(dateStr);
    return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
  } catch {
    return dateStr;
  }
};

const QuickBooksSyncWizard: React.FC<QuickBooksSyncWizardProps> = memo(({
  isOpen,
  onClose,
  onSyncComplete,
}) => {
  const [step, setStep] = useState<WizardStep>('loading');
  const [categorized, setCategorized] = useState<ReturnType<typeof categorizeItems> | null>(null);
  const [syncing, setSyncing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [customersSynced, setCustomersSynced] = useState(false);

  // Simple filter state
  const [filter, setFilter] = useState<TransactionFilter>('all');

  // Simple selection state - just a Set of item keys
  const [selected, setSelected] = useState<Set<string>>(new Set());

  // Get all transaction items - memoized to ensure stable reference
  const allItems = useMemo(() => {
    if (!categorized) return [];
    return [...categorized.expenses, ...categorized.invoices, ...categorized.payments];
  }, [categorized]);

  // Get filtered items for display - memoized and depends on filter
  const displayItems = useMemo(() => {
    if (filter === 'all') return allItems;
    return allItems.filter(item => item.entity_type === filter);
  }, [allItems, filter]);

  // Counts - memoized
  const counts = useMemo(() => {
    // Count selected items in current filter view
    const selectedInView = displayItems.filter(item => selected.has(getItemKey(item))).length;

    return {
      expenses: categorized?.expenses.length ?? 0,
      invoices: categorized?.invoices.length ?? 0,
      payments: categorized?.payments.length ?? 0,
      total: allItems.length,
      totalInView: displayItems.length,
      selected: selected.size,
      selectedInView
    };
  }, [categorized, allItems.length, displayItems, selected]);

  // Load preview data
  const loadPreview = useCallback(async () => {
    setStep('loading');
    setError(null);
    setFilter('all');
    setSelected(new Set());

    try {
      const data: SyncPreview = await previewQuickBooksSync();
      const cats = categorizeItems(data.items);
      setCategorized(cats);

      // Select all items by default
      const allKeys = new Set<string>();
      [...cats.expenses, ...cats.invoices, ...cats.payments].forEach(item => {
        allKeys.add(getItemKey(item));
      });
      setSelected(allKeys);

      // Determine which step to show
      const hasUnlinkedTenants = cats.customers.length > 0;
      const hasTransactions = cats.expenses.length > 0 || cats.invoices.length > 0 || cats.payments.length > 0;

      if (hasUnlinkedTenants) {
        setStep('customers');
      } else if (hasTransactions) {
        setCustomersSynced(true);
        setStep('transactions');
      } else {
        setStep('complete');
      }
    } catch (err) {
      console.error('Failed to load preview:', err);
      Sentry.captureException(err);
      setError('Failed to load sync preview');
      setStep('error');
    }
  }, []);

  // Reset when modal opens
  useEffect(() => {
    if (isOpen) {
      loadPreview();
      setCustomersSynced(false);
    }
  }, [isOpen, loadPreview]);

  // Toggle single item
  const toggleItem = (item: SyncItem) => {
    const key = getItemKey(item);
    setSelected(prev => {
      const next = new Set(prev);
      if (next.has(key)) {
        next.delete(key);
      } else {
        next.add(key);
      }
      return next;
    });
  };

  // Select/deselect all visible
  const toggleAll = () => {
    const visibleKeys = displayItems.map(getItemKey);
    const allSelected = visibleKeys.every(k => selected.has(k));

    setSelected(prev => {
      const next = new Set(prev);
      if (allSelected) {
        visibleKeys.forEach(k => next.delete(k));
      } else {
        visibleKeys.forEach(k => next.add(k));
      }
      return next;
    });
  };

  // Sync customers
  const handleSyncCustomers = async () => {
    if (!categorized) return;

    setSyncing(true);
    try {
      const allCustomerItems = [
        ...categorized.customers,
        ...categorized.customerUpdates
      ].map((item) => ({
        entity_type: item.entity_type,
        entity_id: item.entity_id,
        action: item.action,
        details: item.details,
      }));

      const result = await applyQuickBooksSync(allCustomerItems);

      if (result.success) {
        setCustomersSynced(true);
        const hasTransactions = counts.total > 0;

        if (hasTransactions) {
          setStep('transactions');
        } else {
          setStep('complete');
        }
        toast.success(`Linked ${categorized.customers.length} tenant(s) successfully`);
      } else {
        toast.error(result.errors?.[0] || 'Failed to sync customers');
      }
    } catch (err) {
      console.error('Failed to sync customers:', err);
      Sentry.captureException(err);
      toast.error('Failed to sync customers');
    } finally {
      setSyncing(false);
    }
  };

  // Sync transactions - only sync user-selected items
  const handleSyncTransactions = async () => {
    if (selected.size === 0) return;

    setSyncing(true);
    try {
      // Build payload of only selected preview items
      const itemsToSync = allItems
        .filter(item => selected.has(getItemKey(item)))
        .map(item => ({
          entity_type: item.entity_type,
          entity_id: item.entity_id,
          action: item.action,
          details: item.details,
        }));

      // Use applyQuickBooksSync to sync only selected items
      const result = await applyQuickBooksSync(itemsToSync);

      if (result.success) {
        toast.success(`Synced ${result.synced_count ?? result.items_synced ?? itemsToSync.length} item(s) successfully`);
        setStep('complete');
        onSyncComplete?.();
      } else {
        toast.error(result.errors?.[0] || 'Sync completed with errors');
        setStep('complete');
      }
    } catch (err) {
      console.error('Failed to sync transactions:', err);
      Sentry.captureException(err);
      toast.error('Failed to sync transactions');
    } finally {
      setSyncing(false);
    }
  };

  // Skip customers
  const handleSkipCustomers = () => {
    if (counts.total > 0) {
      setStep('transactions');
    } else {
      setStep('complete');
    }
  };

  // Check if all visible items are selected - memoized
  const selectionState = useMemo(() => {
    const visibleKeys = displayItems.map(getItemKey);
    const selectedCount = visibleKeys.filter(k => selected.has(k)).length;
    return {
      allSelected: visibleKeys.length > 0 && selectedCount === visibleKeys.length,
      someSelected: selectedCount > 0 && selectedCount < visibleKeys.length,
      noneSelected: selectedCount === 0
    };
  }, [displayItems, selected]);

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 overflow-y-auto">
      <div className="flex items-center justify-center min-h-screen px-4 pt-4 pb-20 text-center sm:block sm:p-0">
        {/* Backdrop */}
        <div
          className="fixed inset-0 transition-opacity bg-gray-500 bg-opacity-75 dark:bg-gray-900 dark:bg-opacity-75"
          onClick={onClose}
        />

        {/* Modal */}
        <div className="inline-block w-full max-w-2xl my-8 overflow-hidden text-left align-middle transition-all transform bg-white dark:bg-gray-800 rounded-xl shadow-xl">
          {/* Header */}
          <div className="px-6 py-4 border-b border-gray-200 dark:border-gray-700">
            <div className="flex items-center justify-between">
              <h2 className="text-xl font-semibold text-gray-900 dark:text-white">
                QuickBooks Sync Wizard
              </h2>
              <button
                onClick={onClose}
                className="text-gray-400 hover:text-gray-500 dark:hover:text-gray-300"
              >
                <i className="fas fa-times" />
              </button>
            </div>

            {/* Progress Steps */}
            <div className="flex items-center mt-4 space-x-4">
              <div className={`flex items-center ${step === 'customers' || customersSynced ? 'text-blue-600 dark:text-blue-400' : 'text-gray-400'}`}>
                <div className={`w-8 h-8 rounded-full flex items-center justify-center border-2 ${
                  customersSynced ? 'bg-green-500 border-green-500 text-white' :
                  step === 'customers' ? 'border-blue-600 dark:border-blue-400' : 'border-gray-300 dark:border-gray-600'
                }`}>
                  {customersSynced ? <i className="fas fa-check" /> : '1'}
                </div>
                <span className="ml-2 text-sm font-medium">Link Tenants</span>
              </div>

              <div className="flex-1 h-0.5 bg-gray-200 dark:bg-gray-700" />

              <div className={`flex items-center ${step === 'transactions' ? 'text-blue-600 dark:text-blue-400' : step === 'complete' ? 'text-green-600' : 'text-gray-400'}`}>
                <div className={`w-8 h-8 rounded-full flex items-center justify-center border-2 ${
                  step === 'complete' ? 'bg-green-500 border-green-500 text-white' :
                  step === 'transactions' ? 'border-blue-600 dark:border-blue-400' : 'border-gray-300 dark:border-gray-600'
                }`}>
                  {step === 'complete' ? <i className="fas fa-check" /> : '2'}
                </div>
                <span className="ml-2 text-sm font-medium">Sync Transactions</span>
              </div>
            </div>
          </div>

          {/* Content */}
          <div className="px-6 py-6 max-h-[60vh] overflow-y-auto">
            {step === 'loading' && (
              <div className="flex flex-col items-center justify-center py-12">
                <div className="w-12 h-12 border-4 border-blue-600 border-t-transparent rounded-full animate-spin" />
                <p className="mt-4 text-gray-600 dark:text-gray-400">Loading sync preview...</p>
              </div>
            )}

            {step === 'error' && (
              <div className="flex flex-col items-center justify-center py-12">
                <div className="w-16 h-16 rounded-full bg-red-100 dark:bg-red-900/20 flex items-center justify-center">
                  <i className="fas fa-exclamation-triangle text-2xl text-red-600 dark:text-red-400" />
                </div>
                <p className="mt-4 text-gray-900 dark:text-white font-medium">{error}</p>
                <button
                  onClick={loadPreview}
                  className="mt-4 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700"
                >
                  Try Again
                </button>
              </div>
            )}

            {step === 'customers' && categorized && (
              <div>
                <div className="mb-6">
                  <h3 className="text-lg font-medium text-gray-900 dark:text-white mb-2">
                    Step 1: Link Tenants to QuickBooks Customers
                  </h3>
                  <p className="text-sm text-gray-600 dark:text-gray-400">
                    The following tenants need to be linked to QuickBooks before transactions can sync.
                  </p>
                </div>

                {categorized.customers.length > 0 ? (
                  <>
                    <div className="grid grid-cols-2 gap-3 mb-4">
                      <div className="bg-green-50 dark:bg-green-900/20 rounded-lg p-3 text-center">
                        <p className="text-2xl font-bold text-green-700 dark:text-green-400">
                          {categorized.customers.filter(c => c.entity_type === 'customer_create').length}
                        </p>
                        <p className="text-xs text-green-600 dark:text-green-500">New in QuickBooks</p>
                      </div>
                      <div className="bg-blue-50 dark:bg-blue-900/20 rounded-lg p-3 text-center">
                        <p className="text-2xl font-bold text-blue-700 dark:text-blue-400">
                          {categorized.customers.filter(c => c.entity_type === 'customer_link').length}
                        </p>
                        <p className="text-xs text-blue-600 dark:text-blue-500">Match & Link</p>
                      </div>
                    </div>

                    <div className="space-y-2 max-h-48 overflow-y-auto">
                      {categorized.customers.map((item) => (
                        <div
                          key={item.entity_id}
                          className="flex items-center justify-between p-3 bg-gray-50 dark:bg-gray-700/50 rounded-lg"
                        >
                          <div className="flex items-center">
                            <div className={`w-8 h-8 rounded-full flex items-center justify-center mr-3 ${
                              item.entity_type === 'customer_create'
                                ? 'bg-green-100 dark:bg-green-900/30'
                                : 'bg-blue-100 dark:bg-blue-900/30'
                            }`}>
                              <i className={`fas ${
                                item.entity_type === 'customer_create' ? 'fa-user-plus text-green-600' : 'fa-link text-blue-600'
                              } text-sm`} />
                            </div>
                            <div>
                              <p className="text-sm font-medium text-gray-900 dark:text-white">
                                {item.entity_name}
                              </p>
                              <p className="text-xs text-gray-500 dark:text-gray-400">
                                {item.entity_type === 'customer_create'
                                  ? 'New customer in QuickBooks'
                                  : item.details.qb_display_name
                                    ? `Link to: ${item.details.qb_display_name}`
                                    : 'Link to matching QuickBooks customer'}
                              </p>
                            </div>
                          </div>
                        </div>
                      ))}
                    </div>
                  </>
                ) : (
                  <div className="text-center py-8">
                    <div className="w-16 h-16 mx-auto rounded-full bg-green-100 dark:bg-green-900/20 flex items-center justify-center mb-4">
                      <i className="fas fa-check text-2xl text-green-600 dark:text-green-400" />
                    </div>
                    <p className="text-gray-900 dark:text-white font-medium">All tenants are already linked!</p>
                    <p className="text-sm text-gray-600 dark:text-gray-400 mt-1">
                      You can proceed to sync transactions.
                    </p>
                  </div>
                )}
              </div>
            )}

            {step === 'transactions' && categorized && (
              <div>
                <div className="mb-4">
                  <h3 className="text-lg font-medium text-gray-900 dark:text-white mb-2">
                    {customersSynced ? 'Sync Transactions' : 'Step 2: Sync Transactions'}
                  </h3>
                  <p className="text-sm text-gray-600 dark:text-gray-400">
                    Select items to sync to QuickBooks.
                  </p>
                </div>

                {customersSynced && (
                  <div className="bg-green-50 dark:bg-green-900/20 rounded-lg p-3 mb-4">
                    <div className="flex items-center">
                      <i className="fas fa-check-circle text-green-600 dark:text-green-400 mr-2" />
                      <p className="text-sm text-green-800 dark:text-green-200">
                        All tenants are linked to QuickBooks customers.
                      </p>
                    </div>
                  </div>
                )}

                {/* Filter Buttons */}
                <div className="flex gap-2 mb-4">
                  <button
                    onClick={() => setFilter('all')}
                    className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${
                      filter === 'all'
                        ? 'bg-gray-800 text-white dark:bg-white dark:text-gray-800'
                        : 'bg-gray-100 text-gray-700 hover:bg-gray-200 dark:bg-gray-700 dark:text-gray-300 dark:hover:bg-gray-600'
                    }`}
                  >
                    All ({counts.total})
                  </button>
                  <button
                    onClick={() => setFilter('expense')}
                    className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${
                      filter === 'expense'
                        ? 'bg-purple-600 text-white'
                        : 'bg-purple-50 text-purple-700 hover:bg-purple-100 dark:bg-purple-900/30 dark:text-purple-300 dark:hover:bg-purple-900/50'
                    }`}
                  >
                    <i className="fas fa-receipt mr-1" />
                    Expenses ({counts.expenses})
                  </button>
                  <button
                    onClick={() => setFilter('invoice')}
                    className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${
                      filter === 'invoice'
                        ? 'bg-blue-600 text-white'
                        : 'bg-blue-50 text-blue-700 hover:bg-blue-100 dark:bg-blue-900/30 dark:text-blue-300 dark:hover:bg-blue-900/50'
                    }`}
                  >
                    <i className="fas fa-file-invoice-dollar mr-1" />
                    Invoices ({counts.invoices})
                  </button>
                  <button
                    onClick={() => setFilter('payment')}
                    className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${
                      filter === 'payment'
                        ? 'bg-green-600 text-white'
                        : 'bg-green-50 text-green-700 hover:bg-green-100 dark:bg-green-900/30 dark:text-green-300 dark:hover:bg-green-900/50'
                    }`}
                  >
                    <i className="fas fa-credit-card mr-1" />
                    Payments ({counts.payments})
                  </button>
                </div>

                {counts.total === 0 ? (
                  <div className="text-center py-8">
                    <p className="text-gray-600 dark:text-gray-400">
                      No transactions to sync at this time.
                    </p>
                  </div>
                ) : (
                  <>
                    {/* Table */}
                    <div className="border border-gray-200 dark:border-gray-700 rounded-lg overflow-hidden">
                      {/* Table Header */}
                      <div className="bg-gray-50 dark:bg-gray-700/50 px-4 py-2 border-b border-gray-200 dark:border-gray-700">
                        <div className="flex items-center">
                          <input
                            type="checkbox"
                            checked={selectionState.allSelected}
                            ref={el => { if (el) el.indeterminate = selectionState.someSelected; }}
                            onChange={toggleAll}
                            className="w-4 h-4 text-blue-600 rounded border-gray-300 focus:ring-blue-500 dark:border-gray-600 dark:bg-gray-700"
                          />
                          <span className="ml-3 text-sm font-medium text-gray-700 dark:text-gray-300">
                            {counts.selectedInView} of {counts.totalInView} selected
                            {filter !== 'all' && ` (${counts.selected} total)`}
                          </span>
                        </div>
                      </div>

                      {/* Table Body - key forces re-render when filter changes */}
                      <div key={filter} className="max-h-64 overflow-y-auto divide-y divide-gray-100 dark:divide-gray-700">
                        {displayItems.length === 0 ? (
                          <div className="px-4 py-8 text-center text-gray-500 dark:text-gray-400">
                            No {filter}s found.
                          </div>
                        ) : (
                          displayItems.map((item) => {
                            const key = getItemKey(item);
                            const isSelected = selected.has(key);

                            return (
                              <div
                                key={key}
                                onClick={() => toggleItem(item)}
                                className={`flex items-center px-4 py-3 cursor-pointer transition-colors ${
                                  isSelected
                                    ? 'bg-blue-50 dark:bg-blue-900/20'
                                    : 'hover:bg-gray-50 dark:hover:bg-gray-700/30'
                                }`}
                              >
                                <input
                                  type="checkbox"
                                  checked={isSelected}
                                  onChange={() => toggleItem(item)}
                                  onClick={e => e.stopPropagation()}
                                  className="w-4 h-4 text-blue-600 rounded border-gray-300 focus:ring-blue-500 dark:border-gray-600 dark:bg-gray-700"
                                />

                                <div className={`w-8 h-8 rounded-full flex items-center justify-center ml-3 ${
                                  item.entity_type === 'expense' ? 'bg-purple-100 dark:bg-purple-900/30' :
                                  item.entity_type === 'invoice' ? 'bg-blue-100 dark:bg-blue-900/30' :
                                  'bg-green-100 dark:bg-green-900/30'
                                }`}>
                                  <i className={`fas text-sm ${
                                    item.entity_type === 'expense' ? 'fa-receipt text-purple-600 dark:text-purple-400' :
                                    item.entity_type === 'invoice' ? 'fa-file-invoice-dollar text-blue-600 dark:text-blue-400' :
                                    'fa-credit-card text-green-600 dark:text-green-400'
                                  }`} />
                                </div>

                                <div className="ml-3 flex-1 min-w-0">
                                  <p className="text-sm font-medium text-gray-900 dark:text-white truncate">
                                    {item.entity_name}
                                  </p>
                                  <p className="text-xs text-gray-500 dark:text-gray-400">
                                    {formatDate(item.details.date)}
                                    {item.details.category && item.details.category !== 'other' && ` \u2022 ${item.details.category}`}
                                  </p>
                                </div>

                                <div className="text-right ml-2 shrink-0">
                                  {item.details.amount != null && (
                                    <span className="text-sm font-medium text-gray-900 dark:text-white">
                                      ${item.details.amount.toFixed(2)}
                                    </span>
                                  )}
                                  {/* Show tax breakdown only if there's a real subtotal (not tax-only expenses) */}
                                  {item.entity_type === 'expense' && item.details.subtotal != null && item.details.subtotal > 0 && item.details.tax_amount != null && item.details.tax_amount > 0 && (
                                    <p className="text-xs text-gray-500 dark:text-gray-400">
                                      ${item.details.subtotal.toFixed(2)} + ${item.details.tax_amount.toFixed(2)} tax
                                    </p>
                                  )}
                                </div>
                              </div>
                            );
                          })
                        )}
                      </div>
                    </div>
                  </>
                )}
              </div>
            )}

            {step === 'complete' && (
              <div className="flex flex-col items-center justify-center py-12">
                <div className="w-20 h-20 rounded-full bg-green-100 dark:bg-green-900/20 flex items-center justify-center mb-4">
                  <i className="fas fa-check text-3xl text-green-600 dark:text-green-400" />
                </div>
                <h3 className="text-xl font-semibold text-gray-900 dark:text-white mb-2">
                  Sync Complete!
                </h3>
                <p className="text-gray-600 dark:text-gray-400 text-center max-w-sm">
                  Your QuickBooks data is synchronized with Brikli.
                </p>
              </div>
            )}
          </div>

          {/* Footer */}
          <div className="px-6 py-4 border-t border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800/50">
            <div className="flex justify-between">
              <button
                onClick={onClose}
                className="px-4 py-2 text-gray-700 dark:text-gray-300 hover:text-gray-900 dark:hover:text-white"
              >
                {step === 'complete' ? 'Close' : 'Cancel'}
              </button>

              <div className="flex space-x-3">
                {step === 'customers' && categorized && categorized.customers.length > 0 && (
                  <>
                    <button
                      onClick={handleSkipCustomers}
                      disabled={syncing}
                      className="px-4 py-2 text-gray-600 dark:text-gray-400 hover:text-gray-800 dark:hover:text-gray-200"
                    >
                      Skip for now
                    </button>
                    <button
                      onClick={handleSyncCustomers}
                      disabled={syncing}
                      className="px-6 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 flex items-center"
                    >
                      {syncing ? (
                        <>
                          <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin mr-2" />
                          Linking...
                        </>
                      ) : (
                        <>
                          <i className="fas fa-link mr-2" />
                          Link {categorized.customers.length} Tenant{categorized.customers.length !== 1 ? 's' : ''}
                        </>
                      )}
                    </button>
                  </>
                )}

                {step === 'customers' && categorized && categorized.customers.length === 0 && (
                  <button
                    onClick={() => setStep('transactions')}
                    className="px-6 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700"
                  >
                    Continue
                    <i className="fas fa-arrow-right ml-2" />
                  </button>
                )}

                {step === 'transactions' && (
                  <button
                    onClick={handleSyncTransactions}
                    disabled={syncing || counts.selected === 0}
                    className="px-6 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 disabled:opacity-50 flex items-center"
                  >
                    {syncing ? (
                      <>
                        <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin mr-2" />
                        Syncing...
                      </>
                    ) : (
                      <>
                        <i className="fas fa-sync mr-2" />
                        Sync {counts.selected} Item{counts.selected !== 1 ? 's' : ''}
                      </>
                    )}
                  </button>
                )}

                {step === 'complete' && (
                  <button
                    onClick={() => {
                      onClose();
                      // Call onSyncComplete to let parent refresh data via TanStack Query
                      // instead of a disruptive full page reload
                      onSyncComplete?.();
                    }}
                    className="px-6 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700"
                  >
                    Done
                  </button>
                )}
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
});

QuickBooksSyncWizard.displayName = 'QuickBooksSyncWizard';

export default QuickBooksSyncWizard;
