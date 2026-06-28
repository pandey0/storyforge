'use client'
import Link from 'next/link'
import { useCases } from '@/lib/swr-hooks'
import { PipelineStepper } from '@/components/PipelineStepper'
import { statusColor, PIPELINE_STEPS } from '@/lib/pipeline'
import { CaseListSkeleton } from '@/components/Skeleton'
import { useState } from 'react'

const STATUS_LABELS: Record<string, string> = {
  queued: 'Queued',
  research: 'Researching',
  scripting: 'Writing Script',
  human_review: 'Awaiting Review',
  tts: 'Generating Audio',
  broll: 'Gathering Footage',
  assembling: 'Assembling Video',
  thumbnail: 'Making Thumbnail',
  publishing: 'Publishing',
  published: 'Published',
  failed: 'Failed',
}

export default function CasesPage() {
  const { cases, isLoading } = useCases()
  const [filter, setFilter] = useState('all')

  const filtered = filter === 'all' ? cases : cases.filter(c => c.status === filter)

  return (
    <div className="p-6">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-xl font-semibold text-[#e0e0e0]">Cases</h1>
        <div className="flex items-center gap-3">
          <select value={filter} onChange={e => setFilter(e.target.value)}
            className="bg-[#111] border border-[#333] rounded-lg px-3 py-1.5 text-xs text-[#e0e0e0] focus:outline-none focus:border-[#3b82f6]">
            <option value="all">All Statuses</option>
            {PIPELINE_STEPS.map(s => <option key={s} value={s}>{STATUS_LABELS[s] ?? s}</option>)}
          </select>
        </div>
      </div>

      {isLoading ? <CaseListSkeleton /> : filtered.length === 0 ? (
        <div className="text-[#555] text-sm">
          No cases found. Create one from{' '}
          <Link href="/longform" className="text-[#3b82f6]">Long-form Studio</Link> or{' '}
          <Link href="/shorts" className="text-[#22c55e]">Shorts Studio</Link>.
        </div>
      ) : (
        <div className="flex flex-col gap-2">
          {filtered.map(c => (
            <Link key={c.id} href={`/cases/${c.slug}`}
              className="bg-[#111] rounded-xl p-4 border border-[#222] hover:border-[#333] transition-colors block">
              <div className="flex items-center justify-between mb-2">
                <div>
                  <span className="font-medium text-[#e0e0e0] text-sm">{c.name}</span>
                  {c.subject_name && <span className="text-xs text-[#555] ml-2">{c.subject_name}</span>}
                  {c.location && <span className="text-xs text-[#555] ml-2">· {c.location}</span>}
                  {c.year_of_crime && <span className="text-xs text-[#555] ml-2">· {c.year_of_crime}</span>}
                </div>
                <div className="flex items-center gap-3">
                  <span className="text-[10px] px-2 py-0.5 rounded-full"
                    style={{ backgroundColor: `${statusColor(c.status)}22`, color: statusColor(c.status) }}>
                    {STATUS_LABELS[c.status] ?? c.status}
                  </span>
                  {c.updated_at && (
                    <span className="text-[10px] text-[#555]">
                      {new Date(c.updated_at).toLocaleDateString()}
                    </span>
                  )}
                </div>
              </div>
              <PipelineStepper status={c.status} compact />
            </Link>
          ))}
        </div>
      )}
    </div>
  )
}
