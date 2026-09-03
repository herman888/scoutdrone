import React from 'react';

/**
 * Type definitions for parking unit details
 */
interface ParkingUnitTypeDetails {
  unit_type?: 'Parking';
  space_number?: string;
  is_covered?: boolean;
  is_accessible?: boolean;
  ev_charging?: boolean;
  vehicle_type?: 'car' | 'motorcycle' | 'rv' | 'truck' | 'other';
  [key: string]: unknown;
}

interface UnitFormData {
  name: string;
  floor: string;
  monthly_rent: string;
  description: string;
  size: string;
  unit_type_details?: ParkingUnitTypeDetails;
  [key: string]: unknown;
}

interface ParkingUnitFieldsProps {
  formData: UnitFormData;
  setFormData: React.Dispatch<React.SetStateAction<UnitFormData>>;
  disabled?: boolean;
}

/**
 * ParkingUnitFields Component
 * Renders parking-specific fields for unit creation/editing
 */
const ParkingUnitFields: React.FC<ParkingUnitFieldsProps> = ({
  formData,
  setFormData,
  disabled = false,
}) => {
  // Initialize parking-specific details if not present
  const parkingDetails: ParkingUnitTypeDetails = {
    unit_type: 'Parking',
    ...((formData.unit_type_details as ParkingUnitTypeDetails) || {}),
  };

  // Handle changes to parking-specific fields
  const handleParkingDetailChange = (
    field: keyof ParkingUnitTypeDetails,
    value: unknown
  ) => {
    setFormData((prev) => ({
      ...prev,
      unit_type_details: {
        ...parkingDetails,
        [field]: value,
      },
    }));
  };

  return (
    <div className="space-y-4">
      <h3 className="text-sm font-medium text-gray-900 dark:text-gray-100 flex items-center gap-2">
        <i className="fa-solid fa-square-parking text-purple-600 dark:text-purple-400"></i>
        Parking Space Details
      </h3>

      {/* Vehicle Type */}
      <div>
        <label className="block text-sm font-medium text-gray-900 dark:text-gray-100 mb-1">
          Vehicle Type
          <span className="text-gray-600 dark:text-gray-300 font-normal ml-1">(optional)</span>
        </label>
        <select
          value={parkingDetails.vehicle_type || 'car'}
          onChange={(e) => handleParkingDetailChange('vehicle_type', e.target.value)}
          disabled={disabled}
          className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500 dark:bg-gray-700 dark:text-gray-100 disabled:bg-gray-100 dark:disabled:bg-gray-800 disabled:cursor-not-allowed"
        >
          <option value="car">Car</option>
          <option value="motorcycle">Motorcycle</option>
          <option value="truck">Truck</option>
          <option value="rv">RV</option>
          <option value="other">Other</option>
        </select>
      </div>

      {/* Parking Features - Checkboxes */}
      <div className="space-y-3 pt-2">
        <label className="block text-sm font-medium text-gray-900 dark:text-gray-100 mb-2">
          Parking Features
        </label>

        {/* Covered */}
        <div className="flex items-center">
          <input
            type="checkbox"
            id="is_covered"
            checked={parkingDetails.is_covered || false}
            onChange={(e) => handleParkingDetailChange('is_covered', e.target.checked)}
            disabled={disabled}
            className="h-4 w-4 text-blue-600 focus:ring-blue-500 border-gray-300 dark:border-gray-600 rounded disabled:opacity-50"
          />
          <label
            htmlFor="is_covered"
            className="ml-2 text-sm text-gray-900 dark:text-gray-100 flex items-center gap-2"
          >
            <i className="fa-solid fa-warehouse"></i> Covered/Garage
          </label>
        </div>

        {/* Accessible */}
        <div className="flex items-center">
          <input
            type="checkbox"
            id="is_accessible"
            checked={parkingDetails.is_accessible || false}
            onChange={(e) => handleParkingDetailChange('is_accessible', e.target.checked)}
            disabled={disabled}
            className="h-4 w-4 text-blue-600 focus:ring-blue-500 border-gray-300 dark:border-gray-600 rounded disabled:opacity-50"
          />
          <label
            htmlFor="is_accessible"
            className="ml-2 text-sm text-gray-900 dark:text-gray-100 flex items-center gap-2"
          >
            <i className="fa-solid fa-wheelchair"></i> Accessible Parking
          </label>
        </div>

        {/* EV Charging */}
        <div className="flex items-center">
          <input
            type="checkbox"
            id="ev_charging"
            checked={parkingDetails.ev_charging || false}
            onChange={(e) => handleParkingDetailChange('ev_charging', e.target.checked)}
            disabled={disabled}
            className="h-4 w-4 text-blue-600 focus:ring-blue-500 border-gray-300 dark:border-gray-600 rounded disabled:opacity-50"
          />
          <label
            htmlFor="ev_charging"
            className="ml-2 text-sm text-gray-900 dark:text-gray-100 flex items-center gap-2"
          >
            <i className="fa-solid fa-charging-station"></i> EV Charging Station
          </label>
        </div>
      </div>
    </div>
  );
};

export default ParkingUnitFields;
