// MarketLab Dashboard v2 — State presentation helpers (spec §10.4, §12.2)

import type { SignalState } from '@/types/dashboard';

export const statePresentation = {
  green: {
    colorToken: 'ml.state.green',
    badgeLabelEs: 'Predictiva',
    badgeLabelEn: 'Predictive',
  },
  yellow: {
    colorToken: 'ml.state.yellow',
    badgeLabelEs: 'Contexto',
    badgeLabelEn: 'Context',
  },
  orange: {
    colorToken: 'ml.state.orange',
    badgeLabelEs: 'Emergente',
    badgeLabelEn: 'Emerging',
  },
  red: {
    colorToken: 'ml.state.red',
    badgeLabelEs: 'Debil',
    badgeLabelEn: 'Weak',
  },
  blocked: {
    colorToken: 'ml.state.blocked',
    badgeLabelEs: 'Bloqueada',
    badgeLabelEn: 'Blocked',
  },
} as const;

export function getStateStyles(state: SignalState) {
  switch (state) {
    case 'green':
      return {
        dot: 'bg-[var(--ml-green-500)]',
        border: 'border-[var(--ml-green-border)]',
        bg: 'bg-[var(--ml-green-soft)]',
        text: 'text-[#86EFAC]',
        ring: 'ring-[var(--ml-green-border)]',
        base: '#22C55E',
      };
    case 'yellow':
      return {
        dot: 'bg-[var(--ml-yellow-500)]',
        border: 'border-[var(--ml-yellow-border)]',
        bg: 'bg-[var(--ml-yellow-soft)]',
        text: 'text-[#FDE68A]',
        ring: 'ring-[var(--ml-yellow-border)]',
        base: '#EAB308',
      };
    case 'orange':
      return {
        dot: 'bg-[var(--ml-orange-500)]',
        border: 'border-[var(--ml-orange-border)]',
        bg: 'bg-[var(--ml-orange-soft)]',
        text: 'text-[#FDBA74]',
        ring: 'ring-[var(--ml-orange-border)]',
        base: '#F97316',
      };
    case 'red':
      return {
        dot: 'bg-[var(--ml-red-500)]',
        border: 'border-[var(--ml-red-border)]',
        bg: 'bg-[var(--ml-red-soft)]',
        text: 'text-[#FCA5A5]',
        ring: 'ring-[var(--ml-red-border)]',
        base: '#EF4444',
      };
    default:
      return {
        dot: 'bg-[var(--ml-blocked-500)]',
        border: 'border-[var(--ml-blocked-border)]',
        bg: 'bg-[var(--ml-blocked-soft)]',
        text: 'text-[#CBD5E1]',
        ring: 'ring-[var(--ml-blocked-border)]',
        base: '#64748B',
      };
  }
}
