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
- **The phone app** (`app/`) is built from the test-api board's code (since 11 Oct 2026, so new features reach the
  phone together with test-api; see below); rebuild it when shared code changes.
- **Versions and patch notes.** One version for the boards and the app, kept in `CHANGELOG` in the board (the
  "versions and patch notes" block, which the app copies). With every change add an entry at the top: a new feature
  raises the second number (1.8 → 1.9), a small change adds a third (1.8.1), a bug fix a fourth (1.8.1.1). Notes are
  short, for Dave, in plain words. Settings → About shows them; the relay (17+) adds the publish time
  (`window.OVERHEAD_PAGE_DATE`).
- **Every visible text goes through `T()`** (test boards and app): `T("English text", {vars})`, with `{name}`
  placeholders. Add a row to `I18N_ROWS` (English, German, French, Spanish, Dutch) for every new text; a missing row
  shows English. Flap status words stay English inside (the key for colours and drum order) and are translated when
  drawn. No more German second lines under labels (removed in 1.12); a second label word is only kept for units.
  Patch notes and the connection log stay English.
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
| `index.html` | Main board (PROD). On 11 Oct 2026 a copy of `test-api/index.html`; test-api has moved on since (the new Settings cockpit). |
| `test/index.html` | Test board, free data sources only. |
| `test-api/index.html` | Test board plus Flightradar24 features (`USE_API`, `apiLookup`, FR24 remarks, ...). |
| `app/` | Phone web app: `index.html` (generated), `manifest.webmanifest`, icons. |
| `android/` | Android app: a WebView showing the relay's `/app/` (Kotlin, no AndroidX). Built by `.github/workflows/android.yml`. |
| `relay/serve.py` | The home relay. Python standard library only, 3.8+. `RELAY_VERSION` at the top. |
| `tools/app/` | Builds `app/index.html`: `build.py`, `head.html` (markup and CSS), `main.js` (phone layout and glue). |
| `tools/test/` | `run_test_relay.py` (fake flights + test relay), `fakesrc.py` (the fake data), `shoot.py` (screenshots). |

The three boards are full copies of one single-file app. `test/` is test-api without the Flightradar24 part: to see
that delta, `git diff --no-index test-api/index.html test/index.html`. Work in test-api, then rebuild `test/` by applying
that delta (saved as a patch before the change) to the new test-api, and check the result differs from test-api by
exactly the delta again. Done this way on 12 Oct 2026, when `test/` got everything from 1.7 and 1.8. A hunk that touches the
`REMARKS`/`REMARK_LOOK` tables needs fixing by hand: `test/` has no DIVERTED, CARGO, BIZJET, PRIVATE (API remarks).

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
times, specials, logbook, radar and Settings control code out of `test-api/index.html` by marker strings and wraps them in the phone layout
from `tools/app/head.html` and `tools/app/main.js`. Never hand-edit `app/index.html`. Change `main.js`/`head.html`
(or the board) and rebuild. If the build stops on a marker, the board's code moved: update the marker in `build.py`.
The app keeps its settings under its own key (`od.app.settings`) and needs the relay (relay 13+ serves its icons).

Airport style (`S.mode === "airport"`, switched by tapping Overhead/Airport in the title; the "airport mode" block,
copied by the app): `pageOrder()` = aplists (take-offs and landings side by side), apland, apdep, under the plane on
top, which `apFeature` picks (`apFocus`); apland/apdep reuse the This aircraft page (`isAc(page)`). The airport
statuses (`AP_ICON`) carry a plane pictogram in front of the word, in the flap tile and the app's chips (Dave's choice
over a header sign, which was tried in 1.12.1).
Dave chose this pages layout on 12 Oct 2026; the screens layout (full-screen lists) was removed.

Settings cockpit (shared by test-api and the app): `COCKPIT` plates are CSS grids of `cols` cells, items take `span`
cells or `wide`; `itemHtml()` puts each control in a `.inst` cell with its name above it. Control sounds are
`ctlSound.rotary(steps)/toggle(on)/wheel()/press()` (they play when `S.sound || S.chimes`). "Use current location"
(`wireLocate`, `hereNow`, `nearestAirport`) uses `navigator.geolocation` (secure contexts only, so not on the TVs) or the
Android app's `OverheadAndroid.locate()`, and the relay's `/airports/near` (relay 16+) for the home airport.

On Android it is installed as the Overhead app (`android/`), because Chrome installs web apps only from https and the
relay is plain http (Tailscale was tried and dropped on 11 Oct 2026; don't suggest it again). The app is a full-screen
WebView of `<relay>/app/`, so web app changes need no new APK. It finds the relay by asking `/health` on every
address of the phone's /24 (port 8080, `Server: OverheadRelay`), or takes a typed address; Settings → About →
Change relay calls `window.OverheadAndroid.changeRelay()` (`ANDROID` in `main.js`). Its user agent ends in
`OverheadAndroid/<version>`. On its side the app page itself takes its landscape layout (CSS for
`(orientation: landscape) and (max-height: 600px)`: each tab has a `.lcol` and `.rcol`, the tabs become a column on the
right; `heroLayout()` puts the flaps in four board-like rows); the Android app goes immersive and keeps the screen on
while charging. (1.9–1.12.2 showed the board instead; Dave preferred a layout of the app's own.) GitHub Actions builds it on every push touching `android/` (no Gradle wrapper; Gradle
8.10.2 from the workflow) and, on `main`, publishes a release `android-build-<run>` named "Android app <version> (build <run>)" with `overhead.apk`
(`releases/latest/download/overhead.apk`). The signing key is in the Actions secrets `ANDROID_KEYSTORE_B64` and
`ANDROID_KEYSTORE_PASSWORD`, with a backup in `%USERPROFILE%\overhead-android-key` on Dave's PC: never commit or print
it, and never replace it, or phones refuse the update. Bump nothing by hand: the APK is named after the newest patch-notes entry plus the build number.

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
- Behind a proxy on the same computer, the relay (14+) takes a screen's address from `X-Forwarded-For`.
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
