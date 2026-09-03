import React from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import { XIcon } from 'lucide-react';
import type { Lease } from '../../../types/lease';
import { formatDateForDisplay } from '../../../utils/dateHelpers';

interface ViewLeaseModalProps {
  isOpen: boolean;
  onClose: () => void;
  lease: Lease | null;
  tenantName?: string;
}

const ViewLeaseModal: React.FC<ViewLeaseModalProps> = ({
  isOpen,
  onClose,
  lease,
  tenantName,
}) => {
  if (!lease) return null;

  const formatCurrency = (amount?: string | number | null) => {
    const num = typeof amount === 'string' ? parseFloat(amount) : amount;
    if (num == null || isNaN(num as number)) return '$0.00';
    return `$${(num as number).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
  };

  const getStatusColor = (status?: string) => {
    switch (status?.toUpperCase()) {
      case 'ACTIVE':
        return 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-300';
      case 'PENDING':
        return 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-300';
      case 'EXPIRED':
        return 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-300';
      case 'TERMINATED':
        return 'bg-gray-100 text-gray-800 dark:bg-gray-900/30 dark:text-gray-300';
      default:
        return 'bg-gray-100 text-gray-800 dark:bg-gray-900/30 dark:text-gray-300';
    }
  };

  const calculateLeaseDuration = () => {
    if (!lease.start_date || !lease.end_date) return 'N/A';
    const start = new Date(lease.start_date);
    const end = new Date(lease.end_date);
    const months = Math.round((end.getTime() - start.getTime()) / (1000 * 60 * 60 * 24 * 30));
    return `${months} month${months !== 1 ? 's' : ''}`;
  };

  const getTenantDisplayName = () => {
    if (tenantName) return tenantName;
    if (!lease.tenant) return 'N/A';
    return lease.tenant.full_name ||
           (lease.tenant.first_name && lease.tenant.last_name
            ? `${lease.tenant.first_name} ${lease.tenant.last_name}`
            : 'N/A');
  };

  const getDaySuffix = (day: number): string => {
    if (day >= 11 && day <= 13) return 'th';
    switch (day % 10) {
      case 1: return 'st';
      case 2: return 'nd';
      case 3: return 'rd';
      default: return 'th';
    }
  };

  return (
    <AnimatePresence>
      {isOpen && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          className="fixed inset-0 bg-black bg-opacity-50 dark:bg-opacity-70 backdrop-blur-sm z-[9999] flex items-center justify-center p-4"
          onClick={onClose}
        >
          <motion.div
            initial={{ scale: 0.95, opacity: 0 }}
            animate={{ scale: 1, opacity: 1 }}
            exit={{ scale: 0.95, opacity: 0 }}
            transition={{ type: 'spring', damping: 25, stiffness: 400 }}
            className="relative w-full max-w-lg bg-white dark:bg-gray-800 rounded-xl shadow-xl overflow-hidden"
            onClick={(e) => e.stopPropagation()}
          >
            {/* Header */}
            <div className="flex items-center justify-between px-5 py-4 border-b border-gray-200 dark:border-gray-700">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 bg-blue-100 dark:bg-blue-900/30 rounded-lg flex items-center justify-center">
                  <svg className="w-5 h-5 text-blue-600 dark:text-blue-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                  </svg>
                </div>
                <div>
                  <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100">Lease Details</h2>
                  <div className="flex items-center gap-2 mt-0.5">
                    <span className="text-xs text-gray-500 dark:text-gray-400">#{lease.id}</span>
                    <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${getStatusColor(lease.status)}`}>
                      {lease.status?.toUpperCase() || 'DRAFT'}
                    </span>
                  </div>
                </div>
              </div>
              <button
                onClick={onClose}
                className="p-2 text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg transition-colors"
              >
                <XIcon className="h-5 w-5" />
              </button>
            </div>

            {/* Content */}
            <div className="p-5 space-y-4">
              {/* Property & Tenant Row */}
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wide">Property</label>
                  <p className="text-sm font-medium text-gray-900 dark:text-gray-100 mt-1">
                    {lease.property?.name || 'N/A'}
                  </p>
                  {lease.unit && (
                    <p className="text-xs text-gray-500 dark:text-gray-400">Unit {lease.unit.name}</p>
                  )}
                </div>
                <div>
                  <label className="text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wide">Tenant</label>
                  <p className="text-sm font-medium text-gray-900 dark:text-gray-100 mt-1">
                    {getTenantDisplayName()}
                  </p>
                  {lease.tenant?.email && (
                    <p className="text-xs text-gray-500 dark:text-gray-400">{lease.tenant.email}</p>
                  )}
                </div>
              </div>

              {/* Lease Period */}
              <div className="bg-gray-50 dark:bg-gray-700/50 rounded-lg p-3">
                <label className="text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wide">Lease Period</label>
                <div className="flex items-center justify-between mt-2">
                  <div>
                    <p className="text-sm font-medium text-gray-900 dark:text-gray-100">
                      {formatDateForDisplay(lease.start_date)} — {formatDateForDisplay(lease.end_date)}
                    </p>
                    <p className="text-xs text-gray-500 dark:text-gray-400">{calculateLeaseDuration()}</p>
                  </div>
                  {(lease.auto_renew || lease.is_renewable) && (
                    <span className={`px-2 py-1 rounded text-xs font-medium ${
                      lease.auto_renew
                        ? 'bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300'
                        : 'bg-gray-100 dark:bg-gray-600 text-gray-600 dark:text-gray-300'
                    }`}>
                      {lease.auto_renew ? 'Auto-Renew' : 'Renewable'}
                    </span>
                  )}
                </div>
              </div>

              {/* Financial Terms */}
              <div className="grid grid-cols-3 gap-3">
                <div className="bg-green-50 dark:bg-green-900/20 rounded-lg p-3 text-center">
                  <p className="text-xs text-gray-500 dark:text-gray-400">Monthly Rent</p>
                  <p className="text-lg font-semibold text-green-600 dark:text-green-400 mt-1">
                    {formatCurrency(lease.monthly_rent)}
                  </p>
                  {lease.rent_due_day && (
                    <p className="text-xs text-gray-500 dark:text-gray-400">
                      Due {lease.rent_due_day}{getDaySuffix(lease.rent_due_day)}
                    </p>
                  )}
                </div>
                <div className="bg-gray-50 dark:bg-gray-700/50 rounded-lg p-3 text-center">
                  <p className="text-xs text-gray-500 dark:text-gray-400">Security Deposit</p>
                  <p className="text-lg font-semibold text-gray-900 dark:text-gray-100 mt-1">
                    {formatCurrency(lease.security_deposit)}
                  </p>
                  <p className="text-xs text-gray-500 dark:text-gray-400">Held</p>
                </div>
                <div className="bg-gray-50 dark:bg-gray-700/50 rounded-lg p-3 text-center">
                  <p className="text-xs text-gray-500 dark:text-gray-400">Late Fee</p>
                  {lease.late_fee_amount ? (
                    <>
                      <p className="text-lg font-semibold text-amber-600 dark:text-amber-400 mt-1">
                        {formatCurrency(lease.late_fee_amount)}
                      </p>
                      <p className="text-xs text-gray-500 dark:text-gray-400">
                        {lease.late_fee_after_days ? `After ${lease.late_fee_after_days}d` : ''}
                      </p>
                    </>
                  ) : (
                    <p className="text-sm text-gray-400 dark:text-gray-500 mt-2">None set</p>
                  )}
                </div>
              </div>

              {/* Special Terms */}
              {lease.special_terms && (
                <div className="bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-800 rounded-lg p-3">
                  <label className="text-xs font-medium text-amber-700 dark:text-amber-300 uppercase tracking-wide flex items-center gap-1">
                    <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                    </svg>
                    Special Terms
                  </label>
                  <p className="text-sm text-amber-800 dark:text-amber-200 mt-1">{lease.special_terms}</p>
                </div>
              )}
            </div>

            {/* Footer */}
            <div className="px-5 py-3 bg-gray-50 dark:bg-gray-900 border-t border-gray-200 dark:border-gray-700 flex justify-end">
              <button
                onClick={onClose}
                className="px-4 py-2 bg-gray-600 text-white text-sm font-medium rounded-lg hover:bg-gray-700 transition-colors"
              >
                Close
              </button>
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
};

export default ViewLeaseModal;
