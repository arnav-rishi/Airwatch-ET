import { useState, useRef, useEffect } from 'react'
import { api } from '../services/api'

const LANGUAGES = [
  { code: 'english', label: 'EN' },
  { code: 'hindi',   label: 'हि' },
  { code: 'tamil',   label: 'த' },
  { code: 'kannada', label: 'ಕ' },
]

const AQI_COLOR = (aqi) =>
  aqi > 300 ? '#C62828' : aqi > 200 ? '#FF5722' : aqi > 100 ? '#FFC107' : '#00C853'

const AQI_BG = (label) => ({
  Good: 'bg-green-900/30 border-green-700',
  Satisfactory: 'bg-lime-900/30 border-lime-700',
  Moderate: 'bg-yellow-900/30 border-yellow-700',
  Poor: 'bg-orange-900/30 border-orange-700',
  'Very Poor': 'bg-red-900/30 border-red-700',
  Severe: 'bg-purple-900/30 border-purple-700',
}[label] || 'bg-slate-800 border-slate-600')

export default function AdvisoryGenerator({ stations }) {
  const [selectedCity, setSelectedCity] = useState('')
  const [language, setLanguage] = useState('english')
  const [input, setInput] = useState('')
  const [messages, setMessages] = useState([])
  const [loading, setLoading] = useState(false)
  const bottomRef = useRef(null)

  // Deduplicate stations by city (keep highest-AQI per city) — must match the
  // dropdown list below so the status bar and dropdown always agree.
  const cityList = Object.values(
    stations.reduce((acc, s) => {
      if (!acc[s.city] || s.aqi > acc[s.city].aqi) acc[s.city] = s
      return acc
    }, {})
  ).sort((a, b) => b.aqi - a.aqi)

  const cityData = cityList.find(s => s.city === selectedCity)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, loading])

  const sendMessage = async (overrideText) => {
    // overrideText = string  → free-text (from suggested Qs or textarea)
    // overrideText = undefined → "Generate" button (structured advisory)
    const isGenerate = overrideText === undefined
    const text = isGenerate ? '' : (overrideText ?? input.trim())

    if (!cityData) return
    if (!isGenerate && !text) return

    const langLabel = LANGUAGES.find(l => l.code === language)?.label || 'EN'
    const userMsg = isGenerate
      ? `Generate ${langLabel} advisory for ${cityData.city}`
      : text

    setMessages(prev => [...prev, { role: 'user', content: userMsg }])
    if (!isGenerate && !overrideText) setInput('')
    setLoading(true)

    try {
      const payload = {
        city: cityData.city,
        aqi: cityData.aqi,
        aqi_category: cityData.label,
        language: isGenerate ? language : 'auto',
        user_query: text,
      }
      const result = await api.getAdvisory(payload)
      setMessages(prev => [...prev, { role: 'assistant', content: result.advisory }])
    } catch {
      setMessages(prev => [...prev, { role: 'assistant', content: '⚠️ Failed to get a response. Please try again.', error: true }])
    } finally {
      setLoading(false)
    }
  }

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      sendMessage(input.trim())
    }
  }

  const clearChat = () => setMessages([])

  return (
    <div className="max-w-2xl mx-auto flex flex-col h-full" style={{ maxHeight: 'calc(100vh - 120px)' }}>

      {/* Header */}
      <div className="flex-shrink-0 mb-4">
        <h2 className="text-2xl font-bold text-white">Citizen Health Advisory</h2>
        <p className="text-slate-400 text-sm mt-1">
          Ask in any language — English, हिंदी, தமிழ், ಕನ್ನಡ, or any Indian language
        </p>
      </div>

      {/* Controls row */}
      <div className="flex-shrink-0 flex gap-3 mb-3 flex-wrap">
        {/* City picker */}
        <select
          value={selectedCity}
          onChange={e => { setSelectedCity(e.target.value); clearChat() }}
          className="flex-1 min-w-[180px] bg-[#1a1f2e] border border-[#2d3348] rounded-lg px-3 py-2 text-white text-sm"
        >
          <option value="">— select city —</option>
          {cityList.map(s => (
            <option key={s.city} value={s.city}>
              {s.city} · AQI {s.aqi} ({s.label})
            </option>
          ))}
        </select>

        {/* Language pills */}
        <div className="flex gap-1">
          {LANGUAGES.map(l => (
            <button
              key={l.code}
              onClick={() => setLanguage(l.code)}
              className={`px-3 py-2 rounded-lg text-sm font-medium border transition-colors
                ${language === l.code
                  ? 'bg-blue-600 border-blue-500 text-white'
                  : 'bg-[#1a1f2e] border-[#2d3348] text-slate-300 hover:border-blue-500'}`}
            >
              {l.label}
            </button>
          ))}
        </div>

        {/* Generate button */}
        <button
          onClick={() => sendMessage()}
          disabled={!cityData || loading}
          className="px-4 py-2 bg-blue-600 hover:bg-blue-500 disabled:bg-[#2d3348] disabled:text-slate-500
            text-white text-sm font-medium rounded-lg transition-colors whitespace-nowrap"
        >
          Generate
        </button>
      </div>

      {/* AQI status bar */}
      {cityData && (
        <div className={`flex-shrink-0 flex items-center gap-3 rounded-lg px-4 py-2.5 mb-3 border ${AQI_BG(cityData.label)}`}>
          <div
            className="w-3 h-3 rounded-full flex-shrink-0"
            style={{ background: AQI_COLOR(cityData.aqi) }}
          />
          <span className="text-slate-200 text-sm">
            <strong className="text-white">{cityData.city}</strong>
            {' '}&mdash; AQI{' '}
            <strong style={{ color: AQI_COLOR(cityData.aqi) }}>{cityData.aqi}</strong>
            {' '}<span className="text-slate-400">({cityData.label})</span>
            <span className="text-slate-600 text-xs ml-2">· Live CPCB data</span>
          </span>
          {messages.length > 0 && (
            <button onClick={clearChat} className="ml-auto text-xs text-slate-500 hover:text-slate-300">
              Clear chat
            </button>
          )}
        </div>
      )}

      {/* Chat window */}
      <div className="flex-1 overflow-y-auto rounded-xl border border-[#2d3348] bg-[#0f1117] p-4 space-y-4 min-h-[200px]">
        {messages.length === 0 && !loading && (
          <div className="h-full flex flex-col items-center justify-center text-slate-600 text-sm text-center gap-2 py-8">
            <span className="text-3xl">🌫️</span>
            <p>
              {cityData
                ? 'Ask a health question or click Generate for a full advisory.'
                : 'Select a city above to start.'}
            </p>
            {cityData && (
              <div className="flex flex-col gap-1 mt-2 text-slate-500">
                {[
                  'Is it safe to go for a run today?',
                  'आज बाहर जाना सुरक्षित है?',
                  'இன்று குழந்தைகளை வெளியே அழைத்து செல்லலாமா?',
                ].map(q => (
                  <button
                    key={q}
                    onClick={() => sendMessage(q)}
                    className="text-xs text-blue-400 hover:text-blue-300 text-left"
                  >
                    "{q}"
                  </button>
                ))}
              </div>
            )}
          </div>
        )}

        {messages.map((msg, i) => (
          <div key={i} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
            {msg.role === 'assistant' && (
              <div className="w-7 h-7 rounded-full bg-blue-600 flex items-center justify-center text-xs mr-2 flex-shrink-0 mt-0.5">
                🌫️
              </div>
            )}
            <div
              className={`max-w-[80%] rounded-2xl px-4 py-3 text-sm leading-relaxed whitespace-pre-wrap
                ${msg.role === 'user'
                  ? 'bg-blue-600 text-white rounded-tr-sm'
                  : msg.error
                    ? 'bg-red-900/30 border border-red-700 text-red-300 rounded-tl-sm'
                    : 'bg-[#1a1f2e] border border-[#2d3348] text-slate-200 rounded-tl-sm'}`}
            >
              {msg.content}
              {msg.role === 'assistant' && !msg.error && (
                <button
                  onClick={() => navigator.clipboard.writeText(msg.content)}
                  className="block mt-2 text-xs text-slate-500 hover:text-slate-300"
                >
                  📋 Copy
                </button>
              )}
            </div>
          </div>
        ))}

        {loading && (
          <div className="flex justify-start">
            <div className="w-7 h-7 rounded-full bg-blue-600 flex items-center justify-center text-xs mr-2 flex-shrink-0">
              🌫️
            </div>
            <div className="bg-[#1a1f2e] border border-[#2d3348] rounded-2xl rounded-tl-sm px-4 py-3">
              <div className="flex gap-1 items-center">
                <span className="w-2 h-2 bg-blue-400 rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
                <span className="w-2 h-2 bg-blue-400 rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
                <span className="w-2 h-2 bg-blue-400 rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
              </div>
            </div>
          </div>
        )}

        <div ref={bottomRef} />
      </div>

      {/* Input bar */}
      <div className="flex-shrink-0 mt-3 flex gap-2">
        <textarea
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          disabled={!cityData || loading}
          placeholder={
            cityData
              ? 'Type your question in any language… (Enter to send)'
              : 'Select a city first'
          }
          rows={1}
          className="flex-1 bg-[#1a1f2e] border border-[#2d3348] rounded-xl px-4 py-3 text-white text-sm
            placeholder:text-slate-600 focus:border-blue-500 outline-none resize-none
            disabled:opacity-40"
          style={{ minHeight: '48px', maxHeight: '120px' }}
          onInput={e => {
            e.target.style.height = 'auto'
            e.target.style.height = Math.min(e.target.scrollHeight, 120) + 'px'
          }}
        />
        <button
          onClick={() => sendMessage(input.trim())}
          disabled={!cityData || !input.trim() || loading}
          className="px-4 py-3 bg-blue-600 hover:bg-blue-500 disabled:bg-[#2d3348] disabled:text-slate-500
            text-white rounded-xl transition-colors flex-shrink-0"
        >
          ↑
        </button>
      </div>
    </div>
  )
}
