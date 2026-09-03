import React from 'react';

interface LastPaymentInfo {
  amount: number;
  date: string;
  method?: string;
}

interface PaymentSummaryCardProps {
  paidThisMonth: number;
  outstandingBalance: number;
  securityDeposit: number | string | null;
  hasActiveLease: boolean;
  onRecordPayment: () => void;
  lastPayment?: LastPaymentInfo | null;
  nextDueAmount: number | null;
  nextDueDate: Date | null;
}

const formatCurrency = (value: number | string | undefined | null): string => {
  if (value === undefined || value === null) return 'N/A';
  const numValue = typeof value === 'string' ? parseFloat(value) : value;
  if (isNaN(numValue)) return 'N/A';
  return `$${numValue.toLocaleString('en-CA', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
};

const formatDate = (dateString: string): string => {
  const date = new Date(dateString);
  return date.toLocaleDateString('en-CA', { month: 'short', day: 'numeric', year: 'numeric' });
};

const PaymentSummaryCard: React.FC<PaymentSummaryCardProps> = ({
  paidThisMonth,
  outstandingBalance,
  securityDeposit,
  hasActiveLease,
  onRecordPayment,
  lastPayment,
  nextDueAmount,
  nextDueDate,
}) => {
  return (
    <div className="bg-white dark:bg-gray-800 rounded-lg shadow-sm border border-gray-200 dark:border-gray-700 p-4 h-[320px] flex flex-col">
      {/* Header */}
      <h3 className="text-md font-semibold text-gray-900 dark:text-gray-100 mb-3 flex items-center gap-2">
        <svg className="w-6 h-6 text-green-600 dark:text-green-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8c-1.657 0-3 .895-3 2s1.343 2 3 2 3 .895 3 2-1.343 2-3 2m0-8c1.11 0 2.08.402 2.599 1M12 8V7m0 1v8m0 0v1m0-1c-1.11 0-2.08-.402-2.599-1M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
        </svg>
        Payment Summary
      </h3>

      <div className="flex-1 flex flex-col">
        {/* Financial Grid - 2x2 boxes like CurrentLeaseCard */}
        <div className="grid grid-cols-2 gap-3 mb-3">
          <div className="bg-green-50 dark:bg-green-900/20 rounded-lg p-2.5">
            <div className="text-xs text-gray-500 dark:text-gray-400 mb-0.5">Paid This Month</div>
            <div className="text-base font-semibold text-green-600 dark:text-green-400">
              {formatCurrency(paidThisMonth)}
            </div>
          </div>
          <div className={`rounded-lg p-2.5 ${outstandingBalance > 0 ? 'bg-red-50 dark:bg-red-900/20' : 'bg-gray-50 dark:bg-gray-700/50'}`}>
            <div className="text-xs text-gray-500 dark:text-gray-400 mb-0.5">Outstanding</div>
            <div className={`text-base font-semibold ${outstandingBalance > 0 ? 'text-red-600 dark:text-red-400' : 'text-gray-900 dark:text-gray-100'}`}>
              {formatCurrency(outstandingBalance)}
            </div>
          </div>
        </div>

        {/* Next Due & Security Deposit Row */}
        <div className="grid grid-cols-2 gap-3 mb-3">
          <div>
            <div className="text-xs text-gray-500 dark:text-gray-400 mb-0.5">Next Due</div>
            {nextDueAmount && nextDueDate ? (
              <>
                <div className="text-sm font-semibold text-gray-900 dark:text-gray-100">
                  {formatCurrency(nextDueAmount)}
                </div>
                <div className="text-xs text-gray-500 dark:text-gray-400">
                  {nextDueDate.toLocaleDateString('en-CA', { month: 'short', day: 'numeric' })}
                </div>
              </>
            ) : (
              <div className="text-sm text-gray-400 dark:text-gray-500">N/A</div>
            )}
          </div>
          <div>
            <div className="text-xs text-gray-500 dark:text-gray-400 mb-0.5">Security Deposit</div>
            <div className="text-sm font-semibold text-gray-900 dark:text-gray-100">
              {formatCurrency(securityDeposit)}
            </div>
            <div className="text-xs text-gray-500 dark:text-gray-400">Held</div>
          </div>
        </div>

        {/* Last Payment Info */}
        {lastPayment ? (
          <div className="bg-gray-50 dark:bg-gray-700/50 rounded-lg p-2.5 mb-3">
            <div className="flex items-center justify-between">
              <div>
                <div className="text-xs text-gray-500 dark:text-gray-400">Last Payment</div>
                <div className="text-sm font-medium text-gray-900 dark:text-gray-100">
                  {formatCurrency(lastPayment.amount)}
                </div>
              </div>
              <div className="text-right">
                <div className="text-xs text-gray-500 dark:text-gray-400">{formatDate(lastPayment.date)}</div>
                {lastPayment.method && (
                  <div className="text-xs text-gray-400 dark:text-gray-500">{lastPayment.method}</div>
                )}
              </div>
            </div>
          </div>
        ) : (
          <div className="bg-gray-50 dark:bg-gray-700/50 rounded-lg p-2.5 mb-3">
            <div className="text-xs text-gray-500 dark:text-gray-400 text-center py-1">No payment history</div>
          </div>
        )}

        {/* Action Button */}
        <div className="mt-auto">
          <button
            onClick={onRecordPayment}
            disabled={!hasActiveLease}
            className="w-full inline-flex items-center justify-center gap-2 px-3 py-1.5 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-lg text-gray-700 dark:text-gray-200 text-sm font-medium hover:bg-gray-50 dark:hover:bg-gray-600 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 6v6m0 0v6m0-6h6m-6 0H6" />
            </svg>
            Record Payment
          </button>
        </div>
      </div>
    </div>
  );
};

export default PaymentSummaryCard;
