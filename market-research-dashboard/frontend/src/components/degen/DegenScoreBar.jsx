import React from 'react';

const DegenScoreBar = ({ score, label = 'Score' }) => {
  const pct = Math.min(100, Math.max(0, score));
  const color =
    pct >= 80 ? 'var(--ml-green-500)' :
    pct >= 60 ? 'var(--ml-yellow-500)' :
    pct >= 40 ? 'var(--ml-orange-500)' :
    'var(--ml-red-500)';

  return (
    <div className="degen-score-bar" title={`${label}: ${score.toFixed(1)}`}>
      <div className="degen-score-bar__track">
        <div
          className="degen-score-bar__fill"
          style={{ width: `${pct}%`, background: color }}
        />
      </div>
      <span className="degen-score-bar__value">{score.toFixed(1)}</span>
    </div>
  );
};

export default DegenScoreBar;
