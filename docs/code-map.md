# The code map: finding the right place cheaply

`tools/codemap.py` (to-do #109) knows where every part of Fallblatt lives. The big files are too big to read whole:
`test/index.html` is about 9,000 lines (160k tokens), `relay/serve.py` 7,200, `tools/app/main.js` 4,000. Whatever a
session reads stays in its chat and is read again on every later step, so read only the lines you need.

A feature is never in one place. The plane photos (1.93) touched about 15 board functions, the app's CSS, markup and
four main.js functions, the relay, the i18n rows, three test files, the README, the history and CLAUDE.md. So the map
is organised by **area**, and each area lists every place it has in every file, the small ones too, and the places
of other areas it reaches into (marked `+`).

## How to read here

1. `py tools/codemap.py`: the areas, one line each. Pick the one (or the few) your change belongs to.
2. `py tools/codemap.py AREA`: every place of that area, file by file, with its current lines and its comment; who
   calls its relay endpoints (board, app, flows.py) and the relay version each caller checks; and what goes together
   with it: its i18n rows, README bullets, history entries, CHANGELOG notes and tests. `[app E21]` on a board line
   means the app build copies it (see `--build`). The start of an area's name will do.
3. `py tools/codemap.py --uses NAME` for each name you will change: every line in the sources, tests and docs that
   mentions it, and the function it sits in. This is the "what else touches this" check.
4. Then read small ranges: `sed -n 4003,4020p test/index.html`, or `grep -n` for a word. Never `cat` a big file whole.
5. Never read `app/index.html`: it is generated from the board, `head.html` and `main.js` (`py tools/app/build.py`).
   `index.html` is a copy of `test/index.html` (made by `tools/push_main.py`), and `light/`, `glass/` are parked.

More:

- `py tools/codemap.py --find WORD`: functions, sections, CSS and areas whose name or comment has the word.
- `py tools/codemap.py --file PATH [WORD]`: a file's outline (sections, functions, CSS keys, markup ids, line ranges);
  with a word, only what matches it.
- `py tools/codemap.py --build`: what `tools/app/build.py` copies out of the board (each `//@E` part: board lines, the
  marker in main.js, where it starts in the app) and the strings it patches. A marker that moves stops the build; a
  patched string that changes fails its assert.
- `py tools/codemap.py --diff [REV]`: the places your branch changed since REV (default `origin/main`), and the areas
  that list them. Run it before opening a PR: every area it names may have other places that go with your change.
- `py tools/codemap.py --check`: what is in no area, and the places the map names that are gone (`smoke.py --syntax`
  runs it, so does GitHub).

## Keeping the map current

The areas are `tools/codemap_areas.txt` (its header explains the format). Every top-level function, const, let and
class of the board, main.js and the relay, and every CSS rule of the board and `head.html`, must be in an area. When
`smoke.py --syntax` says something is in no area:

- **New function or constant**: add its name to the `path:` line of its area (the message names the neighbours' areas).
  Places are named, never numbered. If another area reaches into it, list it there too with a `+`: `+planeBody`.
- **Renamed**: the check names the old place that is gone and the new one; rename it in the list.
- **New CSS**: the rules go by their first selector (`.cap:hover` is `.cap`; `body.lite .x` is `css:body.lite`). A class
  that is only styled inside another rule (`#cardBox .cCr`) can be listed as `.cCr` too.
- **Top-level statements** (`setInterval(...)`, `addEventListener(...)`) go with the function above them, or the one
  their first line names. If two have the same name, name the one you mean by a quoted text in it.
- **Tests, README, CLAUDE.md**: a quoted text that is on that line (`"- **Whose photo**"`, `"relay 73: a plane's own"`).
- **A new area**: `[name] one line`, then its files. Keep a `changelog:` pattern that finds its patch notes.

## Changes that go together

**A new visible text**
- `T("English text", {vars})` (board, main.js), `data-t="..."` on the app's fixed markup (head.html).
- A row in `test/i18n.js` (English, German, French, Spanish, Dutch); `py tools/app/build.py` stamps the new
  `i18n.js?v=` into the board. A missing row shows English. Patch notes and the connection log stay English.

**A new relay endpoint**
- Its branch in `Handler.do_GET` / `do_POST` (or `profile_post`, `admin_post`, `account_post`, `pair_post`), with a
  rate limit (`allow(...)`); who may call it (`self.stranger`, `owner_ok()`, `ADMIN_PATHS`).
- A path without a trailing slash goes in the list in `do_GET` of paths that aren't redirected to `path/` (the 301
  list); a path screens poll goes in `BOARD_PATHS` (the screens list counts them).
- `RELAY_VERSION` + 1, and CLAUDE.md's "`RELAY_VERSION` at the top (N now)". The board and app call it only behind
  `(window.OVERHEAD_RELAY_VERSION || 0) >= N`.
- A check in `tools/test/flows.py`; if it calls an outside service, the fake in `tools/test/fakesrc.py` and the URL
  replacement in `tools/test/run_test_relay.py`.
- README (Running the home relay) and docs/history.md (The relay). Update the relay as CLAUDE.md says.

**A board feature that reaches the app**
- Board code inside a build marker range is copied into the app: `codemap.py --build` shows which part and where.
  The app's own glue is in main.js (`renderAircraftInfo`, `renderToday`, ...), its CSS and markup in head.html (font
  sizes only as `--fs-*` tokens: tokens.py checks).
- A name only one page has, reached from shared code behind a guard, goes in `tools/test/lint.py`'s `OPTIONAL`.
- `py tools/app/build.py`, then commit `app/index.html` (GitHub fails a stale one).

**A TV change**
- `WEAK_TV` (Fire TV, LG) and `LITE()` (1080p, 30 fps, shorter runs); the Fire TV lays out at 960x540, so board CSS in
  the cockpit and views is `calc(Npx*var(--k))`.
- Plates can't scroll: smoke.py checks Settings, Account & device, About and the Logbook at the Fire TV's size
  (`tools/test/plates.py`); `SIZE=960x540 DPR=2 py tools/test/shoot.py ...` to look.
- The remote: the keydown handlers (`codemap.py tv`), Back is also keyCode 10009 (Samsung) and 461 (LG); the ring is
  `:focus`. `keys/index.html` tests a remote's keys. The real screens are the test.

**A new setting**
- `DEFAULTS` (board and main.js), its `COCKPIT` entry (`for`/`flaps`/`phone`/`light`), `itemHtml`, `wireCockpit`,
  `cockpitShow`, its `HINTS` line, `applySettings` (board and main.js). It reaches the profile through
  `settingsChanged`/`meSend` unless it stays on the device.
- `tools/test/cockpit_list.py` before and after (nothing lost); it must fit its plate on the Fire TV.
- Its texts (above), README (Settings).

**A version**
- A `CHANGELOG` entry at the top of the board's "versions and patch notes" (a feature raises the second number, a
  small change adds a third, a fix a fourth; notes short, generic, for anyone).
- A docs/history.md entry in its part (board, app, relay) naming the functions; README for what a user notices.
- `RELAY_VERSION` for a relay change. Rebuild the app.

Every area's page ends with these "every change" places and their current lines.
