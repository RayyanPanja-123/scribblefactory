---
version: 1
slug: "web-src-app-vue"
primary_target: "web/src/App.vue"
related_targets: ["web/src/pages"]
---

# Scribble Factory app shell and all routes

Scope: every route in web/ (Operate mode). Audience: one creator today, other creators later. Jobs: pipeline status, building assets, writing parts, reviewing renders, all equally frequent.
Constraints: keep the stickman BrandMark and a hand-drawn personality; light and dark themes plus a selector (Light / Dark / System); WCAG AA in both; keyboard; reduced motion.

## Direction contract

THESIS: The app is an animator's exposure sheet. Parts are rows, pipeline stages are columns, and the creator reads what needs them from the margin. It refuses the soft-card SaaS dashboard (KPI tiles, rounded floating panels, bottom pill tab bar).

OWN-WORLD: Ruled production paper. Light: cool white sheet #fdfdfb on a blue-grey desk, pale blue ruled lines, navy-black ink, blue col-erase pencil for secondary marks, orange-red grease pencil only for "needs you". Dark: the same sheet on a lightbox at night: blue-black board, steel rules, paper-white ink, lit pencil blue. Hairline ruled borders, 6px corners, flat fills, one soft paper shadow. Inter for UI and tabular data; Shantell Sans (marker hand) for headings and pencil annotations.

STORY: The creator opens the app and sees every unfinished part on one sheet, with a grease-pencil circle where they are needed. One click goes to that cell's task. Assets and editors are the same sheet language: ruled forms, column headers.

FIRST VIEWPORT: Left margin rail (brand mark, ruled nav groups Production / Library / Settings, theme selector at its foot). Main: a title-block strip (sheet title, counts written like X-sheet header fields, primary action "Copy story guide"), then the exposure sheet table full width: series and part in the left columns, 8 stage columns (Story ... Post) with ticks, pencil dots, running marks and red circles.

FORM: Exposure sheet (animation X-sheet / dope sheet), position 1 on my ordered list; seed key df2edcfe (chosen as IMPECCABLE'S PICK).

SIGNATURE: a grease-pencil circle draws itself around every cell that needs the creator (stroke-dashoffset, once, instant under reduced motion).

FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance
