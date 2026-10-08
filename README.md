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
| `radius` | Overhead radius in km (default 4) | `radius=3` |
| `home` | Home airport IATA code, for Arriving / Departing | `home=VIE` |
| `maxalt` | Ignore planes above this altitude in feet | `maxalt=15000` |
| `units` | `metric` for metres and km/h (default feet and knots) | `units=metric` |
| `refresh` | Seconds between position updates (default 10) | `refresh=15` |
| `pace` | Flap speed, 1 is original, higher is slower (default 1.15) | `pace=1.3` |
| `sound` | Flap sound on (`1`) or off (`0`) | `sound=1` |
| `logos` | Airline logos on (`1`) or off (`0`) | `logos=0` |
| `demo` | Sample flights instead of live data | `demo` |

Anything changed in the on-screen Settings is saved in that device's browser only.

## Controls

- Click the board, or press **F**, for fullscreen.
- Press **S** for settings.
- Sound starts after the first click or key press (browsers block it until then).

## Data

- Live aircraft positions: [adsb.lol](https://adsb.lol), with [airplanes.live](https://airplanes.live) as a fallback.
- Routes, airlines and aircraft details: [adsbdb](https://www.adsbdb.com) and the adsb.lol route service.
- Airline logos: the public airline logo service from Aviasales.

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
py serve.py --lat 48.2085 --lon 16.3731 --place Vienna --sound
```

When Windows Firewall asks, allow Python on **private** networks so other screens at home can reach it.

**Linux / homelab**

```bash
python3 serve.py --lat 48.2085 --lon 16.3731 --place Vienna --sound
```

Then open `http://localhost:8080`, or `http://<computer-name>:8080` from the TV, tablet or phone.
The relay prints the addresses when it starts. Your location stays on the relay machine: it is handed
to the board when the page loads, so nothing personal lives in this repository.

The relay always serves the latest published board from GitHub Pages (refreshed every five minutes,
with a local copy kept for when GitHub is unreachable). Use `--local path/to/index.html` to serve a
local file instead, and `--help` for all options.
