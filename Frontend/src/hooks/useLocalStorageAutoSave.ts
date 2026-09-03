import { useEffect, useCallback, useRef } from 'react';

interface UseLocalStorageAutoSaveProps {
  key: string;
  data: any;
  enabled?: boolean;
  delay?: number;
}

/**
 * Auto-saves data to localStorage without hitting the database.
 * Provides instant saves and prevents database clutter.
 */
export const useLocalStorageAutoSave = ({
  key,
  data,
  enabled = true,
  delay = 10000, // 10 seconds
}: UseLocalStorageAutoSaveProps) => {
  const timeoutRef = useRef<NodeJS.Timeout | null>(null);
  const lastSavedRef = useRef<string>('');

  const save = useCallback(() => {
    if (!enabled) return;

    try {
      const serialized = JSON.stringify(data);
      
      // Only save if data actually changed
      if (serialized === lastSavedRef.current) {
        return;
      }

      localStorage.setItem(key, serialized);
      lastSavedRef.current = serialized;
      
      // Also save timestamp
      localStorage.setItem(`${key}_timestamp`, new Date().toISOString());
      
      console.log('💾 Auto-saved to localStorage');
    } catch (error) {
      console.error('Failed to auto-save to localStorage:', error);
    }
  }, [key, data, enabled]);

  useEffect(() => {
    if (!enabled) return;

    // Clear existing timeout
    if (timeoutRef.current) {
      clearTimeout(timeoutRef.current);
    }

    // Set new timeout
    timeoutRef.current = setTimeout(() => {
      save();
    }, delay);

    // Cleanup
    return () => {
      if (timeoutRef.current) {
        clearTimeout(timeoutRef.current);
      }
    };
  }, [data, delay, enabled, save]);

  return { save };
};

/**
 * Load saved data from localStorage
 */
export const loadFromLocalStorage = <T,>(key: string): { data: T | null; timestamp: string | null } => {
  try {
    const saved = localStorage.getItem(key);
    const timestamp = localStorage.getItem(`${key}_timestamp`);
    
    if (!saved) {
      return { data: null, timestamp: null };
    }

    return {
      data: JSON.parse(saved) as T,
      timestamp,
    };
  } catch (error) {
    console.error('Failed to load from localStorage:', error);
    return { data: null, timestamp: null };
  }
};

/**
 * Clear saved data from localStorage
 */
export const clearLocalStorage = (key: string) => {
  try {
    localStorage.removeItem(key);
    localStorage.removeItem(`${key}_timestamp`);
    console.log('🗑️ Cleared localStorage');
  } catch (error) {
    console.error('Failed to clear localStorage:', error);
  }
};
