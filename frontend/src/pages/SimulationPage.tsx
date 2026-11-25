import { useState, type ReactNode } from 'react'
import { getSimulation } from '../api'
import { colourInfo } from '../colours'
import ProvinceCropPicker from '../components/ProvinceCropPicker'
import type { Options, Simulation, SimulationOutcome, SimulationQuarter } from '../types'

// "+1.2%" or "-4.5%", so a gain and a loss are easy to tell apart.
const signedPercent = (value: number) => `${value > 0 ? '+' : ''}${value.toFixed(1)}%`

// The three assumptions the user can change. Defaults and ranges match backend/app/api/simulation.py.
const numberInputs = [
  { name: 'pump_share', label: 'Pump share (0 to 1)', max: 1, step: 0.05, initial: '0.2' },
  { name: 'switch_share', label: 'Switch share (0 to 1)', max: 1, step: 0.05, initial: '0.1' },
  { name: 'irrigation_gain', label: 'Irrigation gain, points (0 to 10)', max: 10, step: 0.1, initial: '3.6' },
] as const
type NumberName = (typeof numberInputs)[number]['name']

const assumptionNames: Record<string, string> = {
  farmers: 'Farmers simulated',
  pump_share: 'Pump share',
  switch_share: 'Switch share',
  irrigation_gain: 'Irrigation gain (points)',
}

interface Props {
  options: Options
  province: string
  crop: string
  onProvinceChange: (province: string) => void
  onCropChange: (crop: string) => void
}

function SimulationPage({ options, province, crop, onProvinceChange, onCropChange }: Props) {
  const [irrigation, setIrrigation] = useState(false)
  const [switching, setSwitching] = useState(false)
  // Kept as text, so the user can clear a box. An empty box is left out and the back end uses its default.
  const [numbers, setNumbers] = useState<Record<NumberName, string>>(
    () => Object.fromEntries(numberInputs.map((input) => [input.name, input.initial])) as Record<NumberName, string>,
  )
  const [running, setRunning] = useState(false)
  // Each result remembers the choice it was run for. A result for another province or crop is not
  // shown, which clears the results on a change without any extra state updates.
  const [result, setResult] = useState<{ choice: string; simulation?: Simulation; error?: string } | null>(null)

  const chosen = province !== '' && crop !== ''
  const choice = `${province}|${crop}`
  const current = result?.choice === choice ? result : null

  const run = () => {
    const optional = (name: NumberName) => (numbers[name].trim() === '' ? undefined : Number(numbers[name]))
    setRunning(true)
    getSimulation({
      province, crop, irrigation, switching,
      pump_share: optional('pump_share'),
      switch_share: optional('switch_share'),
      irrigation_gain: optional('irrigation_gain'),
    })
      .then((simulation) => setResult({ choice, simulation }))
      .catch((caught: Error) => setResult({ choice, error: caught.message }))
      .finally(() => setRunning(false))
  }

  return (
    <div className="space-y-6">
      <ProvinceCropPicker
        options={options}
        province={province}
        crop={crop}
        onProvinceChange={onProvinceChange}
        onCropChange={onCropChange}
      />

      <section className="rounded-lg bg-white p-6 shadow-sm">
        <h2 className="text-lg font-semibold">Policies</h2>
        <div className="mt-3 flex flex-wrap gap-6">
          <label className="flex items-center gap-2">
            <input type="checkbox" checked={irrigation} onChange={(event) => setIrrigation(event.target.checked)} />
            Irrigation support (pumps for rainfed palay farmers)
          </label>
          <label className="flex items-center gap-2">
            <input type="checkbox" checked={switching} onChange={(event) => setSwitching(event.target.checked)} />
            Crop switching (rainfed palay to corn)
          </label>
        </div>
        <div className="mt-4 flex flex-wrap gap-4">
          {numberInputs.map((input) => (
            <label key={input.name} className="flex flex-col text-sm text-gray-500">
              {input.label}
              <input
                type="number"
                min={0}
                max={input.max}
                step={input.step}
                value={numbers[input.name]}
                onChange={(event) => setNumbers({ ...numbers, [input.name]: event.target.value })}
                className="mt-1 w-40 rounded border px-3 py-2 text-base text-gray-900"
              />
            </label>
          ))}
        </div>
        <button
          onClick={run}
          disabled={!chosen || running}
          className="mt-4 rounded bg-blue-600 px-6 py-2 text-white hover:bg-blue-700 disabled:cursor-not-allowed disabled:bg-gray-300"
        >
          Run
        </button>
        {!chosen && <p className="mt-2 text-sm text-gray-500">Choose a province and crop to run the simulation.</p>}
      </section>

      {running && <p>Running the simulation (this takes a few seconds)...</p>}
      {!running && current?.error && <p className="text-red-600">Could not run the simulation: {current.error}</p>}
      {!running && current?.simulation && <SimulationResults simulation={current.simulation} />}
    </div>
  )
}

export function SimulationResults({ simulation }: { simulation: Simulation }) {
  return (
    <div className="space-y-6">
      {simulation.irrigated_share !== null && (
        <p>Share of {simulation.province} palay farmland that is irrigated: {(simulation.irrigated_share * 100).toFixed(1)}%</p>
      )}
      {simulation.quarters.map((quarter) => <QuarterResult key={quarter.quarter} quarter={quarter} />)}
      <section className="rounded-lg bg-white p-6 shadow-sm">
        <h2 className="text-lg font-semibold">Assumptions</h2>
        <ul className="mt-2 list-disc pl-6">
          {simulation.assumptions.map((item) => (
            <li key={item.name}>
              {assumptionNames[item.name] ?? item.name}: {item.value} ({item.note})
            </li>
          ))}
        </ul>
        <p className="mt-4 font-medium">{simulation.disclaimer}</p>
      </section>
    </div>
  )
}

function QuarterResult({ quarter }: { quarter: SimulationQuarter }) {
  return (
    <section className="rounded-lg bg-white p-6 shadow-sm">
      <h2 className="flex items-center gap-2 text-lg font-semibold">
        {quarter.quarter}
        <span className="inline-block h-4 w-4 rounded-full" style={{ backgroundColor: colourInfo[quarter.colour].hex }} />
        <span className="text-sm font-normal text-gray-500">Rain: {quarter.rain_pct.toFixed(1)}% of normal</span>
      </h2>
      {quarter.without && quarter.with && (
        <div className="mt-3 grid gap-6 md:grid-cols-2">
          <Outcome title="Without policies" outcome={quarter.without} />
          <Outcome title="With policies" outcome={quarter.with}>
            <p className="mt-2 text-sm text-gray-500">
              Pumps given: {quarter.with.pumps_given}. Farmers switched: {quarter.with.switched}.
            </p>
          </Outcome>
        </div>
      )}
      {/* When enough_data is false the back end sends no outcomes, and the notes say why. */}
      {quarter.notes.length > 0 && (
        <ul className="mt-3 list-disc pl-6 text-sm text-gray-600">
          {quarter.notes.map((note) => <li key={note}>{note}</li>)}
        </ul>
      )}
    </section>
  )
}

function Outcome({ title, outcome, children }: { title: string; outcome: SimulationOutcome; children?: ReactNode }) {
  return (
    <div>
      <h3 className="font-medium">{title}</h3>
      <p className="text-2xl font-semibold">{signedPercent(outcome.avg_yield_change_pct)} average yield</p>
      <table className="mt-2 w-full text-left text-sm">
        <thead className="border-b text-gray-500">
          <tr>
            <th className="py-1">Group</th>
            <th>Farmers</th>
            <th>Yield change</th>
            <th>Yield (t/ha)</th>
          </tr>
        </thead>
        <tbody>
          {outcome.groups.map((group) => (
            <tr key={group.group} className="border-b last:border-0">
              <td className="py-1">{group.group}</td>
              <td>{group.farmers}</td>
              <td>{signedPercent(group.yield_change_pct)}</td>
              <td>{group.yield_t_per_ha === null ? '-' : group.yield_t_per_ha.toFixed(2)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {children}
    </div>
  )
}

export default SimulationPage
