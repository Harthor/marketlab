// MarketLab Dashboard v2 — Mock data (spec §10.3)

import type { DashboardRunData } from '@/types/dashboard';

export const mockDashboardRun: DashboardRunData = {
  runId: 'dashboard_btc_2026-02-28',
  generatedAt: '2026-02-28T00:00:00Z',
  asset: 'BTC-USD',
  modeDefault: 'simple',
  selectedSignalCardKey: 'trends',
  signals: [
    // ── Google Trends — GREEN ──────────────────────────────────────
    {
      cardKey: 'trends',
      signalId: 'gt_bitcoin',
      displayName: 'Google Trends (Atencion)',
      simpleName: 'Atencion publica',
      state: 'green',
      icon: 'search',
      confidence: 82,
      relationshipKind: 'predictive',
      dataFrequency: 'weekly',
      bestLead: {
        value: 2,
        unit: 'week',
        correlation: 0.38,
        pValue: 0.001,
        kind: 'predictive',
        label: '+2w',
      },
      secondaryFindings: [
        {
          signalId: 'crypto_pct_change',
          label: 'Crypto searches',
          lead: {
            value: 0,
            unit: 'week',
            correlation: 0.41,
            pValue: 0.0003,
            kind: 'synchronous',
            label: '0w',
          },
        },
        {
          signalId: 'buy_bitcoin_delta',
          label: 'Buy Bitcoin searches',
          lead: {
            value: 1,
            unit: 'week',
            correlation: 0.32,
            pValue: 0.006,
            kind: 'predictive',
            label: '+1w',
          },
        },
      ],
      sampleSize: null,
      minSampleRequired: null,
      narrative: {
        simple: {
          title: 'Atencion publica',
          subtitle: 'Que esta buscando la gente sobre Bitcoin.',
          summary:
            'Las busquedas de Bitcoin anticipan movimientos del precio con 1-2 semanas de adelanto.',
          cta: 'Ver por que anticipa',
        },
        pro: {
          title: 'Google Trends (Atencion)',
          subtitle: 'Interes de busqueda normalizado por keyword.',
          summary:
            'La atencion publica muestra relacion predictiva robusta; la mejor senal actual es bitcoin_pct_change a +2w.',
          cta: 'Abrir lag profile',
        },
      },
      stats: {
        primaryCorrelation: 0.38,
        primaryPValue: 0.001,
        stabilityScore: 82,
      },
      detail: {
        cardKey: 'trends',
        selectedLead: {
          value: 2,
          unit: 'week',
          correlation: 0.38,
          pValue: 0.001,
          kind: 'predictive',
          label: '+2w',
        },
        rollingCorrelation: [],
        lagProfile: [],
        regimeBreakdown: [],
        bootstrap: { available: false, pValueMaxStat: null },
        granger: {
          available: false,
          direction: 'pending',
          pValueForward: null,
          pValueReverse: null,
        },
        confidenceBreakdown: {
          total: 82,
          strength: 81,
          consistency: 79,
          regimeRobustness: 70,
          significance: 88,
          sampleSufficiency: 90,
        },
      },
      dataQualityNotes: [
        {
          level: 'warning',
          code: 'WEEKLY_ALIGNMENT',
          message: 'Dato semanal; evitar comparar como si fuera diario.',
        },
      ],
    },

    // ── Fear & Greed — YELLOW ──────────────────────────────────────
    {
      cardKey: 'fng',
      signalId: 'fng_value_delta',
      displayName: 'Fear & Greed Index (FGI)',
      simpleName: 'Clima del mercado',
      state: 'yellow',
      icon: 'thermometer',
      confidence: 48,
      relationshipKind: 'reactive',
      dataFrequency: 'daily',
      bestLead: {
        value: -1,
        unit: 'day',
        correlation: 0.62,
        pValue: 0.0001,
        kind: 'reactive',
        label: '-1d',
      },
      secondaryFindings: [
        {
          signalId: 'fng_zscore_30d',
          label: 'FGI z-score 30d',
          lead: {
            value: -1,
            unit: 'day',
            correlation: 0.35,
            pValue: 0.0001,
            kind: 'reactive',
            label: '-1d',
          },
        },
      ],
      narrative: {
        simple: {
          title: 'Clima del mercado',
          subtitle: 'Mide miedo y codicia en cripto.',
          summary:
            'El indice de miedo/codicia refleja lo que ya paso en el precio mas de lo que anticipa lo proximo.',
          cta: 'Ver como usarlo',
        },
        pro: {
          title: 'Fear & Greed Index (FGI)',
          subtitle: 'Sentimiento agregado 0-100.',
          summary:
            'La senal es estadisticamente real, pero principalmente reactiva; util para contexto y regimen.',
          cta: 'Ver uso como contexto',
        },
      },
      stats: {
        primaryCorrelation: 0.62,
        primaryPValue: 0.0001,
        stabilityScore: 48,
      },
      detail: {
        cardKey: 'fng',
        selectedLead: {
          value: -1,
          unit: 'day',
          correlation: 0.62,
          pValue: 0.0001,
          kind: 'reactive',
          label: '-1d',
        },
        rollingCorrelation: [],
        lagProfile: [],
        regimeBreakdown: [
          { name: 'fear', correlation: -0.16, pValue: 0.0001 },
        ],
        bootstrap: { available: false, pValueMaxStat: null },
        granger: {
          available: false,
          direction: 'pending',
          pValueForward: null,
          pValueReverse: null,
        },
        confidenceBreakdown: {
          total: 48,
          strength: 75,
          consistency: 60,
          regimeRobustness: 42,
          significance: 84,
          sampleSufficiency: 90,
          directionality: 12,
        },
      },
    },

    // ── RSS + FinBERT — ORANGE ─────────────────────────────────────
    {
      cardKey: 'rss',
      signalId: 'positive_ratio',
      displayName: 'RSS + FinBERT (Noticias)',
      simpleName: 'Pulso de noticias',
      state: 'orange',
      icon: 'newspaper',
      confidence: 29,
      relationshipKind: 'emergent',
      dataFrequency: 'daily',
      bestLead: {
        value: 2,
        unit: 'day',
        correlation: 0.18,
        pValue: 0.099,
        kind: 'emergent',
        label: '+2d',
      },
      secondaryFindings: [
        {
          signalId: 'sentiment_delta',
          label: 'Sentiment delta',
          lead: {
            value: 0,
            unit: 'day',
            correlation: 0.23,
            pValue: 0.029,
            kind: 'synchronous',
            label: '0d',
          },
          sampleSize: 87,
        },
        {
          signalId: 'sentiment_finbert_std',
          label: 'FinBERT std',
          lead: {
            value: -10,
            unit: 'day',
            correlation: 0.27,
            pValue: 0.011,
            kind: 'reactive',
            label: '-10d',
          },
          sampleSize: 88,
        },
      ],
      sampleSize: 88,
      minSampleRequired: 180,
      narrative: {
        simple: {
          title: 'Pulso de noticias',
          subtitle: 'Tono y volumen de medios crypto.',
          summary:
            'Senal emergente: el sentimiento de noticias crypto muestra correlacion, pero necesitamos mas datos para confirmar.',
          cta: 'Ver que falta',
        },
        pro: {
          title: 'RSS + FinBERT (Noticias)',
          subtitle: 'Conteo de articulos y sentimiento agregado.',
          summary:
            'Hay correlaciones prometedoras, pero la muestra aun es corta y varias metricas siguen en territorio exploratorio.',
          cta: 'Revisar muestra',
        },
      },
      stats: {
        primaryCorrelation: 0.18,
        primaryPValue: 0.099,
        stabilityScore: 29,
      },
      progress: {
        current: 88,
        required: 180,
        unit: 'days',
      },
      detail: {
        cardKey: 'rss',
        selectedLead: {
          value: 2,
          unit: 'day',
          correlation: 0.18,
          pValue: 0.099,
          kind: 'emergent',
          label: '+2d',
        },
        rollingCorrelation: [],
        lagProfile: [],
        regimeBreakdown: [],
        bootstrap: { available: false, pValueMaxStat: null },
        granger: {
          available: false,
          direction: 'pending',
          pValueForward: null,
          pValueReverse: null,
        },
        confidenceBreakdown: {
          total: 29,
          strength: 35,
          consistency: 20,
          regimeRobustness: 18,
          significance: 32,
          sampleSufficiency: 22,
        },
      },
      dataQualityNotes: [
        {
          level: 'warning',
          code: 'SHORT_HISTORY',
          message: 'Muestra corta: 88 observaciones, minimo recomendado 180.',
        },
      ],
    },

    // ── Reddit — BLOCKED ───────────────────────────────────────────
    {
      cardKey: 'reddit',
      signalId: 'reddit_sentiment',
      displayName: 'Reddit / Social',
      simpleName: 'Conversacion social',
      state: 'blocked',
      icon: 'messages-off',
      confidence: 0,
      relationshipKind: 'unknown',
      dataFrequency: 'insufficient',
      bestLead: null,
      sampleSize: 1,
      minSampleRequired: 60,
      narrative: {
        simple: {
          title: 'Conversacion social',
          subtitle: 'Actividad social y sentimiento en comunidades.',
          summary:
            'Acumulando datos. Necesitamos mas historial antes de analizar esta senal.',
          cta: 'Configurar alertas',
        },
        pro: {
          title: 'Reddit / Social',
          subtitle: 'Historico social y sentimiento agregado.',
          summary:
            'Historico insuficiente para calculo de correlaciones, rolling windows y significancia robusta.',
          cta: 'Ver requisitos',
        },
      },
      progress: {
        current: 1,
        required: 60,
        unit: 'days',
      },
      blockedReason: 'N insuficiente para correlacion',
      detail: {
        cardKey: 'reddit',
        timelineNarrative: [],
        dataQualityNotes: [
          {
            level: 'poor',
            code: 'N_TOO_SMALL',
            message: 'Solo 1 observacion disponible; minimo recomendado 60.',
          },
        ],
      },
    },
  ],
  forecast: null,
};
