import React from 'react';
import PropTypes from 'prop-types';
import { SkeletonLine, SkeletonPill } from './SkeletonPrimitives';

/**
 * Skeleton for Stripe Connect / Payment banners (InvoicePaymentsBanner and OnlinePaymentsBanner)
 * Matches the uniform height of all banner states (active, incomplete, not_started)
 * Prevents layout shift when Connect status is loading
 */
const ConnectBannerSkeleton = ({ className = '', ...props }) => (
  <div 
    className={`bg-gray-50 dark:bg-gray-800/50 border border-gray-200 dark:border-gray-700 rounded-lg p-4 mb-4 transition-colors ${className}`}
    {...props}
  >
    <div className="flex items-center justify-between">
      {/* Left side - Status text */}
      <div className="flex items-center space-x-3">
        <SkeletonLine width="160px" height="1rem" />
      </div>
      
      {/* Right side - Action button */}
      <div className="flex-shrink-0">
        <SkeletonLine width="120px" height="1rem" />
      </div>
    </div>
  </div>
);

ConnectBannerSkeleton.propTypes = {
  className: PropTypes.string,
};

export default ConnectBannerSkeleton;
