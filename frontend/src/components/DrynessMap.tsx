import { geoJSON, type Layer, type PathOptions } from 'leaflet'
import { useEffect, useMemo, useState } from 'react'
import { GeoJSON, MapContainer, TileLayer, useMap } from 'react-leaflet'
import { getMap, getMunicipalMap, getMunicipalShapes, getShapes } from '../api'
import { colourInfo } from '../colours'
import type {
  Colour, MapQuarter, MapShape, MapViewName, MunicipalMap, MunicipalRow, MunicipalShapes, MunicipalViewName, Shapes,
} from '../types'
import MunicipalLayer from './MunicipalLayer'

const viewNames: Record<MapViewName, string> = {
  prediction: 'Province prediction',
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
  const [municipalShapes, setMunicipalShapes] = useState<MunicipalShapes | null>(null)
  const [municipalMap, setMunicipalMap] = useState<MunicipalMap | null>(null)
  const [municipalError, setMunicipalError] = useState<string | null>(null)

  useEffect(() => {
    let ignore = false // see App.tsx: stops a cancelled effect run from setting state
    Promise.all([getMap(), getShapes()])
      .then(([quarters, shapes]) => { if (!ignore) setData({ quarters, shapes }) })
      .catch((caught: Error) => { if (!ignore) setError(caught.message) })
    return () => { ignore = true }
  }, [])

  // Every view except the prediction is per municipality.
  const isMunicipal = view !== 'prediction'
  const quarterLabel = data?.quarters[quarterIndex].quarter

  // The municipal shapes (about 620 KB) load the first time a municipal view is picked, then stay.
  useEffect(() => {
    if (!isMunicipal || municipalShapes) return
    let ignore = false
    getMunicipalShapes()
      .then((shapes) => { if (!ignore) setMunicipalShapes(shapes) })
      .catch((caught: Error) => { if (!ignore) setMunicipalError(caught.message) })
    return () => { ignore = true }
  }, [isMunicipal, municipalShapes])

  // The colours (about 11 KB) load on every quarter or view change.
  useEffect(() => {
    if (!isMunicipal || !quarterLabel) return
    let ignore = false
    getMunicipalMap(quarterLabel, view as MunicipalViewName)
      .then((map) => { if (!ignore) { setMunicipalMap(map); setMunicipalError(null) } })
      .catch((caught: Error) => { if (!ignore) setMunicipalError(caught.message) })
    return () => { ignore = true }
  }, [isMunicipal, quarterLabel, view])

  // Stable between renders, so the municipal layer only recolours when new rows arrive.
  const municipalRows = useMemo(
    () => new Map<string, MunicipalRow>((municipalMap?.municipalities ?? []).map((row) => [row.adm3_psgc, row])),
    [municipalMap],
  )
  const provinceNames = useMemo(
    () => new Map((data?.shapes.features ?? []).map((feature) => [feature.properties.map_psgc, feature.properties.name])),
    [data],
  )

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

  // Province borders over the municipal layer: outline only, and not interactive, so hovering
  // still reaches the municipality underneath.
  const outlineFor = (code: string): PathOptions => {
    const chosen = province !== '' && byCode.get(code)?.province === province
    return { fill: false, color: chosen ? '#111827' : '#4b5563', weight: chosen ? 3 : 1 }
  }

  // The colours on screen match the controls only once the matching rows have arrived.
  const municipalReady = municipalMap?.quarter === quarter.quarter && municipalMap.view === view

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

      {/* preferCanvas: draw every shape on one canvas instead of one SVG element each (faster with many shapes). */}
      <MapContainer center={countryCenter} zoom={countryZoom} preferCanvas className="mt-4 h-[500px] w-full rounded">
        <ZoomToProvince province={province} quarters={data.quarters} shapes={data.shapes} />
        <TileLayer
          url="https://tile.openstreetmap.org/{z}/{x}/{y}.png"
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
        />
        {!isMunicipal && (
          // <GeoJSON> only reads its style once, so a new key makes React rebuild it on any change.
          <GeoJSON
            key={`${quarter.quarter}|${view}|${province}`}
            data={data.shapes}
            style={(feature) => styleFor(feature?.properties.map_psgc ?? '')}
            onEachFeature={(feature, layer) => addTooltip(feature.properties.map_psgc, feature.properties.name, layer)}
          />
        )}
        {isMunicipal && municipalShapes && (
          <>
            <MunicipalLayer shapes={municipalShapes} rows={municipalRows} provinceNames={provinceNames} />
            {/* 88 shapes, so rebuilding on a province change is cheap; that moves the thick outline. */}
            <GeoJSON
              key={`outline|${province}`}
              data={data.shapes}
              interactive={false}
              style={(feature) => outlineFor(feature?.properties.map_psgc ?? '')}
            />
          </>
        )}
      </MapContainer>
      {isMunicipal && !municipalError && (!municipalShapes || !municipalReady) && (
        <p className="mt-2 text-sm text-gray-500">
          {municipalShapes ? 'Loading municipal colours...' : 'Loading municipal map (1,642 municipalities)...'}
        </p>
      )}
      {isMunicipal && municipalError && (
        <p className="mt-2 text-red-600">Could not load the municipal map: {municipalError}</p>
      )}

      <div className="mt-3 flex flex-wrap gap-4 text-sm">
        {(Object.keys(colourInfo) as Colour[]).map((colour) => (
          <span key={colour} className="flex items-center gap-2">
            <span className="inline-block h-3 w-3 rounded-full" style={{ backgroundColor: colourInfo[colour].hex }} />
            {colourInfo[colour].label}
          </span>
        ))}
      </div>
      {isMunicipal ? (
        <p className="mt-3 text-sm text-gray-500">
          Each municipality is coloured by its own observed rainfall in that quarter, against its 1989-2018
          normal. Municipal percentages can look very large in dry quarters where normal rain is tiny (for
          example 300% of a 5 mm normal). Kalayaan has no rainfall data and stays grey. Crop yield is only
          available per province, so it is a province estimate.
        </p>
      ) : (
        <p className="mt-3 text-sm text-gray-500">
          Province prediction: each province is coloured by its predicted rainfall. The colours show only the
          central (most likely) forecast, not its uncertainty. The 2027 Q1 red count is likely exaggerated:
          read it as "most provinces near or below the red line".
        </p>
      )}
    </section>
  )
}

export default DrynessMap
