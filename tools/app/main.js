(() => {
"use strict";
const $ = id => document.getElementById(id);
const escH = s => String(s ?? "").replace(/[&<>"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
//@E1

/* ---------- settings: kept on this phone (and, for a guest, with their profile on the relay) ---------- */
// A guest (friends and family, let in with a personal invite link; relay 19+) gets their name and saved settings
// from the relay instead of the home location, and their settings go back to it, so their other devices know them.
const GUEST = window.OVERHEAD_GUEST || null;
const DEFAULTS = {place:"Vienna", lat:48.2085, lon:16.3731, radiusKm:15, home:"VIE", maxAltFt:60000, units:"metric", sound:true, soundSet:"recorded", bell:"airport", real:true, speedPct:85, quick:false, refreshS:5,
  logos:true, overKm:3, demo:false, theme:"classic", favs:"", chimes:true, imperfect:true, airtimeMin:3, mode:"overhead", lang:"auto"};
const SKEY = GUEST ? "od.app.settings.g." + GUEST.id : "od.app.settings";   // each guest's own, in a shared browser
function loadSettings(){
  let saved = {};
  try { saved = JSON.parse(localStorage.getItem(SKEY) || "{}") || {}; } catch {}
  return {...DEFAULTS, ...(GUEST && GUEST.settings || {}), ...saved};
}
// A guest's settings go to their profile a moment after a change, always with their place (`located` once they have
// set one), so the relay knows where to count their planes even when it happens to be the default spot.
let meQ = 0;
function saveMe(changed, now){
  if (!GUEST) return Promise.resolve();
  const settings = S.located ? {...changed, lat: S.lat, lon: S.lon, radiusKm: S.radiusKm, place: S.place, located: true} : changed;
  const send = () => fetch(`${relay()}/me`, {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({settings})}).catch(() => {});
  clearTimeout(meQ);
  if (now) return send();
  meQ = setTimeout(send, 1200);
  return Promise.resolve();
}
const located = () => !GUEST || !!S.located;
function saveSettings(){
  const changed = {};
  for (const [k, v] of Object.entries(S)) if (k !== "proxy" && JSON.stringify(v) !== JSON.stringify(DEFAULTS[k])) changed[k] = v;
  try { localStorage.setItem(SKEY, JSON.stringify(changed)); } catch {}
  return saveMe(changed);
}
Object.assign(DEFAULTS, window.OVERHEAD_DEFAULTS || {});  // location etc. supplied by the home relay
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
// The plane overhead: the board's top half, in eight rows for a phone held upright and, on its side, in three rows
// across the whole width (like the board's top half, with a page under it).
const UM = 14;                                   // margin, in panel units (the panel is 390 units wide)
const HERO = makePanel($("hero"), 390, 404, 10.5);
def(HERO, "flight",  {kind:"chars", n:7, dur:82, label:["Flight","Flug"], loud:1});
def(HERO, "remarks", {kind:"word",  n:6.3, dur:120, words:"remarks", label:["Status",""], loud:1});
def(HERO, "airline", {kind:"word",  n:13.93, dur:120, words:"airline", label:["Airline","Fluglinie"], loud:1});
def(HERO, "fromCode",{kind:"chars", n:3, dur:82, style:"amber", label:["From","Von"], loud:1});
def(HERO, "fromCity",{kind:"chars", n:10, dur:82, loud:1});
def(HERO, "toCode",  {kind:"chars", n:3, dur:82, style:"amber", label:["To","Nach"], loud:1});
def(HERO, "toCity",  {kind:"chars", n:10, dur:82, loud:1});
def(HERO, "type",    {kind:"chars", n:16, dur:66, label:["Aircraft","Flugzeug"]});
def(HERO, "tier",    {kind:"word",  n:1, dur:110, words:"tier"});
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
  HERO.w = wide ? 900 : 390; HERO.h = wide ? 150 : 404;
  HERO.el.style.setProperty("--w", HERO.w); HERO.el.style.setProperty("--h", HERO.h);
  if (wide) {
    placeRow(["flight", "airline", "remarks", "reg"], [1, 1, 1.5], 18, 18, 1.45, UM);
    placeRow(["fromCode", "fromCity", "toCode", "toCity", "type", "tier"], [.4, 1, .4, 1, .15], 66, 18, 1.45, UM);
    placeRow(["alt", "trend", "speed", "pos", "depTime", "arrTime", "airTime"], [.3, .8, .8, 1, .8, .8], 114, 18, 1.45, UM);
    return;
  }
  placeRow(["flight", "remarks"], [.6], 18, 26, 1.45, UM);
  placeRow(["airline"], [], 71, 26, 1.45, UM);
  placeRow(["fromCode", "fromCity"], [.4], 124, 27, 1.45, UM);
  placeRow(["toCode", "toCity"], [.4], 178, 27, 1.45, UM);
  placeRow(["type", "tier"], [.15], 232, 21.4, 1.45, UM);
  placeRow(["reg", "alt", "trend"], [.5, .3], 279, 19.36, 1.45, UM);
  placeRow(["speed", "pos"], [.6], 323, 19.36, 1.45, UM);
  placeRow(["depTime", "arrTime", "airTime"], [1.3, 1.3], 367, 19.36, 1.45, UM);
}
heroLayout();
// On its side, the pages under the plane are flaps too, like the board's lower half (only the newest rows fit).
const NOW_ROWS = 6;
let nowRows = NOW_ROWS;
const lowUnits = k => 196 - 30 * (NOW_ROWS - k);              // the list panels' height for k rows
function setNowRows(k){
  if (k === nowRows) return;
  nowRows = k;
  for (const P of [RECENTP, APP]) {
    P.h = lowUnits(k); P.el.style.setProperty("--h", P.h); P.cssW = 0;
    for (const id of P.ids) fields[id].hidden = +id.match(/\d+/)[0] >= k;
  }
}
const RECENTP = makePanel($("recentP"), 900, 196);
for (let i = 0; i < NOW_ROWS; i++) {
  const lab = en => i === 0 ? [en, ""] : null, s = 14.5;
  def(RECENTP, `nl${i}time`,    {kind:"chars", n:5, drum:DRUM_DIGIT, dur:60, style:"amber", loud:.5, label:lab("Time")});
  def(RECENTP, `nl${i}flight`,  {kind:"chars", n:7, dur:60, loud:.5, label:lab("Flight")});
  def(RECENTP, `nl${i}from`,    {kind:"chars", n:10, dur:60, loud:.5, label:lab("From")});
  def(RECENTP, `nl${i}to`,      {kind:"chars", n:10, dur:60, loud:.5, label:lab("To")});
  def(RECENTP, `nl${i}type`,    {kind:"chars", n:14, dur:60, loud:.5, label:lab("Aircraft")});
  def(RECENTP, `nl${i}remarks`, {kind:"word",  n:10, dur:95, words:"remarks", small:true, loud:.5, label:lab("Remarks")});
  placeRow(["time", "flight", "from", "to", "type", "remarks"].map(c => `nl${i}${c}`), [.8, .8, .8, .8, .8], 18 + i * 30, s, 1.45, UM);
}
const APP = makePanel($("apP"), 900, 196);
for (const k of ["d", "a"]) for (let i = 0; i < NOW_ROWS; i++) {
  const dep = k === "d", lab = en => i === 0 ? [en, ""] : null, s = 13.2, id = c => `na${k}${i}${c}`;
  def(APP, id("time"),   {kind:"chars", n:5, drum:DRUM_DIGIT, dur:60, style:"amber", loud:.5, label:lab(dep ? "Time" : "Due")});
  def(APP, id("flight"), {kind:"chars", n:7, dur:60, loud:.5, label:lab("Flight")});
  def(APP, id("city"),   {kind:"chars", n:10, dur:60, loud:.5, label:lab(dep ? "To" : "From")});
  def(APP, id("st"),     {kind:"word",  n:8, dur:95, words:"remarks", small:true, loud:.5, label:lab("Status")});
  placeRow(["time", "flight", "city", "st"].map(id), [.6, .6, .6], 18 + i * 30, s, 1.45, dep ? UM : UM + 34.2 * s);
}
const ACP = makePanel($("acP"), 560, 192);
def(ACP, "naReg",     {kind:"chars", n:8,  dur:70, style:"amber", label:["Registration", ""]});
def(ACP, "naHex",     {kind:"chars", n:6,  dur:70, label:["Mode S", ""]});
def(ACP, "naFlight",  {kind:"chars", n:9,  dur:70, label:["Flight", ""]});
def(ACP, "naType",    {kind:"chars", n:26, dur:70, label:["Aircraft", ""]});
def(ACP, "naOwner",   {kind:"chars", n:26, dur:70, label:["Operator", ""]});
def(ACP, "naCountry", {kind:"chars", n:14, dur:70, label:["Registered in", ""]});
def(ACP, "naRoute",   {kind:"chars", n:9,  dur:70, style:"amber", label:["Route", ""]});
placeRow(["naReg", "naHex", "naFlight"], [1.5, 1.5], 18, 20.4, 1.45, UM);
placeRow(["naType"], [], 64, 20.4, 1.45, UM);
placeRow(["naOwner"], [], 110, 20.4, 1.45, UM);
placeRow(["naCountry", "naRoute"], [2], 156, 20.4, 1.45, UM);
RECENTP.off = APP.off = ACP.off = true;
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
  applyLook();
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
  const shown = l => userLists.hide.length ? l.filter(e => !isHidden(e)) : l;      // hidden planes stay in the logbook, not in the lists
  if (!relayV5() || !fullDay.list || fullDay.date !== sightDay) return shown(spotted);
  const ids = new Set(spotted.map(e => e.id));
  return shown(spotted.concat(fullDay.list.filter(e => !ids.has(e.id))));
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
    `<div class="meta"><span>${meta}</span><span>${near}</span></div>` +
    (listsOk() ? `<button class="more" type="button" data-more="${escH(e.id || e.hex || "")}" aria-label="${escH(T("More for this plane"))}">⋯</button>` : "") + `</li>`;
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
  for (let i = 0; i < NOW_ROWS; i++) {           // the same, on flaps (the phone on its side)
    const e = list[i], d = i * 150, id = c => `nl${i}${c}`;
    setChars(id("time"), e ? e.time || "" : "", d);
    setChars(id("flight"), e ? e.flight || String(e.hex || "").toUpperCase() : "", d + 60);
    setChars(id("from"), e && e.from ? e.from.city || e.from.code || "" : "", d + 120);
    setChars(id("to"), e && e.to ? e.to.city || e.to.code || "" : "", d + 180);
    setChars(id("type"), e ? e.type || "" : "", d + 240);
    setWord(id("remarks"), e ? remarkFor(e) : "", d + 300);
  }
}
let shownPhoto = null, factsSig = "";
function renderAircraftInfo(){
  $("acSec").hidden = !feat;
  nowEmptyNote(); nowPanels();
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
        scr.classList.add("has"); paintRwy();
        if (!REDUCED) { void scr.offsetWidth; scr.classList.add("on"); }
      };
      img.onerror = () => scr.classList.remove("has");
      img.src = src;
    } else img.removeAttribute("src");
  }
  paintRwy();
  const route = info.from && info.to ? `${code3(info.from) || info.from.code} → ${code3(info.to) || info.to.code}` : "";
  setChars("naReg", info.reg || d.reg || "");
  setChars("naHex", feat.hex.toUpperCase(), 60);
  setChars("naFlight", info.flightNo || "", 120);
  setChars("naType", d.type || info.type || "", 180);
  setChars("naOwner", liveryLine(info) || d.owner || info.airline || "", 240);
  setChars("naCountry", d.country || "", 300);
  setChars("naRoute", info.from && info.to ? `${code3(info.from)} - ${code3(info.to)}` : "", 360);
  const facts = [["Registration", "Kennzeichen", info.reg || d.reg], ["Mode S", "", feat.hex.toUpperCase()],
    ["Aircraft", "Flugzeug", d.type || info.type, true], ["Operator", "Betreiber", liveryLine(info) || d.owner || info.airline, true],
    ["Registered in", "Land", d.country], ["Route", "", route], ["To go", "", toGoText(info, feat.o)],
    ["Seen here", "", seenText(info.reg || d.reg || feat.o.ac.r || ""), true]].filter(f => f[2]);
  const sig = JSON.stringify(facts);
  if (sig === factsSig) return;
  factsSig = sig;
  $("acFacts").innerHTML = facts.map(([en, de, v, wide]) => `<div${wide ? ' class="wide"' : ""}><dt>${escH(T(en))}</dt><dd>${escH(v)}</dd></div>`).join("");
  $("acActs").hidden = !listsOk();
}

// The runway screen of the Take-off and Landing pages, as on the board: the runways, the plane and its track, the photo
// inset (drawCover is the board's, which the app doesn't copy).
function drawCover(g, img, x, y, w, h){
  const sc = Math.max(w / img.naturalWidth, h / img.naturalHeight), iw = img.naturalWidth * sc, ih = img.naturalHeight * sc;
  g.drawImage(img, x + (w - iw) / 2, y + (h - ih) / 2, iw, ih);
}
let rwyKey = "";
function paintRwy(){
  const scr = $("screen"), cv = $("rwyCv"), img = $("photo");
  const e = airportMode() && (nowPage === "dep" || nowPage === "land") && feat && feat.apE && AP.rwys.length && AP.lat != null ? feat.apE : null;
  scr.classList.toggle("rwyOn", !!e);
  if (!e) { rwyKey = ""; return; }
  const w = scr.clientWidth, h = scr.clientHeight;
  if (!w || !h) return;
  const px = Math.min(3, window.devicePixelRatio || 1), photo = scr.classList.contains("has") && img.naturalWidth ? img : null;
  const key = [e.hex, e.ac.lat, e.ac.lon, e.st, AP.rwyLine, w, h, px, FONT, LANG, photo ? img.src : ""].join("|");
  if (key === rwyKey) return;
  rwyKey = key;
  cv.width = Math.round(w * px); cv.height = Math.round(h * px);
  const g = cv.getContext("2d");
  g.setTransform(px, 0, 0, px, 0, 0);
  try { if (paintRunwayScreen(g, w, h, e, photo)) requestAnimationFrame(() => { rwyKey = ""; paintRwy(); }); }   // the photo sliding
  catch (err) { scr.classList.remove("rwyOn"); }
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
  if (feat) setWord("tier", tierOf(feat.o.ac, feat.info));             // the tier needs the logbook
  renderLogbook();
}
let lbSig = "";
function renderLogbook(){
  if (tab !== "logbook") return;
  fetchYear();
  $("lbSum").textContent = logbookSummary();
  const b = lbData() || {}, has = !!lbData();
  const byCount = o => Object.entries(o || {}).sort((x, y) => (y[1].count || 0) - (x[1].count || 0));
  const types = byCount(b.types), airlines = byCount(b.airlines);
  setChars("lvSight", has ? nf.format(b.sightings || 0) : "");
  setChars("lvRegs", has ? nf.format(b.regsCount || 0) : "", 60);
  setChars("lvTypes", has ? nf.format(types.length) : "", 120);
  setChars("lvAirlines", has ? nf.format(airlines.length) : "", 180);
  const sig = JSON.stringify([b.since, b.sightings, b.categories, types.slice(0, 10), airlines.slice(0, 10), b.regsTop, b.regsRecent, b.game, b.records, yearData, LANG]);
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
  const g0 = b.game;
  if (g0) {                                          // the game: points, tiers and the collections
    const tiers = TIER_DRUM.slice(1).map(t => `<li style="--lamp:${TIER_COL[t]}"><img class="tico" src="${tierIcon(t)}" alt=""><span class="name">${escH(T(TIER_NAME[t]))}</span><span class="n">${nf.format(g0.tiers[t] || 0)}</span></li>`).join("");
    const sets = g0.sets.map(s => `<li style="--lamp:${s.have.length >= s.total ? TIER_COL.legendary : "var(--amber)"}"><i class="lamp"></i><span class="name">${escH(T(s.name))}</span><span class="n">${s.have.length} / ${s.total}</span>` +
      `<span class="bar"><i style="width:${(s.have.length / s.total * 100).toFixed(1)}%;background:${s.have.length >= s.total ? TIER_COL.legendary : "var(--amber)"}"></i></span></li>`).join("");
    html = `<h3>${escH(T("Collection"))}</h3><p class="sum">${escH(T("{n} points", {n: nf.format(g0.points)}))} · ${escH(T("{n} points today", {n: nf.format(g0.today)}))}` +
      (g0.best ? ` · ${escH(T("best {n}", {n: nf.format(g0.best.points)}))}` : "") + (g0.streak > 1 ? ` · ${escH(T("{n}-day streak", {n: g0.streak}))}` : "") + `</p>` +
      `<ul class="ranks cats tiers">${tiers}</ul><h3>${escH(T("Collections"))}</h3><ul class="ranks cats">${sets}</ul>` + html;
  }
  const r = b.records;
  if (r && (r.closest || r.lowest || r.fastest || r.farthest)) {           // lifetime records (relay 28)
    const who = x => x.callsign || x.reg || x.type || "", p = r.farthest && r.farthest.place;
    const rows = [["Closest ever", r.closest, x => `${x.v < 10 ? x.v.toFixed(2) : Math.round(x.v)} km`], ["Lowest ever", r.lowest, x => altitudeStr(x.v).toLowerCase()],
      ["Fastest ever", r.fastest, x => speedStr(x.v).toLowerCase()], ["Farthest route", r.farthest, x => `${p ? p.code || p.city : ""} · ${nf.format(x.v)} km`]].filter(x => x[1]);
    const rec = `<h3>${escH(T("Records"))}</h3>` + rank(rows.map(([en, x, v]) => li(T(en), v(x), [who(x), x.ts ? fmtDay(x.ts) : ""].filter(Boolean).join(" · "))), true);
    const k = html.indexOf(`<h3>${escH(T("Categories"))}</h3>`);
    html = k >= 0 ? html.slice(0, k) + rec + html.slice(k) : html + rec;
  }
  const bg = g0 && g0.bingo, won = (g0 && g0.trophies) || {};
  if (bg && bg.card) {                                 // the weekly bingo and the trophies (relay 29)
    const nd = Object.keys(bg.done || {}).length;
    const cells = bg.card.map(k => { const d = (bg.done || {})[k];
      return `<div class="bc${d ? " on" : ""}"><i></i><span>${escH(goalText(k))}</span>${d ? `<small>${escH(fmtDay(d))}</small>` : ""}</div>`; }).join("");
    const cups = TROPHY_IDS.map(k => { const [nm, what] = trophyText(k), d = won[k];
      return `<li class="${d ? "on" : ""}">${CUP}<span class="name">${escH(nm)}<span class="s">${escH(what)}</span></span><span class="n">${d ? escH(fmtDay(d)) : ""}</span></li>`; }).join("");
    const more = `<h3>${escH(T("This week's bingo"))}</h3><p class="sum">${escH(T("{n} of 9 done · full lines: {l}", {n: nd, l: bg.lines || 0}))}</p><div class="bingo">${cells}</div>` +
      `<h3>${escH(T("Trophies"))}</h3><p class="sum">${escH(T("{n} of {t} won", {n: TROPHY_IDS.filter(k => won[k]).length, t: TROPHY_IDS.length}))}</p><ul class="ranks plain cups">${cups}</ul>`;
    const k = html.indexOf(`<h3>${escH(T("Categories"))}</h3>`);
    html = k >= 0 ? html.slice(0, k) + more + html.slice(k) : html + more;
  }
  html = yearHtml() + html;
  $("lbLists").innerHTML = html;
  const cv = $("yCsv"); if (cv) cv.onclick = () => ctlSound.press();
}
// Each tier's icon as on its flap after the aircraft type: the white sign on the tier's colour (drawn once, as a picture).
const tierIcons = {};
function tierIcon(t){
  if (tierIcons[t]) return tierIcons[t];
  const n = 48, cv = document.createElement("canvas"), g = cv.getContext("2d");
  cv.width = cv.height = n;
  const gr = g.createLinearGradient(0, 0, 0, n);
  gr.addColorStop(0, shade(TIER_COL[t], .05)); gr.addColorStop(1, shade(TIER_COL[t], -.28));
  g.fillStyle = gr; g.beginPath(); g.roundRect ? g.roundRect(0, 0, n, n, 9) : g.rect(0, 0, n, n); g.fill();
  drawTierIcon(g, n / 2, n / 2, n * .95, t, "#fbf8f0");
  return tierIcons[t] = cv.toDataURL();
}
// A trophy cup for the trophies list (gold when won, by CSS).
const CUP = '<svg class="cup" viewBox="0 0 24 24" aria-hidden="true"><path d="M7 3h10c0 5-1.5 8-5 8.5C8.5 11 7 8 7 3zM11 11.5h2l.5 4h-3zM8 16h8v2.2H8z"/><path d="M7 4.5C4.5 4.5 4 8 7.5 9M17 4.5c2.5 0 3 3.5-.5 4.5" fill="none" stroke-width="1.6"/></svg>';
// The year in planes (relay 29, /year): a card at the top of the Logbook with a Share button (a picture of the card)
// and the logbook as a spreadsheet (/logbook.csv).
let yearData = null, yearAt = 0;
function fetchYear(){
  if (!relay() || (window.OVERHEAD_RELAY_VERSION || 0) < 29 || Date.now() - yearAt < 5 * 60000) return;
  yearAt = Date.now();
  fetchJSON(`${relay()}/year?y=${new Date().getFullYear()}`, {}, 10000).then(j => { yearData = j; lbSig = ""; renderLogbook(); }).catch(() => { yearAt = 0; });
}
function yearFacts(y){
  const r = y.rarest, m = y.mostSeen, b = y.busiest;
  return [[T("Busiest day"), b ? `${fmtDay(Date.parse(b.day))} · ${nf.format(b.planes)}` : ""],
    [T("Most seen aircraft"), m ? `${m.reg} · ${T("{n} times", {n: nf.format(m.count)})}` : ""],
    [T("Rarest"), r ? `${r.type || r.reg} · ${T(TIER_NAME[r.tier] || "")}` : ""]].filter(x => x[1]);
}
function yearHtml(){
  const y = yearData;
  if (!y || !y.planes) return "";
  const nums = [[y.planes, "planes"], [y.types, "types"], [y.airlines, "airlines"], [y.airframes, "airframes"], [y.countries, "countries"], [y.days, "days"]];
  return `<div class="yearCard"><h3>${escH(T("{y} in planes", {y: y.year}))}</h3><div class="yNums">` +
    nums.map(([n, k]) => `<div><b>${nf.format(n || 0)}</b><span>${escH(T(k))}</span></div>`).join("") + `</div><dl class="yFacts">` +
    yearFacts(y).map(([k, v]) => `<div><dt>${escH(k)}</dt><dd>${escH(v)}</dd></div>`).join("") +
    `</dl><div class="yActs"><button class="cap small" type="button" id="yShare">${escH(T("Share"))}</button>` +
    `<a class="cap small" id="yCsv" href="${escH(relay())}/logbook.csv" download>${escH(T("Download the logbook (CSV)"))}</a></div>` +
    `<p class="sum">${escH(T("Every sighting as a spreadsheet, for a spotting app or Excel."))}</p></div>`;
}
// The year card as a picture to share (or save where sharing pictures isn't possible).
function yearPicture(){
  const y = yearData, cv = document.createElement("canvas"), g = cv.getContext("2d"), W2 = 1080, H2 = 1350;
  cv.width = W2; cv.height = H2;
  g.fillStyle = "#0b0b0c"; g.fillRect(0, 0, W2, H2);
  g.fillStyle = "#f0b429"; rr(g, 80, 80, 140, 140, 18); g.fill();
  drawPlane(g, 150, 150, 120, "#0b0b0c");
  g.fillStyle = "#f3f0e8"; g.font = `700 64px ${FONT}`; g.fillText("FALLBLATT", 260, 170);
  g.fillStyle = "#f0b429"; g.font = `700 92px ${FONT}`; g.fillText(T("{y} in planes", {y: y.year}), 80, 360);
  const nums = [[y.planes, "planes"], [y.types, "types"], [y.airlines, "airlines"], [y.airframes, "airframes"], [y.countries, "countries"], [y.days, "days"]];
  nums.forEach(([n, k], i) => {
    const x = 80 + (i % 3) * 320, yy = 520 + Math.floor(i / 3) * 210;
    g.fillStyle = "#f3f0e8"; g.font = `700 96px ${FONT}`; g.fillText(nf.format(n || 0), x, yy);
    g.fillStyle = "#959aa3"; g.font = `600 36px ${FONT}`; g.fillText(T(k), x, yy + 52);
  });
  yearFacts(y).forEach(([k, v], i) => {
    const yy = 1000 + i * 100;
    g.fillStyle = "#f0b429"; g.font = `600 30px ${FONT}`; g.fillText(k.toUpperCase(), 80, yy);
    g.fillStyle = "#f3f0e8"; g.font = `700 44px ${FONT}`; g.fillText(v, 80, yy + 50);
  });
  return new Promise(ok => cv.toBlob(ok, "image/png"));
}
async function shareYear(){
  ctlSound.press();
  const blob = await yearPicture(), name = `fallblatt-${yearData.year}.png`, file = new File([blob], name, {type: "image/png"});
  try {
    if (navigator.canShare && navigator.canShare({files: [file]})) return await navigator.share({files: [file], title: T("{y} in planes", {y: yearData.year})});
  } catch (e) { if (e && e.name === "AbortError") return; }
  const a = document.createElement("a"); a.href = URL.createObjectURL(blob); a.download = name; document.body.appendChild(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(a.href), 4000);
}
document.addEventListener("click", e => { if (e.target && e.target.id === "yShare") shareYear(); });

// Where to look (1.28): from the place to the plane on top, its compass direction and how high to look; a dial with
// north up, or, with the compass (secure pages only; iPhones ask first), turning with the phone so the arrow points
// at the plane.
let lookHeading = null, lookOn = false, lookRaf = 0, lookErr = "", lookErrAt = 0;
function lookAt(){
  if (!feat || !feat.o || feat.o.ac.lat == null) return null;
  const ac = feat.o.ac, kx = 111.32 * Math.cos(S.lat * Math.PI / 180), x = (ac.lon - S.lon) * kx, y = (ac.lat - S.lat) * 110.57;
  const km = Math.hypot(x, y), brg = (Math.atan2(x, y) * 180 / Math.PI + 360) % 360, alt = feat.o.alt;
  if (alt == null || km > 80) return null;
  const up = Math.round(Math.atan2(Math.max(0, alt) * .3048, Math.max(50, km * 1000)) * 180 / Math.PI);
  return {brg, up, km, alt, dir: ["N", "NE", "E", "SE", "S", "SW", "W", "NW"][Math.round(brg / 45) % 8]};
}
function drawLook(){
  lookRaf = 0;
  const box = $("look"), L = lookAt();
  box.hidden = !L || SIDEWAYS.matches;
  if (box.hidden) return;
  $("lookDir").textContent = T("LOOK {d} · {e}° UP", {d: L.dir, e: L.up});
  $("lookSub").textContent = T("{n} km away · {a}", {n: L.km < 10 ? L.km.toFixed(1) : Math.round(L.km), a: altitudeStr(L.alt).toLowerCase()}) + " · " +
    (lookErr && Date.now() - lookErrAt < 10000 ? lookErr : lookOn && lookHeading != null ? T("Turn until the arrow points up, then look that way.") : lookOn ? T("North is up.") : T("North is up. Hold the phone flat and tap Use the compass to turn it with you."));
  const cv = $("lookCv"), px = Math.min(3, devicePixelRatio || 1), sz = 96;
  if (cv.width !== sz * px) { cv.width = cv.height = sz * px; }
  const g = cv.getContext("2d"), turn = lookOn && lookHeading != null ? -lookHeading : 0;
  g.setTransform(px, 0, 0, px, 0, 0); g.clearRect(0, 0, sz, sz);
  g.translate(sz / 2, sz / 2);
  g.beginPath(); g.arc(0, 0, 44, 0, Math.PI * 2); g.fillStyle = "#0c0d0e"; g.fill(); g.strokeStyle = "rgba(255,255,255,.14)"; g.lineWidth = 1.5; g.stroke();
  g.save(); g.rotate(turn * Math.PI / 180);
  for (let i = 0; i < 8; i++) { g.save(); g.rotate(i * Math.PI / 4); g.fillStyle = "rgba(255,255,255,.25)"; g.fillRect(-1, -42, 2, i % 2 ? 4 : 7); g.restore(); }
  g.fillStyle = "#e0372c"; g.font = `700 12px ${FONT}`; g.textAlign = "center"; g.textBaseline = "middle"; g.fillText("N", 0, -30);
  g.rotate(L.brg * Math.PI / 180);
  g.fillStyle = "#f0b429"; g.beginPath(); g.moveTo(0, -36); g.lineTo(9, -14); g.lineTo(3, -14); g.lineTo(3, 14); g.lineTo(-3, 14); g.lineTo(-3, -14); g.lineTo(-9, -14); g.closePath(); g.fill();
  g.restore();
  $("lookBtn").hidden = lookOn || !window.isSecureContext || typeof DeviceOrientationEvent === "undefined";
  $("arBtn").hidden = !arPossible();
}
const lookSoon = () => { if (!lookRaf) lookRaf = requestAnimationFrame(drawLook); };
function lookHeadingFrom(e){
  let h = null;
  if (typeof e.webkitCompassHeading === "number") h = e.webkitCompassHeading;           // iPhone: degrees from north
  else if (e.absolute && typeof e.alpha === "number") h = (360 - e.alpha) % 360;         // Android: the alpha angle, absolute
  if (h == null) return;
  const so = (screen.orientation && screen.orientation.angle) || 0;
  h = (h + so + 360) % 360;
  if (lookHeading == null) lookHeading = h;
  else { const d = ((h - lookHeading + 540) % 360) - 180; lookHeading = (lookHeading + d * .25 + 360) % 360; }   // smoothed: compasses wobble
  lookSoon();
}
async function lookStart(quiet){
  if (!quiet) ctlSound.press();
  try {
    if (typeof DeviceOrientationEvent.requestPermission === "function" && await DeviceOrientationEvent.requestPermission() !== "granted") throw 0;
    addEventListener("ontouchstart" in window && "ondeviceorientationabsolute" in window ? "deviceorientationabsolute" : "deviceorientation", lookHeadingFrom);
    lookOn = true;
    setTimeout(() => { if (lookHeading == null) $("lookSub").textContent = T("The compass isn't available on this device."); }, 2500);
  } catch { $("lookSub").textContent = T("The compass isn't available on this device."); }
  lookSoon();
}
setInterval(() => { if (tab === "now" && document.visibilityState === "visible") lookSoon(); }, 1000);

/* ---------- Sky view (1.30): the camera, with a label on each plane ----------
   Each plane's direction from where the phone is (its own location, or the place in Settings) and its height, turned
   into the camera's picture with the phone's orientation: the W3C rotation (alpha, beta, gamma; the compass heading
   on iPhones), the back camera looking along the phone's -z. Positions are moved on to now with each plane's speed and
   track. Compasses are often a few degrees off: dragging the picture shifts the labels into place (kept per device). */
const arPossible = () => window.isSecureContext && !!(navigator.mediaDevices && navigator.mediaDevices.getUserMedia) && typeof DeviceOrientationEvent !== "undefined";
let arOn = false, arStream = null, arList = [], arListAt = 0, arAng = null, arWatch = null, arHere = null, arRaf = 0, arDrag = null;
let arOff = {h: 0, p: 0};
const AR_VFOV = 64;                                  // the back camera's vertical field of view, upright (degrees, typical)
function arFeed(list){ arList = list || []; arListAt = Date.now(); }
const arEvent = () => "ondeviceorientationabsolute" in window ? "deviceorientationabsolute" : "deviceorientation";
function arOrient(e){
  let a = e.alpha;
  if (typeof e.webkitCompassHeading === "number") a = 360 - e.webkitCompassHeading;       // iPhone: north from the compass
  else if (!e.absolute && e.type !== "deviceorientationabsolute") return;
  if (a == null || e.beta == null || e.gamma == null) return;
  if (!arAng) arAng = {a, b: e.beta, g: e.gamma};
  else {                                             // smoothed: compasses wobble
    const d = ((a - arAng.a + 540) % 360) - 180;
    arAng = {a: (arAng.a + d * .3 + 360) % 360, b: arAng.b + (e.beta - arAng.b) * .3, g: arAng.g + (e.gamma - arAng.g) * .3};
  }
}
async function arOpen(){
  ctlSound.press();
  const fail = () => { lookErr = T("Sky view needs the camera and the motion sensors, on the https address."); lookErrAt = Date.now(); lookSoon(); };
  try {
    if (typeof DeviceOrientationEvent.requestPermission === "function" && await DeviceOrientationEvent.requestPermission() !== "granted") return fail();
    arStream = await navigator.mediaDevices.getUserMedia({video: {facingMode: {ideal: "environment"}, width: {ideal: 1280}, height: {ideal: 1280}}, audio: false});
  } catch { return fail(); }
  try { arOff = {h: 0, p: 0, ...JSON.parse(localStorage.getItem("od.ar.off") || "{}")}; } catch {}
  const v = $("arVid"); v.srcObject = arStream; v.play().catch(() => {});
  $("arView").hidden = false; document.body.classList.add("arOpen"); arOn = true; arAng = null;
  $("arHint").textContent = T("Hold the phone up and look around. If the labels sit beside the planes, drag them into place.");
  addEventListener(arEvent(), arOrient);
  if (navigator.geolocation) arWatch = navigator.geolocation.watchPosition(p => { arHere = {lat: p.coords.latitude, lon: p.coords.longitude}; }, () => {}, {enableHighAccuracy: true, maximumAge: 15000});
  setTimeout(() => { if (arOn && !arAng) $("arHint").textContent = T("No compass reading yet: move the phone in a figure of eight."); }, 2500);
  arLoop();
}
function arClose(){
  if (!arOn) return;
  arOn = false; ctlSound.press();
  if (arStream) arStream.getTracks().forEach(t => t.stop());
  arStream = null; $("arVid").srcObject = null;
  removeEventListener(arEvent(), arOrient);
  if (arWatch != null && navigator.geolocation) navigator.geolocation.clearWatch(arWatch);
  arWatch = null; cancelAnimationFrame(arRaf);
  $("arView").hidden = true; document.body.classList.remove("arOpen");
}
// The rotation from the phone's axes to east-north-up (W3C DeviceOrientation, Z-X'-Y'' with alpha, beta, gamma).
function arMatrix(a, b, g){
  const r = Math.PI / 180, cA = Math.cos(a * r), sA = Math.sin(a * r), cB = Math.cos(b * r), sB = Math.sin(b * r), cG = Math.cos(g * r), sG = Math.sin(g * r);
  return [[cA * cG - sA * sB * sG, -cB * sA, cA * sG + cG * sA * sB],
          [cG * sA + cA * sB * sG, cA * cB, sA * sG - cA * cG * sB],
          [-cB * sG, sB, cB * cG]];
}
// Where a point (east, north, up in metres from the phone) falls on the screen: [x, y] or, behind the phone, the
// direction to turn ({edge: [dx, dy]}).
function arProject(e, n, u, R, W, H){
  const hh = arOff.h * Math.PI / 180, ce = Math.cos(hh), se = Math.sin(hh);
  const E = e * ce - n * se, N = e * se + n * ce, L = Math.hypot(E, N, u) || 1, p = [E / L, N / L, u / L];
  let vx = R[0][0] * p[0] + R[1][0] * p[1] + R[2][0] * p[2], vy = R[0][1] * p[0] + R[1][1] * p[1] + R[2][1] * p[2];
  const vz = R[0][2] * p[0] + R[1][2] * p[1] + R[2][2] * p[2];
  const so = ((screen.orientation && screen.orientation.angle) || window.orientation || 0) * Math.PI / 180;
  if (so) { const x = vx * Math.cos(so) + vy * Math.sin(so), y = -vx * Math.sin(so) + vy * Math.cos(so); vx = x; vy = y; }
  const f = (H / 2) / Math.tan(AR_VFOV / 2 * Math.PI / 180), shift = f * Math.tan(arOff.p * Math.PI / 180);
  if (vz > -.08) return {edge: [vx, -vy]};
  const x = W / 2 + f * vx / -vz, y = H / 2 - f * vy / -vz + shift;
  return x < -40 || x > W + 40 || y < -40 || y > H + 40 ? {edge: [x - W / 2, y - H / 2], x, y} : {x, y};
}
function arLoop(){
  if (!arOn) return;
  arRaf = requestAnimationFrame(arLoop);
  const cv = $("arCv"), W = cv.clientWidth, H = cv.clientHeight, px = Math.min(2, devicePixelRatio || 1);
  if (cv.width !== Math.round(W * px) || cv.height !== Math.round(H * px)) { cv.width = Math.round(W * px); cv.height = Math.round(H * px); }
  const g = cv.getContext("2d");
  g.setTransform(px, 0, 0, px, 0, 0); g.clearRect(0, 0, W, H);
  if (!arAng) return;
  const R = arMatrix(arAng.a, arAng.b, arAng.g), here = arHere || {lat: S.lat, lon: S.lon};
  const kx = 111320 * Math.cos(here.lat * Math.PI / 180), dt = (Date.now() - arListAt) / 1000, ground = sky && sky.elevation ? sky.elevation * .3048 : 0;
  const shown = [];
  for (const ac of arList) {
    if (ac.lat == null || ac.lon == null) continue;
    const alt = typeof ac.alt_baro === "number" ? ac.alt_baro : typeof ac.alt_geom === "number" ? ac.alt_geom : null;
    if (alt == null || alt < 0) continue;
    let e = (ac.lon - here.lon) * kx, n = (ac.lat - here.lat) * 110570;
    if (ac.gs && ac.track != null) {                     // on to now along its track
      const m = ac.gs * .5144 * Math.min(60, dt + (ac.seen_pos || 0)), t = ac.track * Math.PI / 180;
      e += m * Math.sin(t); n += m * Math.cos(t);
    }
    const d = Math.hypot(e, n);
    if (d > 60000) continue;
    const u = alt * .3048 - ground - d * d / (2 * 6371000) * .87;  // the earth's curve (with the usual refraction)
    const pr = arProject(e, n, u, R, W, H), isFeat = feat && feat.hex === ac.hex;
    if (pr.edge && !isFeat) continue;
    const info = (infoCache.get(ac.hex + "|" + String(ac.flight || "").trim().toUpperCase()) || {}).info || baseInfo(ac);
    shown.push({ac, d, pr, isFeat, name: info.flightNo || String(ac.flight || "").trim() || ac.r || ac.hex.toUpperCase(),
      sub: [shortType(info.type || TYPES[String(ac.t || "").toUpperCase()] || ac.t || ""), altitudeStr(alt).toLowerCase(), (d / 1000 < 10 ? (d / 1000).toFixed(1) : Math.round(d / 1000)) + " km"].filter(Boolean).join(" · ")});
  }
  shown.sort((a, b) => a.d - b.d);
  const boxes = [];
  g.textBaseline = "alphabetic";
  for (const s of shown.slice(0, 14)) {
    if (s.pr.edge) { arEdge(g, s, W, H); continue; }
    const {x, y} = s.pr;
    g.font = `700 15px ${FONT}`; const w1 = g.measureText(s.name).width; g.font = `500 12px ${FONT}`; const w2 = g.measureText(s.sub).width;
    const bw = Math.max(w1, w2) + 18, bh = 40;
    let bx = Math.min(W - bw - 6, Math.max(6, x - bw / 2)), by = y - 26 - bh;
    for (let k = 0; k < 8 && boxes.some(b => bx < b[0] + b[2] && bx + bw > b[0] && by < b[1] + b[3] && by + bh > b[1]); k++) by -= bh + 6;   // no overlaps
    boxes.push([bx, by, bw, bh]);
    const col = s.isFeat ? "#f0b429" : "rgba(255,255,255,.85)";
    g.strokeStyle = col; g.lineWidth = 1.5; g.beginPath(); g.moveTo(x, y - 6); g.lineTo(x, by + bh); g.stroke();
    g.beginPath(); g.arc(x, y, 6, 0, Math.PI * 2); g.stroke();
    g.fillStyle = s.isFeat ? "rgba(240,180,41,.92)" : "rgba(11,11,12,.78)"; rr(g, bx, by, bw, bh, 7); g.fill();
    g.fillStyle = s.isFeat ? "#111" : "#f3f0e8"; g.font = `700 15px ${FONT}`; g.fillText(s.name, bx + 9, by + 18);
    g.fillStyle = s.isFeat ? "#2a2108" : "#b9b3a3"; g.font = `500 12px ${FONT}`; g.fillText(s.sub, bx + 9, by + 33);
  }
  $("arCount").textContent = shown.length ? T("{n} planes around", {n: shown.length}) : T("No planes nearby right now.");
}
// The plane on top, out of the picture: an arrow at the edge pointing the way to turn.
function arEdge(g, s, W, H){
  const [dx, dy] = s.pr.edge, L = Math.hypot(dx, dy) || 1, ux = dx / L, uy = dy / L;
  const t = Math.min((W / 2 - 34) / Math.abs(ux || 1e-6), (H / 2 - 60) / Math.abs(uy || 1e-6)), x = W / 2 + ux * t, y = H / 2 + uy * t;
  g.save(); g.translate(x, y); g.rotate(Math.atan2(uy, ux));
  g.fillStyle = "#f0b429"; g.beginPath(); g.moveTo(18, 0); g.lineTo(-10, -12); g.lineTo(-4, 0); g.lineTo(-10, 12); g.closePath(); g.fill();
  g.restore();
  g.font = `700 13px ${FONT}`; g.fillStyle = "#f0b429"; g.textAlign = ux > .5 ? "right" : ux < -.5 ? "left" : "center";
  g.fillText(s.name, x - ux * 26, y - uy * 26 + 4); g.textAlign = "left";
}
const shortType = t => String(t || "").replace(/^(Airbus|Boeing|Embraer|Bombardier|De Havilland Canada|ATR) /i, "");
// Dragging the picture lines the labels up with the planes: sideways turns them, up and down lifts them.
function arDragStart(e){ arDrag = {x: e.clientX, y: e.clientY, h: arOff.h, p: arOff.p}; e.target.setPointerCapture && e.target.setPointerCapture(e.pointerId); }
function arDragMove(e){
  if (!arDrag) return;
  const H = $("arCv").clientHeight, f = (H / 2) / Math.tan(AR_VFOV / 2 * Math.PI / 180);
  arOff.h = arDrag.h - Math.atan((e.clientX - arDrag.x) / f) * 180 / Math.PI;
  arOff.p = arDrag.p + Math.atan((e.clientY - arDrag.y) / f) * 180 / Math.PI;
}
function arDragEnd(){ if (!arDrag) return; arDrag = null; try { localStorage.setItem("od.ar.off", JSON.stringify(arOff)); } catch {} }
$("arBtn").onclick = arOpen;
$("arClose").onclick = arClose;
$("arReset").onclick = () => { ctlSound.press(); arOff = {h: 0, p: 0}; try { localStorage.removeItem("od.ar.off"); } catch {} };
{ const cv = $("arCv");
  cv.addEventListener("pointerdown", arDragStart); cv.addEventListener("pointermove", arDragMove);
  cv.addEventListener("pointerup", arDragEnd); cv.addEventListener("pointercancel", arDragEnd); }
document.addEventListener("visibilitychange", () => { if (document.visibilityState !== "visible") arClose(); });

// A notification while the app is open: the service worker passes it on, and the page plays its chime (the airport bell
// for special planes) instead of the phone's notification sound.
if ("serviceWorker" in navigator) navigator.serviceWorker.addEventListener("message", e => {
  const d = e.data || {};
  if (d.type === "bell") { audioInit(); chime(d.kind === "emergency" ? "emergency" : d.kind === "fav" ? "fav" : "special", {force: true}); }
});

// The logbook is read now and then even with its tab closed: the tiers need it.
setInterval(() => { if (booted && tab !== "logbook") fetchLogbook(); }, 5 * 60000);

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
    if (t - (radar.listAt || 0) > 1000) { radar.listAt = t; renderRadarList(); }   // the list keeps up with the scope
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
  const ringTags = [];
  for (let r = 5; r <= range; r += 5) {
    g.strokeStyle = "rgba(255,255,255,.1)"; g.lineWidth = 1; g.beginPath(); g.arc(cx, cy, r * k, 0, TAU); g.stroke();
    if (r * k < R - 6) ringTags.push({text: `${r} km`, x: cx + Math.sin(.42) * r * k + 4, y: cy - Math.cos(.42) * r * k + 11});
  }
  g.setLineDash([8, 6]); g.strokeStyle = rgba(COL.amber, .6); g.lineWidth = 1.5;
  g.beginPath(); g.arc(cx, cy, (+S.radiusKm || 15) * k, 0, TAU); g.stroke(); g.setLineDash([]);
  airportPos();
  const ap = AP.code === clean(S.home).slice(0, 3) && AP.lat != null && AP.rwys.length ? AP : null;
  if (ap) {
    const u = rwyInUse();
    g.lineCap = "round"; g.lineWidth = 2.2;
    for (const r of ap.rwys) {
      const used = [r.a.id, r.b.id].some(id => u.arr.includes(id) || u.dep.includes(id));
      g.strokeStyle = used ? rgba(COL.amber, .75) : "rgba(255,255,255,.28)";
      const [x1, y1] = toXY(r.a.lat, r.a.lon), [x2, y2] = toXY(r.b.lat, r.b.lon); g.beginPath(); g.moveTo(x1, y1); g.lineTo(x2, y2); g.stroke();
    }
    const [ax, ay] = toXY(ap.lat, ap.lon);
    g.font = `700 11px ${FONT}`; g.fillStyle = "rgba(255,255,255,.42)"; g.strokeStyle = "rgba(6,7,8,.85)"; g.lineWidth = 3; g.lineJoin = "round";
    if (Math.hypot(ax - cx, ay - cy) < R - 28) { g.strokeText(S.home, ax + 10, ay + 16); g.fillText(S.home, ax + 10, ay + 16); radar.apBox = {x: ax + 9, y: ay + 6, w: 30, h: 14}; } else radar.apBox = null;
    g.lineCap = "butt";
  } else radar.apBox = null;
  const dt = Math.min(20, (now - radar.at) / 1000), shown = [];
  for (const o of radar.planes) {
    const ac = o.ac, th = (ac.track || 0) * Math.PI / 180, pos = radarPos(o, now, kx, ky);
    const [x, y] = toXY(pos.lat, pos.lon);
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
  const centre = {x: cx - 12, y: cy - 12, w: 24, h: 24}, compass = [0, 90, 180, 270].map(d => { const a = d * Math.PI / 180;
    return {x: cx + Math.sin(a) * (R - 12) - 10, y: cy - Math.cos(a) * (R - 12) - 10, w: 20, h: 20}; });   // N E S W stay readable
  ringLabels(g, ringTags, radarLabels(g, shown, cx, cy, R, {name: 11.5, alt: 10, gap: 11}, [centre, ...compass, ...(radar.apBox ? [radar.apBox] : [])]), 10.5);
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
]},
  {title: ["Display", "Anzeige"], cols: 2, items: [
    {k: "lang", type: "rotary", label: "Language", opts: LANGS},
    {k: "theme", type: "rotary", label: "Board style", opts: [["classic", "CLASSIC"], ["frankfurt", "FRANKFURT"], ["blue", "BLUE"]]},
    {k: "units", type: "switch", label: "Units", on: "metric", off: "aviation", upText: "METRIC", downText: "FT · KT"},
    {k: "logos", type: "switch", label: "Airline logos"},
    {k: "real", type: "switch", label: "Realistic look"},
    {k: "demo", type: "switch", label: "Demo mode", guard: true}]},
  {title: ["Flaps & sound", "Klappen & Klang"], cols: 2, items: [
    {k: "speedPct", type: "wheel", label: "Flap speed %", min: 10, max: 100, step: 5},
    {k: "quick", type: "switch", label: "Quick flaps"},
    {k: "imperfect", type: "switch", label: "Worn hardware"},
    {k: "sound", type: "switch", label: "Flap sound"},
    {k: "soundSet", type: "switch", label: "Sounds", on: "recorded", off: "classic", upText: "RECORDED", downText: "CLASSIC"},
    {k: "chimes", type: "switch", label: "Chimes"},
    {k: "bell", type: "switch", label: "Special bell", on: "airport", off: "classic", upText: "AIRPORT", downText: "CLASSIC"}]}];
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
    T("Planes taking off from and landing at {where}. Times: when they took off, and when they're expected on the ground.", {where: apName()}) +
    (AP.rwyLine ? " " + AP.rwyLine + "." : "");
  const deps = AP.deps.map(apRowHtml).join("") || `<li class="empty">${escH(T("No take-offs right now."))}</li>`;
  const arrs = AP.arrs.map(apRowHtml).join("") || `<li class="empty">${escH(T("No landings coming up right now."))}</li>`;
  const sig = sub + deps + arrs + S.units;
  if (sig === apSig) return;
  apSig = sig;
  $("apSub").textContent = sub; $("apDeps").innerHTML = deps; $("apArrs").innerHTML = arrs;
  for (const [k, list] of [["d", AP.deps], ["a", AP.arrs]]) for (let i = 0; i < NOW_ROWS; i++) {   // on flaps, on its side
    const e = list[i], id = c => `na${k}${i}${c}`, d = i * 60;
    setChars(id("time"), e && e.t ? hhmm(new Date(e.t)) : "", d);
    setChars(id("flight"), e ? apFlight(e) : "", d + 20);
    setChars(id("city"), e ? apPlace(e) : "", d + 60);
    setWord(id("st"), e ? e.st : i === 0 && AP.lat != null ? "NO TRAFFIC" : "", d + 100);
  }
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
  buildNowPages();
  renderFeatured(); renderAircraftInfo();
}
/* On its side, Now works like the board: the plane on top and one page under it, Recent flights (or Take-offs &
   landings) and This aircraft, picked with lamp buttons. The pages turn every 20 seconds, skipping This aircraft when
   there is no plane; a page picked by hand stays a minute and, empty, says so. */
// In the Airport style the pages are the board's: Take-offs & landings, Take-off and Landing, the last two putting that
// plane on top, with the runway screen. Upright, the lists are always there and a switch picks Take-off or Landing.
let nowPage = "lists", nowHold = 0, nowTurn = Date.now(), rotI = 0;
const isAcPage = p => p === "ac" || p === "dep" || p === "land";
const PAGE_NAME = {ac: "This<br>aircraft", dep: "Take-off", land: "Landing"};
const nowPageList = () => !airportMode() ? ["lists", "ac"] : SIDEWAYS.matches ? ["lists", "dep", "land"] : ["dep", "land"];
function appApPage(){ return !airportMode() ? "" : nowPage === "dep" ? "apdep" : nowPage === "land" ? "apland" : ""; }
const pageHas = p => p === "lists" || (p === "ac" ? !!feat : !!apFocus(p === "dep" ? "dep" : "arr"));
function buildNowPages(){
  const pages = nowPageList(), name = p => p === "lists" ? (airportMode() ? "Coming up" : "Recent<br>flights") : PAGE_NAME[p];
  const html = list => list.map(p => `<button class="cap" type="button" data-page="${p}">${T(name(p))}</button>`).join("");
  $("nowPages").innerHTML = html(pages);
  $("apPick").innerHTML = html(["dep", "land"]);
  for (const b of [...$("nowPages").children, ...$("apPick").children])
    b.onclick = () => { audioInit(); ctlSound.press(); nowHold = Date.now() + 60000; showNowPage(b.dataset.page); };
  $("t-now").classList.toggle("ap", airportMode());
  showNowPage(pages.includes(nowPage) ? nowPage : pages[0]);
}
function showNowPage(p){
  const was = nowPage;
  nowPage = p; nowTurn = Date.now();
  $("t-now").dataset.page = p;
  for (const b of [...$("nowPages").children, ...$("apPick").children]) b.setAttribute("aria-pressed", String(b.dataset.page === p));
  if (airportMode() && was !== p) apFeature();                // the plane on top: the one taking off or landing
  nowEmptyNote(); nowPanels();
  if (airportMode()) { fitSideways(); refreshPanels(); }   // the airport page's two titles take a line
}
// On its side the plane's flaps and the page under them are as big as the screen allows. A screen that is short for its
// width (a browser's bars, a wide phone) shows fewer list rows, so the flaps can grow until they fill the width; at
// least four rows.
function fitSideways(){
  const el = $("t-now");
  if (!SIDEWAYS.matches) return;
  const cs = getComputedStyle(el), availW = el.clientWidth - parseFloat(cs.paddingLeft) - parseFloat(cs.paddingRight);
  const titles = airportMode() && nowPage === "lists" ? 26 : 0;
  const availH = innerHeight - $("top").offsetHeight - 6 - 8 - 6 - titles;    // main's padding, the gap, a margin
  const fit = k => Math.floor(Math.max(200, Math.min(availW, availH / ((150 + lowUnits(k)) / 900))));
  let k = NOW_ROWS;
  while (k > 4 && fit(k) < availW - 1) k--;
  const W = fit(k), was = nowRows;
  setNowRows(k);
  el.style.setProperty("--fitW", W + "px"); el.style.setProperty("--lowH", Math.floor(W * lowUnits(k) / 900) + "px");
  if (k !== was) { clearTiles(); refreshPanels(true); }
  paintRwy();
}
// Only Now on its side: the tab open before comes back when the phone is upright again.
let sideFrom = null;
function sideways(){
  if (SIDEWAYS.matches) { if (tab !== "now") { sideFrom = tab; showTab("now"); } }
  else if (sideFrom) { const t = sideFrom; sideFrom = null; showTab(t); }
}
// Only the flaps of the page showing are drawn.
function nowPanels(){
  const on = tab === "now" && SIDEWAYS.matches, ap = airportMode(), lists = on && nowPage === "lists";
  let changed = false;
  for (const [P, show] of [[RECENTP, lists && !ap], [APP, lists && ap], [ACP, on && isAcPage(nowPage) && !!feat]])
    if (P.off === show) { P.off = !show; changed = true; }
  if (changed) refreshPanels(true);
}
function nowEmptyNote(){
  const el = $("nowEmpty"), empty = isAcPage(nowPage) && !feat;
  el.hidden = !empty;
  const say = nowPage === "dep" ? "No plane taking off right now" : nowPage === "land" ? "No plane landing right now" : "No plane to show right now";
  if (empty) el.innerHTML = `${escH(T(say))}<small>${escH(T("The page fills in as soon as there is one."))}</small>`;
}
// The pages turn every 20 seconds, like the board's (Airport: the lists, Take-off, the lists, Landing), skipping a page
// with no plane; upright, only the Airport style's Take-off and Landing turn.
setInterval(() => {
  const ap = airportMode();
  if (tab !== "now" || Date.now() < nowHold || (!SIDEWAYS.matches && !ap)) return;
  if (pageHas(nowPage) && Date.now() - nowTurn < 20000) return;
  const seq = !ap ? ["lists", "ac"] : SIDEWAYS.matches ? ["lists", "dep", "lists", "land"] : ["dep", "land"];
  for (let k = 1; k <= seq.length; k++) {
    const i = (rotI + k) % seq.length, p = seq[i];
    if (!pageHas(p)) continue;
    rotI = i;
    if (p !== nowPage) showNowPage(p); else nowTurn = Date.now();
    return;
  }
  nowTurn = Date.now();
}, 1000);
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
      if (it.k === "bell") { audioInit(); setTimeout(() => chime("special", {force: true, set: draft.bell}), 250); }   // hear it
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
  $("t-settings").classList.toggle("dirty", dirty);
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
    (GUEST ? `<p><b>${escH(T("Signed in as {name}.", {name: GUEST.name}))}</b> ${escH(T("Your location, Spotted today and logbook are your own, and this device remembers you."))}</p>` +
        `<p>${escH(T("To keep it like an app: on Android, Chrome's menu → Add to home screen; on an iPhone, Safari → Share → Add to Home Screen."))}</p>` +
        `<p>${escH(T("Privacy: the relay keeps your name, the devices you joined on, your settings and the planes spotted around your location, nothing else. Flight positions come from adsb.lol, adsb.fi and airplanes.live (ODbL), routes and aircraft from adsbdb, photos from airport-data.com."))}</p>` +
        `<div class="acts"><a class="cap big" href="/">${T("Full board")}</a><button class="cap big" type="button" id="signOut">${T("Sign out of this device")}</button></div>`
    : (ANDROID ? `<p>${escH(T("The Fallblatt app for Android, showing the relay at {host}.", {host: location.host}))}</p><div class="acts"><button class="cap big" type="button" id="relayBtn">${T("Change relay")}</button></div>`
      : `<p>${escH(T("On Android, install the Fallblatt app and open the file (allow installs from your browser once):"))} <a href="${APK_URL}">${T("download it")}</a>. ` +
        `${escH(T("On an iPhone, Safari → Share → Add to Home Screen."))}</p>`) +
    `<p>${escH(T("It needs your home Wi-Fi, because the flight data comes through the relay on your computer. The big board:"))} <a href="../">${escH(location.host)}/</a></p>`) +
    aboutHtml() + `</div>` +
    (accountsOk() ? `<div class="plate" style="--cols:1">${screws}<h3>${T("Account")}</h3><div id="acctBox"></div></div>` : "") +
    `<div class="plate" style="--cols:1">${screws}<h3>${T("Notifications")}</h3><div id="pushBox"></div></div>` +
    `<div class="plate" style="--cols:1">${screws}<h3>${T("Legend")}</h3><div class="lgbox">${legendHtml()}</div></div>` +
    `<div class="plate" style="--cols:1">${screws}<h3>${T("Patch notes")}</h3><div class="log">${changelogHtml()}</div></div>` +
    `<div class="acts"><button class="cap big" type="button" id="aboutBack">${T("Settings")}</button></div>`;
  if (GUEST) $("signOut").onclick = async () => {
    ctlSound.press();
    if (!confirm(accountsOk() && hasAccount ? T("Sign out of this device? Your profile stays; sign back in with your account.")
      : T("Sign out of this device? Your profile stays, but you'll need a new link to come back on it."))) return;
    try { await fetch(`${relay()}/signout`, {method: "POST"}); } catch {}
    try { localStorage.removeItem(SKEY); } catch {}
    location.reload();
  };
  if (ANDROID && !GUEST) $("relayBtn").onclick = () => { ctlSound.press(); window.OverheadAndroid.changeRelay(); };
  $("aboutBack").onclick = () => { ctlSound.press(); showTab("settings"); };
  renderAbout();
  renderPush();
  if (accountsOk()) accountBox($("acctBox"), a => { hasAccount = !!(a && a.user && (a.passkeys.length || a.password)); });
}
let hasAccount = false;
$("acFav").onclick = () => listSheet(featFacts());
$("acHide").onclick = () => listSheet(featFacts());
// The compass turns with the phone by itself where no permission is asked (Android): it starts on the first tap.
addEventListener("pointerup", function lookAuto(){
  removeEventListener("pointerup", lookAuto);
  if (!lookOn && window.isSecureContext && typeof DeviceOrientationEvent !== "undefined" && !/iPhone|iPad|Macintosh/.test(navigator.userAgent)) lookStart(true);
});
/* ---------- favourites and hidden planes (1.31, relay 31) ----------
   The lists live on the relay (userLists, shared code), so the boards and the notifications follow them. Here: a sheet
   to switch a plane's aircraft, type, airline or flight on or off as a favourite or hidden (from the lists' ⋯ and
   This aircraft), and the manager in Settings. */
const listsOk = () => !S.demo && !!relay() && (window.OVERHEAD_RELAY_VERSION || 0) >= 31;
const PUSH_KINDS = [["special", "Special planes (A380, 747, Beluga, Antonov, emergencies)"], ["watch", "Watchlist (police, ambulance, government, historic …)"],
  ["military", "Military planes"], ["fav", "Your favourites"], ["newtype", "Types never seen here"], ["low", "Very low passes"],
  ["quiet", "Quiet at night (22:00–07:00), except emergencies and special planes"]];
const PUSH_KIND_DEFAULTS = {special: true, watch: true, military: true, fav: true, newtype: false, low: false, quiet: true};
const KIND_NAME = {reg: "Aircraft", type: "Type", airline: "Airline", flight: "Flight"};
async function listsSave(next){
  const r = await fetch(`${relay()}/lists`, {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(next)});
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
  const j = await r.json();
  userLists = {fav: j.fav || [], hide: j.hide || [], at: Date.now(), v: userLists.v + 1};
  svSig = recentSig = ""; renderLists(); renderFeatured(); renderFavBox();
}
// The choices for one plane: its aircraft (registration), type, airline and flight, those it has.
function listChoices(x){
  const cs = clean(x.callsign || ""), al = (cs.match(/^([A-Z]{3})\d/) || [])[1] || "";
  return [["reg", x.reg, x.reg], ["type", x.typeCode, x.type || TYPES[x.typeCode] || x.typeCode],
    ["airline", al, x.airline || (AIRLINES[al] || [])[1] || al], ["flight", cs, x.flight || cs]].filter(c => c[1]).map(([k, v, n]) => ({k, v: clean(v), n: String(n || v)}));
}
const inList = (L, c) => L.some(i => i.k === c.k && clean(i.v).replace(/[\s-]/g, "") === c.v.replace(/[\s-]/g, ""));
function listSheet(x){
  if (!listsOk() || !x) return;
  ctlSound.press();
  const box = $("sheet"), ch = listChoices(x);
  const draw = () => {
    const btns = which => ch.map((c, i) => `<button class="cap${inList(userLists[which], c) ? " on" : ""}" type="button" data-w="${which}" data-i="${i}">` +
      `<small>${escH(T(KIND_NAME[c.k]))}</small>${escH(c.n)}</button>`).join("");
    box.innerHTML = `<div class="shBox" role="dialog" aria-modal="true"><h3>${escH(x.flight || x.reg || x.callsign || "")}</h3>` +
      `<p class="sum">${escH(T("Tap to switch on or off. Saved for all your devices and boards."))}</p>` +
      `<p class="shH">★ ${escH(T("Make a favourite"))}</p><div class="shRow">${btns("fav")}</div>` +
      `<p class="shH">⊘ ${escH(T("Hide from now on"))}</p><div class="shRow">${btns("hide")}</div>` +
      `<p class="note" id="shNote"></p><div class="acts"><button class="cap big go" type="button" id="shDone">${T("Done")}</button></div></div>`;
    for (const b of box.querySelectorAll("[data-w]")) b.onclick = async () => {
      const w = b.dataset.w, c = ch[+b.dataset.i], on = inList(userLists[w], c);
      ctlSound.toggle(!on);
      const next = {fav: userLists.fav.slice(), hide: userLists.hide.slice()};
      next[w] = on ? next[w].filter(i => !(i.k === c.k && clean(i.v).replace(/[\s-]/g, "") === c.v.replace(/[\s-]/g, ""))) : next[w].concat([c]);
      if (!on) { const o = w === "fav" ? "hide" : "fav"; next[o] = next[o].filter(i => !(i.k === c.k && clean(i.v) === c.v)); }   // not both at once
      try { await listsSave(next); draw(); } catch (e) { $("shNote").textContent = e.message; }
    };
    $("shDone").onclick = () => { ctlSound.press(); box.hidden = true; };
  };
  draw(); box.hidden = false;
  box.onclick = e => { if (e.target === box) box.hidden = true; };
}
// The ⋯ on the lists' rows, and This aircraft's buttons.
document.addEventListener("click", e => {
  const b = e.target && e.target.closest && e.target.closest("[data-more]");
  if (!b) return;
  e.stopPropagation();
  const id = b.dataset.more, x = spotted.concat(fullDay.list || []).find(r => (r.id || r.hex) === id);
  if (x) listSheet(x);
}, true);
function featFacts(){
  if (!feat || !feat.o) return null;
  const f = liveFacts(feat.o.ac, feat.info), d = detailsOf(feat.hex) || {};
  return {...f, reg: f.reg || d.reg, type: f.type || d.type, flight: f.flight || f.callsign};
}
// Settings → Favourites & hidden: the two lists, each entry with its kind and a ×, and a field to add one, with
// airlines and aircraft types to pick from.
function renderFavBox(){
  const box = $("favBox");
  if (!box) return;
  if (!listsOk()) { box.hidden = true; return; }
  box.hidden = false;
  const chips = (w) => userLists[w].length ? `<ul class="chips">${userLists[w].map((i, n) => `<li><small>${escH(T(KIND_NAME[i.k] || ""))}</small>${escH(i.n || i.v)}` +
    `<button type="button" data-rm="${w}:${n}" aria-label="${escH(T("Remove"))}">×</button></li>`).join("")}</ul>` : `<p class="sum">${escH(T("None yet."))}</p>`;
  box.innerHTML = `<div class="plate" style="--cols:1"><i></i><i></i><i></i><i></i><h3>${T("Favourites & hidden")}</h3>` +
    `<p>${escH(T("Favourites light up and get a chime and a notification. Hidden planes stay off the board, the lists and the notifications (they are still in the logbook)."))}</p>` +
    `<p class="shH">★ ${escH(T("Favourites"))}</p>${chips("fav")}<p class="shH">⊘ ${escH(T("Hidden"))}</p>${chips("hide")}` +
    `<div class="favAdd"><select id="favWhich"><option value="fav">★ ${escH(T("Favourites"))}</option><option value="hide">⊘ ${escH(T("Hidden"))}</option></select>` +
    `<input id="favIn" list="favDl" autocomplete="off" placeholder="${escH(T("Code or name, e.g. Austrian, A380, OE-LBN"))}">` +
    `<button class="cap" type="button" id="favAddBtn">${T("Add")}</button></div><p class="note" id="favNote"></p>` +
    `<datalist id="favDl">${Object.entries(AIRLINES).map(([c, a]) => `<option value="${escH(a[1])} (${c})">`).join("")}` +
    `${Object.entries(TYPES).map(([c, n]) => `<option value="${escH(n)} (${c})">`).join("")}</datalist></div>`;
  for (const b of box.querySelectorAll("[data-rm]")) b.onclick = () => {
    const [w, n] = b.dataset.rm.split(":"); ctlSound.press();
    const next = {fav: userLists.fav.slice(), hide: userLists.hide.slice()}; next[w].splice(+n, 1);
    listsSave(next).catch(e => { $("favNote").textContent = e.message; });
  };
  $("favAddBtn").onclick = () => {
    ctlSound.press();
    const c = parseListEntry($("favIn").value), w = $("favWhich").value;
    if (!c) { $("favNote").textContent = T("Code or name, e.g. Austrian, A380, OE-LBN"); return; }
    const next = {fav: userLists.fav.slice(), hide: userLists.hide.slice()};
    if (!inList(next[w], c)) next[w].push(c);
    listsSave(next).then(() => { $("favIn").value = ""; }).catch(e => { $("favNote").textContent = e.message; });
  };
}
// What was typed: "Austrian (AUA)" from the list, an airline or type code, a registration, a flight, or a name.
function parseListEntry(t){
  t = String(t || "").trim();
  if (!t) return null;
  const m = t.match(/\(([A-Z0-9]{2,4})\)\s*$/i), code = clean(m ? m[1] : t).replace(/\s/g, ""), name = m ? t.replace(/\s*\([^)]*\)\s*$/, "") : "";
  if (AIRLINES[code]) return {k: "airline", v: code, n: name || AIRLINES[code][1]};
  if (TYPES[code]) return {k: "type", v: code, n: name || TYPES[code]};
  const byName = Object.entries(AIRLINES).find(([, a]) => clean(a[1]) === clean(t));
  if (byName) return {k: "airline", v: byName[0], n: byName[1][1]};
  const tName = Object.entries(TYPES).find(([, n]) => clean(n) === clean(t));
  if (tName) return {k: "type", v: tName[0], n: tName[1]};
  const tWord = Object.entries(TYPES).find(([, n]) => (" " + clean(n) + " ").includes(" " + code + " "));   // A380, 787 ...
  if (tWord && !/^[A-Z]{3}\d/.test(code)) return {k: "type", v: tWord[0], n: tWord[1]};
  if (/^[A-Z0-9]{1,2}-[A-Z0-9]{2,5}$/i.test(t) || /^N\d{1,5}[A-Z]{0,2}$/i.test(t)) return {k: "reg", v: clean(t), n: clean(t)};
  if (/^[A-Z]{3}\d[A-Z0-9]{0,4}$/i.test(code) || /^[A-Z0-9]{2}\d{1,4}[A-Z]?$/i.test(code)) return {k: "flight", v: code, n: code};
  if (/^[A-Z][A-Z0-9]{2,3}$/i.test(code)) return {k: "type", v: code, n: code};
  return null;
}
// The old Favourites text moves into the lists once (relay 31).
async function listsMigrate(){
  if (!listsOk() || !String(S.favs || "").trim()) return;
  await listsLoad(true);
  const add = String(S.favs).split(/[,;\n]+/).map(parseListEntry).filter(Boolean).filter(c => !inList(userLists.fav, c));
  try {
    if (add.length) await listsSave({fav: userLists.fav.concat(add), hide: userLists.hide});
    S = {...S, favs: ""}; saveSettings();
  } catch {}
}

/* ---------- accounts (relay 30): a username, passkeys and a password, to sign in on a new device ----------
   The guest's profile is made by their invite link; the account is extra and their own choice (About, or the end of
   the welcome). Passkeys need https (the public address); a password works anywhere. Signing in on a new device is the
   relay's /signin page, linked from its "private" page. */
const b64u = buf => btoa(String.fromCharCode(...new Uint8Array(buf))).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
const ub64 = t => Uint8Array.from(atob(t.replace(/-/g, "+").replace(/_/g, "/") + "===".slice((t.length + 3) % 4)), c => c.charCodeAt(0));
const accountsOk = () => !!GUEST && (window.OVERHEAD_RELAY_VERSION || 0) >= 30;
const passkeysHere = () => window.isSecureContext && !!window.PublicKeyCredential;
async function acctPost(path, body){
  const r = await fetch(`${relay()}${path}`, {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(body || {})});
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(j.error || `HTTP ${r.status}`);
  return j;
}
const deviceName = () => { const u = navigator.userAgent;
  return /iPhone/.test(u) ? "iPhone" : /iPad/.test(u) ? "iPad" : /Android/.test(u) ? "Android" : /Macintosh/.test(u) ? "Mac" : /Windows/.test(u) ? "Windows" : "Device"; };
async function passkeyAdd(){
  const o = await acctPost("/account/passkey/begin");
  const c = await navigator.credentials.create({publicKey: {...o, challenge: ub64(o.challenge), user: {...o.user, id: ub64(o.user.id)},
    excludeCredentials: (o.excludeCredentials || []).map(x => ({...x, id: ub64(x.id)}))}});
  return acctPost("/account/passkey/finish", {id: c.id, clientDataJSON: b64u(c.response.clientDataJSON),
    attestationObject: b64u(c.response.attestationObject), name: deviceName()});
}
// The account panel, in About and in the welcome: create (a username), then passkeys and a password.
async function accountBox(el, onChange){
  let a = null;
  try { a = await (await fetch(`${relay()}/account`, {cache: "no-store"})).json(); } catch {}
  if (!a || a.home) { el.innerHTML = ""; return; }
  const draw = (note = "") => {
    const has = a.passkeys.length || a.password, pk = passkeysHere() && a.passkeysOk, field = (id, ph, type = "password", ac = "new-password") =>
      `<input class="acIn" id="${id}" type="${type}" autocomplete="${ac}" placeholder="${escH(T(ph))}">`;
    el.innerHTML = !a.user
      ? `<p>${escH(T("Create an account to sign in on a new phone or computer and find your place, logbook and settings there: with a passkey (Face ID, a fingerprint or the screen lock), and a password as a backup."))}</p>` +
        `${field("acUser", "Username", "text", "username")}<div class="acts"><button class="cap big go" type="button" id="acMake">${T("Create account")}</button></div>`
      : `<p><b>${escH(T("Your account: {user}", {user: a.user}))}</b></p>` +
        (has ? "" : `<p class="warn">${escH(T("Add a passkey or a password, or the account can't be used to sign in yet."))}</p>`) +
        (a.passkeys.length ? `<ul class="ranks plain acKeys">${a.passkeys.map(k => `<li><span class="name">${escH(k.name)}<span class="s">${escH(fmtDay(k.added))}</span></span>` +
          `<button class="cap small" type="button" data-rm="${escH(k.id)}">${T("Remove")}</button></li>`).join("")}</ul>` : "") +
        (pk ? `<div class="acts"><button class="cap big${a.passkeys.length ? "" : " go"}" type="button" id="acKey">${T("Add a passkey")}</button></div>`
          : `<p class="muted">${escH(T("Passkeys need the https address (the one in your invite link)."))}</p>`) +
        `<p><b>${escH(T("Password"))}</b></p>` + (a.password ? field("acCur", "Current password", "password", "current-password") : "") +
        `<input type="text" autocomplete="username" value="${escH(a.user)}" hidden>` + field("acPw", "New password") +
        `<div class="acts"><button class="cap big" type="button" id="acSetPw">${T(a.password ? "Change password" : "Set a password")}</button></div>` +
        `<p class="muted">${escH(T("On a new phone or computer, open {url} and sign in.", {url: location.origin + "/signin"}))}</p>`;
    el.insertAdjacentHTML("beforeend", `<p class="note" id="acNote" aria-live="polite">${escH(note)}</p>`);
    const say = t => { const n = el.querySelector("#acNote"); if (n) n.textContent = t; };
    const run = async (fn, ok) => { try { a = await fn(); draw(ok ? T(ok) : ""); if (onChange) onChange(a); } catch (e) { say(e && e.name === "NotAllowedError" ? T("Cancelled.") : (e && e.message) || String(e)); } };
    const q = id => el.querySelector("#" + id);
    if (q("acUser")) {
      q("acUser").value = String(GUEST.name || "").toLowerCase().replace(/[^a-z0-9._-]+/g, ".").replace(/^[._-]+|[._-]+$/g, "");
      q("acMake").onclick = () => { ctlSound.press(); run(() => acctPost("/account/user", {user: q("acUser").value})); };
    }
    if (q("acKey")) q("acKey").onclick = () => { ctlSound.press(); run(passkeyAdd, "Passkey added."); };
    if (q("acSetPw")) q("acSetPw").onclick = () => { ctlSound.press(); run(() => acctPost("/account/password", {password: q("acPw").value, current: q("acCur") ? q("acCur").value : ""}), "Saved."); };
    for (const b of el.querySelectorAll("[data-rm]")) b.onclick = () => { ctlSound.press(); run(() => acctPost("/account/passkey/remove", {id: b.dataset.rm})); };
  };
  draw();
  if (onChange) onChange(a);
}

/* ---------- notifications (relay 25): the evening summary and "worth going to the window" ----------
   Browser push, which only works on https (fallblatt.app). The service worker (sw.js next to the app) shows them. */
const PUSH_PREFS = "od.push.prefs";
async function pushSub(){
  if (!("serviceWorker" in navigator) || !("PushManager" in window)) return null;
  const reg = await navigator.serviceWorker.getRegistration("./");
  return reg ? reg.pushManager.getSubscription() : null;
}
const pushPossible = () => (window.OVERHEAD_RELAY_VERSION || 0) >= 25 && window.isSecureContext && "serviceWorker" in navigator &&
  "PushManager" in window && "Notification" in window && Notification.permission !== "denied";
// The service worker is registered as the app opens, so it is running by the time notifications are turned on (the
// first try used to fail while it was still starting, and the button had to be pressed twice).
let swReady = null;
function swRegister(){
  if (!swReady && pushPossible()) swReady = navigator.serviceWorker.register("sw.js", {scope: "./"}).then(() => navigator.serviceWorker.ready).catch(() => null);
  return swReady || Promise.resolve(null);
}
setTimeout(swRegister, 1500);
// Turn notifications on: permission, the service worker, the subscription, the relay. Returns an error text, or "".
async function enablePush(){
  try {
    if (await Notification.requestPermission() !== "granted") return T("Notifications are blocked for this site in the browser's settings.");
    const reg = await swRegister();
    if (!reg) return T("This browser can't show notifications. On an iPhone, add Fallblatt to the home screen first and open it from there.");
    const {key} = await fetchJSON(`${relay()}/push/key`, {}, 8000);
    const raw = Uint8Array.from(atob(key.replace(/-/g, "+").replace(/_/g, "/") + "===".slice((key.length + 3) % 4)), c => c.charCodeAt(0));
    let sub = null;
    for (let i = 0; i < 3 && !sub; i++) {              // a worker that has only just become active can refuse once
      try { sub = await reg.pushManager.subscribe({userVisibleOnly: true, applicationServerKey: raw}); }
      catch (e) { if (i === 2) throw e; await new Promise(r => setTimeout(r, 800)); }
    }
    let prefs = {summary: true, window: true, ...PUSH_KIND_DEFAULTS};
    try { prefs = {...prefs, ...JSON.parse(localStorage.getItem(PUSH_PREFS) || "{}")}; } catch {}
    const r = await sendSub(sub, prefs, "subscribe");
    return r.ok ? "" : `HTTP ${r.status}`;
  } catch (e) { return String(e && e.message || e); }
}
async function renderPush(){
  const box = $("pushBox");
  if (!box) return;
  const say = t => `<p>${escH(t)}</p>`;
  if ((window.OVERHEAD_RELAY_VERSION || 0) < 25) { box.innerHTML = say(T("The relay doesn't offer notifications yet.")); return; }
  if (!window.isSecureContext) { box.innerHTML = say(T("Notifications only work through the https address (the one in your invite link), not at home on the Wi-Fi address.")); return; }
  if (!("serviceWorker" in navigator) || !("PushManager" in window) || !("Notification" in window)) {
    box.innerHTML = say(T("This browser can't show notifications. On an iPhone, add Fallblatt to the home screen first and open it from there.")); return;
  }
  if (Notification.permission === "denied") { box.innerHTML = say(T("Notifications are blocked for this site in the browser's settings.")); return; }
  let prefs = {summary: true, window: true, ...PUSH_KIND_DEFAULTS};
  try { prefs = {...prefs, ...JSON.parse(localStorage.getItem(PUSH_PREFS) || "{}")}; } catch {}
  const sub = await pushSub().catch(() => null);
  const sw = (k, label) => `<label class="pushOpt"><input type="checkbox" data-p="${k}"${prefs[k] ? " checked" : ""}> ${escH(T(label))}</label>`;
  const bellNote = /Android/.test(navigator.userAgent) ? `<p class="sum">${escH(T("With the app open, a notification plays the bell. To hear it when the app is closed (Android): save the bell, then in Android's settings open Notifications → Chrome → fallblatt.app → Sound and pick it."))} ` +
    `<a href="airport-bell.wav" download="Fallblatt airport bell.wav">${escH(T("Save the bell"))}</a></p>` : "";
  box.innerHTML = say(T("A summary of your day at 22:30, and a nudge when something special is about to pass over.")) +
    (sub ? say(T("Notifications are on for this device.")) : "") + sw("summary", "Evening summary") + sw("window", "Worth going to the window") +
    ((window.OVERHEAD_RELAY_VERSION || 0) >= 31 ? `<div class="pushKinds"${prefs.window ? "" : " hidden"}><p class="sum"><b>${escH(T("Which notifications"))}</b> · ${escH(T("At most one every 15 minutes, except emergencies and special planes."))}</p>` +
      PUSH_KINDS.map(([k, l]) => sw(k, l)).join("") + `</div>` : "") +
    bellNote + `<div class="acts"><button class="cap big${sub ? "" : " go"}" type="button" id="pushBtn">${T(sub ? "Turn off" : "Turn on notifications")}</button></div><p class="note" id="pushNote"></p>`;
  for (const cb of box.querySelectorAll("[data-p]")) cb.onchange = async () => {
    ctlSound.toggle(cb.checked);
    prefs[cb.dataset.p] = cb.checked;
    if (cb.dataset.p === "window") { const pk = box.querySelector(".pushKinds"); if (pk) pk.hidden = !cb.checked; }
    try { localStorage.setItem(PUSH_PREFS, JSON.stringify(prefs)); } catch {}
    const cur = await pushSub().catch(() => null);
    if (cur) sendSub(cur, prefs, "subscribe");
  };
  $("pushBtn").onclick = async () => {
    ctlSound.press();
    const note = $("pushNote");
    try {
      if (sub) { await sendSub(sub, prefs, "unsubscribe"); await sub.unsubscribe(); return renderPush(); }
      note.textContent = T("Turning on …");
      const err = await enablePush();
      await renderPush();                                  // shows "on" straight away
      if (err && $("pushNote")) $("pushNote").textContent = err;
    } catch (e) { note.textContent = String(e && e.message || e); }
  };
}
function sendSub(sub, prefs, what){
  return fetch(`${relay()}/push/${what}`, {method: "POST", headers: {"Content-Type": "application/json"},
    body: JSON.stringify({subscription: sub.toJSON ? sub.toJSON() : sub, prefs, lang: LANG})});
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
  if (GUEST) S.located = true;                               // a guest who saved Settings has chosen their place
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

/* ---------- a guest's first visit: where to watch the sky ---------- */
// The greeting flips in on a row of flaps of its own: a drum with "!" just after Z, so the "!" (which also starts
// last) has the longest way to go, and its last few flips slow down (slowEnd) like a drum coasting to a stop.
const GREET_DRUM = " ABCDEFGHIJKLMNOPQRSTUVWXYZ!0123456789,.'-";
function greetText(){
  const first = String(GUEST.name || "").trim().split(/\s+/)[0] || "";
  const t = T("Hi {name}!", {name: first}).normalize("NFD").replace(/[\u0300-\u036f]/g, "").replace(/ß/g, "SS").toUpperCase();
  let out = [...t].filter(ch => GREET_DRUM.includes(ch)).join("").replace(/\s+/g, " ").trim();
  if (!out.endsWith("!")) out += "!";
  return out.length > 16 ? out.slice(0, 15).trim() + "!" : out;
}
// The row shows FALLBLATT until the welcome is opened, then turns to the greeting. The letters land in order, left to
// right: each flap starts so that it lands a beat after the one before it (a long way round the drum starts earlier);
// the "!" last, coasting to a stop. Blanks land whenever, they don't show.
const greetW = () => Math.max(greetText().length, 9);
const centred = (t, n) => (" ".repeat(Math.floor((n - t.length) / 2)) + t).padEnd(n);
const splashLeft = () => Math.max(0, (window.SPLASH_END || 0) - performance.now());
function greetFlaps(){
  const n = greetW(), step = 30, P = makePanel($("wHello"), n * step + 2 * 8, 62, 0);
  $("wHello").style.width = `min(100%, ${n * 34}px)`;
  def(P, "greet", {kind: "chars", n, dur: 62, drum: GREET_DRUM, loud: .6});
  placeRow(["greet"], [], 11, step, 1.45, 8);
  requestAnimationFrame(() => showPanel(P));
  setTimeout(() => { if (!greeted) rollTo(centred("FALLBLATT", n)); }, splashLeft() + 300);
}
let greeted = false;
// `dur` is the time of one flip (the board's 62 ms by default); the gaps between the letters scale with it, so the time
// to land scales too. `dry` only works out when the last letter would land.
const COAST = [3.4, 2.3, 1.6, 1.2];                   // the board's slow end: the last flips take this many times longer
function rollTo(text, dur = 62, dry = false){
  const k = dur / 62, per = Math.ceil(dur * pace() / 16.7) * 16.7;      // a flip lasts whole frames (60 a second)
  let land = 0;
  if (!dry) fields.greet.dur = dur;
  fields.greet.cells.forEach((c, i) => {
    const ch = text[i], flips = path(GREET_DRUM, c.cur, ch).length, bang = ch === "!";
    if (ch === " ") return dry || retarget(c, ch, 0);
    if (!flips) return;
    const run = (flips + (bang ? COAST.slice(0, flips).reduce((a, m) => a + m - 1, 0) : 0)) * per;   // the "!" coasts its last flips
    land = Math.max(land + (bang ? 520 : 170) * k, run + 150 * k);      // after the one before; never before it can
    if (!dry) { c.slowEnd = bang; retarget(c, ch, Math.max(0, (land - run) / pace())); }
  });
  return land;
}
// The greeting lands within about two seconds of the tap: from FALLBLATT the flaps turn faster for a longer way round.
const GREET_MS = 1700;                                 // plus the moment before it starts
function greetRoll(){
  greeted = true;
  const text = centred(greetText(), greetW());
  let dur = 62;
  while (dur > 17 && rollTo(text, dur, true) > GREET_MS) dur -= 3;       // the board's pace, or as much faster as it takes
  const land = rollTo(text, dur);
  setTimeout(() => { soundForced = false; }, land + 1800);
}
// From one step of the welcome to the next: the box grows or shrinks to the new step's height, which fades in.
function wSwap(from, to){
  const box = document.querySelector("#welcome .wbox"), h0 = box.offsetHeight;
  for (const e of [].concat(from)) e.hidden = true;
  to.hidden = false;
  to.classList.remove("wIn"); void to.offsetWidth; to.classList.add("wIn");
  const h1 = box.offsetHeight;
  if (REDUCED || Math.abs(h1 - h0) < 2) return;
  box.style.transition = "none"; box.style.height = h0 + "px"; box.style.overflow = "hidden"; void box.offsetHeight;
  box.style.transition = "height .6s cubic-bezier(.22,.8,.24,1)"; box.style.height = h1 + "px";
  setTimeout(() => { box.style.height = box.style.overflow = box.style.transition = ""; }, 650);
}
function welcome(){
  const box = $("welcome"), note = $("wNote"), first = String(GUEST.name || "").trim().split(/\s+/)[0] || GUEST.name;
  $("wHi").textContent = T("Hi {name}!", {name: GUEST.name});
  $("wFor").textContent = T("A board for {name}", {name: first});
  box.hidden = false;
  try { greetFlaps(); } catch {}
  $("wPlace").placeholder = T("London"); $("wHome").placeholder = "LHR"; $("wLat").placeholder = "51.5072"; $("wLon").placeholder = "-0.1276";
  for (const [id, k] of [["wPlace", "place"], ["wHome", "home"], ["wLat", "lat"], ["wLon", "lon"]])
    if (GUEST.settings && GUEST.settings[k] != null) $(id).value = GUEST.settings[k];
  // The tap that opens it also lets the browser play sound: the greeting is heard, whatever the sound setting.
  $("wOpen").onclick = () => {
    soundForced = true; audioInit();
    try { if (actx) actx.resume(); } catch {}
    $("wOpen").onclick = null; $("wOpen").classList.add("wGone");
    setTimeout(() => { try { greetRoll(); } catch {} }, 120);
    setTimeout(() => wSwap($("wOpen"), $("wStep1")), 650);
  };
  $("wLoc").onclick = async () => {
    ctlSound.press(); audioInit();
    $("wLoc").disabled = true; note.textContent = T("Finding out where you are …");
    try {
      const p = await hereNow(), lat = +(+p.lat).toFixed(4), lon = +(+p.lon).toFixed(4);
      let a = null;
      try { a = await nearestAirport(lat, lon); } catch {}
      $("wLat").value = lat; $("wLon").value = lon;
      if (a) { $("wHome").value = a.code; if (!$("wPlace").value) $("wPlace").value = a.city || a.name || ""; }
      note.textContent = (a ? T("Found you. The nearest airport is {name} ({code}).", {name: a.city || a.name, code: a.code}) : T("Found you.")) + " " + T("Check it, then Continue.");
    } catch (e) {
      note.textContent = (e.message || T("The location isn't available right now.")) + " " + T("Latitude and longitude please, e.g. 51.5072 and -0.1276.");
    } finally { $("wLoc").disabled = false; }
  };
  let sent = Promise.resolve();
  const num = v => parseFloat(String(v).replace(",", "."));
  $("wGo").onclick = () => {
    const lat = num($("wLat").value), lon = num($("wLon").value);
    if (!isFinite(lat) || !isFinite(lon) || Math.abs(lat) > 90 || Math.abs(lon) > 180) { note.textContent = T("Latitude and longitude please, e.g. 51.5072 and -0.1276."); $("wLat").focus(); return; }
    ctlSound.press();
    S = {...S, lat: +lat.toFixed(4), lon: +lon.toFixed(4), home: clean($("wHome").value).slice(0, 3) || S.home, place: $("wPlace").value.trim() || T("Home"), located: true};
    saveSettings();
    sent = saveMe(JSON.parse(localStorage.getItem(SKEY) || "{}"), true);
    if (pushPossible()) wSwap($("wStep1"), $("wPush")); else acctStep();
  };
  $("wPushYes").onclick = async () => {
    ctlSound.press();
    const n = $("wPushNote"); n.textContent = T("Turning on …");
    const err = await enablePush();
    if (err) { n.textContent = err; return; }
    n.textContent = T("Notifications are on.");
    setTimeout(acctStep, 700);
  };
  $("wPushNo").onclick = () => { ctlSound.press(); acctStep(); };
  function acctStep(){              // an account, so the logbook comes along to a new phone (https only: passkeys)
    if (!accountsOk() || !passkeysHere()) return pick();
    wSwap([$("wStep1"), $("wPush")], $("wAcct"));
    $("wAcctNo").textContent = T("Not now");
    $("wAcctNo").onclick = () => { ctlSound.press(); pick(); };
    accountBox($("wAcctBox"), a => { if (a && a.user && (a.passkeys.length || a.password)) $("wAcctNo").textContent = T("Continue"); });
  }
  function pick(){                // the phone app or the full board: a phone is offered the app, a computer the board
    wSwap([$("wStep1"), $("wPush"), $("wAcct")], $("wPick"));
    const phone = matchMedia("(pointer: coarse)").matches && Math.min(screen.width, screen.height) < 600, b = $(phone ? "wApp" : "wBoard");
    b.classList.add("go"); b.setAttribute("aria-pressed", "true");
  }
  const go = to => { ctlSound.press(); sent.finally(() => setTimeout(to, 150)); };      // once the profile has the place
  $("wApp").onclick = () => go(() => {                   // the board loads in around the new place, its flaps turning in
    box.classList.add("wDone");
    setTimeout(() => { box.hidden = true; box.classList.remove("wDone"); updateWhere(); run(); }, 380);
  });
  $("wBoard").onclick = () => go(() => { location.href = "/"; });
  $("wLater").onclick = () => { ctlSound.press(); box.hidden = true; run(); showTab("settings"); };
}

/* ---------- tabs: the board's push buttons along the bottom ---------- */
// Small line icons over the tab names (drawn in the button's ink): a plane, a list, a book, a radar scope, a cogwheel.
const ICON = d => `<svg class="ico" viewBox="0 0 24 24" aria-hidden="true">${d}</svg>`;
const TAB_ICONS = {
  now: ICON('<path d="M21 15.5v-1.8l-7.6-4.7V3.7a1.4 1.4 0 0 0-2.8 0V9l-7.6 4.7v1.8l7.6-2.3v5.3l-2 1.5V21l3.4-1 3.4 1v-1.5l-2-1.5v-5.3z" fill="currentColor"/>'),
  today: ICON('<path d="M5 6h14M5 12h14M5 18h9" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" fill="none"/>'),
  logbook: ICON('<path d="M6 3.5h10.5a1.5 1.5 0 0 1 1.5 1.5v15H7.5A1.5 1.5 0 0 1 6 18.5zM6 18.5A1.5 1.5 0 0 1 7.5 17H18M9.5 8h5" stroke="currentColor" stroke-width="2" stroke-linejoin="round" stroke-linecap="round" fill="none"/>'),
  radar: ICON('<circle cx="12" cy="12" r="8.5" stroke="currentColor" stroke-width="2" fill="none"/><circle cx="12" cy="12" r="4" stroke="currentColor" stroke-width="1.6" fill="none"/><path d="M12 12 18 6" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>'),
  settings: ICON('<path d="M18.97 9.84 21.66 10.34 21.66 13.66 18.97 14.16 18.46 15.41 20.00 17.66 17.66 20.00 15.41 18.46 14.16 18.97 13.66 21.66 10.34 21.66 9.84 18.97 8.59 18.46 6.34 20.00 4.00 17.66 5.54 15.41 5.03 14.16 2.34 13.66 2.34 10.34 5.03 9.84 5.54 8.59 4.00 6.34 6.34 4.00 8.59 5.54 9.84 5.03 10.34 2.34 13.66 2.34 14.16 5.03 15.41 5.54 17.66 4.00 20.00 6.34 18.46 8.59Z" stroke="currentColor" stroke-width="1.9" stroke-linejoin="round" fill="none"/><circle cx="12" cy="12" r="3.1" stroke="currentColor" stroke-width="1.9" fill="none"/>'),
};
const TABS = [["now", "Now"], ["today", "Today"], ["logbook", "Logbook"], ["radar", "Radar"], ["settings", "Settings"]];
let tab = "now", tabTimer = null;
function buildTabs(){
  $("tabRow").innerHTML = TABS.map(([t, name]) => `<button class="cap${T(name).length > 9 ? " long" : ""}" type="button" data-tab="${t}">${TAB_ICONS[t]}<span>${T(name)}</span></button>`).join("");
  for (const b of $("tabRow").children) b.onclick = () => { audioInit(); ctlSound.press(); showTab(b.dataset.tab); };
}
function pingNow(on){ const b = $("tabRow").querySelector('[data-tab="now"]'); if (b) b.classList.toggle("ping", on); }
function showTab(t){
  if (!TABS.some(x => x[0] === t) && t !== "about" || SIDEWAYS.matches) t = "now";
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
  document.body.dataset.health = dot.dataset.state || "";          // the line under the lists only shows when it matters
  const bad = ["off", "warn", "demo"].includes(dot.dataset.state), al = $("sideAlert");     // on its side: only when something is wrong
  al.hidden = !bad; al.dataset.state = dot.dataset.state;
  if (bad && al.textContent !== line) al.textContent = line;
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
  if (!booted) return;                    // still in the welcome
  sayHello();
  if (document.visibilityState !== "visible") return;
  // A phone may throw away a hidden page's canvas pictures (and the cached flap faces): draw everything afresh.
  clearTiles(); refreshPanels(true); drawMark(); if (tab === "radar") radarSize();
  poll(true); if (relayV5()) { syncSightings(); fetchLogbook(); }          // back: everything at once again
});
// iPhones allow sound only from a tap as the finger lifts (touchend, click), not as it lands.
["pointerdown", "touchstart", "touchend", "click", "keydown"].forEach(ev => addEventListener(ev, () => audioInit(), {passive: true, capture: true}));
let resizeQ = 0;
addEventListener("resize", () => {
  cancelAnimationFrame(resizeQ);
  resizeQ = requestAnimationFrame(() => { fitSideways(); clearTiles(); refreshPanels(true); drawMark(); if (tab === "radar") radarSize(); });
});

// A newer version published: a banner above the tabs, tap to update.
function watchVersion(show){             // as on the board: ask for this page now and then, nothing reloads by itself
  const check = async () => {
    try {
      const r = await fetch(location.pathname + "?v=" + Date.now(), {cache: "no-store"});
      const m = /\{v: "(\d[\d.]*)"/.exec(await r.text());
      if (m && m[1] !== VERSION) show(m[1]);
    } catch {}
  };
  setTimeout(check, 60000);
  setInterval(check, 10 * 60000);
}
watchVersion(v => { const b = $("newVer"); b.textContent = T("New version · tap to update") + ` (${v})`; b.hidden = false; b.onclick = () => location.reload(); });
async function start(){
  try {
    await Promise.race([
      Promise.all(["700 40px", "600 20px", "400 40px"].map(s => document.fonts.load(`${s} ${(THEMES[S.theme] || THEMES.classic).font}`))),
      new Promise(r => setTimeout(r, 1200))      // not long: the board shouldn't wait for a slow font
    ]);
  } catch {}
  pickLang();
  for (const el of document.querySelectorAll("[data-t]")) el.textContent = T(el.dataset.t);
  buildTabs(); buildSvTools(); buildRadarLegend(); buildSaveBar(); updateWhere();
  for (const b of document.querySelectorAll("#modes [data-mode]")) b.onclick = () => setMode(b.dataset.mode);
  showModes();
  applyTheme();
  showTab(location.hash.slice(1) || "now");
  if (window.splashGo) window.splashGo();          // the board is ready: the opening's plane takes off
  // A new guest first goes through the welcome: the board stays hidden and starts (fetching, drawing) once the place is
  // confirmed and the phone app picked, or the welcome put off ("Later").
  if (!located()) return welcome();
  run();
}
let booted = false;
function run(){
  if (booted) return;
  booted = true;
  if (GUEST) $("setSum").textContent = T("Turn the knobs and flip the switches, then press Save. Settings are kept with your profile, on every device you use.");
  fitSideways();
  if (document.fonts && document.fonts.addEventListener) document.fonts.addEventListener("loadingdone", () => { clearTiles(); refreshPanels(true); });
  if (S.demo || !relayV5()) spotted = S.demo ? demoLog() : [];
  tickClock(); setInterval(tickClock, 1000);
  renderFeatured(); renderLists(); updateFooter();
  if (relayV5()) syncSightings();
  dlog("info", `App started · ${S.demo ? "demo mode" : relay() ? "using the home relay" : "no relay"} · watching ${S.lat.toFixed(4)}, ${S.lon.toFixed(4)}, radius ${+S.radiusKm || 15} km`);
  // Every data source at once, so the board fills as fast as it can (positions, today's list, the logbook the tiers
  // need, the hello that tells the relay where this screen looks); then each on its usual timer.
  poll(true); if (relayV5()) fetchLogbook(); if (airportMode()) airportPos(); sayHello();
  listsLoad(true).then(() => { listsMigrate(); renderFavBox(); svSig = recentSig = ""; renderLists(); });
  setInterval(sayHello, 60000);
  // Turned on its side or upright again: the flaps take the other arrangement (the page's columns are CSS).
  const turned = () => { sideways(); heroLayout(); buildNowPages(); nowPanels(); fitSideways(); clearTiles(); refreshPanels(true); paintRwy(); if (tab === "radar") radarSize(); };
  SIDEWAYS.addEventListener ? SIDEWAYS.addEventListener("change", turned) : SIDEWAYS.addListener && SIDEWAYS.addListener(turned);
}
start();
})();
</script>
</body>
</html>
