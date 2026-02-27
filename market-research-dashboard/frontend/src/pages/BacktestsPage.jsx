import React, { useEffect, useMemo, useState } from 'react';
import { getPlotUrl, getRunDetail, getRunHealth, getRunTable, getRuns } from '../api/client';
import DataTable from '../components/DataTable';
import SeriesChart from '../components/SeriesChart';

const detectDateColumn = (columns) =>
  columns.find((column) => {
    const key = column.toLowerCase();
    return key === 'date' || key === 'datetime' || key.includes('time') || key === 'timestamp';
  });

const detectEquityColumn = (columns) => {
  const candidates = ['equity', 'equity_curve', 'balance', 'portfolio_value', 'cum_equity', 'pnl'];
  const lower = columns.map((item) => item.toLowerCase());
  for (const candidate of candidates) {
    const index = lower.indexOf(candidate);
    if (index >= 0) {
      return columns[index];
    }
  }
  return columns.find((column) => column.toLowerCase().includes('value'));
};

const getArtifactCounts = (run) => {
  const tableCount = Array.isArray(run?.table_names) ? run.table_names.length : 0;
  const plotCount = Array.isArray(run?.plot_names) ? run.plot_names.length : 0;
  return { tableCount, plotCount, total: tableCount + plotCount };
};

const getDefaultRunId = (runs) => {
  const preferred = runs.find((run) => getArtifactCounts(run).total > 0);
  return (preferred || runs[0] || {}).id || '';
};

const errorFromException = (error) => error?.response?.data?.detail || error?.message || 'Error';

const getArtifactError = (health, artifactName) => {
  if (!health || !artifactName) {
    return null;
  }
  const missing = (health.missing_artifacts || []).find(
    (item) => item.name === artifactName || item.path?.endsWith(`/${artifactName}`) || item.path === artifactName,
  );
  return missing ? `artifact missing: ${artifactName}` : null;
};

const BacktestsPage = () => {
  const [runs, setRuns] = useState([]);
  const [selectedRunId, setSelectedRunId] = useState('');
  const [runDetail, setRunDetail] = useState(null);
  const [runHealth, setRunHealth] = useState(null);
  const [tableData, setTableData] = useState({ rows: [], columns: [] });
  const [selectedTable, setSelectedTable] = useState('');
  const [selectedPlot, setSelectedPlot] = useState('');
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    const loadRuns = async () => {
      try {
        const data = await getRuns({ type: 'forecast' });
        setRuns(data);
        setSelectedRunId(getDefaultRunId(data));
      } catch (err) {
        setError('No se pudieron cargar corridas de backtest.');
      } finally {
        setLoading(false);
      }
    };
    loadRuns();
  }, []);

  useEffect(() => {
    const loadRunData = async () => {
      if (!selectedRunId) {
        return;
      }

      setError('');
      try {
        const [detail, health] = await Promise.all([getRunDetail(selectedRunId), getRunHealth(selectedRunId)]);
        setRunDetail(detail);
        setRunHealth(health);

        const tableNames = Array.isArray(detail.table_names) ? detail.table_names : [];
        const plotNames = Array.isArray(detail.plot_names) ? detail.plot_names : [];
        const hasArtifacts = tableNames.length + plotNames.length > 0;

        if (!hasArtifacts) {
          setSelectedTable('');
          setSelectedPlot('');
          setTableData({ rows: [], columns: [], row_count: 0, page: 1, page_size: 250 });
          return;
        }

        const tableName = tableNames.find((name) => name.toLowerCase().includes('equity')) || tableNames[0] || '';
        const plotName = plotNames.find((name) => name.toLowerCase().includes('equity')) || plotNames[0] || '';

        setSelectedTable(tableName);
        setSelectedPlot(plotName);

        const tableMissing = getArtifactError(health, tableName);
        if (!tableName || tableMissing) {
          setTableData({ rows: [], columns: [], row_count: 0, page: 1, page_size: 250 });
          return;
        }

        const table = await getRunTable({
          runId: selectedRunId,
          name: tableName,
          page: 1,
          pageSize: 250,
        });
        setTableData(table);
        setPage(1);
      } catch (err) {
        setError(errorFromException(err));
      }
    };

    loadRunData();
  }, [selectedRunId]);

  useEffect(() => {
    const refreshTable = async () => {
      if (!selectedRunId || !selectedTable) {
        return;
      }

      const tableMissing = getArtifactError(runHealth, selectedTable);
      if (tableMissing) {
        return;
      }

      try {
        const table = await getRunTable({
          runId: selectedRunId,
          name: selectedTable,
          page,
          pageSize: 250,
        });
        setTableData(table);
      } catch (err) {
        setError(errorFromException(err));
      }
    };

    if (selectedRunId && selectedTable) {
      refreshTable();
    }
  }, [selectedRunId, selectedTable, page, runHealth]);

  const tableWarning = getArtifactError(runHealth, selectedTable);
  const plotWarning = getArtifactError(runHealth, selectedPlot);
  const warnings = useMemo(
    () => (runHealth?.warnings || []).filter((item) => typeof item === 'string' && item.length > 0),
    [runHealth],
  );
  const selectedRun = useMemo(() => runs.find((run) => run.id === selectedRunId) || null, [runs, selectedRunId]);
  const selectedRunArtifactCounts = getArtifactCounts(selectedRun);
  const hasSelectedRunArtifacts = selectedRunArtifactCounts.total > 0;

  const chartSeries = useMemo(() => {
    if (!tableData.rows || tableData.rows.length === 0) {
      return [];
    }

    const x = detectDateColumn(tableData.columns || []);
    const y = detectEquityColumn(tableData.columns || []);

    if (!y) {
      return [];
    }

    return tableData.rows
      .map((row, index) => ({
        x: x ? row[x] : index,
        y: Number.parseFloat(row[y]) || 0,
      }))
      .filter((point) => Number.isFinite(point.y));
  }, [tableData]);

  return (
    <section>
      <h2>Backtests</h2>
      <p>Explorá equity curve y métricas por corrida forecast/backtest.</p>

      {loading && <p>Cargando…</p>}
      {error && <p className="error">{error}</p>}
      {runHealth && <p className={`run-status run-status-${runHealth.status}`}>Estado: {runHealth.status}</p>}
      {runHealth?.status === 'failed' && runHealth?.error?.message && <p className="error">error: {runHealth.error.message}</p>}
      {warnings.length > 0 && (
        <div className="warning-box">
          <p>Warnings:</p>
          <ul>
            {warnings.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </div>
      )}
      {(tableWarning || plotWarning) && <p className="error">{tableWarning || plotWarning}</p>}
      {selectedRun && !hasSelectedRunArtifacts && (
        <p className="error">Este run no produjo artifacts (probablemente dataset insuficiente). Seleccioná otro run.</p>
      )}

      {!loading && (
        <>
          <div className="controls-grid">
            <label>
              Corrida
              <select value={selectedRunId} onChange={(event) => setSelectedRunId(event.target.value)}>
                {runs.map((run) => (
                  <option
                    key={run.id}
                    value={run.id}
                    className={
                      getArtifactCounts(run).total > 0 ? 'run-option-has-artifacts' : 'run-option-empty'
                    }
                    disabled={getArtifactCounts(run).total === 0}
                  >
                    {run.name} ({run.dataset}) · {run.status || 'unknown'} · T:{getArtifactCounts(run).tableCount} P:{getArtifactCounts(run).plotCount}
                  </option>
                ))}
              </select>
            </label>

            <label>
              Tabla
              <select
                value={selectedTable}
                onChange={(event) => setSelectedTable(event.target.value)}
                disabled={!selectedRunArtifactCounts.tableCount}
              >
                {runDetail?.table_names?.map((name) => (
                  <option key={name} value={name} disabled={Boolean(getArtifactError(runHealth, name))}>
                    {name}
                  </option>
                ))}
              </select>
            </label>

            <label>
              Plot
              <select
                value={selectedPlot}
                onChange={(event) => setSelectedPlot(event.target.value)}
                disabled={!selectedRunArtifactCounts.plotCount}
              >
                {runDetail?.plot_names?.map((name) => (
                  <option key={name} value={name} disabled={Boolean(getArtifactError(runHealth, name))}>
                    {name}
                  </option>
                ))}
              </select>
            </label>
          </div>

          <div className="layout-two-cols">
            <div>
              <h3>Equity curve</h3>
              {hasSelectedRunArtifacts && runDetail && !plotWarning && selectedPlot ? (
                <img src={getPlotUrl(selectedRunId, selectedPlot)} className="plot-image" alt="Equity plot" />
              ) : (
                <p>Plot no disponible.</p>
              )}
              {!selectedPlot && <p>No hay imagen de equity.</p>}
            </div>

            <div>
              <h3>Stats</h3>
              <pre className="stats-box">
                {JSON.stringify(runDetail?.summary || {}, null, 2)}
              </pre>
            </div>
          </div>

          {chartSeries.length > 0 && <SeriesChart points={chartSeries} xKey="x" yKey="y" title="Equity curve" />}

          <DataTable
            columns={tableData.columns || []}
            rows={tableWarning ? [] : tableData.rows || []}
            page={page}
            pageSize={tableData.page_size || 250}
            rowCount={tableData.row_count || 0}
            onPageChange={setPage}
          />
        </>
      )}
    </section>
  );
};

export default BacktestsPage;
