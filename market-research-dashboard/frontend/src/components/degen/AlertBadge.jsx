import React from 'react';

const ALERT_STYLES = {
  whale_accumulation: { label: 'Whale', bg: 'rgba(88,166,255,0.15)', color: '#93C5FD', border: 'rgba(88,166,255,0.4)' },
  liquidity_event: { label: 'Liq', bg: 'rgba(234,179,8,0.12)', color: '#FDE68A', border: 'rgba(234,179,8,0.35)' },
  rug_risk_detected: { label: 'Rug', bg: 'rgba(239,68,68,0.15)', color: '#FCA5A5', border: 'rgba(239,68,68,0.4)' },
  explosion_score_jump: { label: 'Boom', bg: 'rgba(134,239,172,0.15)', color: '#86EFAC', border: 'rgba(134,239,172,0.4)' },
};

const AlertBadge = ({ alertType }) => {
  const style = ALERT_STYLES[alertType];
  if (!style) return null;

  return (
    <span
      className="degen-badge"
      style={{
        background: style.bg,
        color: style.color,
        border: `1px solid ${style.border}`,
        fontSize: '0.65rem',
        marginLeft: '0.3rem',
      }}
      title={alertType.replace(/_/g, ' ')}
    >
      {style.label}
    </span>
  );
};

export default AlertBadge;
