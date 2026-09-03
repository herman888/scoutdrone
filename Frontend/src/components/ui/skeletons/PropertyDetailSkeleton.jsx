import React from 'react';
import PropTypes from 'prop-types';

/**
 * Property detail page skeleton that matches the updated layout structure
 * Matches PropertyDetail.tsx with full-width white background, stat cards, and units table
 */
const PropertyDetailSkeleton = ({ 
  className = '',
  ...props 
}) => (
  <div className="bg-white dark:bg-gray-900 -m-4 h-[calc(100%+2rem)] overflow-hidden" {...props}>
    <div className="h-full overflow-auto">
      <div className="p-6 max-w-[1600px] mx-auto">
        {/* Stat Cards Grid */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
          <StatCardSkeleton bgColor="bg-blue-50 dark:bg-blue-900/20" />
          <StatCardSkeleton bgColor="bg-yellow-50 dark:bg-yellow-900/20" />
          <StatCardSkeleton bgColor="bg-green-50 dark:bg-green-900/20" />
        </div>

        {/* Units Section */}
        <div className="bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg overflow-hidden">
          {/* Section Header - Matches exact PropertyDetail structure */}
          <div className="p-4 border-b border-gray-200 dark:border-gray-700">
            <div className="flex justify-between items-center">
              <h2 className="text-lg font-medium text-gray-800 dark:text-gray-200">
                Units
              </h2>
              <div className="flex items-center gap-3">
                {/* CSV Upload button */}
                <div className="h-9 w-32 bg-purple-200 dark:bg-purple-900/30 rounded-lg animate-pulse"></div>
                {/* Add a new unit button */}
                <div className="h-9 w-36 bg-blue-200 dark:bg-blue-900/30 rounded-lg animate-pulse"></div>
              </div>
            </div>
          </div>

          {/* Units Table */}
          <UnitsTableSkeleton />
        </div>
      </div>
    </div>
  </div>
);

PropertyDetailSkeleton.propTypes = {
  className: PropTypes.string,
};

/**
 * Stat card skeleton matching the exact StatCard component design
 */
const StatCardSkeleton = ({ bgColor = 'bg-gray-50 dark:bg-gray-800' }) => (
  <div className="bg-white dark:bg-gray-800 overflow-hidden shadow rounded-lg">
    <div className="px-4 py-5 sm:p-6">
      <div className="flex items-center">
        {/* Icon on left - colored rounded box */}
        <div className={`flex-shrink-0 ${bgColor} rounded-md p-3`}>
          <div className="h-6 w-6 bg-gray-400 dark:bg-gray-500 rounded animate-pulse"></div>
        </div>
        {/* Content on right */}
        <div className="ml-5 w-0 flex-1">
          <dl>
            {/* Title */}
            <dt className="mb-1">
              <div className="h-4 w-20 bg-gray-300 dark:bg-gray-600 rounded animate-pulse"></div>
            </dt>
            {/* Value */}
            <dd>
              <div className="h-6 w-12 bg-gray-300 dark:bg-gray-600 rounded animate-pulse"></div>
            </dd>
          </dl>
        </div>
      </div>
    </div>
  </div>
);

StatCardSkeleton.propTypes = {
  bgColor: PropTypes.string,
};

/**
 * Units table skeleton component matching the exact table structure
 * Columns: Selection, Type, Unit Number, Floor, Rent, Tenant, Lease Ends, Status, Actions (9 total)
 */
const UnitsTableSkeleton = ({ rowCount = 8 }) => (
  <div className="overflow-x-auto">
    <table className="data-table min-w-full">
      {/* Table Header */}
      <thead>
        <tr>
          {/* Selection Checkbox Column */}
          <th scope="col" className="text-center w-12 py-4">
            <div className="flex items-center justify-center">
              <div className="h-4 w-4 bg-gray-300 dark:bg-gray-600 rounded animate-pulse"></div>
            </div>
          </th>
          {/* Type Column */}
          <th scope="col" className="text-center py-4">
            <div className="h-3 w-10 bg-gray-300 dark:bg-gray-600 rounded animate-pulse mx-auto"></div>
          </th>
          {/* Unit Number Column */}
          <th scope="col" className="text-center py-4">
            <div className="h-3 w-20 bg-gray-300 dark:bg-gray-600 rounded animate-pulse mx-auto"></div>
          </th>
          {/* Floor Column */}
          <th scope="col" className="text-center py-4">
            <div className="h-3 w-12 bg-gray-300 dark:bg-gray-600 rounded animate-pulse mx-auto"></div>
          </th>
          {/* Rent Column */}
          <th scope="col" className="text-center py-4">
            <div className="h-3 w-10 bg-gray-300 dark:bg-gray-600 rounded animate-pulse mx-auto"></div>
          </th>
          {/* Tenant Column */}
          <th scope="col" className="text-center py-4">
            <div className="h-3 w-14 bg-gray-300 dark:bg-gray-600 rounded animate-pulse mx-auto"></div>
          </th>
          {/* Lease Ends Column */}
          <th scope="col" className="text-center py-4">
            <div className="h-3 w-20 bg-gray-300 dark:bg-gray-600 rounded animate-pulse mx-auto"></div>
          </th>
          {/* Status Column */}
          <th scope="col" className="text-center py-4">
            <div className="h-3 w-14 bg-gray-300 dark:bg-gray-600 rounded animate-pulse mx-auto"></div>
          </th>
          {/* Actions Column */}
          <th scope="col" className="text-center py-4">
            <div className="h-3 w-16 bg-gray-300 dark:bg-gray-600 rounded animate-pulse mx-auto"></div>
          </th>
        </tr>
      </thead>

      {/* Table Body */}
      <tbody>
        {Array.from({ length: rowCount }, (_, rowIndex) => (
          <tr key={rowIndex}>
            {/* Selection Checkbox */}
            <td className="px-6 py-4 whitespace-nowrap text-center">
              <div className="h-4 w-4 bg-gray-200 dark:bg-gray-700 rounded animate-pulse mx-auto"></div>
            </td>
            
            {/* Type Icon */}
            <td className="px-6 py-4 whitespace-nowrap text-center">
              <div className="flex justify-center">
                <div className="h-8 w-8 bg-blue-100 dark:bg-blue-900/30 rounded-lg animate-pulse"></div>
              </div>
            </td>
            
            {/* Unit Number */}
            <td className="px-6 py-4 whitespace-nowrap text-center">
              <div className="h-5 w-16 bg-gray-200 dark:bg-gray-700 rounded animate-pulse mx-auto"></div>
            </td>
            
            {/* Floor */}
            <td className="px-6 py-4 whitespace-nowrap text-center">
              <div className="h-5 w-4 bg-gray-200 dark:bg-gray-700 rounded animate-pulse mx-auto"></div>
            </td>
            
            {/* Rent */}
            <td className="px-6 py-4 whitespace-nowrap text-center">
              <div className="h-5 w-20 bg-gray-200 dark:bg-gray-700 rounded animate-pulse mx-auto"></div>
            </td>
            
            {/* Tenant */}
            <td className="px-6 py-4 whitespace-nowrap text-center">
              <div className="h-5 w-28 bg-gray-200 dark:bg-gray-700 rounded animate-pulse mx-auto"></div>
            </td>
            
            {/* Lease Ends */}
            <td className="px-6 py-4 whitespace-nowrap text-center">
              <div className="h-5 w-24 bg-gray-200 dark:bg-gray-700 rounded animate-pulse mx-auto"></div>
            </td>
            
            {/* Status */}
            <td className="px-6 py-4 whitespace-nowrap text-center">
              <div className="h-6 w-16 bg-gray-200 dark:bg-gray-700 rounded-full animate-pulse mx-auto"></div>
            </td>
            
            {/* Actions */}
            <td className="px-6 py-4 whitespace-nowrap text-center">
              <div className="flex justify-center space-x-3">
                <div className="h-4 w-12 bg-gray-200 dark:bg-gray-700 rounded animate-pulse"></div>
                <div className="h-4 w-10 bg-gray-200 dark:bg-gray-700 rounded animate-pulse"></div>
                <div className="h-4 w-12 bg-gray-200 dark:bg-gray-700 rounded animate-pulse"></div>
              </div>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  </div>
);

UnitsTableSkeleton.propTypes = {
  rowCount: PropTypes.number,
};

export { UnitsTableSkeleton, StatCardSkeleton };
export default PropertyDetailSkeleton;
