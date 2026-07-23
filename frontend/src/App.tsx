import { useEffect, useState } from 'react'
import { getVehicles } from './api/client'
import type { VehicleOut } from './api/types'
import VehiclePicker from './components/VehiclePicker'
import QuickLogForm from './components/QuickLogForm'
import HistoryTable from './components/HistoryTable'
import MpgChart from './components/MpgChart'
import CostChart from './components/CostChart'
import './App.css'

type Tab = 'log' | 'history'

function App() {
  const [vehicles, setVehicles] = useState<VehicleOut[] | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [selectedVehicleId, setSelectedVehicleId] = useState<number | null>(null)
  const [activeTab, setActiveTab] = useState<Tab>('log')
  // Bumped after any create/edit/delete so history + charts refetch.
  const [dataVersion, setDataVersion] = useState(0)

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

  const bumpVersion = () => setDataVersion((v) => v + 1)

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
        <MpgChart vehicleId={selectedVehicleId} version={dataVersion} />
        <CostChart vehicleId={selectedVehicleId} version={dataVersion} />
        <HistoryTable vehicleId={selectedVehicleId} onChanged={bumpVersion} />
      </>
    )
  }

  return (
    <div className="app">
      <header className="app-header">
        <h1>Mileage Tracker</h1>
        {vehicles !== null && (
          <VehiclePicker
            vehicles={vehicles}
            selectedId={selectedVehicleId}
            onSelect={setSelectedVehicleId}
          />
        )}
      </header>

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
