import React from 'react';
import Decimal from 'decimal.js';
import type { InvoiceFormData } from '../../../types/accounting';

interface InvoicePreviewProps {
  formData: InvoiceFormData;
  lineItems: Array<{
    description: string;
    quantity: string;
    unit_price: string;
    line_total?: string;
    is_taxable: boolean;
  }>;
  calculatedTotals: {
    subtotal: Decimal;
    taxableSubtotal: Decimal;
    nonTaxableSubtotal: Decimal;
    totalTax: Decimal;
    grandTotal: Decimal;
  };
  recipientName?: string;
  recipientEmail?: string;
  companyName?: string;
}

/**
 * InvoicePreview Component
 * 
 * Stripe-style live preview of the invoice as it will appear.
 * Updates in real-time as the user fills out the form.
 */
const InvoicePreview: React.FC<InvoicePreviewProps> = ({
  formData,
  lineItems,
  calculatedTotals,
  recipientName,
  recipientEmail,
}) => {
  const formatCurrency = (amount: Decimal | string | number): string => {
    try {
      const decimal = typeof amount === 'string' || typeof amount === 'number' 
        ? new Decimal(amount) 
        : amount;
      return `$${decimal.toFixed(2)}`;
    } catch {
      return '$0.00';
    }
  };

  const formatDate = (dateStr: string): string => {
    if (!dateStr) return 'Not set';
    try {
      // Parse date as local date (YYYY-MM-DD format) to avoid timezone conversion issues
      const [year, month, day] = dateStr.split('T')[0].split('-').map(Number);
      const date = new Date(year, month - 1, day); // month is 0-indexed in JS
      return date.toLocaleDateString('en-US', { 
        year: 'numeric', 
        month: 'long', 
        day: 'numeric' 
      });
    } catch {
      return dateStr;
    }
  };

  return (
    <div className="bg-white dark:bg-gray-900 rounded-lg border border-gray-200 dark:border-gray-700 shadow-sm transform scale-75 origin-top-left w-[133.33%]">
      <div className="p-6">
      {/* Header */}
      <div className="flex justify-between items-start mb-6 pb-4 border-b border-gray-300 dark:border-gray-600">
        <div>
          <img 
            src="/brikli-logo-green-transparent.png" 
            alt="Brikli" 
            className="h-10 w-auto object-contain"
          />
        </div>
        <div className="text-right">
          <h2 className="text-2xl font-bold text-gray-900 dark:text-gray-100">INVOICE</h2>
          <p className="text-xs text-gray-500 dark:text-gray-400 font-mono mt-1">
            {formData.invoice_number || 'DRAFT'}
          </p>
        </div>
      </div>

      {/* Dates */}
      <div className="grid grid-cols-2 gap-4 mb-6">
        <div>
          <p className="text-xs font-medium text-gray-500 dark:text-gray-400 uppercase mb-1">Issue Date</p>
          <p className="text-sm text-gray-900 dark:text-gray-100">{formatDate(formData.issue_date)}</p>
        </div>
        <div>
          <p className="text-xs font-medium text-gray-500 dark:text-gray-400 uppercase mb-1">Due Date</p>
          <p className="text-sm text-gray-900 dark:text-gray-100">{formatDate(formData.due_date)}</p>
        </div>
      </div>

      {/* Bill To */}
      <div className="mb-6">
        <p className="text-xs font-medium text-gray-500 dark:text-gray-400 uppercase mb-2">Bill To</p>
        {recipientName ? (
          <div>
            <p className="text-sm font-medium text-gray-900 dark:text-gray-100">{recipientName}</p>
            {recipientEmail && (
              <p className="text-xs text-gray-600 dark:text-gray-400 mt-0.5">{recipientEmail}</p>
            )}
          </div>
        ) : (
          <p className="text-xs text-gray-400 dark:text-gray-500 italic">No recipient selected</p>
        )}
      </div>

      {/* Line Items */}
      <div className="mb-4">
        <table className="w-full text-xs">
          <thead>
            <tr className="border-b border-gray-200 dark:border-gray-700">
              <th className="text-left font-medium text-gray-500 dark:text-gray-400 uppercase pb-2">Description</th>
              <th className="text-right font-medium text-gray-500 dark:text-gray-400 uppercase pb-2 w-16">Qty</th>
              <th className="text-right font-medium text-gray-500 dark:text-gray-400 uppercase pb-2 w-20">Price</th>
              <th className="text-right font-medium text-gray-500 dark:text-gray-400 uppercase pb-2 w-24">Amount</th>
            </tr>
          </thead>
          <tbody>
            {lineItems.length === 0 ? (
              <tr>
                <td colSpan={4} className="py-3 text-center text-gray-400 dark:text-gray-500 italic">No items</td>
              </tr>
            ) : (
              lineItems.map((item, index) => (
                <tr key={index} className="border-b border-gray-100 dark:border-gray-800">
                  <td className="py-2 text-gray-900 dark:text-gray-100">
                    {item.description || `Item ${index + 1}`}
                    {!item.is_taxable && <span className="text-gray-400 ml-1">(Tax exempt)</span>}
                  </td>
                  <td className="py-2 text-right text-gray-700 dark:text-gray-300">{item.quantity || '1'}</td>
                  <td className="py-2 text-right text-gray-700 dark:text-gray-300">{formatCurrency(item.unit_price || '0')}</td>
                  <td className="py-2 text-right font-medium text-gray-900 dark:text-gray-100">{formatCurrency(item.line_total || '0')}</td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {/* Totals - Enhanced with Taxable/Non-Taxable Breakdown */}
      <div className="space-y-2 pt-3 border-t border-gray-200 dark:border-gray-700 text-xs">
        {/* Show breakdown if there are both taxable and non-taxable items */}
        {calculatedTotals.taxableSubtotal.greaterThan(0) && calculatedTotals.nonTaxableSubtotal.greaterThan(0) ? (
          <>
            {/* Taxable Subtotal */}
            <div className="flex justify-between">
              <span className="text-gray-600 dark:text-gray-400">Subtotal (Taxable)</span>
              <span className="font-medium text-gray-900 dark:text-gray-100">{formatCurrency(calculatedTotals.taxableSubtotal)}</span>
            </div>
            {/* Non-Taxable Subtotal */}
            <div className="flex justify-between">
              <span className="text-gray-600 dark:text-gray-400">Subtotal (Non-Taxable)</span>
              <span className="font-medium text-gray-900 dark:text-gray-100">{formatCurrency(calculatedTotals.nonTaxableSubtotal)}</span>
            </div>
            {/* Divider */}
            <div className="border-t border-gray-200 dark:border-gray-700 my-1"></div>
            {/* Total Subtotal */}
            <div className="flex justify-between">
              <span className="text-gray-700 dark:text-gray-300 font-medium">Total Subtotal</span>
              <span className="font-semibold text-gray-900 dark:text-gray-100">{formatCurrency(calculatedTotals.subtotal)}</span>
            </div>
          </>
        ) : (
          /* Simple subtotal if all items are same tax status */
          <div className="flex justify-between">
            <span className="text-gray-600 dark:text-gray-400">Subtotal</span>
            <span className="font-medium text-gray-900 dark:text-gray-100">{formatCurrency(calculatedTotals.subtotal)}</span>
          </div>
        )}

        {/* Taxes Section */}
        {formData.taxes && formData.taxes.some(t => t.tax_name && t.tax_rate) && (
          <>
            <div className="border-t border-gray-200 dark:border-gray-700 my-1.5"></div>
            <div className="text-gray-500 dark:text-gray-400 text-xs font-medium mb-1">
              Taxes {calculatedTotals.taxableSubtotal.greaterThan(0) ? "(applied to taxable items)" : ""}:
            </div>
            {formData.taxes
              .filter(tax => tax.tax_name && tax.tax_rate)
              .map((tax, index) => {
                const rate = new Decimal(tax.tax_rate || 0);
                const taxAmount = calculatedTotals.taxableSubtotal.mul(rate).div(100);

                return (
                  <div key={index} className="flex justify-between pl-2">
                    <span className="text-gray-600 dark:text-gray-400">{tax.tax_name} ({tax.tax_rate}%)</span>
                    <span className="font-medium text-gray-900 dark:text-gray-100">{formatCurrency(taxAmount)}</span>
                  </div>
                );
              })}
          </>
        )}

        {/* Total Due */}
        <div className="flex justify-between items-center pt-2 mt-2 border-t-2 border-gray-300 dark:border-gray-600 text-sm">
          <span className="font-semibold text-gray-900 dark:text-gray-100">Amount Due</span>
          <span className="text-lg font-bold text-gray-900 dark:text-gray-100">{formatCurrency(calculatedTotals.grandTotal)}</span>
        </div>
      </div>

      {/* Draft Badge */}
      {(formData.invoice_number.includes('DRAFT') || !formData.invoice_number) && (
        <div className="mt-4 pt-3 border-t border-gray-200 dark:border-gray-700 text-center">
          <span className="inline-block px-2 py-1 text-xs font-medium text-amber-700 dark:text-amber-400 bg-amber-100 dark:bg-amber-900/20 rounded">DRAFT</span>
        </div>
      )}
      </div>
    </div>
  );
};

export default InvoicePreview;
