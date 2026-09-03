import React from 'react';
import PropTypes from 'prop-types';
import { SkeletonLine, SkeletonCircle, SkeletonPill, SkeletonBlock } from './SkeletonPrimitives';

/**
 * Integration card skeleton that matches the QuickBooksCard layout
 */
const IntegrationCardSkeleton = ({ className = '' }) => (
  <article className={`dark-panel dark-shadow rounded-lg dark-divider border overflow-hidden transition-colors ${className}`}>
    <div className="p-6 flex items-center justify-between">
      <div className="flex items-center space-x-6">
        {/* Logo skeleton */}
        <SkeletonBlock width="2rem" height="2rem" rounded="md" />

        <div>
          {/* Title */}
          <SkeletonLine width="10rem" height="1.125rem" className="mb-2" />
          {/* Description */}
          <SkeletonLine width="16rem" height="0.75rem" />
        </div>
      </div>

      <div className="flex items-center space-x-6">
        {/* Status badge */}
        <div className="min-w-[120px] flex justify-center">
          <SkeletonPill width="6rem" height="1.75rem" />
        </div>

        {/* Action button and settings */}
        <div className="flex items-center space-x-3">
          <SkeletonPill width="7rem" height="2.25rem" />
          <SkeletonCircle size="2.25rem" />
        </div>
      </div>
    </div>
  </article>
);

IntegrationCardSkeleton.propTypes = {
  className: PropTypes.string,
};

/**
 * Placeholder card skeleton - smooth solid border, no dashed outline
 */
const PlaceholderCardSkeleton = ({ className = '' }) => (
  <section className={`dark-panel rounded-lg dark-divider border transition-colors ${className}`}>
    <div className="h-full flex flex-col items-center justify-center">
      {/* Icon */}
      <div className="w-16 h-16 dark-input rounded-lg flex items-center justify-center mb-4 transition-colors">
        <SkeletonCircle size="2rem" />
      </div>

      {/* Title */}
      <SkeletonLine width="14rem" height="1.125rem" className="mb-3" />

      {/* Description */}
      <div className="space-y-2">
        <SkeletonLine width="18rem" height="0.875rem" />
        <SkeletonLine width="12rem" height="0.875rem" className="mx-auto" />
      </div>
    </div>
  </section>
);

PlaceholderCardSkeleton.propTypes = {
  className: PropTypes.string,
};

/**
 * Full integrations page skeleton - matches new full-height panel structure
 */
const IntegrationsSkeleton = ({
  className = '',
  showPlaceholder = true,
  ...props
}) => (
  <div className={`dark-panel -m-4 h-[calc(100%+2rem)] overflow-hidden flex flex-col ${className}`} role="main" {...props}>
    <div className="p-6 flex-1 flex flex-col min-h-0 overflow-hidden">
      {/* Integration cards container */}
      <div className="flex-1 flex flex-col min-h-0 space-y-6" role="region" aria-label="Integration status and actions">
        {/* Stripe Connect integration card */}
        <div className="flex-shrink-0">
          <IntegrationCardSkeleton />
        </div>

        {/* QuickBooks integration card */}
        <div className="flex-shrink-0">
          <IntegrationCardSkeleton />
        </div>

        {/* Placeholder "Coming Soon" card - fills remaining space */}
        {showPlaceholder && (
          <div className="flex-1 min-h-0">
            <PlaceholderCardSkeleton className="h-full" />
          </div>
        )}
      </div>
    </div>
  </div>
);

IntegrationsSkeleton.propTypes = {
  className: PropTypes.string,
  showPlaceholder: PropTypes.bool,
};

export { IntegrationCardSkeleton, PlaceholderCardSkeleton };
export default IntegrationsSkeleton;