import React from 'react';
import { formatDate } from '../../../../../utils/tenantUtils';

interface LeaseData {
  id?: number;
  property?: { name?: string };
  unit?: { name?: string };
  monthly_rent?: number | string;
  security_deposit?: number | string;
  start_date?: string;
  end_date?: string;
  rent_due_day?: number;
  late_fee_amount?: number | string | null;
  late_fee_after_days?: number | null;
  is_renewable?: boolean;
  auto_renew?: boolean;
  documents?: Array<{ id: number | string }>;
}

interface TenantData {
  property?: { name?: string };
  unit?: { name?: string };
}

interface CurrentLeaseCardProps {
  activeLeases: LeaseData[];
  tenant: TenantData;
  onViewLeaseInfo: (lease?: LeaseData) => void;
  onViewLeaseDocument: (lease: LeaseData) => void;
}

const getDaySuffix = (day: number): string => {
  if (day >= 11 && day <= 13) return 'th';
  switch (day % 10) {
    case 1: return 'st';
    case 2: return 'nd';
    case 3: return 'rd';
    default: return 'th';
  }
};

const formatCurrency = (value: number | string | undefined | null): string => {
  if (value === undefined || value === null) return 'N/A';
  const numValue = typeof value === 'string' ? parseFloat(value) : value;
  if (isNaN(numValue)) return 'N/A';
  return `$${numValue.toLocaleString('en-US', { minimumFractionDigits: 0, maximumFractionDigits: 0 })}`;
};

const calculateDaysUntilExpiry = (endDate: string | undefined): number | null => {
  if (!endDate) return null;
  // Parse date as UTC midnight to avoid timezone-related off-by-one errors
  const end = new Date(endDate + 'T00:00:00Z');
  const today = new Date();
  // Get today's date at UTC midnight for consistent comparison
  const todayUTC = new Date(Date.UTC(today.getUTCFullYear(), today.getUTCMonth(), today.getUTCDate()));
  const diffTime = end.getTime() - todayUTC.getTime();
  return Math.ceil(diffTime / (1000 * 60 * 60 * 24));
};

const getExpiryStatus = (daysUntilExpiry: number | null): { label: string; color: string; bgColor: string; urgent: boolean } => {
  if (daysUntilExpiry === null) {
    return { label: 'Active', color: 'text-green-700 dark:text-green-300', bgColor: 'bg-green-100 dark:bg-green-900/30', urgent: false };
  }
  if (daysUntilExpiry < 0) {
    return { label: 'Expired', color: 'text-red-700 dark:text-red-300', bgColor: 'bg-red-100 dark:bg-red-900/30', urgent: true };
  }
  if (daysUntilExpiry <= 30) {
    return { label: `${daysUntilExpiry}d left`, color: 'text-red-700 dark:text-red-300', bgColor: 'bg-red-100 dark:bg-red-900/30', urgent: true };
  }
  if (daysUntilExpiry <= 60) {
    return { label: `${daysUntilExpiry}d left`, color: 'text-amber-700 dark:text-amber-300', bgColor: 'bg-amber-100 dark:bg-amber-900/30', urgent: false };
  }
  if (daysUntilExpiry <= 90) {
    return { label: `${daysUntilExpiry}d left`, color: 'text-yellow-700 dark:text-yellow-300', bgColor: 'bg-yellow-100 dark:bg-yellow-900/30', urgent: false };
  }
  return { label: 'Active', color: 'text-green-700 dark:text-green-300', bgColor: 'bg-green-100 dark:bg-green-900/30', urgent: false };
};

const CurrentLeaseCard: React.FC<CurrentLeaseCardProps> = ({ activeLeases, tenant, onViewLeaseInfo, onViewLeaseDocument }) => {
  // MULTI-UNIT SUPPORT: Handle display for 0, 1, or multiple active leases
  const hasLeases = activeLeases.length > 0;
  const singleLease = activeLeases.length === 1 ? activeLeases[0] : null;
  
  // For single lease, calculate expiry status
  const daysUntilExpiry = singleLease ? calculateDaysUntilExpiry(singleLease.end_date) : null;
  const expiryStatus = getExpiryStatus(daysUntilExpiry);

  return (
    <div className="bg-white dark:bg-gray-800 rounded-lg shadow-sm border border-gray-200 dark:border-gray-700 p-4 h-[320px] flex flex-col">
      {/* Header */}
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-md font-semibold text-gray-900 dark:text-gray-100 flex items-center gap-2">
          <svg className="w-6 h-6 text-blue-600 dark:text-blue-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
          </svg>
          {activeLeases.length > 1 ? `Active Leases (${activeLeases.length})` : 'Current Lease'}
        </h3>
        {singleLease && (
          <span className={`inline-flex items-center px-2 py-0.5 rounded-md text-xs font-medium ${expiryStatus.bgColor} ${expiryStatus.color}`}>
            {expiryStatus.urgent && (
              <svg className="w-3 h-3 mr-1" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
            )}
            {expiryStatus.label}
          </span>
        )}
      </div>

      {hasLeases ? (
        singleLease ? (
          // Single lease display (original detailed view)
          <div className="flex-1 flex flex-col">
            {/* Location Row */}
            <div className="flex items-center gap-2 mt-6 mb-4 text-sm text-gray-600 dark:text-gray-300">
              <svg className="w-4 h-4 text-gray-400 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17.657 16.657L13.414 20.9a1.998 1.998 0 01-2.827 0l-4.244-4.243a8 8 0 1111.314 0z" />
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 11a3 3 0 11-6 0 3 3 0 016 0z" />
              </svg>
              <span className="truncate">
                {singleLease.property?.name || tenant.property?.name || 'Property'}
                {(singleLease.unit?.name || tenant.unit?.name) && ` • Unit ${singleLease.unit?.name || tenant.unit?.name}`}
              </span>
            </div>

            {/* Financial Grid */}
            <div className="grid grid-cols-2 gap-3 mb-3">
              <div className="bg-gray-50 dark:bg-gray-700/50 rounded-lg p-2.5">
                <div className="text-xs text-gray-500 dark:text-gray-400 mb-0.5">Monthly Rent</div>
                <div className="text-base font-semibold text-gray-900 dark:text-gray-100">
                  {formatCurrency(singleLease.monthly_rent)}
                </div>
                <div className="text-xs text-gray-500 dark:text-gray-400">
                  Due {singleLease.rent_due_day ? `${singleLease.rent_due_day}${getDaySuffix(singleLease.rent_due_day)}` : '1st'}
                </div>
              </div>
              <div className="bg-gray-50 dark:bg-gray-700/50 rounded-lg p-2.5">
                <div className="text-xs text-gray-500 dark:text-gray-400 mb-0.5">Security Deposit</div>
                <div className="text-base font-semibold text-gray-900 dark:text-gray-100">
                  {formatCurrency(singleLease.security_deposit)}
                </div>
                <div className="text-xs text-gray-500 dark:text-gray-400">Held</div>
              </div>
            </div>

            {/* Term & Policy Row */}
            <div className="grid grid-cols-2 gap-3">
              <div>
                <div className="flex items-center gap-1.5 mb-0.5">
                  <span className="text-xs text-gray-500 dark:text-gray-400">Lease Term</span>
                  {singleLease.auto_renew ? (
                    <span className="inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded text-[10px] font-medium bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300">
                      <svg className="w-2.5 h-2.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                      </svg>
                      Auto
                    </span>
                  ) : singleLease.is_renewable ? (
                    <span className="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-medium bg-gray-100 dark:bg-gray-700 text-gray-500 dark:text-gray-400">
                      Renewable
                    </span>
                  ) : (
                    <span className="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-medium bg-gray-100 dark:bg-gray-700 text-gray-500 dark:text-gray-400">
                      Fixed
                    </span>
                  )}
                </div>
                <div className="text-sm font-medium text-gray-900 dark:text-gray-100">
                  {formatDate(singleLease.start_date)} - {formatDate(singleLease.end_date)}
                </div>
              </div>
              <div>
                <div className="text-xs text-gray-500 dark:text-gray-400 mb-0.5">Late Fee</div>
                <div className="text-sm font-medium text-gray-900 dark:text-gray-100">
                  {singleLease.late_fee_amount ? (
                    <>
                      {formatCurrency(singleLease.late_fee_amount)}
                      {singleLease.late_fee_after_days && (
                        <span className="text-xs text-gray-500 dark:text-gray-400 ml-1">
                          after {singleLease.late_fee_after_days}d
                        </span>
                      )}
                    </>
                  ) : (
                    <span className="text-gray-400 dark:text-gray-500">None set</span>
                  )}
                </div>
              </div>
            </div>

            {/* Action Buttons */}
            <div className="mt-auto pt-3 flex gap-2">
              <button
                onClick={() => onViewLeaseInfo(singleLease)}
                className="inline-flex items-center justify-center gap-1.5 px-3 py-1.5 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-lg text-gray-700 dark:text-gray-200 text-sm font-medium hover:bg-gray-50 dark:hover:bg-gray-600 transition-colors flex-1"
              >
                <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
                Details
              </button>
              <button
                onClick={() => onViewLeaseDocument(singleLease)}
                className="inline-flex items-center justify-center gap-1.5 px-3 py-1.5 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-lg text-gray-700 dark:text-gray-200 text-sm font-medium hover:bg-gray-50 dark:hover:bg-gray-600 transition-colors flex-1"
              >
                <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                </svg>
                Document
              </button>
            </div>
          </div>
        ) : (
          // Multiple leases display (compact list view with individual buttons)
          <div className="flex-1 flex flex-col overflow-hidden">
            <div className="flex-1 overflow-y-auto space-y-2.5 pr-1">
              {activeLeases.map((lease, index) => {
                const days = calculateDaysUntilExpiry(lease.end_date);
                const status = getExpiryStatus(days);
                const hasDocument = lease.documents && lease.documents.length > 0;
                
                return (
                  <div 
                    key={lease.id || index}
                    className="bg-gray-50 dark:bg-gray-700/50 rounded-lg p-2.5 border border-gray-200 dark:border-gray-600"
                  >
                    {/* Unit and Status */}
                    <div className="flex items-start justify-between gap-2 mb-2">
                      <div className="flex items-center gap-1.5 min-w-0 flex-1">
                        <svg className="w-3.5 h-3.5 text-gray-400 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5M9 7h1m-1 4h1m4-4h1m-1 4h1m-5 10v-5a1 1 0 011-1h2a1 1 0 011 1v5m-4 0h4" />
                        </svg>
                        <span className="font-medium text-sm text-gray-900 dark:text-gray-100 truncate">
                          {lease.unit?.name || 'Unit'}
                        </span>
                      </div>
                      <span className={`inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-medium flex-shrink-0 ${status.bgColor} ${status.color}`}>
                        {status.label}
                      </span>
                    </div>

                    {/* Rent and Term */}
                    <div className="grid grid-cols-2 gap-2 text-xs mb-2">
                      <div>
                        <span className="text-gray-500 dark:text-gray-400">Rent: </span>
                        <span className="font-semibold text-gray-900 dark:text-gray-100">{formatCurrency(lease.monthly_rent)}</span>
                      </div>
                      <div className="text-right">
                        <span className="text-gray-500 dark:text-gray-400">Due: </span>
                        <span className="text-gray-900 dark:text-gray-100">
                          {lease.rent_due_day ? `${lease.rent_due_day}${getDaySuffix(lease.rent_due_day)}` : '1st'}
                        </span>
                      </div>
                    </div>
                    <div className="text-xs text-gray-500 dark:text-gray-400 mb-2">
                      {formatDate(lease.start_date)} - {formatDate(lease.end_date)}
                    </div>

                    {/* Individual Lease Action Buttons */}
                    <div className="flex gap-1.5">
                      <button
                        onClick={() => onViewLeaseInfo(lease)}
                        className="inline-flex items-center justify-center gap-1 px-2 py-1 bg-white dark:bg-gray-600 border border-gray-300 dark:border-gray-500 rounded text-gray-700 dark:text-gray-200 text-xs font-medium hover:bg-gray-50 dark:hover:bg-gray-500 transition-colors flex-1"
                      >
                        <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                        </svg>
                        Details
                      </button>
                      <button
                        onClick={() => onViewLeaseDocument(lease)}
                        disabled={!hasDocument}
                        className={`inline-flex items-center justify-center gap-1 px-2 py-1 border rounded text-xs font-medium transition-colors flex-1 ${
                          hasDocument
                            ? 'bg-white dark:bg-gray-600 border-gray-300 dark:border-gray-500 text-gray-700 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-gray-500'
                            : 'bg-gray-100 dark:bg-gray-700 border-gray-200 dark:border-gray-600 text-gray-400 dark:text-gray-500 cursor-not-allowed'
                        }`}
                      >
                        <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                        </svg>
                        Document
                      </button>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        )
      ) : (
        <div className="flex-1 flex flex-col items-center justify-center">
          <div className="w-12 h-12 bg-gray-100 dark:bg-gray-700 rounded-lg flex items-center justify-center mb-3">
            <svg className="w-6 h-6 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
            </svg>
          </div>
          <p className="text-sm font-medium text-gray-600 dark:text-gray-300 mb-1">No Active Lease</p>
          <p className="text-xs text-gray-500 dark:text-gray-400">Create a lease from the Leases tab</p>
        </div>
      )}
    </div>
  );
};

export default CurrentLeaseCard;
