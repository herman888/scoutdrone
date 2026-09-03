import React, { useState, useContext, useEffect } from 'react';
import { useSearchParams } from 'react-router-dom';
import { AuthContext } from '../contexts/AuthContext';
import type { User, AvatarUpdateHandler, ProfileUpdateHandler } from '../types/user';
import SettingsSkeleton from '../components/ui/skeletons/SettingsSkeleton';

// Import settings components
import ProfileCard from '../components/settings/ProfileCard';
import ProfileForm from '../components/settings/ProfileForm';
import SecurityForm from '../components/settings/SecurityForm';
import PreferencesForm from '../components/settings/PreferencesForm';
import NotificationSettings from '../components/settings/NotificationSettings';
import OwnershipEntitiesSettings from '../components/settings/OwnershipEntitiesSettings';
import BillingSettings from '../components/settings/BillingSettings';
import PaymentSettings from '../components/settings/PaymentSettings';

interface Tab {
  id: 'profile' | 'security' | 'preferences' | 'notifications' | 'ownership' | 'billing' | 'payments';
  label: string;
  icon: string;
}

type TabId = Tab['id'];

interface AuthContextValue {
  user: User | null;
  setUser: React.Dispatch<React.SetStateAction<User | null>>;
}

const Settings: React.FC = () => {
  const authContext = useContext(AuthContext) as AuthContextValue | null;
  const authUser = authContext?.user;
  const setAuthUser = authContext?.setUser;
  
  const [searchParams] = useSearchParams();
  const [activeTab, setActiveTab] = useState<TabId>('profile');

  // Set active tab from URL query parameter
  useEffect(() => {
    const tabParam = searchParams.get('tab');
    if (tabParam && ['profile', 'security', 'preferences', 'notifications', 'ownership', 'billing', 'payments'].includes(tabParam)) {
      setActiveTab(tabParam as TabId);
    }
  }, [searchParams]);

  // Tab configuration
  const tabs: Tab[] = [
    { id: 'profile', label: 'Profile', icon: 'fa-user' },
    { id: 'security', label: 'Security', icon: 'fa-lock' },
    { id: 'billing', label: 'Billing', icon: 'fa-credit-card' },
    { id: 'payments', label: 'Payments', icon: 'fa-money-bill-wave' },
    { id: 'preferences', label: 'Preferences', icon: 'fa-cog' },
    { id: 'notifications', label: 'Notifications', icon: 'fa-bell' },
    { id: 'ownership', label: 'Ownership Entities', icon: 'fa-briefcase' },
  ];

  // Handle avatar update from ProfileCard
  const handleAvatarUpdate: AvatarUpdateHandler = (newImageUrl: string) => {
    if (setAuthUser) {
      setAuthUser(prev => prev ? { ...prev, profile_image_url: newImageUrl } : prev);
    }
  };

  // Handle profile update from ProfileForm
  const handleProfileUpdate: ProfileUpdateHandler = (updatedData: Partial<User>) => {
    if (setAuthUser) {
      setAuthUser(prev => prev ? { ...prev, ...updatedData } : prev);
    }
  };

  // Handle preferences update
  const handlePreferencesUpdate = (preferences: Record<string, unknown>) => {
    // Update user preferences in context if needed
    // TODO: Implement preference updates in auth context when backend supports it
    console.log('Preferences update:', preferences);
  };

  // Handle notification update
  const handleNotificationUpdate = (notifications: unknown) => {
    // Update notification preferences in context if needed
    // Notification preferences are managed by the NotificationContext
    console.log('Notifications update:', notifications);
  };

  // Loading state
  if (!authUser) {
    return <SettingsSkeleton />;
  }

  return (
    <div className="dark-panel -m-4 h-[calc(100%+2rem)] overflow-hidden flex">
      {/* Left Sidebar - Profile Card (fixed, doesn't scroll) */}
      <div className="w-72 flex-shrink-0 p-6 dark-divider border-r overflow-auto">
        <ProfileCard
          user={authUser}
          onAvatarUpdate={handleAvatarUpdate}
        />
      </div>

      {/* Right Content Area with Tabs */}
      <div className="flex-1 flex flex-col min-w-0 overflow-hidden">
        {/* Tab Navigation - fixed at top */}
        <div className="dark-divider border-b flex-shrink-0 px-6">
          <nav className="flex space-x-6" aria-label="Settings tabs" role="tablist">
            {tabs.map(tab => (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={`
                  py-3 px-1 border-b-2 font-medium text-sm flex items-center gap-2 transition-all duration-200
                  ${activeTab === tab.id
                    ? 'border-blue-500 text-blue-600 dark:text-blue-400'
                    : 'border-transparent text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300 hover:border-gray-300 dark:hover:border-gray-600'}
                `}
                role="tab"
                aria-selected={activeTab === tab.id}
                aria-controls={`${tab.id}-panel`}
                aria-label={`${tab.label} settings`}
              >
                <i className={`fas ${tab.icon}`}></i>
                {tab.label}
              </button>
            ))}
          </nav>
        </div>

        {/* Tab Content - all tabs pre-loaded, visibility controlled by CSS */}
        <div className="flex-1 overflow-auto p-6 pb-20">
          <div
            role="tabpanel"
            id="profile-panel"
            className={activeTab === 'profile' ? '' : 'hidden'}
            aria-hidden={activeTab !== 'profile'}
          >
            <ProfileForm
              user={authUser}
              onProfileUpdate={handleProfileUpdate}
            />
          </div>

          <div
            role="tabpanel"
            id="security-panel"
            className={activeTab === 'security' ? '' : 'hidden'}
            aria-hidden={activeTab !== 'security'}
          >
            <SecurityForm user={authUser} />
          </div>

          <div
            role="tabpanel"
            id="preferences-panel"
            className={activeTab === 'preferences' ? '' : 'hidden'}
            aria-hidden={activeTab !== 'preferences'}
          >
            <PreferencesForm
              user={authUser}
              onPreferencesUpdate={handlePreferencesUpdate}
            />
          </div>

          <div
            role="tabpanel"
            id="notifications-panel"
            className={activeTab === 'notifications' ? '' : 'hidden'}
            aria-hidden={activeTab !== 'notifications'}
          >
            <NotificationSettings
              user={authUser}
              onNotificationUpdate={handleNotificationUpdate}
            />
          </div>

          <div
            role="tabpanel"
            id="ownership-panel"
            className={activeTab === 'ownership' ? '' : 'hidden'}
            aria-hidden={activeTab !== 'ownership'}
          >
            <OwnershipEntitiesSettings />
          </div>

          <div
            role="tabpanel"
            id="billing-panel"
            className={activeTab === 'billing' ? '' : 'hidden'}
            aria-hidden={activeTab !== 'billing'}
          >
            <BillingSettings />
          </div>

          <div
            role="tabpanel"
            id="payments-panel"
            className={activeTab === 'payments' ? '' : 'hidden'}
            aria-hidden={activeTab !== 'payments'}
          >
            <PaymentSettings />
          </div>
        </div>
      </div>
    </div>
  );
};

export default Settings;
