'use client'
import { use } from 'react'
import Link from 'next/link'
import { api } from '@/lib/api'
import { useCase, useCaseFiles, useJob } from '@/lib/swr-hooks'
import { ORDERED_PIPELINE, statusColor } from '@/lib/pipeline'
import { SkeletonCard } from '@/components/Skeleton'
import { EditDecisionListEditor } from '@/components/EditDecisionListEditor'
import { useState, useCallback } from 'react'
import { mutate } from 'swr'

type PipelineEntry = typeof ORDERED_PIPELINE[number]

function StepRow({ step, slug, color, running, onRun, files }: {
  step: PipelineEntry
  slug: string
  color: string
  running: boolean
  onRun: (apiStep: string) => void
  files: Record<string, unknown> | undefined
}) {
  const isGate = step.type === 'gate'
  const ak = step.artifactKey
  const isCountKey = ak === 'characters_count' || ak === 'shorts_script_count' || ak === 'shorts_audio_count'
  const fileInfo = ak && !isCountKey && files
    ? files[ak] as { exists: boolean; size_mb?: number } | undefined
    : undefined
  const countVal = isCountKey && files ? files[ak] as number : null
  const hasArtifact = isCountKey ? (countVal ?? 0) > 0 : fileInfo?.exists

  const href = isGate ? `/cases/${slug}/review` : `/cases/${slug}/steps/${step.id}?from=longform`

  return (
    <Link
      href={href}
      className="flex items-center gap-3 rounded-xl p-4 border transition-all block mb-2"
      style={{
        backgroundColor: '#111',
        borderColor: hasArtifact ? `${color}33` : '#1e1e1e',
        textDecoration: 'none',
      }}
    >
      <div
        className="w-2.5 h-2.5 rounded-full flex-shrink-0"
        style={{ backgroundColor: hasArtifact ? color : '#333' }}
      />
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <span className="text-sm font-medium text-[#e0e0e0]">{step.label}</span>
          {isGate && (
            <span className="text-[9px] px-1.5 py-0.5 rounded border border-[#f59e0b44] text-[#f59e0b]">GATE</span>
          )}
        </div>
        <div className="text-xs text-[#555] mt-0.5">{step.desc}</div>
        {hasArtifact && !isGate && (
          <div className="mt-1.5 flex items-center gap-1.5">
            <div className="w-1 h-1 rounded-full" style={{ backgroundColor: color }} />
            <span className="text-[10px]" style={{ color }}>
              {isCountKey
                ? `${countVal} ${ak === 'characters_count' ? 'characters' : 'items'}`
                : fileInfo?.size_mb != null
                  ? `${fileInfo.size_mb.toFixed(1)} MB`
                  : 'artifact present'}
            </span>
          </div>
        )}
      </div>
      {step.apiStep && (
        <button
          onClick={(e) => { e.preventDefault(); e.stopPropagation(); onRun(step.apiStep as string) }}
          disabled={running}
          className="px-3 py-1.5 rounded-lg text-xs font-medium transition-all flex-shrink-0"
          style={{
            backgroundColor: running ? `${color}22` : 'transparent',
            color: running ? color : hasArtifact ? '#555' : color,
            border: `1px solid ${running ? `${color}44` : hasArtifact ? '#2a2a2a' : `${color}33`}`,
          }}
        >
          {running ? '⟳ Running...' : hasArtifact ? '↺ Rerun' : '▶ Run'}
        </button>
      )}
      {isGate && <span className="text-xs flex-shrink-0" style={{ color: '#f59e0b' }}>Open →</span>}
    </Link>
  )
}

export default function LongformCaseWorkspace({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = use(params)
  const { caseData, isLoading } = useCase(slug)
  const { files } = useCaseFiles(slug)
  const { job } = useJob(slug)
  const [stepRunning, setStepRunning] = useState<Record<string, boolean>>({})
  const [unpublishing, setUnpublishing] = useState(false)
  const [runningAll, setRunningAll] = useState(false)
  const [runAllError, setRunAllError] = useState('')

  const unpublish = useCallback(async () => {
    if (!window.confirm(
      "This resets the dashboard's tracking only — it does NOT unpublish or hide the video on YouTube itself. Continue?"
    )) return
    setUnpublishing(true)
    try {
      const res = await api.unpublishCase(slug)
      window.alert(res.warning)
      mutate(`case:${slug}`)
    } catch (e) {
      window.alert(`Unpublish failed: ${e}`)
    } finally {
      setUnpublishing(false)
    }
  }, [slug])

  const runStep = useCallback(async (apiStep: string) => {
    setStepRunning(prev => ({ ...prev, [apiStep]: true }))
    try {
      await api.runStep(slug, apiStep)
      setTimeout(() => mutate(`case:${slug}`), 2000)
    } catch (e) {
      console.error(e)
    } finally {
      setTimeout(() => setStepRunning(prev => ({ ...prev, [apiStep]: false })), 500)
    }
  }, [slug])

  const runAll = useCallback(async () => {
    setRunningAll(true)
    setRunAllError('')
    try {
      const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'
      const res = await fetch(`${API_BASE}/api/pipeline/${slug}/run_full?track=longform`, { method: 'POST' })
      if (!res.ok) throw new Error(await res.text())
      setTimeout(() => mutate(`case:${slug}`), 3000)
      setTimeout(() => mutate(`case:${slug}`), 8000)
      setTimeout(() => mutate(`case:${slug}`), 20000)
    } catch (e) {
      setRunAllError(String(e))
    } finally {
      setTimeout(() => setRunningAll(false), 2000)
    }
  }, [slug])

  if (isLoading) {
    return (
      <div className="p-6">
        <SkeletonCard className="h-16 mb-4" />
        <div className="grid grid-cols-1 gap-3">
          {[...Array(6)].map((_, i) => <SkeletonCard key={i} className="h-20" />)}
        </div>
      </div>
    )
  }

  if (!caseData) return <div className="p-6 text-[#ef4444]">Case not found: {slug}</div>

  const isRunning = job?.status === 'running'
  const filesMap = files as Record<string, unknown> | undefined
  const sharedSteps = ORDERED_PIPELINE.filter(s => s.track === 'shared')
  const longformSteps = ORDERED_PIPELINE.filter(s => s.track === 'longform')

  return (
    <div className="p-6 max-w-3xl">
      {/* Breadcrumb header */}
      <div className="flex items-center justify-between mb-1">
        <div className="flex items-center gap-2 text-sm">
          <Link href="/longform" className="text-[#3b82f6] hover:text-[#60a5fa] transition-colors">
            ← Long-form Studio
          </Link>
          <span className="text-[#555]">/</span>
          <span className="text-[#e0e0e0] font-medium">{caseData.name}</span>
        </div>
        <div className="flex items-center gap-3">
          {isRunning && (
            <div className="flex items-center gap-1.5 text-xs text-[#3b82f6]">
              <div className="w-1.5 h-1.5 rounded-full bg-[#3b82f6] animate-pulse" />
              {job?.step} running...
            </div>
          )}
          <span className="text-xs px-2 py-0.5 rounded-full"
            style={{ backgroundColor: `${statusColor(caseData.status)}22`, color: statusColor(caseData.status) }}>
            {caseData.status}
          </span>
          {caseData.status === 'published' && (
            <button
              onClick={unpublish}
              disabled={unpublishing}
              className="text-[10px] px-2 py-1 rounded border border-[#333] text-[#888] hover:text-[#ef4444] hover:border-[#ef444444] transition-colors"
            >
              {unpublishing ? '⟳ Unpublishing...' : 'Unpublish (local only)'}
            </button>
          )}
        </div>
      </div>
      {(caseData.subject_name || caseData.location || caseData.year_of_crime) && (
        <div className="text-xs text-[#555] mb-6">
          {[caseData.subject_name, caseData.location, caseData.year_of_crime].filter(Boolean).join(' · ')}
        </div>
      )}

      {/* Run All button */}
      <div className="flex items-center justify-between mb-6">
        <div className="text-[10px] text-[#555]">
          Run steps individually below, or kick off the full pipeline:
        </div>
        <div className="flex items-center gap-3">
          {runAllError && <span className="text-xs text-[#ef4444]">{runAllError}</span>}
          <button
            onClick={runAll}
            disabled={runningAll || isRunning}
            className="px-4 py-2 rounded-lg text-sm font-medium transition-colors"
            style={{
              backgroundColor: runningAll ? '#0d1629' : '#3b82f6',
              color: '#fff',
              opacity: runningAll || isRunning ? 0.6 : 1,
            }}
          >
            {runningAll ? '⟳ Starting pipeline...' : '▶ Run All Steps'}
          </button>
        </div>
      </div>

      {/* Shared section */}
      <div className="mb-8">
        <div className="text-[10px] text-[#555] uppercase tracking-wider font-medium mb-1">Shared</div>
        <div className="text-[11px] text-[#444] mb-3">
          ↳ also used by Shorts Studio if you run that track for this case
        </div>
        {sharedSteps.map(step => (
          <StepRow
            key={step.id}
            step={step}
            slug={slug}
            color="#888"
            running={step.apiStep ? !!stepRunning[step.apiStep] : false}
            onRun={runStep}
            files={filesMap}
          />
        ))}
      </div>

      {/* Long-form section */}
      <div>
        <div className="text-[10px] uppercase tracking-wider font-medium mb-3" style={{ color: '#3b82f6' }}>
          Long-form
        </div>
        {longformSteps.map(step => (
          <StepRow
            key={step.id}
            step={step}
            slug={slug}
            color="#3b82f6"
            running={step.apiStep ? !!stepRunning[step.apiStep] : false}
            onRun={runStep}
            files={filesMap}
          />
        ))}
      </div>

      <div className="mt-8">
        <div className="text-[10px] uppercase tracking-wider font-medium mb-1" style={{ color: '#3b82f6' }}>
          Manual Overrides
        </div>
        <div className="text-[11px] text-[#555] mb-3">
          Optional — override which clip plays for specific segments. Leave on Auto to use the automatic pipeline.
        </div>
        <div className="rounded-xl border border-[#222] p-4" style={{ backgroundColor: '#111' }}>
          <EditDecisionListEditor slug={slug} track="longform" />
        </div>
      </div>
    </div>
  )
}
