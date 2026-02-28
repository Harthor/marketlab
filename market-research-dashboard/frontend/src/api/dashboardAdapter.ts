// MarketLab Dashboard v2 — Data adapter (spec §10)
// Strategy: Live-first from /api/dashboard, fallback to mock data

import type { DashboardRunData } from '@/types/dashboard';
import { mockDashboardRun } from '@/data/mockData';

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? 'http://127.0.0.1:8001/api';

/**
 * Fetch dashboard run data.
 * Tries the live /api/dashboard endpoint first.
 * Falls back to mock data from spec §10.3 if the backend is unreachable.
 */
export async function fetchDashboardRun(): Promise<DashboardRunData> {
  try {
    const res = await fetch(`${API_BASE}/dashboard`, {
      signal: AbortSignal.timeout(8000),
    });
    if (res.ok) {
      const data = await res.json();
      // Validate that it looks like a DashboardRunData
      if (data && data.signals && Array.isArray(data.signals)) {
        console.info('[dashboardAdapter] Using live data from /api/dashboard');
        return data as DashboardRunData;
      }
    }
    console.warn('[dashboardAdapter] /api/dashboard returned unexpected format, falling back to mock');
  } catch {
    console.debug('[dashboardAdapter] /api/dashboard unreachable, using mock data');
  }

  // Fallback to mock data
  return structuredClone(mockDashboardRun);
}
