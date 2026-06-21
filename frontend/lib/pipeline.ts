export const PIPELINE_STEPS = [
  'queued', 'research', 'scripting', 'human_review',
  'tts', 'broll', 'shorts', 'video', 'thumbnail', 'ready', 'published',
] as const

export type PipelineStep = typeof PIPELINE_STEPS[number]

export const STEP_LABELS: Record<string, string> = {
  queued: 'Queued',
  research: 'Research',
  scripting: 'Script',
  qa_review: 'QA',
  human_review: 'Review',
  tts: 'TTS',
  broll: 'B-Roll',
  video: 'Video',
  thumbnail: 'Thumbnail',
  ready: 'Ready',
  published: 'Published',
}

export const RUNNABLE_STEPS = [
  { step: 'research', label: 'Research', desc: 'Scrape sources, court docs, news archive' },
  { step: 'script', label: 'Script', desc: 'Write 30–45 min Hindi documentary script' },
  { step: 'tts', label: 'TTS', desc: 'Generate Hindi voiceover with pause silences' },
  { step: 'characters', label: 'Characters', desc: 'Extract named people from script' },
  { step: 'broll', label: 'B-Roll', desc: 'Fetch stock footage or use character photos' },
  { step: 'assemble', label: 'Assemble', desc: 'Combine audio + b-roll via FFmpeg' },
  { step: 'thumbnail', label: 'Thumbnail', desc: 'Generate DALL-E thumbnail' },
] as const

// track: 'shared'  = runs before the fork — feeds both long-form and shorts
//        'longform' = full 30-45 min documentary track (script → review → broll → tts → assemble → thumbnail)
//        'shorts'   = episodic 9:16 vertical track (self-contained: script+tts+assemble per episode from research.json)
// The two tracks are COMPLETELY INDEPENDENT after research + characters.
export const ORDERED_PIPELINE = [
  // ── Shared (before fork) ─────────────────────────────────────────────────
  {
    id: 'research',
    label: 'Research',
    desc: 'Scrape Indian Kanoon, news archive, Wikipedia → research.json',
    status: 'research',
    apiStep: 'research',
    artifactKey: 'research',
    type: 'step' as const,
    track: 'shared' as const,
  },
  {
    id: 'characters',
    label: 'Characters',
    desc: 'Extract named people, assign roles, add photos',
    status: 'tts',
    apiStep: 'characters',
    artifactKey: 'characters_count',
    type: 'step' as const,
    track: 'shared' as const,
  },
  // ── Long-form track ──────────────────────────────────────────────────────
  {
    id: 'script',
    label: 'Script',
    desc: 'Gemini 2.5 Flash — 30–45 min Hindi documentary script',
    status: 'scripting',
    apiStep: 'script',
    artifactKey: 'script_draft',
    type: 'step' as const,
    track: 'longform' as const,
  },
  {
    id: 'human_review',
    label: 'Review',
    desc: 'AI QA check → human approve/reject before audio production',
    status: 'human_review',
    apiStep: null,
    artifactKey: null,
    type: 'gate' as const,
    track: 'longform' as const,
  },
  {
    id: 'broll',
    label: 'B-Roll',
    desc: 'Fetch stock footage per section (Pexels) → 16:9 clips',
    status: 'broll',
    apiStep: 'broll',
    artifactKey: null,
    type: 'step' as const,
    track: 'longform' as const,
  },
  {
    id: 'tts',
    label: 'TTS Audio',
    desc: 'Sarvam Bulbul v2 — single 30-45 min Hindi voiceover',
    status: 'tts',
    apiStep: 'tts',
    artifactKey: 'audio',
    type: 'step' as const,
    track: 'longform' as const,
  },
  {
    id: 'assemble',
    label: 'Video Assembly',
    desc: 'FFmpeg — audio + b-roll + overlays → H.264 1080p 16:9',
    status: 'video',
    apiStep: 'assemble',
    artifactKey: 'video',
    type: 'step' as const,
    track: 'longform' as const,
  },
  {
    id: 'thumbnail',
    label: 'Thumbnail',
    desc: 'DALL-E 3 + Pillow overlay → 1280×720 JPG',
    status: 'thumbnail',
    apiStep: 'thumbnail',
    artifactKey: 'thumbnail',
    type: 'step' as const,
    track: 'longform' as const,
  },
  // ── Shorts track ─────────────────────────────────────────────────────────
  {
    id: 'shorts_plan',
    label: 'Episode Plan',
    desc: 'Gemini — decides episode count + angles from research.json (no fixed menu)',
    status: 'shorts',
    apiStep: 'shorts_plan',
    artifactKey: 'shorts_plan_count',
    type: 'step' as const,
    track: 'shorts' as const,
  },
  {
    id: 'shorts_script',
    label: 'Episode Scripts',
    desc: 'Gemini — standalone Hindi episode scripts, one per planned episode',
    status: 'shorts',
    apiStep: 'shorts_script',
    artifactKey: 'shorts_script_count',
    type: 'step' as const,
    track: 'shorts' as const,
  },
  {
    id: 'shorts_tts',
    label: 'Episode Audio',
    desc: 'Sarvam Bulbul — per-episode Hindi voiceover (60-90s each)',
    status: 'shorts',
    apiStep: 'shorts_tts',
    artifactKey: 'shorts_audio_count',
    type: 'step' as const,
    track: 'shorts' as const,
  },
  {
    id: 'shorts_assemble',
    label: 'Shorts Assembly',
    desc: 'FFmpeg — blur-box 9:16 + captions + hook frame → vertical .mp4',
    status: 'shorts',
    apiStep: 'shorts_assemble',
    artifactKey: null,
    type: 'step' as const,
    track: 'shorts' as const,
  },
] as const

export function getStepIndex(status: string): number {
  return PIPELINE_STEPS.indexOf(status as PipelineStep)
}

export function statusColor(status: string): string {
  if (['published', 'ready'].includes(status)) return '#22c55e'
  if (status === 'human_review') return '#f59e0b'
  if (status === 'failed') return '#ef4444'
  if (status === 'queued') return '#555555'
  return '#3b82f6'
}

export function isDone(caseStatus: string, step: string): boolean {
  const caseIdx = getStepIndex(caseStatus)
  const stepIdx = getStepIndex(step)
  return stepIdx < caseIdx
}

// ── Step prerequisites ──────────────────────────────────────────────────────
// fileKey: artifact that must exist before this step can run
// afterStatus: case must have passed this pipeline status (for gate enforcement)
// blocking: true = cannot skip — blocks the main production chain
export interface StepPrereq {
  fileKey?: string     // key in /cases/{slug}/files response
  countKey?: string    // key in /files response whose value must be > 0
  afterStatus?: string // case.status must be >= this in PIPELINE_STEPS order
  blocking: boolean
  blockedBy: string    // human-readable previous step label
}

export const STEP_PREREQ: Record<string, StepPrereq> = {
  // shared
  research:   { blocking: true,  blockedBy: '' },
  // long-form track
  script:     { fileKey: 'research',    blocking: true,  blockedBy: 'Research' },
  tts:        { afterStatus: 'human_review', blocking: true,  blockedBy: 'Script + Review gate' },
  characters: { fileKey: 'research', blocking: false, blockedBy: 'Research' },
  broll:      { fileKey: 'script_draft', blocking: false, blockedBy: 'Script' },
  assemble:   { fileKey: 'audio',        blocking: true,  blockedBy: 'TTS Audio' },
  thumbnail:  { blocking: false, blockedBy: '' },
  // shorts track — only needs research.json, fully independent of long-form
  shorts_plan:     { fileKey: 'research',             blocking: true,  blockedBy: 'Research' },
  shorts_script:   { countKey: 'shorts_plan_count',   blocking: true,  blockedBy: 'Episode Plan' },
  shorts_tts:      { countKey: 'shorts_script_count', blocking: true,  blockedBy: 'Episode Scripts' },
  shorts_assemble: { countKey: 'shorts_audio_count',  blocking: true,  blockedBy: 'Episode Audio' },
}

// Next step within each track (for step workspace breadcrumb)
// research has no single next — it branches into two independent tracks
export const NEXT_STEP: Record<string, string | null> = {
  // shared → branches, no linear next
  research:   null,
  characters: null,
  // long-form track
  script:     'human_review',
  human_review: 'broll',
  broll:      'tts',
  tts:        'assemble',
  assemble:   'thumbnail',
  thumbnail:  null,
  // shorts track — linear sub-pipeline
  shorts_plan:     'shorts_script',
  shorts_script:   'shorts_tts',
  shorts_tts:      'shorts_assemble',
  shorts_assemble: null,
}

export const STEP_LABEL: Record<string, string> = {
  research:   'Research',
  script:     'Script',
  tts:        'TTS Audio',
  characters: 'Characters',
  broll:          'B-Roll',
  shorts_plan:     'Episode Plan',
  shorts_script:   'Episode Scripts',
  shorts_tts:      'Episode Audio',
  shorts_assemble: 'Shorts Assembly',
  assemble:        'Video Assembly',
  thumbnail:  'Thumbnail',
}

// ── Track navigation (Home → Long-form Studio | Shorts Studio) ─────────────
// Fixed 7 shorts episode topics — order/slugs must mirror
// src/agents/shorts_script_agent.py `_TOPICS` exactly.
export const SHORTS_TOPICS: { slug: string; label: string }[] = [
  { slug: 'who_was_the_victim', label: 'Who Was the Victim' },
  { slug: 'the_accused',        label: 'The Accused' },
  { slug: 'the_evidence',       label: 'The Evidence' },
  { slug: 'the_trial',          label: 'The Trial' },
  { slug: 'the_verdict',        label: 'The Verdict' },
  { slug: 'systemic_angle',     label: 'Systemic Angle' },
  { slug: 'where_are_they_now', label: 'Where Are They Now' },
]

// The 3-step sub-pipeline that runs per shorts episode.
export const SHORTS_EPISODE_STEPS = [
  { id: 'shorts_script',   label: 'Script' },
  { id: 'shorts_tts',      label: 'Audio' },
  { id: 'shorts_assemble', label: 'Assemble' },
] as const

// Find the filename (if any) for `topicSlug` among a list returned by /files
// (e.g. files.shorts_scripts, files.shorts_audio, files.shorts_episodes).
// Filenames follow `ep{NN}_{topic_slug}.{ext}` — NN varies, suffix doesn't.
export function topicFileMatch(filenames: string[] | undefined, topicSlug: string): string | undefined {
  return filenames?.find(f => f.replace(/\.\w+$/, '').endsWith(`_${topicSlug}`))
}

// Longform progress = how many of the 4 artifact-producing steps have output.
// (human_review is a gate with no artifact; broll has no single artifactKey.)
const LONGFORM_ARTIFACT_KEYS = ['script_draft', 'audio', 'video', 'thumbnail'] as const

export function longformProgress(files: Record<string, unknown> | undefined): { done: number; total: number } {
  const total = LONGFORM_ARTIFACT_KEYS.length
  if (!files) return { done: 0, total }
  const done = LONGFORM_ARTIFACT_KEYS.filter(k => (files[k] as { exists?: boolean } | undefined)?.exists).length
  return { done, total }
}

export function shortsProgress(files: Record<string, unknown> | undefined): { done: number; total: number } {
  const planCount = files?.shorts_plan_count as number | undefined
  const total = planCount && planCount > 0 ? planCount : SHORTS_TOPICS.length
  const done = (files?.shorts_episodes as string[] | undefined)?.length ?? 0
  return { done: Math.min(done, total), total }
}
