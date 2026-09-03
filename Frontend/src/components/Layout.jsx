import React, { useContext } from "react";
import { Outlet, useLocation, Link, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import Sidebar from "./Sidebar";
import { AuthContext } from "../contexts/AuthContext";
import { useMessaging } from "../contexts/MessagingContext";
import NotificationBell from "./notifications/NotificationBell";
import MessagingDrawer from "./messaging/MessagingDrawer";
import { fetchPropertyById } from "../utils/api";

const Layout = () => {
  const { user, signOut } = useContext(AuthContext);
  const { toggleDrawer, unreadCount } = useMessaging();
  const location = useLocation();
  const params = useParams();

  // Detect special page types for breadcrumb display
  const isTenantProfile = location.pathname.includes('/tenants/') && params.id;
  const isPropertyDetail = location.pathname.includes('/properties/') && params.id;
  const isInvoiceCreate = location.pathname === '/accounting/invoices/new';
  const isInvoiceEdit = location.pathname.includes('/accounting/invoices/') && location.pathname.includes('/edit');

  // Fetch property data for breadcrumb (only when on property detail page)
  const { data: property } = useQuery({
    queryKey: ['property', params.id],
    queryFn: () => fetchPropertyById(params.id),
    enabled: isPropertyDetail && !!params.id,
    staleTime: 5 * 60 * 1000, // 5 minutes - property name rarely changes
  });

  // Map routes to page titles
  const getPageTitle = (pathname) => {
    const routes = {
      "/dashboard": "Dashboard",
      "/properties": "Properties",
      "/leases": "Leases",
      "/vendors": "Vendors",
      "/accounting": "Accounting",
      "/applications": "Applications",
      "/tenants": "Tenants",
      "/maintenance": "Maintenance",
      "/calendar": "Calendar",
      "/reports": "Reports",
      "/settings": "Settings",
      "/integrations": "Integrations",
    };

    // Handle nested routes (e.g., /properties/:id)
    const basePath = "/" + pathname.split("/")[1];
    return routes[basePath] || "Dashboard";
  };

  const getInitials = (firstName, lastName) => {
    return `${firstName?.charAt(0) || ""}${
      lastName?.charAt(0) || ""
    }`.toUpperCase();
  };

  return (
    <div className="flex h-screen dark-bg transition-colors duration-300">
      {/* Sidebar - Hidden on invoice create/edit pages */}
      {!isInvoiceCreate && !isInvoiceEdit && <Sidebar />}

      {/* Main Content */}
      <div className="flex-1 flex flex-col overflow-hidden">
        {/* Header */}
        <header className="dark-panel dark-divider border-b z-10 h-16 transition-colors duration-300 dark-shadow">
          <div className="px-6 h-full flex justify-between items-center">
            {/* Page Title or Breadcrumb */}
            {isTenantProfile ? (
              <div className="flex items-center space-x-2 text-xl font-bold">
                <Link
                  to="/tenants"
                  className="text-gray-900 dark:text-white hover:text-blue-600 dark:hover:text-blue-400 transition-colors"
                >
                  Tenants
                </Link>
                <span className="text-gray-400 dark:text-gray-500">/</span>
                <span className="text-gray-900 dark:text-white">
                  Tenant Profile
                </span>
              </div>
            ) : isPropertyDetail ? (
              <div className="flex items-center space-x-2 text-xl font-bold">
                <Link
                  to="/properties"
                  className="text-gray-900 dark:text-white hover:text-blue-600 dark:hover:text-blue-400 transition-colors"
                >
                  Properties
                </Link>
                <span className="text-gray-400 dark:text-gray-500">/</span>
                <span className="text-gray-900 dark:text-white">
                  {property?.name || 'Loading...'}
                </span>
              </div>
            ) : isInvoiceCreate || isInvoiceEdit ? (
              <div className="flex items-center space-x-2 text-xl font-bold">
                <Link
                  to="/accounting"
                  className="text-gray-900 dark:text-white hover:text-blue-600 dark:hover:text-blue-400 transition-colors"
                >
                  Accounting
                </Link>
                <span className="text-gray-400 dark:text-gray-500">/</span>
                <Link
                  to="/accounting/invoices"
                  className="text-gray-900 dark:text-white hover:text-blue-600 dark:hover:text-blue-400 transition-colors"
                >
                  Invoices
                </Link>
                <span className="text-gray-400 dark:text-gray-500">/</span>
                <span className="text-gray-900 dark:text-white">
                  {isInvoiceCreate ? 'Create New Invoice' : 'Edit Invoice'}
                </span>
              </div>
            ) : (
              <h1 className="text-xl font-bold text-gray-900 dark:text-white transition-colors duration-300">
                {getPageTitle(location.pathname)}
              </h1>
            )}

            {/* User dropdown area */}
            <div className="flex items-center space-x-3">
              {/* Message Icon */}
              <button
                onClick={toggleDrawer}
                className="relative p-2 text-gray-600 dark:text-gray-300 hover:text-gray-900 dark:hover:text-white hover:bg-gray-100 dark:hover:bg-gray-700 rounded-full transition-colors duration-150"
                aria-label="Messages"
              >
                <i className="fas fa-comments text-xl" />
                {unreadCount > 0 && (
                  <span className="absolute top-0 left-0 inline-flex items-center justify-center px-1 py-1 text-[10px] font-bold leading-none text-white bg-green-500 rounded-full min-w-[16px]">
                    {unreadCount > 99 ? '99+' : unreadCount}
                  </span>
                )}
              </button>

              {/* Notification Bell */}
              <NotificationBell />

              {/* Link the avatar and name to settings */}
              <Link
                to="/settings"
                className="flex items-center space-x-2.5 cursor-pointer group"
              >
                <div className="h-7 w-7 rounded-full bg-teal-100 dark:bg-teal-900/50 flex items-center justify-center text-teal-700 dark:text-teal-300 overflow-hidden group-hover:ring-2 group-hover:ring-teal-500 group-hover:ring-offset-1 dark:group-hover:ring-offset-gray-800 transition-all">
                  {user?.profile_image_url ? (
                    <img
                      key={user.profile_image_url}
                      src={user.profile_image_url}
                      alt="User Avatar"
                      className="h-full w-full object-cover"
                      onError={(e) => {
                        e.target.onerror = null;
                        if (import.meta.env.MODE === 'development') {
                          console.warn(
                            "Header avatar failed to load:",
                            user.profile_image_url
                          );
                        }
                        e.target.style.display = "none";
                      }}
                    />
                  ) : (
                    <span className="text-[10px] font-medium">
                      {getInitials(user?.first_name, user?.last_name)}
                    </span>
                  )}
                </div>
                <div className="hidden md:block">
                  <p className="text-sm font-medium text-gray-900 dark:text-white group-hover:text-teal-600 dark:group-hover:text-teal-400 transition-colors">
                    {user?.first_name} {user?.last_name}
                  </p>
                  <p className="text-[11px] text-gray-500 dark:text-gray-400 capitalize transition-colors duration-300">
                    {user?.user_type}
                  </p>
                </div>
              </Link>
              {/* Logout Button */}
              <button
                className="text-sm text-gray-700 dark:text-gray-300 hover:text-red-600 dark:hover:text-red-400 px-2.5 py-1.5 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors flex items-center"
                onClick={signOut}
              >
                <i className="fas fa-sign-out-alt mr-1.5"></i> Logout
              </button>
            </div>
          </div>
        </header>

        {/* Page content */}
        <main className="flex-1 overflow-auto bg-gray-50 dark:bg-gray-900 p-4 transition-colors duration-200">
          <Outlet />
        </main>
      </div>

      {/* Messaging Drawer */}
      <MessagingDrawer />
    </div>
  );
};

export default Layout;
