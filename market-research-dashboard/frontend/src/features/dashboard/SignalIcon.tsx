// MarketLab Dashboard v2 — SignalIcon (spec §5.3)

import { Search, ThermometerSun, Newspaper, MessageSquareOff, BookOpen, Link2 } from 'lucide-react';
import type { SignalCardData } from '@/types/dashboard';

type IconType = SignalCardData['icon'];

interface SignalIconProps {
  icon: IconType;
  className?: string;
  size?: number;
}

const iconMap = {
  search: Search,
  thermometer: ThermometerSun,
  newspaper: Newspaper,
  'messages-off': MessageSquareOff,
  'book-open': BookOpen,
  link: Link2,
} as const;

export default function SignalIcon({ icon, className = '', size = 18 }: SignalIconProps) {
  const IconComponent = iconMap[icon];
  return <IconComponent size={size} className={className} />;
}
