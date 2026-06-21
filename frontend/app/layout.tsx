import type { Metadata } from 'next'
import { Geist, Geist_Mono } from 'next/font/google'
import './globals.css'
import { Sidebar } from '@/components/Sidebar'
import { AgentPanel } from '@/components/AgentPanel'

const geistSans = Geist({
  variable: '--font-geist-sans',
  subsets: ['latin'],
})

const geistMono = Geist_Mono({
  variable: '--font-geist-mono',
  subsets: ['latin'],
})

export const metadata: Metadata = {
  title: 'IndianCrimes Pipeline',
  description: 'Hindi True Crime YouTube Pipeline',
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`dark ${geistSans.variable} ${geistMono.variable}`}>
      <body style={{ background: '#0a0a0a', margin: 0 }}>
        <div className="flex min-h-screen">
          <Sidebar />
          <main
            className="flex-1 overflow-y-auto"
            style={{ marginLeft: '220px', marginRight: '320px', minHeight: '100vh' }}
          >
            {children}
          </main>
          <AgentPanel />
        </div>
      </body>
    </html>
  )
}
