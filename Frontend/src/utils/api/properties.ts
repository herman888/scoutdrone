/**
 * Property Management API Functions
 * 
 * Provides fully-typed API functions for property operations including CRUD,
 * filtering, and bulk operations.
 */

import { apiRequest } from './core';
import type {
  Property,
  PropertyCreatePayload,
  PropertyUpdatePayload,
} from '../../types/property';

/**
 * Property query parameters for filtering
 */
export interface PropertyQueryParams {
  owner_id?: string;
  property_type?: string;
}

/**
 * API request options with abort signal support
 */
export interface ApiRequestOptions {
  headers?: Record<string, string>;
  signal?: AbortSignal;
}

/**
 * Fetches properties from the API with optional filtering
 * 
 * Supports filtering by owner and property type. Results can be aborted
 * using an AbortController signal for better UX when navigating away.
 * 
 * @param params - Query parameters for filtering properties
 * @param options - Optional request options (headers, abort signal)
 * @returns Promise resolving to array of properties
 * 
 * @example
 * ```ts
 * // Fetch all properties
 * const properties = await fetchProperties();
 * 
 * // Fetch with filters
 * const residentialProps = await fetchProperties({
 *   property_type: 'Residential'
 * });
 * 
 * // Fetch with abort signal
 * const controller = new AbortController();
 * const properties = await fetchProperties({}, {
 *   signal: controller.signal
 * });
 * // Later: controller.abort();
 * ```
 */
export const fetchProperties = async (
  params: PropertyQueryParams = {},
  options: ApiRequestOptions = {}
): Promise<Property[]> => {
  const queryParams = new URLSearchParams();

  if (params.owner_id) {
    queryParams.append('owner_id', params.owner_id);
  }
  if (params.property_type) {
    queryParams.append('property_type', params.property_type);
  }

  const queryString = queryParams.toString();
  return apiRequest(`/properties/${queryString ? '?' + queryString : ''}`, options);
};

/**
 * Fetches a single property by ID
 * 
 * Returns complete property data including units, images, ownership entity,
 * and type-specific details. Used for property detail pages.
 * 
 * @param propertyId - The numeric or string ID of the property
 * @returns Promise resolving to property object
 * @throws Error if property doesn't exist or user lacks permission
 * 
 * @example
 * ```ts
 * const property = await fetchPropertyById('123');
 * console.log(property.name, property.units?.length);
 * ```
 */
export const fetchPropertyById = async (propertyId: string | number, signal?: AbortSignal): Promise<Property> => {
  return apiRequest(`/properties/${propertyId}`, { signal });
};

/**
 * Creates a new property
 * 
 * Creates a property with basic details and optional type-specific fields.
 * For Apartment Complexes, can optionally create units in the same request.
 * Returns the created property with a numeric ID.
 * 
 * @param propertyData - Complete property creation payload
 * @returns Promise resolving to the created property
 * @throws Error if validation fails or user lacks permission
 * 
 * @example
 * ```ts
 * const newProperty = await createProperty({
 *   name: '123 Main Street',
 *   address: '123 Main Street',
 *   city: 'Toronto',
 *   province: 'ON',
 *   postal_code: 'M1M 1M1',
 *   property_type: PropertyType.RESIDENTIAL,
 *   status: PropertyStatus.ACTIVE,
 *   type_specific_details: {
 *     bedrooms: 3,
 *     bathrooms: 2,
 *     square_feet: 1500
 *   }
 * });
 * console.log('Created property ID:', newProperty.id);
 * ```
 */
export const createProperty = async (propertyData: PropertyCreatePayload): Promise<Property> => {
  return apiRequest('/properties/', {
    method: 'POST',
    body: JSON.stringify(propertyData),
  });
};

/**
 * Updates an existing property
 * 
 * All fields are optional - only provided fields will be updated.
 * Type-specific details are merged, not replaced.
 * 
 * @param propertyId - The ID of the property to update
 * @param propertyData - Fields to update (partial update supported)
 * @returns Promise resolving to the updated property
 * @throws Error if property doesn't exist or user lacks permission
 * 
 * @example
 * ```ts
 * // Update just the name and description
 * const updated = await updateProperty(123, {
 *   name: '125 Main Street (Updated)',
 *   description: 'Recently renovated property'
 * });
 * 
 * // Update type-specific details
 * const updated = await updateProperty(123, {
 *   type_specific_details: {
 *     square_feet: 1600 // Will merge with existing details
 *   }
 * });
 * ```
 */
export const updateProperty = async (
  propertyId: number,
  propertyData: PropertyUpdatePayload
): Promise<Property> => {
  return apiRequest(`/properties/${propertyId}`, {
    method: 'PUT',
    body: JSON.stringify(propertyData),
  });
};

/**
 * Deletes a single property
 * 
 * Warning: This action cannot be undone. All associated data (units, leases,
 * images) may be cascaded depending on backend configuration.
 * 
 * @param propertyId - The ID of the property to delete
 * @returns Promise resolving when deletion completes (204 No Content)
 * @throws Error if property doesn't exist, has active leases, or user lacks permission
 * 
 * @example
 * ```ts
 * if (confirm('Are you sure you want to delete this property?')) {
 *   await deleteProperty(123);
 *   toast.success('Property deleted successfully');
 *   navigate('/properties');
 * }
 * ```
 */
export const deleteProperty = async (propertyId: number): Promise<void> => {
  return apiRequest(`/properties/${propertyId}`, {
    method: 'DELETE',
  });
};

/**
 * Deletes multiple properties in bulk
 * 
 * Warning: This action cannot be undone. All associated data for all
 * properties will be cascaded. The operation is atomic - either all
 * succeed or all fail.
 * 
 * @param propertyIds - Array of property IDs to delete
 * @returns Promise resolving when all deletions complete
 * @throws Error if any property has active leases or user lacks permission
 * 
 * @example
 * ```ts
 * const selectedIds = [123, 456, 789];
 * 
 * if (confirm(`Delete ${selectedIds.length} properties? This cannot be undone.`)) {
 *   try {
 *     await bulkDeleteProperties(selectedIds);
 *     toast.success(`${selectedIds.length} properties deleted successfully`);
 *     refreshPropertyList();
 *   } catch (error) {
 *     toast.error('Failed to delete properties: ' + error.message);
 *   }
 * }
 * ```
 */
export const bulkDeleteProperties = async (propertyIds: number[]): Promise<void> => {
  return apiRequest('/properties/bulk-delete-property', {
    method: 'DELETE',
    body: JSON.stringify({ property_ids: propertyIds }),
  });
};
