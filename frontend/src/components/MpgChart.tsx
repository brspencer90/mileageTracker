import { useEffect, useState } from 'react'
import {
  CartesianGrid,
  Line,
  LineChart,
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

/** MpgPoint plus a numeric timestamp so the x-axis is true time, not index. */
type TimedPoint = MpgPoint & { ts: number }

/**
 * One tooltip carries the value the reader is hunting for: MPG leads,
 * the date is secondary, keyed by a short stroke of the series color.
 */
function MpgTip({ active, payload }: TooltipContentProps) {
  if (active !== true || payload === undefined || payload.length === 0) {
    return null
  }
  const point = payload[0]?.payload as MpgPoint | undefined
  if (point === undefined) return null
  return (
    <div className="chart-tip">
      <div className="tip-value-row">
        <span className="tip-key" aria-hidden="true" />
        <span className="tip-value">
          {point.mpg !== null ? `${point.mpg.toFixed(1)} MPG` : 'No MPG'}
        </span>
      </div>
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
        if (!cancelled) {
          setData(points.map((p) => ({ ...p, ts: dateToTs(p.date) })))
        }
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

  return (
    <section className="chart-card" aria-label="MPG over time">
      <h2 className="section-title">MPG per fill-up</h2>
      {error !== null ? (
        <p className="status-msg error-msg">{error}</p>
      ) : data === null ? (
        <div className="chart-placeholder">Loading…</div>
      ) : data.length === 0 ? (
        <div className="chart-placeholder">No fill-ups yet</div>
      ) : (
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
              domain={['auto', 'auto']}
              tick={{ fill: t.axisText, fontSize: 12 }}
              tickLine={false}
              axisLine={false}
            />
            <Tooltip
              content={MpgTip}
              cursor={{ stroke: t.baseline, strokeWidth: 1 }}
              isAnimationActive={false}
            />
            <Line
              type="monotone"
              dataKey="mpg"
              connectNulls={false}
              stroke={t.series}
              strokeWidth={2}
              strokeLinecap="round"
              strokeLinejoin="round"
              // >=8px marker with a 2px surface ring so isolated points
              // (either side of a missed-fill gap) stay visible and legible.
              dot={{ r: 4, fill: t.series, stroke: t.surface, strokeWidth: 2 }}
              activeDot={{ r: 5, fill: t.series, stroke: t.surface, strokeWidth: 2 }}
              isAnimationActive={false}
            />
          </LineChart>
        </ResponsiveContainer>
      )}
    </section>
  )
}

export default MpgChart
