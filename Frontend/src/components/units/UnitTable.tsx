import React from 'react';
import UnitStatusBadge from './UnitStatusBadge';
import type { UnitTableProps, UnitWithLease } from '../../types/unit';
import { getUnitTypeIcon, getUnitTypeBgColor, getUnitTypeTextColor } from '../../utils/unitTypeHelpers';
import { UnitType } from '../../types/unit';

/**
 * Formats a number as CAD currency
 */
const formatCurrency = (amount: number | null | undefined): string => {
  return new Intl.NumberFormat('en-CA', {
    style: 'currency',
    currency: 'CAD',
  }).format(amount || 0);
};

/**
 * Extracts tenant display name from unit
 * Handles both individual and company tenants
 */
const getTenantName = (unit: UnitWithLease): string => {
  if (!unit || typeof unit !== 'object') return 'Not assigned';
  const tenant = unit.tenant;
  if (!tenant || typeof tenant !== 'object') return 'Not assigned';

  // Handle company tenants first (normalize case for comparison)
  if (
    tenant.tenant_type?.toUpperCase() === 'COMPANY' &&
    tenant.company_name
  ) {
    return tenant.company_name;
  }

  // Handle individual tenants
  const name = [tenant.first_name, tenant.last_name].filter(Boolean).join(' ');

  // Fallback to company name if individual names are not available
  if (!name && tenant.company_name) {
    return tenant.company_name;
  }

  return name || 'Not assigned';
};

/**
 * Formats a date string for display
 */
const formatDate = (dateString: string | null | undefined): string => {
  if (!dateString) return 'N/A';
  const date = new Date(dateString);
  return date.toLocaleDateString('en-CA', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  });
};

/**
 * Formats floor number for display
 * Converts negative floors to basement notation (e.g., -1 → B1, -2 → B2)
 */
const formatFloor = (floor: number | null | undefined): string => {
  if (floor === null || floor === undefined) return 'N/A';
  if (floor === 0) return 'Ground';
  if (floor < 0) return `B${Math.abs(floor)}`;
  return floor.toString();
};

/**
 * Gets the lease end date display text for a unit
 * Handles loading, no lease, and active lease states
 */
const getLeaseEndDate = (unit: UnitWithLease): string => {
  // If unit has lease info attached, use it
  if (unit.lease?.end_date) {
    return formatDate(unit.lease.end_date);
  }
  // If unit is rented but lease fetch completed with no result
  if (unit.is_rented) {
    // lease === undefined means fetch is still in progress
    // lease === null means fetch completed but no lease found
    if (unit.lease === undefined) {
      return 'Loading...';
    }
    return 'No lease';
  }
  // Not rented
  return 'N/A';
};

/**
 * UnitTable Component
 * Displays a table of property units with actions for managing them
 */
const UnitTable: React.FC<UnitTableProps> = ({
  units,
  loading = false,
  error = null,
  onEdit,
  onDelete,
  onAssign,
  onViewLease,
  selectedUnits = [],
  onUnitSelect,
  onSelectAll,
}) => {
  // Calculate column count dynamically to avoid hardcoded colspan values
  // Columns: Selection, Type, Unit Number, Floor, Rent, Tenant, Lease Ends, Status, Actions
  const totalColumns = 9;

  const isUnitSelected = (unitId: number): boolean => {
    return selectedUnits.includes(unitId);
  };

  const isAllSelected = (): boolean => {
    if (!units || units.length === 0) return false;
    // Only consider vacant units for "select all" state
    const vacantUnits = units.filter((unit) => !unit.is_rented);
    return vacantUnits.length > 0 && vacantUnits.every((unit) => selectedUnits.includes(unit.id));
  };

  const isPartiallySelected = (): boolean => {
    if (!units || units.length === 0) return false;
    const vacantUnits = units.filter((unit) => !unit.is_rented);
    const selectedVacantUnits = vacantUnits.filter((unit) => selectedUnits.includes(unit.id));
    return selectedVacantUnits.length > 0 && selectedVacantUnits.length < vacantUnits.length;
  };

  const handleSelectUnit = (unitId: number): void => {
    if (onUnitSelect) {
      onUnitSelect(unitId);
    }
  };

  const handleSelectAll = (): void => {
    if (onSelectAll) {
      onSelectAll();
    }
  };

  if (loading) {
    return (
      <div className="p-8 text-center bg-white dark:bg-gray-800">
        <div className="inline-block animate-spin rounded-full h-8 w-8 border-t-2 border-b-2 border-blue-500 mb-2"></div>
        <p className="text-gray-600 dark:text-gray-400">Loading units...</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-8 text-center text-red-600 dark:text-red-400 bg-white dark:bg-gray-800">
        Error loading units: {error}
      </div>
    );
  }

  return (
    <div className="overflow-x-auto">
      <table className="data-table min-w-full">
        <thead>
          <tr>
            <th scope="col" className="text-center w-12 py-4">
              <div className="flex items-center justify-center">
                <input
                  type="checkbox"
                  className="h-4 w-4 text-blue-600 border-gray-300 dark:border-gray-600 rounded focus:ring-blue-500 dark:bg-gray-700"
                  checked={isAllSelected()}
                  ref={(input) => {
                    if (input) {
                      input.indeterminate = isPartiallySelected();
                    }
                  }}
                  onChange={handleSelectAll}
                  title="Select all vacant units"
                />
              </div>
            </th>
            <th scope="col" className="text-center py-4">
              Type
            </th>
            <th scope="col" className="text-center py-4">
              Unit Number
            </th>
            <th scope="col" className="text-center py-4">
              Floor
            </th>
            <th scope="col" className="text-center py-4">
              Rent
            </th>
            <th scope="col" className="text-center py-4">
              Tenant
            </th>
            <th scope="col" className="text-center py-4">
              Lease Ends
            </th>
            <th scope="col" className="text-center py-4">
              Status
            </th>
            <th scope="col" className="text-center py-4">
              Actions
            </th>
          </tr>
        </thead>
        <tbody>
          {units && units.length > 0 ? (
            units.map((unit) => (
              <tr
                key={unit.id}
                className={`data-table-row transition-colors ${
                  isUnitSelected(unit.id)
                    ? 'bg-blue-50 dark:bg-blue-900/20 border-blue-200 dark:border-blue-700'
                    : 'hover:bg-gray-50 dark:hover:bg-gray-700/50'
                }`}
              >
                <td className="px-6 py-4 whitespace-nowrap text-center">
                  <input
                    type="checkbox"
                    className={`h-4 w-4 border-gray-300 dark:border-gray-600 rounded focus:ring-blue-500 transition-colors duration-300 ${
                      isUnitSelected(unit.id)
                        ? 'text-blue-600 cursor-pointer dark:bg-gray-700'
                        : 'cursor-pointer dark:bg-gray-700'
                    }`}
                    checked={isUnitSelected(unit.id)}
                    onChange={() => handleSelectUnit(unit.id)}
                    title="Select unit"
                  />
                </td>
                <td className="px-6 py-4 whitespace-nowrap text-center">
                  <div className="flex justify-center">
                    <span
                      className={`inline-flex items-center justify-center w-8 h-8 rounded-lg ${getUnitTypeBgColor(
                        unit.unit_type || UnitType.UNIT
                      )} ${getUnitTypeTextColor(unit.unit_type || UnitType.UNIT)} transition-colors duration-300`}
                      title={unit.unit_type || UnitType.UNIT}
                    >
                      <i className={`${getUnitTypeIcon(unit.unit_type || UnitType.UNIT)} text-sm`}></i>
                    </span>
                  </div>
                </td>
                <td className="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-900 dark:text-gray-100 text-center transition-colors duration-300">
                  {unit.name || unit.id}
                </td>
                <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500 dark:text-gray-400 text-center transition-colors duration-300">
                  {formatFloor(unit.floor)}
                </td>
                <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500 dark:text-gray-400 text-center transition-colors duration-300">
                  {formatCurrency(unit.monthly_rent)}
                </td>
                <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500 dark:text-gray-400 text-center transition-colors duration-300">
                  <div className="truncate max-w-xs">{getTenantName(unit)}</div>
                </td>
                <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500 dark:text-gray-400 text-center transition-colors duration-300">
                  {getLeaseEndDate(unit)}
                </td>
                <td className="px-6 py-4 whitespace-nowrap text-center">
                  <UnitStatusBadge isRented={unit.is_rented} size="small" />
                </td>
                <td className="px-6 py-4 whitespace-nowrap text-center text-sm font-medium">
                  <div className="flex justify-center space-x-3">
                    {!unit.is_rented && onAssign && (
                      <button
                        onClick={() => onAssign(unit)}
                        className="text-green-600 hover:text-green-900 dark:text-green-400 dark:hover:text-green-300 disabled:opacity-50 transition-colors duration-300"
                      >
                        Assign
                      </button>
                    )}
                    {unit.is_rented && onViewLease && (
                      <button
                        onClick={() => onViewLease(unit.id)}
                        className="text-purple-600 hover:text-purple-900 dark:text-purple-400 dark:hover:text-purple-300 disabled:opacity-50 transition-colors duration-300"
                      >
                        View Lease
                      </button>
                    )}
                    <button
                      onClick={() => onEdit?.(unit.id)}
                      className="text-blue-600 hover:text-blue-900 dark:text-blue-400 dark:hover:text-blue-300 disabled:opacity-50 transition-colors duration-300"
                    >
                      Edit
                    </button>
                    <button
                      onClick={() => onDelete?.(unit.id)}
                      className="text-red-600 hover:text-red-900 dark:text-red-400 dark:hover:text-red-300 disabled:opacity-50 transition-colors duration-300"
                    >
                      Delete
                    </button>
                  </div>
                </td>
              </tr>
            ))
          ) : (
            <tr>
              <td
                colSpan={totalColumns}
                className="px-6 py-4 text-center text-sm text-gray-500 dark:text-gray-400 transition-colors duration-300"
              >
                No units found for this property.
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
};

export default UnitTable;
