import { useEffect, useState } from 'react'
import { getOptions } from './api'
import ForecastPage from './pages/ForecastPage'
import ImpactPage from './pages/ImpactPage'
import type { Options } from './types'

const tabs = ['Forecast', 'Impact', 'Simulation'] as const
type Tab = (typeof tabs)[number]

function App() {
  const [activeTab, setActiveTab] = useState<Tab>('Forecast')
  const [options, setOptions] = useState<Options | null>(null)
  const [optionsError, setOptionsError] = useState<string | null>(null)
  // Shared by the Impact and Simulation tabs. An empty string means nothing is chosen yet.
  const [province, setProvince] = useState('')
  const [crop, setCrop] = useState('')

  useEffect(() => {
    // In development, StrictMode runs effects twice. The flag stops the first call from setting state.
    let ignore = false
    getOptions()
      .then((result) => { if (!ignore) setOptions(result) })
      .catch((error: Error) => { if (!ignore) setOptionsError(error.message) })
    return () => { ignore = true }
  }, [])

  return (
    <div className="min-h-screen bg-gray-50 text-gray-900">
      <header className="border-b bg-white px-6 py-4">
        <div className="mx-auto max-w-5xl">
          <h1 className="text-xl font-semibold">El Niño Impact on Philippine Agriculture</h1>
          <nav className="mt-3 flex gap-2">
            {tabs.map((tab) => (
              <button
                key={tab}
                onClick={() => setActiveTab(tab)}
                className={`rounded px-4 py-2 ${
                  tab === activeTab ? 'bg-blue-600 text-white' : 'bg-gray-100 hover:bg-gray-200'
                }`}
              >
                {tab}
              </button>
            ))}
          </nav>
        </div>
      </header>
      <main className="mx-auto max-w-5xl p-6">
        {optionsError && <p className="text-red-600">Could not load provinces and crops: {optionsError}</p>}
        {!options && !optionsError && <p>Loading provinces and crops...</p>}
        {activeTab === 'Forecast' && <ForecastPage />}
        {activeTab === 'Impact' && options && (
          <ImpactPage
            options={options}
            province={province}
            crop={crop}
            onProvinceChange={setProvince}
            onCropChange={setCrop}
          />
        )}
        {/* The Simulation page is added in task 6. */}
        {activeTab === 'Simulation' && <p>Simulation page</p>}
      </main>
    </div>
  )
}

export default App
