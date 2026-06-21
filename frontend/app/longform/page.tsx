'use client'
import Link from 'next/link'
import { useCases, useCaseFiles } from '@/lib/swr-hooks'
import { Case } from '@/lib/api'
import { statusColor, longformProgress } from '@/lib/pipeline'
import { CaseListSkeleton } from '@/components/Skeleton'

function LongformProgressBar({ slug }: { slug: string }) {
  const { files } = useCaseFiles(slug)
  const { done, total } = longformProgress(files as Record<string, unknown> | undefined)

  return (
    <div className="flex items-center gap-1">
      {Array.from({ length: total }).map((_, i) => (
        <div
          key={i}
          className="h-1.5 flex-1 rounded-full"
          style={{ backgroundColor: i < done ? '#3b82f6' : '#1e1e1e' }}
        />
      ))}
      <span className="text-[10px] text-[#555] ml-2 flex-shrink-0">{done}/{total}</span>
    </div>
  )
}

function LongformCaseCard({ c }: { c: Case }) {
  return (
    <Link
      href={`/longform/${c.slug}`}
      className="bg-[#111] rounded-xl p-4 border border-[#222] hover:border-[#3b82f644] transition-colors block"
    >
      <div className="flex items-center justify-between mb-2">
        <div>
          <span className="font-medium text-[#e0e0e0] text-sm">{c.name}</span>
          {c.subject_name && <span className="text-xs text-[#555] ml-2">{c.subject_name}</span>}
          {c.location && <span className="text-xs text-[#555] ml-2">· {c.location}</span>}
          {c.year_of_crime && <span className="text-xs text-[#555] ml-2">· {c.year_of_crime}</span>}
        </div>
        <span className="text-[10px] px-2 py-0.5 rounded-full"
          style={{ backgroundColor: `${statusColor(c.status)}22`, color: statusColor(c.status) }}>
          {c.status}
        </span>
      </div>
      <LongformProgressBar slug={c.slug} />
    </Link>
  )
}

export default function LongformPage() {
  const { cases, isLoading } = useCases()

  return (
    <div className="p-6">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-xl font-semibold text-[#e0e0e0]">Long-form Studio</h1>
          <p className="text-xs text-[#555] mt-1">30-45 min Hindi documentaries</p>
        </div>
        <Link href="/longform/new"
          className="px-3 py-1.5 rounded-lg text-xs font-medium bg-[#3b82f6] text-white hover:bg-[#2563eb] transition-colors">
          + New Case
        </Link>
      </div>

      {isLoading ? <CaseListSkeleton /> : cases.length === 0 ? (
        <div className="text-center py-16 text-[#555]">
          No cases yet. <Link href="/longform/new" className="text-[#3b82f6]">Create one →</Link>
        </div>
      ) : (
        <div className="flex flex-col gap-2">
          {cases.map(c => <LongformCaseCard key={c.id} c={c} />)}
        </div>
      )}
    </div>
  )
}
