import React from 'react';

const CATEGORY_LABELS = {
  meme_bluechip: 'Meme Bluechip',
  meme_emerging: 'Meme Emerging',
  narrative_high_beta: 'Narrative',
  dex_new_launch: 'New Launch',
  pre_cex_watch: 'Pre-CEX',
  dead_or_toxic: 'Dead/Toxic',
  unclassified: 'Unclassified',
};

const CATEGORY_COLORS = {
  meme_bluechip: '#8b5cf6',
  meme_emerging: '#a78bfa',
  narrative_high_beta: '#3b82f6',
  dex_new_launch: '#f59e0b',
  pre_cex_watch: '#10b981',
  dead_or_toxic: '#6b7280',
  unclassified: '#6b7280',
};

const CategoryBadge = ({ category }) => {
  const label = CATEGORY_LABELS[category] || category;
  const color = CATEGORY_COLORS[category] || '#6b7280';
  return (
    <span
      className="degen-badge"
      style={{
        background: `${color}22`,
        border: `1px solid ${color}55`,
        color: color,
      }}
    >
      {label}
    </span>
  );
};

export default CategoryBadge;
