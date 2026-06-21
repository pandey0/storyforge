'use client'
import { use, useState, useCallback, useRef } from 'react'
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { api } from '@/lib/api'
import { useScript, useCase, useCheckpoint } from '@/lib/swr-hooks'
import { mutate } from 'swr'

type QAResult = { passed: boolean; notes: string[] }
type Mode = 'read' | 'edit'

export default function ReviewPage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = use(params)
  const router = useRouter()
  const { script, isLoading, mutate: mutateScript } = useScript(slug)
  const { caseData } = useCase(slug)
  const { checkpoint, mutate: mutateCheckpoint } = useCheckpoint(slug, 'script')

  const [qaRunning, setQaRunning] = useState(false)
  const [qaResult, setQaResult] = useState<QAResult | null>(null)
  const [approving, setApproving] = useState(false)
  const [rejecting, setRejecting] = useState(false)
  const [fixing, setFixing] = useState(false)
  const [mode, setMode] = useState<Mode>('read')
  const [editText, setEditText] = useState('')
  const [saving, setSaving] = useState(false)
  const [msg, setMsg] = useState('')
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  const showMsg = (m: string) => { setMsg(m); setTimeout(() => setMsg(''), 4000) }

  const scriptText: string = script?.text ?? ''
  const displayText = mode === 'edit' ? editText : scriptText
  const wordCount = displayText.split(/\s+/).filter(Boolean).length
  const estMinutes = Math.round(wordCount / 130)
  const isGatePassed = caseData?.status &&
    !['queued', 'research', 'scripting', 'human_review'].includes(caseData.status)
  // Approve is only safe once QA has actually run against whatever is
  // currently saved — mirrors the server-side guard in pipeline.py's
  // approve_step (checkpoint status must be "ai_validated").
  const qaValidated = checkpoint?.status === 'ai_validated'
  const approveDisabledReason = isGatePassed
    ? null
    : !scriptText
    ? null
    : !qaValidated
    ? (checkpoint?.status === 'ai_flagged'
        ? 'QA flagged issues — fix and re-run QA before approving'
        : 'Run QA first — script has unvalidated changes')
    : null

  const enterEdit = () => {
    setEditText(scriptText)
    setMode('edit')
    setTimeout(() => textareaRef.current?.focus(), 50)
  }

  const cancelEdit = () => {
    setMode('read')
    setEditText('')
  }

  const saveEdit = useCallback(async () => {
    setSaving(true)
    try {
      const res = await api.saveScript(slug, editText)
      mutateScript()
      mutateCheckpoint()
      // Backend auto-reruns QA on every manual save now — use that result
      // directly instead of clearing and waiting for a manual "Run QA" click.
      if (res.qa_result) {
        const notes = res.qa_result.notes
        setQaResult({
          passed: res.qa_result.passed,
          notes: Array.isArray(notes) ? notes : [notes].filter(Boolean),
        })
        showMsg(res.qa_result.passed ? 'Saved & QA passed ✓' : 'Saved — QA found issues')
      } else {
        setQaResult(null)
        showMsg('Saved as manual override ✓')
      }
      setMode('read')
    } finally {
      setSaving(false)
    }
  }, [slug, editText, mutateScript, mutateCheckpoint])

  const runQA = useCallback(async () => {
    if (qaRunning) return  // idempotent guard
    setQaRunning(true)
    try {
      const res = await api.runStep(slug, 'qa') as { passed: boolean; notes: string | string[] }
      const notes = Array.isArray(res.notes) ? res.notes : [res.notes].filter(Boolean)
      setQaResult({ passed: res.passed, notes })
      mutateCheckpoint()
    } catch (e) {
      setQaResult({ passed: false, notes: [`QA failed: ${e}`] })
    } finally {
      setQaRunning(false)
    }
  }, [slug, qaRunning, mutateCheckpoint])

  // AI fix: saves QA notes to script config then reruns script agent
  const fixWithAI = useCallback(async () => {
    if (!qaResult?.notes.length) return
    setFixing(true)
    try {
      // Save QA notes as fix_notes in script config so agent can pick them up
      await api.saveStepConfig(slug, 'script', {
        fix_notes: qaResult.notes.join('\n'),
        fix_mode: true,
      })
      await api.runStep(slug, 'script')
      showMsg('Script agent running with QA fix instructions…')
      setQaResult(null)
      // Poll for script update — the rerun route now auto-runs QA itself when
      // it finishes, so refresh the checkpoint alongside the script/case data.
      setTimeout(() => { mutateScript(); mutate(`case:${slug}`); mutateCheckpoint() }, 8000)
    } catch (e) {
      showMsg(`Fix failed: ${e}`)
    } finally {
      setFixing(false)
    }
  }, [slug, qaResult, mutateScript, mutateCheckpoint])

  const approve = useCallback(async () => {
    if (approving || isGatePassed) return  // idempotent guard
    setApproving(true)
    try {
      const res = await api.approveGate(slug)
      mutate(`case:${slug}`)
      showMsg(`Approved ✓ → ${res?.new_status ?? 'tts'}`)
      setTimeout(() => router.push(`/cases/${slug}/steps/tts?from=longform`), 1500)
    } catch (e) {
      const message = e instanceof Error ? e.message : String(e)
      if (message.startsWith('400')) {
        // Server-side QA-before-approve guard tripped — surface its detail
        // text directly rather than the raw "400 Bad Request — {...}" string.
        const match = message.match(/detail":\s*"([^"]+)"/)
        showMsg(match ? match[1] : 'Run QA first — script has unvalidated changes')
      } else {
        showMsg(`Approve failed: ${message}`)
      }
      mutateCheckpoint()
    } finally {
      setApproving(false)
    }
  }, [slug, router, approving, isGatePassed, mutateCheckpoint])

  const reject = useCallback(async () => {
    if (rejecting) return  // idempotent guard
    setRejecting(true)
    try {
      await api.rejectGate(slug)
      mutate(`case:${slug}`)
      mutateCheckpoint()
      showMsg('Rejected — back to scripting')
      setTimeout(() => router.push(`/cases/${slug}/steps/script?from=longform`), 1500)
    } catch (e) {
      showMsg(`Reject failed: ${e}`)
    } finally {
      setRejecting(false)
    }
  }, [slug, router, rejecting, mutateCheckpoint])

  return (
    <div className="flex flex-col" style={{ minHeight: '100vh' }}>
      {/* Header */}
      <div className="px-6 py-3 border-b border-[#222] flex-shrink-0">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2 text-xs text-[#555]">
            <Link href={`/longform/${slug}`} className="hover:text-[#888] transition-colors">← {slug}</Link>
            <span>/</span>
            <span className="text-[#e0e0e0]">Review</span>
            <span className="ml-1 text-[10px] px-1.5 py-0.5 rounded border border-[#f59e0b44] text-[#f59e0b]">GATE</span>
          </div>

          <div className="flex items-center gap-2">
            {msg && <span className="text-xs text-[#22c55e] mr-2">{msg}</span>}

            {caseData?.status === 'failed' ? (
              /* Step failed after gate — show retry path, not re-approve */
              <div className="flex items-center gap-2">
                <span className="text-xs text-[#ef4444]">⚠ Step failed</span>
                <Link
                  href={`/cases/${slug}/steps/tts?from=longform`}
                  className="px-3 py-1.5 rounded-lg text-xs font-medium"
                  style={{ backgroundColor: '#1a0505', color: '#ef4444', border: '1px solid #ef444433' }}
                >
                  → Retry TTS
                </Link>
              </div>
            ) : isGatePassed ? (
              <span className="text-xs text-[#22c55e]">✓ Gate passed</span>
            ) : mode === 'edit' ? (
              /* Edit mode header actions */
              <>
                <button onClick={cancelEdit} className="px-3 py-1.5 rounded-lg text-xs text-[#555] border border-[#333]">
                  Cancel
                </button>
                <button
                  onClick={saveEdit}
                  disabled={saving}
                  className="px-3 py-1.5 rounded-lg text-xs font-medium"
                  style={{ backgroundColor: '#1a2744', color: '#3b82f6', border: '1px solid #3b82f633' }}
                >
                  {saving ? 'Saving...' : '💾 Save override'}
                </button>
              </>
            ) : (
              /* Read mode header actions */
              <>
                <button
                  onClick={runQA}
                  disabled={qaRunning || isLoading || !scriptText}
                  className="px-3 py-1.5 rounded-lg text-xs transition-colors"
                  style={{ backgroundColor: '#111', color: '#888', border: '1px solid #333' }}
                >
                  {qaRunning ? '⟳ Running QA...' : 'Run QA'}
                </button>
                <button
                  onClick={enterEdit}
                  disabled={!scriptText}
                  className="px-3 py-1.5 rounded-lg text-xs transition-colors"
                  style={{ backgroundColor: '#111', color: '#888', border: '1px solid #333' }}
                >
                  ✏ Edit
                </button>
                <button
                  onClick={reject}
                  disabled={rejecting}
                  className="px-3 py-1.5 rounded-lg text-xs font-medium"
                  style={{ backgroundColor: '#1a0505', color: '#ef4444', border: '1px solid #ef444433' }}
                >
                  {rejecting ? '...' : '✗ Reject'}
                </button>
                <button
                  onClick={approve}
                  disabled={approving || !scriptText || !qaValidated}
                  title={approveDisabledReason ?? undefined}
                  className="px-4 py-1.5 rounded-lg text-xs font-medium"
                  style={{ backgroundColor: '#052010', color: '#22c55e', border: '1px solid #22c55e44' }}
                >
                  {approving ? '...' : '✓ Approve → TTS'}
                </button>
              </>
            )}
          </div>
        </div>

        {/* Meta */}
        {displayText && (
          <div className="mt-1.5 flex items-center gap-4 text-[10px] text-[#555]">
            <span>{wordCount.toLocaleString()} words</span>
            <span>~{estMinutes} min</span>
            {mode === 'edit' && <span className="text-[#f59e0b]">editing — unsaved</span>}
            {mode === 'read' && approveDisabledReason && (
              <span className="text-[#f59e0b]">⚠ {approveDisabledReason}</span>
            )}
          </div>
        )}
      </div>

      {/* QA result banner — shown when not in edit mode */}
      {qaResult && mode === 'read' && (
        <div
          className="px-6 py-3 flex-shrink-0 border-b"
          style={{
            backgroundColor: qaResult.passed ? '#071a0d' : '#150808',
            borderColor: qaResult.passed ? '#22c55e22' : '#ef444422',
          }}
        >
          <div className="flex items-start justify-between gap-4">
            <div className="flex items-start gap-3">
              <span className="text-sm font-medium flex-shrink-0" style={{ color: qaResult.passed ? '#22c55e' : '#ef4444' }}>
                {qaResult.passed ? '✓ QA Passed' : '✗ QA Issues'}
              </span>
              {qaResult.notes.length > 0 && (
                <div className="flex flex-col gap-1">
                  {qaResult.notes.map((n, i) => (
                    <span key={i} className="text-xs text-[#888]">· {n}</span>
                  ))}
                </div>
              )}
            </div>

            {/* Fix options when QA failed */}
            {!qaResult.passed && (
              <div className="flex gap-2 flex-shrink-0">
                <button
                  onClick={enterEdit}
                  className="px-3 py-1.5 rounded-lg text-xs font-medium"
                  style={{ backgroundColor: '#111', color: '#888', border: '1px solid #333' }}
                >
                  ✏ Fix manually
                </button>
                <button
                  onClick={fixWithAI}
                  disabled={fixing}
                  className="px-3 py-1.5 rounded-lg text-xs font-medium"
                  style={{ backgroundColor: '#0d1a2e', color: '#3b82f6', border: '1px solid #3b82f633' }}
                >
                  {fixing ? '⟳ Fixing...' : '✦ Fix with AI'}
                </button>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Script content */}
      <div className="flex-1 overflow-y-auto">
        {isLoading ? (
          <div className="p-8 text-[#555] text-sm">Loading script…</div>
        ) : !scriptText ? (
          <div className="p-8">
            <div className="text-[#555] text-sm mb-3">No script found.</div>
            <Link href={`/cases/${slug}/steps/script?from=longform`} className="text-xs text-[#3b82f6] hover:underline">
              → Run Script step first
            </Link>
          </div>
        ) : mode === 'edit' ? (
          <textarea
            ref={textareaRef}
            value={editText}
            onChange={e => setEditText(e.target.value)}
            className="w-full h-full p-8 bg-transparent text-sm text-[#d0d0d0] resize-none focus:outline-none leading-8"
            style={{ fontFamily: "'Georgia', serif", minHeight: 'calc(100vh - 200px)' }}
          />
        ) : (
          <div className="max-w-3xl mx-auto px-8 py-8">
            <pre
              className="text-sm text-[#d0d0d0] whitespace-pre-wrap leading-8"
              style={{ fontFamily: "'Georgia', serif" }}
            >
              {scriptText}
            </pre>
          </div>
        )}
      </div>

      {/* Sticky bottom bar — read mode only */}
      {!isGatePassed && scriptText && mode === 'read' && (
        <div
          className="px-6 py-4 flex-shrink-0 flex items-center justify-between border-t border-[#222]"
          style={{ backgroundColor: '#0a0a0a' }}
        >
          <span className="text-xs text-[#555]">
            {approveDisabledReason ? (
              <span className="text-[#f59e0b]">⚠ {approveDisabledReason}</span>
            ) : (
              'Done reading? Choose your verdict.'
            )}
          </span>
          <div className="flex gap-3">
            <button
              onClick={reject}
              disabled={rejecting}
              className="px-4 py-2 rounded-lg text-sm font-medium"
              style={{ backgroundColor: '#1a0505', color: '#ef4444', border: '1px solid #ef444433' }}
            >
              {rejecting ? '...' : '✗ Reject — full rewrite'}
            </button>
            <button
              onClick={approve}
              disabled={approving || !qaValidated}
              title={approveDisabledReason ?? undefined}
              className="px-5 py-2 rounded-lg text-sm font-medium"
              style={{ backgroundColor: '#052010', color: '#22c55e', border: '1px solid #22c55e44' }}
            >
              {approving ? '...' : '✓ Approve — proceed to TTS'}
            </button>
          </div>
        </div>
      )}

      {/* Edit mode bottom bar */}
      {mode === 'edit' && (
        <div
          className="px-6 py-4 flex-shrink-0 flex items-center justify-between border-t border-[#3b82f633]"
          style={{ backgroundColor: '#030d1a' }}
        >
          <span className="text-xs text-[#555]">
            Saved as <code className="text-[#3b82f6]">script_manual.md</code> — overrides AI draft
          </span>
          <div className="flex gap-3">
            <button onClick={cancelEdit} className="px-4 py-2 rounded-lg text-sm text-[#555] border border-[#333]">
              Cancel
            </button>
            <button
              onClick={saveEdit}
              disabled={saving}
              className="px-5 py-2 rounded-lg text-sm font-medium"
              style={{ backgroundColor: '#1a2744', color: '#3b82f6', border: '1px solid #3b82f633' }}
            >
              {saving ? 'Saving...' : '💾 Save & re-check'}
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
