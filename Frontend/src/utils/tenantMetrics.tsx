/**
 * Tenant Metrics Calculation Utilities
 * 
 * Provides robust calculations for tenant financial and operational metrics
 * based on lease terms, payment history, and maintenance data.
 * 
 * Key Principle: Payments are lease-based, NOT invoice-based.
 * Invoices are optional and used for miscellaneous charges.
 */

import { EnrichedTenant, Lease, Payment, MaintenanceStatus, RentPaymentTransaction } from '../types/tenant';

// ============================================================================
// TYPE DEFINITIONS
// ============================================================================

export interface PaymentPerformanceMetrics {
  rate: number | null;           // Percentage (0-100) or null if no data
  onTimeCount: number;           // Number of on-time payments
  totalCount: number;            // Total payments considered
  avgDaysEarly: number;          // Positive = early, negative = late, 0 = exact
  status: 'excellent' | 'good' | 'needs_attention' | 'no_data';
}

export interface OpenBalanceMetrics {
  totalBalance: number;          // Total outstanding balance
  overdueBalance: number;        // Amount that is past due
  rentBalance: number;           // Expected vs paid rent
  invoiceBalance: number;        // Unpaid invoices
  unpaidInvoiceCount: number;    // Number of unpaid invoices
  isOverdue: boolean;            // Whether any amount is overdue
  nextDueAmount: number | null;  // Next rent payment amount
  nextDueDate: Date | null;      // Next rent due date
}

export interface TicketResolutionMetrics {
  avgDays: number | null;        // Average days to resolve or null
  completedCount: number;        // Completed tickets
  totalCount: number;            // Total tickets
  pendingCount: number;          // Pending tickets
  status: 'excellent' | 'good' | 'needs_improvement' | 'no_data';
}

export interface MaintenanceTicketsMetrics {
  totalCount: number;            // Total tickets
  newCount: number;              // New tickets (not yet reviewed)
  pendingCount: number;          // Pending tickets (reviewed, work not started)
  inProgressCount: number;       // In Progress tickets
  scheduledCount: number;        // Scheduled tickets
  completedCount: number;        // Completed tickets
  cancelledCount: number;        // Cancelled tickets
  activeCount: number;           // All non-completed/cancelled tickets
  avgResolutionDays: number | null; // Average days to resolve completed tickets
  highPriorityCount: number;     // High priority active tickets
  status: 'excellent' | 'good' | 'needs_attention' | 'no_data';
}

export interface UpcomingEvent {
  id: string;
  type: 'rent' | 'lease_expiry' | 'invoice' | 'insurance' | 'maintenance';
  title: string;
  subtitle: string;
  date: Date;
  daysRemaining: number;
  amount?: number;
  urgency: 'critical' | 'high' | 'medium' | 'low';
  icon: 'money' | 'document' | 'alert' | 'tool' | 'shield';
  color: string;
  bgColor: string;
}

// ============================================================================
// HELPER FUNCTIONS
// ============================================================================

/**
 * Calculate days between two dates
 */
export const daysBetween = (date1: Date, date2: Date): number => {
  const diffTime = date2.getTime() - date1.getTime();
  return Math.ceil(diffTime / (1000 * 60 * 60 * 24));
};

/**
 * Get next occurrence of rent due day
 */
export const getNextRentDueDate = (rentDueDay: number): Date => {
  const today = new Date();
  const currentMonth = today.getMonth();
  const currentYear = today.getFullYear();
  const currentDay = today.getDate();
  
  // If due day hasn't passed this month, return this month's due date
  if (currentDay <= rentDueDay) {
    return new Date(currentYear, currentMonth, rentDueDay);
  }
  
  // Otherwise, return next month's due date
  return new Date(currentYear, currentMonth + 1, rentDueDay);
};

/**
 * Format days remaining as human-readable string
 */
export const formatDaysRemaining = (days: number): string => {
  if (days < 0) return `${Math.abs(days)}d overdue`;
  if (days === 0) return 'Today';
  if (days === 1) return '1 day';
  return `${days}d`;
};

/**
 * Check if payment was made on time based on lease terms
 */
const isPaymentOnTime = (payment: Payment, lease: Lease): boolean => {
  const paymentDate = new Date(payment.payment_date);
  const rentDueDay = lease.rent_due_day || 1;

  // Expected due date is rent_due_day of the payment's month
  const expectedDueDate = new Date(
    paymentDate.getFullYear(),
    paymentDate.getMonth(),
    rentDueDay
  );

  // On time = paid on or before due day
  return paymentDate <= expectedDueDate;
};

/**
 * Check if a rent payment transaction was made on time based on lease terms
 */
const isRentTransactionOnTime = (txn: RentPaymentTransaction, lease: Lease): boolean => {
  // Use succeeded_at if available, otherwise initiated_at
  const txnDate = new Date(txn.succeeded_at || txn.initiated_at);
  const rentDueDay = lease.rent_due_day || 1;

  // Expected due date is rent_due_day of the transaction's month
  const expectedDueDate = new Date(
    txnDate.getFullYear(),
    txnDate.getMonth(),
    rentDueDay
  );

  // On time = paid on or before due day
  return txnDate <= expectedDueDate;
};

/**
 * Calculate months elapsed in a lease
 *
 * Note: Uses UTC dates to avoid timezone issues where "2025-12-01" parsed as
 * a Date becomes Nov 30 in local time (PST/EST).
 */
const calculateMonthsElapsed = (leaseStart: Date, currentDate: Date): number => {
  // Use UTC values consistently to avoid timezone conversion issues
  const startYear = leaseStart.getUTCFullYear();
  const startMonth = leaseStart.getUTCMonth();
  const currentYear = currentDate.getUTCFullYear();
  const currentMonth = currentDate.getUTCMonth();

  const yearDiff = currentYear - startYear;
  const monthDiff = currentMonth - startMonth;
  return Math.max(1, yearDiff * 12 + monthDiff + 1); // +1 to include current month, minimum 1
};

/**
 * Calculate total NET amount paid in the current month (after refunds)
 * Uses rent_payment_transactions if available, else legacy payments
 */
/**
 * Calculate total payments made this month
 * 
 * MULTI-UNIT SUPPORT: Aggregates payments across ALL active leases
 */
export const calculatePaidThisMonth = (
  tenant: EnrichedTenant,
  activeLeases: Lease[]
): number => {
  const today = new Date();
  const startOfMonth = new Date(today.getFullYear(), today.getMonth(), 1);
  const endOfMonth = new Date(today.getFullYear(), today.getMonth() + 1, 0, 23, 59, 59);

  let paidThisMonth = 0;

  // Get all lease IDs
  const leaseIds = new Set(activeLeases.map(lease => lease.id));

  // Check for new Stripe Connect rent payment transactions
  // Include succeeded transactions AND those that were refunded (to show net)
  const rentTransactions = tenant.rent_payment_transactions?.filter(txn => {
    if (!leaseIds.has(txn.lease_id)) return false;
    // Include succeeded, partially_refunded, and refunded transactions
    if (!['succeeded', 'partially_refunded', 'refunded'].includes(txn.status)) return false;
    const txnDate = new Date(txn.succeeded_at || txn.initiated_at);
    return txnDate >= startOfMonth && txnDate <= endOfMonth;
  }) || [];

  if (rentTransactions.length > 0) {
    // Use net_amount which accounts for refunds
    paidThisMonth = rentTransactions.reduce((sum, txn) => sum + Number(txn.net_amount), 0);
  } else {
    // Fallback to legacy payments
    const legacyPayments = tenant.payments?.filter(p => {
      if (!p.lease_id || !leaseIds.has(p.lease_id)) return false;
      if (p.status !== 'Paid') return false;
      const paymentDate = new Date(p.payment_date);
      return paymentDate >= startOfMonth && paymentDate <= endOfMonth;
    }) || [];

    paidThisMonth = legacyPayments.reduce((sum, p) => sum + Number(p.amount), 0);
  }

  return paidThisMonth;
};

/**
 * Get the most recent payment info for display
 * Uses rent_payment_transactions if available, else legacy payments
 * Shows net amount (after any refunds)
 */
export const getLastPaymentInfo = (
  tenant: EnrichedTenant,
  activeLease: Lease | undefined
): { amount: number; date: string; method?: string } | null => {
  // Check for new Stripe Connect rent payment transactions first
  // Include succeeded, partially_refunded, and refunded transactions
  const rentTransactions = tenant.rent_payment_transactions
    ?.filter(txn => {
      if (activeLease && txn.lease_id !== activeLease.id) return false;
      return ['succeeded', 'partially_refunded', 'refunded'].includes(txn.status);
    })
    .sort((a, b) => new Date(b.succeeded_at || b.initiated_at).getTime() - new Date(a.succeeded_at || a.initiated_at).getTime()) || [];

  if (rentTransactions.length > 0) {
    const lastTxn = rentTransactions[0];
    return {
      // Show net amount after refunds
      amount: Number(lastTxn.net_amount),
      date: lastTxn.succeeded_at || lastTxn.initiated_at,
      method: lastTxn.payment_method_type === 'acss_debit' ? 'Pre-Auth Debit' : lastTxn.payment_method_type === 'card' ? 'Card' : lastTxn.payment_method_type || undefined
    };
  }

  // Fallback to legacy payments
  const legacyPayments = tenant.payments
    ?.filter(p => {
      if (activeLease && p.lease_id !== activeLease.id) return false;
      return p.status === 'Paid';
    })
    .sort((a, b) => new Date(b.payment_date).getTime() - new Date(a.payment_date).getTime()) || [];

  if (legacyPayments.length > 0) {
    const lastPayment = legacyPayments[0];
    return {
      amount: Number(lastPayment.amount),
      date: lastPayment.payment_date,
      method: lastPayment.payment_method || undefined
    };
  }

  return null;
};

// ============================================================================
// PAYMENT PERFORMANCE CALCULATION
// ============================================================================

/**
 * Calculate payment performance metrics based on lease terms and payment history
 *
 * MULTI-UNIT SUPPORT: Aggregates performance across ALL active leases
 * 
 * Logic:
 * - Uses rent_payment_transactions if available (new Stripe Connect system)
 * - Falls back to legacy payments table for backward compatibility
 * - Only considers succeeded payments during active lease periods
 * - Compares payment date with expected rent_due_day for each lease
 * - Returns percentage of on-time payments across all leases
 */
export const calculatePaymentPerformance = (
  tenant: EnrichedTenant,
  activeLeases: Lease[]
): PaymentPerformanceMetrics => {
  // No active leases = no performance data
  if (!activeLeases || activeLeases.length === 0) {
    return {
      rate: null,
      onTimeCount: 0,
      totalCount: 0,
      avgDaysEarly: 0,
      status: 'no_data'
    };
  }

  // Get all lease IDs for filtering
  const leaseIds = new Set(activeLeases.map(lease => lease.id));

  // First, check for new Stripe Connect rent payment transactions
  const rentTransactions = tenant.rent_payment_transactions?.filter(txn => {
    // Only include transactions for active leases
    if (!leaseIds.has(txn.lease_id)) return false;
    // Only include succeeded transactions (including refunded as they still count as payments made)
    if (!['succeeded', 'partially_refunded', 'refunded'].includes(txn.status)) return false;
    // Exclude fully refunded transactions with zero net value to avoid distorting metrics
    if (Number(txn.net_amount) <= 0) return false;

    // Check if within any active lease period
    const txnDate = new Date(txn.succeeded_at || txn.initiated_at);
    const lease = activeLeases.find(l => l.id === txn.lease_id);
    if (!lease) return false;

    const leaseStart = new Date(lease.start_date);
    const leaseEnd = new Date(lease.end_date);
    return txnDate >= leaseStart && txnDate <= leaseEnd;
  }) || [];

  // If we have rent transactions, use those
  if (rentTransactions.length > 0) {
    const onTimeTransactions = rentTransactions.filter(txn => {
      const lease = activeLeases.find(l => l.id === txn.lease_id);
      return lease ? isRentTransactionOnTime(txn, lease) : false;
    });

    const rate = (onTimeTransactions.length / rentTransactions.length) * 100;

    // Calculate average days early/late
    let totalDaysOffset = 0;
    rentTransactions.forEach(txn => {
      const lease = activeLeases.find(l => l.id === txn.lease_id);
      if (!lease) return;

      const txnDate = new Date(txn.succeeded_at || txn.initiated_at);
      const rentDueDay = lease.rent_due_day || 1;
      const expectedDueDate = new Date(
        txnDate.getFullYear(),
        txnDate.getMonth(),
        rentDueDay
      );
      const daysOffset = daysBetween(txnDate, expectedDueDate);
      totalDaysOffset += daysOffset;
    });

    const avgDaysEarly = Math.round(totalDaysOffset / rentTransactions.length);

    // Determine status
    let status: PaymentPerformanceMetrics['status'];
    if (rate >= 95) {
      status = 'excellent';
    } else if (rate >= 80) {
      status = 'good';
    } else {
      status = 'needs_attention';
    }

    return {
      rate: Math.round(rate),
      onTimeCount: onTimeTransactions.length,
      totalCount: rentTransactions.length,
      avgDaysEarly,
      status
    };
  }

  // Fallback to legacy payments table
  if (!tenant.payments || tenant.payments.length === 0) {
    return {
      rate: null,
      onTimeCount: 0,
      totalCount: 0,
      avgDaysEarly: 0,
      status: 'no_data'
    };
  }

  // Filter to only completed payments within active lease periods
  const relevantPayments = tenant.payments.filter(payment => {
    if (!payment.lease_id || !leaseIds.has(payment.lease_id)) return false;
    if (payment.status !== 'Paid') return false;

    const lease = activeLeases.find(l => l.id === payment.lease_id);
    if (!lease) return false;

    const paymentDate = new Date(payment.payment_date);
    const leaseStart = new Date(lease.start_date);
    const leaseEnd = new Date(lease.end_date);
    return paymentDate >= leaseStart && paymentDate <= leaseEnd;
  });

  if (relevantPayments.length === 0) {
    return {
      rate: null,
      onTimeCount: 0,
      totalCount: 0,
      avgDaysEarly: 0,
      status: 'no_data'
    };
  }

  // Calculate on-time payments
  const onTimePayments = relevantPayments.filter(payment => {
    const lease = activeLeases.find(l => l.id === payment.lease_id);
    return lease ? isPaymentOnTime(payment, lease) : false;
  });

  const rate = (onTimePayments.length / relevantPayments.length) * 100;

  // Calculate average days early/late
  let totalDaysOffset = 0;
  relevantPayments.forEach(payment => {
    const lease = activeLeases.find(l => l.id === payment.lease_id);
    if (!lease) return;

    const paymentDate = new Date(payment.payment_date);
    const rentDueDay = lease.rent_due_day || 1;
    const expectedDueDate = new Date(
      paymentDate.getFullYear(),
      paymentDate.getMonth(),
      rentDueDay
    );

    // Positive = early, negative = late
    const daysOffset = daysBetween(paymentDate, expectedDueDate);
    totalDaysOffset += daysOffset;
  });

  const avgDaysEarly = relevantPayments.length > 0
    ? Math.round(totalDaysOffset / relevantPayments.length)
    : 0;

  // Determine status
  let status: PaymentPerformanceMetrics['status'];
  if (rate >= 95) {
    status = 'excellent';
  } else if (rate >= 80) {
    status = 'good';
  } else {
    status = 'needs_attention';
  }

  return {
    rate: Math.round(rate),
    onTimeCount: onTimePayments.length,
    totalCount: relevantPayments.length,
    avgDaysEarly,
    status
  };
};

// ============================================================================
// OPEN BALANCE CALCULATION
// ============================================================================

/**
 * Calculate open balance from lease expectations and payment history
 *
 * MULTI-UNIT SUPPORT: Aggregates across ALL active leases
 * 
 * Logic:
 * - Calculate expected rent based on months elapsed for EACH active lease
 * - Sum actual payments made (from rent_payment_transactions if available, else legacy payments)
 * - Add any unpaid invoices (miscellaneous charges)
 * - Check for overdue amounts across all leases
 *
 * Priority: Uses new Stripe Connect rent_payment_transactions if available,
 * falls back to legacy payments table for backward compatibility.
 */
export const calculateOpenBalance = (
  tenant: EnrichedTenant,
  activeLeases: Lease[]
): OpenBalanceMetrics => {
  let rentBalance = 0;
  let invoiceBalance = 0;
  let overdueBalance = 0;
  let nextDueAmount: number = 0;
  let nextDueDate: Date | null = null;
  const today = new Date();

  // PART 1: Calculate rent balance (expected vs paid) - AGGREGATE ACROSS ALL ACTIVE LEASES
  if (activeLeases && activeLeases.length > 0) {
    activeLeases.forEach(activeLease => {
      const leaseStart = new Date(activeLease.start_date);
      const leaseEnd = new Date(activeLease.end_date);
      const currentDate = today > leaseEnd ? leaseEnd : today;

      // Calculate expected rent based on months elapsed
      const monthsElapsed = calculateMonthsElapsed(leaseStart, currentDate);
      const monthlyRent = Number(activeLease.monthly_rent);
      const expectedRent = monthsElapsed * monthlyRent;

      // Calculate NET paid rent (after refunds) - prefer rent_payment_transactions (new system), fallback to payments (legacy)
      let paidRent = 0;

      // First, check for new Stripe Connect rent payment transactions
      // Include succeeded, partially_refunded, and refunded transactions to get net amounts
      const rentTransactions = tenant.rent_payment_transactions?.filter(
        txn => txn.lease_id === activeLease.id &&
               ['succeeded', 'partially_refunded', 'refunded'].includes(txn.status)
      ) || [];

      if (rentTransactions.length > 0) {
        // Use net_amount which accounts for refunds (in dollars)
        paidRent = rentTransactions.reduce((sum, txn) => sum + Number(txn.net_amount), 0);
      } else {
        // Fallback to legacy payments table
        paidRent = tenant.payments
          ?.filter(p => p.lease_id === activeLease.id && p.status === 'Paid')
          .reduce((sum, p) => sum + Number(p.amount), 0) || 0;
      }

      const leaseBalance = Math.max(0, expectedRent - paidRent);
      rentBalance += leaseBalance;

      // Aggregate monthly rent for next due amount (sum of all active lease rents)
      nextDueAmount += monthlyRent;

      // Check if current month's rent is overdue for this lease
      const rentDueDay = activeLease.rent_due_day || 1;
      const dueDateThisMonth = new Date(today.getFullYear(), today.getMonth(), rentDueDay);

      if (today > dueDateThisMonth && leaseBalance >= monthlyRent) {
        overdueBalance += monthlyRent;
      }

      // Use earliest next due date among all leases (or most common rent_due_day)
      const leaseDueDate = getNextRentDueDate(rentDueDay);
      if (!nextDueDate || leaseDueDate < nextDueDate) {
        nextDueDate = leaseDueDate;
      }
    });
  }

  // PART 2: Add unpaid invoices (miscellaneous charges)
  if (tenant.invoices && tenant.invoices.length > 0) {
    const unpaidInvoices = tenant.invoices.filter(
      inv => inv.status !== 'Paid' && inv.status !== 'Cancelled'
    );

    unpaidInvoices.forEach(invoice => {
      const invoiceAmount = Number(invoice.amount);
      invoiceBalance += invoiceAmount;

      // Check if invoice is overdue
      const dueDate = new Date(invoice.due_date);
      if (today > dueDate) {
        overdueBalance += invoiceAmount;
      }
    });
  }

  const totalBalance = rentBalance + invoiceBalance;

  return {
    totalBalance,
    overdueBalance,
    rentBalance,
    invoiceBalance,
    unpaidInvoiceCount: tenant.invoices?.filter(
      inv => inv.status !== 'Paid' && inv.status !== 'Cancelled'
    ).length || 0,
    isOverdue: overdueBalance > 0,
    nextDueAmount,
    nextDueDate
  };
};

// ============================================================================
// TICKET RESOLUTION CALCULATION
// ============================================================================

/**
 * Calculate average maintenance ticket resolution time
 * 
 * Logic:
 * - Only considers completed tickets with completion dates
 * - Calculates days between request_date and completed_date
 * - Returns average across all completed tickets
 */
export const calculateTicketResolution = (
  tenant: EnrichedTenant
): TicketResolutionMetrics => {
  if (!tenant.maintenance_requests || tenant.maintenance_requests.length === 0) {
    return {
      avgDays: null,
      completedCount: 0,
      totalCount: 0,
      pendingCount: 0,
      status: 'no_data'
    };
  }

  const completedRequests = tenant.maintenance_requests.filter(
    req => req.status === MaintenanceStatus.COMPLETED && req.completed_date
  );

  const totalCount = tenant.maintenance_requests.length;
  const pendingCount = tenant.maintenance_requests.filter(
    req => req.status === MaintenanceStatus.PENDING || req.status === MaintenanceStatus.IN_PROGRESS
  ).length;

  if (completedRequests.length === 0) {
    return {
      avgDays: null,
      completedCount: 0,
      totalCount,
      pendingCount,
      status: 'no_data'
    };
  }

  // Calculate resolution time for each completed request
  const resolutionTimes = completedRequests.map(req => {
    const requestDate = new Date(req.request_date);
    const completedDate = new Date(req.completed_date!);
    return daysBetween(requestDate, completedDate);
  });

  const avgDays = resolutionTimes.reduce((sum, days) => sum + days, 0) / resolutionTimes.length;
  const roundedAvg = Math.round(avgDays * 10) / 10; // Round to 1 decimal

  // Determine status based on average resolution time
  let status: TicketResolutionMetrics['status'];
  if (roundedAvg <= 3) {
    status = 'excellent';
  } else if (roundedAvg <= 7) {
    status = 'good';
  } else {
    status = 'needs_improvement';
  }

  return {
    avgDays: roundedAvg,
    completedCount: completedRequests.length,
    totalCount,
    pendingCount,
    status
  };
};

// ============================================================================
// COMPREHENSIVE MAINTENANCE TICKETS CALCULATION
// ============================================================================

/**
 * Calculate comprehensive maintenance ticket metrics showing all statuses
 *
 * Logic:
 * - Counts tickets by each status
 * - Calculates active tickets (non-completed/cancelled)
 * - Tracks high priority items for attention indicators
 * - Computes average resolution time for completed tickets
 */
export const calculateMaintenanceTickets = (
  tenant: EnrichedTenant
): MaintenanceTicketsMetrics => {
  if (!tenant.maintenance_requests || tenant.maintenance_requests.length === 0) {
    return {
      totalCount: 0,
      newCount: 0,
      pendingCount: 0,
      inProgressCount: 0,
      scheduledCount: 0,
      completedCount: 0,
      cancelledCount: 0,
      activeCount: 0,
      avgResolutionDays: null,
      highPriorityCount: 0,
      status: 'no_data'
    };
  }

  const requests = tenant.maintenance_requests;

  // Count by status
  const newCount = requests.filter(req => req.status === MaintenanceStatus.NEW).length;
  const pendingCount = requests.filter(req => req.status === MaintenanceStatus.PENDING).length;
  const inProgressCount = requests.filter(req => req.status === MaintenanceStatus.IN_PROGRESS).length;
  const scheduledCount = requests.filter(req => req.status === MaintenanceStatus.SCHEDULED).length;
  const completedCount = requests.filter(req => req.status === MaintenanceStatus.COMPLETED).length;
  const cancelledCount = requests.filter(req => req.status === MaintenanceStatus.CANCELLED).length;

  const totalCount = requests.length;
  const activeCount = newCount + pendingCount + inProgressCount + scheduledCount;

  // High priority active tickets (non-completed/cancelled with HIGH priority)
  const highPriorityCount = requests.filter(req =>
    req.priority === 'High' &&
    req.status !== MaintenanceStatus.COMPLETED &&
    req.status !== MaintenanceStatus.CANCELLED
  ).length;

  // Calculate average resolution time for completed tickets
  let avgResolutionDays: number | null = null;
  const completedWithDates = requests.filter(
    req => req.status === MaintenanceStatus.COMPLETED && req.completed_date
  );

  if (completedWithDates.length > 0) {
    const resolutionTimes = completedWithDates.map(req => {
      const requestDate = new Date(req.request_date);
      const completedDate = new Date(req.completed_date!);
      return daysBetween(requestDate, completedDate);
    });
    const avgDays = resolutionTimes.reduce((sum, days) => sum + days, 0) / resolutionTimes.length;
    avgResolutionDays = Math.round(avgDays * 10) / 10;
  }

  // Determine status based on active tickets and high priority items
  let status: MaintenanceTicketsMetrics['status'];
  if (activeCount === 0) {
    status = 'excellent'; // All resolved
  } else if (highPriorityCount > 0 || activeCount > 3) {
    status = 'needs_attention'; // High priority items or many active tickets
  } else {
    status = 'good'; // Some active tickets but manageable
  }

  return {
    totalCount,
    newCount,
    pendingCount,
    inProgressCount,
    scheduledCount,
    completedCount,
    cancelledCount,
    activeCount,
    avgResolutionDays,
    highPriorityCount,
    status
  };
};

/**
 * Get color classes for maintenance tickets based on status
 */
export const getMaintenanceTicketsColor = (metrics: MaintenanceTicketsMetrics) => {
  switch (metrics.status) {
    case 'excellent':
      return {
        icon: 'text-green-600 dark:text-green-400',
        bg: 'bg-green-100 dark:bg-green-900/30',
        text: 'text-green-600 dark:text-green-400'
      };
    case 'good':
      return {
        icon: 'text-blue-600 dark:text-blue-400',
        bg: 'bg-blue-100 dark:bg-blue-900/30',
        text: 'text-blue-600 dark:text-blue-400'
      };
    case 'needs_attention':
      return {
        icon: 'text-orange-600 dark:text-orange-400',
        bg: 'bg-orange-100 dark:bg-orange-900/30',
        text: 'text-orange-600 dark:text-orange-400'
      };
    default:
      return {
        icon: 'text-gray-600 dark:text-gray-400',
        bg: 'bg-gray-100 dark:bg-gray-700',
        text: 'text-gray-600 dark:text-gray-400'
      };
  }
};

// ============================================================================
// UPCOMING EVENTS GENERATION
// ============================================================================

/**
 * Generate upcoming events for tenant (rent due, lease expiry, invoices, etc.)
 * 
 * Returns sorted list of events by urgency and date
 */
export const generateUpcomingEvents = (
  tenant: EnrichedTenant,
  activeLease: Lease | undefined,
  openBalance?: OpenBalanceMetrics
): UpcomingEvent[] => {
  const events: UpcomingEvent[] = [];
  const today = new Date();
  today.setHours(0, 0, 0, 0); // Reset time for accurate day comparison

  // 1. NEXT RENT DUE (if active lease exists and there's an outstanding balance)
  if (activeLease && openBalance && openBalance.rentBalance > 0) {
    const rentDueDay = activeLease.rent_due_day || 1;
    const nextDueDate = getNextRentDueDate(rentDueDay);
    const daysRemaining = daysBetween(today, nextDueDate);

    // Use the actual remaining balance, not the full monthly rent
    const amountDue = openBalance.rentBalance;
    const urgency = daysRemaining < 0 ? 'critical' : daysRemaining <= 7 ? 'high' : daysRemaining <= 14 ? 'medium' : 'low';

    events.push({
      id: 'rent-due',
      type: 'rent',
      title: 'Rent Due',
      subtitle: `$${amountDue.toLocaleString()} • ${formatDaysRemaining(daysRemaining)}`,
      date: nextDueDate,
      daysRemaining,
      amount: amountDue,
      urgency,
      icon: 'money',
      color: urgency === 'critical' ? 'text-red-600 dark:text-red-400' : 'text-blue-600 dark:text-blue-400',
      bgColor: urgency === 'critical' ? 'bg-red-100 dark:bg-red-900/30' : 'bg-blue-100 dark:bg-blue-900/30'
    });
  }

  // 2. OVERDUE BALANCE (if exists)
  if (openBalance && openBalance.overdueBalance > 0) {
    events.push({
      id: 'overdue-balance',
      type: 'invoice',
      title: 'Overdue Payment',
      subtitle: `$${openBalance.overdueBalance.toLocaleString()} past due`,
      date: today,
      daysRemaining: 0,
      amount: openBalance.overdueBalance,
      urgency: 'critical',
      icon: 'alert',
      color: 'text-red-600 dark:text-red-400',
      bgColor: 'bg-red-100 dark:bg-red-900/30'
    });
  }

  // 3. LEASE EXPIRY WARNING (if within 90 days)
  if (activeLease) {
    const leaseEnd = new Date(activeLease.end_date);
    const daysUntilExpiry = daysBetween(today, leaseEnd);

    if (daysUntilExpiry > 0 && daysUntilExpiry <= 90) {
      const urgency = daysUntilExpiry <= 30 ? 'critical' : daysUntilExpiry <= 60 ? 'high' : 'medium';
      
      events.push({
        id: 'lease-expiry',
        type: 'lease_expiry',
        title: 'Lease Expires',
        subtitle: `${formatDate(activeLease.end_date)} • ${formatDaysRemaining(daysUntilExpiry)}`,
        date: leaseEnd,
        daysRemaining: daysUntilExpiry,
        urgency,
        icon: 'document',
        color: urgency === 'critical' ? 'text-red-600 dark:text-red-400' : 'text-orange-600 dark:text-orange-400',
        bgColor: urgency === 'critical' ? 'bg-red-100 dark:bg-red-900/30' : 'bg-orange-100 dark:bg-orange-900/30'
      });
    }
  }

  // 4. UPCOMING UNPAID INVOICES (due within 30 days)
  if (tenant.invoices && tenant.invoices.length > 0) {
    const upcomingInvoices = tenant.invoices.filter(inv => {
      if (inv.status === 'Paid' || inv.status === 'Cancelled') return false;

      const dueDate = new Date(inv.due_date);
      const daysUntilDue = daysBetween(today, dueDate);
      
      return daysUntilDue >= -7 && daysUntilDue <= 30; // Include up to 7 days overdue
    });

    upcomingInvoices.forEach((inv) => {
      const dueDate = new Date(inv.due_date);
      const daysUntilDue = daysBetween(today, dueDate);
      const urgency = daysUntilDue < 0 ? 'critical' : daysUntilDue <= 7 ? 'high' : 'medium';

      events.push({
        id: `invoice-${inv.id}`,
        type: 'invoice',
        title: inv.description || `Invoice ${inv.invoice_number}`,
        subtitle: `$${Number(inv.amount).toLocaleString()} • ${formatDaysRemaining(daysUntilDue)}`,
        date: dueDate,
        daysRemaining: daysUntilDue,
        amount: Number(inv.amount),
        urgency,
        icon: 'alert',
        color: urgency === 'critical' ? 'text-red-600 dark:text-red-400' : 'text-orange-600 dark:text-orange-400',
        bgColor: urgency === 'critical' ? 'bg-red-100 dark:bg-red-900/30' : 'bg-orange-100 dark:bg-orange-900/30'
      });
    });
  }

  // 5. SCHEDULED MAINTENANCE (within next 30 days)
  if (tenant.maintenance_requests && tenant.maintenance_requests.length > 0) {
    const scheduledRequests = tenant.maintenance_requests.filter(req => {
      if (!req.scheduled_date || req.status === MaintenanceStatus.COMPLETED || req.status === MaintenanceStatus.CANCELLED) {
        return false;
      }

      const scheduledDate = new Date(req.scheduled_date);
      const daysUntil = daysBetween(today, scheduledDate);
      
      return daysUntil >= 0 && daysUntil <= 30;
    });

    scheduledRequests.forEach(req => {
      const scheduledDate = new Date(req.scheduled_date!);
      const daysUntil = daysBetween(today, scheduledDate);
      const urgency = daysUntil <= 3 ? 'high' : 'medium';

      events.push({
        id: `maintenance-${req.id}`,
        type: 'maintenance',
        title: 'Maintenance Scheduled',
        subtitle: `${req.issue_title} • ${formatDaysRemaining(daysUntil)}`,
        date: scheduledDate,
        daysRemaining: daysUntil,
        urgency,
        icon: 'tool',
        color: 'text-purple-600 dark:text-purple-400',
        bgColor: 'bg-purple-100 dark:bg-purple-900/30'
      });
    });
  }

  // Sort by urgency and days remaining
  const urgencyOrder = { critical: 0, high: 1, medium: 2, low: 3 };
  return events
    .sort((a, b) => {
      // Critical items first
      if (urgencyOrder[a.urgency] !== urgencyOrder[b.urgency]) {
        return urgencyOrder[a.urgency] - urgencyOrder[b.urgency];
      }
      // Then by days remaining (soonest first, overdue items have negative values)
      return a.daysRemaining - b.daysRemaining;
    })
    .slice(0, 5); // Limit to 5 most important events
};

// ============================================================================
// UI HELPER FUNCTIONS
// ============================================================================

/**
 * Get color classes for payment performance based on rate
 */
export const getPaymentPerformanceColor = (metrics: PaymentPerformanceMetrics) => {
  switch (metrics.status) {
    case 'excellent':
      return {
        icon: 'text-green-600 dark:text-green-400',
        bg: 'bg-green-100 dark:bg-green-900/30',
        text: 'text-green-600 dark:text-green-400'
      };
    case 'good':
      return {
        icon: 'text-yellow-600 dark:text-yellow-400',
        bg: 'bg-yellow-100 dark:bg-yellow-900/30',
        text: 'text-yellow-600 dark:text-yellow-400'
      };
    case 'needs_attention':
      return {
        icon: 'text-red-600 dark:text-red-400',
        bg: 'bg-red-100 dark:bg-red-900/30',
        text: 'text-red-600 dark:text-red-400'
      };
    default:
      return {
        icon: 'text-gray-600 dark:text-gray-400',
        bg: 'bg-gray-100 dark:bg-gray-700',
        text: 'text-gray-600 dark:text-gray-400'
      };
  }
};

/**
 * Get color classes for open balance based on amount
 */
export const getOpenBalanceColor = (balance: number, isOverdue: boolean, monthlyRent: number = 0) => {
  if (balance === 0) {
    return {
      icon: 'text-green-600 dark:text-green-400',
      bg: 'bg-green-100 dark:bg-green-900/30',
      text: 'text-green-600 dark:text-green-400'
    };
  }
  
  if (isOverdue) {
    return {
      icon: 'text-red-600 dark:text-red-400',
      bg: 'bg-red-100 dark:bg-red-900/30',
      text: 'text-red-600 dark:text-red-400'
    };
  }
  
  if (balance < monthlyRent) {
    return {
      icon: 'text-yellow-600 dark:text-yellow-400',
      bg: 'bg-yellow-100 dark:bg-yellow-900/30',
      text: 'text-yellow-600 dark:text-yellow-400'
    };
  }
  
  return {
    icon: 'text-orange-600 dark:text-orange-400',
    bg: 'bg-orange-100 dark:bg-orange-900/30',
    text: 'text-orange-600 dark:text-orange-400'
  };
};

/**
 * Get color classes for ticket resolution based on average days
 */
export const getTicketResolutionColor = (metrics: TicketResolutionMetrics) => {
  switch (metrics.status) {
    case 'excellent':
      return {
        icon: 'text-purple-600 dark:text-purple-400',
        bg: 'bg-purple-100 dark:bg-purple-900/30',
        text: 'text-purple-600 dark:text-purple-400'
      };
    case 'good':
      return {
        icon: 'text-blue-600 dark:text-blue-400',
        bg: 'bg-blue-100 dark:bg-blue-900/30',
        text: 'text-blue-600 dark:text-blue-400'
      };
    case 'needs_improvement':
      return {
        icon: 'text-orange-600 dark:text-orange-400',
        bg: 'bg-orange-100 dark:bg-orange-900/30',
        text: 'text-orange-600 dark:text-orange-400'
      };
    default:
      return {
        icon: 'text-gray-600 dark:text-gray-400',
        bg: 'bg-gray-100 dark:bg-gray-700',
        text: 'text-gray-600 dark:text-gray-400'
      };
  }
};

/**
 * Format date for display
 */
export const formatDate = (dateString: string | Date): string => {
  if (!dateString) return 'N/A';
  const date = new Date(dateString);
  return date.toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric'
  });
};

/**
 * Get icon SVG for upcoming event type
 */
export const getEventIcon = (icon: UpcomingEvent['icon']): JSX.Element => {
  const icons: Record<UpcomingEvent['icon'], JSX.Element> = {
    money: (
      <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8c-1.657 0-3 .895-3 2s1.343 2 3 2 3 .895 3 2-1.343 2-3 2m0-8c1.11 0 2.08.402 2.599 1M12 8V7m0 1v8m0 0v1m0-1c-1.11 0-2.08-.402-2.599-1M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
      </svg>
    ),
    document: (
      <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
      </svg>
    ),
    alert: (
      <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
      </svg>
    ),
    tool: (
      <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
      </svg>
    ),
    shield: (
      <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
      </svg>
    )
  };
  
  return icons[icon];
};

