import React from 'react';
import PropTypes from 'prop-types';
import { SkeletonLine, SkeletonBlock, SkeletonPill } from './SkeletonPrimitives';

/**
 * Settings page skeleton that matches the settings layout
 * Full-height panel with tabs and content
 */
const SettingsSkeleton = ({
  className = '',
  ...props
}) => (
  <div className={`dark-panel -m-4 h-[calc(100%+2rem)] overflow-hidden flex ${className}`} {...props}>
    {/* Left Sidebar - Profile Card (fixed, doesn't scroll) */}
    <div className="w-72 flex-shrink-0 p-6 dark-divider border-r overflow-auto">
      <ProfileCardSkeleton />
    </div>

    {/* Right Content Area with Tabs */}
    <div className="flex-1 flex flex-col min-w-0 overflow-hidden">
      {/* Tab Navigation - fixed at top */}
      <div className="dark-divider border-b flex-shrink-0 px-6">
        <nav className="flex space-x-6" aria-label="Settings tabs skeleton">
          {[1, 2, 3, 4, 5, 6, 7].map(i => (
            <div key={i} className="py-3 flex items-center gap-2">
              <SkeletonBlock width="1rem" height="1rem" rounded="sm" />
              <SkeletonLine width={`${3 + (i % 3) * 1.5}rem`} height="0.875rem" />
            </div>
          ))}
        </nav>
      </div>

      {/* Main Settings Content - scrollable */}
      <div className="flex-1 overflow-auto p-6 space-y-6">
        {/* Settings Section 1 */}
        <SettingsSectionSkeleton />

        {/* Settings Section 2 */}
        <SettingsSectionSkeleton />

        {/* Settings Section 3 */}
        <SettingsSectionSkeleton />
      </div>
    </div>
  </div>
);

SettingsSkeleton.propTypes = {
  className: PropTypes.string,
};

/**
 * Profile card skeleton component
 */
const ProfileCardSkeleton = () => (
  <div className="dark-panel dark-shadow rounded-lg dark-divider border p-6">
    {/* Avatar and name */}
    <div className="text-center mb-6">
      <SkeletonBlock width="5rem" height="5rem" rounded="full" className="mx-auto mb-4" />
      <SkeletonLine width="8rem" height="1.25rem" className="mb-2 mx-auto" />
      <SkeletonLine width="10rem" height="1rem" className="mx-auto" />
    </div>

    {/* Profile details */}
    <div className="space-y-4">
      <div className="flex justify-between items-center">
        <SkeletonLine width="4rem" height="0.875rem" />
        <SkeletonLine width="6rem" height="1rem" />
      </div>
      <div className="flex justify-between items-center">
        <SkeletonLine width="6rem" height="0.875rem" />
        <SkeletonLine width="5rem" height="1rem" />
      </div>
      <div className="flex justify-between items-center">
        <SkeletonLine width="5rem" height="0.875rem" />
        <SkeletonPill width="4rem" height="1.25rem" />
      </div>
      <div className="flex justify-between items-center">
        <SkeletonLine width="6rem" height="0.875rem" />
        <SkeletonPill width="4rem" height="1.25rem" />
      </div>
    </div>
  </div>
);

/**
 * Settings section skeleton component
 */
const SettingsSectionSkeleton = () => (
  <div className="dark-panel dark-shadow rounded-lg dark-divider border overflow-hidden">
    {/* Section header */}
    <div className="px-6 py-4 dark-divider border-b">
      <SkeletonLine width="10rem" height="1.25rem" className="mb-1" />
      <SkeletonLine width="16rem" height="0.875rem" />
    </div>

    {/* Section content */}
    <div className="px-6 py-4 space-y-4">
      {/* Setting item 1 - input field */}
      <div className="grid grid-cols-2 gap-4">
        <div>
          <SkeletonLine width="5rem" height="0.875rem" className="mb-2" />
          <SkeletonBlock width="100%" height="2.5rem" rounded="md" />
        </div>
        <div>
          <SkeletonLine width="5rem" height="0.875rem" className="mb-2" />
          <SkeletonBlock width="100%" height="2.5rem" rounded="md" />
        </div>
      </div>

      {/* Setting item 2 - input field */}
      <div className="grid grid-cols-2 gap-4">
        <div>
          <SkeletonLine width="6rem" height="0.875rem" className="mb-2" />
          <SkeletonBlock width="100%" height="2.5rem" rounded="md" />
        </div>
        <div>
          <SkeletonLine width="6rem" height="0.875rem" className="mb-2" />
          <SkeletonBlock width="100%" height="2.5rem" rounded="md" />
        </div>
      </div>

      {/* Setting item 3 - full width */}
      <div>
        <SkeletonLine width="6rem" height="0.875rem" className="mb-2" />
        <SkeletonBlock width="100%" height="2.5rem" rounded="md" />
      </div>
    </div>
  </div>
);

export { ProfileCardSkeleton, SettingsSectionSkeleton };
export default SettingsSkeleton;