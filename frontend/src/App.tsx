import { useState } from 'react'

const tabs = ['Forecast', 'Impact', 'Simulation'] as const
type Tab = (typeof tabs)[number]

function App() {
  const [activeTab, setActiveTab] = useState<Tab>('Forecast')

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
        {/* Pages are added in later tasks. */}
        <p>{activeTab} page</p>
      </main>
    </div>
  )
}

export default App
