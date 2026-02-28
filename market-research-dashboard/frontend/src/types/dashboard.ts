// MarketLab Dashboard v2 — TypeScript types (spec §3.3)

export type DashboardMode = 'simple' | 'pro';
export type SignalState = 'green' | 'yellow' | 'orange' | 'red' | 'blocked';
export type SignalCardKey = 'trends' | 'fng' | 'rss' | 'reddit' | 'wikipedia' | 'onchain';
export type TimeUnit = 'day' | 'week';
export type RelationshipKind = 'predictive' | 'synchronous' | 'reactive' | 'emergent' | 'unknown';
export type DataQualityLevel = 'good' | 'warning' | 'poor';

export interface LeadMetric {
  value: number;
  unit: TimeUnit;
  correlation: number;
  pValue: number | null;
  kind: RelationshipKind;
  label: string;
}

export interface SecondaryFinding {
  signalId: string;
  label: string;
  lead: LeadMetric;
  sampleSize?: number;
}

export interface ConfidenceBreakdown {
  total: number;
  strength?: number;
  consistency?: number;
  regimeRobustness?: number;
  significance?: number;
  sampleSufficiency?: number;
  directionality?: number;
}

export interface RollingPoint {
  ts: string;
  window: '30d' | '60d' | '90d' | '8w' | '12w' | '26w';
  value: number;
}

export interface LagPoint {
  lag: number;
  unit: TimeUnit;
  correlation: number;
  pValue?: number | null;
}

export interface RegimeMetric {
  name: 'bull' | 'bear' | 'fear' | 'greed' | 'high_vol' | 'low_vol';
  correlation: number | null;
  pValue?: number | null;
  n?: number;
}

export interface AsymmetryMetric {
  negative: number | null;
  positive: number | null;
  delta?: number | null;
  dominantSide?: 'negative' | 'positive' | 'none';
}

export interface GrangerMetric {
  available: boolean;
  direction: 'signal_to_price' | 'price_to_signal' | 'bidirectional' | 'none' | 'pending';
  pValueForward: number | null;
  pValueReverse: number | null;
}

export interface BootstrapMetric {
  available: boolean;
  pValueMaxStat: number | null;
  ciLow?: number | null;
  ciHigh?: number | null;
}

export interface DataQualityNote {
  level: DataQualityLevel;
  code: string;
  message: string;
}

export interface NarrativeCopy {
  title: string;
  subtitle: string;
  summary: string;
  cta: string;
  disclaimer?: string;
}

export interface SignalCardData {
  cardKey: SignalCardKey;
  signalId: string;
  displayName: string;
  simpleName: string;
  state: SignalState;
  icon: 'search' | 'thermometer' | 'newspaper' | 'messages-off' | 'book-open' | 'link';
  confidence: number;
  confidenceBreakdown?: ConfidenceBreakdown;
  bestLead?: LeadMetric | null;
  secondaryFindings?: SecondaryFinding[];
  sampleSize?: number | null;
  minSampleRequired?: number | null;
  relationshipKind?: RelationshipKind;
  dataFrequency: 'daily' | 'weekly' | 'insufficient';
  narrative: {
    simple: NarrativeCopy;
    pro: NarrativeCopy;
  };
  stats?: {
    primaryCorrelation?: number | null;
    primaryPValue?: number | null;
    stabilityScore?: number | null;
    regimeBull?: number | null;
    regimeBear?: number | null;
    asymmetryNegative?: number | null;
    asymmetryPositive?: number | null;
  };
  detail?: SignalDetailData;
  dataQualityNotes?: DataQualityNote[];
  blockedReason?: string | null;
  progress?: {
    current: number;
    required: number;
    unit: 'days' | 'weeks' | 'observations';
  } | null;
}

export interface SignalDetailData {
  cardKey: SignalCardKey;
  selectedLead?: LeadMetric | null;
  normalizedOverlaySeries?: Array<{ ts: string; price: number; signal: number }>;
  rollingCorrelation?: RollingPoint[];
  lagProfile?: LagPoint[];
  regimeBreakdown?: RegimeMetric[];
  asymmetry?: AsymmetryMetric | null;
  granger?: GrangerMetric | null;
  bootstrap?: BootstrapMetric | null;
  confidenceBreakdown?: ConfidenceBreakdown | null;
  timelineNarrative?: Array<{
    ts: string;
    label: string;
    kind: 'signal' | 'price' | 'note';
  }>;
  dataQualityNotes?: DataQualityNote[];
}

export interface ForecastModelRow {
  modelId: string;
  label: string;
  sharpe?: number | null;
  maxDrawdown?: number | null;
  hitRate?: number | null;
  cagr?: number | null;
}

export interface ForecastPanelData {
  available: boolean;
  equityCurve: Array<{ ts: string; strategy: number; benchmark: number }>;
  models: ForecastModelRow[];
}

export interface DashboardRunData {
  runId: string;
  generatedAt: string;
  asset: string;
  modeDefault: DashboardMode;
  selectedSignalCardKey?: SignalCardKey;
  signals: SignalCardData[];
  forecast?: ForecastPanelData | null;
}
