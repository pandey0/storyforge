'use client'
import { use, useCallback, useState } from 'react'
import Link from 'next/link'
import { api } from '@/lib/api'
import { useCase, useCaseFiles, useShortsPlan } from '@/lib/swr-hooks'
import { LiveTerminal } from '@/components/LiveTerminal'
import { SkeletonCard } from '@/components/Skeleton'
import { EditDecisionListEditor } from '@/components/EditDecisionListEditor'
import { AudioSegmentList } from '@/components/AudioSegmentList'
import { SHORTS_EPISODE_STEPS, topicFileMatch } from '@/lib/pipeline'

const ACCENT = '#22c55e'
const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

export default function ShortsEpisodePage({ params }: { params: Promise<{ slug: string; episode: string }> }) {
  const { slug, episode } = use(params)
  const { caseData, isLoading } = useCase(slug)
  const { files } = useCaseFiles(slug)
  const { plan, isLoading: planLoading } = useShortsPlan(slug)
  const filesMap = files as Record<string, unknown> | undefined
  const [running, setRunning] = useState<Record<string, boolean>>({})
  const [errors, setErrors] = useState<Record<string, string>>({})

  const topic = plan?.find(t => t.slug === episode)

  const runStep = useCallback(async (stepId: string) => {
    setRunning(prev => ({ ...prev, [stepId]: true }))
    setErrors(prev => ({ ...prev, [stepId]: '' }))
    try {
      await api.runStep(slug, stepId, episode)
    } catch (e) {
      setErrors(prev => ({ ...prev, [stepId]: String(e) }))
    } finally {
      setTimeout(() => setRunning(prev => ({ ...prev, [stepId]: false })), 1000)
    }
  }, [slug, episode])

  if (isLoading || (!topic && planLoading)) {
    return (
      <div className="p-6">
        <SkeletonCard className="h-16 mb-4" />
        <SkeletonCard className="h-96" />
      </div>
    )
  }

  if (!topic) {
    return (
      <div className="p-6">
        <div className="text-sm text-[#ef4444] mb-3">Unknown episode: {episode}</div>
        <Link href={`/shorts/${slug}`} className="text-sm" style={{ color: ACCENT }}>
          ← Back to episodes
        </Link>
      </div>
    )
  }

  if (!caseData) return <div className="p-6 text-[#ef4444]">Case not found: {slug}</div>

  const scriptFilename = topicFileMatch(filesMap?.shorts_scripts as string[] | undefined, episode)
  const audioFilename = topicFileMatch(filesMap?.shorts_audio as string[] | undefined, episode)
  const videoFilename = topicFileMatch(filesMap?.shorts_episodes as string[] | undefined, episode)

  return (
    <div className="p-6">
      {/* Breadcrumb */}
      <div className="flex items-center gap-2 text-xs text-[#555] mb-4">
        <Link href={`/shorts/${slug}`} className="hover:text-[#888] transition-colors">
          ← {caseData.name}
        </Link>
        <span>/</span>
        <span className="text-[#e0e0e0]">{topic.label}</span>
      </div>

      {/* What the planner decided for this episode — operator visibility into
          a model decision, not a black box */}
      <div className="bg-[#111] rounded-xl border border-[#222] p-4 mb-6">
        <div className="text-[10px] uppercase tracking-wider font-medium mb-2" style={{ color: ACCENT }}>
          Episode Plan
        </div>
        <div className="text-sm text-[#e0e0e0] mb-2">{topic.angle}</div>
        <div className="flex flex-wrap gap-x-6 gap-y-1 text-xs text-[#888]">
          <span>Hook: <span className="text-[#e0e0e0]">{topic.hook_text}</span></span>
          <span>B-roll query: <span className="text-[#e0e0e0]">{topic.broll_query}</span></span>
          {topic.role_hint && <span>Focus: <span className="text-[#e0e0e0]">{topic.role_hint}</span></span>}
        </div>
        <div className="text-xs text-[#555] mt-2">CTA: {topic.cta}</div>
      </div>

      <div className="flex gap-6">
        {/* Left: stepper */}
        <div className="flex-1 min-w-0 flex flex-col gap-4">
          <StepCard
            step={SHORTS_EPISODE_STEPS[0]}
            done={!!scriptFilename}
            running={!!running.shorts_script}
            error={errors.shorts_script}
            onRun={() => runStep('shorts_script')}
          >
            {scriptFilename ? (
              <ScriptPreview slug={slug} filename={scriptFilename} />
            ) : (
              <EmptyHint text="No script yet for this episode." />
            )}
          </StepCard>

          <StepCard
            step={SHORTS_EPISODE_STEPS[1]}
            done={!!audioFilename}
            running={!!running.shorts_tts}
            error={errors.shorts_tts}
            hint={!scriptFilename ? 'Run Script first' : undefined}
            onRun={() => runStep('shorts_tts')}
          >
            {audioFilename ? (
              <>
                <audio controls className="w-full" style={{ filter: 'invert(0.9) hue-rotate(180deg)' }}>
                  <source src={`${API_BASE}/files/cases/${slug}/shorts/${audioFilename}`} type="audio/mpeg" />
                </audio>
                <div className="mt-3 pt-3 border-t border-[#1e1e1e]">
                  <AudioSegmentList slug={slug} track="shorts" topic={episode} timingsFilename={audioFilename} />
                </div>
              </>
            ) : (
              <EmptyHint text="No audio yet for this episode." />
            )}
            <Link
              href={`/cases/${slug}/steps/shorts_tts?from=shorts`}
              className="text-[10px] inline-block mt-2"
              style={{ color: ACCENT }}
            >
              ⚙ Voice, pace, pitch & loudness settings →
            </Link>
          </StepCard>

          <StepCard
            step={SHORTS_EPISODE_STEPS[2]}
            done={!!videoFilename}
            running={!!running.shorts_assemble}
            error={errors.shorts_assemble}
            hint={!audioFilename ? 'Run Audio first' : undefined}
            onRun={() => runStep('shorts_assemble')}
          >
            {videoFilename ? (
              <div style={{ width: '220px', aspectRatio: '9/16', background: '#000', borderRadius: '8px', overflow: 'hidden' }}>
                <video
                  controls
                  src={`${API_BASE}/files/cases/${slug}/shorts/${videoFilename}`}
                  style={{ width: '100%', height: '100%', objectFit: 'cover' }}
                />
              </div>
            ) : (
              <EmptyHint text="No assembled episode yet." />
            )}
          </StepCard>

          <div>
            <div className="text-[10px] uppercase tracking-wider font-medium mb-1" style={{ color: ACCENT }}>
              Manual Overrides
            </div>
            <div className="text-[11px] text-[#555] mb-3">
              Optional — override which clip plays for specific segments. Leave on Auto to use the automatic pipeline.
            </div>
            <div className="rounded-xl border border-[#222] p-4" style={{ backgroundColor: '#111' }}>
              <EditDecisionListEditor slug={slug} track="shorts" topic={episode} />
            </div>
          </div>
        </div>

        {/* Right: live logs */}
        <div className="flex-shrink-0" style={{ width: '380px' }}>
          <LiveTerminal slug={slug} height="400px" />
        </div>
      </div>
    </div>
  )
}

function StepCard({
  step, done, running, error, hint, onRun, children,
}: {
  step: { id: string; label: string }
  done: boolean
  running: boolean
  error?: string
  hint?: string
  onRun: () => void
  children: React.ReactNode
}) {
  return (
    <div className="bg-[#111] rounded-xl border border-[#222] p-4">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <div
            className="w-2 h-2 rounded-full"
            style={{ backgroundColor: done ? ACCENT : '#333' }}
          />
          <span className="text-sm font-medium text-[#e0e0e0]">{step.label}</span>
        </div>
        <button
          onClick={onRun}
          disabled={running}
          className="px-3 py-1.5 rounded-lg text-xs font-medium transition-colors"
          style={{
            backgroundColor: running ? '#0d1f15' : 'transparent',
            color: running ? ACCENT : done ? '#555' : ACCENT,
            border: `1px solid ${running ? `${ACCENT}44` : done ? '#2a2a2a' : `${ACCENT}33`}`,
          }}
        >
          {running ? '⟳ Running...' : done ? '↺ Rerun' : '▶ Run'}
        </button>
      </div>
      {hint && !done && (
        <div className="text-[10px] text-[#888] mb-2">{hint}</div>
      )}
      {error && (
        <div className="text-[10px] text-[#ef4444] mb-2">{error}</div>
      )}
      <div>{children}</div>
    </div>
  )
}

function EmptyHint({ text }: { text: string }) {
  return <div className="text-xs text-[#555] py-4">{text}</div>
}

function ScriptPreview({ slug, filename }: { slug: string; filename: string }) {
  const [text, setText] = useState<string | null>(null)
  const [loaded, setLoaded] = useState(false)
  const [loadedFor, setLoadedFor] = useState<string | null>(null)

  if (!loaded || loadedFor !== filename) {
    setLoaded(true)
    setLoadedFor(filename)
    fetch(`${API_BASE}/files/cases/${slug}/shorts/${filename}`)
      .then(r => r.ok ? r.text() : '')
      .then(setText)
      .catch(() => setText('Failed to load script.'))
  }

  return (
    <pre className="text-xs text-[#e0e0e0] font-mono whitespace-pre-wrap leading-relaxed overflow-auto rounded-lg bg-[#0a0a0a] border border-[#1e1e1e] p-3" style={{ maxHeight: '300px' }}>
      {text ?? 'Loading...'}
    </pre>
  )
}
