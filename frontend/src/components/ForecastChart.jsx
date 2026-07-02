import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, ReferenceLine } from 'recharts'

const AQI_COLOR = (aqi) =>
  aqi > 300 ? '#C62828' : aqi > 200 ? '#FF5722' : aqi > 100 ? '#FFC107' : '#00C853'

export default function ForecastChart({ forecast }) {
  if (!forecast?.forecast?.length) return null

  const data = forecast.forecast.map(f => ({
    hour: f.hour,
    aqi: f.predicted_aqi,
    confidence: f.confidence,
  }))

  const peakColor = AQI_COLOR(forecast.peak_aqi || 0)

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-slate-300">24hr AQI Forecast</h3>
        <div className="text-xs text-slate-500">
          Peak: <span style={{ color: peakColor }} className="font-bold">{forecast.peak_aqi}</span>
          {' '}at {forecast.peak_hour}
        </div>
      </div>

      <ResponsiveContainer width="100%" height={120}>
        <LineChart data={data}>
          <XAxis dataKey="hour" tick={{ fontSize: 9, fill: '#94a3b8' }} />
          <YAxis domain={['auto', 'auto']} tick={{ fontSize: 9, fill: '#94a3b8' }} width={30} />
          <Tooltip
            contentStyle={{ background: '#1a1f2e', border: '1px solid #2d3348', fontSize: 11 }}
            labelStyle={{ color: '#94a3b8' }}
          />
          <ReferenceLine y={200} stroke="#FF5722" strokeDasharray="3 3" />
          <Line
            type="monotone"
            dataKey="aqi"
            stroke="#3b82f6"
            strokeWidth={2}
            dot={{ r: 3, fill: '#3b82f6' }}
          />
        </LineChart>
      </ResponsiveContainer>

      {forecast.narrative && (
        <p className="text-xs text-slate-400 italic">{forecast.narrative}</p>
      )}
    </div>
  )
}
