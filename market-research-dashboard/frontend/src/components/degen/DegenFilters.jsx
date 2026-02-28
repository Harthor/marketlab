import React from 'react';

const CHAINS = ['all', 'solana', 'base', 'bsc'];
const CATEGORIES = [
  'all',
  'meme_bluechip',
  'meme_emerging',
  'narrative_high_beta',
  'dex_new_launch',
  'pre_cex_watch',
];
const RISK_LEVELS = ['all', 'low', 'medium', 'high', 'extreme'];

const CATEGORY_LABELS = {
  all: 'All Categories',
  meme_bluechip: 'Meme Bluechip',
  meme_emerging: 'Meme Emerging',
  narrative_high_beta: 'Narrative',
  dex_new_launch: 'New Launch',
  pre_cex_watch: 'Pre-CEX',
};

const DegenFilters = ({ filters, onChange }) => {
  const update = (key, value) => onChange({ ...filters, [key]: value });

  return (
    <div className="degen-filters">
      <label>
        Chain
        <select value={filters.chain} onChange={(e) => update('chain', e.target.value)}>
          {CHAINS.map((c) => (
            <option key={c} value={c}>{c === 'all' ? 'All Chains' : c.toUpperCase()}</option>
          ))}
        </select>
      </label>

      <label>
        Category
        <select value={filters.category} onChange={(e) => update('category', e.target.value)}>
          {CATEGORIES.map((c) => (
            <option key={c} value={c}>{CATEGORY_LABELS[c] || c}</option>
          ))}
        </select>
      </label>

      <label>
        Risk
        <select value={filters.risk} onChange={(e) => update('risk', e.target.value)}>
          {RISK_LEVELS.map((r) => (
            <option key={r} value={r}>{r === 'all' ? 'All Risk Levels' : r.charAt(0).toUpperCase() + r.slice(1)}</option>
          ))}
        </select>
      </label>

      <label>
        Sort By
        <select value={filters.sortBy} onChange={(e) => update('sortBy', e.target.value)}>
          <option value="universe_score">Score</option>
          <option value="market_cap_usd">Market Cap</option>
          <option value="volume_24h_usd">Volume 24h</option>
          <option value="risk_score">Risk</option>
        </select>
      </label>
    </div>
  );
};

export default DegenFilters;
