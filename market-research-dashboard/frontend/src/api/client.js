import axios from 'axios';
import { DEMO_DATA } from './mockData';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8001/api';
const API_TOKEN = import.meta.env.VITE_API_TOKEN || '';
const DEMO_MODE = import.meta.env.VITE_DEMO_MODE === '1';

const api = axios.create({
  baseURL: API_BASE_URL,
  timeout: 30000,
});

// Add Bearer token to all requests when configured
if (API_TOKEN) {
  api.interceptors.request.use((config) => {
    config.headers.Authorization = `Bearer ${API_TOKEN}`;
    return config;
  });
}

export { API_BASE_URL, API_TOKEN };

/**
 * Fetch helper that includes the API token for direct fetch() calls.
 */
export async function apiFetch(url, options = {}) {
  const headers = {
    ...(API_TOKEN ? { Authorization: `Bearer ${API_TOKEN}` } : {}),
    ...options.headers,
  };
  return fetch(url, { ...options, headers });
}

const pause = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

const demoPaginate = (rows, page, pageSize) => {
  const safePage = Number.isFinite(page) && page > 0 ? page : 1;
  const safePageSize = Number.isFinite(pageSize) && pageSize > 0 ? Math.min(pageSize, 1000) : 100;
  const start = (safePage - 1) * safePageSize;
  const end = start + safePageSize;

  return {
    page: safePage,
    pageSize: safePageSize,
    rows: rows.slice(start, end),
    rowCount: rows.length,
  };
};

const demoPlotDataUri = (runId, name) => {
  const safeRun = encodeURIComponent(runId.slice(0, 40));
  const safeName = encodeURIComponent(name || 'plot');
  const svg = `<?xml version='1.0' encoding='UTF-8'?>\n<svg xmlns='http://www.w3.org/2000/svg' width='1280' height='720'>\n  <defs>\n    <linearGradient id='bg' x1='0' y1='0' x2='0' y2='1'>\n      <stop offset='0%' stop-color='#0e1726'/>\n      <stop offset='100%' stop-color='#05070d'/>\n    </linearGradient>\n  </defs>\n  <rect width='100%' height='100%' fill='url(%23bg)'/>\n  <text x='50' y='120' fill='%23f0f6fc' font-size='48' font-family='Inter, Arial'>Demo plot</text>\n  <text x='50' y='180' fill='%238b949e' font-size='28' font-family='Inter, Arial'>run: ${safeRun}</text>\n  <text x='50' y='230' fill='%238b949e' font-size='28' font-family='Inter, Arial'>file: ${safeName}</text>\n  <text x='50' y='300' fill='%238b949e' font-size='22' font-family='Inter, Arial'>No backend attached in demo mode.</text>\n</svg>`;
  return `data:image/svg+xml;utf8,${encodeURIComponent(svg)}`;
};

export const getDatasets = async () => {
  if (DEMO_MODE) {
    await pause(200);
    return DEMO_DATA.datasets;
  }

  const { data } = await api.get('/datasets');
  return data;
};

export const getRuns = async ({ type } = {}) => {
  if (DEMO_MODE) {
    await pause(220);
    return type
      ? DEMO_DATA.runs.filter((run) => (run.kind ?? run.run_type) === type)
      : DEMO_DATA.runs;
  }

  const params = type ? { type } : {};
  const { data } = await api.get('/runs', { params });
  return data;
};

export const getRunDetail = async (runId) => {
  if (DEMO_MODE) {
    await pause(150);
    const run = DEMO_DATA.runs.find((item) => item.run_id === runId || item.id === runId);
    if (!run) {
      throw new Error('Run not found in demo mode');
    }
    return run;
  }

  const { data } = await api.get(`/runs/${encodeURIComponent(runId)}`);
  return data;
};

export const getRunHealth = async (runId) => {
  if (DEMO_MODE) {
    await pause(120);
    const run = DEMO_DATA.runs.find((item) => item.run_id === runId || item.id === runId);
    if (!run) {
      throw new Error('Run not found in demo mode');
    }

    const missingArtifacts = (run.artifacts?.tables || [])
      .concat(run.artifacts?.plots || [])
      .filter((artifact) => artifact.missing === true)
      .map((artifact) => ({
        kind: artifact.type || artifact.kind || 'table',
        name: artifact.name,
        path: artifact.path,
      }));

    return {
      run_id: run.run_id,
      status: run.status || 'complete',
      schema_version: run.schema_version || null,
      missing_artifacts: missingArtifacts,
      warnings: run.warnings || [],
      error: run.error || null,
    };
  }

  const { data } = await api.get(`/runs/${encodeURIComponent(runId)}/health`);
  return data;
};

export const getRunTable = async ({ runId, name, page = 1, pageSize = 50 }) => {
  if (DEMO_MODE) {
    await pause(180);
    const runTables = DEMO_DATA.tablesByRun[runId] || {};
    const selected = runTables[name || 'correlations.csv'] || runTables[Object.keys(runTables)[0]];

    if (!selected) {
      throw new Error('No table artifact found in demo mode');
    }

    const pagination = demoPaginate(selected, page, pageSize);
    const columns = selected.length > 0 ? Object.keys(selected[0]) : [];

    return {
      run_id: runId,
      table: name || Object.keys(runTables)[0],
      columns,
      rows: pagination.rows,
      row_count: pagination.rowCount,
      page: pagination.page,
      page_size: pagination.pageSize,
    };
  }

  const params = { page, page_size: pageSize };
  if (name) {
    params.name = name;
  }
  const { data } = await api.get(`/runs/${encodeURIComponent(runId)}/table`, { params });
  return data;
};

export const getPlotUrl = (runId, name) => {
  if (DEMO_MODE) {
    return demoPlotDataUri(runId, name);
  }

  const params = new URLSearchParams();
  if (name) {
    params.set('name', name);
  }
  const query = params.toString();
  return `${API_BASE_URL}/runs/${encodeURIComponent(runId)}/plot${query ? `?${query}` : ''}`;
};

export default api;
