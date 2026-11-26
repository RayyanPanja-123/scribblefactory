# 1. Capability manifest and feasibility pass

**Problem.** We find out the engine cannot do something after writing the whole script, at planning or render time.

**Design.**
- `scripts/capabilities.py` writes `capabilities.json` from the code itself: actions and what they need (hands, a partner,
  a prop), camera angles and moves, expressions, weather, moods, effects, built-in sets and creatures, stage size. A
  hand-kept `LIMITS` list holds the known walls, each with a status and a workaround.
- **Feasibility pass** (a step in the story guide, before directive scripts): the AI reads the manifest and labels each
  beat of the approved voice script `supported`, `needs a library item` (which one), or `unsupported` (the nearest
  workaround, or a gap-log row for us). It reports this and waits.
- A `capabilities` check in CI/tests: `scripts/capabilities.py --check` fails when the file is stale, so the manifest
  cannot drift from the code.

**Done.** `scripts/capabilities.py`, `capabilities.json` (with limits).

**Next.**
1. Add the manifest to the prompts the app builds (`web/src/lib/stagePrompt.ts`, `storyGuide.ts`) and a feasibility step to `docs/story-writter/STORY_GUIDE.md`.
2. A test that runs `scripts/capabilities.py --check`.
3. Add library-derived capabilities (custom actions, sets with trails, creatures) to the inventory list the AI already receives.

**Done when.** A story with an unsupported beat (say, a swim) is flagged by the AI before any directives are written.
