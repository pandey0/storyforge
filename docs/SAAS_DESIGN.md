# SaaS Design Philosophy — Claude's Working Reference

> This is not a product spec. It's a checklist Claude consults BEFORE designing
> any new feature in this codebase. Single-operator tool, SaaS-shaped internals —
> no auth/billing/multi-tenant DB work, but every design decision should be made
> as if a tenant boundary could be added later without a rewrite.
>
> Decided 2026-06-20: scope is "single-operator, SaaS-shaped architecture" — clean
> module boundaries, topic/niche as config not hardcoded, longform and shorts fully
> decoupled. Re-confirm scope with the user before assuming multi-tenant work is wanted.

---

## 0. Niche/genre independence — niche is DATA, never CODE (corrected 2026-06-20)

**This corrects an earlier mistake in this same document.** §1 below originally said
content structure (the 7 shorts topics, the 9 longform sections, role-keyword lists,
language) was "fine to be fixed in code" as a genre/format decision. That was wrong —
it meant the entire app could only ever produce Hindi true-crime content; a second
niche (different language, different structure, different voice) would have required
editing Python files, not adding a row. That's exactly the kind of code-level coupling
this document exists to prevent.

Fixed in Phase 17 (`docs/TRACKER.md`): all of it — voice/system prompt, section
structure, shorts topics + guidance + CTAs, entity-role taxonomy — now lives on
`ChannelProfile` (`src/db/models.py`), a DB row. Agents call
`get_profile_for_case(slug)` (`src/db/channel_profile.py`) and read fields off the
returned profile. The current Hindi true-crime behavior is the **seeded** profile
(`indian-true-crime-hindi`, see `src/db/seed_default_profile.py`), not the app's
identity. A second niche/language is a new row, never a code change.

**Test before merging any change:** could a channel in a completely different
language, on a completely different topic, with a completely different structure,
use this exact code by adding one `channel_profiles` row — zero Python edits? If the
answer requires editing an agent file to add a new niche, the design is wrong.

Known remaining gaps (logged, not silently ignored — see §4 below): TTS hardcodes
`hi-IN` (`tts_agent.py`), `case_research_agent.py`'s scraper sources are still
India/crime-specific code, character role disambiguation heuristics
(`ROLE_STRONG_SIGNALS`, AI-portrait `_ROLE_DESC`) are still crime-specific, Hindi
name-detection regex is language- (not niche-) coupled. See `CLAUDE.md`'s
"Niche Is Data Too" section for the live list.

## 1. Case independence — case is DATA, never CODE

A "case" (which specific piece of content within a niche) must never appear as a
literal in agent logic, schema, or routing. It only appears as:
- a row in `cases` table (`slug`, `name`, `subject_name`, `channel_profile_id`, etc.)
- files under `data/cases/{slug}/`

**Test before merging any change:** could this exact code run unmodified for a case
that hasn't been loaded yet? If the answer requires editing a Python file to add a
new case, the design is wrong.

Content structure (the 7 shorts episode topics, the 9 longform sections, role-keyword
lists) is a genre/format decision, not a case decision — it applies to every case in
the SAME niche identically. Per §0 above, these now live on `ChannelProfile` rows, not
module-level constants — so a future pivot to a different niche/format is a new DB row,
not a code edit.

---

## 2. Track independence — longform and shorts are separate services

Only `research.json` (+ the `characters` step output) is shared. Past that fork:
- No agent in one track imports the **orchestration** of the other track.
- Shared **utilities** (broll fetching, character photos, scene images) are fine to
  reuse from either track — that's composition, not coupling. The line: does the
  imported thing know which track is calling it? It must not.
- Either track must be able to run to completion alone. If shorts breaks when
  longform hasn't run (or vice versa), that's a regression, not an edge case.
- The frontend enforces this visually too — `pipeline.ts`'s `track` field and the
  two-column UI exist so a broken assumption shows up immediately, not three steps
  downstream.

**Test before merging any change:** run shorts-only on a freshly-researched case with
zero longform steps run. Does it work end to end? If not, something leaked across
the fork.

---

## 3. Visual/asset sourcing — declare priority, don't ad-hoc it

Every visual-sourcing feature must state, explicitly, where it sits in this chain
(shorts assembler is the reference implementation — `src/agents/shorts_assembler_agent.py`):

```
1. Scene-specific generated asset   (most specific — matches THIS moment)
2. Character reference asset        (matches THIS person, any moment)
3. Topic/section stock footage      (matches THIS theme, generic)
4. Black card / silence             (no crash, no broken video — last resort)
```

Never add a visual source that silently overrides a more-specific one above it in
the chain. Never let a missing asset at any tier crash the pipeline — always fall
through to the next tier.

---

## 4. Cost control is a first-class design constraint

External paid calls (DALL-E 3, Sarvam TTS, Gemini, Pexels) must be:
- **Capped** — explicit numeric limits (e.g. scene images capped at 4/episode), not
  "however many segments happen to qualify."
- **Cached/idempotent** — check disk/DB for an existing result before regenerating.
  Re-running a step on an already-processed case must cost ~$0, not re-bill in full.
- **Logged when capped** — if a cap drops content (5th qualifying segment skipped),
  log it. Silent truncation looks like full coverage when it isn't.

**Test before merging any change:** run the same step twice in a row. Second run
should make zero paid API calls (or only for genuinely new/missing content).

---

## 5. Graceful degradation — missing config never crashes the pipeline

Every external integration (OPENAI_API_KEY, PEXELS_API_KEY, etc.) must:
- Check for its own credential/package at the top of its method.
- Log a `logger.warning` and return `None`/`[]` if unavailable.
- Never raise out of an agent method into the pipeline runner.

This is what lets a single-operator tool behave like a SaaS product would have to:
one tenant's misconfigured key can't take down the run for everyone else — here,
it means one missing optional key can't take down a run that doesn't strictly need it.

---

## 6. Per-step granularity — no monolithic batch steps

Every pipeline step must be independently runnable, re-runnable, and resumable:
- A step operating over N items (7 shorts episodes, multiple b-roll segments) should
  support running for ONE item at a time, not just all-or-nothing.
- A step must check "is this already done?" before redoing expensive work (see §4).
- The frontend step workspace exists to make per-step, per-item control visible —
  new steps should expose that same granularity, not hide behind one big button.

---

## 7. Schema neutrality

`src/db/models.py` must never gain a column or table that only makes sense for one
case, niche, or language. If a new feature seems to need that, the data belongs in
a JSON file under `data/cases/{slug}/` or a generic `notes`/`metadata` column, not a
new case-specific schema field.

---

## 8. Feature design checklist (run through this before writing code)

1. **Which track does this belong to** — shared / longform / shorts / cross-cutting
   utility? State it explicitly in the plan.
2. **Is the niche-specific part data or code?** If code, can it be config instead?
3. **Where in the visual/asset priority chain does this sit**, if it touches visuals?
4. **Is it capped and cached?** What's the $ cost of running it twice?
5. **Does it degrade gracefully** if its API key/dependency is missing?
6. **Can it run for one item at a time**, not just the whole batch?
7. **Does it leak a case/topic literal into code, schema, or routing?**

If a feature request doesn't cleanly answer these, surface the ambiguity to the user
before building — don't silently pick an answer that violates one of the above.
