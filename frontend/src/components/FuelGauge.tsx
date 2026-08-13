import { useId, useRef } from 'react'
import type { KeyboardEvent, PointerEvent } from 'react'

/**
 * FuelGauge — a horizontal fuel-gauge stepper styled after a 2019 VW Golf GTI
 * (MK7.5) instrument cluster. The owner reads the gauge as 8 major notches
 * (E→F) in quarter-notch steps, so the value runs 0..8 in 0.25 increments.
 *
 * Value semantics: `null` means "not recorded" (the field is optional). The
 * control starts empty and stays null until the user touches it; a Clear
 * affordance returns it to null.
 */

const MAX = 8
const STEP = 0.25
const RESERVE = 1.5 // notches near E shaded warm to evoke the low-fuel warning

interface Props {
  value: number | null
  onChange: (value: number | null) => void
  /** id of an external label element, if any */
  labelledBy?: string
}

function clamp(v: number): number {
  return Math.min(MAX, Math.max(0, v))
}

function snap(v: number): number {
  return clamp(Math.round(v / STEP) * STEP)
}

const FRAC: Record<number, string> = { 0.25: '¼', 0.5: '½', 0.75: '¾' }

/** 4.25 -> "4¼", 0.5 -> "½", 8 -> "8". */
function formatNotches(v: number): string {
  const whole = Math.floor(v + 1e-9)
  const frac = Math.round((v - whole) / STEP) * STEP
  const f = FRAC[frac]
  if (!f) return String(whole)
  return whole === 0 ? f : `${whole}${f}`
}

function PumpGlyph() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true" className="fg-pump" focusable="false">
      <path
        fill="none"
        stroke="currentColor"
        strokeWidth="1.7"
        strokeLinecap="round"
        strokeLinejoin="round"
        d="M4 20V6a2 2 0 0 1 2-2h5a2 2 0 0 1 2 2v14M3 20h11M4 12h9M16 8l3 3v6a1.6 1.6 0 0 0 3 0v-8l-3-3"
      />
    </svg>
  )
}

function FuelGauge({ value, onChange, labelledBy }: Props) {
  const faceRef = useRef<HTMLDivElement>(null)
  const dragging = useRef(false)
  const autoId = useId()

  const set = value !== null
  const pct = set ? (value / MAX) * 100 : 0

  // Reserve zone shading is anchored to E (left), not to the fill's own width,
  // so it stays put as the bar grows. Since the gradient is relative to the
  // fill element (which spans `value` notches), the reserve boundary sits at
  // fraction RESERVE/value of the fill.
  const reserveFrac = set && value > 0 ? Math.min(1, RESERVE / value) : 1
  const fillStyle =
    set && value > 0
      ? {
          width: `${pct}%`,
          backgroundImage: `linear-gradient(90deg, var(--fg-reserve) 0%, var(--fg-reserve) ${reserveFrac * 55}%, var(--fg-red) ${reserveFrac * 100}%, var(--fg-red) 100%)`,
        }
      : { width: '0%' }

  const commit = (v: number | null) => onChange(v)

  const fromClientX = (clientX: number): number => {
    const el = faceRef.current
    if (!el) return 0
    const rect = el.getBoundingClientRect()
    const frac = (clientX - rect.left) / rect.width
    return snap(frac * MAX)
  }

  const handlePointerDown = (e: PointerEvent<HTMLDivElement>) => {
    dragging.current = true
    e.currentTarget.setPointerCapture(e.pointerId)
    commit(fromClientX(e.clientX))
  }
  const handlePointerMove = (e: PointerEvent<HTMLDivElement>) => {
    if (!dragging.current) return
    commit(fromClientX(e.clientX))
  }
  const handlePointerUp = (e: PointerEvent<HTMLDivElement>) => {
    dragging.current = false
    if (e.currentTarget.hasPointerCapture(e.pointerId)) {
      e.currentTarget.releasePointerCapture(e.pointerId)
    }
  }

  const nudge = (delta: number) => commit(snap((value ?? 0) + delta))

  const handleKeyDown = (e: KeyboardEvent<HTMLDivElement>) => {
    const base = value ?? 0
    let next: number | null = null
    switch (e.key) {
      case 'ArrowRight':
      case 'ArrowUp':
        next = snap(base + STEP)
        break
      case 'ArrowLeft':
      case 'ArrowDown':
        next = snap(base - STEP)
        break
      case 'PageUp':
        next = snap(base + 1)
        break
      case 'PageDown':
        next = snap(base - 1)
        break
      case 'Home':
        next = 0
        break
      case 'End':
        next = MAX
        break
      case 'Delete':
      case 'Backspace':
        e.preventDefault()
        commit(null)
        return
      default:
        return
    }
    e.preventDefault()
    commit(next)
  }

  // 33 tick positions (0..8 in quarter steps); every 4th is a major notch.
  const ticks = Array.from({ length: MAX * 4 + 1 }, (_, i) => i)

  const readoutId = `${autoId}-readout`

  return (
    <div className="fuel-gauge">
      <div className="fg-head">
        <span className="fg-title" id={readoutId}>
          <PumpGlyph />
          Fuel gauge
          <span className="fg-optional">optional</span>
        </span>
        <span className="fg-readout" aria-hidden="true">
          {set ? (
            <>
              <b>{formatNotches(value)}</b>
              <span className="fg-readout-max"> / {MAX}</span>
            </>
          ) : (
            <span className="fg-notset">Not set</span>
          )}
        </span>
      </div>

      <div className="fg-controls">
        <button
          type="button"
          className="fg-nudge"
          aria-label="Down a quarter notch"
          onClick={() => nudge(-STEP)}
        >
          <span aria-hidden="true">&minus;</span>
        </button>

        <div className="fg-track">
          <div
            ref={faceRef}
            className="fg-face"
            role="slider"
            tabIndex={0}
            aria-labelledby={labelledBy ?? readoutId}
            aria-valuemin={0}
            aria-valuemax={MAX}
            {...(set ? { 'aria-valuenow': value } : {})}
            aria-valuetext={set ? `${formatNotches(value)} of ${MAX} notches` : 'Not set'}
            aria-orientation="horizontal"
            onPointerDown={handlePointerDown}
            onPointerMove={handlePointerMove}
            onPointerUp={handlePointerUp}
            onPointerCancel={handlePointerUp}
            onKeyDown={handleKeyDown}
          >
            <div className="fg-ticks" aria-hidden="true">
              {ticks.map((i) => (
                <span
                  key={i}
                  className={i % 4 === 0 ? 'fg-tick fg-tick-major' : 'fg-tick'}
                  style={{ left: `${(i / (MAX * 4)) * 100}%` }}
                />
              ))}
            </div>
            <div className="fg-fill" style={fillStyle} aria-hidden="true" />
            {set && (
              <div
                className="fg-thumb"
                style={{ left: `${pct}%` }}
                aria-hidden="true"
              />
            )}
          </div>
          <div className="fg-scale" aria-hidden="true">
            <span className="fg-scale-e">E</span>
            <span className="fg-scale-h">&frac12;</span>
            <span className="fg-scale-f">F</span>
          </div>
        </div>

        <button
          type="button"
          className="fg-nudge"
          aria-label="Up a quarter notch"
          onClick={() => nudge(STEP)}
        >
          <span aria-hidden="true">+</span>
        </button>
      </div>

      {set && (
        <button type="button" className="fg-clear" onClick={() => commit(null)}>
          Clear
        </button>
      )}
    </div>
  )
}

export default FuelGauge
