// Overhead board relay (Cloudflare Worker).
// The live ADS-B services don't allow browsers on other websites to read their data, so this
// worker fetches it on the board's behalf and adds the header that lets the board read it.
// It only forwards the two kinds of request the board makes, so it can't be used as an open proxy.

const ALLOWED_ORIGINS = [
  "https://belstria.github.io",
];

const POSITION_SOURCES = {
  adsblol: "https://api.adsb.lol/v2/point/",
  airplaneslive: "https://api.airplanes.live/v2/point/",
};
const ROUTESET = "https://api.adsb.lol/api/0/routeset";
const USER_AGENT = "overhead-board (github.com/Belstria/overhead-board)";

export default {
  async fetch(request, env, ctx) {
    const origin = request.headers.get("Origin") || "";
    const cors = {
      "Access-Control-Allow-Origin": ALLOWED_ORIGINS.includes(origin) ? origin : ALLOWED_ORIGINS[0],
      "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
      "Access-Control-Allow-Headers": "Content-Type",
      "Access-Control-Max-Age": "86400",
      "Vary": "Origin",
    };
    if (request.method === "OPTIONS") return new Response(null, { headers: cors });

    const url = new URL(request.url);

    // Aircraft around a point: /adsblol/<lat>/<lon>/<radius in nm>
    const m = url.pathname.match(/^\/(adsblol|airplaneslive)\/(-?\d{1,2}(?:\.\d{1,6})?)\/(-?\d{1,3}(?:\.\d{1,6})?)\/(\d{1,3})$/);
    if (request.method === "GET" && m) {
      const [, source, lat, lon, nm] = m;
      if (Math.abs(+lat) > 90 || Math.abs(+lon) > 180 || +nm < 1 || +nm > 50) return text("Out of range", 400, cors);
      const upstream = `${POSITION_SOURCES[source]}${lat}/${lon}/${nm}`;
      const cache = caches.default, key = new Request(upstream);
      let res = await cache.match(key);
      if (!res) {
        const r = await fetch(upstream, { headers: { "User-Agent": USER_AGENT, "Accept": "application/json" } });
        res = new Response(r.body, r);
        res.headers.set("Cache-Control", "public, max-age=5");
        if (r.ok) ctx.waitUntil(cache.put(key, res.clone()));
      }
      return withCors(res, cors);
    }

    // Route lookup fallback: POST /routeset with {"planes":[{callsign,lat,lng}]}
    if (request.method === "POST" && url.pathname === "/routeset") {
      const body = await request.text();
      if (body.length > 2048) return text("Too large", 413, cors);
      const r = await fetch(ROUTESET, {
        method: "POST",
        headers: { "Content-Type": "application/json", "User-Agent": USER_AGENT },
        body,
      });
      return withCors(new Response(r.body, r), cors);
    }

    return text("Not found", 404, cors);
  },
};

function withCors(res, cors) {
  const out = new Response(res.body, res);
  for (const [k, v] of Object.entries(cors)) out.headers.set(k, v);
  return out;
}
function text(msg, status, cors) {
  return new Response(msg, { status, headers: { ...cors, "Content-Type": "text/plain" } });
}
