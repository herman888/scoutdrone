import React, { useMemo } from 'react';
import type { EnrichedTenant } from '../../../types/tenant';
import { TenantType } from '../../../types/tenant';
import type { Property } from '../../../types/property';

type RecipientType = 'tenant' | 'ownership_entity' | 'vendor';

interface OwnershipEntity {
  id: string;
  name: string;
  email?: string;
}

interface Vendor {
  id: number;
  company_name: string;
  contact_person?: string;
  email?: string;
}

interface RecipientSelectorProps {
  recipientType: RecipientType | null;
  selectedTenantId: string | number | null;
  selectedOwnershipEntityId: string | null;
  selectedVendorId: string | number | null;
  tenants: EnrichedTenant[];
  ownershipEntities: OwnershipEntity[];
  vendors: Vendor[];
  properties: Property[];
  propertyId?: string | number | null;
  onRecipientTypeChange: (type: RecipientType | null) => void;
  onTenantChange: (tenantId: number | null) => void;
  onOwnershipEntityChange: (entityId: string | null) => void;
  onVendorChange: (vendorId: number | null) => void;
  onPropertyChange: (propertyId: number | null) => void;
  errors?: Record<string, string>;
}

/**
 * RecipientSelector Component
 * 
 * Allows users to select invoice recipients from:
 * - Tenants (rent invoices, utilities, etc.)
 * - Ownership Entities (building expenses, ownership distributions)
 * - Vendors (vendor bills, reimbursements)
 * 
 * Implements the three-recipient-type system required for professional accounting.
 */
const RecipientSelector: React.FC<RecipientSelectorProps> = ({
  recipientType,
  selectedTenantId,
  selectedOwnershipEntityId,
  selectedVendorId,
  tenants,
  ownershipEntities,
  vendors,
  properties,
  propertyId,
  onRecipientTypeChange,
  onTenantChange,
  onOwnershipEntityChange,
  onVendorChange,
  onPropertyChange,
  errors = {},
}) => {
  // Helper to get tenant display name
  const getTenantDisplayName = (tenant: EnrichedTenant): string => {
    if (tenant.tenant_type === TenantType.COMPANY) {
      return tenant.company_name || 'Unnamed Company';
    }
    return `${tenant.first_name || ''} ${tenant.last_name || ''}`.trim() || 'Unnamed Tenant';
  };

  // Filter tenants based on selected property
  const filteredTenants = useMemo(() => {
    if (!propertyId) return tenants;
    
    const propertyIdStr = String(propertyId).trim();
    if (!propertyIdStr) return tenants;
    
    const selectedPropertyId = parseInt(propertyIdStr, 10);
    if (isNaN(selectedPropertyId)) return tenants;
    
    return tenants.filter(tenant => {
      // Check current unit assignment (tenant.unit is the enriched current unit)
      if (tenant.unit && Number(tenant.unit.property_id) === selectedPropertyId) {
        return true;
      }
      
      // Check property from top-level property field
      if (tenant.property && Number(tenant.property.id) === selectedPropertyId) {
        return true;
      }
      
      // Check units from leases
      if (tenant.leases && tenant.leases.length > 0) {
        return tenant.leases.some(lease => {
          // Check lease property directly
          if (lease.property && Number(lease.property.id) === selectedPropertyId) {
            return true;
          }
          // Check unit's property within lease
          if (lease.unit && lease.unit.property_id && Number(lease.unit.property_id) === selectedPropertyId) {
            return true;
          }
          return false;
        });
      }
      
      return false;
    });
  }, [tenants, propertyId]);

  return (
    <div>
      <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
        Invoice Recipient
      </h2>

      {/* Recipient Type Selection */}
      <div className="mb-4">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
          <button
            type="button"
            onClick={() => onRecipientTypeChange('tenant')}
            className={`px-4 py-3 rounded-lg border-2 transition-all ${
              recipientType === 'tenant'
                ? 'border-blue-500 bg-blue-50 dark:bg-blue-900/20 text-blue-700 dark:text-blue-300'
                : 'border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-700 dark:text-gray-300 hover:border-blue-300 dark:hover:border-blue-500'
            }`}
          >
            <div className="flex items-center justify-center space-x-2">
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
              </svg>
              <span className="font-medium">Tenant</span>
            </div>
            <p className="text-xs mt-1 opacity-75">Rent, utilities, charges</p>
          </button>

          <button
            type="button"
            onClick={() => onRecipientTypeChange('ownership_entity')}
            className={`px-4 py-3 rounded-lg border-2 transition-all ${
              recipientType === 'ownership_entity'
                ? 'border-blue-500 bg-blue-50 dark:bg-blue-900/20 text-blue-700 dark:text-blue-300'
                : 'border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-700 dark:text-gray-300 hover:border-blue-300 dark:hover:border-blue-500'
            }`}
          >
            <div className="flex items-center justify-center space-x-2">
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5M9 7h1m-1 4h1m4-4h1m-1 4h1m-5 10v-5a1 1 0 011-1h2a1 1 0 011 1v5m-4 0h4" />
              </svg>
              <span className="font-medium">Ownership</span>
            </div>
            <p className="text-xs mt-1 opacity-75">Building expenses</p>
          </button>

          <button
            type="button"
            onClick={() => onRecipientTypeChange('vendor')}
            className={`px-4 py-3 rounded-lg border-2 transition-all ${
              recipientType === 'vendor'
                ? 'border-blue-500 bg-blue-50 dark:bg-blue-900/20 text-blue-700 dark:text-blue-300'
                : 'border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-700 dark:text-gray-300 hover:border-blue-300 dark:hover:border-blue-500'
            }`}
          >
            <div className="flex items-center justify-center space-x-2">
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 13.255A23.931 23.931 0 0112 15c-3.183 0-6.22-.62-9-1.745M16 6V4a2 2 0 00-2-2h-4a2 2 0 00-2 2v2m4 6h.01M5 20h14a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
              </svg>
              <span className="font-medium">Vendor</span>
            </div>
            <p className="text-xs mt-1 opacity-75">Vendor bills, services</p>
          </button>
        </div>
        {errors.recipient_type && (
          <p className="mt-2 text-sm text-red-600 dark:text-red-400">{errors.recipient_type}</p>
        )}
      </div>

      {/* Property Selection (shown when any recipient type is selected) */}
      {recipientType && (
        <div className="mb-4">
          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
            Property (Optional)
          </label>
          <select
            value={propertyId || ''}
            onChange={(e) => onPropertyChange(e.target.value ? parseInt(e.target.value, 10) : null)}
            className="w-full px-3 py-2 border rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 dark:focus:ring-blue-400 bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 border-gray-300 dark:border-gray-600"
          >
            <option value="">None</option>
            {properties.filter(p => p.id !== undefined).map((property) => (
              <option key={property.id} value={property.id}>
                {property.name}
              </option>
            ))}
          </select>
          <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
            {recipientType === 'tenant' && 'Filter tenants by property'}
            {recipientType === 'ownership_entity' && 'Associate invoice with a specific property'}
            {recipientType === 'vendor' && 'Associate invoice with a specific property'}
          </p>
        </div>
      )}

      {/* Conditional Recipient Selection */}
      {recipientType === 'tenant' && (
        <div>
          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
            Select Tenant {propertyId && '(filtered by property)'}
          </label>
          <select
            value={selectedTenantId || ''}
            onChange={(e) => onTenantChange(e.target.value ? parseInt(e.target.value, 10) : null)}
            className={`w-full px-3 py-2 border rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 dark:focus:ring-blue-400 bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 ${
              errors.tenant_id ? 'border-red-300 dark:border-red-500' : 'border-gray-300 dark:border-gray-600'
            }`}
          >
            <option value="">Select a tenant...</option>
            {filteredTenants.map((tenant) => (
              <option key={tenant.id} value={tenant.id}>
                {getTenantDisplayName(tenant)}
                {tenant.assigned_units && tenant.assigned_units.length > 0 && (
                  ` - Unit ${tenant.assigned_units[0].name}`
                )}
              </option>
            ))}
          </select>
          {errors.tenant_id && (
            <p className="mt-1 text-sm text-red-600 dark:text-red-400">{errors.tenant_id}</p>
          )}
        </div>
      )}

      {recipientType === 'ownership_entity' && (
        <div>
          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
            Select Ownership Entity
          </label>
          <select
            value={selectedOwnershipEntityId || ''}
            onChange={(e) => onOwnershipEntityChange(e.target.value || null)}
            className={`w-full px-3 py-2 border rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 dark:focus:ring-blue-400 bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 ${
              errors.ownership_entity_id ? 'border-red-300 dark:border-red-500' : 'border-gray-300 dark:border-gray-600'
            }`}
          >
            <option value="">Select an ownership entity...</option>
            {ownershipEntities.map((entity) => (
              <option key={entity.id} value={entity.id}>
                {entity.name}
                {entity.email && ` (${entity.email})`}
              </option>
            ))}
          </select>
          {errors.ownership_entity_id && (
            <p className="mt-1 text-sm text-red-600 dark:text-red-400">{errors.ownership_entity_id}</p>
          )}
        </div>
      )}

      {recipientType === 'vendor' && (
        <div>
          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
            Select Vendor
          </label>
          <select
            value={selectedVendorId || ''}
            onChange={(e) => onVendorChange(e.target.value ? parseInt(e.target.value, 10) : null)}
            className={`w-full px-3 py-2 border rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 dark:focus:ring-blue-400 bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 ${
              errors.vendor_id ? 'border-red-300 dark:border-red-500' : 'border-gray-300 dark:border-gray-600'
            }`}
          >
            <option value="">Select a vendor...</option>
            {vendors.map((vendor) => (
              <option key={vendor.id} value={vendor.id}>
                {vendor.company_name}
                {vendor.contact_person && ` - ${vendor.contact_person}`}
              </option>
            ))}
          </select>
          {errors.vendor_id && (
            <p className="mt-1 text-sm text-red-600 dark:text-red-400">{errors.vendor_id}</p>
          )}
        </div>
      )}

    </div>
  );
};

export default RecipientSelector;
