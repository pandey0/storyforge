export function SkeletonCard({ className = '' }: { className?: string }) {
  return (
    <div className={`bg-[#111] rounded-xl border border-[#1a1a1a] animate-pulse ${className}`} />
  )
}

export function SkeletonText({ width = 'w-full', className = '' }: { width?: string; className?: string }) {
  return (
    <div className={`h-3 bg-[#1a1a1a] rounded animate-pulse ${width} ${className}`} />
  )
}

export function DashboardSkeleton() {
  return (
    <div className="p-6">
      <div className="h-6 bg-[#1a1a1a] rounded w-32 mb-6 animate-pulse" />
      <div className="grid grid-cols-4 gap-4 mb-8">
        {[...Array(4)].map((_, i) => (
          <SkeletonCard key={i} className="h-20" />
        ))}
      </div>
      <div className="h-4 bg-[#1a1a1a] rounded w-24 mb-3 animate-pulse" />
      <div className="grid grid-cols-2 gap-4">
        {[...Array(4)].map((_, i) => (
          <SkeletonCard key={i} className="h-36" />
        ))}
      </div>
    </div>
  )
}

export function CaseListSkeleton() {
  return (
    <div className="flex flex-col gap-2">
      {[...Array(6)].map((_, i) => (
        <SkeletonCard key={i} className="h-16" />
      ))}
    </div>
  )
}
