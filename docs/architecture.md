# Fallblatt: architecture

Moved out of `CLAUDE.md` (which keeps the rules, testing and pointers) so that every session doesn't have to read it
with every step: the files, how the pieces fit together, and the relay's home. Read the part for what you are
changing. Where this file and the code disagree, the code wins.

## Files

| Path | What it is |
|------|------------|
| `index.html` | Main board (PROD): a copy of `test/index.html` (only the title "Fallblatt" and one comment differ), made when Dave says "push to main" by `py tools/push_main.py` (also copies `i18n.js`, `sounds.js` to the root). |
| `test/index.html` | The test board, with the Flightradar24 features (`USE_API`, `apiLookup`, ...). |
| `test/i18n.js`, `test/sounds.js` | The translations (`I18N_ROWS`) and recorded sounds (`SOUND_DATA`), loaded by the board, app and light by version (`?v=`, stamped by `tools/assets.py`; 1.53.1). |
| `test-api/index.html` | Forwards to `/test/`. |
| `keys/index.html` | Remote key test for the TVs. |
| `app/` | Phone web app: `index.html` (generated, never hand-edit), `manifest.webmanifest`, icons, `sw.js`. |
| `light/`, `glass/` | Parked since 1.71.3: each `index.html` only forwards to `/app/`. Not built, checked or linked. |
| `android/` | Android app: a WebView showing the relay's `/app/` (Kotlin, no AndroidX). Built by `.github/workflows/android.yml`. |
| `relay/serve.py` | The home relay. Python standard library only, 3.8+. `RELAY_VERSION` at the top (74 now). |
| `relay/install.sh`, `relay/overhead-relay.service` | Install or update the relay as a systemd service. |
| `tools/app/` | Builds `app/index.html`: `build.py`, `head.html` (markup, CSS), `main.js` (phone layout and glue). `WMM.COF`: NOAA's World Magnetic Model (public domain), packed into main.js's `WMM_C` for Sky view's true north. |
| `tools/light/`, `tools/glass/` | Parked source of the light version (`light.js` for main.js's `//@L:name` ... `//@L:end` regions, `light.css`) and Glass (`glass.js`, `glass.css`). Kept for later; running their `build.py` overwrites the forwarders. |
| `tools/sounds/` | `build_sounds.py` cuts recorded sounds (originals in git-ignored `sounds-src/`) into `test/sounds.js`. |
| `fonts/` | The typefaces (woff2, Latin and Latin Extended, named by content) and `fonts.css`, loaded by every board and app as `../fonts/fonts.css` (1.64); made by `tools/fonts.py`. |
| `tools/assets.py`, `tools/push_main.py` | Stamp the versions of `i18n.js`/`sounds.js` into the boards (the app build does it first); make the main board. |
| `tools/model_pages.py` | Writes `MODEL_PAGES` (type code → Wikipedia page, for model pictures) into `test/index.html` from Wikipedia's list of type designators plus its own fixes and additions, all checked online; run by hand, then rebuild the app (1.93.1.1). |
| `tools/test/` | `flows.py` (the relay's access rules and saves, run by smoke.py), `run_test_relay.py` (fake flights + test relay), `fakesrc.py`, `fakehue.py` (a fake Hue Bridge, `--hue`), `smoke.py`, `shoot.py` (screenshots), `cockpit_list.py` (Settings controls per target), `sky_jitter.js` (Sky view's label jitter on a made-up sensor stream, 1.90), `model_pics.js` (the model pictures' lookup over a list of types, against Wikipedia, 1.93.1.1). |
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
Realistic look is `S.real`/`REAL()`. The game (1.72, relay 59): only "live" sightings within `GAME_KM` (15 km) score, scans only within `SCAN_KM` (10 km, relay 82), kept in
the logbook's own `game3` part (`game_note`, `game_lockon` (the scan), `game_awards`, `level_of`, `league_json`); the app's score
strip, Game page, pop-ups and Sky view scan are `gStrip*`/`renderGame`/`gAwards`/`gPop`/`gLockOn` in main.js, the scan tickets `gTixSync` (from `/game/me`'s `scan` list, `game_scannable`, 1.98); the rules come from the relay (`game_rules`, 1.96); the
board's League page is `renderLeague`. Styles unlock by level (`{lvl: n}`), First Class only for the champion. Fire TV and LG (`WEAK_TV`) draw at 1080p, 30 fps, shorter runs (`LITE()`); the
Fire TV lays out at 960x540, so board CSS in the cockpit and views scales with `calc(Npx*var(--k))`.

**Airport style** (`S.mode === "airport"`, toggled by tapping Overhead/Airport in the title): pages aplists, apland,
apdep (`pageOrder()`), `apFeature` picks the plane; runways from `AIRPORTS` or the relay's `/airport`.

**Data**: positions from the relay (`/aircraft/...`); routes and aircraft from adsbdb (browser) and adsb.lol's routeset
(via the relay); Spotted today and the logbook from the relay (`/sightings`, `/logbook`); times from Vienna Airport
(`/times`); Flightradar24 via `/flightinfo`; photos in the order Planespotters.net (`/planephoto`, relay 73; never kept
or passed on, so never in the share picture), adsbdb's, the model's from Wikipedia (`planePic`, 1.93; found by `modelPage`: the code's page in `MODEL_PAGES`, then the names, never another model's, 1.93.1.1). The info cards (1.94, `infoCard`: Sky view's card
style, More info, fun facts) get Wikipedia's and Wikidata's facts cleaned by the relay (`/facts`, relay 74: a model by
its page, an airline by ICAO code, an airport by IATA code; relay 78: kept in `data/facts.db`, SQLite read per card,
every airline still flying, airport and model refreshed in batches once a month at night, `facts_refresh`) and what you spotted
from `/logbook/spotted` and the logbook search. Unknown details show "/" (`NA`/`orNA`). Features check
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

**Light version and Glass: parked (1.71.3).** Not built, not in CI, smoke or lint, no Device tiles; `/light/` and
`/glass/` forward to `/app/`. Don't keep `light.js`/`glass.js` in step with main.js; leave main.js's `//@L:` markers
in place for when Dave revives them (then `light.js` needs bringing up to date: `py tools/light/build.py` stops on a
missing region).

**Relay** (`relay/serve.py`): serves the published boards from GitHub Pages (refreshed at most once a minute; pushing to
`main` reaches screens within minutes; `--local-root <repo>` serves a checkout), positions (`SOURCES` tried in order:
adsb.fi, adsb.lol (in reserve for its 500 a day, relay 68), airplanes.live, AvioADSB emergency only), sightings, logbook and game, Web Push, Flightradar24
(Explorer plan, pacing and per-profile daily limits; boards fall back to free sources when off; relay 66: away from
home it fills in the low planes the free sources miss for the owner's screens, `fill_*`; relay 67: one record per
profile, not for pages in the background), cards' data, geo search, a health watch that pushes the owner (relay 45), week/month review (`/review`, push; relay 46),
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
  tight systemd sandbox.
- From outside through a Cloudflare Tunnel (`cloudflared`, token in `/etc/cloudflared/token`, root only; Dave enters it
  in the console, never through chat) to `http://localhost:8080`; Cloudflare Access is off, the invite links decide who
  gets in. `public_url` in `overhead.json` makes admin links full.
- **Update**: `py -m py_compile relay/serve.py`, scp `relay/serve.py`, `relay/overhead-relay.service`, `relay/install.sh`
  to `/root/overhead-install/` on the container and run `sh /root/overhead-install/install.sh` there (checks it compiles,
  replaces it, keeps settings and data, restarts). Bump `RELAY_VERSION`; gate board features needing it on
  `OVERHEAD_RELAY_VERSION`.
- Useful: `/status` (JSON), `/screens`; on the container `journalctl -u overhead-relay -f`.
