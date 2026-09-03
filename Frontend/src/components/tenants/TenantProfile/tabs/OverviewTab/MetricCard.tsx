import React from 'react';

interface MetricCardProps {
  title: string;
  value: string | number | null;
  subtitle: string;
  icon: React.ReactNode;
  bgColor: string;
  iconColor: string;
  valueColor?: string;
  /** Optional secondary stat to display (e.g., "Avg 15d late") */
  secondaryStat?: string;
  /** Optional tertiary stat (e.g., trend indicator) */
  tertiaryStat?: string;
}

const MetricCard: React.FC<MetricCardProps> = ({
  title,
  value,
  subtitle,
  icon,
  bgColor,
  iconColor,
  valueColor = 'text-gray-900 dark:text-gray-100',
  secondaryStat,
  tertiaryStat,
}) => {
  const displayValue = value !== null ? value : '—';
  const finalValueColor = value !== null ? valueColor : 'text-gray-400 dark:text-gray-600';

  return (
    <div className="bg-white dark:bg-gray-800 rounded-lg shadow-sm border border-gray-200 dark:border-gray-700 p-4 h-[160px] flex flex-col">
      {/* Header with title and icon */}
      <div className="flex items-center justify-between mb-3">
        <h4 className="text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wide">
          {title}
        </h4>
        <div className={`w-7 h-7 rounded-lg ${bgColor} flex items-center justify-center flex-shrink-0`}>
          <div className={iconColor}>{icon}</div>
        </div>
      </div>

      {/* Main value - larger and centered vertically */}
      <div className="flex-1 flex flex-col justify-center">
        <span className={`text-3xl font-bold ${finalValueColor} leading-none`}>{displayValue}</span>
        {/* Primary subtitle */}
        <p className="text-sm text-gray-500 dark:text-gray-400 mt-1.5">{subtitle}</p>
      </div>

      {/* Optional secondary stats row */}
      {(secondaryStat || tertiaryStat) && (
        <div className="flex items-center justify-between pt-2 border-t border-gray-100 dark:border-gray-700 mt-auto">
          {secondaryStat && (
            <span className="text-xs text-gray-400 dark:text-gray-500">{secondaryStat}</span>
          )}
          {tertiaryStat && (
            <span className="text-xs text-gray-400 dark:text-gray-500">{tertiaryStat}</span>
          )}
        </div>
      )}
    </div>
  );
};

export default MetricCard;
