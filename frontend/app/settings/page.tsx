'use client'

import Link from 'next/link'
import { useEffect, useState } from 'react'

export default function SettingsPage() {
  const KEYS = [
    { key: 'GOOGLE_API_KEY', label: 'Google AI (Gemini)', desc: 'Scripts, QA, agent' },
    { key: 'SARVAM_API_KEY', label: 'Sarvam Bulbul', desc: 'Hindi TTS' },
    { key: 'PEXELS_API_KEY', label: 'Pexels', desc: 'B-roll stock footage' },
    { key: 'PIXABAY_API_KEY', label: 'Pixabay', desc: 'B-roll fallback' },
    { key: 'OPENAI_API_KEY', label: 'OpenAI', desc: 'DALL-E thumbnails' },
    { key: 'DATABASE_URL', label: 'Database URL', desc: 'PostgreSQL connection' },
    { key: 'YOUTUBE_CLIENT_ID', label: 'YouTube OAuth', desc: 'Upload API' },
  ]

  const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'
  const [keyStatus, setKeyStatus] = useState<Record<string, boolean | null>>({})

  useEffect(() => {
    fetch(`${apiUrl}/api/settings/keys/status`)
      .then(r => r.ok ? r.json() : null)
      .then(data => { if (data) setKeyStatus(data) })
      .catch(() => {}) // graceful — endpoint may not exist yet
  }, [apiUrl])

  return (
    <div className="p-6 max-w-lg">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-xl font-semibold text-[#e0e0e0]">Settings</h1>
        <Link href="/settings/profiles" className="text-xs text-[#3b82f6] hover:text-[#60a5fa]">
          Channel Profiles →
        </Link>
      </div>
      <div className="bg-[#111] rounded-xl border border-[#222] overflow-hidden">
        <div className="px-4 py-3 border-b border-[#222] text-xs text-[#555]">
          API keys are loaded from .env file — edit it directly on the server
        </div>
        {KEYS.map(({ key, label, desc }, i) => (
          <div
            key={key}
            className="px-4 py-3 flex items-center justify-between"
            style={{ borderBottom: i < KEYS.length - 1 ? '1px solid #1a1a1a' : 'none' }}
          >
            <div>
              <div className="text-sm text-[#e0e0e0]">{label}</div>
              <div className="text-xs text-[#555]">{desc}</div>
            </div>
            <div className="flex items-center gap-2">
              {keyStatus[key] === true && <span style={{ color: '#22c55e', fontSize: '11px' }}>✓ set</span>}
              {keyStatus[key] === false && <span style={{ color: '#ef4444', fontSize: '11px' }}>✗ missing</span>}
              <code className="text-[10px] text-[#555] bg-[#1a1a1a] px-2 py-1 rounded">{key}</code>
            </div>
          </div>
        ))}
      </div>

      <div className="mt-6 bg-[#111] rounded-xl border border-[#222] p-4">
        <div className="text-sm text-[#888] mb-2">Server</div>
        <div className="text-xs text-[#555]">API: {apiUrl}</div>
        <div className="mt-2">
          <a
            href={`${apiUrl}/docs`}
            target="_blank"
            rel="noopener noreferrer"
            className="text-xs text-[#3b82f6] hover:text-[#60a5fa]"
          >
            FastAPI Swagger Docs →
          </a>
        </div>
      </div>
    </div>
  )
}
