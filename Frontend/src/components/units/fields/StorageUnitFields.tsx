import React from 'react';
import { UnitType } from '../../../types/unit';

/**
 * Type definitions for storage/locker unit details
 */
interface StorageUnitTypeDetails {
  unit_type?: 'Storage' | 'Locker';
  locker_number?: string;
  is_climate_controlled?: boolean;
  has_power?: boolean;
  is_indoor?: boolean;
  access_code?: string;
  dimensions?: string;
  [key: string]: unknown;
}

interface UnitFormData {
  name: string;
  floor: string;
  monthly_rent: string;
  description: string;
  size: string;
  unit_type_details?: StorageUnitTypeDetails;
  [key: string]: unknown;
}

interface StorageUnitFieldsProps {
  formData: UnitFormData;
  setFormData: React.Dispatch<React.SetStateAction<UnitFormData>>;
  disabled?: boolean;
  unitType: UnitType.LOCKER | UnitType.STORAGE;
}

/**
 * StorageUnitFields Component
 * Renders storage/locker-specific fields for unit creation/editing
 */
const StorageUnitFields: React.FC<StorageUnitFieldsProps> = ({
  formData,
  setFormData,
  disabled = false,
  unitType,
}) => {
  // Initialize storage-specific details if not present
  const storageDetails: StorageUnitTypeDetails = {
    unit_type: unitType === UnitType.LOCKER ? 'Locker' : 'Storage',
    ...((formData.unit_type_details as StorageUnitTypeDetails) || {}),
  };

  const isLocker = unitType === UnitType.LOCKER;

  // Handle changes to storage-specific fields
  const handleStorageDetailChange = (
    field: keyof StorageUnitTypeDetails,
    value: unknown
  ) => {
    setFormData((prev) => ({
      ...prev,
      unit_type_details: {
        ...storageDetails,
        [field]: value,
      },
    }));
  };

  return (
    <div className="space-y-4">
      <h3 className="text-sm font-medium text-gray-900 dark:text-gray-100 flex items-center gap-2">
        <i className={`${isLocker ? 'fa-solid fa-lock text-orange-600 dark:text-orange-400' : 'fa-solid fa-box text-amber-600 dark:text-amber-400'}`}></i>
        {isLocker ? 'Locker' : 'Storage Unit'} Details
      </h3>

      {/* Dimensions */}
      <div>
        <label className="block text-sm font-medium text-gray-900 dark:text-gray-100 mb-1">
          Dimensions
          <span className="text-gray-600 dark:text-gray-300 font-normal ml-1">(optional)</span>
        </label>
        <input
          type="text"
          value={storageDetails.dimensions || ''}
          onChange={(e) => handleStorageDetailChange('dimensions', e.target.value)}
          placeholder="e.g., 5' x 10' x 8'"
          disabled={disabled}
          className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500 dark:bg-gray-700 dark:text-gray-100 placeholder-gray-400 dark:placeholder-gray-400 disabled:bg-gray-100 dark:disabled:bg-gray-800 disabled:cursor-not-allowed"
        />
        <p className="text-xs text-gray-600 dark:text-gray-300 mt-1">
          Width × Depth × Height
        </p>
      </div>

      {/* Access Code */}
      <div>
        <label className="block text-sm font-medium text-gray-900 dark:text-gray-100 mb-1">
          Access Code
          <span className="text-gray-600 dark:text-gray-300 font-normal ml-1">(optional)</span>
        </label>
        <input
          type="text"
          value={storageDetails.access_code || ''}
          onChange={(e) => handleStorageDetailChange('access_code', e.target.value)}
          placeholder="e.g., 1234#"
          disabled={disabled}
          className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500 dark:bg-gray-700 dark:text-gray-100 placeholder-gray-400 dark:placeholder-gray-400 disabled:bg-gray-100 dark:disabled:bg-gray-800 disabled:cursor-not-allowed"
        />
        <p className="text-xs text-gray-600 dark:text-gray-300 mt-1">
          Gate or door access code for tenant
        </p>
      </div>

      {/* Storage Features - Checkboxes */}
      <div className="space-y-3 pt-2">
        <label className="block text-sm font-medium text-gray-900 dark:text-gray-100 mb-2">
          Features
        </label>

        {/* Climate Controlled */}
        <div className="flex items-center">
          <input
            type="checkbox"
            id="is_climate_controlled"
            checked={storageDetails.is_climate_controlled || false}
            onChange={(e) => handleStorageDetailChange('is_climate_controlled', e.target.checked)}
            disabled={disabled}
            className="h-4 w-4 text-blue-600 focus:ring-blue-500 border-gray-300 dark:border-gray-600 rounded disabled:opacity-50"
          />
          <label
            htmlFor="is_climate_controlled"
            className="ml-2 text-sm text-gray-900 dark:text-gray-100 flex items-center gap-2"
          >
            <i className="fa-solid fa-temperature-half"></i> Climate Controlled
          </label>
        </div>

        {/* Indoor */}
        <div className="flex items-center">
          <input
            type="checkbox"
            id="is_indoor"
            checked={storageDetails.is_indoor || false}
            onChange={(e) => handleStorageDetailChange('is_indoor', e.target.checked)}
            disabled={disabled}
            className="h-4 w-4 text-blue-600 focus:ring-blue-500 border-gray-300 dark:border-gray-600 rounded disabled:opacity-50"
          />
          <label
            htmlFor="is_indoor"
            className="ml-2 text-sm text-gray-900 dark:text-gray-100 flex items-center gap-2"
          >
            <i className="fa-solid fa-building"></i> Indoor
          </label>
        </div>

        {/* Has Power */}
        <div className="flex items-center">
          <input
            type="checkbox"
            id="has_power"
            checked={storageDetails.has_power || false}
            onChange={(e) => handleStorageDetailChange('has_power', e.target.checked)}
            disabled={disabled}
            className="h-4 w-4 text-blue-600 focus:ring-blue-500 border-gray-300 dark:border-gray-600 rounded disabled:opacity-50"
          />
          <label
            htmlFor="has_power"
            className="ml-2 text-sm text-gray-900 dark:text-gray-100 flex items-center gap-2"
          >
            <i className="fa-solid fa-bolt"></i> Power Outlet
          </label>
        </div>
      </div>
    </div>
  );
};

export default StorageUnitFields;
