import type { VehicleOut } from '../api/types'

interface Props {
  vehicles: VehicleOut[]
  selectedId: number | null
  onSelect: (id: number) => void
}

/** Renders nothing with a single vehicle; a select strip when several. */
function VehiclePicker({ vehicles, selectedId, onSelect }: Props) {
  if (vehicles.length <= 1) return null
  return (
    <select
      className="vehicle-picker"
      aria-label="Vehicle"
      value={selectedId ?? ''}
      onChange={(e) => onSelect(Number(e.target.value))}
    >
      {vehicles.map((v) => (
        <option key={v.id} value={v.id}>
          {v.name}
        </option>
      ))}
    </select>
  )
}

export default VehiclePicker
