// MarketLab Dashboard v2 — useDashboardRun hook

import { useState, useEffect } from 'react';
import type { DashboardRunData } from '@/types/dashboard';
import { fetchDashboardRun } from '@/api/dashboardAdapter';
import { mockDashboardRun } from '@/data/mockData';

interface UseDashboardRunResult {
  run: DashboardRunData;
  loading: boolean;
  error: string | null;
}

export function useDashboardRun(): UseDashboardRunResult {
  const [run, setRun] = useState<DashboardRunData>(mockDashboardRun);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      try {
        setLoading(true);
        const data = await fetchDashboardRun();
        if (!cancelled) {
          setRun(data);
          setError(null);
        }
      } catch (e) {
        if (!cancelled) {
          setError(e instanceof Error ? e.message : 'Error loading dashboard data');
          // Keep mock data as fallback
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }

    load();
    return () => { cancelled = true; };
  }, []);

  return { run, loading, error };
}
