## Script format
- Line 1 `# Title`, then a blank line.
- One directive per line, alone.
- `@do`, `@face`, `@fx`, `@sfx`: next narration line only (one must follow). Others last until changed.
- Narration: plain text, numbers as words; no digits, symbols, abbreviations, parentheses, markdown.


## Directives
- Directives are silent and must occupy their own line. They are never sent to TTS.
- Persistent directives remain active until changed. `@do`, `@face`, `@fx`, `@fx lightning`, and `@sfx` apply to the next narration line only.

### Persistent scene state

- `@set <id>`: place the following lines in a set. Required before the first line. A set change resets the crowd teams,
  crowd wardrobe/weapons, runners, and actors' positions, then applies the set's weather default. The car remains in its
  current directive state until `@car off` or another car mode. Use `@set` for a new location,
  time jump, or establishing shot.
- `@weather clear | rain | snow | fog | wind | storm [light | medium | heavy]`: persistent weather until another
  `@weather` or `@set`. Intensity defaults to medium. Use storm for war, gods, or villains; rain for loss; fog for mystery;
  snow or wind for a journey. A new set starts with its configured default weather, or clear.
- `@cast a, b`: the characters on stage. The character named in the narration, or named by `@do`, is staged in front.
  Maximum 12 cast members; maximum 6 fit in the front row. Remove someone by writing a new `@cast` without them.
  A sudden entrance is a new `@cast` immediately above the entrance line.
- `@look <cast>: <look>`: switches a cast member to a named look from their cast entry, such as armour, a crown, or a
  held spear. The look persists for the rest of the part until another look or `default` is used. It resets on a new part.
- `@car arrive | ride | leave | off`: persistent vehicle state. `arrive` parks beside the subject, `ride` carries up to
  three cast members through an outdoor travel shot, `leave` drives away, and `off` removes it. During `ride`, only
  `@do car: broken` is allowed; use `@car off` before staging the cast outside it.
- `@dogs N`: persistent pack of 0–6 dogs. Dogs chase during travel shots and idle or bark at the edges otherwise.
  Use `@dogs 0` to clear them.
- `@runners N`: persistent background runners, 0–6. They run with the scroll in travel shots and cross behind the cast
  in ordinary shots. Use `@runners 0` to clear them.
- `@crowd <mood> [N]`: one anonymous background crowd, with mood `cheer`, `angry`, `gasp`, or `neutral`; N is 1–12,
  default 8. `@crowd off` clears it. Crowds stand behind the stage and are omitted from travel shots. Change the mood
  as the scene turns: cheer → neutral → gasp, or angry for a hostile mob.
- `@crowd <group> <mood> [N]`: a named team, such as `red` or `blue`. Named teams occupy opposing sides and face
  inward. Use `@crowd <group> off` to clear one team. `@crowd <group> fight <target>` gives the team a fighting pose
  aimed at another named team; use the command for both teams when they are fighting each other.
- `@crowd-look <group>: <top>, <headwear>, <legwear>`: assigns wardrobe to every member of a named crowd team.
  Items may be built-ins or IDs from the wardrobe library. For example: `@crowd-look red: suit, flat_cap, trousers`.
  Set this before or after creating the team; it persists until the set changes or another look is assigned.
- `@crowd-weapon <group>: <prop>`: assigns a held prop to every member of a named crowd team. The prop must be a
  built-in prop or an ID from the props library, such as `@crowd-weapon red: rifle`. Use this for weapons, banners,
  tools, torches, or any repeated group object.

Two-team battle example:

```md
@set battlefield
@cast general_a, general_b
@weather storm heavy
@crowd-look red: suit, flat_cap, trousers
@crowd-look blue: suit, flat_cap, trousers
@crowd-weapon red: rifle
@crowd-weapon blue: rifle
@crowd red angry 8
@crowd blue angry 8
@do general_a: point
General A ordered the red army forward.
@do general_b: point
General B ordered the blue army forward.
@crowd red fight blue
@crowd blue fight red
The armies charged—and accidentally fought each other.
```

The main cast remains in the foreground while the named teams occupy opposite background halves. Use the cast for
commanders, witnesses, or a narrator; use crowd teams for armies, mobs, fans, rival factions, processions, or repeated
background characters. Add custom `military` wardrobe and `rifle` prop entries to the library when the built-ins do not
fit the story's period or design.

### Next-line staging

- `@do <cast>: <action> [prop] [target]`: controls the next narration line and must name cast members currently in
  `@cast`. Actions include `idle`, `talk`, `point`, `react`, `wave`, `cheer`, `angry`, `gasp`, `walk`, `run`, `stagger`,
  `lie`, `collapse`, `eat [prop]`, `give <prop> <target>`, `carry <target>`, `support <target>`, `car: broken`, and
  custom actions. Several clauses may be comma-separated. A later `@do` before the narration line replaces the earlier one.
- `@face <cast>: <expression>`: sets a face for the next line: `neutral`, `happy`, `cheer`, `sad`, `angry`, `surprised`, `sleepy`,
  `cheeky`, `exhausted`, `worried`, or `dead`. `dead` draws X eyes. Use it for a reaction that narration words do not make
  clear; narration mood words can also change faces during the line.
- `@fx drop | shake | pop`: animates the next line's caption. Use `shake` for impact, `pop` for a reveal, and `drop` for
  a dramatic entrance or punchline. Use sparingly.
- `@fx lightning [cast | prop]`: creates one lightning bolt and flash beside a cast member or the holder of a prop on
  the next line. Maximum 3 per part. It is useful for divine entrances, weapon reveals, and major reversals.
- `@sfx <id> [volume 0-1]`: plays a library sound on the next line. Maximum 5 per part and never on back-to-back lines.
  Use a riser before a reveal, an impact on a strike, or a location sound to establish a scene.
- `@background-music <track> [volume 0-1]`: starts a named music file from the Stickman History Shorts pack and keeps
  it under the narration until another `@background-music` changes it. The default volume is `0.15` (about 15%); use
  `@background-music off` to stop it. Track IDs: `monkeys-spinning-monkeys`, `comedy-quirky-sneaky`, `sneaky-snitch`,
  `cartoon-pizzicato`, `fluffing-a-duck`, `scheming-weasel-faster`, and `funny-comedy-quirky`.
- `!! <line>`: the twist line. The line is read aloud and gets a push-in, roll, music stop, and low hit. Use it for the
  final reversal, not for ordinary emphasis.

`@do` actions:
- `idle talk point react wave cheer angry gasp walk run stagger lie collapse`
- `eat [prop]`, `give <prop> <target>`, `carry <target>` (exactly 2 carriers), `support <target>` (1 or 2)
- `car: broken` (car on stage)
- Custom actions, optionally aimed: `@do marcus: attack-with-spears neptune` (faces them and lunges toward them, never
  past; too close: strikes where they stand)
- Several characters on one line: one `@do` line, comma separated: `@do fred: lie, amy: wave`. A second `@do` line
  before the same narration line replaces the first.

### Less-obvious directive behavior

- Indentation is allowed: `  @do fred: wave` is still a directive. Any line whose first non-space character is `@` is
  silent and is removed from the TTS script.
- Directive lines do not consume a narration line. You can stack `@do`, `@face`, `@fx`, `@sfx`, and other state changes
  immediately above one narration line; all next-line directives apply to the next spoken line.
- `@do <cast>, <cast>: <action>` applies one action to several cast members. Multiple clauses can mix actions, for
  example `@do fred: point, amy: gasp`. A cast member may not receive two actions in the same directive.
- `@face fred, amy: surprised` and `@look fred, amy: armour` target several cast members at once. `@look ...: default`
  returns each member to their own base look.
- `@do <cast>: eat` automatically uses an apple when no prop is named. `give` accepts the prop and target in either
  order, as long as one argument is a known prop and the other is a cast target. `carry` requires exactly two carriers;
  `support` accepts one or two.
- Custom `@do` actions may take one target: `@do cassius: attack-with-spears caligula`. The target is faced or moved
  toward according to that action; the action does not automatically add the target to `@cast`.
- `@fx lightning` can target a cast id, a prop id, or no target. A prop target resolves to whoever holds that prop on
  the next line, including a prop supplied by a named `@look` or a previous `give`. If another lightning directive is
  placed before any narration, the later one replaces the earlier pending strike.
- Several `@sfx` lines may be stacked above the same narration line and all attach to it. `@sfx id 0.6` overrides the
  library sound's default volume only for that use. A sound left without a following narration line is reported by
  `check-story`.
- When there is no explicit `@do`, the planner infers actions from narration words such as `walked`, `ran`, `waved`,
  `laughed`, or `gasped`. Explicit `@do` wins over that inference; `@face` wins over the inferred face for its line.
- A line that cannot fit a walking or running action may be kept in place rather than forced off the stage. Use a
  deliberate in-place action such as `react`, `angry`, `gasp`, or `cheer` when the beat must remain visible.

### Staging (required: the video shows only what directives and names tell it)
- New place, new `@set`, then a fitting `@weather`: `storm` sea, gods, war, villains; `rain` loss; `fog` mystery;
  `snow` / `wind` journeys.
- Match the era: built-in sets are modern. Past stories use a period set from the inventory, or add one under SETS.
- Name a cast member in every line (the planner picks who acts by name).
- Faces:
  - A line's first mood word (angry, laughed, sobbed, gasped, scared...) sets the named character's face; each later
    mood word switches it ("grinned, then screamed" = happy, then angry).
  - No mood word: `@do angry | gasp | react | cheer` or `@face`.
  - Otherwise the default face shows: every emotional beat needs one of these.
- Direct every line: a `@do` and / or `@face` on nearly every narration line (the Model part: 11 of 12
  lines have a `@do`, 8 a `@face`). An undirected line plays as generic idle shots.
- Groups: `@crowd` with the right mood, changed as the scene turns (cheer, then neutral, then gasp); `@dogs`,
  `@runners` where they fit.
- Objects are seen: props held through a `@look` switched on the line they are first used (coins before the give,
  the spear before the attack).
- Punch: `@fx shake` or `drop` on line 1 (hook), `@fx pop` on line 3, `@fx drop` or a `@sfx` (`camera_flash`,
  `metallic_riser`) on the rehook line, `@fx lightning` on one to three big beats.
- Thirty or more directives besides `@set` and `@cast` (the model part has 38).

### Entrances, attacks, deaths (do these exactly)
- Sudden entrance: a character is not in `@cast` until the line they appear on; add them with a new `@cast` right
  above it. Anyone on stage earlier stands, walks and gets moved around by the planner.
- Attack: the attacker enters on the strike line and plays an aimed action at the victim:
  `@do cassius: attack-with-spears caligula`. Never `run` / `walk` to reach someone: that roams around them.
- The victim reacts on the strike line: `@face caligula: surprised` (or `worried`).
- Death: `@do <victim>: collapse` + `@face <victim>: dead` on the next line. On every later line of that scene keep
  them down: `lie` in that line's shared `@do` plus `@face <victim>: dead` (else they stand up again).
- Every on-stage character with a role in the beat gets the `@do`; bystanders stay idle (no `@do`).
- Moving actions (`walk`, `run`, `stagger`) need free stage room: with four or more on stage they often have none and
  play as idle. Use an in-place action there (`react` for a hit, `gasp`, `angry`, `cheer`, an in-place custom action).

### Scene shape (the model part)
- Build-up scene: one `@set`, the full cast, a crowd, six or seven lines of escalation.
- Payoff scene: a time jump ("Months later, ...") on a new `@set` with moodier `@weather`, a small cast (one or two),
  the strike and the fall in two lines, then the `!!` twist.
- Raise the weather toward the twist: clear, then fog, then storm as a god or villain arrives.
- The twist character may enter on the `!!` line itself: `@cast` adds them, their signature custom action plays,
  `@fx lightning <prop>` hits what they hold, `@sfx riser` + `@sfx bass_impact`.
- Use the inventory: follow "use for" notes, switch on cast looks, give characters their custom actions (a god raises
  a trident before `@fx lightning`).

### Sound effects
- Real ids and purposes: inventory list. Defaults:
  - `fahhh`: the hook (plays after its line)
  - `camera_flash`: smooth transition
  - `metallic_riser`, `riser`: tension before a payoff (end as the line starts)
  - `right` / `wrong`: positive / negative
  - `vine_boom`: comedy only
  - `bass_impact`: weight before the main reveal
  - `core`: a statement, emphasis
  - `among_us`: unexpected reveal (traitor, fake)
  - `pop` / `click`: pop-up text, UI
  - `glitch`: transition between clips
  - `money`: money moments only
- `@sfx` goes directly above its narration line (next to `@do` / `@fx` is fine). Volume overrides: `@sfx riser 0.6`.
- Risers only right before a payoff, usually the `!!` line.
- Default: `fahhh` on line 1 of part 1; `riser` + `bass_impact` (or `among_us`) on the twist.


## Model part (copy the staging, not the story)
A finished part that played exactly as written: the standard every part should match.
- Series library: sets `colosseum`, `roman-street` (period sets); custom actions `attack-with-spears`, `raise-trident`;
  looks `caligula: coins` (prop `stack-of-silver-coins`), `marcus: shell`, `cassius: spear`; Neptune holds a
  `trident`. Use your own inventory's ids.
- 116 words, 12 lines, a name in every line; 38 directives besides `@set` and `@cast`; 11 lines with a `@do`, 8 with
  a `@face`.
- Loops: hook = line 1 (a parade for seashells); intensifier = lines 2 to 5 (a hundred coins, Rome cheered instead,
  a seashell crown, one sandal); rehook = lines 7 and 8 at words 55 to 75 (Caligula mocks Cassius, who starts
  counting the days); twist = the `!!` line.
- Scenes: build-up in the colosseum with a crowd whose mood turns (cheer, neutral, gasp); then a time jump to a
  foggy street: Caligula alone, Cassius appears and strikes on one line, Caligula falls on the next and stays down,
  and Neptune arrives on the twist line as the storm breaks.

```md
# The Seashell Parade

@set colosseum
@weather clear
@cast caligula, cassius, marcus, lucius
@crowd cheer 12
@fx shake
@face caligula: happy
@sfx fahhh
Caligula threw Rome a giant victory parade for seashells!
@look caligula: coins
@do caligula: give stack-of-silver-coins marcus
@face caligula: happy
Caligula paid Marcus one hundred silver coins for the win.
@do cassius: react
@fx pop
Cassius thought Rome would laugh. Rome cheered instead.
@look marcus: shell
@do marcus: cheer
Marcus waved his seashell like a golden crown.
@do lucius: walk
@sfx vine_boom
Lucius marched proudly in his one remaining sandal.
@crowd neutral 12
@do caligula: point
@face caligula: happy
Caligula told the senators to bow to the conqueror of the sea.
@crowd gasp 12
@do caligula: point
@face caligula: cheeky
Caligula pointed at Cassius and mocked him in front of everyone.
@do cassius: angry
Cassius gritted his teeth and started counting the days.

@set roman-street
@weather fog
@cast caligula
@do caligula: walk
@face caligula: happy
Months later, Caligula strolled down a quiet Roman street.
@cast caligula, cassius
@look cassius: spear
@do cassius: attack-with-spears caligula
@face caligula: surprised
@fx lightning cassius
@sfx among_us
Cassius jumped out with his spear and a very long grudge.
@do caligula: collapse
@face caligula: dead
Caligula, conqueror of the ocean, lost to one angry soldier.
@cast caligula, cassius, neptune
@weather storm medium
@do neptune: raise-trident, caligula: lie
@face neptune: happy
@face caligula: dead
@fx lightning trident
@sfx riser
@sfx bass_impact
!! Neptune rose from a puddle, raised his trident and laughed last.
```

Why it works, line by line:
- Line 1: hook with a name and an absurd claim, `@fx shake`, `fahhh`, a happy face, a cheering crowd.
- Line 2: the coins look is switched on the line the give uses them; the target (`marcus`) is on stage.
- Line 3: the flip ("should laugh ... cheered instead") gets `@fx pop` and a reaction.
- Lines 6 to 8: the crowd turns (neutral, gasp) as the mood turns; a cheeky face on the insult; Cassius's anger plants
  the rehook.
- Line 9: the time jump opens a new set, foggy, with Caligula alone: nobody waits on stage for a later beat.
- Line 10: Cassius enters on his line, spear look on, aimed attack, victim surprised, lightning and `among_us`.
- Line 11: `collapse` + `dead`. Line 12: still `lie` + `dead` in the shared `@do`, while the twist character enters
  with his custom action, lightning on his trident, `riser` + `bass_impact`.
- Nothing after the `!!` line: the app adds the silent "Follow for more" screen.
