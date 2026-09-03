import { useEffect, useRef, useCallback } from 'react';

interface UseAutoSaveOptions {
  data: any;
  onSave: () => Promise<void>;
  delay?: number; // milliseconds
  enabled?: boolean;
  isDirty?: boolean;
}

/**
 * Auto-save hook that saves data after a delay of inactivity
 * Industry standard: Stripe uses 10s, Google Docs uses ~2s
 * We use 10s to avoid excessive API calls while still providing good UX
 */
export const useAutoSave = ({
  data,
  onSave,
  delay = 10000, // 10 seconds default
  enabled = true,
  isDirty = true,
}: UseAutoSaveOptions) => {
  const timerRef = useRef<NodeJS.Timeout | null>(null);
  const isSavingRef = useRef<boolean>(false);
  const lastSavedDataRef = useRef<string | undefined>(undefined);

  const saveData = useCallback(async () => {
    if (isSavingRef.current || !enabled || !isDirty) return;

    // Check if data actually changed
    const currentData = JSON.stringify(data);
    if (currentData === lastSavedDataRef.current) return;

    try {
      isSavingRef.current = true;
      await onSave();
      lastSavedDataRef.current = currentData;
    } catch (error) {
      console.error('Auto-save failed:', error);
    } finally {
      isSavingRef.current = false;
    }
  }, [data, onSave, enabled, isDirty]);

  useEffect(() => {
    if (!enabled || !isDirty) return;

    // Clear existing timer
    if (timerRef.current) {
      clearTimeout(timerRef.current);
    }

    // Set new timer
    timerRef.current = setTimeout(() => {
      saveData();
    }, delay);

    // Cleanup on unmount or data change
    return () => {
      if (timerRef.current) {
        clearTimeout(timerRef.current);
      }
    };
  }, [data, delay, enabled, isDirty, saveData]);

  // Save on unmount if dirty
  useEffect(() => {
    return () => {
      if (enabled && isDirty && !isSavingRef.current) {
        // Fire and forget on unmount
        saveData();
      }
    };
  }, [enabled, isDirty, saveData]);

  return {
    isSaving: isSavingRef.current,
    forceSave: saveData,
  };
};
