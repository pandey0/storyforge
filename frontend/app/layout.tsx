import type { Metadata } from 'next'
import { Geist, Geist_Mono } from 'next/font/google'
import './globals.css'
import { Sidebar } from '@/components/Sidebar'
import { LayoutShell } from '@/components/LayoutShell'

const geistSans = Geist({
  variable: '--font-geist-sans',
  subsets: ['latin'],
})

const geistMono = Geist_Mono({
  variable: '--font-geist-mono',
  subsets: ['latin'],
})

export const metadata: Metadata = {
  title: 'StoryForge',
  description: 'AI content production engine — research to video',
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`dark ${geistSans.variable} ${geistMono.variable}`}>
      <body style={{ background: '#0a0a0a', margin: 0 }}>
        <div className="flex min-h-screen">
          <Sidebar />
          <LayoutShell>{children}</LayoutShell>
        </div>
      </body>
    </html>
  )
}
