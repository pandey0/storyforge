import useSWR from 'swr'
import { api, Case, CaseProfile, Character, Job, StepConfig, CaseVersion, Checkpoint, ResearchResponse } from './api'

export function useCases(track?: 'longform' | 'shorts') {
  const { data, error, isLoading, mutate } = useSWR(
    track ? `cases:${track}` : 'cases',
    () => api.getCases(track),
    { refreshInterval: 15000 }
  )
  return { cases: (data ?? []) as Case[], error, isLoading, mutate }
}

export function useCase(slug: string) {
  const { data, error, isLoading, mutate } = useSWR(
    slug ? `case:${slug}` : null,
    () => api.getCase(slug),
    { refreshInterval: 8000, revalidateOnFocus: true, revalidateOnMount: true }
  )
  return { caseData: (data ?? null) as Case | null, error, isLoading, mutate }
}

export function useCaseProfile(slug: string) {
  const { data, error, isLoading } = useSWR(
    slug ? `profile:${slug}` : null,
    () => api.getCaseProfile(slug).catch(() => null),
    { revalidateOnFocus: false }
  )
  return { profile: (data ?? null) as CaseProfile | null, error, isLoading }
}

export function useCheckpoint(slug: string, step: string) {
  const { data, error, isLoading, mutate } = useSWR(
    slug && step ? `checkpoint:${slug}:${step}` : null,
    () => api.getCheckpoint(slug, step).catch(() => null),
    { revalidateOnFocus: false }
  )
  return { checkpoint: (data ?? null) as Checkpoint | null, error, isLoading, mutate }
}

export function useResearch(slug: string) {
  const { data, error, isLoading, mutate } = useSWR(
    slug ? `research:${slug}` : null,
    () => api.getResearch(slug).catch(() => null),
    { revalidateOnFocus: false }
  )
  return { research: (data ?? null) as ResearchResponse | null, error, isLoading, mutate }
}

export interface EpisodeCard {
  slug: string
  label: string
  hook_text: string
  angle: string
  broll_query: string
  role_hint: string | null
  cta: string
}

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

export function useShortsPlan(slug: string) {
  const { data, error, isLoading, mutate } = useSWR(
    slug ? `shorts_plan:${slug}` : null,
    () => fetch(`${API_BASE}/files/cases/${slug}/shorts_plan.json`)
      .then(r => (r.ok ? r.json() : null))
      .catch(() => null),
    { revalidateOnFocus: false }
  )
  return { plan: (data ?? null) as EpisodeCard[] | null, error, isLoading, mutate }
}

export interface WordTimingSegment {
  segment_idx: number
  section: string
  text_preview: string
  start_sec: number
  end_sec: number
}

// Longform: data/cases/{slug}/audio/word_timings.json
// Shorts: data/cases/{slug}/shorts/ep{NN}_{topic}_timings.json — caller passes
// the exact filename (resolved from useCaseFiles' shorts_audio listing) since
// the episode number prefix isn't known client-side ahead of time.
export function useWordTimings(slug: string, track: 'longform' | 'shorts', filename?: string) {
  const path = track === 'longform'
    ? `audio/word_timings.json`
    : filename ? `shorts/${filename}` : null
  const key = slug && path ? `word_timings:${slug}:${path}` : null
  const { data, error, isLoading, mutate } = useSWR(
    key,
    () => fetch(`${API_BASE}/files/cases/${slug}/${path}`)
      .then(r => (r.ok ? r.json() : null))
      .catch(() => null),
    { revalidateOnFocus: false }
  )
  return { timings: (data ?? null) as WordTimingSegment[] | null, error, isLoading, mutate }
}

export function useCaseFiles(slug: string) {
  const { data, error, isLoading, mutate } = useSWR(
    slug ? `files:${slug}` : null,
    () => api.getFiles(slug),
    { refreshInterval: 10000 }
  )
  return { files: data ?? null, error, isLoading, mutate }
}

export function useJobs() {
  const { data, isLoading } = useSWR(
    'jobs',
    () => api.getJobs(),
    { refreshInterval: 5000 }
  )
  return { jobs: (data ?? []) as Job[], isLoading }
}

export function useJob(slug: string) {
  const { data } = useSWR(
    slug ? `job:${slug}` : null,
    () => api.getJob(slug),
    { refreshInterval: 3000 }
  )
  return { job: (data ?? null) as Job | null }
}

export function useScript(slug: string) {
  const { data, isLoading, mutate } = useSWR(
    slug ? `script:${slug}` : null,
    () => api.getScript(slug),
    { revalidateOnFocus: false }
  )
  return { script: data ?? null, isLoading, mutate }
}

export function useCharacters(slug: string) {
  const { data, isLoading, mutate } = useSWR(
    slug ? `chars:${slug}` : null,
    () => api.getCharacters(slug),
    { refreshInterval: 30000 }
  )
  return { characters: (data ?? []) as Character[], isLoading, mutate }
}

export function useStepConfig(slug: string, step: string) {
  const { data, isLoading, mutate } = useSWR(
    slug && step ? `stepconfig:${slug}:${step}` : null,
    () => api.getStepConfig(slug, step),
    { revalidateOnFocus: false }
  )
  const d = (data ?? null) as StepConfig | null
  return { schema: d?.schema ?? [], config: d?.values ?? {}, isLoading, mutate }
}

export function useCaseVersions(slug: string) {
  const { data, isLoading, mutate } = useSWR(
    slug ? `versions:${slug}` : null,
    () => api.getCaseVersions(slug).catch(() => null),
    { refreshInterval: 30000 }
  )
  const d = data as { root_slug: string; versions: CaseVersion[] } | null
  return { versions: d?.versions ?? [] as CaseVersion[], rootSlug: d?.root_slug ?? null, isLoading, mutate }
}
