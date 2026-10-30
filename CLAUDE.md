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

**Finding the code: `py tools/codemap.py` lists the areas, `py tools/codemap.py AREA` every place of one (all files,
current lines), `--uses NAME` what else touches a name. Read small ranges (`sed -n`), never a big file whole or
`app/index.html`. `docs/code-map.md`: how, and the checklists of changes that go together.** `smoke.py --syntax` fails
on a function or CSS rule in no area: add it to `tools/codemap_areas.txt`.

## Rules Dave set (keep to them)

- **Test first.** Visual and feature changes go to the test board first. Copy to the main board (`index.html`) only
  when Dave says so.
- **One test board.** `test/` is the test board, Flightradar24 features included (since 17 Oct 2026, 1.35.2;
  `test-api/index.html` only forwards to `/test/`). Without a key it falls back to the free sources by itself.
- **Focus (21 Oct 2026):** only the phone app and the board, in English and the default board look. Unlockable
  styles, the APK and the parked light/Glass versions only when Dave asks; translations: see the text rule below.
- **Stay simple (30 Oct 2026): read `docs/design-brief.md` before any visible change or mockup.** At rest a card shows
  a label and a value, no sentence; the explanation opens on a tap of the label. Five keys in the bottom bar, one row
  of tabs, three taps to any fact; things open as panels, not pages. A feature wanting more room gets a row in an
  existing index, not a new tab, key or setting. A notice says what kind of thing it names and what to do. Three
  options for every design choice. Run the brief's check before sending a mockup and before opening a PR.
- **The phone app** (`app/`) is built from the test board's code, so new features reach the phone together with
  `test/`; rebuild it when shared code changes.
- **Versions and patch notes.** One version for the boards and the app, kept in `CHANGELOG` in the board (the
  "versions and patch notes" block, which the app copies). With every change add an entry at the top: a new feature
  raises the second number (1.8 → 1.9), a small change adds a third (1.8.1), a bug fix a fourth (1.8.1.1). Notes are
  short and generic (one line each, what changed for someone using it): no names, places or internals such as relay
  versions (guests read them too). Settings → About shows them. Bump `RELAY_VERSION` with every relay change.
- **Every visible text goes through `T()`** (test board and app): `T("English text", {vars})`, `{name}` placeholders.
  **No new rows in `test/i18n.js`** (Dave, 30 Oct 2026: no more translations until the app is finished; a missing row
  shows English; switching the language setting off is to-do #226). Flap status words stay English inside (key for colours and drum order) and are translated when drawn. No German
  second lines under labels; a second label word is only kept for units. Patch notes and the connection log stay English.
- **Don't rename statuses or remarks** (OVERHEAD, INBOUND, SUPERJUMBO, ...) unless asked.
- **No secrets or personal data in the repository; it is public.** The Flightradar24 key lives only in
  `overhead.json` next to the relay: never print, read out or commit that file. When a key is needed, Dave types it
  into the terminal himself; don't ask him to paste it in chat. Dave's home location never goes into the repository
  either (the relay hands it to the board at page load). Test data uses central Vienna (48.2085, 16.3731). No
  addresses of the homelab or tunnel here: they are in Claude's memory.
- Removed on request, don't bring back: the page-flip sound on page turns, the board shake, the Delay field, the
  falling-page animation for views.
- **Change SSH or the firewall only with a `systemd-run --on-active=180` rollback armed, cancelled once a fresh login
  works.** (On the relay's container; its home and updates: `docs/architecture.md`.)
- Android notifications (1.70): Firebase project "fallblatt". Its app config is the Actions secret `GOOGLE_SERVICES_JSON`
  (written into the build by CI, git-ignored); the service account key is `data/fcm.json` on the relay (mode 600, user
  overhead; replace it by copying a new key there over SSH or the Proxmox console). Never commit or print either.
- The Android signing key (Actions secrets `ANDROID_KEYSTORE_B64`, `ANDROID_KEYSTORE_PASSWORD`; backup in
  `%USERPROFILE%\overhead-android-key`): never commit or print it, never replace it, or phones refuse updates.
- No Tailscale suggestions (tried and dropped 11 Oct 2026). OpenSky is ruled out (needs a written licence).

## Where the rest is

**`docs/architecture.md`**: the Files table, how it works (board, Airport style, data, phone app, light and Glass,
relay, profiles and access) and the relay's home and how to update it. Read the part you need before changing an area
or the relay; `docs/code-map.md` and `docs/history.md` as above.

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
3. Syntax check: `py tools/test/smoke.py --syntax` (Node): the scripts parse, ESLint finds no undefined names
   (`tools/test/lint.py`; a name only one page has, reached behind a guard, goes in its OPTIONAL list) and the app's
   CSS keeps to the type scale (`tools/test/tokens.py`; use the `--fs-*` tokens).
4. For the TVs, the real screens are the test: open the relay's `/test/` on them.

Then commit (what changed and why), push, and tell Dave which boards changed and whether the relay needs an update.
