import { useEffect, useState } from 'react'
import { getMpgStats } from '../api/client'
import type { MpgPoint, SummaryStats } from '../api/types'

interface Props {
  vehicleId: number
  summary: SummaryStats | null
  /** bumped on any create/edit/delete so the sparkline refetches */
  version: number
}

/** "—" for null, else the formatted value. */
function num(n: number | null | undefined, digits = 1): string {
  return n === null || n === undefined ? '—' : n.toFixed(digits)
}

/** Split "$153.32" into a big-dollars / small-cents pair like the mockup. */
function money(n: number | null): { main: string; cents: string | null } {
  if (n === null) return { main: '—', cents: null }
  const dollars = Math.floor(n)
  const cents = Math.round((n - dollars) * 100)
  return { main: `$${dollars.toLocaleString()}`, cents: `.${String(cents).padStart(2, '0')}` }
}

/**
 * A small SVG sparkline (area + line + end dot) over the last ~14 real MPG
 * points. Plain DOM SVG — CSS var() resolves here, unlike Recharts attrs.
 */
function Sparkline({ points }: { points: number[] }) {
  if (points.length < 2) return <svg className="spark" viewBox="0 0 300 34" aria-hidden="true" />
  const min = Math.min(...points) - 0.5
  const max = Math.max(...points) + 0.5
  const span = max - min || 1
  const sx = (i: number) => 2 + (i / (points.length - 1)) * 296
  const sy = (v: number) => 32 - ((v - min) / span) * 30
  const line = points.map((v, i) => `${i ? 'L' : 'M'}${sx(i).toFixed(1)} ${sy(v).toFixed(1)}`).join(' ')
  const last = points.length - 1
  return (
    <svg className="spark" viewBox="0 0 300 34" preserveAspectRatio="none" aria-hidden="true">
      <path d={`${line} L ${sx(last).toFixed(1)} 34 L 2 34 Z`} fill="var(--accent-soft)" stroke="none" />
      <path d={line} fill="none" stroke="var(--accent)" strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" />
      <circle cx={sx(last)} cy={sy(points[last])} r={3} fill="var(--accent)" />
    </svg>
  )
}

const DownArrow = () => (
  <svg viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="M6 2v8" />
    <path d="M2.5 6.5 6 10l3.5-3.5" />
  </svg>
)
const UpArrow = () => (
  <svg viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="M6 10V2" />
    <path d="M2.5 5.5 6 2l3.5 3.5" />
  </svg>
)

function SummaryTiles({ vehicleId, summary, version }: Props) {
  const [spark, setSpark] = useState<number[]>([])

  useEffect(() => {
    let cancelled = false
    getMpgStats(vehicleId)
      .then((pts: MpgPoint[]) => {
        if (cancelled) return
        const vals = pts
          .map((p) => p.mpg)
          .filter((m): m is number => m !== null)
          .slice(-14)
        setSpark(vals)
      })
      .catch(() => {
        if (!cancelled) setSpark([])
      })
    return () => {
      cancelled = true
    }
  }, [vehicleId, version])

  const delta = summary?.mpg_delta ?? null
  const deltaDown = delta !== null && delta < 0
  const showDelta = delta !== null && Math.abs(delta) >= 0.05
  const spend = money(summary?.spend_30d ?? null)
  const showHealth = delta !== null && delta <= -1.0

  return (
    <>
      <section className="kpis" aria-label="Summary">
        <div className="card tile hero">
          <div className="tile-top">
            <span className="tile-label">Recent fuel economy</span>
            {showDelta && (
              <span className={deltaDown ? 'delta down' : 'delta up'}>
                {deltaDown ? <DownArrow /> : <UpArrow />}
                {Math.abs(delta as number).toFixed(1)} vs lifetime
              </span>
            )}
          </div>
          <div className="tile-val tnum">
            {num(summary?.recent_mpg)}
            <span className="unit">MPG</span>
          </div>
          <Sparkline points={spark} />
          <div className="tile-note">
            trailing average
            {summary?.lifetime_mpg != null && ` · lifetime ${summary.lifetime_mpg.toFixed(1)} MPG`}
          </div>
        </div>

        <div className="card tile">
          <span className="tile-label">Cost per mile</span>
          <div className="tile-val tnum">
            {summary?.cost_per_mile != null ? `$${summary.cost_per_mile.toFixed(2)}` : '—'}
          </div>
          <div className="tile-note">recent fills</div>
        </div>

        <div className="card tile">
          <span className="tile-label">Fuel, 30 days</span>
          <div className="tile-val tnum">
            {spend.main}
            {spend.cents !== null && <span className="unit">{spend.cents}</span>}
          </div>
          <div className="tile-note">
            {summary != null
              ? `across ${summary.spend_30d_fills} ${summary.spend_30d_fills === 1 ? 'fill-up' : 'fill-ups'}`
              : '—'}
          </div>
        </div>

        <div className="card tile">
          <span className="tile-label">Between fills</span>
          <div className="tile-val tnum">
            {num(summary?.avg_days_between)}
            <span className="unit">days</span>
          </div>
          <div className="tile-note">average gap</div>
        </div>

        <div className="card tile">
          <span className="tile-label">Logged</span>
          <div className="tile-val tnum">{summary?.total_fills ?? '—'}</div>
          <div className="tile-note">fill-ups on record</div>
        </div>
      </section>

      {showHealth && (
        <div className="health" role="status">
          <span className="health-ic" aria-hidden="true">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round">
              <path d="M12 9v4" />
              <path d="M12 17h.01" />
              <path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0Z" />
            </svg>
          </span>
          <span>
            Running <b>{Math.abs(delta as number).toFixed(1)} MPG below</b> your lifetime average over
            the last several fills — worth a tire-pressure check.
          </span>
        </div>
      )}
    </>
  )
}

export default SummaryTiles
