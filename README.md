# Overhead

An airport-style split-flap board that shows the planes flying over a chosen spot, live.
It is a single static page: open `index.html` in any modern browser, or serve it from GitHub Pages.

## Choosing the location

The page ships with central Vienna as its location. Set your own through the address, so the
location never has to live in this repository:

```
https://<user>.github.io/overhead-board/?lat=48.2085&lon=16.3731&place=Vienna
```

| Parameter | What it does | Example |
|-----------|--------------|---------|
| `lat`, `lon` | Spot to watch over | `lat=48.2085&lon=16.3731` |
| `place` | Name printed under the title | `place=Vienna` |
| `radius` | Spotting radius in km: planes within it are added to Spotted today (default 15) | `radius=8` |
| `over` | Counts as directly overhead within this many km (default 3) | `over=2` |
| `home` | Home airport IATA code, for Arriving / Departing | `home=VIE` |
| `maxalt` | Ignore planes above this altitude in feet | `maxalt=15000` |
| `units` | `aviation` for feet and knots (default metres and km/h) | `units=aviation` |
| `refresh` | Seconds between position updates (default 10) | `refresh=15` |
| `speed` | Flap speed in percent: 100 is fastest, 10 is ten times slower (default 85) | `speed=50` |
| `hd` | Render at 4K even if the screen reports a lower resolution | `hd` |
| `sound` | Flap sound on (`1`, the default) or off (`0`) | `sound=0` |
| `logos` | Airline logos on (`1`) or off (`0`) | `logos=0` |
| `theme` | Test board: `classic`, `frankfurt` or `blue` | `theme=frankfurt` |
| `rotate` | Test board: seconds per page, `0` to stay on one page (default 30) | `rotate=0` |
| `favs` | Test board: favourites, separated by commas | `favs=Austrian,A380` |
| `chimes` | Test board: chimes on (`1`, the default) or off (`0`) | `chimes=0` |
| `night` | Test board: night mode on (`1`, the default) or off (`0`) | `night=0` |
| `demo` | Sample flights instead of live data | `demo` |
| `debug` | Open the diagnostics panel at start | `debug` |

Anything changed in the on-screen Settings is saved in that device's browser only, and only the
values you changed are kept, so new defaults from the relay still reach that screen.

## What the board shows

The top half shows one plane and how it relates to you, worked out from its position, heading and speed:

- **Overhead**: directly above, within the overhead distance (3 km by default).
- **Inbound**: on course to pass over within three minutes; Position counts down to the pass.
- **Flying by**: getting closer, but its closest approach will be further than the overhead distance.
- **Outbound**: moving away. **Passed** is shown for a little while after an overhead pass.

Planes that are overhead or inbound always take the top spot; otherwise the board shows the plane in the
spotting radius that is coming closer. Every plane that enters the spotting radius is added to
**Spotted today** once per pass. The list marks the ones that flew directly overhead and otherwise shows
Arriving or Departing for your home airport. The Spotted today panel also lists each plane's closest distance.

## The three boards

| Address | What it is |
|---------|------------|
| `/` | **Main board**: the version for everyday use. Free data sources only. |
| `/test/` | **Test board**: where changes are tried before they go to the main board. Free data sources only. |
| `/test-api/` | **Test API board**: the test board plus features that need the paid Flightradar24 API. |

Changes are tried on a test board first and copied to the main board when they're ready. Features that need the
API are only ever built on `/test-api/`, so `/test/` always holds a complete version that works without it. If the
subscription ends, the main board keeps working: either it never had API features, or it falls back to the free
sources by itself (and `/test/` can be copied over it to remove them completely).

### Flightradar24 on the test API board

With a [Flightradar24 API](https://fr24api.flightradar24.com) key on the relay (version 8 or newer), `/test-api/`
shows the real flight number and route for airline flights: RYR3EG becomes FR 1234 Vienna to London instead of a
guess from a callsign database. Add the key once on the relay computer (it is saved in `overhead.json` there and
never leaves that computer):

```powershell
py serve.py --fr24-key YOUR_KEY --save
```

- Lookups happen only while a test API board is open, once per flight, shared by every screen, at most 10 a minute.
- Each lookup costs 1 to 3 credits. The relay stops at 27,000 credits a month (the Explorer plan includes 30,000);
  change that with `--fr24-budget 50000 --save`. Diagnostics on the test API board shows what has been used.
- If the key is refused (the subscription ended) or the budget is used up, the boards quietly use the free sources.
- To turn it off: `py serve.py --fr24-key off --save`.
- Flightradar24 data is kept for two days at most (their terms allow 30); the lifetime logbook doesn't use it.

## Test board

`/test/` is where changes are tried out before they go to the main board. Open it through the relay at
`http://<computer-name>:8080/test/`. It currently adds:

- **Rotating pages** in the lower half, every 30 seconds by default (Settings → Change pages every, or `?rotate=0`
  to stay on one page): Spotted today, **Today in numbers**, and **This aircraft** (a photo and registration details
  of the plane on the board, when one exists). Pages without anything to show are skipped. Pages change like one giant
  split flap: the whole lower half tips forward, falls and settles with a small bounce, revealing the next page. To pick
  a page yourself, click its dot or the arrows next to the page title, or use the left and right arrow keys or the keys
  1 to 3; a page you pick stays for at least a minute.
- **Special aircraft**: A380s, 747s, Belugas, Antonovs, military and government aircraft, helicopters and
  emergency squawks (7500, 7600, 7700) get their own remark. The status flap alternates between the plane's
  status and that remark.
- **Favourites**: airlines, aircraft types or registrations listed in Settings (for example
  `Austrian, Emirates, A380, 747, OE-LBN`) are marked FAVOURITE.
- **Chimes**: a two-note chime when a special aircraft enters the spotting radius, three rising notes for a
  favourite, and a separate alert for emergencies. Needs a first click or key press, like the flap sound.
- **Spotted today** (press **T**, or the Spotted today button): today's full list as its own tab, with airline,
  route, aircraft, registration, closest distance, altitude and remarks, filterable to overhead or special planes.
- **Logbook** (press **L**): every type, airline and individual aircraft ever spotted, with counts and first
  sightings. The first sighting of a new type or airline is marked NEW TYPE or NEW AIRLINE on the board.
- **Radar** (press **R**): a plan view of everything around you, with trails, the spotting radius, the airport's
  runways and the nearest planes. Add `#spotted`, `#logbook` or `#radar` to the address to open a tab at start.
- **Board styles**: classic white on black, Frankfurt yellow on black, or white on blue, each with its own typeface
  (Settings, or `?theme=frankfurt` / `?theme=blue`).
- **Worn hardware**: modules sit very slightly out of line and the odd flap hesitates or catches. Can be turned off.
- **Night mode**: dims the board and mutes it between set times (22:30 to 07:00 by default; `?night=0` turns it off).

The logbook and a Spotted today list shared by every screen need relay version 5 or newer (see below).

## Controls

- Click the board, or press **F**, for fullscreen.
- Press **S** for settings.
- Press **D**, or use **Diagnostics** in the corner, for the connection log: which source the data
  comes from, recent failures, the closest plane and why it was or wasn't added to Spotted today.
  **Copy log** puts everything on the clipboard. Add `?debug` to the address to open it at start.
- Flap sound is on by default but starts after the first click or key press (browsers block it until then);
  the status line reminds you. Turn it off in Settings, with `?sound=0`, or with the relay's `--mute`.

## Data

- Live aircraft positions: [adsb.lol](https://adsb.lol), with [airplanes.live](https://airplanes.live) as a fallback.
- Routes, airlines and aircraft details: [adsbdb](https://www.adsbdb.com) and the adsb.lol route service.
  These are looked up by callsign, and airlines reuse callsigns (Ryanair especially), so a listed route is only
  shown when the plane is actually along it and heading towards its destination; otherwise the route stays blank.
- Airline logos: the public airline logo service from Aviasales. When an airline has no logo there, its
  code is shown instead; flights without an airline (private, military, unlisted) get a plain aircraft mark.

The position services don't let browsers on other websites read their data, and they turn away
requests from cloud servers. So the live data has to come through a small relay running on a computer
in your home: [`relay/serve.py`](relay/serve.py). Opened directly from GitHub Pages, the board can't get
positions and says so in its status line.

## Running the home relay

The relay serves the board and fetches the flight data from your home connection. It needs Python 3.8
or newer and nothing else.

**Windows**

```powershell
winget install Python.Python.3.13          # skip if `py --version` already works
mkdir $HOME\overhead-relay; cd $HOME\overhead-relay
curl.exe -O https://raw.githubusercontent.com/Belstria/overhead-board/main/relay/serve.py
py serve.py --lat 48.2085 --lon 16.3731 --place Vienna --save
```

`--save` stores your settings in `overhead.json` next to the script (it never goes into this repository),
so from then on `py serve.py` on its own starts the relay with your location. Anything you pass on the
command line still wins over the saved file. Other relay options: `--units aviation`, `--radius 8`, `--mute`,
`--home VIE`, `--port 8080`.

When Windows Firewall asks, allow Python on **private** networks so other screens at home can reach it.

**Linux / homelab**

```bash
python3 serve.py --lat 48.2085 --lon 16.3731 --place Vienna --save
```

Then open `http://localhost:8080`, or `http://<computer-name>:8080` from the TV, tablet or phone.
The relay prints the addresses when it starts. Your location stays on the relay machine: it is handed
to the board when the page loads, so nothing personal lives in this repository.

Positions come from adsb.lol, adsb.fi and airplanes.live, tried in that order. A source that answers
"too many requests" or "forbidden" is rested for a while and the next one is used; if all of them fail,
the relay keeps serving the last good data for up to two minutes. Problems are printed in the relay's
window and appear in the board's diagnostics panel.

**Shared history (relay version 5).** The relay records every plane that comes within its spotting radius
itself, so every screen shows the same Spotted today list and nothing is lost when a browser is closed. It
also keeps a lifetime logbook. Both live in a `data` folder next to `serve.py` (`sightings-<date>.json` and
`logbook.json`). A new logbook spends its first day learning what normally flies over, so NEW TYPE and
NEW AIRLINE marks start the day after. The spotting radius the relay uses is `--radius` (15 km by default).

The relay always serves the latest published board from GitHub Pages (it checks for a newer one at most once
a minute, so a change shows up a minute or two after it is published; a local copy is kept for when GitHub is
unreachable). Use `--local path/to/index.html` to serve a
local file instead, `--source URL` to read positions from your own receiver (a URL with `{lat}`, `{lon}` and
`{nm}` placeholders, or a local `aircraft.json`), and `--help` for all options.
