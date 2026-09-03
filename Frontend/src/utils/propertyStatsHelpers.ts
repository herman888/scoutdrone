/**
 * Property Statistics Calculation Helpers
 * 
 * Centralized logic for calculating property statistics to ensure consistency
 * and reduce code duplication across components.
 */

import type { PropertyStats } from '../types/unit';

/**
 * Calculates updated property stats after a unit deletion
 * 
 * @param currentStats - Current property statistics
 * @param unitData - Data about the unit being deleted
 * @returns Updated statistics or null if currentStats was null/undefined
 */
export const calculateStatsAfterUnitDeletion = (
  currentStats: PropertyStats | null | undefined,
  unitData: {
    is_rented: boolean;
    monthly_rent?: number | null;
  }
): PropertyStats | null => {
  if (!currentStats) return null;

  return {
    ...currentStats,
    total_units: currentStats.total_units - 1,
    vacant_units: unitData.is_rented
      ? currentStats.vacant_units
      : currentStats.vacant_units - 1,
    occupied_units: unitData.is_rented
      ? currentStats.occupied_units - 1
      : currentStats.occupied_units,
    monthly_revenue:
      unitData.is_rented && unitData.monthly_rent
        ? Number((currentStats.monthly_revenue - unitData.monthly_rent).toFixed(2))
        : currentStats.monthly_revenue,
  };
};

/**
 * Calculates updated property stats after a unit creation
 * 
 * New units are always vacant initially.
 * 
 * @param currentStats - Current property statistics
 * @returns Updated statistics or null if currentStats was null/undefined
 */
export const calculateStatsAfterUnitCreation = (
  currentStats: PropertyStats | null | undefined
): PropertyStats | null => {
  if (!currentStats) return null;

  return {
    ...currentStats,
    total_units: currentStats.total_units + 1,
    vacant_units: currentStats.vacant_units + 1,
  };
};

/**
 * Calculates updated property stats after a unit rent change
 * 
 * Only recalculates monthly_revenue if the unit is currently rented.
 * 
 * @param currentStats - Current property statistics
 * @param originalRent - The unit's original monthly rent
 * @param newRent - The unit's new monthly rent
 * @param isRented - Whether the unit is currently rented
 * @returns Updated statistics or null if currentStats was null/undefined
 */
export const calculateStatsAfterRentChange = (
  currentStats: PropertyStats | null | undefined,
  originalRent: number | null | undefined,
  newRent: number | null | undefined,
  isRented: boolean
): PropertyStats | null => {
  if (!currentStats || !isRented) return currentStats || null;

  const oldRent = originalRent || 0;
  const rentAmount = newRent || 0;
  const rentDifference = rentAmount - oldRent;

  return {
    ...currentStats,
    monthly_revenue: Number((currentStats.monthly_revenue + rentDifference).toFixed(2)),
  };
};

