'use client'
import { useState, useEffect } from 'react'
import { AgentPanel } from './AgentPanel'

export function LayoutShell({ children }: { children: React.ReactNode }) {
  const [open, setOpen] = useState(true)

  useEffect(() => {
    const saved = localStorage.getItem('agentPanelOpen')
    if (saved !== null) setOpen(saved === 'true')
  }, [])

  const toggle = () => {
    setOpen(prev => {
      const next = !prev
      localStorage.setItem('agentPanelOpen', String(next))
      return next
    })
  }

  const panelW = open ? 320 : 48

  return (
    <>
      <main
        className="flex-1 overflow-y-auto"
        style={{ marginLeft: '220px', marginRight: panelW, minHeight: '100vh' }}
      >
        {children}
      </main>
      <AgentPanel open={open} onToggle={toggle} />
    </>
  )
}
