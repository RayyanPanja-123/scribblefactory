---
name: Scribble Factory
description: An animator's exposure sheet for a local stickman-shorts factory. Parts are rows, pipeline stages are columns.
colors:
  sheet: "#fdfdfb"
  desk: "#e7ebf0"
  well: "#f2f5f8"
  rule: "#d3dde7"
  rule-strong: "#9fb2c5"
  ink: "#1b2531"
  muted: "#4c5a69"
  faint: "#8797a8"
  grease-pencil: "#e8692c"
  grease-pencil-ink: "#a2410c"
  col-erase-blue: "#2f6db3"
  col-erase-blue-ink: "#24578f"
  red: "#d23b2f"
  red-ink: "#a52a20"
  youtube: "#e5482f"
  instagram: "#a43fd6"
  night-board: "#0d1116"
  night-sheet: "#141a21"
  night-well: "#1a222b"
  night-rule: "#26313d"
  night-rule-strong: "#3d4d5f"
  night-ink: "#e6ecf2"
  night-muted: "#a2b0be"
  night-grease-pencil: "#ff8f4d"
  night-col-erase-blue: "#6aa6ec"
  night-red: "#ff6a5c"
typography:
  display:
    fontFamily: "Shantell Sans, Inter, ui-sans-serif, sans-serif"
    fontSize: "1.875rem"
    fontWeight: 600
    lineHeight: 1.2
  headline:
    fontFamily: "Shantell Sans, Inter, ui-sans-serif, sans-serif"
    fontSize: "1.5rem"
    fontWeight: 600
    lineHeight: 1.33
  title:
    fontFamily: "Shantell Sans, Inter, ui-sans-serif, sans-serif"
    fontSize: "1.125rem"
    fontWeight: 600
    lineHeight: 1.55
  annotation:
    fontFamily: "Shantell Sans, Inter, ui-sans-serif, sans-serif"
    fontSize: "13px"
    fontWeight: 600
  body:
    fontFamily: "Inter, ui-sans-serif, system-ui, sans-serif"
    fontSize: "0.875rem"
    fontWeight: 400
    lineHeight: 1.43
  label:
    fontFamily: "Inter, ui-sans-serif, system-ui, sans-serif"
    fontSize: "11px"
    fontWeight: 600
    letterSpacing: "0.06em"
  number:
    fontFamily: "Inter, ui-sans-serif, system-ui, sans-serif"
    fontWeight: 600
    fontFeature: "tnum"
rounded:
  sm: "4px"
  md: "6px"
  lg: "8px"
  frame: "10px"
spacing:
  xs: "4px"
  sm: "8px"
  md: "12px"
  lg: "16px"
  xl: "20px"
  2xl: "24px"
components:
  button-primary:
    backgroundColor: "{colors.ink}"
    textColor: "{colors.sheet}"
    rounded: "{rounded.md}"
    padding: "7px 14px"
    height: "38px"
  button-secondary:
    backgroundColor: "{colors.sheet}"
    textColor: "{colors.ink}"
    rounded: "{rounded.md}"
    padding: "7px 14px"
    height: "38px"
  button-secondary-hover:
    backgroundColor: "{colors.well}"
  icon-button:
    backgroundColor: "{colors.sheet}"
    textColor: "{colors.muted}"
    rounded: "{rounded.md}"
    size: "40px"
  chip:
    textColor: "{colors.muted}"
    rounded: "{rounded.sm}"
    padding: "1px 8px"
    typography: "{typography.label}"
  sheet:
    backgroundColor: "{colors.sheet}"
    rounded: "{rounded.lg}"
  well:
    backgroundColor: "{colors.well}"
    rounded: "{rounded.md}"
  nav-item-active:
    backgroundColor: "{colors.ink}"
    textColor: "{colors.sheet}"
    rounded: "{rounded.md}"
    padding: "8px"
  rail:
    backgroundColor: "{colors.sheet}"
    width: "232px"
---

# Design System: Scribble Factory

Tokens live in `web/src/styles/tokens.css` (Tailwind 4 `@theme`, so every token is both a CSS variable and a utility: `--color-ink` is `text-ink`, `bg-ink`). Themes swap values only; class names never change per theme.

## Overview

**Creative North Star: "The Exposure Sheet"**

The app is an animator's exposure sheet (X-sheet, dope sheet). Parts are rows, the eight pipeline stages (Story, Voice, Plan, Stills, Test, Final, Thumb, Post) are columns, and the creator reads what needs them from the margin. Every surface is ruled production paper: a cool white sheet laid on a blue-grey desk, pale blue ruled lines, navy-black ink, a blue col-erase pencil for secondary marks, and an orange-red grease pencil reserved for one meaning: "this needs you".

Dark is the same sheet on a lightbox at night: a blue-black board, steel rules, paper-white ink, a lit pencil blue. The world does not change between themes; only the light does. Libraries and editors (props, creatures, sets, settings) use the same sheet language as the Overview: ruled tables with column headers, one row per thing.

Density is a working document's density: hairline borders, tight ruled rows, tabular figures. The hand-drawn personality the product owes its stickman subject lives in the marker-hand headings, the pencil tick, and the grease-pencil circle, not in ornament.

**Key Characteristics:**
- Ruled tables over cards: rows and columns carry the information.
- Flat fills, hairline rules, one soft paper shadow.
- Ink for done, grease pencil for "needs you", col-erase blue for running, links and focus, red for failed.
- Two faces: Inter for UI and data, Shantell Sans (marker hand) for headings and pencil annotations.
- Light, Dark and System themes, chosen at the foot of the left rail.

## Colors

A near-monochrome ink-on-paper palette with three pencil colours, each owning exactly one meaning.

### Primary
- **Drafting Ink** (light #1b2531 / dark #e6ecf2): all body text, the primary button fill, the active nav item, and every "done" mark. Text on an ink fill uses `--on-ink` (the sheet colour in light, the night board in dark).

### Secondary
- **Grease Pencil** (#e8692c / dark #ff8f4d; text form #a2410c / dark #ffb37f): only for what needs the creator: the grease-pencil circle, the "you" / "approve" annotations, the Needs-you count, the queued-jobs badge, amber chips and the cast-sheets notice.
- **Col-Erase Blue** (#2f6db3 / dark #6aa6ec; text form #24578f / dark #9cc4f3): running work, the "next" dot, links, disk-usage bars, focus outlines, caret and selection tint, and the cell hover wash.

### Tertiary
- **Correction Red** (#d23b2f / dark #ff6a5c; text form #a52a20 / dark #ff9d92): failed stages, destructive buttons, danger tints.
- **Platform swatches** (YouTube #e5482f, Instagram #a43fd6; lifted in dark): small dots that label a platform row. Never a status.

### Neutral
- **Sheet** (#fdfdfb / dark #141a21): the paper. Panels, the rail, the top bar, sticky table columns.
- **Desk** (#e7ebf0 / dark #0d1116): the page behind the sheets.
- **Ruled Cell** (#f2f5f8 / dark #1a222b): inputs, wells, series group rows, row hover, empty states.
- **Pale Rule** (#d3dde7 / dark #26313d): every hairline border and column divider.
- **Strong Rule** (#9fb2c5 / dark #3d4d5f): the 2px rule under a table header, secondary-button borders, the "to do" dot.
- **Muted** (#4c5a69 / dark #a2b0be): secondary text (6.5:1 on the sheet).
- **Faint** (#8797a8 / dark #66778a): icons, empty dots and rules only.

### Named Rules
**The Done Is Ink Rule.** A finished stage is a pencil tick in ink, never green. The `green` and `green-ink` tokens equal ink in both themes; there is no success green in this world.

**The Grease Pencil Rule.** Orange-red means "needs you" and nothing else. If an element is not waiting on the creator, it does not get grease pencil.

**The Text Ink Rule.** Pencil hues fill dots, strokes and tints; text on the sheet or a tinted chip uses the matching `*-ink` token (all at least 5:1). Faint is never text.

**The White Paper Rule.** Engine drawings (the `.drawing` well behind prop and creature previews) stay on paper-white #fdfdfb with #dfe7ef rules in both themes, because the renderer draws in black ink.

## Typography

**Display Font:** Shantell Sans 500/600 (with Inter fallback)
**Body Font:** Inter 400/500/600 (with ui-sans-serif, system-ui)

**Character:** Inter is the drafting table: neutral, tabular, legible at 11px. Shantell Sans is the animator's marker: headings, series names, and the short pencil notes written into sheet cells. Both are self-hosted via @fontsource.

### Hierarchy
- **Display** (600, 30px): rare page-level headings in editors.
- **Headline** (600, 24px): page titles (Props, Creatures, Settings), title-block figures, empty-sheet headings.
- **Title** (600, 18-20px): section headings on a sheet ("Exposure sheet", "Posting log"), item names in library rows.
- **Annotation** (600, 13px, Shantell Sans): pencil notes inside a cell: "you", "approve", "next", "running", "failed".
- **Body** (400-500, 14px): table cells, descriptions, helper text; long prose capped at 48rem (`max-w-3xl`).
- **Label** (600, 11px, 0.06em, uppercase, muted): X-sheet column headers, title-block field names, rail group names. Nothing else.
- **Number** (600, tabular figures): part numbers (zero-padded, "03"), sizes, counts.

### Named Rules
**The Column Header Rule.** Uppercase tracked labels exist only as headers of something ruled: a table column, a title-block field, a rail group, a fieldset legend. Never as a kicker above a heading.

**The Marker Hand Rule.** Shantell Sans writes headings and pencil notes; it never sets body copy, buttons, inputs or table data.

## Layout

A fixed left margin rail (232px) holds the brand mark, the ruled nav groups (Production, Library, Setup) and the theme selector at its foot. A slim top bar carries search and the job reel. Main content scrolls inside, with 16px side padding (32px from 1024px) and 24px top. Content caps at 80rem on the Overview and 48-72rem on forms and editors.

Under 1024px the rail becomes a drawer behind a menu button, over a scrim, with the current page name in the top bar. Wide tables scroll sideways inside their sheet with the first column sticky; on phones the Overview puts the sheet first and names the circled stage under each part title so nothing is lost off-screen.

Spacing follows Tailwind's 4px scale; sheets sit 24px apart, sheet headers pad 16px by 20px, ruled rows run 40-48px tall.

## Elevation & Depth

Flat paper on a desk. Every sheet carries a hairline rule and one soft shadow; hover on a clickable sheet deepens it to the pop shadow and darkens the rule. Overlays (the open rail drawer, dialogs, the job drawer) use the pop shadow. Nothing else casts a shadow, and nothing is inset or embossed.

### Shadow Vocabulary
- **Sheet** (light `0 1px 2px rgb(27 37 49 / 0.06), 0 10px 24px -14px rgb(27 37 49 / 0.22)`; dark adds a 1px black ring): every `.raised` sheet and the selected theme segment.
- **Pop** (light `0 2px 6px rgb(27 37 49 / 0.1), 0 18px 40px -12px rgb(27 37 49 / 0.3)`): hovered clickable sheets and overlays.

### Named Rules
**The One Shadow Rule.** A surface is either on the desk (sheet shadow) or above it (pop shadow). No third level, no inner shadows.

**The Terminal Exception.** The job drawer's console and logs stay dark (#121920 / #0d1318) in both themes, because they are a terminal. Their green LED and green finished steps are terminal colours and do not leak into the sheet.

## Shapes

Small, even corners: 4px on chips and segments, 6px on buttons, inputs, wells and nav items, 8px on sheets, 10px reserved for framed media. Borders are always 1px hairlines in the rule colour, with a 2px strong rule under table headers. Round shapes appear only on dots (to-do, next, platform, status) and the queued-jobs badge.

## Components

### Buttons
Ink on paper, compact and plain.
- **Shape:** gently squared (6px), 38px minimum height, 14px semibold label, 16px Lucide icon before the label.
- **Primary:** ink fill, on-ink text. Hover and active mix 14% and 25% col-erase blue into the ink.
- **Secondary:** sheet fill, ink text, strong-rule border; hover fills with the ruled-cell colour and the border goes to ink.
- **Icon button:** 40px square, sheet fill, muted icon, hairline border; `aria-current` fills it with the ruled-cell colour.
- **Focus:** a 2px col-erase blue outline at 2px offset on every focusable element.
- **Disabled:** 50% opacity, not-allowed cursor, and a title that says why.

### Chips
- **Style:** 4px corners, 12px semibold text, a 14-16% tint of the status hue mixed into the sheet, text in the matching `*-ink`.
- **State:** grey (neutral), amber (needs you), blue (running), red (failed), "green" (done, which renders as ink).

### Cards / Containers
- **Corner Style:** 8px.
- **Background:** the sheet colour on the desk.
- **Shadow Strategy:** the sheet shadow; clickable sheets lift to pop on hover (see Elevation & Depth).
- **Border:** 1px pale rule.
- **Internal Padding:** a 16px by 20px header strip ruled off from the content; tables run edge to edge.
- **Tinted sheets:** red and amber tints (9-10% hue in the sheet, 35% hue in the border) for danger zones, errors and the cast-sheets notice.

### Inputs / Fields
- **Style:** ruled-cell fill, 1px pale rule, 6px corners, col-erase blue caret and accent colour.
- **Focus:** border shifts to col-erase blue (search) or the global blue outline.

### Navigation
Rail groups headed by column-header labels; items are 14px medium Inter with a 17px icon, muted at rest, ruled-cell fill and ink text on hover, ink fill with on-ink text when current. The theme selector is a three-segment Light / Dark / System radio group in a well; the chosen segment is a sheet with the sheet shadow. The choice is stored as `sf-theme`, applied as `data-theme` on `<html>` before first paint by the inline script in `web/index.html`; System removes the attribute and follows `prefers-color-scheme`.

### Exposure Sheet Row (signature)
The Overview sheet and the part page's stepper share one row grammar: eight numbered stage columns under a 2px strong rule, and each cell holds one mark: a pencil tick in ink (done), a faint dot (to do), a blue dot and "next" (current), a spinning reel and "running", a red cross and "failed", or a grease-pencil circle around "you" / "approve" (needs you) on a 7% amber wash. Every cell with a mark links to the section where that stage happens and carries a screen-reader label.

### Grease-Pencil Circle (signature)
A hand-looped orange-red stroke that draws itself once around whatever needs the creator (stroke-dashoffset over 0.7s, `cubic-bezier(0.22, 1, 0.36, 1)`), instant under reduced motion.

### Approval
An explicit secondary "Approve" button with a stamp icon. Once approved it becomes a pencil tick plus the label and a muted "approved": approvals are one-way, so the approved state is not a control.

## Do's and Don'ts

### Do:
- **Do** lay out lists of things as ruled tables with column headers: one row per part, prop, creature or set.
- **Do** write done as an ink pencil tick, and keep the green tokens equal to ink.
- **Do** circle what needs the creator with the grease-pencil circle, and use grease pencil for nothing else.
- **Do** keep engine drawings on the paper-white `.drawing` well in both themes, and the job console dark in both themes.
- **Do** define every themed colour once per theme in `tokens.css` and keep the `prefers-color-scheme` block and the `[data-theme="dark"]` block identical.
- **Do** give every motion a reduced-motion form: shimmer, pulse and reel become opacity fades; the circle appears already drawn.

### Don't:
- **Don't** use a success green anywhere on the sheet.
- **Don't** build KPI tiles, rounded floating cards, gradients or a bottom pill tab bar; this world refused the soft-card SaaS dashboard.
- **Don't** put an uppercase tracked label above a heading as a kicker; uppercase labels head columns and fields only.
- **Don't** set body copy, buttons or data in Shantell Sans.
- **Don't** use inset, embossed or offset shadows; a sheet has one soft paper shadow.
- **Don't** set text in a pencil hue or in faint; use the `*-ink` tokens.
