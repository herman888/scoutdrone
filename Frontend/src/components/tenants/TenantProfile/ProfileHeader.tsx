import React, { useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'react-toastify';
import * as Sentry from '@sentry/react';
import { EnrichedTenant, TenantStatus, MaintenancePriority, MaintenanceStatus } from '../../../types/tenant';
import { getInitials } from '../../../utils/tenantUtils';
import { InvitationResponse, InvitationStatus, getPortalStatusDisplay } from '../../../types/invitation';
import {
  getTenantInvitation,
  createTenantInvitation,
  resendTenantInvitation,
  revokeTenantInvitation,
  isInvitationValid,
  getInvitationExpiryText,
} from '../../../utils/api/tenantInvitations';
import { getSeatAvailability } from '../../../utils/api/tenantPortalSeats';
import { QUERY_KEYS } from '../../../hooks/queryKeys';
import SeatSubscriptionModal from '../SeatSubscriptionModal';
import { useMessaging } from '../../../contexts/MessagingContext';

interface TenantProfileHeaderProps {
  tenant: EnrichedTenant;
  onEdit: () => void;
  onDelete: () => void;
  onRefresh: () => void;
  onNewTicket?: (initialData: any) => void;
  onRecordPayment?: (initialData: any) => void;
  onUploadDocument?: () => void;
}

const TenantProfileHeader: React.FC<TenantProfileHeaderProps> = ({
  tenant,
  onEdit,
  onDelete,
  onRefresh,
  onNewTicket,
  onRecordPayment,
  onUploadDocument
}) => {
  const queryClient = useQueryClient();
  const [showMoreMenu, setShowMoreMenu] = useState(false);
  const [isInviting, setIsInviting] = useState(false);
  const [showSeatModal, setShowSeatModal] = useState(false);
  const [showInviteConfirm, setShowInviteConfirm] = useState(false);

  // Fetch invitation status for portal indicator
  const { data: invitation, refetch: refetchInvitation } = useQuery<InvitationResponse | null>({
    queryKey: [...QUERY_KEYS.tenants.detail(tenant.id), 'invitation'],
    queryFn: () => getTenantInvitation(tenant.id),
    enabled: !!tenant.id && !tenant.user_id, // Only fetch if no portal access
    staleTime: 60 * 1000, // 1 minute
  });

  // Fetch seat availability for the landlord
  const { data: seatAvailability, isLoading: loadingSeatAvailability } = useQuery({
    queryKey: ['tenantPortalSeats', 'availability'],
    queryFn: getSeatAvailability,
    enabled: !tenant.user_id,
    staleTime: 30 * 1000, // 30 seconds
    refetchOnWindowFocus: false,
  });

  // Determine portal status for display
  const hasPortalAccess = !!tenant.user_id;
  const portalStatus = getPortalStatusDisplay(hasPortalAccess, invitation ?? null);

  const getDisplayName = () => {
    if (tenant.tenant_type === 'Company') {
      return tenant.company_name || 'Company Tenant';
    }
    return `${tenant.first_name || ''} ${tenant.last_name || ''}`.trim() || 'Individual Tenant';
  };

  const getStatusBadgeClass = (status: TenantStatus) => {
    const baseClasses = 'inline-flex items-center px-3 py-1 rounded-full text-xs font-semibold';

    switch (status.toLowerCase()) {
      case 'active':
        return `${baseClasses} bg-green-100 dark:bg-green-900/30 text-green-800 dark:text-green-200`;
      case 'pending':
        return `${baseClasses} bg-yellow-100 dark:bg-yellow-900/30 text-yellow-800 dark:text-yellow-200`;
      case 'inactive':
        return `${baseClasses} bg-gray-100 dark:bg-gray-900/30 text-gray-800 dark:text-gray-200`;
      case 'evicted':
        return `${baseClasses} bg-red-100 dark:bg-red-900/30 text-red-800 dark:text-red-200`;
      case 'moved out':
        return `${baseClasses} bg-blue-100 dark:bg-blue-900/30 text-blue-800 dark:text-blue-200`;
      default:
        return `${baseClasses} bg-gray-100 dark:bg-gray-900/30 text-gray-800 dark:text-gray-200`;
    }
  };

  const getPropertyInfo = () => {
    // MULTI-UNIT SUPPORT: Show all units from active leases
    const activeLeases = tenant.leases?.filter(lease => lease.status === 'ACTIVE') || [];
    const unitsWithLeases = activeLeases
      .filter(lease => lease.unit?.name)
      .map(lease => ({ property: lease.property?.name, unit: lease.unit?.name }));

    if (unitsWithLeases.length === 0) {
      // Fallback to legacy property/unit fields
      const property = tenant.property?.name;
      const unit = tenant.unit?.name;
      if (property && unit) return `${property} • Unit ${unit}`;
      if (property) return property;
      return null;
    }

    // Check if all units are in the same property
    const uniqueProperties = [...new Set(unitsWithLeases.map(item => item.property).filter(Boolean))];
    const unitNames = unitsWithLeases.map(item => item.unit).filter(Boolean);

    // Single unit case
    if (unitNames.length === 1) {
      return `${uniqueProperties[0]} • Unit ${unitNames[0]}`;
    }

    // Multiple units in the same property
    if (uniqueProperties.length === 1) {
      return `${uniqueProperties[0]} • ${unitNames.length} Units`;
    }

    // Multiple units across different properties
    if (uniqueProperties.length > 1) {
      return `${uniqueProperties.length} Properties • ${unitNames.length} Units`;
    }

    return uniqueProperties[0] || null;
  };

  const { openDrawer } = useMessaging();

  const handleMessage = () => {
    // Only allow messaging tenants with portal access
    if (!tenant.user_id) {
      toast.error('This tenant must have portal access to receive messages. Send them a portal invitation first.');
      return;
    }
    // Open messaging drawer with this tenant
    openDrawer(tenant.id);
  };

  const handleNewTicket = () => {
    if (!onNewTicket) return;
    
    // Get active lease to extract property and unit info
    const activeLease = tenant.leases?.find(lease => lease.status === 'ACTIVE');
    
    // Ensure all IDs are strings (modal expects strings for select inputs)
    const propertyId = activeLease?.property_id || tenant.current_property_id;
    const unitId = activeLease?.unit_id || tenant.assigned_units?.[0]?.id || tenant.unit?.id;
    
    const initialData = {
      tenant_id: String(tenant.id),
      property_id: propertyId ? String(propertyId) : '',
      unit_id: unitId ? String(unitId) : '',
      priority: MaintenancePriority.MEDIUM,  // Uses enum for type safety
      status: MaintenanceStatus.PENDING,     // Uses enum for type safety
    };

    onNewTicket(initialData);
  };

  const handleUpload = () => {
    if (onUploadDocument) {
      onUploadDocument();
    }
  };

  const handlePayment = () => {
    if (!onRecordPayment) return;
    
    // Get active lease to extract property and payment info
    const activeLease = tenant.leases?.find(lease => lease.status === 'ACTIVE');
    
    if (!activeLease) {
      // Could show a toast here, but button should be disabled if no active lease
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

    onRecordPayment(initialData);
  };

  // Show confirmation before sending invitation
  const handleInviteClick = () => {
    if (!tenant.email) {
      toast.error('Cannot invite tenant: No email address on file');
      return;
    }

    // Check seat availability before showing confirmation
    if (seatAvailability && seatAvailability.available <= 0) {
      Sentry.captureMessage('Seat limit reached, showing subscription modal', {
        level: 'warning',
        tags: { component: 'ProfileHeader', action: 'invite_tenant' },
        extra: {
          landlord_seats_used: seatAvailability.used,
          landlord_seats_limit: seatAvailability.limit,
          tenant_id: tenant.id,
        },
      });
      setShowSeatModal(true);
      return;
    }

    // Show confirmation dialog
    setShowInviteConfirm(true);
  };

  // Handle sending invitation after confirmation
  const handleInviteConfirm = async () => {
    setShowInviteConfirm(false);
    setIsInviting(true);

    try {
      await Sentry.startSpan(
        { op: 'api.call', name: 'Create Tenant Invitation' },
        async (span) => {
          try {
            const result = await createTenantInvitation(tenant.id);

            if (result) {
              toast.success(`Invitation sent to ${tenant.email}`);
              await refetchInvitation();
              queryClient.invalidateQueries({
                queryKey: QUERY_KEYS.tenants.detail(tenant.id),
              });
              span?.setStatus({ code: 1 }); // OK status
            }
          } catch (innerError) {
            span?.setStatus({ code: 2, message: 'Internal error' }); // Error status
            throw innerError; // Re-throw to be caught by outer catch
          }
        }
      );
    } catch (error: unknown) {
      console.error('Failed to send invitation:', error);

      Sentry.captureException(error, {
        tags: { component: 'ProfileHeader', action: 'invite_tenant' },
        contexts: { tenant: { id: tenant.id, email: tenant.email } },
      });

      const errorMessage = error instanceof Error ? error.message : 'Failed to send invitation';
      toast.error(errorMessage);
    } finally {
      setIsInviting(false);
    }
  };

  // Handle resending invitation
  const handleResend = async () => {
    if (!invitation) return;

    setIsInviting(true);

    try {
      const result = await resendTenantInvitation(invitation.id);

      if (result.success) {
        toast.success('Invitation resent successfully');
        await refetchInvitation();
      } else {
        toast.error(result.message || 'Failed to resend invitation');
      }
    } catch (error: unknown) {
      console.error('Failed to resend invitation:', error);

      Sentry.captureException(error, {
        tags: { component: 'ProfileHeader', action: 'resend_invitation' },
      });

      toast.error('Failed to resend invitation');
    } finally {
      setIsInviting(false);
    }
  };

  // Handle revoking invitation
  const handleRevoke = async () => {
    if (!invitation) return;

    setIsInviting(true);

    try {
      const result = await revokeTenantInvitation(invitation.id);

      if (result.success) {
        toast.success('Invitation revoked');
        await refetchInvitation();
      } else {
        toast.error(result.message || 'Failed to revoke invitation');
      }
    } catch (error: unknown) {
      console.error('Failed to revoke invitation:', error);

      Sentry.captureException(error, {
        tags: { component: 'ProfileHeader', action: 'revoke_invitation' },
      });

      toast.error('Failed to revoke invitation');
    } finally {
      setIsInviting(false);
    }
  };

  return (
    <div className="bg-white dark:bg-gray-800 border-b border-gray-200 dark:border-gray-700 px-6 py-6">
      <div className="flex items-start justify-between gap-6">
        {/* Left: Avatar and Info */}
        <div className="flex items-center gap-4 flex-1">
          {/* Avatar */}
          <div className="relative flex-shrink-0">
            {tenant.profile_image_url ? (
              <img
                src={tenant.profile_image_url}
                alt={getDisplayName()}
                className="w-20 h-20 rounded-full object-cover ring-4 ring-gray-100 dark:ring-gray-700"
              />
            ) : (
              <div className="w-20 h-20 rounded-full bg-gradient-to-br from-blue-500 to-blue-600 flex items-center justify-center ring-4 ring-gray-100 dark:ring-gray-700">
                <span className="text-white font-bold text-2xl">
                  {getInitials({ full_name: getDisplayName() })}
                </span>
              </div>
            )}
            {tenant.tenant_type === 'Company' && (
              <div className="absolute -bottom-1 -right-1 bg-blue-500 rounded-full p-1.5 ring-2 ring-white dark:ring-gray-800">
                <svg className="w-4 h-4 text-white" fill="currentColor" viewBox="0 0 20 20">
                  <path fillRule="evenodd" d="M4 4a2 2 0 012-2h8a2 2 0 012 2v12a1 1 0 110 2h-3a1 1 0 01-1-1v-2a1 1 0 00-1-1H9a1 1 0 00-1 1v2a1 1 0 01-1 1H4a1 1 0 110-2V4zm3 1h2v2H7V5zm2 4H7v2h2V9zm2-4h2v2h-2V5zm2 4h-2v2h2V9z" clipRule="evenodd" />
                </svg>
              </div>
            )}
          </div>

          {/* Name, Contact, and Property Info */}
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-3 mb-1">
              <h1 className="text-3xl font-bold text-gray-900 dark:text-gray-100">
                {getDisplayName()}
              </h1>
              <span className={getStatusBadgeClass(tenant.status)}>
                <span className="w-1.5 h-1.5 rounded-full bg-current mr-1.5"></span>
                {tenant.status}
              </span>
              {/* Portal Status Indicator */}
              <span className={`inline-flex items-center px-2.5 py-1 rounded-full text-xs font-medium ${portalStatus.bgClass} ${portalStatus.textClass}`}>
                {portalStatus.status === 'active' && (
                  <svg className="w-3 h-3 mr-1" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
                  </svg>
                )}
                {portalStatus.status === 'invited' && (
                  <svg className="w-3 h-3 mr-1" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 8l7.89 5.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
                  </svg>
                )}
                <span className="opacity-75 mr-1">Portal:</span>
                {portalStatus.label}
              </span>
            </div>

            <div className="flex flex-wrap items-center gap-x-6 gap-y-2 text-sm text-gray-600 dark:text-gray-400">
              {tenant.email && (
                <a
                  href={`mailto:${tenant.email}`}
                  className="flex items-center gap-1.5 hover:text-blue-600 dark:hover:text-blue-400 transition-colors"
                >
                  <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 8l7.89 5.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
                  </svg>
                  {tenant.email}
                </a>
              )}
              {tenant.phone && (
                <a
                  href={`tel:${tenant.phone}`}
                  className="flex items-center gap-1.5 hover:text-blue-600 dark:hover:text-blue-400 transition-colors"
                >
                  <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 5a2 2 0 012-2h3.28a1 1 0 01.948.684l1.498 4.493a1 1 0 01-.502 1.21l-2.257 1.13a11.042 11.042 0 005.516 5.516l1.13-2.257a1 1 0 011.21-.502l4.493 1.498a1 1 0 01.684.949V19a2 2 0 01-2 2h-1C9.716 21 3 14.284 3 6V5z" />
                  </svg>
                  {tenant.phone}
                </a>
              )}
              {getPropertyInfo() && (
                <div className="flex items-center gap-1.5">
                  <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-6 0a1 1 0 001-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 001 1m-6 0h6" />
                  </svg>
                  {getPropertyInfo()}
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Right: Action Buttons */}
        <div className="flex items-center gap-2 flex-shrink-0">
          <div 
            className="relative group"
            title={tenant.user_id ? undefined : "Tenant must have portal access to receive messages"}
          >
            <button
              onClick={handleMessage}
              disabled={!tenant.user_id}
              className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md text-sm transition-colors ${
                tenant.user_id
                  ? 'bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-600'
                  : 'bg-gray-100 dark:bg-gray-800 border border-gray-200 dark:border-gray-700 text-gray-400 dark:text-gray-500 cursor-not-allowed'
              }`}
            >
              <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
              </svg>
              Message
            </button>
            {!tenant.user_id && (
              <div className="absolute top-full left-1/2 -translate-x-1/2 mt-2 px-3 py-2 bg-gray-900 text-white text-xs rounded-lg whitespace-nowrap opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none z-10">
                Tenant must have portal access to receive messages
                <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-1 border-4 border-transparent border-b-gray-900"></div>
              </div>
            )}
          </div>

          <button
            onClick={handleNewTicket}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-md text-sm text-gray-700 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-gray-600 transition-colors"
          >
            <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
            </svg>
            New Ticket
          </button>

          <button
            onClick={handleUpload}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-md text-sm text-gray-700 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-gray-600 transition-colors"
          >
            <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
            </svg>
            Upload
          </button>

          <button
            onClick={handlePayment}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-green-600 text-white rounded-md text-sm hover:bg-green-700 transition-colors"
          >
            <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8c-1.657 0-3 .895-3 2s1.343 2 3 2 3 .895 3 2-1.343 2-3 2m0-8c1.11 0 2.08.402 2.599 1M12 8V7m0 1v8m0 0v1m0-1c-1.11 0-2.08-.402-2.599-1M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
            Payment
          </button>

          {/* More Menu */}
          <div className="relative">
            <button
              onClick={() => setShowMoreMenu(!showMoreMenu)}
              className="p-2 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-lg text-gray-700 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-gray-600 transition-colors"
            >
              <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 5v.01M12 12v.01M12 19v.01M12 6a1 1 0 110-2 1 1 0 010 2zm0 7a1 1 0 110-2 1 1 0 010 2zm0 7a1 1 0 110-2 1 1 0 010 2z" />
              </svg>
            </button>

            {showMoreMenu && (
              <>
                <div
                  className="fixed inset-0 z-10"
                  onClick={() => setShowMoreMenu(false)}
                />
                <div className="absolute right-0 mt-2 w-48 bg-white dark:bg-gray-700 rounded-lg shadow-lg border border-gray-200 dark:border-gray-600 z-20">
                  <button
                    onClick={() => {
                      onRefresh();
                      setShowMoreMenu(false);
                    }}
                    className="w-full text-left px-4 py-2 text-sm text-gray-700 dark:text-gray-200 hover:bg-gray-100 dark:hover:bg-gray-600 first:rounded-t-lg"
                  >
                    Refresh
                  </button>
                  <button
                    onClick={() => {
                      onEdit();
                      setShowMoreMenu(false);
                    }}
                    className="w-full text-left px-4 py-2 text-sm text-gray-700 dark:text-gray-200 hover:bg-gray-100 dark:hover:bg-gray-600"
                  >
                    Edit Tenant
                  </button>
                  <button
                    onClick={() => {
                      onDelete();
                      setShowMoreMenu(false);
                    }}
                    className="w-full text-left px-4 py-2 text-sm text-red-600 dark:text-red-400 hover:bg-gray-100 dark:hover:bg-gray-600 last:rounded-b-lg"
                  >
                    Delete Tenant
                  </button>
                </div>
              </>
            )}
          </div>
        </div>
      </div>

      {/* Dedicated Portal Invitation Section - Only show if tenant doesn't have portal access */}
      {!hasPortalAccess && (
        <div className="mt-4 pt-4 border-t border-gray-200 dark:border-gray-700">
          <div className="flex items-center justify-between gap-4">
            {/* Left: Portal Benefits Info */}
            <div className="flex-1">
              <div className="flex items-center gap-2">
                <svg className="w-4 h-4 text-green-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
                </svg>
                <h3 className="text-sm mb-1 font-semibold text-gray-900 dark:text-gray-100">
                  Tenant Portal Access
                </h3>
                <span className="text-sm text-gray-500 dark:text-gray-400">—</span>
                <p className="text-sm text-gray-600 dark:text-gray-400">
                  Give {tenant.first_name || 'this tenant'} access to:
                </p>
              </div>
              <div className="flex flex-wrap gap-x-4 text-sm text-gray-600 dark:text-gray-400 ml-6">
                <div className="flex items-center gap-1">
                  <svg className="w-3.5 h-3.5 text-green-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                  </svg>
                  <span>Pay rent online</span>
                </div>
                <div className="flex items-center gap-1">
                  <svg className="w-3.5 h-3.5 text-green-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                  </svg>
                  <span>Submit maintenance requests</span>
                </div>
                <div className="flex items-center gap-1">
                  <svg className="w-3.5 h-3.5 text-green-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                  </svg>
                  <span>View lease documents</span>
                </div>
                <div className="flex items-center gap-1">
                  <svg className="w-3.5 h-3.5 text-green-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                  </svg>
                  <span>Track payment history</span>
                </div>
              </div>
            </div>

            {/* Right: Invitation Status & Action */}
            <div className="flex-shrink-0 flex items-center">
              {/* Show current invitation status if pending */}
              {invitation && invitation.status === InvitationStatus.PENDING && isInvitationValid(invitation) ? (
                <div className="flex items-center gap-3">
                  <div className="text-right">
                    <div className="flex items-center gap-1.5 text-sm text-yellow-700 dark:text-yellow-400">
                      <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
                      </svg>
                      <span className="font-medium">Invitation Pending</span>
                    </div>
                    <p className="text-xs text-gray-500 dark:text-gray-400">
                      {getInvitationExpiryText(invitation)}
                    </p>
                  </div>
                  <div className="flex gap-2">
                    <button
                      onClick={handleResend}
                      disabled={isInviting}
                      className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-lg text-sm text-gray-700 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-gray-600 transition-colors disabled:opacity-50"
                    >
                      <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                      </svg>
                      Resend
                    </button>
                    <button
                      onClick={handleRevoke}
                      disabled={isInviting}
                      className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-white dark:bg-gray-700 border border-red-300 dark:border-red-600 rounded-lg text-sm text-red-600 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-900/20 transition-colors disabled:opacity-50"
                    >
                      <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                      </svg>
                      Revoke
                    </button>
                  </div>
                </div>
              ) : (
                <div className="flex flex-col items-center gap-1 mt-2">
                  {tenant.email ? (
                    <>
                      <button
                        onClick={handleInviteClick}
                        disabled={isInviting}
                        className="inline-flex items-center gap-2 px-4 py-2 bg-green-600 text-white rounded-lg text-sm font-medium hover:bg-green-700 transition-colors disabled:opacity-50"
                      >
                        {isInviting ? (
                          <>
                            <svg className="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
                              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                            </svg>
                            Sending...
                          </>
                        ) : (
                          <>
                            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 8l7.89 5.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
                            </svg>
                            Send Portal Invitation
                          </>
                        )}
                      </button>
                      <p className="text-xs text-gray-500 dark:text-gray-400 text-center min-h-[16px]">
                        {loadingSeatAvailability ? (
                          <span className="inline-block w-24 h-3 bg-gray-200 dark:bg-gray-700 rounded animate-pulse"></span>
                        ) : seatAvailability ? (
                          `${seatAvailability.available} portal seat${seatAvailability.available !== 1 ? 's' : ''} available`
                        ) : null}
                      </p>
                    </>
                  ) : (
                    <div className="text-center">
                      <button
                        disabled
                        className="inline-flex items-center gap-2 px-4 pt-4 bg-gray-100 dark:bg-gray-700 text-gray-400 dark:text-gray-500 rounded-lg text-sm font-medium cursor-not-allowed"
                      >
                        <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 8l7.89 5.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
                        </svg>
                        Send Portal Invitation
                      </button>
                      <p className="text-xs text-red-500 dark:text-red-400 mt-1">
                        Add email to send invitation
                      </p>
                    </div>
                  )}
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Seat Subscription Modal */}
      <SeatSubscriptionModal
        isOpen={showSeatModal}
        onClose={() => setShowSeatModal(false)}
        requiredSeats={1}
      />

      {/* Invite Confirmation Dialog */}
      {showInviteConfirm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
          {/* Backdrop */}
          <div
            className="absolute inset-0 bg-black/30"
            onClick={() => setShowInviteConfirm(false)}
          />

          {/* Dialog */}
          <div className="relative bg-white dark:bg-gray-800 rounded-xl shadow-xl max-w-sm w-full p-5 animate-in fade-in zoom-in-95 duration-200">
            {/* Icon */}
            <div className="flex items-center justify-center w-12 h-12 mx-auto mb-4 bg-brand-teal/10 rounded-full">
              <svg className="w-6 h-6 text-brand-teal" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 8l7.89 5.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
              </svg>
            </div>

            {/* Content */}
            <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100 text-center mb-2">
              Send Portal Invitation
            </h3>
            <p className="text-sm text-gray-600 dark:text-gray-400 text-center mb-4">
              An email invitation will be sent to <span className="font-medium text-gray-900 dark:text-gray-200">{tenant.email}</span> to join the Tenant Portal.
            </p>

            {/* Seat Info */}
            {seatAvailability && (
              <div className="bg-gray-50 dark:bg-gray-700/50 rounded-lg p-3 mb-4">
                <div className="flex items-center justify-between text-sm">
                  <span className="text-gray-600 dark:text-gray-400">Portal seats available</span>
                  <span className="font-medium text-gray-900 dark:text-gray-100">
                    {seatAvailability.available} of {seatAvailability.limit}
                  </span>
                </div>
                {seatAvailability.available <= 3 && seatAvailability.available > 0 && (
                  <p className="text-xs text-amber-600 dark:text-amber-400 mt-1">
                    Running low on seats
                  </p>
                )}
              </div>
            )}

            {/* Actions */}
            <div className="flex gap-3">
              <button
                onClick={() => setShowInviteConfirm(false)}
                className="flex-1 px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-300 bg-gray-100 dark:bg-gray-700 hover:bg-gray-200 dark:hover:bg-gray-600 rounded-lg transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={handleInviteConfirm}
                className="flex-1 px-4 py-2 text-sm font-medium text-white bg-green-600 hover:bg-green-700 rounded-lg transition-colors"
              >
                Send Invitation
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default TenantProfileHeader;
