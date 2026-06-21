'use client'
import Link from 'next/link'
import { useCases } from '@/lib/swr-hooks'
import { useCaseFiles } from '@/lib/swr-hooks'
import { shortsProgress } from '@/lib/pipeline'
import { CaseListSkeleton } from '@/components/Skeleton'

const ACCENT = '#22c55e'

export default function ShortsStudioPage() {
  const { cases, isLoading } = useCases()

  return (
    <div className="p-6">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-xl font-semibold text-[#e0e0e0]">
          Shorts <span style={{ color: ACCENT }}>Studio</span>
        </h1>
        <Link
          href="/shorts/new"
          className="px-3 py-1.5 rounded-lg text-xs font-medium text-white transition-colors"
          style={{ backgroundColor: ACCENT }}
        >
          + New Case
        </Link>
      </div>

      {isLoading ? (
        <CaseListSkeleton />
      ) : cases.length === 0 ? (
        <div className="rounded-xl border border-[#222] bg-[#111] p-10 text-center">
          <div className="text-sm text-[#888] mb-3">No cases yet.</div>
          <Link href="/shorts/new" className="text-sm" style={{ color: ACCENT }}>
            Create your first case →
          </Link>
        </div>
      ) : (
        <div className="grid gap-3" style={{ gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))' }}>
          {cases.map(c => (
            <Link
              key={c.id}
              href={`/shorts/${c.slug}`}
              className="bg-[#111] rounded-xl p-4 border border-[#222] hover:border-[#22c55e33] transition-colors block"
            >
              <div className="mb-2">
                <div className="font-medium text-[#e0e0e0] text-sm">{c.name}</div>
                {(c.subject_name || c.location || c.year_of_crime) && (
                  <div className="text-xs text-[#555] mt-0.5">
                    {[c.subject_name, c.location, c.year_of_crime].filter(Boolean).join(' · ')}
                  </div>
                )}
              </div>
              <ShortsProgress slug={c.slug} />
            </Link>
          ))}
        </div>
      )}
    </div>
  )
}

function ShortsProgress({ slug }: { slug: string }) {
  const { files } = useCaseFiles(slug)
  const filesMap = files as Record<string, unknown> | undefined
  const { done, total } = shortsProgress(filesMap)

  return (
    <div>
      <div className="flex items-center justify-between mb-1.5">
        <span className="text-[10px] text-[#555]">{done}/{total} episodes assembled</span>
      </div>
      <div className="flex gap-1">
        {Array.from({ length: total }).map((_, i) => (
          <div
            key={i}
            className="flex-1 h-1.5 rounded-full"
            style={{ backgroundColor: i < done ? ACCENT : '#1e1e1e' }}
          />
        ))}
      </div>
    </div>
  )
}
