'use client'
import { use, useState, useCallback } from 'react'
import Link from 'next/link'
import { api } from '@/lib/api'
import { useCase, useJob, useCaseFiles, useScript, useCharacters } from '@/lib/swr-hooks'
import { PipelineStepper } from '@/components/PipelineStepper'
import { LiveTerminal } from '@/components/LiveTerminal'
import { FileStatusGrid } from '@/components/FileStatusGrid'
import { statusColor, getStepIndex, ORDERED_PIPELINE, PIPELINE_STEPS } from '@/lib/pipeline'
import { SkeletonCard } from '@/components/Skeleton'
import { mutate } from 'swr'
import { Character } from '@/lib/api'

const TABS = ['Pipeline', 'Script', 'Characters', 'Audio', 'Video', 'Data', 'Logs'] as const
type Tab = typeof TABS[number]

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

export default function CaseDetailPage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = use(params)
  const { caseData, isLoading } = useCase(slug)
  const { job } = useJob(slug)
  const [activeTab, setActiveTab] = useState<Tab>('Pipeline')
  const [stepRunning, setStepRunning] = useState<Record<string, boolean>>({})

  const runStep = useCallback(async (step: string) => {
    setStepRunning(prev => ({ ...prev, [step]: true }))
    try {
      await api.runStep(slug, step)
      setTimeout(() => mutate(`case:${slug}`), 2000)
    } catch (e) {
      console.error(e)
    } finally {
      setTimeout(() => setStepRunning(prev => ({ ...prev, [step]: false })), 500)
    }
  }, [slug])

  const approve = useCallback(async () => {
    await api.approveGate(slug)
    mutate(`case:${slug}`)
  }, [slug])

  const reject = useCallback(async () => {
    await api.rejectGate(slug)
    mutate(`case:${slug}`)
  }, [slug])

  if (isLoading) {
    return (
      <div className="p-6">
        <SkeletonCard className="h-24 mb-4" />
        <SkeletonCard className="h-10 mb-4" />
        <div className="grid grid-cols-2 gap-3">
          {[...Array(6)].map((_, i) => <SkeletonCard key={i} className="h-24" />)}
        </div>
      </div>
    )
  }

  if (!caseData) return <div className="p-6 text-[#ef4444]">Case not found: {slug}</div>

  const isRunning = job?.status === 'running'

  return (
    <div className="flex flex-col" style={{ minHeight: '100vh' }}>
      {/* Header */}
      <div className="px-6 py-4 border-b border-[#222] flex-shrink-0">
        <div className="flex items-center justify-between mb-1">
          <h1 className="text-lg font-semibold text-[#e0e0e0]">{caseData.name}</h1>
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
          </div>
        </div>
        {(caseData.subject_name || caseData.location || caseData.year_of_crime) && (
          <div className="text-xs text-[#555] mb-3">
            {[caseData.subject_name, caseData.location, caseData.year_of_crime].filter(Boolean).join(' · ')}
          </div>
        )}
        <PipelineStepper status={caseData.status} />
      </div>

      {/* Tabs */}
      <div className="flex border-b border-[#222] px-6 flex-shrink-0 overflow-x-auto">
        {TABS.map(tab => (
          <button key={tab} onClick={() => setActiveTab(tab)}
            className="px-4 py-2.5 text-xs font-medium border-b-2 transition-colors whitespace-nowrap"
            style={{ borderColor: activeTab === tab ? '#3b82f6' : 'transparent', color: activeTab === tab ? '#3b82f6' : '#555' }}>
            {tab}
          </button>
        ))}
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto p-6">
        {activeTab === 'Pipeline' && (
          <PipelineTab slug={slug} caseData={caseData} stepRunning={stepRunning} onRun={runStep} onApprove={approve} onReject={reject} />
        )}
        {activeTab === 'Script' && <ScriptTab slug={slug} />}
        {activeTab === 'Characters' && <CharactersTab slug={slug} />}
        {activeTab === 'Audio' && <AudioTab slug={slug} />}
        {activeTab === 'Video' && <VideoTab slug={slug} />}
        {activeTab === 'Data' && <DataTab slug={slug} />}
        {activeTab === 'Logs' && <LiveTerminal slug={slug} height="calc(100vh - 220px)" />}
      </div>
    </div>
  )
}

// ---- Pipeline Tab ----
type PipelineEntry = typeof ORDERED_PIPELINE[number]

function PipelineStepCard({
  pipeStep, idx, isLast, slug, caseData, stepRunning, onRun, files,
}: {
  pipeStep: PipelineEntry
  idx: number
  isLast: boolean
  slug: string
  caseData: { status: string }
  stepRunning: Record<string, boolean>
  onRun: (s: string) => void
  files: Record<string, unknown> | undefined
}) {
  const caseStatusIdx = getStepIndex(caseData.status)
  const stepStatusIdx = PIPELINE_STEPS.indexOf(pipeStep.status as typeof PIPELINE_STEPS[number])
  const isDone = caseStatusIdx > stepStatusIdx
  const isActive = caseData.status === pipeStep.status
  const isGate = pipeStep.type === 'gate'
  const running = pipeStep.apiStep ? stepRunning[pipeStep.apiStep] : false

  const ak = pipeStep.artifactKey
  const isCountKey = ak === 'characters_count' || ak === 'shorts_script_count' || ak === 'shorts_audio_count'
  const fileInfo = ak && !isCountKey && files
    ? files[ak] as { exists: boolean; size_mb?: number } | undefined
    : undefined
  const countVal = isCountKey && files ? files[ak] as number : null
  const hasArtifact = isCountKey ? (countVal ?? 0) > 0 : fileInfo?.exists

  const dotColor = isDone ? '#22c55e' : isActive ? (isGate ? '#f59e0b' : '#3b82f6') : '#333'
  const lineColor = isDone ? '#22c55e33' : '#1a1a1a'

  return (
    <div className="flex gap-4">
      <div className="flex flex-col items-center flex-shrink-0" style={{ width: '24px' }}>
        <div
          className="w-6 h-6 rounded-full flex items-center justify-center flex-shrink-0 z-10 transition-all"
          style={{
            backgroundColor: isDone ? '#22c55e' : isActive ? (isGate ? '#1a1200' : '#1a2744') : '#111',
            border: `2px solid ${dotColor}`,
            boxShadow: isActive ? `0 0 8px ${dotColor}` : 'none',
          }}
        >
          {isDone ? (
            <span className="text-[10px] text-white">✓</span>
          ) : running ? (
            <div className="w-2 h-2 rounded-full bg-[#3b82f6] animate-ping" />
          ) : isActive ? (
            <div className="w-2 h-2 rounded-full" style={{ backgroundColor: dotColor }} />
          ) : (
            <span className="text-[8px] text-[#555]">{idx + 1}</span>
          )}
        </div>
        {!isLast && (
          <div className="flex-1 w-px mt-1" style={{ backgroundColor: lineColor, minHeight: '24px' }} />
        )}
      </div>

      {isGate ? (
        <Link
          href={`/cases/${slug}/review`}
          className="flex-1 mb-3 rounded-xl p-4 border transition-all block"
          style={{
            backgroundColor: isActive ? '#1a1200' : '#111',
            borderColor: isActive ? `${dotColor}44` : isDone ? '#22c55e11' : '#1e1e1e',
            textDecoration: 'none',
          }}
        >
          <div className="flex items-start justify-between gap-3">
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2">
                <span className="text-sm font-medium" style={{ color: isActive ? '#e0e0e0' : isDone ? '#888' : '#666' }}>
                  {pipeStep.label}
                </span>
                <span className="text-[9px] px-1.5 py-0.5 rounded border border-[#f59e0b44] text-[#f59e0b]">GATE</span>
              </div>
              <div className="text-xs mt-0.5" style={{ color: isActive ? '#888' : '#444' }}>{pipeStep.desc}</div>
            </div>
            {isActive && <span className="text-xs text-[#f59e0b] flex-shrink-0">Open →</span>}
            {isDone && <span className="text-[10px] text-[#22c55e] flex-shrink-0">✓ approved</span>}
          </div>
        </Link>
      ) : (
        <Link
          href={`/cases/${slug}/steps/${pipeStep.id}`}
          className="flex-1 mb-3 rounded-xl p-4 border transition-all block"
          style={{
            backgroundColor: isActive ? '#0d1629' : '#111',
            borderColor: isActive ? `${dotColor}44` : isDone ? '#22c55e11' : '#1e1e1e',
            textDecoration: 'none',
          }}
        >
          <div className="flex items-start justify-between gap-3">
            <div className="flex-1 min-w-0">
              <span className="text-sm font-medium" style={{ color: isActive ? '#e0e0e0' : isDone ? '#888' : '#666' }}>
                {pipeStep.label}
              </span>
              <div className="text-xs mt-0.5" style={{ color: isActive ? '#888' : '#444' }}>{pipeStep.desc}</div>
              {hasArtifact && (
                <div className="mt-1.5 flex items-center gap-1.5">
                  <div className="w-1 h-1 rounded-full bg-[#22c55e]" />
                  <span className="text-[10px] text-[#22c55e]">
                    {isCountKey
                      ? `${countVal} ${ak === 'characters_count' ? 'characters' : ak === 'shorts_script_count' ? 'episode scripts' : 'audio files'}`
                      : fileInfo?.size_mb != null
                        ? `${fileInfo.size_mb.toFixed(1)} MB`
                        : 'artifact present'}
                  </span>
                </div>
              )}
            </div>
            {pipeStep.apiStep && (
              <button
                onClick={(e) => { e.preventDefault(); e.stopPropagation(); pipeStep.apiStep && onRun(pipeStep.apiStep) }}
                disabled={running}
                className="px-3 py-1.5 rounded-lg text-xs font-medium transition-all flex-shrink-0"
                style={{
                  backgroundColor: running ? '#1a2744' : 'transparent',
                  color: running ? '#3b82f6' : isDone ? '#555' : isActive ? '#3b82f6' : '#444',
                  border: `1px solid ${running ? '#3b82f644' : isDone ? '#2a2a2a' : isActive ? '#3b82f633' : '#222'}`,
                }}
              >
                {running ? '⟳ Running...' : isDone ? '↺ Rerun' : '▶ Run'}
              </button>
            )}
          </div>
        </Link>
      )}
    </div>
  )
}

function TrackColumn({ title, color, steps, slug, caseData, stepRunning, onRun, files }: {
  title: string
  color: string
  steps: readonly PipelineEntry[]
  slug: string
  caseData: { status: string }
  stepRunning: Record<string, boolean>
  onRun: (s: string) => void
  files: Record<string, unknown> | undefined
}) {
  return (
    <div className="flex-1 min-w-0 rounded-xl border p-4" style={{ borderColor: `${color}22`, backgroundColor: '#0a0a0a' }}>
      <div className="flex items-center gap-2 mb-4">
        <div className="w-2 h-2 rounded-full" style={{ backgroundColor: color }} />
        <span className="text-[10px] uppercase tracking-wider font-medium" style={{ color }}>{title}</span>
      </div>
      {steps.map((step, i) => (
        <PipelineStepCard
          key={step.id}
          pipeStep={step}
          idx={i}
          isLast={i === steps.length - 1}
          slug={slug}
          caseData={caseData}
          stepRunning={stepRunning}
          onRun={onRun}
          files={files}
        />
      ))}
    </div>
  )
}

function PipelineTab({ slug, caseData, stepRunning, onRun, onApprove, onReject }: {
  slug: string
  caseData: { status: string; name: string }
  stepRunning: Record<string, boolean>
  onRun: (s: string) => void
  onApprove: () => void
  onReject: () => void
}) {
  const { files } = useCaseFiles(slug)

  const sharedSteps = ORDERED_PIPELINE.filter(s => s.track === 'shared')
  const longformSteps = ORDERED_PIPELINE.filter(s => s.track === 'longform')
  const shortsSteps = ORDERED_PIPELINE.filter(s => s.track === 'shorts')
  const filesMap = files as Record<string, unknown> | undefined

  return (
    <div className="max-w-3xl">
      <div className="text-[10px] text-[#555] uppercase tracking-wider mb-3 font-medium">Shared</div>
      <div className="relative mb-1">
        {sharedSteps.map((pipeStep, i) => (
          <PipelineStepCard
            key={pipeStep.id}
            pipeStep={pipeStep}
            idx={i}
            isLast={i === sharedSteps.length - 1}
            slug={slug}
            caseData={caseData}
            stepRunning={stepRunning}
            onRun={onRun}
            files={filesMap}
          />
        ))}
      </div>

      {/* Fork indicator */}
      <div className="flex items-end gap-0 ml-3 mb-4" style={{ height: '24px' }}>
        <div className="w-px h-full bg-[#222]" />
        <div className="flex-1 flex gap-3 pb-0">
          <div className="flex-1 h-3 border-t border-l rounded-tl" style={{ borderColor: '#1a2744' }} />
          <div className="flex-1 h-3 border-t border-r rounded-tr" style={{ borderColor: '#14532d' }} />
        </div>
      </div>

      {/* Two-track columns */}
      <div className="flex gap-4 mb-6">
        <TrackColumn
          title="Long-form"
          color="#3b82f6"
          steps={longformSteps}
          slug={slug}
          caseData={caseData}
          stepRunning={stepRunning}
          onRun={onRun}
          files={filesMap}
        />
        <TrackColumn
          title="Shorts / Reels"
          color="#22c55e"
          steps={shortsSteps}
          slug={slug}
          caseData={caseData}
          stepRunning={stepRunning}
          onRun={onRun}
          files={filesMap}
        />
      </div>

      <div className="mt-2 mb-2 text-xs text-[#555]">Artifacts</div>
      <FileStatusGrid slug={slug} />
    </div>
  )
}

// ---- Review Gate: QA check + Approve/Reject ----
function ReviewGateActions({ slug, onApprove, onReject }: {
  slug: string
  onApprove: () => void
  onReject: () => void
}) {
  const [qaRunning, setQaRunning] = useState(false)
  const [qaResult, setQaResult] = useState<{ passed: boolean; notes: string[] } | null>(null)

  const runQA = async (e: React.MouseEvent) => {
    e.preventDefault()
    e.stopPropagation()
    setQaRunning(true)
    try {
      const res = await api.runStep(slug, 'qa') as { passed: boolean; notes: string | string[] }
      const notes = Array.isArray(res.notes) ? res.notes : [res.notes].filter(Boolean)
      setQaResult({ passed: res.passed, notes })
    } catch {
      setQaResult({ passed: false, notes: ['QA request failed'] })
    } finally {
      setQaRunning(false)
    }
  }

  return (
    <div className="flex flex-col gap-2 items-end flex-shrink-0" onClick={e => e.preventDefault()}>
      {/* QA result badge */}
      {qaResult && (
        <div
          className="text-[10px] px-2 py-1 rounded max-w-xs"
          style={{
            backgroundColor: qaResult.passed ? '#22c55e11' : '#ef444411',
            color: qaResult.passed ? '#22c55e' : '#ef4444',
            border: `1px solid ${qaResult.passed ? '#22c55e33' : '#ef444433'}`,
          }}
        >
          {qaResult.passed ? '✓ QA passed' : '✗ QA issues'}
          {qaResult.notes?.length > 0 && (
            <div className="mt-0.5 text-[#888]">{qaResult.notes.slice(0, 2).join(' · ')}</div>
          )}
        </div>
      )}
      <div className="flex gap-1.5">
        <button
          onClick={runQA}
          disabled={qaRunning}
          className="px-2.5 py-1.5 rounded-lg text-xs transition-colors"
          style={{ backgroundColor: '#111', color: '#888', border: '1px solid #333' }}
        >
          {qaRunning ? '⟳ QA...' : 'Run QA'}
        </button>
        <button
          onClick={(e) => { e.preventDefault(); e.stopPropagation(); onApprove() }}
          className="px-3 py-1.5 rounded-lg text-xs font-medium bg-[#22c55e] text-white hover:bg-[#16a34a]"
        >
          Approve ✓
        </button>
        <button
          onClick={(e) => { e.preventDefault(); e.stopPropagation(); onReject() }}
          className="px-3 py-1.5 rounded-lg text-xs font-medium bg-[#ef4444] text-white hover:bg-[#dc2626]"
        >
          Reject ✗
        </button>
      </div>
    </div>
  )
}

// ---- Script Tab ----
function ScriptTab({ slug }: { slug: string }) {
  const { script, isLoading, mutate: mutateScript } = useScript(slug)
  const [text, setText] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  const [msg, setMsg] = useState('')

  const currentText = text ?? script?.text ?? ''
  const wordCount = currentText.split(/\s+/).filter(Boolean).length
  const durationMin = Math.round(wordCount / 130)

  const save = async () => {
    setSaving(true)
    try {
      await api.saveScript(slug, currentText)
      mutateScript()
      setMsg('Saved ✓')
      setTimeout(() => setMsg(''), 2000)
    } finally {
      setSaving(false)
    }
  }

  const removeOverride = async () => {
    await api.deleteManualScript(slug)
    mutateScript()
    setText(null)
    setMsg('Override removed')
    setTimeout(() => setMsg(''), 2000)
  }

  if (isLoading) return <SkeletonCard className="h-96" />

  return (
    <div>
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-3">
          <span className="text-xs text-[#555]">{wordCount.toLocaleString()} words · ~{durationMin} min</span>
          {script?.source === 'manual' && (
            <span className="text-[10px] px-2 py-0.5 rounded-full bg-[#f59e0b22] text-[#f59e0b]">manual override</span>
          )}
          {script?.source && script.source !== 'manual' && (
            <span className="text-[10px] text-[#555]">source: {script.source}</span>
          )}
        </div>
        <div className="flex items-center gap-2">
          {msg && <span className="text-xs text-[#22c55e]">{msg}</span>}
          {script?.source === 'manual' && (
            <button onClick={removeOverride} className="text-xs text-[#ef4444] hover:text-[#f87171]">
              Remove override
            </button>
          )}
          <button onClick={save} disabled={saving || !currentText}
            className="px-3 py-1.5 rounded-lg text-xs font-medium bg-[#3b82f6] text-white disabled:opacity-50">
            {saving ? 'Saving...' : 'Save override'}
          </button>
        </div>
      </div>
      {script?.qa_notes && (
        <div className="rounded-lg p-3 border border-[#f59e0b33] bg-[#f59e0b0a] mb-3 text-xs text-[#f59e0b]">
          QA: {script.qa_notes}
        </div>
      )}
      <textarea
        value={currentText}
        onChange={e => setText(e.target.value)}
        className="w-full bg-[#0a0a0a] border border-[#222] rounded-xl p-4 text-xs text-[#e0e0e0] font-mono focus:outline-none focus:border-[#333] resize-none"
        style={{ height: 'calc(100vh - 320px)', minHeight: '400px' }}
        placeholder="Script will appear here after generation..."
      />
    </div>
  )
}

// ---- Characters Tab ----
function CharactersTab({ slug }: { slug: string }) {
  const { characters, isLoading, mutate: mutateChars } = useCharacters(slug)
  const [adding, setAdding] = useState(false)
  const [newChar, setNewChar] = useState({ name: '', role: '', notes: '' })
  const [expandedId, setExpandedId] = useState<string | null>(null)
  const [imageUrl, setImageUrl] = useState('')
  const [autoFinding, setAutoFinding] = useState(false)
  const [autoResult, setAutoResult] = useState<string | null>(null)
  const [autoFindingId, setAutoFindingId] = useState<string | null>(null)

  const ROLE_COLORS: Record<string, string> = {
    victim: '#22c55e',
    accused: '#ef4444',
    judge: '#3b82f6',
    lawyer: '#8b5cf6',
    witness: '#f59e0b',
    family: '#f97316',
    police: '#6b7280',
  }

  const addChar = async () => {
    if (!newChar.name) return
    await api.addCharacter(slug, newChar)
    setNewChar({ name: '', role: '', notes: '' })
    setAdding(false)
    mutateChars()
  }

  const addImage = async (id: string) => {
    if (!imageUrl) return
    try {
      await api.addCharacterImageUrl(slug, id, imageUrl)
      setImageUrl('')
      setExpandedId(null)
      setAutoResult('Photo saved ✓')
      mutateChars()
    } catch (e) {
      setAutoResult(`Failed — check URL is a direct image link (.jpg/.png): ${e}`)
    }
  }

  const autoFindAll = async () => {
    setAutoFinding(true)
    setAutoResult(null)
    try {
      const res = await api.autoImageAll(slug) as { found: number; total: number; results: { name: string; found: boolean; wiki_title?: string; skipped?: boolean }[] }
      const found = res.results.filter(r => r.found === true)
      const notFound = res.results.filter(r => r.found === false)
      setAutoResult(`Found ${found.length}/${res.total}: ${found.map(r => r.name).join(', ') || '—'}${notFound.length ? ` · Not found: ${notFound.map(r => r.name).join(', ')}` : ''}`)
      mutateChars()
    } catch (e) {
      setAutoResult(`Error: ${e}`)
    } finally {
      setAutoFinding(false)
    }
  }

  const autoFindOne = async (id: string) => {
    setAutoFindingId(id)
    try {
      const res = await api.autoImageOne(slug, id) as { found: boolean; name: string; wiki_title?: string }
      if (!res.found) setAutoResult(`No Wikipedia photo found for ${res.name}`)
      mutateChars()
    } catch (e) {
      setAutoResult(`Error: ${e}`)
    } finally {
      setAutoFindingId(null)
    }
  }

  if (isLoading) return (
    <div className="grid grid-cols-3 gap-3">
      {[...Array(6)].map((_, i) => <SkeletonCard key={i} className="h-40" />)}
    </div>
  )

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <span className="text-sm text-[#888]">{characters.length} characters</span>
        <div className="flex gap-2">
          {characters.length > 0 && (
            <button onClick={autoFindAll} disabled={autoFinding}
              className="px-3 py-1.5 rounded-lg text-xs font-medium border transition-colors"
              style={{ backgroundColor: '#071a0d', border: '1px solid #22c55e33', color: autoFinding ? '#555' : '#22c55e' }}>
              {autoFinding ? '⟳ Searching Wikipedia…' : '⚡ Auto-find photos'}
            </button>
          )}
          <button onClick={() => setAdding(true)}
            className="px-3 py-1.5 rounded-lg text-xs font-medium bg-[#1a1a1a] border border-[#333] text-[#888] hover:text-[#e0e0e0] hover:border-[#444]">
            + Add Character
          </button>
        </div>
      </div>

      {autoResult && (
        <div className="mb-3 px-3 py-2 rounded-lg text-[11px]"
          style={{ backgroundColor: autoResult.startsWith('Error') ? '#1a0505' : '#071a0d', color: autoResult.startsWith('Error') ? '#ef4444' : '#22c55e' }}>
          {autoResult}
        </div>
      )}

      {characters.length === 0 && !adding && (
        <div className="rounded-xl border border-[#222] bg-[#0a0a0a] p-8 text-center">
          <div className="text-3xl mb-3">👤</div>
          <div className="text-sm text-[#555] mb-1">No characters extracted yet</div>
          <div className="text-[11px] text-[#444] mb-4">Run the Characters step to extract people from the script</div>
          <a href={`/cases/${slug}/steps/characters`}
            className="inline-block px-4 py-2 rounded-lg text-xs font-medium bg-[#1a1a1a] border border-[#333] text-[#888] hover:text-[#e0e0e0]">
            Go to Characters step →
          </a>
        </div>
      )}

      <div className="grid grid-cols-3 gap-3">
        {characters.map((c: Character) => (
          <div key={c.id} className="bg-[#111] rounded-xl p-4 border border-[#222]">
            <div className="flex flex-col items-center text-center">
              <div className="w-16 h-16 rounded-full mb-2 flex items-center justify-center text-2xl overflow-hidden"
                style={{ backgroundColor: '#1a1a1a', border: '2px solid #222' }}>
                {c.image_path ? (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img src={`${API_BASE}/files/cases/${slug}/characters/${c.image_path.split('/').pop()}`}
                    alt={c.name} className="w-full h-full object-cover" />
                ) : <span>👤</span>}
              </div>
              <div className="text-sm font-medium text-[#e0e0e0] mb-1">{c.name}</div>
              {c.role && (
                <span className="text-[10px] px-2 py-0.5 rounded-full"
                  style={{ backgroundColor: `${ROLE_COLORS[c.role] || '#888'}22`, color: ROLE_COLORS[c.role] || '#888' }}>
                  {c.role}
                </span>
              )}
            </div>
            {/* Photo controls */}
            {!c.image_path && (
              <button onClick={() => autoFindOne(c.id)} disabled={autoFindingId === c.id}
                className="mt-3 text-[10px] w-full text-center py-1 rounded"
                style={{ color: autoFindingId === c.id ? '#555' : '#22c55e', backgroundColor: '#071a0d' }}>
                {autoFindingId === c.id ? '⟳ searching…' : '⚡ Find on Wikipedia'}
              </button>
            )}
            <button onClick={() => setExpandedId(expandedId === c.id ? null : c.id)}
              className="mt-1.5 text-[10px] text-[#555] hover:text-[#888] w-full text-center">
              {expandedId === c.id ? '▲ collapse' : c.image_path ? '▼ change photo' : '▼ paste URL'}
            </button>
            {expandedId === c.id && (
              <div className="mt-2 flex gap-1">
                <input value={imageUrl} onChange={e => setImageUrl(e.target.value)}
                  placeholder="Image URL..."
                  className="flex-1 bg-[#0a0a0a] border border-[#333] rounded px-2 py-1 text-[10px] text-[#e0e0e0] focus:outline-none" />
                <button onClick={() => addImage(c.id)} className="px-2 py-1 bg-[#3b82f6] rounded text-[10px] text-white">Add</button>
              </div>
            )}
          </div>
        ))}

        {adding && (
          <div className="bg-[#111] rounded-xl p-4 border border-[#3b82f633]">
            <div className="flex flex-col gap-2">
              <input value={newChar.name} onChange={e => setNewChar(p => ({ ...p, name: e.target.value }))}
                placeholder="Name"
                className="bg-[#0a0a0a] border border-[#333] rounded px-2 py-1.5 text-xs text-[#e0e0e0] focus:outline-none" />
              <select value={newChar.role} onChange={e => setNewChar(p => ({ ...p, role: e.target.value }))}
                className="bg-[#0a0a0a] border border-[#333] rounded px-2 py-1.5 text-xs text-[#e0e0e0] focus:outline-none">
                <option value="">No role</option>
                {Object.keys(ROLE_COLORS).map(r => <option key={r} value={r}>{r}</option>)}
              </select>
              <div className="flex gap-2">
                <button onClick={addChar} className="flex-1 px-2 py-1 bg-[#3b82f6] rounded text-xs text-white">Add</button>
                <button onClick={() => setAdding(false)} className="px-2 py-1 bg-[#333] rounded text-xs text-[#888]">Cancel</button>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

// ---- Audio Tab ----
function AudioTab({ slug }: { slug: string }) {
  const { files, isLoading } = useCaseFiles(slug)
  if (isLoading) return <SkeletonCard className="h-20" />

  const audio = files?.['audio'] as { exists: boolean; size_mb?: number } | undefined
  if (!audio?.exists) return (
    <div className="text-center py-16 text-[#555]">
      No audio yet. Run TTS from the Pipeline tab.
    </div>
  )

  return (
    <div>
      <div className="text-xs text-[#555] mb-4">
        voiceover.mp3{audio.size_mb != null ? ` · ${audio.size_mb.toFixed(1)} MB` : ''}
      </div>
      <audio controls className="w-full" style={{ filter: 'invert(0.9) hue-rotate(180deg)' }}>
        <source src={`${API_BASE}/files/cases/${slug}/audio/voiceover.mp3`} type="audio/mpeg" />
      </audio>
    </div>
  )
}

// ---- Video Tab ----
function VideoTab({ slug }: { slug: string }) {
  const { files, isLoading } = useCaseFiles(slug)
  if (isLoading) return <SkeletonCard className="h-20" />

  const video = files?.['video'] as { exists: boolean; size_mb?: number } | undefined
  if (!video?.exists) return (
    <div className="text-center py-16 text-[#555]">
      No video yet. Run Assemble from the Pipeline tab.
    </div>
  )

  return (
    <div>
      <div className="text-xs text-[#555] mb-4">
        video_final.mp4{video.size_mb != null ? ` · ${video.size_mb.toFixed(1)} MB` : ''}
      </div>
      <video controls className="w-full rounded-xl" style={{ maxHeight: '500px', background: '#000' }}>
        <source src={`${API_BASE}/files/cases/${slug}/output/video_final.mp4`} type="video/mp4" />
      </video>
    </div>
  )
}

// ---- Data Tab ----
function DataTab({ slug }: { slug: string }) {
  const { files } = useCaseFiles(slug)
  const { script } = useScript(slug)
  const [rawData, setRawData] = useState<string | null>(null)
  const [selectedFile, setSelectedFile] = useState<string | null>(null)
  const [loadingRaw, setLoadingRaw] = useState(false)

  const FILE_LINKS = [
    { key: 'research', label: 'research.json', url: `${API_BASE}/files/cases/${slug}/research.json` },
    { key: 'audio', label: 'word_timings.json', url: `${API_BASE}/files/cases/${slug}/audio/word_timings.json` },
    { key: 'script_draft', label: 'script_draft.md', url: null },
    { key: 'script_manual', label: 'script_manual.md', url: null },
  ]

  const loadRaw = async (label: string, url: string | null) => {
    if (!url) {
      if (label.includes('script')) {
        setSelectedFile(label)
        setRawData(script?.text ?? 'No script content')
      }
      return
    }
    setLoadingRaw(true)
    setSelectedFile(label)
    try {
      const r = await fetch(url)
      const text = await r.text()
      setRawData(text)
    } catch (e) {
      setRawData(`Error loading: ${e}`)
    } finally {
      setLoadingRaw(false)
    }
  }

  return (
    <div className="flex gap-4" style={{ height: 'calc(100vh - 220px)' }}>
      {/* File list */}
      <div className="flex flex-col gap-2 flex-shrink-0" style={{ width: '200px' }}>
        <div className="text-xs text-[#555] mb-2">Raw Files</div>
        {FILE_LINKS.map(({ key, label, url }) => {
          const info = files?.[key] as { exists: boolean } | undefined
          const exists = info?.exists ?? false
          return (
            <button
              key={key}
              onClick={() => exists && loadRaw(label, url)}
              disabled={!exists}
              className="text-left px-3 py-2 rounded-lg text-xs transition-colors"
              style={{
                backgroundColor: selectedFile === label ? '#1a2744' : '#111',
                color: exists ? (selectedFile === label ? '#3b82f6' : '#e0e0e0') : '#444',
                border: `1px solid ${selectedFile === label ? '#3b82f633' : '#222'}`,
                cursor: exists ? 'pointer' : 'not-allowed',
              }}>
              {exists ? '📄' : '○'} {label}
            </button>
          )
        })}

        {/* Artifacts summary */}
        <div className="mt-4 text-xs text-[#555] mb-2">Artifacts Summary</div>
        {files && Object.entries(files).map(([k, v]) => {
          if (k === 'slug') return null
          if (typeof v === 'number') return (
            <div key={k} className="text-[10px] text-[#555] px-1">{k}: {v}</div>
          )
          const info = v as { exists: boolean; size_mb?: number }
          return (
            <div key={k} className="text-[10px] px-1" style={{ color: info.exists ? '#22c55e' : '#444' }}>
              {info.exists ? '✓' : '○'} {k}{info.size_mb ? ` (${info.size_mb.toFixed(1)}MB)` : ''}
            </div>
          )
        })}
      </div>

      {/* Raw content viewer */}
      <div className="flex-1 bg-[#0a0a0a] border border-[#222] rounded-xl overflow-hidden">
        {!selectedFile ? (
          <div className="h-full flex items-center justify-center text-[#555] text-sm">
            Select a file to view raw content
          </div>
        ) : loadingRaw ? (
          <div className="h-full flex items-center justify-center text-[#555] text-sm">Loading...</div>
        ) : (
          <div className="h-full overflow-auto p-4">
            <div className="flex items-center justify-between mb-3">
              <span className="text-xs text-[#888] font-mono">{selectedFile}</span>
              <button
                onClick={() => navigator.clipboard.writeText(rawData ?? '')}
                className="text-[10px] text-[#555] hover:text-[#888]">
                Copy
              </button>
            </div>
            <pre className="text-[11px] text-[#e0e0e0] font-mono whitespace-pre-wrap leading-relaxed">
              {rawData}
            </pre>
          </div>
        )}
      </div>
    </div>
  )
}
