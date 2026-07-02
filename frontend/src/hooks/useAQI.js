import { useState, useEffect, useCallback } from 'react'
import { api } from '../services/api'

export function useAQI() {
  const [stations, setStations] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [lastUpdated, setLastUpdated] = useState(null)

  const refresh = useCallback(async () => {
    try {
      setLoading(true)
      const data = await api.getLiveAQI()
      setStations(data.stations)
      setLastUpdated(new Date())
      setError(null)
    } catch (e) {
      setError('Failed to fetch AQI data')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    refresh()
    const interval = setInterval(refresh, 5 * 60 * 1000)
    return () => clearInterval(interval)
  }, [refresh])

  return { stations, loading, error, lastUpdated, refresh }
}
