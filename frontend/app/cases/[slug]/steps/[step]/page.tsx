'use client'
import { use, useState, useCallback, useEffect } from 'react'
import Link from 'next/link'
import { useRouter, useSearchParams } from 'next/navigation'
import { api, ConfigField, CheckpointStatus } from '@/lib/api'
import { useStepConfig, useCaseFiles, useCaseVersions, useCase, useJob, useCharacters, useCheckpoint, useResearch } from '@/lib/swr-hooks'
import { LiveTerminal } from '@/components/LiveTerminal'
import { SkeletonCard } from '@/components/Skeleton'
import { AudioSegmentList } from '@/components/AudioSegmentList'
import { ORDERED_PIPELINE, STEP_PREREQ, NEXT_STEP, STEP_LABEL, getStepIndex } from '@/lib/pipeline'
import { mutate } from 'swr'

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

const PIVOT_STEPS = new Set(['research', 'script', 'tts'])

export default function StepPage({ params }: { params: Promise<{ slug: string; step: string }> }) {
  const router = useRouter()
  const { slug, step } = use(params)
  const searchParams = useSearchParams()
  const fromTrack = searchParams.get('from') // 'longform' | 'shorts' | null
  const backHref = fromTrack === 'shorts' ? `/shorts/${slug}` : fromTrack === 'longform' ? `/longform/${slug}` : `/cases/${slug}`
  const { schema, config: savedConfig, isLoading } = useStepConfig(slug, step)
  const { files } = useCaseFiles(slug)
  const { versions } = useCaseVersions(slug)
  const { caseData } = useCase(slug)
  const { job } = useJob(slug)

  const [config, setConfig] = useState<Record<string, unknown>>({})
  const [configInit, setConfigInit] = useState(false)
  const [saving, setSaving] = useState(false)
  const [running, setRunning] = useState(false)
  // server-side running state: any job active for this slug
  const serverRunning = job?.status === 'running'
  const serverRunningThisStep = serverRunning && job?.step === step
  const [forceRun, setForceRun] = useState(false)
  const [branching, setBranching] = useState(false)
  const [showBranchForm, setShowBranchForm] = useState(false)
  const [branchReason, setBranchReason] = useState('')
  const [msg, setMsg] = useState('')

  if (savedConfig && Object.keys(savedConfig).length > 0 && !configInit) {
    setConfig(savedConfig)
    setConfigInit(true)
  }

  const isPivot = PIVOT_STEPS.has(step)
  const showMsg = (m: string) => { setMsg(m); setTimeout(() => setMsg(''), 4000) }

  // Artifact existence
  const pipeStep = ORDERED_PIPELINE.find(s => s.id === step)
  const ak = pipeStep?.artifactKey as string | null | undefined
  const isCountArtifact = ak === 'characters_count' || ak === 'shorts_script_count' || ak === 'shorts_audio_count'
  const hasArtifact = ak && !isCountArtifact && files
    ? (files[ak] as { exists: boolean } | undefined)?.exists ?? false
    : false

  // Prerequisite check
  const prereq = STEP_PREREQ[step]
  const prereqFileMissing = prereq?.fileKey
    ? !(files?.[prereq.fileKey] as { exists: boolean } | undefined)?.exists
    : false
  const prereqCountMissing = prereq?.countKey
    ? ((files?.[prereq.countKey] as number | undefined) ?? 0) === 0
    : false
  // Don't block while caseData is still loading (null gives -1 which always blocks)
  // Don't block when status is 'failed' — user must be able to retry the step
  const prereqStatusMissing = prereq?.afterStatus && caseData?.status && caseData.status !== 'failed'
    ? getStepIndex(caseData.status) <= getStepIndex(prereq.afterStatus)
    : false
  const prereqBlocked = (prereqFileMissing || prereqStatusMissing || prereqCountMissing) && !forceRun
  const prereqBlocking = prereq?.blocking ?? false

  // Next step
  const nextStepId = NEXT_STEP[step] ?? null

  const saveConfig = useCallback(async (): Promise<boolean> => {
    setSaving(true)
    try {
      await api.saveStepConfig(slug, step, config)
      showMsg('Config saved ✓')
      return true
    } catch (e) {
      console.warn('saveConfig failed (non-fatal):', e)
      return false
    } finally {
      setSaving(false)
    }
  }, [slug, step, config])

  const runStep = useCallback(async () => {
    if (running || serverRunning) return  // idempotent guard — backend also returns 409
    await saveConfig()   // best-effort — failure doesn't block run
    setRunning(true)
    try {
      await api.runStep(slug, step)
      showMsg(`${STEP_LABEL[step] || step} started`)
      setTimeout(() => { mutate(`files:${slug}`); mutate(`case:${slug}`) }, 3000)
    } catch (e) {
      showMsg(`Error: ${e}`)
    } finally {
      setTimeout(() => setRunning(false), 1000)
    }
  }, [slug, step, saveConfig, running, serverRunning])  // eslint-disable-line react-hooks/exhaustive-deps

  const branchCase = useCallback(async () => {
    setBranching(true)
    try {
      const child = await api.branchCase(slug, step, branchReason || undefined)
      showMsg(`Created ${child.slug} ✓`)
      const branchTarget = fromTrack === 'shorts' ? `/shorts/${child.slug}` : fromTrack === 'longform' ? `/longform/${child.slug}` : `/cases/${child.slug}`
      setTimeout(() => router.push(branchTarget), 1500)
    } catch (e) {
      showMsg(`Branch failed: ${e}`)
    } finally {
      setBranching(false)
      setShowBranchForm(false)
    }
  }, [slug, step, branchReason, router])

  if (isLoading) {
    return (
      <div className="p-6">
        <SkeletonCard className="h-12 mb-4" />
        <div className="flex gap-4">
          <SkeletonCard className="h-96 w-60 flex-shrink-0" />
          <SkeletonCard className="h-96 flex-1" />
          <SkeletonCard className="h-96 w-72 flex-shrink-0" />
        </div>
      </div>
    )
  }

  return (
    <div className="flex flex-col" style={{ minHeight: '100vh' }}>
      {/* Header */}
      <div className="px-6 py-3 border-b border-[#222] flex-shrink-0 flex items-center justify-between">
        <div className="flex items-center gap-2 text-xs text-[#555]">
          <Link href={backHref} className="hover:text-[#888] transition-colors">
            ← {slug}
          </Link>
          <span>/</span>
          <span className="text-[#e0e0e0]">{STEP_LABEL[step] || step}</span>
          {isPivot && (
            <span className="ml-1 text-[10px] px-1.5 py-0.5 rounded border border-[#f59e0b44] text-[#f59e0b]">
              PIVOT
            </span>
          )}
          {prereqBlocking && (
            <span className="ml-1 text-[10px] px-1.5 py-0.5 rounded border border-[#ef444444] text-[#ef4444]">
              BLOCKING
            </span>
          )}
        </div>
        <div className="flex items-center gap-3">
          {msg && <div className="text-xs text-[#22c55e]">{msg}</div>}
          {/* Next step button */}
          {nextStepId && hasArtifact && (
            <Link
              href={`/cases/${slug}/steps/${nextStepId}${fromTrack ? `?from=${fromTrack}` : ''}`}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-colors"
              style={{ backgroundColor: '#0d1a2e', color: '#3b82f6', border: '1px solid #3b82f633' }}
            >
              {STEP_LABEL[nextStepId]} →
            </Link>
          )}
        </div>
      </div>

      {/* 3-column body */}
      <div className="flex flex-1 overflow-hidden">
        {/* LEFT: Config panel */}
        <div
          className="flex flex-col border-r border-[#222] overflow-y-auto flex-shrink-0"
          style={{ width: '240px' }}
        >
          <div className="p-4">
            <div className="text-[10px] text-[#555] uppercase tracking-wider mb-3 font-medium">Config</div>
            <ConfigForm schema={schema} values={config} onChange={setConfig} />

            <div className="mt-4 flex flex-col gap-2">
              {/* Prereq warning */}
              {prereqBlocked && (
                <div className="rounded-lg p-2.5 text-[10px] leading-relaxed"
                  style={{ backgroundColor: prereqBlocking ? '#1a0505' : '#0a0800', color: prereqBlocking ? '#ef4444' : '#f59e0b', border: `1px solid ${prereqBlocking ? '#ef444422' : '#f59e0b22'}` }}>
                  <div className="font-medium mb-1">
                    {prereqBlocking ? '🔒 Blocked' : '⚠ Recommended first'}
                  </div>
                  <div className="text-[#888]">
                    {prereqFileMissing && `${prereq?.blockedBy} not done yet.`}
                    {prereqCountMissing && `${prereq?.blockedBy} has 0 files.`}
                    {prereqStatusMissing && ' Review gate not passed.'}
                  </div>
                  {!prereqBlocking && (
                    <button
                      onClick={() => setForceRun(true)}
                      className="mt-1.5 text-[10px] underline text-[#f59e0b] cursor-pointer"
                    >
                      Skip prereq anyway
                    </button>
                  )}
                </div>
              )}

              <button
                onClick={runStep}
                disabled={running || serverRunning || (prereqBlocked && prereqBlocking)}
                className="w-full py-2 rounded-lg text-xs font-medium transition-all"
                style={{
                  backgroundColor: (running || serverRunning) ? '#0d1a2e' : prereqBlocked && prereqBlocking ? '#111' : '#0d1117',
                  color: (running || serverRunning) ? '#3b82f6' : prereqBlocked && prereqBlocking ? '#444' : '#e0e0e0',
                  border: `1px solid ${(running || serverRunning) ? '#3b82f633' : prereqBlocked && prereqBlocking ? '#222' : '#333'}`,
                  cursor: (running || serverRunning) || (prereqBlocked && prereqBlocking) ? 'not-allowed' : 'pointer',
                }}
              >
                {(running || serverRunning)
                  ? serverRunning && !serverRunningThisStep
                    ? `⟳ ${job?.step} running...`
                    : '⟳ Running...'
                  : prereqBlocked && prereqBlocking ? '🔒 Blocked' : '▶ Run'}
              </button>

              <button
                onClick={saveConfig}
                disabled={saving}
                className="w-full py-1.5 rounded-lg text-xs transition-colors"
                style={{ backgroundColor: '#111', color: '#555', border: '1px solid #222' }}
              >
                {saving ? 'Saving...' : 'Save config'}
              </button>

              {/* Branch button — pivot steps only, after artifact exists */}
              {isPivot && hasArtifact && !showBranchForm && (
                <button
                  onClick={() => setShowBranchForm(true)}
                  className="w-full py-1.5 rounded-lg text-xs transition-colors"
                  style={{ backgroundColor: '#0a0600', color: '#f59e0b', border: '1px solid #f59e0b33' }}
                >
                  ⑂ Branch version
                </button>
              )}

              {showBranchForm && (
                <div className="p-3 rounded-lg" style={{ backgroundColor: '#0a0600', border: '1px solid #f59e0b22' }}>
                  <div className="text-[10px] text-[#f59e0b] mb-2">
                    New case version branching at {STEP_LABEL[step] || step}
                  </div>
                  <input
                    type="text"
                    value={branchReason}
                    onChange={e => setBranchReason(e.target.value)}
                    placeholder="Reason (optional)"
                    className="w-full mb-2 bg-[#0a0a0a] border border-[#333] rounded px-2 py-1 text-xs text-[#e0e0e0] placeholder-[#444] focus:outline-none"
                  />
                  <div className="flex gap-1.5">
                    <button
                      onClick={branchCase}
                      disabled={branching}
                      className="flex-1 py-1.5 rounded text-xs font-medium"
                      style={{ backgroundColor: '#f59e0b22', color: '#f59e0b', border: '1px solid #f59e0b44' }}
                    >
                      {branching ? '...' : 'Create'}
                    </button>
                    <button
                      onClick={() => setShowBranchForm(false)}
                      className="px-3 py-1.5 rounded text-xs text-[#555] border border-[#333]"
                    >
                      ✕
                    </button>
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>

        {/* CENTER: Output + versions */}
        <div className="flex-1 overflow-y-auto flex flex-col min-w-0">
          <div className="flex-1 p-4">
            <StepOutputPreview step={step} slug={slug} files={files} />
          </div>

          {/* Case versions bar */}
          {versions.length > 1 && (
            <div className="border-t border-[#222] px-4 py-3 flex-shrink-0">
              <div className="text-[10px] text-[#555] uppercase tracking-wider mb-2">Case versions</div>
              <div className="flex gap-1.5 flex-wrap">
                {versions.map(v => (
                  <Link
                    key={v.slug}
                    href={`/cases/${v.slug}/steps/${step}${fromTrack ? `?from=${fromTrack}` : ''}`}
                    className="flex items-center gap-1 px-2 py-1 rounded text-[10px] transition-colors"
                    style={{
                      backgroundColor: v.slug === slug ? '#1a1a1a' : 'transparent',
                      color: v.slug === slug ? '#e0e0e0' : '#555',
                      border: `1px solid ${v.slug === slug ? '#333' : 'transparent'}`,
                    }}
                  >
                    v{v.case_version}
                    {v.slug === slug && <span className="text-[#3b82f6] ml-0.5">●</span>}
                    {v.pivot_step && (
                      <span className="text-[#444] ml-0.5">@{v.pivot_step}</span>
                    )}
                  </Link>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* RIGHT: Logs */}
        <div className="flex-shrink-0 border-l border-[#222]" style={{ width: '280px' }}>
          <div className="p-3 border-b border-[#222]">
            <span className="text-[10px] text-[#555] uppercase tracking-wider">Live Logs</span>
          </div>
          <LiveTerminal slug={slug} height="calc(100vh - 100px)" />
        </div>
      </div>
    </div>
  )
}

// Step-specific output preview
function StepOutputPreview({
  step, slug, files,
}: {
  step: string
  slug: string
  files: Record<string, unknown> | null
}) {
  const pipeStep = ORDERED_PIPELINE.find(s => s.id === step)
  const ak = pipeStep?.artifactKey as string | null | undefined
  const fileInfo = ak && ak !== 'characters_count' && files
    ? files[ak] as { exists: boolean; size_mb?: number | null } | undefined
    : undefined

  // Characters step: show inline character grid (count comes from DB, not files)
  if (step === 'characters') {
    return <CharactersArtifact slug={slug} />
  }

  if (step === 'shorts_script') {
    const scripts = (files?.shorts_scripts as string[] | undefined) ?? []
    return <ShortsScriptArtifact slug={slug} scripts={scripts} />
  }

  if (step === 'shorts_tts') {
    const audioFiles = (files?.shorts_audio as string[] | undefined) ?? []
    return <ShortsAudioArtifact slug={slug} audioFiles={audioFiles} />
  }

  if (step === 'shorts_assemble') {
    const episodes = (files?.shorts_episodes as string[] | undefined) ?? []
    return <ShortsArtifact slug={slug} episodes={episodes} />
  }

  if (step === 'broll') {
    const clips = (files?.broll_clips as string[] | undefined) ?? []
    return <BRollArtifact slug={slug} clips={clips} />
  }

  if (!fileInfo?.exists) {
    return (
      <div className="h-48 flex items-center justify-center text-[#555] text-sm">
        No output yet — configure and run this step.
      </div>
    )
  }

  const sizeLine = fileInfo.size_mb != null ? `${fileInfo.size_mb.toFixed(2)} MB` : ''

  if (step === 'tts') {
    return <AudioEditor slug={slug} sizeLine={sizeLine} />
  }

  if (step === 'assemble') {
    const url = `${API_BASE}/files/cases/${slug}/output/video_final.mp4`
    return (
      <div>
        <div className="text-xs text-[#555] mb-3">{sizeLine}</div>
        <video controls className="w-full rounded-lg" style={{ maxHeight: '420px', background: '#000' }}>
          <source src={url} type="video/mp4" />
        </video>
      </div>
    )
  }

  if (step === 'thumbnail') {
    const url = `${API_BASE}/files/cases/${slug}/output/thumbnail.jpg`
    return (
      <div>
        <div className="text-xs text-[#555] mb-3">{sizeLine}</div>
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src={url} alt="thumbnail" className="rounded-lg" style={{ maxWidth: '400px' }} />
      </div>
    )
  }

  if (step === 'research') {
    return <ResearchPreview slug={slug} sizeLine={sizeLine} />
  }

  if (step === 'script') {
    return <ScriptPreview slug={slug} sizeLine={sizeLine} />
  }

  // Default: just show artifact exists
  return (
    <div className="text-xs text-[#555]">
      Artifact exists · {sizeLine}
    </div>
  )
}

function BRollArtifact({ slug, clips }: { slug: string; clips: string[] }) {
  if (clips.length === 0) {
    return (
      <div className="h-48 flex flex-col items-center justify-center gap-2">
        <div className="text-[#555] text-sm">No B-roll clips yet</div>
        <div className="text-[11px] text-[#444]">Run the step to fetch stock footage</div>
      </div>
    )
  }

  const SECTION_LABELS: Record<string, string> = {
    cold_open: 'Cold Open', the_break: 'The Break', world_building: 'World Building',
    the_crime: 'The Crime', investigation: 'Investigation', legal_battle: 'Legal Battle',
    aftermath: 'Aftermath', systemic_angle: 'Systemic Angle', close: 'Close',
  }

  return (
    <div className="flex flex-col gap-3">
      <div className="text-xs text-[#555]">{clips.length} clip{clips.length !== 1 ? 's' : ''} downloaded</div>
      <div className="grid grid-cols-2 gap-3">
        {clips.map(filename => {
          const base = filename.replace(/\.mp4$/, '')
          const label = SECTION_LABELS[base] ?? base.replace(/_/g, ' ')
          const url = `${API_BASE}/files/cases/${slug}/broll/${filename}`
          return (
            <div key={filename} className="bg-[#0a0a0a] rounded-xl border border-[#222] overflow-hidden">
              <video
                src={url}
                controls
                muted
                className="w-full"
                style={{ maxHeight: '160px', background: '#000' }}
              />
              <div className="px-2 py-1.5 text-[10px] text-[#666] capitalize">{label}</div>
            </div>
          )
        })}
      </div>
    </div>
  )
}

function ShortsScriptArtifact({ slug, scripts }: { slug: string; scripts: string[] }) {
  if (scripts.length === 0) {
    return (
      <div className="flex items-center justify-center h-full text-xs text-[#444]">
        No episode scripts yet. Run &quot;Episode Scripts&quot; step.
      </div>
    )
  }
  return (
    <div className="p-4 space-y-3">
      <div className="text-[10px] text-[#555] uppercase tracking-wider mb-4">
        {scripts.length} episode scripts
      </div>
      {scripts.map((name, i) => {
        const ep = name.replace(/^ep\d+_/, '').replace(/_/g, ' ').replace('.md', '')
        return (
          <div key={name} className="rounded-xl border border-[#1e1e1e] p-3 bg-[#0a0a0a]">
            <div className="flex items-center gap-2 mb-1">
              <span className="text-[10px] text-[#555] font-mono">EP {String(i + 1).padStart(2, '0')}</span>
              <span className="text-xs text-[#888] capitalize">{ep}</span>
            </div>
            <div className="text-[10px] text-[#22c55e]">{name}</div>
          </div>
        )
      })}
    </div>
  )
}

function ShortsAudioArtifact({ slug, audioFiles }: { slug: string; audioFiles: string[] }) {
  if (audioFiles.length === 0) {
    return (
      <div className="flex items-center justify-center h-full text-xs text-[#444]">
        No episode audio yet. Run &quot;Episode Audio&quot; step.
      </div>
    )
  }
  return (
    <div className="p-4 space-y-3">
      <div className="text-[10px] text-[#555] uppercase tracking-wider mb-4">
        {audioFiles.length} episode audio files
      </div>
      {audioFiles.map((name, i) => {
        const ep = name.replace(/^ep\d+_/, '').replace(/_/g, ' ').replace('.mp3', '')
        return (
          <div key={name} className="rounded-xl border border-[#1e1e1e] p-3 bg-[#0a0a0a]">
            <div className="flex items-center gap-2 mb-2">
              <span className="text-[10px] text-[#555] font-mono">EP {String(i + 1).padStart(2, '0')}</span>
              <span className="text-xs text-[#888] capitalize">{ep}</span>
            </div>
            <audio
              controls
              className="w-full h-8"
              style={{ accentColor: '#22c55e' }}
              src={`${API_BASE}/files/cases/${slug}/shorts/${name}`}
            />
          </div>
        )
      })}
    </div>
  )
}

function ShortsArtifact({ slug, episodes }: { slug: string; episodes: string[] }) {
  if (episodes.length === 0) {
    return (
      <div className="h-48 flex flex-col items-center justify-center gap-2">
        <div className="text-[#555] text-sm">No episodes yet — run this step</div>
        <div className="text-[11px] text-[#444]">Generates one short per script section</div>
      </div>
    )
  }
  return (
    <div className="flex flex-col gap-3">
      <div className="text-xs text-[#555]">{episodes.length} episode{episodes.length !== 1 ? 's' : ''}</div>
      <div className="flex gap-3 overflow-x-auto pb-2">
        {episodes.map(filename => {
          const label = filename.replace(/^ep\d+_/, '').replace(/_/g, ' ').replace('.mp4', '')
          const url = `${API_BASE}/files/cases/${slug}/shorts/${filename}`
          return (
            <div key={filename} className="flex-shrink-0 bg-[#0a0a0a] rounded-xl border border-[#222] overflow-hidden"
              style={{ width: '160px' }}>
              <div style={{ aspectRatio: '9/16', background: '#000' }}>
                <video src={url} controls muted style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
              </div>
              <div className="px-2 py-1.5 text-[10px] text-[#666] capitalize">{label}</div>
            </div>
          )
        })}
      </div>
    </div>
  )
}

function CharactersArtifact({ slug }: { slug: string }) {
  const { characters, isLoading, mutate: mutateChars } = useCharacters(slug)
  const [autoFinding, setAutoFinding] = useState(false)
  const [autoFindingId, setAutoFindingId] = useState<string | null>(null)
  const [msg, setMsg] = useState<string | null>(null)
  const [urlInputId, setUrlInputId] = useState<string | null>(null)
  const [urlValue, setUrlValue] = useState('')

  const ROLE_COLORS: Record<string, string> = {
    victim: '#22c55e', accused: '#ef4444', judge: '#3b82f6',
    lawyer: '#8b5cf6', witness: '#f59e0b', family: '#f97316', police: '#6b7280',
  }

  const autoFindAll = async () => {
    setAutoFinding(true); setMsg(null)
    try {
      const res = await api.autoImageAll(slug) as { found: number; total: number; results: { name: string; found: boolean }[] }
      const found = res.results.filter(r => r.found === true).map(r => r.name)
      setMsg(`Found ${found.length}/${res.total}${found.length ? ': ' + found.join(', ') : ''}`)
      mutateChars()
    } catch (e) { setMsg(`Error: ${e}`) } finally { setAutoFinding(false) }
  }

  const autoFindOne = async (id: string) => {
    setAutoFindingId(id)
    try {
      await api.autoImageOne(slug, id)
      mutateChars()
    } catch (e) { setMsg(`Error: ${e}`) } finally { setAutoFindingId(null) }
  }

  if (isLoading) return <div className="text-xs text-[#555] py-6 text-center">Loading…</div>

  if (characters.length === 0) {
    return (
      <div className="h-48 flex flex-col items-center justify-center gap-2">
        <div className="text-[#555] text-sm">No characters extracted yet</div>
        <div className="text-[11px] text-[#444]">Configure voice/speed above, then run the step</div>
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center justify-between">
        <span className="text-xs text-[#555]">{characters.length} characters</span>
        <button onClick={autoFindAll} disabled={autoFinding}
          className="px-3 py-1 rounded-lg text-[11px] border"
          style={{ backgroundColor: '#071a0d', border: '1px solid #22c55e33', color: autoFinding ? '#555' : '#22c55e' }}>
          {autoFinding ? '⟳ Searching…' : '⚡ Auto-find photos'}
        </button>
      </div>
      {msg && (
        <div className="px-3 py-1.5 rounded text-[11px]"
          style={{ backgroundColor: msg.startsWith('Error') ? '#1a0505' : '#071a0d', color: msg.startsWith('Error') ? '#ef4444' : '#22c55e' }}>
          {msg}
        </div>
      )}
      <div className="grid grid-cols-4 gap-2">
        {characters.map((c: { id: string; name: string; role?: string; image_path?: string }) => (
          <div key={c.id} className="bg-[#0a0a0a] rounded-xl p-3 border border-[#222] flex flex-col items-center text-center gap-1.5">
            <div className="w-12 h-12 rounded-full overflow-hidden flex items-center justify-center text-xl"
              style={{ backgroundColor: '#1a1a1a', border: '2px solid #222' }}>
              {c.image_path
                ? <img src={`${API_BASE}/files/cases/${slug}/characters/${c.image_path.split('/').pop()}`} alt={c.name} className="w-full h-full object-cover" />
                : <span>👤</span>}
            </div>
            <div className="text-[11px] font-medium text-[#e0e0e0] leading-tight">{c.name}</div>
            {c.role && (
              <span className="text-[9px] px-1.5 py-0.5 rounded-full"
                style={{ backgroundColor: `${ROLE_COLORS[c.role] || '#888'}22`, color: ROLE_COLORS[c.role] || '#888' }}>
                {c.role}
              </span>
            )}
            <div className="flex gap-1 w-full justify-center">
              {!c.image_path && (
                <button onClick={() => autoFindOne(c.id)} disabled={autoFindingId === c.id}
                  className="text-[9px] px-2 py-0.5 rounded"
                  style={{ backgroundColor: '#071a0d', color: autoFindingId === c.id ? '#555' : '#22c55e' }}>
                  {autoFindingId === c.id ? '⟳' : '⚡'}
                </button>
              )}
              <button onClick={() => { setUrlInputId(urlInputId === c.id ? null : c.id); setUrlValue('') }}
                className="text-[9px] px-2 py-0.5 rounded"
                style={{ backgroundColor: '#1a1a1a', color: '#666' }}>
                🔗
              </button>
            </div>
            {urlInputId === c.id && (
              <div className="flex gap-1 w-full mt-1">
                <input value={urlValue} onChange={e => setUrlValue(e.target.value)}
                  placeholder="Image URL"
                  className="flex-1 min-w-0 bg-[#0a0a0a] border border-[#333] rounded px-1.5 py-0.5 text-[9px] text-[#e0e0e0] focus:outline-none" />
                <button onClick={async () => {
                  if (!urlValue) return
                  try {
                    await api.addCharacterImageUrl(slug, c.id, urlValue)
                    setUrlInputId(null); setUrlValue('')
                    setMsg(`Photo saved for ${c.name}`)
                    mutateChars()
                  } catch (e) {
                    setMsg(`Failed to fetch image — check URL is a direct image link (.jpg/.png): ${e}`)
                  }
                }} className="px-1.5 py-0.5 bg-[#3b82f6] rounded text-[9px] text-white">✓</button>
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}

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

function ResearchPreview({ slug, sizeLine }: { slug: string; sizeLine: string }) {
  const { research, isLoading, mutate: mutateResearch } = useResearch(slug)
  const { checkpoint, mutate: mutateCheckpoint } = useCheckpoint(slug, 'research')

  const [text, setText] = useState<string | null>(null)
  const [initedFor, setInitedFor] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  const [validating, setValidating] = useState(false)
  const [reverting, setReverting] = useState(false)
  const [actioning, setActioning] = useState(false)
  const [msg, setMsg] = useState<{ text: string; ok: boolean } | null>(null)

  // Initialize the textarea once per loaded research payload (re-init if source flips).
  if (research && initedFor !== `${slug}:${research.source}`) {
    setText(JSON.stringify(research.data, null, 2))
    setInitedFor(`${slug}:${research.source}`)
  }

  const showMsg = (text: string, ok: boolean) => {
    setMsg({ text, ok })
    setTimeout(() => setMsg(null), 5000)
  }

  const handleSave = async () => {
    if (!text) return
    let parsed: Record<string, unknown>
    try {
      parsed = JSON.parse(text)
    } catch (e) {
      showMsg(`Invalid JSON: ${e instanceof Error ? e.message : String(e)}`, false)
      return
    }
    setSaving(true)
    try {
      await api.saveResearch(slug, parsed)
      await mutateResearch()
      await mutateCheckpoint()
      showMsg('Saved as manual override. Running validation…', true)
      setValidating(true)
      try {
        const result = await api.validateResearch(slug)
        await mutateCheckpoint()
        showMsg(result.passed ? 'Saved and validated.' : `Saved, but validation flagged it: ${result.notes}`, result.passed)
      } finally {
        setValidating(false)
      }
    } catch (e) {
      showMsg(`Save failed: ${e instanceof Error ? e.message : String(e)}`, false)
    } finally {
      setSaving(false)
    }
  }

  const handleValidate = async () => {
    setValidating(true)
    try {
      const result = await api.validateResearch(slug)
      await mutateCheckpoint()
      showMsg(result.passed ? 'Validation passed.' : `Validation flagged: ${result.notes}`, result.passed)
    } catch (e) {
      showMsg(`Validation failed: ${e instanceof Error ? e.message : String(e)}`, false)
    } finally {
      setValidating(false)
    }
  }

  const handleRevert = async () => {
    setReverting(true)
    try {
      await api.deleteResearchOverride(slug)
      setInitedFor(null)
      await mutateResearch()
      await mutateCheckpoint()
      showMsg('Reverted to AI-generated research.', true)
    } catch (e) {
      showMsg(`Revert failed: ${e instanceof Error ? e.message : String(e)}`, false)
    } finally {
      setReverting(false)
    }
  }

  const handleApprove = async () => {
    setActioning(true)
    try {
      await api.approveCheckpoint(slug, 'research')
      await mutateCheckpoint()
      showMsg('Approved.', true)
    } catch (e) {
      showMsg(`Approve failed: ${e instanceof Error ? e.message : String(e)}`, false)
    } finally {
      setActioning(false)
    }
  }

  const handleReject = async () => {
    setActioning(true)
    try {
      await api.rejectCheckpoint(slug, 'research')
      await mutateCheckpoint()
      showMsg('Rejected.', true)
    } catch (e) {
      showMsg(`Reject failed: ${e instanceof Error ? e.message : String(e)}`, false)
    } finally {
      setActioning(false)
    }
  }

  const status = checkpoint?.status ?? null
  const canApprove = status === 'ai_validated' || status === 'human_edited'
  const hasManualOverride = research?.source === 'manual'
  const busy = saving || validating || reverting || actioning

  return (
    <div>
      <div className="flex items-center justify-between mb-3">
        <span className="text-xs text-[#555]">{sizeLine}{research ? ` · source: ${research.source}` : ''}</span>
        <CheckpointBadge status={status} />
      </div>

      {msg && (
        <div
          className="text-xs py-2 px-3 rounded-lg mb-3"
          style={{ backgroundColor: msg.ok ? '#071a0d' : '#1a0505', color: msg.ok ? '#22c55e' : '#ef4444' }}
        >
          {msg.text}
        </div>
      )}

      {!research && isLoading && (
        <div className="text-xs text-[#555]">Loading research…</div>
      )}

      {text !== null && (
        <textarea
          value={text}
          onChange={e => setText(e.target.value)}
          className="w-full text-[11px] text-[#e0e0e0] font-mono whitespace-pre rounded-lg bg-[#0a0a0a] border border-[#222] p-3 focus:outline-none focus:border-[#3b82f6]"
          style={{ minHeight: '320px', maxHeight: 'calc(100vh - 380px)', resize: 'vertical' }}
          spellCheck={false}
        />
      )}

      <div className="flex flex-wrap gap-2 mt-3">
        <button
          onClick={handleSave}
          disabled={busy || text === null}
          className="px-3 py-1.5 rounded-lg text-xs font-medium transition-colors"
          style={{ backgroundColor: '#071a0d', color: '#22c55e', border: '1px solid #22c55e33' }}
        >
          {saving ? '⟳ Saving…' : '✓ Save as manual override'}
        </button>
        <button
          onClick={handleValidate}
          disabled={busy}
          className="px-3 py-1.5 rounded-lg text-xs transition-colors"
          style={{ backgroundColor: '#111', color: '#888', border: '1px solid #333' }}
        >
          {validating ? '⟳ Validating…' : 'Run validation'}
        </button>
        {hasManualOverride && (
          <button
            onClick={handleRevert}
            disabled={busy}
            className="px-3 py-1.5 rounded-lg text-xs transition-colors"
            style={{ backgroundColor: '#1a1205', color: '#f59e0b', border: '1px solid #f59e0b33' }}
          >
            {reverting ? '⟳ Reverting…' : '↩ Revert to AI version'}
          </button>
        )}
        <div className="flex-1" />
        {canApprove && (
          <button
            onClick={handleApprove}
            disabled={busy}
            className="px-3 py-1.5 rounded-lg text-xs font-medium transition-colors"
            style={{ backgroundColor: '#071a0d', color: '#22c55e', border: '1px solid #22c55e33' }}
          >
            Approve
          </button>
        )}
        <button
          onClick={handleReject}
          disabled={busy}
          className="px-3 py-1.5 rounded-lg text-xs transition-colors"
          style={{ backgroundColor: '#1a0505', color: '#ef4444', border: '1px solid #ef444433' }}
        >
          Reject
        </button>
      </div>

      {checkpoint?.validation_notes && (
        <div className="text-[10px] text-[#555] mt-2">Notes: {checkpoint.validation_notes}</div>
      )}
    </div>
  )
}

function ScriptPreview({ slug, sizeLine }: { slug: string; sizeLine: string }) {
  const [text, setText] = useState<string | null>(null)
  const [loaded, setLoaded] = useState(false)
  const API_BASE_INNER = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

  if (!loaded) {
    setLoaded(true)
    fetch(`${API_BASE_INNER}/api/scripts/${slug}`)
      .then(r => r.ok ? r.json() : null)
      .then(d => d?.text && setText(d.text))
      .catch(() => {})
  }

  return (
    <div>
      <div className="text-xs text-[#555] mb-3">{sizeLine}</div>
      {text ? (
        <pre className="text-xs text-[#e0e0e0] font-mono whitespace-pre-wrap leading-relaxed overflow-auto" style={{ maxHeight: 'calc(100vh - 280px)' }}>
          {text}
        </pre>
      ) : (
        <div className="text-xs text-[#555]">Loading script…</div>
      )}
    </div>
  )
}

// ─── Audio Editor ──────────────────────────────────────────────────────────────
function AudioEditor({ slug, sizeLine }: { slug: string; sizeLine: string }) {
  const API_BASE_INNER = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'
  const audioUrl = `${API_BASE_INNER}/files/cases/${slug}/audio/voiceover.mp3`
  const previewUrl = `${API_BASE_INNER}/files/cases/${slug}/audio/voiceover_preview.mp3`

  const [tempo,  setTempo]  = useState(1.0)
  const [pitch,  setPitch]  = useState(1.0)
  const [volume, setVolume] = useState(1.0)
  const [processing, setProcessing] = useState(false)
  const [previewing, setPreviewing] = useState(false)
  const [result, setResult] = useState<string | null>(null)
  const [hasOriginal, setHasOriginal] = useState(false)
  const [durMin, setDurMin] = useState<number | null>(null)
  // Increment these to force React to unmount/remount the audio element,
  // bypassing browser cache entirely (new key = new DOM node = fresh fetch).
  const [mainKey, setMainKey] = useState(0)
  const [previewKey, setPreviewKey] = useState(0)

  useEffect(() => {
    fetch(`${API_BASE_INNER}/api/audio/${slug}/info`)
      .then(r => r.ok ? r.json() : null)
      .then(d => {
        if (d?.exists) {
          setHasOriginal(d.has_original)
          setDurMin(d.duration_min)
        }
      })
      .catch(() => {})
  }, [slug])

  const fmtMin = (m: number | null) => m != null ? `${Math.floor(m)}m ${Math.round((m % 1) * 60)}s` : '—'

  const handlePreview = async () => {
    setPreviewing(true)
    setResult(null)
    try {
      const res = await api.processAudio(slug, { tempo, pitch, volume, preview_only: true }) as { duration_min: number }
      setPreviewKey(k => k + 1)
      setResult(`Preview ready — ${fmtMin(res.duration_min)}`)
    } catch (e) {
      setResult(`Error: ${e}`)
    } finally {
      setPreviewing(false)
    }
  }

  const handleApply = async () => {
    setProcessing(true)
    setResult(null)
    try {
      const res = await api.processAudio(slug, { tempo, pitch, volume }) as { duration_min: number }
      setDurMin(res.duration_min)
      setHasOriginal(true)
      setMainKey(k => k + 1)
      setResult(`Applied ✓ — ${fmtMin(res.duration_min)}`)
    } catch (e) {
      setResult(`Error: ${e}`)
    } finally {
      setProcessing(false)
    }
  }

  const handleReset = async () => {
    try {
      const res = await api.resetAudio(slug) as { duration_min: number }
      setTempo(1.0); setPitch(1.0); setVolume(1.0)
      setDurMin(res.duration_min)
      setMainKey(k => k + 1)
      setResult(`Reset to original — ${fmtMin(res.duration_min)}`)
    } catch (e) {
      setResult(`Reset failed: ${e}`)
    }
  }

  const sliders: { label: string; key: 'tempo' | 'pitch' | 'volume'; val: number; set: (v: number) => void; min: number; max: number; step: number; desc: (v: number) => string }[] = [
    {
      label: 'Tempo', key: 'tempo', val: tempo, set: setTempo,
      min: 0.6, max: 1.5, step: 0.05,
      desc: (v) => v < 0.85 ? 'Very slow' : v < 0.97 ? 'Slow' : v < 1.04 ? 'Normal' : 'Fast',
    },
    {
      label: 'Pitch', key: 'pitch', val: pitch, set: setPitch,
      min: 0.8, max: 1.2, step: 0.02,
      desc: (v) => v < 0.94 ? 'Lower pitch' : v > 1.06 ? 'Higher pitch' : 'Original pitch',
    },
    {
      label: 'Volume', key: 'volume', val: volume, set: setVolume,
      min: 0.5, max: 2.0, step: 0.05,
      desc: (v) => v < 0.8 ? 'Quiet' : v > 1.3 ? 'Loud' : 'Normal',
    },
  ]

  const unchanged = tempo === 1.0 && pitch === 1.0 && volume === 1.0

  return (
    <div className="flex flex-col gap-4">
      {/* Current audio player */}
      <div>
        <div className="flex items-center justify-between mb-1.5">
          <span className="text-[10px] text-[#555]">{sizeLine}{durMin != null ? ` · ${fmtMin(durMin)}` : ''}</span>
          {hasOriginal && (
            <button onClick={handleReset} className="text-[10px] text-[#f59e0b] hover:underline">
              ↩ Reset to original
            </button>
          )}
        </div>
        <audio key={mainKey} controls className="w-full" style={{ filter: 'invert(0.9) hue-rotate(180deg)' }}>
          <source src={`${audioUrl}?t=${mainKey}`} type="audio/mpeg" />
        </audio>
      </div>

      {/* Sliders */}
      <div className="rounded-xl border border-[#222] bg-[#0a0a0a] p-4 flex flex-col gap-4">
        <div className="text-[10px] text-[#555] uppercase tracking-wider font-medium">Audio Editor</div>
        {sliders.map(s => (
          <div key={s.key}>
            <div className="flex items-center justify-between mb-1.5">
              <span className="text-xs text-[#888]">{s.label}</span>
              <span className="text-xs font-mono" style={{ color: s.val === 1.0 && s.key !== 'volume' ? '#555' : '#e0e0e0' }}>
                {s.val.toFixed(2)} <span className="text-[#555]">— {s.desc(s.val)}</span>
              </span>
            </div>
            <input
              type="range" min={s.min} max={s.max} step={s.step}
              value={s.val}
              onChange={e => s.set(parseFloat(e.target.value))}
              className="w-full accent-[#3b82f6]"
            />
            <div className="flex justify-between text-[10px] text-[#444] mt-0.5">
              <span>{s.min}</span>
              <span>1.0</span>
              <span>{s.max}</span>
            </div>
          </div>
        ))}

        {result && (
          <div className="text-xs py-2 px-3 rounded-lg" style={{ backgroundColor: result.startsWith('Error') ? '#1a0505' : '#071a0d', color: result.startsWith('Error') ? '#ef4444' : '#22c55e' }}>
            {result}
          </div>
        )}

        <div className="flex gap-2 pt-1">
          <button
            onClick={handlePreview}
            disabled={previewing || processing || unchanged}
            className="flex-1 py-2 rounded-lg text-xs transition-colors"
            style={{ backgroundColor: '#111', color: previewing ? '#3b82f6' : unchanged ? '#444' : '#888', border: '1px solid #333' }}
          >
            {previewing ? '⟳ Generating…' : '▶ Preview 30s'}
          </button>
          <button
            onClick={handleApply}
            disabled={processing || previewing || unchanged}
            className="flex-1 py-2 rounded-lg text-xs font-medium transition-colors"
            style={{ backgroundColor: unchanged ? '#111' : '#071a0d', color: unchanged ? '#444' : '#22c55e', border: `1px solid ${unchanged ? '#222' : '#22c55e33'}` }}
          >
            {processing ? '⟳ Processing…' : '✓ Apply to full audio'}
          </button>
        </div>
      </div>

      {/* Preview player — rendered only after first preview generated */}
      {previewKey > 0 && (
        <div>
          <div className="text-[10px] text-[#555] mb-1">30s preview</div>
          <audio key={previewKey} controls className="w-full" style={{ filter: 'invert(0.9) hue-rotate(180deg)' }}>
            <source src={`${previewUrl}?t=${previewKey}`} type="audio/mpeg" />
          </audio>
        </div>
      )}

      {/* Per-segment replace + checkpoint approve/reject */}
      <div className="rounded-xl border border-[#222] bg-[#0a0a0a] p-4">
        <div className="text-[10px] text-[#555] uppercase tracking-wider font-medium mb-3">Segments</div>
        <AudioSegmentList slug={slug} track="longform" />
      </div>
    </div>
  )
}

// Dynamic config form
function ConfigForm({
  schema, values, onChange,
}: {
  schema: ConfigField[]
  values: Record<string, unknown>
  onChange: (v: Record<string, unknown>) => void
}) {
  if (!schema || schema.length === 0) {
    return <div className="text-xs text-[#555]">No config for this step.</div>
  }

  const set = (key: string, val: unknown) => onChange({ ...values, [key]: val })

  return (
    <div className="flex flex-col gap-3">
      {schema.map(field => {
        const val = values[field.key] ?? field.default ?? ''
        return (
          <div key={field.key}>
            <label className="block text-[10px] text-[#555] mb-1">{field.label}</label>
            {field.type === 'select' ? (
              <select
                value={String(val)}
                onChange={e => set(field.key, e.target.value)}
                className="w-full bg-[#0a0a0a] border border-[#333] rounded px-2 py-1.5 text-xs text-[#e0e0e0] focus:outline-none"
              >
                {field.options?.map(o => {
                  const [v, label] = o.includes('|') ? o.split('|') : [o, o]
                  return <option key={o} value={o}>{label ?? v}</option>
                })}
              </select>
            ) : field.type === 'textarea' ? (
              <textarea
                value={String(val)}
                onChange={e => set(field.key, e.target.value)}
                placeholder={field.placeholder}
                rows={3}
                className="w-full bg-[#0a0a0a] border border-[#333] rounded px-2 py-1.5 text-xs text-[#e0e0e0] placeholder-[#444] focus:outline-none resize-none"
              />
            ) : field.type === 'boolean' ? (
              <label className="flex items-center gap-2 cursor-pointer">
                <input
                  type="checkbox"
                  checked={Boolean(val)}
                  onChange={e => set(field.key, e.target.checked)}
                  className="accent-[#3b82f6]"
                />
                <span className="text-xs text-[#888]">{val ? 'Yes' : 'No'}</span>
              </label>
            ) : (
              <input
                type={field.type === 'number' ? 'number' : 'text'}
                value={String(val)}
                onChange={e => set(field.key, field.type === 'number' ? Number(e.target.value) : e.target.value)}
                placeholder={field.placeholder}
                min={field.min}
                max={field.max}
                step={field.step}
                className="w-full bg-[#0a0a0a] border border-[#333] rounded px-2 py-1.5 text-xs text-[#e0e0e0] placeholder-[#444] focus:outline-none"
              />
            )}
          </div>
        )
      })}
    </div>
  )
}
