import { useEffect, useState } from 'react'
import { getSummary, getVehicles } from './api/client'
import type { SummaryStats, VehicleOut } from './api/types'
import { formatMonthYear } from './lib/format'
import VehiclePicker from './components/VehiclePicker'
import QuickLogForm from './components/QuickLogForm'
import HistoryTable from './components/HistoryTable'
import MpgChart from './components/MpgChart'
import CostChart from './components/CostChart'
import SummaryTiles from './components/SummaryTiles'
import './App.css'

type Tab = 'log' | 'history'

/** "2019 VW GTI" from whichever of year/make/model are present, else null. */
function vehicleDesc(v: VehicleOut): string | null {
  const parts = [
    v.year !== null ? String(v.year) : null,
    v.make,
    v.model,
  ].filter((p): p is string => p !== null && p !== '')
  return parts.length > 0 ? parts.join(' ') : null
}

function App() {
  const [vehicles, setVehicles] = useState<VehicleOut[] | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [selectedVehicleId, setSelectedVehicleId] = useState<number | null>(null)
  const [activeTab, setActiveTab] = useState<Tab>('log')
  // Bumped after any create/edit/delete so history + charts + summary refetch.
  const [dataVersion, setDataVersion] = useState(0)
  // Shared summary — powers the header odometer, SummaryTiles, and the
  // HistoryTable "vs avg" baseline. Null while loading or on error.
  const [summary, setSummary] = useState<SummaryStats | null>(null)

  useEffect(() => {
    getVehicles()
      .then((vs) => {
        setVehicles(vs)
        // Auto-select when exactly one; with several, default to the first
        // so the form is immediately usable (picker lets you switch).
        if (vs.length >= 1) setSelectedVehicleId(vs[0].id)
      })
      .catch((e: unknown) => {
        setLoadError(e instanceof Error ? e.message : 'Failed to load vehicles')
      })
  }, [])

  useEffect(() => {
    if (selectedVehicleId === null) {
      setSummary(null)
      return
    }
    let cancelled = false
    getSummary(selectedVehicleId)
      .then((s) => {
        if (!cancelled) setSummary(s)
      })
      .catch(() => {
        // Summary is progressive enhancement — never blocks the core UI.
        if (!cancelled) setSummary(null)
      })
    return () => {
      cancelled = true
    }
  }, [selectedVehicleId, dataVersion])

  const bumpVersion = () => setDataVersion((v) => v + 1)

  const selectedVehicle =
    vehicles?.find((v) => v.id === selectedVehicleId) ?? null

  const subtitle = (() => {
    if (selectedVehicle === null) return null
    const parts = [
      vehicleDesc(selectedVehicle),
      summary?.tracked_since != null
        ? `tracked since ${formatMonthYear(summary.tracked_since)}`
        : null,
    ].filter((p): p is string => p !== null)
    return parts.length > 0 ? parts.join(' · ') : null
  })()

  let content
  if (loadError !== null) {
    content = <p className="status-msg error-msg">{loadError}</p>
  } else if (vehicles === null) {
    content = <p className="status-msg">Loading…</p>
  } else if (vehicles.length === 0 || selectedVehicleId === null) {
    content = (
      <p className="status-msg">
        No vehicles yet — create one with the importer or sqlite3 CLI.
      </p>
    )
  } else if (activeTab === 'log') {
    content = (
      <QuickLogForm
        key={selectedVehicleId}
        vehicleId={selectedVehicleId}
        onLogged={bumpVersion}
      />
    )
  } else {
    content = (
      <>
        <SummaryTiles
          vehicleId={selectedVehicleId}
          summary={summary}
          version={dataVersion}
        />
        <MpgChart vehicleId={selectedVehicleId} version={dataVersion} />
        <CostChart vehicleId={selectedVehicleId} version={dataVersion} />
        <HistoryTable
          vehicleId={selectedVehicleId}
          onChanged={bumpVersion}
          lifetimeMpg={summary?.lifetime_mpg ?? null}
        />
      </>
    )
  }

  return (
    <div className="app">
      <header className="app-header">
        <div className="brand">
          <span className="brand-mark" aria-hidden="true">
            <svg viewBox="0 0 24 24" fill="none" stroke="#fff" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round">
              <path d="M5 21V5a2 2 0 0 1 2-2h6a2 2 0 0 1 2 2v16" />
              <path d="M3 21h14" />
              <path d="M15 9h2.5a1.5 1.5 0 0 1 1.5 1.5V16a2 2 0 0 0 2 2v0a2 2 0 0 0 2-2v-6l-3-3" />
              <path d="M7 8h6" />
            </svg>
          </span>
          <div className="brand-id">
            <h1>{selectedVehicle?.name ?? 'Mileage Tracker'}</h1>
            {subtitle !== null && <div className="brand-sub">{subtitle}</div>}
          </div>
        </div>
        <div className="odo">
          <div className="odo-n tnum">
            {summary?.odometer != null ? summary.odometer.toLocaleString() : '—'}
          </div>
          <div className="odo-l">miles</div>
        </div>
      </header>

      {vehicles !== null && vehicles.length > 1 && (
        <div className="vehicle-picker-row">
          <VehiclePicker
            vehicles={vehicles}
            selectedId={selectedVehicleId}
            onSelect={setSelectedVehicleId}
          />
        </div>
      )}

      <main className="app-main">{content}</main>

      <nav className="tab-bar" aria-label="Main">
        <button
          type="button"
          className={activeTab === 'log' ? 'tab active' : 'tab'}
          aria-current={activeTab === 'log' ? 'page' : undefined}
          onClick={() => setActiveTab('log')}
        >
          <span className="tab-icon" aria-hidden="true">⛽</span>
          Log
        </button>
        <button
          type="button"
          className={activeTab === 'history' ? 'tab active' : 'tab'}
          aria-current={activeTab === 'history' ? 'page' : undefined}
          onClick={() => setActiveTab('history')}
        >
          <span className="tab-icon" aria-hidden="true">📈</span>
          History
        </button>
      </nav>
    </div>
  )
}

export default App
