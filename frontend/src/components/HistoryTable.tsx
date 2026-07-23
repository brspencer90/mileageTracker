import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import {
  ApiError,
  deleteFillup,
  getFillups,
  resolveMileage,
  updateFillup,
} from '../api/client'
import type { FillupOut, FillupUpdate } from '../api/types'
import { formatDate, formatMoney, todayISO } from '../lib/format'

const PAGE_SIZE = 50
const ZIP_RE = /^\d{5}$/

interface Props {
  vehicleId: number
  onChanged: () => void
}

/** "a" · "a & b" · "a, b & c" */
function joinLabels(labels: string[]): string {
  if (labels.length <= 1) return labels[0] ?? ''
  if (labels.length === 2) return `${labels[0]} & ${labels[1]}`
  return `${labels.slice(0, -1).join(', ')} & ${labels[labels.length - 1]}`
}

/** Which submitted fields differ from the row's previous values (MT-23). */
function changedFields(prev: FillupOut, body: FillupUpdate): string[] {
  const out: string[] = []
  if (body.date !== undefined && body.date !== prev.date) out.push('date')
  if (body.mileage !== undefined && body.mileage !== prev.mileage) {
    out.push('mileage')
  }
  if (body.gallons !== undefined && body.gallons !== prev.gallons) {
    out.push('gallons')
  }
  if (body.cost !== undefined && body.cost !== prev.cost) out.push('cost')
  if (body.station !== undefined && body.station !== prev.station) {
    out.push('station')
  }
  if (body.zip !== undefined && body.zip !== prev.zip) out.push('ZIP')
  if (
    body.missed_last_fill !== undefined &&
    body.missed_last_fill !== prev.missed_last_fill
  ) {
    out.push('missed-fill flag')
  }
  return out
}

function mpgText(f: FillupOut | undefined | null): string {
  return f != null && f.mpg !== null ? f.mpg.toFixed(1) : '—'
}

function HistoryTable({ vehicleId, onChanged }: Props) {
  const [items, setItems] = useState<FillupOut[] | null>(null)
  const [total, setTotal] = useState(0)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [loadingMore, setLoadingMore] = useState(false)
  const [editing, setEditing] = useState<FillupOut | null>(null)
  const [actionError, setActionError] = useState<string | null>(null)
  const [toast, setToast] = useState<string | null>(null)
  const toastTimer = useRef<number | undefined>(undefined)

  // MT-23: scroll position to restore after an in-place refresh.
  const pendingScroll = useRef<number | null>(null)

  // Load page 0 on mount and whenever the vehicle changes — NOT on data
  // mutations (edit/delete/accept refresh in place, preserving scroll + pages).
  useEffect(() => {
    let cancelled = false
    setItems(null)
    getFillups(vehicleId, PAGE_SIZE, 0)
      .then((res) => {
        if (cancelled) return
        setItems(res.items)
        setTotal(res.total)
        setLoadError(null)
      })
      .catch((e: unknown) => {
        if (!cancelled) {
          setLoadError(e instanceof Error ? e.message : 'Failed to load history')
        }
      })
    return () => {
      cancelled = true
    }
  }, [vehicleId])

  useEffect(() => {
    return () => window.clearTimeout(toastTimer.current)
  }, [])

  // Restore scroll after the list re-renders from an in-place refresh (MT-23).
  useLayoutEffect(() => {
    if (pendingScroll.current !== null) {
      window.scrollTo(0, pendingScroll.current)
      pendingScroll.current = null
    }
  }, [items])

  const showToast = (msg: string) => {
    window.clearTimeout(toastTimer.current)
    setToast(msg)
    toastTimer.current = window.setTimeout(() => setToast(null), 5000)
  }

  /**
   * Refetch exactly the window currently loaded (all pages), at offset 0, and
   * keep the scroll position. Returns the fresh rows for derived-value lookups.
   */
  const refreshInPlace = async (): Promise<FillupOut[]> => {
    const count = Math.max(items?.length ?? PAGE_SIZE, PAGE_SIZE)
    pendingScroll.current = window.scrollY
    const res = await getFillups(vehicleId, count, 0)
    setItems(res.items)
    setTotal(res.total)
    return res.items
  }

  const loadMore = () => {
    if (items === null) return
    setLoadingMore(true)
    getFillups(vehicleId, PAGE_SIZE, items.length)
      .then((res) => {
        setItems([...items, ...res.items])
        setTotal(res.total)
      })
      .catch((e: unknown) => {
        setActionError(e instanceof Error ? e.message : 'Failed to load more')
      })
      .finally(() => setLoadingMore(false))
  }

  const handleEditSaved = async (prev: FillupOut, body: FillupUpdate) => {
    setEditing(null)
    setActionError(null)
    const changed = changedFields(prev, body)
    const mpgAffected =
      changed.includes('mileage') ||
      changed.includes('gallons') ||
      changed.includes('missed-fill flag')
    try {
      const fresh = await refreshInPlace()
      let msg =
        changed.length === 0 ? 'Saved — no changes.' : `Updated ${joinLabels(changed)}.`
      if (mpgAffected) {
        const idx = fresh.findIndex((i) => i.id === prev.id)
        const edited = idx >= 0 ? fresh[idx] : null
        // Higher-mileage neighbor derives its MPG from this row, so it shifts too.
        const neighbor = idx > 0 ? fresh[idx - 1] : null
        const neighborClause =
          neighbor != null && neighbor.mpg !== null
            ? `, next ${mpgText(neighbor)}`
            : ''
        msg += ` MPG recalculated: this fill ${mpgText(edited)}${neighborClause}.`
      }
      showToast(msg)
      onChanged()
    } catch (e: unknown) {
      setActionError(e instanceof Error ? e.message : 'Saved, but refresh failed')
    }
  }

  const handleDelete = async (f: FillupOut) => {
    const label =
      f.mileage !== null
        ? `${formatDate(f.date)} fill-up at ${f.mileage.toLocaleString()} mi`
        : `${formatDate(f.date)} pending fill-up`
    const ok = window.confirm(`Delete the ${label}?`)
    if (!ok) return
    setActionError(null)
    // The higher-mileage neighbor derives its MPG from this row.
    const idx = items?.findIndex((i) => i.id === f.id) ?? -1
    const neighborId = idx > 0 ? (items as FillupOut[])[idx - 1].id : null
    try {
      await deleteFillup(f.id)
      const fresh = await refreshInPlace()
      let msg = `Deleted the ${formatDate(f.date)} fill-up.`
      if (neighborId !== null) {
        const neighbor = fresh.find((i) => i.id === neighborId)
        if (neighbor != null && neighbor.mpg !== null) {
          msg += ` Next fill's MPG recalculated: ${mpgText(neighbor)}.`
        }
      }
      showToast(msg)
      onChanged()
    } catch (e: unknown) {
      setActionError(e instanceof ApiError ? e.message : 'Delete failed')
    }
  }

  // MT-24: accept the server's interpolated odometer for a pending fill.
  const handleAccept = async (f: FillupOut) => {
    if (f.suggested_mileage === null) return
    setActionError(null)
    const suggested = f.suggested_mileage
    try {
      await resolveMileage(f.id, suggested)
      await refreshInPlace()
      showToast(`Mileage set to ~${suggested.toLocaleString()} (estimated).`)
      onChanged()
    } catch (e: unknown) {
      setActionError(e instanceof ApiError ? e.message : 'Could not set mileage')
    }
  }

  if (loadError !== null) {
    return <p className="status-msg error-msg">{loadError}</p>
  }
  if (items === null) {
    return <p className="status-msg">Loading history…</p>
  }
  if (items.length === 0) {
    return <p className="status-msg">No fill-ups yet — log your first one.</p>
  }

  return (
    <section className="history" aria-label="Fill-up history">
      <h2 className="section-title">Fill-ups</h2>
      {actionError !== null && (
        <p className="inline-error" role="alert">
          {actionError}
        </p>
      )}
      <ul className="fillup-list">
        {items.map((f) => {
          const pending = f.mileage === null
          return (
            <li
              key={f.id}
              className={pending ? 'fillup-card pending' : 'fillup-card'}
            >
              <div className="fillup-top">
                <span className="fillup-date">{formatDate(f.date)}</span>
                <span className="fillup-mpg">
                  {f.mpg !== null
                    ? `${f.mpg_estimated ? '~' : ''}${f.mpg.toFixed(1)} MPG`
                    : '— MPG'}
                </span>
              </div>
              <div className="fillup-stats">
                {pending ? (
                  <span className="pending-badge">Mileage pending</span>
                ) : (
                  <span>
                    {f.mileage_estimated ? '≈' : ''}
                    {(f.mileage as number).toLocaleString()} mi
                  </span>
                )}
                <span>{f.gallons.toFixed(3)} gal</span>
                <span>{formatMoney(f.cost)}</span>
              </div>
              {(f.station !== null ||
                f.missed_last_fill ||
                f.mileage_estimated) && (
                <div className="fillup-meta">
                  {f.station !== null && (
                    <span>
                      {f.station}
                      {f.zip !== null ? ` · ${f.zip}` : ''}
                    </span>
                  )}
                  {f.missed_last_fill && (
                    <span className="missed-badge">missed previous fill</span>
                  )}
                  {f.mileage_estimated && (
                    <span className="estimated-badge">estimated odometer</span>
                  )}
                </div>
              )}
              {pending && (
                <div className="pending-estimate">
                  {f.suggested_mileage !== null ? (
                    <>
                      <span className="pending-suggest">
                        Estimate mileage: ~{f.suggested_mileage.toLocaleString()} mi
                      </span>
                      <button
                        type="button"
                        className="accept-btn"
                        onClick={() => void handleAccept(f)}
                      >
                        Accept
                      </button>
                    </>
                  ) : (
                    <span className="pending-note">
                      Mileage pending — will be estimable after your next fill
                    </span>
                  )}
                </div>
              )}
              <div className="fillup-actions">
                <button type="button" onClick={() => setEditing(f)}>
                  Edit
                </button>
                <button
                  type="button"
                  className="danger"
                  onClick={() => void handleDelete(f)}
                >
                  Delete
                </button>
              </div>
            </li>
          )
        })}
      </ul>
      {items.length < total && (
        <button
          type="button"
          className="load-more"
          disabled={loadingMore}
          onClick={loadMore}
        >
          {loadingMore ? 'Loading…' : `Load more (${total - items.length} older)`}
        </button>
      )}
      {editing !== null && (
        <EditDialog
          fillup={editing}
          onClose={() => setEditing(null)}
          onSaved={(body) => void handleEditSaved(editing, body)}
        />
      )}
      {toast !== null && (
        <div className="toast toast-multiline" role="status">
          {toast}
        </div>
      )}
    </section>
  )
}

interface EditProps {
  fillup: FillupOut
  onClose: () => void
  /** MT-23: hands the submitted values back so the parent can diff + confirm. */
  onSaved: (body: FillupUpdate) => void
}

function EditDialog({ fillup, onClose, onSaved }: EditProps) {
  const [date, setDate] = useState(fillup.date)
  const [mileage, setMileage] = useState(
    fillup.mileage !== null ? String(fillup.mileage) : '',
  )
  const [gallons, setGallons] = useState(String(fillup.gallons))
  const [cost, setCost] = useState(fillup.cost !== null ? fillup.cost.toFixed(2) : '')
  const [station, setStation] = useState(fillup.station ?? '')
  const [zip, setZip] = useState(fillup.zip ?? '')
  const [missed, setMissed] = useState(fillup.missed_last_fill)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const mileageNum = /^\d+$/.test(mileage.trim())
    ? parseInt(mileage.trim(), 10)
    : NaN
  const gallonsNum = parseFloat(gallons)
  const costNum = parseFloat(cost)
  const valid =
    Number.isFinite(mileageNum) &&
    mileageNum > 0 &&
    Number.isFinite(gallonsNum) &&
    gallonsNum > 0 &&
    Number.isFinite(costNum) &&
    costNum > 0 &&
    (zip === '' || ZIP_RE.test(zip)) &&
    date !== '' &&
    date <= todayISO()

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    if (!valid || saving) return
    setSaving(true)
    setError(null)
    const body: FillupUpdate = {
      date,
      mileage: mileageNum,
      gallons: gallonsNum,
      cost: Math.round(costNum * 100) / 100,
      station: station.trim() === '' ? null : station.trim(),
      zip: zip === '' ? null : zip,
      missed_last_fill: missed,
    }
    try {
      await updateFillup(fillup.id, body)
      onSaved(body)
    } catch (err: unknown) {
      setError(err instanceof ApiError ? err.message : 'Save failed')
      setSaving(false)
    }
  }

  return (
    <div className="dialog-backdrop" onClick={onClose}>
      <div
        className="dialog"
        role="dialog"
        aria-modal="true"
        aria-label="Edit fill-up"
        onClick={(e) => e.stopPropagation()}
      >
        <h3 className="dialog-title">Edit fill-up</h3>
        <form onSubmit={handleSubmit} noValidate>
          <label className="field">
            <span className="field-label">Date</span>
            <input
              type="date"
              value={date}
              max={todayISO()}
              onChange={(e) => setDate(e.target.value)}
            />
          </label>
          <label className="field">
            <span className="field-label">Mileage</span>
            <input
              type="text"
              inputMode="numeric"
              pattern="[0-9]*"
              value={mileage}
              onChange={(e) => setMileage(e.target.value)}
            />
          </label>
          <label className="field">
            <span className="field-label">Gallons</span>
            <input
              type="text"
              inputMode="decimal"
              value={gallons}
              onChange={(e) => setGallons(e.target.value)}
            />
          </label>
          <label className="field">
            <span className="field-label">Total cost</span>
            <input
              type="text"
              inputMode="decimal"
              value={cost}
              onChange={(e) => setCost(e.target.value)}
            />
          </label>
          <label className="field">
            <span className="field-label">Station</span>
            <input
              type="text"
              value={station}
              onChange={(e) => setStation(e.target.value)}
            />
          </label>
          <label className="field">
            <span className="field-label">ZIP</span>
            <input
              type="text"
              inputMode="numeric"
              pattern="[0-9]*"
              maxLength={5}
              value={zip}
              onChange={(e) => setZip(e.target.value)}
            />
          </label>
          <label className="check-field">
            <input
              type="checkbox"
              checked={missed}
              onChange={(e) => setMissed(e.target.checked)}
            />
            <span>Missed the previous fill-up</span>
          </label>
          {error !== null && (
            <p className="inline-error" role="alert">
              {error}
            </p>
          )}
          <div className="dialog-actions">
            <button type="button" onClick={onClose}>
              Cancel
            </button>
            <button type="submit" className="submit-btn" disabled={!valid || saving}>
              {saving ? 'Saving…' : 'Save'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

export default HistoryTable
