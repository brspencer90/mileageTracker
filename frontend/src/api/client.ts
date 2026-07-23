import type {
  FillupContext,
  FillupCreate,
  FillupList,
  FillupOut,
  FillupUpdate,
  MonthCost,
  MpgPoint,
  VehicleOut,
} from './types'

export class ApiError extends Error {
  readonly status: number

  constructor(status: number, message: string) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

/** Extract a human message from a FastAPI error body. */
function detailMessage(body: unknown, fallback: string): string {
  if (typeof body !== 'object' || body === null || !('detail' in body)) {
    return fallback
  }
  const detail = (body as { detail: unknown }).detail
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) {
    // Pydantic validation errors: [{loc, msg, type}, ...]
    const msgs = detail
      .map((d) =>
        typeof d === 'object' && d !== null && 'msg' in d
          ? String((d as { msg: unknown }).msg)
          : null,
      )
      .filter((m): m is string => m !== null)
    if (msgs.length > 0) return msgs.join('; ')
  }
  return fallback
}

async function request<T>(
  method: string,
  path: string,
  body?: unknown,
): Promise<T> {
  let res: Response
  try {
    res = await fetch(path, {
      method,
      headers:
        body === undefined ? undefined : { 'Content-Type': 'application/json' },
      body: body === undefined ? undefined : JSON.stringify(body),
    })
  } catch {
    throw new ApiError(0, 'Network error — is the server reachable?')
  }
  if (!res.ok) {
    const fallback = `Request failed (${res.status})`
    let parsed: unknown = null
    try {
      parsed = await res.json()
    } catch {
      // non-JSON error body; keep fallback
    }
    throw new ApiError(res.status, detailMessage(parsed, fallback))
  }
  if (res.status === 204) return undefined as T
  return (await res.json()) as T
}

export function getVehicles(): Promise<VehicleOut[]> {
  return request('GET', '/api/vehicles')
}

export function getFillups(
  vehicleId: number,
  limit = 50,
  offset = 0,
): Promise<FillupList> {
  return request(
    'GET',
    `/api/fillups?vehicle_id=${vehicleId}&limit=${limit}&offset=${offset}`,
  )
}

export function createFillup(body: FillupCreate): Promise<FillupOut> {
  return request('POST', '/api/fillups', body)
}

export function updateFillup(
  id: number,
  body: FillupUpdate,
): Promise<FillupOut> {
  return request('PATCH', `/api/fillups/${id}`, body)
}

export function deleteFillup(id: number): Promise<void> {
  return request('DELETE', `/api/fillups/${id}`)
}

/**
 * Accept the server's interpolated odometer for a PENDING fill (MT-24).
 * Stores it flagged as estimated and returns the updated row.
 */
export function resolveMileage(
  id: number,
  mileage: number,
): Promise<FillupOut> {
  return request('POST', `/api/fillups/${id}/resolve-mileage`, { mileage })
}

export function getFillupContext(vehicleId: number): Promise<FillupContext> {
  return request('GET', `/api/fillups/context?vehicle_id=${vehicleId}`)
}

export function getMpgStats(vehicleId: number): Promise<MpgPoint[]> {
  return request('GET', `/api/stats/mpg?vehicle_id=${vehicleId}`)
}

export function getCostByMonth(vehicleId: number): Promise<MonthCost[]> {
  return request('GET', `/api/stats/cost-by-month?vehicle_id=${vehicleId}`)
}
