# Gap log

One row per limit a story hit. Newest at the bottom. Status: `open`, `workaround`, `closed`. When you hit a new wall:
add a row (what the story needed, the nearest workaround), then decide which fragment closes it.

| # | found in | what the story needed | status | closed by / workaround | fragment |
|---|---|---|---|---|---|
| 1 | Emperor Norton | camera arcing around the subject | closed | `orbit_left` / `orbit_right` (5f636fc); the planner orbits instead of trucking on subject shots | 04 |
| 2 | Emperor Norton | a character puts on an item mid-line (crown) | closed | `@do <cast>: don <item>` (975fe31); drops when `@look` changes (ff0b72c) | 03 |
| 3 | Emperor Norton | a flat rug in a set broke the stage-clearance rule | closed | flat boxes are floor decals (18afa9b) | - |
| 4 | Olympus | characters only walk on flat ground (the climb up the mountain) | closed | set `trail` + `@do <cast>: climb [up or down]` (0bf9395); set `olympus-stairs` | 02 |
| 5 | Olympus | cast voice acting needed a cast created first | closed | AI invents the characters, the app adds them (a827c2a) | 05 |
| 6 | Atlantis (planned) | swimming, diving, free movement at depth, underwater look | open | none; see 02 (volume surface + swim mode + water environment) | 02, 04 |
| 7 | Atlantis (planned) | sword fighting with a battle structure (strike, parry, exchange, knockback, formations) | open | one aimed action per line, `@crowd <group> fight <other>` | 03 |
| 8 | all | no collision: two characters on one trail or path overlap | workaround | one climber at a time | 02 |
| 9 | all | one action per cast member per line | workaround | one beat per line | 03 |
| 10 | all | the story AI learns a limit only when planning fails | open | feasibility pass | 01 |
