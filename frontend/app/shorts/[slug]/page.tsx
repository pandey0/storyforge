'use client'
import { use, useCallback, useState } from 'react'
import Link from 'next/link'
import { api } from '@/lib/api'
import { useCase, useCaseFiles, useShortsPlan } from '@/lib/swr-hooks'
import { SkeletonCard } from '@/components/Skeleton'
import {
  ORDERED_PIPELINE, SHORTS_EPISODE_STEPS,
  topicFileMatch, statusColor,
} from '@/lib/pipeline'

const ACCENT = '#22c55e'

export default function ShortsCasePage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = use(params)
  const { caseData, isLoading } = useCase(slug)
  const { files, mutate: mutateFiles } = useCaseFiles(slug)
  const { plan, isLoading: planLoading, mutate: mutatePlan } = useShortsPlan(slug)
  const filesMap = files as Record<string, unknown> | undefined
  const [stepRunning, setStepRunning] = useState<Record<string, boolean>>({})

  const runStep = useCallback(async (step: string) => {
    setStepRunning(prev => ({ ...prev, [step]: true }))
    try {
      await api.runStep(slug, step)
      // Plan/files only land after the background job finishes — give it a
      // moment then refetch rather than polling indefinitely.
      setTimeout(() => { mutatePlan(); mutateFiles() }, 8000)
    } catch (e) {
      console.error(e)
    } finally {
      setTimeout(() => setStepRunning(prev => ({ ...prev, [step]: false })), 1000)
    }
  }, [slug, mutatePlan, mutateFiles])

  if (isLoading) {
    return (
      <div className="p-6">
        <SkeletonCard className="h-16 mb-4" />
        <div className="grid grid-cols-3 gap-3">
          {[...Array(7)].map((_, i) => <SkeletonCard key={i} className="h-32" />)}
        </div>
      </div>
    )
  }

  if (!caseData) return <div className="p-6 text-[#ef4444]">Case not found: {slug}</div>

  const sharedSteps = ORDERED_PIPELINE.filter(s => s.track === 'shared')
  const planStep = ORDERED_PIPELINE.find(s => s.id === 'shorts_plan')!
  const planCount = (filesMap?.shorts_plan_count as number | undefined) ?? 0
  const hasPlan = planCount > 0 || (plan?.length ?? 0) > 0

  const renderStepRow = (step: typeof ORDERED_PIPELINE[number]) => {
    const ak = step.artifactKey
    const isCountKey = ak === 'characters_count' || ak === 'shorts_plan_count'
    const hasArtifact = isCountKey
      ? ((filesMap?.[ak as string] as number | undefined) ?? 0) > 0
      : ak
        ? (filesMap?.[ak] as { exists?: boolean } | undefined)?.exists
        : false
    const running = stepRunning[step.apiStep ?? '']
    return (
      <div
        key={step.id}
        className="bg-[#111] rounded-xl p-3 border border-[#222] flex items-center justify-between gap-3"
      >
        <Link href={`/cases/${slug}/steps/${step.id}?from=shorts`} className="flex-1 min-w-0 block">
          <div className="flex items-center gap-2">
            <div
              className="w-1.5 h-1.5 rounded-full flex-shrink-0"
              style={{ backgroundColor: hasArtifact ? ACCENT : '#333' }}
            />
            <span className="text-sm text-[#e0e0e0]">{step.label}</span>
          </div>
          <div className="text-xs text-[#555] mt-0.5">{step.desc}</div>
        </Link>
        {step.apiStep && (
          <button
            onClick={() => runStep(step.apiStep as string)}
            disabled={running}
            className="px-3 py-1.5 rounded-lg text-xs font-medium transition-colors flex-shrink-0"
            style={{
              backgroundColor: running ? '#0d1f15' : 'transparent',
              color: running ? ACCENT : hasArtifact ? '#555' : ACCENT,
              border: `1px solid ${running ? `${ACCENT}44` : hasArtifact ? '#2a2a2a' : `${ACCENT}33`}`,
            }}
          >
            {running ? '⟳ Running...' : hasArtifact ? '↺ Rerun' : '▶ Run'}
          </button>
        )}
      </div>
    )
  }

  return (
    <div className="p-6">
      {/* Breadcrumb */}
      <div className="flex items-center gap-2 text-xs text-[#555] mb-1">
        <Link href="/shorts" className="hover:text-[#888] transition-colors">
          ← Shorts Studio
        </Link>
        <span>/</span>
        <span className="text-[#e0e0e0]">{caseData.name}</span>
      </div>
      <div className="flex items-center justify-between mb-6 mt-2">
        <div>
          {(caseData.subject_name || caseData.location || caseData.year_of_crime) && (
            <div className="text-xs text-[#555]">
              {[caseData.subject_name, caseData.location, caseData.year_of_crime].filter(Boolean).join(' · ')}
            </div>
          )}
        </div>
        <span
          className="text-xs px-2 py-0.5 rounded-full"
          style={{ backgroundColor: `${statusColor(caseData.status)}22`, color: statusColor(caseData.status) }}
        >
          {caseData.status}
        </span>
      </div>

      {/* Shared section */}
      <div className="mb-8">
        <div className="text-[10px] text-[#555] uppercase tracking-wider mb-3 font-medium">Shared</div>
        <div className="flex flex-col gap-2">
          {sharedSteps.map(renderStepRow)}
        </div>
      </div>

      {/* Episode Plan step — gates the grid below */}
      <div className="mb-8">
        <div className="text-[10px] text-[#555] uppercase tracking-wider mb-3 font-medium">Plan</div>
        <div className="flex flex-col gap-2">
          {renderStepRow(planStep)}
        </div>
      </div>

      {/* Episodes grid — dynamic count, sourced from shorts_plan.json, not a fixed menu */}
      <div>
        <div className="text-[10px] text-[#555] uppercase tracking-wider mb-3 font-medium">Episodes</div>
        {!hasPlan ? (
          <div className="text-xs text-[#555] bg-[#111] border border-[#222] rounded-xl p-4">
            {planLoading ? 'Loading…' : 'No episode plan yet — run "Episode Plan" above to decide episode count and angles from this case\'s research.'}
          </div>
        ) : (
          <div className="grid gap-3" style={{ gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))' }}>
            {(plan ?? []).map(card => (
              <EpisodeCard key={card.slug} slug={slug} topic={card} files={filesMap} />
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

function EpisodeCard({
  slug, topic, files,
}: {
  slug: string
  topic: { slug: string; label: string }
  files: Record<string, unknown> | undefined
}) {
  const scriptDone = !!topicFileMatch(files?.shorts_scripts as string[] | undefined, topic.slug)
  const audioDone = !!topicFileMatch(files?.shorts_audio as string[] | undefined, topic.slug)
  const assembleDone = !!topicFileMatch(files?.shorts_episodes as string[] | undefined, topic.slug)
  const doneMap: Record<string, boolean> = {
    shorts_script: scriptDone,
    shorts_tts: audioDone,
    shorts_assemble: assembleDone,
  }

  return (
    <Link
      href={`/shorts/${slug}/${topic.slug}`}
      className="bg-[#111] rounded-xl p-4 border border-[#222] hover:border-[#22c55e33] transition-colors block"
    >
      <div className="text-sm text-[#e0e0e0] mb-3">{topic.label}</div>
      <div className="flex items-center gap-2">
        {SHORTS_EPISODE_STEPS.map(step => (
          <div key={step.id} className="flex items-center gap-1.5 flex-1">
            <div
              className="w-2 h-2 rounded-full flex-shrink-0"
              style={{ backgroundColor: doneMap[step.id] ? ACCENT : '#333' }}
            />
            <span className="text-[10px] text-[#555]">{step.label}</span>
          </div>
        ))}
      </div>
    </Link>
  )
}
