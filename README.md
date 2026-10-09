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
| `airtime` | Test board: minutes an hour a helicopter or circling plane may hold the top half, `0` for no limit (default 3) | `airtime=5` |
| `photo` | Test board: the aircraft photo `screen` (default), `engraved` or `plain` | `photo=engraved` |
| `quality` | Test board: `auto` (default), `high`, `1440`, or `1080` (lighter, for TVs) | `quality=1080` |
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

- Remarks from Flightradar24: **DIVERTED** (the Spotted today tab shows where to), **CARGO**, **BIZJET**, **PRIVATE**,
  and military and helicopter flights by Flightradar24's own category. Flightradar24's API has no schedules, so delays
  aren't available from it.
- Lookups happen only while a test API board is open, once per flight, shared by every screen, at most 10 a minute.
- Each lookup costs 1 to 3 credits. The relay stops at 27,000 credits a month (the Explorer plan includes 30,000);
  change that with `--fr24-budget 50000 --save`. Diagnostics on the test API board shows what has been used.
- If the key is refused (the subscription ended) or the budget is used up, the boards quietly use the free sources.
- To turn it off: `py serve.py --fr24-key off --save`.
- Flightradar24 data is kept for two days at most (their terms allow 30); the lifetime logbook doesn't use it.

## Test board

`/test/` is where changes are tried out before they go to the main board. Open it through the relay at
`http://<computer-name>:8080/test/`. It currently adds:

- **Flight times** in a fourth row of the top half: departure, arrival and flight time so far. Vienna Airport
  publishes its arrivals and departures with planned and expected times, and the relay (version 11 or newer) reads
  them, so flights to and from Vienna get an arrival or departure time. On the test API board Flightradar24 adds the
  take-off time, and with it the flight time, for any flight. When there is no arrival time but the destination is
  known, the board estimates one from the distance still to fly and the plane's speed, plus a few minutes to land.
  Overflights without a known route show what is known, often nothing.
- **Special planes take the board**: when a plane rings the bell (an emergency, a special or military aircraft, a
  favourite), it goes straight onto the top half and the lower half turns to **This aircraft**, and both stay with it
  while it is within the spotting radius. Without a photo, the screen there says so.
- **Rotating pages** in the lower half, every 30 seconds by default (Settings → Change pages every, or `?rotate=0`
  to stay on one page): **Recent flights** (the last eight planes that were on the top half, kept per screen),
  **Today in numbers** (counted over the whole day by the relay), and **This aircraft** (a photo and registration details
  of the plane on the board, when one exists). Pages without anything to show are skipped. Pages change like one giant
  split flap: the whole lower half tips forward, falls and settles with a small bounce, revealing the next page; flaps
  still turning on the old page keep turning as it falls. A rail of backlit push buttons runs along the bottom of the
  board: the pages on the left, the views on the right. The button for what is on show is lit, with a small flicker as
  the lamp comes on. To pick a page yourself, press its button, or use the left and right arrow keys or the keys 1 to 3;
  a page you pick stays for at least a minute.
- **Views on the board**: Spotted today, Logbook, Radar and Settings take over the whole board below the header at
  once, without the falling page, and show on the board itself: lists and numbers on split flaps or engraved into the
  panel. Press the button again, Esc, or a page button to turn back; left alone for five minutes, a view turns back by itself. Add
  `#spotted`, `#logbook`, `#radar` or `#settings` to the address to open one at start.
- **The aircraft photo** sits on a small screen set into the board, in a housing with screws and a power light; the
  screen is off while the page falls into place and warms up after it lands. Settings → Aircraft photo (or
  `?photo=engraved` / `?photo=plain`) can instead engrave it into the metal as fine lines, or show the plain photo.
- **Special aircraft**: A380s, 747s, Belugas, Antonovs, military and government aircraft, helicopters and
  emergency squawks (7500, 7600, 7700) get their own remark. The status flap alternates between the plane's
  status and that remark.
- **Favourites**: airlines, aircraft types or registrations listed in Settings (for example
  `Austrian, Emirates, A380, 747, OE-LBN`) are marked FAVOURITE.
- **Chimes**: a two-note chime when a special aircraft enters the spotting radius, three rising notes for a
  favourite, and a separate alert for emergencies. Needs a first click or key press, like the flap sound.
- **The day runs from 03:00 to 03:00**, so late-evening flights count to the evening they belong to.
- **Airtime limit**: a plane that hangs around (a police helicopter over an incident, a light aircraft circling) gets at
  most 3 minutes an hour on the top half while other planes are within the spotting radius, then gives them a turn.
  It counts helicopters and anything slower than 140 knots; other planes only after six minutes, so an airliner
  passing over is never cut short. With nothing else around it stays on the board. Settings → Limit hovering planes,
  or `?airtime=5`; Diagnostics notes each time it happens.
- **Spotted today** (press **T**): every plane that came within the spotting radius today, seventeen rows to a page
  as plain text engraved into the panel, like the legend: time, flight, airline, route, aircraft and registration,
  closest distance, altitude and remarks. Special planes get a lamp and a tinted row in the remark's colour. Buttons above it filter to overhead or special planes, turn the pages (or the arrow keys), and
  show the **Legend** of every remark. It covers the whole day (relay 10 or newer; older relays send the newest 400).
- **Logbook** (press **L**): totals, the most seen model, the categories, and the top aircraft types, airlines and
  individual aircraft, with the newest ones, all on flaps. How many were passenger, cargo, business jet, private and light, helicopter,
  military or other flights (sorted by the relay from the free data, so the numbers are the same on every board;
  relay 10 or newer, which also counts the days already saved). The first sighting of a new type or airline is
  marked NEW TYPE or NEW AIRLINE on the board.
- **Radar** (press **R**): a plan view of everything around you in an instrument set into the board, with trails,
  the spotting radius and the airport's runways, and the twelve nearest planes on flaps beside it.
- **Settings** (press **S**): a cockpit panel. Rotary selectors, flip switches, thumbwheels and amber read-outs on
  painted plates with screws; nothing changes until **Save**, and Cancel leaves everything as it was.
- **Board styles**: classic white on black, Frankfurt yellow on black, or white on blue, each with its own typeface
  (Settings, or `?theme=frankfurt` / `?theme=blue`).
- **Worn hardware**: modules sit very slightly out of line and the odd flap hesitates or catches, and the panel has
  some honest wear: fine scratches, polish marks, grime in the corners, paint rubbed off the edges, a few small dings.
  Can be turned off.
- **Night mode**: dims the board and mutes it between set times (22:30 to 07:00 by default; `?night=0` turns it off).
- **Drawing quality** (Settings, or `?quality=`): Automatic draws as sharp as the screen allows, up to 4K, except on
  Fire TV and LG TVs, which get `1080`: drawn at 1080p, 30 frames a second, shorter flap runs and a smaller image cache,
  because their graphics chips struggle with the full board. `1440` sits in between, `high` forces the sharpest. The
  falling page is always drawn at 1080p at most; it moves too fast to need more.

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
- Planned and expected times (test boards): [Vienna Airport](https://www.viennaairport.com/en/passengers/arrival__departure)'s
  own arrivals and departures lists, read by the relay at most every three minutes while a board is open.
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
