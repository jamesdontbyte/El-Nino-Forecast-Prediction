import { useEffect, useState } from 'react'
import { getForecast } from '../api'
import type { EventStatus, Forecast } from '../types'

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

function ForecastPage() {
  const [forecast, setForecast] = useState<Forecast | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let ignore = false // see App.tsx: stops a cancelled effect run from setting state
    getForecast()
      .then((result) => { if (!ignore) setForecast(result) })
      .catch((caught: Error) => { if (!ignore) setError(caught.message) })
    return () => { ignore = true }
  }, [])

  if (error) return <p className="text-red-600">Could not load the forecast: {error}</p>
  if (!forecast) return <p>Loading forecast...</p>
  return <ForecastDetails forecast={forecast} />
}

// Kept apart from the fetching so it can be rendered with a fake forecast in a check.
export function ForecastDetails({ forecast }: { forecast: Forecast }) {
  return (
    <div className="space-y-6">
      <section className="rounded-lg bg-white p-6 shadow-sm">
        <h2 className="text-lg font-semibold">El Niño status</h2>
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
          Model: {modelNames[forecast.model_used] ?? forecast.model_used}
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
              <th>ONI</th>
              <th>Likely range</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            {forecast.forecast_series.map((row, index) => (
              <tr key={row.month} className="border-b last:border-0">
                <td className="py-2">{row.month}</td>
                <td>{row.oni.toFixed(2)}</td>
                <td>{row.lower.toFixed(2)} to {row.upper.toFixed(2)}</td>
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
