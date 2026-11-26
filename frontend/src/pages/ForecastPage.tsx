import { useEffect, useState } from 'react'
import { getForecast, getForecastForYear } from '../api'
import type { Climatology, EventStatus, Forecast } from '../types'

// Display names for the back end's model and status codes. An unknown model name is shown as sent.
const modelNames: Record<string, string> = {
  linear_regression: 'Linear regression',
  random_forest: 'Random forest',
  xgboost: 'XGBoost',
}
const statusNames: Record<EventStatus, string> = {
  'El Nino': 'El Niño',
  Neutral: 'Neutral',
  'La Nina': 'La Niña',
}
const monthNames = [
  'January', 'February', 'March', 'April', 'May', 'June',
  'July', 'August', 'September', 'October', 'November', 'December',
]
const hindcastSuffix = ' (hindcast)'

function ForecastPage() {
  const [yearText, setYearText] = useState('')
  // The year that was submitted; null means the live forecast. A request is sent only when it changes.
  const [year, setYear] = useState<number | null>(null)
  // Each result remembers the year it belongs to, so an old result or error never shows next to a new year.
  const [result, setResult] = useState<{ key: number | null; data?: Forecast | Climatology; error?: string } | null>(null)
  const current = result?.key === year ? result : null

  useEffect(() => {
    // The flag stops an older, slower response from overwriting the result for a newer year.
    let ignore = false
    const request = year === null ? getForecast() : getForecastForYear(year)
    request
      .then((data) => { if (!ignore) setResult({ key: year, data }) })
      .catch((caught: Error) => { if (!ignore) setResult({ key: year, error: caught.message }) })
    return () => { ignore = true }
  }, [year])

  const data = current?.data
  return (
    <div className="space-y-6">
      {/* noValidate: the back end alone judges the year, so the browser must not block any value. */}
      <form
        noValidate
        onSubmit={(event) => {
          event.preventDefault()
          // Sent as typed (even 1997.5), so the back end returns its own error text.
          setYear(Number(yearText.trim()))
        }}
        className="rounded-lg bg-white p-6 shadow-sm"
      >
        <div className="flex flex-wrap items-end gap-4">
          <label className="flex flex-col text-sm text-gray-500">
            Target year (optional)
            <input
              type="number"
              value={yearText}
              onChange={(event) => setYearText(event.target.value)}
              className="mt-1 w-40 rounded border px-3 py-2 text-base text-gray-900"
            />
          </label>
          <button
            type="submit"
            disabled={yearText.trim() === ''}
            className="rounded bg-blue-600 px-6 py-2 text-white hover:bg-blue-700 disabled:cursor-not-allowed disabled:bg-gray-300"
          >
            Show
          </button>
          <button
            type="button"
            onClick={() => { setYearText(''); setYear(null) }}
            className="rounded border px-6 py-2 hover:bg-gray-50"
          >
            Live forecast
          </button>
        </div>
      </form>

      {current?.error && <p className="text-red-600">Could not load the forecast: {current.error}</p>}
      {!current && <p>Loading forecast...</p>}
      {data && (data.mode === 'climatology' ? <ClimatologyDetails climatology={data} /> : <ForecastDetails forecast={data} />)}
    </div>
  )
}

function ClimatologyDetails({ climatology }: { climatology: Climatology }) {
  return (
    <div className="space-y-6">
      <section role="note" className="rounded-lg border-2 border-amber-400 bg-amber-50 p-6">
        <h2 className="text-xl font-semibold">Historical average, not a forecast</h2>
        <p className="mt-2 font-medium text-amber-900">{climatology.note}</p>
      </section>
      <section className="rounded-lg bg-white p-6 shadow-sm">
        <h2 className="text-lg font-semibold">ONI by month, {climatology.target_year}</h2>
        <p className="text-sm text-gray-500">
          ONI is a difference from normal, so its average is near 0 in every month. The shares of years are the useful part.
        </p>
        <table className="mt-3 w-full text-left">
          <thead className="border-b text-gray-500">
            <tr>
              <th className="py-2">Month</th>
              <th>Mean ONI</th>
              <th>El Niño (share of years)</th>
              <th>Neutral (share of years)</th>
              <th>La Niña (share of years)</th>
              <th>El Niño start (share of years)</th>
            </tr>
          </thead>
          <tbody>
            {climatology.climatology.map((row) => (
              <tr key={row.month} className="border-b last:border-0">
                <td className="py-2">{monthNames[row.month - 1]}</td>
                <td>{row.mean_oni.toFixed(2)}</td>
                {[row.el_nino_share, row.neutral_share, row.la_nina_share, row.event_start_share].map((share, index) => (
                  <td key={index}>{Math.round(share * 100)}%</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
        <p className="mt-4 text-sm text-gray-500">Model: No model (historical average)</p>
      </section>
    </div>
  )
}

// Kept apart from the fetching so it can be rendered with a fake forecast in a check.
export function ForecastDetails({ forecast }: { forecast: Forecast }) {
  const hindcast = forecast.mode === 'hindcast'
  const year = forecast.target_year
  // The back end marks hindcasts by a suffix on the model name; split it off so the name lookup still works.
  const baseModel = forecast.model_used.endsWith(hindcastSuffix)
    ? forecast.model_used.slice(0, -hindcastSuffix.length)
    : forecast.model_used
  const modelName = (modelNames[baseModel] ?? baseModel) + (baseModel !== forecast.model_used ? hindcastSuffix : '')
  return (
    <div className="space-y-6">
      {forecast.mode && (
        <section className="rounded-lg bg-white p-6 shadow-sm">
          <h2 className="text-lg font-semibold">
            {hindcast
              ? `Hindcast for ${year}: what the model would have said in March ${year}. Not a live forecast.`
              : `Forecast for ${year}`}
          </h2>
          <p className="mt-2">{forecast.note}</p>
          {hindcast && (
            <p className="mt-2 text-sm text-gray-500">
              Hindcasts look better than real forecasts were: past data is cleaner now, and the model was chosen on 2009 to 2016 data.
            </p>
          )}
        </section>
      )}
      <section className="rounded-lg bg-white p-6 shadow-sm">
        <h2 className="text-lg font-semibold">{hindcast ? `As forecast in March ${year}` : 'El Niño status'}</h2>
        {forecast.event_underway ? (
          <dl className="mt-3 grid grid-cols-[max-content_1fr] gap-x-6 gap-y-1">
            <dt className="text-gray-500">Event</dt>
            <dd className="font-medium">El Niño underway</dd>
            <dt className="text-gray-500">Started</dt>
            <dd>{forecast.start_month}</dd>
            <dt className="text-gray-500">Strength</dt>
            <dd>{forecast.strength}</dd>
            <dt className="text-gray-500">Duration</dt>
            <dd>
              {forecast.duration_months?.text}
              {forecast.duration_open_ended && (
                <span className="block text-sm text-gray-500">
                  The event is still going at the end of the forecast, so it may last longer.
                </span>
              )}
            </dd>
          </dl>
        ) : (
          <div className="mt-3">
            <p className="font-medium">No event underway</p>
            {/* start_month and strength are only set here when the forecast predicts an event. */}
            {forecast.start_month && forecast.strength ? (
              <p>Predicted El Niño: starts {forecast.start_month}, {forecast.strength}</p>
            ) : (
              <p>No El Niño is predicted in the forecast period.</p>
            )}
          </div>
        )}
        <p className="mt-4 text-sm text-gray-500">
          Model: {modelName}
        </p>
        <p className="text-sm text-gray-500">
          {forecast.era5_used
            ? `Data: ONI and ERA5 Pacific reanalysis${hindcast ? '' : '. The newest ERA5 months are an early release (ERA5T) and may still be revised.'}`
            : 'Data: ONI only (ERA5 file not built, so the ONI-only model was used)'}
        </p>
      </section>

      <section className="rounded-lg bg-white p-6 shadow-sm">
        <h2 className="text-lg font-semibold">ONI forecast</h2>
        <p className="text-sm text-gray-500">
          ONI is the ocean temperature index used to define El Niño (+0.5 or above) and La Niña (−0.5 or below).
        </p>
        <table className="mt-3 w-full text-left">
          <thead className="border-b text-gray-500">
            <tr>
              <th className="py-2">Month</th>
              <th>{hindcast ? 'Predicted ONI' : 'ONI'}</th>
              <th>Likely range</th>
              {hindcast && <th>Actual ONI (observed)</th>}
              <th>{hindcast ? 'Predicted status' : 'Status'}</th>
            </tr>
          </thead>
          <tbody>
            {forecast.forecast_series.map((row, index) => (
              <tr key={row.month} className="border-b last:border-0">
                <td className="py-2">{row.month}</td>
                <td>{row.oni.toFixed(2)}</td>
                <td>{row.lower.toFixed(2)} to {row.upper.toFixed(2)}</td>
                {hindcast && <td>{row.observed_oni == null ? 'not observed' : row.observed_oni.toFixed(2)}</td>}
                <td>{statusNames[forecast.event_status[index]]}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </div>
  )
}

export default ForecastPage
