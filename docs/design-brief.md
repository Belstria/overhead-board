# Fallblatt: brief for a visual overhaul

You are asked to give Fallblatt a visual overhaul. Read this first, then `CLAUDE.md` (how everything fits together) and
`README.md` (what users see). Hand back your work as a branch or as changed files; it will be checked and merged from
there.

## What Fallblatt is

A split-flap "planes overhead" board: an airport departures board look, drawn on canvas, showing the plane flying
over right now, the day's sightings, a lifetime logbook and a radar. It runs in three places:

- **TV boards** (`index.html`, `test/`): a fixed 1920×1080 layout scaled to the screen, on a Samsung The
  Frame, a Fire TV and an LG TV (weak hardware), and on computers.
- **The phone web app** (`app/`): the same flap engine in a phone layout. Upright: tabs (Now, Today, Logbook, Radar,
  Settings). Sideways: the board only, full screen.
- **An Android app**: a WebView of the phone app, so it changes with it.

Two styles: **Overhead** (planes flying over) and **Airport** (take-offs and landings).

## What stays (the identity)

- The **split-flap look**: flaps that turn through a drum of characters, with sound. It is the product; refine it,
  don't replace it.
- **Amber on black**: `--amber:#f0b429`, `--housing:#0b0b0c`, `--ink:#f3f0e8` (in `tools/app/head.html`), the board's
  `THEMES` (classic, frankfurt, blue) in `test/index.html`.
- **The logo**: an amber rounded square with a dark plane (app icons in `app/`, the opening `#splash` and the welcome
  in `tools/app/head.html`). Don't use emoji for it; iPhones draw them in colour.
- The **status words and remarks** (OVERHEAD, INBOUND, SUPERJUMBO, …): their words and their order stay; colours
  and drawing may change (`REMARK_LOOK`).
- The **rarity tiers** and their colours and icons (`TIER_COL`, `drawTierIcon`): common, uncommon, rare, very rare,
  special.
- **Removed on request, don't bring back**: the page-flip sound on page turns, a board shake, a Delay field, a
  falling-page animation for views.

## Open for a redesign

These are suggestions; the owner chooses.

- The phone app around the flaps: the header, the tab bar (`.cap` buttons, `TAB_ICONS`), cards and lists in Today
  and Logbook, the Collection, the status line.
- The welcome for new guests (`#welcome`) and the opening animation (`#splash`).
- The Settings cockpit (`COCKPIT`, `.inst`, `body.real` CSS): plates of knobs, switches and wheels.
- The radar (`drawRadar`).
- The board's static frame (`drawStatic`: metal, wear, slots, engraved labels) and the flap faces (`tile`,
  `paintCell`), within the TV limits below.

## Where the code is

| File | What to change there |
|------|----------------------|
| `tools/app/head.html` | The phone app's markup and CSS (colour tokens on `:root`, the welcome, the splash, tabs, lists). |
| `tools/app/main.js` | The phone app's layout and glue (`heroLayout`, `fitSideways`, `buildTabs`, `welcome`, the logbook lists). |
| `test/index.html` | The whole board in one file (about 400 KB): flap engine (`tile`, `paintCell`, `frame`), `drawStatic`, `THEMES`, `REMARK_LOOK`, `drawRadar`, `COCKPIT`, patch notes (`CHANGELOG`); the translations (`I18N_ROWS`) and sounds are in `test/i18n.js` and `test/sounds.js` next to it. |
| `app/index.html` | **Generated** by `py tools/app/build.py` from the three files above. Never edit it by hand. |
| `index.html` | The main board. **Don't touch**: changes reach it only when the owner says so. |

The board file is too big to read whole; search it for the function names above. The app's code runs inside one
closure, so its variables aren't reachable from the browser console.

## Rules

1. **Test boards first.** Change `test/` (and the app sources), never `index.html`.
2. **Every visible text goes through `T("English text", {vars})`**, with a row in `I18N_ROWS` (`test/i18n.js`) for English, German,
   French, Spanish and Dutch. New text without a row shows English.
3. **TVs are weak.** Fire TV and LG run at 1080p and 30 fps (`WEAK_TV`, `LITE()`). Anything heavy (blur, big
   shadows, per-frame gradients, filters on canvas) needs a light path there. Flap faces are pre-rendered and cached
   by `tile()`; keep per-frame drawing cheap.
4. **Phones:** upright and sideways (CSS `(orientation: landscape) and (max-height: 600px)`), from a small Android
   phone to an iPhone Pro Max, notch and home bar included (`env(safe-area-inset-*)`, `--cut-l`, `--cut-r`). No
   horizontal scrolling.
5. **Reduced motion:** honour `prefers-reduced-motion` for new animations.
6. **Fonts and libraries:** web fonts from Google Fonts only; no frameworks or build steps (plain HTML, CSS, JS).
7. **Nothing personal or secret** in the code: no addresses, keys or locations. The repository is public.
8. **A patch note** for a visible change: a line at the top of `CHANGELOG` in `test/index.html`, short and generic. Visual changes raise the second number of the version (1.25 → 1.26).

## Trying it

```
py tools/test/run_test_relay.py
```

This serves the checkout with made-up flights at `http://localhost:8096/` (`/test/`, `/app/`). After
changing the app sources, run `py tools/app/build.py`. `py tools/test/shoot.py URL OUT wait:4000 shot:now` takes
screenshots (`PHONE=390x844` for the app; its docstring lists the steps). Needs Playwright: `py -m pip install playwright`
and `py -m playwright install chromium`.

## What to hand back

- The changed files, or a branch, with a short list of what changed and why.
- Screenshots of the phone app upright (390×844), sideways (about 932×430) and the board (1920×1080), before and
  after.
- Anything you couldn't check (for example, the TVs).
