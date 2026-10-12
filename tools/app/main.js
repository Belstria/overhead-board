(() => {
"use strict";
const $ = id => document.getElementById(id);
const escH = s => String(s ?? "").replace(/[&<>"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
//@E1

/* ---------- settings: kept on this phone only ---------- */
const DEFAULTS = {place:"Vienna", lat:48.2085, lon:16.3731, radiusKm:15, home:"VIE", maxAltFt:60000, units:"metric", sound:false, speedPct:85, refreshS:10,
  logos:true, overKm:3, demo:false, theme:"classic", favs:"", chimes:true, imperfect:true, airtimeMin:3, mode:"overhead", lang:"auto"};
const SKEY = "od.app.settings";
function loadSettings(){
  let saved = {};
  try { saved = JSON.parse(localStorage.getItem(SKEY) || "{}") || {}; } catch {}
  return {...DEFAULTS, ...saved};
}
function saveSettings(){
  const changed = {};
  for (const [k, v] of Object.entries(S)) if (k !== "proxy" && JSON.stringify(v) !== JSON.stringify(DEFAULTS[k])) changed[k] = v;
  try { localStorage.setItem(SKEY, JSON.stringify(changed)); } catch {}
}
Object.assign(DEFAULTS, window.OVERHEAD_DEFAULTS || {});  // location etc. supplied by the home relay
DEFAULTS.sound = false;                                    // a phone starts quiet; flap sound can be turned on in Settings
let S = loadSettings();
(() => { // a few of the board's address options work here too: ?lat=..&lon=..&radius=..&home=..&place=..&theme=..&demo
  const q = new URLSearchParams(location.search);
  const num = k => { const v = parseFloat(q.get(k)); return isFinite(v) ? v : null; };
  if (num("lat") != null) S.lat = num("lat");
  if (num("lon") != null) S.lon = num("lon");
  if (num("radius") != null) S.radiusKm = num("radius");
  if (num("over") != null) S.overKm = num("over");
  if (q.get("home")) S.home = q.get("home").toUpperCase();
  if (q.get("place")) S.place = q.get("place");
  if (q.get("units")) S.units = q.get("units") === "metric" ? "metric" : "aviation";
  if (q.get("proxy")) S.proxy = q.get("proxy");
  if (q.has("demo")) S.demo = q.get("demo") !== "0";
  if (q.get("theme") && THEMES[q.get("theme")]) S.theme = q.get("theme");
  if (q.get("favs")) S.favs = q.get("favs");
  if (q.get("lang")) S.lang = q.get("lang");
  if (q.get("mode")) S.mode = q.get("mode") === "airport" ? "airport" : "overhead";
})();

/* ---------- a small log, for the About plate in Settings ---------- */
const DIAG = {log: [], polls: [], closest: null};
function dlog(level, msg){
  DIAG.log.unshift({t: Date.now(), level, msg: String(msg)});
  if (DIAG.log.length > 200) DIAG.log.length = 200;
}
const scheduleDiag = () => {};
let nightOn = false;          // the board's night mode; a phone doesn't need it
//@E2
//@E33

/* ---------- split-flap panels ----------
   The flaps are drawn exactly as on the board, on canvases set into the page: the plane overhead, the clock, and the
   counters on Spotted today and the Logbook. Each panel is laid out in its own units and scaled to its width. */
const LITE = () => false;
const fields = {}, allCells = [], panels = [];
function makePanel(el, w, h, lab = 11){
  const P = {el, w, h, lab, px: 1, cssW: 0, ids: [], off: false};
  el.style.setProperty("--w", w); el.style.setProperty("--h", h);
  el.innerHTML = '<canvas aria-hidden="true"></canvas><canvas aria-hidden="true"></canvas>';
  [P.bg, P.fx] = el.querySelectorAll("canvas");
  P.bgx = P.bg.getContext("2d"); P.fxx = P.fx.getContext("2d");
  panels.push(P);
  return P;
}
function def(P, id, o){
  const f = fields[id] = {id, drum: DRUM_ALPHA, style: "ink", align: "left", loud: .7, panel: P, ...o};
  P.ids.push(id);
  const count = f.kind === "chars" ? f.n : 1;
  f.cells = [];
  for (let i = 0; i < count; i++) {
    const hsh = [...f.id].reduce((a, ch) => (a * 31 + ch.charCodeAt(0)) | 0, i * 977 + 13);
    const c = {f, i, cur: f.kind === "chars" ? " " : "", target: null, queue: [], anim: null, next: 0,
      variant: [...f.id].reduce((a, ch) => a + ch.charCodeAt(0), i * 7) % 3,
      jx: ((hsh & 255) / 255 - .5) * 2, jy: (((hsh >> 8) & 255) / 255 - .5) * 2};
    c.target = c.cur; f.cells.push(c); allCells.push(c);
  }
}
function placeRow(ids, gaps, y, step, ratio, x0){
  let x = x0;
  ids.forEach((id, i) => {
    const f = fields[id];
    f.x = x; f.y = y; f.step = step; f.cw = step * .9; f.ch = f.cw * ratio;
    f.wordW = f.n * step - (step - f.cw);
    x += f.n * step + (gaps[i] || 0) * step;
  });
}
// The plane overhead: the board's top half, in eight rows for a phone held upright and in four rows (like the board)
// on its side.
const UM = 14;                                   // margin, in panel units (the panel is 390 units wide)
const HERO = makePanel($("hero"), 390, 404, 10.5);
def(HERO, "flight",  {kind:"chars", n:7, dur:82, label:["Flight","Flug"], loud:1});
def(HERO, "remarks", {kind:"word",  n:6.3, dur:120, words:"remarks", label:["Status",""], loud:1});
def(HERO, "airline", {kind:"word",  n:13.93, dur:120, words:"airline", label:["Airline","Fluglinie"], loud:1});
def(HERO, "fromCode",{kind:"chars", n:3, dur:82, style:"amber", label:["From","Von"], loud:1});
def(HERO, "fromCity",{kind:"chars", n:10, dur:82, loud:1});
def(HERO, "toCode",  {kind:"chars", n:3, dur:82, style:"amber", label:["To","Nach"], loud:1});
def(HERO, "toCity",  {kind:"chars", n:10, dur:82, loud:1});
def(HERO, "type",    {kind:"chars", n:17, dur:66, label:["Aircraft","Flugzeug"]});
def(HERO, "reg",     {kind:"chars", n:7, dur:66, label:["Reg.","Kennz."]});
def(HERO, "alt",     {kind:"chars", n:9, dur:66, drum:DRUM_ALT, align:"right", label:["Altitude","Höhe"]});
def(HERO, "trend",   {kind:"word",  n:2, dur:110, words:"trend"});
def(HERO, "speed",   {kind:"chars", n:8, dur:66, drum:DRUM_ALT, align:"right", label:["Speed","Geschw."]});
def(HERO, "pos",     {kind:"chars", n:9, dur:66, drum:DRUM_POS, label:["Position",""]});
def(HERO, "depTime", {kind:"chars", n:5, dur:80, drum:DRUM_DIGIT, label:["Departure","Abflug"]});
def(HERO, "arrTime", {kind:"chars", n:5, dur:80, drum:DRUM_DIGIT, label:["Arrival","Ankunft"]});
def(HERO, "airTime", {kind:"chars", n:5, dur:80, drum:DRUM_DIGIT, label:["Flight time","Flugzeit"]});
const SIDEWAYS = window.matchMedia ? matchMedia("(orientation: landscape) and (max-height: 600px)") : {matches: false};
function heroLayout(){
  const wide = SIDEWAYS.matches;
  HERO.w = wide ? 560 : 390; HERO.h = wide ? 194 : 404;
  HERO.el.style.setProperty("--w", HERO.w); HERO.el.style.setProperty("--h", HERO.h);
  if (wide) {
    placeRow(["flight", "airline", "remarks"], [.6, .6], 18, 18.6, 1.45, UM);
    placeRow(["fromCode", "fromCity", "toCode", "toCity"], [.4, 1, .4], 66, 18.6, 1.45, UM);
    placeRow(["type", "reg", "alt", "trend"], [.5, .5, .3], 116, 14.4, 1.45, UM);
    placeRow(["speed", "pos", "depTime", "arrTime", "airTime"], [.6, 1, 1, 1], 160, 14.4, 1.45, UM);
    return;
  }
  placeRow(["flight", "remarks"], [.6], 18, 26, 1.45, UM);
  placeRow(["airline"], [], 71, 26, 1.45, UM);
  placeRow(["fromCode", "fromCity"], [.4], 124, 27, 1.45, UM);
  placeRow(["toCode", "toCity"], [.4], 178, 27, 1.45, UM);
  placeRow(["type"], [], 232, 21.4, 1.45, UM);
  placeRow(["reg", "alt", "trend"], [.5, .3], 279, 19.36, 1.45, UM);
  placeRow(["speed", "pos"], [.6], 323, 19.36, 1.45, UM);
  placeRow(["depTime", "arrTime", "airTime"], [1.3, 1.3], 367, 19.36, 1.45, UM);
}
heroLayout();
const CLOCK = makePanel($("clockP"), 112, 34);
def(CLOCK, "clock", {kind:"chars", n:5, drum:DRUM_DIGIT, dur:95, loud:.8});
placeRow(["clock"], [], 4, 22.4, 1.25, 1);
// Spotted today: today's numbers on flaps.
const TODAYP = makePanel($("todayP"), 390, 52);
def(TODAYP, "stPlanes",   {kind:"chars", n:4, dur:70, drum:DRUM_DIGIT, align:"right", label:["Planes","Flüge"]});
def(TODAYP, "stAirlines", {kind:"chars", n:3, dur:70, drum:DRUM_DIGIT, align:"right", label:["Airlines",""]});
def(TODAYP, "stTypes",    {kind:"chars", n:3, dur:70, drum:DRUM_DIGIT, align:"right", label:["Types","Typen"]});
def(TODAYP, "stOver",     {kind:"chars", n:3, dur:70, drum:DRUM_DIGIT, align:"right", label:["Overhead",""]});
placeRow(["stPlanes", "stAirlines", "stTypes", "stOver"], [1.3, 1.3, 1.3], 18, 21.5, 1.3, UM);
// Logbook totals.
const LBP = makePanel($("lbP"), 390, 108);
def(LBP, "lvSight",    {kind:"chars", n:7, drum:DRUM_ALT, align:"right", dur:70, label:["Sightings","Sichtungen"]});
def(LBP, "lvRegs",     {kind:"chars", n:7, drum:DRUM_ALT, align:"right", dur:70, label:["Individual aircraft",""]});
def(LBP, "lvTypes",    {kind:"chars", n:4, drum:DRUM_ALT, align:"right", dur:70, label:["Aircraft types","Typen"]});
def(LBP, "lvAirlines", {kind:"chars", n:4, drum:DRUM_ALT, align:"right", dur:70, label:["Airlines",""]});
placeRow(["lvSight", "lvRegs"], [1.5], 18, 22, 1.3, UM);
placeRow(["lvTypes", "lvAirlines"], [4.5], 69, 22, 1.3, UM);
//@E3
/* ---------- drawing a flap, mid-flip or at rest ---------- */
function drawCell(c, p){
  const f = c.f, P = f.panel;
  if (f.hidden || P.off || !P.cssW) return;
  paintCell(P.fxx, c, p, false);
}
//@E4
function redrawAll(){
  for (const P of panels) {
    if (P.off || !P.cssW) continue;
    P.fxx.clearRect(0, 0, P.fx.width, P.fx.height);
    for (const id of P.ids) for (const c of fields[id].cells) drawCell(c, c.anim ? .0001 : null);
  }
}
//@E5
// Panel geometry in device pixels, worked out when a panel is shown (a hidden one has no size).
function sizePanel(P){
  const css = P.el.clientWidth;
  if (!css) return false;
  const dpr = window.devicePixelRatio || 1;
  P.cssW = css; P.px = Math.min(3, css / P.w * dpr);
  P.bg.width = P.fx.width = Math.round(P.w * P.px);
  P.bg.height = P.fx.height = Math.round(P.h * P.px);
  for (const id of P.ids) {
    const f = fields[id];
    f.pw = Math.round((f.kind === "chars" ? f.cw : f.wordW) * P.px);
    f.ph = Math.round(f.ch * P.px);
    const wear = S.imperfect ? Math.min(f.pw, f.ph) : 0;           // worn modules sit a hair out of line
    f.cells.forEach((c, i) => {
      c.x = Math.round((f.x + i * f.step) * P.px + c.jx * wear * .02);
      c.y = Math.round(f.y * P.px + c.jy * wear * .028);
    });
  }
  return true;
}
function showPanel(P){
  if (P.off) return;
  if (P.el.clientWidth !== P.cssW && !sizePanel(P)) return;
  drawPanelStatic(P);
  P.fxx.clearRect(0, 0, P.fx.width, P.fx.height);
  for (const id of P.ids) for (const c of fields[id].cells) drawCell(c, c.anim ? .0001 : null);
}
function refreshPanels(force){
  if (force) for (const P of panels) P.cssW = 0;
  for (const P of panels) showPanel(P);
}
//@E6
//@E8
// The panel itself: a recessed channel for each row of flaps, each module casting a shadow, and the engraved labels.
function drawPanelStatic(P){
  const g = P.bgx;
  g.setTransform(1, 0, 0, 1, 0, 0); g.clearRect(0, 0, P.bg.width, P.bg.height);
  g.setTransform(P.px, 0, 0, P.px, 0, 0);
  for (const id of P.ids) {
    const f = fields[id];
    if (f.hidden || f.cw == null) continue;
    const pad = Math.max(2, f.step * .11), wide = f.kind === "chars" ? (f.n - 1) * f.step + f.cw : f.wordW;
    const x = f.x - pad, y = f.y - pad, w = wide + pad * 2, h = f.ch + pad * 2;
    g.fillStyle = "#060607"; rr(g, x, y, w, h, pad * .8); g.fill();
    const inset = g.createLinearGradient(0, y, 0, y + h);
    inset.addColorStop(0, "rgba(0,0,0,.8)"); inset.addColorStop(.15, "rgba(0,0,0,0)"); inset.addColorStop(.9, "rgba(255,255,255,0)"); inset.addColorStop(1, "rgba(255,255,255,.06)");
    g.fillStyle = inset; rr(g, x, y, w, h, pad * .8); g.fill();
    const cells = f.kind === "chars" ? f.n : 1;
    const sw = Math.round(((f.kind === "chars" ? f.cw : f.wordW) - 2) * P.px), sh = Math.round((f.ch - 2) * P.px);
    const sp = slotShadow(sw, sh, Math.round(f.ch * .12 * P.px), Math.round(f.ch * .05 * P.px));
    g.save(); g.setTransform(1, 0, 0, 1, 0, 0);
    for (let i = 0; i < cells; i++) g.drawImage(sp.cv, Math.round((f.x + i * f.step + 1) * P.px) - sp.pad, Math.round((f.y + 1) * P.px) - sp.pad);
    g.restore();
  }
  const labelled = P.ids.map(id => fields[id]).filter(f => f.label && !f.hidden);
  for (const f of labelled) {         // each label may run up to the next one on its row (narrower if a font is wider)
    const next = labelled.filter(o => o.y === f.y && o.x > f.x).reduce((m, o) => Math.min(m, o.x), P.w - 4);
    label(g, f, f.label[0], f.label[1], P.lab, next - f.x - P.lab * .6);
  }
}
function label(g, f, main, second, size, max = Infinity){
  const yb = f.y - Math.max(4, size * .5), a = T(main).toUpperCase(), b = second && UNIT.test(second) ? second.toUpperCase() : "";   // units only
  g.font = `600 ${size}px ${FONT}`; g.textBaseline = "alphabetic"; g.textAlign = "left";
  if ("letterSpacing" in g) g.letterSpacing = (size * .08).toFixed(1) + "px";
  const wa = g.measureText(a).width, gap = size * .7, total = wa + (b ? gap + g.measureText(b).width : 0);
  g.save(); g.translate(f.x, yb);
  if (total > max) g.scale(Math.max(.6, max / total), 1);
  g.fillStyle = COL.amber; g.fillText(a, 0, 0);
  if (b) { g.fillStyle = COL.labelEn; g.fillText(b, wa + gap, 0); }
  g.restore();
  if ("letterSpacing" in g) g.letterSpacing = "0px";
}
//@E9
/* ---------- the metal: brushed, a little worn, as a tile the page is painted with ---------- */
let metalUrl = "";
function metalTile(){
  const T = 600, d = Math.min(2, window.devicePixelRatio || 1), cv = document.createElement("canvas");
  cv.width = cv.height = Math.round(T * d);
  const g = cv.getContext("2d");
  g.scale(d, d);
  g.fillStyle = METAL[1]; g.fillRect(0, 0, T, T);
  const rnd = (seed => () => (seed = (seed * 1103515245 + 12345) & 0x7fffffff) / 0x7fffffff)(1234567);
  g.lineWidth = .7;                                         // brushed grain, wrapping round the tile's edges
  for (let i = 0; i < 700; i++) {
    const y = 1 + rnd() * (T - 2), x = rnd() * T, len = 60 + rnd() * 380, light = rnd() < .5;
    g.strokeStyle = light ? `rgba(255,255,255,${.012 + rnd() * .03})` : `rgba(0,0,0,${.03 + rnd() * .06})`;
    for (const dx of [0, -T]) { g.beginPath(); g.moveTo(x + dx, y); g.lineTo(x + dx + len, y); g.stroke(); }
  }
  if (S.imperfect) {
    for (let i = 0; i < 6; i++) {                           // dull polish marks
      const x = 120 + rnd() * (T - 240), y = 120 + rnd() * (T - 240), r = 50 + rnd() * 60;
      const pg = g.createRadialGradient(x, y, 0, x, y, r);
      pg.addColorStop(0, `rgba(255,255,255,${.01 + rnd() * .012})`); pg.addColorStop(1, "rgba(255,255,255,0)");
      g.fillStyle = pg; g.fillRect(x - r, y - r, r * 2, r * 2);
    }
    for (let i = 0; i < 16; i++) {                          // fine scratches
      const x = 40 + rnd() * (T - 80), y = 40 + rnd() * (T - 80), ang = rnd() * Math.PI * 2, len = 10 + rnd() * 30, a = .04 + rnd() * .06;
      const ex = x + Math.cos(ang) * len, ey = y + Math.sin(ang) * len;
      g.lineCap = "round";
      g.lineWidth = .9; g.strokeStyle = `rgba(0,0,0,${a * .9})`; g.beginPath(); g.moveTo(x, y + .8); g.lineTo(ex, ey + .8); g.stroke();
      g.lineWidth = .6; g.strokeStyle = `rgba(235,238,245,${a})`; g.beginPath(); g.moveTo(x, y); g.lineTo(ex, ey); g.stroke();
    }
  }
  cv.toBlob(b => {
    if (!b) return;
    if (metalUrl) URL.revokeObjectURL(metalUrl);
    metalUrl = URL.createObjectURL(b);
    document.documentElement.style.setProperty("--metal-img", `url(${metalUrl})`);
  });
}
function drawMark(){
  const cv = $("mark"), d = window.devicePixelRatio || 1, s = 40;
  cv.width = cv.height = Math.round(s * d);
  const g = cv.getContext("2d");
  g.setTransform(d, 0, 0, d, 0, 0);
  pictogram(g, 0, 0, s);
}
//@E10

/* ---------- board styles ---------- */
function applyTheme(){
  const T = THEMES[S.theme] || THEMES.classic;
  FONT = T.font; FLAP.splice(0, 4, ...T.flap); METAL = T.metal;
  COL.ink = T.ink; COL.amber = T.accent; COL.labelEn = T.label2;
  const root = document.documentElement.style;
  root.setProperty("--f-board", T.font); root.setProperty("--amber", T.accent); root.setProperty("--ink", T.ink);
  root.setProperty("--label2", T.label2); root.setProperty("--metal", T.metal[1]);
  const tc = document.querySelector('meta[name="theme-color"]');
  if (tc) tc.content = T.metal[1];
  metalTile();
  const redraw = () => { clearTiles(); refreshPanels(true); drawMark(); if (tab === "radar") radarSize(); };
  try {
    Promise.race([Promise.all(["700 40px", "600 20px", "400 40px"].map(w => document.fonts.load(`${w} ${T.font}`))), new Promise(r => setTimeout(r, 2500))])
      .then(redraw, redraw);
  } catch { redraw(); }
}
//@E11
//@E12
//@E13

/* ---------- Spotted today: the relay records every sighting; the app mirrors its list ---------- */
//@E14
let spotted = [], logDay = todayKey();
function rollDay(){
  if (logDay === todayKey()) return;
  logDay = todayKey();
  if (relayV5()) { sightRev = null; fullDay = {at: 0, rev: null, date: null, list: null}; syncSightings(); return; }
  spotted = S.demo ? demoLog() : []; renderLists();
}
//@E15
async function syncSightings(){
  if (sightBusy || !relayV5()) return;
  sightBusy = true;
  try {
    const j = await fetchJSON(`${relay()}/sightings?over=${overKm()}${apiOn() ? "&api=1" : ""}`, {}, 8000);
    if (apiOn() && j.fr24 === false) { apiLive = false; dlog("warn", "Flightradar24 isn't available on the relay right now; using the free sources"); }
    const first = sightRev === null;
    spotted = (j.entries || []).map(fromRelay);
    relayStats = j.stats || null;
    sightRev = String(j.rev); sightDay = j.date || null;
    if (first) dlog("info", `Spotted today comes from the relay (${spotted.length} so far)`);
    renderLists(); updateFooter();
  } catch (e) { dlog("warn", `Couldn't read Spotted today from the relay: ${netError(e, "relay")}`); }
  finally { sightBusy = false; }
}
// The regular sync has the newest 400; the Spotted today tab asks the relay for the whole day.
let fullDay = {at: 0, rev: null, date: null, list: null};
async function loadFullDay(){
  const now = Date.now();
  if (!relayV5() || fullDay.busy || now - fullDay.at < 15000 || (fullDay.list && fullDay.rev === sightRev)) return;
  fullDay.busy = true; fullDay.at = now;
  try {
    const j = await fetchJSON(`${relay()}/sightings?all=1&over=${overKm()}${apiOn() ? "&api=1" : ""}`, {}, 20000);
    fullDay = {at: now, rev: String(j.rev), date: j.date || null, list: (j.entries || []).map(fromRelay)};
    if (j.stats) relayStats = j.stats;
    renderToday();
  } catch (e) { dlog("warn", `Couldn't read the whole day from the relay: ${netError(e, "relay")}`); }
  finally { fullDay.busy = false; }
}
function dayList(){
  if (!relayV5() || !fullDay.list || fullDay.date !== sightDay) return spotted;
  const ids = new Set(spotted.map(e => e.id));
  return spotted.concat(fullDay.list.filter(e => !ids.has(e.id)));
}
//@E16
//@E17
function setFeat(o, mode, alert = false){
  const now = Date.now();
  if (!feat || feat.hex !== o.ac.hex) {
    const p = enrich(o.ac);
    const h = feat = {hex: o.ac.hex, since: now, logged: false, info: p.info};
    p.then(info => { h.info = info; if (feat === h) { renderFeatured(); renderAircraftInfo(); } });
  }
  if (feat.mode !== mode) dlog("info", `Board: ${planeName(feat, o.ac)} · ${MODE_REMARK[mode]} · ${o.dist.toFixed(1)} km`);
  feat.o = o; feat.mode = mode;
  if (mode === "over" || mode === "soon") feat.lastSeen = now;
  if (alert && !feat.alert) {
    feat.alert = true;
    dlog("info", `${planeName(feat, o.ac)} rang the bell`);
    if (tab !== "now") pingNow(true);
  } else if (!alert) feat.alert = false;
}
//@E18
//@E19
//@E20
//@E21
//@E22
//@E23
let lbCache = null, lbError = "";
//@E24
const API_NOTE = () => apiOn() ? " · flight numbers and routes from Flightradar24" : "";
//@E25
//@E26

/* ---------- what the lists look like ---------- */
const PLANE_SVG = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M21 16v-2l-8-5V3.5c0-.83-.67-1.5-1.5-1.5S10 2.67 10 3.5V9l-8 5v2l8-2.5V19l-2 1.5V22l3.5-1 3.5 1v-1.5L13 19v-5.5l8 2.5z"/></svg>';
function chip(r){                        // the status word in this language; its colours by the English name
  const L = REMARK_LOOK[r] || {};
  const bg = L.fill ? `background:linear-gradient(${L.fill[0]},${L.fill[1]});` : "";
  const icon = AP_ICON[r] ? `<i class="apic ${AP_ICON[r]}">${PLANE_SVG}</i>` : "";        // taking off or landing, as on the flaps
  return `<span class="chip" style="${bg}color:${L.fg || "var(--ink)"}">${icon}${escH(T(r))}</span>`;
}
const distText = d => d == null ? "" : (+d < 10 ? (+d).toFixed(1) : String(Math.round(d))) + " km";
const altText = ft => typeof ft === "number" ? altNum(ft) + (S.units === "metric" ? " m" : " ft") : "";
function placeHtml(a){
  if (!a) return `<span class="no">–</span>`;
  const c = code3(a) || a.code || "";
  return `${c ? `<b>${escH(c)}</b>` : ""}${escH(a.city || "")}`;
}
function rowHtml(e){
  const r = remarkFor(e), col = badgeFor(e) ? lampOf(r) : "";
  const style = col ? ` style="--lamp:${col};background:${rgba(col, .11)}"` : "";
  const meta = [e.type, e.reg].filter(Boolean).map(escH).join(" · ");
  const near = [distText(e.minDist), altText(e.altAtMin)].filter(Boolean).join(" · ");
  return `<li class="fl${col ? " sp" : ""}"${style}><time>${escH(e.time || "")}</time>` +
    `<div class="who"><strong>${escH(e.flight || String(e.hex || "").toUpperCase())}</strong>${e.airline ? `<span>${escH(e.airline)}</span>` : ""}</div>` +
    `${r ? chip(r) : "<span></span>"}${e.from || e.to ? `<div class="rt">${placeHtml(e.from)}<i>→</i>${placeHtml(e.to)}</div>` : ""}` +
    `<div class="meta"><span>${meta}</span><span>${near}</span></div></li>`;
}
const rowSig = e => [e.id || e.hex, e.time, e.flight, e.airline, e.type, e.reg, code3(e.from), code3(e.to), e.minDist, e.altAtMin, remarkFor(e)].join("|");

/* Now: the plane overhead on flaps, its photo and details, and the latest sightings. */
let recentSig = "";
function renderRecent(){
  const list = dayList().filter(e => !e.sample || S.demo).slice(0, 8);
  const sig = list.map(rowSig).join("~") + S.units;
  if (sig === recentSig) return;
  recentSig = sig;
  $("recent").innerHTML = list.length ? list.map(rowHtml).join("")
    : `<li class="empty">${escH(T("Nothing spotted yet today. Every plane that comes within {n} km is listed here.", {n: +S.radiusKm || 15}))}</li>`;
}
let shownPhoto = null, factsSig = "";
function renderAircraftInfo(){
  $("acSec").hidden = !feat;
  if (!feat) return;
  const info = feat.info || baseInfo(feat.o.ac), d = detailsOf(feat.hex) || {};
  const src = d.photo || "";
  if (src !== shownPhoto) {
    shownPhoto = src;
    const scr = $("screen"), img = $("photo");
    scr.classList.remove("on", "has");
    if (src) {
      img.onload = () => {
        if (img.getAttribute("src") !== src) return;
        scr.classList.add("has");
        if (!REDUCED) { void scr.offsetWidth; scr.classList.add("on"); }
      };
      img.onerror = () => scr.classList.remove("has");
      img.src = src;
    } else img.removeAttribute("src");
  }
  const route = info.from && info.to ? `${code3(info.from) || info.from.code} → ${code3(info.to) || info.to.code}` : "";
  const facts = [["Registration", "Kennzeichen", info.reg || d.reg], ["Mode S", "", feat.hex.toUpperCase()],
    ["Aircraft", "Flugzeug", d.type || info.type, true], ["Operator", "Betreiber", d.owner || info.airline, true],
    ["Registered in", "Land", d.country], ["Route", "", route]].filter(f => f[2]);
  const sig = JSON.stringify(facts);
  if (sig === factsSig) return;
  factsSig = sig;
  $("acFacts").innerHTML = facts.map(([en, de, v, wide]) => `<div${wide ? ' class="wide"' : ""}><dt>${escH(T(en))}</dt><dd>${escH(v)}</dd></div>`).join("");
}

/* Spotted today */
let svFilter = "all", svSig = "";
function svData(){
  const real = dayList().filter(e => !e.sample || S.demo), OVK = overKm();
  const isOver = e => e.minDist != null && e.minDist <= OVK, isSpecial = e => !!badgeFor(e);
  const counts = {all: real.length, over: real.filter(isOver).length, special: real.filter(isSpecial).length};
  const rows = real.filter(svFilter === "over" ? isOver : svFilter === "special" ? isSpecial : () => true);
  return {real, rows, counts};
}
//@E27
const SV_TOOLS = [["all", "All"], ["over", "Overhead"], ["special", "Special"]];
function buildSvTools(){
  const box = $("svTools");
  box.innerHTML = SV_TOOLS.map(([k, t]) => `<button class="cap small" type="button" data-t="${k}" aria-pressed="false">${T(t)}</button>`).join("");
  for (const b of box.children) b.onclick = () => {
    ctlSound.press();
    const k = b.dataset.t;
    svFilter = k;
    svSig = ""; renderToday();
  };
}
function legendHtml(){
  return legendGroups().map(([h, items]) => `<h3>${escH(h)}</h3><ul class="legend">` +
    items.map(([r, t]) => `<li>${chip(r)}<span>${escH(t)}</span></li>`).join("") + "</ul>").join("") +
    `<p class="sum">${escH(T("A plane can be more than one of these; the board shows the most special one, in the order listed. Arriving, Departing and Overflight only show in the lists."))}</p>`;
}
function todayNumbers(){
  const st = relayV5() && relayStats, list = dayList(), OVK = overKm();
  if (st) {
    const name = x => x ? fromRelay(x).flight : "";
    const t = st.topAirline, tn = t ? shortAirline(t.name || (AIRLINES[t.code] || [])[1] || t.code) : "";
    return {planes: st.planes, airlines: st.airlines, types: st.types, over: st.overhead, facts: [
      ["Busiest hour", "Meiste Flüge", st.busiestHour != null ? `${String(st.busiestHour).padStart(2, "0")}:00` : ""],
      ["First of the day", "Erster", st.first ? `${st.first.time} ${name(st.first)}` : ""],
      ["Lowest pass", "Tiefster", st.lowest ? `${name(st.lowest)} · ${altText(st.lowest.altAtMin)}` : ""],
      ["Highest pass", "Höchster", st.highest ? `${name(st.highest)} · ${altText(st.highest.altAtMin)}` : ""],
      ["Fastest", "Schnellster", st.fastest ? `${name(st.fastest)} · ${speedStr(st.fastest.maxSpeed).toLowerCase()}` : ""],
      ["Most seen airline", "", t ? `${tn} · ${t.count}` : ""],
      ["New in the logbook", "Neu", st.newTypes || st.newAirlines ? T("{a} types · {b} airlines", {a: st.newTypes, b: st.newAirlines}) : T("Nothing new yet")]]};
  }
  const uniq = fn => new Set(list.map(fn).filter(Boolean)).size;
  const withAlt = list.filter(e => typeof e.altAtMin === "number");
  const low = withAlt.reduce((a, e) => !a || e.altAtMin < a.altAtMin ? e : a, null);
  const high = withAlt.reduce((a, e) => !a || e.altAtMin > a.altAtMin ? e : a, null);
  const first = list[list.length - 1];
  return {planes: list.length, airlines: uniq(e => e.airlineCode || clean(e.airline)), types: uniq(e => e.typeCode || clean(e.type)),
    over: list.filter(e => e.minDist != null && e.minDist <= OVK).length, facts: [
      ["First of the day", "Erster", first ? `${first.time} ${first.flight}` : ""],
      ["Lowest pass", "Tiefster", low ? `${low.flight} · ${altText(low.altAtMin)}` : ""],
      ["Highest pass", "Höchster", high ? `${high.flight} · ${altText(high.altAtMin)}` : ""]]};
}
let todayFactsSig = "";
function renderTodayNumbers(){
  const n = todayNumbers();
  setChars("stPlanes", String(n.planes)); setChars("stAirlines", String(n.airlines), 60);
  setChars("stTypes", String(n.types), 120); setChars("stOver", String(n.over), 180);
  const html = n.facts.filter(f => f[2]).map(([en, de, v]) => `<div><dt>${escH(T(en))}</dt><dd>${escH(v)}</dd></div>`).join("");
  if (html !== todayFactsSig) { todayFactsSig = html; $("todayFacts").innerHTML = html; }
}
function renderToday(){
  if (tab !== "today") return;
  loadFullDay();
  renderTodayNumbers();
  const d = svData();
  for (const b of $("svTools").children) {
    const k = b.dataset.t, n = d.counts[k];
    const text = `${T(SV_TOOLS.find(t => t[0] === k)[1])}${n != null ? " " + nf.format(n) : ""}`;
    if (b.textContent !== text) b.textContent = text;
    b.setAttribute("aria-pressed", String(k === svFilter));
  }
  $("svSum").textContent = spottedSummary();
  const sig = svFilter + S.units + d.rows.map(rowSig).join("~");
  if (sig === svSig) return;
  svSig = sig;
  $("svList").innerHTML = d.rows.length ? d.rows.map(rowHtml).join("")
    : `<li class="empty">${svFilter === "all" ? T("Nothing spotted yet today.") : T("None of today's planes match this filter yet.")}</li>`;
}
function renderLists(){
  renderRecent();
  if (tab === "today") renderToday();
}

/* Logbook */
//@E28
async function fetchLogbook(){
  if (!S.demo && relayV5()) {
    try { lbCache = await fetchJSON(`${relay()}/logbook`, {}, 8000); lbError = ""; }
    catch (e) { lbError = netError(e, "relay"); }
  }
  renderLogbook();
}
let lbSig = "";
function renderLogbook(){
  if (tab !== "logbook") return;
  $("lbSum").textContent = logbookSummary();
  const b = lbData() || {}, has = !!lbData();
  const byCount = o => Object.entries(o || {}).sort((x, y) => (y[1].count || 0) - (x[1].count || 0));
  const types = byCount(b.types), airlines = byCount(b.airlines);
  setChars("lvSight", has ? nf.format(b.sightings || 0) : "");
  setChars("lvRegs", has ? nf.format(b.regsCount || 0) : "", 60);
  setChars("lvTypes", has ? nf.format(types.length) : "", 120);
  setChars("lvAirlines", has ? nf.format(airlines.length) : "", 180);
  const sig = JSON.stringify([b.since, b.sightings, b.categories, types.slice(0, 10), airlines.slice(0, 10), b.regsTop, b.regsRecent]);
  if (sig === lbSig) return;
  lbSig = sig;
  $("lbModel").innerHTML = types[0] ? `<small>${escH(T("Most seen model"))}</small>${escH(typeLabel(types[0][0], types[0][1].name))}<span>${escH(T("{n} times", {n: nf.format(types[0][1].count || 0)}))}</span>` : "";
  const rank = (items, plain) => `<ol class="ranks${plain ? " plain" : ""}">${items.join("")}</ol>`;
  const li = (name, n, sub) => `<li><span class="name">${escH(name)}${sub ? `<span class="s">${escH(sub)}</span>` : ""}</span><span class="n">${escH(n)}</span></li>`;
  let html = "";
  if (b.categories) {
    const max = Math.max(1, ...LB_CATS.map(([k]) => b.categories[k] || 0));
    html += `<h3>${escH(T("Categories"))}</h3><ul class="ranks cats">` + LB_CATS.map(([k, en, de, col]) => {
      const n = b.categories[k] || 0;
      return `<li style="--lamp:${col}"><i class="lamp"></i><span class="name">${escH(T(en))}</span><span class="n">${nf.format(n)}</span>` +
        `<span class="bar"><i style="width:${(n / max * 100).toFixed(1)}%"></i></span></li>`;
    }).join("") + "</ul>";
  }
  if (types.length) html += `<h3>${escH(T("Aircraft types"))}</h3>` + rank(types.slice(0, 10).map(([c, t]) => li(typeLabel(c, t.name), nf.format(t.count || 0))));
  if (airlines.length) html += `<h3>${escH(T("Airlines"))}</h3>` + rank(airlines.slice(0, 10).map(([c, a]) => li((AIRLINES[c] || [])[1] || a.name || c, nf.format(a.count || 0))));
  if ((b.regsTop || []).length) html += `<h3>${escH(T("Most seen aircraft"))}</h3>` + rank(b.regsTop.slice(0, 8).map(r => li(r.reg, nf.format(r.count || 0), r.name)));
  if ((b.regsRecent || []).length) html += `<h3>${escH(T("Newest aircraft"))}</h3>` + rank(b.regsRecent.slice(0, 8).map(r => li(r.reg, fmtDay(r.first), r.name)), true);
  $("lbLists").innerHTML = html;
}

/* Radar: the board's instrument, sized to the phone. North up; the nearest planes listed below it. */
const RG = {S: 400, cx: 200, cy: 200, R: 172};
function radarSize(){
  const css = $("scope").clientWidth;
  if (!css) return;
  radar.px = Math.min(3, css / RG.S * (window.devicePixelRatio || 1));
  for (const cv of [$("radarBg"), $("radarCv")]) cv.width = cv.height = Math.round(RG.S * radar.px);
  radarStatic();
}
function radarStatic(){
  const g = $("radarBg").getContext("2d"), {cx, cy, R} = RG, TAU = Math.PI * 2;
  g.setTransform(1, 0, 0, 1, 0, 0); g.clearRect(0, 0, g.canvas.width, g.canvas.height);
  g.setTransform(radar.px, 0, 0, radar.px, 0, 0);
  g.save();
  g.shadowColor = "rgba(0,0,0,.7)"; g.shadowBlur = 12 * radar.px; g.shadowOffsetY = 4 * radar.px;
  const ring = g.createLinearGradient(0, cy - R - 22, 0, cy + R + 22);
  ring.addColorStop(0, "#303135"); ring.addColorStop(.5, "#1d1e21"); ring.addColorStop(1, "#141517");
  g.fillStyle = ring; g.beginPath(); g.arc(cx, cy, R + 22, 0, TAU); g.fill();
  g.restore();
  g.strokeStyle = "rgba(255,255,255,.1)"; g.lineWidth = 1.2; g.beginPath(); g.arc(cx, cy, R + 21, Math.PI * 1.1, Math.PI * 1.9); g.stroke();
  g.fillStyle = "#050607"; g.beginPath(); g.arc(cx, cy, R + 3, 0, TAU); g.fill();
  const scope = g.createRadialGradient(cx, cy, 0, cx, cy, R);
  scope.addColorStop(0, "#15191b"); scope.addColorStop(1, "#090b0c");
  g.fillStyle = scope; g.beginPath(); g.arc(cx, cy, R, 0, TAU); g.fill();
  for (let i = 0; i < 8; i++) { const a = i / 8 * TAU + Math.PI / 8; screw(g, cx + Math.cos(a) * (R + 12), cy + Math.sin(a) * (R + 12), 3.2); }
}
function startRadar(){
  radarSize();
  const loop = t => {
    if (tab !== "radar") return;
    if (t - radar.last > 66) { radar.last = t; drawRadar(t); }
    radar.raf = requestAnimationFrame(loop);
  };
  cancelAnimationFrame(radar.raf); radar.raf = requestAnimationFrame(loop);
}
function stopRadar(){ cancelAnimationFrame(radar.raf); }
function drawRadar(t){
  const g = $("radarCv").getContext("2d"), now = Date.now(), {cx, cy, R} = RG, range = radarRange(), k = R / range, TAU = Math.PI * 2;
  g.setTransform(radar.px, 0, 0, radar.px, 0, 0); g.clearRect(0, 0, RG.S, RG.S);
  const kx = 111.32 * Math.cos(S.lat * Math.PI / 180), ky = 110.57;
  const toXY = (lat, lon) => [cx + (lon - S.lon) * kx * k, cy - (lat - S.lat) * ky * k];
  g.save(); g.beginPath(); g.arc(cx, cy, R, 0, TAU); g.clip();
  const a0 = (t / 7000) * TAU;                                  // slow sweep
  for (let i = 0; i < 28; i++) {
    g.fillStyle = rgba(COL.amber, .075 * (1 - i / 28));
    g.beginPath(); g.moveTo(cx, cy); g.arc(cx, cy, R, a0 - (i + 1) * .028 - Math.PI / 2, a0 - i * .028 - Math.PI / 2); g.closePath(); g.fill();
  }
  g.fillStyle = rgba(RADAR_COL.over, .12); g.beginPath(); g.arc(cx, cy, overKm() * k, 0, TAU); g.fill();
  g.strokeStyle = "rgba(255,255,255,.06)"; g.lineWidth = 1;
  g.beginPath(); g.moveTo(cx - R, cy); g.lineTo(cx + R, cy); g.moveTo(cx, cy - R); g.lineTo(cx, cy + R); g.stroke();
  g.font = `600 10.5px ${FONT}`; g.textAlign = "left"; g.textBaseline = "alphabetic";
  for (let r = 5; r <= range; r += 5) {
    g.strokeStyle = "rgba(255,255,255,.1)"; g.lineWidth = 1; g.beginPath(); g.arc(cx, cy, r * k, 0, TAU); g.stroke();
    g.fillStyle = "rgba(255,255,255,.32)"; g.fillText(`${r} km`, cx + Math.sin(.42) * r * k + 4, cy - Math.cos(.42) * r * k + 11);
  }
  g.setLineDash([8, 6]); g.strokeStyle = rgba(COL.amber, .6); g.lineWidth = 1.5;
  g.beginPath(); g.arc(cx, cy, (+S.radiusKm || 15) * k, 0, TAU); g.stroke(); g.setLineDash([]);
  const ap = AIRPORTS[S.home];
  if (ap && ap.strips) {
    g.strokeStyle = "rgba(255,255,255,.55)"; g.lineCap = "round"; g.lineWidth = 3.5;
    for (const [la1, lo1, la2, lo2] of ap.strips) { const [x1, y1] = toXY(la1, lo1), [x2, y2] = toXY(la2, lo2); g.beginPath(); g.moveTo(x1, y1); g.lineTo(x2, y2); g.stroke(); }
    const [ax, ay] = toXY(ap.lat, ap.lon);
    g.font = `700 12px ${FONT}`; g.fillStyle = "rgba(255,255,255,.6)"; g.fillText(S.home, ax + 12, ay + 18); g.lineCap = "butt";
  }
  const dt = Math.min(20, (now - radar.at) / 1000), shown = [];
  for (const o of radar.planes) {
    const ac = o.ac, v = (ac.gs || 0) * 1.852 / 3600 * dt, th = (ac.track || 0) * Math.PI / 180;
    const lat = ac.lat + v * Math.cos(th) / ky, lon = ac.lon + v * Math.sin(th) / kx;
    const [x, y] = toXY(lat, lon);
    if (Math.hypot(x - cx, y - cy) > R + 8) continue;
    const col = radarColor(o), tr = radar.trails.get(ac.hex);
    if (tr && tr.length > 1) {
      g.strokeStyle = rgba(col, .35); g.lineWidth = 1.8; g.beginPath();
      tr.forEach((p, i) => { const [px, py] = toXY(p.lat, p.lon); i ? g.lineTo(px, py) : g.moveTo(px, py); });
      g.lineTo(x, y); g.stroke();
    }
    g.save(); g.translate(x, y); g.rotate(th - Math.PI / 4);
    drawPlane(g, 0, 0, o.kind ? 19 : 14, col);
    g.restore();
    shown.push({o, x, y, col});
  }
  for (const {o, x, y, col} of shown) {
    if (!o.kind) continue;
    const info = (infoCache.get(o.ac.hex + "|" + String(o.ac.flight || "").trim().toUpperCase()) || {}).info;
    const name = (info && info.flightNo) || String(o.ac.flight || "").trim() || o.ac.r || o.ac.hex.toUpperCase();
    g.font = `700 11.5px ${FONT}`; g.fillStyle = COL.ink; g.fillText(name, x + 12, y - 3);
    g.font = `500 10px ${FONT}`; g.fillStyle = col; g.fillText(altShort(o.alt), x + 12, y + 9);
  }
  g.restore();
  g.strokeStyle = "rgba(255,255,255,.22)"; g.lineWidth = 1.5; g.beginPath(); g.arc(cx, cy, R, 0, TAU); g.stroke();
  const gl = g.createLinearGradient(cx - R, cy - R, cx + R * .2, cy + R * .4);          // the instrument's glass
  gl.addColorStop(0, "rgba(255,255,255,.06)"); gl.addColorStop(.5, "rgba(255,255,255,.015)"); gl.addColorStop(.501, "rgba(255,255,255,0)");
  g.fillStyle = gl; g.beginPath(); g.arc(cx, cy, R, 0, TAU); g.fill();
  g.font = `700 13px ${FONT}`; g.fillStyle = COL.muted; g.textAlign = "center"; g.textBaseline = "middle";
  [["N", 0], ["E", 90], ["S", 180], ["W", 270]].forEach(([l, deg]) => { const a = deg * Math.PI / 180; g.fillText(l, cx + Math.sin(a) * (R - 12), cy - Math.cos(a) * (R - 12)); });
  pictogram(g, cx - 8, cy - 8, 16);
  g.textAlign = "left"; g.textBaseline = "alphabetic";
}
function buildRadarLegend(){
  $("rLegend").innerHTML = [[RADAR_COL.over, "Overhead"], [RADAR_COL.soon, "Inbound"], [RADAR_COL.by, "Flying by"], [RADAR_COL.away, "Outbound"],
    [RADAR_COL.special, "Special"], [RADAR_COL.fav, "Favourite"], [RADAR_COL.high, "Too high"]].map(([c, t]) => `<li><i style="--c:${c}"></i>${escH(T(t))}</li>`).join("");
}
let rvSig = "";
function renderRadarList(){
  if (tab !== "radar") return;
  const range = radarRange(), list = radar.planes.filter(o => o.kind && o.dist <= range).sort((a, b) => a.dist - b.dist).slice(0, 12);
  const rows = list.map(o => {
    const info = (infoCache.get(o.ac.hex + "|" + String(o.ac.flight || "").trim().toUpperCase()) || {}).info || baseInfo(o.ac);
    const name = info.flightNo || String(o.ac.flight || "").trim() || o.ac.r || o.ac.hex.toUpperCase();
    const st = MODE_REMARK[o.kind === "over" ? "over" : o.kind === "soon" ? "soon" : o.kind === "by" ? "by" : "away"];
    return `<li class="rv" style="--lamp:${radarColor(o)}"><strong>${escH(name)}<span>${escH(String(o.ac.t || ""))}</span></strong>` +
      `<span class="num">${distText(o.dist)} ${o.dir}</span><span class="num">${escH(altShort(o.alt))}</span>${chip(st)}</li>`;
  });
  const html = rows.length ? rows.join("") : `<li class="empty">${escH(T("No planes within {n} km right now.", {n: range}))}</li>`;
  if (html !== rvSig) { rvSig = html; $("rvList").innerHTML = html; }
}

/* ---------- settings: the cockpit plates, stacked for a phone ---------- */
// Two cells to a row on a phone (three for the switches); `span: 2` or `wide` takes the whole row.
const COCKPIT = [
  {title: ["Location", "Standort"], cols: 2, items: [
    {k: "place", type: "lcd", label: "Place name", max: 24},
    {k: "home", type: "lcd", label: "Home airport", max: 3},
    {k: "lat", type: "lcd", label: "Latitude", max: 12},
    {k: "lon", type: "lcd", label: "Longitude", max: 12},
    {k: "radiusKm", type: "wheel", label: "Radius km", min: 1, max: 20, step: 1},
    {k: "overKm", type: "rotary", label: "Overhead within", opts: [[1, "1"], [2, "2"], [3, "3"], [5, "5 KM"]]},
    {type: "locate", label: "Current location", span: 2}]},
  {title: ["Traffic", "Verkehr"], cols: 2, items: [
    {k: "maxAltFt", type: "rotary", label: "Ignore planes above", opts: [[8000, "8K FT"], [15000, "15K"], [25000, "25K"], [60000, "ALL"]]},
    {k: "airtimeMin", type: "rotary", label: "Hovering, min/hour", opts: [[2, "2"], [3, "3"], [5, "5"], [10, "10"], [0, "OFF"]]},
    {k: "favs", type: "lcd", label: "Favourites: airlines, aircraft types or registrations, separated by commas", wide: true, max: 300}]},
  {title: ["Display", "Anzeige"], cols: 2, items: [
    {k: "lang", type: "rotary", label: "Language", opts: LANGS},
    {k: "theme", type: "rotary", label: "Board style", opts: [["classic", "CLASSIC"], ["frankfurt", "FRANKFURT"], ["blue", "BLUE"]]},
    {k: "units", type: "switch", label: "Units", on: "metric", off: "aviation", upText: "METRIC", downText: "FT · KT"},
    {k: "speedPct", type: "wheel", label: "Flap speed %", min: 10, max: 100, step: 5},
    {k: "logos", type: "switch", label: "Airline logos"},
    {k: "imperfect", type: "switch", label: "Worn hardware"}]},
  {title: ["Phone", "Telefon"], cols: 3, items: [
    {k: "chimes", type: "switch", label: "Chimes"},
    {k: "sound", type: "switch", label: "Flap sound"},
    {k: "demo", type: "switch", label: "Demo mode", guard: true}]}];
let draft = null;
// Inside the Android app (android/ in the repository) the page runs in a WebView that offers OverheadAndroid.
const ANDROID = !!(window.OverheadAndroid && window.OverheadAndroid.changeRelay);
const APK_URL = "https://github.com/Belstria/overhead-board/releases/latest/download/overhead.apk";
const ITEMS = COCKPIT.flatMap(p => p.items || []).filter(it => it.k);
//@E29
//@E32
/* Airport style on the phone: on Now, the plane taking off or landing right now on the flaps with its photo and details,
   then the take-offs and the landings as lists (in place of Recent flights). */
function apRowHtml(e){
  const info = e.info || baseInfo(e.ac), place = e.kind === "dep" ? info.to : info.from;
  const route = place ? (e.kind === "dep" ? `<i>→</i>${placeHtml(place)}` : `${placeHtml(place)}<i>→</i>`) : "";
  const meta = [info.type || e.ac.t, e.ac.r].filter(Boolean).map(escH).join(" · ");
  return `<li class="fl"><time>${e.t ? hhmm(new Date(e.t)) : ""}</time>` +
    `<div class="who"><strong>${escH(apFlight(e))}</strong>${info.airline ? `<span>${escH(info.airline)}</span>` : ""}</div>${chip(e.st)}` +
    `${route ? `<div class="rt">${route}</div>` : ""}<div class="meta"><span>${meta}</span><span>${e.alt != null ? altText(e.alt) : e.ground ? T("on the ground") : ""}</span></div></li>`;
}
let apSig = "";
function renderAirport(){
  if (tab !== "now" || !airportMode()) return;
  const sub = !AP.code ? T("Set the home airport in Settings.") : AP.lat == null ? T("Looking up {code} …", {code: AP.code}) :
    T("Planes taking off from and landing at {where}. Times: when they took off, and when they're expected on the ground.", {where: apName()});
  const deps = AP.deps.map(apRowHtml).join("") || `<li class="empty">${escH(T("No take-offs right now."))}</li>`;
  const arrs = AP.arrs.map(apRowHtml).join("") || `<li class="empty">${escH(T("No landings coming up right now."))}</li>`;
  const sig = sub + deps + arrs + S.units;
  if (sig === apSig) return;
  apSig = sig;
  $("apSub").textContent = sub; $("apDeps").innerHTML = deps; $("apArrs").innerHTML = arrs;
}
function airportChanged(){ apSig = ""; renderAirport(); }
// The page's fixed texts are marked data-t with their English; this puts them in the language chosen.
function applyLang(){
  pickLang();
  for (const el of document.querySelectorAll("[data-t]")) el.textContent = T(el.dataset.t);
  buildTabs(); buildSvTools(); buildRadarLegend();
  if (tab) showTab(tab);
  clearTiles(); refreshPanels(true);
}
// Overhead and Airport in the title: tap one to switch.
function setMode(md){
  if (S.mode === md) return;
  ctlSound.press(); audioInit();
  S.mode = md; saveSettings();
  if (tab !== "now") showTab("now"); else applyMode();
  showModes();
  poll(true);                                       // the new style picks its plane from fresh positions
}
function showModes(){ for (const b of document.querySelectorAll("#modes [data-mode]")) b.setAttribute("aria-pressed", String(b.dataset.mode === (S.mode || "overhead"))); }
// Which of the two the Now tab shows.
function applyMode(){
  showModes();
  const ap = airportMode();
  $("apSec").hidden = !ap; $("recentSec").hidden = ap;
  if (ap) { airportPos(); apSig = ""; renderAirport(); apFeature(); }
  renderFeatured(); renderAircraftInfo();
}
//@E31
function plateHtml(p){
  return `<div class="plate" style="--cols:${p.cols || 2}"><i></i><i></i><i></i><i></i><h3>${escH(T(p.title[0]))}</h3>${p.items.map(itemHtml).join("")}</div>`;
}
function cockpitOpen(){
  draft = {...S};
  const box = $("cockpit");
  box.innerHTML = COCKPIT.map(plateHtml).join("") +
    `<div class="plate about" style="--cols:1"><i></i><i></i><i></i><i></i><h3>${T("About")}</h3><p class="ver">${escH(versionLine())}</p>` +
    `<p>${escH(T("What's new in each version, the relay and who made it."))}</p><div class="acts"><button class="cap big" type="button" id="aboutBtn">${T("About")}</button></div></div>`;
  $("aboutBtn").onclick = () => { ctlSound.press(); showTab("about"); };
  for (const el of box.querySelectorAll("[data-k]")) {
    const it = ITEMS.find(x => x.k === el.dataset.k);
    if (el.classList.contains("lcd")) el.oninput = () => { draft[it.k] = el.value; cockpitDirty(); };
    else if (el.classList.contains("rotary")) {
      const turn = i => { const was = rotaryIndex(it); draft[it.k] = it.opts[(i + it.opts.length) % it.opts.length][0]; cockpitShow(); ctlSound.rotary(Math.abs(rotaryIndex(it) - was)); };
      el.onclick = e => { const b = e.target.closest("b"); turn(b ? +b.dataset.i : rotaryIndex(it) + 1); };
      el.onkeydown = e => { const d = /Right|Up/.test(e.key) ? 1 : /Left|Down/.test(e.key) ? -1 : 0; if (d) { e.preventDefault(); const j = rotaryIndex(it) + d; if (j >= 0 && j < it.opts.length) turn(j); } };
    } else if (el.classList.contains("toggle")) el.onclick = () => {
      draft[it.k] = it.on ? (draft[it.k] === it.on ? it.off : it.on) : !draft[it.k]; cockpitShow(); ctlSound.toggle(el.getAttribute("aria-pressed") === "true");
    };
    else if (el.classList.contains("wheel")) {
      const roll = d => { const was = draft[it.k]; wheelStep(it, el.dataset.part, d); cockpitShow(el, d); if (draft[it.k] !== was) ctlSound.wheel(); };
      el.querySelector(".inc").onclick = () => roll(1);
      el.querySelector(".dec").onclick = () => roll(-1);
    }
  }
  wireLocate(box);
  cockpitShow();
  renderAbout();
}
function cockpitDirty(){
  const dirty = !!draft && ITEMS.some(it => String(draft[it.k] ?? "") !== String(S[it.k] ?? ""));
  $("saveBtn").setAttribute("aria-pressed", String(dirty));
}
// Save applies the draft and keeps it on this phone; Cancel puts the controls back to the saved settings.
let savedTimer = 0;
function buildSaveBar(){
  $("saveBtn").onclick = () => {
    ctlSound.press();
    applySettings(draft); cockpitOpen();
    const b = $("saveBtn");
    b.textContent = T("Saved"); clearTimeout(savedTimer);
    savedTimer = setTimeout(() => { b.textContent = T("Save"); }, 1600);
  };
  $("cancelBtn").onclick = () => { ctlSound.press(); cockpitOpen(); };
}
/* About: a page of its own, opened from Settings. The version and patch notes are the board's (test-api). */
function aboutOpen(){
  const screws = "<i></i><i></i><i></i><i></i>";
  $("aboutBox").innerHTML =
    `<div class="plate" style="--cols:1">${screws}<h3>${T("About")}</h3><p class="ver" id="aboutVer"></p><p id="aboutStatus"></p>` +
    (ANDROID ? `<p>${escH(T("The Overhead app for Android, showing the relay at {host}.", {host: location.host}))}</p><div class="acts"><button class="cap big" type="button" id="relayBtn">${T("Change relay")}</button></div>`
      : `<p>${escH(T("On Android, install the Overhead app and open the file (allow installs from your browser once):"))} <a href="${APK_URL}">${T("download it")}</a>. ` +
        `${escH(T("On an iPhone, Safari → Share → Add to Home Screen."))}</p>`) +
    `<p>${escH(T("It needs your home Wi-Fi, because the flight data comes through the relay on your computer. The big board:"))} <a href="../">${escH(location.host)}/</a></p>` +
    aboutHtml() + `</div>` +
    `<div class="plate" style="--cols:1">${screws}<h3>${T("Legend")}</h3><div class="lgbox">${legendHtml()}</div></div>` +
    `<div class="plate" style="--cols:1">${screws}<h3>${T("Patch notes")}</h3><div class="log">${changelogHtml()}</div></div>` +
    `<div class="acts"><button class="cap big" type="button" id="aboutBack">${T("Settings")}</button></div>`;
  if (ANDROID) $("relayBtn").onclick = () => { ctlSound.press(); window.OverheadAndroid.changeRelay(); };
  $("aboutBack").onclick = () => { ctlSound.press(); showTab("settings"); };
  renderAbout();
}
function renderAbout(){
  const el = $("aboutStatus");
  if (!el) return;
  el.textContent = statusLine();
  $("aboutVer").textContent = versionLine();
}
function applySettings(n){
  const num = v => parseFloat(String(v).replace(",", "."));
  const lat = num(n.lat), lon = num(n.lon), wasDemo = S.demo;
  S = {...S, ...n,
    place: String(n.place || "").trim() || DEFAULTS.place,
    lat: isFinite(lat) && Math.abs(lat) <= 90 ? lat : S.lat,
    lon: isFinite(lon) && Math.abs(lon) <= 180 ? lon : S.lon,
    radiusKm: Math.min(20, Math.max(1, num(n.radiusKm) || 15)),
    home: clean(n.home).slice(0, 3), favs: String(n.favs || "").trim(),
    maxAltFt: +n.maxAltFt, airtimeMin: +n.airtimeMin, speedPct: +n.speedPct || 85, overKm: +n.overKm || 3};
  const langWas = LANG;
  saveSettings(); audioInit();
  pickLang(); if (LANG !== langWas) applyLang();
  AP.code = "";                                               // the home airport may have changed
  if (wasDemo !== S.demo) {
    feat = null; infoCache.clear(); sightRev = null; relayStats = null; airtime.clear(); lbCache = null;
    fullDay = {at: 0, rev: null, date: null, list: null};
    spotted = relayV5() ? [] : S.demo ? demoLog() : [];
    if (relayV5()) syncSightings();
  }
  applyTheme(); updateWhere();
  recentSig = svSig = lbSig = factsSig = ""; shownPhoto = null;
  if (tab === "now") applyMode();
  renderLists(); renderFeatured(); renderAircraftInfo(); updateFooter(); poll(true); sayHello();
}

/* ---------- tabs: the board's push buttons along the bottom ---------- */
const TABS = [["now", "Now"], ["today", "Today"], ["logbook", "Logbook"], ["radar", "Radar"], ["settings", "Settings"]];
let tab = "now", tabTimer = null;
function buildTabs(){
  $("tabRow").innerHTML = TABS.map(([t, name]) => `<button class="cap${T(name).length > 9 ? " long" : ""}" type="button" data-tab="${t}">${T(name)}</button>`).join("");
  for (const b of $("tabRow").children) b.onclick = () => { audioInit(); ctlSound.press(); showTab(b.dataset.tab); };
}
function pingNow(on){ const b = $("tabRow").querySelector('[data-tab="now"]'); if (b) b.classList.toggle("ping", on); }
function showTab(t){
  if (!TABS.some(x => x[0] === t) && t !== "about") t = "now";
  const was = tab;
  tab = t;
  for (const [x] of TABS) $("t-" + x).hidden = x !== t;
  $("t-about").hidden = t !== "about";
  for (const b of $("tabRow").children) { if (b.dataset.tab === (t === "about" ? "settings" : t)) b.setAttribute("aria-current", "page"); else b.removeAttribute("aria-current"); }
  HERO.off = t !== "now"; TODAYP.off = t !== "today"; LBP.off = t !== "logbook";
  clearInterval(tabTimer); tabTimer = null;
  stopRadar();
  refreshPanels();
  if (t === "now") { pingNow(false); applyMode(); renderFeatured(); renderAircraftInfo(); renderRecent(); }
  else if (t === "today") { svSig = ""; renderToday(); }
  else if (t === "logbook") { lbSig = ""; fetchLogbook(); tabTimer = setInterval(fetchLogbook, 60000); }
  else if (t === "radar") { rvSig = ""; startRadar(); renderRadarList(); }
  else if (t === "settings") cockpitOpen();
  else if (t === "about") aboutOpen();
  const hash = t === "now" ? "" : "#" + t;
  if (location.hash !== hash) history.replaceState(null, "", location.pathname + location.search + hash);
  if (was !== t) window.scrollTo(0, 0);
}
addEventListener("hashchange", () => showTab(location.hash.slice(1)));

/* ---------- status: a dot by the clock, a line under the lists ---------- */
function statusLine(){
  if (S.demo) return T("Demo mode · sample flights, not live data");
  if (!relay()) return T("No flight data here: open the app through your home relay, at http://<your computer>:8080/app/");
  if (isOffline()) return T("No flight data for over a minute · retrying");
  if (!lastOk && failures) return T(failures > 1 ? "Waiting for flight data · {n} failed attempts" : "Waiting for flight data · {n} failed attempt", {n: failures});
  if (!lastOk) return T("Connecting…");
  const age = Math.round((Date.now() - lastOk) / 1000), stale = lastFreshness.startsWith("stale");
  return T("Live via {src}", {src: feedName}) + (stale ? " " + T("(last good copy)") : "") + " · " + (age < 3 ? T("updated just now") : T("updated {n} s ago", {n: age})) +
    (failures ? " · " + T("retrying") : "") + " · " + T("{n} aircraft within {km} km", {n: nearbyCount ?? 0, km: QUERY_KM}) + (apiOn() ? " · " + T("flight numbers by Flightradar24") : "");
}
function updateFooter(){
  const dot = $("dot");
  dot.dataset.state = S.demo ? "demo" : !relay() || isOffline() ? "off" : !lastOk ? (failures ? "warn" : "") : failures || lastFreshness.startsWith("stale") ? "warn" : "live";
  const line = statusLine();
  for (const el of document.querySelectorAll(".statusText")) if (el.textContent !== line) el.textContent = line;
  if (tab === "about") renderAbout();
}
function updateWhere(){ $("where").textContent = `${clean(S.place)}  ·  ${T("RADIUS {n} KM", {n: +S.radiusKm || 15})}`; }
function tickClock(){
  setChars("clock", hhmm()); rollDay(); updateFooter();
  if (feat && !isOffline()) setWord("remarks", featRemark());
}

/* ---------- saying hello to the relay, so it can list this phone among its screens ---------- */
const relayV12 = () => !!relay() && !relayLegacy && (window.OVERHEAD_RELAY_VERSION || 0) >= 12;
function sayHello(){
  if (!relayV12()) return;
  const d = window.devicePixelRatio || 1;
  const params = new URLSearchParams({name: "", w: Math.round(screen.width * d), h: Math.round(screen.height * d), q: "", vis: document.visibilityState || ""});
  timedFetch(`${relay()}/hello?${params}`, {}, 6000).catch(() => {});
}
addEventListener("pagehide", () => { try { if (relayV12() && navigator.sendBeacon) navigator.sendBeacon(tagged(`${relay()}/bye`)); } catch {} });
//@E30

// A phone in a pocket doesn't need updates every ten seconds: back to full speed as soon as the app is looked at.
document.addEventListener("visibilitychange", () => {
  sayHello();
  if (document.visibilityState !== "visible") return;
  // A phone may throw away a hidden page's canvas pictures (and the cached flap faces): draw everything afresh.
  clearTiles(); refreshPanels(true); drawMark(); if (tab === "radar") radarSize();
  poll(true); if (relayV5()) syncSightings();
  if (tab === "logbook") fetchLogbook();
});
["pointerdown", "touchstart", "keydown"].forEach(ev => addEventListener(ev, () => audioInit(), {passive: true, capture: true}));
let resizeQ = 0;
addEventListener("resize", () => {
  cancelAnimationFrame(resizeQ);
  resizeQ = requestAnimationFrame(() => { clearTiles(); refreshPanels(true); drawMark(); if (tab === "radar") radarSize(); });
});

async function start(){
  try {
    await Promise.race([
      Promise.all(["700 40px", "600 20px", "400 40px"].map(s => document.fonts.load(`${s} ${(THEMES[S.theme] || THEMES.classic).font}`))),
      new Promise(r => setTimeout(r, 2500))
    ]);
  } catch {}
  pickLang();
  for (const el of document.querySelectorAll("[data-t]")) el.textContent = T(el.dataset.t);
  buildTabs(); buildSvTools(); buildRadarLegend(); buildSaveBar(); updateWhere();
  for (const b of document.querySelectorAll("#modes [data-mode]")) b.onclick = () => setMode(b.dataset.mode);
  showModes();
  applyTheme();
  showTab(location.hash.slice(1) || "now");
  if (document.fonts && document.fonts.addEventListener) document.fonts.addEventListener("loadingdone", () => { clearTiles(); refreshPanels(true); });
  if (S.demo || !relayV5()) spotted = S.demo ? demoLog() : [];
  tickClock(); setInterval(tickClock, 1000);
  renderFeatured(); renderLists(); updateFooter();
  if (relayV5()) syncSightings();
  dlog("info", `App started · ${S.demo ? "demo mode" : relay() ? "using the home relay" : "no relay"} · watching ${S.lat.toFixed(4)}, ${S.lon.toFixed(4)}, radius ${+S.radiusKm || 15} km`);
  setTimeout(poll, 300);
  setTimeout(sayHello, 2000); setInterval(sayHello, 60000);
  // Turned on its side or upright again: the flaps take the other arrangement (the page's columns are CSS).
  const turned = () => { heroLayout(); clearTiles(); refreshPanels(true); if (tab === "radar") radarSize(); };
  SIDEWAYS.addEventListener ? SIDEWAYS.addEventListener("change", turned) : SIDEWAYS.addListener && SIDEWAYS.addListener(turned);
}
start();
})();
</script>
</body>
</html>
