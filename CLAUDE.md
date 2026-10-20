# Fallblatt (the Overhead board): notes for Claude

Called Fallblatt since 13 Oct 2026 (1.16). Overhead (planes flying over you) and Airport (take-offs and landings)
are its two styles and stay named so; so do the OVERHEAD status, the repository name, `OVERHEAD_*` page variables,
storage keys, the cookie and the `OverheadRelay` server header the Android app looks for.

A split-flap "planes overhead" board for Dave's home in Vienna, drawn on canvas: the plane overhead now, Spotted
today, a lifetime logbook and a radar. Published with GitHub Pages, served to the screens through a small relay
(Python) on Dave's homelab. Shown on a Samsung The Frame (Tizen), a Fire TV, an LG TV, and on phones as a web app and
an Android app. The README is the user guide; keep it current with every change someone would notice.

**Version-by-version details (what each version added, function names): `docs/history.md`; read it when touching that
area.** Where it and the code disagree, the code wins.

## Rules Dave set (keep to them)

- **Test first.** Visual and feature changes go to the test board first. Copy to the main board (`index.html`) only
  when Dave says so.
- **One test board.** `test/` is the test board, Flightradar24 features included (since 17 Oct 2026, 1.35.2;
  `test-api/index.html` only forwards to `/test/`). Without a key it falls back to the free sources by itself.
- **The phone app** (`app/`) is built from the test board's code, so new features reach the phone together with
  `test/`; rebuild it when shared code changes, and its light version (`light/`, `py tools/light/build.py`) with it.
- **Versions and patch notes.** One version for the boards and the app, kept in `CHANGELOG` in the board (the
  "versions and patch notes" block, which the app copies). With every change add an entry at the top: a new feature
  raises the second number (1.8 → 1.9), a small change adds a third (1.8.1), a bug fix a fourth (1.8.1.1). Notes are
  short and generic (one line each, what changed for someone using it): no names, places or internals such as relay
  versions (guests read them too). Settings → About shows them. Bump `RELAY_VERSION` with every relay change.
- **Every visible text goes through `T()`** (test board and app): `T("English text", {vars})`, `{name}` placeholders.
  Add a row to `test/i18n.js` (English, German, French, Spanish, Dutch) for every new text; a missing row shows English.
  Flap status words stay English inside (key for colours and drum order) and are translated when drawn. No German
  second lines under labels; a second label word is only kept for units. Patch notes and the connection log stay English.
- **Don't rename statuses or remarks** (OVERHEAD, INBOUND, SUPERJUMBO, ...) unless asked.
- **No secrets or personal data in the repository; it is public.** The Flightradar24 key lives only in
  `overhead.json` next to the relay: never print, read out or commit that file. When a key is needed, Dave types it
  into the terminal himself; don't ask him to paste it in chat. Dave's home location never goes into the repository
  either (the relay hands it to the board at page load). Test data uses central Vienna (48.2085, 16.3731). No
  addresses of the homelab or tunnel here: they are in Claude's memory.
- Removed on request, don't bring back: the page-flip sound on page turns, the board shake, the Delay field, the
  falling-page animation for views.
- The Android signing key (Actions secrets `ANDROID_KEYSTORE_B64`, `ANDROID_KEYSTORE_PASSWORD`; backup in
  `%USERPROFILE%\overhead-android-key`): never commit or print it, never replace it, or phones refuse updates.
- No Tailscale suggestions (tried and dropped 11 Oct 2026). OpenSky is ruled out (needs a written licence).

## Files

| Path | What it is |
|------|------------|
| `index.html` | Main board (PROD): a copy of `test/index.html` (only the title "Fallblatt" and one comment differ), made when Dave says "push to main" by `py tools/push_main.py` (also copies `i18n.js`, `sounds.js` to the root). |
| `test/index.html` | The test board, with the Flightradar24 features (`USE_API`, `apiLookup`, ...). |
| `test/i18n.js`, `test/sounds.js` | The translations (`I18N_ROWS`) and recorded sounds (`SOUND_DATA`), loaded by the board, app and light by version (`?v=`, stamped by `tools/assets.py`; 1.53.1). |
| `test-api/index.html` | Forwards to `/test/`. |
| `keys/index.html` | Remote key test for the TVs. |
| `app/` | Phone web app: `index.html` (generated, never hand-edit), `manifest.webmanifest`, icons, `sw.js`. |
| `light/` | The app without split flaps (`light/index.html`, generated). |
| `android/` | Android app: a WebView showing the relay's `/app/` (Kotlin, no AndroidX). Built by `.github/workflows/android.yml`. |
| `relay/serve.py` | The home relay. Python standard library only, 3.8+. `RELAY_VERSION` at the top (55 now). |
| `relay/install.sh`, `relay/overhead-relay.service` | Install or update the relay as a systemd service. |
| `tools/app/` | Builds `app/index.html`: `build.py`, `head.html` (markup, CSS), `main.js` (phone layout and glue). |
| `tools/light/` | `build.py`, `light.js` (code for main.js's `//@L:name` ... `//@L:end` regions), `light.css`. |
| `tools/sounds/` | `build_sounds.py` cuts recorded sounds (originals in git-ignored `sounds-src/`) into `test/sounds.js`. |
| `fonts/` | The typefaces (woff2, Latin and Latin Extended, named by content) and `fonts.css`, loaded by every board and app as `../fonts/fonts.css` (1.64); made by `tools/fonts.py`. |
| `tools/assets.py`, `tools/push_main.py` | Stamp the versions of `i18n.js`/`sounds.js` into the boards (the app build does it first); make the main board. |
| `tools/test/` | `flows.py` (the relay's access rules and saves, run by smoke.py), `run_test_relay.py` (fake flights + test relay), `fakesrc.py`, `fakehue.py` (a fake Hue Bridge, `--hue`), `smoke.py`, `shoot.py` (screenshots), `cockpit_list.py` (Settings controls per target). |
| `docs/history.md` | Version details; `docs/design-brief.md` the design brief. |

## How it works

**Board** (`test/index.html`, single file, copied to `index.html`): fixed 1920x1080 layout in board units, scaled to
the screen. Two canvases: `bg` (static: metal, wear, engraved labels; `drawStatic()`) and `fx` (the flaps). Flap
engine: `def()` fields of cells, `tile()` pre-renders flap faces, `setChars`/`setWord` queue the drum path, `frame()`
animates, `paintCell()` draws a flap mid-flip; drums are `DRUM_*` tables. Sounds: recordings in `SOUND_DATA` (`test/sounds.js`, fetched when sound is on; made by
`build_sounds.py`), played by `sample()`; flaps always clack synthesised. Top half: the plane overhead (`process()`
picks it: alerts, overhead, inbound, flying by) via `renderFeatured()`/`renderTimes()`. Lower half: rotating pages
(Recent flights, This aircraft, Today in numbers) turned by a giant falling flap; views (Spotted today, Logbook,
Radar, Settings) take over below the header (`switchView`). The rail buttons and Settings cockpit are DOM; Settings
are one `COCKPIT` for board, app and light (`for`/`flaps`/`phone`/`light` flags, `cockpitFor()`; 1.53.2; Account, Device and
About too as `view` plates, 1.56), checked with
`tools/test/cockpit_list.py`; smoke.py fails when a plate overflows at Fire TV size (`tools/test/plates.py`, 1.58). The radar's optional map (1.55) is OpenFreeMap vector tiles drawn by the board
itself (`radarMapBuild`, `mvtRead`; no text, no key); trophies are mostly tiers (`TROPHY_LADDERS`, relay `TROPHY_LADDER`,
progress from `trophyCounts`). Unlockable styles (1.59): `STYLES`, `stylesCard()` (◀ ▶ rows, 1.61), flap finishes in `tile()`;
colours and finishes only with the Classic board (`classicLook()`); badge icons `app/icon-*-<badge>.png` by `tools/app/make_icons.py`.
Realistic look is `S.real`/`REAL()`. Fire TV and LG (`WEAK_TV`) draw at 1080p, 30 fps, shorter runs (`LITE()`); the
Fire TV lays out at 960x540, so board CSS in the cockpit and views scales with `calc(Npx*var(--k))`.

**Airport style** (`S.mode === "airport"`, toggled by tapping Overhead/Airport in the title): pages aplists, apland,
apdep (`pageOrder()`), `apFeature` picks the plane; runways from `AIRPORTS` or the relay's `/airport`.

**Data**: positions from the relay (`/aircraft/...`); routes and aircraft from adsbdb (browser) and adsb.lol's routeset
(via the relay); Spotted today and the logbook from the relay (`/sightings`, `/logbook`); times from Vienna Airport
(`/times`); Flightradar24 via `/flightinfo`. Unknown details show "/" (`NA`/`orNA`). Features check
`window.OVERHEAD_RELAY_VERSION` before using newer relay endpoints. Shared blocks (cards, places, tips, achievements,
account, game/records) live in the board and are copied by the app build.

**Phone app**: `app/index.html` is generated by `py tools/app/build.py`, which copies the flap engine, tables,
network, tracking, logbook, radar, Settings code etc. out of `test/index.html` by marker strings and wraps them in
`tools/app/head.html` and `main.js`. If the build stops on a marker, the board's code moved: update the marker in
`build.py`. Settings under `od.app.settings`. On Android, the Overhead app (`android/`) is a full-screen WebView of
`<relay>/app/` (so web changes need no new APK); it finds the relay via `/health` on the phone's /24 (port 8080,
`Server: OverheadRelay`). Landscape on the phone shows the board-like Now layout (`heroLayout()`, `fitSideways()`).
GitHub Actions builds the APK on pushes touching `android/` and releases it from `main` (named after the newest
patch-notes entry; bump nothing by hand).

**Light version**: `py tools/light/build.py` builds `light/index.html` from the app's head.html/main.js and the board's
code, replacing main.js's `//@L:` regions with `light.js`'s. A new region in main.js needs one in light.js, or the
build stops. Settings under `od.light.settings`; Settings → Device switches (`od.ui`).

**Relay** (`relay/serve.py`): serves the published boards from GitHub Pages (refreshed at most once a minute; pushing to
`main` reaches screens within minutes; `--local-root <repo>` serves a checkout), positions (`SOURCES` tried in order:
adsb.lol, adsb.fi, airplanes.live, AvioADSB emergency only), sightings, logbook and game, Web Push, Flightradar24
(Explorer plan, pacing and per-profile daily limits; boards fall back to free sources when off), cards' data, geo search, a health watch that pushes the owner (relay 45), week/month review (`/review`, push; relay 46),
photos for the share picture (`/photo`) and the owner's Hue light pulse (`data/hue.json`, admin page; relay 47), QR sign-in, and since relay 48 board files named by version (`i18n.js?v=<sha256 start>`) with a year's cache when the copy matches. Credit links are in About.

**Profiles and access (relay 42+)**: there is no Home. Every visitor is a profile's device (cookie from a personal invite
link, an account sign-in, or a QR pairing) or a stranger (only the private page with the QR sign-in, `/health`, the app's
icons and manifest). A profile has its own spot (sightings, logbook, places, lists, settings under `data/profiles/<id>/`)
and may have an account (user, scrypt password, passkeys). `at_home()` only opens the admin paths (`/admin`, `/screens`,
`/status`, `/admin/*` POSTs), and since relay 43 `owner_ok()` only for the one profile named `HOME_OWNER` (David)
(relay 54: a device without a profile only on the relay's own computer, e.g. `curl` over SSH, or while no David
profile exists; other guests: 403). A guest not yet `located` gets the relay's place and airport in
`OVERHEAD_DEFAULTS`, never its lat/lon (Dave's home). `/admin` makes invites, accounts and limits. Screens name
their place on each position request. `host_ok()` refuses foreign Host names; loopback (the tunnel) always passes.

## The relay's home and how to update it

- Runs since 12 Oct 2026 on Dave's homelab: Debian LXC on Proxmox (`overhead-relay`, always on), systemd service
  `overhead-relay` in `/opt/overhead-relay` with `overhead.json` (settings, API key: never read it out) and `data/`.
  Port 8080. Address and login (root, key `~/.ssh/overhead_homelab` on Dave's PC) are in Claude's memory. The old copy
  in `%USERPROFILE%\overhead-relay` stays stopped: two relays on one network confuse the Android app's search.
- Kept to a standard: unattended-upgrades; SSH keys only (`/etc/ssh/sshd_config.d/10-overhead.conf`; `ssh.socket` is off,
  both on a reload leaves SSH dead); nftables lets in only 22 and 8080 from private addresses; journal capped at 100 MB;
  tight systemd sandbox. **Change SSH or the firewall only with a `systemd-run --on-active=180` rollback armed, cancelled
  once a fresh login works.**
- From outside through a Cloudflare Tunnel (`cloudflared`, token in `/etc/cloudflared/token`, root only; Dave enters it
  in the console, never through chat) to `http://localhost:8080`; Cloudflare Access is off, the invite links decide who
  gets in. `public_url` in `overhead.json` makes admin links full.
- **Update**: `py -m py_compile relay/serve.py`, scp `relay/serve.py`, `relay/overhead-relay.service`, `relay/install.sh`
  to `/root/overhead-install/` on the container and run `sh /root/overhead-install/install.sh` there (checks it compiles,
  replaces it, keeps settings and data, restarts). Bump `RELAY_VERSION`; gate board features needing it on
  `OVERHEAD_RELAY_VERSION`.
- Useful: `/status` (JSON), `/screens`; on the container `journalctl -u overhead-relay -f`.

## Testing a change

0. `py tools/test/smoke.py`: loads every page against the test relay and fails on a page error (GitHub runs it on pull requests).
1. `py tools/test/run_test_relay.py` (`--fr24` for Flightradar24 features, `--quiet` without special planes, `--hover`
   for a hovering helicopter, `--far` a landing 32 km out). It runs a copy of the relay against made-up flights and serves
   this checkout at `http://localhost:8096/` (`/test/`, `/app/`); Dave's real relay and data are untouched. Profiles:
   "Test" (cookie `overhead=test-device`; a browser gets it from `/test-signin`) "New guest" (`?as=new`, the welcome) and "David" (`overhead=owner-device`, the owner: the admin pages).
   Flights play out in the first minutes (restart for the Airport style). `--port N` (and `smoke.py --port N`; the
   fake source runs on N-1) when another checkout may be testing at the same time: use your own, e.g. 8296.
2. Look at it: a browser, or `py tools/test/shoot.py URL OUT steps...` (`PHONE=390x844` for the app, `SIZE=960x540 DPR=2`
   for the Fire TV, `COOKIE=` for another profile). Check the page errors it prints and look at the screenshots.
3. Syntax check: extract the inline `<script>` and `node --check` it if Node is installed.
4. For the TVs, the real screens are the test: open the relay's `/test/` on them.

Then commit (what changed and why), push, and tell Dave which boards changed and whether the relay needs an update.
