'use client'
import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { useJobs } from '@/lib/swr-hooks'

const NAV = [
  { href: '/', label: 'Home', icon: '▤' },
  { href: '/longform', label: 'Long-form Studio', icon: '📺' },
  { href: '/shorts', label: 'Shorts Studio', icon: '🎬' },
  { href: '/cases', label: 'All Cases', icon: '📁' },
  { href: '/settings/profiles', label: 'Profiles', icon: '◈' },
  { href: '/settings', label: 'Settings', icon: '⚙' },
]

export function Sidebar() {
  const path = usePathname()
  const { jobs } = useJobs()
  const running = jobs.filter(j => j.status === 'running')

  return (
    <div className="flex flex-col border-r border-[#222] bg-[#0f0f0f] flex-shrink-0"
      style={{ width: '220px', height: '100vh', position: 'fixed', left: 0, top: 0 }}>
      <div className="px-4 py-4 border-b border-[#222]">
        <div className="font-semibold text-[#e0e0e0] text-sm">StoryForge</div>
        <div className="text-[10px] text-[#555] mt-0.5">Content Engine</div>
      </div>
      <nav className="flex flex-col gap-0.5 p-2 flex-1">
        {NAV.map(({ href, label, icon }) => {
          const active = href === '/' ? path === '/' : path.startsWith(href) && href !== '/'
          return (
            <Link key={href} href={href}
              className="flex items-center gap-2 px-3 py-2 rounded-lg text-sm transition-colors"
              style={{ backgroundColor: active ? '#1a2744' : 'transparent', color: active ? '#3b82f6' : '#888' }}>
              <span className="text-base w-4">{icon}</span>
              {label}
            </Link>
          )
        })}
      </nav>
      {running.length > 0 && (
        <div className="px-3 py-3 border-t border-[#222]">
          <div className="text-[10px] text-[#555] mb-2 uppercase tracking-wider">Running</div>
          {running.map(job => (
            <div key={job.slug + job.step} className="flex items-center gap-2 py-1">
              <div className="w-1.5 h-1.5 rounded-full bg-[#3b82f6] animate-pulse" />
              <div className="text-xs text-[#888] truncate">
                <span className="text-[#e0e0e0]">{job.step}</span> — {job.slug}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
