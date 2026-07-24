import { useEffect, useMemo, useState } from 'react'
import {
  CartesianGrid,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import type { TooltipContentProps } from 'recharts'
import { getMpgStats } from '../api/client'
import type { MpgPoint } from '../api/types'
import { dateToTs, formatDate, formatTsTick } from '../lib/format'
import { useChartTheme } from '../lib/theme'

interface Props {
  vehicleId: number
  version: number
}

/** MpgPoint plus a numeric timestamp and the derived 5-fill rolling average. */
type TimedPoint = MpgPoint & { ts: number; rolling: number | null }

// Y-domain clamp: partial-fill outliers (45–57 MPG) are clipped at the top
// edge so they can't flatten the real 24–30 band. Averaging also clamps to 40.
const Y_MIN = 18
const Y_MAX = 40
const CLEAN_MIN = 15
const ROLL_WINDOW = 5

/**
 * Trailing 5-fill average over MPG clamped to ≤40, so one partial-fill spike
 * can't drag the line. Computed only where a real MPG exists; null elsewhere
 * (connectNulls bridges the occasional gap so the accent line stays smooth).
 */
function withRolling(points: MpgPoint[]): TimedPoint[] {
  const seen: number[] = []
  return points.map((p) => {
    let rolling: number | null = null
    if (p.mpg !== null) {
      seen.push(Math.min(p.mpg, Y_MAX))
      const seg = seen.slice(-ROLL_WINDOW)
      rolling = seg.reduce((a, b) => a + b, 0) / seg.length
    }
    return { ...p, ts: dateToTs(p.date), rolling }
  })
}

function MpgTip({ active, payload }: TooltipContentProps) {
  if (active !== true || payload === undefined || payload.length === 0) {
    return null
  }
  const point = payload[0]?.payload as TimedPoint | undefined
  if (point === undefined) return null
  return (
    <div className="chart-tip">
      <div className="tip-value-row">
        <span className="tip-key" aria-hidden="true" />
        <span className="tip-value">
          {point.mpg !== null ? `${point.mpg.toFixed(1)} MPG` : 'No MPG'}
        </span>
      </div>
      {point.rolling !== null && (
        <div className="tip-sub">5-fill avg {point.rolling.toFixed(1)}</div>
      )}
      <div className="tip-sub">{formatDate(point.date)}</div>
      <div className="tip-sub">{point.mileage.toLocaleString()} mi</div>
    </div>
  )
}

function MpgChart({ vehicleId, version }: Props) {
  const [data, setData] = useState<TimedPoint[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const t = useChartTheme()

  useEffect(() => {
    let cancelled = false
    getMpgStats(vehicleId)
      .then((points) => {
        if (!cancelled) setData(withRolling(points))
      })
      .catch((e: unknown) => {
        if (!cancelled) {
          setError(e instanceof Error ? e.message : 'Failed to load MPG data')
        }
      })
    return () => {
      cancelled = true
    }
  }, [vehicleId, version])

  // Lifetime average over the real driving band (excludes partial-fill
  // outliers), matching the dashed reference line.
  const lifetime = useMemo(() => {
    if (data === null) return null
    const clean = data
      .map((p) => p.mpg)
      .filter((m): m is number => m !== null && m >= CLEAN_MIN && m <= Y_MAX)
    if (clean.length === 0) return null
    return clean.reduce((a, b) => a + b, 0) / clean.length
  }, [data])

  return (
    <section className="chart-card" aria-label="Fuel economy over time">
      <div className="chart-head">
        <h2 className="section-title">Fuel economy</h2>
      </div>
      {error !== null ? (
        <p className="status-msg error-msg">{error}</p>
      ) : data === null ? (
        <div className="chart-placeholder">Loading…</div>
      ) : data.length === 0 ? (
        <div className="chart-placeholder">No fill-ups yet</div>
      ) : (
        <>
          <ResponsiveContainer width="100%" height={220}>
            <LineChart data={data} margin={{ top: 8, right: 12, bottom: 0, left: 0 }}>
              <CartesianGrid stroke={t.grid} strokeWidth={1} vertical={false} />
              <XAxis
                dataKey="ts"
                type="number"
                scale="time"
                domain={['dataMin', 'dataMax']}
                tickFormatter={formatTsTick}
                tick={{ fill: t.axisText, fontSize: 12 }}
                tickLine={false}
                axisLine={{ stroke: t.baseline, strokeWidth: 1 }}
                minTickGap={32}
              />
              <YAxis
                width={34}
                domain={[Y_MIN, Y_MAX]}
                allowDataOverflow
                ticks={[20, 25, 30, 35, 40]}
                tick={{ fill: t.axisText, fontSize: 12 }}
                tickLine={false}
                axisLine={false}
              />
              {lifetime !== null && (
                <ReferenceLine
                  y={lifetime}
                  stroke={t.muted}
                  strokeWidth={1.5}
                  strokeDasharray="4 4"
                  label={{
                    value: lifetime.toFixed(1),
                    position: 'insideTopRight',
                    fill: t.muted,
                    fontSize: 11,
                    fontWeight: 600,
                  }}
                />
              )}
              <Tooltip
                content={MpgTip}
                cursor={{ stroke: t.baseline, strokeWidth: 1 }}
                isAnimationActive={false}
              />
              {/* Per-fill points: demoted to a faint muted dot cloud, no line. */}
              <Line
                dataKey="mpg"
                connectNulls={false}
                stroke="none"
                dot={{ r: 2, fill: t.dot, stroke: 'none' }}
                activeDot={{ r: 3.5, fill: t.series, stroke: t.surface, strokeWidth: 2 }}
                isAnimationActive={false}
              />
              {/* 5-fill rolling average: the prominent accent line. */}
              <Line
                type="monotone"
                dataKey="rolling"
                connectNulls
                stroke={t.series}
                strokeWidth={2}
                strokeLinecap="round"
                strokeLinejoin="round"
                dot={false}
                activeDot={{ r: 4, fill: t.series, stroke: t.surface, strokeWidth: 2 }}
                isAnimationActive={false}
              />
            </LineChart>
          </ResponsiveContainer>
          <div className="chart-legend" aria-hidden="true">
            <span>
              <span className="lg-dot" />
              per fill
            </span>
            <span>
              <span className="lg-line" />
              5-fill average
            </span>
            <span>
              <span className="lg-ref" />
              lifetime avg
            </span>
          </div>
        </>
      )}
    </section>
  )
}

export default MpgChart
