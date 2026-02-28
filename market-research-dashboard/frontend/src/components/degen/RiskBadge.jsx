import React from 'react';

const RISK_CONFIG = {
  low:     { label: 'Low',     bg: 'var(--ml-green-soft)',  border: 'var(--ml-green-border)',  color: 'var(--ml-green-text)' },
  medium:  { label: 'Medium',  bg: 'var(--ml-yellow-soft)', border: 'var(--ml-yellow-border)', color: 'var(--ml-yellow-text)' },
  high:    { label: 'High',    bg: 'var(--ml-orange-soft)', border: 'var(--ml-orange-border)', color: 'var(--ml-orange-text)' },
  extreme: { label: 'Extreme', bg: 'var(--ml-red-soft)',    border: 'var(--ml-red-border)',    color: 'var(--ml-red-text)' },
};

function riskLevel(score) {
  if (score >= 75) return 'extreme';
  if (score >= 50) return 'high';
  if (score >= 25) return 'medium';
  return 'low';
}

const RiskBadge = ({ riskScore }) => {
  const level = riskLevel(riskScore);
  const cfg = RISK_CONFIG[level];
  return (
    <span
      className="degen-badge"
      style={{ background: cfg.bg, border: `1px solid ${cfg.border}`, color: cfg.color }}
    >
      {cfg.label}
    </span>
  );
};

export default RiskBadge;
