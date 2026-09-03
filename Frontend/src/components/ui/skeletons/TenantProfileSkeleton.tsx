import React from 'react';
import { SkeletonLine, SkeletonCircle, SkeletonBlock, SkeletonPill } from './SkeletonPrimitives';

/**
 * Tenant profile page skeleton that matches the exact TenantProfile.tsx layout structure
 * Uses same flexbox layout with fixed header and scrollable content area
 */
const TenantProfileSkeleton: React.FC<{ className?: string }> = ({ className = '' }) => (
  <div className={`bg-gray-50 dark:bg-gray-900 transition-colors duration-300 -m-4 h-[calc(100%+2rem)] overflow-hidden flex flex-col ${className}`}>
    {/* Header - Fixed at top (flex-shrink-0) */}
    <div className="flex-shrink-0">
      {/* Profile Header Skeleton */}
      <div className="bg-white dark:bg-gray-800 border-b border-gray-200 dark:border-gray-700 px-6 py-6">
        <div className="flex items-start justify-between gap-6">
          {/* Left: Avatar and Info */}
          <div className="flex items-center gap-4 flex-1">
            {/* Avatar */}
            <SkeletonCircle size="5rem" />

            {/* Name, Contact, and Property Info */}
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-3 mb-3">
                <SkeletonLine width="14rem" height="2rem" />
                <SkeletonPill width="4.5rem" height="1.5rem" />
                <SkeletonPill width="5.5rem" height="1.5rem" />
              </div>

              <div className="flex flex-wrap items-center gap-x-6 gap-y-2">
                <SkeletonLine width="10rem" height="1rem" />
                <SkeletonLine width="12rem" height="1rem" />
              </div>
            </div>
          </div>

          {/* Right: Action Buttons */}
          <div className="flex items-center gap-2 flex-shrink-0">
            <SkeletonBlock width="6rem" height="2.25rem" rounded="md" />
            <SkeletonBlock width="5rem" height="2.25rem" rounded="md" />
            <SkeletonBlock width="5.5rem" height="2.25rem" rounded="md" />
            <SkeletonBlock width="6rem" height="2.25rem" rounded="md" />
            <SkeletonBlock width="2.25rem" height="2.25rem" rounded="md" />
          </div>
        </div>
      </div>

      {/* Fetching Indicator Placeholder */}
      <div className="h-1" />

      {/* Tab Navigation Skeleton */}
      <div className="bg-white dark:bg-gray-800 border-b border-gray-200 dark:border-gray-700">
        <div className="px-6">
          <nav className="flex space-x-8" aria-label="Tabs">
            {Array.from({ length: 9 }, (_, i) => (
              <div key={i} className="py-4">
                <SkeletonLine
                  width={['4.5rem', '3.5rem', '5.5rem', '6.5rem', '5rem', '5.5rem', '6rem', '3.5rem', '4.5rem'][i]}
                  height="0.875rem"
                />
              </div>
            ))}
          </nav>
        </div>
      </div>
    </div>

    {/* Main Content - Fills remaining space (flex-1 min-h-0) */}
    <div className="flex-1 min-h-0 p-4 max-w-[1600px] mx-auto w-full">
      {/* OverviewTab Content Skeleton */}
      <div className="h-full overflow-auto">
        {/* Main Grid Layout - matches OverviewTab */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
          {/* Left Column - 2/3 width */}
          <div className="lg:col-span-2 flex flex-col gap-4">
            {/* 3 Metric Cards Row */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <MetricCardSkeleton />
              <MetricCardSkeleton />
              <MetricCardSkeleton />
            </div>

            {/* Current Lease and Payment Summary Row */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <LeaseCardSkeleton />
              <PaymentSummaryCardSkeleton />
            </div>
          </div>

          {/* Right Column - 1/3 width (Sidebar) */}
          <div className="flex flex-col gap-4">
            <UpcomingCardSkeleton />
            <ContactsCardSkeleton />
          </div>
        </div>
      </div>
    </div>
  </div>
);

/**
 * Metric card skeleton (h-[160px] to match MetricCard)
 */
const MetricCardSkeleton: React.FC = () => (
  <div className="bg-white dark:bg-gray-800 rounded-lg shadow-sm border border-gray-200 dark:border-gray-700 p-4 h-[160px] flex flex-col">
    {/* Header */}
    <div className="flex items-center justify-between mb-3">
      <SkeletonLine width="7rem" height="0.75rem" />
      <SkeletonBlock width="1.75rem" height="1.75rem" rounded="lg" />
    </div>
    {/* Main value */}
    <div className="flex-1 flex flex-col justify-center">
      <SkeletonLine width="4rem" height="2rem" className="mb-1.5" />
      <SkeletonLine width="6rem" height="0.875rem" />
    </div>
    {/* Secondary stats */}
    <div className="flex items-center justify-between pt-2 border-t border-gray-100 dark:border-gray-700 mt-auto">
      <SkeletonLine width="5rem" height="0.75rem" />
      <SkeletonLine width="4rem" height="0.75rem" />
    </div>
  </div>
);

/**
 * Current Lease card skeleton
 */
const LeaseCardSkeleton: React.FC = () => (
  <div className="bg-white dark:bg-gray-800 rounded-lg shadow-sm border border-gray-200 dark:border-gray-700 p-4">
    {/* Header */}
    <div className="flex items-center justify-between mb-4">
      <div className="flex items-center gap-2">
        <SkeletonBlock width="1.25rem" height="1.25rem" rounded="md" />
        <SkeletonLine width="6rem" height="1rem" />
      </div>
      <SkeletonPill width="3.5rem" height="1.25rem" />
    </div>
    {/* Property/Unit */}
    <div className="flex items-center gap-2 mb-4">
      <SkeletonCircle size="1rem" />
      <SkeletonLine width="10rem" height="0.875rem" />
    </div>
    {/* Stats Grid */}
    <div className="grid grid-cols-2 gap-4 mb-4">
      <div>
        <SkeletonLine width="4rem" height="0.625rem" className="mb-1" />
        <SkeletonLine width="5rem" height="1.25rem" />
        <SkeletonLine width="3rem" height="0.625rem" className="mt-0.5" />
      </div>
      <div>
        <SkeletonLine width="5rem" height="0.625rem" className="mb-1" />
        <SkeletonLine width="4rem" height="1.25rem" />
        <SkeletonLine width="2rem" height="0.625rem" className="mt-0.5" />
      </div>
    </div>
    {/* Lease Term */}
    <div className="mb-4">
      <div className="flex items-center gap-2 mb-1">
        <SkeletonLine width="4rem" height="0.625rem" />
        <SkeletonPill width="2.5rem" height="1rem" />
      </div>
      <SkeletonLine width="10rem" height="0.875rem" />
    </div>
    {/* Buttons */}
    <div className="grid grid-cols-2 gap-2">
      <SkeletonBlock width="100%" height="2.25rem" rounded="md" />
      <SkeletonBlock width="100%" height="2.25rem" rounded="md" />
    </div>
  </div>
);

/**
 * Payment Summary card skeleton
 */
const PaymentSummaryCardSkeleton: React.FC = () => (
  <div className="bg-white dark:bg-gray-800 rounded-lg shadow-sm border border-gray-200 dark:border-gray-700 p-4">
    {/* Header */}
    <div className="flex items-center gap-2 mb-4">
      <SkeletonCircle size="1.25rem" />
      <SkeletonLine width="8rem" height="1rem" />
    </div>
    {/* Top Stats Row */}
    <div className="grid grid-cols-2 gap-3 mb-4">
      <div className="bg-gray-50 dark:bg-gray-700/50 rounded-lg p-3">
        <SkeletonLine width="5rem" height="0.625rem" className="mb-1" />
        <SkeletonLine width="6rem" height="1.25rem" />
      </div>
      <div className="bg-gray-50 dark:bg-gray-700/50 rounded-lg p-3">
        <SkeletonLine width="5rem" height="0.625rem" className="mb-1" />
        <SkeletonLine width="4rem" height="1.25rem" />
      </div>
    </div>
    {/* Middle Stats Row */}
    <div className="grid grid-cols-2 gap-3 mb-4">
      <div>
        <SkeletonLine width="4rem" height="0.625rem" className="mb-1" />
        <SkeletonLine width="5rem" height="1rem" />
        <SkeletonLine width="2rem" height="0.625rem" className="mt-0.5" />
      </div>
      <div>
        <SkeletonLine width="5rem" height="0.625rem" className="mb-1" />
        <SkeletonLine width="5rem" height="1rem" />
        <SkeletonLine width="2rem" height="0.625rem" className="mt-0.5" />
      </div>
    </div>
    {/* Last Payment */}
    <div className="border-t border-gray-100 dark:border-gray-700 pt-3 mb-4">
      <div className="flex items-center justify-between">
        <div>
          <SkeletonLine width="5rem" height="0.625rem" className="mb-1" />
          <SkeletonLine width="4rem" height="1rem" />
        </div>
        <div className="text-right">
          <SkeletonLine width="5rem" height="0.625rem" className="mb-1" />
          <SkeletonLine width="3rem" height="0.625rem" />
        </div>
      </div>
    </div>
    {/* Button */}
    <SkeletonBlock width="100%" height="2.25rem" rounded="md" />
  </div>
);

/**
 * Upcoming card skeleton (flex-1 to fill space)
 */
const UpcomingCardSkeleton: React.FC = () => (
  <div className="bg-white dark:bg-gray-800 rounded-lg shadow-sm border border-gray-200 dark:border-gray-700 p-4 flex-1 flex flex-col">
    {/* Header */}
    <div className="flex items-center gap-2 mb-3">
      <SkeletonBlock width="1rem" height="1rem" rounded="md" />
      <SkeletonLine width="5rem" height="0.875rem" />
    </div>
    {/* Events */}
    <div className="flex-1 space-y-2">
      {[1, 2, 3].map((i) => (
        <div key={i} className={`flex items-center gap-2 ${i < 3 ? 'pb-2 border-b border-gray-100 dark:border-gray-700' : ''}`}>
          <SkeletonBlock width="1.75rem" height="1.75rem" rounded="lg" />
          <div className="flex-1">
            <SkeletonLine width="6rem" height="0.875rem" className="mb-1" />
            <SkeletonLine width="8rem" height="0.75rem" />
          </div>
          <SkeletonLine width="2.5rem" height="0.75rem" />
        </div>
      ))}
    </div>
  </div>
);

/**
 * Contacts card skeleton
 */
const ContactsCardSkeleton: React.FC = () => (
  <div className="bg-white dark:bg-gray-800 rounded-lg shadow-sm border border-gray-200 dark:border-gray-700 p-4">
    {/* Header */}
    <div className="flex items-center gap-2 mb-3">
      <SkeletonBlock width="1rem" height="1rem" rounded="md" />
      <SkeletonLine width="4rem" height="0.875rem" />
    </div>
    {/* Tenant Contact */}
    <div className="space-y-1.5 mb-3">
      <SkeletonLine width="3rem" height="0.625rem" />
      <SkeletonLine width="6rem" height="0.875rem" />
      <div className="flex flex-col gap-0.5">
        <div className="flex items-center gap-1">
          <SkeletonCircle size="0.75rem" />
          <SkeletonLine width="10rem" height="0.75rem" />
        </div>
        <div className="flex items-center gap-1">
          <SkeletonCircle size="0.75rem" />
          <SkeletonLine width="6rem" height="0.75rem" />
        </div>
      </div>
    </div>
    {/* Emergency Contacts */}
    <div className="pt-3 border-t border-gray-100 dark:border-gray-700">
      <div className="flex items-center justify-between mb-2">
        <SkeletonLine width="7rem" height="0.625rem" />
        <SkeletonLine width="2rem" height="0.75rem" />
      </div>
      <SkeletonLine width="5rem" height="0.75rem" />
    </div>
  </div>
);

export default TenantProfileSkeleton;
