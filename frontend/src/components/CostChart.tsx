import { useEffect, useState } from 'react'
import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import type { TooltipContentProps } from 'recharts'
import { getCostByMonth } from '../api/client'
import type { MonthCost } from '../api/types'
import { formatMoney, formatMonth } from '../lib/format'
import { useChartTheme } from '../lib/theme'

interface Props {
  vehicleId: number
  version: number
}

function CostTip({ active, payload }: TooltipContentProps) {
  if (active !== true || payload === undefined || payload.length === 0) {
    return null
  }
  const m = payload[0]?.payload as MonthCost | undefined
  if (m === undefined) return null
  return (
    <div className="chart-tip">
      <div className="tip-value-row">
        <span className="tip-key" aria-hidden="true" />
        <span className="tip-value">{formatMoney(m.cost)}</span>
      </div>
      <div className="tip-sub">{formatMonth(m.month)}</div>
      <div className="tip-sub">
        {m.gallons.toFixed(1)} gal · {m.fillups}{' '}
        {m.fillups === 1 ? 'fill-up' : 'fill-ups'}
      </div>
    </div>
  )
}

/**
 * Insert $0 rows for months with no fill-ups so the category axis is
 * uniform in time — otherwise a 6-month gap collapses to nothing and
 * the chart lies about spacing.
 */
function fillMonthGaps(months: MonthCost[]): MonthCost[] {
  const sorted = [...months].sort((a, b) => a.month.localeCompare(b.month))
  const first = sorted[0]
  const last = sorted[sorted.length - 1]
  if (first === undefined || last === undefined) return sorted
  const [firstY, firstM] = first.month.split('-').map(Number)
  const [lastY, lastM] = last.month.split('-').map(Number)
  if (!firstY || !firstM || !lastY || !lastM) return sorted
  const byMonth = new Map(sorted.map((m) => [m.month, m]))
  const out: MonthCost[] = []
  for (let y = firstY, m = firstM; y < lastY || (y === lastY && m <= lastM); ) {
    const key = `${y}-${String(m).padStart(2, '0')}`
    out.push(byMonth.get(key) ?? { month: key, cost: 0, gallons: 0, fillups: 0 })
    m += 1
    if (m > 12) {
      m = 1
      y += 1
    }
  }
  return out
}

function CostChart({ vehicleId, version }: Props) {
  const [data, setData] = useState<MonthCost[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const t = useChartTheme()

  useEffect(() => {
    let cancelled = false
    getCostByMonth(vehicleId)
      .then((months) => {
        if (!cancelled) setData(fillMonthGaps(months))
      })
      .catch((e: unknown) => {
        if (!cancelled) {
          setError(e instanceof Error ? e.message : 'Failed to load cost data')
        }
      })
    return () => {
      cancelled = true
    }
  }, [vehicleId, version])

  return (
    <section className="chart-card" aria-label="Fuel cost by month">
      <h2 className="section-title">Fuel cost by month</h2>
      {error !== null ? (
        <p className="status-msg error-msg">{error}</p>
      ) : data === null ? (
        <div className="chart-placeholder">Loading…</div>
      ) : data.length === 0 ? (
        <div className="chart-placeholder">No fill-ups yet</div>
      ) : (
        <ResponsiveContainer width="100%" height={220}>
          <BarChart data={data} margin={{ top: 8, right: 12, bottom: 0, left: 0 }}>
            <CartesianGrid stroke={t.grid} strokeWidth={1} vertical={false} />
            <XAxis
              dataKey="month"
              tickFormatter={formatMonth}
              tick={{ fill: t.axisText, fontSize: 12 }}
              tickLine={false}
              axisLine={{ stroke: t.baseline, strokeWidth: 1 }}
              minTickGap={32}
            />
            <YAxis
              width={40}
              tickFormatter={(v: number) => `$${v}`}
              tick={{ fill: t.axisText, fontSize: 12 }}
              tickLine={false}
              axisLine={false}
            />
            <Tooltip
              content={CostTip}
              cursor={{ fill: t.hoverWash }}
              isAnimationActive={false}
            />
            {/* Thin bars: capped width, 4px rounded data-end, square baseline. */}
            <Bar
              dataKey="cost"
              fill={t.series}
              maxBarSize={24}
              radius={[4, 4, 0, 0]}
              isAnimationActive={false}
            />
          </BarChart>
        </ResponsiveContainer>
      )}
    </section>
  )
}

export default CostChart
