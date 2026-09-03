import { useEffect } from 'react';

/**
 * Custom hook to warn users about unsaved changes before navigating away
 * 
 * Features:
 * - Warns on browser close/refresh/back button
 * - Uses native browser beforeunload event
 * - Works with all routing systems
 * 
 * Note: This provides browser-level warnings (tab close, refresh, back button).
 * For in-app React Router navigation blocking, the app would need to migrate to
 * React Router's data router (createBrowserRouter) to use useBlocker.
 * 
 * Usage:
 * ```tsx
 * useUnsavedChangesWarning(isDirty && !isSubmitting);
 * ```
 */
export const useUnsavedChangesWarning = (
  when: boolean,
  message: string = 'You have unsaved changes. Are you sure you want to leave?'
) => {
  useEffect(() => {
    if (!when) return;

    // Handle browser close, refresh, and back button
    const handleBeforeUnload = (event: BeforeUnloadEvent) => {
      event.preventDefault();
      // Modern browsers ignore custom message and show their own
      // But we still need to set returnValue for the warning to appear
      event.returnValue = message;
      return message;
    };

    window.addEventListener('beforeunload', handleBeforeUnload);

    return () => {
      window.removeEventListener('beforeunload', handleBeforeUnload);
    };
  }, [when, message]);
};
