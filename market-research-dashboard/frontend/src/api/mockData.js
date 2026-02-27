const correlationRows = Array.from({ length: 120 }, (_, index) => {
  const feature = `feature_${index + 1}`;
  const corr = ((Math.sin(index / 5) * 0.65) + (index % 7) / 40).toFixed(3);
  return {
    feature,
    target: 'BTCUSDT',
    correlation: Number(corr),
    lag: index % 10,
    rho: Number(corr),
  };
});

const equityRows = Array.from({ length: 220 }, (_, index) => ({
  date: `2026-02-${String((index % 28) + 1).padStart(2, '0')}`,
  equity: Number((10000 + Math.sin(index / 8) * 300 + index * 12).toFixed(2)),
  return: Number((0.0008 * index + (index % 11) / 50).toFixed(4)),
  drawdown: Number((Math.cos(index / 10) * 0.04).toFixed(4)),
}));

export const DEMO_DATA = {
  datasets: [
    {
      name: 'BTCUSD',
      run_count: 2,
      source_types: ['correlation', 'forecast'],
      last_seen: '2026-02-26T11:00:00Z',
      table_count: 2,
      plot_count: 2,
    },
    {
      name: 'ETHUSD',
      run_count: 1,
      source_types: ['forecast'],
      last_seen: '2026-02-20T10:00:00Z',
      table_count: 1,
      plot_count: 1,
    },
  ],

  runs: [
    {
      run_id: 'correlation:Y29ycmVsL3J1bl9iYXRjaF8x',
      id: 'correlation:Y29ycmVsL3J1bl9iYXRjaF8x',
      kind: 'correlation',
      run_type: 'correlation',
      schema_version: '2.0',
      status: 'complete',
      name: 'corr_run_2026-02-26',
      path: '/workspace/correlation-engine/reports/corr_run_1',
      warnings: [],
      error: null,
      paths: {
        run: '/workspace/correlation-engine/reports/corr_run_1',
        tables: ['/workspace/correlation-engine/reports/corr_run_1/correlations.csv'],
        plots: ['/workspace/correlation-engine/reports/corr_run_1/rolling_correlation.png'],
      },
      artifacts: {
        tables: [
          {
            name: 'correlations.csv',
            path: '/workspace/correlation-engine/reports/corr_run_1/correlations.csv',
          },
        ],
        plots: [
          {
            name: 'rolling_correlation.png',
            path: '/workspace/correlation-engine/reports/corr_run_1/rolling_correlation.png',
          },
        ],
      },
      dataset_hash: 'BTCUSD',
      dataset: 'BTCUSD',
      created_at_utc: '2026-02-25T08:00:00Z',
      created_at: '2026-02-25T08:00:00Z',
      label: 'top_features=120',
      top_features: 120,
      summary: {
        top_features: 120,
        lookback: 252,
        source: 'demo',
      },
      table_names: ['correlations.csv'],
      plot_names: ['rolling_correlation.png'],
    },
    {
      run_id: 'forecast:YWJjL2Fuc2ktYmFja3Rlc3Qtb25l',
      id: 'forecast:YWJjL2Fuc2ktYmFja3Rlc3Qtb25l',
      kind: 'forecast',
      run_type: 'forecast',
      schema_version: '2.0',
      status: 'complete',
      name: 'backtest_run_2026-02-26',
      path: '/workspace/forecasting-backtest/runs/backtest_run_one',
      warnings: [],
      error: null,
      paths: {
        run: '/workspace/forecasting-backtest/runs/backtest_run_one',
        tables: ['/workspace/forecasting-backtest/runs/backtest_run_one/equity_curve.csv'],
        plots: ['/workspace/forecasting-backtest/runs/backtest_run_one/equity_curve.png'],
      },
      artifacts: {
        tables: [
          {
            name: 'equity_curve.csv',
            path: '/workspace/forecasting-backtest/runs/backtest_run_one/equity_curve.csv',
          },
        ],
        plots: [
          {
            name: 'equity_curve.png',
            path: '/workspace/forecasting-backtest/runs/backtest_run_one/equity_curve.png',
          },
        ],
      },
      dataset_hash: 'BTCUSD',
      dataset: 'BTCUSD',
      model_name: 'demo_model_v1',
      created_at_utc: '2026-02-24T06:12:00Z',
      created_at: '2026-02-24T06:12:00Z',
      label: 'demo_model_v1',
      summary: {
        sharpe: 1.35,
        max_drawdown: -0.09,
        final_balance: 10922.4,
        total_trades: 143,
        source: 'demo',
      },
      table_names: ['equity_curve.csv'],
      plot_names: ['equity_curve.png'],
    },
    {
      run_id: 'forecast:bW9yZS9iYWNrdGVzdC1ydW4y',
      id: 'forecast:bW9yZS9iYWNrdGVzdC1ydW4y',
      kind: 'forecast',
      run_type: 'forecast',
      schema_version: '2.0',
      status: 'complete',
      name: 'backtest_run_2026-02-20',
      path: '/workspace/forecasting-backtest/runs/backtest_run_two',
      warnings: [],
      error: null,
      paths: {
        run: '/workspace/forecasting-backtest/runs/backtest_run_two',
        tables: ['/workspace/forecasting-backtest/runs/backtest_run_two/equity_curve.csv'],
        plots: ['/workspace/forecasting-backtest/runs/backtest_run_two/equity_curve.png'],
      },
      artifacts: {
        tables: [
          {
            name: 'equity_curve.csv',
            path: '/workspace/forecasting-backtest/runs/backtest_run_two/equity_curve.csv',
          },
        ],
        plots: [
          {
            name: 'equity_curve.png',
            path: '/workspace/forecasting-backtest/runs/backtest_run_two/equity_curve.png',
          },
        ],
      },
      dataset_hash: 'ETHUSD',
      dataset: 'ETHUSD',
      model_name: 'demo_model_v2',
      created_at_utc: '2026-02-18T03:10:00Z',
      created_at: '2026-02-18T03:10:00Z',
      label: 'demo_model_v2',
      summary: {
        sharpe: 1.01,
        max_drawdown: -0.14,
        final_balance: 9802.7,
        total_trades: 91,
        source: 'demo',
      },
      table_names: ['equity_curve.csv'],
      plot_names: ['equity_curve.png'],
    },
  ],

  tablesByRun: {
    'correlation:Y29ycmVsL3J1bl9iYXRjaF8x': {
      'correlations.csv': correlationRows,
    },
    'forecast:YWJjL2Fuc2ktYmFja3Rlc3Qtb25l': {
      'equity_curve.csv': equityRows,
    },
    'forecast:bW9yZS9iYWNrdGVzdC1ydW4y': {
      'equity_curve.csv': equityRows.slice(0, 120).map((row, index) => ({
        ...row,
        date: `2026-01-${String((index % 28) + 1).padStart(2, '0')}`,
        equity: Number((9500 + Math.sin(index / 12) * 180 + index * 9).toFixed(2)),
      })),
    },
  },
};
