/**
 * Skeleton loader for calendar event cards
 * Shows a loading placeholder while events are being fetched
 */

import React from 'react';

export const CalendarEventCardSkeleton: React.FC = () => {
  return (
    <div className="bg-white dark:bg-gray-800 border-l-4 border-gray-300 dark:border-gray-600 rounded-lg shadow-sm p-4 animate-pulse">
      {/* Header */}
      <div className="flex items-start justify-between mb-3">
        <div className="flex items-start space-x-3 flex-1">
          {/* Icon placeholder */}
          <div className="w-5 h-5 bg-gray-200 dark:bg-gray-700 rounded"></div>
          
          <div className="flex-1 space-y-2">
            {/* Title placeholder */}
            <div className="h-5 bg-gray-200 dark:bg-gray-700 rounded w-3/4"></div>
            {/* Date placeholder */}
            <div className="h-4 bg-gray-200 dark:bg-gray-700 rounded w-1/2"></div>
          </div>
        </div>
        
        {/* Status badge placeholder */}
        <div className="h-6 w-20 bg-gray-200 dark:bg-gray-700 rounded-full"></div>
      </div>

      {/* Description placeholder */}
      <div className="h-4 bg-gray-200 dark:bg-gray-700 rounded w-full mb-3 ml-8"></div>

      {/* Related entities placeholders */}
      <div className="flex flex-wrap gap-3 ml-8 mb-3">
        <div className="h-4 w-24 bg-gray-200 dark:bg-gray-700 rounded"></div>
        <div className="h-4 w-20 bg-gray-200 dark:bg-gray-700 rounded"></div>
      </div>

      {/* Action buttons placeholder */}
      <div className="flex flex-wrap gap-2 ml-8">
        <div className="h-8 w-24 bg-gray-200 dark:bg-gray-700 rounded"></div>
        <div className="h-8 w-28 bg-gray-200 dark:bg-gray-700 rounded"></div>
      </div>
    </div>
  );
};

/**
 * Multiple skeleton cards for initial loading
 */
export const CalendarEventListSkeleton: React.FC<{ count?: number }> = ({ count = 5 }) => {
  return (
    <div className="space-y-4">
      {Array.from({ length: count }).map((_, index) => (
        <CalendarEventCardSkeleton key={index} />
      ))}
    </div>
  );
};

