/**
 * useCalendar Hook
 * 
 * Outlook-style calendar with intelligent prefetching and caching
 * Features:
 * - Wider default range (±3 months from current)
 * - Automatic prefetching of adjacent months
 * - Smart caching of loaded events
 * - Seamless navigation with no loading delays
 */

import { useState, useEffect, useCallback, useRef } from 'react';
import { fetchCalendarEvents, CalendarFilters, CalendarEventsResponse } from '../utils/api/calendar';
import { startOfMonth, endOfMonth, addMonths, subMonths, format } from 'date-fns';

// Cache for storing loaded events by date range
interface EventCache {
  [key: string]: CalendarEventsResponse['events'];
}

export const useCalendar = (initialFilters?: Partial<CalendarFilters>) => {
  const [data, setData] = useState<CalendarEventsResponse | null>(null);
  const [allEvents, setAllEvents] = useState<CalendarEventsResponse['events']>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [isInitialLoading, setIsInitialLoading] = useState<boolean>(true);
  const [loadingMore, setLoadingMore] = useState<boolean>(false);
  const [error, setError] = useState<Error | null>(null);
  const [hasMore, setHasMore] = useState<boolean>(false);
  const [prefetching, setPrefetching] = useState<boolean>(false);
  
  // Cache for events - persists across filter changes
  const eventCache = useRef<EventCache>({});
  const prefetchQueue = useRef<Set<string>>(new Set());
  const hasInitialPrefetched = useRef<boolean>(false);
  
  // Default: Load ±3 months from current date for Outlook-like experience
  const now = new Date();
  const defaultFromDate = format(startOfMonth(subMonths(now, 3)), 'yyyy-MM-dd');
  const defaultToDate = format(endOfMonth(addMonths(now, 3)), 'yyyy-MM-dd');
  
  const [filters, setFilters] = useState<CalendarFilters>({
    from_date: defaultFromDate,
    to_date: defaultToDate,
    limit: 500, // Higher limit for wider range
    offset: 0,
    ...initialFilters,
  });

  // Generate cache key from filters
  const getCacheKey = useCallback((filterSet: CalendarFilters): string => {
    return `${filterSet.from_date}_${filterSet.to_date}_${filterSet.property_id || 'all'}_${filterSet.event_type || 'all'}_${filterSet.status || 'all'}`;
  }, []);

  // Fetch events with caching
  const fetchEvents = useCallback(async (
    customFilters?: CalendarFilters, 
    append: boolean = false,
    silent: boolean = false
  ) => {
    const targetFilters = customFilters || filters;
    const cacheKey = getCacheKey(targetFilters);
    
    // Check cache first
    if (eventCache.current[cacheKey] && !append) {
      console.log(`📦 Using cached events for ${cacheKey}`);
      setAllEvents(eventCache.current[cacheKey]);
      setLoading(false);
      setIsInitialLoading(false);
      return;
    }
    
    if (!silent) {
      if (append) {
        setLoadingMore(true);
      } else {
        setLoading(true);
      }
    } else {
      setPrefetching(true);
    }
    setError(null);
    
    try {
      const response = await fetchCalendarEvents(targetFilters);
      setData(response);
      setHasMore(response.has_more);
      
      // Store in cache
      eventCache.current[cacheKey] = response.events;
      
      if (append) {
        // Append to existing events
        const combined = [...allEvents, ...response.events];
        setAllEvents(combined);
        eventCache.current[cacheKey] = combined;
      } else if (!silent) {
        // Replace with new events (only if not silent prefetch)
        setAllEvents(response.events);
      }
    } catch (err) {
      if (!silent) {
        setError(err as Error);
        console.error('Failed to fetch calendar events:', err);
      }
    } finally {
      setLoading(false);
      setIsInitialLoading(false);
      setLoadingMore(false);
      setPrefetching(false);
    }
  }, [filters, getCacheKey, allEvents]);

  // Prefetch adjacent months for seamless navigation
  const prefetchAdjacentMonths = useCallback((centerDate: Date) => {
    // Prefetch ±1 month from the center date
    const prevMonth = subMonths(centerDate, 1);
    const nextMonth = addMonths(centerDate, 1);
    
    [prevMonth, nextMonth].forEach(date => {
      const fromDate = format(startOfMonth(date), 'yyyy-MM-dd');
      const toDate = format(endOfMonth(date), 'yyyy-MM-dd');
      const cacheKey = getCacheKey({ 
        from_date: fromDate, 
        to_date: toDate,
        property_id: filters.property_id,
        event_type: filters.event_type,
        status: filters.status,
        limit: 500,
        offset: 0
      });
      
      // Only prefetch if not already in cache or queue
      if (!eventCache.current[cacheKey] && !prefetchQueue.current.has(cacheKey)) {
        prefetchQueue.current.add(cacheKey);
        console.log(`🔄 Prefetching ${format(date, 'MMMM yyyy')}`);
        
        // Fetch silently in background
        fetchEvents({
          from_date: fromDate,
          to_date: toDate,
          property_id: filters.property_id,
          event_type: filters.event_type,
          status: filters.status,
          limit: 500,
          offset: 0
        }, false, true).finally(() => {
          prefetchQueue.current.delete(cacheKey);
        });
      }
    });
  }, [filters.property_id, filters.event_type, filters.status, fetchEvents, getCacheKey]);

  useEffect(() => {
    fetchEvents();
    
    // Prefetch adjacent months on initial load (only once)
    if (!hasInitialPrefetched.current) {
      const currentDate = new Date();
      setTimeout(() => prefetchAdjacentMonths(currentDate), 500); // Slight delay to prioritize main load
      hasInitialPrefetched.current = true;
    }
  }, [fetchEvents, prefetchAdjacentMonths]);

  const updateFilters = useCallback((newFilters: Partial<CalendarFilters>) => {
    setFilters(prev => ({ 
      ...prev, 
      ...newFilters,
      // Reset offset when filters change (except when explicitly setting offset)
      offset: newFilters.offset !== undefined ? newFilters.offset : 0
    }));
  }, []);

  const loadMore = useCallback(() => {
    if (!hasMore || loadingMore) return;
    
    const newOffset = (filters.offset || 0) + (filters.limit || 500);
    setFilters(prev => ({ ...prev, offset: newOffset }));
    
    // Fetch with append flag
    fetchEvents(undefined, true);
  }, [hasMore, loadingMore, filters.offset, filters.limit, fetchEvents]);

  const refetch = useCallback(() => {
    // Clear cache on manual refetch
    eventCache.current = {};
    setFilters(prev => ({ ...prev, offset: 0 }));
    fetchEvents();
  }, [fetchEvents]);

  return {
    events: allEvents,
    total: data?.total || 0,
    loading,
    isInitialLoading,
    loadingMore,
    prefetching,
    error,
    hasMore,
    filters,
    updateFilters,
    loadMore,
    refetch,
    prefetchAdjacentMonths,
  };
};

