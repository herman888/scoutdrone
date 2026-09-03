/**
 * Unit Type Helper Utilities
 * Provides icons, labels, colors, and field visibility logic for different unit types
 */

import { UnitType } from '../types/unit';

/**
 * Unit type display configuration
 */
interface UnitTypeConfig {
  icon: string;
  label: string;
  description: string;
  color: string;
  bgColor: string;
  textColor: string;
}

/**
 * Configuration for each unit type
 */
const UNIT_TYPE_CONFIGS: Record<UnitType, UnitTypeConfig> = {
  [UnitType.UNIT]: {
    icon: 'fa-solid fa-door-closed',
    label: 'Unit',
    description: 'Primary rentable space',
    color: 'blue',
    bgColor: 'bg-blue-100 dark:bg-blue-900/30',
    textColor: 'text-blue-800 dark:text-blue-300',
  },
  [UnitType.PARKING]: {
    icon: 'fa-solid fa-square-parking',
    label: 'Parking',
    description: 'Parking space or garage',
    color: 'purple',
    bgColor: 'bg-purple-100 dark:bg-purple-900/30',
    textColor: 'text-purple-800 dark:text-purple-300',
  },
  [UnitType.LOCKER]: {
    icon: 'fa-solid fa-lock',
    label: 'Locker',
    description: 'Storage locker',
    color: 'orange',
    bgColor: 'bg-orange-100 dark:bg-orange-900/30',
    textColor: 'text-orange-800 dark:text-orange-300',
  },
  [UnitType.STORAGE]: {
    icon: 'fa-solid fa-box',
    label: 'Storage',
    description: 'Storage room or unit',
    color: 'amber',
    bgColor: 'bg-amber-100 dark:bg-amber-900/30',
    textColor: 'text-amber-800 dark:text-amber-300',
  },
  [UnitType.LAND]: {
    icon: 'fa-solid fa-mountain',
    label: 'Land',
    description: 'Land parcel',
    color: 'green',
    bgColor: 'bg-green-100 dark:bg-green-900/30',
    textColor: 'text-green-800 dark:text-green-300',
  },
  [UnitType.OTHER]: {
    icon: 'fa-solid fa-circle-question',
    label: 'Other',
    description: 'Miscellaneous rentable asset',
    color: 'gray',
    bgColor: 'bg-gray-100 dark:bg-gray-700',
    textColor: 'text-gray-800 dark:text-gray-300',
  },
};

/**
 * Get icon for unit type
 */
export const getUnitTypeIcon = (unitType: UnitType): string => {
  return UNIT_TYPE_CONFIGS[unitType]?.icon || '❓';
};

/**
 * Get display label for unit type
 */
export const getUnitTypeLabel = (unitType: UnitType): string => {
  return UNIT_TYPE_CONFIGS[unitType]?.label || 'Unknown';
};

/**
 * Get description for unit type
 */
export const getUnitTypeDescription = (unitType: UnitType): string => {
  return UNIT_TYPE_CONFIGS[unitType]?.description || '';
};

/**
 * Get color for unit type badge
 */
export const getUnitTypeColor = (unitType: UnitType): string => {
  return UNIT_TYPE_CONFIGS[unitType]?.color || 'gray';
};

/**
 * Get background color class for unit type
 */
export const getUnitTypeBgColor = (unitType: UnitType): string => {
  return UNIT_TYPE_CONFIGS[unitType]?.bgColor || 'bg-gray-100 dark:bg-gray-700';
};

/**
 * Get text color class for unit type
 */
export const getUnitTypeTextColor = (unitType: UnitType): string => {
  return UNIT_TYPE_CONFIGS[unitType]?.textColor || 'text-gray-800 dark:text-gray-300';
};

/**
 * Get all unit type options for dropdowns
 */
export const getAllUnitTypeOptions = () => {
  return Object.values(UnitType).map((type) => ({
    value: type,
    label: getUnitTypeLabel(type),
    icon: getUnitTypeIcon(type),
    description: getUnitTypeDescription(type),
  }));
};

/**
 * Determine which fields should be visible for a given unit type
 */
export const shouldShowField = (unitType: UnitType, fieldName: string): boolean => {
  const fieldVisibility: Record<UnitType, Set<string>> = {
    [UnitType.UNIT]: new Set([
      'name',
      'floor',
      'monthly_rent',
      'description',
      'size',
      'property_specific_fields', // Show property-type-specific fields
    ]),
    [UnitType.PARKING]: new Set([
      'name',
      'floor',
      'monthly_rent',
      'description',
      'parking_specific_fields',
    ]),
    [UnitType.LOCKER]: new Set([
      'name',
      'floor',
      'size',
      'monthly_rent',
      'description',
      'storage_specific_fields',
    ]),
    [UnitType.STORAGE]: new Set([
      'name',
      'floor',
      'size',
      'monthly_rent',
      'description',
      'storage_specific_fields',
    ]),
    [UnitType.LAND]: new Set([
      'name',
      'size',
      'monthly_rent',
      'description',
      'land_specific_fields',
    ]),
    [UnitType.OTHER]: new Set([
      'name',
      'floor',
      'monthly_rent',
      'description',
      'size',
    ]),
  };

  return fieldVisibility[unitType]?.has(fieldName) || false;
};

/**
 * Get placeholder text for unit name based on unit type
 */
export const getUnitNamePlaceholder = (unitType: UnitType): string => {
  const placeholders: Record<UnitType, string> = {
    [UnitType.UNIT]: 'e.g., Unit 101, Suite A, Bay 3',
    [UnitType.PARKING]: 'e.g., P-15, Garage Spot 3',
    [UnitType.LOCKER]: 'e.g., Locker L-42',
    [UnitType.STORAGE]: 'e.g., Storage S-10',
    [UnitType.LAND]: 'e.g., Parcel A, Lot 5',
    [UnitType.OTHER]: 'e.g., Unit name',
  };

  return placeholders[unitType] || 'e.g., Unit name';
};
