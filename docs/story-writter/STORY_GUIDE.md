# scribblefactory story guide (for AI assistants)

## Interaction contract
- This is a staged conversation, not a one-shot package-generation task. Stop at every gate below and wait for the user's explicit next instruction.
- The user first shares this guide and the current library list, then supplies a story title and the agreed number of parts.
- **Before writing anything, ask the user one question and wait for the answer: single narration (one narrator reads everything) or cast voice acting (a narrator plus the characters speaking their own lines, each in their own voice)?** Unless the user already said which in this conversation. Recommend cast voice acting for comedy, banter and character-driven stories, single narration for history explainers. Use the answer for every part.
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
- Under-staged scripts: every part needs actions (`@do` at least every third line), faces on the emotional beats, 3-4 `@cam` beats, 2-3 `@mood` changes, 2-4 `@sfx` and 10+ directives; the Check rejects less. Use crowds, props, looks and items from the library.
- Flat scripts (one `@set`, few directives) and lines where a character only talks or stands while the narration names an act: follow the Direction playbook in the script doc.
- Characters by role ("the commander") from line 4 on: use their cast `name`. Lines 1 to 3 never name anyone.

## What this makes
- Each part = one vertical Short: a voice reads the narration (or, in cast voice acting, the narrator and each speaking character in their own voice), a planner turns each line into stickman shots in 3D. The character who speaks a line is the one whose mouth moves; on a narrator line nobody's does.
- `@` lines are silent directives: `@set`, `@weather`, `@mood` (scene tone: tense, dark, flashback, bright), `@do` (including `don <item>` to put something on), `@face`, `@cam` (including `orbit_left` / `orbit_right` arcs around the subject), `@fx`, `@sfx`, `@pause`. Staging sprinkles the library's reaction actions (`shock-jump`, `double-take`, `facepalm`...) on their beats, a `@pause 0.4` to `0.6` before a punchline or the twist, and `@mood` on turns of the story (details: script and stage docs).

## Workflow and stop gates
1. The user provides this guide and the current library list, then gives a story title and the agreed part count. Never ask the user to repeat the inventory if it was already provided.
   - The library list contains every set, prop, expression, creature, action, wardrobe item, sound and existing cast by id. Never guess ids.
2. Shape the story from the title and the user's notes: real history or invented fantasy are both fine.
3. Ask single narration or cast voice acting (Interaction contract) and wait for the answer. Then write the TTS scripts for exactly the agreed number of parts. These are the words the voices will read: no `@` directives, no staging, no props JSON, no Story Package, and no extra parts. In cast voice acting, a character's own line is `<cast id>: words` (Voice mode in Writing rules).
   - Keep the hook, intensifier, rehook and twist rules in Writing rules.
4. Stop and wait for explicit approval or requested edits to the TTS scripts. Do not continue automatically.
5. When the user explicitly asks to plan library items, work through the categories in this exact order: props, expressions, creatures, wardrobe, sets, actions, sounds.
   - Give one proposed item at a time, explain which TTS line requires it, and wait for `next` before giving the next item.
   - Props are exhaustive: every tool or object possessed, held, carried, eaten, given or used by any cast member in the TTS scripts is a prop, from a single coin to a bazooka. Do not omit an object because it is small, ordinary or used only once.
   - Capture every emotional beat as an expression requirement, then continue through the remaining categories only when asked.
   - Wardrobe covers every item a character puts on during the story (a crown, a cape, a hat): the `@do <id>: don <item>` action needs it in the library as a `headwear` or `back` item.
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
   - CAST: every character of the whole series. In cast voice acting, give every speaking character a `"voice": {"id": "<voice id>", "speed": 1.0}` from TTS VOICES in the library list: a distinct voice each, matching who they are (gender, age, accent), never the narrator's. The narrator's voice is picked in the app.
   - SCRIPT: cast lines keep their `<cast id>: ` prefix, and the speaker is on stage (`@cast`) for that line.
   - VOICE: its SCRIPT's spoken lines word for word, one line each; no `@` lines, title, `!!` or `<cast id>:` prefix.
7. User pastes back `staging:` warnings: fix every one that fits; resend the whole package.

## Story quality (required)
Write like a human storyteller, not a viral-content template. Each story should feel specific to its characters and situation, not assembled from familiar short-form formulas.

- Give important characters believable motives, personal stakes, flaws and distinct personalities. Their choices should make sense to them, even when those choices are poor.
- Make dialogue natural and character-specific. Avoid lines that exist only to explain the plot to the audience.
- Show emotion through actions, reactions, hesitation, choices and small details instead of repeatedly naming the emotion.
- Build tension through cause and effect. Let events create questions naturally; do not manufacture suspense with empty announcements.
- Use concrete, memorable details that belong to this story. Avoid generic dramatic wording that could fit any story.
- Let reveals emerge from earlier details. Foreshadow subtly, then let the audience connect the pieces. Do not explain a twist after revealing it.
- Vary sentence length and rhythm. Use short sentences when the moment earns them, not as the default style.
- Avoid clickbait phrasing and narrator prompts such as "Here's where it gets weird", "Watch what happens", "You won't believe", or "But then things changed".
- Avoid excessive fragments, fake countdowns, arbitrary numbers, repeated rhetorical questions and overdramatic claims.
- Do not force a twist, villain, death or surprise ending when the story does not need one. Make the ending feel earned.
- Keep narration clear and speakable. Every line should add meaningful action, character, emotion, atmosphere or information.
- The hook should come from an unusual but meaningful situation or character choice, not clickbait wording. Make the audience care about the people, not just the reveal.
- These quality rules never override the required voice mode, agreed part count, story structure, script format, library workflow or Story Package markers.

## Your series
- **About:**
- **Parts:**
- **Tone / avoid:**
