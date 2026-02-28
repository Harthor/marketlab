// MarketLab Dashboard v2 — i18n (spec §6)

export type Locale = 'es' | 'en';

const translations = {
  es: {
    modeToggle: {
      simple: 'Simple',
      pro: 'Pro',
      simple_tooltip: 'Explicaciones claras y menos estadistica',
      pro_tooltip: 'Mas metricas, lags, regimenes y significancia',
    },
    common: {
      confidence: 'Confianza',
      stability: 'Estabilidad',
      sample: 'Muestra',
      best_lead: 'Mejor adelanto',
      best_lead_pro: 'Best lead',
      predictive: 'predictiva',
      synchronous: 'sincronica',
      reactive: 'reactiva',
      emergent: 'emergente',
      blocked: 'bloqueada',
      pending: 'pendiente',
      view_more: 'Ver mas',
      view_details: 'Ver detalle',
      configure_alerts: 'Configurar alertas',
      usage: 'Uso',
      data: 'Datos',
      best_finding: 'Mejor hallazgo',
      progress: 'Progreso',
      status: 'Estado',
      not_analyzable: 'aun no analizable',
      daily: 'Diario',
      weekly: 'Semanal',
      insufficient: 'Bloqueado',
      models_backtests: 'Modelos y backtests',
      view_models: 'Ver modelos',
      last_update: 'Ultima actualizacion',
      main_signal: 'senal principal',
      context_indicator: 'indicador de contexto',
    },
    detail: {
      what_means: 'Que significa esto?',
      human_summary: 'Resumen',
      lag_profile: 'Perfil de lag',
      rolling_corr: 'Correlacion rolling',
      regime_breakdown: 'Regimenes',
      granger_direction: 'Direccion Granger',
      bootstrap_confidence: 'Bootstrap',
      stability_score: 'Score de estabilidad',
      data_quality: 'Calidad de datos',
      blocked_title: 'Senal bloqueada',
      blocked_checklist_days: '60+ dias de historial',
      blocked_checklist_coverage: 'Cobertura continua',
      blocked_checklist_gaps: 'Sin gaps criticos',
      blocked_progress: 'Progreso hacia desbloqueo',
      observations: 'observaciones',
      minimum: 'minimo',
      analogies: {
        trends: 'Es como mirar cuanta gente busca paraguas antes de que empiece a llover.',
        fng: 'Es como un termometro que sube despues de que la habitacion ya se calento.',
        rss: 'Es como escuchar mas ruido en las noticias antes de que el mercado termine de reaccionar.',
        reddit: 'Todavia no hay suficientes conversaciones guardadas como para saber si la multitud llega antes o despues.',
      },
      timeline: {
        trends: [
          'Hace 2 semanas: subieron busquedas de "bitcoin"',
          'Hoy: BTC mostro movimiento al alza',
        ],
        fng: [
          'Ayer: BTC se movio fuerte',
          'Hoy: cambio el indice de miedo/codicia',
        ],
        rss: [
          'Hace 2 dias: aumento el tono positivo en noticias',
          'Hoy: BTC mostro una respuesta moderada',
        ],
        reddit: [],
      },
    },
    cards: {
      trends: {
        title_simple: 'Atencion publica',
        title_pro: 'Google Trends (Atencion)',
        subtitle_simple: 'Que esta buscando la gente sobre Bitcoin.',
        subtitle_pro: 'Interes de busqueda normalizado por keyword.',
        confidence_tooltip: 'Combina fuerza de correlacion, estabilidad temporal y suficiencia de muestra.',
        states: {
          green: {
            summary_simple: 'Las busquedas de Bitcoin anticipan movimientos del precio con 1-2 semanas de adelanto.',
            summary_pro: 'La atencion publica muestra relacion predictiva robusta; la mejor senal actual es bitcoin_pct_change a +2w (r=0.38, p=0.001).',
            cta_simple: 'Ver por que anticipa',
            cta_pro: 'Abrir lag profile',
          },
          yellow: {
            summary_simple: 'Las busquedas se relacionan con el precio, pero no siempre llegan antes. Usalo como apoyo, no como senal principal.',
            summary_pro: 'Existe correlacion util, pero la estabilidad o la direccion temporal no alcanza para declararla predictiva de forma consistente.',
            cta_simple: 'Ver cuando falla',
            cta_pro: 'Revisar estabilidad',
          },
          orange: {
            summary_simple: 'La atencion publica parece prometer, pero todavia faltan datos o consistencia para confiar.',
            summary_pro: 'Hay indicios de senal, pero el tamano de muestra, la estabilidad rolling o la correccion por multiples lags aun no sostienen un estado fuerte.',
            cta_simple: 'Ver que falta',
            cta_pro: 'Revisar muestra',
          },
          red: {
            summary_simple: 'En este periodo, las busquedas no ayudan a anticipar el precio.',
            summary_pro: 'No hay evidencia robusta de relacion utilizable tras corregir por significancia y estabilidad temporal.',
            cta_simple: 'Ver por que no sirve',
            cta_pro: 'Inspeccionar resultados',
          },
          blocked: {
            summary_simple: 'No hay suficientes datos de busquedas para analizar esta senal.',
            summary_pro: 'El dataset no tiene historia suficiente o presenta problemas de calidad que impiden el analisis.',
            cta_simple: 'Ver requisitos',
            cta_pro: 'Ver requisitos',
          },
        },
      },
      fng: {
        title_simple: 'Clima del mercado',
        title_pro: 'Fear & Greed Index (FGI)',
        subtitle_simple: 'Mide miedo y codicia en cripto.',
        subtitle_pro: 'Sentimiento agregado 0-100.',
        confidence_tooltip: 'Combina fuerza estadistica, estabilidad y utilidad practica. En FGI el score baja si la senal es principalmente reactiva.',
        states: {
          green: {
            summary_simple: 'El clima del mercado se mueve antes que el precio con suficiente consistencia para usarlo como senal.',
            summary_pro: 'El FGI muestra evidencia adelantada y estabilidad suficiente para uso operativo, no solo de contexto.',
            cta_simple: 'Ver adelanto',
            cta_pro: 'Abrir lag profile',
          },
          yellow: {
            summary_simple: 'El indice de miedo/codicia refleja lo que ya paso en el precio mas de lo que anticipa lo proximo.',
            summary_pro: 'La senal es estadisticamente real, pero principalmente reactiva; util para regimen y contexto, no como predictor principal.',
            cta_simple: 'Ver como usarlo',
            cta_pro: 'Ver uso como contexto',
          },
          orange: {
            summary_simple: 'El clima del mercado muestra algo de senal, pero todavia es demasiado fragil para confiar.',
            summary_pro: 'Hay correlaciones parciales, aunque la estabilidad o la muestra no alcanzan para una lectura fuerte.',
            cta_simple: 'Ver que falta',
            cta_pro: 'Revisar fragilidad',
          },
          red: {
            summary_simple: 'El indice no esta aportando una lectura util en este periodo.',
            summary_pro: 'No hay evidencia robusta de relacion util una vez controlados rezagos y significancia.',
            cta_simple: 'Ver diagnostico',
            cta_pro: 'Inspeccionar diagnostico',
          },
          blocked: {
            summary_simple: 'No hay suficientes datos del indice para analizarlo.',
            summary_pro: 'FGI no disponible o incompleto para el periodo seleccionado.',
            cta_simple: 'Ver requisitos',
            cta_pro: 'Ver requisitos',
          },
        },
      },
      rss: {
        title_simple: 'Pulso de noticias',
        title_pro: 'RSS + FinBERT (Noticias)',
        subtitle_simple: 'Tono y volumen de medios crypto.',
        subtitle_pro: 'Conteo de articulos y sentimiento agregado.',
        confidence_tooltip: 'Combina fuerza de correlacion, estabilidad y suficiencia de muestra. En RSS penaliza fuerte cuando N es menor al minimo recomendado.',
        states: {
          green: {
            summary_simple: 'El tono de las noticias se mueve antes que el precio y ya tiene suficiente historial para confiar.',
            summary_pro: 'Las metricas de noticias muestran relacion adelantada, significativa y estable, con muestra suficiente.',
            cta_simple: 'Ver senales lideres',
            cta_pro: 'Abrir detalle',
          },
          yellow: {
            summary_simple: 'Las noticias ayudan a leer el contexto, pero todavia no son una senal principal.',
            summary_pro: 'Existe relacion util, aunque su fuerza o estabilidad todavia es moderada y dependiente del regimen.',
            cta_simple: 'Ver contexto',
            cta_pro: 'Ver regimen',
          },
          orange: {
            summary_simple: 'Senal emergente: el sentimiento de noticias crypto muestra correlacion, pero necesitamos mas datos para confirmar.',
            summary_pro: 'Hay correlaciones prometedoras, pero la muestra aun es corta y varias metricas siguen en territorio exploratorio.',
            cta_simple: 'Ver que falta',
            cta_pro: 'Revisar muestra',
          },
          red: {
            summary_simple: 'Las noticias no estan aportando una relacion consistente con el precio.',
            summary_pro: 'No hay evidencia robusta de senal una vez corregidos p-values, muestra y estabilidad temporal.',
            cta_simple: 'Ver diagnostico',
            cta_pro: 'Inspeccionar resultados',
          },
          blocked: {
            summary_simple: 'Todavia no hay suficientes noticias procesadas para analizar esta senal.',
            summary_pro: 'Dataset insuficiente o fallas de parsing/sentiment impiden el analisis actual.',
            cta_simple: 'Ver requisitos',
            cta_pro: 'Ver requisitos',
          },
        },
      },
      reddit: {
        title_simple: 'Conversacion social',
        title_pro: 'Reddit / Social',
        subtitle_simple: 'Actividad social y sentimiento en comunidades.',
        subtitle_pro: 'Historico social y sentimiento agregado.',
        confidence_tooltip: 'La confianza solo aparece cuando existe suficiente historico. Mientras este bloqueado, mostrar progreso y requisitos.',
        states: {
          green: {
            summary_simple: 'La conversacion social se adelanta al precio con suficiente consistencia para usarla como senal.',
            summary_pro: 'El historico social ya muestra relacion adelantada, estable y estadisticamente valida.',
            cta_simple: 'Ver adelanto',
            cta_pro: 'Abrir lag profile',
          },
          yellow: {
            summary_simple: 'La conversacion social acompana al mercado, pero no siempre llega antes.',
            summary_pro: 'La relacion existe, aunque es mixta o reactiva y todavia no alcanza para semaforo verde.',
            cta_simple: 'Ver como leerla',
            cta_pro: 'Ver estabilidad',
          },
          orange: {
            summary_simple: 'La conversacion social empieza a mostrar patron, pero todavia faltan observaciones para confiar.',
            summary_pro: 'Hay indicios iniciales, aunque la muestra o la estabilidad aun no sostienen una lectura robusta.',
            cta_simple: 'Ver progreso',
            cta_pro: 'Revisar muestra',
          },
          red: {
            summary_simple: 'En este periodo, la conversacion social no ayuda a explicar el precio.',
            summary_pro: 'No hay evidencia robusta de relacion utilizable una vez aplicados los controles estadisticos.',
            cta_simple: 'Ver diagnostico',
            cta_pro: 'Inspeccionar resultados',
          },
          blocked: {
            summary_simple: 'Acumulando datos. Necesitamos mas historial antes de analizar esta senal.',
            summary_pro: 'Historico insuficiente para calculo de correlaciones, rolling windows y significancia robusta.',
            cta_simple: 'Configurar alertas',
            cta_pro: 'Ver requisitos',
          },
        },
      },
    },
  },
  en: {
    modeToggle: {
      simple: 'Simple',
      pro: 'Pro',
      simple_tooltip: 'Clear explanations with less statistics',
      pro_tooltip: 'More metrics, lags, regimes, and significance',
    },
    common: {
      confidence: 'Confidence',
      stability: 'Stability',
      sample: 'Sample',
      best_lead: 'Best lead',
      best_lead_pro: 'Best lead',
      predictive: 'predictive',
      synchronous: 'synchronous',
      reactive: 'reactive',
      emergent: 'emergent',
      blocked: 'blocked',
      pending: 'pending',
      view_more: 'View more',
      view_details: 'View details',
      configure_alerts: 'Set alerts',
      usage: 'Usage',
      data: 'Data',
      best_finding: 'Best finding',
      progress: 'Progress',
      status: 'Status',
      not_analyzable: 'not yet analyzable',
      daily: 'Daily',
      weekly: 'Weekly',
      insufficient: 'Blocked',
      models_backtests: 'Models & backtests',
      view_models: 'View models',
      last_update: 'Last update',
      main_signal: 'main signal',
      context_indicator: 'context indicator',
    },
    detail: {
      what_means: 'What does this mean?',
      human_summary: 'Summary',
      lag_profile: 'Lag profile',
      rolling_corr: 'Rolling correlation',
      regime_breakdown: 'Regimes',
      granger_direction: 'Granger direction',
      bootstrap_confidence: 'Bootstrap',
      stability_score: 'Stability score',
      data_quality: 'Data quality',
      blocked_title: 'Signal blocked',
      blocked_checklist_days: '60+ days of history',
      blocked_checklist_coverage: 'Continuous coverage',
      blocked_checklist_gaps: 'No critical gaps',
      blocked_progress: 'Progress toward unlock',
      observations: 'observations',
      minimum: 'minimum',
      analogies: {
        trends: 'It is like watching how many people search for umbrellas before it starts raining.',
        fng: 'It is like a thermometer that rises after the room is already warm.',
        rss: 'It is like hearing more noise in the news before the market finishes reacting.',
        reddit: 'There are not yet enough saved conversations to know if the crowd arrives before or after.',
      },
      timeline: {
        trends: [
          '2 weeks ago: Bitcoin searches rose',
          'Today: BTC showed upward movement',
        ],
        fng: [
          'Yesterday: BTC moved sharply',
          'Today: fear/greed index changed',
        ],
        rss: [
          '2 days ago: positive tone in news increased',
          'Today: BTC showed a moderate response',
        ],
        reddit: [],
      },
    },
    cards: {
      trends: {
        title_simple: 'Public attention',
        title_pro: 'Google Trends (Attention)',
        subtitle_simple: 'What people are searching about Bitcoin.',
        subtitle_pro: 'Normalized search interest by keyword.',
        confidence_tooltip: 'Combines correlation strength, temporal stability, and sample sufficiency.',
        states: {
          green: {
            summary_simple: 'Bitcoin searches are leading price moves by 1-2 weeks.',
            summary_pro: 'Public attention shows a robust predictive relationship; the current best signal is bitcoin_pct_change at +2w (r=0.38, p=0.001).',
            cta_simple: 'See why it leads',
            cta_pro: 'Open lag profile',
          },
          yellow: {
            summary_simple: 'Search interest is related to price, but it does not consistently move first.',
            summary_pro: 'The relationship is useful, but temporal direction or stability is not strong enough.',
            cta_simple: 'See when it fails',
            cta_pro: 'Review stability',
          },
          orange: {
            summary_simple: 'Public attention looks promising, but there is not enough data to trust it fully.',
            summary_pro: 'There are signs of signal, but sample size or rolling stability still do not support a strong state.',
            cta_simple: 'See what is missing',
            cta_pro: 'Review sample',
          },
          red: {
            summary_simple: 'In this period, search activity is not helping anticipate price.',
            summary_pro: 'No robust usable relationship after accounting for significance and temporal stability.',
            cta_simple: 'See why it fails',
            cta_pro: 'Inspect results',
          },
          blocked: {
            summary_simple: 'There is not enough search data to analyze this signal.',
            summary_pro: 'The dataset lacks enough history or has quality issues that prevent analysis.',
            cta_simple: 'See requirements',
            cta_pro: 'See requirements',
          },
        },
      },
      fng: {
        title_simple: 'Market mood',
        title_pro: 'Fear & Greed Index (FGI)',
        subtitle_simple: 'Measures fear and greed in crypto.',
        subtitle_pro: 'Aggregate sentiment index from 0 to 100.',
        confidence_tooltip: 'Combines statistical strength, stability, and practical usefulness.',
        states: {
          green: {
            summary_simple: 'Market mood is moving before price often enough to use it as a signal.',
            summary_pro: 'FGI shows leading evidence and enough stability for operational use.',
            cta_simple: 'See the lead',
            cta_pro: 'Open lag profile',
          },
          yellow: {
            summary_simple: 'The fear/greed index reflects what already happened more than what comes next.',
            summary_pro: 'The signal is statistically real but mainly reactive; useful for regime and context.',
            cta_simple: 'See how to use it',
            cta_pro: 'View context usage',
          },
          orange: {
            summary_simple: 'Market mood shows some signal, but it is still too fragile to trust.',
            summary_pro: 'There are partial correlations, but stability or sample size does not support a strong reading.',
            cta_simple: 'See what is missing',
            cta_pro: 'Review fragility',
          },
          red: {
            summary_simple: 'The index is not adding a useful reading in this period.',
            summary_pro: 'No robust usable relationship once lag structure and significance are controlled.',
            cta_simple: 'See diagnosis',
            cta_pro: 'Inspect diagnosis',
          },
          blocked: {
            summary_simple: 'There is not enough index data to analyze it.',
            summary_pro: 'FGI is unavailable or incomplete for the selected period.',
            cta_simple: 'See requirements',
            cta_pro: 'See requirements',
          },
        },
      },
      rss: {
        title_simple: 'News pulse',
        title_pro: 'RSS + FinBERT (News)',
        subtitle_simple: 'Tone and volume from crypto media.',
        subtitle_pro: 'Article counts, mentions, and aggregated sentiment.',
        confidence_tooltip: 'Combines correlation strength, stability, and sample sufficiency.',
        states: {
          green: {
            summary_simple: 'News tone is moving before price and has enough history to trust it.',
            summary_pro: 'News metrics show a leading, significant, and stable relationship with enough sample.',
            cta_simple: 'See leading signals',
            cta_pro: 'Open details',
          },
          yellow: {
            summary_simple: 'News helps read context, but it is not a primary signal yet.',
            summary_pro: 'There is a useful relationship, but strength or stability is still moderate.',
            cta_simple: 'See context',
            cta_pro: 'View regimes',
          },
          orange: {
            summary_simple: 'Emerging signal: crypto news sentiment shows correlation, but we need more data.',
            summary_pro: 'Promising correlations, but the sample is still short and several metrics remain exploratory.',
            cta_simple: 'See what is missing',
            cta_pro: 'Review sample',
          },
          red: {
            summary_simple: 'News is not adding a consistent relationship with price right now.',
            summary_pro: 'No robust signal after correcting for p-values, sample size, and temporal stability.',
            cta_simple: 'See diagnosis',
            cta_pro: 'Inspect results',
          },
          blocked: {
            summary_simple: 'There are not enough processed news records to analyze this signal.',
            summary_pro: 'Insufficient dataset or parsing/sentiment failures prevent analysis.',
            cta_simple: 'See requirements',
            cta_pro: 'See requirements',
          },
        },
      },
      reddit: {
        title_simple: 'Social conversation',
        title_pro: 'Reddit / Social',
        subtitle_simple: 'Community activity and sentiment.',
        subtitle_pro: 'Historical social activity and aggregated sentiment.',
        confidence_tooltip: 'Confidence only appears once enough history exists.',
        states: {
          green: {
            summary_simple: 'Social conversation is leading price with enough consistency to use as a signal.',
            summary_pro: 'The social history shows a leading, stable, statistically valid relationship.',
            cta_simple: 'See the lead',
            cta_pro: 'Open lag profile',
          },
          yellow: {
            summary_simple: 'Social conversation follows the market, but does not always move first.',
            summary_pro: 'The relationship exists, but is mixed or reactive, not strong enough for green.',
            cta_simple: 'See how to read it',
            cta_pro: 'View stability',
          },
          orange: {
            summary_simple: 'Social conversation is starting to show a pattern, but more observations are needed.',
            summary_pro: 'There are early signs, but the sample or stability still does not support a robust reading.',
            cta_simple: 'See progress',
            cta_pro: 'Review sample',
          },
          red: {
            summary_simple: 'In this period, social conversation is not helping explain price.',
            summary_pro: 'No robust usable relationship after statistical controls are applied.',
            cta_simple: 'See diagnosis',
            cta_pro: 'Inspect results',
          },
          blocked: {
            summary_simple: 'Collecting data. We need more history before analyzing this signal.',
            summary_pro: 'Insufficient history for correlations, rolling windows, and robust significance.',
            cta_simple: 'Set alerts',
            cta_pro: 'See requirements',
          },
        },
      },
    },
  },
} as const;

export type I18nTree = typeof translations;

/** Helper to get a nested translation value by dot-path */
export function t(locale: Locale, path: string): string {
  const keys = path.split('.');
  let current: unknown = translations[locale];
  for (const key of keys) {
    if (current && typeof current === 'object' && key in (current as Record<string, unknown>)) {
      current = (current as Record<string, unknown>)[key];
    } else {
      return path; // fallback: return key path
    }
  }
  return typeof current === 'string' ? current : path;
}

export default translations;
