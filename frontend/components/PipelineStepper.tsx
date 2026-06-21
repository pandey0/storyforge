'use client'
import { PIPELINE_STEPS, STEP_LABELS, getStepIndex, statusColor } from '@/lib/pipeline'

interface Props {
  status: string
  compact?: boolean
}

export function PipelineStepper({ status, compact = false }: Props) {
  const currentIdx = getStepIndex(status)

  if (compact) {
    return (
      <div className="flex items-center gap-1 flex-wrap">
        {PIPELINE_STEPS.map((step, i) => {
          const done = i < currentIdx
          const active = i === currentIdx
          return (
            <div
              key={step}
              className="h-1.5 rounded-full transition-all"
              style={{
                width: '18px',
                backgroundColor: done ? '#22c55e' : active ? statusColor(status) : '#333',
              }}
              title={STEP_LABELS[step]}
            />
          )
        })}
      </div>
    )
  }

  return (
    <div className="flex items-center gap-0 overflow-x-auto pb-1">
      {PIPELINE_STEPS.map((step, i) => {
        const done = i < currentIdx
        const active = i === currentIdx
        const color = done ? '#22c55e' : active ? statusColor(status) : '#333'
        return (
          <div key={step} className="flex items-center">
            <div className="flex flex-col items-center">
              <div
                className="w-3 h-3 rounded-full flex-shrink-0"
                style={{
                  backgroundColor: color,
                  boxShadow: active ? `0 0 8px ${color}` : 'none',
                }}
              />
              <span
                className="text-[9px] mt-1 whitespace-nowrap"
                style={{ color: active ? color : done ? '#22c55e' : '#555' }}
              >
                {STEP_LABELS[step]}
              </span>
            </div>
            {i < PIPELINE_STEPS.length - 1 && (
              <div
                className="h-px w-6 flex-shrink-0 mb-3"
                style={{ backgroundColor: done ? '#22c55e' : '#333' }}
              />
            )}
          </div>
        )
      })}
    </div>
  )
}
