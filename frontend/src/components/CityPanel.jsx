import { PieChart, Pie, Cell, LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer } from 'recharts'

const SOURCE_COLORS = ['#3b82f6', '#f97316', '#a855f7', '#10b981', '#94a3b8']
const AQI_COLOR = (aqi) =>
  aqi > 300 ? '#C62828' : aqi > 200 ? '#FF5722' : aqi > 100 ? '#FFC107' : '#00C853'

export default function CityPanel({ city, detail, attribution, onClose }) {
  const sources = attribution
    ? [
        { name: 'Traffic', value: attribution.traffic },
        { name: 'Industrial', value: attribution.industrial },
        { name: 'Construction', value: attribution.construction },
        { name: 'Biomass', value: attribution.biomass_burning },
        { name: 'Other', value: attribution.other },
      ]
    : []

  return (
    <div className="p-5 space-y-5">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <h2 className="text-xl font-bold text-white">{city.city}</h2>
          <p className="text-sm text-slate-400">{city.state || ''}</p>
        </div>
        <button onClick={onClose} className="text-slate-400 hover:text-white text-xl leading-none">×</button>
      </div>

      {/* AQI Badge */}
      <div
        className="rounded-xl p-4 text-center"
        style={{ background: AQI_COLOR(city.aqi) + '22', border: `1px solid ${AQI_COLOR(city.aqi)}44` }}
      >
        <div className="text-5xl font-black" style={{ color: AQI_COLOR(city.aqi) }}>
          {city.aqi}
        </div>
        <div className="text-sm font-medium text-slate-300 mt-1">{city.label}</div>
        <div className="text-xs text-slate-400 mt-1">
          PM2.5: {city.pm25 ? `${city.pm25} μg/m³` : 'See live readings below'}
        </div>
      </div>

      {/* Source Attribution */}
      {attribution ? (
        <div>
          <h3 className="text-sm font-semibold text-slate-300 mb-3">Pollution Sources</h3>
          <div className="flex items-center gap-4">
            <PieChart width={120} height={120}>
              <Pie data={sources} cx={55} cy={55} innerRadius={30} outerRadius={55} dataKey="value">
                {sources.map((_, i) => <Cell key={i} fill={SOURCE_COLORS[i]} />)}
              </Pie>
            </PieChart>
            <div className="space-y-1.5 flex-1">
              {sources.map((s, i) => (
                <div key={i} className="flex items-center gap-2 text-xs">
                  <div className="w-3 h-3 rounded-full flex-shrink-0" style={{ background: SOURCE_COLORS[i] }} />
                  <span className="text-slate-300 flex-1">{s.name}</span>
                  <span className="font-bold text-white">{s.value}%</span>
                </div>
              ))}
            </div>
          </div>
          {attribution.reasoning && (
            <p className="text-xs text-slate-400 mt-2 italic">{attribution.reasoning}</p>
          )}
        </div>
      ) : (
        <div className="text-center py-4 text-slate-500 text-sm">Analysing sources...</div>
      )}

      {/* 24hr Trend */}
      {detail?.history?.length > 0 && (
        <div>
          <h3 className="text-sm font-semibold text-slate-300 mb-3">24hr AQI Trend</h3>
          <ResponsiveContainer width="100%" height={100}>
            <LineChart data={detail.history}>
              <XAxis dataKey="hour" tick={{ fontSize: 9, fill: '#94a3b8' }} interval={5} />
              <YAxis domain={['auto', 'auto']} tick={{ fontSize: 9, fill: '#94a3b8' }} width={30} />
              <Tooltip
                contentStyle={{ background: '#1a1f2e', border: '1px solid #2d3348', fontSize: 11 }}
                labelStyle={{ color: '#94a3b8' }}
              />
              <Line
                type="monotone"
                dataKey="aqi"
                stroke={AQI_COLOR(city.aqi)}
                strokeWidth={2}
                dot={false}
              />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* Real Multi-Pollutant Breakdown from WAQI feed */}
      {detail?.feed && (
        <div>
          <h3 className="text-sm font-semibold text-slate-300 mb-2">Live Pollutant Readings</h3>
          <div className="grid grid-cols-2 gap-2">
            {[
              { key: 'pm25', label: 'PM2.5', unit: 'μg/m³', limit: 60 },
              { key: 'pm10', label: 'PM10',  unit: 'μg/m³', limit: 100 },
              { key: 'no2',  label: 'NO₂',   unit: 'μg/m³', limit: 80 },
              { key: 'o3',   label: 'O₃',    unit: 'μg/m³', limit: 100 },
            ].map(({ key, label, unit, limit }) => {
              const val = detail.feed[key]
              if (!val) return null
              const over = val > limit
              return (
                <div key={key} className="bg-[#0f1117] rounded-lg p-2.5">
                  <div className="text-xs text-slate-400">{label}</div>
                  <div className={`text-lg font-bold ${over ? 'text-orange-400' : 'text-green-400'}`}>
                    {val.toFixed(1)}
                  </div>
                  <div className="text-xs text-slate-500">{unit}</div>
                </div>
              )
            })}
          </div>
          <p className="text-xs text-slate-500 mt-1.5">
            Source: CPCB via WAQI · Updated: {detail.feed.updated_at || 'recently'}
          </p>
        </div>
      )}

      {/* Weather Context */}
      {detail?.weather && (
        <div className="bg-[#0f1117] rounded-lg p-3 text-xs text-slate-400 grid grid-cols-2 gap-2">
          <span>🌡 {detail.weather.temp_c}°C</span>
          <span>💧 {detail.weather.humidity_pct}% humidity</span>
          <span>💨 {detail.weather.wind_speed_kmh} km/h wind</span>
          <span>👁 {detail.weather.visibility_km} km visibility</span>
        </div>
      )}

      <div className="text-xs text-slate-600 text-center pt-1">
        AQI: CPCB India scale · Pollutants: WAQI live feed · Weather: OpenWeatherMap
      </div>
    </div>
  )
}
