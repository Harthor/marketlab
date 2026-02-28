// MarketLab — Home page (hub with section previews)

import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { apiFetch, API_BASE_URL } from '../api/client';
import { fetchDashboardRun } from '../api/dashboardAdapter';
import type { DashboardRunData, SignalCardData } from '../types/dashboard';
import StateBadge from '../features/dashboard/StateBadge';
import SignalIcon from '../features/dashboard/SignalIcon';
import '../styles/homepage.css';

/* ---------- helpers ---------- */
function fmtCorr(signal: SignalCardData): string {
  const r = signal.stats?.primaryCorrelation ?? signal.bestLead?.correlation;
  if (r == null) return '—';
  return r.toFixed(2);
}

function fmtUsd(val: number | null | undefined): string {
  if (val == null) return '—';
  if (Math.abs(val) >= 1e9) return `$${(val / 1e9).toFixed(2)}B`;
  if (Math.abs(val) >= 1e6) return `$${(val / 1e6).toFixed(1)}M`;
  if (Math.abs(val) >= 1e3) return `$${(val / 1e3).toFixed(1)}K`;
  return `$${val.toFixed(0)}`;
}

/* ---------- types ---------- */
interface DegenToken {
  symbol: string;
  name: string;
  universe_score: number;
  risk_score: number;
  market_cap_usd: number;
  chain: string;
}

interface DegenData {
  tokens: DegenToken[];
  updated_at?: string;
}

interface PaperPortfolio {
  slug: string;
  name: string;
  initial_capital: number;
}

/* ---------- Section wrapper ---------- */
function Section({ title, count, linkTo, linkLabel, children }: {
  title: string;
  count?: string;
  linkTo: string;
  linkLabel?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="home-section">
      <div className="home-section__header">
        <h3 className="home-section__title">{title}</h3>
        {count && <span className="home-section__count">{count}</span>}
        <Link to={linkTo} className="home-section__link">{linkLabel ?? 'Ver más'} →</Link>
      </div>
      <div className="home-section__body">
        {children}
      </div>
    </div>
  );
}

/* ---------- Main component ---------- */
export default function HomePage() {
  const [signals, setSignals] = useState<DashboardRunData | null>(null);
  const [degen, setDegen] = useState<DegenData | null>(null);
  const [paper, setPaper] = useState<PaperPortfolio[]>([]);
  const [health, setHealth] = useState<{ status: string; sources: Array<{ source: string; status: string }> } | null>(null);

  useEffect(() => {
    // Fetch all data in parallel
    fetchDashboardRun().then(setSignals).catch(() => {});

    apiFetch(`${API_BASE_URL}/degen/watchlist`, { signal: AbortSignal.timeout(8000) })
      .then((r: Response) => r.ok ? r.json() : null)
      .then((d: DegenData | null) => d && setDegen(d))
      .catch(() => {});

    apiFetch(`${API_BASE_URL}/paper/portfolios/`, { signal: AbortSignal.timeout(8000) })
      .then((r: Response) => r.ok ? r.json() : [])
      .then(setPaper)
      .catch(() => {});

    apiFetch(`${API_BASE_URL}/health`, { signal: AbortSignal.timeout(5000) })
      .then((r: Response) => r.ok ? r.json() : null)
      .then(setHealth)
      .catch(() => {});
  }, []);

  const topDegen = (degen?.tokens ?? [])
    .sort((a, b) => b.universe_score - a.universe_score)
    .slice(0, 3);

  return (
    <div className="home-page">
      <div className="home-hero">
        <h1 className="home-hero__title">MarketLab</h1>
        <p className="home-hero__sub">Crypto Market Intelligence</p>
      </div>

      <div className="home-grid">
        {/* BTC Signals */}
        <Section
          title="BTC Signals"
          count={signals ? `${signals.signals.length} tracked` : undefined}
          linkTo="/signals"
        >
          {signals ? (
            <table className="home-mini-table">
              <tbody>
                {signals.signals.map((s) => (
                  <tr key={s.cardKey}>
                    <td>
                      <span className="home-signal-name">
                        <SignalIcon icon={s.icon} size={14} />
                        {s.displayName}
                      </span>
                    </td>
                    <td><StateBadge state={s.state} size="sm" /></td>
                    <td className="home-mono">{fmtCorr(s)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <p className="home-muted">Cargando señales...</p>
          )}
        </Section>

        {/* Degen Scanner */}
        <Section
          title="Degen Scanner"
          count={degen ? `${degen.tokens.length} tokens` : undefined}
          linkTo="/degen"
        >
          {topDegen.length > 0 ? (
            <table className="home-mini-table">
              <tbody>
                {topDegen.map((t, i) => (
                  <tr key={t.symbol}>
                    <td className="home-rank">{i + 1}</td>
                    <td>
                      <span className="home-signal-name">
                        <strong>{t.symbol}</strong>
                        <span className="home-muted-inline">{t.name}</span>
                      </span>
                    </td>
                    <td className="home-mono">{t.universe_score.toFixed(1)}</td>
                    <td className="home-mono">{fmtUsd(t.market_cap_usd)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <p className="home-muted">Cargando tokens...</p>
          )}
        </Section>

        {/* Paper Trading */}
        <Section
          title="Paper Trading"
          count={paper.length > 0 ? `${paper.length} portfolios` : undefined}
          linkTo="/paper"
        >
          {paper.length > 0 ? (
            <table className="home-mini-table">
              <tbody>
                {paper.slice(0, 3).map((p) => (
                  <tr key={p.slug}>
                    <td><strong>{p.name}</strong></td>
                    <td className="home-mono">{fmtUsd(p.initial_capital)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <p className="home-muted">Sin portfolios. Creá uno desde Paper Trading.</p>
          )}
        </Section>

        {/* System Health */}
        <Section
          title="System Health"
          linkTo="/datasets"
          linkLabel="Datasets"
        >
          {health ? (
            <div className="home-health">
              <div className="home-health__status">
                <span className={`home-health__dot home-health__dot--${health.status}`} />
                <span>API: {health.status}</span>
              </div>
              {health.sources.length > 0 && (
                <div className="home-health__sources">
                  {health.sources.map((s) => (
                    <span key={s.source} className="home-health__source">
                      <span className={`home-health__dot home-health__dot--${s.status === 'fresh' ? 'healthy' : 'degraded'}`} />
                      {s.source}
                    </span>
                  ))}
                </div>
              )}
            </div>
          ) : (
            <p className="home-muted">Verificando...</p>
          )}
        </Section>
      </div>
    </div>
  );
}
