import React from 'react';

const CHAIN_CONFIG = {
  solana: { label: 'SOL', color: '#9945FF' },
  base:   { label: 'BASE', color: '#0052FF' },
  bsc:    { label: 'BSC', color: '#F0B90B' },
};

const ChainIcon = ({ chain }) => {
  const cfg = CHAIN_CONFIG[chain] || { label: chain?.toUpperCase() || '?', color: '#6b7280' };
  return (
    <span
      className="degen-chain-icon"
      style={{ background: `${cfg.color}28`, color: cfg.color, borderColor: `${cfg.color}55` }}
    >
      {cfg.label}
    </span>
  );
};

export default ChainIcon;
