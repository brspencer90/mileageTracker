// Mirrors the pydantic models in docs/IMPLEMENTATION_PLAN.md §3.

export interface VehicleOut {
  id: number
  name: string
  make: string | null
  model: string | null
  year: number | null
  tank_size_gal: number | null
}

export interface FillupCreate {
  vehicle_id: number
  /** ISO date, YYYY-MM-DD */
  date: string
  /** null creates a PENDING fill with no odometer reading (MT-24) */
  mileage: number | null
  gallons: number
  cost: number
  station: string | null
  /** 5 digits when present */
  zip: string | null
  missed_last_fill: boolean
}

/** PATCH semantics: all fields optional, vehicle_id excluded. */
export type FillupUpdate = Partial<Omit<FillupCreate, 'vehicle_id'>>

export interface FillupOut extends Omit<FillupCreate, 'cost'> {
  id: number
  /** null on one historical row imported with a blank cost */
  cost: number | null
  /**
   * Interpolated odometer the server offers for a PENDING fill (mileage null)
   * once it is bracketed by real fills; null when not yet estimable (MT-24).
   */
  suggested_mileage: number | null
  /** odometer reconstructed on import (MT-21) */
  mileage_estimated: boolean
  /** raw fuel-gauge column from the xlsx source (MT-20/MT-22) */
  gauge_notches: number | null
  mpf: number | null
  mpg: number | null
  /** MPG rests on at least one estimated odometer reading */
  mpg_estimated: boolean
  created_at: string
}

export interface FillupList {
  items: FillupOut[]
  total: number
}

export interface StationPick {
  station: string
  zip: string | null
}

export interface FillupContext {
  prev_mileage: number | null
  last_station: string | null
  last_zip: string | null
  /** 5 most recent distinct station+zip pairs */
  recent_stations: StationPick[]
  tank_size_gal: number | null
}

export interface MpgPoint {
  date: string
  mileage: number
  mpg: number | null
  /** MPG rests on at least one estimated odometer reading */
  estimated: boolean
}

export interface MonthCost {
  /** "YYYY-MM" */
  month: string
  cost: number
  gallons: number
  fillups: number
}

/**
 * Dashboard KPIs — one call powering the summary tiles + header odometer.
 * Every metric is nullable so a fresh vehicle with no derivable history
 * degrades to "—" rather than erroring.
 */
export interface SummaryStats {
  /** latest known odometer reading */
  odometer: number | null
  total_fills: number
  /** ISO date of the earliest fill-up */
  tracked_since: string | null
  lifetime_mpg: number | null
  /** trailing-average MPG over the recent window */
  recent_mpg: number | null
  /** recent_mpg − lifetime_mpg (negative = running below average) */
  mpg_delta: number | null
  cost_per_mile: number | null
  spend_30d: number | null
  spend_30d_fills: number
  avg_days_between: number | null
}
