import type { GeoJSON as LeafletGeoJSON, PathOptions } from 'leaflet'
import { useEffect, useRef } from 'react'
import { GeoJSON } from 'react-leaflet'
import { colourInfo } from '../colours'
import type { MunicipalRow, MunicipalShapes } from '../types'

type Feature = MunicipalShapes['features'][number]
type Rows = Map<string, MunicipalRow> // by adm3_psgc

function styleFor(rows: Rows, feature?: Feature): PathOptions {
  const row = feature && rows.get(feature.properties.adm3_psgc)
  return { fillColor: colourInfo[row?.colour ?? 'grey'].hex, fillOpacity: 0.7, color: '#ffffff', weight: 0.5 }
}

// 1,642 municipal shapes. Built once (no changing key); when new rows arrive, the colours are
// changed in place with setStyle, and the tooltips read the latest rows through a ref. Rebuilding
// 1,642 shapes and tooltips on every quarter or view change would be slow.
function MunicipalLayer({ shapes, rows, provinceNames }: {
  shapes: MunicipalShapes
  rows: Rows // empty while the first colours load
  provinceNames: Map<string, string> // map_psgc -> province shape name, for the tooltip
}) {
  const layerRef = useRef<LeafletGeoJSON>(null)
  const rowsRef = useRef(rows)

  useEffect(() => {
    rowsRef.current = rows
    layerRef.current?.setStyle((feature) => styleFor(rows, feature as Feature))
  }, [rows])

  return (
    <GeoJSON
      ref={layerRef}
      data={shapes}
      style={(feature) => styleFor(rowsRef.current, feature as Feature)}
      onEachFeature={(feature: Feature, layer) => {
        const { adm3_psgc, name, map_psgc } = feature.properties
        // A function, so the tooltip shows the current rows without being bound again.
        layer.bindTooltip(() => {
          const rain = rowsRef.current.get(adm3_psgc)?.rain_pct
          const rainText = rain == null ? 'no rainfall data' : `${rain.toFixed(1)}% of normal rain`
          return `${name} (${provinceNames.get(map_psgc) ?? ''}): ${rainText}`
        })
      }}
    />
  )
}

export default MunicipalLayer
