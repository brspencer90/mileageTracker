import { useSyncExternalStore } from 'react'

const QUERY = '(prefers-color-scheme: dark)'

function subscribe(onChange: () => void): () => void {
  const mql = window.matchMedia(QUERY)
  mql.addEventListener('change', onChange)
  return () => mql.removeEventListener('change', onChange)
}

export function usePrefersDark(): boolean {
  return useSyncExternalStore(
    subscribe,
    () => window.matchMedia(QUERY).matches,
    () => false,
  )
}

/**
 * Chart color tokens (dataviz reference palette). Recharts sets SVG
 * presentation attributes, where CSS var() doesn't resolve, so charts
 * consume plain hex from this hook; the dark set is the palette's own
 * dark-surface steps, not an automatic flip.
 */
export interface ChartTheme {
  /** categorical slot 1 (single series) — the mockup accent */
  series: string
  surface: string
  grid: string
  baseline: string
  axisText: string
  /** muted ink for reference-line + its label */
  muted: string
  /** faint per-fill dot-cloud fill */
  dot: string
  textPrimary: string
  textSecondary: string
  /** ghost wash for bar hover cursor */
  hoverWash: string
}

const LIGHT: ChartTheme = {
  series: '#2a78d6',
  surface: '#ffffff',
  grid: '#e4e7ec',
  baseline: '#c6ccd4',
  axisText: '#79818c',
  muted: '#79818c',
  dot: 'rgba(42, 120, 214, 0.28)',
  textPrimary: '#10141a',
  textSecondary: '#47505b',
  hoverWash: 'rgba(15, 22, 34, 0.06)',
}

const DARK: ChartTheme = {
  series: '#3d8bf0',
  surface: '#17191d',
  grid: '#26292e',
  baseline: '#3a3f46',
  axisText: '#7c838d',
  muted: '#7c838d',
  dot: 'rgba(120, 170, 235, 0.3)',
  textPrimary: '#f2f4f7',
  textSecondary: '#b7bdc6',
  hoverWash: 'rgba(255, 255, 255, 0.08)',
}

export function useChartTheme(): ChartTheme {
  return usePrefersDark() ? DARK : LIGHT
}
