## Format
- Line 1 `# Title`, blank line. One directive per line, alone, above its narration line.
- Keep narration as given. Speaker lines `<cast id>: words`; the speaker must be in `@cast`. `!! line` = final twist, nothing after it.
- Next line only: `@do @face @cam @fx @sfx @pause @pace` (a narration line must follow). Everything else persists until changed.

## Directives
- `@set <id>`: new place/time jump; required before line 1. Resets crowds, positions. Then `@weather clear|rain|snow|fog|wind|storm [light|medium|heavy]` (storm = war/gods/villain, rain = loss, fog = mystery, snow/wind = journey).
- `@cast a, b`: on stage (max 12, 6 in front). Sudden entrance = new `@cast` right above the entrance line.
- `@look <cast>: <look>`: only looks listed on that cast member; `default` = own outfit. Lasts until changed.
- `@hold <cast>: <prop> [left|right]` / `none`: keeps a prop in hand.
- `@ride <rider>: <creature>` / `none`: rider stays in the saddle while mount is in `@cast`; saddle allows only idle talk point wave react gasp angry cheer give receive.
- `@car arrive|ride|leave|off`.
- `@item <tag>: <item> [sky|back|mid|stage] [far-left|left|center|right|far-right] [state]`, `@item <tag>: state <s>`, `@item <tag>: remove`. Drawn items only.
- `@dogs N`, `@runners N` (0-6). `@crowd <mood> [N]` mood cheer|angry|gasp|neutral, `@crowd off`; teams: `@crowd <group> <mood> [N]`, `@crowd <group> fight <other>`, `@crowd-look <group>: top, headwear, legwear`, `@crowd-weapon <group>: <prop>`.
- `@do <cast>: <action>`: actions idle talk point react wave cheer angry gasp walk run stagger lie collapse, `eat [prop]`, `give <prop> <target>`, `carry <target>` (2 carriers), `support <target>`, `car: broken`, custom actions (`@do marcus: attack-with-spears neptune`). Comma-separate several: `@do fred: lie, amy: wave`. Item use: `@do <cast>: pickup|drop|open|close|push|sit|enter|exit <tag>`; `@do <tag>: fly|drive left|right [slow|fast]`.
- `@face <cast>: <expression>`: neutral happy cheer sad angry surprised sleepy cheeky exhausted worried dead smug proud love excited relieved laughing wink furious annoyed disgusted crying scared embarrassed jealous guilty confused thinking suspicious shocked deadpan bored facepalm_ready dizzy drunk knocked_out evil crazy blank sick.
- `@cam [wide|medium|close|low|high|over_shoulder] [push_in|pull_out|truck_left|truck_right|crane_up|crane_down|hold] [fast] [shake] [dutch deg]`: key beats only (2-3 per part).
- `@fx drop|shake|pop` (caption), `@fx lightning [cast|prop]` (max 3 per part). `@sfx <id> [vol 0-1]` (max 5 per part, never back-to-back lines). `@background-music calm|mysterious|funny|scary|off [vol]`. `@pause 0-3`, `@pace slow|fast`.

## Staging rules
- New place = new `@set` + fitting `@weather`. Match the era with a period set from the inventory.
- Lines 1-3 name nobody: give each a `@do` for whoever acts. From line 4 on, name a cast member in every line.
- Direct nearly every line with `@do` and/or `@face`. Every emotional beat needs a mood word, `@face` or an emotional `@do`. An undirected line plays as generic idle.
- Props are seen: `@hold` or switch `@look` on the line they are first used.
- Crowds change mood as the scene turns (cheer, neutral, gasp).
- Punch: `@fx shake|drop` on line 1, `@fx pop` on the flip, `@fx lightning` on 1-3 big beats. At least 10 directives besides `@set` and `@cast`.
- Use the inventory: follow "use for" notes, cast looks and custom actions.

## Entrances, attacks, deaths
- Entrance: new `@cast` right above the line they appear on.
- Attack: attacker enters on the strike line with an aimed action: `@do cassius: attack-with-spears caligula`. Never `run`/`walk` to reach someone. Victim reacts on that line (`@face ...: surprised`).
- Death: `@do victim: collapse` + `@face victim: dead`; on every later line of the scene `lie` + `dead` again.
- Only characters with a role in the beat get a `@do`; bystanders stay idle.
- `walk`/`run`/`stagger` need room: with 4+ on stage use an in-place action (`react`, `gasp`, `angry`, `cheer`).
- Scenes: build-up in one `@set` with crowd; payoff after a time jump on a new `@set`, moodier weather, small cast. Raise weather toward the twist.

## Sounds
- `fahhh` hook (line 1 of part 1); `riser`/`metallic_riser` before the payoff; `bass_impact` reveal weight; `among_us` unexpected reveal; `vine_boom` comedy; `camera_flash`/`glitch` transitions; `right`/`wrong`; `money` money only. Real ids: inventory.

## Example (shape only)
```md
# The Seashell Parade

@set colosseum
@weather clear
@cast caligula, cassius, marcus
@crowd cheer 12
@fx shake
@face caligula: happy
@do caligula: wave
@sfx fahhh
An emperor threw Rome a giant parade for seashells!
@look caligula: coins
@do caligula: give stack-of-silver-coins marcus
He paid his champion one hundred silver coins.
@set roman-street
@weather fog
@cast caligula
@do caligula: walk
Months later, Caligula strolled down a quiet street.
@cast caligula, cassius
@look cassius: spear
@do cassius: attack-with-spears caligula
@face caligula: surprised
@fx lightning cassius
@sfx among_us
Cassius jumped out with his spear and a long grudge.
@do caligula: collapse
@face caligula: dead
Caligula lost to one angry soldier.
@cast caligula, cassius, neptune
@weather storm medium
@do neptune: raise-trident, caligula: lie
@face caligula: dead
@fx lightning trident
@sfx riser
!! Neptune rose from a puddle and laughed last.
```
