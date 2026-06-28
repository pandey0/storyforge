'use client'
import { useState } from 'react'
import { useRouter } from 'next/navigation'
import Link from 'next/link'
import { api, ProfileCreateBody } from '@/lib/api'

const INPUT = 'w-full bg-[#111] border border-[#333] rounded-lg px-3 py-2 text-sm text-[#e0e0e0] placeholder-[#555] focus:outline-none focus:border-[#3b82f6]'
const LABEL = 'block text-xs text-[#888] mb-1'
const SECTION = 'flex flex-col gap-2'

function toSlug(s: string) {
  return s.toLowerCase().replace(/\s+/g, '_').replace(/[^a-z0-9_]/g, '').slice(0, 50)
}

export default function NewProfilePage() {
  const router = useRouter()
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  const [name, setName] = useState('')
  const [language, setLanguage] = useState('hi')
  const [voicePrompt, setVoicePrompt] = useState('')
  const [sections, setSections] = useState<string[]>([''])
  const [minWords, setMinWords] = useState(4000)
  const [maxWords, setMaxWords] = useState(6500)
  const [caseTemplate, setCaseTemplate] = useState('')
  const [topics, setTopics] = useState<{ label: string }[]>([{ label: '' }])
  const [roles, setRoles] = useState<{ label: string; keywords: string }[]>([{ label: '', keywords: '' }])

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!name.trim() || !voicePrompt.trim()) {
      setError('Name and Voice Prompt are required')
      return
    }
    setSaving(true)
    setError('')
    try {
      const body: ProfileCreateBody = {
        name: name.trim(),
        language: language.trim() || 'hi',
        voice_system_prompt: voicePrompt.trim(),
        section_headers: sections.map(s => s.trim()).filter(Boolean),
        case_prompt_template: caseTemplate.trim(),
        word_count_range: [minWords, maxWords],
        shorts_topics: topics.filter(t => t.label.trim()).map(t => ({ slug: toSlug(t.label), label: t.label.trim() })),
        shorts_episode_prompt_template: '',
        shorts_word_range: [200, 300],
        shorts_planner_prompt: '',
        entity_roles: roles.filter(r => r.label.trim()).map(r => ({
          slug: toSlug(r.label),
          label: r.label.trim(),
          keywords: r.keywords.split(',').map(k => k.trim()).filter(Boolean),
        })),
        research_sources: [],
      }
      await api.createProfile(body)
      router.push('/settings/profiles')
    } catch (e) {
      setError(String(e))
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="p-6 max-w-2xl">
      <div className="flex items-center gap-2 text-xs text-[#555] mb-6">
        <Link href="/settings/profiles" className="hover:text-[#888]">← Profiles</Link>
        <span>/</span>
        <span className="text-[#e0e0e0]">New Profile</span>
      </div>
      <h1 className="text-xl font-semibold text-[#e0e0e0] mb-6">Create Channel Profile</h1>

      <form onSubmit={submit} className="flex flex-col gap-6">

        {/* Basic */}
        <div className="bg-[#111] rounded-xl border border-[#222] p-4 flex flex-col gap-4">
          <div className="text-xs text-[#555] uppercase tracking-wider font-medium">Basic</div>
          <div>
            <label className={LABEL}>Profile Name *</label>
            <input value={name} onChange={e => setName(e.target.value)} required
              placeholder="e.g. English Biography, Tamil Mythology" className={INPUT} />
          </div>
          <div>
            <label className={LABEL}>Language code</label>
            <input value={language} onChange={e => setLanguage(e.target.value)}
              placeholder="hi, en, ta, bn, mr, te …" className={INPUT} />
            <div className="text-[10px] text-[#555] mt-1">BCP-47 language tag used for TTS and script language</div>
          </div>
        </div>

        {/* Voice */}
        <div className="bg-[#111] rounded-xl border border-[#222] p-4 flex flex-col gap-4">
          <div className="text-xs text-[#555] uppercase tracking-wider font-medium">Voice &amp; Style Prompt *</div>
          <div>
            <label className={LABEL}>Tell the AI how to write scripts for this profile</label>
            <textarea value={voicePrompt} onChange={e => setVoicePrompt(e.target.value)} rows={8}
              placeholder={`Describe the writing voice, tone, and style.\n\nExample:\n"Write in a journalistic, warm tone. Use present tense for crime reconstruction. Always cite sources. Avoid sensationalism and tabloid language. Target educated Hindi-speaking audience aged 25-45. Use respectful language when referring to victims. Begin each section with a scene-setting sentence."`}
              className={INPUT + ' resize-none'} />
          </div>
        </div>

        {/* Sections */}
        <div className="bg-[#111] rounded-xl border border-[#222] p-4 flex flex-col gap-3">
          <div className="text-xs text-[#555] uppercase tracking-wider font-medium">Documentary Sections</div>
          <div className="text-[11px] text-[#555]">The structural sections of the longform documentary script</div>
          <div className={SECTION}>
            {sections.map((s, i) => (
              <div key={i} className="flex gap-2 items-center">
                <input value={s} onChange={e => { const n = [...sections]; n[i] = e.target.value; setSections(n) }}
                  placeholder={`Section ${i + 1} name, e.g. COLD OPEN`} className={INPUT} />
                <button type="button" onClick={() => setSections(sections.filter((_, j) => j !== i))}
                  className="text-[#555] hover:text-[#ef4444] text-sm flex-shrink-0 px-2">×</button>
              </div>
            ))}
            <button type="button" onClick={() => setSections([...sections, ''])}
              className="text-xs text-[#3b82f6] hover:text-[#60a5fa] self-start">+ Add section</button>
          </div>
          <div className="flex gap-4 mt-2">
            <div className="flex-1">
              <label className={LABEL}>Min words (longform)</label>
              <input type="number" value={minWords} onChange={e => setMinWords(+e.target.value)} className={INPUT} />
            </div>
            <div className="flex-1">
              <label className={LABEL}>Max words (longform)</label>
              <input type="number" value={maxWords} onChange={e => setMaxWords(+e.target.value)} className={INPUT} />
            </div>
          </div>
        </div>

        {/* Episode topics */}
        <div className="bg-[#111] rounded-xl border border-[#222] p-4 flex flex-col gap-3">
          <div className="text-xs text-[#555] uppercase tracking-wider font-medium">Shorts Episode Topics</div>
          <div className="text-[11px] text-[#555]">Reference topics fed to the episode planner (actual episodes are decided per case)</div>
          <div className={SECTION}>
            {topics.map((t, i) => (
              <div key={i} className="flex gap-2 items-center">
                <input value={t.label} onChange={e => { const n = [...topics]; n[i] = { label: e.target.value }; setTopics(n) }}
                  placeholder="e.g. Who was the victim?" className={INPUT} />
                <span className="text-[10px] text-[#555] flex-shrink-0 font-mono">{toSlug(t.label) || '—'}</span>
                <button type="button" onClick={() => setTopics(topics.filter((_, j) => j !== i))}
                  className="text-[#555] hover:text-[#ef4444] text-sm flex-shrink-0 px-1">×</button>
              </div>
            ))}
            <button type="button" onClick={() => setTopics([...topics, { label: '' }])}
              className="text-xs text-[#3b82f6] hover:text-[#60a5fa] self-start">+ Add topic</button>
          </div>
        </div>

        {/* Entity roles */}
        <div className="bg-[#111] rounded-xl border border-[#222] p-4 flex flex-col gap-3">
          <div className="text-xs text-[#555] uppercase tracking-wider font-medium">Entity Roles</div>
          <div className="text-[11px] text-[#555]">People roles used for character extraction and portrait generation</div>
          <div className={SECTION}>
            {roles.map((r, i) => (
              <div key={i} className="flex gap-2 items-start">
                <div className="flex-1 flex flex-col gap-1">
                  <input value={r.label} onChange={e => { const n = [...roles]; n[i] = { ...n[i], label: e.target.value }; setRoles(n) }}
                    placeholder="Role label, e.g. Protagonist" className={INPUT} />
                  <input value={r.keywords} onChange={e => { const n = [...roles]; n[i] = { ...n[i], keywords: e.target.value }; setRoles(n) }}
                    placeholder="Keywords (comma-separated): hero, main character, subject" className={INPUT} />
                </div>
                <button type="button" onClick={() => setRoles(roles.filter((_, j) => j !== i))}
                  className="text-[#555] hover:text-[#ef4444] text-sm flex-shrink-0 px-2 mt-1">×</button>
              </div>
            ))}
            <button type="button" onClick={() => setRoles([...roles, { label: '', keywords: '' }])}
              className="text-xs text-[#3b82f6] hover:text-[#60a5fa] self-start">+ Add role</button>
          </div>
        </div>

        {/* Script template */}
        <div className="bg-[#111] rounded-xl border border-[#222] p-4 flex flex-col gap-3">
          <div className="text-xs text-[#555] uppercase tracking-wider font-medium">Script Template (optional)</div>
          <textarea value={caseTemplate} onChange={e => setCaseTemplate(e.target.value)} rows={5}
            placeholder={`Optional prompt template for the script writer.\nAvailable variables: {case_name}, {location}, {year}, {subject_name}, {research_summary}, {word_count}\n\nLeave blank to use the default template.`}
            className={INPUT + ' resize-none'} />
        </div>

        {error && <div className="text-xs text-[#ef4444] px-1">{error}</div>}

        <div className="flex gap-3">
          <Link href="/settings/profiles"
            className="px-4 py-2 rounded-lg text-sm border border-[#333] text-[#888] hover:text-[#e0e0e0]">
            Cancel
          </Link>
          <button type="submit" disabled={saving}
            className="px-6 py-2 rounded-lg text-sm font-medium bg-[#3b82f6] text-white hover:bg-[#2563eb] disabled:opacity-50">
            {saving ? 'Creating...' : 'Create Profile →'}
          </button>
        </div>
      </form>
    </div>
  )
}
