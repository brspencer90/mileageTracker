import { useCallback, useEffect, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import { ApiError, createFillup, getFillupContext } from '../api/client'
import type { FillupContext, FillupCreate } from '../api/types'
import { todayISO } from '../lib/format'
import FuelGauge from './FuelGauge'

interface Props {
  vehicleId: number
  onLogged: () => void
}

const ZIP_RE = /^\d{5}$/

function QuickLogForm({ vehicleId, onLogged }: Props) {
  const [context, setContext] = useState<FillupContext | null>(null)
  const [contextError, setContextError] = useState<string | null>(null)

  const [mileage, setMileage] = useState('')
  const [noOdometer, setNoOdometer] = useState(false)
  const [gallons, setGallons] = useState('')
  const [cost, setCost] = useState('')
  const [station, setStation] = useState('')
  const [zip, setZip] = useState('')
  const [date, setDate] = useState(todayISO())
  const [missedLastFill, setMissedLastFill] = useState(false)
  const [partialFill, setPartialFill] = useState(false)
  const [gaugeNotches, setGaugeNotches] = useState<number | null>(null)

  const [submitting, setSubmitting] = useState(false)
  const [serverError, setServerError] = useState<string | null>(null)
  const [toast, setToast] = useState<string | null>(null)
  const toastTimer = useRef<number | undefined>(undefined)

  const loadContext = useCallback(() => {
    setContextError(null)
    getFillupContext(vehicleId)
      .then((ctx) => {
        setContext(ctx)
        // Prefill station/zip from last-used, but never clobber typed input.
        setStation((s) => (s === '' ? (ctx.last_station ?? '') : s))
        setZip((z) => (z === '' ? (ctx.last_zip ?? '') : z))
      })
      .catch((e: unknown) => {
        setContextError(
          e instanceof Error ? e.message : 'Failed to load fill-up context',
        )
      })
  }, [vehicleId])

  useEffect(() => {
    loadContext()
  }, [loadContext])

  useEffect(() => {
    return () => window.clearTimeout(toastTimer.current)
  }, [])

  const showToast = (msg: string) => {
    window.clearTimeout(toastTimer.current)
    setToast(msg)
    toastTimer.current = window.setTimeout(() => setToast(null), 4000)
  }

  const prevMileage = context?.prev_mileage ?? null
  const tankSize = context?.tank_size_gal ?? null

  const mileageNum = /^\d+$/.test(mileage.trim())
    ? parseInt(mileage.trim(), 10)
    : NaN
  const gallonsNum = parseFloat(gallons)
  const costNum = parseFloat(cost)

  const mileageValid =
    Number.isFinite(mileageNum) &&
    mileageNum > 0 &&
    (prevMileage === null || mileageNum > prevMileage)
  const gallonsValid =
    Number.isFinite(gallonsNum) &&
    gallonsNum > 0 &&
    (tankSize === null || gallonsNum <= tankSize * 1.1)
  const costValid = Number.isFinite(costNum) && costNum > 0
  const zipValid = zip === '' || ZIP_RE.test(zip)
  const dateValid = date !== '' && date <= todayISO()
  // MT-24: a pending fill has no odometer, so mileage is not required.
  const canSubmit =
    (noOdometer || mileageValid) &&
    gallonsValid &&
    costValid &&
    zipValid &&
    dateValid &&
    !submitting

  // Live preview (MT-7): computed client-side from prev_mileage as you type.
  // MT-24: when logging without an odometer, mileage/MPG are deferred instead.
  // MT-9: a partial fill has no MPG of its own; its fuel rolls into the next
  // full fill. Annotate the preview and suppress the computed MPG.
  let preview: string | null = null
  if (noOdometer) {
    preview = partialFill
      ? 'Partial fill — mileage estimated later; its fuel rolls into your next full fill.'
      : 'Mileage & MPG will be estimated once a later fill is logged.'
  } else if (partialFill) {
    if (prevMileage !== null && mileageValid) {
      const miles = mileageNum - prevMileage
      preview = `+${miles} mi — partial fill, its fuel rolls into your next full fill`
    } else {
      preview = 'Partial fill — its fuel rolls into your next full fill'
    }
  } else if (prevMileage !== null && mileageValid) {
    const miles = mileageNum - prevMileage
    if (missedLastFill) {
      preview = `+${miles} mi since last logged fill — MPG skipped`
    } else if (gallonsValid) {
      preview = `+${miles} mi — ${(miles / gallonsNum).toFixed(1)} MPG`
    } else {
      preview = `+${miles} mi`
    }
  }

  // Field-level hints, shown only once the field has content.
  const mileageHint =
    !noOdometer && mileage !== '' && !mileageValid
      ? prevMileage !== null
        ? `Must be more than the last fill-up (${prevMileage.toLocaleString()} mi)`
        : 'Enter a whole number of miles'
      : null
  const gallonsHint =
    gallons !== '' && !gallonsValid
      ? tankSize !== null && Number.isFinite(gallonsNum) && gallonsNum > 0
        ? `That's a lot for a ${tankSize} gal tank`
        : 'Enter gallons greater than 0'
      : null
  const costHint =
    cost !== '' && !costValid ? 'Enter a total cost greater than 0' : null
  const zipHint = !zipValid ? 'ZIP must be 5 digits' : null
  const dateHint = !dateValid && date !== '' ? 'Date can’t be in the future' : null

  const quickPicks = (context?.recent_stations ?? []).slice(0, 5)

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    if (!canSubmit) return
    setSubmitting(true)
    setServerError(null)
    const body: FillupCreate = {
      vehicle_id: vehicleId,
      date,
      mileage: noOdometer ? null : mileageNum,
      gallons: gallonsNum,
      cost: Math.round(costNum * 100) / 100,
      station: station.trim() === '' ? null : station.trim(),
      zip: zip === '' ? null : zip,
      missed_last_fill: missedLastFill,
      partial_fill: partialFill,
      gauge_notches: gaugeNotches,
    }
    try {
      const saved = await createFillup(body)
      showToast(
        partialFill
          ? 'Saved — partial fill, MPG rolls into your next full fill'
          : noOdometer
            ? 'Saved — mileage pending'
            : saved.mpg !== null
              ? `Saved — ${saved.mpg.toFixed(1)} MPG`
              : 'Saved',
      )
      // Reset for the next fill-up; context refetch re-prefills station/zip.
      setMileage('')
      setNoOdometer(false)
      setGallons('')
      setCost('')
      setDate(todayISO())
      setMissedLastFill(false)
      setPartialFill(false)
      setGaugeNotches(null)
      loadContext()
      onLogged()
    } catch (err: unknown) {
      setServerError(
        err instanceof ApiError ? err.message : 'Could not save — try again',
      )
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <form className="log-form" onSubmit={handleSubmit} noValidate>
      {contextError !== null && (
        <p className="inline-error" role="alert">
          {contextError}
        </p>
      )}

      <label className="field">
        <span className="field-label">Date</span>
        <input
          type="date"
          value={date}
          max={todayISO()}
          onChange={(e) => setDate(e.target.value)}
        />
        {dateHint !== null && <span className="field-hint">{dateHint}</span>}
      </label>

      {/* Primary group: the three numbers that define a fill-up plus the fuel
          gauge, grouped and prominent so the common case is a no-scroll entry. */}
      <div className="primary-group card">
        {!noOdometer && (
          <label className="field">
            <span className="field-label">Mileage</span>
            <input
              type="text"
              inputMode="numeric"
              pattern="[0-9]*"
              autoFocus
              enterKeyHint="next"
              placeholder={
                prevMileage !== null
                  ? `Last: ${prevMileage.toLocaleString()}`
                  : 'Odometer'
              }
              value={mileage}
              onChange={(e) => setMileage(e.target.value)}
            />
            {mileageHint !== null && (
              <span className="field-hint">{mileageHint}</span>
            )}
          </label>
        )}

        <label className="field">
          <span className="field-label">Gallons</span>
          <input
            type="text"
            inputMode="decimal"
            enterKeyHint="next"
            placeholder="0.000"
            value={gallons}
            onChange={(e) => setGallons(e.target.value)}
          />
          {gallonsHint !== null && (
            <span className="field-hint">{gallonsHint}</span>
          )}
        </label>

        <label className="field">
          <span className="field-label">Total cost</span>
          <input
            type="text"
            inputMode="decimal"
            enterKeyHint="done"
            placeholder="$0.00"
            value={cost}
            onChange={(e) => setCost(e.target.value)}
          />
          {costHint !== null && <span className="field-hint">{costHint}</span>}
        </label>

        <FuelGauge value={gaugeNotches} onChange={setGaugeNotches} />
      </div>

      <div className="preview-line" aria-live="polite">
        {preview ?? ' '}
      </div>

      {serverError !== null && (
        <p className="inline-error" role="alert">
          {serverError}
        </p>
      )}

      <button type="submit" className="submit-btn" disabled={!canSubmit}>
        {submitting ? 'Saving…' : 'Save fill-up'}
      </button>

      {/* Secondary "details" — visually demoted, but present without extra
          taps: the no-odometer flag, station + quick-picks, ZIP, date, and
          the missed-fill flag. */}
      <div className="details-group">
        <span className="details-label">Details</span>

        <label className="check-field">
          <input
            type="checkbox"
            checked={noOdometer}
            onChange={(e) => setNoOdometer(e.target.checked)}
          />
          <span>I don&apos;t have an odometer reading</span>
        </label>

        <label className="field">
          <span className="field-label">Station</span>
          <input
            type="text"
            value={station}
            placeholder="Station name"
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
            placeholder="ZIP code"
            value={zip}
            onChange={(e) => setZip(e.target.value)}
          />
          {zipHint !== null && <span className="field-hint">{zipHint}</span>}
        </label>

        {quickPicks.length > 0 && (
          <div className="chip-row" role="group" aria-label="Recent stations">
            {quickPicks.map((p) => (
              <button
                key={`${p.station}|${p.zip ?? ''}`}
                type="button"
                className="chip"
                onClick={() => {
                  setStation(p.station)
                  setZip(p.zip ?? '')
                }}
              >
                {p.station}
                {p.zip !== null && <span className="chip-zip">{p.zip}</span>}
              </button>
            ))}
          </div>
        )}

        <label className="check-field">
          <input
            type="checkbox"
            checked={missedLastFill}
            onChange={(e) => setMissedLastFill(e.target.checked)}
          />
          <span>I missed logging my last fill-up</span>
        </label>

        <label className="check-field">
          <input
            type="checkbox"
            checked={partialFill}
            onChange={(e) => setPartialFill(e.target.checked)}
          />
          <span>Partial fill — didn&apos;t fill to full</span>
        </label>
      </div>

      {toast !== null && (
        <div className="toast" role="status">
          {toast}
        </div>
      )}
    </form>
  )
}

export default QuickLogForm
