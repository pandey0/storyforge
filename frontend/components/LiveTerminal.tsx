'use client'
import { useEffect, useRef, useState } from 'react'
import { api } from '@/lib/api'

interface Props {
  slug: string
  height?: string
}

export function LiveTerminal({ slug, height = '400px' }: Props) {
  const [lines, setLines] = useState<string[]>([])
  const [connected, setConnected] = useState(false)
  const bottomRef = useRef<HTMLDivElement>(null)
  const esRef = useRef<EventSource | null>(null)

  useEffect(() => {
    // Load tail first
    api.getLogTail(slug).then((data: { lines: string[] }) => {
      if (data.lines) setLines(data.lines.slice(-200))
    }).catch(() => {})

    // Connect SSE
    const es = new EventSource(api.logStreamUrl(slug))
    esRef.current = es
    es.onopen = () => setConnected(true)
    es.onerror = () => setConnected(false)
    es.onmessage = (e) => {
      const line = e.data as string
      if (line && line !== ': ping') {
        setLines(prev => [...prev.slice(-499), line])
      }
    }
    return () => { es.close(); setConnected(false) }
  }, [slug])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [lines])

  return (
    <div className="rounded-lg overflow-hidden border border-[#222]" style={{ height }}>
      <div className="flex items-center justify-between px-3 py-1.5 bg-[#111] border-b border-[#222]">
        <span className="text-xs font-mono text-[#888]">Pipeline Logs</span>
        <div className="flex items-center gap-1.5">
          <div
            className="w-2 h-2 rounded-full"
            style={{
              backgroundColor: connected ? '#22c55e' : '#555',
              boxShadow: connected ? '0 0 6px #22c55e' : 'none',
            }}
          />
          <span className="text-[10px] text-[#888]">{connected ? 'LIVE' : 'IDLE'}</span>
        </div>
      </div>
      <div
        className="overflow-y-auto p-3 font-mono text-xs bg-[#0a0a0a]"
        style={{ height: `calc(${height} - 36px)` }}
      >
        {lines.length === 0 ? (
          <span className="text-[#555]">No logs yet...</span>
        ) : (
          lines.map((line, i) => (
            <div
              key={i}
              className="leading-5"
              style={{
                color: line.includes('ERROR') ? '#ef4444' : line.includes('WARNING') ? '#f59e0b' : '#4ade80',
              }}
            >
              {line}
            </div>
          ))
        )}
        <div ref={bottomRef} />
      </div>
    </div>
  )
}
