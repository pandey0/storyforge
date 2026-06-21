'use client'
import { ActionCard as ActionCardType } from '@/lib/api'

interface Props {
  action: ActionCardType
  onExecute: (id: string) => void
  onDismiss: (id: string) => void
}

const SEVERITY_COLORS: Record<string, string> = {
  error: '#ef4444',
  warning: '#f59e0b',
  info: '#3b82f6',
}

export function ActionCard({ action, onExecute, onDismiss }: Props) {
  const color = SEVERITY_COLORS[action.severity] || '#3b82f6'
  return (
    <div
      className="rounded-lg p-3 border text-xs"
      style={{ borderColor: color, backgroundColor: `${color}11` }}
    >
      <div className="font-medium text-[#e0e0e0] mb-1">{action.title}</div>
      <div className="text-[#888] mb-2">{action.description}</div>
      <div className="flex gap-2">
        {action.requires_approval && (
          <button
            onClick={() => onExecute(action.id)}
            className="px-2 py-1 rounded text-xs font-medium bg-[#22c55e] text-white"
          >
            Approve &#x2713;
          </button>
        )}
        <button
          onClick={() => onDismiss(action.id)}
          className="px-2 py-1 rounded text-xs font-medium bg-[#333] text-[#888]"
        >
          Dismiss
        </button>
      </div>
    </div>
  )
}
