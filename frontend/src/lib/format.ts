const MONTHS = [
  'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
  'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec',
]

/** Today's date in local time as YYYY-MM-DD. */
export function todayISO(): string {
  const d = new Date()
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${d.getFullYear()}-${m}-${day}`
}

/** "2024-03-08" -> "Mar 8, 2024" (parsed manually — no UTC off-by-one). */
export function formatDate(iso: string): string {
  const [y, m, d] = iso.split('-').map(Number)
  if (!y || !m || !d) return iso
  return `${MONTHS[m - 1]} ${d}, ${y}`
}

/** "2024-03-08" -> "Mar '24" for compact axis ticks. */
export function formatDateTick(iso: string): string {
  const [y, m] = iso.split('-').map(Number)
  if (!y || !m) return iso
  return `${MONTHS[m - 1]} '${String(y).slice(2)}`
}

/** "2024-03-08" -> local-midnight timestamp in ms (no UTC off-by-one). */
export function dateToTs(iso: string): number {
  const [y, m, d] = iso.split('-').map(Number)
  if (!y || !m || !d) return NaN
  return new Date(y, m - 1, d).getTime()
}

/** Timestamp in ms -> "Mar '24" for compact time-axis ticks. */
export function formatTsTick(ms: number): string {
  const d = new Date(ms)
  return `${MONTHS[d.getMonth()]} '${String(d.getFullYear()).slice(2)}`
}

/** "2024-03" -> "Mar '24". */
export function formatMonth(month: string): string {
  const [y, m] = month.split('-').map(Number)
  if (!y || !m) return month
  return `${MONTHS[m - 1]} '${String(y).slice(2)}`
}

export function formatMoney(n: number | null): string {
  return n !== null ? `$${n.toFixed(2)}` : '$—'
}
