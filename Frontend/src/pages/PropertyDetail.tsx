import React, { useState, useEffect, useCallback, useMemo } from 'react';
import { useParams } from 'react-router-dom';
import * as Sentry from '@sentry/react';
import {
  fetchPropertyById,
  createUnit,
  updateUnit,
  deleteUnit,
  fetchUnitLease,
} from '../utils/api';
import StatCard from '../components/StatCard';
import UnitTable from '../components/units/UnitTable';
import NewUnitModal from '../components/units/NewUnitModal';
import EditUnitModal from '../components/units/EditUnitModal';
import PropertyDetailSkeleton from '../components/ui/skeletons/PropertyDetailSkeleton';
import { toast } from 'react-toastify';
import 'react-toastify/dist/ReactToastify.css';
import AssignTenantModal from '../components/units/AssignTenantModal';
import BulkAssignTenantModal from '../components/units/BulkAssignTenantModal';
import CSVUploadModal from '../components/units/CSVUploadModal';
import ViewLeaseModal from '../components/leases/modals/ViewLeaseModal';
import {
  calculateStatsAfterUnitDeletion,
  calculateStatsAfterUnitCreation,
  calculateStatsAfterRentChange,
} from '../utils/propertyStatsHelpers';
import type {
  PropertyWithUnits,
  UnitWithLease,
  PropertyStats,
  Unit,
  UnitCreateData,
  UnitUpdateData,
} from '../types/unit';
import { UnitType } from '../types/unit';
import type { Lease } from '../types/lease';

/**
 * Raw unit data from API before lease enrichment
 */
interface RawUnit extends Unit {
  tenant?: {
    first_name?: string;
    last_name?: string;
    tenant_type?: string;
    company_name?: string;
  } | null;
}

/**
 * Raw property data from API before processing
 */
interface RawPropertyResponse {
  id: number;
  name: string;
  address?: string;
  city?: string;
  province?: string;
  postal_code?: string;
  property_type?: string;
  year_built?: number;
  description?: string;
  status?: string;
  user_id?: string;
  created_at?: string;
  updated_at?: string;
  units?: RawUnit[];
  stats?: PropertyStats | null;
}

// Icons for StatCards
const UnitIcon: React.FC = () => <i className="fas fa-door-closed text-blue-600"></i>;
const VacantIcon: React.FC = () => <i className="fas fa-door-open text-yellow-600"></i>;
const RevenueIcon: React.FC = () => <i className="fas fa-dollar-sign text-green-600"></i>;

/**
 * Unit data structure for edit modal compatibility
 */
interface EditableUnit {
  id: string;
  name: string;
  unit_type?: UnitType;
  floor?: number;
  description?: string;
  size?: number;
  monthly_rent?: number;
  is_rented?: boolean;
  bedrooms?: number;
  bathrooms?: number;
  unit_type_details?: Record<string, unknown>;
  tenant?: {
    first_name: string;
    last_name: string;
  };
}

/**
 * PropertyDetail Page Component
 * Displays detailed information about a property including units, stats, and management actions
 */
const PropertyDetail: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const [property, setProperty] = useState<PropertyWithUnits | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  // Create unit modal states
  const [isCreateModalOpen, setIsCreateModalOpen] = useState<boolean>(false);
  const [isSubmitting, setIsSubmitting] = useState<boolean>(false);

  // Edit unit modal states
  const [isEditModalOpen, setIsEditModalOpen] = useState<boolean>(false);
  const [unitToEdit, setUnitToEdit] = useState<EditableUnit | null>(null);

  // Assign tenant modal states
  const [isAssignModalOpen, setIsAssignModalOpen] = useState<boolean>(false);
  const [currentUnit, setCurrentUnit] = useState<UnitWithLease | null>(null);

  // View lease modal states
  const [isViewLeaseModalOpen, setIsViewLeaseModalOpen] = useState<boolean>(false);
  const [leaseToView, setLeaseToView] = useState<Lease | null>(null);
  const [tenantNameForLease, setTenantNameForLease] = useState<string>('');

  // Unit selection and bulk operations state
  const [selectedUnits, setSelectedUnits] = useState<number[]>([]);
  const [showBulkAssignModal, setShowBulkAssignModal] = useState<boolean>(false);
  const [showCSVUploadModal, setShowCSVUploadModal] = useState<boolean>(false);

  const loadProperty = useCallback(
    async (signal?: AbortSignal) => {
      if (!id) return;

      try {
        setLoading(true);
        setError(null);
        console.log(`Fetching property details for ID: ${id}`);

        // Pass abort signal to API request for cancellation support
        const data = (await fetchPropertyById(id, signal)) as RawPropertyResponse;
        
        // Check if request was aborted after awaiting
        if (signal?.aborted) return;
        
        console.log('Property data received:', data);

        // Fetch lease data for rented units
        let processedUnits: UnitWithLease[] | undefined;
        if (data.units && data.units.length > 0) {
          processedUnits = await Promise.all(
            data.units.map(async (unit: RawUnit): Promise<UnitWithLease> => {
              // Check abort signal before each lease fetch
              if (signal?.aborted) {
                return { ...unit, lease: null } as UnitWithLease;
              }

              if (unit.is_rented) {
                try {
                  const lease = await fetchUnitLease(unit.id, signal);
                  return { ...unit, lease } as UnitWithLease;
                } catch (leaseError) {
                  // Handle abort errors silently - user navigated away
                  if (leaseError instanceof Error && leaseError.name === 'AbortError') {
                    return { ...unit, lease: null } as UnitWithLease;
                  }

                  /**
                   * Lease Fetch Error Handling Strategy
                   *
                   * DECISION: Treat lease fetch failures the same as "no lease found"
                   *
                   * RATIONALE:
                   * - Most common case: Unit is marked rented but lease hasn't been created yet
                   * - Network failures are rare and logged to Sentry for investigation
                   * - Showing error state would create false alarms for users
                   *
                   * TRADEOFFS:
                   * ✅ Better UX: No scary error messages for expected scenarios
                   * ✅ Graceful degradation: Page remains functional even with partial data
                   * ❌ Masking issues: Real API failures are invisible to users
                   *
                   * ALTERNATIVES CONSIDERED:
                   * 1. Show error toast → Too noisy when multiple units fail
                   * 2. Add retry button → Adds complexity, users can refresh page
                   * 3. Display warning badge → Considered but deprioritized
                   *
                   * MONITORING: All failures logged to Sentry with unit context
                   */
                  Sentry.captureException(leaseError, {
                    tags: {
                      component: 'PropertyDetail',
                      action: 'fetch_unit_lease',
                      unitId: String(unit.id),
                    },
                    contexts: {
                      business: {
                        feature: 'property_management',
                        operation: 'lease_enrichment',
                      },
                    },
                  });

                  return { ...unit, lease: null } as UnitWithLease;
                }
              }
              return { ...unit, lease: null } as UnitWithLease;
            })
          );
        }

        // Final abort check before setting state
        if (signal?.aborted) return;

        const propertyWithUnits: PropertyWithUnits = {
          ...data,
          units: processedUnits,
          stats: data.stats,
        };

        setProperty(propertyWithUnits);
      } catch (err) {
        // Silently handle abort errors - user navigated away
        if (err instanceof Error && err.name === 'AbortError') {
          console.log('Property fetch aborted - user navigated away');
          return;
        }

        console.error('Error fetching property details:', err);
        setError(err instanceof Error ? err.message : 'Failed to load property details.');
      } finally {
        // Only update loading state if not aborted
        if (!signal?.aborted) {
          setLoading(false);
        }
      }
    },
    [id]
  );

  useEffect(() => {
    // Create AbortController for request cancellation
    const abortController = new AbortController();

    // Load property data with abort signal
    loadProperty(abortController.signal);

    // Cleanup: abort all pending requests when component unmounts or id changes
    return () => {
      abortController.abort();
      console.log(`Aborted property fetch for ID: ${id}`);
    };
  }, [id, loadProperty]);

  const formatCurrency = (amount: number | string | null | undefined): string => {
    return new Intl.NumberFormat('en-CA', {
      style: 'currency',
      currency: 'CAD',
    }).format(Number(amount) || 0);
  };

  // Function to handle unit editing
  const handleEditUnit = (unitId: number): void => {
    if (!property || !property.units) return;

    // Find the unit in the property data
    const unit = property.units.find((u) => u.id === unitId);
    if (!unit) {
      console.error(`Unit with ID ${unitId} not found`);
      return;
    }

    // Convert to EditableUnit format for the modal
    const editableUnit: EditableUnit = {
      id: String(unit.id),
      name: unit.name,
      unit_type: unit.unit_type ?? UnitType.UNIT, // Include unit type!
      floor: unit.floor ?? undefined,
      description: unit.description ?? undefined,
      size: unit.size ?? undefined,
      monthly_rent: unit.monthly_rent ?? undefined,
      is_rented: unit.is_rented,
      bedrooms: unit.bedrooms ?? undefined,
      bathrooms: unit.bathrooms ?? undefined,
      unit_type_details: unit.unit_type_details,
      tenant: unit.tenant
        ? {
            first_name: unit.tenant.first_name || '',
            last_name: unit.tenant.last_name || '',
          }
        : undefined,
    };

    // Set up the edit modal
    setUnitToEdit(editableUnit);
    setIsEditModalOpen(true);
  };

  // Function to handle unit deletion with optimistic updates
  const handleDeleteUnit = async (unitId: number): Promise<void> => {
    if (
      !window.confirm(
        'Are you sure you want to delete this unit? This action cannot be undone.'
      )
    ) {
      return;
    }

    // Store original property state for rollback
    const originalProperty = property;
    const unitToDelete = property?.units?.find((u) => u.id === unitId);

    try {
      setIsSubmitting(true);
      console.log(`Deleting unit with ID: ${unitId}`);

      // Optimistically remove the unit from local state
      setProperty((prev) => {
        if (!prev) return prev;

        const newStats = unitToDelete
          ? calculateStatsAfterUnitDeletion(prev.stats, unitToDelete)
          : prev.stats;

        return {
          ...prev,
          units: prev.units?.filter((unit) => unit.id !== unitId),
          stats: newStats,
        };
      });

      // Call API to delete the unit
      await deleteUnit(unitId);

      // Show success notification
      toast.success('Unit deleted successfully');

      // Refresh property data in the background for consistency
      loadProperty();
    } catch (err) {
      console.error('Error deleting unit:', err);

      // Rollback to original state on error
      setProperty(originalProperty);

      toast.error(err instanceof Error ? err.message : 'Failed to delete unit');
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleAddNewUnit = (): void => {
    // Open create modal
    setIsCreateModalOpen(true);
  };

  // Function to handle unit creation with optimistic updates
  const handleCreateUnit = async (
    propertyId: string,
    unitData: UnitCreateData
  ): Promise<Unit> => {
    try {
      setIsSubmitting(true);
      console.log('Creating new unit with data:', unitData);

      // Call API to create the unit
      const result = await createUnit(Number(propertyId), unitData);

      // Optimistically add the new unit to the property
      setProperty((prev) => {
        if (!prev) return prev;

        return {
          ...prev,
          units: [...(prev.units || []), result as UnitWithLease],
          stats: calculateStatsAfterUnitCreation(prev.stats),
        };
      });

      // Show success notification
      toast.success('Unit created successfully');

      // Close modal
      setIsCreateModalOpen(false);

      // Refresh property data in the background for consistency
      loadProperty();

      return result;
    } catch (err) {
      console.error('Error creating unit:', err);

      // Display a more user-friendly error
      const errorMessage = err instanceof Error ? err.message : 'Failed to create unit';
      toast.error(errorMessage);

      // Re-throw so the modal can handle display of the error
      throw err;
    } finally {
      setIsSubmitting(false);
    }
  };

  // Function to handle unit update with optimistic updates
  const handleUpdateUnit = async (unitId: string, unitData: UnitUpdateData): Promise<Unit> => {
    // Store original property state for rollback
    const originalProperty = property;
    const numericUnitId = parseInt(unitId, 10);
    const originalUnit = property?.units?.find((u) => u.id === numericUnitId);

    try {
      setIsSubmitting(true);
      console.log(`Updating unit ${unitId} with data:`, unitData);

      // Optimistically update the unit in local state and recalculate stats
      setProperty((prev) => {
        if (!prev) return prev;

        const updatedUnits = prev.units?.map((unit) =>
          unit.id === numericUnitId
            ? ({ ...unit, ...unitData, lease: unit.lease } as UnitWithLease)
            : unit
        );

        // Recalculate monthly revenue if rent changed for rented units
        const newStats =
          unitData.monthly_rent !== undefined && originalUnit
            ? calculateStatsAfterRentChange(
                prev.stats,
                originalUnit.monthly_rent,
                unitData.monthly_rent,
                originalUnit.is_rented
              )
            : prev.stats;

        return {
          ...prev,
          units: updatedUnits,
          stats: newStats,
        };
      });

      // Close modal immediately for better UX
      setIsEditModalOpen(false);
      setUnitToEdit(null);

      // Call API to update the unit
      const result = await updateUnit(numericUnitId, unitData);

      // Show success notification
      toast.success('Unit updated successfully');

      // Refresh property data in the background for consistency
      loadProperty();

      return result;
    } catch (err) {
      console.error('Error updating unit:', err);

      // Rollback to original state on error
      setProperty(originalProperty);

      // Display a more user-friendly error
      const errorMessage = err instanceof Error ? err.message : 'Failed to update unit';
      toast.error(errorMessage);

      // Re-throw so the modal can handle display of the error
      throw err;
    } finally {
      setIsSubmitting(false);
    }
  };

  // Function to handle assign tenant action
  const handleAssignTenant = (unit: UnitWithLease): void => {
    setCurrentUnit(unit);
    setIsAssignModalOpen(true);
  };

  // Function to handle view lease action
  const handleViewLease = async (unitId: number): Promise<void> => {
    try {
      // Fetch the lease for this unit
      const lease = await fetchUnitLease(unitId);
      
      // Set tenant name for display using lease.tenant (most up-to-date)
      if (lease.tenant) {
        const tenantName = lease.tenant.first_name && lease.tenant.last_name
          ? `${lease.tenant.first_name} ${lease.tenant.last_name}`
          : lease.tenant.company_name || 'N/A';
        setTenantNameForLease(tenantName);
      } else {
        setTenantNameForLease('');
      }
      
      setLeaseToView(lease);
      setIsViewLeaseModalOpen(true);
    } catch (error) {
      console.error('Failed to fetch lease:', error);
      toast.error('Failed to load lease details');
      Sentry.captureException(error, {
        tags: {
          component: 'PropertyDetail',
          action: 'view_lease',
        },
      });
    }
  };

  // Function to refresh data after tenant assignment
  const handleTenantAssigned = async (createdLease: Lease): Promise<void> => {
    console.log('[PropertyDetail] handleTenantAssigned called with lease:', createdLease);

    // Show success notification immediately
    toast.success('Lease created and tenant assigned successfully');

    // Refresh property data from server to ensure consistency
    await loadProperty();
  };

  // Close the assign tenant modal
  const handleCloseAssignModal = (): void => {
    setIsAssignModalOpen(false);
    setCurrentUnit(null);
  };

  // Close the create modal
  const handleCloseCreateModal = (): void => {
    setIsCreateModalOpen(false);
  };

  // Close the edit modal
  const handleCloseEditModal = (): void => {
    setIsEditModalOpen(false);
    setUnitToEdit(null);
  };

  const handleUnitSelect = (unitId: number): void => {
    setSelectedUnits((prev) => {
      if (prev.includes(unitId)) {
        return prev.filter((id) => id !== unitId);
      } else {
        return [...prev, unitId];
      }
    });
  };

  const handleSelectAll = (): void => {
    if (!property?.units) return;

    // Select all units (both vacant and occupied)
    const allUnitIds = property.units.map((unit) => unit.id);

    const allSelected = allUnitIds.every((id) => selectedUnits.includes(id));

    if (allSelected) {
      setSelectedUnits([]); // Deselect all
    } else {
      setSelectedUnits(allUnitIds); // Select all units
    }
  };

  const handleBulkAssign = (): void => {
    // Filter to only vacant units for bulk assignment
    const vacantUnits = property?.units?.filter(
      (unit) => selectedUnits.includes(unit.id) && !unit.is_rented
    ) || [];

    if (vacantUnits.length === 0) {
      toast.warning('Please select vacant units to assign tenants to');
      return;
    }
    setShowBulkAssignModal(true);
  };

  const handleBulkDelete = async (): Promise<void> => {
    if (selectedUnits.length === 0) {
      toast.warning('Please select units to delete');
      return;
    }

    // Confirmation dialog
    const confirmed = window.confirm(
      `Are you sure you want to delete ${selectedUnits.length} unit${selectedUnits.length !== 1 ? 's' : ''}? This action cannot be undone.`
    );

    if (!confirmed) return;

    try {
      setIsSubmitting(true);

      // Attempt to delete all selected units
      const results = await Promise.allSettled(
        selectedUnits.map((unitId) => deleteUnit(unitId))
      );

      const successfulDeletions = results
        .map((result, index) => ({ result, unitId: selectedUnits[index] }))
        .filter(({ result }) => result.status === 'fulfilled');

      const successfulIds = new Set(successfulDeletions.map(({ unitId }) => unitId));

      // Update local state optimistically only for successful deletions
      if (property && successfulIds.size > 0) {
        const remainingUnits = property.units?.filter(
          (unit) => !successfulIds.has(unit.id)
        );

        // Recalculate stats based on successfully deleted units
        let updatedStats = property.stats;
        if (property.units) {
          const deletedUnits = property.units.filter((unit) =>
            successfulIds.has(unit.id)
          );
          deletedUnits.forEach((unit) => {
            updatedStats = calculateStatsAfterUnitDeletion(updatedStats, unit);
          });
        }

        setProperty({
          ...property,
          units: remainingUnits,
          stats: updatedStats,
        });
      }

      const failedCount = selectedUnits.length - successfulIds.size;
      if (failedCount > 0) {
        toast.warning(
          `Deleted ${successfulIds.size} unit${successfulIds.size !== 1 ? 's' : ''}, ${failedCount} failed`
        );
      } else {
        toast.success(
          `Successfully deleted ${successfulIds.size} unit${successfulIds.size !== 1 ? 's' : ''}`
        );
      }
      setSelectedUnits([]);
    } catch (error) {
      console.error('Error deleting units:', error);
      toast.error('Failed to delete units. Please try again.');
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleCSVUpload = (): void => {
    setShowCSVUploadModal(true);
  };

  const handleCSVUploadSuccess = (): void => {
    // Refresh property data to reflect new assignments
    loadProperty();
    setSelectedUnits([]);
  };

  const handleBulkAssignSuccess = (): void => {
    // Refresh property data to reflect new assignments
    loadProperty();
    setSelectedUnits([]);
    setShowBulkAssignModal(false);
  };

  /**
   * Memoized calculations for bulk operations
   * 
   * These values are expensive to compute (O(n) array filtering) and are used
   * multiple times in the render. Memoization prevents unnecessary recalculation
   * on every render, only recomputing when dependencies change.
   * 
   * Performance impact example:
   * - 100 units × 10 renders = 1,000 filter operations without memoization
   * - 100 units × 1 recalculation = 100 filter operations with memoization (90% reduction!)
   */

  // Count of selected units - simple length check, memoized to prevent function recreation
  const selectedUnitsCount = useMemo(() => selectedUnits.length, [selectedUnits]);

  // Filtered list of selected units that are vacant (for bulk assignment)
  const vacantSelectedUnits = useMemo(() => {
    if (!property?.units) return [];
    return property.units.filter(
      (unit) => selectedUnits.includes(unit.id) && !unit.is_rented
    );
  }, [property?.units, selectedUnits]);

  // Complete list of selected unit objects (for passing to modals)
  const selectedUnitObjects = useMemo(() => {
    if (!property?.units) return [];
    return property.units.filter((unit) => selectedUnits.includes(unit.id));
  }, [property?.units, selectedUnits]);

  if (loading) return <PropertyDetailSkeleton />;

  if (error)
    return (
      <div className="bg-white dark:bg-gray-900 -m-4 h-[calc(100%+2rem)] overflow-hidden">
        <div className="h-full overflow-auto">
          <div className="p-6 text-center">
          <div className="bg-red-50 dark:bg-red-900/20 border-l-4 border-red-500 dark:border-red-400 p-4 mb-4 max-w-md mx-auto transition-colors duration-300">
            <div className="flex">
              <div className="flex-shrink-0">
                <svg
                  className="h-5 w-5 text-red-400 dark:text-red-500"
                  viewBox="0 0 20 20"
                  fill="currentColor"
                >
                  <path
                    fillRule="evenodd"
                    d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z"
                    clipRule="evenodd"
                  />
                </svg>
              </div>
              <div className="ml-3">
                <p className="text-sm leading-5 text-red-700 dark:text-red-300 transition-colors duration-300">
                  {error}
                </p>
              </div>
            </div>
          </div>
          <button
            onClick={() => window.location.reload()}
            className="mt-2 px-4 py-2 border border-transparent text-sm leading-5 font-medium rounded-md text-white bg-blue-600 hover:bg-blue-500 dark:bg-blue-700 dark:hover:bg-blue-600 focus:outline-none focus:border-blue-700 focus:shadow-outline-blue active:bg-blue-700 transition ease-in-out duration-150"
          >
            Try Again
          </button>
          </div>
        </div>
      </div>
    );

  if (!property)
    return (
      <div className="bg-white dark:bg-gray-900 -m-4 h-[calc(100%+2rem)] overflow-hidden">
        <div className="h-full overflow-auto">
          <div className="p-6 text-center text-gray-900 dark:text-gray-100">Property not found.</div>
        </div>
      </div>
    );

  return (
    <div className="bg-white dark:bg-gray-900 -m-4 h-[calc(100%+2rem)] overflow-hidden">
      <div className="h-full overflow-auto">
        <div className="p-6 max-w-[1600px] mx-auto">
        {/* Stat Cards */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
        <StatCard
          title="Total units"
          value={property.stats?.total_units || 0}
          icon={<UnitIcon />}
          bgColor="bg-blue-50 dark:bg-blue-900/20"
          textColor="text-blue-600 dark:text-blue-400"
          onClick={undefined}
        />
        <StatCard
          title="Vacant units"
          value={property.stats?.vacant_units || 0}
          icon={<VacantIcon />}
          bgColor="bg-yellow-50 dark:bg-yellow-900/20"
          textColor="text-yellow-600 dark:text-yellow-400"
          onClick={undefined}
        />
        <StatCard
          title="Monthly Revenue"
          value={formatCurrency(property.stats?.monthly_revenue || 0)}
          icon={<RevenueIcon />}
          bgColor="bg-green-50 dark:bg-green-900/20"
          textColor="text-green-600 dark:text-green-400"
          onClick={undefined}
        />
      </div>

      {/* Units Section */}
      <div className="bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg overflow-hidden">
        <div className="p-4 border-b border-gray-200 dark:border-gray-700">
          <div className="flex justify-between items-center">
            <h2 className="text-lg font-medium text-gray-800 dark:text-gray-200">
              Units
            </h2>
            <div className="flex items-center gap-3">
              {/* Delete Selected Button */}
              {selectedUnitsCount > 0 && (
                <button
                  onClick={handleBulkDelete}
                  disabled={isSubmitting}
                  className="inline-flex items-center px-4 py-2 border border-transparent rounded-lg shadow-sm text-sm font-medium text-white bg-red-600 hover:bg-red-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-red-500 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                >
                  <i className="fas fa-trash mr-2 text-xs"></i>
                  Delete Selected ({selectedUnitsCount})
                </button>
              )}
              {/* Assign Tenants Button */}
              {selectedUnitsCount > 0 && vacantSelectedUnits.length > 0 && (
                <button
                  onClick={handleBulkAssign}
                  disabled={isSubmitting}
                  className="inline-flex items-center px-4 py-2 border border-transparent rounded-lg shadow-sm text-sm font-medium text-white bg-green-600 hover:bg-green-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-green-500 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                >
                  <i className="fas fa-user-plus mr-2 text-xs"></i>
                  Assign Tenants ({vacantSelectedUnits.length})
                </button>
              )}
              {/* CSV Upload Button */}
              <button
                onClick={handleCSVUpload}
                className="bg-purple-600 hover:bg-purple-700 text-white px-4 py-2 rounded-lg text-sm font-medium flex items-center gap-2 transition-colors"
              >
                <i className="fas fa-table text-xs"></i>
                CSV Upload
              </button>
              {/* Add New Unit Button */}
              <button
                onClick={handleAddNewUnit}
                className="bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded-lg text-sm font-medium flex items-center gap-2 transition-colors"
              >
                <i className="fas fa-plus text-xs"></i>
                Add a new unit
              </button>
            </div>
          </div>
        </div>

        {/* Unit Table */}
        <UnitTable
          units={property.units || []}
          loading={false}
          error={null}
          onEdit={handleEditUnit}
          onDelete={handleDeleteUnit}
          onAssign={handleAssignTenant}
          onViewLease={handleViewLease}
          selectedUnits={selectedUnits}
          onUnitSelect={handleUnitSelect}
          onSelectAll={handleSelectAll}
        />
      </div>

      {/* Create Unit Modal */}
      <NewUnitModal
        isOpen={isCreateModalOpen}
        onClose={handleCloseCreateModal}
        onSubmit={handleCreateUnit}
        propertyId={id || ''}
        propertyType={property?.property_type}
        isLoading={isSubmitting}
      />

      {/* Edit Unit Modal */}
      <EditUnitModal
        isOpen={isEditModalOpen}
        onClose={handleCloseEditModal}
        onSubmit={handleUpdateUnit}
        unit={unitToEdit}
        propertyType={property?.property_type}
        isLoading={isSubmitting}
      />

      {/* Assign Tenant Modal */}
      {currentUnit && (
        <AssignTenantModal
          isOpen={isAssignModalOpen}
          onClose={handleCloseAssignModal}
          unit={currentUnit}
          propertyId={id}
          onSuccess={handleTenantAssigned}
        />
      )}

      {/* View Lease Modal */}
      <ViewLeaseModal
        isOpen={isViewLeaseModalOpen}
        onClose={() => setIsViewLeaseModalOpen(false)}
        lease={leaseToView}
        tenantName={tenantNameForLease}
      />

      {/* Bulk Assign Tenant Modal */}
      <BulkAssignTenantModal
        isOpen={showBulkAssignModal}
        onClose={() => setShowBulkAssignModal(false)}
        selectedUnits={selectedUnitObjects}
        propertyId={id}
        onSuccess={handleBulkAssignSuccess}
      />

      {/* CSV Upload Modal */}
      <CSVUploadModal
        isOpen={showCSVUploadModal}
        onClose={() => setShowCSVUploadModal(false)}
        propertyId={id}
        onSuccess={handleCSVUploadSuccess}
      />
        </div>
      </div>
    </div>
  );
};

export default PropertyDetail;
