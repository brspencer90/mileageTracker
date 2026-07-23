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
  /** categorical slot 1 (single series) */
  series: string
  surface: string
  grid: string
  baseline: string
  axisText: string
  textPrimary: string
  textSecondary: string
  /** ghost wash for bar hover cursor */
  hoverWash: string
}

const LIGHT: ChartTheme = {
  series: '#2a78d6',
  surface: '#fcfcfb',
  grid: '#e1e0d9',
  baseline: '#c3c2b7',
  axisText: '#898781',
  textPrimary: '#0b0b0b',
  textSecondary: '#52514e',
  hoverWash: 'rgba(11, 11, 11, 0.06)',
}

const DARK: ChartTheme = {
  series: '#3987e5',
  surface: '#1a1a19',
  grid: '#2c2c2a',
  baseline: '#383835',
  axisText: '#898781',
  textPrimary: '#ffffff',
  textSecondary: '#c3c2b7',
  hoverWash: 'rgba(255, 255, 255, 0.08)',
}

export function useChartTheme(): ChartTheme {
  return usePrefersDark() ? DARK : LIGHT
}
