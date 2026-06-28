'use client'
import { useState } from 'react'

interface Topic {
  title: string
  snippet: string
  url: string
  source: string
  type: string
}

interface Props {
  language?: string
  onSelect: (title: string) => void
  accentColor?: string
}

const API = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

export function TopicDiscovery({ language = 'en', onSelect, accentColor = '#3b82f6' }: Props) {
  const [open, setOpen] = useState(false)
  const [q, setQ] = useState('')
  const [results, setResults] = useState<Topic[]>([])
  const [loading, setLoading] = useState(false)
  const [searched, setSearched] = useState(false)

  const search = async () => {
    setLoading(true)
    setSearched(true)
    try {
      const params = new URLSearchParams({ q, language, limit: '12' })
      const res = await fetch(`${API}/api/topics/search?${params}`)
      const data = await res.json()
      setResults(Array.isArray(data) ? data : [])
    } catch {
      setResults([])
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="rounded-xl border border-[#222] bg-[#0d0d0d] overflow-hidden">
      <button
        type="button"
        onClick={() => setOpen(o => !o)}
        className="w-full flex items-center justify-between px-4 py-3 text-left hover:bg-[#111] transition-colors"
      >
        <div className="flex items-center gap-2">
          <span className="text-sm" style={{ color: accentColor }}>🔍</span>
          <span className="text-sm font-medium text-[#e0e0e0]">Discover Topics</span>
          <span className="text-xs text-[#555]">Search web for trending ideas</span>
        </div>
        <span className="text-[#555] text-sm transition-transform" style={{ transform: open ? 'rotate(90deg)' : '' }}>›</span>
      </button>

      {open && (
        <div className="border-t border-[#1a1a1a] p-4 flex flex-col gap-3">
          <div className="flex gap-2">
            <input
              value={q}
              onChange={e => setQ(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && (e.preventDefault(), search())}
              placeholder="e.g. political scandal 2025, viral story, historical event…"
              className="flex-1 bg-[#111] border border-[#333] rounded-lg px-3 py-2 text-sm text-[#e0e0e0] placeholder-[#555] focus:outline-none focus:border-[#3b82f6]"
            />
            <button
              type="button"
              onClick={search}
              disabled={loading}
              className="px-4 py-2 rounded-lg text-sm font-medium text-white disabled:opacity-50 flex-shrink-0"
              style={{ backgroundColor: accentColor }}
            >
              {loading ? '…' : 'Search'}
            </button>
          </div>

          {loading && (
            <div className="text-xs text-[#555] text-center py-4 animate-pulse">Searching the web…</div>
          )}

          {!loading && searched && results.length === 0 && (
            <div className="text-xs text-[#555] text-center py-4">No results. Try different keywords.</div>
          )}

          {!loading && results.length > 0 && (
            <div className="flex flex-col gap-2 max-h-72 overflow-y-auto">
              {results.map((r, i) => (
                <button
                  key={i}
                  type="button"
                  onClick={() => onSelect(r.title)}
                  className="text-left rounded-lg border border-[#222] bg-[#111] p-3 hover:border-[#3b82f644] hover:bg-[#151515] transition-all group"
                >
                  <div className="flex items-start justify-between gap-2">
                    <div className="flex-1 min-w-0">
                      <div className="text-sm text-[#e0e0e0] font-medium line-clamp-2 group-hover:text-white">
                        {r.title}
                      </div>
                      {r.snippet && (
                        <div className="text-xs text-[#555] mt-0.5 line-clamp-2">{r.snippet}</div>
                      )}
                      <div className="flex items-center gap-2 mt-1">
                        <span className="text-[10px] text-[#444]">{r.source}</span>
                        {r.type === 'news' && (
                          <span className="text-[10px] px-1 rounded" style={{ background: '#1a2a1a', color: '#22c55e' }}>news</span>
                        )}
                      </div>
                    </div>
                    <span className="text-[#555] text-xs flex-shrink-0 mt-0.5 group-hover:text-[#3b82f6]">Use →</span>
                  </div>
                </button>
              ))}
            </div>
          )}

          {!loading && !searched && (
            <div className="text-xs text-[#555] text-center py-2">
              Search for any topic — news, events, controversies, historical moments
            </div>
          )}
        </div>
      )}
    </div>
  )
}
