/**
 * Transaction Ledger Utilities for Tenant Payment History
 *
 * Merges payments, rent payment transactions (Stripe Connect), and invoices
 * into a unified chronological transaction view with running balance calculations.
 *
 * Payment Sources:
 * - payments: Manual entries, QuickBooks sync, and other legacy sources
 * - rent_payment_transactions: Stripe Connect rent payments with refund tracking
 * - invoices: Charges/fees added to the tenant's account
 */

import { Lease, Payment, Invoice, RentPaymentTransaction } from '../types/tenant';

export interface Transaction {
  id: string;                    // Composite: 'payment-123', 'rent-txn-uuid', or 'invoice-456'
  date: Date;                    // payment_date, succeeded_at, or issue_date
  type: 'charge' | 'payment';    // Derived from source
  source: 'invoice' | 'payment' | 'rent_transaction'; // Original source
  description: string;           // invoice.description or payment description
  amount: number;                // Always positive (for rent txns, uses net_amount for refund tracking)
  balance: number;               // Running balance (calculated later)
  paymentMethod?: string;        // payment.payment_method or rent_txn payment_method_type
  receiptUrl?: string;           // payment.receipt_url or rent_txn receipt_url
  status: string;                // payment.status, rent_txn display_status, or invoice.status
  isCharge: boolean;             // true for invoices, false for payments
  rawData: Payment | Invoice | RentPaymentTransaction; // Original data for reference
  // Rent transaction specific fields
  refundedAmount?: number;       // For partially refunded transactions
  stripePaymentIntentId?: string; // For Stripe tracking
}

export interface LedgerMetrics {
  totalPaid: number;             // Sum of paid payments (legacy + Stripe)
  totalCharges: number;          // Expected rent + invoices
  expectedRent: number;          // Expected rent based on lease duration
  invoiceCharges: number;        // Sum of all invoice amounts
  currentBalance: number;        // totalCharges - totalPaid
  lastPaymentDate: Date | null;  // Most recent payment
  nextDueDate: Date | null;      // Next rent due date
  transactionCount: number;      // Total transactions
}

/**
 * Format payment method from Stripe payment_method_type to user-friendly display
 */
const formatStripePaymentMethod = (
  methodType?: string,
  lastFour?: string,
  bankName?: string
): string => {
  if (!methodType) return 'Stripe';

  switch (methodType) {
    case 'us_bank_account':
      return bankName ? `${bankName} ****${lastFour || ''}` : `Bank ****${lastFour || ''}`;
    case 'card':
      return `Card ****${lastFour || ''}`;
    case 'ach_debit':
      return `ACH ****${lastFour || ''}`;
    default:
      return methodType.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase());
  }
};

/**
 * Map rent transaction status to display-friendly status
 */
const mapRentTransactionStatus = (status: string): string => {
  switch (status) {
    case 'succeeded':
      return 'Paid';
    case 'partially_refunded':
      return 'Partial Refund';
    case 'refunded':
      return 'Refunded';
    case 'pending':
    case 'processing':
      return 'Pending';
    case 'failed':
      return 'Failed';
    case 'canceled':
      return 'Cancelled';
    default:
      return status.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase());
  }
};

/**
 * Build unified transaction ledger from payments, rent transactions, and invoices
 *
 * @param payments - Legacy payments (manual, QuickBooks, etc.)
 * @param invoices - Charges/fees on tenant account
 * @param rentTransactions - Stripe Connect rent payment transactions
 */
export const buildTransactionLedger = (
  payments: Payment[] | undefined,
  invoices: Invoice[] | undefined,
  rentTransactions?: RentPaymentTransaction[] | undefined
): Transaction[] => {
  const transactions: Transaction[] = [];

  // Build a set of stripe_payment_intent_ids from rent transactions for deduplication
  // This prevents showing the same Stripe payment twice (once from payments table, once from rent_transactions)
  const stripeIntentIds = new Set<string>();
  if (rentTransactions && rentTransactions.length > 0) {
    rentTransactions.forEach(txn => {
      if (txn.stripe_payment_intent_id) {
        stripeIntentIds.add(txn.stripe_payment_intent_id);
      }
    });
  }

  // Add legacy payments as transactions (manual entries, QuickBooks sync, etc.)
  // IMPORTANT: Skip payments that have a stripe_payment_intent_id matching a rent transaction
  // to avoid duplicate entries in the ledger
  if (payments && payments.length > 0) {
    payments.forEach(payment => {
      // Skip if this payment is a Stripe payment that will be shown via rent_transactions
      if (payment.stripe_payment_intent_id && stripeIntentIds.has(payment.stripe_payment_intent_id)) {
        return;
      }

      transactions.push({
        id: `payment-${payment.id}`,
        date: new Date(payment.payment_date),
        type: 'payment',
        source: 'payment',
        description: payment.description || 'Rent Payment',
        amount: Number(payment.amount),
        balance: 0, // Will be calculated
        paymentMethod: payment.payment_method,
        receiptUrl: payment.receipt_url || undefined,
        status: payment.status,
        isCharge: false,
        rawData: payment,
      });
    });
  }

  // Add Stripe Connect rent payment transactions
  if (rentTransactions && rentTransactions.length > 0) {
    rentTransactions.forEach(txn => {
      // Only include transactions that should appear in the ledger
      // (succeeded, partially_refunded, refunded - not pending/failed)
      const validStatuses = ['succeeded', 'partially_refunded', 'refunded'];
      if (!validStatuses.includes(txn.status)) return;

      // Use net_amount which accounts for any refunds
      const amount = Number(txn.net_amount);
      const refundedAmount = Number(txn.total_refunded) || 0;

      transactions.push({
        id: `rent-txn-${txn.id}`,
        date: new Date(txn.succeeded_at || txn.initiated_at),
        type: 'payment',
        source: 'rent_transaction',
        description: txn.property_name ? `Rent Payment - ${txn.property_name}` : 'Rent Payment (Stripe)',
        amount: amount,
        balance: 0, // Will be calculated
        paymentMethod: formatStripePaymentMethod(
          txn.payment_method_type,
          txn.payment_method_last_four,
          txn.payment_method_bank_name
        ),
        receiptUrl: txn.receipt_url || undefined,
        status: mapRentTransactionStatus(txn.status),
        isCharge: false,
        rawData: txn,
        refundedAmount: refundedAmount > 0 ? refundedAmount : undefined,
        stripePaymentIntentId: txn.stripe_payment_intent_id,
      });
    });
  }

  // Add invoices as transactions
  if (invoices && invoices.length > 0) {
    invoices.forEach(invoice => {
      transactions.push({
        id: `invoice-${invoice.id}`,
        date: new Date(invoice.issue_date),
        type: 'charge',
        source: 'invoice',
        description: invoice.description || `Invoice ${invoice.invoice_number}`,
        amount: Number(invoice.amount),
        balance: 0, // Will be calculated
        status: invoice.status,
        isCharge: true,
        rawData: invoice,
      });
    });
  }

  // Sort chronologically (oldest first for running balance)
  transactions.sort((a, b) => a.date.getTime() - b.date.getTime());

  // Calculate running balance
  // IMPORTANT: Only successful payments affect the balance.
  // - Legacy payments: status === 'Paid'
  // - Rent transactions: already filtered to succeeded/partially_refunded/refunded
  //   and amount uses net_amount which accounts for refunds
  let runningBalance = 0;
  transactions.forEach(txn => {
    if (txn.isCharge) {
      // All charges/invoices increase the balance owed
      runningBalance += txn.amount;
    } else if (txn.source === 'rent_transaction') {
      // Rent transactions are pre-filtered to successful ones,
      // and amount is already net of refunds
      runningBalance -= txn.amount;
    } else if (txn.status === 'Paid') {
      // Only successful "Paid" legacy payments reduce the balance
      runningBalance -= txn.amount;
    }
    // Pending/Cancelled/Failed payments don't affect balance
    // but are still shown in the ledger for transparency
    txn.balance = runningBalance;
  });

  // Return in reverse chronological order for display (newest first)
  return transactions.reverse();
};

/**
 * Calculate months elapsed in a lease
 * Uses UTC dates to avoid timezone issues
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
 * Calculate financial metrics from transaction data
 *
 * Key principle: Rent charges are lease-based (monthly_rent × months_elapsed),
 * NOT invoice-based. Invoices are for miscellaneous charges only.
 *
 * MULTI-UNIT SUPPORT: Aggregates expected rent across all active leases.
 *
 * @param payments - Legacy payments (manual, QuickBooks, etc.)
 * @param invoices - Miscellaneous charges/fees on tenant account
 * @param activeLeases - All active leases for rent and due date calculation
 * @param rentTransactions - Stripe Connect rent payment transactions
 */
export const calculateLedgerMetrics = (
  payments: Payment[] | undefined,
  invoices: Invoice[] | undefined,
  activeLeases: Lease[],
  rentTransactions?: RentPaymentTransaction[] | undefined
): LedgerMetrics => {
  const validStatuses = ['succeeded', 'partially_refunded', 'refunded'];

  // =========================================================================
  // CALCULATE TOTAL PAID (from all payment sources)
  // =========================================================================

  // Build a set of stripe_payment_intent_ids from rent transactions for deduplication
  const stripeIntentIds = new Set<string>();
  if (rentTransactions && rentTransactions.length > 0) {
    rentTransactions.forEach(txn => {
      if (txn.stripe_payment_intent_id) {
        stripeIntentIds.add(txn.stripe_payment_intent_id);
      }
    });
  }

  // Legacy payments (only "Paid" status, excluding Stripe payments that are in rent_transactions)
  const legacyPaid = payments
    ?.filter(p => p.status === 'Paid')
    .filter(p => !p.stripe_payment_intent_id || !stripeIntentIds.has(p.stripe_payment_intent_id))
    .reduce((sum, p) => sum + Number(p.amount), 0) || 0;

  // Stripe Connect rent transactions (using net_amount for refund tracking)
  const rentPaid = rentTransactions
    ?.filter(txn => validStatuses.includes(txn.status))
    .reduce((sum, txn) => sum + Number(txn.net_amount), 0) || 0;

  const totalPaid = legacyPaid + rentPaid;

  // =========================================================================
  // CALCULATE TOTAL CHARGES (expected rent + invoice charges)
  // =========================================================================

  // MULTI-UNIT SUPPORT: Expected rent summed across ALL active leases
  let expectedRent = 0;
  if (activeLeases && activeLeases.length > 0) {
    activeLeases.forEach(lease => {
      const leaseStart = new Date(lease.start_date);
      const leaseEnd = new Date(lease.end_date);
      const today = new Date();
      const currentDate = today > leaseEnd ? leaseEnd : today;

      const monthsElapsed = calculateMonthsElapsed(leaseStart, currentDate);
      const monthlyRent = Number(lease.monthly_rent) || 0;
      expectedRent += monthsElapsed * monthlyRent;
    });
  }

  // Invoice charges (miscellaneous fees)
  const invoiceCharges = invoices
    ?.reduce((sum, inv) => sum + Number(inv.amount), 0) || 0;

  const totalCharges = expectedRent + invoiceCharges;

  // Current balance (what tenant owes)
  const currentBalance = totalCharges - totalPaid;

  // =========================================================================
  // FIND LAST PAYMENT DATE (from all sources)
  // =========================================================================

  let lastPaymentDate: Date | null = null;

  // Check legacy payments (excluding Stripe payments that are in rent_transactions)
  if (payments && payments.length > 0) {
    const paidPayments = payments
      .filter(p => p.status === 'Paid')
      .filter(p => !p.stripe_payment_intent_id || !stripeIntentIds.has(p.stripe_payment_intent_id));
    if (paidPayments.length > 0) {
      const sortedPayments = [...paidPayments].sort(
        (a, b) => new Date(b.payment_date).getTime() - new Date(a.payment_date).getTime()
      );
      lastPaymentDate = new Date(sortedPayments[0].payment_date);
    }
  }

  // Check rent transactions for more recent payment
  if (rentTransactions && rentTransactions.length > 0) {
    const successfulTxns = rentTransactions.filter(txn => validStatuses.includes(txn.status));
    if (successfulTxns.length > 0) {
      const sortedTxns = [...successfulTxns].sort((a, b) => {
        const dateA = new Date(a.succeeded_at || a.initiated_at).getTime();
        const dateB = new Date(b.succeeded_at || b.initiated_at).getTime();
        return dateB - dateA;
      });
      const rentLastDate = new Date(sortedTxns[0].succeeded_at || sortedTxns[0].initiated_at);

      // Use whichever is more recent
      if (!lastPaymentDate || rentLastDate > lastPaymentDate) {
        lastPaymentDate = rentLastDate;
      }
    }
  }

  // =========================================================================
  // CALCULATE NEXT DUE DATE
  // =========================================================================

  // MULTI-UNIT SUPPORT: Show earliest due date across all active leases
  let nextDueDate: Date | null = null;
  if (activeLeases && activeLeases.length > 0) {
    const today = new Date();
    const currentMonth = today.getMonth();
    const currentYear = today.getFullYear();
    const currentDay = today.getDate();

    const dueDates: Date[] = [];
    activeLeases.forEach(lease => {
      const rentDueDay = lease.rent_due_day || 1;
      
      // If due day hasn't passed this month, use this month's due date
      if (currentDay <= rentDueDay) {
        dueDates.push(new Date(currentYear, currentMonth, rentDueDay));
      } else {
        // Otherwise, use next month's due date
        dueDates.push(new Date(currentYear, currentMonth + 1, rentDueDay));
      }
    });

    // Return the earliest due date
    if (dueDates.length > 0) {
      nextDueDate = new Date(Math.min(...dueDates.map(d => d.getTime())));
    }
  }

  // =========================================================================
  // COUNT TRANSACTIONS (excluding duplicates)
  // =========================================================================

  const rentTxnCount = rentTransactions?.filter(txn => validStatuses.includes(txn.status)).length || 0;
  // Count legacy payments excluding those that are duplicates of rent transactions
  const legacyPaymentCount = payments
    ?.filter(p => !p.stripe_payment_intent_id || !stripeIntentIds.has(p.stripe_payment_intent_id))
    .length || 0;
  const transactionCount = legacyPaymentCount + (invoices?.length || 0) + rentTxnCount;

  return {
    totalPaid,
    totalCharges,
    expectedRent,
    invoiceCharges,
    currentBalance,
    lastPaymentDate,
    nextDueDate,
    transactionCount,
  };
};

/**
 * Format currency for display
 */
export const formatCurrency = (value: number): string => {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 2,
    maximumFractionDigits: 2
  }).format(value);
};

/**
 * Format amount with +/- prefix for transaction display
 */
export const formatTransactionAmount = (amount: number, isCharge: boolean): string => {
  const formatted = formatCurrency(Math.abs(amount));
  return isCharge ? `+${formatted}` : `-${formatted}`;
};

/**
 * Get color class for balance display in summary cards
 */
export const getBalanceColor = (balance: number): string => {
  if (balance > 0) return 'text-red-600 dark:text-red-400';  // Owes money
  if (balance < 0) return 'text-green-600 dark:text-green-400';  // Overpaid/credit
  return 'text-gray-900 dark:text-gray-100';  // Paid up - white
};

/**
 * Get status badge class
 */
export const getStatusBadgeClass = (status: string): string => {
  switch (status.toLowerCase()) {
    case 'paid':
      return 'bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-300';
    case 'pending':
    case 'partial':
      return 'bg-yellow-100 dark:bg-yellow-900/30 text-yellow-700 dark:text-yellow-300';
    case 'overdue':
      return 'bg-red-100 dark:bg-red-900/30 text-red-700 dark:text-red-300';
    case 'cancelled':
    case 'refunded':
      return 'bg-gray-100 dark:bg-gray-900/30 text-gray-700 dark:text-gray-300';
    default:
      return 'bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300';
  }
};

/**
 * Format date for CSV export (ISO 8601: YYYY-MM-DD)
 * Uses en-CA locale for consistent, sortable date format
 */
export const formatDateForCSV = (date: Date): string => {
  return date.toLocaleDateString('en-CA'); // YYYY-MM-DD format
};

/**
 * Format date for UI display (US format: MMM DD, YYYY)
 * Uses en-US locale for consistent user-facing display
 */
export const formatDateForDisplay = (date: Date, options?: Intl.DateTimeFormatOptions): string => {
  const defaultOptions: Intl.DateTimeFormatOptions = {
    month: 'short',
    day: 'numeric',
    year: 'numeric'
  };
  return date.toLocaleDateString('en-US', options || defaultOptions);
};

