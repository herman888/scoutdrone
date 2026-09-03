import React from 'react';

/**
 * Type definitions for land unit details
 * Note: Land size (acreage) is stored in the main 'size' field of the unit
 */
interface LandUnitTypeDetails {
  unit_type?: 'Land';
  parcel_number?: string;
  zoning?: string;
  utilities_available?: string[];
  has_road_access?: boolean;
  is_cleared?: boolean;
  topography?: 'flat' | 'rolling' | 'sloped' | 'hilly' | 'mixed';
  [key: string]: unknown;
}

interface UnitFormData {
  name: string;
  floor: string;
  monthly_rent: string;
  description: string;
  size: string;
  unit_type_details?: LandUnitTypeDetails;
  [key: string]: unknown;
}

interface LandUnitFieldsProps {
  formData: UnitFormData;
  setFormData: React.Dispatch<React.SetStateAction<UnitFormData>>;
  disabled?: boolean;
}

/**
 * LandUnitFields Component
 * Renders land-specific fields for unit creation/editing
 */
const LandUnitFields: React.FC<LandUnitFieldsProps> = ({
  formData,
  setFormData,
  disabled = false,
}) => {
  // Initialize land-specific details if not present
  const landDetails: LandUnitTypeDetails = {
    unit_type: 'Land',
    utilities_available: [],
    ...((formData.unit_type_details as LandUnitTypeDetails) || {}),
  };

  // Handle changes to land-specific fields
  const handleLandDetailChange = (
    field: keyof LandUnitTypeDetails,
    value: unknown
  ) => {
    setFormData((prev) => ({
      ...prev,
      unit_type_details: {
        ...(prev.unit_type_details as LandUnitTypeDetails),
        [field]: value,
      },
    }));
  };

  // Handle utility checkbox changes
  const handleUtilityChange = (utility: string, checked: boolean) => {
    const currentUtilities = landDetails.utilities_available || [];
    const newUtilities = checked
      ? [...currentUtilities, utility]
      : currentUtilities.filter((u) => u !== utility);
    
    handleLandDetailChange('utilities_available', newUtilities);
  };

  const availableUtilities = landDetails.utilities_available || [];

  return (
    <div className="space-y-4">
      <h3 className="text-sm font-medium text-gray-900 dark:text-gray-100 flex items-center gap-2">
        <i className="fa-solid fa-mountain text-green-600 dark:text-green-400"></i>
        Land Parcel Details
      </h3>

      {/* Zoning */}
      <div>
        <label className="block text-sm font-medium text-gray-900 dark:text-gray-100 mb-1">
          Zoning
          <span className="text-gray-600 dark:text-gray-300 font-normal ml-1">(optional)</span>
        </label>
        <input
          type="text"
          value={landDetails.zoning || ''}
          onChange={(e) => handleLandDetailChange('zoning', e.target.value)}
          placeholder="e.g., Residential, Agricultural, Commercial"
          disabled={disabled}
          className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500 dark:bg-gray-700 dark:text-gray-100 placeholder-gray-400 dark:placeholder-gray-400 disabled:bg-gray-100 dark:disabled:bg-gray-800 disabled:cursor-not-allowed"
        />
        <p className="text-xs text-gray-600 dark:text-gray-300 mt-1">
          Zoning classification
        </p>
      </div>

      {/* Topography */}
      <div>
        <label className="block text-sm font-medium text-gray-900 dark:text-gray-100 mb-1">
          Topography
          <span className="text-gray-600 dark:text-gray-300 font-normal ml-1">(optional)</span>
        </label>
        <select
          value={landDetails.topography || 'flat'}
          onChange={(e) => handleLandDetailChange('topography', e.target.value)}
          disabled={disabled}
          className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500 dark:bg-gray-700 dark:text-gray-100 disabled:bg-gray-100 dark:disabled:bg-gray-800 disabled:cursor-not-allowed"
        >
          <option value="flat">Flat</option>
          <option value="rolling">Rolling</option>
          <option value="sloped">Sloped</option>
          <option value="hilly">Hilly</option>
          <option value="mixed">Mixed</option>
        </select>
      </div>

      {/* Utilities Available - Checkboxes */}
      <div className="space-y-3 pt-2">
        <label className="block text-sm font-medium text-gray-900 dark:text-gray-100 mb-2">
          Utilities Available
        </label>

        <div className="flex items-center">
          <input
            type="checkbox"
            id="utility_water"
            checked={availableUtilities.includes('water')}
            onChange={(e) => handleUtilityChange('water', e.target.checked)}
            disabled={disabled}
            className="h-4 w-4 text-blue-600 focus:ring-blue-500 border-gray-300 dark:border-gray-600 rounded disabled:opacity-50"
          />
          <label htmlFor="utility_water" className="ml-2 text-sm text-gray-900 dark:text-gray-100 flex items-center gap-2">
            <i className="fa-solid fa-droplet"></i> Water
          </label>
        </div>

        <div className="flex items-center">
          <input
            type="checkbox"
            id="utility_electricity"
            checked={availableUtilities.includes('electricity')}
            onChange={(e) => handleUtilityChange('electricity', e.target.checked)}
            disabled={disabled}
            className="h-4 w-4 text-blue-600 focus:ring-blue-500 border-gray-300 dark:border-gray-600 rounded disabled:opacity-50"
          />
          <label htmlFor="utility_electricity" className="ml-2 text-sm text-gray-900 dark:text-gray-100 flex items-center gap-2">
            <i className="fa-solid fa-bolt"></i> Electricity
          </label>
        </div>

        <div className="flex items-center">
          <input
            type="checkbox"
            id="utility_gas"
            checked={availableUtilities.includes('gas')}
            onChange={(e) => handleUtilityChange('gas', e.target.checked)}
            disabled={disabled}
            className="h-4 w-4 text-blue-600 focus:ring-blue-500 border-gray-300 dark:border-gray-600 rounded disabled:opacity-50"
          />
          <label htmlFor="utility_gas" className="ml-2 text-sm text-gray-900 dark:text-gray-100 flex items-center gap-2">
            <i className="fa-solid fa-fire"></i> Natural Gas
          </label>
        </div>

        <div className="flex items-center">
          <input
            type="checkbox"
            id="utility_sewer"
            checked={availableUtilities.includes('sewer')}
            onChange={(e) => handleUtilityChange('sewer', e.target.checked)}
            disabled={disabled}
            className="h-4 w-4 text-blue-600 focus:ring-blue-500 border-gray-300 dark:border-gray-600 rounded disabled:opacity-50"
          />
          <label htmlFor="utility_sewer" className="ml-2 text-sm text-gray-900 dark:text-gray-100 flex items-center gap-2">
            <i className="fa-solid fa-water"></i> Sewer
          </label>
        </div>
      </div>

      {/* Land Features - Checkboxes */}
      <div className="space-y-3 pt-2">
        <label className="block text-sm font-medium text-gray-900 dark:text-gray-100 mb-2">
          Land Features
        </label>

        <div className="flex items-center">
          <input
            type="checkbox"
            id="has_road_access"
            checked={landDetails.has_road_access || false}
            onChange={(e) => handleLandDetailChange('has_road_access', e.target.checked)}
            disabled={disabled}
            className="h-4 w-4 text-blue-600 focus:ring-blue-500 border-gray-300 dark:border-gray-600 rounded disabled:opacity-50"
          />
          <label htmlFor="has_road_access" className="ml-2 text-sm text-gray-900 dark:text-gray-100 flex items-center gap-2">
            <i className="fa-solid fa-road"></i> Road Access
          </label>
        </div>

        <div className="flex items-center">
          <input
            type="checkbox"
            id="is_cleared"
            checked={landDetails.is_cleared || false}
            onChange={(e) => handleLandDetailChange('is_cleared', e.target.checked)}
            disabled={disabled}
            className="h-4 w-4 text-blue-600 focus:ring-blue-500 border-gray-300 dark:border-gray-600 rounded disabled:opacity-50"
          />
          <label htmlFor="is_cleared" className="ml-2 text-sm text-gray-900 dark:text-gray-100 flex items-center gap-2">
            <i className="fa-solid fa-tree"></i> Cleared Land
          </label>
        </div>
      </div>
    </div>
  );
};

export default LandUnitFields;
