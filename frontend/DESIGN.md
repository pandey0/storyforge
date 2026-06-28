---
name: StoryForge Control Room
description: Dark, minimal production dashboard for a generalist content engine. Operator-focused, never decorative.
version: alpha

colors:
  background: "#0a0a0a"
  surface: "#111111"
  surface-raised: "#1a1a1a"
  surface-border: "#222222"
  sidebar: "#0f0f0f"
  on-surface: "#e0e0e0"
  on-surface-muted: "#888888"
  primary: "#3b82f6"
  on-primary: "#ffffff"
  primary-ring: "#3b82f6"
  success: "#22c55e"
  warning: "#f59e0b"
  error: "#ef4444"
  error-container: "#450a0a"
  purple: "#8b5cf6"
  input: "#1a1a1a"
  popover: "#111111"
  on-popover: "#e0e0e0"

typography:
  heading-xl:
    fontFamily: Geist Sans
    fontSize: 24px
    fontWeight: "600"
    lineHeight: 32px
    letterSpacing: -0.01em
  heading-lg:
    fontFamily: Geist Sans
    fontSize: 18px
    fontWeight: "600"
    lineHeight: 28px
  heading-md:
    fontFamily: Geist Sans
    fontSize: 15px
    fontWeight: "500"
    lineHeight: 24px
  body-md:
    fontFamily: Geist Sans
    fontSize: 14px
    fontWeight: "400"
    lineHeight: 20px
  body-sm:
    fontFamily: Geist Sans
    fontSize: 13px
    fontWeight: "400"
    lineHeight: 18px
  label:
    fontFamily: Geist Sans
    fontSize: 12px
    fontWeight: "500"
    lineHeight: 16px
    letterSpacing: 0.02em
  mono:
    fontFamily: Geist Mono
    fontSize: 13px
    fontWeight: "400"
    lineHeight: 20px

rounded:
  sm: 0.375rem
  DEFAULT: 0.5rem
  md: 0.5rem
  lg: 0.625rem
  xl: 0.875rem
  full: 9999px

spacing:
  unit: 4px
  card-padding: 16px
  section-gap: 24px
  sidebar-width: 240px
  panel-gap: 12px

components:
  card:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.on-surface}"
    borderColor: "{colors.surface-border}"
    rounded: "{rounded.lg}"
    padding: "{spacing.card-padding}"
  card-raised:
    backgroundColor: "{colors.surface-raised}"
    textColor: "{colors.on-surface}"
    borderColor: "{colors.surface-border}"
    rounded: "{rounded.lg}"
    padding: "{spacing.card-padding}"
  button-primary:
    backgroundColor: "{colors.primary}"
    textColor: "{colors.on-primary}"
    typography: "{typography.label}"
    rounded: "{rounded.md}"
    height: 36px
    padding: "0 16px"
  button-ghost:
    backgroundColor: "transparent"
    textColor: "{colors.on-surface-muted}"
    rounded: "{rounded.md}"
    height: 36px
  status-badge-done:
    backgroundColor: "{colors.success}"
    textColor: "#ffffff"
    rounded: "{rounded.full}"
    padding: "2px 8px"
    typography: "{typography.label}"
  status-badge-running:
    backgroundColor: "{colors.primary}"
    textColor: "#ffffff"
    rounded: "{rounded.full}"
    padding: "2px 8px"
    typography: "{typography.label}"
  status-badge-error:
    backgroundColor: "{colors.error-container}"
    textColor: "{colors.error}"
    rounded: "{rounded.full}"
    padding: "2px 8px"
    typography: "{typography.label}"
  status-badge-pending:
    backgroundColor: "{colors.surface-raised}"
    textColor: "{colors.on-surface-muted}"
    rounded: "{rounded.full}"
    padding: "2px 8px"
    typography: "{typography.label}"
  pipeline-step-done:
    backgroundColor: "{colors.success}"
  pipeline-step-active:
    backgroundColor: "{colors.primary}"
  pipeline-step-gate:
    backgroundColor: "{colors.warning}"
  pipeline-step-pending:
    backgroundColor: "{colors.surface-border}"
  log-panel:
    backgroundColor: "#050505"
    textColor: "#aaaaaa"
    typography: "{typography.mono}"
    rounded: "{rounded.md}"
    borderColor: "{colors.surface-border}"
  input-field:
    backgroundColor: "{colors.input}"
    textColor: "{colors.on-surface}"
    borderColor: "{colors.surface-border}"
    typography: "{typography.body-md}"
    rounded: "{rounded.md}"
    height: 36px
    padding: "0 12px"
  sidebar-nav-item:
    textColor: "{colors.on-surface-muted}"
    rounded: "{rounded.md}"
    padding: "6px 12px"
    typography: "{typography.body-sm}"
  sidebar-nav-item-active:
    backgroundColor: "{colors.surface-raised}"
    textColor: "{colors.on-surface}"
---

## Overview

This is an operator control room, not a consumer product. Design serves function: operators run pipeline steps, monitor agent logs, review scripts, and approve checkpoints. Every pixel either carries information or gets out of the way.

Single color scheme — dark only. No light mode. Operators use this in low-light environments for extended sessions.

## Colors

Near-black foundation with a tight 4-step surface stack:

- **`#0a0a0a`** — page background (deepest)
- **`#0f0f0f`** — sidebar (slightly lighter)
- **`#111111`** — card surfaces
- **`#1a1a1a`** — raised elements, inputs, hover states
- **`#222222`** — borders (only as much border as needed for structure)

Text is a warm gray `#e0e0e0` — not pure white, reduces eye strain on dark background. Muted text `#888888` for secondary labels, timestamps, descriptions.

**Primary blue `#3b82f6`:** Tailwind blue-500. Used for: active pipeline steps, primary buttons, links, progress rings, focus rings. One blue, used consistently.

**Status colors are semantic, never decorative:**
- `#22c55e` (green) — completed, published, healthy
- `#f59e0b` (amber) — human review gate, warning, needs attention
- `#ef4444` (red) — error, failed, destructive action
- `#8b5cf6` (purple) — analytics, charts, secondary data series

Do not invent accent colors. Do not use gradients on surfaces. Dark + border + status color is enough visual hierarchy.

## Typography

Two fonts: **Geist Sans** (UI) and **Geist Mono** (code, logs, file paths, JSON).

Geist Sans is used for everything that isn't a terminal or data stream. Geist Mono is used in the log streaming panel, script preview (raw text), research JSON viewer, and any agent output that looks like code.

Font sizes are conservative — 13-14px body, 12px labels. Operators read dense information; don't inflate sizes to fill space.

**No uppercase labels unless they mark a structural section.** No decorative text treatments.

## Layout

Three-zone layout:
1. **Sidebar** (240px fixed) — case navigation, global status
2. **Main content** — pipeline stepper, step workspace, artifact previews
3. **Log panel** (collapsible right rail or bottom drawer) — SSE log stream from active agent

Pipeline stepper runs horizontally for the shared→longform/shorts fork visualization. Individual step workspaces take full remaining width.

8px minimum touch target for interactive elements in a desktop-only context. This is never used on mobile.

## Elevation & Depth

No shadows. Depth is established through background color alone:
- Background `#0a0a0a` sits deepest
- Cards `#111111` float one level up
- Raised elements `#1a1a1a` (dropdowns, tooltips, hover states) float highest
- Borders `#222222` delineate without adding visual weight

Never use `box-shadow` for UI chrome. Use it only for modal overlays (dark semi-transparent backdrop, no blur).

## Shapes

Base radius: **0.625rem (10px)**. Consistent across cards, buttons, inputs, badges.
- Buttons: `0.5rem`
- Badges/chips: `9999px` (pill)
- Cards: `0.625rem`
- Modals: `0.75rem`
- Log panel: `0.5rem`

No sharp corners. No overly rounded "bubbly" corners. Professional tool aesthetic.

## Components

### Pipeline Stepper
Horizontal track of steps, colored by status. Longform and shorts tracks diverge after the shared steps — use a fork/branch visual (two parallel rows) not a linear list. Gate steps (human_review) use amber, not blue.

### Status Badges
Pill-shaped, font-weight 500, 12px. Four states only: done (green), running (blue), gate (amber), error (red). No "pending" color — just muted gray background.

### Log Panel
Monospace, 13px, `#aaaaaa` text on `#050505` background. SSE stream auto-scrolls. No syntax highlighting needed — these are logger lines, not code. Timestamp prefix in even more muted `#555555`.

### Cards
All cards use `#111111` with `1px solid #222222` border. No shadow. Padding 16px. Headers inside cards are `heading-md`, never bigger. Avoid deeply nested card-in-card — use `surface-raised` for inner sections instead.

### Buttons
Primary: blue `#3b82f6`, white text, 36px height, 16px horizontal padding.
Ghost: transparent background, muted text, no border by default, border-on-hover acceptable.
Destructive: error red `#ef4444`.
Never use icon-only buttons without tooltip.

## Do's and Don'ts

**Do:**
- Use status colors semantically and consistently
- Show empty states with clear CTAs (no decorative illustrations)
- Use monospace for any agent output, file paths, or JSON
- Keep information density high — operators are power users
- Show pipeline progress numerically (e.g., "3/7 episodes") not just a bar

**Don't:**
- Add gradients, glassmorphism, or decorative backgrounds
- Use colors other than the defined palette
- Show loading spinners for > 2s without also showing log output
- Add animations beyond simple opacity transitions (150ms max)
- Use more than 2 font weights per component
