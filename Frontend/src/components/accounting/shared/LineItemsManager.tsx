import React from 'react';
import Decimal from 'decimal.js';

export interface LineItem {
  description: string;
  quantity: string;
  unit_price: string;
  is_taxable: boolean;
  expense_category?: string;
  sort_order?: number;
}

interface LineItemsManagerProps {
  lineItems: LineItem[];
  onAddLineItem: () => void;
  onRemoveLineItem: (index: number) => void;
  onUpdateLineItem: (index: number, field: keyof LineItem, value: string | boolean) => void;
  errors?: Record<string, string>;
  showExpenseCategory?: boolean;
}

/**
 * LineItemsManager Component
 * 
 * Manages multiple line items for invoices following industry best practices:
 * - Description: What is being charged
 * - Quantity: How many units (supports decimals like 2.5 hours)
 * - Unit Price: Price per unit
 * - Line Total: Auto-calculated (quantity × unit_price)
 * - Taxable: Whether taxes apply to this line
 * - Expense Category: For accounting classification
 * 
 * Mimics Stripe/QuickBooks invoice line item UX.
 */
const LineItemsManager: React.FC<LineItemsManagerProps> = ({
  lineItems,
  onAddLineItem,
  onRemoveLineItem,
  onUpdateLineItem,
  errors = {},
  showExpenseCategory = true,
}) => {
  // Calculate line total for display
  const calculateLineTotal = (quantity: string, unitPrice: string): string => {
    try {
      const qty = new Decimal(quantity || '0');
      const price = new Decimal(unitPrice || '0');
      return qty.mul(price).toFixed(2);
    } catch {
      return '0.00';
    }
  };

  // Calculate subtotal of all lines

  // Common expense categories for real estate
  const expenseCategories = [
    'Rent',
    'Utilities',
    'Maintenance',
    'Repairs',
    'Cleaning',
    'Landscaping',
    'Property Management',
    'Insurance',
    'Property Tax',
    'Legal Fees',
    'Other',
  ];

  return (
    <div>
      <div className="flex items-center justify-between mb-3">
        <h2 className="text-lg font-semibold text-gray-900 dark:text-white">
          Line Items
        </h2>
        <button
          type="button"
          onClick={onAddLineItem}
          className="px-3 py-1.5 bg-blue-600 text-white rounded-md hover:bg-blue-700 transition-colors text-sm font-medium flex items-center space-x-1"
        >
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
          </svg>
          <span>Add Line</span>
        </button>
      </div>

      <div className="space-y-3">
        {lineItems.length === 0 ? (
          <div className="text-center py-8 text-gray-500 dark:text-gray-400">
            <svg className="w-12 h-12 mx-auto mb-3 opacity-50" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
            </svg>
            <p className="text-sm">No line items yet. Click "Add Line" to start.</p>
          </div>
        ) : (
          lineItems.map((item, index) => {
            const lineTotal = calculateLineTotal(item.quantity, item.unit_price);
            
            return (
              <div
                key={index}
                className="bg-white dark:bg-gray-700 p-3 rounded-lg border border-gray-200 dark:border-gray-600 space-y-2.5"
              >
                {/* Header with line number and remove button */}
                <div className="flex items-center justify-between mb-1">
                  <span className="text-sm font-medium text-gray-700 dark:text-gray-300">
                    Line {index + 1}
                  </span>
                  {lineItems.length > 1 && (
                    <button
                      type="button"
                      onClick={() => onRemoveLineItem(index)}
                      className="text-red-600 hover:text-red-700 dark:text-red-400 dark:hover:text-red-300 p-1"
                      title="Remove line item"
                    >
                      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                      </svg>
                    </button>
                  )}
                </div>

                {/* Description */}
                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                    Description *
                  </label>
                  <input
                    type="text"
                    value={item.description}
                    onChange={(e) => onUpdateLineItem(index, 'description', e.target.value)}
                    placeholder="e.g., Monthly rent - Unit 101"
                    className={`w-full px-3 py-2 border rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 dark:focus:ring-blue-400 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 ${
                      errors[`line_item_${index}_description`] ? 'border-red-300 dark:border-red-500' : 'border-gray-300 dark:border-gray-600'
                    }`}
                  />
                  {errors[`line_item_${index}_description`] && (
                    <p className="mt-1 text-sm text-red-600 dark:text-red-400">{errors[`line_item_${index}_description`]}</p>
                  )}
                </div>

                {/* Quantity, Unit Price, and Line Total */}
                <div className="grid grid-cols-3 gap-3">
                  <div>
                    <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                      Quantity *
                    </label>
                    <input
                      type="number"
                      step="0.001"
                      min="0.001"
                      value={item.quantity}
                      onChange={(e) => onUpdateLineItem(index, 'quantity', e.target.value)}
                      placeholder="1"
                      className={`w-full px-3 py-2 border rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 dark:focus:ring-blue-400 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 ${
                        errors[`line_item_${index}_quantity`] ? 'border-red-300 dark:border-red-500' : 'border-gray-300 dark:border-gray-600'
                      }`}
                    />
                    {errors[`line_item_${index}_quantity`] && (
                      <p className="mt-1 text-xs text-red-600 dark:text-red-400">{errors[`line_item_${index}_quantity`]}</p>
                    )}
                  </div>

                  <div>
                    <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                      Unit Price *
                    </label>
                    <input
                      type="number"
                      step="0.01"
                      min="0"
                      value={item.unit_price}
                      onChange={(e) => onUpdateLineItem(index, 'unit_price', e.target.value)}
                      placeholder="0.00"
                      className={`w-full px-3 py-2 border rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 dark:focus:ring-blue-400 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 ${
                        errors[`line_item_${index}_unit_price`] ? 'border-red-300 dark:border-red-500' : 'border-gray-300 dark:border-gray-600'
                      }`}
                    />
                    {errors[`line_item_${index}_unit_price`] && (
                      <p className="mt-1 text-xs text-red-600 dark:text-red-400">{errors[`line_item_${index}_unit_price`]}</p>
                    )}
                  </div>

                  <div>
                    <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                      Line Total
                    </label>
                    <div className="px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-gray-50 dark:bg-gray-900 text-gray-900 dark:text-gray-100 font-mono">
                      ${lineTotal}
                    </div>
                  </div>
                </div>

                {/* Category and Taxable Flag */}
                <div className="flex items-end gap-3">
                  {showExpenseCategory && (
                    <div className="flex-1">
                      <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                        Category
                      </label>
                      <select
                        value={item.expense_category || ''}
                        onChange={(e) => onUpdateLineItem(index, 'expense_category', e.target.value)}
                        className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 dark:focus:ring-blue-400 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100"
                      >
                        <option value="">Select category...</option>
                        {expenseCategories.map((category) => (
                          <option key={category} value={category.toLowerCase()}>
                            {category}
                          </option>
                        ))}
                      </select>
                    </div>
                  )}

                  <div className="pb-2">
                    <label className="flex items-center space-x-2 cursor-pointer">
                      <input
                        type="checkbox"
                        checked={item.is_taxable}
                        onChange={(e) => onUpdateLineItem(index, 'is_taxable', e.target.checked)}
                        className="w-4 h-4 text-blue-600 border-gray-300 dark:border-gray-600 rounded focus:ring-blue-500 dark:focus:ring-blue-400"
                      />
                      <span className="text-sm font-medium text-gray-700 dark:text-gray-300">
                        Taxable
                      </span>
                    </label>
                  </div>
                </div>
              </div>
            );
          })
        )}
      </div>

    </div>
  );
};

export default LineItemsManager;
