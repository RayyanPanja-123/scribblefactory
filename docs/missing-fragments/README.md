# Missing fragments

The engine is built story by story, and each new story finds a limit (stairs, swimming, sword fights). This folder is how
we stop fixing those one by one with a code change: every limit becomes a **fragment**, and every fragment is closed
by turning the special case into **data** an author (or an AI) can write, not by patching the engine.

## The idea in one line
New story type -> the writer finds the gap *before* writing 30 directives -> the gap is logged -> it is closed with a
general primitive (a library entry + a schema), not a one-off case.

## What is here
| file | what |
|---|---|
| `gap-log.md` | running list of every limit found, its status, and the commit that closed it. **Add a row whenever a story hits a wall.** |
| `capabilities.json` | generated: what the engine can do and the known limits. Regenerate with `scripts/capabilities.py`. |
| `01-capability-manifest.md` | the feasibility pass: the story AI reads the manifest and flags unsupported beats first |
| `02-locomotion-modes.md` | walk, climb, swim, fly, crawl as library data (generalises `climb`/`trail`) |
| `03-interaction-choreography.md` | duels, parries, battles, group moves as data (sword fighting, formations) |
| `04-registries.md` | camera moves, environments and effects as registries, not switch statements |
| `05-ai-authored-library-items.md` | Gemini drafts library items; schema check, preview, one-click approval |
| `06-expression-escape-hatch.md` | a small sandboxed formula language for the long tail |
| `safety-net.md` | golden frames, generated docs, add-a-feature checklist: change the engine without breaking old stories |

## Order (and status)
| # | fragment | status |
|---|---|---|
| 1 | capability manifest | **started**: `capabilities.json` + generator; not yet fed to the story AI |
| 2 | locomotion modes | designed; `climb` + `trail` already ships as the first mode |
| 3 | interaction choreography | designed |
| 4 | registries | designed |
| 5 | AI-authored library items | designed (Gemini, same key as captions) |
| 6 | expression escape hatch | designed, last |

## Principles
- **Data over code.** If a new story needs it, ask "what library entry would express this?" before "what `if` do I add?".
- **Validated, never executed.** AI-authored things are JSON checked against a schema (and previewed), never code.
- **Say no early.** A beat the engine cannot show is a logged gap with a workaround, not a surprise at render time.
- **Old stories keep rendering.** Every engine change runs against the golden frames (`safety-net.md`).
- **Not zero code.** The target is that about four in five new needs are data; the rest are small, isolated additions
  that follow the checklist in `safety-net.md`.
