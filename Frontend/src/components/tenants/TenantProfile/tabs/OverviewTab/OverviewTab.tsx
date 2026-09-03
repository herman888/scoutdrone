import React, { useMemo, useState } from 'react';
import { useOutletContext } from 'react-router-dom';
import { toast } from 'react-toastify';
import * as Sentry from '@sentry/react';
import { EnrichedTenant } from '../../../../../types/tenant';
import { getSecureDocumentUrl } from '../../../../../utils/api/leases';
import { updateTenant, sendTenantReminder, TenantReminderRequest } from '../../../../../utils/api/tenants';
import ReminderMethodModal, { type ReminderMethod } from '../../ReminderMethodModal';
import ReminderConfirmationModal from '../../ReminderConfirmationModal';
import ViewLeaseModal from '../../../../leases/modals/ViewLeaseModal';
import type { Lease } from '../../../../../types/lease';
import MetricCard from './MetricCard';
import CurrentLeaseCard from './CurrentLeaseCard';
import PaymentSummaryCard from './PaymentSummaryCard';
import UpcomingCard from './UpcomingCard';
import ContactsCard from './ContactsCard';
import {
  calculatePaymentPerformance,
  calculateOpenBalance,
  calculateMaintenanceTickets,
  generateUpcomingEvents,
  getPaymentPerformanceColor,
  getOpenBalanceColor,
  getMaintenanceTicketsColor,
  calculatePaidThisMonth,
  getLastPaymentInfo,
  UpcomingEvent
} from '../../../../../utils/tenantMetrics.tsx';

interface OutletContext {
  tenant: EnrichedTenant;
  refetch: () => void;
  openFilePreviewModal: (url: string, name: string) => void;
  closeFilePreviewModal: () => void;
  openPaymentModal: (initialData: any) => void;
  openEmergencyContactModal: (contact?: any) => void;
}

/** Get ordinal suffix for a number (1st, 2nd, 3rd, etc.) */
const getOrdinalSuffix = (n: number): string => {
  const s = ['th', 'st', 'nd', 'rd'];
  const v = n % 100;
  return s[(v - 20) % 10] || s[v] || s[0];
};

const OverviewTab: React.FC = () => {
  const context = useOutletContext<OutletContext>();

  // State for delete confirmation and loading
  const [deletingContactIndex, setDeletingContactIndex] = useState<number | null>(null);
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const [contactIndexToDelete, setContactIndexToDelete] = useState<number | null>(null);

  // State for reminder sending
  const [sendingReminder, setSendingReminder] = useState<string | null>(null);
  const [showMethodModal, setShowMethodModal] = useState(false);
  const [showEmailModal, setShowEmailModal] = useState(false);
  const [selectedEvent, setSelectedEvent] = useState<UpcomingEvent | null>(null);

  // State for lease details modal
  const [showLeaseModal, setShowLeaseModal] = useState(false);
  const [selectedLeaseForModal, setSelectedLeaseForModal] = useState<any>(null);

  // Guard: Handle undefined context gracefully
  if (!context || !context.tenant) {
    return null;
  }

  const { tenant, refetch, openFilePreviewModal, openPaymentModal, openEmergencyContactModal } = context;

  // Calculate all metrics from tenant data (now aggregates across ALL active leases)
  const metrics = useMemo(() => {
    // MULTI-UNIT SUPPORT: Get ALL active leases instead of just one
    const activeLeases = tenant.leases?.filter(lease => lease.status === 'ACTIVE') || [];
    const activeLease = activeLeases[0]; // For backward compatibility with single-lease components

    const openBalance = calculateOpenBalance(tenant, activeLeases);
    return {
      paymentPerformance: calculatePaymentPerformance(tenant, activeLeases),
      openBalance,
      maintenanceTickets: calculateMaintenanceTickets(tenant),
      upcomingEvents: generateUpcomingEvents(tenant, activeLease, openBalance),
      paidThisMonth: calculatePaidThisMonth(tenant, activeLeases),
      lastPayment: getLastPaymentInfo(tenant, activeLease)
    };
  }, [tenant]);

  // Get active leases for rendering components
  const activeLeases = tenant.leases?.filter(lease => lease.status === 'ACTIVE') || [];
  const activeLease = activeLeases[0];

  // Handle clicking Remind button
  const handleRemindClick = (event: UpcomingEvent) => {
    setSelectedEvent(event);
    setShowMethodModal(true);
  };

  // Handle method selection from ReminderMethodModal
  const handleMethodSelect = async (method: ReminderMethod) => {
    if (!selectedEvent || !tenant) return;

    setShowMethodModal(false);

    if (method === 'portal') {
      setSendingReminder(selectedEvent.id);
      try {
        const reminderData: TenantReminderRequest = {
          event_type: selectedEvent.type as TenantReminderRequest['event_type'],
          event_title: selectedEvent.title,
          event_subtitle: selectedEvent.subtitle,
          event_date: selectedEvent.date ? selectedEvent.date.toISOString() : null,
          event_amount: selectedEvent.amount ?? null,
          days_remaining: selectedEvent.daysRemaining ?? null,
          delivery_method: 'portal',
        };

        const response = await sendTenantReminder(tenant.id, reminderData);

        if (response.success) {
          toast.success(response.message);
          setSelectedEvent(null);
        } else {
          toast.error('Failed to send reminder');
        }
      } catch (error: any) {
        Sentry.captureException(error, {
          tags: { component: 'OverviewTab', action: 'send_portal_reminder' },
          contexts: { tenant: { id: tenant?.id }, event: { type: selectedEvent.type } },
        });
        toast.error(error?.message || 'Failed to send reminder. Please try again.');
      } finally {
        setSendingReminder(null);
      }
    } else {
      setShowEmailModal(true);
    }
  };

  // Handle confirming reminder email
  const handleConfirmReminder = async (customSubject: string | null, customMessage: string | null) => {
    if (!selectedEvent || !tenant) {
      toast.error('Cannot send reminder: missing information');
      setShowEmailModal(false);
      setSelectedEvent(null);
      return;
    }

    setSendingReminder(selectedEvent.id);

    try {
      const reminderData: TenantReminderRequest = {
        event_type: selectedEvent.type as TenantReminderRequest['event_type'],
        event_title: selectedEvent.title,
        event_subtitle: selectedEvent.subtitle,
        event_date: selectedEvent.date ? selectedEvent.date.toISOString() : null,
        event_amount: selectedEvent.amount ?? null,
        days_remaining: selectedEvent.daysRemaining ?? null,
        custom_subject: customSubject,
        custom_message: customMessage,
        delivery_method: 'email',
      };

      const response = await sendTenantReminder(tenant.id, reminderData);

      if (response.success) {
        toast.success(response.message);
        setShowEmailModal(false);
        setSelectedEvent(null);
      } else {
        toast.error('Failed to send reminder email');
      }
    } catch (error: any) {
      Sentry.captureException(error, {
        tags: { component: 'OverviewTab', action: 'send_email_reminder' },
        contexts: { tenant: { id: tenant?.id }, event: { type: selectedEvent.type, id: selectedEvent.id } },
      });
      toast.error(error?.message || 'Failed to send reminder email. Please try again.');
    } finally {
      setSendingReminder(null);
    }
  };

  // Handle closing modals
  const handleCloseMethodModal = () => {
    setShowMethodModal(false);
    setSelectedEvent(null);
  };

  const handleCloseEmailModal = () => {
    if (sendingReminder) return;
    setShowEmailModal(false);
    setSelectedEvent(null);
  };

  // Handle View Lease Document button - can accept a specific lease or default to first active lease
  const handleViewLease = async (lease?: any) => {
    const targetLease = lease || activeLease;
    
    if (!targetLease) {
      toast.error('No active lease found.');
      return;
    }

    const leaseDocument = targetLease.documents?.[0];

    if (!leaseDocument || !leaseDocument.id) {
      toast.info('No Document Available');
      return;
    }

    try {
      const loadingToast = toast.info('Generating secure preview link...', { autoClose: false });
      const { secure_url } = await getSecureDocumentUrl(targetLease.id, leaseDocument.id);
      toast.dismiss(loadingToast);

      const tenantName = tenant.tenant_type === 'Company'
        ? tenant.company_name
        : `${tenant.first_name} ${tenant.last_name}`;
      const propertyName = targetLease.property?.name || tenant.property?.name || 'Property';
      const unitName = targetLease.unit?.name ? ` - Unit ${targetLease.unit.name}` : '';
      const fileName = `Lease: ${tenantName} - ${propertyName}${unitName}`;
      openFilePreviewModal(secure_url, fileName);
    } catch (error: unknown) {
      toast.error('Failed to load document. Please try again.');
      Sentry.captureException(error, {
        tags: { component: 'OverviewTab', action: 'view_lease_document' },
        contexts: { lease: { id: targetLease.id }, document: { id: leaseDocument?.id } },
      });
    }
  };

  // Handle opening lease details modal - can accept a specific lease or default to first active lease
  const handleViewLeaseInfo = (lease?: any) => {
    const targetLease = lease || activeLease;
    
    if (!targetLease) {
      toast.error('No active lease found.');
      return;
    }

    setSelectedLeaseForModal(targetLease);
    setShowLeaseModal(true);
  };

  // Handle Record Payment button
  const handleRecordPayment = () => {
    if (!activeLease) {
      toast.error('No active lease found for this tenant.');
      return;
    }

    const tenantName = tenant.tenant_type === 'Company'
      ? tenant.company_name || 'Company Tenant'
      : `${tenant.first_name || ''} ${tenant.last_name || ''}`.trim();

    const propertyName = activeLease.property?.name || tenant.property?.name || '';
    const propertyId = activeLease.property?.id || tenant.current_property_id;

    const initialData = {
      tenant_id: tenant.id,
      tenant_name: tenantName,
      property_id: propertyId?.toString() || '',
      property_name: propertyName,
      lease_id: activeLease.id,
      amount: activeLease.monthly_rent?.toString() || '',
      payment_date: new Date().toISOString().split('T')[0],
      payment_method: 'Other',
      status: 'Paid',
    };

    openPaymentModal(initialData);
  };

  // Emergency Contact Handlers
  const handleAddEmergencyContact = () => {
    openEmergencyContactModal();
  };

  const handleEditEmergencyContact = (contact: any) => {
    openEmergencyContactModal(contact);
  };

  const handleDeleteEmergencyContact = (contactIndex: number) => {
    setContactIndexToDelete(contactIndex);
    setShowDeleteConfirm(true);
  };

  const confirmDeleteContact = async () => {
    if (contactIndexToDelete === null || !tenant.id) {
      toast.error('Invalid operation');
      setShowDeleteConfirm(false);
      setContactIndexToDelete(null);
      return;
    }

    setDeletingContactIndex(contactIndexToDelete);

    try {
      const updatedContacts = tenant.emergency_contacts?.filter((_c, index) => index !== contactIndexToDelete) || [];
      await updateTenant(tenant.id, { emergency_contacts: updatedContacts });
      await refetch();
      toast.success('Emergency contact removed successfully');

      Sentry.addBreadcrumb({
        category: 'emergency_contact',
        message: 'Emergency contact deleted',
        level: 'info',
        data: { tenant_id: tenant.id, contact_index: contactIndexToDelete },
      });
    } catch (error: any) {
      Sentry.captureException(error, {
        tags: { component: 'tenant_profile', action: 'delete_emergency_contact', tenant_id: tenant.id.toString() },
        contexts: {
          emergency_contact: {
            contact_index: contactIndexToDelete,
            tenant_id: tenant.id,
            total_contacts: tenant.emergency_contacts?.length || 0,
          },
        },
      });
      const errorMessage = error?.response?.data?.detail || error?.message || 'Failed to remove emergency contact.';
      toast.error(errorMessage);
    } finally {
      setDeletingContactIndex(null);
      setShowDeleteConfirm(false);
      setContactIndexToDelete(null);
    }
  };

  const cancelDeleteContact = () => {
    setShowDeleteConfirm(false);
    setContactIndexToDelete(null);
  };

  // Get tenant display name
  const tenantName = tenant.tenant_type === 'Company'
    ? tenant.company_name || 'Company Tenant'
    : `${tenant.first_name || ''} ${tenant.last_name || ''}`.trim() || 'Tenant';

  // Get metric colors
  const paymentColors = getPaymentPerformanceColor(metrics.paymentPerformance);
  const maintenanceColors = getMaintenanceTicketsColor(metrics.maintenanceTickets);
  const balanceColors = getOpenBalanceColor(
    metrics.openBalance.totalBalance,
    metrics.openBalance.isOverdue,
    activeLease?.monthly_rent ? Number(activeLease.monthly_rent) : 0
  );

  return (
    <div className="h-full overflow-auto">
      {/* Main Grid Layout */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* Left Column - 2/3 width */}
        <div className="lg:col-span-2 flex flex-col gap-4">
          {/* 3 Metric Cards Row */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <MetricCard
              title="Payment Performance"
              value={metrics.paymentPerformance.rate !== null ? `${metrics.paymentPerformance.rate}%` : null}
              subtitle={metrics.paymentPerformance.totalCount > 0
                ? `${metrics.paymentPerformance.onTimeCount}/${metrics.paymentPerformance.totalCount} on-time`
                : 'No payment history'}
              icon={
                <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 7h8m0 0v8m0-8l-8 8-4-4-6 6" />
                </svg>
              }
              bgColor={paymentColors.bg}
              iconColor={paymentColors.icon}
              secondaryStat={metrics.paymentPerformance.totalCount > 0 && metrics.paymentPerformance.avgDaysEarly !== 0
                ? (metrics.paymentPerformance.avgDaysEarly > 0
                  ? `Avg ${metrics.paymentPerformance.avgDaysEarly}d early`
                  : `Avg ${Math.abs(metrics.paymentPerformance.avgDaysEarly)}d late`)
                : undefined}
              tertiaryStat={metrics.paymentPerformance.totalCount > 0
                ? `Due: ${activeLease?.rent_due_day || 1}${getOrdinalSuffix(activeLease?.rent_due_day || 1)}`
                : undefined}
            />
            <MetricCard
              title="Maintenance Tickets"
              value={metrics.maintenanceTickets.totalCount > 0 ? metrics.maintenanceTickets.activeCount : null}
              subtitle={metrics.maintenanceTickets.totalCount > 0
                ? `${metrics.maintenanceTickets.activeCount} active, ${metrics.maintenanceTickets.completedCount} resolved`
                : 'No tickets'}
              icon={
                <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                </svg>
              }
              bgColor={maintenanceColors.bg}
              iconColor={maintenanceColors.icon}
              secondaryStat={metrics.maintenanceTickets.totalCount > 0
                ? `${metrics.maintenanceTickets.inProgressCount} in progress, ${metrics.maintenanceTickets.scheduledCount} scheduled`
                : undefined}
              tertiaryStat={metrics.maintenanceTickets.highPriorityCount > 0
                ? `${metrics.maintenanceTickets.highPriorityCount} high priority`
                : (metrics.maintenanceTickets.avgResolutionDays !== null
                  ? `Avg ${metrics.maintenanceTickets.avgResolutionDays}d to resolve`
                  : undefined)}
            />
            <MetricCard
              title="Outstanding"
              value={`$${metrics.openBalance.totalBalance.toLocaleString('en-US', { minimumFractionDigits: 0, maximumFractionDigits: 0 })}`}
              subtitle={metrics.openBalance.totalBalance === 0
                ? 'No balance'
                : metrics.openBalance.isOverdue
                  ? `$${metrics.openBalance.overdueBalance.toLocaleString()} overdue`
                  : 'Current'}
              icon={
                <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8c-1.657 0-3 .895-3 2s1.343 2 3 2 3 .895 3 2-1.343 2-3 2m0-8c1.11 0 2.08.402 2.599 1M12 8V7m0 1v8m0 0v1m0-1c-1.11 0-2.08-.402-2.599-1M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
              }
              bgColor={balanceColors.bg}
              iconColor={balanceColors.icon}
              valueColor={balanceColors.text}
              secondaryStat={metrics.openBalance.rentBalance > 0
                ? `Rent: $${metrics.openBalance.rentBalance.toLocaleString()}`
                : undefined}
              tertiaryStat={metrics.openBalance.invoiceBalance > 0
                ? `Invoices: $${metrics.openBalance.invoiceBalance.toLocaleString()}`
                : undefined}
            />
          </div>

          {/* Current Lease and Payment Summary Row */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <CurrentLeaseCard
              activeLeases={activeLeases}
              tenant={tenant}
              onViewLeaseInfo={handleViewLeaseInfo}
              onViewLeaseDocument={handleViewLease}
            />
            <PaymentSummaryCard
              paidThisMonth={metrics.paidThisMonth}
              outstandingBalance={metrics.openBalance.totalBalance}
              securityDeposit={activeLease?.security_deposit ?? null}
              hasActiveLease={!!activeLease}
              onRecordPayment={handleRecordPayment}
              lastPayment={metrics.lastPayment}
              nextDueAmount={metrics.openBalance.nextDueAmount}
              nextDueDate={metrics.openBalance.nextDueDate}
            />
          </div>
        </div>

        {/* Right Column - 1/3 width (Sidebar) */}
        <div className="flex flex-col gap-4">
          <UpcomingCard
            events={metrics.upcomingEvents}
            tenantHasEmail={!!tenant.email}
            sendingReminder={sendingReminder}
            onRemindClick={handleRemindClick}
          />
          <ContactsCard
            tenantName={tenantName}
            tenantEmail={tenant.email}
            tenantPhone={tenant.phone}
            emergencyContacts={tenant.emergency_contacts || []}
            onAddContact={handleAddEmergencyContact}
            onEditContact={handleEditEmergencyContact}
            onDeleteContact={handleDeleteEmergencyContact}
          />
        </div>
      </div>

      {/* Modals */}
      {selectedEvent && (
        <ReminderMethodModal
          isOpen={showMethodModal}
          onClose={handleCloseMethodModal}
          onSelect={handleMethodSelect}
          tenantName={tenantName}
          hasPortalAccess={!!tenant.user_id}
        />
      )}

      {selectedEvent && (
        <ReminderConfirmationModal
          isOpen={showEmailModal}
          onClose={handleCloseEmailModal}
          onConfirm={handleConfirmReminder}
          tenant={tenant}
          event={selectedEvent}
          isLoading={sendingReminder === selectedEvent.id}
        />
      )}

      {showDeleteConfirm && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
          <div className="bg-white dark:bg-gray-800 rounded-lg shadow-xl max-w-md w-full p-6">
            <div className="flex items-center gap-3 mb-4">
              <div className="flex-shrink-0 w-12 h-12 bg-red-100 dark:bg-red-900/30 rounded-full flex items-center justify-center">
                <svg className="w-6 h-6 text-red-600 dark:text-red-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                </svg>
              </div>
              <div className="flex-1">
                <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100">Delete Emergency Contact</h3>
                <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
                  Are you sure? This action cannot be undone.
                </p>
              </div>
            </div>
            <div className="flex items-center gap-3 mt-6">
              <button
                onClick={cancelDeleteContact}
                disabled={deletingContactIndex !== null}
                className="flex-1 px-4 py-2.5 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-lg text-gray-700 dark:text-gray-200 text-sm font-medium hover:bg-gray-50 dark:hover:bg-gray-600 transition-colors disabled:opacity-50"
              >
                Cancel
              </button>
              <button
                onClick={confirmDeleteContact}
                disabled={deletingContactIndex !== null}
                className="flex-1 px-4 py-2.5 bg-red-600 hover:bg-red-700 text-white rounded-lg text-sm font-medium transition-colors disabled:opacity-50 flex items-center justify-center gap-2"
              >
                {deletingContactIndex !== null ? (
                  <>
                    <svg className="animate-spin h-4 w-4" fill="none" viewBox="0 0 24 24">
                      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                    </svg>
                    Deleting...
                  </>
                ) : (
                  'Delete'
                )}
              </button>
            </div>
          </div>
        </div>
      )}

      <ViewLeaseModal
        isOpen={showLeaseModal}
        onClose={() => {
          setShowLeaseModal(false);
          setSelectedLeaseForModal(null);
        }}
        lease={selectedLeaseForModal as Lease | null}
        tenantName={tenantName}
      />
    </div>
  );
};

export default OverviewTab;
