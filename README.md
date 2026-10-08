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

## Test board

`/test/` is a copy of the main board for trying out visual changes before they go live. It uses the same
data, settings and Spotted today history as the main board. Open it through the relay at `http://<computer-name>:8080/test/` (relay version 3 or newer).

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

The relay always serves the latest published board from GitHub Pages (refreshed every five minutes,
with a local copy kept for when GitHub is unreachable). Use `--local path/to/index.html` to serve a
local file instead, and `--help` for all options.
