'use client'
import { useState, useEffect } from 'react'
import { useRouter } from 'next/navigation'
import { api } from '@/lib/api'

function toSlug(name: string) {
  return name.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '').slice(0, 80)
}

export default function NewLongformCasePage() {
  const router = useRouter()
  const [form, setForm] = useState({
    name: '', slug: '', year_of_crime: '', location: '', subject_name: '', tier: '2', channel_profile_id: '',
  })
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [profiles, setProfiles] = useState<{ id: string; slug: string; name: string; language: string }[]>([])

  useEffect(() => {
    api.getProfiles().then(rows => {
      setProfiles(rows)
      if (rows.length === 1) setForm(prev => ({ ...prev, channel_profile_id: rows[0].id }))
    }).catch(() => {})
  }, [])

  const set = (k: string, v: string) => {
    setForm(prev => {
      const next = { ...prev, [k]: v }
      if (k === 'name') next.slug = toSlug(v)
      return next
    })
  }

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    setLoading(true)
    setError('')
    try {
      await api.createCase({
        name: form.name,
        slug: form.slug || undefined,
        year_of_crime: form.year_of_crime ? parseInt(form.year_of_crime) : undefined,
        location: form.location || undefined,
        subject_name: form.subject_name || undefined,
        tier: parseInt(form.tier),
        channel_profile_id: form.channel_profile_id || undefined,
      })
      router.push(`/longform/${form.slug || toSlug(form.name)}`)
    } catch (e) {
      setError(String(e))
    } finally {
      setLoading(false)
    }
  }

  const fields: Array<{ key: keyof typeof form; label: string; placeholder: string; required?: boolean }> = [
    { key: 'name', label: 'Case Name', placeholder: 'Jessica Lall Murder Case', required: true },
    { key: 'slug', label: 'Slug', placeholder: 'jessica-lall-murder-case' },
    { key: 'subject_name', label: 'Subject Name', placeholder: 'e.g. the person, product, or topic this is about' },
    { key: 'location', label: 'Location', placeholder: 'New Delhi' },
    { key: 'year_of_crime', label: 'Year', placeholder: '1999' },
  ]

  return (
    <div className="p-6 max-w-lg">
      <h1 className="text-xl font-semibold text-[#e0e0e0] mb-6">New Case — Long-form Studio</h1>
      <form onSubmit={submit} className="flex flex-col gap-4">
        {fields.map(({ key, label, placeholder, required }) => (
          <div key={key}>
            <label className="block text-xs text-[#888] mb-1">{label}</label>
            <input
              value={form[key]}
              onChange={e => set(key, e.target.value)}
              placeholder={placeholder}
              required={required}
              className="w-full bg-[#111] border border-[#333] rounded-lg px-3 py-2 text-sm text-[#e0e0e0] placeholder-[#555] focus:outline-none focus:border-[#3b82f6]"
            />
          </div>
        ))}
        <div>
          <label className="block text-xs text-[#888] mb-1">Channel Profile (niche + language)</label>
          <select
            value={form.channel_profile_id}
            onChange={e => set('channel_profile_id', e.target.value)}
            className="w-full bg-[#111] border border-[#333] rounded-lg px-3 py-2 text-sm text-[#e0e0e0] focus:outline-none focus:border-[#3b82f6]"
          >
            {profiles.map(p => (
              <option key={p.id} value={p.id}>{p.name} ({p.language})</option>
            ))}
          </select>
        </div>
        <div>
          <label className="block text-xs text-[#888] mb-1">Priority Tier</label>
          <select
            value={form.tier}
            onChange={e => set('tier', e.target.value)}
            className="w-full bg-[#111] border border-[#333] rounded-lg px-3 py-2 text-sm text-[#e0e0e0] focus:outline-none focus:border-[#3b82f6]"
          >
            <option value="1">Tier 1 — High priority</option>
            <option value="2">Tier 2 — Standard</option>
            <option value="3">Tier 3 — Low priority</option>
          </select>
        </div>
        {error && <div className="text-xs text-[#ef4444]">{error}</div>}
        <button
          type="submit"
          disabled={loading || !form.name}
          className="px-4 py-2 rounded-lg text-sm font-medium bg-[#3b82f6] text-white hover:bg-[#2563eb] transition-colors disabled:opacity-50"
        >
          {loading ? 'Creating...' : 'Create Case →'}
        </button>
      </form>
    </div>
  )
}
