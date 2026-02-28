import React, { useCallback, useEffect, useMemo, useState } from 'react';
import DegenFilters from '../components/degen/DegenFilters';
import DegenTable from '../components/degen/DegenTable';
import DegenTokenDetail from '../components/degen/DegenTokenDetail';
import '../styles/degen.css';

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? 'http://127.0.0.1:8001/api';

function riskLevel(score) {
  if (score >= 75) return 'extreme';
  if (score >= 50) return 'high';
  if (score >= 25) return 'medium';
  return 'low';
}

const DEFAULT_FILTERS = {
  chain: 'all',
  category: 'all',
  risk: 'all',
  sortBy: 'universe_score',
};

const DegenScannerPage = () => {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [filters, setFilters] = useState(DEFAULT_FILTERS);
  const [selectedToken, setSelectedToken] = useState(null);

  useEffect(() => {
    const fetchWatchlist = async () => {
      try {
        const res = await fetch(`${API_BASE}/degen/watchlist`, {
          signal: AbortSignal.timeout(8000),
        });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const json = await res.json();
        setData(json);
      } catch (err) {
        setError('Could not load degen watchlist.');
      } finally {
        setLoading(false);
      }
    };
    fetchWatchlist();
  }, []);

  const filteredTokens = useMemo(() => {
    if (!data?.tokens) return [];
    let tokens = [...data.tokens];

    if (filters.chain !== 'all') {
      tokens = tokens.filter((t) => t.chain === filters.chain);
    }
    if (filters.category !== 'all') {
      tokens = tokens.filter((t) => t.category === filters.category);
    }
    if (filters.risk !== 'all') {
      tokens = tokens.filter((t) => riskLevel(t.risk_score || 0) === filters.risk);
    }

    const sortKey = filters.sortBy;
    tokens.sort((a, b) => {
      const va = a[sortKey] ?? 0;
      const vb = b[sortKey] ?? 0;
      return sortKey === 'risk_score' ? va - vb : vb - va;
    });

    return tokens;
  }, [data, filters]);

  const handleSelect = useCallback((token) => {
    setSelectedToken((prev) => (prev?.asset_uid === token.asset_uid ? null : token));
  }, []);

  if (loading) {
    return (
      <div className="degen-page">
        <div className="degen-loading">Loading watchlist...</div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="degen-page">
        <div className="degen-error">{error}</div>
      </div>
    );
  }

  return (
    <div className="degen-page">
      <div className="degen-header">
        <h2>Degen Scanner</h2>
        <div className="degen-header__meta">
          <span>{data?.total_tokens || 0} tokens tracked</span>
          {data?.generated_at && (
            <span className="degen-header__ts">
              Updated: {new Date(data.generated_at).toLocaleString()}
            </span>
          )}
        </div>
      </div>

      <div className="degen-summary-bar">
        {data?.category_counts && Object.entries(data.category_counts).map(([cat, count]) => (
          <div key={cat} className="degen-summary-chip">
            <span className="degen-summary-chip__label">{cat.replace(/_/g, ' ')}</span>
            <span className="degen-summary-chip__count">{count}</span>
          </div>
        ))}
      </div>

      <DegenFilters filters={filters} onChange={setFilters} />

      <div className="degen-content">
        <div className={`degen-table-container ${selectedToken ? 'degen-table-container--with-detail' : ''}`}>
          <DegenTable
            tokens={filteredTokens}
            onSelect={handleSelect}
            selectedUid={selectedToken?.asset_uid}
          />
        </div>

        {selectedToken && (
          <DegenTokenDetail
            token={selectedToken}
            onClose={() => setSelectedToken(null)}
          />
        )}
      </div>
    </div>
  );
};

export default DegenScannerPage;
