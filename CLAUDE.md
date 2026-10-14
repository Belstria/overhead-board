# Fallblatt (the Overhead board): notes for Claude

The app is called Fallblatt since 13 Oct 2026 (1.16). Overhead (planes flying over you) and Airport
(take-offs and landings) are the names of its two styles and stay; so do the OVERHEAD status, the repository name,
`OVERHEAD_*` page variables, storage keys, the cookie and the `OverheadRelay` server header the Android app looks for.

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
  short and generic (one line each, what changed for someone using it): no names, places or internals such as relay
  versions (guests read them too; the history was rewritten that way on 14 Oct 2026). Settings → About shows them; the relay (17+) adds the publish time
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
| `index.html` | Main board (PROD). Since 12 Oct 2026 (1.13) a copy of `test-api/index.html` (only the title and one comment differ). |
| `test/index.html` | Test board, free data sources only. |
| `test-api/index.html` | Test board plus Flightradar24 features (`USE_API`, `apiLookup`, FR24 remarks, ...). |
| `app/` | Phone web app: `index.html` (generated), `manifest.webmanifest`, icons. |
| `android/` | Android app: a WebView showing the relay's `/app/` (Kotlin, no AndroidX). Built by `.github/workflows/android.yml`. |
| `relay/serve.py` | The home relay. Python standard library only, 3.8+. `RELAY_VERSION` at the top. |
| `relay/install.sh`, `relay/overhead-relay.service` | Install or update the relay as a systemd service on Linux (the homelab). |
| `tools/app/` | Builds `app/index.html`: `build.py`, `head.html` (markup and CSS), `main.js` (phone layout and glue). |
| `tools/sounds/` | `build_sounds.py` cuts the recorded sounds (originals in git-ignored `sounds-src/`) into the boards' `@sounds-begin` block; credits and licenses in its README. |
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
  `setChars(id, text, delay)` / `setWord(id, word, delay)` queue the drum path (`retarget`; with Quick flaps, `S.quick`, each flip gets `c.qdur` so the run ends within `QUICK_MS`, and `frame()` chains and skips flips), `frame()` animates and
  `paintCell()` draws a flap mid-flip. Sounds (1.17): recordings in `SOUND_DATA` (embedded, made by
  `tools/sounds/build_sounds.py`), decoded by `loadSounds()`, played by `sample()` from `clack()` and `ctlSound`; with
  `S.soundSet === "classic"` or before decoding, the old synthesised sounds play. The flaps always clack synthesised
  (1.19.1, Dave's choice; the flap recording was dropped). The board's rail buttons carry the app's tab icons (`RAIL_ICONS`). Drums: `DRUM_ALPHA`, `DRUM_DIGIT`, `DRUM_ALT`, `DRUM_POS`, `REMARKS`.
- Top half: the plane overhead (`process()` picks it: alerts first, then overhead, inbound, flying by; airtime limit
  for hovering planes) rendered by `renderFeatured()` and `renderTimes()`.
- Lower half: rotating pages (Recent flights, This aircraft, Today in numbers; `ROTATION`), turned by one giant
  falling flap (`startBigFlap`). Views (Spotted today, Logbook, Radar, Settings) take over below the header at once
  (`switchView`). The rail of lamp buttons is DOM (`.cap`), as is the Settings cockpit (`COCKPIT`, `cockpitOpen`).
- Look (1.18): the footer and the app's status line stay quiet while live (`updateFooter`, `body[data-health]` in
  the app), the radar's labels go through `radarLabels()` (no overlaps, inside the scope), the app's Save bar only
  shows when `#t-settings.dirty`, the app's tabs carry line icons (`TAB_ICONS`), and altitudes below zero show as 0.
- Realistic look (1.19, `S.real`, `REAL()`): extra layers in `tile()` (two-card print, grain, lighting) and
  `paintCell()` (light and edge on a turning flap), `#glass` over the stage and `body.real` CSS for the cockpit. Settings
  show a description per control (`HINTS`, hover; press and hold on touch).
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
The game (1.21, relay 24): the relay scores each sighting when it is recorded (`tier_of`, `score`: `e.tier`,
`book.points/days/tiers/rareDays`; `game_json` in `/logbook` with the `SETS`); the board's `tierOf()` gives the plane on
top its tier (the relay's for planes on today's list, else from the logbook's type counts) on the `tier` flap
(`TIER_COL`, `drawTierIcon`), and the `collection` view (from Logbook's view tools) shows `game`.
Runways (1.20, relay 23): `AP.rwys` from `AIRPORTS[code].runways` (Vienna) or the relay's `/airport` (OurAirports
runways.csv, cached per airport); `rwyTrack()` matches each take-off and landing to the runway it is lined up with,
`rwyInUse()`/`rwyLine()` give the ones used in the last 15 minutes (shown next to the lists' title and lit on the radar),
and the Take-off and Landing pages paint `paintRunwayScreen()` on the photo screen (the photo as an inset).

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
`(orientation: landscape) and (max-height: 600px)`): only Now, full screen, no tab buttons (`sideways()` switches to
Now and back; `showTab` refuses other tabs on its side), the status line only as a pop-up when something is wrong
(`#sideAlert`). Now is the board (1.13.2/1.13.3, Dave's choice): `heroLayout()` puts the flaps in three rows across the
width, and under them one page at a time, `nowPage` "lists" or "ac", picked by lamp buttons in the title strip
(`buildNowPages`; in the Airport style `lists`/`dep`/`land`, the board's pages, `appApPage()` telling `apFeature` which plane, `paintRwy()` the runway screen; upright a `#apPick` switch), turning every 20 s, drawn on their own flap panels (`RECENTP`, `APP`, `ACP`, switched by
`nowPanels()`) in place of the text lists; `fitSideways()` sizes it all to fill the screen (`--fitW`, `--lowH`), with fewer list rows (`setNowRows`, 6 down to 4) on a screen short for its width. The
Android app goes immersive, draws under the camera cutout and tells the page how far it reaches (`--cut-l`, `--cut-r`),
and keeps the screen on while it is open (`FLAG_KEEP_SCREEN_ON`, since 1.13.3.1; before only on its side and charging). (1.9–1.12.2 showed the board instead; Dave preferred a layout of the app's own.) GitHub Actions builds it on every push touching `android/` (no Gradle wrapper; Gradle
8.10.2 from the workflow) and, on `main`, publishes a release `android-build-<run>` named "Android app <version> (build <run>)" with `overhead.apk`
(`releases/latest/download/overhead.apk`). The signing key is in the Actions secrets `ANDROID_KEYSTORE_B64` and
`ANDROID_KEYSTORE_PASSWORD`, with a backup in `%USERPROFILE%\overhead-android-key` on Dave's PC: never commit or print
it, and never replace it, or phones refuse the update. Bump nothing by hand: the APK is named after the newest patch-notes entry plus the build number.

## The relay

- Since 12 Oct 2026 it runs on Dave's homelab: a Debian LXC container on Proxmox (`overhead-relay`, always on), as the
  systemd service `overhead-relay` (`relay/overhead-relay.service`) in `/opt/overhead-relay`, which also holds
  `overhead.json` (settings and the API key) and `data/` (sightings per day, logbook, Flightradar24 cache). Port 8080.
  The container's address and how to reach it are in Claude's memory for this project, not here (the repository is
  public). Claude logs in as root with the key `~/.ssh/overhead_homelab` on Dave's PC. The old copy in
  `%USERPROFILE%\overhead-relay` on the PC stays stopped: two relays on one network confuse the Android app's search.
- The container is kept to a standard (13 Oct 2026): security updates install themselves (unattended-upgrades), SSH
  takes keys only (`/etc/ssh/sshd_config.d/10-overhead.conf`; `ssh.socket` is off, as with both on a reload leaves SSH
  dead), nftables lets in only 22 and 8080 from private addresses (`/etc/nftables.conf`), the journal is capped at
  100 MB, and the service runs in a tight systemd sandbox (`systemd-analyze security overhead-relay`: 1.3). Change SSH
  or the firewall only with a `systemd-run --on-active=180` rollback armed, cancelled once a fresh login works.
- From outside it is reached through a Cloudflare Tunnel (since 13 Oct 2026; the address is in Claude's memory, not
  here): `cloudflared` from Cloudflare's apt repository (also updated by unattended-upgrades), the tunnel's token in
  `/etc/cloudflared/token` (root only; Dave pasted it in the console, it never passes through chat), and a sandbox
  drop-in `cloudflared.service.d/10-sandbox.conf` (DynamicUser, the token handed over with LoadCredential). The tunnel
  sends the hostname to `http://localhost:8080`; Cloudflare Access is off, as the relay's invite links decide who gets
  in. The relay's `public_url` in `overhead.json` makes the admin page hand out full links.
- To update it: `py -m py_compile relay/serve.py`, copy `relay/serve.py`, `relay/overhead-relay.service` and
  `relay/install.sh` to the container (scp, to `/root/overhead-install/`) and run `sh /root/overhead-install/install.sh`
  there: it checks the file compiles, replaces it, keeps the settings and data, and restarts the service. (After the
  change is on `main`, `curl -fsSL .../relay/install.sh | sh` on the container does the same from GitHub.) Bump
  `RELAY_VERSION` with every relay change and gate board features that need the new version on
  `OVERHEAD_RELAY_VERSION`.
- Friends and family (relay 19, app 1.15): every visitor is home (a direct connection from a private address, no
  `Cf-Connecting-IP`), a guest (a device cookie from a personal invite link, `/join/<code>`; profiles, invite and
  cookie hashes in `data/profiles.json`) or a stranger (only the "private" page, `/health`, the app's icons and
  manifest). Each profile has a `Spot` (sightings and logbook; home in `data/`, guests in `data/profiles/<id>/`), and
  a screen's positions are recorded into its own spot (`Spot.take`) if they cover the spot's place. Guests get
  `OVERHEAD_GUEST` (id, name, settings) instead of the home location, their settings back via `/me`
  (merged, so the app and the board don't wipe each other's), the boards too (1.16; the welcome's "Phone app / Full
  board" choice; a board sends a guest without `located` to the app's welcome), per-guest storage keys
  (`od.app.settings.g.<id>`, `od.settings.g.<id>`), `/signout` (About), no `/screens`, `/status` or `/admin`, rate limits (`allow`), and Flightradar24 only if turned on for them
  (`GUEST_FR24_DAY`). `/admin` (home only, same-origin POSTs) makes invite links; `--public-url` gives them the public
  address. The app's welcome (`welcome()`, `located()`, `S.located`) asks a new guest for their place. The app opens with `#splash` (head.html; `splashGo()` once the board is ready).
- Notifications (relay 25, app 1.22): Web Push with the relay's VAPID key (`data/vapid.pem`), encrypted per RFC 8291
  (`push_send`, needs the `cryptography` package, `PUSH_OK`); subscriptions per profile (`p["push"]`, home in
  `profiles["home"]`), from the app's About → Notifications (`renderPush`, `enablePush`, also asked in the welcome; `app/sw.js`, registered as the app opens; https only). `_push_watch`
  runs `window_check` (passes within 5 km in 20–180 s: special, first-ever, favourite or below 3,000 ft) and
  `summary_check` (once a day at `SUMMARY_AT`) every 30 s. "Link a device to Home" (`/admin/homelink`) makes an
  invite for the pseudo-profile `home`: such a device is home from anywhere (`self.homelinked`), but `/admin` needs the
  home network itself (`at_home()`).
- Useful: `http://<relay>:8080/status` (JSON), `/screens` (screens using it); on the container
  `journalctl -u overhead-relay -f` is the relay's window (Enter-for-screens only works when run in a terminal).
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
Art Mode at night (Samsung's local TV API); a spotter's
collection page and weekly bingo of rare planes; rarity marks ("first time ever", "seen 4 times"); worth going to
the window (cloud base vs altitude, sunset, which window); runways in use at Vienna; a day in review at night; a Hue
light pulse for special planes (local Hue Bridge API), phone push via ntfy; a Vestaboard-style 6x22 view; a report of
what Flightradar24 added, to decide on renewing; merging the two test boards into one file with the API switched on
by address.
