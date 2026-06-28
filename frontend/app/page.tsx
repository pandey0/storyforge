'use client'
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { useCases } from '@/lib/swr-hooks'
import { DashboardSkeleton } from '@/components/Skeleton'

export default function Home() {
  const { cases: longformCases, isLoading: lfLoading } = useCases('longform')
  const { cases: shortsCases, isLoading: shLoading } = useCases('shorts')
  const router = useRouter()

  if (lfLoading || shLoading) return <DashboardSkeleton />

  const inProgress = longformCases.filter(c => !['queued', 'published'].includes(c.status)).length

  return (
    <div className="p-6 flex flex-col" style={{ minHeight: '100vh' }}>
      <h1 className="text-xl font-semibold text-[#e0e0e0] mb-1">StoryForge</h1>
      <p className="text-sm text-[#555] mb-8">Pick a track to start working.</p>

      <div className="flex-1 flex items-center justify-center">
        <div className="grid grid-cols-2 gap-6 w-full max-w-5xl">
          <button
            onClick={() => router.push('/longform')}
            className="text-left rounded-xl border p-8 transition-all hover:-translate-y-0.5"
            style={{
              backgroundColor: '#0d1629',
              borderColor: '#3b82f644',
              minHeight: '40vh',
            }}
          >
            <div className="flex flex-col h-full justify-between">
              <div>
                <div className="text-4xl mb-4">📺</div>
                <div className="text-2xl font-semibold mb-2" style={{ color: '#3b82f6' }}>
                  Long-form Studio
                </div>
                <div className="text-sm text-[#888]">30-45 min documentaries</div>
              </div>
              <div className="mt-8">
                <div className="text-3xl font-bold" style={{ color: '#3b82f6' }}>{longformCases.length}</div>
                <div className="text-xs text-[#555] mt-1">
                  {inProgress > 0 ? `${inProgress} in production` : 'cases total'}
                </div>
                <div className="mt-4 text-sm font-medium" style={{ color: '#3b82f6' }}>Open Long-form Studio →</div>
              </div>
            </div>
          </button>

          <button
            onClick={() => router.push('/shorts')}
            className="text-left rounded-xl border p-8 transition-all hover:-translate-y-0.5"
            style={{
              backgroundColor: '#06170d',
              borderColor: '#22c55e44',
              minHeight: '40vh',
            }}
          >
            <div className="flex flex-col h-full justify-between">
              <div>
                <div className="text-4xl mb-4">🎬</div>
                <div className="text-2xl font-semibold mb-2" style={{ color: '#22c55e' }}>
                  Shorts Studio
                </div>
                <div className="text-sm text-[#888]">7 episodic reels per case</div>
              </div>
              <div className="mt-8">
                <div className="text-3xl font-bold" style={{ color: '#22c55e' }}>{shortsCases.length}</div>
                <div className="text-xs text-[#555] mt-1">cases total</div>
                <div className="mt-4 text-sm font-medium" style={{ color: '#22c55e' }}>Open Shorts Studio →</div>
              </div>
            </div>
          </button>
        </div>
      </div>

      <div className="text-center mt-6">
        <Link href="/cases" className="text-xs text-[#555] hover:text-[#888] transition-colors">
          or view all cases across both tracks →
        </Link>
      </div>
    </div>
  )
}
