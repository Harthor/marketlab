import React, { useEffect, useMemo, useState } from 'react';
import { getPlotUrl, getRunDetail, getRunHealth, getRunTable, getRuns } from '../api/client';
import DataTable from '../components/DataTable';
import SeriesChart from '../components/SeriesChart';

const filterRowsByCorrelation = (rows, corrColumn, threshold) => {
  if (!corrColumn || !Number.isFinite(threshold)) {
    return rows;
  }
  return rows.filter((row) => {
    const value = Number.parseFloat(row[corrColumn]);
    if (Number.isNaN(value)) {
      return false;
    }
    return Math.abs(value) >= threshold;
  });
};

const topByAbsoluteCorrelation = (rows, corrColumn, topFeatures) => {
  if (!corrColumn || topFeatures <= 0) {
    return rows;
  }

  return [...rows]
    .sort((a, b) => {
      const aValue = Math.abs(Number.parseFloat(a[corrColumn] || 0));
      const bValue = Math.abs(Number.parseFloat(b[corrColumn] || 0));
      return bValue - aValue;
    })
    .slice(0, topFeatures);
};

const detectCorrelationColumn = (columns) =>
  columns.find((item) => {
    const lowered = item.toLowerCase();
    return lowered.includes('corr') || lowered === 'rho';
  });

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
  if (!missing) {
    return null;
  }
  return `artifact missing: ${artifactName}${missing.reason ? ` (${missing.reason})` : ''}`;
};

const CorrelationsPage = () => {
  const [runs, setRuns] = useState([]);
  const [selectedRunId, setSelectedRunId] = useState('');
  const [runDetail, setRunDetail] = useState(null);
  const [runHealth, setRunHealth] = useState(null);
  const [tableData, setTableData] = useState({ rows: [], columns: [] });
  const [selectedTable, setSelectedTable] = useState('');
  const [selectedPlot, setSelectedPlot] = useState('');
  const [threshold, setThreshold] = useState('');
  const [topFeatures, setTopFeatures] = useState('20');
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    const loadRuns = async () => {
      try {
        const data = await getRuns({ type: 'correlation' });
        setRuns(data);
        setSelectedRunId(getDefaultRunId(data));
      } catch (err) {
        setError('No se pudieron cargar las corridas de correlación.');
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
          setTableData({ rows: [], columns: [], row_count: 0, page: 1, page_size: 200 });
          return;
        }

        const tableName = tableNames[0] || '';
        const plotName = plotNames.find((name) => name.toLowerCase().includes('rolling')) || plotNames[0] || '';

        setSelectedTable(tableName);
        setSelectedPlot(plotName);

        const tableMissing = getArtifactError(health, tableName);
        if (!tableName || tableMissing) {
          setTableData({ rows: [], columns: [], row_count: 0, page: 1, page_size: 200 });
          return;
        }

        const table = await getRunTable({
          runId: selectedRunId,
          name: tableName,
          page: 1,
          pageSize: 200,
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
          pageSize: 200,
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

  const filteredRows = useMemo(() => {
    if (!tableData.rows) {
      return [];
    }

    const corrColumn = detectCorrelationColumn(tableData.columns || []);
    const withFilter = filterRowsByCorrelation(tableData.rows, corrColumn, Number.parseFloat(threshold));
    const top = topByAbsoluteCorrelation(withFilter, corrColumn, Number.parseInt(topFeatures, 10));
    return top;
  }, [tableData, threshold, topFeatures]);

  const points = useMemo(() => {
    if (!filteredRows.length) {
      return [];
    }
    const xField = tableData.columns[0];
    const yField = detectCorrelationColumn(tableData.columns) || tableData.columns[1] || tableData.columns[0];
    return filteredRows.map((item, idx) => ({
      x: item[xField] ?? idx,
      y: Number.parseFloat(item[yField]) || 0,
      ...item,
    }));
  }, [filteredRows, tableData.columns]);

  return (
    <section>
      <h2>Correlations</h2>
      <p>Seleccioná corrida, tabla y filtros para inspeccionar top features y plot de correlación.</p>

      {loading && <p>Cargando…</p>}
      {error && <p className="error">{error}</p>}
      {runHealth && (
        <p className={`run-status run-status-${runHealth.status_ui || runHealth.status}`}>Estado: {runHealth.status_ui || runHealth.status}</p>
      )}
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
                  >
                    {run.name} ({run.dataset}) · {(run.status_ui || run.status) || 'unknown'} · T:{getArtifactCounts(run).tableCount} P:{getArtifactCounts(run).plotCount}
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

            <label>
              Corr mínimo absoluto
              <input
                type="number"
                step="0.01"
                placeholder="0"
                value={threshold}
                onChange={(event) => setThreshold(event.target.value)}
              />
            </label>

            <label>
              Top N
              <input type="number" min="1" value={topFeatures} onChange={(event) => setTopFeatures(event.target.value)} />
            </label>
          </div>

          <div className="layout-two-cols">
            <div>
              <h3>Rolling correlation plot</h3>
              {hasSelectedRunArtifacts && runDetail && !plotWarning && selectedPlot ? (
                <img
                  src={getPlotUrl(selectedRunId, selectedPlot)}
                  className="plot-image"
                  alt="Rolling correlation plot"
                  onError={(event) => {
                    event.currentTarget.src = '';
                    event.currentTarget.classList.add('hidden');
                  }}
                />
              ) : (
                <p>Plot no disponible.</p>
              )}
              {runDetail && !runDetail?.plot_names?.length && <p>Sin plot asociado.</p>}
            </div>

            <div>
              <h3>Tabla de resultados</h3>
              <DataTable
                columns={tableData.columns || []}
                rows={tableWarning ? [] : filteredRows}
                page={page}
                pageSize={tableData.page_size || 200}
                rowCount={tableData.row_count || 0}
                onPageChange={setPage}
              />
            </div>
          </div>

          {points.length > 0 && (
            <SeriesChart
              points={points.map((item, index) => ({
                index,
                value: item.y,
                feature: item.x,
              }))}
              xKey="feature"
              yKey="value"
              title="Top correlations"
            />
          )}
        </>
      )}
    </section>
  );
};

export default CorrelationsPage;
