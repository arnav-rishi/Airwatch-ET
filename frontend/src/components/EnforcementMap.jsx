import { useMemo } from 'react'
import L from 'leaflet'
import { MapContainer, TileLayer, Marker, CircleMarker, Polyline, Tooltip, Circle } from 'react-leaflet'
import { MAX_RELEVANT_KM } from '../constants/enforcement'

// Category palette — kept distinct from the AQI severity ramp used on the main
// map so a source marker is never mistaken for an air-quality reading.
const CATEGORY_COLORS = {
  industry: '#f97316',
  construction: '#a855f7',
  waste_burning: '#eab308',
  diesel_fleet: '#38bdf8',
}

const CATEGORY_LABELS = {
  industry: 'Industry',
  construction: 'Construction',
  waste_burning: 'Waste site',
  diesel_fleet: 'Diesel fleet depot',
}

function hotspotIcon(aqi) {
  return L.divIcon({
    html: `<div style="
      width:46px;height:46px;border-radius:50%;
      background:rgba(198,40,40,0.25);border:2px solid #C62828;
      display:flex;align-items:center;justify-content:center;
      color:#fff;font-weight:800;font-size:13px;">${aqi}</div>`,
    className: '',
    iconSize: [46, 46],
    iconAnchor: [23, 23],
  })
}

/**
 * Project a point `km` away from an origin along a compass bearing.
 * Used to draw the wind vector; good enough at city scale where the
 * flat-earth error is negligible.
 */
function projectPoint(lat, lon, bearingDeg, km) {
  const rad = (bearingDeg * Math.PI) / 180
  const dLat = (km / 111) * Math.cos(rad)
  const dLon = (km / (111 * Math.cos((lat * Math.PI) / 180))) * Math.sin(rad)
  return [lat + dLat, lon + dLon]
}

export default function EnforcementMap({ hotspot, selectedSourceId, onSelectSource }) {
  const candidates = hotspot?.candidate_sources || []

  // The wind vector runs *from* the upwind side *through* the station, because
  // OpenWeatherMap's wind_direction is the direction the wind blows from. Drawn
  // as a line so the viewer can see at a glance why the upwind candidates sit
  // where they do — it's the geometry the ranking is built on.
  const windLine = useMemo(() => {
    if (hotspot?.wind_direction == null) return null
    const upwind = projectPoint(hotspot.lat, hotspot.lon, hotspot.wind_direction, 12)
    const downwind = projectPoint(hotspot.lat, hotspot.lon, hotspot.wind_direction + 180, 6)
    return [upwind, [hotspot.lat, hotspot.lon], downwind]
  }, [hotspot])

  if (!hotspot) return null

  return (
    <div className="space-y-2">
      <div className="rounded-xl overflow-hidden border border-[#2d3348]" style={{ height: 340 }}>
        <MapContainer
          key={hotspot.city}
          center={[hotspot.lat, hotspot.lon]}
          zoom={11}
          style={{ height: '100%', width: '100%', background: '#0f1117' }}
        >
          <TileLayer
            url="https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png"
            attribution='&copy; OpenStreetMap &copy; CARTO'
          />

          {/* Screening radius the scorer actually uses — makes the search area explicit
              rather than leaving the viewer to guess why distant sources are absent. */}
          <Circle
            center={[hotspot.lat, hotspot.lon]}
            radius={MAX_RELEVANT_KM * 1000}
            pathOptions={{ color: '#475569', weight: 1, fill: false, dashArray: '5 6' }}
          />

          {windLine && (
            <Polyline
              positions={windLine}
              pathOptions={{ color: '#22d3ee', weight: 2, opacity: 0.7, dashArray: '6 5' }}
            >
              <Tooltip sticky>
                Wind from {hotspot.wind_direction}°
                {hotspot.wind_speed_kmh != null && ` at ${hotspot.wind_speed_kmh} km/h`}
                <br />
                <span className="text-xs">Sources upwind along this line can reach the station</span>
              </Tooltip>
            </Polyline>
          )}

          {/* Evidence lines from each candidate to the station. */}
          {candidates.map(s => {
            const isSelected = s.id === selectedSourceId
            return (
              <Polyline
                key={`line-${s.id}`}
                positions={[[hotspot.lat, hotspot.lon], [s.lat, s.lon]]}
                pathOptions={{
                  color: isSelected ? '#ffffff' : CATEGORY_COLORS[s.category] || '#888',
                  weight: isSelected ? 2.5 : 1,
                  opacity: isSelected ? 0.9 : 0.35,
                }}
              />
            )
          })}

          {candidates.map(s => {
            const isSelected = s.id === selectedSourceId
            const color = CATEGORY_COLORS[s.category] || '#888'
            return (
              <CircleMarker
                key={s.id}
                center={[s.lat, s.lon]}
                // Radius tracks evidence score, so the strongest candidate reads
                // as the largest mark without needing to be clicked.
                radius={6 + s.evidence_score * 10}
                pathOptions={{
                  color: isSelected ? '#ffffff' : color,
                  fillColor: color,
                  fillOpacity: isSelected ? 0.95 : 0.6,
                  weight: isSelected ? 3 : 1,
                }}
                eventHandlers={{ click: () => onSelectSource?.(s.id) }}
              >
                <Tooltip>
                  <div className="text-sm">
                    <strong>{s.dispatch_label || s.name}</strong><br />
                    {CATEGORY_LABELS[s.category] || s.category}<br />
                    {s.distance_km} km {s.compass_from_hotspot} of station<br />
                    {s.upwind_alignment != null && (
                      <>Upwind alignment: {s.upwind_alignment > 0.6 ? 'directly upwind' : s.upwind_alignment > 0.2 ? 'partially upwind' : 'crosswind'} ({s.upwind_alignment})<br /></>
                    )}
                    Evidence score: <strong>{s.evidence_score}</strong>
                  </div>
                </Tooltip>
              </CircleMarker>
            )
          })}

          <Marker position={[hotspot.lat, hotspot.lon]} icon={hotspotIcon(hotspot.aqi)}>
            <Tooltip>
              <div className="text-sm">
                <strong>{hotspot.city}</strong> — monitoring station<br />
                AQI {hotspot.aqi} {hotspot.label && `(${hotspot.label})`}<br />
                {hotspot.dominant_source && <>Attributed to: {hotspot.dominant_source}</>}
              </div>
            </Tooltip>
          </Marker>
        </MapContainer>
      </div>

      {/* Legend */}
      <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-slate-400">
        {Object.entries(CATEGORY_LABELS).map(([key, label]) => (
          <span key={key} className="flex items-center gap-1.5">
            <span className="w-2.5 h-2.5 rounded-full" style={{ background: CATEGORY_COLORS[key] }} />
            {label}
          </span>
        ))}
        <span className="flex items-center gap-1.5">
          <span className="w-4 h-0 border-t-2 border-dashed" style={{ borderColor: '#22d3ee' }} />
          Wind axis
        </span>
        <span className="flex items-center gap-1.5">
          <span className="w-4 h-0 border-t border-dashed border-slate-500" />
          {MAX_RELEVANT_KM} km screening radius
        </span>
      </div>
    </div>
  )
}
