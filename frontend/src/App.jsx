import { useState, useEffect } from 'react'
import MapView from './components/MapView'
import CityPanel from './components/CityPanel'
import EnforcementSidebar from './components/EnforcementSidebar'
import AdvisoryGenerator from './components/AdvisoryGenerator'
import { useAQI } from './hooks/useAQI'
import { api } from './services/api'

export default function App() {
  const { stations, loading, lastUpdated } = useAQI()
  const [selectedCity, setSelectedCity] = useState(null)
  const [cityDetail, setCityDetail] = useState(null)
  const [attribution, setAttribution] = useState(null)
  const [forecast, setForecast] = useState(null)
  const [enforcement, setEnforcement] = useState(null)
  const [enforcementLoading, setEnforcementLoading] = useState(false)
  const [activeTab, setActiveTab] = useState('map')

  const handleTabChange = (tab) => {
    setActiveTab(tab)
    if (tab === 'enforcement' && !enforcement && !enforcementLoading) {
      setEnforcementLoading(true)
      api.getEnforcement()
        .then(data => { setEnforcement(data); setEnforcementLoading(false) })
        .catch(err => { console.error(err); setEnforcementLoading(false) })
    }
  }

  const handleCityClick = async (station) => {
    setSelectedCity(station)
    setCityDetail(null)
    setAttribution(null)
    setForecast(null)

    // Step 1: fetch real city detail (includes real weather + forecast from OWM)
    let detail
    try {
      detail = await api.getCityDetail(station.city, station.lat, station.lon)
    } catch (e) {
      console.error(e)
      return
    }
    setCityDetail(detail)

    // Step 2: pass REAL weather values to attribution
    const now = new Date()
    const weather = detail.weather || {}
    api.getAttribution({
      city: station.city,
      state: station.state || '',
      aqi: station.aqi,
      pm25: detail.feed?.pm25 ?? station.pm25 ?? 0,
      hour_of_day: now.getHours(),
      day_of_week: now.toLocaleDateString('en-US', { weekday: 'long' }),
      weather_desc: weather.description || 'clear',
      wind_speed_kmh: weather.wind_speed_kmh || 0,
      humidity_pct: weather.humidity_pct || 50,
    }).then(setAttribution).catch(console.error)

    // Step 3: 24hr AQI forecast, using real history + OWM forecast
    if (detail.history?.length) {
      api.getForecast({
        city: station.city,
        current_aqi: station.aqi,
        history_24h: detail.history,
        weather_forecast: detail.weather_forecast || [],
      }).then(setForecast).catch(console.error)
    }
  }

  return (
    <div className="h-screen flex flex-col bg-[#0f1117] text-slate-200">
      <header className="flex items-center justify-between px-6 py-3 bg-[#1a1f2e] border-b border-[#2d3348]">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 bg-blue-500 rounded-lg flex items-center justify-center text-sm font-bold">🌫️</div>
          <div>
            <h1 className="text-lg font-bold text-white">AirWatch India</h1>
            <p className="text-xs text-slate-400">Urban Air Quality Intelligence Platform</p>
          </div>
        </div>
        <div className="flex gap-2">
          {['map', 'enforcement', 'advisory'].map(tab => (
            <button key={tab} onClick={() => handleTabChange(tab)}
              className={`px-4 py-1.5 rounded-lg text-sm font-medium transition-colors
                ${activeTab === tab ? 'bg-blue-600 text-white' : 'bg-[#2d3348] text-slate-300 hover:bg-[#374162]'}`}>
              {tab.charAt(0).toUpperCase() + tab.slice(1)}
            </button>
          ))}
        </div>
        <div className="text-xs text-slate-400">
          {loading
            ? 'Loading...'
            : lastUpdated
              ? `Live · ${lastUpdated.toLocaleTimeString()}`
              : 'Connecting...'}
          <span className="ml-2 inline-block w-2 h-2 rounded-full bg-green-400 animate-pulse" />
        </div>
      </header>

      <div className="flex flex-1 overflow-hidden">
        {activeTab === 'map' && (
          <>
            <div className="flex-1">
              <MapView stations={stations} onCityClick={handleCityClick} selectedCity={selectedCity} />
            </div>
            {selectedCity && (
              <div className="w-96 overflow-y-auto border-l border-[#2d3348] bg-[#1a1f2e]">
                <CityPanel city={selectedCity} detail={cityDetail} attribution={attribution}
                  forecast={forecast} onClose={() => setSelectedCity(null)} />
              </div>
            )}
          </>
        )}
        {activeTab === 'enforcement' && (
          <div className="flex-1 overflow-y-auto p-6">
            <EnforcementSidebar
              enforcement={enforcement}
              loading={enforcementLoading}
              stations={stations}
            />
          </div>
        )}
        {activeTab === 'advisory' && (
          <div className="flex-1 overflow-y-auto p-6">
            <AdvisoryGenerator stations={stations} />
          </div>
        )}
      </div>
    </div>
  )
}
