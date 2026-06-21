'use client'
import { useCaseFiles } from '@/lib/swr-hooks'

const FILES = [
  { key: 'research', label: 'Research' },
  { key: 'script_draft', label: 'Script Draft' },
  { key: 'script_manual', label: 'Script Override' },
  { key: 'audio', label: 'Audio' },
  { key: 'timings', label: 'Timings' },
  { key: 'video', label: 'Video' },
  { key: 'thumbnail', label: 'Thumbnail' },
]

export function FileStatusGrid({ slug }: { slug: string }) {
  const { files, isLoading } = useCaseFiles(slug)

  if (isLoading) return (
    <div className="grid grid-cols-4 gap-2">
      {FILES.map(({ key }) => (
        <div key={key} className="rounded-lg p-2 border border-[#1a1a1a] bg-[#111] h-12 animate-pulse" />
      ))}
    </div>
  )

  if (!files) return null

  return (
    <div className="grid grid-cols-4 gap-2">
      {FILES.map(({ key, label }) => {
        const info = files[key] as { exists: boolean; size_mb?: number } | undefined
        const exists = info?.exists ?? false
        return (
          <div key={key} className="rounded-lg p-2 border text-xs transition-colors"
            style={{ borderColor: exists ? '#22c55e33' : '#222', backgroundColor: exists ? '#22c55e0a' : '#111' }}>
            <div className="font-medium" style={{ color: exists ? '#22c55e' : '#555' }}>
              {exists ? '✓' : '○'} {label}
            </div>
            {exists && info?.size_mb != null && (
              <div className="text-[10px] text-[#555] mt-0.5">{info.size_mb.toFixed(1)} MB</div>
            )}
          </div>
        )
      })}
      <div className="rounded-lg p-2 border border-[#222] bg-[#111] text-xs">
        <div className="font-medium" style={{ color: (files.characters_count as number) > 0 ? '#22c55e' : '#555' }}>
          {(files.characters_count as number) > 0 ? '✓' : '○'} Characters
        </div>
        <div className="text-[10px] text-[#555] mt-0.5">{files.characters_count as number} found</div>
      </div>
    </div>
  )
}
