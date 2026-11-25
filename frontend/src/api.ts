// One function per back-end route. The Vite proxy forwards /api to FastAPI (see vite.config.ts).
import type { Forecast, Impact, MapQuarter, Options, Shapes, Simulation } from './types'

// Fetch JSON. On a non-2xx response, throw an Error carrying the back end's `detail` text.
async function getJson<T>(path: string): Promise<T> {
  const response = await fetch(path)
  if (!response.ok) {
    let message = `${response.status} ${response.statusText}`
    try {
      const body = await response.json()
      // Our routes send detail as text. FastAPI's own range checks send a list of {msg} objects.
      if (typeof body.detail === 'string') message = body.detail
      else if (Array.isArray(body.detail)) message = body.detail.map((item: { msg: string }) => item.msg).join('; ')
    } catch {
      // The body was not JSON (for example the back end is not running), so keep the status text.
    }
    throw new Error(message)
  }
  return response.json()
}

export const getOptions = () => getJson<Options>('/api/options')
export const getForecast = () => getJson<Forecast>('/api/forecast')
export const getMap = () => getJson<MapQuarter[]>('/api/map')
export const getShapes = () => getJson<Shapes>('/api/shapes')

// URLSearchParams encodes spaces in crop names such as "Irrigated Palay".
export const getImpact = (province: string, crop: string) =>
  getJson<Impact>(`/api/impact?${new URLSearchParams({ province, crop })}`)

export interface SimulationInput {
  province: string
  crop: string
  irrigation: boolean
  switching: boolean
  // Left out of the URL when undefined, so the back end uses its defaults.
  pump_share?: number
  switch_share?: number
  irrigation_gain?: number
}

export function getSimulation(input: SimulationInput) {
  const params = new URLSearchParams()
  for (const [name, value] of Object.entries(input)) {
    if (value !== undefined) params.set(name, String(value))
  }
  return getJson<Simulation>(`/api/simulate?${params}`)
}
