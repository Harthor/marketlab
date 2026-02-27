import React, { useEffect, useMemo, useState } from 'react';
import { getDatasets } from '../api/client';

const Metric = ({ title, value }) => (
  <div className="metric-card">
    <strong>{title}</strong>
    <span>{value}</span>
  </div>
);

const DatasetsPage = () => {
  const [datasets, setDatasets] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [copiedDataset, setCopiedDataset] = useState('');

  useEffect(() => {
    const run = async () => {
      try {
        const payload = await getDatasets();
        setDatasets(payload);
      } catch (err) {
        setError('No se pudo cargar datasets desde el backend.');
      } finally {
        setLoading(false);
      }
    };
    run();
  }, []);

  const copyDataset = async (datasetName) => {
    try {
      await navigator.clipboard.writeText(datasetName);
      setCopiedDataset(datasetName);
      window.setTimeout(() => {
        setCopiedDataset((current) => (current === datasetName ? '' : current));
      }, 1200);
    } catch (err) {
      console.error('No se pudo copiar el dataset', err);
    }
  };

  const summary = useMemo(() => ({
    totalDatasets: datasets.length,
    totalRuns: datasets.reduce((acc, dataset) => acc + (dataset.run_count || 0), 0),
    totalTables: datasets.reduce((acc, dataset) => acc + (dataset.table_count || 0), 0),
    totalPlots: datasets.reduce((acc, dataset) => acc + (dataset.plot_count || 0), 0),
  }), [datasets]);

  return (
    <section>
      <h2>Datasets</h2>
      <p>Explorá los datasets encontrados en el workspace y su estado de corridas.</p>

      <div className="metric-grid">
        <Metric title="Datasets" value={summary.totalDatasets} />
        <Metric title="Runs totales" value={summary.totalRuns} />
        <Metric title="Tablas" value={summary.totalTables} />
        <Metric title="Plots" value={summary.totalPlots} />
      </div>

      {loading && <p>Cargando…</p>}
      {error && <p className="error">{error}</p>}

      {!loading && !error && (
        <div className="dataset-list">
          {datasets.length === 0 ? (
            <p>No hay datasets detectados. Verificá MARKETLAB_WORKSPACE y estructura de carpetas.</p>
          ) : (
            datasets.map((dataset) => (
              <article className="dataset-card" key={dataset.name}>
                <div className="dataset-header">
                  <h3 className="dataset-name" title={dataset.name}>
                    {dataset.name}
                  </h3>
                  <button
                    type="button"
                    className="copy-button"
                    onClick={() => copyDataset(dataset.name)}
                    aria-label={`Copiar dataset ${dataset.name}`}
                  >
                    {copiedDataset === dataset.name ? 'Copiado' : 'Copiar'}
                  </button>
                </div>
                <p>
                  Runs: <strong>{dataset.run_count}</strong> · Fuentes: <strong>{dataset.source_types.join(', ')}</strong>
                </p>
                <p>
                  Tablas: <strong>{dataset.table_count}</strong> · Plots: <strong>{dataset.plot_count}</strong>
                </p>
                <p>Último run: {dataset.last_seen || 'N/A'}</p>
              </article>
            ))
          )}
        </div>
      )}
    </section>
  );
};

export default DatasetsPage;
