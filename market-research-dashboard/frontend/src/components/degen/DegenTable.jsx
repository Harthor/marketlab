import React from 'react';
import AlertBadge from './AlertBadge';
import CategoryBadge from './CategoryBadge';
import ChainIcon from './ChainIcon';
import DegenScoreBar from './DegenScoreBar';
import RiskBadge from './RiskBadge';

function fmtUsd(val) {
  if (val == null) return '-';
  if (val >= 1e9) return `$${(val / 1e9).toFixed(2)}B`;
  if (val >= 1e6) return `$${(val / 1e6).toFixed(2)}M`;
  if (val >= 1e3) return `$${(val / 1e3).toFixed(1)}K`;
  return `$${val.toFixed(2)}`;
}

function fmtAge(hours) {
  if (hours == null) return '-';
  if (hours < 24) return `${hours.toFixed(0)}h`;
  if (hours < 720) return `${(hours / 24).toFixed(0)}d`;
  return `${(hours / 720).toFixed(1)}mo`;
}

const DegenTable = ({ tokens, onSelect, selectedUid }) => {
  if (!tokens || tokens.length === 0) {
    return (
      <div className="degen-empty">
        No tokens match the current filters.
      </div>
    );
  }

  return (
    <div className="degen-table-wrap">
      <table className="degen-table">
        <thead>
          <tr>
            <th>#</th>
            <th>Token</th>
            <th>Chain</th>
            <th>Category</th>
            <th>Score</th>
            <th>Risk</th>
            <th>MCap</th>
            <th>Vol 24h</th>
            <th>Liquidity</th>
            <th>Age</th>
          </tr>
        </thead>
        <tbody>
          {tokens.map((t, i) => (
            <tr
              key={t.asset_uid}
              className={`degen-table__row ${selectedUid === t.asset_uid ? 'degen-table__row--selected' : ''}`}
              onClick={() => onSelect(t)}
            >
              <td className="degen-table__rank">{i + 1}</td>
              <td className="degen-table__token">
                <strong>{t.symbol}</strong>
                {t.active_alerts && t.active_alerts.map((a) => (
                  <AlertBadge key={a} alertType={a} />
                ))}
                <span className="degen-table__name">{t.name}</span>
              </td>
              <td><ChainIcon chain={t.chain} /></td>
              <td><CategoryBadge category={t.category} /></td>
              <td><DegenScoreBar score={t.universe_score || 0} /></td>
              <td><RiskBadge riskScore={t.risk_score || 0} /></td>
              <td>{fmtUsd(t.market_cap_usd)}</td>
              <td>{fmtUsd(t.volume_24h_usd)}</td>
              <td>{fmtUsd(t.liquidity_usd)}</td>
              <td>{fmtAge(t.age_hours)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
};

export default DegenTable;
