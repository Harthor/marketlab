import React from 'react';
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

const Row = ({ label, value }) => (
  <div className="degen-detail__row">
    <span className="degen-detail__label">{label}</span>
    <span className="degen-detail__value">{value}</span>
  </div>
);

const DegenTokenDetail = ({ token, onClose }) => {
  if (!token) return null;

  return (
    <div className="degen-detail-panel">
      <div className="degen-detail__header">
        <div className="degen-detail__title">
          <ChainIcon chain={token.chain} />
          <h3>{token.symbol}</h3>
          <span className="degen-detail__name">{token.name}</span>
        </div>
        <button className="degen-detail__close" onClick={onClose}>x</button>
      </div>

      <div className="degen-detail__badges">
        <CategoryBadge category={token.category} />
        <RiskBadge riskScore={token.risk_score || 0} />
      </div>

      <div className="degen-detail__scores">
        <DegenScoreBar score={token.universe_score || 0} label="Universe Score" />
      </div>

      <div className="degen-detail__grid">
        <Row label="Market Cap" value={fmtUsd(token.market_cap_usd)} />
        <Row label="Liquidity" value={fmtUsd(token.liquidity_usd)} />
        <Row label="Volume 24h" value={fmtUsd(token.volume_24h_usd)} />
        <Row label="Price" value={token.price_usd != null ? `$${token.price_usd}` : '-'} />
        <Row label="Holders" value={token.holder_count?.toLocaleString() || '-'} />
        <Row label="Age" value={fmtAge(token.age_hours)} />
      </div>

      {token.attention_flags?.length > 0 && (
        <div className="degen-detail__section">
          <h4>Attention Flags</h4>
          <div className="degen-detail__flags">
            {token.attention_flags.map((f) => (
              <span key={f} className="degen-flag degen-flag--attention">{f}</span>
            ))}
          </div>
        </div>
      )}

      {token.security_flags?.length > 0 && (
        <div className="degen-detail__section">
          <h4>Security Flags</h4>
          <div className="degen-detail__flags">
            {token.security_flags.map((f) => (
              <span key={f} className="degen-flag degen-flag--security">{f}</span>
            ))}
          </div>
        </div>
      )}

      <div className="degen-detail__address">
        <span className="degen-detail__label">Address</span>
        <code>{token.token_address}</code>
      </div>
    </div>
  );
};

export default DegenTokenDetail;
