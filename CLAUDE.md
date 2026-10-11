# Overhead board: notes for Claude

A split-flap "planes overhead" board for Dave's home in Vienna: an airport departures board look, drawn on canvas,
showing the plane flying over right now plus Spotted today, a lifetime logbook and a radar. Published with GitHub
Pages and served to the screens through a small relay on Dave's PC. Shown on a Samsung The Frame (2021, Tizen), a
Fire TV and an LG TV, and on phones as a web app. The README is the user guide; keep it current with every change
someone would notice.

## Rules Dave set (keep to them)

- **Test first.** Visual and feature changes go to the test boards first. Copy to the main board (`index.html`) only
  when Dave says so.
- **Two test boards.** Changes that don't need the paid API go to both `test/` and `test-api/` ("both TEST").
  Features that need Flightradar24 only ever go into `test-api/`, so `test/` always works without the API.
- **The phone app** (`app/`) is built from the main board's code (see below); rebuild it when shared code changes.
- **Don't rename statuses or remarks** (OVERHEAD, INBOUND, SUPERJUMBO, ...) unless asked.
- **No secrets or personal data in the repository; it is public.** The Flightradar24 key lives only in
  `overhead.json` next to the relay on Dave's PC (`py serve.py --fr24-key ... --save`). Never print, read out or
  commit that file. When a key is needed, Dave types it into the terminal himself; don't ask him to paste it in chat.
  Dave's home location never goes into the repository either: the relay hands it to the board at page load.
  Test data uses central Vienna (48.2085, 16.3731).
- Removed on request earlier, don't bring back: the page-flip sound on page turns, the board shake, the Delay field,
  the falling-page animation for views.

## Files

| Path | What it is |
|------|------------|
| `index.html` | Main board (PROD). Since 11 Oct 2026 a copy of `test-api/index.html` (only the title and one comment differ). |
| `test/index.html` | Test board, free data sources only. |
| `test-api/index.html` | Test board plus Flightradar24 features (`USE_API`, `apiLookup`, FR24 remarks, ...). |
| `app/` | Phone web app: `index.html` (generated), `manifest.webmanifest`, icons. |
| `relay/serve.py` | The home relay. Python standard library only, 3.8+. `RELAY_VERSION` at the top. |
| `tools/app/` | Builds `app/index.html`: `build.py`, `head.html` (markup and CSS), `main.js` (phone layout and glue). |
| `tools/test/` | `run_test_relay.py` (fake flights + test relay), `fakesrc.py` (the fake data), `shoot.py` (screenshots). |

The three boards are full copies of one single-file app. To see the API delta: `git diff --no-index test/index.html
test-api/index.html`. To carry a non-API change to both test boards, make it in `test/` and apply the same patch to
`test-api/` (a `diff -u` of the change applies cleanly almost always; fix the odd reject by hand).

## How the board works (index.html and the test boards)

- Fixed 1920x1080 layout in board units, scaled to the screen. Two canvases: `bg` (static: metal, wear, slots,
  engraved labels; `drawStatic()`) and `fx` (the flaps).
- Flap engine: `def()` fields with cells; `tile()` pre-renders each flap face (cached, byte-budgeted);
  `setChars(id, text, delay)` / `setWord(id, word, delay)` queue the drum path (`retarget`), `frame()` animates and
  `paintCell()` draws a flap mid-flip. Drums: `DRUM_ALPHA`, `DRUM_DIGIT`, `DRUM_ALT`, `DRUM_POS`, `REMARKS`.
- Top half: the plane overhead (`process()` picks it: alerts first, then overhead, inbound, flying by; airtime limit
  for hovering planes) rendered by `renderFeatured()` and `renderTimes()`.
- Lower half: rotating pages (Recent flights, This aircraft, Today in numbers; `ROTATION`), turned by one giant
  falling flap (`startBigFlap`). Views (Spotted today, Logbook, Radar, Settings) take over below the header at once
  (`switchView`). The rail of lamp buttons is DOM (`.cap`), as is the Settings cockpit (`COCKPIT`, `cockpitOpen`).
- Drawing quality: Fire TV and LG TVs (`WEAK_TV`) draw at 1080p, 30 fps, shorter flap runs (`LITE()`).
- Data: positions from the relay (`/aircraft/...`), routes and aircraft from adsbdb (browser) and adsb.lol's
  routeset (through the relay), Spotted today and the logbook from the relay (`/sightings`, `/logbook`), times from
  Vienna Airport via the relay (`/times`), Flightradar24 via the relay (`/flightinfo`). Features check
  `window.OVERHEAD_RELAY_VERSION` before using newer relay endpoints.

## The phone app

`app/index.html` is generated: `py tools/app/build.py` copies the flap engine, reference tables, network, tracking,
times, specials, logbook and radar code out of `index.html` by marker strings and wraps them in the phone layout
from `tools/app/head.html` and `tools/app/main.js`. Never hand-edit `app/index.html`. Change `main.js`/`head.html`
(or the board) and rebuild. If the build stops on a marker, the board's code moved: update the marker in `build.py`.
The app keeps its settings under its own key (`od.app.settings`) and needs the relay (relay 13+ serves its icons).

## The relay

- Dave runs it from `%USERPROFILE%\overhead-relay` (the folder the README sets up), not from this repository: that
  folder also holds `overhead.json` (settings and the API key) and `data/` (sightings per day, logbook,
  Flightradar24 cache). Started with `py serve.py` in a terminal; port 8080.
- To update it: copy `relay/serve.py` over the one in that folder (after `py -m py_compile relay/serve.py`), then
  restart it: Ctrl+C in its window, `py serve.py`. Bump `RELAY_VERSION` with every relay change and gate board
  features that need the new version on `OVERHEAD_RELAY_VERSION`.
- Useful: `http://localhost:8080/status` (JSON), `/screens` (screens using it), Enter in its window lists screens.
- Flightradar24 (Explorer plan, Dave may stop after the first month): at most 10 lookups a minute, 27,000 credits a
  month, spread as a daily share (`fr24_paced`). Boards fall back to the free sources when the key is off or refused.
- It serves the published boards from GitHub Pages (refreshed at most once a minute), so pushing to `main` reaches
  the screens a minute or two later, when they reload. `--local-root <repo>` serves a local checkout instead.

## Testing a change

1. `py tools/test/run_test_relay.py` (add `--fr24` for the API boards, `--quiet` without special planes,
   `--hover` for a hovering helicopter). It runs a copy of the relay in a temporary folder against made-up flights
   and serves this checkout at `http://localhost:8096/` (`/test/`, `/test-api/`, `/app/`). Dave's real relay and
   data are untouched.
2. Look at it: in a browser, or `py tools/test/shoot.py URL OUT steps...` for screenshots (set `PHONE=390x844` for
   the app). Check the page errors it prints and look at the screenshots, not just the exit code.
3. Syntax check of the inline script: extract the `<script>` and run `node --check` on it if Node is installed.
4. For anything about the TVs, the real screens are the test: open `http://<pc>:8080/test/` on them.

Then commit (what changed and why), push to `main`, and tell Dave which boards changed and whether the relay needs
a restart.

## Ideas Dave hasn't picked yet (Oct 2026)

Screens update themselves when a new version is published; wake The Frame and reopen the board when it drops off,
Art Mode at night (Samsung's local TV API); start the relay with Windows, later Docker on the homelab; a spotter's
collection page and weekly bingo of rare planes; rarity marks ("first time ever", "seen 4 times"); worth going to
the window (cloud base vs altitude, sunset, which window); runways in use at Vienna; a day in review at night; a Hue
light pulse for special planes (local Hue Bridge API), phone push via ntfy; a Vestaboard-style 6x22 view; a report of
what Flightradar24 added, to decide on renewing; merging the two test boards into one file with the API switched on
by address.
