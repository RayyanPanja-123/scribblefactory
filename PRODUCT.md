# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users
Today: one creator running the app locally in a desktop browser, in long working sessions, producing stickman animated Shorts series for YouTube and Instagram. Planned: the app becomes a product for other creators (a desktop app is sketched in `docs/future-desktop-app.md`), so first-run clarity and onboarding matter, not just the owner's muscle memory.

## Product Purpose
A local, offline factory that turns a written story plus a recorded voice track into a finished 9:16 stickman short (1080x1920, 30 fps). The creator plans series and parts, builds reusable assets (props, sets, creatures, cast), writes each part's story, records voice, renders stills, test and final videos, approves each stage, and logs where it was posted. Success: a part moves from idea to posted without the creator losing track of what is waiting on them.

## Positioning
Everything runs on the creator's own machine: the renderer (Three.js + Playwright), the Python pipeline and the library on disk. Runs fully offline. AI help works via copy/paste with any chat AI (ChatGPT, Claude, Gemini): the app writes the prompt and imports the reply; there are no AI providers, accounts or API keys. Every editor also works by hand. Stories are a plain-text script format (`docs/story-writter/STORY_GUIDE.md`) the engine animates directly.

## Operating Context
- Workflow per part: story -> voice -> stills -> final -> upload text -> posted.
- Human approval gates: stills, final, and per-series cast sheets.
- Long-running render jobs run one at a time on a worker; the UI shows live job status over SSE.
- Library generation: Props, Sets, Creatures, Actions and Wardrobe each have their own Generate with AI modal. The modal collects a description, creates a type-specific copy/paste prompt, accepts JSON, and imports directly into that library.
- Actions page: custom `@do` actions as keyframed poses, facing the camera or sideways, with a move speed (negative glides backwards).
- Series are created from the Series flow (`/new-series`), with cast and optional whole-series JSON import. Parts, stories, voice and assets are then managed from the series workspace.
- All four jobs are frequent and equally important: pipeline status, building assets, writing parts, reviewing renders.

## Capabilities and Constraints
- Vue 3 + Vite + Tailwind 4 SPA (`web/`), FastAPI backend (`api/`), files on disk are the source of truth.
- Localhost only, no accounts or auth.
- Routes: Overview, Series list/detail, New series, New part, Part detail, Review, Props, Creatures, Sets, Actions (+ editors), Posted, History, Help.

## Brand Commitments
- Name: Scribble Factory.
- Keep the stickman head brand mark (`web/src/components/BrandMark.vue`).
- Keep a hand-drawn / scribble personality somewhere in the interface: the product makes stickman cartoons.

## Evidence on Hand
Real library data lives in `library/` (gitignored). No testimonials, user counts or metrics exist; do not invent any.

## Product Principles
1. Always show what is waiting on the creator next.
2. Every render is reviewed before it ships: approvals are explicit and one-way.
3. Local and in the creator's control: nothing leaves the machine unless they choose.
4. Make the first run understandable for someone who is not the author.

## Accessibility & Inclusion
WCAG AA contrast in both light and dark themes; full keyboard use; respect reduced motion.
