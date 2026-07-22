import L from 'leaflet'
import { MapContainer, TileLayer, Marker, Tooltip } from 'react-leaflet'
import MarkerClusterGroup from 'react-leaflet-cluster'
import 'leaflet.markercluster/dist/MarkerCluster.css'
import 'leaflet.markercluster/dist/MarkerCluster.Default.css'

const AQI_COLORS = {
  Good: '#00C853',
  Satisfactory: '#C6E03A',
  Moderate: '#FFC107',
  Poor: '#FF5722',
  'Very Poor': '#C62828',
  Severe: '#4A148C',
}

function clusterIcon(cluster) {
  const children = cluster.getAllChildMarkers()
  const worst = children.reduce((acc, m) => (m.options.aqi > acc ? m.options.aqi : acc), 0)
  const color = children.find(m => m.options.aqi === worst)?.options.color || '#888'
  const count = cluster.getChildCount()
  const size = count > 15 ? 44 : count > 5 ? 38 : 32
  return L.divIcon({
    html: `<div style="
      width:${size}px;height:${size}px;border-radius:50%;
      background:${color};opacity:0.85;border:2px solid rgba(255,255,255,0.6);
      display:flex;align-items:center;justify-content:center;
      color:#0f1117;font-weight:700;font-size:13px;">${count}</div>`,
    className: '',
    iconSize: [size, size],
  })
}

function pinIcon(color, isSelected) {
  const size = isSelected ? 34 : 26
  const stroke = isSelected ? '#ffffff' : 'rgba(0,0,0,0.35)'
  const strokeWidth = isSelected ? 2 : 1
  const svg = `
    <svg width="${size}" height="${size * 1.33}" viewBox="0 0 24 32" xmlns="http://www.w3.org/2000/svg">
      <path d="M12 0C5.4 0 0 5.4 0 12c0 9 12 20 12 20s12-11 12-20c0-6.6-5.4-12-12-12z"
        fill="${color}" stroke="${stroke}" stroke-width="${strokeWidth}" />
      <circle cx="12" cy="12" r="4.5" fill="rgba(0,0,0,0.35)" />
    </svg>
  `
  return L.divIcon({
    html: svg,
    className: '',
    iconSize: [size, size * 1.33],
    iconAnchor: [size / 2, size * 1.33],
    popupAnchor: [0, -size],
  })
}

function handleClusterMouseOver(e) {
  const names = e.layer.getAllChildMarkers().map(m => m.options.city)
  e.layer.bindTooltip(names.join(', '), { sticky: true, direction: 'top', opacity: 0.95 }).openTooltip()
}

function handleClusterMouseOut(e) {
  e.layer.closeTooltip()
}

// Generously padded around the mainland — this is only a panning limit, not
// the initial framing (see center/zoom below), so it needs to comfortably
// contain that default view rather than fit India's aspect ratio exactly.
// Wide enough for border context, tight enough that Japan/Korea etc. are
// unreachable no matter how far the map is panned or zoomed out.
const INDIA_BOUNDS = [
  [0, 55],
  [45, 110],
]

export default function MapView({ stations, onCityClick, selectedCity }) {
  return (
    <MapContainer
      center={[22.5, 82.0]}
      zoom={5}
      maxBounds={INDIA_BOUNDS}
      maxBoundsViscosity={1.0}
      minZoom={5}
      style={{ height: '100%', width: '100%', background: '#0f1117' }}
    >
      <TileLayer
        url="https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png"
        attribution='&copy; OpenStreetMap &copy; CARTO'
      />
      <MarkerClusterGroup
        iconCreateFunction={clusterIcon}
        onMouseOver={handleClusterMouseOver}
        onMouseOut={handleClusterMouseOut}
        maxClusterRadius={50}
        spiderfyOnMaxZoom
        showCoverageOnHover={false}
      >
        {stations.map((station, idx) => {
          const isSelected = selectedCity?.city === station.city
          const color = AQI_COLORS[station.label] || '#888'
          return (
          <Marker
            key={idx}
            position={[station.lat, station.lon]}
            icon={pinIcon(color, isSelected)}
            city={station.city}
            aqi={station.aqi}
            color={color}
            eventHandlers={{ click: () => onCityClick(station) }}
          >
            <Tooltip>
              <div className="text-sm">
                <strong>{station.city}</strong><br />
                AQI: {station.aqi} — {station.label}<br />
                PM2.5: {station.pm25 ? `${station.pm25} μg/m³` : 'See city detail'}<br />
                <span className="text-gray-400 text-xs">
                  {station.source === 'openaq_live' ? 'Live · CPCB via OpenAQ'
                    : station.source === 'waqi_live' ? 'Live · CPCB via WAQI'
                    : 'Last-known (no live reading)'}
                  {typeof station.age_hours === 'number' &&
                    ` · ${station.age_hours < 1
                      ? '<1h' : `${Math.round(station.age_hours)}h`} ago`}
                </span>
              </div>
            </Tooltip>
          </Marker>
          )
        })}
      </MarkerClusterGroup>
    </MapContainer>
  )
}
