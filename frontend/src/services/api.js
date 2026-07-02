import axios from 'axios'

// In dev, proxies through vite.config.js to localhost:8000.
// In production, set VITE_API_URL in Vercel's environment variables.
const BASE = import.meta.env.VITE_API_URL || '/api'

export const api = {
  getLiveAQI: () =>
    axios.get(`${BASE}/aqi/live`).then(r => r.data),

  getCityDetail: (city, lat, lon) =>
    axios.get(`${BASE}/aqi/city/${encodeURIComponent(city)}`, {
      params: { lat, lon }
    }).then(r => r.data),

  getAttribution: (payload) =>
    axios.post(`${BASE}/intel/attribution`, payload).then(r => r.data),

  getEnforcement: () =>
    axios.get(`${BASE}/intel/enforcement/auto`).then(r => r.data),

  getForecast: (payload) =>
    axios.post(`${BASE}/intel/forecast`, payload).then(r => r.data),

  getAdvisory: (payload) =>
    axios.post(`${BASE}/intel/advisory`, payload).then(r => r.data),
}
