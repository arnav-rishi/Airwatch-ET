const RANK_COLORS = ['#f59e0b', '#94a3b8', '#b45309']

export default function EnforcementSidebar({ enforcement, loading }) {
  if (loading) return (
    <div className="text-center py-20 text-slate-500">
      <div className="text-3xl mb-3">⚖️</div>
      <p>Analysing live AQI data with AI…</p>
      <p className="text-xs text-slate-600 mt-2">gpt-5-nano is reasoning — this takes ~20 seconds</p>
    </div>
  )
  if (!enforcement) return (
    <div className="text-center py-20 text-slate-500">
      <div className="text-3xl mb-3">⚖️</div>
      <p>Click the Enforcement tab to load today's priorities.</p>
    </div>
  )

  return (
    <div className="max-w-3xl mx-auto space-y-6">
      <div>
        <h2 className="text-2xl font-bold text-white">Today's Enforcement Priorities</h2>
        <p className="text-slate-400 text-sm mt-1">
          AI-generated recommendations based on real-time AQI data — {enforcement.generated_at}
        </p>
      </div>

      {enforcement.priorities?.map((p) => (
        <div key={p.rank} className="bg-[#1a1f2e] rounded-xl p-5 border border-[#2d3348] space-y-3">
          <div className="flex items-center gap-3">
            <div
              className="w-10 h-10 rounded-full flex items-center justify-center font-black text-lg"
              style={{ background: RANK_COLORS[p.rank - 1] + '33', color: RANK_COLORS[p.rank - 1] }}
            >
              #{p.rank}
            </div>
            <div>
              <h3 className="font-bold text-white text-lg">{p.city}</h3>
              <p className="text-slate-400 text-sm">{p.violation_type}</p>
            </div>
            <div className="ml-auto text-right">
              <div className="text-2xl font-black text-red-400">{p.aqi_at_decision}</div>
              <div className="text-xs text-slate-400">AQI</div>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3 text-sm">
            <div className="bg-[#0f1117] rounded-lg p-3">
              <div className="text-slate-400 text-xs mb-1">Action</div>
              <div className="text-white font-medium">{p.action}</div>
            </div>
            <div className="bg-[#0f1117] rounded-lg p-3">
              <div className="text-slate-400 text-xs mb-1">Target Zone</div>
              <div className="text-white font-medium">{p.target_zone}</div>
            </div>
          </div>

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
      ))}
    </div>
  )
}
