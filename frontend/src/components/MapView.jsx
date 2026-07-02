import { MapContainer, TileLayer, CircleMarker, Tooltip } from 'react-leaflet'

const AQI_COLORS = {
  Good: '#00C853',
  Satisfactory: '#C6E03A',
  Moderate: '#FFC107',
  Poor: '#FF5722',
  'Very Poor': '#C62828',
  Severe: '#4A148C',
}

export default function MapView({ stations, onCityClick, selectedCity }) {
  return (
    <MapContainer
      center={[22.5, 82.0]}
      zoom={5}
      style={{ height: '100%', width: '100%', background: '#0f1117' }}
    >
      <TileLayer
        url="https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png"
        attribution='&copy; OpenStreetMap &copy; CARTO'
      />
      {stations.map((station, idx) => (
        <CircleMarker
          key={idx}
          center={[station.lat, station.lon]}
          radius={station.aqi > 300 ? 22 : station.aqi > 200 ? 18 : station.aqi > 100 ? 14 : 10}
          pathOptions={{
            color: AQI_COLORS[station.label] || '#888',
            fillColor: AQI_COLORS[station.label] || '#888',
            fillOpacity: selectedCity?.city === station.city ? 1.0 : 0.7,
            weight: selectedCity?.city === station.city ? 3 : 1,
          }}
          eventHandlers={{ click: () => onCityClick(station) }}
        >
          <Tooltip>
            <div className="text-sm">
              <strong>{station.city}</strong><br />
              AQI: {station.aqi} — {station.label}<br />
              PM2.5: {station.pm25 ? `${station.pm25} μg/m³` : 'See city detail'}<br />
              <span className="text-gray-400 text-xs">
                Source: {station.source === 'waqi_live' ? 'CPCB via WAQI' : station.source}
              </span>
            </div>
          </Tooltip>
        </CircleMarker>
      ))}
    </MapContainer>
  )
}
