import React, { useState } from 'react';
import { toast } from 'react-toastify';
import { removeUserTaxDefault } from '../../../utils/api/accounting';
import type { TaxDetail } from '../../../types/accounting';

interface SavedTaxesModalProps {
  isOpen: boolean;
  onClose: () => void;
  savedTaxes: TaxDetail[];
  onTaxesUpdated: () => void;
  onApplyTax?: (tax: TaxDetail) => void;
}

/**
 * SavedTaxesModal Component
 * 
 * Displays all saved/favorite taxes and allows users to manage them (delete).
 */
const SavedTaxesModal: React.FC<SavedTaxesModalProps> = ({
  isOpen,
  onClose,
  savedTaxes,
  onTaxesUpdated,
  onApplyTax,
}) => {
  const [deletingTaxName, setDeletingTaxName] = useState<string | null>(null);
  const [applyingTaxName, setApplyingTaxName] = useState<string | null>(null);

  if (!isOpen) return null;

  const handleApply = async (tax: TaxDetail) => {
    try {
      setApplyingTaxName(tax.tax_name);
      if (onApplyTax) {
        onApplyTax(tax);
        toast.success(`Applied ${tax.tax_name} (${tax.tax_rate}%) to invoice`);
      }
    } catch (error) {
      console.error('Failed to apply tax:', error);
      toast.error('Failed to apply tax');
    } finally {
      setApplyingTaxName(null);
    }
  };

  const handleDelete = async (tax: TaxDetail) => {
    if (!window.confirm(`Remove ${tax.tax_name} (${tax.tax_rate}%) from saved taxes?`)) {
      return;
    }

    try {
      setDeletingTaxName(tax.tax_name);
      const result = await removeUserTaxDefault({
        tax_name: tax.tax_name,
        tax_rate: tax.tax_rate
      });
      
      if (result.success) {
        toast.success(`Removed ${tax.tax_name} from saved taxes`);
        onTaxesUpdated();
      } else {
        toast.error(result.error || 'Failed to remove tax');
      }
    } catch (error) {
      console.error('Failed to remove tax:', error);
      toast.error('Failed to remove tax');
    } finally {
      setDeletingTaxName(null);
    }
  };

  return (
    <>
      {/* Backdrop */}
      <div
        className="fixed inset-0 bg-black bg-opacity-50 z-40"
        onClick={onClose}
      />

      {/* Modal */}
      <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
        <div className="bg-white dark:bg-gray-800 rounded-lg shadow-xl max-w-md w-full max-h-[80vh] flex flex-col">
          {/* Header */}
          <div className="flex items-center justify-between p-4 border-b border-gray-200 dark:border-gray-700">
            <h2 className="text-lg font-semibold text-gray-900 dark:text-white">
              Saved Taxes
            </h2>
            <button
              onClick={onClose}
              className="text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 transition-colors"
            >
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>

          {/* Content */}
          <div className="flex-1 overflow-y-auto p-4">
            {savedTaxes.length === 0 ? (
              <div className="text-center py-8">
                <svg className="w-16 h-16 mx-auto mb-4 text-gray-400 dark:text-gray-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                </svg>
                <p className="text-sm text-gray-600 dark:text-gray-400 mb-2">No saved taxes yet</p>
                <p className="text-xs text-gray-500 dark:text-gray-500">
                  Click the star icon next to a tax to save it for future invoices
                </p>
              </div>
            ) : (
              <div className="space-y-2">
                {savedTaxes.map((tax, index) => (
                  <div
                    key={`${tax.tax_name}-${tax.tax_rate}-${index}`}
                    className="flex items-center justify-between p-3 bg-gray-50 dark:bg-gray-900 rounded-lg border border-gray-200 dark:border-gray-700 hover:border-gray-300 dark:hover:border-gray-600 transition-colors"
                  >
                    <div className="flex items-center space-x-3 flex-1">
                      <div className="flex-shrink-0">
                        <svg className="w-5 h-5 text-yellow-500" fill="currentColor" viewBox="0 0 20 20">
                          <path d="M9.049 2.927c.3-.921 1.603-.921 1.902 0l1.07 3.292a1 1 0 00.95.69h3.462c.969 0 1.371 1.24.588 1.81l-2.8 2.034a1 1 0 00-.364 1.118l1.07 3.292c.3.921-.755 1.688-1.54 1.118l-2.8-2.034a1 1 0 00-1.175 0l-2.8 2.034c-.784.57-1.838-.197-1.539-1.118l1.07-3.292a1 1 0 00-.364-1.118L2.98 8.72c-.783-.57-.38-1.81.588-1.81h3.461a1 1 0 00.951-.69l1.07-3.292z" />
                        </svg>
                      </div>
                      <div>
                        <p className="text-sm font-medium text-gray-900 dark:text-white">
                          {tax.tax_name}
                        </p>
                        <p className="text-xs text-gray-500 dark:text-gray-400">
                          {tax.tax_rate}% rate
                        </p>
                      </div>
                    </div>

                    <div className="flex items-center gap-2">
                      {onApplyTax && (
                        <button
                          onClick={() => handleApply(tax)}
                          disabled={applyingTaxName === tax.tax_name}
                          className="px-3 py-1.5 text-xs font-medium text-white bg-blue-600 hover:bg-blue-700 dark:bg-blue-500 dark:hover:bg-blue-600 rounded-md disabled:opacity-50 transition-colors"
                          title="Apply to invoice"
                        >
                          {applyingTaxName === tax.tax_name ? (
                            <svg className="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
                              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                            </svg>
                          ) : (
                            'Apply'
                          )}
                        </button>
                      )}
                      
                      <button
                        onClick={() => handleDelete(tax)}
                        disabled={deletingTaxName === tax.tax_name}
                        className="text-red-600 hover:text-red-700 dark:text-red-400 dark:hover:text-red-300 disabled:opacity-50 p-1 transition-colors"
                        title="Remove saved tax"
                      >
                        {deletingTaxName === tax.tax_name ? (
                          <svg className="w-5 h-5 animate-spin" fill="none" viewBox="0 0 24 24">
                            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                          </svg>
                        ) : (
                          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                          </svg>
                        )}
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Footer */}
          <div className="p-4 border-t border-gray-200 dark:border-gray-700">
            <button
              onClick={onClose}
              className="w-full px-4 py-2 bg-gray-100 dark:bg-gray-700 text-gray-900 dark:text-white rounded-lg font-medium hover:bg-gray-200 dark:hover:bg-gray-600 transition-colors"
            >
              Close
            </button>
          </div>
        </div>
      </div>
    </>
  );
};

export default SavedTaxesModal;
