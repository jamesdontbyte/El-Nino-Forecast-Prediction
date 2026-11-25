import { useEffect, useState } from 'react'
import { getImpact } from '../api'
import { colourInfo } from '../colours'
import DrynessMap from '../components/DrynessMap'
import ProvinceCropPicker from '../components/ProvinceCropPicker'
import type { Impact, ImpactQuarter, Options } from '../types'

// "+1.2%" or "-4.5%", so a gain and a loss are easy to tell apart.
const signedPercent = (value: number) => `${value > 0 ? '+' : ''}${value.toFixed(1)}%`

interface Props {
  options: Options
  province: string
  crop: string
  onProvinceChange: (province: string) => void
  onCropChange: (crop: string) => void
}

function ImpactPage({ options, province, crop, onProvinceChange, onCropChange }: Props) {
  // Each result remembers which choice it belongs to. A result for an older choice is not shown,
  // so the page shows "Loading" after a change without having to clear anything.
  const [result, setResult] = useState<{ choice: string; impact?: Impact; error?: string } | null>(null)
  const chosen = province !== '' && crop !== ''
  const choice = `${province}|${crop}`
  const current = result?.choice === choice ? result : null

  useEffect(() => {
    if (!chosen) return
    // The flag stops an older, slower response from overwriting the result for a newer choice.
    let ignore = false
    getImpact(province, crop)
      .then((impact) => { if (!ignore) setResult({ choice, impact }) })
      .catch((caught: Error) => { if (!ignore) setResult({ choice, error: caught.message }) })
    return () => { ignore = true }
  }, [chosen, choice, province, crop])

  const impact = current?.impact
  const error = current?.error

  return (
    <div className="space-y-6">
      <ProvinceCropPicker
        options={options}
        province={province}
        crop={crop}
        onProvinceChange={onProvinceChange}
        onCropChange={onCropChange}
      />
      {!chosen && <p>Choose a province and crop.</p>}
      {chosen && error && <p className="text-red-600">Could not load the impact: {error}</p>}
      {chosen && !error && !impact && <p>Loading impact...</p>}
      {chosen && impact && (
        <div className="grid gap-6 sm:grid-cols-2">
          {impact.quarters.map((quarter) => <QuarterCard key={quarter.quarter} quarter={quarter} />)}
        </div>
      )}
      <DrynessMap province={province} />
    </div>
  )
}

export function QuarterCard({ quarter }: { quarter: ImpactQuarter }) {
  const colour = colourInfo[quarter.colour]
  return (
    <section className="rounded-lg bg-white p-6 shadow-sm">
      <h2 className="text-lg font-semibold">{quarter.quarter}</h2>
      <p className="mt-3 flex items-center gap-2">
        <span className="inline-block h-4 w-4 rounded-full" style={{ backgroundColor: colour.hex }} />
        {colour.label}
      </p>
      <p className="mt-1">Rain: {quarter.rain_pct.toFixed(1)}% of normal</p>
      {/* When enough_data is true the back end always fills the three yield fields, hence the `!`. */}
      {quarter.enough_data ? (
        <>
          <p className="mt-3 text-2xl font-semibold">{signedPercent(quarter.yield_change_pct!)} yield</p>
          <p className="text-gray-500">
            Normal {quarter.normal_yield_t_per_ha!.toFixed(2)} t/ha, predicted{' '}
            {quarter.predicted_yield_t_per_ha!.toFixed(2)} t/ha
          </p>
        </>
      ) : (
        <p className="mt-3 text-gray-500">Not enough data to predict the yield for this crop here.</p>
      )}
    </section>
  )
}

export default ImpactPage
