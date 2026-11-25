# scribblefactory story guide (for AI assistants)

## Interaction contract
- This is a staged conversation, not a one-shot package-generation task. Stop at every gate below and wait for the user's explicit next instruction.
- The user first shares this guide and the current library list, then supplies a story title and the agreed number of parts.
- **Before writing anything, ask the user one question and wait for the answer: single narration (one narrator reads
  everything) or cast voice acting (a narrator plus the characters speaking their own lines, each in their own voice)?**
  Unless the user already said which in this conversation. Recommend cast voice acting for comedy, banter and
  character-driven stories, single narration for history explainers. Use the answer for every part.
- For the title phase, write TTS scripts in that voice mode for exactly the agreed number of parts. The story may be real history or invented fantasy: follow the title and the user's notes.
- After the TTS scripts, stop. Do not suggest or create props, expressions, creatures, wardrobe, sets, actions or sounds until the user explicitly asks for library planning.
- In library planning, give items one at a time in this order: props, expressions, creatures, wardrobe, sets, actions, sounds. Stop after each item and wait for `next` or an equivalent explicit request.
- After the library items are concluded, stop again. Only when the user explicitly asks for directive scripts may you convert the approved TTS scripts into `story.md` scripts with directives and a Story Package.

## Never
- Formatting while brainstorming (images, cards, tables, headings): plain short chat only.
- Directive scripts, staging, or a Story Package before the TTS scripts and library items are explicitly approved.
- The Story Package before the user says "approved".
- Rename, reorder, skip `<<<...>>>` markers; split the package; text around it.
- Ids not in the inventory list, Library basics, or the package.
- Digits, symbols or markdown in narration; narration on a directive line.
- Scripts before the user has picked single narration or cast voice acting.
- Cast lines (`id: words`) in a single-narration series; in cast voice acting, a speaker id that is not a cast id.
- Flat scripts (one `@set`, few directives).
- Characters by role ("the commander") from line 4 on: use their cast `name`. Lines 1 to 3 never name anyone.

## What this makes
- Each part = one vertical Short: a voice reads the narration (or, in cast voice acting, the narrator and each
  speaking character in their own voice), a planner turns each line into stickman shots in 3D. The character who
  speaks a line is the one whose mouth moves; on a narrator line nobody's does.
- `@` lines are silent directives.

## Workflow and stop gates
1. The user provides this guide and the current library list, then gives a story title and the agreed part count. Never ask the user to repeat the inventory if it was already provided.
   - The library list contains every set, prop, expression, creature, action, wardrobe item, sound and existing cast by id. Never guess ids.
2. Shape the story from the title and the user's notes: real history or invented fantasy are both fine.
3. Ask single narration or cast voice acting (Interaction contract) and wait for the answer. Then write the TTS
   scripts for exactly the agreed number of parts. These are the words the voices will read: no `@` directives, no
   staging, no props JSON, no Story Package, and no extra parts. In cast voice acting, a character's own line is
   `<cast id>: words` (Voice mode in Writing rules).
   - Keep the hook, intensifier, rehook and twist rules in Writing rules.
4. Stop and wait for explicit approval or requested edits to the TTS scripts. Do not continue automatically.
5. When the user explicitly asks to plan library items, work through the categories in this exact order: props, expressions, creatures, wardrobe, sets, actions, sounds.
   - Give one proposed item at a time, explain which TTS line requires it, and wait for `next` before giving the next item.
   - Props are exhaustive: every tool or object possessed, held, carried, eaten, given or used by any cast member in the TTS scripts is a prop, from a single coin to a bazooka. Do not omit an object because it is small, ordinary or used only once.
   - Capture every emotional beat as an expression requirement, then continue through the remaining categories only when asked.
6. Stop after the library categories are concluded. Only after the user explicitly asks for directive scripts, write the staged `story.md` scripts and assemble the Story Package:

```text
<<<SCRIBBLE_PACKAGE v1>>>
<<<META>>>
{"series_title": "Title", "parts": 2}
<<<PROPS>>>
[]
<<<SETS>>>
[]
<<<CREATURES>>>
[]
<<<ACTIONS>>>
[]
<<<WARDROBE>>>
[]
<<<OBJECTS>>>
[]
<<<CAST>>>
[{"id": "ava", "name": "Ava", "color": "#3b6ea5"}]
<<<PART 1>>>
<<<SCRIPT>>>
# Part title

@set street
...
<<<VOICE>>>
narration only
<<<PART 2>>>
<<<SCRIPT>>>
...
<<<VOICE>>>
...
<<<END>>>
```

   - Markers exactly as shown, alone on their line, in order, none skipped; empty sections `[]`.
   - Asset sections: only new items.
   - CAST: every character of the whole series. In cast voice acting, give every speaking character a
     `"voice": {"id": "<voice id>", "speed": 1.0}` from TTS VOICES in the library list: a distinct voice each,
     matching who they are (gender, age, accent), never the narrator's. The narrator's voice is picked in the app.
   - SCRIPT: cast lines keep their `<cast id>: ` prefix, and the speaker is on stage (`@cast`) for that line.
   - VOICE: its SCRIPT's spoken lines word for word, one line each; no `@` lines, title, `!!` or `<cast id>: `
     prefix.
7. User pastes back `staging:` warnings: fix every one that fits; resend the whole package.


## Your series
- **About:**
- **Parts:**
- **Tone / avoid:**
