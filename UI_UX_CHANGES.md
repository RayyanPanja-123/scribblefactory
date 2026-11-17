# UI/UX Accessibility Pass

Date: 2026-11-18

This pass focused on making the dashboard easier to navigate, faster to understand, safer to operate, and usable at smaller viewport sizes while preserving the existing warm skeuomorphic visual language.

## Changes made

### Navigation and responsive layout

- Replaced the duplicated desktop icon rail and floating navigation with one labelled navigation bar.
- Moved the brand mark into the header so the navigation has one clear home.
- Added active navigation matching for New series and New part routes.
- Made the header wrap cleanly on small screens.
- Made the bottom navigation fit small screens with compact icon-and-label controls.
- Made the job drawer fluid on small screens instead of using a fixed 440px width.
- Made toast notifications fit small screens and avoid being pushed off-screen by the job drawer.

Files: `web/src/App.vue`, `web/src/components/JobDrawer.vue`, `web/src/components/Overlays.vue`

### Faster approval workflow

- Overview approval rows now deep-link directly to the relevant series, part, and review/approval section.
- Preserved the existing direct deep-link behavior on the Review page.
- Added a sticky section navigator to Part Detail for Video, Voice, Run, Review, Approvals, Thumbnail, and Post.
- Added scroll margins so anchored sections are not hidden beneath the sticky navigator.

Files: `web/src/pages/Overview.vue`, `web/src/pages/PartDetail.vue`

### Job recovery

- Failed job history now offers an Open part action.
- Failed jobs now offer Run again directly from their expanded history entry.
- Kept the existing log-copy action and added the recovery actions beside it.

File: `web/src/components/JobDrawer.vue`

### Dialog and keyboard accessibility

- Confirmation dialogs now expose their body through `aria-describedby`.
- Confirmation dialogs trap Tab focus inside the dialog.
- Confirmation dialogs return focus to the control that opened them.
- Image zoom now has a visible Close image button.
- Clicking the image no longer closes the zoom accidentally; clicking the backdrop still closes it.
- Image zoom padding now adapts to small screens.

File: `web/src/components/Overlays.vue`

### Media and data presentation

- Video source tabs now have `type`, `aria-controls`, and selected-tab keyboard semantics.
- Video load failures now produce an actionable alert.
- Posted table is horizontally scrollable on narrow screens and announces that behavior.
- Added a screen-reader summary to the posts-per-month chart.
- Made the visible Series list Open control keyboard accessible instead of hiding it from keyboard users.

Files: `web/src/components/VideoPlayer.vue`, `web/src/components/AreaChart.vue`, `web/src/pages/Posted.vue`, `web/src/pages/SeriesList.vue`

### Workflow vocabulary

- Stage chips now use friendlier visible labels such as “Check voice”, “Plan shots”, “Render video”, and “Finish and QA”.
- Technical stage names remain available in the underlying stage data and error details.

File: `web/src/components/StageChips.vue`

### Simpler creation flow

- New series now starts with the simple path: title, slug, and character names.
- Costume, eye, hand-prop, and imported-look fields are behind “Customize cast”.
- JSON import is explicitly labelled as an advanced option.
- The form now explains that cast can be added after the series exists.

File: `web/src/pages/NewSeries.vue`

### Lightweight Sets page

- Removed the live `SetPreview` renderer from every set card.
- Replaced large preview cards with compact list cards showing the set name, `@set` id, indoor/outdoor kind, and edit action.
- This avoids starting many renderer-backed previews while browsing the catalog.

File: `web/src/pages/Sets.vue`

### Frame and content spacing

- Removed the unnecessary outer page padding around the dark device frame so the app fills the viewport more cleanly.
- Reduced the frame inset and added consistent content/header padding inside the screen so page content no longer hugs the edge.

File: `web/src/App.vue`

### Overview layout

- Reorganized the dashboard so “Waiting for you” appears immediately after the KPI cards instead of below the analytics area.
- Grouped approvals and disk usage into a focused left column.
- Gave the posts chart the larger right column so it uses the available desktop width.
- Made approval rows more compact while retaining direct links to the exact task.
- Improved empty-state visibility: “All caught up” is now visible without requiring the user to scroll past a large chart.

File: `web/src/pages/Overview.vue`

## Verification

Passed:

- `cd web && npm.cmd run typecheck`
- `cd web && npm.cmd test` — 26 tests passed
- `cd web && npm.cmd run build`
- `node web/scripts/screenshots.mjs` — 2 screenshots, 95 texts checked, 0 contrast problems
- `git diff --check`

The screenshot smoke check also confirmed the intended 24px clearance between the final content and the floating navigation bar.
