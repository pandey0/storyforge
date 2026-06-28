'use client'
import { use, useState, useEffect } from 'react'
import { useRouter } from 'next/navigation'
import Link from 'next/link'
import { api, FullProfile } from '@/lib/api'

const INPUT = 'w-full bg-[#111] border border-[#333] rounded-lg px-3 py-2 text-sm text-[#e0e0e0] placeholder-[#555] focus:outline-none focus:border-[#3b82f6]'
const LABEL = 'block text-xs text-[#888] mb-1'

function toSlug(s: string) {
  return s.toLowerCase().replace(/\s+/g, '_').replace(/[^a-z0-9_]/g, '').slice(0, 50)
}

export default function EditProfilePage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = use(params)
  const router = useRouter()
  const [profile, setProfile] = useState<FullProfile | null>(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [deleting, setDeleting] = useState(false)
  const [error, setError] = useState('')
  const [msg, setMsg] = useState('')

  const [name, setName] = useState('')
  const [language, setLanguage] = useState('')
  const [voicePrompt, setVoicePrompt] = useState('')
  const [sections, setSections] = useState<string[]>([])
  const [minWords, setMinWords] = useState(4000)
  const [maxWords, setMaxWords] = useState(6500)
  const [caseTemplate, setCaseTemplate] = useState('')
  const [topics, setTopics] = useState<{ label: string }[]>([])
  const [roles, setRoles] = useState<{ label: string; keywords: string }[]>([])

  useEffect(() => {
    api.getProfile(slug)
      .then(p => {
        setProfile(p)
        setName(p.name)
        setLanguage(p.language)
        setVoicePrompt(p.voice_system_prompt)
        setSections(p.section_headers.length ? p.section_headers : [''])
        setMinWords(p.word_count_range[0] ?? 4000)
        setMaxWords(p.word_count_range[1] ?? 6500)
        setCaseTemplate(p.case_prompt_template)
        setTopics(p.shorts_topics.length ? p.shorts_topics : [{ label: '' }])
        setRoles(p.entity_roles.length
          ? p.entity_roles.map(r => ({ label: r.label, keywords: r.keywords.join(', ') }))
          : [{ label: '', keywords: '' }])
      })
      .catch(() => setError('Profile not found'))
      .finally(() => setLoading(false))
  }, [slug])

  const save = async (e: React.FormEvent) => {
    e.preventDefault()
    setSaving(true)
    setError('')
    try {
      await api.updateProfile(slug, {
        name: name.trim(),
        language: language.trim(),
        voice_system_prompt: voicePrompt.trim(),
        section_headers: sections.map(s => s.trim()).filter(Boolean),
        case_prompt_template: caseTemplate.trim(),
        word_count_range: [minWords, maxWords],
        shorts_topics: topics.filter(t => t.label.trim()).map(t => ({ slug: toSlug(t.label), label: t.label.trim() })),
        entity_roles: roles.filter(r => r.label.trim()).map(r => ({
          slug: toSlug(r.label),
          label: r.label.trim(),
          keywords: r.keywords.split(',').map(k => k.trim()).filter(Boolean),
        })),
      })
      setMsg('Saved ✓')
      setTimeout(() => setMsg(''), 3000)
    } catch (e) {
      setError(String(e))
    } finally {
      setSaving(false)
    }
  }

  const del = async () => {
    if (!window.confirm(`Delete profile "${name}"? This cannot be undone.`)) return
    setDeleting(true)
    try {
      await api.deleteProfile(slug)
      router.push('/settings/profiles')
    } catch (e) {
      setError(String(e))
      setDeleting(false)
    }
  }

  if (loading) return <div className="p-6 text-sm text-[#555]">Loading...</div>
  if (!profile && !loading) return <div className="p-6 text-sm text-[#ef4444]">{error || 'Not found'}</div>

  return (
    <div className="p-6 max-w-2xl">
      <div className="flex items-center gap-2 text-xs text-[#555] mb-6">
        <Link href="/settings/profiles" className="hover:text-[#888]">← Profiles</Link>
        <span>/</span>
        <span className="text-[#e0e0e0]">{profile?.name}</span>
      </div>
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-xl font-semibold text-[#e0e0e0]">Edit Profile</h1>
        {msg && <span className="text-sm text-[#22c55e]">{msg}</span>}
      </div>

      <form onSubmit={save} className="flex flex-col gap-6">

        <div className="bg-[#111] rounded-xl border border-[#222] p-4 flex flex-col gap-4">
          <div className="text-xs text-[#555] uppercase tracking-wider font-medium">Basic</div>
          <div>
            <label className={LABEL}>Profile Name</label>
            <input value={name} onChange={e => setName(e.target.value)} className={INPUT} />
          </div>
          <div>
            <label className={LABEL}>Language code</label>
            <input value={language} onChange={e => setLanguage(e.target.value)} placeholder="hi, en, ta…" className={INPUT} />
          </div>
          <div className="text-[10px] text-[#555]">Slug: <code className="text-[#888]">{slug}</code> (cannot be changed)</div>
        </div>

        <div className="bg-[#111] rounded-xl border border-[#222] p-4 flex flex-col gap-3">
          <div className="text-xs text-[#555] uppercase tracking-wider font-medium">Voice &amp; Style Prompt</div>
          <textarea value={voicePrompt} onChange={e => setVoicePrompt(e.target.value)} rows={8}
            className={INPUT + ' resize-none'} />
        </div>

        <div className="bg-[#111] rounded-xl border border-[#222] p-4 flex flex-col gap-3">
          <div className="text-xs text-[#555] uppercase tracking-wider font-medium">Documentary Sections</div>
          <div className="flex flex-col gap-2">
            {sections.map((s, i) => (
              <div key={i} className="flex gap-2 items-center">
                <input value={s} onChange={e => { const n = [...sections]; n[i] = e.target.value; setSections(n) }}
                  placeholder="Section name" className={INPUT} />
                <button type="button" onClick={() => setSections(sections.filter((_, j) => j !== i))}
                  className="text-[#555] hover:text-[#ef4444] text-sm px-2">×</button>
              </div>
            ))}
            <button type="button" onClick={() => setSections([...sections, ''])}
              className="text-xs text-[#3b82f6] self-start">+ Add section</button>
          </div>
          <div className="flex gap-4">
            <div className="flex-1">
              <label className={LABEL}>Min words</label>
              <input type="number" value={minWords} onChange={e => setMinWords(+e.target.value)} className={INPUT} />
            </div>
            <div className="flex-1">
              <label className={LABEL}>Max words</label>
              <input type="number" value={maxWords} onChange={e => setMaxWords(+e.target.value)} className={INPUT} />
            </div>
          </div>
        </div>

        <div className="bg-[#111] rounded-xl border border-[#222] p-4 flex flex-col gap-3">
          <div className="text-xs text-[#555] uppercase tracking-wider font-medium">Shorts Episode Topics</div>
          <div className="flex flex-col gap-2">
            {topics.map((t, i) => (
              <div key={i} className="flex gap-2 items-center">
                <input value={t.label} onChange={e => { const n = [...topics]; n[i] = { label: e.target.value }; setTopics(n) }}
                  placeholder="Topic label" className={INPUT} />
                <span className="text-[10px] text-[#555] font-mono flex-shrink-0">{toSlug(t.label) || '—'}</span>
                <button type="button" onClick={() => setTopics(topics.filter((_, j) => j !== i))}
                  className="text-[#555] hover:text-[#ef4444] text-sm px-1">×</button>
              </div>
            ))}
            <button type="button" onClick={() => setTopics([...topics, { label: '' }])}
              className="text-xs text-[#3b82f6] self-start">+ Add topic</button>
          </div>
        </div>

        <div className="bg-[#111] rounded-xl border border-[#222] p-4 flex flex-col gap-3">
          <div className="text-xs text-[#555] uppercase tracking-wider font-medium">Entity Roles</div>
          <div className="flex flex-col gap-3">
            {roles.map((r, i) => (
              <div key={i} className="flex gap-2 items-start">
                <div className="flex-1 flex flex-col gap-1">
                  <input value={r.label} onChange={e => { const n = [...roles]; n[i] = { ...n[i], label: e.target.value }; setRoles(n) }}
                    placeholder="Role label" className={INPUT} />
                  <input value={r.keywords} onChange={e => { const n = [...roles]; n[i] = { ...n[i], keywords: e.target.value }; setRoles(n) }}
                    placeholder="Keywords (comma-separated)" className={INPUT} />
                </div>
                <button type="button" onClick={() => setRoles(roles.filter((_, j) => j !== i))}
                  className="text-[#555] hover:text-[#ef4444] text-sm px-2 mt-1">×</button>
              </div>
            ))}
            <button type="button" onClick={() => setRoles([...roles, { label: '', keywords: '' }])}
              className="text-xs text-[#3b82f6] self-start">+ Add role</button>
          </div>
        </div>

        <div className="bg-[#111] rounded-xl border border-[#222] p-4 flex flex-col gap-3">
          <div className="text-xs text-[#555] uppercase tracking-wider font-medium">Script Template (optional)</div>
          <textarea value={caseTemplate} onChange={e => setCaseTemplate(e.target.value)} rows={4}
            placeholder="Optional prompt template. Variables: {case_name}, {location}, {year}, {research_summary}, {word_count}"
            className={INPUT + ' resize-none'} />
        </div>

        {error && <div className="text-xs text-[#ef4444]">{error}</div>}

        <div className="flex items-center justify-between">
          <button type="button" onClick={del} disabled={deleting}
            className="px-4 py-2 rounded-lg text-sm text-[#ef4444] border border-[#ef444433] hover:bg-[#1a0505] disabled:opacity-50">
            {deleting ? 'Deleting...' : 'Delete profile'}
          </button>
          <div className="flex gap-3">
            <Link href="/settings/profiles"
              className="px-4 py-2 rounded-lg text-sm border border-[#333] text-[#888] hover:text-[#e0e0e0]">
              Cancel
            </Link>
            <button type="submit" disabled={saving}
              className="px-6 py-2 rounded-lg text-sm font-medium bg-[#3b82f6] text-white hover:bg-[#2563eb] disabled:opacity-50">
              {saving ? 'Saving...' : 'Save Changes'}
            </button>
          </div>
        </div>
      </form>
    </div>
  )
}
