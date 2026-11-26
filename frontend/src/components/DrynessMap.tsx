import { geoJSON, type Layer, type PathOptions } from 'leaflet'
import { useEffect, useState } from 'react'
import { GeoJSON, MapContainer, TileLayer, useMap } from 'react-leaflet'
import { getMap, getShapes } from '../api'
import { colourInfo } from '../colours'
import type { Colour, MapQuarter, MapShape, MapViewName, Shapes } from '../types'

const viewNames: Record<MapViewName, string> = {
  prediction: 'Prediction',
  normal: 'Normal year',
  el_nino_2015_16: 'El Niño 2015-16',
  el_nino_2023_24: 'El Niño 2023-24',
}

const countryCenter: [number, number] = [12.5, 122]
const countryZoom = 5

// Zooms to the chosen province, or back to the whole country when none is chosen.
// Sits outside the keyed <GeoJSON>, so changing quarter or view does not re-zoom.
function ZoomToProvince({ province, quarters, shapes }: { province: string; quarters: MapQuarter[]; shapes: Shapes }) {
  const map = useMap()
  useEffect(() => {
    // Merged provinces (Maguindanao, Davao del Sur) have 2 shapes, so collect every code with this name.
    const codes = new Set(
      quarters[0].views.prediction.shapes.filter((shape) => shape.province === province).map((shape) => shape.map_psgc),
    )
    const chosen = shapes.features.filter((feature) => codes.has(feature.properties.map_psgc))
    if (chosen.length === 0) map.setView(countryCenter, countryZoom)
    else map.fitBounds(geoJSON(chosen).getBounds())
  }, [map, province, quarters, shapes])
  return null
}

// The chosen province (a crop province name, '' if none) gets a thick outline.
function DrynessMap({ province }: { province: string }) {
  const [data, setData] = useState<{ quarters: MapQuarter[]; shapes: Shapes } | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [quarterIndex, setQuarterIndex] = useState(0)
  const [view, setView] = useState<MapViewName>('prediction')

  useEffect(() => {
    let ignore = false // see App.tsx: stops a cancelled effect run from setting state
    Promise.all([getMap(), getShapes()])
      .then(([quarters, shapes]) => { if (!ignore) setData({ quarters, shapes }) })
      .catch((caught: Error) => { if (!ignore) setError(caught.message) })
    return () => { ignore = true }
  }, [])

  if (error) return <p className="text-red-600">Could not load the map: {error}</p>
  if (!data) return <p>Loading map...</p>

  const quarter = data.quarters[quarterIndex]
  const shownView = quarter.views[view]
  // The shapes carry only map_psgc and name; colour and rain come from /api/map by the same code.
  const byCode = new Map<string, MapShape>(shownView.shapes.map((shape) => [shape.map_psgc, shape]))

  const styleFor = (code: string): PathOptions => {
    const shape = byCode.get(code)
    const chosen = province !== '' && shape?.province === province
    return {
      fillColor: colourInfo[shape?.colour ?? 'grey'].hex,
      fillOpacity: 0.7,
      color: chosen ? '#111827' : '#ffffff',
      weight: chosen ? 3 : 1,
    }
  }

  const addTooltip = (code: string, name: string, layer: Layer) => {
    const rain = byCode.get(code)?.rain_pct
    layer.bindTooltip(`${name}: ${rain == null ? 'no rainfall data' : `${rain.toFixed(1)}% of normal rain`}`)
  }

  return (
    <section className="rounded-lg bg-white p-6 shadow-sm">
      <h2 className="text-lg font-semibold">Dryness map</h2>
      <div className="mt-3 flex flex-wrap gap-4">
        <label className="flex flex-col text-sm text-gray-500">
          Quarter
          <select
            value={quarterIndex}
            onChange={(event) => setQuarterIndex(Number(event.target.value))}
            className="mt-1 rounded border bg-white px-3 py-2 text-base text-gray-900"
          >
            {data.quarters.map((item, index) => <option key={item.quarter} value={index}>{item.quarter}</option>)}
          </select>
        </label>
        <label className="flex flex-col text-sm text-gray-500">
          View
          <select
            value={view}
            onChange={(event) => setView(event.target.value as MapViewName)}
            className="mt-1 rounded border bg-white px-3 py-2 text-base text-gray-900"
          >
            {(Object.keys(viewNames) as MapViewName[]).map((name) => {
              const year = quarter.views[name].year
              return (
                // A past event with no year for this quarter has no data, so it cannot be picked.
                <option key={name} value={name} disabled={year === null}>
                  {viewNames[name]} {year === null ? '(no data for this quarter)' : `(${year})`}
                </option>
              )
            })}
          </select>
        </label>
      </div>

      <MapContainer center={countryCenter} zoom={countryZoom} className="mt-4 h-[500px] w-full rounded">
        <ZoomToProvince province={province} quarters={data.quarters} shapes={data.shapes} />
        <TileLayer
          url="https://tile.openstreetmap.org/{z}/{x}/{y}.png"
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
        />
        {/* <GeoJSON> only reads its style once, so a new key makes React rebuild it on any change. */}
        <GeoJSON
          key={`${quarter.quarter}|${view}|${province}`}
          data={data.shapes}
          style={(feature) => styleFor(feature?.properties.map_psgc ?? '')}
          onEachFeature={(feature, layer) => addTooltip(feature.properties.map_psgc, feature.properties.name, layer)}
        />
      </MapContainer>

      <div className="mt-3 flex flex-wrap gap-4 text-sm">
        {(Object.keys(colourInfo) as Colour[]).map((colour) => (
          <span key={colour} className="flex items-center gap-2">
            <span className="inline-block h-3 w-3 rounded-full" style={{ backgroundColor: colourInfo[colour].hex }} />
            {colourInfo[colour].label}
          </span>
        ))}
      </div>
      <p className="mt-3 text-sm text-gray-500">
        The colours show only the central (most likely) forecast, not its uncertainty. The 2027 Q1 red count
        is likely exaggerated: read it as "most provinces near or below the red line".
      </p>
    </section>
  )
}

export default DrynessMap
