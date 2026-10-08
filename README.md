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
| `proxy` | Address of your relay, if not built into the page | `proxy=https://overhead-proxy.example.workers.dev` |

Anything changed in the on-screen Settings is saved in that device's browser only.

## Controls

- Click the board, or press **F**, for fullscreen.
- Press **S** for settings.
- Sound starts after the first click or key press (browsers block it until then).

## Data

- Live aircraft positions: [adsb.lol](https://adsb.lol), with [airplanes.live](https://airplanes.live) as a fallback.
- Routes, airlines and aircraft details: [adsbdb](https://www.adsbdb.com) and the adsb.lol route service.
- Airline logos: the public airline logo service from Aviasales.

The position services don't allow browsers on other websites to read their data, so those requests go
through a small relay: a free Cloudflare Worker whose code is in [`proxy/worker.js`](proxy/worker.js).
It only forwards the board's own two kinds of request and adds the header that lets the browser read
the answer. Route lookups (adsbdb) and logos load directly. No API keys are needed anywhere.

### Setting up the relay

1. Sign in at [dash.cloudflare.com](https://dash.cloudflare.com) (a free account is enough).
2. Go to **Workers & Pages → Create → Create Worker**, name it `overhead-proxy`, and click **Deploy**.
3. Click **Edit code**, replace everything with the contents of `proxy/worker.js`, and click **Deploy** again.
4. The relay's address is shown on the worker page, for example `https://overhead-proxy.<your-subdomain>.workers.dev`.
   Set it as `PROXY` near the top of the data section in `index.html`, or pass it with `?proxy=`.

If you host the board somewhere other than `belstria.github.io`, add that address to `ALLOWED_ORIGINS` in the worker.
