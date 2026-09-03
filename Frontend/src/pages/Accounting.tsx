import React from "react";
import { Outlet, useNavigate, useLocation } from "react-router-dom";
import { AccountingProvider } from "../components/accounting/AccountingContext";
import SharedFilePreviewModal from "../components/accounting/shared/SharedFilePreviewModal";

type TabName = "overview" | "invoices" | "expenses" | "payments" | "rent-tracker";

interface TabConfig {
  name: TabName;
  label: string;
}

const TABS: TabConfig[] = [
  { name: "overview", label: "Overview" },
  { name: "invoices", label: "Invoices" },
  { name: "expenses", label: "Expenses" },
  { name: "payments", label: "Payments" },
  { name: "rent-tracker", label: "Rent Tracker" },
];

const Accounting: React.FC = () => {
  const navigate = useNavigate();
  const location = useLocation();
  
  // Determine the current active tab from the URL
  const getCurrentTab = (): TabName => {
    const path = location.pathname.split('/').pop() as string;
    return path === 'accounting' ? 'overview' : path as TabName;
  };
  
  const activeTab = getCurrentTab();

  const handleTabChange = (tabName: TabName): void => {
    navigate(`/accounting/${tabName}`);
  };

  const getTabClassName = (tabName: TabName): string => {
    const baseClasses = "whitespace-nowrap py-4 px-1 border-b-2 font-medium text-sm transition-colors duration-200";
    const activeClasses = "border-blue-500 text-blue-600 dark:text-blue-400";
    const inactiveClasses = "border-transparent text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300 hover:border-gray-300 dark:hover:border-gray-500";
    
    return `${baseClasses} ${activeTab === tabName ? activeClasses : inactiveClasses}`;
  };

  return (
    <AccountingProvider>
      <div className="dark-panel -m-4 h-[calc(100%+2rem)] overflow-hidden flex flex-col">
        <div className="dark-divider border-b flex-shrink-0">
          <nav className="-mb-px flex space-x-8 px-6" role="tablist" aria-label="Accounting sections">
            {TABS.map((tab) => (
              <button
                key={tab.name}
                onClick={() => handleTabChange(tab.name)}
                className={getTabClassName(tab.name)}
                type="button"
                role="tab"
                aria-selected={activeTab === tab.name}
                aria-controls={`${tab.name}-panel`}
              >
                {tab.label}
              </button>
            ))}
          </nav>
        </div>

        {/* Tab content rendered by React Router */}
        <div className="flex-1 overflow-auto p-6" role="tabpanel" id={`${activeTab}-panel`}>
          <Outlet />
        </div>

        {/* Shared file preview modal */}
        <SharedFilePreviewModal />
      </div>
    </AccountingProvider>
  );
};

export default Accounting;
