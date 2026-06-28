'use client'
import { useState, useEffect, useRef } from 'react'
import { api, ActionCard as ActionCardType, AgentMessage } from '@/lib/api'
import { ActionCard } from './ActionCard'

interface Props {
  caseSlug?: string
  open?: boolean
  onToggle?: () => void
}

export function AgentPanel({ caseSlug, open = true, onToggle }: Props) {
  const [messages, setMessages] = useState<AgentMessage[]>([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [actionCards, setActionCards] = useState<ActionCardType[]>([])
  const [toolCalls, setToolCalls] = useState<string[]>([])
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const check = () => {
      api.getAgentStatus().then((data: { notifications: unknown[]; pending_actions: Record<string, ActionCardType> }) => {
        const pending = Object.values(data.pending_actions || {})
        setActionCards(prev => {
          const existingIds = new Set(prev.map(a => a.id))
          const newCards = pending.filter((a) => !existingIds.has(a.id))
          return newCards.length ? [...prev, ...newCards] : prev
        })
      }).catch(() => {})
    }
    check()
    const t = setInterval(check, 30000)
    return () => clearInterval(t)
  }, [])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, actionCards])

  const send = async () => {
    const msg = input.trim()
    if (!msg || loading) return
    setInput('')
    const userMsg: AgentMessage = { role: 'user', content: msg }
    setMessages(prev => [...prev, userMsg])
    setLoading(true)
    try {
      const res = await api.sendAgentMessage(msg, caseSlug || null, [...messages, userMsg])
      setMessages(prev => [...prev, { role: 'assistant', content: res.reply }])
      setToolCalls(res.tool_calls || [])
      if (res.action_cards?.length) {
        setActionCards(prev => [...prev, ...res.action_cards])
      }
    } catch (e) {
      setMessages(prev => [...prev, { role: 'assistant', content: `Error: ${e}` }])
    } finally {
      setLoading(false)
    }
  }

  const executeAction = async (id: string) => {
    try {
      await api.executeAction(id)
      setActionCards(prev => prev.filter(a => a.id !== id))
    } catch (e) {
      alert(`Failed: ${e}`)
    }
  }

  const dismissAction = (id: string) => setActionCards(prev => prev.filter(a => a.id !== id))

  if (!open) {
    return (
      <div
        className="flex flex-col items-center border-l border-[#222] bg-[#0f0f0f]"
        style={{ width: '48px', height: '100vh', position: 'fixed', right: 0, top: 0 }}
      >
        <button
          onClick={onToggle}
          title="Open Agent"
          className="mt-4 flex flex-col items-center gap-1 text-[#555] hover:text-[#e0e0e0] transition-colors"
        >
          <div className="w-2 h-2 rounded-full bg-[#22c55e]" style={{ boxShadow: '0 0 6px #22c55e' }} />
          <span className="text-[9px] mt-1" style={{ writingMode: 'vertical-rl', transform: 'rotate(180deg)' }}>⚡ Agent</span>
        </button>
      </div>
    )
  }

  return (
    <div
      className="flex flex-col border-l border-[#222] bg-[#0f0f0f]"
      style={{ width: '320px', height: '100vh', position: 'fixed', right: 0, top: 0 }}
    >
      {/* Header */}
      <div className="flex items-center gap-2 px-4 py-3 border-b border-[#222]">
        <div className="w-2 h-2 rounded-full bg-[#22c55e]" style={{ boxShadow: '0 0 6px #22c55e' }} />
        <span className="text-sm font-medium text-[#e0e0e0]">&#x26A1; Agent</span>
        {caseSlug && (
          <span className="text-xs text-[#555] ml-2">/{caseSlug}</span>
        )}
        <button
          onClick={onToggle}
          title="Collapse"
          className="ml-auto text-[#555] hover:text-[#e0e0e0] transition-colors text-sm leading-none"
        >
          ›
        </button>
      </div>

      {/* Action cards */}
      {actionCards.length > 0 && (
        <div className="p-3 border-b border-[#222] flex flex-col gap-2">
          {actionCards.map(card => (
            <ActionCard
              key={card.id}
              action={card}
              onExecute={executeAction}
              onDismiss={dismissAction}
            />
          ))}
        </div>
      )}

      {/* Messages */}
      <div className="flex-1 overflow-y-auto p-3 flex flex-col gap-3">
        {messages.length === 0 && (
          <div className="text-[#555] text-xs text-center mt-8">
            Ask anything about the pipeline.<br />
            I can see logs, trigger steps, diagnose failures.
          </div>
        )}
        {messages.map((m, i) => (
          <div key={i} className={`flex ${m.role === 'user' ? 'justify-end' : 'justify-start'}`}>
            <div
              className="rounded-lg px-3 py-2 text-xs max-w-[90%] whitespace-pre-wrap"
              style={{
                backgroundColor: m.role === 'user' ? '#1d4ed8' : '#1a1a1a',
                color: '#e0e0e0',
              }}
            >
              {m.content}
            </div>
          </div>
        ))}
        {loading && (
          <div className="flex justify-start">
            <div className="rounded-lg px-3 py-2 text-xs bg-[#1a1a1a] text-[#888]">
              {toolCalls.length > 0 && (
                <div className="flex flex-wrap gap-1 mb-1">
                  {toolCalls.map((t, i) => (
                    <span key={i} className="bg-[#222] text-[#888] px-1.5 py-0.5 rounded text-[10px]">
                      [{t} &#x2713;]
                    </span>
                  ))}
                </div>
              )}
              <span className="animate-pulse">Thinking...</span>
            </div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      {/* Input */}
      <div className="p-3 border-t border-[#222]">
        <div className="flex gap-2">
          <textarea
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={e => {
              if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send() }
            }}
            placeholder="Ask the agent..."
            rows={2}
            className="flex-1 bg-[#111] border border-[#333] rounded-lg px-3 py-2 text-xs text-[#e0e0e0] placeholder-[#555] resize-none focus:outline-none focus:border-[#3b82f6]"
          />
          <button
            onClick={send}
            disabled={loading || !input.trim()}
            className="px-3 py-2 rounded-lg text-xs font-medium transition-colors"
            style={{ backgroundColor: loading ? '#333' : '#3b82f6', color: '#fff' }}
          >
            &#x21B5;
          </button>
        </div>
      </div>
    </div>
  )
}
