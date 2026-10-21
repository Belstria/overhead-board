// The glass version's code (1.71): its region of tools/app/main.js (//@L:extra), on top of the light version.
// tools/glass/build.py puts it in; every other region is light.js's.

//@L:extra
/* ---------- the glass version (1.71, "Glasshouse", designed with Gemini) ----------
   A light, map-first app: the live map fills the screen (the radar's own map and planes, drawn light), the plane that
   matters floats over it on a photo card, and Today, Logbook, Nearby and Settings slide over the map as pages. Under it
   is the light version, so every feature, setting and card is the same: this layer only lays them out anew. */
const G = {cv: null, px: 1, sel: "", hits: [], raf: 0, last: 0, pill: 0, sig: "", active: true};
document.documentElement.classList.add("glass");
// The map in the glass version's colours: warm white land, pale water, quiet grey roads; the planes in bold colours
// that read on it (and on photos).
RADAR_MAP_LOOK.splice(0, RADAR_MAP_LOOK.length,
  ["landuse", ["residential", "commercial", "industrial", "retail"], "rgba(15,23,42,.035)"],
  ["water", null, "#dfe9ef"],
  ["waterway", ["river", "canal"], "#cfdfe9", 1.8],
  ["transportation", ["secondary", "tertiary"], "rgba(15,23,42,.07)", .8],
  ["transportation", ["primary", "trunk"], "rgba(15,23,42,.1)", 1.1],
  ["transportation", ["motorway"], "rgba(180,140,60,.28)", 1.6],
  ["aeroway", ["apron"], "rgba(15,23,42,.05)", 0, 6],
  ["building", null, "rgba(15,23,42,.06)", 0, 6],
  ["aeroway", ["taxiway"], "rgba(100,116,139,.35)", 1.4, 6],
  ["aeroway", ["runway"], "#a3b1c2", 2.6]);
Object.assign(RADAR_COL, {over: "#2563eb", soon: "#059669", by: "#0ea5e9", away: "#64748b", high: "#a8b3c2", special: "#9333ea",
  emergency: "#dc2626", fav: "#db2777", ground: "#78716c", dep: "#ea580c", arr: "#059669"});
// The page's own colours, also over what applyTheme sets on the root (it runs again after every Settings save).
const GLASS_VARS = {"--f-board": '"Inter","Archivo Narrow",sans-serif', "--ink": "#0f172a", "--amber": "#2563eb", "--metal": "#ffffff", "--label2": "#94a3b8"};
// It also keeps the Daylight rules on (light chips, fields and cards), which applyTheme would take off.
function glassVars(){
  const h = document.documentElement, r = h.style;
  for (const [k, v] of Object.entries(GLASS_VARS)) if (r.getPropertyValue(k) !== v) r.setProperty(k, v);
  if (!h.classList.contains("daylight")) h.classList.add("daylight");
}
new MutationObserver(glassVars).observe(document.documentElement, {attributes: true, attributeFilter: ["style", "class"]});
glassVars();

const GLASS_ICON = {
  home: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 11.5 12 5l8 6.5V20h-5v-5h-6v5H4z" fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round"/></svg>',
  runway: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M7 21 11 3M17 21 13 3M12 6v2M12 11v2M12 16v2" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg>',
  me: '<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="8.5" r="3.5" fill="none" stroke="currentColor" stroke-width="2"/><path d="M5 20c1.2-3.6 3.8-5.5 7-5.5s5.8 1.9 7 5.5" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg>',
  back: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M15 5l-7 7 7 7" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"/></svg>'};
document.body.insertAdjacentHTML("afterbegin",
  `<canvas id="gMap" aria-label="${escH(T("Map of the planes around you"))}"></canvas>` +
  `<div id="gCtl"><div class="gSeg" role="group"><button type="button" data-gm="overhead">${GLASS_ICON.home}</button><button type="button" data-gm="airport">${GLASS_ICON.runway}</button></div>` +
  `<button type="button" id="gMe">${GLASS_ICON.me}<i id="gDot"></i></button></div>` +
  `<div class="gEdges"><button type="button" id="gToday"><span></span></button><button type="button" id="gLog"><span></span></button></div>` +
  `<div id="gCard" tabindex="0" role="button"></div>`);
G.cv = $("gMap");
for (const s of document.querySelectorAll("main .tab:not(#t-now)")) {                // each page: a way back to the map
  s.insertAdjacentHTML("afterbegin", `<button type="button" class="gBack">${GLASS_ICON.back}<span></span></button>`);
  s.querySelector(".gBack").onclick = () => { ctlSound.press(); showTab("now"); };
}
function glassLabels(){
  for (const b of document.querySelectorAll(".gBack span")) b.textContent = T("Map");
  $("gToday").querySelector("span").textContent = T("Today"); $("gLog").querySelector("span").textContent = T("Logbook");
  for (const b of document.querySelectorAll("[data-gm]")) b.setAttribute("aria-label", T(b.dataset.gm === "airport" ? "Airport" : "Overhead"));
  $("gMe").setAttribute("aria-label", T("Settings"));
}
glassLabels();
for (const b of document.querySelectorAll("[data-gm]")) b.onclick = () => { setMode(b.dataset.gm); G.sig = ""; glassCard(); };
$("gMe").onclick = () => { ctlSound.press(); showTab("settings"); };
$("gToday").onclick = () => { ctlSound.press(); showTab("today"); };
$("gLog").onclick = () => { ctlSound.press(); showTab("logbook"); };
// The map shows while no page covers it (Now): it is drawn then, and only then fetches its tiles.
new MutationObserver(() => { G.active = !$("t-now").hidden; radarMapOn = G.active; if (G.active) glassLoop(); }).observe($("t-now"), {attributes: true, attributeFilter: ["hidden"]});

/* The map: centred on your place (or the airport), the planes by status with their trails, the spotting radius, the
   distance rings, the runways. Its top part is clear of the card, which floats over the lower part. */
function glassGeo(){
  const W = innerWidth, H = innerHeight, side = W > H, card = side ? 0 : Math.min(H * .42, 360);
  const cx = side ? W * .62 : W / 2, cy = side ? H / 2 : Math.max(150, (H - card) / 2 + 20), R = side ? H * .42 : Math.min(W * .45, (H - card) * .42);
  return {W, H, cx, cy, R};
}
function glassSize(){
  G.px = Math.min(2.5, devicePixelRatio || 1);
  const w = Math.round(innerWidth * G.px), h = Math.round(innerHeight * G.px);
  if (G.cv.width !== w || G.cv.height !== h) { G.cv.width = w; G.cv.height = h; }
}
function glassPaint(){
  glassSize();
  radar.px = G.px;
  const g = G.cv.getContext("2d"), {W, H, cx, cy, R} = glassGeo(), now = Date.now(), TAU = Math.PI * 2;
  g.setTransform(G.px, 0, 0, G.px, 0, 0);
  g.fillStyle = "#faf9f6"; g.fillRect(0, 0, W, H);
  const range = radarRange(), k = R / range, C = radarCentre(), kx = 111.32 * Math.cos(C.lat * Math.PI / 180), ky = 110.57;
  const toXY = (lat, lon) => [cx + (lon - C.lon) * kx * k, cy - (lat - C.lat) * ky * k];
  const Rc = Math.ceil(Math.hypot(Math.max(cx, W - cx), Math.max(cy, H - cy)) / 50) * 50;      // the map reaches every corner
  radarMapOn = G.active;
  radarMapDraw(g, cx, cy, Rc, range * Rc / R, C, G.px);
  if (!C.ap) { g.fillStyle = rgba(RADAR_COL.over, .06); g.beginPath(); g.arc(cx, cy, overKm() * k, 0, TAU); g.fill(); }
  const step = radarRing(range);
  g.strokeStyle = "rgba(100,116,139,.22)"; g.lineWidth = 1; g.setLineDash([3, 5]);
  for (let r = step; r * k < Rc; r += step) { g.beginPath(); g.arc(cx, cy, r * k, 0, TAU); g.stroke(); }
  g.setLineDash([7, 6]); g.strokeStyle = rgba(RADAR_COL.over, .45); g.lineWidth = 1.5;
  g.beginPath(); g.arc(cx, cy, (+S.radiusKm || 15) * k, 0, TAU); g.stroke(); g.setLineDash([]);
  airportPos();
  const ap = AP.code === clean(S.home).slice(0, 3) && AP.lat != null && AP.rwys.length ? AP : null;
  if (ap) {
    const u = rwyInUse();
    g.lineCap = "round";
    for (const r of ap.rwys) {
      const used = [r.a.id, r.b.id].some(id => u.arr.includes(id) || u.dep.includes(id));
      const [x1, y1] = toXY(r.a.lat, r.a.lon), [x2, y2] = toXY(r.b.lat, r.b.lon);
      g.strokeStyle = used ? rgba(RADAR_COL.dep, .8) : "#a3b1c2"; g.lineWidth = used ? 4 : 3;
      g.beginPath(); g.moveTo(x1, y1); g.lineTo(x2, y2); g.stroke();
    }
    g.lineCap = "butt";
  }
  const featHex = feat && feat.o && feat.o.ac.hex, shown = [];
  for (const o of radar.planes) {
    const ac = o.ac, pos = radarPos(o, now, kx, ky), [x, y] = toXY(pos.lat, pos.lon);
    if (x < -30 || x > W + 30 || y < -30 || y > H + 30) continue;
    const col = radarColor(o), tr = radar.trails.get(ac.hex), main = ac.hex === (G.sel || featHex);
    if (tr && tr.length > 1) {
      g.strokeStyle = rgba(col, .4); g.lineWidth = 2; g.lineCap = "round"; g.beginPath();
      tr.forEach((p, i) => { const [qx, qy] = toXY(p.lat, p.lon); i ? g.lineTo(qx, qy) : g.moveTo(qx, qy); });
      g.lineTo(x, y); g.stroke(); g.lineCap = "butt";
    }
    const size = (radarZoomed() ? 26 : 22) * (main ? 1.25 : 1) * (o.kind || ac.alt_baro === "ground" ? 1 : .8);
    if (main) { g.fillStyle = rgba(col, .16); g.beginPath(); g.arc(x, y, size * .95, 0, TAU); g.fill(); }
    g.save(); g.translate(x, y); g.rotate(((ac.track || 0) * Math.PI / 180) - Math.PI / 4);
    drawPlane(g, 0, 0, size + 5, "#ffffff");                        // a white edge: the plane stands off the map
    drawPlane(g, 0, 0, size, col);
    g.restore();
    shown.push({o, x, y, col, main});
  }
  G.hits = shown.map(s => ({o: s.o, x: s.x, y: s.y}));
  glassNames(g, shown, W, H);
  g.fillStyle = "#ffffff"; g.beginPath(); g.arc(...(C.ap ? toXY(S.lat, S.lon) : [cx, cy]), 7, 0, TAU); g.fill();       // your place
  g.fillStyle = "#0f172a"; g.beginPath(); g.arc(...(C.ap ? toXY(S.lat, S.lon) : [cx, cy]), 4.5, 0, TAU); g.fill();
}
// The flight and height beside each plane that counts, on a soft light edge, where they don't cover another.
function glassNames(g, shown, W, H){
  const boxes = [];
  const nameOf = o => { const info = (infoCache.get(o.ac.hex + "|" + String(o.ac.flight || "").trim().toUpperCase()) || {}).info;
    return (info && info.flightNo) || String(o.ac.flight || "").trim() || o.ac.r || o.ac.hex.toUpperCase(); };
  g.textBaseline = "alphabetic"; g.lineJoin = "round";
  for (const s of shown.filter(s => s.o.kind || s.main).sort((a, b) => (b.main - a.main) || a.o.dist - b.o.dist)) {
    const name = nameOf(s.o), sub = s.o.ac.alt_baro === "ground" ? String(s.o.ac.t || "") : altShort(s.o.alt);
    g.font = `700 13px Inter, sans-serif`; const w = Math.max(g.measureText(name).width, (g.font = `500 11px Inter, sans-serif`, g.measureText(sub).width));
    for (const [x, y] of [[s.x + 16, s.y - 12], [s.x - 16 - w, s.y - 12], [s.x - w / 2, s.y - 40], [s.x - w / 2, s.y + 16]]) {
      const b = {x: x - 3, y: y - 3, w: w + 6, h: 32};
      if (b.x < 4 || b.x + b.w > W - 4 || b.y < 4 || b.y + b.h > H - 4 || boxes.some(o => b.x < o.x + o.w && o.x < b.x + b.w && b.y < o.y + o.h && o.y < b.y + b.h)) continue;
      boxes.push(b);
      g.strokeStyle = "rgba(250,249,246,.92)"; g.lineWidth = 4;
      g.font = `700 13px Inter, sans-serif`; g.strokeText(name, x, y + 12); g.fillStyle = "#0f172a"; g.fillText(name, x, y + 12);
      g.font = `500 11px Inter, sans-serif`; g.strokeText(sub, x, y + 26); g.fillStyle = s.col; g.fillText(sub, x, y + 26);
      break;
    }
  }
}
function glassLoop(){
  cancelAnimationFrame(G.raf);
  const step = t => {
    if (!G.active || document.hidden) return;
    if (t - G.last > 66) { G.last = t; glassPaint(); }
    G.raf = requestAnimationFrame(step);
  };
  G.raf = requestAnimationFrame(step);
}
document.addEventListener("visibilitychange", () => { if (!document.hidden) glassLoop(); });
addEventListener("resize", () => { G.sig = ""; glassCard(); });

/* The floating card: the plane overhead (or the one tapped on the map), with its photo; a tap opens its full card. While
   the fingers move the map it shrinks to a slim pill, out of the way. */
function glassCard(){
  const box = $("gCard");
  let o = G.sel ? radar.planes.find(p => p.ac.hex === G.sel) : feat && feat.o;
  if (G.sel && !o) { G.sel = ""; o = feat && feat.o; }
  for (const b of document.querySelectorAll("[data-gm]")) b.setAttribute("aria-pressed", String(airportMode() === (b.dataset.gm === "airport")));
  $("gDot").dataset.state = $("dot").dataset.state || "";
  box.classList.toggle("pill", Date.now() < G.pill);
  const near = radar.planes.filter(p => p.kind).length;
  const more = near > (o ? 1 : 0) ? `<button type="button" class="gMore" data-more>${escH(T(near === 1 ? "1 plane nearby" : "{n} planes nearby", {n: near}))} ›</button>` : "";
  if (!o) {
    const sig = "none|" + near + LANG;
    if (sig === G.sig) return;
    G.sig = sig;
    box.innerHTML = `<div class="gInfo"><b class="gFlight gNone">${escH(T(isOffline() ? "Offline" : "No plane overhead right now"))}</b>` +
      `<p class="gSub">${escH(statusLine())}</p>${more}</div>`;
    return glassWire(box, null);
  }
  const ac = o.ac, info = G.sel ? (infoCache.get(ac.hex + "|" + String(ac.flight || "").trim().toUpperCase()) || {}).info || baseInfo(ac) : feat.info || baseInfo(ac);
  lookupDetails(ac.hex);
  const d = detailsOf(ac.hex) || {}, word = G.sel ? (badgeFor(liveFacts(ac, info)) || radarStatus(o)) : featRemark(), col = radarColor(o);
  const pic = d.photo || modelPic([TYPES[String(ac.t || "").toUpperCase()], info.type, d.type], () => { G.sig = ""; glassCard(); });
  const flight = info.flightNo || String(ac.flight || "").trim() || ac.r || ac.hex.toUpperCase();
  const trend = o.rate == null ? "" : o.rate > 250 ? " ↑" : o.rate < -250 ? " ↓" : "";
  const alt = o.alt != null ? altitudeStr(o.alt).toLowerCase() + trend : "";
  const where = o.dist != null ? `${o.dist < 10 ? o.dist.toFixed(1) : Math.round(o.dist)} km ${o.dir || ""}` : "";
  const route = info.from && info.to ? `${code3(info.from) || ""} → ${code3(info.to) || ""}` : "";
  const sub = [info.airline || "", info.type || TYPES[String(ac.t || "").toUpperCase()] || ac.t, where].filter(Boolean).join(" · ");
  const sig = [ac.hex, word, alt, sub, route, pic, near, G.sel, LANG].join("|");
  if (sig === G.sig) return;
  G.sig = sig;
  box.style.setProperty("--c", col);
  box.innerHTML = (pic ? `<div class="gPhoto"><img src="${escH(pic)}" alt="" referrerpolicy="no-referrer">` +
      (isModelPic(pic) ? `<span class="gTag">${escH(T("Model photo · not this aircraft"))}</span>` : "") + `</div>` : "") +
    `<div class="gInfo"><span class="gStat"><i></i>${escH(T(word || ""))}</span>` +
    `<div class="gRow"><b class="gFlight">${escH(flight)}</b><span class="gAlt">${escH(alt)}</span></div>` +
    `<p class="gSub">${escH(sub)}</p>${route ? `<p class="gRoute">${escH(route)}</p>` : ""}${more}</div>` +
    (G.sel ? `<button type="button" class="gX" data-x aria-label="${escH(T("Close"))}">×</button>` : "");
  glassWire(box, o);
}
function glassWire(box, o){
  box.onclick = e => {
    if (e.target.closest("[data-x]")) { ctlSound.press(); G.sel = ""; G.sig = ""; return glassCard(); }
    if (e.target.closest("[data-more]")) { ctlSound.press(); return showTab("radar"); }
    if (o) planeCard(o);
  };
  box.onkeydown = e => { if ((e.key === "Enter" || e.key === " ") && o) { e.preventDefault(); planeCard(o); } };
}
setInterval(() => { if (G.active) glassCard(); }, 1000);

/* The fingers on the map: a tap on a plane puts it on the card (a tap elsewhere goes back to the plane overhead), a
   swipe across goes to Today (right) or the Logbook (left), a pinch zooms (and the card makes room), a double tap steps
   closer. */
(() => {
  const pts = new Map();
  let start = null, d0 = 0, r0 = 0, lastTap = 0;
  const dist = () => { const [a, b] = [...pts.values()]; return Math.hypot(a.x - b.x, a.y - b.y); };
  G.cv.style.touchAction = "none";
  G.cv.addEventListener("pointerdown", e => {
    pts.set(e.pointerId, {x: e.clientX, y: e.clientY});
    if (pts.size === 1) start = {x: e.clientX, y: e.clientY, t: Date.now()};
    if (pts.size === 2 && !(airportMode() && AP.lat == null)) {
      if (!radarZoomed() && airportMode()) radarZoomSet(radarBase());
      d0 = dist(); r0 = radarRange(); start = null;
    }
  });
  G.cv.addEventListener("pointermove", e => {
    if (!pts.has(e.pointerId)) return;
    pts.set(e.pointerId, {x: e.clientX, y: e.clientY});
    if (pts.size === 2 && d0) { radar.live = Math.max(RADAR_MIN, Math.min(radarBase(), r0 * d0 / Math.max(1, dist()))); G.pill = Date.now() + 1500; glassCard(); }
  });
  const end = e => {
    if (!pts.delete(e.pointerId)) return;
    if (d0) {
      if (pts.size) return;
      const v = radar.live || r0;
      d0 = 0; radar.live = 0;
      radarZoomSet(v >= radarBase() * .97 ? 0 : Math.round(v * 10) / 10);
      G.pill = Date.now() + 1200;
      return;
    }
    if (!start || e.type === "pointercancel") return;
    const dx = e.clientX - start.x, dy = e.clientY - start.y, quick = Date.now() - start.t < 600;
    start = null;
    if (quick && Math.abs(dx) > 70 && Math.abs(dy) < 50) { ctlSound.press(); return showTab(dx > 0 ? "today" : "logbook"); }
    if (Math.hypot(dx, dy) > 10) return;
    const hit = G.hits.reduce((a, h) => { const d = Math.hypot(h.x - e.clientX, h.y - e.clientY); return d < 28 && (!a || d < a.d) ? {o: h.o, d} : a; }, null);
    if (!hit && Date.now() - lastTap < 320) { lastTap = 0; return radarZoomTo(radarZoomCan(1) ? 1 : -9); }
    lastTap = Date.now();
    const sel = hit ? hit.o.ac.hex : "";
    if (sel === G.sel && !hit) return;
    ctlSound.press(); G.sel = hit && hit.o.ac.hex !== (feat && feat.o && feat.o.ac.hex) ? sel : ""; G.sig = ""; glassCard();
  };
  G.cv.addEventListener("pointerup", end); G.cv.addEventListener("pointercancel", end);
})();
setTimeout(() => { glassLabels(); glassCard(); glassLoop(); }, 0);
//@L:end
