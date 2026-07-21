import { useState, useEffect } from 'react'
import EnforcementMap from './EnforcementMap'

const RANK_COLORS = ['#f59e0b', '#94a3b8', '#b45309']

const CATEGORY_LABELS = {
  industry: 'Industry',
  construction: 'Construction',
  waste_burning: 'Waste site',
  diesel_fleet: 'Diesel fleet depot',
}

function upwindPhrase(alignment) {
  if (alignment == null) return { text: 'wind data unavailable', tone: 'text-slate-500' }
  if (alignment > 0.6) return { text: 'directly upwind', tone: 'text-red-400' }
  if (alignment > 0.2) return { text: 'partially upwind', tone: 'text-orange-400' }
  return { text: 'crosswind', tone: 'text-slate-400' }
}

/** The evidence behind one recommendation, laid out so it can be checked rather than trusted. */
function EvidenceBlock({ source }) {
  if (!source) return null
  const upwind = upwindPhrase(source.upwind_alignment)
  const c = source.score_components || {}

  return (
    <div className="bg-[#0f1117] rounded-lg p-3 space-y-2.5">
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="text-xs text-slate-400 mb-0.5">Target facility</div>
          <div className="text-white font-medium text-sm">{source.dispatch_label || source.name}</div>
          <div className="text-xs text-slate-500 mt-0.5">
            {CATEGORY_LABELS[source.category] || source.category}
            {!source.identifiable && ' · unnamed in register, located by coordinates'}
          </div>
        </div>
        <div className="text-right flex-shrink-0">
          <div className="text-lg font-bold text-blue-400">{source.evidence_score}</div>
          <div className="text-[10px] text-slate-500">evidence score</div>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-2 text-xs">
        <div>
          <span className="text-slate-500">Distance </span>
          <span className="text-slate-200">{source.distance_km} km {source.compass_from_hotspot}</span>
        </div>
        <div>
          <span className="text-slate-500">Wind </span>
          <span className={upwind.tone}>{upwind.text}</span>
          {source.upwind_alignment != null && (
            <span className="text-slate-600"> ({source.upwind_alignment})</span>
          )}
        </div>
      </div>

      {/* Component breakdown — the arithmetic behind the score, not a black box. */}
      <div className="space-y-1">
        {[
          ['Proximity', c.proximity],
          ['Upwind alignment', c.upwind],
          ['Category match', c.category_match],
          ['Dispatchability', c.identifiability],
          ['Hotspot severity', c.severity],
        ].filter(([, v]) => v != null).map(([label, value]) => (
          <div key={label} className="flex items-center gap-2">
            <span className="text-[10px] text-slate-500 w-28 flex-shrink-0">{label}</span>
            <div className="flex-1 h-1.5 bg-[#1a1f2e] rounded-full overflow-hidden">
              <div className="h-full bg-blue-500/70 rounded-full" style={{ width: `${value * 100}%` }} />
            </div>
            <span className="text-[10px] text-slate-400 w-7 text-right">{value}</span>
          </div>
        ))}
      </div>

      <div className="flex items-center gap-3 text-xs pt-0.5">
        <span className="text-slate-600 font-mono text-[10px]">{source.lat}, {source.lon}</span>
        {source.osm_url && (
          <a href={source.osm_url} target="_blank" rel="noreferrer"
            className="text-blue-400 hover:text-blue-300">
            View on OpenStreetMap ↗
          </a>
        )}
      </div>
    </div>
  )
}

export default function EnforcementSidebar({ enforcement, loading }) {
  const [activeCity, setActiveCity] = useState(null)
  const [selectedSourceId, setSelectedSourceId] = useState(null)

  const hotspots = enforcement?.hotspots || []
  const priorities = enforcement?.priorities || []

  // Default to the top-ranked priority's city so the map opens on the action
  // the agent actually recommends, not an arbitrary first entry.
  useEffect(() => {
    if (!priorities.length) return
    setActiveCity(prev => prev ?? priorities[0].city)
    setSelectedSourceId(prev => prev ?? priorities[0].source_id ?? null)
  }, [priorities])

  if (loading) return (
    <div className="text-center py-20 text-slate-500">
      <div className="text-3xl mb-3">⚖️</div>
      <p>Correlating hotspots against the emission source registry…</p>
      <p className="text-xs text-slate-600 mt-2">
        Attribution → geospatial correlation → enforcement narration
      </p>
    </div>
  )

  if (!enforcement) return (
    <div className="text-center py-20 text-slate-500">
      <div className="text-3xl mb-3">⚖️</div>
      <p>Click the Enforcement tab to load today's priorities.</p>
    </div>
  )

  const activeHotspot = hotspots.find(h => h.city === activeCity) || hotspots[0]

  return (
    <div className="max-w-3xl mx-auto space-y-5">
      <div>
        <h2 className="text-2xl font-bold text-white">Today's Enforcement Priorities</h2>
        <p className="text-slate-400 text-sm mt-1">
          Registered emission sources correlated against live pollution hotspots
          {enforcement.generated_at && ` — ${enforcement.generated_at}`}
        </p>

        <div className="flex flex-wrap gap-x-4 gap-y-1 mt-2 text-xs">
          {enforcement.multi_agent && (
            <span className="text-blue-400">
              Multi-agent chain: Attribution → geospatial correlation → Enforcement
            </span>
          )}
          {enforcement.registry_backed === false && (
            <span className="text-amber-400">
              ⚠ No registry sources in range — recommendations are AQI-only
            </span>
          )}
          {enforcement.response_time_seconds != null && (
            <span className="text-slate-500">
              Signal → dispatch-ready in{' '}
              <span className="text-green-400 font-medium">{enforcement.response_time_seconds}s</span>
            </span>
          )}
        </div>
      </div>

      {/* Geospatial documentation for the selected hotspot. */}
      {activeHotspot && (
        <div className="space-y-3">
          {hotspots.length > 1 && (
            <div className="flex flex-wrap gap-1.5">
              {hotspots.map(h => (
                <button
                  key={h.city}
                  onClick={() => { setActiveCity(h.city); setSelectedSourceId(null) }}
                  className={`px-3 py-1 rounded-lg text-xs font-medium transition-colors
                    ${h.city === activeHotspot.city
                      ? 'bg-blue-600 text-white'
                      : 'bg-[#1a1f2e] text-slate-400 hover:bg-[#2d3348]'}`}
                >
                  {h.city} · {h.aqi}
                  <span className="ml-1 text-[10px] opacity-70">
                    ({h.candidate_sources?.length || 0})
                  </span>
                </button>
              ))}
            </div>
          )}

          <EnforcementMap
            hotspot={activeHotspot}
            selectedSourceId={selectedSourceId}
            onSelectSource={setSelectedSourceId}
          />

          {activeHotspot.dominant_source && (
            <p className="text-xs text-slate-500">
              Attribution Agent blamed <span className="text-slate-300">{activeHotspot.dominant_source}</span> for
              {' '}{activeHotspot.city}
              {activeHotspot.wind_direction != null && (
                <> · wind from {activeHotspot.wind_direction}°, so sources on that side of the
                station are the ones physically able to reach it</>
              )}
            </p>
          )}
        </div>
      )}

      {/* Ranked actions. */}
      {priorities.map(p => {
        const hotspot = hotspots.find(h => h.city === p.city)
        const source = hotspot?.candidate_sources?.find(s => s.id === p.source_id)
        return (
          <div
            key={p.rank}
            onClick={() => { setActiveCity(p.city); setSelectedSourceId(p.source_id ?? null) }}
            className={`bg-[#1a1f2e] rounded-xl p-5 border space-y-3 cursor-pointer transition-colors
              ${p.city === activeHotspot?.city && p.source_id === selectedSourceId
                ? 'border-blue-500' : 'border-[#2d3348] hover:border-[#3d4568]'}`}
          >
            <div className="flex items-center gap-3">
              <div
                className="w-10 h-10 rounded-full flex items-center justify-center font-black text-lg flex-shrink-0"
                style={{ background: RANK_COLORS[p.rank - 1] + '33', color: RANK_COLORS[p.rank - 1] }}
              >
                #{p.rank}
              </div>
              <div className="min-w-0">
                <h3 className="font-bold text-white text-lg">{p.city}</h3>
                <p className="text-slate-400 text-sm">{p.violation_type}</p>
              </div>
              <div className="ml-auto text-right flex-shrink-0">
                <div className="text-2xl font-black text-red-400">{p.aqi_at_decision}</div>
                <div className="text-xs text-slate-400">AQI</div>
              </div>
            </div>

            <div className="bg-[#0f1117] rounded-lg p-3">
              <div className="text-slate-400 text-xs mb-1">Action</div>
              <div className="text-white font-medium text-sm">{p.action}</div>
            </div>

            {source
              ? <EvidenceBlock source={source} />
              : p.target_facility && (
                  <div className="bg-[#0f1117] rounded-lg p-3">
                    <div className="text-slate-400 text-xs mb-1">Target facility</div>
                    <div className="text-white font-medium text-sm">{p.target_facility}</div>
                    <div className="text-xs text-amber-500/80 mt-1">
                      {p.source_matched === false
                        ? 'This facility is not in the source registry — the model named it without correlated evidence, so treat it as unverified'
                        : 'Not matched to a registry entry — evidence not independently verifiable'}
                    </div>
                  </div>
                )}

            <div className="flex items-center gap-2 text-sm">
              <span className="text-slate-400">Inspectors required:</span>
              <span className="bg-blue-500/20 text-blue-300 px-2 py-0.5 rounded font-bold">
                {p.inspector_count}
              </span>
            </div>

            <div className="text-sm text-slate-300 bg-[#0f1117] rounded-lg p-3 italic">
              {p.rationale}
            </div>
          </div>
        )
      })}

      {enforcement.registry_meta?.upstream && (
        <p className="text-xs text-slate-600 text-center pt-1">
          Source registry: {enforcement.registry_meta.upstream}
          {enforcement.registry_meta.total_sources &&
            ` · ${enforcement.registry_meta.total_sources} sources`}
          <br />
          <span className="text-slate-700">{enforcement.registry_meta.caveat}</span>
        </p>
      )}
    </div>
  )
}
