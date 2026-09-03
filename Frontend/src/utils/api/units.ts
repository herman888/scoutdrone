/**
 * Unit Management API Functions
 * 
 * Provides fully-typed API functions for unit operations including CRUD,
 * search, bulk operations, and lease management.
 */

import { apiRequest } from './core';
import type { Unit, UnitCreateData, UnitUpdateData } from '../../types/unit';
import type { Lease } from '../../types/lease';
import type { BulkAssignmentResponse } from '../../types/unit';

/**
 * Unit search filters
 */
export interface UnitSearchFilters {
  min_rent?: number;
  max_rent?: number;
  bedrooms?: number;
  bathrooms?: number;
  is_rented?: boolean;
  property_id?: number;
}

/**
 * Pagination options for search
 */
export interface SearchOptions {
  skip?: number;
  limit?: number;
}

/**
 * Bulk unit creation payload
 */
export interface BulkUnitCreateData {
  units: UnitCreateData[];
}

/**
 * Bulk unit creation response
 */
export interface BulkUnitCreateResponse {
  total_units: number;
  successful_creations: number;
  failed_creations: number;
  errors?: Array<{
    unit_name: string;
    error_message: string;
  }>;
  created_units: Unit[];
}

/**
 * CSV assignment data structure
 */
export interface CSVAssignmentData {
  assignments: Array<{
    unit_id: number;
    tenant_id: number;
    lease_start_date: string;
    end_date: string;
    monthly_rent?: number;
    security_deposit: number;
  }>;
}

/**
 * Bulk assignment from CSV response
 */
export interface BulkCSVAssignmentResponse {
  total_assignments: number;
  successful_assignments: number;
  failed_assignments: number;
  errors?: Array<{
    unit_id: number;
    error_message: string;
  }>;
}

/**
 * Bulk assignment payload
 */
export interface BulkAssignmentPayload {
  unit_ids: number[];
  tenant_id: number;
  lease_start_date: string;
  end_date: string;
  monthly_rent: number | null;
  security_deposit: number;
  rent_due_day: number;
  late_fee_amount: number | null;
  late_fee_after_days: number | null;
  special_terms: string | null;
}

/**
 * Fetches all units for a specific property
 * 
 * @param propertyId - The ID of the property
 * @returns Promise resolving to array of units
 * @throws Error if the property doesn't exist or user lacks permission
 */
export const fetchPropertyUnits = async (propertyId: number): Promise<Unit[]> => {
  return apiRequest(`/properties/${propertyId}/units`);
};

/**
 * Fetches a single unit by ID
 * 
 * @param unitId - The ID of the unit
 * @returns Promise resolving to unit object
 * @throws Error if unit ID is missing, unit doesn't exist, or user lacks permission
 */
export const fetchUnitById = async (unitId: number): Promise<Unit> => {
  if (!unitId) {
    throw new Error('Unit ID is required to fetch unit details.');
  }
  return apiRequest(`/units/${unitId}`);
};

/**
 * Creates a new unit for a property
 * 
 * @param propertyId - The ID of the property
 * @param unitData - The unit creation data
 * @returns Promise resolving to the created unit
 * @throws Error if validation fails or user lacks permission
 * 
 * @example
 * ```ts
 * const newUnit = await createUnit(123, {
 *   name: 'Unit 101',
 *   monthly_rent: 1200,
 *   bedrooms: 2,
 *   bathrooms: 1
 * });
 * ```
 */
export const createUnit = async (propertyId: number, unitData: UnitCreateData): Promise<Unit> => {
  return apiRequest(`/properties/${propertyId}/units`, {
    method: 'POST',
    body: JSON.stringify(unitData),
  });
};

/**
 * Updates an existing unit
 * 
 * Automatically formats numeric values to ensure proper data types.
 * All fields are optional - only provided fields will be updated.
 * 
 * @param unitId - The ID of the unit to update
 * @param unitData - The fields to update
 * @returns Promise resolving to the updated unit
 * @throws Error if unit doesn't exist or user lacks permission
 * 
 * @example
 * ```ts
 * const updated = await updateUnit(456, {
 *   monthly_rent: 1300,
 *   description: 'Updated description'
 * });
 * ```
 */
export const updateUnit = async (unitId: number, unitData: UnitUpdateData): Promise<Unit> => {
  // Ensure numeric values are properly formatted
  // Keep all fields from unitData, only override specific numeric fields that need formatting
  const formattedData: UnitUpdateData = {
    ...unitData,
    ...(unitData.monthly_rent != null && { monthly_rent: parseFloat(String(unitData.monthly_rent)) }),
    ...(unitData.size != null && { size: parseFloat(String(unitData.size)) }),
    ...(unitData.bedrooms != null && { bedrooms: parseInt(String(unitData.bedrooms), 10) }),
    ...(unitData.bathrooms != null && { bathrooms: parseFloat(String(unitData.bathrooms)) }),
    ...(unitData.floor != null && { floor: parseInt(String(unitData.floor), 10) }),
    ...(unitData.tenant_id != null && { tenant_id: unitData.tenant_id }),
    // unit_type and unit_type_details preserved from spread
  };

  return apiRequest(`/units/${unitId}`, {
    method: 'PUT',
    body: JSON.stringify(formattedData),
  });
};

/**
 * Deletes a unit
 * 
 * Warning: This action cannot be undone. Associated data may be cascaded.
 * 
 * @param unitId - The ID of the unit to delete
 * @returns Promise resolving when deletion completes (204 No Content)
 * @throws Error if unit doesn't exist, is occupied, or user lacks permission
 */
export const deleteUnit = async (unitId: number): Promise<void> => {
  // The response will be null for 204 status, which is OK
  return apiRequest(`/units/${unitId}`, {
    method: 'DELETE',
  });
};

/**
 * Fetches the active lease for a unit
 * 
 * @param unitId - The ID of the unit
 * @returns Promise resolving to the active lease
 * @throws Error if unit ID is missing, unit doesn't exist, or no active lease found
 * 
 * @example
 * ```ts
 * try {
 *   const lease = await fetchUnitLease(789);
 *   console.log('Lease ends:', lease.end_date);
 * } catch (error) {
 *   // Handle no active lease case
 * }
 * ```
 */
export const fetchUnitLease = async (unitId: number, signal?: AbortSignal): Promise<Lease> => {
  if (!unitId) {
    throw new Error('Unit ID is required to fetch unit lease.');
  }
  return apiRequest(`/units/${unitId}/lease`, { signal });
};

/**
 * Search units with filters and pagination
 * 
 * @param filters - Search criteria (rent range, bedrooms, etc.)
 * @param options - Pagination options
 * @returns Promise resolving to array of matching units
 * 
 * @example
 * ```ts
 * const affordableUnits = await searchUnits({
 *   max_rent: 1500,
 *   bedrooms: 2,
 *   is_rented: false
 * }, {
 *   skip: 0,
 *   limit: 20
 * });
 * ```
 */
export const searchUnits = async (
  filters: UnitSearchFilters = {},
  options: SearchOptions = {}
): Promise<Unit[]> => {
  const { skip = 0, limit = 100 } = options;
  const params = new URLSearchParams();

  // Add pagination
  params.append('skip', String(skip));
  params.append('limit', String(limit));

  // Append query parameters to the URL
  const url = `/units/search?${params.toString()}`;

  return apiRequest(url, {
    method: 'POST',
    body: JSON.stringify(filters),
    headers: {
      'Content-Type': 'application/json',
    },
  });
};

/**
 * Bulk create multiple units for a property
 * 
 * Creates multiple units in a single transaction. If any unit fails validation,
 * the entire operation may be rolled back depending on backend configuration.
 * 
 * @param propertyId - The ID of the property
 * @param bulkData - Object containing array of units to create
 * @returns Promise resolving to creation results with success/failure counts
 * 
 * @example
 * ```ts
 * const result = await createUnitsBulk(123, {
 *   units: [
 *     { name: 'Unit 101', monthly_rent: 1200 },
 *     { name: 'Unit 102', monthly_rent: 1300 },
 *     { name: 'Unit 103', monthly_rent: 1250 }
 *   ]
 * });
 * console.log(`Created ${result.successful_creations} units`);
 * ```
 */
export const createUnitsBulk = async (
  propertyId: number,
  bulkData: BulkUnitCreateData
): Promise<BulkUnitCreateResponse> => {
  return apiRequest(`/properties/${propertyId}/units/bulk`, {
    method: 'POST',
    body: JSON.stringify(bulkData),
  });
};

/**
 * Bulk assign tenants to units via CSV data
 * 
 * Processes multiple tenant-to-unit assignments in a single operation.
 * Each assignment creates a new lease with the provided terms.
 * 
 * @param propertyId - The ID of the property
 * @param csvData - Object containing array of assignments from CSV
 * @returns Promise resolving to assignment results
 * 
 * @example
 * ```ts
 * const result = await bulkAssignFromCSV(123, {
 *   assignments: [
 *     {
 *       unit_id: 456,
 *       tenant_id: 789,
 *       lease_start_date: '2024-01-01',
 *       end_date: '2024-12-31',
 *       security_deposit: 1200
 *     }
 *   ]
 * });
 * ```
 */
export const bulkAssignFromCSV = async (
  propertyId: number,
  csvData: CSVAssignmentData
): Promise<BulkCSVAssignmentResponse> => {
  return apiRequest(`/properties/${propertyId}/units/bulk-assign-csv`, {
    method: 'POST',
    body: JSON.stringify(csvData),
  });
};

/**
 * Bulk assign a single tenant to multiple units
 * 
 * Creates identical leases for the selected tenant across all specified units.
 * All units must be vacant. The operation is atomic - either all succeed or all fail.
 * 
 * @param bulkData - Object containing unit IDs and tenant assignment data
 * @returns Promise resolving to assignment results with success/failure details
 * @throws Error if any unit is occupied or tenant doesn't exist
 * 
 * @example
 * ```ts
 * const result = await bulkAssignTenant({
 *   unit_ids: [101, 102, 103],
 *   tenant_id: 456,
 *   lease_start_date: '2024-01-01',
 *   end_date: '2025-01-01',
 *   monthly_rent: null, // Use unit's default rent
 *   security_deposit: 1500,
 *   rent_due_day: 1,
 *   late_fee_amount: 50,
 *   late_fee_after_days: 5,
 *   special_terms: 'No pets allowed'
 * });
 * 
 * if (result.successful_assignments > 0) {
 *   console.log(`Successfully assigned to ${result.successful_assignments} units`);
 * }
 * ```
 */
export const bulkAssignTenant = async (
  bulkData: BulkAssignmentPayload
): Promise<BulkAssignmentResponse> => {
  return apiRequest(`/units/bulk-assign`, {
    method: 'POST',
    body: JSON.stringify(bulkData),
  });
};
