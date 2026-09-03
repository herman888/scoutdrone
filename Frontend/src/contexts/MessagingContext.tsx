import React, { createContext, useContext, useState, useCallback, useMemo, ReactNode } from 'react';
import { useUnreadCount } from '../hooks/useConversations';

interface MessagingContextValue {
  isDrawerOpen: boolean;
  openDrawer: (tenantId?: number) => void;
  closeDrawer: () => void;
  toggleDrawer: () => void;
  selectedTenantId: number | null;
  unreadCount: number;
}

const MessagingContext = createContext<MessagingContextValue | null>(null);

export const useMessaging = (): MessagingContextValue => {
  const context = useContext(MessagingContext);
  if (!context) {
    throw new Error('useMessaging must be used within a MessagingProvider');
  }
  return context;
};

interface MessagingProviderProps {
  children: ReactNode;
}

export const MessagingProvider: React.FC<MessagingProviderProps> = ({ children }) => {
  const [isDrawerOpen, setIsDrawerOpen] = useState(false);
  const [selectedTenantId, setSelectedTenantId] = useState<number | null>(null);

  // Get real unread count from React Query
  const unreadCount = useUnreadCount();

  const openDrawer = useCallback((tenantId?: number) => {
    if (tenantId) {
      setSelectedTenantId(tenantId);
    }
    setIsDrawerOpen(true);
  }, []);

  const closeDrawer = useCallback(() => {
    setIsDrawerOpen(false);
    // Don't clear selectedTenantId immediately to allow for smooth animation
    setTimeout(() => setSelectedTenantId(null), 300);
  }, []);

  const toggleDrawer = useCallback(() => {
    setIsDrawerOpen(prev => !prev);
  }, []);

  const value: MessagingContextValue = useMemo(
    () => ({
      isDrawerOpen,
      openDrawer,
      closeDrawer,
      toggleDrawer,
      selectedTenantId,
      unreadCount,
    }),
    [isDrawerOpen, openDrawer, closeDrawer, toggleDrawer, selectedTenantId, unreadCount]
  );

  return (
    <MessagingContext.Provider value={value}>
      {children}
    </MessagingContext.Provider>
  );
};
