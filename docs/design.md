# Dashboard design system

Soft-skeuomorphic: warm paper surfaces with raised cards and pressed-in wells, inside a dark device bezel.
Tokens live in `web/src/styles/tokens.css` (Tailwind `@theme`, so each token is both a CSS variable and a
utility: `--color-ink` → `text-ink`, `bg-ink`). Components there: `.raised`, `.inset`, `.chip`, `.btn`,
`.round-btn`, `.skeleton`, `.grain`, `.num`.

## Frame and surfaces
- Page `#111113`, bezel `#1c1c1e` (radius 36, 12 px padding, faint inner rim highlight), app surface `#e8e3d9`
  (radius 24, recessed: 1 px light rim + soft inner shadow).
- Panels / cards `#fbf9f5` with a top-to-bottom light gradient (2-3% lighter at the top); wells `#efebe3`.
- Brand: a stickman head (white wobbly circle, dot eyes, brows, thick outline; SVG in `BrandMark.vue`) in a raised
  dark disc, plus the "Scribble Factory" wordmark in Fredoka beside the welcome text.
- Paper grain: SVG `feTurbulence` noise at 3% opacity on the surface and every raised card (`::before`).

## Depth
- **Raised** (`.raised`, radius 24): `inset 0 1px 0 #fff, -6 -6 14 white/.85, 10 14 28 rgb(96 78 52/.18),
  2 3 6 rgb(96 78 52/.10)`. Hover fades in a second layer with offsets and blur x1.4 (`::after` opacity only).
- **Inset** (`.inset`, radius 16): `inset 3 3 8 rgb(96 78 52/.16), inset -3 -3 8 white/.9`; search, chart wells,
  cast chips, stage strips, the donut track.
- **Chips** (`.chip`): pill, soft inset, tinted background + dark ink text.
- **Buttons**: `.btn-primary` dark pill, white text, raised; `.btn-secondary` raised light pill. `:active` swaps
  the shadow for an inset one (sinks). Round icon buttons (`.round-btn`) are inset when active (`aria-current`).

## Colour
| Token | Hex | Use |
|---|---|---|
| ink | `#1f1d1a` | text (15:1) |
| muted | `#5f5a51` | secondary **text** (5.3:1 on surface, 5.8:1 in wells, 6.5:1 on cards) |
| faint | `#8a857c` | icons and rules only (2.9:1 on surface: never text) |
| green / red / amber / blue | `#2fa36b` `#e35b4f` `#f2b84b` `#4f7cf7` | fills, dots, lines: done-up / failed-down / waiting / running |
| *-ink | `#1b6b45` `#a8352b` `#7f5a10` `#2c4fb8` `#5c584f` | text on the matching tinted chip (all ≥ 4.9:1) |

The brief's muted `#8a857c` and the accents fail WCAG AA as text on these surfaces, so text uses the darker
inks above and the original hues stay for non-text. Cast swatches use each cast member's top colour.

**KPI identities** (icon: raised round chip, gradient fill, white icon; badge: 12% tint + ink; number stays ink):

| Card | Gradient | Badge bg / ink |
|---|---|---|
| Series | indigo `#5b6cf0 → #4453d6` | `#e8e8f4` / `#3a47c4` (6.0:1) |
| Parts in progress | blue `#4f9cf7 → #2f7be0` | `#e6eef5` / `#1d5fb5` (5.3:1) |
| Waiting for you | amber `#f5b544 → #e0901a` | `#faf1e0` / `#875400` (5.7:1) |
| Posted this month | green `#3fbf7f → #23a063` | `#e4f2e7` / `#147045` (5.3:1) |

**Charts**: YouTube red-orange `#ff6b4a`, Instagram magenta-violet `#b44cf0` (red means "failed" only on status
chips). Area fill accent 35% → 0%, 2.5 px lines, glowing dots on hover. Donut series cycle through `PALETTE`
(`web/src/composables/ui.ts`): `#5b6cf0 #ff6b4a #3fbf7f #f5b544 #b44cf0 #2bb3c0`; rounded caps (each segment is
trimmed by one cap width so caps never overlap), a pressed-in track and a raised centre disc with the total.

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

## Scrolling
- Content gets bottom padding of tab bar height + 20 px offset + 24 px, so the floating tab bar never covers the end.
- Thin scrollbar inside the frame: 6 px, rounded, `#b3ab9d` thumb, transparent track; the thumb shows only while
  scrolling (`.scrolling` for 800 ms after a scroll event). Firefox falls back to `scrollbar-width: thin`.

## Part detail and live controls (6.2b)
- **Shared-element expand**: a part card records its rect on click; the part header animates from it with a FLIP
  (translate + scale only, spring), skipped under reduced motion.
- **Player**: raised round play button, inset scrub track (native range input) with a raised thumb, Fredoka time
  readout, source tabs (Test render / Preview / Final, only those that exist) with a sliding raised segment.
  Space plays, ←/→ seek 5 s. Media comes through `/api/media` (Range, so seeking works).
- **Switches** (approvals, cast): inset track, raised knob that springs across; on = green track. Approvals are
  one-way, so an "on" switch is locked; disabled switches say why (title + caption). Final asks for confirmation.
- **Light table**: an inset panel with a warm centre glow; sheets are raised white mounts that zoom (scale spring,
  dimmed backdrop). Thumbnail candidates are tilted polaroids; the picked one straightens, lifts and gets a green pin.
- **VU meter**: analogue dial −30…0 LUFS, green target band at −14, red-orange above −6; the needle springs in.
- **upload.md**: inset "paper" (grain + faint ruled lines), autosized with `field-sizing: content`, amber
  unsaved dot, Ctrl+S.
- **Danger zone**: pale red panel, red-ink text; destructive buttons always go through the confirm dialog.
- **Job drawer**: slides in from the right (transform). Progress fill is `scaleX` (transform only); unknown
  progress shimmers (translateX), a fade under reduced motion. Log: inset monospace, auto-scrolls, last 200 lines.
- **Top-bar reel**: spins while a job runs (opacity pulse under reduced motion), amber badge = queued jobs, grey dot
  while live updates are reconnecting.
- **Toasts**: raised cards sliding up bottom right (left of the drawer while it is open); errors stay 8 s and show
  the API's message verbatim.
- **Bottom fade**: the scroll area fades out under the tab bar (`mask-image`, decorative only).
- **Status colours**: the Posted-this-month badge follows the sign (green up, red-orange `#e8603c` tint with
  `#a8401f` ink down, neutral grey equal). Amber KPI icon gradient ends at `#c97a0a` (white icon 3.35:1).
- **Donut**: one series (or one at ≥ 99.5%) is a single seamless ring: butt caps, no gap.

## States
- Loading: skeleton blocks with a shimmer (translateX), shaped like the content.
- Error: a raised card with the API message and a Retry button.
- Empty: an inset well with an icon, a title and the next step (never a blank area).
