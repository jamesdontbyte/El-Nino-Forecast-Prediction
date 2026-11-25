import { useEffect, useState } from 'react'
import { getOptions } from './api'
import type { Options } from './types'

const tabs = ['Forecast', 'Impact', 'Simulation'] as const
type Tab = (typeof tabs)[number]

function App() {
  const [activeTab, setActiveTab] = useState<Tab>('Forecast')
  const [options, setOptions] = useState<Options | null>(null)
  const [optionsError, setOptionsError] = useState<string | null>(null)

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
      </header>
      <main className="p-6">
        {optionsError && <p className="text-red-600">Could not load provinces and crops: {optionsError}</p>}
        {!options && !optionsError && <p>Loading provinces and crops...</p>}
        {/* Pages are added in later tasks. */}
        <p>{activeTab} page</p>
      </main>
    </div>
  )
}

export default App
