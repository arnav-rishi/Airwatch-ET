import { useEffect, useMemo } from 'react'
import L from 'leaflet'
import { MapContainer, TileLayer, Marker, CircleMarker, Polyline, Tooltip, Circle, useMap } from 'react-leaflet'
import { MAX_RELEVANT_KM } from '../constants/enforcement'

// CPCB severity ramp, matching MapView so a station reads the same colour on
// both maps.
const AQI_COLORS = {
  Good: '#00C853',
  Satisfactory: '#C6E03A',
  Moderate: '#FFC107',
  Poor: '#FF5722',
  'Very Poor': '#C62828',
  Severe: '#4A148C',
}

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

/**
 * Frame the map on the evidence, and fix Leaflet's zero-size initialisation.
 *
 * Two bugs this addresses, both of which showed up as "the map opens zoomed out
 * to the whole subcontinent with only the hotspot marker visible":
 *
 * 1. The Enforcement tab mounts this map inside a container that has not been
 *    laid out yet, so Leaflet measures a zero-size viewport and falls back to a
 *    world view. invalidateSize() after paint makes it re-measure.
 *
 * 2. A fixed zoom can't frame the evidence. Candidates sit anywhere from 0.7 km
 *    (Guwahati) to 6.3 km (Kolkata) out, so any single zoom level either crops
 *    the far ones or strands the near ones in an empty frame. Fitting to the
 *    actual candidate bounds means every source the recommendation rests on is
 *    on screen, which is the whole point of showing a map.
 */
function evidenceBounds(hotspot) {
  if (!hotspot || !isFinite(hotspot.lat) || !isFinite(hotspot.lon)) return null
  const points = [
    [hotspot.lat, hotspot.lon],
    ...(hotspot.candidate_sources || [])
      .filter(s => isFinite(s.lat) && isFinite(s.lon))
      .map(s => [s.lat, s.lon]),
  ]
  if (points.length < 2) return null
  return L.latLngBounds(points)
}

/** Bounds covering every hotspot — the national overview. */
function overviewBounds(hotspots) {
  const points = (hotspots || [])
    .filter(h => isFinite(h.lat) && isFinite(h.lon))
    .map(h => [h.lat, h.lon])
  if (points.length < 2) return null
  return L.latLngBounds(points)
}

function FitToEvidence({ hotspot, overview, allHotspots }) {
  const map = useMap()

  useEffect(() => {
    if (overview) {
      const bounds = overviewBounds(allHotspots)
      const apply = () => {
        map.invalidateSize({ animate: false })
        if (bounds) map.fitBounds(bounds, { padding: [50, 50], maxZoom: 7, animate: false })
      }
      const t1 = setTimeout(apply, 0)
      const t2 = setTimeout(apply, 250)
      return () => { clearTimeout(t1); clearTimeout(t2) }
    }

    if (!hotspot) return

    const bounds = evidenceBounds(hotspot)

    // Re-measure and re-frame. Done on a short timeout rather than a single
    // animation frame because invalidateSize() only queues Leaflet's internal
    // resize handling — fitting in the very next frame can still compute the
    // zoom against the stale (zero) viewport, which is what produced a
    // whole-subcontinent view. Repeated a second time because the tab's
    // container can settle a beat after the map is created.
    const apply = () => {
      map.invalidateSize({ animate: false })
      if (bounds) {
        map.fitBounds(bounds, { padding: [45, 45], maxZoom: 14, animate: false })
      } else {
        map.setView([hotspot.lat, hotspot.lon], 12, { animate: false })
      }
    }

    const t1 = setTimeout(apply, 0)
    const t2 = setTimeout(apply, 250)
    return () => { clearTimeout(t1); clearTimeout(t2) }
  }, [map, hotspot, overview, allHotspots])

  return null
}

export default function EnforcementMap({
  hotspot, selectedSourceId, onSelectSource,
  overview = false, allHotspots = [], contextStations = [], onSelectCity,
}) {
  const candidates = overview ? [] : (hotspot?.candidate_sources || [])

  // The wind vector runs *from* the upwind side *through* the station, because
  // OpenWeatherMap's wind_direction is the direction the wind blows from. Drawn
  // as a line so the viewer can see at a glance why the upwind candidates sit
  // where they do — it's the geometry the ranking is built on.
  const windLine = useMemo(() => {
    if (overview || hotspot?.wind_direction == null) return null
    const upwind = projectPoint(hotspot.lat, hotspot.lon, hotspot.wind_direction, 12)
    const downwind = projectPoint(hotspot.lat, hotspot.lon, hotspot.wind_direction + 180, 6)
    return [upwind, [hotspot.lat, hotspot.lon], downwind]
  }, [hotspot, overview])

  // Frame from the evidence at construction time, so the very first paint is
  // already correct — FitToEvidence then only has to correct for a container
  // that hadn't been laid out yet.
  const initialBounds = useMemo(
    () => (overview ? overviewBounds(allHotspots) : evidenceBounds(hotspot)),
    [hotspot, overview, allHotspots],
  )

  if (!overview && !hotspot) return null
  if (overview && !allHotspots.length) return null

  const centreOn = overview ? allHotspots[0] : hotspot

  return (
    <div className="space-y-2">
      <div className="rounded-xl overflow-hidden border border-[#2d3348]" style={{ height: 340 }}>
        <MapContainer
          key={overview ? '__overview__' : hotspot.city}
          {...(initialBounds
            ? {
                bounds: initialBounds,
                boundsOptions: { padding: [50, 50], maxZoom: overview ? 7 : 14 },
              }
            : { center: [centreOn.lat, centreOn.lon], zoom: overview ? 5 : 12 })}
          scrollWheelZoom={false}
          style={{ height: '100%', width: '100%', background: '#0f1117' }}
        >
          <FitToEvidence hotspot={hotspot} overview={overview} allHotspots={allHotspots} />
          <TileLayer
            url="https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png"
            attribution='&copy; OpenStreetMap &copy; CARTO'
          />

          {/* Every monitored city, as context behind the ranked hotspots. The
              enforcement chain only runs on the top few (each costs an LLM call),
              but showing the full network makes clear those few were selected
              from national coverage rather than being all the system watches. */}
          {overview && contextStations
            .filter(s => !allHotspots.some(h => h.city === s.city))
            .map((s, i) => (
              <CircleMarker
                key={`ctx-${s.city}-${i}`}
                center={[s.lat, s.lon]}
                radius={4}
                pathOptions={{
                  color: AQI_COLORS[s.label] || '#64748b',
                  fillColor: AQI_COLORS[s.label] || '#64748b',
                  fillOpacity: 0.55,
                  weight: 1,
                }}
              >
                <Tooltip>
                  <div className="text-sm">
                    <strong>{s.city}</strong> — AQI {s.aqi}{s.label && ` (${s.label})`}<br />
                    <span className="text-gray-400 text-xs">
                      Monitored · not in today's top {allHotspots.length}
                    </span>
                  </div>
                </Tooltip>
              </CircleMarker>
            ))}

          {/* Overview: every hotspot at once, sized by AQI, click to drill in. */}
          {overview && allHotspots.map(h => (
            <Marker
              key={h.city}
              position={[h.lat, h.lon]}
              icon={hotspotIcon(h.aqi)}
              eventHandlers={{ click: () => onSelectCity?.(h.city) }}
            >
              <Tooltip>
                <div className="text-sm">
                  <strong>{h.city}</strong> — AQI {h.aqi}{h.label && ` (${h.label})`}<br />
                  {h.candidate_sources?.length || 0} candidate source
                  {h.candidate_sources?.length === 1 ? '' : 's'}
                  {h.dominant_source && <><br />Attributed to: {h.dominant_source}</>}
                  <br /><span className="text-gray-400 text-xs">Click to inspect</span>
                </div>
              </Tooltip>
            </Marker>
          ))}

          {/* Screening radius the scorer actually uses — makes the search area explicit
              rather than leaving the viewer to guess why distant sources are absent. */}
          {!overview && (
            <Circle
              center={[hotspot.lat, hotspot.lon]}
              radius={MAX_RELEVANT_KM * 1000}
              pathOptions={{ color: '#475569', weight: 1, fill: false, dashArray: '5 6' }}
            />
          )}

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
            const isSatellite = s.source_type === 'satellite'
            const color = isSatellite ? '#ef4444' : (CATEGORY_COLORS[s.category] || '#888')
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
                  // Satellite detections are drawn dashed: they're observed
                  // thermal anomalies, not registered premises, and the map
                  // shouldn't imply the same standing for both.
                  dashArray: isSatellite ? '3 3' : undefined,
                }}
                eventHandlers={{ click: () => onSelectSource?.(s.id) }}
              >
                <Tooltip>
                  <div className="text-sm">
                    <strong>{s.dispatch_label || s.name}</strong><br />
                    {isSatellite
                      ? <>🛰 Satellite fire detection<br /></>
                      : <>{CATEGORY_LABELS[s.category] || s.category}<br /></>}
                    {s.distance_km} km {s.compass_from_hotspot} of station<br />
                    {s.upwind_alignment != null && (
                      <>Upwind alignment: {s.upwind_alignment > 0.6 ? 'directly upwind' : s.upwind_alignment > 0.2 ? 'partially upwind' : 'crosswind'} ({s.upwind_alignment})<br /></>
                    )}
                    {isSatellite && s.frp_mw != null && (
                      <>Fire radiative power: {s.frp_mw} MW · confidence {s.detection_confidence}<br /></>
                    )}
                    Evidence score: <strong>{s.evidence_score}</strong>
                  </div>
                </Tooltip>
              </CircleMarker>
            )
          })}

          {!overview && (
            <Marker position={[hotspot.lat, hotspot.lon]} icon={hotspotIcon(hotspot.aqi)}>
              <Tooltip>
                <div className="text-sm">
                  <strong>{hotspot.city}</strong> — monitoring station<br />
                  AQI {hotspot.aqi} {hotspot.label && `(${hotspot.label})`}<br />
                  {hotspot.dominant_source && <>Attributed to: {hotspot.dominant_source}</>}
                </div>
              </Tooltip>
            </Marker>
          )}
        </MapContainer>
      </div>

      {/* Legend */}
      {overview ? (
        <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-slate-400">
          <span className="flex items-center gap-1.5">
            <span className="w-3 h-3 rounded-full border" style={{ background: 'rgba(198,40,40,0.25)', borderColor: '#C62828' }} />
            Today's top {allHotspots.length} hotspots
          </span>
          {contextStations.length > 0 && (
            <span className="flex items-center gap-1.5">
              <span className="w-2 h-2 rounded-full bg-slate-500" />
              {contextStations.length} monitored cities
            </span>
          )}
          <span className="text-slate-500">Click a hotspot to see its correlated emission sources</span>
        </div>
      ) : (
      <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-slate-400">
        {Object.entries(CATEGORY_LABELS).map(([key, label]) => (
          <span key={key} className="flex items-center gap-1.5">
            <span className="w-2.5 h-2.5 rounded-full" style={{ background: CATEGORY_COLORS[key] }} />
            {label}
          </span>
        ))}
        {candidates.some(s => s.source_type === 'satellite') && (
          <span className="flex items-center gap-1.5">
            <span className="w-2.5 h-2.5 rounded-full border border-dashed" style={{ background: '#ef444488', borderColor: '#ef4444' }} />
            🛰 Satellite fire
          </span>
        )}
        <span className="flex items-center gap-1.5">
          <span className="w-4 h-0 border-t-2 border-dashed" style={{ borderColor: '#22d3ee' }} />
          Wind axis
        </span>
        <span className="flex items-center gap-1.5">
          <span className="w-4 h-0 border-t border-dashed border-slate-500" />
          {MAX_RELEVANT_KM} km screening radius
        </span>
      </div>
      )}
    </div>
  )
}
