'use client'

import { useEffect, useState } from 'react'
import Link from 'next/link'

interface Profile {
  id: string
  slug: string
  name: string
  language: string
}

export default function ProfilesPage() {
  const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'
  const [profiles, setProfiles] = useState<Profile[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    fetch(`${apiUrl}/api/profiles`)
      .then(r => {
        if (!r.ok) throw new Error(`${r.status} ${r.statusText}`)
        return r.json()
      })
      .then((data: Profile[]) => setProfiles(data))
      .catch(e => setError(e.message))
      .finally(() => setLoading(false))
  }, [apiUrl])

  return (
    <div className="p-6 max-w-xl">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-xl font-semibold text-[#e0e0e0]">Channel Profiles</h1>
          <p className="text-xs text-[#555] mt-1">Each profile defines a niche, language, and voice for content production.</p>
        </div>
        <div className="flex items-center gap-3">
          <Link href="/settings" className="text-xs text-[#555] hover:text-[#888]">← Settings</Link>
          <Link href="/settings/profiles/new"
            className="px-4 py-1.5 rounded-lg text-sm font-medium bg-[#3b82f6] text-white hover:bg-[#2563eb]">
            + New Profile
          </Link>
        </div>
      </div>

      {loading && <div className="text-sm text-[#555] py-4">Loading profiles…</div>}

      {error && (
        <div className="bg-[#1a0a0a] border border-[#3b1010] rounded-xl p-3 text-xs text-[#ef4444] mb-4">
          Failed to load profiles: {error}
        </div>
      )}

      {!loading && !error && profiles.length === 0 && (
        <div className="text-sm text-[#555] py-4">No profiles yet. Create one above.</div>
      )}

      <div className="flex flex-col gap-3">
        {profiles.map((profile, i) => (
          <div key={profile.id}
            className="bg-[#111] border border-[#222] rounded-xl p-4 flex items-start justify-between">
            <div>
              <div className="flex items-center gap-2">
                <span className="text-[0.9375rem] font-medium text-[#e0e0e0]">{profile.name}</span>
                {i === 0 && (
                  <span className="text-[10px] text-[#3b82f6] border border-[#1e3a5f] rounded px-1.5 py-0.5 bg-[#0c1a2e]">
                    default
                  </span>
                )}
              </div>
              <div className="mt-1 flex gap-3">
                <span className="text-xs text-[#555]">slug: <code className="text-[#666]">{profile.slug}</code></span>
                <span className="text-xs text-[#555]">lang: <code className="text-[#666]">{profile.language}</code></span>
              </div>
            </div>
            <Link href={`/settings/profiles/${profile.slug}`}
              className="text-xs text-[#3b82f6] hover:text-[#60a5fa] flex-shrink-0 ml-4">
              Edit →
            </Link>
          </div>
        ))}
      </div>
    </div>
  )
}
