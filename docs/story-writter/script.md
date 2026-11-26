## Script format

- Line 1 `# Title`, then a blank line.
- One directive per line, alone.
- `@do`, `@face`, `@cam`, `@fx`, `@sfx`: next narration line only (one must follow). Others last until changed.
- Narration: plain text, numbers as words; no digits, symbols, abbreviations, parentheses, markdown.
- A cast member's own line: `<cast id>: words` (the id in lowercase, e.g. `kai: Everyone alive?`); quotes around the words are optional. Every other text line is the narrator's. The narrator and the cast never speak at once: one line, one voice. A spoken twist is `!! kai: Then we walk.` Only start a line with `word:` for a speaker: a narrator line never begins with a lowercase word and a colon. The speaker must be on stage (`@cast`) to be seen talking; the others turn to them, and a quick back-and-forth plays in one held wide shot. In a story with cast lines nobody mouths the narrator's lines (use `@do` for what people do meanwhile).

## Story quality (required)

Write like a human storyteller, not a viral-content template. The story must feel specific to its characters and situation, not assembled from familiar short-form hooks.

- Give each important character a believable motive, personal stake, and distinct personality. Their choices should make sense to them, even when flawed.
- Make dialogue sound natural and character-specific. Avoid lines that exist only to explain the plot to the audience.
- Show emotion through actions, reactions, hesitation, choices, and small details instead of repeatedly naming the emotion.
- Build tension from cause and effect. Let events create questions naturally; do not manufacture suspense with empty announcements.
- Use concrete, memorable details that belong to this story. Avoid generic dramatic wording that could fit any story.
- Let reveals emerge from earlier details. Foreshadow subtly, then let the audience connect the pieces. Do not explain a twist after revealing it.
- Vary sentence length and rhythm. Use short sentences when the moment earns them, not as the default style.
- Avoid clickbait phrasing and narrator prompts such as "Here's where it gets weird", "Watch what happens", "You won't believe", or "But then things changed".
- Avoid excessive fragments, fake countdowns, arbitrary numbers, repeated rhetorical questions, and overdramatic claims.
- Do not force a twist, villain, death, or surprise ending when the story does not need one. Make the ending feel earned.
- Keep the narration clear and speakable. Every line should add meaningful action, character, emotion, atmosphere, or information.
- Preserve the required script format and staging rules below. Story quality never permits breaking directives, cast IDs, line limits, or output structure.
  The hook should come from an unusual but meaningful situation or character choice, not clickbait wording. Make the audience care about the people before asking them to care about the reveal.

## Directives

- Directives are silent and must occupy their own line. They are never sent to TTS.
- Persistent directives (`@set`, `@weather`, `@mood`, `@cast`...) remain active until changed. `@do`, `@face`, `@cam`, `@fx`, `@fx lightning`, and `@sfx` apply to the next narration line only.

### Persistent scene state

- `@set <id>`: place the following lines in a set. Required before the first line. A set change resets the crowd teams,
    crowd wardrobe/weapons, runners, and actors' positions, then applies the set's weather default. The car remains in its
    current directive state until `@car off` or another car mode. Use `@set` for a new location,
    time jump, or establishing shot.
- `@weather clear | rain | snow | fog | wind | storm [light | medium | heavy]`: persistent weather until another
    `@weather` or `@set`. Intensity defaults to medium. Use storm for war, gods, or villains; rain for loss; fog for mystery;
    snow or wind for a journey. A new set starts with its configured default weather, or clear.
- `@mood tense | dark | flashback | bright | off`: persistent scene tone until another `@mood` or `@set` (a new set
    starts neutral). It shifts the lighting, fog haze and colour of the whole frame and eases in over a third of a second.
    `tense` (a threat closing in: harder contrast, drained colour, a red edge), `dark` (night, a cellar, grief: dim and
    cool), `flashback` (memory: washed-out sepia haze), `bright` (relief, triumph, a sunny morning: warm and lifted).
    Use it on turns of the story, two or three per part; `off` returns to neutral. It stacks with `@weather`.
- `@cast a, b`: the characters on stage. The character named in the narration, or named by `@do`, is staged in front.
    Maximum 12 cast members; maximum 6 fit in the front row. Remove someone by writing a new `@cast` without them.
    A sudden entrance is a new `@cast` immediately above the entrance line.
- `@look <cast>: <look>`: switches a cast member to a named look. Looks come only from that member's cast entry
    (its `looks`, listed with the cast); `default` always exists and puts their own outfit back. The look stays on for
    the rest of the part, across `@set` changes, until another `@look`; each part starts in `default`. A look can
    also hold props (a look with `"props"`). A creature (cat, horse...) wears only custom headwear, face, accessory
    and back items (a crown, a saddle); no top, legwear, footwear, hair or built-in hat: use `@face` or `@do` for it. A creature's look can set its flame (`"flame": "low"` or `"high"`: fire on
    the mane, tail and hooves, eyes glowing; `"off"` puts it out), e.g. `@look charro-horse: blazing`.
    `  @look ethan: crown
  Ethan crowned himself.           <- wears the crown from here on
  @look ethan: default
  He took it off.                  <- back to his own outfit
 `
- `@hold <cast>: <prop> [left | right]`: puts a prop in a hand (right by default) from the next line for the rest of
    the part, on top of the current look (it replaces only that hand, and stays through later `@look` changes).
    `@hold <cast>: none [left | right]` empties a hand; `none` without a hand empties both. Use it for any object a
    character keeps holding; `@do give` / `eat` only use a prop for one line. Creatures without hands cannot hold.
    `  @hold ethan: grocery-receipt
  Ethan stared at the deed.        <- holds the receipt from here on
  @hold ethan: flip-phone left
  His phone rang.                  <- receipt in the right hand, phone in the left
  @hold ethan: none
  He dropped everything.
 `
- `@ride <rider>: <creature>`: a person rides a creature (horse...) from the next line until `@ride <rider>: none` or
    the end of the part, across `@set` changes. Rider and mount are one wider actor: move the mount
    (`@do charro-horse: walk`) and the rider goes along. In the saddle the rider can only idle, talk, point, wave,
    react, gasp, angry, cheer, give or receive; any other `@do` falls back to idle (check-story warns). One rider per creature, get off
    before riding another; `@car ride` seats everyone in the car instead. The mount is a cast member with a creature
    body (the cast list marks it "rideable"); one named after a person (`charro-horse`) is that person's mount.
    Whenever a rider and their mount share `@cast`, put the rider in the saddle by default, even when the narration
    never says "rode": a horseman stays on his horse. Get off (`@ride charro: none`) only for a beat the saddle cannot
    do (eat, walk, fight...) or when the narration puts them on foot. Narration that has someone riding with no
    mount in the cast: write `MISSING: cast <id>: <creature> for <rider> to ride`.
    `  @ride charro: charro-horse
  @do charro-horse: walk
  Charro rode into town.           <- the horse walks, Charro sits in the saddle
  @ride charro: none
  He got down by the well.         <- standing beside the horse
 `
- `@car arrive | ride | leave | off`: persistent vehicle state. `arrive` parks beside the subject, `ride` carries up to
    three cast members through an outdoor travel shot, `leave` drives away, and `off` removes it. During `ride`, only
    `@do car: broken` is allowed; use `@car off` before staging the cast outside it.
- `@item <tag>: <item> [sky | back | mid | stage] [far-left | left | center | right | far-right] [state]`: puts a drawn
    World Item (listed as "drawn" under WORLD ITEMS) on stage until `@item <tag>: remove` or the next `@set`. The tag is
    your name for it in later lines (not a cast id). The layer defaults to the item's own; the spot defaults to center;
    the state to its first. `@item <tag>: state <state>` switches state from the next line on. `@do <tag>: fly left |
  right [slow | fast]` (or `drive`) carries it across the next line, off screen that way, at most 4 units/s (slow 2,
    fast 8): on a short line it crosses the middle of the view instead of rushing the whole way; flying the same way again brings it back
    in from the other side. `remove` and `state` are reserved words, never state names.
    `  @item ship: saucer back
  @item ship: state flying
  @do ship: fly left
  Something silver shot across the sky.   <- the ship crosses the whole line
  @item ship: remove
 `
- Using an item: `@do <cast>: <pickup | drop | open | close | push | sit | enter | exit> <tag>` (one cast member per
    clause, the item a drawn one on stage with that capability; stage items stand within reach beside the cast). A
    character out of reach walks over first, in the first part of the line (check-story warns when the line is too
    short for the walk: place the item closer or add a line).
    `pickup` puts it in a free hand (its prop) for the rest of the set until `drop` puts it back down at their feet;
    one held item per character. `open` / `close` switch it mid-line. `sit` keeps them seated until their next `@do`
    (`@do <cast>: stand` gets up). `enter` seats
    the character inside until `exit`: inside, they ride along when the item moves (`@do pod: fly right`) and no other
    `@do` is allowed for them.
    `  @item pod: escape-pod
  @do mia: open pod
  The hatch hissed open.
  @do mia: enter pod
  She climbed in.
  @do pod: fly right
  And she was gone.
 `
- `@dogs N`: persistent pack of 0–6 dogs. Dogs chase during travel shots and idle or bark at the edges otherwise.
    Use `@dogs 0` to clear them.
- `@runners N`: persistent background runners, 0–6. They run with the scroll in travel shots and cross behind the cast
    in ordinary shots. Use `@runners 0` to clear them.
- `@crowd <mood> [N]`: one anonymous background crowd, with mood `cheer`, `angry`, `gasp`, `salute`, or `neutral`; N is 1–12,
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
    `@cast`. Actions include `idle`, `talk`, `point`, `react`, `wave`, `cheer`, `angry`, `gasp`, `salute`, `walk`, `run`, `stagger`,
    `lie`, `collapse`, `eat [prop]`, `give <prop> <target>`, `carry <target>`, `support <target>`, `car: broken`, and
    custom actions. Several clauses may be comma-separated. A later `@do` before the narration line replaces the earlier one.
- `@face <cast>: <expression>`: sets a face for the next line: `neutral`, `happy`, `cheer`, `sad`, `angry`, `surprised`, `sleepy`,
    `cheeky`, `exhausted`, `worried`, `dead`, `smug`, `proud`, `love`, `excited`, `relieved`, `laughing`, `wink`, `furious`, `annoyed`, `disgusted`, `crying`, `scared`, `embarrassed`, `jealous`, `guilty`, `confused`, `thinking`, `suspicious`, `shocked`, `deadpan`, `bored`, `facepalm_ready`, `dizzy`, `drunk`, `knocked_out`, `evil`, `crazy`, `blank`, or `sick`.
    `dead` draws X eyes. Use it for a reaction that narration words do not make
    clear; narration mood words can also change faces during the line. With no `@face` and no mood word, the line's
    punctuation picks the speaker's face: a `!!` twist line is `shocked`, a line ending in `!` is `surprised`, a line
    ending in `?` is `confused` (a `!` or `?` mid-line does nothing). Use `@face <cast>: neutral` to keep a plain face.
- `@cam [angle] [move] [fast] [shake] [dutch <deg>]`: picks the camera for the next line's first shot; the planner
    chooses everything you leave out (and every other shot). angle: `wide`, `medium`, `close`, `low`, `high`,
    `over_shoulder` (needs two on stage); move: `push_in`, `pull_out`, `truck_left`, `truck_right`, `crane_up`,
    `crane_down`, `orbit_left` / `orbit_right` (the camera arcs up to 45° around the subject and stays centred on them; the side is where the camera drifts on screen), or `hold` (still); `fast` speeds a move up (a fast push punches in); `shake` jolts the camera on the
    line's first word; `dutch <deg>` tilts the horizon (-25..25). On a `!!` line the twist keeps its push and roll
    unless you give a move or `dutch`. `fast` works best with `push_in` / `pull_out`: trucks and cranes on close shots
    barely speed up (the camera slows them so the cast stays in frame). Key beats only (two or three a part), never every line:
    `@cam low crane_up` (someone rises to power), `@cam close push_in fast shake` (the reveal hits),
    `@cam dutch 15` (something is off).
- `@fx drop | shake | pop`: animates the next line's caption. Use `shake` for impact, `pop` for a reveal, and `drop` for
    a dramatic entrance or punchline. Use sparingly.
- `@fx lightning [cast | prop]`: creates one lightning bolt and flash beside a cast member or the holder of a prop on
    the next line. Maximum 3 per part. It is useful for divine entrances, weapon reveals, and major reversals.
- `@sfx <id> [volume 0-1]`: plays a library sound on the next line. Maximum 5 per part and never on back-to-back lines.
    Use a riser before a reveal, an impact on a strike, or a location sound to establish a scene.
- `@background-music <track> [volume 0-1]`: starts a named music file from the Stickman History Shorts pack and keeps
    it under the narration until another `@background-music` changes it. The default volume is `0.5` (about 6 dB under the voice); use
    `@background-music off` to stop it. Without any `@background-music` the part plays the default synth loop (it stops on the `!!` line). Prefer the four moods, switching as the story turns: `calm` (the world at ease), `mysterious` (something unexpected happened, or is building up), `funny` (a funny moment) and `scary` (exploring the unknown). Named tracks also work: `monkeys-spinning-monkeys`, `comedy-quirky-sneaky`, `sneaky-snitch`,
    `fluffing-a-duck`, `scheming-weasel-faster`, `funny-comedy-quirky`, `darkling` and `hus-hus-hus-numbers`.
- `@pause <seconds>` (0-3): silence before the next line, for comic timing (a beat before the punchline). `@pace
  slow | fast`: the next line spoken slower or faster. Both only shape a TTS voice (a recorded one keeps its own
    timing); the narrator and the cast still never overlap.
- `!! <line>`: the twist line. The line is read aloud and gets a push-in, roll, and low hit. Use it for the
    final reversal, not for ordinary emphasis.
  `@do` actions:
- `idle talk point react wave cheer angry gasp walk run stagger lie collapse`; the library's reaction micro-actions
    (`double-take`, `nervous-fidget`, `lean-in`, `sigh-slump`, `shock-jump`, `smug-nod`, `facepalm`, `point-quick`)
- `eat [prop]`, `give <prop> <target>`, `climb [up|down]` (the character walks up the set's stairs or slope, the camera rising with them; only in a set that has a `trail` in the library; they stay at the top until the next `@set`; one `climb` per line, the line should be 2 to 3 s of speech for a natural pace), `don <item>` (hands rise to the head, the headwear or back wardrobe item appears halfway through the line and stays on; face turns smug: `@do ethan: don crown`), `carry <target>` (exactly 2 carriers), `support <target>` (1 or 2)
- `car: broken` (car on stage)
- Custom actions, optionally aimed: `@do marcus: attack-with-spears neptune` (faces them and lunges toward them, never
    past; too close: strikes where they stand)
- Several characters on one line: one `@do` line, comma separated: `@do fred: lie, amy: wave`, or several `@do`
    lines before the same narration line (`@do ship: fly left`, then `@do bob: walk`): they all apply, as long as each
    names different characters or items. The same one in two `@do` lines is an error ("two @do for bob on one line").

### Less-obvious directive behavior

- Indentation is allowed: `  @do fred: wave` is still a directive. Any line whose first non-space character is `@` is
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
    A walk word (`came`, `went`, `left`, `ran`...) moves only a character the phrase names ("Bob came back" walks Bob;
    "the saucer came back" walks nobody). A pronoun (`he`, `she`, `they`, `you`...) points back at the character last
    named, so "he came back" walks them; outdoors a walk turns the shot into a travel shot. check-story warns on each
    pronoun walk; `@do <cast>: idle` (or any `@do` for them) stops it. Nobody seated or inside an item walks from a word.
- A walk over several shots of one sentence keeps going the same way (it stops at the stage edge, never turns back).
- A line that cannot fit a walking or running action may be kept in place rather than forced off the stage. Use a
    deliberate in-place action such as `react`, `angry`, `gasp`, or `cheer` when the beat must remain visible.

### Staging (required: the video shows only what directives and names tell it)

- New place, new `@set`, then a fitting `@weather`: `storm` sea, gods, war, villains; `rain` loss; `fog` mystery;
    `snow` / `wind` journeys.
- Match the era: built-in sets are modern. Past stories use a period set from the inventory, or add one under SETS.
- Name a cast member in every line from line 4 on (the planner picks who acts by name). Lines 1 to 3 name nobody, so
    give each of them a `@do` for whoever acts.
- Faces:
    - A line's first mood word (angry, laughed, sobbed, gasped, scared...) sets the named character's face; each later
      mood word switches it ("grinned, then screamed" = happy, then angry).
    - No mood word: `@do angry | gasp | react | cheer` or `@face`.
    - Otherwise the default face shows: every emotional beat needs one of these.
- Direct every line: a `@do` and / or `@face` on nearly every narration line (the Model part: 12 of 12
    lines have a `@do`, 8 a `@face`). An undirected line plays as generic idle shots.
- Groups: `@crowd` with the right mood, changed as the scene turns (cheer, then neutral, then gasp); `@dogs`,
    `@runners` where they fit.
- Objects are seen: props held through a `@hold` (or a `@look`) switched on the line they are first used (coins before the give,
    the spear before the attack).
- Punch: `@fx shake` or `drop` on line 1 (hook), `@fx pop` on line 3, `@fx drop` or a `@sfx` (`camera_flash`,
    `metallic_riser`) on the rehook line, `@fx lightning` on one to three big beats.
- Reactions: sprinkle the library's reaction micro-actions on the beat they belong to instead of a plain `react`:
    `shock-jump` (jump scare, sudden reveal), `double-take` (a second look at something absurd), `facepalm` (someone's
    stupidity), `sigh-slump` (defeat, bad news), `smug-nod` (pleased with themselves), `nervous-fidget` (worried, caught
    out), `lean-in` (secrets, listening), `point-quick` (an accusing jab). Pair each with a matching `@face`
    (`shock-jump` + `surprised`, `facepalm` + `facepalm_ready`, `smug-nod` + `smug`). Only use ids that are in the
    inventory; one per beat, never on every line. `shock-jump` and `double-take` also snap the camera in.
- Comic timing: put `@pause 0.4` to `@pause 0.6` right above the line that delivers a punchline or the `!!` twist, so
    the audience gets a beat of silence first (once or twice per part, not every joke).
- Mood: set `@mood` when the tone turns (`tense` into the strike, `dark` for the night scene, `flashback` for a memory
    set, `bright` for the relief), and `@mood off` when it ends.
- Thirty or more directives besides `@set` and `@cast` (the model part has 39).

### Direction playbook (make full use of the engine: nobody just stands and narrates)

The picture must show what the line says. For every narration line ask five questions, in this order, and answer each with a directive:

1. **Who acts?** The one the line is about (lines 1 to 3: a `@do` names them). Everyone else stays idle.
2. **What do they physically do?** A `@do` for the verb of the line, never `talk` or `idle` for an act. Map the verb:
    - puts on / wears / crowns / dons something: `@do <id>: don <item>` (a `headwear` or `back` wardrobe item that is in the library, e.g. `crown`, `cape`): the hands rise, it appears halfway through the line and stays on until their `@look` changes. A whole outfit change = `@look`.
    - hands over / receives: `@do <id>: give <prop> <target>`. Eats: `eat <prop>`. Picks up / opens / pushes / sits on a drawn thing: `@do <id>: pickup|open|push|sit <item tag>` after `@item <tag>: ...`.
    - strikes / fights: an aimed custom action (`attack-with-spears <target>`). Falls: `collapse`, then `lie` + `dead`.
    - climbs a mountain, stairs or a slope: `@do <id>: climb` (up) or `climb down`, in a set with a `trail`; plain `walk` only crosses flat ground.
    - goes somewhere: `walk` / `run` (only with free room). Points, waves, cheers: `point`, `wave`, `cheer`.
    - reacts: the reaction actions (`shock-jump`, `double-take`, `facepalm`, `sigh-slump`, `smug-nod`, `nervous-fidget`, `lean-in`, `point-quick`).
3. **What do we see them holding or wearing?** Switch it on the line it first matters: `@hold <id>: <prop> [left|right]` (the note, the newspaper, the bag), `@look <id>: <look>` for a different outfit (broke / rich / emperor), `@item` for a big drawn object. Take it away with `@hold <id>: none` the moment they lose it ("lost everything").
4. **What is the face?** `@face <id>: <expression>` on every emotional beat (smug on a power move, scared on a loss). Narration mood words also change it.
5. **Where is the camera?** Only on the beats that matter, `@cam` (see below). Everywhere else the planner already cuts and drifts, and it arcs around the subject on medium, close and low shots.

Camera (`@cam [angle] [move] [fast] [shake] [dutch deg]`, three or four key beats a part, never two in a row, never the same angle twice in a row):
- `orbit_left` / `orbit_right`: the camera arcs up to 45 degrees around the subject, who stays in the middle of the frame. The side is where the camera drifts on screen. Use it for a power move, a transformation, a reveal of what someone is (crowning, a new outfit, a villain's entrance): `@cam medium orbit_left` above the line.
- `push_in` (`fast` for a hit): a reaction, a secret, a threat closing in. `low crane_up`: someone rises to power. `high crane_down` / `pull_out`: someone is small, lost or alone. `dutch 12`: something is wrong. `shake`: an impact.
- The `!!` twist already pushes in and rolls: do not add a move unless you mean a different one.

Tone and scene shape: a new `@set` + `@weather` for every place or time jump; `@mood` two or three times a part on the turns (`flashback` for a memory, `tense` into the strike, `bright` for relief); a crowd (`@crowd`) wherever a public scene needs one; keep weather rising toward the twist.

Budget per part: 30 or more directives besides `@set` and `@cast`; every line with a `@do` or `@face`; one reaction action on each emotional turn (about four a part, never on every line); at most one `don` / `@look` change per character per beat; props and looks always switched on at the line where they are first seen.

Common mistakes: a line that names an act but only `talk`s or idles; a prop used with no `@hold` or `@look` before it; a character used before `@cast` adds them; forgetting to take the prop away; the same camera on every line (or an `@cam` on every line); `@pause` or voice-length changes after the voice is recorded (keep narration word for word).

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

## Model part (copy the staging quality, not the story or its narrative formula)

A finished part that played exactly as written (its first three lines since reworded to hide names): the standard every part should match.

- Series library: sets `colosseum`, `roman-street` (period sets); custom actions `attack-with-spears`, `raise-trident`;
    looks `caligula: coins` (prop `stack-of-silver-coins`), `marcus: shell`, `cassius: spear`; Neptune holds a
    `trident`. Use your own inventory's ids.
- Length: it predates the 45 to 55 s rule. A part now has 109 to 135 words (docs/story-writter/tts-shorts.md): match this part's staging
    density per line, not its length or its word positions.
- 120 words, 12 lines, no name in lines 1 to 3 and a name in every later line; 39 directives besides `@set` and
    `@cast`; 12 lines with a `@do`, 8 with a `@face`.
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
@do caligula: wave
@sfx fahhh
An emperor threw Rome a giant victory parade for seashells!
@look caligula: coins
@do caligula: give stack-of-silver-coins marcus
@face caligula: happy
He paid his champion one hundred silver coins for the win.
@do cassius: react
@fx pop
His own guard thought Rome would laugh. Rome cheered instead.
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

- Lines 1 to 3 name nobody ("An emperor", "his champion", "his own guard"); each line's `@do` says who acts.
- Line 1: hook with an absurd claim, `@fx shake`, `fahhh`, a happy face, a cheering crowd.
- Line 2: the coins look is switched on the line the give uses them; the target (`marcus`) is on stage.
- Line 3: the flip ("should laugh ... cheered instead") gets `@fx pop` and a reaction.
- Lines 6 to 8: the crowd turns (neutral, gasp) as the mood turns; a cheeky face on the insult; Cassius's anger plants
    the rehook.
- Line 9: the time jump opens a new set, foggy, with Caligula alone: nobody waits on stage for a later beat.
- Line 10: Cassius enters on his line, spear look on, aimed attack, victim surprised, lightning and `among_us`.
- Line 11: `collapse` + `dead`. Line 12: still `lie` + `dead` in the shared `@do`, while the twist character enters
    with his custom action, lightning on his trident, `riser` + `bass_impact`.
- Nothing after the `!!` line: the app adds the silent "Follow for more" screen.
