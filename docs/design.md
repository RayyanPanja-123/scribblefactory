# Dashboard design system

Soft-skeuomorphic: warm paper surfaces with raised cards and pressed-in wells, inside a dark device bezel.
Tokens live in `web/src/styles/tokens.css` (Tailwind `@theme`, so each token is both a CSS variable and a
utility: `--color-ink` → `text-ink`, `bg-ink`). Components there: `.raised`, `.inset`, `.chip`, `.btn`,
`.round-btn`, `.skeleton`, `.grain`, `.num`.

## Frame and surfaces
- Page `#111113`, bezel `#1c1c1e` (radius 36, 12 px padding), app surface `#f2efe9` (radius 24).
- Panels / cards `#f8f6f1`; wells `#ebe7df`.
- Paper grain: SVG `feTurbulence` noise at 3% opacity on the surface and every raised card (`::before`).

## Depth
- **Raised** (`.raised`, radius 24): white highlight top-left, warm-grey shadow bottom-right, 1 px inner top highlight.
  Hover deepens the shadow by fading in a second shadow layer (`::after` opacity), so only opacity animates.
- **Inset** (`.inset`, radius 16): inner shadows, for search, stat/chart wells, cast chips, stage strips.
- **Chips** (`.chip`): pill, soft inset, tinted background + dark ink text.
- **Buttons**: `.btn-primary` dark pill, white text, raised; `.btn-secondary` raised light pill. `:active` swaps
  the shadow for an inset one (sinks). Round icon buttons (`.round-btn`) are inset when active (`aria-current`).

## Colour
| Token | Hex | Use |
|---|---|---|
| ink | `#1f1d1a` | text (15:1) |
| muted | `#6b665d` | secondary **text** (5.0:1 on surface) |
| faint | `#8a857c` | icons, rules, large decorative numerals only (3.2:1: never body text) |
| green / red / amber / blue | `#2fa36b` `#e35b4f` `#f2b84b` `#4f7cf7` | fills, dots, lines: done-up / failed-down / waiting / running |
| *-ink | `#1b6b45` `#a8352b` `#7f5a10` `#2c4fb8` `#5c584f` | text on the matching tinted chip (all ≥ 4.9:1) |

The brief's muted `#8a857c` and the four accents fail WCAG AA as text on these surfaces, so text uses the darker
inks above and the original hues stay for non-text. Charts: YouTube `#4f7cf7`, Instagram `#9a6ff0`; series in
the donut cycle through `PALETTE` (`web/src/composables/ui.ts`). Cast swatches use each cast member's top colour.

## Type
- Inter (400/500/600) for UI, Fredoka (500/600) for headings and numbers (echoes the Fredoka One captions).
  Self-hosted via @fontsource, no CDN. Numbers use `.num` (tabular figures).

## Spacing and radii
- Spacing 4 / 8 / 12 / 16 / 24 / 32 (Tailwind's 4 px scale: `1 2 3 4 6 8`).
- Radii 12 / 16 / 24 / 36 (`rounded-sm / md / lg / frame`).

## Motion (motion-v)
- Springs: stiffness 320, damping 30 (`SPRING`). Transform and opacity only.
- Cards: hover lift y −5 + deeper shadow; press scale 0.97 (clickable cards only).
- Card grids enter staggered, 40 ms apart. KPI numbers count up on first load.
- Tab bar: the dark pill is one shared-layout element (`layout-id="tab-pill"`) that slides between tabs.
- Route change: crossfade + 12 px slide.
- Charts: the area chart is revealed by a clip rect scaling in from the left; donut segments sweep in
  (`pathLength`, the one non-transform animation, on a single SVG stroke).
- `prefers-reduced-motion`: `MotionConfig reducedMotion="user"` makes every transform instant; cards drop hover
  and press movement, numbers and the donut appear at their final value, the skeleton shimmer and the running
  pulse become opacity fades.

## States
- Loading: skeleton blocks with a shimmer (translateX), shaped like the content.
- Error: a raised card with the API message and a Retry button.
- Empty: an inset well with an icon, a title and the next step (never a blank area).
