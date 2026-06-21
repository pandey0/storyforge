'use client'
import { useEffect, useMemo, useState } from 'react'
import { Timeline } from '@xzdarcy/react-timeline-editor'
import type { TimelineRow, TimelineAction } from '@xzdarcy/timeline-engine'
import '@xzdarcy/react-timeline-editor/dist/react-timeline-editor.css'
import { api, EDL, EDLSegment } from '@/lib/api'
import { useCaseFiles, useCharacters } from '@/lib/swr-hooks'

const ACCENT: Record<'longform' | 'shorts', string> = {
  longform: '#3b82f6',
  shorts: '#22c55e',
}

function formatTime(sec: number): string {
  const m = Math.floor(sec / 60)
  const s = Math.floor(sec % 60)
  return `${m}:${s.toString().padStart(2, '0')}`
}

function basename(p: string): string {
  return p.split('/').pop() ?? p
}

function sourceLabel(seg: EDLSegment): string {
  if (seg.source_type === 'auto' || !seg.source_path) return 'Auto'
  if (seg.source_type === 'broll') return `B-roll clip: ${basename(seg.source_path)}`
  if (seg.source_type === 'character_photo') return `Character photo: ${basename(seg.source_path)}`
  return `Scene image: ${basename(seg.source_path)}`
}

function badgeColor(seg: EDLSegment, accent: string): string {
  return seg.source_type === 'auto' ? '#666' : accent
}

export function EditDecisionListEditor({
  slug,
  track,
  topic,
}: {
  slug: string
  track: 'longform' | 'shorts'
  topic?: string
}) {
  const accent = ACCENT[track]
  const { files } = useCaseFiles(slug)
  const { characters } = useCharacters(slug)
  const [edl, setEdl] = useState<EDL | null>(null)
  const [loadedKey, setLoadedKey] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  const [msg, setMsg] = useState<{ text: string; ok: boolean } | null>(null)

  const requestKey = `${slug}:${track}:${topic ?? ''}`
  const loading = loadedKey !== requestKey

  useEffect(() => {
    let cancelled = false
    api.getEdl(slug, track, topic)
      .then(data => { if (!cancelled) setEdl(data) })
      .catch(e => { if (!cancelled) setMsg({ text: String(e), ok: false }) })
      .finally(() => { if (!cancelled) setLoadedKey(requestKey) })
    return () => { cancelled = true }
  }, [slug, track, topic, requestKey])

  const filesMap = files as Record<string, unknown> | undefined
  const brollOptions = useMemo(() => {
    const key = track === 'longform' ? 'broll_clips' : 'shorts_episodes'
    return (filesMap?.[key] as string[] | undefined) ?? []
  }, [filesMap, track])
  const characterOptions = useMemo(
    () => (characters ?? []).filter(c => !!c.image_path),
    [characters]
  )

  const timelineData: TimelineRow[] = useMemo(() => {
    if (!edl) return []
    const actions: TimelineAction[] = edl.segments.map(seg => ({
      id: seg.segment_id,
      start: seg.start,
      end: seg.end,
      effectId: seg.source_type,
      selected: false,
      flexible: false,
      movable: false,
    }))
    return [{ id: 'segments', actions }]
  }, [edl])

  const timelineEffects = useMemo(() => {
    return {
      auto: { id: 'auto', name: 'Auto' },
      broll: { id: 'broll', name: 'B-roll' },
      character_photo: { id: 'character_photo', name: 'Character photo' },
      scene_image: { id: 'scene_image', name: 'Scene image' },
    }
  }, [])

  function updateSegment(segmentId: string, source_type: EDLSegment['source_type'], source_path: string | null) {
    setEdl(prev => {
      if (!prev) return prev
      return {
        ...prev,
        segments: prev.segments.map(s =>
          s.segment_id === segmentId ? { ...s, source_type, source_path } : s
        ),
      }
    })
  }

  function handleSelectChange(seg: EDLSegment, value: string) {
    if (value === 'auto') {
      updateSegment(seg.segment_id, 'auto', null)
      return
    }
    const [kind, rest] = value.split('::')
    if (kind === 'broll') {
      const relDir = track === 'longform' ? 'broll' : 'shorts'
      updateSegment(seg.segment_id, 'broll', `${relDir}/${rest}`)
    } else if (kind === 'character') {
      const character = characterOptions.find(c => c.id === rest)
      if (character?.image_path) {
        updateSegment(seg.segment_id, 'character_photo', `characters/${basename(character.image_path)}`)
      }
    }
  }

  function currentSelectValue(seg: EDLSegment): string {
    if (seg.source_type === 'auto' || !seg.source_path) return 'auto'
    if (seg.source_type === 'broll') return `broll::${basename(seg.source_path)}`
    if (seg.source_type === 'character_photo') {
      const match = characterOptions.find(c => c.image_path && basename(c.image_path) === basename(seg.source_path ?? ''))
      return match ? `character::${match.id}` : 'auto'
    }
    return 'auto'
  }

  async function handleSave() {
    if (!edl) return
    setSaving(true)
    setMsg(null)
    try {
      await api.saveEdl(slug, edl)
      setMsg({ text: 'Overrides saved.', ok: true })
    } catch (e) {
      setMsg({ text: String(e), ok: false })
    } finally {
      setSaving(false)
    }
  }

  if (loading) {
    return <div className="text-xs text-[#555] py-4">Loading edit decision list...</div>
  }

  if (!edl || edl.segments.length === 0) {
    return <div className="text-xs text-[#555] py-4">No segments available yet — run the script/TTS step first.</div>
  }

  return (
    <div>
      {timelineData[0]?.actions.length > 0 && (
        <div className="mb-4 rounded-lg overflow-hidden border border-[#1e1e1e]" style={{ background: '#0a0a0a' }}>
          <Timeline
            editorData={timelineData}
            effects={timelineEffects}
            style={{ width: '100%', height: '64px' }}
            autoScroll
            disableDrag
            getActionRender={(action) => {
              const seg = edl.segments.find(s => s.segment_id === action.id)
              const color = seg ? badgeColor(seg, accent) : '#666'
              return (
                <div
                  className="w-full h-full flex items-center px-2 text-[10px] truncate rounded"
                  style={{ backgroundColor: `${color}33`, border: `1px solid ${color}66`, color }}
                  title={seg ? sourceLabel(seg) : ''}
                >
                  {seg?.section ?? action.id}
                </div>
              )
            }}
          />
        </div>
      )}

      <div className="rounded-lg border border-[#1e1e1e] divide-y divide-[#1e1e1e] max-h-[420px] overflow-y-auto">
        {edl.segments.map(seg => (
          <div key={seg.segment_id} className="flex items-center gap-3 px-3 py-2.5">
            <div className="text-[11px] text-[#888] font-mono flex-shrink-0 w-20">
              {formatTime(seg.start)}–{formatTime(seg.end)}
            </div>
            <div className="text-[11px] text-[#666] flex-1 min-w-0 truncate">
              {seg.section ?? `Segment ${seg.segment_id}`}
            </div>
            <span
              className="text-[9px] px-1.5 py-0.5 rounded-full flex-shrink-0"
              style={{
                backgroundColor: `${badgeColor(seg, accent)}22`,
                color: badgeColor(seg, accent),
              }}
            >
              {seg.source_type}
            </span>
            <select
              value={currentSelectValue(seg)}
              onChange={e => handleSelectChange(seg, e.target.value)}
              className="text-xs rounded-md px-2 py-1 flex-shrink-0"
              style={{ backgroundColor: '#111', border: '1px solid #222', color: '#e0e0e0', maxWidth: '220px' }}
            >
              <option value="auto">Auto</option>
              {brollOptions.map(f => (
                <option key={f} value={`broll::${f}`}>B-roll clip: {f}</option>
              ))}
              {characterOptions.map(c => (
                <option key={c.id} value={`character::${c.id}`}>Character photo: {c.name}</option>
              ))}
            </select>
            {seg.source_type !== 'auto' && (
              <button
                onClick={() => updateSegment(seg.segment_id, 'auto', null)}
                className="text-[10px] px-2 py-1 rounded-md flex-shrink-0 transition-colors"
                style={{ border: '1px solid #2a2a2a', color: '#555' }}
              >
                Reset
              </button>
            )}
          </div>
        ))}
      </div>

      <div className="flex items-center gap-3 mt-3">
        <button
          onClick={handleSave}
          disabled={saving}
          className="px-3 py-1.5 rounded-lg text-xs font-medium transition-all"
          style={{
            backgroundColor: saving ? `${accent}22` : 'transparent',
            color: accent,
            border: `1px solid ${accent}44`,
          }}
        >
          {saving ? 'Saving...' : 'Save Overrides'}
        </button>
        {msg && (
          <span className="text-xs" style={{ color: msg.ok ? '#22c55e' : '#ef4444' }}>
            {msg.text}
          </span>
        )}
      </div>
    </div>
  )
}
