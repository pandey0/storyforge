const API = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

export interface Case {
  id: string
  slug: string
  name: string
  status: string
  year_of_crime?: number
  location?: string
  subject_name?: string
  updated_at?: string
  notes?: string
  tier?: number
  channel_profile_id?: string
}

export interface CaseProfile {
  slug: string
  name: string
  language: string
  shorts_topics: { slug: string; label: string }[]
  entity_roles: { slug: string; label: string }[]
}

export interface Job {
  slug: string
  step: string
  status: 'running' | 'done' | 'failed'
  started_at: string
  progress?: number
  error?: string
}

export interface Character {
  id: string
  name: string
  role?: string
  image_path?: string
  notes?: string
}

export interface ActionCard {
  id: string
  type: string
  title: string
  description: string
  severity: 'info' | 'warning' | 'error'
  requires_approval: boolean
  payload: Record<string, unknown>
}

export interface AgentMessage {
  role: 'user' | 'assistant'
  content: string
}

export interface ConfigField {
  key: string
  label: string
  type: 'text' | 'number' | 'textarea' | 'select' | 'boolean'
  placeholder?: string
  default?: unknown
  options?: string[]
  min?: number
  max?: number
  step?: number
}

export interface StepConfig {
  schema: ConfigField[]
  values: Record<string, unknown>
}

export interface CaseVersion {
  id: string
  slug: string
  name: string
  status: string
  case_version: number
  pivot_step?: string | null
  is_root: boolean
}

export interface EDLSegment {
  segment_id: string
  start: number
  end: number
  section?: string | null
  source_type: 'auto' | 'broll' | 'character_photo' | 'scene_image'
  source_path?: string | null
}

export interface EDL {
  track: 'longform' | 'shorts'
  topic?: string | null
  segments: EDLSegment[]
}

async function apiFetch(path: string, opts?: RequestInit) {
  const res = await fetch(`${API}${path}`, {
    ...opts,
    headers: { 'Content-Type': 'application/json', ...opts?.headers },
  })
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    throw new Error(`${res.status} ${res.statusText} — ${JSON.stringify(body)}`)
  }
  return res.json()
}

export const api = {
  getCases: (): Promise<Case[]> => apiFetch('/api/cases'),
  getCase: (slug: string) => apiFetch(`/api/cases/${slug}`),
  createCase: (data: Partial<Case> & { name: string }) =>
    apiFetch('/api/cases', { method: 'POST', body: JSON.stringify(data) }),
  updateStatus: (slug: string, status: string) =>
    apiFetch(`/api/cases/${slug}/status`, { method: 'PUT', body: JSON.stringify({ status }) }),
  getFiles: (slug: string) => apiFetch(`/api/cases/${slug}/files`),
  getCaseProfile: (slug: string): Promise<CaseProfile> => apiFetch(`/api/cases/${slug}/profile`),
  getProfiles: (): Promise<{ id: string; slug: string; name: string; language: string }[]> =>
    apiFetch('/api/profiles'),

  runStep: (slug: string, step: string, topic?: string) =>
    apiFetch(`/api/pipeline/${slug}/${step}${topic ? `?topic=${topic}` : ''}`, { method: 'POST' }),
  approveGate: (slug: string) =>
    apiFetch(`/api/pipeline/${slug}/approve`, { method: 'POST' }),
  rejectGate: (slug: string) =>
    apiFetch(`/api/pipeline/${slug}/reject`, { method: 'POST' }),
  getJobs: (): Promise<Job[]> => apiFetch('/api/pipeline/jobs'),
  getJob: (slug: string): Promise<Job | null> =>
    apiFetch(`/api/pipeline/${slug}/job`).catch(() => null),

  getScript: (slug: string) => apiFetch(`/api/scripts/${slug}`),
  saveScript: (slug: string, text: string) =>
    apiFetch(`/api/scripts/${slug}`, { method: 'PUT', body: JSON.stringify({ text }) }),
  deleteManualScript: (slug: string) =>
    apiFetch(`/api/scripts/${slug}/manual`, { method: 'DELETE' }),

  getCharacters: (slug: string): Promise<Character[]> =>
    apiFetch(`/api/characters/${slug}`),
  addCharacter: (slug: string, data: { name: string; role?: string; notes?: string }) =>
    apiFetch(`/api/characters/${slug}`, { method: 'POST', body: JSON.stringify(data) }),
  updateCharacter: (slug: string, id: string, data: { role?: string; notes?: string }) =>
    apiFetch(`/api/characters/${slug}/${id}`, { method: 'PUT', body: JSON.stringify(data) }),
  deleteCharacter: (slug: string, id: string) =>
    apiFetch(`/api/characters/${slug}/${id}`, { method: 'DELETE' }),
  addCharacterImageUrl: (slug: string, id: string, url: string) =>
    apiFetch(`/api/characters/${slug}/${id}/image-url`, {
      method: 'POST',
      body: JSON.stringify({ url }),
    }),
  autoImageOne: (slug: string, id: string) =>
    apiFetch(`/api/characters/${slug}/${id}/auto-image`, { method: 'POST' }),
  autoImageAll: (slug: string) =>
    apiFetch(`/api/characters/${slug}/auto-image-all`, { method: 'POST' }),

  sendAgentMessage: (
    message: string,
    case_slug: string | null,
    history: AgentMessage[]
  ) =>
    apiFetch('/api/agent/chat', {
      method: 'POST',
      body: JSON.stringify({ message, case_slug, history }),
    }),
  getAgentStatus: () => apiFetch('/api/agent/status'),
  executeAction: (action_id: string) =>
    apiFetch('/api/agent/execute', { method: 'POST', body: JSON.stringify({ action_id }) }),

  logStreamUrl: (slug: string) => `${API}/api/logs/${slug}/stream`,
  getLogTail: (slug: string) => apiFetch(`/api/logs/${slug}/tail`),

  getStepConfig: (slug: string, step: string): Promise<StepConfig> =>
    apiFetch(`/api/steps/${slug}/${step}/config`),
  saveStepConfig: (slug: string, step: string, config: Record<string, unknown>) =>
    apiFetch(`/api/steps/${slug}/${step}/config`, { method: 'PUT', body: JSON.stringify({ config }) }),

  getCaseVersions: (slug: string): Promise<{ root_slug: string; versions: CaseVersion[] }> =>
    apiFetch(`/api/cases/${slug}/versions`),
  branchCase: (slug: string, pivot_step: string, reason?: string): Promise<CaseVersion & { files_copied: string[] }> =>
    apiFetch(`/api/cases/${slug}/branch`, { method: 'POST', body: JSON.stringify({ pivot_step, reason }) }),

  getAudioInfo: (slug: string) => apiFetch(`/api/audio/${slug}/info`),
  processAudio: (slug: string, settings: { tempo?: number; pitch?: number; volume?: number; preview_only?: boolean }) =>
    apiFetch(`/api/audio/${slug}/process`, { method: 'POST', body: JSON.stringify(settings) }),
  resetAudio: (slug: string) =>
    apiFetch(`/api/audio/${slug}/reset`, { method: 'POST' }),

  getEdl: (slug: string, track: 'longform' | 'shorts', topic?: string): Promise<EDL> =>
    apiFetch(`/api/edl/${slug}?track=${track}${topic ? `&topic=${topic}` : ''}`),
  saveEdl: (slug: string, edl: EDL) =>
    apiFetch(`/api/edl/${slug}`, { method: 'PUT', body: JSON.stringify(edl) }),
}
