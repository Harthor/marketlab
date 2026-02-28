import React, { useEffect, useState } from 'react';
import '../styles/paper.css';

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? 'http://127.0.0.1:8001/api';

function fmtUsd(val) {
  if (val == null) return '-';
  if (Math.abs(val) >= 1e6) return `$${(val / 1e6).toFixed(2)}M`;
  if (Math.abs(val) >= 1e3) return `$${(val / 1e3).toFixed(1)}K`;
  return `$${val.toFixed(2)}`;
}

function fmtPct(val) {
  if (val == null) return '-';
  const sign = val >= 0 ? '+' : '';
  return `${sign}${val.toFixed(2)}%`;
}

const REGIME_LABELS = {
  mania: 'Mania',
  rotation: 'Rotation',
  flight_to_quality: 'Flight to Quality',
  low_activity: 'Low Activity',
  capitulation: 'Capitulation',
};

const REGIME_COLORS = {
  mania: '#22c55e',
  rotation: '#eab308',
  flight_to_quality: '#3b82f6',
  low_activity: '#6b7280',
  capitulation: '#ef4444',
};

const PaperTradingPage = () => {
  const [portfolios, setPortfolios] = useState([]);
  const [selectedSlug, setSelectedSlug] = useState(null);
  const [detail, setDetail] = useState(null);
  const [trades, setTrades] = useState([]);
  const [scorecards, setScorecards] = useState([]);
  const [regime, setRegime] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    const fetchPortfolios = async () => {
      try {
        const res = await fetch(`${API_BASE}/paper/portfolios/`, {
          signal: AbortSignal.timeout(8000),
        });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();
        setPortfolios(data);
        if (data.length > 0) setSelectedSlug(data[0].slug);
      } catch {
        setError('Could not load paper portfolios.');
      } finally {
        setLoading(false);
      }
    };
    const fetchRegime = async () => {
      try {
        const res = await fetch(`${API_BASE}/paper/regime/current/`, {
          signal: AbortSignal.timeout(5000),
        });
        if (res.ok) setRegime(await res.json());
      } catch {
        // silent — regime badge is optional
      }
    };
    fetchPortfolios();
    fetchRegime();
  }, []);

  useEffect(() => {
    if (!selectedSlug) return;
    const fetchDetail = async () => {
      try {
        const [dRes, tRes, sRes] = await Promise.all([
          fetch(`${API_BASE}/paper/portfolios/${selectedSlug}/`),
          fetch(`${API_BASE}/paper/portfolios/${selectedSlug}/trades/?limit=20`),
          fetch(`${API_BASE}/paper/portfolios/${selectedSlug}/scorecards/`),
        ]);
        if (dRes.ok) setDetail(await dRes.json());
        if (tRes.ok) setTrades(await tRes.json());
        if (sRes.ok) setScorecards(await sRes.json());
      } catch {
        // silent
      }
    };
    fetchDetail();
  }, [selectedSlug]);

  if (loading) {
    return (
      <div className="paper-page">
        <div className="paper-loading">Loading paper trading...</div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="paper-page">
        <div className="paper-error">{error}</div>
      </div>
    );
  }

  if (portfolios.length === 0) {
    return (
      <div className="paper-page">
        <h2>Paper Trading</h2>
        <div className="paper-empty">
          No portfolios yet. Create one via the API:
          <code>POST /api/paper/portfolios/</code>
        </div>
      </div>
    );
  }

  return (
    <div className="paper-page">
      <div className="paper-header">
        <h2>Paper Trading</h2>
        {regime && regime.regime && (
          <span
            className="paper-regime-badge"
            style={{ borderColor: REGIME_COLORS[regime.regime] || '#6b7280' }}
          >
            <span
              className="paper-regime-dot"
              style={{ background: REGIME_COLORS[regime.regime] || '#6b7280' }}
            />
            {REGIME_LABELS[regime.regime] || regime.regime}
            <span className="paper-regime-conf">
              {(regime.confidence * 100).toFixed(0)}%
            </span>
          </span>
        )}
        {portfolios.length > 1 && (
          <select
            value={selectedSlug || ''}
            onChange={(e) => setSelectedSlug(e.target.value)}
          >
            {portfolios.map((p) => (
              <option key={p.slug} value={p.slug}>{p.name}</option>
            ))}
          </select>
        )}
      </div>

      {detail && (
        <>
          <div className="paper-stats-grid">
            <div className="paper-stat-card">
              <span className="paper-stat-label">Equity</span>
              <span className="paper-stat-value">{fmtUsd(detail.total_equity_usd)}</span>
            </div>
            <div className="paper-stat-card">
              <span className="paper-stat-label">Cash</span>
              <span className="paper-stat-value">{fmtUsd(detail.cash_usd)}</span>
            </div>
            <div className="paper-stat-card">
              <span className="paper-stat-label">PnL</span>
              <span className={`paper-stat-value ${detail.pnl_usd >= 0 ? 'paper-green' : 'paper-red'}`}>
                {fmtUsd(detail.pnl_usd)} ({fmtPct(detail.pnl_pct)})
              </span>
            </div>
            <div className="paper-stat-card">
              <span className="paper-stat-label">Drawdown</span>
              <span className="paper-stat-value paper-red">{fmtPct(-detail.drawdown_pct)}</span>
            </div>
            <div className="paper-stat-card">
              <span className="paper-stat-label">Positions</span>
              <span className="paper-stat-value">{detail.open_position_count} / {detail.max_positions}</span>
            </div>
          </div>

          {detail.positions && detail.positions.length > 0 && (
            <section className="paper-section">
              <h3>Open Positions</h3>
              <table className="paper-table">
                <thead>
                  <tr>
                    <th>Token</th>
                    <th>Chain</th>
                    <th>Qty</th>
                    <th>Entry</th>
                    <th>Current</th>
                    <th>PnL</th>
                  </tr>
                </thead>
                <tbody>
                  {detail.positions.map((p) => (
                    <tr key={p.id}>
                      <td><strong>{p.symbol}</strong></td>
                      <td>{p.chain}</td>
                      <td>{p.quantity.toFixed(2)}</td>
                      <td>${p.avg_entry_price_usd.toFixed(6)}</td>
                      <td>${p.current_price_usd.toFixed(6)}</td>
                      <td className={p.unrealized_pnl_usd >= 0 ? 'paper-green' : 'paper-red'}>
                        {fmtUsd(p.unrealized_pnl_usd)} ({fmtPct(p.unrealized_pnl_pct)})
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </section>
          )}
        </>
      )}

      {trades.length > 0 && (
        <section className="paper-section">
          <h3>Recent Trades</h3>
          <table className="paper-table">
            <thead>
              <tr>
                <th>Token</th>
                <th>Side</th>
                <th>Status</th>
                <th>Notional</th>
                <th>Impact</th>
                <th>Cost</th>
                <th>Trigger</th>
                <th>Time</th>
              </tr>
            </thead>
            <tbody>
              {trades.map((t) => (
                <tr key={t.id} className={t.status === 'rejected' ? 'paper-row-rejected' : ''}>
                  <td><strong>{t.symbol}</strong></td>
                  <td className={t.side === 'buy' ? 'paper-green' : 'paper-red'}>{t.side.toUpperCase()}</td>
                  <td>{t.status}</td>
                  <td>{fmtUsd(t.filled_notional_usd)}</td>
                  <td>{t.impact_bps.toFixed(1)} bps</td>
                  <td>{fmtUsd(t.total_cost_usd)}</td>
                  <td>{t.trigger_type || '-'}</td>
                  <td>{t.executed_at ? new Date(t.executed_at).toLocaleString() : '-'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}

      {scorecards.length > 0 && (
        <section className="paper-section">
          <h3>Scorecard by Trigger</h3>
          <table className="paper-table">
            <thead>
              <tr>
                <th>Trigger</th>
                <th>Trades</th>
                <th>Total Notional</th>
                <th>Avg Impact</th>
                <th>Avg Fail Prob</th>
              </tr>
            </thead>
            <tbody>
              {scorecards.map((s, i) => (
                <tr key={i}>
                  <td>{s.trigger_type || '(none)'}</td>
                  <td>{s.trade_count}</td>
                  <td>{fmtUsd(s.total_notional)}</td>
                  <td>{s.avg_impact_bps?.toFixed(1) || '-'} bps</td>
                  <td>{s.avg_failure_prob ? (s.avg_failure_prob * 100).toFixed(1) + '%' : '-'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}
    </div>
  );
};

export default PaperTradingPage;
