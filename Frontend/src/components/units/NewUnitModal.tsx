import React, { useState, useEffect } from 'react';
import { motion } from 'framer-motion';
import ResidentialUnitFields from './fields/ResidentialUnitFields';
import IndustrialUnitFields from './fields/IndustrialUnitFields';
import ParkingUnitFields from './fields/ParkingUnitFields';
import StorageUnitFields from './fields/StorageUnitFields';
import LandUnitFields from './fields/LandUnitFields';
import { UnitType, type Unit, type UnitCreateData } from '../../types/unit';
import {
  getAllUnitTypeOptions,
  getUnitTypeIcon,
  getUnitNamePlaceholder,
  shouldShowField,
  getUnitTypeLabel,
} from '../../utils/unitTypeHelpers';

interface UnitFormData {
  name: string;
  floor: string;
  monthly_rent: string;
  description: string;
  size: string;
  unit_type_details?: Record<string, unknown>;
  [key: string]: unknown;
}

interface NewUnitModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSubmit: (propertyId: string, unitData: UnitCreateData) => Promise<Unit>;
  propertyId: string;
  propertyType?: string;
  isLoading?: boolean;
}

const NewUnitModal: React.FC<NewUnitModalProps> = ({
  isOpen,
  onClose,
  onSubmit,
  propertyId,
  propertyType,
}) => {
  const [selectedUnitType, setSelectedUnitType] = useState<UnitType>(UnitType.UNIT);
  const [formData, setFormData] = useState<UnitFormData>({
    name: '',
    floor: '',
    monthly_rent: '',
    description: '',
    size: '',
    unit_type_details: {}
  });
  const [error, setError] = useState<string>('');
  const [isSubmitting, setIsSubmitting] = useState<boolean>(false);

  // Determine property-specific unit types
  const isIndustrialOrCommercial = propertyType === 'Industrial' || propertyType === 'Commercial';
  const isResidentialType = propertyType === 'Residential' || propertyType === 'Apartment Complex';

  /**
   * Get the discriminator value for unit_type_details based on unit type and property type
   */
  const getUnitTypeDetailsDiscriminator = (unitType: UnitType): string => {
    switch (unitType) {
      case UnitType.UNIT:
        // For generic "Unit" type, use property-specific discriminator
        if (isResidentialType) return 'Residential';
        if (isIndustrialOrCommercial) return 'Industrial';
        return 'Other'; // Fallback for other property types
      case UnitType.PARKING:
        return 'Parking';
      case UnitType.LOCKER:
      case UnitType.STORAGE:
        return 'Storage';
      case UnitType.LAND:
        return 'Land';
      case UnitType.OTHER:
        return 'Other';
      default:
        return 'Other';
    }
  };

  /**
   * Handle unit type selection change
   */
  const handleUnitTypeChange = (newUnitType: UnitType): void => {
    setSelectedUnitType(newUnitType);
    
    // Reset the entire form to its initial state to clear irrelevant fields
    const discriminator = getUnitTypeDetailsDiscriminator(newUnitType);
    setFormData({
      name: '',
      floor: '',
      monthly_rent: '',
      description: '',
      size: '',
      unit_type_details: { unit_type: discriminator }
    });
  };

  // Get all unit type options
  const unitTypeOptions = getAllUnitTypeOptions();

  // Reset form when modal opens or closes
  useEffect(() => {
    if (isOpen) {
      setError('');
      const defaultUnitType = UnitType.UNIT;
      setSelectedUnitType(defaultUnitType);
      
      // Initialize with correct discriminator
      const discriminator = getUnitTypeDetailsDiscriminator(defaultUnitType);
      setFormData({
        name: '',
        floor: '',
        monthly_rent: '',
        description: '',
        size: '',
        unit_type_details: { unit_type: discriminator }
      });
    }
  }, [isOpen, isResidentialType, isIndustrialOrCommercial]);

  // Handle form input changes for basic fields
  const handleChange = (
    e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>
  ): void => {
    const { name, value } = e.target;
    setFormData((prev) => ({
      ...prev,
      [name]: value,
    }));
  };

  // Handle form submission
  const handleSubmit = async (e: React.FormEvent<HTMLFormElement>): Promise<void> => {
    e.preventDefault();
    setError('');
    setIsSubmitting(true);

    try {
      // Validate required fields
      if (!formData.name) {
        setError('Unit name/number is required');
        setIsSubmitting(false);
        return;
      }

      // Floor is only required for UNIT type
      if (selectedUnitType === UnitType.UNIT && !formData.floor) {
        setError('Floor is required for units');
        setIsSubmitting(false);
        return;
      }

      // Validate type-specific required fields for UNIT type only
      if (selectedUnitType === UnitType.UNIT && isResidentialType) {
        if (!formData.unit_type_details?.bedrooms) {
          setError('Bedrooms is required for residential units');
          setIsSubmitting(false);
          return;
        }
        if (!formData.unit_type_details?.bathrooms) {
          setError('Bathrooms is required for residential units');
          setIsSubmitting(false);
          return;
        }
      }

      // Format numeric values and convert empty strings to undefined
      // TypeScript note: UnitCreateData expects optional fields as `undefined`, not `null`
      const formattedData: UnitCreateData = {
        name: formData.name,
        unit_type: selectedUnitType,
        floor: formData.floor ? parseInt(formData.floor, 10) : undefined,
        monthly_rent: formData.monthly_rent ? parseFloat(formData.monthly_rent) : undefined,
        description: formData.description || undefined,
        size: formData.size ? parseFloat(formData.size) : undefined,
        is_rented: false, // New units are always created as vacant
        unit_type_details: formData.unit_type_details || undefined,
      };

      // Call the parent component's submit handler
      await onSubmit(propertyId, formattedData);

      // Close the modal on success
      handleClose();
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : 'Failed to create unit';
      setError(errorMessage);
    } finally {
      setIsSubmitting(false);
    }
  };

  // Handle modal close
  const handleClose = (): void => {
    setFormData({
      name: '',
      floor: '',
      monthly_rent: '',
      description: '',
      size: '',
      unit_type_details: {}
    });
    setError('');
    onClose();
  };

  // Don't render anything if modal is not open
  if (!isOpen) return null;

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50 dark:bg-opacity-70 p-4"
      onClick={handleClose}
    >
      <motion.div
        initial={{ scale: 0.95, opacity: 0 }}
        animate={{ scale: 1, opacity: 1 }}
        exit={{ scale: 0.95, opacity: 0 }}
        transition={{ type: 'spring', stiffness: 300, damping: 30 }}
        className="relative w-full max-w-2xl bg-white dark:bg-gray-800 rounded-lg shadow-xl max-h-[90vh] flex flex-col overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header - Fixed */}
        <div className="px-6 py-4 border-b border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-900 flex justify-between items-center flex-shrink-0">
          <h2 className="text-xl font-semibold text-gray-900 dark:text-gray-100">
            Add New Unit
            {propertyType && (
              <span className="ml-2 text-sm font-normal text-gray-600 dark:text-gray-300">
                ({propertyType})
              </span>
            )}
          </h2>
          <button
            onClick={handleClose}
            className="text-gray-400 dark:text-gray-400 hover:text-gray-600 dark:hover:text-gray-200 transition-colors"
            aria-label="Close modal"
          >
            <svg
              className="h-6 w-6"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M6 18L18 6M6 6l12 12"
              />
            </svg>
          </button>
        </div>

        {/* Body - Scrollable */}
        <div className="p-6 bg-white dark:bg-gray-800 overflow-y-auto flex-1">
          {error && (
            <div className="mb-4 p-3 bg-red-50 dark:bg-red-900/50 border border-red-200 dark:border-red-800 text-red-700 dark:text-red-400 rounded-lg">
              <div className="flex items-center">
                <svg
                  className="h-5 w-5 text-red-500 dark:text-red-400 mr-2 flex-shrink-0"
                  viewBox="0 0 20 20"
                  fill="currentColor"
                >
                  <path
                    fillRule="evenodd"
                    d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z"
                    clipRule="evenodd"
                  />
                </svg>
                <span className="text-sm">{error}</span>
              </div>
            </div>
          )}

          <form onSubmit={handleSubmit} id="new-unit-form" className="space-y-4">
            {/* Unit Type Selector */}
            <div className="bg-blue-50 dark:bg-blue-900/20 rounded-lg p-4 border border-blue-200 dark:border-blue-700">
              <label htmlFor="unit_type" className="block text-sm font-medium text-gray-900 dark:text-gray-100 mb-2">
                Unit Type <span className="text-red-500 dark:text-red-400">*</span>
              </label>
              <select
                id="unit_type"
                value={selectedUnitType}
                onChange={(e) => handleUnitTypeChange(e.target.value as UnitType)}
                className="w-full px-4 py-2.5 border border-gray-300 dark:border-gray-600 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent transition-all bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100"
              >
                {unitTypeOptions.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label} - {option.description}
                  </option>
                ))}
              </select>
              <div className="flex items-center gap-2 mt-2">
                <i className={`${getUnitTypeIcon(selectedUnitType)} text-blue-600 dark:text-blue-400`}></i>
                <span className="text-sm text-gray-600 dark:text-gray-300">
                  {unitTypeOptions.find(opt => opt.value === selectedUnitType)?.description}
                </span>
              </div>
              <p className="text-xs text-gray-600 dark:text-gray-300 mt-2">
                Select the type of rentable asset you're adding
              </p>
            </div>

            {/* Unit Basic Information */}
            <div className="bg-white dark:bg-gray-800 rounded-lg p-4 shadow-sm border border-gray-200 dark:border-gray-700">
              <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-4">
                Basic Information
              </h3>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div>
                  <label htmlFor="name" className="block text-sm font-medium text-gray-900 dark:text-gray-100 mb-2">
                    {selectedUnitType === UnitType.UNIT ? 'Unit' : (
                      <>
                        <i className={`${getUnitTypeIcon(selectedUnitType)} mr-1`}></i>
                        {getUnitTypeLabel(selectedUnitType)}
                      </>
                    )} Name/Number <span className="text-red-500 dark:text-red-400">*</span>
                  </label>
                  <input
                    type="text"
                    id="name"
                    name="name"
                    value={formData.name}
                    onChange={handleChange}
                    placeholder={getUnitNamePlaceholder(selectedUnitType)}
                    className="w-full px-4 py-2.5 border border-gray-300 dark:border-gray-600 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent transition-all bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 placeholder-gray-400 dark:placeholder-gray-400"
                    required
                  />
                </div>

                {shouldShowField(selectedUnitType, 'floor') && (
                  <div>
                    <label htmlFor="floor" className="block text-sm font-medium text-gray-900 dark:text-gray-100 mb-2">
                      Floor {selectedUnitType === UnitType.UNIT && <span className="text-red-500 dark:text-red-400">*</span>}
                    </label>
                    <input
                      type="number"
                      id="floor"
                      name="floor"
                      value={formData.floor}
                      onChange={handleChange}
                      placeholder="e.g., -1 (Basement), 0 (Ground), 1, 2"
                      className="w-full px-4 py-2.5 border border-gray-300 dark:border-gray-600 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent transition-all bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 placeholder-gray-400 dark:placeholder-gray-400"
                      required={selectedUnitType === UnitType.UNIT}
                    />
                    <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
                      Use negative numbers for basement levels (e.g., -1 for B1, -2 for B2)
                    </p>
                  </div>
                )}

                <div>
                  <label htmlFor="monthly_rent" className="block text-sm font-medium text-gray-900 dark:text-gray-100 mb-2">
                    Monthly Rent ($)
                  </label>
                  <input
                    type="number"
                    id="monthly_rent"
                    name="monthly_rent"
                    value={formData.monthly_rent}
                    onChange={handleChange}
                    placeholder="e.g., 1200"
                    step="0.01"
                    min="0"
                    className="w-full px-4 py-2.5 border border-gray-300 dark:border-gray-600 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent transition-all bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 placeholder-gray-400 dark:placeholder-gray-400"
                  />
                </div>

                {shouldShowField(selectedUnitType, 'size') && (
                  <div>
                    <label htmlFor="size" className="block text-sm font-medium text-gray-900 dark:text-gray-100 mb-2">
                      Size ({selectedUnitType === UnitType.LAND ? 'acres' : 'sq ft'})
                    </label>
                    <input
                      type="number"
                      id="size"
                      name="size"
                      value={formData.size}
                      onChange={handleChange}
                      placeholder={selectedUnitType === UnitType.LAND ? 'e.g., 2.5' : 'e.g., 850'}
                      step="0.01"
                      min="0"
                      className="w-full px-4 py-2.5 border border-gray-300 dark:border-gray-600 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent transition-all bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 placeholder-gray-400 dark:placeholder-gray-400"
                    />
                  </div>
                )}
              </div>

              <div className="mt-4">
                <label htmlFor="description" className="block text-sm font-medium text-gray-900 dark:text-gray-100 mb-2">
                  Description
                </label>
                <textarea
                  id="description"
                  name="description"
                  value={formData.description}
                  onChange={handleChange}
                  placeholder="Additional details about the unit..."
                  rows={3}
                  className="w-full px-4 py-2.5 border border-gray-300 dark:border-gray-600 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent transition-all bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 placeholder-gray-400 dark:placeholder-gray-400"
                />
              </div>
            </div>

            {/* Type-Specific Fields */}
            {selectedUnitType === UnitType.UNIT ? (
              // For primary units, show property-type-specific fields
              isIndustrialOrCommercial ? (
                <IndustrialUnitFields
                  formData={formData}
                  setFormData={setFormData as React.Dispatch<React.SetStateAction<typeof formData>>}
                  disabled={isSubmitting}
                />
              ) : isResidentialType ? (
                <ResidentialUnitFields
                  formData={formData}
                  setFormData={setFormData as React.Dispatch<React.SetStateAction<typeof formData>>}
                  disabled={isSubmitting}
                />
              ) : (
                <div className="bg-yellow-50 dark:bg-yellow-900/20 border border-yellow-200 dark:border-yellow-800 rounded-lg p-4">
                  <p className="text-sm text-yellow-700 dark:text-yellow-400">
                    Property type &quot;{propertyType}&quot; does not have specific unit fields configured.
                    Only basic unit information will be saved.
                  </p>
                </div>
              )
            ) : selectedUnitType === UnitType.PARKING ? (
              <ParkingUnitFields
                formData={formData}
                setFormData={setFormData as React.Dispatch<React.SetStateAction<typeof formData>>}
                disabled={isSubmitting}
              />
            ) : selectedUnitType === UnitType.LOCKER || selectedUnitType === UnitType.STORAGE ? (
              <StorageUnitFields
                formData={formData}
                setFormData={setFormData as React.Dispatch<React.SetStateAction<typeof formData>>}
                disabled={isSubmitting}
                unitType={selectedUnitType}
              />
            ) : selectedUnitType === UnitType.LAND ? (
              <LandUnitFields
                formData={formData}
                setFormData={setFormData as React.Dispatch<React.SetStateAction<typeof formData>>}
                disabled={isSubmitting}
              />
            ) : null}

          </form>
        </div>

        {/* Footer - Fixed */}
        <div className="px-6 py-4 bg-gray-50 dark:bg-gray-900 border-t border-gray-200 dark:border-gray-700 flex justify-end space-x-3 flex-shrink-0">
          <button
            type="button"
            onClick={handleClose}
            className="px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-200 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-600 transition-colors"
            disabled={isSubmitting}
          >
            Cancel
          </button>
          <button
            type="submit"
            form="new-unit-form"
            className="px-4 py-2 text-sm font-medium text-white bg-blue-600 dark:bg-blue-500 rounded-lg hover:bg-blue-700 dark:hover:bg-blue-600 disabled:opacity-50 disabled:cursor-not-allowed transition-colors inline-flex items-center"
            disabled={isSubmitting}
          >
            {isSubmitting ? (
              <>
                <svg
                  className="animate-spin -ml-1 mr-3 h-5 w-5 text-white"
                  xmlns="http://www.w3.org/2000/svg"
                  fill="none"
                  viewBox="0 0 24 24"
                >
                  <circle
                    className="opacity-25"
                    cx="12"
                    cy="12"
                    r="10"
                    stroke="currentColor"
                    strokeWidth="4"
                  ></circle>
                  <path
                    className="opacity-75"
                    fill="currentColor"
                    d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
                  ></path>
                </svg>
                Creating Unit...
              </>
            ) : (
              'Create Unit'
            )}
          </button>
        </div>
      </motion.div>
    </motion.div>
  );
};

export default NewUnitModal;
