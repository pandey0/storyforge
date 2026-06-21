'use client'
import { useRef, useState } from 'react'
import { api, CheckpointStatus } from '@/lib/api'
import { useWordTimings, useCheckpoint } from '@/lib/swr-hooks'

const CHECKPOINT_BADGE: Record<string, { label: string; color: string; bg: string }> = {
  ai_generated: { label: 'AI Generated', color: '#888', bg: '#111' },
  human_edited: { label: 'Human Edited', color: '#3b82f6', bg: '#0a1422' },
  ai_validated: { label: 'Validated', color: '#22c55e', bg: '#071a0d' },
  ai_flagged: { label: 'Flagged', color: '#f59e0b', bg: '#1a1205' },
  human_approved: { label: 'Approved', color: '#22c55e', bg: '#071a0d' },
  human_rejected: { label: 'Rejected', color: '#ef4444', bg: '#1a0505' },
}

function CheckpointBadge({ status }: { status: CheckpointStatus }) {
  if (!status) return null
  const cfg = CHECKPOINT_BADGE[status]
  if (!cfg) return null
  return (
    <span
      className="text-[10px] px-2 py-0.5 rounded-full font-medium"
      style={{ color: cfg.color, backgroundColor: cfg.bg, border: `1px solid ${cfg.color}33` }}
    >
      {cfg.label}
    </span>
  )
}

function fmtSec(s: number): string {
  const m = Math.floor(s / 60)
  const sec = (s % 60).toFixed(1)
  return `${m}:${sec.padStart(4, '0')}`
}

/**
 * Plain list of word_timings.json segments with inline "replace this segment's
 * audio" controls + the generic checkpoint approve/reject UI. Deliberately NOT
 * a waveform/timeline editor — that's an explicit future stretch goal, not
 * in scope here. Used by both the longform "tts" step page and the shorts
 * per-episode "Audio" StepCard.
 */
export function AudioSegmentList({
  slug,
  track,
  topic,
  timingsFilename,
}: {
  slug: string
  track: 'longform' | 'shorts'
  /** Required when track === 'shorts' — the episode topic slug. */
  topic?: string
  /** Required when track === 'shorts' — e.g. "ep01_who_was_the_victim.mp3" (used to derive the _timings.json filename). */
  timingsFilename?: string
}) {
  const step = track === 'longform' ? 'tts' : 'shorts_tts'
  const tFilename = timingsFilename ? timingsFilename.replace(/\.mp3$/, '_timings.json') : undefined
  const { timings, isLoading, mutate: mutateTimings } = useWordTimings(slug, track, tFilename)
  const { checkpoint, mutate: mutateCheckpoint } = useCheckpoint(slug, step)
  const [busyIdx, setBusyIdx] = useState<number | null>(null)
  const [results, setResults] = useState<Record<number, { passed: boolean; notes: string }>>({})
  const [errors, setErrors] = useState<Record<number, string>>({})
  const [actioning, setActioning] = useState(false)
  const fileInputs = useRef<Record<number, HTMLInputElement | null>>({})

  if (isLoading) {
    return <div className="text-xs text-[#555] py-4">Loading segments…</div>
  }
  if (!timings || timings.length === 0) {
    return <div className="text-xs text-[#555] py-4">No word timings found yet — run TTS first.</div>
  }

  const handleReplace = async (segmentIdx: number, file: File) => {
    setBusyIdx(segmentIdx)
    setErrors(prev => ({ ...prev, [segmentIdx]: '' }))
    try {
      const res = await api.replaceAudioSegment(slug, segmentIdx, file, track, topic)
      setResults(prev => ({ ...prev, [segmentIdx]: res.validation }))
      await mutateTimings()
      await mutateCheckpoint()
    } catch (e) {
      setErrors(prev => ({ ...prev, [segmentIdx]: String(e) }))
    } finally {
      setBusyIdx(null)
    }
  }

  const status = checkpoint?.status ?? null
  const canApprove = status === 'ai_validated' || status === 'human_edited' || status === 'ai_flagged'

  const handleApprove = async () => {
    setActioning(true)
    try {
      await api.approveCheckpoint(slug, step)
      await mutateCheckpoint()
    } finally {
      setActioning(false)
    }
  }

  const handleReject = async () => {
    setActioning(true)
    try {
      await api.rejectCheckpoint(slug, step)
      await mutateCheckpoint()
    } finally {
      setActioning(false)
    }
  }

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center justify-between">
        <span className="text-[10px] text-[#555] uppercase tracking-wider">
          {timings.length} segment{timings.length !== 1 ? 's' : ''}
        </span>
        <CheckpointBadge status={status} />
      </div>

      <div className="flex flex-col gap-2">
        {timings.map(seg => {
          const idx = seg.segment_idx
          const result = results[idx]
          const err = errors[idx]
          return (
            <div
              key={idx}
              className="rounded-lg border border-[#1e1e1e] bg-[#0a0a0a] p-2.5 flex flex-col gap-1.5"
            >
              <div className="flex items-center justify-between gap-2">
                <div className="flex items-center gap-2 min-w-0">
                  <span className="text-[10px] text-[#555] font-mono flex-shrink-0">
                    {fmtSec(seg.start_sec)}–{fmtSec(seg.end_sec)}
                  </span>
                  {seg.section && (
                    <span className="text-[9px] px-1.5 py-0.5 rounded bg-[#1a1a1a] text-[#888] flex-shrink-0">
                      {seg.section}
                    </span>
                  )}
                </div>
                <div className="flex items-center gap-1.5 flex-shrink-0">
                  <input
                    ref={el => { fileInputs.current[idx] = el }}
                    type="file"
                    accept="audio/*"
                    className="hidden"
                    onChange={e => {
                      const file = e.target.files?.[0]
                      if (file) handleReplace(idx, file)
                      e.target.value = ''
                    }}
                  />
                  <button
                    onClick={() => fileInputs.current[idx]?.click()}
                    disabled={busyIdx === idx}
                    className="text-[10px] px-2 py-1 rounded"
                    style={{
                      backgroundColor: busyIdx === idx ? '#0d1a2e' : '#111',
                      color: busyIdx === idx ? '#3b82f6' : '#888',
                      border: '1px solid #333',
                    }}
                  >
                    {busyIdx === idx ? '⟳ Replacing…' : '↑ Replace'}
                  </button>
                </div>
              </div>
              <div className="text-[11px] text-[#aaa] truncate">{seg.text_preview}</div>
              {result && (
                <div
                  className="text-[10px]"
                  style={{ color: result.passed ? '#22c55e' : '#f59e0b' }}
                >
                  {result.passed ? 'Validation passed' : `Validation flagged: ${result.notes}`}
                </div>
              )}
              {err && <div className="text-[10px] text-[#ef4444]">{err}</div>}
            </div>
          )
        })}
      </div>

      {checkpoint?.validation_notes && (
        <div className="text-[10px] text-[#555]">Notes: {checkpoint.validation_notes}</div>
      )}

      <div className="flex gap-2 justify-end">
        {canApprove && (
          <button
            onClick={handleApprove}
            disabled={actioning}
            className="px-3 py-1.5 rounded-lg text-xs font-medium transition-colors"
            style={{ backgroundColor: '#071a0d', color: '#22c55e', border: '1px solid #22c55e33' }}
          >
            Approve
          </button>
        )}
        <button
          onClick={handleReject}
          disabled={actioning}
          className="px-3 py-1.5 rounded-lg text-xs transition-colors"
          style={{ backgroundColor: '#1a0505', color: '#ef4444', border: '1px solid #ef444433' }}
        >
          Reject
        </button>
      </div>
    </div>
  )
}
