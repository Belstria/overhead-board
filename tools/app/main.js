(() => {
"use strict";
const $ = id => document.getElementById(id);
const escH = s => String(s ?? "").replace(/[&<>"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
//@E1

/* ---------- settings: kept on this phone (and, for a guest, with their profile on the relay) ---------- */
// A guest (friends and family, let in with a personal invite link; relay 19+) gets their name and saved settings
// from the relay instead of the home location, and their settings go back to it, so their other devices know them.
//@L:flag
const LIGHT = false;                  // the light version (tools/light/build.py): the same app without the split flaps
//@L:end
const GUEST = window.OVERHEAD_GUEST || null;
const DEFAULTS = {place:"Vienna", lat:48.2085, lon:16.3731, radiusKm:15, home:"VIE", maxAltFt:60000, units:"metric", sound:true, soundSet:"recorded", bell:"airport", real:true, speedPct:85, quick:false, refreshS:5,
  logos:true, overKm:1, demo:false, daylight:false, theme:"classic", palette:"", finish:"", badge:"", ticket:"", favs:"", chimes:true, ding:true, imperfect:true, airtimeMin:3, mode:"overhead", lang:"auto",
  night:true, nightFrom:"22:30", nightTo:"07:00"};
const SKEY = (LIGHT ? "od.light.settings" : "od.app.settings") + (GUEST ? ".g." + GUEST.id : "");   // each guest's own, in a shared browser
// The light version has no flaps: these stay fixed there, and aren't sent to the profile (the app and the board keep theirs).
const LIGHT_FIXED = {real: false, imperfect: false, quick: false, theme: "classic", finish: "", soundSet: "recorded"};
function loadSettings(){
  let saved = {};
  try { saved = JSON.parse(localStorage.getItem(SKEY) || "{}") || {}; } catch {}
  const {mode, live, livePrev, daylight, ...shared} = GUEST && GUEST.settings || {};      // the style (1.40) and Daylight (1.66) stay this device's own
  return overRule({...DEFAULTS, ...shared, ...saved, ...(LIGHT ? LIGHT_FIXED : {})});
}
// 1.84: OVERHEAD became within 1 km at any height or 45° up; settings saved with the old 3 km move to 1 km, once.
function overRule(s){ if (s.overRule == null) { if (+s.overKm === 3) s.overKm = 1; s.overRule = 2; } return s; }
// A guest's settings go to their profile a moment after a change, always with their place (`located` once they have
// set one), so the relay knows where to count their planes even when it happens to be the default spot (locSet, E12).
function saveMe(changed, now){
  if (!GUEST) return Promise.resolve();
  const {live, livePrev, mode, daylight, ...rest} = changed;   // following the phone, the style and Daylight are this device's own
  changed = rest;
  if (LIGHT) for (const k of [...Object.keys(LIGHT_FIXED), "sound"]) delete changed[k];
  return meSend(S.located ? {...changed, ...locSet(), located: true} : changed, now);   // kept until the relay has it (1.64)
}
const located = () => !GUEST || !!S.located;
function saveSettings(){
  const changed = settingsChanged({});                // 1.68: the board's own rules, shared (E12)
  if (GUEST && S.located) Object.assign(changed, locSet());
  try { localStorage.setItem(SKEY, JSON.stringify(changed)); } catch {}
  return saveMe(changed);
}
Object.assign(DEFAULTS, window.OVERHEAD_DEFAULTS || {});  // location etc. supplied by the home relay
let S = loadSettings();
S.logos = true;                                      // airline logos are always on (1.54: the switch went)
let meBase = {...S};                                 // the settings as last saved (1.64)
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

/* ---------- the app's log: Settings → About → Log (1.80) ---------- */
const DIAG = {log: [], polls: [], closest: null, page: false};
// Each line has a kind for the Log page's filters: "net" (the relay, the sources, routes), "sky" (Sky view, Where to
// look) or "" (the rest); guessed from its words when not given.
const LOG_NET = /\b(relay|sources?|positions?|adsb\.?(lol|fi)?|adsbdb|airplanes\.live|AvioADSB|Flightradar24|routes?|offline|online|HTTP|timed out)\b/i;
function dlog(level, msg, kind){
  msg = String(msg);
  DIAG.log.unshift({t: Date.now(), level, msg, kind: kind ?? (/^(Sky view|Where to look)/.test(msg) ? "sky" : LOG_NET.test(msg) ? "net" : "")});
  if (DIAG.log.length > 400) DIAG.log.length = 400;
  if (DIAG.page) logSoon();
}
const scheduleDiag = () => {};
// Night mode (1.57): on a phone quiet hours only, the sounds check nightOn as on the board; no dimming.
let nightOn = false;
function nightCheck(){
  const mins = v => { const [h, m] = String(v || "").split(":").map(Number); return (h || 0) * 60 + (m || 0); };
  const d = new Date(), n = d.getHours() * 60 + d.getMinutes(), a = mins(S.nightFrom), b = mins(S.nightTo);
  nightOn = !!S.night && a !== b && (a < b ? n >= a && n < b : n >= a || n < b);
}
nightCheck(); setInterval(() => nightCheck(), 30000);
//@E2
//@E33

/* ---------- split-flap panels ----------
   The flaps are drawn exactly as on the board, on canvases set into the page: the plane overhead, the clock, and the
   counters on Spotted today and the Logbook. Each panel is laid out in its own units and scaled to its width. */
//@L:engine1
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
//@L:end
// 1.64: screen readers hear what the flaps say. Each panel's label is its name and the text its flaps are turning to
// ("The plane overhead: OS 802, Austrian, FLYING BY, …"), refreshed every few seconds; before, only the name.
function panelSpeech(){
  if (typeof panels === "undefined") return;
  for (const P of panels) {
    if (P.off || !P.el.isConnected) continue;
    const name = P.el.dataset.al ?? (P.el.dataset.al = P.el.getAttribute("aria-label") || "");
    const parts = P.ids.map(id => fields[id]).filter(f => f.kind !== "logo" && !["tier", "trend", "lamp"].includes(f.words)).map(f => {
      const t = f.cells.map(c => c.target ?? c.cur ?? "").join("").replace(/\s+/g, " ").trim();
      if (!t || /^[-|/ ]+$/.test(t)) return "";                 // empty, or "/" for not known
      const lab = Array.isArray(f.label) && f.label[0] ? T(f.label[0]) + " " : "";
      return lab + (f.kind === "word" ? T(t.split("|").pop()) : t);      // airline words are "EK|EMIRATES"
    }).filter(Boolean);
    const say = T(name) + (parts.length ? ": " + parts.join(", ") : "");
    if (P.el.getAttribute("aria-label") !== say) P.el.setAttribute("aria-label", say);
  }
}
setInterval(panelSpeech, 4000);
// The plane overhead: the board's top half, in eight rows for a phone held upright and, on its side, in three rows
// across the whole width (like the board's top half, with a page under it).
const UM = 14;                                   // margin, in panel units (the panel is 390 units wide)
const HERO = makePanel($("hero"), 390, 404, 10.5);
def(HERO, "flight",  {kind:"chars", n:7, dur:82, label:["Flight","Flug"], loud:1});
def(HERO, "remarks", {kind:"word",  n:6.3, dur:70, words:"remarks", label:["Status",""], loud:1});
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
// 1.82.2 (Dave): no Points field before the remarks (1.73.1-1.82.1); points show when they come in, on the score strip.
def(HERO, "seen",    {kind:"chars", n:19, dur:60, style:"amber", label:["Remarks",""]});
def(HERO, "toGo",    {kind:"chars", n:9, dur:70, drum:DRUM_ALT, align:"right", label:["To go",""]});
fields.toGo.hidden = true;                       // filled by the shared code, not shown on the phone
const SIDEWAYS = window.matchMedia ? matchMedia("(orientation: landscape) and (max-height: 600px)") : {matches: false};
function heroLayout(){
  const wide = SIDEWAYS.matches;
  HERO.w = wide ? 900 : 390; HERO.h = wide ? 150 : 448;
  fields.seen.hidden = wide;                    // on its side the three rows are full
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
  placeRow(["seen"], [], 411, 17.4, 1.45, UM);
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
  def(RECENTP, `nl${i}remarks`, {kind:"word",  n:10, dur:60, words:"remarks", small:true, loud:.5, label:lab("Remarks")});
  placeRow(["time", "flight", "from", "to", "type", "remarks"].map(c => `nl${i}${c}`), [.8, .8, .8, .8, .8], 18 + i * 30, s, 1.45, UM);
}
const APP = makePanel($("apP"), 900, 196);
for (const k of ["d", "a"]) for (let i = 0; i < NOW_ROWS; i++) {
  const dep = k === "d", lab = en => i === 0 ? [en, ""] : null, s = 13.2, id = c => `na${k}${i}${c}`;
  def(APP, id("time"),   {kind:"chars", n:5, drum:DRUM_DIGIT, dur:60, style:"amber", loud:.5, label:lab(dep ? "Time" : "Due")});
  def(APP, id("flight"), {kind:"chars", n:7, dur:60, loud:.5, label:lab("Flight")});
  def(APP, id("city"),   {kind:"chars", n:10, dur:60, loud:.5, label:lab(dep ? "To" : "From")});
  def(APP, id("st"),     {kind:"word",  n:8, dur:60, words:"remarks", small:true, loud:.5, label:lab("Status")});
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
// Upright, the take-offs and the landings are two flap panels of their own (the board's rows, a phone's width).
const APDP = makePanel($("apDP"), 390, 166), APAP = makePanel($("apAP"), 390, 166);
for (const [P, k] of [[APDP, "d"], [APAP, "a"]]) for (let i = 0; i < 5; i++) {     // AP_ROWS (defined further down)
  const dep = k === "d", lab = en => i === 0 ? [en, ""] : null, s = 13, id = c => `nu${k}${i}${c}`;
  def(P, id("time"),   {kind:"chars", n:5, drum:DRUM_DIGIT, dur:60, style:"amber", loud:.5, label:lab(dep ? "Time" : "Due")});
  def(P, id("flight"), {kind:"chars", n:7, dur:60, loud:.5, label:lab("Flight")});
  def(P, id("city"),   {kind:"chars", n:7, dur:60, loud:.5, label:lab(dep ? "To" : "From")});
  def(P, id("st"),     {kind:"word",  n:7, dur:60, words:"remarks", small:true, loud:.5, label:lab("Status")});
  placeRow(["time", "flight", "city", "st"].map(id), [.4, .4, .4], 18 + i * 30, s, 1.45, UM);
}
RECENTP.off = APP.off = ACP.off = APDP.off = APAP.off = true;
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
//@L:engine2
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
//@L:end
//@E6
//@E8
//@L:static
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
  g.fillStyle = COL.labelInk || COL.amber; g.fillText(a, 0, 0);          // 1.66: darker on Daylight's cream
  if (b) { g.fillStyle = COL.labelEn; g.fillText(b, wa + gap, 0); }
  g.restore();
  if ("letterSpacing" in g) g.letterSpacing = "0px";
}
//@L:end
//@E9
//@L:metal
/* ---------- the metal: brushed, a little worn, as a tile the page is painted with ---------- */
let metalUrl = "";
function metalTile(){
  const T = 600, d = Math.min(2, window.devicePixelRatio || 1), cv = document.createElement("canvas");
  cv.width = cv.height = Math.round(T * d);
  const g = cv.getContext("2d");
  g.scale(d, d);
  g.fillStyle = METAL[1]; g.fillRect(0, 0, T, T);
  const rnd = (seed => () => (seed = (seed * 1103515245 + 12345) & 0x7fffffff) / 0x7fffffff)(1234567);
  if (themeNow().leather) leatherGrain(g, T, T, rnd, false);    // 1.72: First Class's leather
  else {
  g.lineWidth = .7;                                         // brushed grain, wrapping round the tile's edges
  for (let i = 0; i < 700; i++) {
    const y = 1 + rnd() * (T - 2), x = rnd() * T, len = 60 + rnd() * 380, light = rnd() < .5;
    g.strokeStyle = light ? `rgba(255,255,255,${.012 + rnd() * .03})` : `rgba(0,0,0,${.03 + rnd() * .06})`;
    for (const dx of [0, -T]) { g.beginPath(); g.moveTo(x + dx, y); g.lineTo(x + dx + len, y); g.stroke(); }
  }
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
//@L:end
function drawMark(){
  const cv = $("mark"), d = window.devicePixelRatio || 1, s = 40;
  cv.width = cv.height = Math.round(s * d);
  const g = cv.getContext("2d");
  g.setTransform(d, 0, 0, d, 0, 0);
  pictogram(g, 0, 0, s, S.badge);                        // 1.61: the title badge takes the plane's place
  badgeIcons();                                          // and the browser tab's icon
}
//@E10

/* ---------- board styles ---------- */
function applyTheme(){
  applyLook();
  const T = themeNow();
  FONT = T.font; FLAP.splice(0, 4, ...T.flap); METAL = T.metal;
  COL.ink = T.ink; COL.amber = T.accent; COL.labelEn = T.label2; COL.labelInk = T.pageAccent || null;
  const root = document.documentElement.style;
  root.setProperty("--f-board", T.font); root.setProperty("--amber", T.pageAccent || T.accent); root.setProperty("--ink", daylightOn() ? "#191919" : T.ink);
  document.documentElement.classList.toggle("daylight", daylightOn());   // 1.66: the page's own colours (head.html)
  document.documentElement.classList.toggle("leather", !!T.leather && !daylightOn());   // 1.72: First Class's seams
  document.documentElement.classList.toggle("gilt", !!T.gilt && !daylightOn());         // 1.72: Gold leaf's rim
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
    const j = await fetchJSON(`${relay()}/sightings?over=${overKm()}&deg=${OVER_DEG}${apiWanted() ? "&api=1" : ""}${sightPlaceQ()}`, {}, 8000);
    if (j.fr24 === false) apiOff();
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
    const j = await fetchJSON(`${relay()}/sightings?all=1&over=${overKm()}&deg=${OVER_DEG}${apiWanted() ? "&api=1" : ""}${sightPlaceQ(allPlaces)}`, {}, 20000);
    fullDay = {at: now, rev: String(j.rev), date: j.date || null, list: (j.entries || []).map(fromRelay), all: allPlaces, stats: j.stats || null};
    if (j.stats && !allPlaces) relayStats = j.stats;
    renderToday();
  } catch (e) { dlog("warn", `Couldn't read the whole day from the relay: ${netError(e, "relay")}`); }
  finally { fullDay.busy = false; }
}
function dayList(){
  if (liveWaiting()) return [];                      // 1.90: live location before its first fix: nothing from the old spot
  const shown = l => userLists.hide.length ? l.filter(e => !isHidden(e)) : l;      // hidden planes stay in the logbook, not in the lists
  if (!relayV5() || !fullDay.list || fullDay.date !== sightDay || fullDay.all) return shown(spotted);
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
  // 1.84: the ding says "look up": once, as the plane on top becomes overhead or approaching (as on the board)
  if (!alert && !feat.dinged && (mode === "over" || mode === "soon")) { feat.dinged = true; seatbeltDing(); }
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
function chip(r, more = ""){              // the status word in this language; its colours by the English name
  if (!r && more) return `<span class="chip">${escH(more)}</span>`;
  const L = REMARK_LOOK[r] || {};
  const bg = L.fill ? `background:linear-gradient(${L.fill[0]},${L.fill[1]});` : "";
  const icon = AP_ICON[r] ? `<i class="apic">${apSvg(AP_ICON[r])}</i>` : "";        // taking off or landing, as on the flaps (1.49: the board's pictograms)
  return `<span class="chip" style="${bg}color:${L.fg || "var(--ink)"}">${icon}${escH(T(r) + (more ? " · " + more : ""))}</span>`;
}
const distText = d => d == null ? "" : (+d < 10 ? (+d).toFixed(1) : String(Math.round(d))) + " km";
const altText = ft => typeof ft === "number" ? altNum(ft) + (S.units === "metric" ? " m" : " ft") : "";
/* 1.95 (to-do #115, Dave's pick 1b): the lists are a timeline. Each plane is a slim row on a rail, its node in its
   remark's colour: the time, the flight, the route's codes and the remark, then quietly its airline, type and closest
   pass. A tap opens its card in place (Dave's option 1); the airline, places and type open theirs from the card. A
   plane without a flight number goes by its registration (or its owner); without a route the row says why. */
const tlKey = e => String(e.id || e.hex || "");
const plainCode = s => String(s || "").toUpperCase().replace(/[^A-Z0-9]/g, "");
const noFlightNo = e => { const f = plainCode(e.flight); return !f || f === plainCode(e.reg) || f === plainCode(e.hex); };     // it flies under its registration
const rowName = e => noFlightNo(e) ? e.reg || e.owner || e.flight || String(e.hex || "").toUpperCase() : e.flight || plainCode(e.callsign);
const noRoute = e => T(noFlightNo(e) ? "No route: private or local flight" : "Route not known");
const tlNode = e => lampOf(remarkFor(e)) || "#55585e";
function rowInner(e){
  const r = remarkFor(e), done = e.done !== false, name = rowName(e);
  const rt = e.from || e.to ? `<span class="rt"><b>${escH(code3(e.from) || "···")}</b><i>→</i><b>${escH(code3(e.to) || "···")}</b></span>`
    : `<span class="rt no">${done ? escH(noRoute(e)) : ""}</span>`;
  const l2 = [e.airline || (e.owner !== name ? e.owner : ""), e.type, distText(e.minDist), altText(e.altAtMin), allPlaces && e.place ? "◉ " + placeName(e.place) : ""];
  return `<div class="l1"><time>${escH(e.time || "")}</time><b class="f">${escH(name)}</b>${rt}<span class="rk">${r ? escH(T(r)) : ""}</span></div>` +
    `<div class="l2">${escH(l2.filter(Boolean).join(" · "))}</div>`;
}
const rowHtml = e => `<li class="fl" data-more="${escH(tlKey(e))}" style="--node:${tlNode(e)}" tabindex="0">${rowInner(e)}</li>`;
const rowSig = e => [e.id || e.hex, e.time, e.flight, e.callsign, e.airline, e.owner, e.type, e.reg, code3(e.from), code3(e.to), e.from && e.from.city, e.to && e.to.city,
  e.minDist, e.altAtMin, remarkFor(e), e.done, e.place].join("|");
// The card in the list: 1.94's info card (D's): the photo (Planespotters' first; it opens the whole plane card, so only
// its credit links to Planespotters) with the flight, airline and remark on it, the route band and three boxes.
const tlPic = e => planePic({hex: e.hex, r: e.reg, t: e.typeCode, desc: e.desc}, {reg: e.reg, type: e.type}, detailsOf(e.hex) || {photo: e.photo}, tlLate);
const tlCardSig = e => { const p = tlPic(e); return [rowSig(e), S.units, p.src, p.kind, p.by].join("|"); };
// The rows' photos are asked for ahead, one at a time: the relay asks Planespotters once a second for every screen
// (a TV's plane on top too), so a card opens with its own without crowding anyone out.
let tlAsking = false;
function tlAhead(list){
  if (tlAsking || !psOk()) return;
  const e = list.find(x => x.reg && !psPhotos.has(String(x.reg).trim().toUpperCase()));
  if (!e) return;
  tlAsking = true;                               // once answered, the model's picture for one without a photo, then the next
  psPhoto(e.reg, e.hex, () => setTimeout(() => { tlAsking = false; tlPic(e); renderRecent(); }, 1500));
}
function tlAgo(e){
  const m = Math.max(0, Math.floor((Date.now() - (e.ts || 0)) / 6e4));
  return m < 1 ? T("just now") : m < 60 ? T("{n} min ago", {n: m}) : T("{h} h {m} min ago", {h: Math.floor(m / 60), m: m % 60});
}
function tlCardHtml(e){
  const r = remarkFor(e), name = rowName(e);
  const card = infoCard({pic: tlPic(e), picAttr: " data-full", title: name, sub: e.airline || (e.owner !== name ? e.owner || "" : ""), subAttr: e.airline ? " data-al" : "",
    chip: chipHtml(r), band: e.from || e.to ? [routeEnd(e.from, "from"), "", routeEnd(e.to, "to")] : e.done !== false ? noRoute(e) : null,
    tiles: [["Aircraft", shortType(e.type), "", e.type ? " data-ty" : ""], ["Closest", distText(e.minDist)], ["Height", altText(e.altAtMin)]]});
  return `<div class="tlCard cardish"><i class="tlBg"></i><p class="tlK"><span>${escH(e.time || "")} · <span data-ago>${escH(tlAgo(e))}</span></span>` +
    `<button type="button" class="tlX" data-fold aria-label="${escH(T("Close"))}">${DD}</button></p>${card}</div>`;
}
const cardLi = e => `<li class="fl open" data-more="${escH(tlKey(e))}" style="--node:${tlNode(e)}">${tlCardHtml(e)}</li>`;
// The groups: the quarter hour (Recent flights) or the hour (Today), the one under way marked Now. A row's time is
// the relay's clock, so "now" is worked out on that clock from the newest row.
const tlMin = e => { const m = /^(\d\d):(\d\d)/.exec(e.time || ""), d = new Date(e.ts || 0); return m ? +m[1] * 60 + +m[2] : d.getHours() * 60 + d.getMinutes(); };
const tlHm = m => `${String(Math.floor(m / 60) % 24).padStart(2, "0")}:${String(m % 60).padStart(2, "0")}`;
function tlHtml(list, span, open){
  const top = list[0], now = top ? (tlMin(top) + Math.floor(Date.now() / 6e4) - Math.floor((top.ts || 0) / 6e4)) % 1440 : -1;
  let html = "", last = null;
  for (const e of list) {
    const g = Math.floor(tlMin(e) / span);
    if (g !== last) {
      last = g;
      const isNow = g === Math.floor(now / span) && Date.now() - (e.ts || 0) < span * 6e4;
      html += `<li class="tg">${isNow ? `<b>${escH(T("Now"))}</b> · ` : ""}${tlHm(g * span)} – ${tlHm(g * span + span)}</li>`;
    }
    html += tlKey(e) === open ? cardLi(e) : rowHtml(e);
  }
  return html;
}
// The empty list: why, on the rail (the newest-first line it will be)
const tlState = (head, title, text, find) => `<li class="tg"><b>${escH(head)}</b></li><li class="st${find ? " find" : ""}">${title ? `<b>${escH(title)}</b>` : ""}${escH(text)}</li>`;
const tlFinding = () => tlState(T("Now"), T("Finding where you are …"), T("The planes show once live location has found you."), true);
const tlNothing = () => tlState(T("Today"), T("Nothing spotted yet"), T("Every plane that comes within {n} km joins this line, the newest on top.", {n: +S.radiusKm || 15}));
const tlOpenId = {recent: "", svList: ""};      // each list's open card (one at a time)
let tlTok = 0, tlRunning = 0, tlCap = 0, tlAgain = false;       // the last tap; openings and foldings under way (a redraw waits for them)
const tlBusy = () => tlRunning > 0 && Date.now() < tlCap;
// The list's rows; its open card stays as it is (the same element) while what it shows hasn't changed.
function tlFill(L, html, open){
  const sig = open ? tlCardSig(open) : "", old = L.querySelector("li.fl.open");
  const keep = old && open && old.dataset.more === tlKey(open) && L.dataset.card === sig ? old : null;
  L.innerHTML = html;
  const now = L.querySelector("li.fl.open");
  if (keep && now) now.replaceWith(keep);
  else if (now) tlWire(now);
  L.dataset.card = sig;
}
const tlWire = li => { for (const im of li.querySelectorAll(".cPicW img")) im.onerror = () => picFailed(im, tlLate); };
// A photo found late (Planespotters' answer, the model's picture): an open card takes it.
function tlLate(){ if (tlOpenId.recent || tlOpenId.svList) { renderRecent(); renderToday(); } }
function tlDone(){ if (!tlBusy() && tlAgain) { tlAgain = false; renderRecent(); renderToday(); } }

/* Now: the plane overhead on flaps, its photo and details, and the latest sightings. */
let recentSig = "";
function renderRecent(){
  const all = dayList().filter(e => !e.sample || S.demo), list = all.slice(0, 8), L = $("recent");
  // 1.95: the heading counts the last hour; the link at the end goes to Today, with the whole day's count
  const hour = all.filter(e => Date.now() - (e.ts || 0) < 36e5).length, day = Math.max(all.length, spotted.length >= 400 && relayStats ? relayStats.planes || 0 : 0);
  const head = all.length ? T(hour ? "{n} in the last hour" : "None in the last hour", {n: nf.format(hour)}) : "", link = T(day === 1 ? "1 plane today ›" : "All {n} planes today ›", {n: nf.format(day)});
  if ($("recentN").textContent !== head) $("recentN").textContent = head;
  if ($("recentAll").textContent !== link) $("recentAll").textContent = link;
  $("recentFoot").hidden = !all.length;
  tlAhead(list);
  const open = list.find(e => tlKey(e) === tlOpenId.recent);
  if (!open) tlOpenId.recent = "";
  const ago = open && L.querySelector("li.open [data-ago]"), agoT = open ? tlAgo(open) : "";
  if (ago && ago.textContent !== agoT) ago.textContent = agoT;
  const sig = list.map(rowSig).join("~") + S.units + liveWaiting() + "|" + Math.floor(Date.now() / 9e5) + "|" + (open ? tlCardSig(open) : "");
  if (sig === recentSig) return;
  for (let i = 0; i < NOW_ROWS; i++) {           // the same, on flaps (the phone on its side)
    const e = list[i], d = i * 150, id = c => `nl${i}${c}`;
    setChars(id("time"), e ? e.time || "" : "", d);
    setChars(id("flight"), e ? e.flight || String(e.hex || "").toUpperCase() : "", d + 60);
    const done = !!e && e.done !== false;
    setChars(id("from"), e ? orNA(e.from && (e.from.city || e.from.code), done) : "", d + 120);
    setChars(id("to"), e ? orNA(e.to && (e.to.city || e.to.code), done) : "", d + 180);
    setChars(id("type"), e ? orNA(e.type, done) : "", d + 240);
    setWord(id("remarks"), e ? remarkFor(e) : "", d + 300);
  }
  if (tlBusy()) { tlAgain = true; return; }
  recentSig = sig;
  tlFill(L, list.length ? tlHtml(list, 15, tlOpenId.recent) : liveWaiting() ? tlFinding() : tlNothing(), open);
}
$("recentAll").onclick = () => { ctlSound.nav(); showTab("today"); };
let shownPhoto = null;
function renderAircraftInfo(){
  $("acSec").hidden = !feat;
  nowEmptyNote(); nowPanels(); skyRowRender();
  if (!feat) return;
  const info = feat.info || baseInfo(feat.o.ac), d = detailsOf(feat.hex) || {};
  // 1.93: Planespotters' photo first (not on the runway screen, which has no room for its credit), its credit a link
  const p = planePic(feat.o.ac, info, d, () => renderAircraftInfo(), !!rwyE()), src = p.src, a = $("photoLink");
  $("photoCr").innerHTML = picCreditHtml(p);
  if (p.kind === "ps") Object.assign(a, {href: p.link, target: "_blank", rel: "noopener"}); else a.removeAttribute("href");
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
      img.onerror = () => { scr.classList.remove("has"); if (p.kind === "ps" && img.getAttribute("src") === src) { psBad.add(src); renderAircraftInfo(); } };
      img.src = src;
    } else img.removeAttribute("src");
  }
  paintRwy();
  const done = !!info.done && detailsDone(feat.hex);           // "/": looked up, not known (1.48)
  setChars("naReg", orNA(info.reg || d.reg, done));
  setChars("naHex", feat.hex.toUpperCase(), 60);
  setChars("naFlight", info.flightNo || "", 120);
  setChars("naType", orNA(d.type || info.type, done), 180);
  setChars("naOwner", orNA(liveryLine(info) || d.owner || info.airline, done), 240);
  setChars("naCountry", orNA(d.country, done), 300);
  setChars("naRoute", info.from && info.to ? `${code3(info.from)} - ${code3(info.to)}` : done ? NA : "", 360);
}

// The runway screen of the Take-off and Landing pages, as on the board: the runways, the plane and its track, the photo
// inset (drawCover is the board's, which the app doesn't copy).
function drawCover(g, img, x, y, w, h){
  const sc = Math.max(w / img.naturalWidth, h / img.naturalHeight), iw = img.naturalWidth * sc, ih = img.naturalHeight * sc;
  g.drawImage(img, x + (w - iw) / 2, y + (h - ih) / 2, iw, ih);
}
let rwyKey = "";
function rwyE(){ return airportMode() && (nowPage === "dep" || nowPage === "land") && feat && feat.apE && AP.rwys.length && AP.lat != null ? feat.apE : null; }
function paintRwy(){
  const scr = $("screen"), cv = $("rwyCv"), img = $("photo");
  const e = rwyE();
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
  try { if (paintRunwayScreen(g, w, h, e, photo)) rwyAgain(() => { rwyKey = ""; paintRwy(); }); }   // the photo sliding, the plane moving
  catch (err) { scr.classList.remove("rwyOn"); }
}

/* Spotted today */
let svFilter = "all", svSig = "";
// Today's list: this place (as Now), or every place once the whole day has come in for them (1.42: until then it
// stays empty instead of showing this place's planes and jumping).
function todayList(){
  if (!allPlaces) return dayList();
  if (!fullDay.all || !fullDay.list) return [];
  return userLists.hide.length ? fullDay.list.filter(e => !isHidden(e)) : fullDay.list;
}
function svData(){
  const real = todayList().filter(e => !e.sample || S.demo), hit = svQuery ? real.filter(e => spotMatch(e, svQuery)) : real;
  const isOver = overEntry;      // 1.72: Special is special planes only; favourites have their own
  const counts = {all: hit.length, over: hit.filter(isOver).length, special: hit.filter(isSpecialPlane).length, fav: hit.filter(isFav).length};
  const rows = hit.filter(svFilter === "over" ? isOver : svFilter === "special" ? isSpecialPlane : svFilter === "fav" ? isFav : () => true);
  return {real, rows, counts};
}
//@E27
const SV_TOOLS = [["all", "All"], ["over", "Overhead"], ["special", "Special"], ["fav", "Favourites"]];
function buildSvTools(){
  const box = $("svTools");
  box.innerHTML = svFindHtml() + `<div class="seg svFilters" role="group">` + SV_TOOLS.map(([k, t]) => `<button type="button" data-t="${k}" aria-pressed="false">${T(t)}</button>`).join("") + `</div>`;   // 1.73: a segmented bar
  svFindWire(box, () => { svSig = ""; renderToday(); });
  for (const b of box.querySelectorAll("[data-t]")) b.onclick = () => {
    ctlSound.click();
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
// 1.78.2: the most seen aircraft types today (up to three, "A320 ×12"), counted from the day's list
function topTypes(list){
  const c = new Map();
  for (const e of list) { const k = e.typeCode || clean(e.type); if (k) c.set(k, (c.get(k) || 0) + 1); }
  // 1.87.2.1: only types seen twice or more; a day of one of each has no most seen
  return [...c].filter(x => x[1] > 1).sort((a, b) => b[1] - a[1]).slice(0, 3).map(([k, n]) => `${shortType(TYPES[k] || k)} ×${n}`).join(" · ")
    || (c.size ? T("No type twice yet") : "");
}
function todayNumbers(){
  const st = relayV5() && (allPlaces ? fullDay.all && fullDay.stats : !liveWaiting() && relayStats), list = todayList();
  if (st) {
    const name = x => x ? fromRelay(x).flight : "";
    const t = st.topAirline, tn = t ? shortAirline(t.name || (AIRLINES[t.code] || [])[1] || t.code) : "";
    return {planes: st.planes, airlines: st.airlines, types: st.types, over: st.overhead, facts: [
      ["Lowest pass", "Tiefster", st.lowest ? `${name(st.lowest)} · ${altText(st.lowest.altAtMin)}` : ""],   // 1.78.2: no busiest hour, no first
      ["Highest pass", "Höchster", st.highest ? `${name(st.highest)} · ${altText(st.highest.altAtMin)}` : ""],
      ["Fastest", "Schnellster", st.fastest ? `${name(st.fastest)} · ${speedStr(st.fastest.maxSpeed).toLowerCase()}` : ""],
      ["Most seen airline", "", t ? (t.count > 1 ? `${tn} · ${t.count}` : T("No airline twice yet")) : ""],
      ["Most seen types", "", topTypes(list)],
      ["New in the logbook", "Neu", st.newTypes || st.newAirlines ? T("{a} types · {b} airlines", {a: st.newTypes, b: st.newAirlines}) : T("Nothing new yet")]]};
  }
  const uniq = fn => new Set(list.map(fn).filter(Boolean)).size;
  const withAlt = list.filter(e => typeof e.altAtMin === "number");
  const low = withAlt.reduce((a, e) => !a || e.altAtMin < a.altAtMin ? e : a, null);
  const high = withAlt.reduce((a, e) => !a || e.altAtMin > a.altAtMin ? e : a, null);
  return {planes: list.length, airlines: uniq(e => e.airlineCode || clean(e.airline)), types: uniq(e => e.typeCode || clean(e.type)),
    over: list.filter(overEntry).length, facts: [
      ["Lowest pass", "Tiefster", low ? `${low.flight} · ${altText(low.altAtMin)}` : ""],
      ["Highest pass", "Höchster", high ? `${high.flight} · ${altText(high.altAtMin)}` : ""],
      ["Most seen types", "", topTypes(list)]]};
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
  for (const b of $("svTools").querySelectorAll("[data-t]")) {
    const k = b.dataset.t, n = d.counts[k];
    const text = `${T(SV_TOOLS.find(t => t[0] === k)[1])}${n != null ? " " + nf.format(n) : ""}`;
    if (b.textContent !== text) b.textContent = text;
    b.setAttribute("aria-pressed", String(k === svFilter));
  }
  $("svSum").textContent = spottedSummary();
  const ap = $("svPlaces");
  if (ap) {
    const seenFrom = ((lbData() || {}).places || []).filter(([k, n]) => n > 0).length;
    ap.hidden = !placesRelay() || !places.list.length && !S.live && placeKeyNow() === "home" && seenFrom < 2;
    const [one, all] = ap.children;
    one.textContent = placeLabel(); all.textContent = T("All places");
    one.setAttribute("aria-pressed", String(!allPlaces)); all.setAttribute("aria-pressed", String(allPlaces));
  }
  // 1.95: the same timeline as Now, by the hour (a whole day reads better so), and the same card in place
  const L = $("svList"), open = d.rows.find(e => tlKey(e) === tlOpenId.svList);
  if (!open) tlOpenId.svList = "";
  const ago = open && L.querySelector("li.open [data-ago]"), agoT = open ? tlAgo(open) : "";
  if (ago && ago.textContent !== agoT) ago.textContent = agoT;
  const sig = svFilter + svQuery + S.units + allPlaces + liveWaiting() + "|" + Math.floor(Date.now() / 36e5) + "|" + (open ? tlCardSig(open) : "") + d.rows.map(rowSig).join("~");
  if (sig === svSig) return;
  const waiting = allPlaces && !(fullDay.all && fullDay.list);
  // 1.55 (to-do #72): every place's list keeps this place's on show, dimmed, until it has come in
  if (waiting && L.children.length && !L.querySelector(".st")) return void L.classList.add("wait");
  if (tlBusy()) { tlAgain = true; return; }
  svSig = sig;
  L.classList.remove("wait");
  if (!waiting) L.style.minHeight = "";
  tlFill(L, waiting ? tlState(T("Today"), "", T("Loading …")) : d.rows.length ? tlHtml(d.rows, 60, tlOpenId.svList)
    : liveWaiting() && !allPlaces ? tlFinding() : svFilter === "all" && !svQuery ? tlNothing() : tlState(T("Today"), "", T("None of today's planes match this filter yet.")), open);
}
function renderLists(){
  renderRecent();
  if (tab === "today") renderToday();
}

/* Logbook */
//@E28
// The logbook by place (1.42, relay 37): lbPlace, lbPlaceData and lbPlaceOk come with the board's code.
async function fetchLogbook(){
  if (!S.demo && relayV5()) {
    try { lbCache = await fetchJSON(`${relay()}/logbook`, {}, 8000); lbError = ""; }
    catch (e) { lbError = netError(e, "relay"); }
    if (lbPlace && lbPlaceOk() && tab === "logbook") {
      try { lbPlaceData[lbPlace] = await fetchJSON(lbPlaceUrl(lbPlace), {}, 12000); } catch {}
    }
  }
  if (feat) setWord("tier", tierOf(feat.o.ac, feat.info));             // the tier needs the logbook
  achCheck((lbData() || {}).game); medalNudge((lbData() || {}).game);
  renderLogbook(); renderGame();
}
let lbSig = "", lbView = "logbook";
// 1.97.1.1 (to-do #130): the places list can arrive after the Logbook's first draw; its bar (the places are chips) then shows at once.
placesHooks.push(() => { if (tab === "logbook") renderLogbook(); });
// 1.55 (to-do #65): the Logbook tab shows one of the board's four logbook views at a time, picked in a row that stays
// put (Logbook, Collection, Records, Week & month); the places are a second row, only under Logbook.
function lbViewsBar(){
  // 1.72: Collection and Records on the Spotters' Club page; 1.74: Week & month in the period card
  const bar = $("lbViews"), views = LB_VIEWS.filter(v => v !== "review" && !(gameOk() && (v === "collection" || v === "records")));
  if (!views.includes(lbView)) lbView = "logbook";
  const sig = JSON.stringify([views, lbView, LANG]);
  bar.hidden = views.length < 2;
  if (bar.dataset.sig === sig) return;
  bar.dataset.sig = sig;
  bar.innerHTML = views.map(v => `<button type="button" data-v="${v}"${v === lbView ? ' aria-current="page"' : ""}>${escH(T(LB_VIEW_NAMES[v]))}</button>`).join("");
  for (const btn of bar.children) btn.onclick = () => {
    if (btn.dataset.v === lbView) return;
    ctlSound.nav(); lbView = btn.dataset.v; lbSig = ""; renderLogbook();
  };
}
/* 1.65: search the whole logbook (relay 55): a registration, a flight, a type or an airline, over every saved day.
   Typing searches after a short pause; × clears it and the logbook comes back. */
let lbQuery = "", lbFindT = 0, lbFindTok = 0;
function lbFindSetup(){
  const box = $("lbFindBox");
  box.hidden = (window.OVERHEAD_RELAY_VERSION || 0) < 55 || !relay() || S.demo;
  if (box.hidden || box.firstChild) return;
  box.innerHTML = `<span class="svFind"><input type="search" data-q enterkeyhint="search" autocomplete="off" spellcheck="false" ` +
    `placeholder="${escH(T((window.OVERHEAD_RELAY_VERSION || 0) >= 63 ? "Search the logbook, e.g. OE-LBN, A380, Santorini" : "Search the logbook, e.g. OE-LBN, A380, OS 802"))}" aria-label="${escH(T("Search the logbook"))}">` +
    `<button type="button" data-qx aria-label="${escH(T("Clear"))}" hidden>×</button></span>`;
  const inp = box.querySelector("[data-q]"), x = box.querySelector("[data-qx]");
  const set = v => { lbQuery = v; x.hidden = !v; clearTimeout(lbFindT); lbFindT = setTimeout(lbFind, v ? 350 : 0); };
  inp.oninput = () => set(inp.value.trim());
  x.onclick = () => { ctlSound.click(); inp.value = ""; set(""); inp.focus(); };
}
async function lbFind(){
  const out = $("lbFound"), on = lbQuery.replace(/[\s-]/g, "").length >= 2, tok = ++lbFindTok;
  $("t-logbook").classList.toggle("finding", on); out.hidden = !on;
  if (!on) { out.innerHTML = ""; return; }
  out.innerHTML = `<p class="lbfHead">${escH(T("Searching …"))}</p>`;
  let j;
  try { j = await fetchJSON(`${relay()}/search?q=${encodeURIComponent(lbQuery)}`, {}, 10000); }
  catch { if (tok === lbFindTok) out.innerHTML = `<p class="sum">${escH(T("The search didn't answer. Try again."))}</p>`; return; }
  if (tok !== lbFindTok) return;
  const when = t => t ? fmtDay(t) : "", time = t => t ? hhmm(new Date(t)) : "";
  lbFoundRows = j.rows;
  const pill = (k, i, t) => t ? `<button class="cLink" type="button" data-fp="${k}" data-fi="${i}">${escH(t)}</button>` : "";
  const rows = j.rows.map((g, i) => {
    // 1.75: each part a pill that opens its card (the aircraft, the model, the airline)
    const title = g.by === "f" ? [pill("al", i, g.flight), pill("al", i, g.airline)].filter(Boolean).join(" · ")
      : [pill("reg", i, g.reg || g.key.toUpperCase()), pill("ty", i, g.type), pill("al", i, g.airline)].filter(Boolean).join(" · ");
    const seen = g.n === 1 ? T("Seen once, {d} {t}", {d: when(g.last), t: time(g.last)})
      : T("Seen {n} times · first {a} · last {b}", {n: nf.format(g.n), a: when(g.first), b: `${when(g.last)} ${time(g.last)}`});
    const more = [g.minDist != null ? T("closest {d}", {d: distText(g.minDist)}) : "", (g.by === "f" ? g.regs : g.flights).join(", ")].filter(Boolean).join(" · ");
    const pl = lbfPlaces(g);
    return `<li><b>${title}</b><span>${escH(seen)}${more ? " · " + escH(more) : ""}</span>${pl.length ? `<span class="lbfPin">${PIN}${escH(pl.join(" · "))}</span>` : ""}</li>`;
  });
  const cat = j.category && LB_CATS.find(c => c[0] === j.category);       // 1.75: how the search read the words
  const read = cat ? `<p class="lbfRead"><span class="lbfChip">${escH(T("Category: {c}", {c: T(cat[1])}))}</span>${j.text ? `<span class="lbfChip">${escH(T("Text: {t}", {t: j.text}))}</span>` : ""}</p>` : "";
  out.innerHTML = read + `<p class="lbfHead">${escH(T(j.total === 1 ? "1 sighting · whole logbook" : "{n} sightings · whole logbook", {n: nf.format(j.total)}))}</p>` +
    (rows.length ? `<ol>${rows.join("")}</ol>` : `<p class="sum">${escH(T("Nothing in the logbook matches that."))}</p>`);
}
// 1.75: Logbook → Categories: a category tapped opens in place with its top ten (types, aircraft or operators) over the
// whole logbook (relay 61, /logbook/category); a type opens its card, an operator its airline card, an aircraft the search.
const catOk = () => !S.demo && !!relay() && (window.OVERHEAD_RELAY_VERSION || 0) >= 61;
let lbCat = "", lbCatView = "types", lbCatData = {};
const lbCatKey = () => lbCat + "|" + (lbPlace || "");
function catOpenHtml(k){
  const d = lbCatData[lbCatKey()];
  if (!d) return `<li class="catSub"><p class="sum">${escH(T("Loading …"))}</p></li>`;
  const seg = `<div class="seg catSeg" role="group">` + [["types", "Types"], ["regs", "Aircraft"], ["operators", "Operators"]]
    .map(([v, l]) => `<button type="button" data-cv="${v}" aria-pressed="${lbCatView === v}">${escH(T(l))}</button>`).join("") + `</div>`;
  const list = d[lbCatView] || [];
  const row = (x, i) => lbCatView === "types" ? `<button type="button" class="catRow" data-ct="${escH(x.code)}" data-cn="${escH(x.name)}"><span>${i + 1}</span>${escH(typeLabel(x.code, x.name))}<b>${nf.format(x.n)}</b></button>`
    : lbCatView === "regs" ? `<button type="button" class="catRow" data-cr="${escH(x.reg)}"><span>${i + 1}</span>${escH(x.reg)}${x.type ? ` · ${escH(x.type)}` : ""}<b>${nf.format(x.n)}</b></button>`
    : `<button type="button" class="catRow" data-co="${escH(x.icao || "")}" data-cn="${escH(x.name)}" data-ci="${escH(x.iata || "")}"><span>${i + 1}</span>${escH((AIRLINES[x.icao] || [])[1] || x.name)}<b>${nf.format(x.n)}</b></button>`;
  return `<li class="catSub">${seg}${list.length ? list.map(row).join("") : `<p class="sum">${escH(T("Nothing here yet."))}</p>`}</li>`;
}
async function catFetch(){
  const key = lbCatKey();
  if (lbCatData[key]) return;
  try { lbCatData[key] = await fetchJSON(`${relay()}/logbook/category?c=${lbCat}${lbPlace ? "&place=" + encodeURIComponent(lbPlace) : ""}`, {}, 15000); }
  catch { lbCatData[key] = {types: [], regs: [], operators: []}; }
  lbSig = ""; renderLogbook();
}
document.addEventListener("click", e => {
  const t = e.target && e.target.closest && e.target.closest("#lbLists [data-cat], #lbLists [data-cv], #lbLists .catRow, #lbFound [data-fp]");
  if (!t) return;
  ctlSound.click();
  if (t.dataset.cat) { lbCat = lbCat === t.dataset.cat ? "" : t.dataset.cat; lbCatView = "types"; if (lbCat) catFetch(); }
  else if (t.dataset.cv) lbCatView = t.dataset.cv;
  else if (t.dataset.ct) return typeCard({typeCode: t.dataset.ct, type: t.dataset.cn});
  else if (t.dataset.co != null && t.classList.contains("catRow")) return airlineCard({airlineIcao: t.dataset.co, airline: t.dataset.cn, airlineCode: t.dataset.ci});
  else if (t.dataset.cr) { const inp = $("lbFindBox").querySelector("[data-q]"); if (inp) { inp.value = t.dataset.cr; inp.dispatchEvent(new Event("input")); window.scrollTo({top: 0, behavior: "smooth"}); } return; }
  else if (t.dataset.fp) return foundCard(t.dataset.fp, lbFoundRows[+t.dataset.fi]);
  lbSig = ""; renderLogbook();
});
// 1.81 (Dave's to-do 3, his pick A): where a result was seen (relay 63's places, newest first): a line with a pin under
// it, and Seen from on its card. A place on the go is its town and the area round it; one guessed for a sighting from
// before relay 63 only its country (relay 64).
const PIN = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 21s-6-5.2-6-10a6 6 0 0 1 12 0c0 4.8-6 10-6 10z"/><circle cx="12" cy="11" r="2.2"/></svg>';
// 1.91 (to-do #105, Dave's pick C): the arrow of whatever opens, a chevron in a small ring (.dd), for the place bar's
// Saved places and the Categories rows; the Favourites & hidden picker has the same drawing in the board's CSS.
const DD = '<svg class="dd" viewBox="0 0 20 20" aria-hidden="true"><circle cx="10" cy="10" r="9.25" fill="none" stroke="#4a4c52" stroke-width="1.5"/><path d="M6 8l4 4 4-4" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>';
const lbfPlaces = g => [...new Set((g.places || []).map(p => p.k !== "live" ? lbPlaceName(p.k) : p.n ? [p.n, p.a].filter(Boolean).join(", ") : p.c || placeName("live")).filter(Boolean))];
// 1.75: a search result's parts: the aircraft (a card from what the search found), the model, the airline. 1.94: the
// aircraft in Sky view's card style: its photo, its last route, Spotted · Closest · Flights, back after months.
let lbFoundRows = [];
async function foundCard(k, g){
  if (!g) return;
  if (k === "ty") return typeCard({typeCode: g.typeCode, type: g.type});
  if (k === "al") return airlineCard({airline: g.airline, callsign: g.callsign, airlineCode: g.airlineIata});
  const reg = g.reg || g.key.toUpperCase(), ac = {hex: g.hex || "", r: reg, t: g.typeCode, desc: g.type};
  const c = {k: "reg", v: reg, n: [reg, g.type].filter(Boolean).join(" · ")};
  let shown = 0;
  const late = () => { if (shown && shown === cardTok && cardOpenNow()) shown = cardOpen(html(), wire); };   // its photo found later
  const pic = () => planePic(ac, {reg, type: g.type}, detailsOf(ac.hex) || {}, late);
  const html = () => infoCard({pic: pic(), title: reg, sub: g.airline || "", subAttr: g.airline ? " data-fal" : "", chip: tierChip(g.typeCode),
    band: g.route ? [routeEnd(g.route.from, "from"), "", routeEnd(g.route.to, "to")] : null, tiles: planeTiles(g), facts: planeFunFacts(g),
    det: [["Aircraft", g.type ? `<button class="cLink" type="button" data-fty>${escH(g.type)} ›</button>` : ""], ["Operator", escH(g.owner || g.airline || "")],
      ["Registered", escH(g.ownerCountry || "")], ["Mode S", escH(String(g.hex || "").toUpperCase())],
      ["Last seen", escH(g.last ? `${fmtDay(g.last)}, ${hhmm(new Date(g.last))}` : "")], ["Seen from", escH(lbfPlaces(g).join(", "))]],
    btns: listsOk() ? `<div class="cBtns">${togBtn("fav", c, "★ " + escH(T("Favourite")))}${togBtn("hide", c, "⊘ " + escH(T("Hide")))}</div><p class="note"></p>` : ""});
  const wire = el => {
    for (const im of el.querySelectorAll(".cPicA img")) im.onerror = () => picFailed(im, late);
    const al = el.querySelector("[data-fal]"); if (al) al.onclick = () => airlineCard({airline: g.airline, callsign: g.callsign, airlineCode: g.airlineIata});
    const ty = el.querySelector("[data-fty]"); if (ty) ty.onclick = () => typeCard({typeCode: g.typeCode, type: g.type});
    for (const b of el.querySelectorAll("[data-pl]")) b.onclick = () => placeCard(g.route[b.dataset.pl]);
  };
  const tok = cardLoading();
  if (ac.hex) lookupDetails(ac.hex);
  for (const t0 = Date.now(); (pic().asking || (ac.hex && acDetails.get(ac.hex) === null)) && Date.now() - t0 < 2500 && tok === cardTok;) await new Promise(r => setTimeout(r, 150));
  shown = await cardWhenReady(tok, html(), wire);
}
function renderLogbook(){
  if (tab !== "logbook") return;
  lbFindSetup();
  lbViewsBar();
  const v = lbView;
  if (v === "logbook") { if (lbPeriod === "year") fetchYear(); else fetchReview(() => { lbSig = ""; renderLogbook(); }); }
  const all = lbData() || {}, pl = v === "logbook" && lbPlaceOk() ? lbChips() : [];
  if (v === "logbook" && lbPlace && !pl.some(c => c.id === lbPlace)) lbPlace = "";
  const place = v === "logbook" ? lbPlace : "";
  // 1.89 (to-do #90, Dave's pick): All · On the go · Saved places, a bar like Week · Month · Year; the saved places are
  // picked in a sheet, and the third part then names the one picked. Counting since and a place's own line are the
  // footnote at the bottom.
  const bar = $("lbPlaces"), live = pl.find(c => c.id === "live"), saved = pl.filter(c => c.id !== "live");
  const cur = saved.find(c => c.id === lbPlace);
  const want = [["", T("All")], ...(live ? [["live", live.name]] : []), ...(saved.length ? [["saved", cur ? cur.name : T("Saved places")]] : [])];
  bar.hidden = want.length < 2;
  const csig = JSON.stringify([want, lbPlace, LANG]);
  if (!bar.hidden && bar.dataset.sig !== csig) {
    bar.dataset.sig = csig;
    bar.innerHTML = want.map(([k, name]) => k === "saved" ? `<button type="button" data-p="saved" aria-pressed="${!!cur}" aria-haspopup="dialog"><span class="ddL">${escH(name)}</span>${DD}</button>`
      : `<button type="button" data-p="${escH(k)}" aria-pressed="${k === lbPlace}">${escH(name)}</button>`).join("");
    for (const btn of bar.children) btn.onclick = () => {
      if (btn.dataset.p === "saved") return lbPlaceSheet(true);
      if (btn.dataset.p !== lbPlace) { ctlSound.click(); lbPick(btn.dataset.p); }
    };
  }
  const b = place ? lbPlaceData[place] || {} : all, has = place ? !!lbPlaceData[place] : !!lbData();
  $("lbSum").hidden = v === "review" || v === "logbook";
  $("lbSum").textContent = v === "collection" ? T("How rare a type is depends on how many fly today. Every type you see fills its place in the collections; points come in the Spotters' Club.")
    : v === "records" ? T("The logbook's records, this week's bingo card (a new one every Monday) and the trophies, which are kept for good.") : "";
  const foot = v !== "logbook" ? "" : [place ? !has ? T("Loading …")
    : T(b.sightings === 1 ? "1 plane seen from {place} since {d}." : "{n} planes seen from {place} since {d}.", {n: nf.format(b.sightings || 0), place: lbPlaceName(place), d: b.since ? fmtDay(new Date(b.since + "T12:00:00").getTime()) : "–"}) : "",
    logbookSummary()].filter(Boolean).map(escH).join("<br>");
  const byCount = o => Object.entries(o || {}).sort((x, y) => (y[1].count || 0) - (x[1].count || 0));
  const types = byCount(b.types), airlines = byCount(b.airlines);
  $("lbTop").hidden = v !== "logbook";
  setChars("lvSight", has ? nf.format(b.sightings || 0) : "");
  setChars("lvRegs", has ? nf.format(b.regsCount || 0) : "", 60);
  setChars("lvTypes", has ? nf.format(types.length) : "", 120);
  setChars("lvAirlines", has ? nf.format(airlines.length) : "", 180);
  const sig = JSON.stringify([v, place, foot, b.since, b.sightings, b.categories, types.slice(0, 10), airlines.slice(0, 10), b.regsTop, all.game, all.records, yearData, lbCat, lbCatView, lbCat && lbCatData[lbCatKey()], lbPeriod, yearBack, lbPeriod !== "year" && reviewOk() && reviewData(), review.span, review.back, LANG]);
  if (sig === lbSig) return;
  lbSig = sig;
  $("lbModel").innerHTML = types[0] && types[0][1].count > 1 ?`<small>${escH(T("Most seen model"))}</small>${escH(typeLabel(types[0][0], types[0][1].name))}<span>${escH(T("{n} times", {n: nf.format(types[0][1].count || 0)}))}</span>` : "";
  const rank = (items, plain) => `<ol class="ranks${plain ? " plain" : ""}">${items.join("")}</ol>`;
  const li = (name, n, sub) => `<li><span class="name">${escH(name)}${sub ? `<span class="s">${escH(sub)}</span>` : ""}</span><span class="n">${escH(n)}</span></li>`;
  let html = "";
  const g0 = all.game;                               // the collection, bingo and trophies count every place
  if (v === "logbook") {
    if (b.categories) {
      const max = Math.max(1, ...LB_CATS.map(([k]) => b.categories[k] || 0));
      html += secPlate(T("Categories"), `<ul class="ranks cats">` + LB_CATS.map(([k, en, de, col]) => {
        const n = b.categories[k] || 0;
        const open = lbCat === k && catOk() && n;
        return `<li style="--lamp:${col}"${n && catOk() ? ` data-cat="${k}" class="catTap${open ? " open" : ""}"` : ""}><i class="lamp"></i><span class="name">${escH(T(en))}${n && catOk() ? ` <span class="chev">${DD}</span>` : ""}</span><span class="n">${nf.format(n)}</span>` +
          `<span class="bar"><i style="width:${(n / max * 100).toFixed(1)}%"></i></span></li>` + (open ? catOpenHtml(k) : "");
      }).join("") + "</ul>");
    }
    if (types.length) html += secPlate(T("Aircraft types"), rank(types.slice(0, 10).map(([c, t]) => li(typeLabel(c, t.name), nf.format(t.count || 0)))));
    if (airlines.length) html += secPlate(T("Airlines"), rank(airlines.slice(0, 10).map(([c, a]) => li((AIRLINES[c] || [])[1] || a.name || c, nf.format(a.count || 0)))));
    if ((b.regsTop || []).length) html += secPlate(T("Most seen aircraft"), rank(b.regsTop.slice(0, 8).map(r => li(r.reg, nf.format(r.count || 0), r.name))));
    if (!place) html = periodHtml() + html;
  } else if (v === "collection") html = collectionHtml(g0);
  else if (v === "records") html = recordsHtml(all, g0);
  else html = reviewHtml();
  $("lbLists").innerHTML = (html || `<p class="sum">${escH(T("Loading …"))}</p>`) + (foot ? `<p class="sum lbFoot">${foot}</p>` : "");
  const cv = $("yCsv"); if (cv) cv.onclick = () => ctlSound.click();
  trWire($("lbLists"), () => { lbSig = ""; renderLogbook(); });
}
// 1.89: a place picked (All, on the go or a saved one): its numbers come from the relay the first time.
async function lbPick(id){
  lbPlace = id; lbSig = ""; renderLogbook();
  if (lbPlace && !lbPlaceData[lbPlace]) { try { lbPlaceData[lbPlace] = await fetchJSON(lbPlaceUrl(lbPlace), {}, 12000); } catch {} lbSig = ""; renderLogbook(); }
}
// 1.89 (to-do #90, Dave's pick A): the saved places in a sheet, each with its count, the one picked lit.
function lbPlaceSheet(button){
  button ? ctlSound.click() : ctlSound.nav();      // 1.97.4: the bar's button clicks like a button
  const saved = (lbPlaceOk() ? lbChips() : []).filter(c => c.id !== "live");
  cardOpen(`<div class="cHead"><div><h3>${escH(T("Logbook for"))}</h3></div></div>` +
    `<ul class="ranks cats">` + saved.map(c => `<li class="catTap" data-pk="${escH(c.id)}" style="--lamp:${c.id === lbPlace ? "var(--c-gold)" : "#3a3c41"}"><i class="lamp"></i><span class="name">${escH(c.name)}</span><span class="n">${nf.format(c.n)}</span></li>`).join("") + `</ul>` +
    `<p class="sum">${escH(T("Places are saved in Settings → Places."))}</p>`,
    ci => { for (const li of ci.querySelectorAll("[data-pk]")) li.onclick = () => { ctlSound.click(); cardClose(); if (li.dataset.pk !== lbPlace) lbPick(li.dataset.pk); }; });
}
// The game's collection (points, tiers, the collections) and its records, bingo and trophies: on the Game page since
// 1.72 (relay 59), in the Logbook before.
function collectionHtml(g0){
  if (!g0) return "";
  const tiers = TIER_DRUM.slice(1).map(t => `<li style="--lamp:${TIER_COL[t]}"><img class="tico" src="${tierIcon(t)}" alt=""><span class="name">${escH(T(TIER_NAME[t]))}</span><span class="n">${nf.format(g0.tiers[t] || 0)}</span></li>`).join("");
  const sets = g0.sets.map(s => `<li style="--lamp:${s.have.length >= s.total ? "var(--c-good)" : "var(--amber)"}"><i class="lamp"></i><span class="name">${escH(T(s.name))}</span><span class="n">${s.have.length} / ${s.total}</span>` +
    `<span class="bar"><i style="width:${(s.have.length / s.total * 100).toFixed(1)}%;background:${s.have.length >= s.total ? "var(--c-good)" : "var(--amber)"};opacity:1"></i></span></li>`).join("");   // 1.73: gold, green once complete
  // 1.79 (Dave's pick B): "Your catch" (by rarity) and "Sets" (to complete), not Collection and Collections; the points
  // line went (the top of the page says it). 1.81: on the club page the Sets list becomes the hangar once it's in.
  hangarLoad();
  return secPlate(T("Your catch"), `<ul class="ranks cats tiers">${tiers}</ul>`) +
    (hangar && tab === "game" ? hangarHtml(hangar) : secPlate(T("Sets"), `<ul class="ranks cats">${sets}</ul>`));
}
/* 1.106 (to-do #162, Dave's pick A, with the airline trophies): airline loyalty. Each airline's planes you scan raise your
   tier with it: Member at the first, Silver, Gold, Platinum (relay 89: rules.loyalty, [scans, bonus] a tier, paid at the
   scan that reaches it). The club's wallet holds a member card for every airline the game caught live (g0.wallet, what the
   airline trophies count; 0 scans: not a member yet), the best in front, the others' tops peeking out; a tap on one
   brings it to the front. A ticket prints "OS · GOLD" (a member's plain); the step-up is a line of the scan's. */
const LY = [[10, 25], [50, 100], [200, 250]], LY_NAME = ["Member", "Silver", "Gold", "Platinum"];
const LY_TO = ["{n} to Silver", "{n} to Gold", "{n} to Platinum"];
// the airline's own colour on its card (a few that fly here often); any other gets one from its code
const LY_COL = {AUA: "#d81e05", RYR: "#073590", DLH: "#0a1d3d", WZZ: "#c6007e", WMT: "#c6007e", WAZ: "#c6007e", SWR: "#e2001a", THY: "#c8102e",
  LDA: "#e30613", UAE: "#b5121b", QTR: "#5c0632", EZY: "#ff6600", EJU: "#ff6600", EWG: "#a5027d", BAW: "#075aaa", AFR: "#002157", KLM: "#00a1de",
  ITY: "#0047bb", LOT: "#11397e", TAP: "#e1261c", IBE: "#d7192d", SAS: "#000f7a", FIN: "#0b1560", AEE: "#0a3a7a", ELY: "#0b2a6f", CTN: "#d8232a"};
const lySteps = () => { const r = gRules(); return (r && r.loyalty) || LY; };
const lyOf = n => (n || 0) < 1 ? -1 : lySteps().filter(s => n >= s[0]).length;    // -1: not a member yet; 0 Member … 3 Platinum
const lyCode = icao => (AIRLINES[icao] || [])[0] || icao;
const lyName = icao => shortAirline((AIRLINES[icao] || [])[1] || icao);
const lyCol = icao => LY_COL[icao] || `hsl(${[...icao].reduce((h, c) => h * 31 + c.charCodeAt(0), 7) % 360} 55% 38%)`;
// a ticket's printed line: the airline's code and your tier with it (none while not a member)
const lyTicket = (icao, n) => { const t = lyOf(n); return icao && t >= 0 ? {code: lyCode(icao), t} : null; };
let lyFront = "", lyAll = false;
function walletHtml(g0){
  const w = g0 && g0.wallet;
  if (!w) return "";
  const list = Object.entries(w).sort((a, b) => b[1] - a[1] || lyName(a[0]).localeCompare(lyName(b[0]))), n = list.length;
  const st = trophyLadder(g0, TROPHY_LADDERS.find(l => l[0] === "airlines")), [a, b, c] = lySteps();
  const sum = [T(n === 1 ? "1 airline" : "{n} airlines", {n: nf.format(n)}), st.next ? T("{t} at {n}", {t: T(st.next[2]), n: nf.format(st.next[1])}) : ""].filter(Boolean).join(" · ");
  const rule = T("Scan an airline's planes to climb: Silver at {a}, Gold at {b}, Platinum at {c}.", {a: a[0], b: b[0], c: c[0]});
  if (!n) return secPlate(T("Member cards"), `<p class="sum">${escH(rule)}</p>`, "lyPlate");
  const front = list.find(x => x[0] === lyFront) || list[0], rest = list.filter(x => x !== front);
  const card = ([icao, s], big) => {
    const t = lyOf(s), nx = t >= 0 ? lySteps()[t] : null, lo = t > 0 ? lySteps()[t - 1][0] : 1;
    const tier = t >= 0 ? T(LY_NAME[t]) : "";
    return `<button type="button" class="lyCard ${t >= 0 ? "ly" + t : "lyN"}" data-ly="${escH(icao)}" style="--ac:${lyCol(icao)}">` +
      `<span class="hd"><b>${escH(lyName(icao))}</b><em>${escH(tier)}</em><i>${escH(lyCode(icao))}</i></span>` +
      (!big ? "" : t < 0 ? `<span class="nm">${escH(T("Not a member yet"))}</span><span class="ft"><span>${escH(T("Scan one of its planes to join"))}</span></span>`
        : `<span class="nm">${escH(tier)}</span>` + (nx ? `<span class="br"><i style="width:${Math.min(100, (s - lo) / (nx[0] - lo) * 100).toFixed(1)}%"></i></span>` : "") +
          `<span class="ft"><span>${escH(T("{n} scanned", {n: nf.format(s)}))}</span><span>${nx ? escH(T(LY_TO[t], {n: nf.format(nx[0] - s)})) : ""}</span></span>`) + `</button>`;
  };
  const tops = (lyAll ? rest : rest.slice(0, 4)).reverse();
  return secPlate(T("Member cards"), `<p class="sum">${escH(sum)}</p><div class="lyWal">${tops.map(x => card(x)).join("")}${card(front, true)}</div>` +
    `<p class="sum">${escH(rule)}${n > 1 ? " " + escH(T("Tap a card to bring it to the front.")) : ""}</p>` +
    (rest.length > 4 ? `<button class="gHow" type="button" data-lyall>${escH(lyAll ? T("Fewer cards") : T("All {n} cards", {n: nf.format(n)}))}<i>›</i></button>` : ""), "lyPlate");
}
function lyWire(box, redraw){
  for (const b of box.querySelectorAll("[data-ly]")) b.onclick = () => { if (b.dataset.ly === lyFront) return; ctlSound.click(); lyFront = b.dataset.ly; redraw(); };
  const all = box.querySelector("[data-lyall]");
  if (all) all.onclick = () => { ctlSound.nav(); lyAll = !lyAll; redraw(); };
}
/* 1.107 (to-do #150, Dave's pick: round 1's C, the stamp shelves, with round 2's C map, the ink patchwork, and B's
   scratch as an option): the passport. Each scanned flight with a known route stamps the countries of its two airports
   (relay 90: g0.passport, {country: [day, airport, lat, lon, continent, paid]}; a country new to it pays +25 at the scan).
   The plate under Your hangar: the map (test/world.js, Natural Earth's countries, fetched when the passport first
   shows) printed on passport paper, each stamped country inked in its stamp's colour, the player's place never marked;
   then a shelf per region, a stamp card for each country (its name, the airport, the day, in its ink) and up to three
   nearby countries not yet stamped face down. A tap on the map opens it large (Europe & around or the World, a bar per
   region). A scan that stamps a new country shows its route on the ticket, and a card on top presses the stamp and
   inks the country in, unless the player rubs it in with a finger first (ppNew). Never on other players' cards. */
let worldLoad = null, worldFailed = 0;
function worldMap(){
  if (window.WORLD) return Promise.resolve(window.WORLD);
  if (!worldLoad && Date.now() - worldFailed > 60000) worldLoad = new Promise(done => {
    const s = document.createElement("script");
    s.src = WORLD_JS; s.async = true;
    s.onload = () => done(window.WORLD || null);
    s.onerror = () => { worldLoad = null; worldFailed = Date.now(); s.remove(); done(null); };
    document.head.appendChild(s);
  });
  return worldLoad || Promise.resolve(null);
}
const PP_REG = [["E", "Europe"], ["M", "Middle East"], ["F", "Africa"], ["A", "Asia"], ["N", "Americas"], ["O", "Oceania"]];
const PP_ME = new Set("AE BH IL IQ IR JO KW LB OM PS QA SA SY TR YE".split(" "));   // a country the map lacks: by its airport's continent, these the Middle East
const PP_INK = ["#1f4fb8", "#b3262d", "#333", "#1f7a3c", "#6b3fa0", "#7a2416"];
const PP_VIEW = {eu: [16, 46, 6.2], world: [12, 24, 1.02]};       // the map's centre (lon, lat) and its scale (px a degree)
const ppHash = cc => [...cc].reduce((h, c) => h * 31 + c.charCodeAt(0), 7);
// Each stamp's ink: its own by its code, else the next one no stamped neighbour (within 12°) has; taken in the order they
// were stamped, so a stamp keeps its colour when others come.
let ppInks = {}, ppInksKey = "";
function ppInkAll(pp){
  const W = window.WORLD, key = Object.keys(pp).sort().join() + (W ? "+" : "");
  if (key === ppInksKey) return;
  ppInksKey = key; ppInks = {};
  const pt = c => W && W[c] ? [W[c][1] / 10, W[c][2] / 10] : pp[c][2] != null ? [pp[c][3], pp[c][2]] : null;
  for (const [c] of Object.entries(pp).sort((a, b) => String(a[1][0]).localeCompare(String(b[1][0])) || a[0].localeCompare(b[0]))) {
    const p = pt(c), h = ppHash(c);
    const near = new Set(Object.keys(ppInks).filter(o => { const q = pt(o); return p && q && Math.hypot(p[0] - q[0], p[1] - q[1]) < 12; }).map(o => ppInks[o]));
    let i = 0;
    while (i < PP_INK.length - 1 && near.has(PP_INK[(h + i) % PP_INK.length])) i++;
    ppInks[c] = PP_INK[(h + i) % PP_INK.length];
  }
}
const ppInk = cc => ppInks[cc] || PP_INK[ppHash(cc) % PP_INK.length];
const ppReg = (cc, s) => (window.WORLD && window.WORLD[cc] ? window.WORLD[cc][0] : PP_ME.has(cc) ? "M" : {EU: "E", AF: "F", AS: "A", NA: "N", SA: "N", OC: "O"}[s && s[4]] || "A");
let ppNames = null;
function ppName(cc){
  try { ppNames = ppNames || new Intl.DisplayNames([LANG], {type: "region"}); return ppNames.of(cc) || cc; } catch { return cc; }
}
const ppDate = d => { try { return new Intl.DateTimeFormat(LANG === "en" ? "en-GB" : LANG, {day: "numeric", month: "short", year: "numeric"}).format(new Date(d + "T12:00")).toUpperCase(); } catch { return d; } };
const ppToday = () => { const d = new Date(Date.now() - 3 * 3600e3); return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`; };
const ppList = pp => Object.entries(pp || {}).sort((a, b) => String(b[1][0]).localeCompare(String(a[1][0])) || ppName(a[0]).localeCompare(ppName(b[0])));
// A stamp, as on its card: round, a box or an oval (by the country), tilted, in the country's ink.
function ppStamp(cc, s){
  const h = ppHash(cc), sh = ["rd", "rc", "ov"][h % 3];
  return `<span class="pS ${sh}" style="--ink-c:${ppInk(cc)};--r:${(h >> 3) % 21 - 10}deg"><small>${escH(ppName(cc))}</small><b>${escH(s[1] || cc)}</b>` +
    `<i>${sh === "rd" ? `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="${RK_PLANE}" fill="currentColor"/></svg>` : ""}${escH(ppDate(s[0]))}</i></span>`;
}
// The map: Mercator, the countries' outer rings (whole tenths of a degree), those outside the view left out.
const ppMerc = la => Math.log(Math.tan(Math.PI / 4 + Math.max(-80, Math.min(84, la)) * Math.PI / 360)) * 180 / Math.PI;
const ppView = (w, h, [lon, lat, k]) => ({w, h, k: [lon, lat, k].join(), x: lo => w / 2 + (lo - lon) * k, y: la => h / 2 - (ppMerc(la) - ppMerc(lat)) * k});
function ppPath(v, cc){
  let out = "";
  for (const r of (window.WORLD[cc] || [])[3] || []) {
    let a = 1e9, b = -1e9, c = 1e9, d = -1e9, p = "";
    for (let i = 0; i < r.length; i += 2) {
      const x = v.x(r[i] / 10), y = v.y(r[i + 1] / 10);
      a = Math.min(a, x); b = Math.max(b, x); c = Math.min(c, y); d = Math.max(d, y);
      p += (i ? "L" : "M") + x.toFixed(1) + " " + y.toFixed(1);
    }
    if (b > -20 && a < v.w + 20 && d > -20 && c < v.h + 20) out += p + "Z";
  }
  return out;
}
const ppLand = new Map();                                        // the paper's land, once a view
let ppUid = 0;
// o.labels: the stamped countries' codes; o.fresh: countries still to ink (masked: ppNew soaks or scratches them in).
function ppMapSvg(pp, v, o = {}){
  const id = "pp" + (++ppUid), fresh = o.fresh || [], have = Object.keys(pp).filter(c => !fresh.includes(c));
  if (!ppLand.has(v.w + "," + v.h + "," + v.k)) ppLand.set(v.w + "," + v.h + "," + v.k, Object.keys(window.WORLD).map(c => ppPath(v, c)).join(""));
  const ink = (c, more = "") => window.WORLD[c] ? `<path d="${ppPath(v, c)}" fill="${ppInk(c)}" fill-opacity=".8"${more}/>`
    : pp[c] && pp[c][2] != null ? `<circle cx="${v.x(pp[c][3]).toFixed(1)}" cy="${v.y(pp[c][2]).toFixed(1)}" r="${o.labels ? 4 : 3}" fill="${ppInk(c)}"${more}/>` : "";
  const lbl = c => { const w = window.WORLD[c]; if (!w) return ""; const x = v.x(w[1] / 10), y = v.y(w[2] / 10);
    return x < 6 || x > v.w - 6 || y < 6 || y > v.h - 6 ? "" : `<text x="${x.toFixed(1)}" y="${(y + 3).toFixed(1)}">${c}</text>`; };
  return `<svg viewBox="0 0 ${v.w} ${v.h}" preserveAspectRatio="xMidYMid slice" aria-hidden="true"><defs>` +
    `<filter id="${id}r" x="-5%" y="-5%" width="110%" height="110%"><feTurbulence type="fractalNoise" baseFrequency=".9" numOctaves="2" seed="4" result="n"/>` +
    `<feDisplacementMap in="SourceGraphic" in2="n" scale="2.2" xChannelSelector="R" yChannelSelector="G" result="d"/>` +
    `<feTurbulence type="fractalNoise" baseFrequency=".55" numOctaves="2" seed="9" result="s"/><feColorMatrix in="s" values="0 0 0 0 0  0 0 0 0 0  0 0 0 0 0  0 0 0 -7 6" result="h"/>` +
    `<feComposite in="d" in2="h" operator="in"/></filter>` +
    (fresh.length ? `<filter id="${id}b" x="-20%" y="-20%" width="140%" height="140%"><feTurbulence type="fractalNoise" baseFrequency=".06" numOctaves="2" seed="12" result="n"/>` +
      `<feDisplacementMap in="SourceGraphic" in2="n" scale="26" xChannelSelector="R" yChannelSelector="G"/></filter>` +
      `<mask id="${id}m" maskUnits="userSpaceOnUse" x="0" y="0" width="${v.w}" height="${v.h}"><g class="ppSoak" filter="url(#${id}b)" fill="#fff" stroke="#fff" stroke-linecap="round" stroke-linejoin="round"></g></mask>` : "") +
    `</defs><path d="${ppLand.get(v.w + "," + v.h + "," + v.k)}" fill="#e6ddc7" stroke="#b5a98d" stroke-width=".5" stroke-linejoin="round"/>` +
    `<g filter="url(#${id}r)" class="ppInk">${have.map(c => ink(c)).join("")}</g>` +
    (fresh.length ? `<g mask="url(#${id}m)" class="ppInk">${fresh.map(c => ink(c, ` filter="url(#${id}r)"`)).join("")}</g>` : "") +
    `<path d="${have.filter(c => window.WORLD[c]).map(c => ppPath(v, c)).join("")}" fill="none" stroke="rgba(60,45,30,.35)" stroke-width=".5"/>` +
    (o.labels ? `<g class="ppLbl">${have.map(lbl).join("")}</g>` : "") + `</svg>`;
}
// The countries of each region (the map's, and those stamped that it lacks, as dots).
function ppTotals(pp){
  const t = {};
  for (const c of new Set([...Object.keys(window.WORLD), ...Object.keys(pp)])) t[ppReg(c, pp[c])] = (t[ppReg(c, pp[c])] || 0) + 1;
  return t;
}
// Up to three countries of the region not yet stamped, those nearest a stamped one first (by the map's label points).
function ppGoals(pp, reg, have){
  const pts = have.map(c => window.WORLD[c]).filter(Boolean);
  if (!pts.length) return [];
  return Object.keys(window.WORLD).filter(c => !pp[c] && window.WORLD[c][0] === reg)
    .map(c => [c, Math.min(...pts.map(p => Math.hypot(p[1] - window.WORLD[c][1], p[2] - window.WORLD[c][2])))]).sort((a, b) => a[1] - b[1]).slice(0, 3).map(x => x[0]);
}
function passportHtml(g0){
  const pp = g0 && g0.passport;
  if (!pp) return "";                                            // relay 89 or older, or its airport list still loading
  if (!window.WORLD) worldMap().then(w => w && renderGame());
  ppInkAll(pp);
  const list = ppList(pp), n = list.length;
  const map = `<button type="button" class="ppMap" data-ppmap aria-label="${escH(T("Open the map"))}">${window.WORLD ? ppMapSvg(pp, ppView(360, 190, PP_VIEW.eu)) : ""}` +
    `<span class="ct">${escH(T(n === 1 ? "1 country" : "{n} countries", {n: nf.format(n)}))}</span><span class="lg">${escH(T("inked in each stamp's colour"))}</span></button>`;
  if (!n) return secPlate(T("Passport"), map + `<p class="sum">${escH(T("Scan a flight with a known route: the countries it flies from and to are stamped here."))}</p>`, "ppPlate");
  const shelves = PP_REG.map(([reg, name]) => {
    const have = list.filter(([c, s]) => ppReg(c, s) === reg);
    if (!have.length) return "";
    const goals = window.WORLD ? ppGoals(pp, reg, have.map(x => x[0])) : [];
    return `<div class="ppShelf"><div class="hgHead"><b>${escH(T(name))}</b><em>${escH(T("{n} stamped", {n: nf.format(have.length)}))}</em></div>` +
      `<div class="hgRow" data-set="pp-${reg}">${have.map(([c, s]) => `<span class="pCard">${ppStamp(c, s)}</span>`).join("")}` +
      goals.map(c => `<span class="pCard no"><b>${c}</b>${escH(ppName(c))}<br>${escH(T("still to stamp"))}</span>`).join("") + `</div></div>`;
  }).join("");
  return secPlate(T("Passport"), map + shelves, "ppPlate");
}
function ppWire(box){
  const m = box.querySelector("[data-ppmap]");
  if (m) m.onclick = ppCard;
}
let ppAt = "eu";
function ppCard(){
  const g0 = (lbData() || {}).game, pp = g0 && g0.passport;
  if (!pp || !window.WORLD) return;
  ctlSound.nav(); ppInkAll(pp);
  const n = Object.keys(pp).length, tot = ppTotals(pp), all = Object.values(tot).reduce((a, b) => a + b, 0);
  const bars = PP_REG.filter(([reg]) => tot[reg]).map(([reg, name]) => { const h = Object.entries(pp).filter(([c, s]) => ppReg(c, s) === reg).length;
    return `<li style="--lamp:${h ? "#b3262d" : "var(--muted)"}"><i class="lamp"></i><span class="name">${escH(T(name))}</span><span class="n">${escH(T("{n} of {m}", {n: nf.format(h), m: nf.format(tot[reg])}))}</span>` +
      `<span class="bar"><i style="width:${(h / tot[reg] * 100).toFixed(1)}%;background:#b3262d;opacity:1"></i></span></li>`; }).join("");
  const draw = el => { el.innerHTML = ppMapSvg(pp, ppView(360, 440, PP_VIEW[ppAt]), {labels: true}); };
  cardOpen(`<div class="cHead"><div><h3>${escH(T("Passport"))}</h3><span>${escH(T("{n} of {m} countries inked in", {n: nf.format(n), m: nf.format(all)}))}</span></div></div>` +
    `<div class="seg gSeg" role="group"><button type="button" data-ppv="eu" aria-pressed="${ppAt === "eu"}">${escH(T("Europe & around"))}</button>` +
    `<button type="button" data-ppv="world" aria-pressed="${ppAt === "world"}">${escH(T("World"))}</button></div>` +
    `<div class="ppMap big"></div><ul class="ranks cats">${bars}</ul>`, box => {
    draw(box.querySelector(".ppMap.big"));
    for (const b of box.querySelectorAll("[data-ppv]")) b.onclick = () => {
      if (ppAt === b.dataset.ppv) return;
      ctlSound.click(); ppAt = b.dataset.ppv;
      for (const x of box.querySelectorAll("[data-ppv]")) x.setAttribute("aria-pressed", String(x === b));
      draw(box.querySelector(".ppMap.big"));
    };
  });
}
// The scan's ticket: the route, the countries new to the passport marked (relay 90: r.route, [[airport, country, new]]).
const ppRoute = rt => rt && rt.length === 2 ? `<div class="ppRt">${rt.map(([ap, cc, nw], i) => (i ? "<i></i>" : "") +
  `<b class="${nw ? "nw" : ""}">${escH(ap)}<small>${escH(ppName(cc))}${nw ? " · " + escH(T("NEW")) : ""}</small></b>`).join("")}</div>` : "";
/* A country new to the passport, at the scan: a card over the scan's ticket, the map round the country. The stamp
   comes down on it (fsThud) and the ink soaks in from where it landed; or, before it does, the player rubs it in
   with a finger ("Scratch Spain in"). Left alone, or once the finger stops, it inks the rest itself. */
function ppNew(r){
  const nw = (r.route || []).filter(x => x[2]), g0 = (lbData() || {}).game;
  if (!nw.length) return;
  if (g0 && g0.passport) for (const [ap, cc] of nw) g0.passport[cc] = g0.passport[cc] || [ppToday(), ap, null, null, "", (gRules() || {}).country || 25];
  worldMap().then(W => {
    if (!W || !$("gAws")) return;
    const pp = {...((g0 && g0.passport) || {})}, ccs = nw.map(x => x[1]), c0 = ccs.find(c => W[c]) || ccs[0];
    for (const [ap, cc] of nw) pp[cc] = pp[cc] || [ppToday(), ap];
    ppInkAll(pp);
    // the view: the country's largest ring, with room round it
    const ring = ((W[c0] || [])[3] || []).reduce((a, b) => b.length > a.length ? b : a, []);
    const xs = ring.filter((_, i) => i % 2 === 0).map(x => x / 10), ys = ring.filter((_, i) => i % 2).map(y => ppMerc(y / 10));
    const lon = xs.length ? (Math.min(...xs) + Math.max(...xs)) / 2 : 16, mid = ys.length ? (Math.min(...ys) + Math.max(...ys)) / 2 : ppMerc(46);
    const lat = Math.atan(Math.sinh(mid * Math.PI / 180)) * 180 / Math.PI;
    const k = Math.max(1, Math.min(16, 340 / (Math.max(...xs, lon + 1) - Math.min(...xs, lon - 1)) / 1.5, 170 / (Math.max(...ys, mid + 1) - Math.min(...ys, mid - 1)) / 1.5));
    const v = ppView(340, 170, [lon, lat, k]), sx = W[c0] ? v.x(W[c0][1] / 10) : v.w / 2, sy = W[c0] ? v.y(W[c0][2] / 10) : v.h / 2;
    const name = ccs.map(ppName).join(" · "), count = r.countries || Object.keys(pp).length;
    const el = document.createElement("div");
    el.className = "gAw ppNew"; el.setAttribute("role", "status");
    el.innerHTML = `<div class="hd"><span>${escH(T("PASSPORT · NEW STAMP"))}</span><b>+${nf.format(nw.length * ((gRules() || {}).country || 25))}</b></div>` +
      `<div class="ppMap"><div class="sv">${ppMapSvg(pp, v, {fresh: ccs})}</div>` +
      `<span class="ppDrop" style="left:${sx.toFixed(0)}px;top:${sy.toFixed(0)}px">${ppStamp(c0, pp[c0])}</span>` +
      `<span class="ppTip">${escH(T("Scratch {c} in", {c: ppName(c0)}))}</span></div>` +
      `<div class="ft">${escH(ccs.length > 1 ? T("{c}: new to your passport. {n} countries now.", {c: name, n: nf.format(count)})
        : T("{c}: country {n} in your passport.", {c: name, n: nf.format(count)}))}</div>`;
    const box = $("gAws");
    box.appendChild(el); gTixStack();
    const soak = el.querySelector(".ppSoak"), mapEl = el.querySelector(".ppMap"), still = fsStill();
    const NS = "http://www.w3.org/2000/svg", blot = document.createElementNS(NS, "circle");
    blot.setAttribute("cx", sx.toFixed(1)); blot.setAttribute("cy", sy.toFixed(1)); blot.setAttribute("r", "0");
    soak.appendChild(blot);
    let raf = 0, auto = 0, done = false, line = null, scratched = false;
    const full = Math.hypot(Math.max(sx, v.w - sx), Math.max(sy, v.h - sy)) + 30;
    const inkIn = (ms = 1600) => {                                   // the rest soaks in from the stamp
      if (done) return;
      done = true; el.classList.add("inked"); clearTimeout(auto);
      const t0 = performance.now(), r0 = +blot.getAttribute("r");
      const step = t => { const f = Math.min(1, (t - t0) / ms); blot.setAttribute("r", (r0 + (full - r0) * (1 - Math.pow(1 - f, 3))).toFixed(1)); if (f < 1) raf = requestAnimationFrame(step); };
      if (still) blot.setAttribute("r", full.toFixed(1)); else raf = requestAnimationFrame(step);
    };
    const wait = ms => { clearTimeout(auto); auto = setTimeout(() => inkIn(), ms); };
    // the finger: each stroke inks a broad band under it; the stamp's own soak waits until it stops
    const at = e => { const b = mapEl.getBoundingClientRect(), s = Math.max(v.w / b.width, v.h / b.height); return [v.w / 2 + (e.clientX - b.left - b.width / 2) * s, v.h / 2 + (e.clientY - b.top - b.height / 2) * s]; };
    mapEl.addEventListener("pointerdown", e => {
      if (done) return;
      e.stopPropagation(); clearTimeout(auto);
      if (!scratched) { scratched = true; el.classList.add("scr"); }
      line = document.createElementNS(NS, "polyline");
      line.setAttribute("fill", "none"); line.setAttribute("stroke-width", String(Math.max(18, k * 1.6)));
      line.setAttribute("points", at(e).map(x => x.toFixed(1)).join(","));
      soak.appendChild(line);
      try { mapEl.setPointerCapture(e.pointerId); } catch {}
    });
    mapEl.addEventListener("pointermove", e => { if (line && !done) line.setAttribute("points", line.getAttribute("points") + " " + at(e).map(x => x.toFixed(1)).join(",")); });
    const up = () => { if (line) { line = null; wait(1800); } };
    mapEl.addEventListener("pointerup", up); mapEl.addEventListener("pointercancel", up);
    mapEl.addEventListener("click", e => e.stopPropagation());
    const out = () => { if (!el.isConnected || el.classList.contains("out")) return; cancelAnimationFrame(raf); clearTimeout(auto); el.classList.add("out"); setTimeout(() => { el.remove(); gTixStack(); }, 350); };
    el.onclick = () => (done ? out() : inkIn(500));
    setTimeout(() => { fsThud(); try { navigator.vibrate && navigator.vibrate(30); } catch {} }, still ? 0 : 640);   // as the stamp lands
    wait(still ? 300 : 3200);                                        // time to put a finger on it
    el.outT = setTimeout(function later(){ if (line || (!done && scratched)) { el.outT = setTimeout(later, 2000); return; } out(); }, TIX_MS + 4000);
  });
}
/* 1.81 (Dave's to-do 4, his mix of C and B): Your hangar. The Sets list as shelves you swipe, one per set, with a
   collectible card for each type: the photo of the first one you caught (its model's when it has none), the rarity in
   its colour, the name, when and which; the types still missing lie face down. Types in no set get a shelf of their
   own. A tap opens a card's details (a missing one: its model's card). Data: /game/hangar (relay 63; photos relay 64).
   1.96 (to-do #127): a type fills its card with any sighting, from any screen (relay 76: the logbook's types); one the
   game caught wears a badge and its card says how often. The face-down cards show their model's picture, dimmed.
   1.97 (to-do #132, Dave's pick 2, "Scored"): a line under the name instead of the badge, how often the game scored the
   type (every plane of it within its circle) and how often Sky view scanned it (relay 79: "scans"). */
const hangarOk = () => gameOk() && (window.OVERHEAD_RELAY_VERSION || 0) >= 63;
let hangar = null, hangarAt = 0, hgT = 0;
const hgBad = new Set();                                         // photos that didn't load: the model's instead
function hangarLoad(){
  if (!hangarOk() || Date.now() - hangarAt < 5 * 60000) return;
  hangarAt = Date.now();
  fetchJSON(`${relay()}/game/hangar`, {}, 12000).then(j => { hangar = j; renderGame(); }).catch(() => { hangarAt = Date.now() - 4 * 60000; });
}
// 1.82.2: names as the app's table has them (the relay's are "AIRBUS A-320neo", which Wikipedia doesn't know), the relay's
// as a second try; the model photo already found for them, else "".
const hgNames = (code, name) => [...new Set([TYPES[code], name].map(n => String(n || "").trim()).filter(Boolean))];
const modelPicNow = (names, code) => modelPics.get(modelKey(names, code)) || "";
/* 1.103.0.1 (to-do #166): a card's picture sits in a frame of its own size from the start (.hgPh, "heli" with a helicopter
   on the Helicopters shelf), painted in place as photos and model pictures come (hgPaint), so the shelves aren't drawn
   again for them (that made a swipe jump back). The model pictures are asked for in a queue, two at a time (hgAsk): the
   cards in view first, then every shelf's first HG_EAGER cards, then the rest; one not answered is asked again a minute
   later (twice at most). Those first cards' pictures load at once, the rest as they come near; a shelf touched has all
   its pictures fetched beside it (hgAll, hgPre), not in it. Nothing in a shelf changes while it moves, not even an
   attribute (the browser snaps it back to its card then: hgMove, hgBusy), and the Club isn't drawn again (hgHeld). */
const HG_EAGER = 6, hgQ = [], hgTries = new Map(), hgAll = new Set(), hgPreDone = new Set();
let hgRun = 0, hgIO = null, hgHeld = false, hgBusy = 0, hgMove = null, hgLate = 0;
const hgMoving = r => r === hgMove && Date.now() - hgBusy < (hgHeld ? 10000 : 800);
function hgPre(src){ if (!src || hgPreDone.has(src)) return; hgPreDone.add(src); const im = new Image(); im.referrerPolicy = "no-referrer"; im.src = src; }
/* 1.105 (to-do #149, Dave's pick A "metal frames", without its medal on the shelf): mastery. A type's scans climb its
   card bronze, silver, gold (relay 88: rules.mastery, [scans, bonus] a step, paid at the scan that reaches it). On the
   shelf only the card's frame in its metal (and a thin bar to the next step); the opened card has the three steps. */
const MST = [[5, 25], [25, 100], [100, 250]], MST_NAME = ["", "Bronze", "Silver", "Gold"];
const MST_TO = ["{n} of {m} scans to bronze", "{n} of {m} scans to silver", "{n} of {m} scans to gold"];
const mstSteps = () => { const r = gRules(); return (r && r.mastery) || MST; };
const mstOf = n => mstSteps().filter(st => (n || 0) >= st[0]).length;
// the way to the next step: its index, the share done (0–1); null at gold
function mstNext(n){
  const st = mstSteps(), k = mstOf(n);
  if (k >= st.length) return null;
  const lo = k ? st[k - 1][0] : 0;
  return {k, at: st[k][0], p: st[k][1], f: Math.max(0, Math.min(1, ((n || 0) - lo) / (st[k][0] - lo)))};
}
const mstBar = f => `<span class="mkBar"><i style="width:${Math.round(f * 100)}%"></i></span>`;
// the opened card's part: the three steps (scans and bonus; those not reached dimmed), the bar and how far to the next
function mstHtml(n){
  const k = mstOf(n), nx = mstNext(n), med = `<svg viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="${RK_STAR}"/></svg>`;
  return `<div class="mkMast"><h4>${escH(T("Mastery"))}${k ? `<b>${escH(T(MST_NAME[k]))}</b>` : ""}</h4><div class="mkSteps">` +
    mstSteps().map(([at, p], i) => `<div class="mk${i + 1}${k > i ? "" : " off"}"><span class="md">${med}</span><b>${escH(T(MST_NAME[i + 1]))}</b>` +
      `${escH(T("{n} scans · +{p}", {n: nf.format(at), p: nf.format(p)}))}</div>`).join("") + `</div>` +
    (nx ? mstBar(nx.f) + `<div class="mkBarT"><b>${escH(T(MST_TO[nx.k], {n: nf.format(n || 0), m: nf.format(nx.at)}))}</b><span>+${nf.format(nx.p)}</span></div>`
      : `<div class="mkBarT"><b>${escH(T("Gold: {n} scans", {n: nf.format(n || 0)}))}</b></div>`) + `</div>`;
}
function hangarHtml(hg){
  const by = new Map((hg.types || []).map(t => [t.code, t])), inSet = new Set((hg.sets || []).flatMap(s => s.types));
  const card = (code, heli, eager) => {
    const t = by.get(code), names = hgNames(code, t && t.name), name = typeLabel(code, t && t.name);
    const img = `<span class="hgPh${heli || SPECIAL_TYPES[code] === "HELICOPTER" ? " heli" : ""}" data-mp="${escH(names.join("|"))}"` +
      `${t ? ` data-own="${escH([t.thumb, t.photo].filter(Boolean).join(" "))}"` : ""}${eager ? ' data-e="1"' : ""}></span>`;
    if (!t) return `<button type="button" class="hgCard back" data-hg="${escH(code)}">${img}<b>${escH(code)}</b><span>${escH(T("still to find"))}</span></button>`;
    const mk = mstOf(t.scans), nx = t.scans ? mstNext(t.scans) : null;
    return `<button type="button" class="hgCard${mk ? " mk" + mk : ""}" data-hg="${escH(code)}" style="--t:${TIER_COL[t.tier] || TIER_COL.uncommon}">` + img +
      `<span class="hgT"><em>${escH(T(TIER_NAME[t.tier] || "Uncommon"))}</em><b>${escH(name)}</b>` +
      `<span>${escH([t.first ? T("First: {d}", {d: fmtDay(t.first)}) : "", t.reg].filter(Boolean).join(" · "))}</span>` +
      (t.game ? `<span class="hgL"><i>★</i>${escH(T("Scored {n}×", {n: nf.format(t.game)}))}${t.scans ? `<u>· ${escH(T("{n} scanned", {n: nf.format(t.scans)}))}</u>` : ""}</span>`
        : `<span class="hgL no">${escH(T("Not scored yet"))}</span>`) + (nx ? mstBar(nx.f) : "") + `</span></button>`;
  };
  const shelf = (key, name, codes, count, done) => `<div class="hgShelf"><div class="hgHead"><b>${escH(name)}</b><em${done ? ' class="done"' : ""}>${escH(count)}</em></div>` +
    `<div class="hgRow" data-set="${escH(key)}">${codes.map((c, i) => card(c, key === "Helicopters", i < HG_EAGER)).join("")}</div></div>`;
  const shelves = (hg.sets || []).map(s => {
    const have = s.types.filter(c => by.has(c)), miss = s.types.filter(c => !by.has(c));
    return shelf(s.name, T(s.name), have.sort((a, b) => (by.get(b).first || 0) - (by.get(a).first || 0)).concat(miss), `${have.length} / ${s.types.length}`, have.length >= s.types.length);
  });
  const other = (hg.types || []).filter(t => !inSet.has(t.code)).map(t => t.code);
  if (other.length) shelves.push(shelf("_other", T("Other types"), other, nf.format(other.length)));
  const n = (hg.types || []).length, g = (hg.types || []).filter(t => t.game).length;
  return secPlate(T("Your hangar"), `<p class="sum">${escH(T(n === 1 ? "1 type seen" : "{n} types seen", {n: nf.format(n)}) + " · " + T("★ {n} scored in the game", {n: nf.format(g)}))}</p>${shelves.join("")}`, "hgPlate");
}
// The cards' taps; the pictures painted, the model pictures asked for (those in view first), the shelves watched.
function hgWire(box){
  for (const b of box.querySelectorAll("[data-hg]")) b.onclick = () => hangarCard(b.dataset.hg);
  const rows = [...box.querySelectorAll(".hgRow")], frames = r => [...r.querySelectorAll(".hgPh")];
  for (const r of rows) {
    const touch = () => {
      hgBusy = Date.now(); hgMove = r;
      if (hgAll.has(r.dataset.set)) return;
      hgAll.add(r.dataset.set);
      for (const el of frames(r).reverse()) { hgPre(hgPic(el)); hgAsk(el, true); }
    };
    r.addEventListener("touchstart", () => { hgHeld = true; touch(); }, {passive: true});
    r.addEventListener("touchend", () => { hgHeld = false; hgBusy = Date.now(); }, {passive: true});
    r.addEventListener("touchcancel", () => { hgHeld = false; }, {passive: true});
    r.addEventListener("scroll", touch, {passive: true});
  }
  hgPaint(box);
  for (const r of rows) frames(r).slice(0, HG_EAGER).forEach(el => hgAsk(el));
  for (const r of rows) frames(r).slice(HG_EAGER).forEach(el => hgAsk(el));
  if (hgIO) hgIO.disconnect();
  if (typeof IntersectionObserver !== "function") return;
  hgIO = new IntersectionObserver(es => { for (const e of es) if (e.isIntersecting) { hgIO.unobserve(e.target); hgAsk(e.target, true); } }, {rootMargin: "150px"});
  for (const el of box.querySelectorAll(".hgPh")) if (!el.firstChild) hgIO.observe(el);
}
// What a frame shows now: the first one's own photo, else its model's ("" none yet).
function hgPic(el){
  const own = (el.dataset.own || "").split(" ").find(u => u && !hgBad.has(u));
  const mp = modelPicNow(el.dataset.mp.split("|").filter(Boolean), el.closest("[data-hg]").dataset.hg);
  return own || (mp && !hgBad.has(mp) ? mp : "");
}
function hgPaint(root){
  for (const el of root.querySelectorAll(".hgPh")) {
    const src = hgPic(el), old = el.firstElementChild, row = el.closest(".hgRow");
    if (old ? old.getAttribute("src") === src : !src) continue;
    if (hgMoving(row)) { clearTimeout(hgLate); hgLate = setTimeout(() => hgPaint($("gameBox")), 900); continue; }    // once it stands still
    if (hgAll.has(row.dataset.set)) hgPre(src);
    if (!src) { old.remove(); continue; }
    const im = old || document.createElement("img");
    im.alt = ""; im.referrerPolicy = "no-referrer"; im.decoding = "async"; im.loading = el.dataset.e ? "eager" : "lazy";
    im.onerror = () => { hgBad.add(src); hgPaint(el.parentNode); hgAsk(el, true); };
    im.src = src;
    if (!old) el.append(im);
  }
}
function hgAsk(el, first){
  if (S.demo || !el.isConnected || hgPic(el)) return;
  const code = el.closest("[data-hg]").dataset.hg, names = el.dataset.mp.split("|").filter(Boolean), k = modelKey(names, code);
  if (modelPics.has(k)) return;                                  // being looked for, or looked for already
  const i = hgQ.findIndex(q => q.k === k);
  if (i >= 0) { if (!first) return; hgQ.splice(i, 1); }
  hgQ[first ? "unshift" : "push"]({k, names, code});
  hgPump();
}
function hgPump(){
  while (hgRun < 2 && hgQ.length && tab === "game") {
    const q = hgQ.shift();
    if (modelPics.has(q.k)) continue;
    hgRun++;
    modelPic(q.names, null, q.code);
    modelLook(q.names, q.code).catch(() => {
      const n = (hgTries.get(q.k) || 0) + 1;
      hgTries.set(q.k, n);
      if (n < 3) setTimeout(() => { if (!modelPics.has(q.k)) { hgQ.push(q); hgPump(); } }, 61000);
    }).then(() => { hgRun--; hgPaint($("gameBox")); setTimeout(hgPump, 100); });
  }
}
function hgSoon(){ clearTimeout(hgT); hgT = setTimeout(renderGame, 400); }
function hangarCard(code, again){
  const t = hangar && (hangar.types || []).find(x => x.code === code);
  if (!t) return typeCard({typeCode: code, type: TYPES[code] || code});      // still to find: what the model is
  if (!again) ctlSound.nav();
  let tok = 0;                                    // 1.93.1.1: the model's picture found later comes to the card while it is open
  const name = typeLabel(code, t.name), pic = [t.photo, t.thumb].find(u => u && !hgBad.has(u));
  const mp = !pic && modelPic(hgNames(code, t.name), () => { if (tok === cardTok && cardOpenNow()) hangarCard(code, true); }, code);
  // 1.94: in Sky view's card style: the photo with the name, code and tier on it; 1.97: how often seen, scored, scanned
  tok = cardOpen(infoCard({pic: pic || mp ? {src: pic || mp, kind: pic ? "own" : "model"} : modelAsking(hgNames(code, t.name), code) ? {src: "", asking: true} : null, title: name, sub: code,
    chip: `<span class="cChip" style="background:${TIER_COL[t.tier] || TIER_COL.uncommon};color:#fff">${escH(T(TIER_NAME[t.tier] || "Uncommon"))}</span>`,
    // 1.96: how often seen (any screen) and scored in the game; the first one's aircraft went to the details
    tiles: [["Seen", timesText(t.count)], ["Scored", t.game ? timesText(t.game) : "–"], ["Scanned", t.scans ? timesText(t.scans) : "–"]],
    afterTiles: mstHtml(t.scans),                 // 1.105: mastery
    det: [["Aircraft", escH(t.reg || "")], ["Airline", escH(t.airline || "")], ["Flight", escH(t.flight || "")], ["Code", escH(code)]],
    btns: `<div class="cBtns">${scBtn(code)}<button class="cBtn" type="button" data-hgm>${escH(T("About this model"))}</button></div>`}), el => {
    el.querySelector("[data-hgm]").onclick = () => typeCard({typeCode: code, type: name});
    scWire(el, code, name);
  });
}
/* 1.108 (to-do #156, Dave's pick A, the glass cabinet, "and add the origin/destination"): the showcase. Up to three
   catches pinned to your player card, as the hangar's cards in miniature behind a glass pane, each with its route; the
   spots open at levels 3, 5 and 8 (the relay's showcase_json: the pins, and the spots still locked with the points to
   go). A hangar card pins its type's best catch, which the relay picks (relay 91, showcase_catch): one Sky view scanned
   before one the game scored before one only seen; then one with a known route; then the first. Others see the pins
   on your card, never where you were; you see your empty and locked spots too. */
const SC_LOCK = `<svg viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M7 10V7a5 5 0 0 1 10 0v3h1a1 1 0 0 1 1 1v9a1 1 0 0 1-1 1H6a1 1 0 0 1-1-1v-9a1 1 0 0 1 1-1zm2 0h6V7a3 3 0 0 0-6 0z"/></svg>`;
const scMine = () => gme && gme.showcase;
const scDate = t => new Date(t).toLocaleDateString(LOC(), {day: "numeric", month: "short"}).replace(/\.$/, "");
function scPin(x, attr){
  const pic = [x.thumb, x.photo].find(u => u && !hgBad.has(u)) || modelPicNow(hgNames(x.code, x.name), x.code);
  const rt = x.route && x.route.length === 2 && x.route.every(Boolean) ? `${x.route[0]} → ${x.route[1]}` : "", tag = attr ? "button" : "div";
  return `<${tag}${attr ? ` type="button"${attr}` : ""} class="hgCard sc" data-scc="${escH(x.code)}" data-scn="${escH(x.name || "")}" style="--t:${TIER_COL[x.tier] || TIER_COL.uncommon}">` +
    (pic ? `<img src="${escH(pic)}" alt="">` : `<span class="hgPh"></span>`) +
    `<span class="hgT"><em>${escH(T(TIER_NAME[x.tier] || "Uncommon"))}</em><b>${escH(typeLabel(x.code, x.name))}</b>` +
    (rt ? `<span class="scRt">${escH(rt)}</span>` : "") +
    `<span>${escH([x.airline || x.flight, x.ts ? scDate(x.ts) : ""].filter(Boolean).join(" · "))}</span></span></${tag}>`;
}
// The pictures: a photo that doesn't load gives way to the model's, asked for and painted in when it comes.
function scPics(el){
  for (const c of el.querySelectorAll(".scCab [data-scc]")) {
    const code = c.dataset.scc, names = hgNames(code, c.dataset.scn), im = c.querySelector("img");
    const model = () => { const u = modelPicNow(names, code), ph = c.isConnected && c.querySelector(".hgPh"); if (u && ph) ph.outerHTML = `<img src="${escH(u)}" alt="">`; };
    const ask = () => { if (modelPic(names, model, code)) model(); };
    if (im) im.onerror = () => { hgBad.add(im.getAttribute("src")); im.outerHTML = `<span class="hgPh"></span>`; ask(); };
    else ask();
  }
}
// The cabinet. o.mine: the empty and locked spots too (your own card); o.pick: each open spot a button (data-scp).
function scCab(sc, o = {}){
  const pins = (sc && sc.pins) || [], locked = o.mine ? (sc && sc.locked) || [] : [];
  const at = i => o.pick ? ` data-scp="${i}"` : "";
  const cells = pins.map((x, i) => x ? scPin(x, at(i)) : o.mine ? `<${o.pick ? `button type="button"${at(i)}` : "div"} class="hgCard sc emp">` +
      `<b>${escH(T("Empty spot"))}</b><span>${escH(T("Pin one from your hangar"))}</span></${o.pick ? "button" : "div"}>` : "").join("") +
    locked.map(l => `<div class="hgCard sc emp lk">${SC_LOCK}<b>${escH(T("Opens at level {n}", {n: l.level}))}</b><span>${escH(T("{n} to go", {n: nf.format(l.toGo)}))}</span></div>`).join("");
  return cells ? `<div class="scCab">${cells}</div>` : "";
}
// The hangar card's button: put the type in (the first empty spot, else the spots to swap with) or take it out.
function scBtn(code){
  const sc = scMine();
  if (!sc || !(sc.pins || []).length) return "";
  return `<button class="cBtn" type="button" data-scb>${escH(T(sc.pins.some(x => x && x.code === code) ? "Take out of your showcase" : "Put in your showcase"))}</button>`;
}
function scWire(el, code, name){
  const b = el.querySelector("[data-scb]");
  if (!b) return;
  const pin = async (spot, out) => {
    let r = null;
    try { r = await fetchJSON(`${relay()}/game/showcase`, {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({code: out ? "" : code, spot})}, 8000); } catch {}
    if (!r || !r.pins) { toast(T("Couldn't change your showcase.")); return; }
    if (gme) gme.showcase = r;
    toast(T(out ? "Back in your hangar" : "In your showcase"));
    if (el.isConnected && cardOpenNow()) hangarCard(code, true);
  };
  b.onclick = () => {
    const pins = scMine().pins, i = pins.findIndex(x => x && x.code === code);
    if (i >= 0) return pin(i, true);
    const free = pins.indexOf(null);
    if (free >= 0) return pin(free);
    ctlSound.nav();
    let box = el.querySelector(".scPick");                   // all full: tap a spot to swap
    if (!box) {
      el.querySelector(".cBtns").insertAdjacentHTML("afterend", `<div class="scPick"><h4>${escH(T("Where should the {t} go?", {t: name.replace(/^(Airbus|Boeing|Embraer|Bombardier|McDonnell Douglas|De Havilland Canada) /, "")}))}</h4>` +
        `<p>${escH(T("Tap a spot to swap: that one goes back to your hangar."))}</p>${scCab(scMine(), {mine: true, pick: true})}</div>`);
      box = el.querySelector(".scPick");
      scPics(box);
      for (const s of box.querySelectorAll("[data-scp]")) s.onclick = () => pin(+s.dataset.scp);
    }
    box.scrollIntoView({block: "end", behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth"});
  };
}
function recordsHtml(all, g0){
  const rank = (items, plain) => `<ol class="ranks${plain ? " plain" : ""}">${items.join("")}</ol>`;
  const li = (name, n, sub) => `<li><span class="name">${escH(name)}${sub ? `<span class="s">${escH(sub)}</span>` : ""}</span><span class="n">${escH(n)}</span></li>`;
  let html = "";
  const r = all.records;
  if (r && (r.closest || r.lowest || r.fastest || r.farthest)) {           // lifetime records (relay 28; the game's since relay 59)
    const who = x => x.callsign || x.reg || x.type || "", p = r.farthest && r.farthest.place;
    const rows = [["Closest ever", r.closest, x => `${x.v < 10 ? x.v.toFixed(2) : Math.round(x.v)} km`], ["Lowest ever", r.lowest, x => altitudeStr(x.v).toLowerCase()],
      ["Fastest ever", r.fastest, x => speedStr(x.v).toLowerCase()], ["Farthest route", r.farthest, x => `${p ? p.code || p.city : ""} · ${nf.format(x.v)} km`]].filter(x => x[1]);
    html += secPlate(T("Records"), rank(rows.map(([en, x, val]) => li(T(en), val(x), [who(x), x.ts ? fmtDay(x.ts) : ""].filter(Boolean).join(" · "))), true));
  }
  const bg = g0 && g0.bingo;
  if (bg && bg.card) {                                 // the weekly bingo (relay 29)
    const nd = Object.keys(bg.done || {}).length;
    const cells = bg.card.map(k => { const d = (bg.done || {})[k];
      return `<div class="bc${d ? " on" : ""}"><i></i><span>${escH(goalText(k))}</span>${d ? `<small>${escH(fmtDay(d))}</small>` : ""}</div>`; }).join("");
    html += secPlate(T("This week's bingo"), `<p class="sum">${escH(T("{n} of 9 done · full lines: {l}", {n: nd, l: bg.lines || 0}))} · ${escH(bingoReset(bg))}</p><div class="bingo">${cells}</div>`);
  }
  if (g0) html += trophiesHtml(g0);
  return html;
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
// The trophies (1.55). 1.79 (Dave's pick B): the three closest to winning first, each a line with its bar. 1.79.2 (Dave's
// picks): a switch shows Closest, Won or Still to win, one list at a time (kept while the page updates); a trophy with
// ranks shows its rank's medal, bronze to diamond: the cup in that metal (filled once won) and a tag before the dots.
let gTrTab = "near";
function trophiesHtml(g0){
  const won = g0.trophies || {}, nWon = TROPHY_IDS.filter(k => won[k]).length;
  const lads = TROPHY_LADDERS.map(L => ({L, st: trophyLadder(g0, L)}));
  const prog = x => x.st.next && x.st.have != null ? Math.min(1, x.st.have / x.st.next[1]) : 0;
  const todo = lads.filter(x => x.st.next).sort((a, b) => prog(b) - prog(a));
  const pips = st => `<span class="pips">${st.tiers.map(x => `<b class="${st.won[x[0]] ? "on" : ""}"></b>`).join("")}</span>`;
  const medal = (st, t) => { const i = st.tiers.indexOf(t); return {cls: ` medal m${i}`, tag: `<span class="metal">${escH(T(TROPHY_MEDALS[i]))}</span>`}; };
  const row = (on, name, what, right, extra = "", cls = "") => `<li class="${on ? "on" : ""}${cls}">${CUP}<span class="name">${escH(name)}${what ? ` <span class="s">${escH(what)}</span>` : ""}</span>` +
    `<span class="n">${escH(right)}</span>${extra}</li>`;
  const toGo = x => { const t = x.st.next, m = medal(x.st, t);
    return row(false, T(t[2]), T(x.L[1], {n: nf.format(t[1])}), x.st.have != null ? `${nf.format(Math.min(x.st.have, t[1]))} / ${nf.format(t[1])}` : "",
      `<span class="tl">${m.tag}${pips(x.st)}<span class="bar"><i style="width:${(prog(x) * 100).toFixed(1)}%"></i></span></span>`, m.cls); };
  const single = k => { const [nm, what] = trophyText(k); return row(!!won[k], nm, what, won[k] ? fmtDay(won[k]) : ""); };
  const lists = {near: todo.slice(0, 3).map(toGo),
    won: lads.filter(x => x.st.last).map(x => { const t = x.st.last, m = medal(x.st, t);
      return row(true, T(t[2]), T(x.L[1], {n: nf.format(t[1])}), fmtDay(x.st.won[t[0]]),
        `<span class="tl">${m.tag}${pips(x.st)}${x.st.next ? `<span class="nx">${escH(T("Next: {name}", {name: T(x.st.next[2])}))}</span>` : ""}</span>`, m.cls); })
      .concat(TROPHY_SINGLES.filter(k => won[k]).map(single)),
    todo: todo.map(toGo).concat(TROPHY_SINGLES.filter(k => !won[k]).map(single))};
  const tabs = [["near", T("Closest")], ["won", T("Won · {n}", {n: nWon})], ["todo", T("Still to win")]];
  const none = {near: "Every rank is won.", won: "No trophies won yet.", todo: "Every trophy is won."}[gTrTab];
  return secPlate(T("Trophies"), `<p class="sum">${escH(T("{n} of {t} won", {n: nWon, t: TROPHY_IDS.length}))}</p>` +
    `<div class="seg trSeg" role="group">${tabs.map(([k, l]) => `<button type="button" data-tt="${k}" aria-pressed="${k === gTrTab}">${escH(l)}</button>`).join("")}</div>` +
    (lists[gTrTab].length ? `<ul class="ranks plain cups">${lists[gTrTab].join("")}</ul>` : `<p class="sum">${escH(T(none))}</p>`));
}
// The trophies' switch, on the Spotters' Club page or the Logbook's Records: redraws the page that shows it.
function trWire(box, redraw){
  for (const b of box.querySelectorAll("[data-tt]")) b.onclick = () => { if (b.dataset.tt === gTrTab) return; ctlSound.nav(); gTrTab = b.dataset.tt; redraw(); };
}
// 1.83 (Dave): a section of the Logbook, the Spotters' Club or the radar on a plate of its own, as Settings' and the
// radar's controls: screws in the corners, its name engraved between two lines.
const secPlate = (title, body, cls = "") => `<section class="plate secPlate${cls ? " " + cls : ""}" style="--cols:1"><i></i><i></i><i></i><i></i><h3>${escH(title)}</h3>${body}</section>`;
// A trophy cup for the trophies list (gold when won, by CSS).
const CUP = '<svg class="cup" viewBox="0 0 24 24" aria-hidden="true"><path d="M7 3h10c0 5-1.5 8-5 8.5C8.5 11 7 8 7 3zM11 11.5h2l.5 4h-3zM8 16h8v2.2H8z"/><path d="M7 4.5C4.5 4.5 4 8 7.5 9M17 4.5c2.5 0 3 3.5-.5 4.5" fill="none" stroke-width="1.6"/></svg>';
// The year in planes (relay 29, /year): a card at the top of the Logbook with a Share button (a picture of the card)
// and the logbook as a spreadsheet (/logbook.csv).
let yearData = null, yearAt = {}, yearCache = {};
function fetchYear(){
  const y = new Date().getFullYear() - yearBack;
  yearData = yearCache[y] || null;
  if (!relay() || (window.OVERHEAD_RELAY_VERSION || 0) < 29 || Date.now() - (yearAt[y] || 0) < 5 * 60000) return;
  yearAt[y] = Date.now();
  fetchJSON(`${relay()}/year?y=${y}`, {}, 10000).then(j => { yearCache[y] = j; if (y === new Date().getFullYear() - yearBack) yearData = j; lbSig = ""; renderLogbook(); }).catch(() => { yearAt[y] = 0; });
}
function yearFacts(y){
  const r = y.rarest, m = y.mostSeen, b = y.busiest;
  return [[T("Busiest day"), b ? `${fmtDay(Date.parse(b.day))} · ${nf.format(b.planes)}` : ""],
    [T("Most seen aircraft"), m && m.count > 1 ? `${m.reg} · ${T("{n} times", {n: nf.format(m.count)})}` : ""],
    [T("Rarest"), r ? `${r.type || r.reg} · ${T(TIER_NAME[r.tier] || "")}` : ""]].filter(x => x[1]);
}
// 1.74: the Logbook's period card: this week, this month or the year in one card, picked with Week · Month · Year,
// ◀ ▶ for earlier and later (week and month from /review, relay 46; the year from /year, with Share and the CSV).
let lbPeriod = "year", yearBack = 0;
function periodHtml(){
  const per = reviewOk() ? lbPeriod : "year", yr = new Date().getFullYear() - yearBack, back = per === "year" ? yearBack : review.back;
  const seg = reviewOk() ? `<div class="seg lbPer" role="group">` + [["week", "Week"], ["month", "Month"], ["year", "Year"]]
    .map(([k, l]) => `<button type="button" data-per="${k}" aria-pressed="${per === k}">${escH(T(l))}</button>`).join("") + `</div>` : "";
  const arrows = `<span class="perArr"><button class="cBtn" type="button" data-pb="1" aria-label="${escH(T("Earlier"))}">◀</button>` +
    `<button class="cBtn" type="button" data-pb="-1" aria-label="${escH(T("Later"))}"${back ? "" : " disabled"}>▶</button></span>`;
  const nums = list => `<div class="yNums">` + list.map(([n, k]) => `<div><b>${nf.format(n || 0)}</b><span>${escH(T(k))}</span></div>`).join("") + `</div>`;
  const facts = list => `<dl class="yFacts">` + list.filter(x => x[1]).map(([k, v]) => `<div><dt>${escH(k)}</dt><dd>${escH(v)}</dd></div>`).join("") + `</dl>`;
  let title, body;
  if (per === "year") {
    const y = yearData && yearData.year === yr ? yearData : null;
    title = T("{y} in planes", {y: yr});
    body = !y ? `<p class="sum">${escH(T("Loading …"))}</p>` : !y.planes ? `<p class="sum">${escH(T("No planes that year."))}</p>`
      : nums([[y.planes, "planes"], [y.types, "types"], [y.airlines, "airlines"], [y.airframes, "airframes"], [y.countries, "countries"], [y.days, "days"]]) + facts(yearFacts(y)) +
        `<div class="yActs"><button class="cBtn" type="button" id="yShare">${escH(T("Share"))}</button>` +
        `<a class="cBtn" id="yCsv" href="${escH(relay())}/logbook.csv" download>${escH(T("Download the logbook (CSV)"))}</a></div>` +
        `<p class="sum">${escH(T("Every sighting as a spreadsheet, for a spotting app or Excel."))}</p>`;
  } else {
    const r = reviewData();
    title = T("{p} in planes", {p: reviewTitle()});
    body = `<p class="sum">${escH(reviewSummary(r))}</p>` + (r && r.planes ? nums(REVIEW_NUMS.map(([k, l]) => [r[k], l])) +
      facts(reviewFacts(r).concat([[T("New types"), reviewNewTypes(r)]])) +
      `<div class="yActs"><button class="cBtn" type="button" id="pShare">${escH(T("Share"))}</button></div>` : "");
  }
  return secPlate(title, `<div class="perHead">${seg}${arrows}</div>${body}`, "perCard");
}
document.addEventListener("click", e => {
  const b = e.target && e.target.closest && e.target.closest("[data-per], [data-pb]");
  if (!b || b.disabled) return;
  ctlSound.click();
  if (b.dataset.per) { lbPeriod = b.dataset.per; if (lbPeriod !== "year") { review.span = lbPeriod; review.back = 0; } }
  else if (lbPeriod === "year") yearBack = Math.max(0, Math.min(10, yearBack + +b.dataset.pb));
  else review.back = Math.max(0, Math.min(60, review.back + +b.dataset.pb));
  lbSig = ""; renderLogbook();
});
// Week and month in review (1.52, relay 46): a card above the year's, with Week / Month and earlier / later.
function reviewHtml(){
  if (!reviewOk()) return "";
  const r = reviewData(), bt = (a, t, on, x = "") => `<button class="cap small" type="button" ${a}${on != null ? ` aria-pressed="${on}"` : ""}${x}>${t}</button>`;
  const tools = `<div class="rvTools">${bt('data-rs="week"', escH(T("Week")), review.span === "week")}${bt('data-rs="month"', escH(T("Month")), review.span === "month")}` +
    `<span></span>${bt('data-rb="1"', "◀", null, ` aria-label="${escH(T("Earlier"))}"`)}${bt('data-rb="-1"', "▶", null, ` aria-label="${escH(T("Later"))}"${review.back ? "" : " disabled"}`)}</div>`;
  const head = `<h3>${escH(reviewTitle())}</h3>${tools}<p class="sum">${escH(reviewSummary(r))}</p>`;
  if (!r || !r.planes) return `<div class="yearCard reviewCard">${head}</div>`;
  const nums = REVIEW_NUMS.map(([k, l]) => `<div><b>${nf.format(r[k] || 0)}</b><span>${escH(T(l))}</span></div>`).join("");
  const facts = reviewFacts(r).concat([[T("New types"), reviewNewTypes(r)]]).filter(x => x[1]);
  return `<div class="yearCard reviewCard">${head}<div class="yNums">${nums}</div><dl class="yFacts">` +
    facts.map(([k, v]) => `<div><dt>${escH(k)}</dt><dd>${escH(v)}</dd></div>`).join("") + `</dl></div>`;
}
document.addEventListener("click", e => {
  const b = e.target && e.target.closest && e.target.closest("[data-rs], [data-rb]");
  if (!b || b.disabled) return;
  ctlSound.click();
  if (b.dataset.rs) { review.span = b.dataset.rs; review.back = 0; } else review.back = Math.max(0, Math.min(60, review.back + +b.dataset.rb));
  lbSig = ""; renderLogbook();
});
// The year card as a picture to share (1.74); since 1.80 (Dave's to-do 8, his pick A) the week and the month in the same
// look: the mark, the title (and the dates), six numbers and up to three facts. Shown in a card with Share and Save.
const PIC_ONE = {planes: "plane", types: "type", airlines: "airline", airframes: "airframe", countries: "country", "new types": "new type", points: "point", days: "day"};
function periodPicture(p){
  const cv = document.createElement("canvas"), g = cv.getContext("2d"), W2 = 1080, H2 = 1350, dy = p.sub ? 24 : 0;
  cv.width = W2; cv.height = H2;
  g.fillStyle = "#0b0b0c"; g.fillRect(0, 0, W2, H2);
  g.fillStyle = "#f0b429"; rr(g, 80, 80, 140, 140, 18); g.fill();
  drawPlane(g, 150, 150, 120, "#0b0b0c");
  const by = spottedBy();
  g.fillStyle = "#f3f0e8"; g.font = `700 64px ${FONT}`; g.fillText("FALLBLATT", 260, by ? 152 : 170);
  if (by) { g.fillStyle = "#959aa3"; g.font = `600 34px ${FONT}`; g.fillText(by, 262, 204); }     // 1.82.1: whose it is
  let fs = 92;
  g.font = `700 ${fs}px ${FONT}`;
  while (fs > 52 && g.measureText(p.title).width > W2 - 160) g.font = `700 ${fs -= 4}px ${FONT}`;    // "Last month in planes" is long
  g.fillStyle = "#f0b429"; g.fillText(p.title, 80, 360);
  if (p.sub) { g.fillStyle = "#959aa3"; g.font = `600 38px ${FONT}`; g.fillText(p.sub, 80, 424); }
  p.nums.forEach(([n, k], i) => {
    const x = 80 + (i % 3) * 320, yy = 520 + dy + Math.floor(i / 3) * 210;
    g.fillStyle = "#f3f0e8"; g.font = `700 96px ${FONT}`; g.fillText(nf.format(n || 0), x, yy);
    g.fillStyle = "#959aa3"; g.font = `600 36px ${FONT}`; g.fillText(T(n === 1 ? PIC_ONE[k] || k : k), x, yy + 52);
  });
  p.facts.slice(0, 3).forEach(([k, v], i) => {
    const yy = 1000 + dy + i * 100;
    g.fillStyle = "#f0b429"; g.font = `600 30px ${FONT}`; g.fillText(k.toUpperCase(), 80, yy);
    g.fillStyle = "#f3f0e8"; g.font = `700 44px ${FONT}`; g.fillText(v, 80, yy + 50);
  });
  return new Promise(ok => cv.toBlob(ok, "image/png"));
}
async function shareYear(){
  ctlSound.click();
  const y = yearData;
  picCard(await periodPicture({title: T("{y} in planes", {y: y.year}), facts: yearFacts(y),
    nums: [[y.planes, "planes"], [y.types, "types"], [y.airlines, "airlines"], [y.airframes, "airframes"], [y.countries, "countries"], [y.days, "days"]]}), `fallblatt-${y.year}.png`);
}
async function sharePeriod(){
  const r = reviewData();
  if (!r || !r.planes) return;
  ctlSound.click();
  const yr = {day: "numeric", month: "short", year: "numeric"};
  const sub = r.complete === false ? `${reviewDay(r.start, yr)} – ${T("today")}` : `${reviewDay(r.start)} – ${reviewDay(r.end, yr)}`;
  picCard(await periodPicture({title: T("{p} in planes", {p: reviewTitle()}), sub, facts: reviewFacts(r).filter(x => x[1]),
    nums: [[r.planes, "planes"], [r.types, "types"], [r.airlines, "airlines"], [r.newTypeCount, "new types"], r.points != null ? [r.points, "points"] : [r.airframes, "aircraft"], [r.days, "days"]]}),
    `fallblatt-${r.span}-${r.start}.png`);
}
document.addEventListener("click", e => { if (e.target && e.target.id === "pShare") sharePeriod(); });
document.addEventListener("click", e => { if (e.target && e.target.id === "yShare") shareYear(); });

// Where to look (1.28): from the place to the plane on top, its compass direction and how high to look; a dial with
// north up, or, with the compass (secure pages only; iPhones ask first), turning with the phone so the arrow points
// at the plane.
let lookHeading = null, lookOn = false, lookRaf = 0, lookErr = "", lookErrAt = 0;
let lookWhy = "", lookWhyLogged = "";
function lookAt(){
  if (!feat || !feat.o || feat.o.ac.lat == null) { lookWhy = feat ? "no position" : ""; return null; }
  // 1.75.2: where the plane is now and how high (as Sky view has it: moved on from the data's time, its true height)
  const ac = feat.o.ac, mv = arMove(ac, Math.min(60, (Date.now() - arListAt) / 1000 + (ac.seen_pos || 0))), wx = arWeather(), h = arHeight(ac, wx);
  const kx = 111.32 * Math.cos(S.lat * Math.PI / 180), x = (ac.lon - S.lon) * kx + mv[0] / 1000, y = (ac.lat - S.lat) * 110.57 + mv[1] / 1000;
  const km = Math.hypot(x, y), brg = (Math.atan2(x, y) * 180 / Math.PI + 360) % 360, alt = feat.o.alt;
  lookWhy = alt == null || h == null ? "no height" : km > 80 ? `${Math.round(km)} km away` : !isFinite(km) ? "position unclear" : "";
  if (lookWhy) return null;
  const up = Math.round(Math.atan2(Math.max(0, h + mv[2] - wx.elev) - km * km * 1e6 / (2 * 6371000) * .87, Math.max(50, km * 1000)) * 180 / Math.PI);
  return {brg, up, km, alt, dir: ["N", "NE", "E", "SE", "S", "SW", "W", "NW"][Math.round(brg / 45) % 8]};
}
function drawLook(){
  lookRaf = 0;
  let L = null;
  try { L = lookAt(); } catch (e) { lookWhy = "error: " + (e && e.message || e); }
  // 1.78.1: a plane on top without a direction says why in the connection log (once a plane)
  if (!L && feat && lookWhy && lookWhyLogged !== feat.hex + lookWhy) { lookWhyLogged = feat.hex + lookWhy; dlog(/^error/.test(lookWhy) ? "warn" : "debug", `Where to look: none for ${planeName(feat, feat.o.ac)} (${lookWhy})`); }
  const box = $("look"), why = !L && feat && feat.o ? lookWhy : "";
  box.hidden = (!L && !why) || SIDEWAYS.matches;
  box.classList.toggle("why", !!why);
  if (box.hidden) return skyRowRender();
  if (why) return lookWhyDraw(why);
  // 1.73.1: a heading tape: with the compass the directions slide as the phone turns and the words say which way to
  // turn; without it the tape is centred on the plane
  const on = lookOn && lookHeading != null, c = on ? lookHeading : L.brg, d = ((L.brg - c + 540) % 360) - 180;
  const ad = Math.abs(d), side = d > 0 ? "right" : "left";
  $("lookDir").textContent = !on ? T("LOOK {d} · {e}° UP", {d: L.dir, e: L.up})
    : ad <= 8 ? T("Straight ahead · {e}° up", {e: L.up}) : T(ad < 45 ? `Turn a little ${side} · {e}° up` : `Turn ${side} · {e}° up`, {e: L.up});
  $("lookSub").textContent = [L.dir, T("{n} km away · {a}", {n: L.km < 10 ? L.km.toFixed(1) : Math.round(L.km), a: altitudeStr(L.alt).toLowerCase()})].join(" · ") + " · " +
    (lookErr && Date.now() - lookErrAt < 10000 ? lookErr : on ? T("The gold line is where you face.")
      : !lookOn && /iPhone|iPad/.test(navigator.userAgent) && window.isSecureContext ? T("Tap the strip to let it turn with your phone.") : T("The plane is in the middle."));
  drawTape($("lookCv"), c, on, d);
  $("arBtn").hidden = !arPossible();
  skyRowRender();
}
// 1.80 (Dave's to-do 14, his pick A): a plane on top without a direction keeps the card: the big line names it and
// the reason, dimmed, a sentence under it says what's missing, and the tape greys out.
function lookWhyDraw(why){
  const ac = feat.o.ac, info = feat.info || {}, f = info.flightNo || String(ac.flight || "").trim() || ac.r || String(ac.hex || "").toUpperCase();
  const km = /^(\d+) km away$/.exec(why);
  const [big, sub] = why === "no position" ? [T("{f} · NO POSITION YET", {f}), T("Its position hasn't come in yet; the arrow comes with the first one.")]
    : why === "no height" ? [T("{f} · NO HEIGHT YET", {f}), T("It hasn't sent its height, so how high to look can't be worked out.")]
    : km ? [T("{f} · {n} KM AWAY", {f, n: km[1]}), T("Too far to look for yet: the arrow comes once it's within 80 km.")]
    : why === "position unclear" ? [T("{f} · POSITION UNCLEAR", {f}), T("Its position doesn't add up; the next one should.")]
    : [T("{f} · CAN'T WORK IT OUT", {f}), T("Something went wrong working out where it is; the Log has the details.")];
  $("lookDir").textContent = big; $("lookSub").textContent = sub;
  drawTape($("lookCv"), lookOn && lookHeading != null ? lookHeading : 0, false, null);
  $("arBtn").hidden = !arPossible();
  skyRowRender();
}
// The heading tape (1.73.1): the directions around c, the gold line where you face (bright with the compass), and the
// plane d degrees off (an arrow at the end when it is off the tape; none when d is null: 1.77, the no-plane card).
function drawTape(cv, c, on, d){
  const px = Math.min(3, devicePixelRatio || 1), W = cv.clientWidth || 300, H = 44;
  if (cv.width !== Math.round(W * px)) { cv.width = Math.round(W * px); cv.height = H * px; }
  const g = cv.getContext("2d"), ppd = W / 120, X = deg => W / 2 + deg * ppd;
  g.setTransform(px, 0, 0, px, 0, 0); g.clearRect(0, 0, W, H);
  g.fillStyle = "#0c0d0e"; rr(g, 0, 0, W, H, 8); g.fill();
  g.textAlign = "center"; g.textBaseline = "alphabetic";
  const NAMES = {0: "N", 45: "NE", 90: "E", 135: "SE", 180: "S", 225: "SW", 270: "W", 315: "NW"};
  for (let k = Math.ceil((c - 66) / 5) * 5; k <= c + 66; k += 5) {
    const deg = (k + 360) % 360, x = X(k - c), big = deg % 45 === 0;
    g.fillStyle = big ? "rgba(255,255,255,.55)" : "rgba(255,255,255,.22)";
    g.fillRect(x - .75, H - (big ? 12 : deg % 15 === 0 ? 8 : 5), 1.5, big ? 12 : deg % 15 === 0 ? 8 : 5);
    if (big) { g.fillStyle = deg === 0 ? "#e0372c" : "#c9c3b4"; g.font = `700 12px ${FONT}`; g.fillText(NAMES[deg], x, H - 16); }
  }
  g.fillStyle = on ? "#f0b429" : "rgba(240,180,41,.35)"; g.fillRect(W / 2 - 1, 0, 2, H);      // where you face
  if (d == null) return;
  if (Math.abs(d) <= 58) drawPlane(g, X(d), 13, 18, "#f0b429");
  else {                                                         // off the tape: an arrow at its end, pointing the way
    const x = d > 0 ? W - 10 : 10, s = d > 0 ? 1 : -1;
    g.fillStyle = "#f0b429"; g.beginPath(); g.moveTo(x + 6 * s, 13); g.lineTo(x - 5 * s, 6); g.lineTo(x - 5 * s, 20); g.closePath(); g.fill();
  }
}
// 1.95.0.2: not while Sky view covers it (it drew on every compass reading, on the thread Sky view needs); after it, at once
const lookSoon = () => { if (!lookRaf && !arOn) lookRaf = requestAnimationFrame(drawLook); };
function lookHeadingFrom(e){
  let h = null;
  if (typeof e.webkitCompassHeading === "number") h = e.webkitCompassHeading;           // iPhone: degrees from north
  else if (e.absolute && typeof e.alpha === "number") h = (360 - e.alpha) % 360;         // Android: the alpha angle, absolute
  if (h == null) return;
  const so = (screen.orientation && screen.orientation.angle) || 0;
  h = (h + so + magDecl(S.lat, S.lon) + 360) % 360;                                       // 1.76: true north
  if (lookHeading == null) lookHeading = h;
  else { const d = ((h - lookHeading + 540) % 360) - 180; lookHeading = (lookHeading + d * .25 + 360) % 360; }   // smoothed: compasses wobble
  lookSoon();
}
async function lookStart(quiet){
  if (!quiet) ctlSound.nav();
  try {
    if (typeof DeviceOrientationEvent.requestPermission === "function" && await DeviceOrientationEvent.requestPermission() !== "granted") throw 0;
    addEventListener("ontouchstart" in window && "ondeviceorientationabsolute" in window ? "deviceorientationabsolute" : "deviceorientation", lookHeadingFrom);
    lookOn = true;
    setTimeout(() => { if (lookHeading == null && !quiet) $("lookSub").textContent = T("The compass isn't available on this device."); }, 2500);
  } catch { if (!quiet) $("lookSub").textContent = T("The compass isn't available on this device."); }
  lookSoon();
}
setInterval(() => { if (tab === "now" && document.visibilityState === "visible") lookSoon(); }, 1000);

/* ---------- Sky view (1.30): the camera, with a label on each plane ----------
   Each plane's direction from where the phone is (its own location, or the place in Settings) and its height, turned
   into the camera's picture with the phone's orientation: the W3C rotation (alpha, beta, gamma; the compass heading
   on iPhones), the back camera looking along the phone's -z. Positions are moved on to now with each plane's speed and
   track. Compasses are often a few degrees off: dragging the picture shifts the labels into place (kept per device).
   1.75.2: the turn is smoothed as a quaternion; the picture's scale comes from the video's own size, and held sideways
   the labels turn the right way; planes are moved on from the time the source made the data (not when it arrived),
   along their turn and climb; heights are made true with the home airport's QNH and temperature.
   1.76: true north (the compass points to magnetic north: the World Magnetic Model's declination is added), the sun
   and the moon as dashed rings to line the compass up on, and AUTO, which finds nearby planes in the picture.
   1.86 (Dave's real sky on an island: the sun's ring 24° off, and sliding sideways as the phone tilted): the gyroscope
   turns the labels and the compass only says where north is, while the phone is held still; once lined up (AUTO or a
   drag) north is held and the compass left out; AUTO finds the sun anywhere in the picture. */
const arPossible = () => window.isSecureContext && !!(navigator.mediaDevices && navigator.mediaDevices.getUserMedia) && typeof DeviceOrientationEvent !== "undefined";
let arOn = false, arSince = 0, arStream = null, arList = [], arListAt = 0, arQ = null, arQt = 0, arGap = null, arGapT = 0, arWatch = null, arHere = null, arRaf = 0, arDrag = null, arHits = [], arSel = "", arWant = "";
let arOff = {h: 0, p: 0}, arDec = 0, arHintText = "", arAlt = null;
const arOffSave = () => { try { localStorage.setItem("od.ar.off", JSON.stringify({...arOff, v: 2})); } catch {} };
// 1.66: point to pick. A ring in the middle of the picture; the plane in it lights up, and kept there for 1.5 s it opens
// (the ring fills as it waits). Then it waits for the ring to be empty again.
const AR_AIM_R = 56, AR_AIM_MS = 1500;
let arAim = {hex: "", since: 0, done: ""};
// 1.66: the compass is unsure when the heading jumps about while the phone is held still (or iOS says it is poor):
// a note asks for a figure of eight, or a drag to line the labels up.
let arRaw = [], arCalAt = 0;
// 1.86: Android sends two readings: the compass's (gyroscope, gravity and compass fused; a compass that is off swings it
// about while the phone moves and settles after) and the gyroscope's (gyroscope and gravity: it turns exactly as the
// phone does, but its zero is anywhere). The labels follow the gyroscope's; the gap between the two (arGap) is north,
// nudged towards the compass's slowly (1.90). iPhones work the same way with their gyro alpha and compass heading. Lined
// up (AUTO or a drag, arHeldAt), north stays where it is until ⟲.
// 1.90 (Dave's indoor try: the labels wandered while the phone was held still, following the compass's swings): a
// complementary filter. The gyroscope alone moves the labels; north glides to the compass's within AR_GAP_TAU, three
// times slower while the phone turns and four times slower while the compass is unsure, and never faster than
// AR_GAP_MAX a second (a quarter of it unsure). For the first AR_GAP_SETTLE ms it settles quickly from the first reading.
// A steady difference is no swing: while the phone is still and the compass's last AR_GAP_STEADY ms agree among
// themselves (spread under 2.5°) but differ from north in use by over 4° (a compass that came right after the start, or
// north carried over wrongly), north glides there within a few seconds (τ 1.5 s).
const AR_GAP_TAU = 6, AR_GAP_MAX = 1, AR_GAP_SETTLE = 1500, AR_GAP_STEADY = 1500, AR_STILL_MS = 1500;   // s; °/s; ms; ms; ms
let arAbsR = null, arAbsT = 0, arRelQ = null, arRelT = 0, arLastQ = null, arRate = 0, arMovedAt = 0, arGapLog = [], arHeldAt = 0, arGap0 = 0, arGapRef = null, arGapFast = false;
let arEvN = {abs: 0, rel: 0, ios: 0, motion: 0}, arHeldWhy = "", arSunLast = null, arNote = {text: "", until: 0};   // 1.90: for the report
const AR_FOV = 64;                                   // the back camera's view along the picture's long side (degrees, typical)
// 1.75.2: the focal length in screen pixels. The video fills the screen (object-fit: cover), so its long side, however
// much of it is cut off, spans AR_FOV; this holds upright, sideways and on a tablet alike. Camera sensors are 4:3:
// a narrower video (square) was cut along its long side too, and sees less.
function arFocal(W, H){
  const v = $("arVid"), vw = v.videoWidth, vh = v.videoHeight;
  if (!vw || !vh) return Math.max(W, H) / 2 / Math.tan(AR_FOV / 2 * Math.PI / 180) * arZk * arZc;
  const lo = Math.max(vw, vh), t = Math.tan(AR_FOV / 2 * Math.PI / 180) * Math.min(1, lo / Math.min(vw, vh) * .75);
  return lo * Math.max(W / vw, H / vh) / 2 / t * arZk * arZc;      // 1.99: times the zoom
}
/* 1.99 (to-do #161, Dave's request of 28 Oct): ×2 and ×5, for everyone. The camera's own zoom where the browser offers
   it (getCapabilities().zoom: Chrome on most Android phones), up to its top; the rest (all of it on an iPhone, in
   Firefox, on a camera without zoom) the picture enlarged round its middle, object-fit: cover kept. arZk: the camera's
   part (once it has taken it), arZc: the enlargement now, easing to arZcTo (at once with reduced motion or a camera
   zoom, which jumps). The focal length takes both, so the labels, the sun and moon, the arrows and the drag follow;
   AUTO and the snapshot read the picture with arZc. A second tap and leaving Sky view go back to ×1. */
let arZoom = 1, arZk = 1, arZc = 1, arZcTo = 1, arZBase = null, arZSeq = 0;
async function arZoomSet(z){
  ctlSound.click();
  arZoom = arZoom === z ? 1 : z; const seq = ++arZSeq;
  arZoomBtns();
  arAutoFinds = []; arAutoLock = null; arAutoPause = Math.max(arAutoPause, Date.now() + 800);   // AUTO looks again at the new size
  const tr = arStream && arStream.getVideoTracks()[0], cap = tr && tr.getCapabilities ? tr.getCapabilities() : {}, zc = cap.zoom;
  let k = 1;
  const cam = !!(zc && zc.max > zc.min);
  if (cam) {
    if (arZBase == null) arZBase = tr.getSettings().zoom || Math.max(1, zc.min);
    try { await tr.applyConstraints({advanced: [{zoom: Math.min(zc.max, Math.max(zc.min, arZBase * arZoom))}]}); } catch {}
    if (seq !== arZSeq || !arOn) return;
    k = (tr.getSettings().zoom || arZBase) / arZBase;
  }
  dlog("debug", `Sky view: ×${arZoom}${cam ? `, the camera's zoom ×${Math.round(k * 10) / 10} (up to ×${Math.round(zc.max / arZBase * 10) / 10})` : ", the picture enlarged"}`);
  arZk = k; arZcTo = arZoom / k;
  if (cam || REDUCED) { arZc = arZcTo; arZoomCss(); }
}
function arZoomBtns(){
  for (const [id, z] of [["arZ2", 2], ["arZ5", 5]]) { const b = $(id); b.classList.toggle("on", arZoom === z); b.setAttribute("aria-pressed", String(arZoom === z)); }
}
const arZoomCss = () => { $("arVid").style.transform = arZc === 1 ? "" : `scale(${arZc})`; };
// Each frame: the enlargement eases to where it is going (about a fifth of a second)
function arZoomStep(){
  if (arZc === arZcTo) return;
  arZc = Math.abs(arZcTo / arZc - 1) < .01 ? arZcTo : arZc * Math.pow(arZcTo / arZc, .25);
  arZoomCss();
}
// 1.75.2: the time the source made the positions (getAircraft's list.now), so the relay's few seconds of keeping them
// count too; a phone clock far off falls back to when they arrived. Turn rates are measured between two updates.
const arTurns = new Map();                           // hex -> {at, track, rate}
function arFeed(list){
  const now = Date.now(), t = list && list.now;
  arList = list || []; arListAt = t && now - t > -2000 && now - t < 120000 ? Math.min(now, t) : now;
  for (const ac of arList) {
    if (ac.track == null) continue;
    const at = arListAt - (ac.seen_pos || 0) * 1000, was = arTurns.get(ac.hex);
    if (was && at - was.at < 1000) continue;         // the same position again
    const gap = was ? (at - was.at) / 1000 : 0, r = gap ? (((ac.track - was.track) % 360) + 540) % 360 - 180 : 0;
    arTurns.set(ac.hex, {at, track: ac.track, rate: gap > 1 && gap < 20 && Math.abs(r / gap) <= 6 ? r / gap : 0});
  }
  if (arTurns.size > 400) for (const [k, v] of arTurns) if (now - v.at > 120000) arTurns.delete(k);
}
const arEvent = () => "ondeviceorientationabsolute" in window ? "deviceorientationabsolute" : "deviceorientation";
// 1.75.2: the W3C angles (Z-X'-Y'') as a quaternion [w, x, y, z], and back into the rotation matrix (the phone's axes in
// east-north-up). Smoothing the angles one by one went wrong where they wrap: looking straight up (beta at ±180,
// planes overhead) or holding the phone sideways (gamma at ±90).
function arQuat(a, b, g){
  const r = Math.PI / 360, cX = Math.cos(b * r), cY = Math.cos(g * r), cZ = Math.cos(a * r), sX = Math.sin(b * r), sY = Math.sin(g * r), sZ = Math.sin(a * r);
  return [cX * cY * cZ - sX * sY * sZ, sX * cY * cZ - cX * sY * sZ, cX * sY * cZ + sX * cY * sZ, cX * cY * sZ + sX * sY * cZ];
}
function arQMatrix([w, x, y, z]){
  return [[1 - 2 * (y * y + z * z), 2 * (x * y - w * z), 2 * (x * z + w * y)],
          [2 * (x * y + w * z), 1 - 2 * (x * x + z * z), 2 * (y * z - w * x)],
          [2 * (x * z - w * y), 2 * (y * z + w * x), 1 - 2 * (x * x + y * y)]];
}
const wrap180 = d => ((d % 360) + 540) % 360 - 180;
// 1.86: the turn about the vertical that takes orientation B to A (degrees, counted as alpha is)
const arYaw = (A, B) => Math.atan2(A[1][0] * B[0][0] + A[1][1] * B[0][1] + A[1][2] * B[0][2], A[0][0] * B[0][0] + A[0][1] * B[0][1] + A[0][2] * B[0][2]) * 180 / Math.PI;
function arOrient(e){
  if (e.beta == null || e.gamma == null) return;
  const t = performance.now();
  arEvN[typeof e.webkitCompassHeading === "number" ? "ios" : e.type === "deviceorientationabsolute" || e.absolute ? "abs" : "rel"]++;   // 1.90: for the report
  let a = e.alpha, raw = a;
  if (typeof e.webkitCompassHeading === "number" && e.webkitCompassHeading >= 0) {
    // iPhone: alpha comes from the gyro (steady, but with its own zero) and the compass says where north is
    raw = 360 - e.webkitCompassHeading;
    if (a == null) a = raw;
    else {
      arGyroStep(arQuat(a, e.beta, e.gamma), t);
      arGapStep(raw - a, t, typeof e.webkitCompassAccuracy === "number" && (e.webkitCompassAccuracy < 0 || e.webkitCompassAccuracy > 25));
      a += arGap;
    }
  }
  else if (e.type === "deviceorientationabsolute" || e.absolute) {
    if (a == null) return;
    // 1.86: Android's compass reading. While the gyroscope's comes too, this one only says where north is.
    arAbsR = arQMatrix(arQuat(a, e.beta, e.gamma)); arAbsT = t;
    if (t - arRelT < 400) return arCalCheck(raw, e.beta, e.gamma, e.webkitCompassAccuracy, true);
  }
  else {
    // 1.86: Android's gyroscope reading turns the labels, north added as the gap to the compass's
    if (a == null) return;
    const q = arQuat(a, e.beta, e.gamma), fresh = arAbsR && t - arAbsT < 400;
    if (arGap == null && !fresh) return;
    arGyroStep(q, t);
    if (fresh) arGapStep(arYaw(arAbsR, arQMatrix(q)), t);
    return arTurn(arQuat(a + arGap, e.beta, e.gamma), t);
  }
  if (a == null) return;
  arCalCheck(raw, e.beta, e.gamma, e.webkitCompassAccuracy, arGap != null);
  arTurn(arQuat(a, e.beta, e.gamma), t);
}
// 1.86: north (the gap between the compass and the gyroscope): the first reading, then followed (1.90: slowly, see
// AR_GAP_TAU), not at all once lined up. The compass swinging 12° or more against the gyroscope within 4 s (moving
// or not) wants calibrating: the note asks for a figure of eight.
function arGapStep(meas, t, poor){
  if (arGap == null) { arGap = arGapRef = meas; arGapT = arGap0 = t; arGapLog = []; return; }
  if (arGapRef == null) arGapRef = meas;             // (after the gyroscope's zero jumped)
  const off = wrap180(meas - arGap), dt = Math.min(.2, Math.max(0, (t - arGapT) / 1000));
  arGapT = t;
  // 1.90: the log keeps the compass against the gyroscope (from the first reading), not against north in use
  if (arRate < 60) arGapLog.push([t, wrap180(meas - arGapRef)]);   // (a fast flick puts the two readings a little apart in time)
  while (arGapLog.length && t - arGapLog[0][0] > 4000) arGapLog.shift();
  if (!arHeldAt && arGapLog.length > 30) {
    let lo = Infinity, hi = -Infinity;
    for (const g of arGapLog) { lo = Math.min(lo, g[1]); hi = Math.max(hi, g[1]); }
    if (hi - lo > 12) arCalAt = Date.now();
  }
  if (arHeldAt) return;
  if (t - arGap0 < AR_GAP_SETTLE) { arGap += off * (1 - Math.exp(-dt / .4)); return; }
  const still = t - arMovedAt >= AR_STILL_MS, recent = arGapLog.filter(g => t - g[0] < AR_GAP_STEADY).map(g => g[1]);
  let steady = null;
  if (still && recent.length >= 30) {
    const m = recent.reduce((x, y) => x + y, 0) / recent.length, sd = Math.sqrt(recent.reduce((x, y) => x + (y - m) ** 2, 0) / recent.length);
    if (sd < 2.5) steady = wrap180(arGapRef + m - arGap);
  }
  // once going there, all the way (within 1°), or until the phone moves or the compass wavers
  arGapFast = steady != null && Math.abs(steady) > (arGapFast ? 1 : 4);
  if (arGapFast) { arGap += steady * (1 - Math.exp(-dt / 1.5)); return; }
  const unsure = poor || Date.now() - arCalAt < 4000, tau = AR_GAP_TAU * (unsure ? 4 : 1) * (still ? 1 : 3);
  const cap = AR_GAP_MAX * (unsure ? .25 : 1) * dt;
  arGap += Math.max(-cap, Math.min(cap, off * (1 - Math.exp(-dt / tau))));
}
// The gyroscope's reading: how fast the phone turns (smoothed; over 6°/s it moves), and a jump no hand makes (its zero
// was reset): then north is carried over, so the labels stay put.
function arGyroStep(q, t){
  if (arRelQ) {
    const d = Math.abs(arRelQ[0] * q[0] + arRelQ[1] * q[1] + arRelQ[2] * q[2] + arRelQ[3] * q[3]), ang = 360 / Math.PI * Math.acos(Math.min(1, d));
    const dt = Math.max(.016, (t - arRelT) / 1000);
    if (ang > 20 && ang / dt > 1000) {
      if (arLastQ && arGap != null) { arGap = arYaw(arQMatrix(arLastQ), arQMatrix(q)); arGapRef = null; arGapLog = []; }
      dlog("debug", `Sky view: the gyroscope's zero jumped ${Math.round(ang)}°, north carried over`);
    } else {
      arRate += (ang / dt - arRate) * (1 - Math.exp(-Math.min(dt, .2) / .25));
      if (arRate > 6) arMovedAt = t;
    }
  }
  arRelQ = q; arRelT = t;
}
// 1.95.0.2 (to-do #125, Dave's pick B): the labels follow where the phone points at each frame, not at each reading.
// Chrome hands the readings over on the page's own thread, polled 60 times a second: while the page is busy they come
// late and bunched (Dave's recording: the labels held for 60-420 ms, then jumped up to 100 px). A reading (arTurn) is
// kept with the phone's turning speed (arW, radians a second about east, north and up); each frame (arFrame) turns the
// newest reading on by that speed for as long as it is old, up to AR_AHEAD (older still, back to the reading), and the
// labels glide there like a 1€ filter: held still heavily (sensors wobble), turning hardly at all (they keep up).
// Chrome sends no reading while no angle changes by 0.1°, so an old reading may mean a stop: the gyroscope's rate
// (devicemotion, arMotion; sent 60 times a second, still or not) tells which. Under 2°/s nothing is run on.
const AR_AHEAD = .15;                                // s
let arRd = null, arRdRef = null, arW = [0, 0, 0], arFrT = 0, arFrN = 0, arTim = {reads: [], frames: [], fresh: []}, arMo = null;
function arMotion(e){
  const r = e.rotationRate;
  if (!r || typeof r.alpha !== "number") return;
  arEvN.motion++;
  arMo = {deg: Math.hypot(r.alpha, r.beta || 0, r.gamma || 0), t: performance.now()};   // only how fast, not which way
}
const arQMul = (a, b) => [a[0] * b[0] - a[1] * b[1] - a[2] * b[2] - a[3] * b[3], a[0] * b[1] + a[1] * b[0] + a[2] * b[3] - a[3] * b[2],
  a[0] * b[2] - a[1] * b[3] + a[2] * b[0] + a[3] * b[1], a[0] * b[3] + a[1] * b[2] - a[2] * b[1] + a[3] * b[0]];
const arTimPush = (a, v) => { a.push(Math.round(v * 10) / 10); if (a.length > 120) a.shift(); };   // for the report
function arTurn(q, t){
  arLastQ = q;
  if (arRd) arTimPush(arTim.reads, t - arRd.t);
  arFrN++; arRd = {q, t};
  if (!arRdRef) { arRdRef = arRd; return; }
  const dt = (t - arRdRef.t) / 1000;
  if (dt < .008) return;                             // (two handed over at once: the speed from a longer span)
  const p = arRdRef.q, s = p[0] * q[0] + p[1] * q[1] + p[2] * q[2] + p[3] * q[3] < 0 ? -1 : 1;
  const d = arQMul(q.map(v => v * s), [p[0], -p[1], -p[2], -p[3]]), n = Math.hypot(d[1], d[2], d[3]), ang = 2 * Math.atan2(n, d[0]);
  arRdRef = arRd;
  if (ang > .5 || ang / dt > 8) { arW = [0, 0, 0]; return; }   // a jump no hand makes (the gyroscope's zero, the compass taking over)
  const k = 1 - Math.exp(-Math.min(dt, .2) / .05);
  arW = arW.map((v, i) => v + ((n > 1e-9 ? d[i + 1] / n * ang / dt : 0) - v) * k);
}
function arFrame(now){
  if (arFrT) { arTimPush(arTim.frames, now - arFrT); arTim.fresh.push(arFrN); if (arTim.fresh.length > 120) arTim.fresh.shift(); }
  arFrT = now; arFrN = 0;
  if (!arRd) return;
  // (without the gyroscope's rate a stop can't be told from a late reading: only a little ahead)
  const ahead = arMo ? AR_AHEAD : .05, age = Math.max(0, (now - arRd.t) / 1000), lead = age <= ahead ? age : Math.max(0, 2 * ahead - age);
  const wl = Math.hypot(...arW), deg = arMo && now - arMo.t < 100 ? arMo.deg : wl * 180 / Math.PI, run = lead * Math.min(1, Math.max(0, (deg - 2) / 4));
  let p = arRd.q;
  if (run > 0) { const h = wl * run / 2, s = Math.sin(h) / wl; p = arQMul([Math.cos(h), arW[0] * s, arW[1] * s, arW[2] * s], p); }
  if (!arQ) { arQ = p; arQt = now; return; }
  let d = arQ[0] * p[0] + arQ[1] * p[1] + arQ[2] * p[2] + arQ[3] * p[3];
  if (d < 0) { p = p.map(v => -v); d = -d; }
  const ang = 360 / Math.PI * Math.acos(Math.min(1, d)), tau = .03 + .17 * Math.sqrt(arZk * arZc) * Math.exp(-Math.max(ang / .7, deg / 6));
  const k = 1 - Math.exp(-Math.min(.2, Math.max(.002, (now - arQt) / 1000)) / tau), m = arQ.map((v, i) => v + (p[i] - v) * k), L = Math.hypot(...m);
  arQ = m.map(v => v / L); arQt = now;
}
// 1.86: lined up (AUTO or a drag): north is held, the gyroscope alone turns the labels until ⟲ or Sky view closes.
function arHold(why){
  if (!arHeldAt && arGap != null) dlog("debug", `Sky view: lined up (${why}); north held, the compass left out`);
  arHeldAt = Date.now(); arHeldWhy = why;
}
async function arOpen(button){
  button ? ctlSound.click() : ctlSound.nav();      // 1.97.4: the Sky view buttons click like buttons
  const fail = () => { lookErr = T("Sky view needs the camera and the motion sensors, on the https address."); lookErrAt = Date.now(); lookSoon();
    dlog("warn", `Sky view: no camera or motion sensors (refused, or ${window.isSecureContext ? "not available" : "not on https"})`); };
  try {
    if (typeof DeviceOrientationEvent.requestPermission === "function" && await DeviceOrientationEvent.requestPermission() !== "granted") return fail();
    arStream = await navigator.mediaDevices.getUserMedia({video: {facingMode: {ideal: "environment"}, width: {ideal: 1280}, height: {ideal: 1280}}, audio: false});
  } catch { return fail(); }
  try { arOff = {h: 0, p: 0, ...JSON.parse(localStorage.getItem("od.ar.off") || "{}")}; } catch {}
  // 1.76: labels lined up before true north was known carry the declination in their drag: taken out once
  if (!arOff.v) { if (arOff.h) { arOff.h -= magDecl(S.lat, S.lon); arOffSave(); } arOff.v = 2; }
  try { arAuto = localStorage.getItem("od.ar.auto") !== "0"; } catch {}
  arAutoFinds = []; arAutoLock = null; arAutoSig = ""; arAutoPause = 0;
  const v = $("arVid"); v.srcObject = arStream; v.play().catch(() => {});
  v.addEventListener("loadedmetadata", () => {                 // 1.75.2: what the camera gives, for the log
    const tr = arStream && arStream.getVideoTracks()[0], st = tr && tr.getSettings ? tr.getSettings() : {};
    dlog("debug", `Sky view camera: ${v.videoWidth}×${v.videoHeight}${st.resizeMode ? ` (${st.resizeMode})` : ""}, picture ${Math.round(arFocal($("arCv").clientWidth, $("arCv").clientHeight))} px to the radian`);
  }, {once: true});
  $("arView").hidden = false; document.body.classList.add("arOpen"); if ($("gAws")) gAwsBox(); arOn = true; arQ = null; arGap = null; arAlt = null;
  arAbsR = null; arRelQ = null; arRelT = 0; arRd = arRdRef = null; arW = [0, 0, 0]; arFrT = arFrN = 0; arTim = {reads: [], frames: [], fresh: []}; arLastQ = null; arRate = 0; arMovedAt = 0; arGapLog = []; arHeldAt = 0; arGapRef = null; arGapFast = false;
  arEvN = {abs: 0, rel: 0, ios: 0, motion: 0}; arMo = null; arHeldWhy = ""; arSunLast = null; arNote = {text: "", until: 0};
  $("arFlag").hidden = !arReportOk(); $("arFlag").classList.remove("sent"); $("arFlag").setAttribute("aria-label", T("Send a report to tune Sky view"));
  arShotAt = 0; arLocked = ""; $("arShut").hidden = true; $("arShut").setAttribute("aria-label", T("Take a picture"));
  $("arZ2").setAttribute("aria-label", T("Zoom in two times")); $("arZ5").setAttribute("aria-label", T("Zoom in five times"));
  arSince = Date.now(); dlog("info", `Sky view opened · ${arList.length} planes around · AUTO ${arAuto ? "on" : "off"}`);
  $("arHint").textContent = T("Hold a plane in the ring for a moment to open it. If the labels sit beside the planes, drag them into place.") +
    (gameOk() && S.live ? " " + T("★ can be scanned for points · CLOSER TO SCAN: more than {s} km away · NO PTS: more than {k} km away.", {s: gScanKm(), k: gKm()}) : "");
  arHintText = $("arHint").textContent;
  arAim = {hex: "", since: 0, done: ""}; arRaw = []; arCalAt = 0; $("arCal").hidden = true;
  addEventListener(arEvent(), arOrient);
  if (arEvent() === "deviceorientationabsolute") addEventListener("deviceorientation", arOrient);   // 1.86: and the gyroscope's
  addEventListener("devicemotion", arMotion);                     // 1.95.0.2: the gyroscope's rate, to tell a stop from a late reading
  if (navigator.geolocation) arWatch = navigator.geolocation.watchPosition(p => {
    if (geoPos(p).age > LIVE_OLD_MS) return;                           // 1.93.1: one the browser kept from earlier
    const c = p.coords; arHere = {lat: c.latitude, lon: c.longitude};
    // 1.76.1: the phone's own height above the sea (GPS, smoothed): on a hillside or a cliff top the airport's is far off
    if (typeof c.altitude === "number" && !(c.altitudeAccuracy > 60)) arAlt = arAlt == null ? c.altitude : arAlt + (c.altitude - arAlt) * .3;
  }, () => {}, {enableHighAccuracy: true, maximumAge: 15000});
  setTimeout(() => { if (arOn && !arQ) { $("arHint").textContent = T("No compass reading yet: move the phone in a figure of eight."); dlog("warn", "Sky view: no compass reading after 2.5 s"); } }, 2500);
  try { if (!localStorage.getItem("od.ar.tour")) setTimeout(() => { if (arOn) arTour(0); }, 700); } catch {}   // 1.72.7: the first time
  arLoop();
}
// 1.90: with the gyroscope's reading (gyro), arGapStep's check is the exact one; the heading swinging while the tilt holds
// is then left out, as a smooth pan looks just like that (it showed "Compass unsure" while turning).
function arCalCheck(a, b, g, acc, gyro){
  const now = Date.now();
  arRaw.push([now, a, b, g]);
  while (arRaw.length && now - arRaw[0][0] > 1500) arRaw.shift();
  if (arRaw.length < 8) return;
  const spread = i => { const v = arRaw.map(r => r[i]); return Math.max(...v) - Math.min(...v); };
  const as = arRaw.map(r => ((r[1] - arRaw[0][1] + 540) % 360) - 180), aSpread = Math.max(...as) - Math.min(...as);
  if ((typeof acc === "number" && acc > 25) || (!gyro && spread(2) < 3 && spread(3) < 3 && aSpread > 12)) arCalAt = now;
  const el = $("arCal"), show = now - arCalAt < 4000 && !arHeldAt;   // 1.86: not once lined up
  if (el.hidden === show) {
    el.hidden = !show;
    if (show) el.innerHTML = `<b>${escH(T("Compass unsure"))}</b> · ${escH(T("move the phone in a figure of eight, or drag the picture to line the labels up"))}`;
  }
}
function arClose(){
  if (!arOn) return;
  arOn = false; ctlSound.nav();
  dlog("debug", `Sky view closed after ${Math.round((Date.now() - arSince) / 1000)} s`);
  $("arTour").hidden = true; $("arView").classList.remove("tourBtns"); $("arMoved").hidden = true;
  if (arStream) arStream.getTracks().forEach(t => t.stop());
  arStream = null; $("arVid").srcObject = null;
  arZoom = arZk = arZc = arZcTo = 1; arZBase = null; arZSeq++; arZoomCss(); arZoomBtns();   // 1.99: back to ×1
  removeEventListener(arEvent(), arOrient); removeEventListener("deviceorientation", arOrient); removeEventListener("devicemotion", arMotion);
  if (arWatch != null && navigator.geolocation) navigator.geolocation.clearWatch(arWatch);
  arWatch = null; cancelAnimationFrame(arRaf);
  arSel = arWant = ""; arCardRender();
  $("arView").hidden = true; document.body.classList.remove("arOpen"); if ($("gAws")) gAwsBox();
  lookSoon();
}
/* 1.97 (to-do #133): Sky view opened at a plane (a tap on its pass): it is picked out (its card, its ring) and the
   arrow at the edge points to it rather than to the plane on top, until it is scanned or Sky view closes. */
async function arOpenAt(hex, flight){
  if (!arOn) { await arOpen(); if (!arOn) return; }
  const ac = arList.find(a => a.hex === hex);
  arWant = arSel = hex; arFull = false; arAwayAt = 0; arCardSig = ""; arCardRender();
  const name = flight || (ac && (String(ac.flight || "").trim() || ac.r)) || hex.toUpperCase();
  arNote = {text: T("Follow the arrow to {f} and hold it in the ring to scan it.", {f: name}), until: Date.now() + 8000};
  dlog("info", `Sky view opened at ${name} (its points pass)${ac ? "" : ", not in the list yet"}`);
}
// 1.76: true north. Phone compasses point to magnetic north; the World Magnetic Model gives the declination, how
// far east of true north it lies (about 5° in Vienna). WMM2025 by NOAA NCEI (public domain; tools/app/WMM.COF, its
// g, h, ġ, ḣ for n 1..12, m 0..n), good to 2030 and still close for some years after.
const WMM_EPOCH = 2025, WMM_C = "-29351.8 0 12 0 -1410.8 4545.4 9.7 -21.5 -2556.6 0 -11.6 0 2951.1 -3133.6 -5.2 -27.7 1649.3 -815.1 -8 -12.1 1361 0 -1.3 0 -2404.1 -56.6 -4.2 4 1243.8 237.5 0.4 -0.3 453.6 -549.5 -15.6 -4.1 895 0 -1.6 0 799.5 278.6 -2.4 -1.1 55.7 -133.9 -6 4.1 -281.1 212 5.6 1.6 12.1 -375.6 -7 -4.4 -233.2 0 0.6 0 368.9 45.4 1.4 -0.5 187.2 220.2 0 2.2 -138.7 -122.9 0.6 0.4 -142 43 2.2 1.7 20.9 106.1 0.9 1.9 64.4 0 -0.2 0 63.8 -18.4 -0.4 0.3 76.9 16.8 0.9 -1.6 -115.7 48.8 1.2 -0.4 -40.9 -59.8 -0.9 0.9 14.9 10.9 0.3 0.7 -60.7 72.7 0.9 0.9 79.5 0 -0 0 -77 -48.9 -0.1 0.6 -8.8 -14.4 -0.1 0.5 59.3 -1 0.5 -0.8 15.8 23.4 -0.1 0 2.5 -7.4 -0.8 -1 -11.1 -25.1 -0.8 0.6 14.2 -2.3 0.8 -0.2 23.2 0 -0.1 0 10.8 7.1 0.2 -0.2 -17.5 -12.6 0 0.5 2 11.4 0.5 -0.4 -21.7 -9.7 -0.1 0.4 16.9 12.7 0.3 -0.5 15 0.7 0.2 -0.6 -16.8 -5.2 -0 0.3 0.9 3.9 0.2 0.2 4.6 0 -0 0 7.8 -24.8 -0.1 -0.3 3 12.2 0.1 0.3 -0.2 8.3 0.3 -0.3 -2.5 -3.3 -0.3 0.3 -13.1 -5.2 0 0.2 2.4 7.2 0.3 -0.1 8.6 -0.6 -0.1 -0.2 -8.7 0.8 0.1 0.4 -12.9 10 -0.1 0.1 -1.3 0 0.1 0 -6.4 3.3 0 0 0.2 0 0.1 -0 2 2.4 0.1 -0.2 -1 5.3 -0 0.1 -0.6 -9.1 -0.3 -0.1 -0.9 0.4 0 0.1 1.5 -4.2 -0.1 0 0.9 -3.8 -0.1 -0.1 -2.7 0.9 -0 0.2 -3.9 -9.1 -0 -0 2.9 0 0 0 -1.5 0 -0 -0 -2.5 2.9 0 0.1 2.4 -0.6 0 -0 -0.6 0.2 0 0.1 -0.1 0.5 -0.1 -0 -0.6 -0.3 0 -0 -0.1 -1.2 -0 0.1 1.1 -1.7 -0.1 -0 -1 -2.9 -0.1 0 -0.2 -1.8 -0.1 0 2.6 -2.3 -0.1 0 -2 0 0 0 -0.2 -1.3 0 -0 0.3 0.7 -0 0 1.2 1 -0 -0.1 -1.3 -1.4 -0 0.1 0.6 -0 -0 -0 0.6 0.6 0.1 -0 0.5 -0.1 -0 -0 -0.1 0.8 0 0 -0.4 0.1 0 -0 -0.2 -1 -0.1 -0 -1.3 0.1 -0 0 -0.7 0.2 -0.1 -0.1".split(" ").map(Number);
let magCache = {key: "", d: 0};
function magField(lat, lon, hKm, year){
  const N = 12, r0 = 6371.2, A = 6378.137, F = 1 / 298.257223563, e2 = F * (2 - F), rad = Math.PI / 180;
  // geodetic to geocentric
  const sp = Math.sin(lat * rad), cp = Math.cos(lat * rad), Rc = A / Math.sqrt(1 - e2 * sp * sp);
  const px = (Rc + hKm) * cp, pz = (Rc * (1 - e2) + hKm) * sp, r = Math.hypot(px, pz), lc = Math.asin(pz / r);
  const x = Math.sin(lc), c = Math.cos(lc), dt = year - WMM_EPOCH, fact = [1];
  for (let i = 1; i <= 2 * N; i++) fact[i] = fact[i - 1] * i;
  // associated Legendre functions (no Condon-Shortley phase), P[n][m]
  const P = [[1]];
  for (let n = 1; n <= N; n++) {
    P[n] = [];
    for (let m = 0; m <= n; m++)
      P[n][m] = m === n ? (2 * m - 1) * c * P[n - 1][n - 1] : m === n - 1 ? (2 * m + 1) * x * P[n - 1][m]
        : ((2 * n - 1) * x * P[n - 1][m] - (n + m - 1) * P[n - 2][m]) / (n - m);
  }
  let X = 0, Y = 0, Z = 0, k = 0;
  for (let n = 1; n <= N; n++) {
    const ar = Math.pow(r0 / r, n + 2);
    for (let m = 0; m <= n; m++, k += 4) {
      const g = WMM_C[k] + dt * WMM_C[k + 2], h = WMM_C[k + 1] + dt * WMM_C[k + 3], S = Math.sqrt((m ? 2 : 1) * fact[n - m] / fact[n + m]);
      const cm = Math.cos(m * lon * rad), sm = Math.sin(m * lon * rad), Pn = S * P[n][m];
      const dP = S * ((n + m) * (m <= n - 1 ? P[n - 1][m] : 0) - n * x * P[n][m]) / c;
      X -= ar * (g * cm + h * sm) * dP;
      Y += ar * m * (g * sm - h * cm) * Pn / c;
      Z -= ar * (n + 1) * (g * cm + h * sm) * Pn;
    }
  }
  const psi = lc - lat * rad;                                 // geocentric to geodetic
  return {X: X * Math.cos(psi) - Z * Math.sin(psi), Y, Z: X * Math.sin(psi) + Z * Math.cos(psi)};
}
// The declination at a place now, in degrees east (kept while the place moves less than about 10 km).
function magDecl(lat, lon){
  const key = lat.toFixed(1) + "," + lon.toFixed(1);
  if (magCache.key !== key) {
    const d = new Date(), y0 = Date.UTC(d.getUTCFullYear(), 0, 1), y1 = Date.UTC(d.getUTCFullYear() + 1, 0, 1);
    const f = magField(Math.max(-89.9, Math.min(89.9, lat)), lon, 0, d.getUTCFullYear() + (d - y0) / (y1 - y0));
    magCache = {key, d: Math.atan2(f.Y, f.X) * 180 / Math.PI};
  }
  return magCache.d;
}
// 1.76: where the sun and the moon are in the sky (azimuth from north, elevation in degrees, refraction included):
// the Astronomical Almanac's low-precision formulas, some 0.01° for the sun and 0.3° for the moon, the moon as seen
// from here (it sits up to 1° lower than from the earth's centre). lit: how much of the moon is lit, 0 to 1.
function skyBodies(lat, lon, t){
  const r = Math.PI / 180, n = t / 86400000 - 10957.5, T = n / 36525, ep = (23.439 - 4e-7 * n) * r, phi = lat * r;
  const lst = ((280.46061837 + 360.98564736629 * n + lon) % 360) * r;
  const azel = (ra, dec) => {
    const H = lst - ra, el = Math.asin(Math.sin(phi) * Math.sin(dec) + Math.cos(phi) * Math.cos(dec) * Math.cos(H)) / r;
    const az = Math.atan2(-Math.cos(dec) * Math.sin(H), Math.sin(dec) * Math.cos(phi) - Math.cos(dec) * Math.sin(phi) * Math.cos(H)) / r;
    return {az: (az + 360) % 360, el: el > -1 ? el + 1.02 / Math.tan((el + 10.3 / (el + 5.11)) * r) / 60 : el};
  };
  const g = (357.528 + .9856003 * n) * r, L = (280.46 + .9856474 * n + 1.915 * Math.sin(g) + .02 * Math.sin(2 * g)) * r;
  const sun = azel(Math.atan2(Math.cos(ep) * Math.sin(L), Math.cos(L)), Math.asin(Math.sin(ep) * Math.sin(L)));
  const S = (a, b) => Math.sin((a + b * T) * r), C = (a, b) => Math.cos((a + b * T) * r);
  const lm = (218.32 + 481267.881 * T + 6.29 * S(135, 477198.87) - 1.27 * S(259.3, -413335.36) + .66 * S(235.7, 890534.22)
    + .21 * S(269.9, 954397.74) - .19 * S(357.5, 35999.05) - .11 * S(186.5, 966404.03)) * r;
  const bm = (5.13 * S(93.3, 483202.02) + .28 * S(228.2, 960400.89) - .28 * S(318.3, 6003.15) - .17 * S(217.6, -407332.21)) * r;
  const hp = (.9508 + .0518 * C(135, 477198.87) + .0095 * C(259.3, -413335.36) + .0078 * C(235.7, 890534.22) + .0028 * C(269.9, 954397.74)) * r;
  const l = Math.cos(bm) * Math.cos(lm), m = Math.cos(ep) * Math.cos(bm) * Math.sin(lm) - Math.sin(ep) * Math.sin(bm);
  const z = Math.sin(ep) * Math.cos(bm) * Math.sin(lm) + Math.cos(ep) * Math.sin(bm), d = 1 / Math.sin(hp);
  const X = d * l - Math.cos(phi) * Math.cos(lst), Y = d * m - Math.cos(phi) * Math.sin(lst), Z = d * z - Math.sin(phi);
  const moon = azel(Math.atan2(Y, X), Math.asin(Z / Math.hypot(X, Y, Z)));
  moon.lit = (1 - Math.cos(lm) * Math.cos(bm) * Math.cos(L) - Math.cos(bm) * Math.sin(lm) * Math.sin(L)) / 2;   // from its angle to the sun
  return {sun, moon};
}
// Where a point (east, north, up in metres from the phone) falls on the screen: [x, y] or, behind the phone, the
// direction to turn ({edge: [dx, dy]}).
function arProject(e, n, u, R, W, H){
  const hh = (arOff.h + arDec) * Math.PI / 180, ce = Math.cos(hh), se = Math.sin(hh);   // 1.76: and magnetic to true north
  const E = e * ce - n * se, N = e * se + n * ce, L = Math.hypot(E, N, u) || 1, p = [E / L, N / L, u / L];
  let vx = R[0][0] * p[0] + R[1][0] * p[1] + R[2][0] * p[2], vy = R[0][1] * p[0] + R[1][1] * p[1] + R[2][1] * p[2];
  const vz = R[0][2] * p[0] + R[1][2] * p[1] + R[2][2] * p[2];
  // held sideways the screen's axes are the phone's turned by the screen angle (90: the top to the left). 1.75.2: the
  // turn went the other way, so sideways every label sat mirrored through the middle.
  const so = ((screen.orientation && screen.orientation.angle) || window.orientation || 0) * Math.PI / 180;
  if (so) { const x = vx * Math.cos(so) - vy * Math.sin(so), y = vx * Math.sin(so) + vy * Math.cos(so); vx = x; vy = y; }
  const f = arFocal(W, H), shift = f * Math.tan(arOff.p * Math.PI / 180);
  if (vz > -.08) return {edge: [vx, -vy]};
  const x = W / 2 + f * vx / -vz, y = H / 2 - f * vy / -vz + shift;
  return x < -40 || x > W + 40 || y < -40 || y > H + 40 ? {edge: [x - W / 2, y - H / 2], x, y} : {x, y};
}
// 1.86: the other way round: where a point on the screen looks in the sky, {az, el} in degrees from true north.
function arUnproject(x, y, R, W, H){
  const f = arFocal(W, H), shift = f * Math.tan(arOff.p * Math.PI / 180), so = ((screen.orientation && screen.orientation.angle) || window.orientation || 0) * Math.PI / 180;
  let vx = (x - W / 2) / f, vy = -(y - shift - H / 2) / f;
  if (so) { const a = vx * Math.cos(so) + vy * Math.sin(so), b = -vx * Math.sin(so) + vy * Math.cos(so); vx = a; vy = b; }
  const E = R[0][0] * vx + R[0][1] * vy - R[0][2], N = R[1][0] * vx + R[1][1] * vy - R[1][2], U = R[2][0] * vx + R[2][1] * vy - R[2][2];
  const hh = (arOff.h + arDec) * Math.PI / 180, e = E * Math.cos(hh) + N * Math.sin(hh), n = N * Math.cos(hh) - E * Math.sin(hh);
  return {az: (Math.atan2(e, n) * 180 / Math.PI + 360) % 360, el: Math.atan2(U, Math.hypot(e, n)) * 180 / Math.PI};
}
function arLoop(){
  if (!arOn) return;
  arRaf = requestAnimationFrame(arLoop);
  const cv = $("arCv"), W = cv.clientWidth, H = cv.clientHeight, px = Math.min(2, devicePixelRatio || 1);
  if (cv.width !== Math.round(W * px) || cv.height !== Math.round(H * px)) { cv.width = Math.round(W * px); cv.height = Math.round(H * px); }
  const g = cv.getContext("2d");
  g.setTransform(px, 0, 0, px, 0, 0); g.clearRect(0, 0, W, H);
  arZoomStep();                                      // 1.99
  arFrame(performance.now());                        // 1.95.0.2: where the phone points now
  if (!arQ) return;
  const R = arQMatrix(arQ), here = arHere || {lat: S.lat, lon: S.lon}, wx = arWeather();
  arDec = magDecl(here.lat, here.lon);
  const r = here.lat * Math.PI / 180, ky = 111132.95 - 559.82 * Math.cos(2 * r) + 1.18 * Math.cos(4 * r), kx = 111412.84 * Math.cos(r) - 93.5 * Math.cos(3 * r);
  const dt = (Date.now() - arListAt) / 1000;
  const shown = [];
  for (const ac of arList) {
    if (ac.lat == null || ac.lon == null) continue;
    const h = arHeight(ac, wx), alt = typeof ac.alt_baro === "number" ? ac.alt_baro : typeof ac.alt_geom === "number" ? ac.alt_geom : null;
    if (h == null || h < -200) continue;
    const mv = arMove(ac, Math.min(60, dt + (ac.seen_pos || 0)));   // on to now
    const e = (ac.lon - here.lon) * kx + mv[0], n = (ac.lat - here.lat) * ky + mv[1], d = Math.hypot(e, n);
    if (d > 60000) continue;
    // 1.76.1: from the phone's height (else the airport's), so a plane below a cliff top shows below the horizon; a
    // descent isn't carried on below the airport. The earth's curve too (with the usual refraction).
    const u = Math.max(h + mv[2], Math.min(h, wx.elev)) - (arAlt != null ? arAlt : wx.elev) - d * d / (2 * 6371000) * .87;
    const pr = arProject(e, n, u, R, W, H), isFeat = arWant ? arWant === ac.hex : feat && feat.hex === ac.hex;
    if (pr.edge && !isFeat) continue;
    const info = (infoCache.get(ac.hex + "|" + String(ac.flight || "").trim().toUpperCase()) || {}).info || baseInfo(ac);
    // 1.72.1: the game's chip: ★ within reach of points, ✓ once locked on, NO PTS too far (live location only).
    // 1.80 (Dave's to-do 7, his pick A): the ★ in the plane's rarity colour, with what it gives (what it gave, once scored).
    // 1.96: what a scan gives (the relay's rules); 1.97: the plane's full points, on top of what it scored on its way in
    // 1.98 (relay 82): ★ only for a plane a scan counts for (the relay's list, or within the scan's 10 km now); one within
    // the passive circle (15 km), now or on its way, scored already: CLOSER TO SCAN
    const game = gameOk() && S.live, gx = game ? spotted.find(x => x.hex === ac.hex && (x.lock || x.scan)) : null;
    const near = game && !gx && (gScanSet().has(ac.hex) || d / 1000 <= gScanKm());
    const closer = game && !gx && !near && (d / 1000 <= gKm() || spotted.some(x => x.hex === ac.hex && x.gp != null && x.liveMin != null && x.liveMin <= gKm()));
    // 1.101 (to-do #148): a golden ticket's plane (the relay's list): its ★ shows the doubled points, its label edged in gold
    const gold = near && gGoldSet().has(ac.hex), tier = tierOf(ac, info), pts = gBase(tier) == null ? null : gBase(tier) * (gold ? 2 : 1);
    const chip = !game ? "" : gx ? "✓ +" + nf.format((gx.lock || 0) + (gx.gs || 0)) : near ? "★" + (pts == null ? "" : " " + nf.format(pts)) : closer ? T("CLOSER TO SCAN") : T("NO PTS");
    shown.push({ac, d, pr, isFeat, chip, gold, locked: !!gx, tier: near ? tier : "", el: Math.atan2(u, d) * 180 / Math.PI, far: game && !gx && !near, name: info.flightNo || String(ac.flight || "").trim() || ac.r || ac.hex.toUpperCase(),
      sub: [shortType(info.type || TYPES[String(ac.t || "").toUpperCase()] || ac.t || ""), altitudeStr(alt).toLowerCase(), (d / 1000 < 10 ? (d / 1000).toFixed(1) : Math.round(d / 1000)) + " km"].filter(Boolean).join(" · ")});
  }
  shown.sort((a, b) => a.d - b.d);
  const marks = arBodiesDraw(g, R, here, W, H), boxes = [];
  arHits = [];
  g.textBaseline = "alphabetic";
  for (const s of shown.slice(0, 14)) {
    if (s.pr.edge) { arEdge(g, s, W, H); continue; }
    const {x, y} = s.pr;
    g.font = `700 15px ${FONT}`; const w1 = g.measureText(s.name).width; g.font = `500 12px ${FONT}`; const w2 = g.measureText(s.sub).width;
    g.font = `700 10px ${FONT}`; const wc = s.chip ? g.measureText(s.chip).width + 12 : 0;
    const bw = Math.max(w1 + (wc ? wc + 6 : 0), w2) + 18, bh = 40;
    let bx = Math.min(W - bw - 6, Math.max(6, x - bw / 2)), by = y - 26 - bh;
    for (let k = 0; k < 8 && boxes.some(b => bx < b[0] + b[2] && bx + bw > b[0] && by < b[1] + b[3] && by + bh > b[1]); k++) by -= bh + 6;   // no overlaps
    boxes.push([bx, by, bw, bh]); arHits.push({hex: s.ac.hex, x, y, box: [bx, by, bw, bh]});
    const col = s.isFeat ? "#f0b429" : "rgba(255,255,255,.85)";
    if (s.ac.hex === arSel || s.ac.hex === arWant) { g.strokeStyle = "#f3f0e8"; g.lineWidth = 2.5; g.beginPath(); g.arc(x, y, 14, 0, Math.PI * 2); g.stroke(); }
    g.strokeStyle = col; g.lineWidth = 1.5; g.beginPath(); g.moveTo(x, y - 6); g.lineTo(x, by + bh); g.stroke();
    g.beginPath(); g.arc(x, y, 6, 0, Math.PI * 2); g.stroke();
    g.globalAlpha = s.far ? .62 : 1;                 // too far for points: dimmed
    g.fillStyle = s.isFeat ? "rgba(240,180,41,.92)" : "rgba(11,11,12,.78)"; rr(g, bx, by, bw, bh, 7); g.fill();
    g.fillStyle = s.isFeat ? "#111" : "#f3f0e8"; g.font = `700 15px ${FONT}`; g.fillText(s.name, bx + 9, by + 18);
    g.fillStyle = s.isFeat ? "#2a2108" : "#b9b3a3"; g.font = `500 12px ${FONT}`; g.fillText(s.sub, bx + 9, by + 33);
    if (s.chip) {
      const cx = bx + 9 + w1 + 6;
      const tc = TIER_COL[s.tier] && !(s.isFeat && s.tier === "legendary") ? TIER_COL[s.tier] : "";   // gold on the gold label: as before
      g.fillStyle = s.far ? "rgba(255,255,255,.2)" : tc || (s.isFeat ? "#17140e" : "#f0b429"); rr(g, cx, by + 6, wc, 15, 7.5); g.fill();
      g.fillStyle = s.far ? "#e7e2d6" : tc ? (s.tier === "legendary" ? "#17140e" : "#fff") : s.isFeat ? "#f0b429" : "#17140e"; g.font = `700 10px ${FONT}`; g.fillText(s.chip, cx + 6, by + 17);
    }
    if (s.gold) {                                    // 1.101: a gold edge round the label and a GOLDEN ×2 tab on it
      const gr = g.createLinearGradient(bx, by, bx + bw, by + bh), tab = T("GOLDEN ×2");
      gr.addColorStop(0, "#fff1b8"); gr.addColorStop(.4, "#e0aa1f"); gr.addColorStop(.7, "#b8860b"); gr.addColorStop(1, "#f6d27a");
      g.strokeStyle = gr; g.lineWidth = 2.5; rr(g, bx, by, bw, bh, 7); g.stroke();
      g.font = `700 9px ${FONT}`; const tw = g.measureText(tab).width + 10;
      g.fillStyle = gr; rr(g, bx + 10, by - 9, tw, 14, 7); g.fill();
      g.fillStyle = "#17140e"; g.fillText(tab, bx + 15, by + 1.5);
    }
    g.globalAlpha = 1;
  }
  if (arAutoLock) for (const s of shown) if (!s.pr.edge && arAutoLock.hexes.includes(s.ac.hex)) arBrackets(g, s.pr.x, s.pr.y);
  if (arAutoLock && arAutoLock.sun) for (const m of marks) if (m.k === "sun") arBrackets(g, m.x, m.y, 32, 10);   // 1.86
  arShownN = shown.length;
  if (arLocked && shown.some(s => s.ac.hex === arLocked && !s.pr.edge)) arShotAt = Date.now();   // 1.90: only once locked on (the ring full)
  const shut = $("arShut"), snap = Date.now() - arShotAt < 5000;
  if (shut.hidden === snap) shut.hidden = !snap;
  // 1.90: with the small card open, the shutter sits above it (it was behind it)
  const card = $("arCard"), lift = snap && !card.hidden && !arFull && arP === 0 ? card.offsetHeight + 4 : 0;
  if (lift !== arLift) { arLift = lift; $("arView").style.setProperty("--ar-lift", lift + "px"); }
  $("arCount").textContent = shown.length ? T(shown.length === 1 ? "1 plane" : "{n} planes", {n: shown.length}) : T("No planes nearby");
  $("arReset").classList.toggle("moved", Math.abs(arOff.h) > .5 || Math.abs(arOff.p) > .5);   // 1.72.7: the labels were dragged
  // 1.86: until the labels are lined up, AUTO asks for a look near the sun (it finds it in the picture by itself)
  const sunUp = arBody && arBody.sun.el > 1 && arBody.sun.el < 75;
  const hint = Date.now() < arNote.until ? arNote.text : arHeldAt ? arHintText : arAuto && sunUp ? T("Point the phone near the sun for a moment, without looking into it: AUTO finds it and lines every label up.")
    : marks.some(m => m.k === "sun") ? T("Sun beside its ring? Drag the sky until it sits in it on the screen: every label follows. Don't look into the sun.")
    : marks.length ? T("Moon beside its ring? Drag the sky until it sits in it: every label follows.") : arHintText;
  if (hint && $("arHint").textContent !== hint) $("arHint").textContent = hint;
  arAimDraw(g, W, H);
  arRibbon(R, W, H);
  arAutoStep(shown, W, H, marks.filter(m => m.k === "sun"), R);
}
/* 1.90 (Dave's pick A, relay 72): the flag in the top bar sends the relay what Sky view knows about the compass, so it can
   be tuned from real phones: the readings the sensors gave, north as the compass says and as it is in use, the gyroscope's
   turn, what AUTO found and how far off the sun's ring was. No picture and no place (only the declination, rounded).
   The owner's devices only; the relay keeps the newest 200. */
const arReportOk = () => (window.OVERHEAD_RELAY_VERSION || 0) >= 72 && !!relay() && !!(GUEST && GUEST.owner);
const arR1 = v => typeof v === "number" && isFinite(v) ? Math.round(v * 10) / 10 : null;
function arReport(){
  const now = Date.now(), t = performance.now(), cv = $("arCv"), W = cv.clientWidth, H = cv.clientHeight, v = $("arVid");
  const c = arQ ? arUnproject(W / 2, H / 2, arQMatrix(arQ), W, H) : null, sun = arBody && arBody.sun, moon = arBody && arBody.moon;
  return {
    v: 2, app: typeof VERSION === "string" ? VERSION : "", os: /iPhone|iPad/.test(navigator.userAgent) ? "ios" : /Android/.test(navigator.userAgent) ? "android" : "other",
    secs: Math.round((now - arSince) / 1000), events: arEvN, gap: arR1(arGap), dec: arR1(arDec), off: {h: arR1(arOff.h), p: arR1(arOff.p)},
    held: arHeldAt ? {secs: Math.round((now - arHeldAt) / 1000), why: arHeldWhy} : null,
    unsure: now - arCalAt < 4000, rate: arR1(arRate), stillSecs: arR1((t - arMovedAt) / 1000),
    facing: c && {az: arR1(c.az), el: arR1(c.el)}, q: arQ && arQ.map(x => Math.round(x * 1e4) / 1e4),
    gapRef: arR1(arGapRef), gapLog: arGapLog.filter((x, i) => i % 4 === 0).map(([gt, rel]) => [Math.round(gt - t), arR1(rel)]),
    raw: arRaw.map(([rt, a, b, g]) => [rt - now, arR1(a), arR1(b), arR1(g)]),
    auto: {on: arAuto, sun: !!(arAutoLock && arAutoLock.sun), planes: arAutoLock && !arAutoLock.sun ? arAutoLock.hexes.length : 0},
    finds: arAutoFinds.map(x => [x.hex === "sun" ? "sun" : "plane", x.t - now, arR1(x.h), arR1(x.p)]),
    sun: sun && {az: arR1(sun.az), el: arR1(sun.el), ring: arSunLast && {secs: Math.round((now - arSunLast.t) / 1000), h: arR1(arSunLast.h), p: arR1(arSunLast.p)}},
    moon: moon && moon.el > -.5 ? {az: arR1(moon.az), el: arR1(moon.el)} : null,
    screen: {w: W, h: H, video: [v.videoWidth || 0, v.videoHeight || 0], focal: Math.round(arFocal(W, H)), zoom: arR1(arZk * arZc), camZoom: arR1(arZk), turned: (screen.orientation && screen.orientation.angle) || 0},
    planes: arShownN,
    // 1.95.0.2: the last 120 gaps between readings and between frames (ms), the readings each frame had, the turn (°/s)
    timing: {ahead: AR_AHEAD, reads: arTim.reads, frames: arTim.frames, fresh: arTim.fresh, turn: arR1(Math.hypot(...arW) * 180 / Math.PI)},
  };
}
$("arFlag").onclick = async () => {
  ctlSound.click();
  const b = $("arFlag"), say = text => { arNote = {text, until: Date.now() + 8000}; $("arHint").textContent = text; };
  b.disabled = true;
  try {
    const r = await fetch(`${relay()}/skyreport`, {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(arReport())});
    if (!r.ok) throw new Error(r.status === 429 ? "too soon" : "HTTP " + r.status);
    b.classList.add("sent");
    say(T("✓ Report sent: the compass and gyroscope readings, AUTO's finds and the sun's offset went to the relay, to tune Sky view. No picture, no place."));
    dlog("info", "Sky view: report sent");
  } catch (e) {
    say(T(String(e.message) === "too soon" ? "A report was just sent: try again in a moment." : "Couldn't send the report: the relay didn't answer."));
    dlog("warn", `Sky view report: not sent (${e.message})`);
  }
  b.disabled = false;
};
// 1.80 (Dave's to-do 1, his pick A, the button only once a plane in view has been scanned; 1.90: once a plane in view is
// locked on, the ring full, and for 5 s after it leaves the picture): Sky view as it is on the
// screen, the camera's picture and the labels, with a slim band under it: the mark, the place, the date and time and how
// many planes. Shown in a card with Share and Save.
let arShotAt = 0, arShownN = 0, arLocked = "", arLift = 0;   // arLocked (1.90): the plane the ring last filled on
async function arSnap(){
  ctlSound.click();
  const v = $("arVid"), ov = $("arCv"), W = ov.width, H = ov.height, B = Math.round(W * .16), d = new Date(), n = arShownN;
  if (!W || !H) return;
  const cv = document.createElement("canvas"), g = cv.getContext("2d");
  cv.width = W; cv.height = H + B;
  g.fillStyle = "#000"; g.fillRect(0, 0, W, H);
  if (v.videoWidth) {                                   // as the screen shows it: the video covers it, cut to fit
    const k = Math.max(W / v.videoWidth, H / v.videoHeight) * arZc, w = v.videoWidth * k, h = v.videoHeight * k;
    g.drawImage(v, (W - w) / 2, (H - h) / 2, w, h);
  }
  g.drawImage(ov, 0, 0);
  g.fillStyle = "#0b0b0c"; g.fillRect(0, H, W, B);
  const L = Math.round(B * .56), x0 = Math.round(B * .22), y0 = H + (B - L) / 2, tx = x0 + L + B * .2, place = String(placeNow() || "").trim();
  g.fillStyle = "#f0b429"; rr(g, x0, y0, L, L, L * .13); g.fill();
  drawPlane(g, x0 + L / 2, y0 + L / 2, L * .86, "#0b0b0c");
  g.textAlign = "left"; g.textBaseline = "alphabetic";
  const title = place ? T("Sky over {p}", {p: place}) : T("Sky view"), by = spottedBy();      // 1.82.1: whose it is
  g.fillStyle = "#f3f0e8"; g.font = `700 ${Math.round(B * .24)}px ${FONT}`;
  g.fillText(title, tx, H + B * .47);
  const tw = g.measureText(title).width;
  g.fillStyle = "#959aa3"; g.font = `600 ${Math.round(B * .16)}px ${FONT}`;
  const right = by && tx + tw + B * .3 + g.measureText(by).width <= W - x0;
  if (right) { g.textAlign = "right"; g.fillText(by, W - x0, H + B * .47); g.textAlign = "left"; }
  g.fillText([d.toLocaleDateString(LOC(), {day: "numeric", month: "short", year: "numeric"}), hhmm(d), T(n === 1 ? "1 plane" : "{n} planes", {n}), right ? "" : by].filter(Boolean).join(" · "), tx, H + B * .75);
  const fl = document.createElement("div"); fl.className = "arFlash"; $("arView").appendChild(fl); setTimeout(() => fl.remove(), 450);
  const blob = await new Promise(ok => cv.toBlob(ok, "image/png"));
  dlog(blob ? "info" : "warn", blob ? `Sky view snapshot · ${n} planes · ${W}×${H + B}` : "Sky view snapshot: couldn't make the picture");
  if (blob) picCard(blob, `fallblatt-sky-${d.getFullYear()}${String(d.getMonth() + 1).padStart(2, "0")}${String(d.getDate()).padStart(2, "0")}-${hhmm(d).replace(":", "")}.png`);
}
// 1.76: AUTO's mark on a plane it found in the picture: gold corners round its dot.
function arBrackets(g, x, y, r = 14, arm = 6){
  g.save(); g.strokeStyle = "#f0b429"; g.lineWidth = 2.5; g.beginPath();
  for (const [a, b] of [[-1, -1], [1, -1], [-1, 1], [1, 1]]) { g.moveTo(x + a * r, y + b * (r - arm)); g.lineTo(x + a * r, y + b * r); g.lineTo(x + a * (r - arm), y + b * r); }
  g.stroke(); g.restore();
}
/* 1.76: AUTO, Sky view lining itself up (experimental; on unless switched off, kept per phone). A few times a second
   the camera's picture around each nearby plane's label is searched for a plane-sized dot against the sky (darker than
   the sky by day, a light at night). Where one keeps turning up in the same place for a second or so, the labels
   slide onto it, as a drag would. Labels close together and the sun's glare are left out; a lone dot in an even sky
   counts, edges (clouds, roofs) and lines (contrails, wires) don't. */
const AR_AUTO_MS = 160, AR_AUTO_R = 9, AR_AUTO_N = 240;   // how often, how far around a label (degrees), samples across
let arAuto = true, arAutoAt = 0, arAutoFinds = [], arAutoLock = null, arAutoPause = 0, arAutoSaved = 0, arAutoSig = "";
const arCan = document.createElement("canvas"), arCx = arCan.getContext("2d", {willReadFrequently: true});
function arAutoStep(shown, W, H, avoid, R){
  const now = Date.now(), v = $("arVid");
  if (!arAuto || arDrag || now < arAutoPause || now - arAutoAt < AR_AUTO_MS || !(v.readyState >= 2) || !v.videoWidth) return arAutoChip();
  arAutoAt = now;
  // 1.86: the sun, anywhere in the picture, says how far off the compass is (up to 45°)
  const sun = arBody && arBody.sun;
  if (sun && sun.el > 1 && sun.el < 75) {
    const hit = arSunFind(v, R, W, H, sun);
    if (hit) {
      arAutoFinds.push({hex: "sun", t: now, h: arOff.h + wrap180(sun.az - hit.az), p: arOff.p + sun.el - hit.el});
      arSunLast = {t: now, h: wrap180(sun.az - hit.az), p: sun.el - hit.el};   // 1.90: how far off the sun's ring was, for the report
    }
  }
  const f = arFocal(W, H), r = f * Math.tan(AR_AUTO_R * Math.PI / 180);
  const near = shown.filter(o => !o.pr.edge && o.d < 15000 && o.el > 2 && o.pr.x > 0 && o.pr.x < W && o.pr.y > 0 && o.pr.y < H);
  for (const o of near.slice(0, 3)) {
    if (near.some(q => q !== o && Math.hypot(q.pr.x - o.pr.x, q.pr.y - o.pr.y) < r * 1.3)) continue;   // two planes close: which is which?
    if (avoid.some(a => Math.hypot(a.x - o.pr.x, a.y - o.pr.y) < r * 1.6)) continue;                      // the sun's glare
    const span = {A1: 11, A2: 20, A5: 65, A7: 11}[o.ac.category] || 35;                             // wingspan or rotor, metres
    const hit = arFind(v, W, H, o.pr.x, o.pr.y, r, span / o.d * f);
    if (hit) arAutoFinds.push({hex: o.ac.hex, t: now, h: arOff.h - Math.atan((hit.x - o.pr.x) / f) * 180 / Math.PI, p: arOff.p + Math.atan((hit.y - o.pr.y) / f) * 180 / Math.PI});
  }
  arAutoFinds = arAutoFinds.filter(x => now - x.t < 2500);
  // a plane counts when most of its last finds agree (within 0.7°; the sun, 4 finds within 1.2°); the planes counted
  // must agree with each other. 1.86: the sun, once found, decides alone (where it is is known exactly).
  const med = a => [...a].sort((x, y) => x - y)[a.length >> 1], got = [];
  for (const hex of new Set(arAutoFinds.map(x => x.hex))) {
    const fs = arAutoFinds.filter(x => x.hex === hex), tol = hex === "sun" ? 1.2 : .7;
    if (fs.length < (hex === "sun" ? 4 : 5)) continue;
    const h = med(fs.map(x => x.h)), p = med(fs.map(x => x.p));
    if (fs.filter(x => Math.abs(x.h - h) < tol && Math.abs(x.p - p) < tol).length >= fs.length * .8) got.push({hex, h, p});
  }
  const use = got.some(x => x.hex === "sun") ? got.filter(x => x.hex === "sun") : got;
  const h = use.length ? med(use.map(x => x.h)) : 0, p = use.length ? med(use.map(x => x.p)) : 0;
  if (use.length && use.every(x => Math.abs(x.h - h) < 1.5 && Math.abs(x.p - p) < 1.5)) {
    const onSun = use[0].hex === "sun";
    if (!arAutoLock || arAutoLock.sun !== onSun) dlog("debug", `Sky view AUTO: lined up on ${onSun ? "the sun" : use.length === 1 ? "1 plane" : use.length + " planes"}, moved ${(h - arOff.h).toFixed(1)}° across, ${(p - arOff.p).toFixed(1)}° up`);
    arAutoLock = {hexes: use.map(x => x.hex), sun: onSun, at: now};
    const k = 1 - Math.exp(-AR_AUTO_MS / 700);       // glides there in a second or two
    arOff.h += (h - arOff.h) * k; arOff.p += (p - arOff.p) * k;
    if (now - arAutoSaved > 5000) { arAutoSaved = now; arOffSave(); }
    arHold(onSun ? "AUTO, on the sun" : "AUTO");
  } else if (arAutoLock && now - arAutoLock.at > 2000) arAutoLock = null;
  arAutoChip();
}
// Looks for a plane-sized dot in the camera's picture within r of (x, y) on the screen: its screen position, or null.
// The picture is scaled so the plane (size: its expected span in screen px) comes out about 3 samples across.
function arFind(v, W, H, x, y, r, size){
  const vw = v.videoWidth, vh = v.videoHeight, s = Math.max(W / vw, H / vh) * arZc;   // screen px to a video px (cover; 1.99: enlarged)
  const cx = vw / 2 + (x - W / 2) / s, cy = vh / 2 + (y - H / 2) / s, vr = r / s;
  const x0 = Math.max(0, cx - vr), y0 = Math.max(0, cy - vr), x1 = Math.min(vw, cx + vr), y1 = Math.min(vh, cy + vr);
  const k = Math.min(1, AR_AUTO_N / (2 * vr), 3 / Math.max(1, size / s)), w = Math.round((x1 - x0) * k), h = Math.round((y1 - y0) * k);
  if (w < 24 || h < 24) return null;
  if (arCan.width !== w || arCan.height !== h) { arCan.width = w; arCan.height = h; }
  arCx.drawImage(v, x0, y0, x1 - x0, y1 - y0, 0, 0, w, h);
  const px = arCx.getImageData(0, 0, w, h).data, w1 = w + 1, I = new Float64Array(w1 * (h + 1));
  for (let j = 0; j < h; j++) for (let i = 0, row = 0; i < w; i++) {   // the brightness, summed (an integral image)
    const q = (j * w + i) * 4; row += .299 * px[q] + .587 * px[q + 1] + .114 * px[q + 2];
    I[(j + 1) * w1 + i + 1] = I[j * w1 + i + 1] + row;
  }
  const box = (i, j, b) => {                         // the mean brightness of the square of side 2b+1 around (i, j)
    const a0 = Math.max(0, i - b), b0 = Math.max(0, j - b), a1 = Math.min(w, i + b + 1), b1 = Math.min(h, j + b + 1);
    return (I[b1 * w1 + a1] - I[b0 * w1 + a1] - I[b1 * w1 + a0] + I[b0 * w1 + a0]) / ((a1 - a0) * (b1 - b0));
  };
  const d = new Float32Array(w * h);                 // how much each small spot stands out from the sky around it
  for (let j = 1; j < h - 1; j++) for (let i = 1; i < w - 1; i++) d[j * w + i] = box(i, j, 1) - box(i, j, 6);
  const smp = [];
  for (let q = w + 1; q < d.length; q += 7) smp.push(Math.abs(d[q]));
  smp.sort((a, b) => a - b);
  const noise = Math.max(1.2, smp[smp.length >> 1] * 1.4826), ci = (cx - x0) * k, cj = (cy - y0) * k, rr2 = (vr * k) ** 2;
  const at = (i, j) => Math.abs(d[Math.round(j) * w + Math.round(i)] || 0);
  let best = null, second = 0;
  for (let j = 7; j < h - 7; j++) for (let i = 7; i < w - 7; i++) {
    const a = Math.abs(d[j * w + i]);
    if (a < noise * 5 || (i - ci) ** 2 + (j - cj) ** 2 > rr2) continue;
    let top = true;
    for (let jj = -2; jj <= 2 && top; jj++) for (let ii = -2; ii <= 2; ii++) if ((ii || jj) && Math.abs(d[(j + jj) * w + i + ii]) > a) { top = false; break; }
    if (!top) continue;
    const ring = [], arm = [];
    for (let q = 0; q < 12; q++) ring.push(at(i + 5 * Math.cos(q * Math.PI / 6), j + 5 * Math.sin(q * Math.PI / 6)));
    for (let q = 0; q < 4; q++) arm.push((at(i + 3 * Math.cos(q * Math.PI / 4), j + 3 * Math.sin(q * Math.PI / 4)) + at(i - 3 * Math.cos(q * Math.PI / 4), j - 3 * Math.sin(q * Math.PI / 4))) / 2);
    ring.sort((x, y) => x - y);
    if (ring[6] > noise * 2 || ring[6] > a * .35) continue;                       // not on its own: an edge or a patch
    if (Math.max(...arm) > a * .5 && Math.max(...arm) > Math.min(...arm) * 2.5) continue;   // a line through it
    if (!best || a > best.a) { if (best && Math.hypot(best.i - i, best.j - j) > 6) second = Math.max(second, best.a); best = {i, j, a}; }
    else if (Math.hypot(best.i - i, best.j - j) > 6) second = Math.max(second, a);
  }
  if (!best || second > best.a * .7) return null;    // nothing, or two alike: can't tell
  let sw = 0, si = 0, sj = 0;
  for (let jj = -1; jj <= 1; jj++) for (let ii = -1; ii <= 1; ii++) { const q = at(best.i + ii, best.j + jj); sw += q; si += q * ii; sj += q * jj; }
  const fx = x0 + (best.i + si / sw + .5) / k, fy = y0 + (best.j + sj / sw + .5) / k;
  return {x: W / 2 + (fx - vw / 2) * s, y: H / 2 + (fy - vh / 2) * s};
}
// 1.86: the sun in the camera's picture, wherever it is: the largest patch burnt out to white (its glare is several
// degrees across), round, not cut off by the picture's edge, at the sun's height (the tilt is right even when the
// compass isn't: reflections on the sea, lamps and white walls sit lower) and the only one there. {az, el, x, y} or null.
const arSunCan = document.createElement("canvas"), arSunCx = arSunCan.getContext("2d", {willReadFrequently: true});
function arSunFind(v, R, W, H, sun){
  const vw = v.videoWidth, vh = v.videoHeight, k = 160 / Math.max(vw, vh), w = Math.round(vw * k), h = Math.round(vh * k), n = w * h;
  if (arSunCan.width !== w || arSunCan.height !== h) { arSunCan.width = w; arSunCan.height = h; }
  arSunCx.drawImage(v, 0, 0, w, h);
  const px = arSunCx.getImageData(0, 0, w, h).data, L = new Float32Array(n);
  let top = 0;
  for (let q = 0; q < n; q++) { L[q] = .299 * px[q * 4] + .587 * px[q * 4 + 1] + .114 * px[q * 4 + 2]; if (L[q] > top) top = L[q]; }
  if (top < 245) return null;                        // nothing burnt out: no sun in the picture, or it is behind cloud
  const T = top - 10, lab = new Uint8Array(n), st = new Int32Array(n), s = Math.max(W / vw, H / vh) * arZc;
  let best = null, second = 0;
  for (let q0 = 0; q0 < n; q0++) {
    if (lab[q0] || L[q0] < T) continue;
    let sp = 0, cnt = 0, sx = 0, sy = 0, x0 = w, x1 = 0, y0 = h, y1 = 0;
    st[sp++] = q0; lab[q0] = 1;
    while (sp) {                                     // the patch, filled out from here
      const q = st[--sp], i = q % w, j = (q - i) / w;
      cnt++; sx += i; sy += j; x0 = Math.min(x0, i); x1 = Math.max(x1, i); y0 = Math.min(y0, j); y1 = Math.max(y1, j);
      for (let dj = -1; dj <= 1; dj++) for (let di = -1; di <= 1; di++) {
        const ii = i + di, jj = j + dj, qq = jj * w + ii;
        if (ii >= 0 && ii < w && jj >= 0 && jj < h && !lab[qq] && L[qq] >= T) { lab[qq] = 1; st[sp++] = qq; }
      }
    }
    if (cnt < 3) continue;
    const x = W / 2 + ((sx / cnt + .5) / k - vw / 2) * s, y = H / 2 + ((sy / cnt + .5) / k - vh / 2) * s, d = arUnproject(x, y, R, W, H);
    if (Math.abs(d.el - sun.el) > 6) continue;
    if (!best || cnt > best.cnt) {
      if (best) second = Math.max(second, best.cnt);
      best = {cnt, x, y, az: d.az, el: d.el, cut: x0 === 0 || y0 === 0 || x1 === w - 1 || y1 === h - 1, bw: x1 - x0 + 1, bh: y1 - y0 + 1};
    } else second = Math.max(second, cnt);
  }
  if (!best || best.cut || second > best.cnt / 3) return null;
  const across = 2 * Math.sqrt(best.cnt / Math.PI) / k * s / arFocal(W, H) * 180 / Math.PI;   // degrees
  if (across < .7 || across > 20 || best.cnt < .45 * best.bw * best.bh || Math.max(best.bw, best.bh) > 1.8 * Math.min(best.bw, best.bh)) return null;
  return Math.abs(wrap180(sun.az - best.az)) > 45 ? null : best;
}
// The AUTO switch under the title: off, looking, or lined up on the sun or n planes.
function arAutoChip(){
  const n = arAutoLock ? arAutoLock.hexes.length : 0, sun = !!(arAutoLock && arAutoLock.sun), sig = arAuto + "|" + n + "|" + sun;
  if (sig === arAutoSig) return;
  arAutoSig = sig;
  const b = $("arAuto");
  b.classList.toggle("on", arAuto && !!n); b.classList.toggle("off", !arAuto); b.setAttribute("aria-pressed", String(arAuto));
  b.innerHTML = `<b>${escH(T("AUTO"))}</b><span>${escH(!arAuto ? T("off") : sun ? T("lined up · sun") : n ? T(n === 1 ? "lined up · 1 plane" : "lined up · {n} planes", {n}) : T("looking"))}</span>`;
}
$("arAuto").onclick = () => {
  ctlSound.click(); arAuto = !arAuto; arAutoFinds = []; arAutoLock = null;
  try { localStorage.setItem("od.ar.auto", arAuto ? "1" : "0"); } catch {}
  arAutoChip();
};
// 1.76: the sun and the moon where they really are, as dashed rings: if the real one isn't in its ring, a drag lines it
// and every label up. Returns where they are on the screen.
let arBody = null, arBodyAt = 0;
function arBodiesDraw(g, R, here, W, H){
  const now = Date.now(), out = [], r = Math.PI / 180;
  if (now - arBodyAt > 1000) { arBody = skyBodies(here.lat, here.lon, now); arBodyAt = now; }
  for (const [k, b, name] of [["sun", arBody.sun, "SUN"], ["moon", arBody.moon, "MOON"]]) {
    if (b.el < -.5 || (k === "moon" && b.lit < .04)) continue;
    const pr = arProject(Math.sin(b.az * r) * Math.cos(b.el * r), Math.cos(b.az * r) * Math.cos(b.el * r), Math.sin(b.el * r), R, W, H);
    if (pr.edge) { arBodyEdge(g, k, b, pr, R, W, H); continue; }
    out.push({k, x: pr.x, y: pr.y});
    g.save(); g.shadowColor = "rgba(0,0,0,.55)"; g.shadowBlur = 4;
    g.setLineDash([6, 5]); g.strokeStyle = "#f0b429"; g.lineWidth = 2.5; g.beginPath(); g.arc(pr.x, pr.y, 22, 0, Math.PI * 2); g.stroke();
    g.font = `700 12px ${FONT}`; g.fillStyle = "#f0b429"; g.textAlign = "center"; g.fillText((k === "sun" ? "☀ " : "☾ ") + T(name), pr.x, pr.y - 30);
    g.restore();
  }
  return out;
}
// 1.90 (Dave's pick A): the sun or the moon out of the picture: a dashed arrow at the edge pointing the way, as the plane
// on top's arrow does, with how far to turn ("☀ SUN · 139° right"; up or down when it is above or below the picture).
function arBodyEdge(g, k, b, pr, R, W, H){
  const [dx, dy] = pr.edge, L = Math.hypot(dx, dy) || 1, ux = dx / L, uy = dy / L;
  const t = Math.min((W / 2 - 40) / Math.abs(ux || 1e-6), Math.max(30, H / 2 - 150) / Math.abs(uy || 1e-6)), x = W / 2 + ux * t, y = H / 2 + uy * t;
  const c = arUnproject(W / 2, H / 2, R, W, H), da = wrap180(b.az - c.az), half = Math.atan(W / 2 / arFocal(W, H)) * 180 / Math.PI;
  const how = Math.abs(da) > half ? T(da > 0 ? "{n}° right" : "{n}° left", {n: Math.round(Math.abs(da))})
    : T(b.el > c.el ? "{n}° up" : "{n}° down", {n: Math.round(Math.abs(b.el - c.el))});
  g.save(); g.shadowColor = "rgba(0,0,0,.55)"; g.shadowBlur = 4;
  g.translate(x, y); g.rotate(Math.atan2(uy, ux));
  g.setLineDash([5, 4]); g.strokeStyle = "#f0b429"; g.lineWidth = 2.5; g.lineJoin = "round";
  g.beginPath(); g.moveTo(18, 0); g.lineTo(-10, -12); g.lineTo(-4, 0); g.lineTo(-10, 12); g.closePath(); g.stroke();
  g.restore();
  g.save(); g.shadowColor = "rgba(0,0,0,.6)"; g.shadowBlur = 4; g.fillStyle = "#f0b429";
  g.textAlign = ux > .5 ? "right" : ux < -.5 ? "left" : "center";
  const tx = x - ux * 28, ty = y - uy * 28;
  g.font = `700 13px ${FONT}`; g.fillText((k === "sun" ? "☀ " : "☾ ") + T(k === "sun" ? "SUN" : "MOON"), tx, ty - 2);
  g.font = `600 12px ${FONT}`; g.fillText(how, tx, ty + 13);
  g.restore();
}
// 1.90 (Dave's pick: B's compass): a ribbon of the whole compass above the hint, the way the picture faces in the middle,
// the picture's width bracketed, the sun and the moon (when up) at their bearings with how high they are.
const AR_RIB = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"];
let arRibSig = "";
function arRibbon(R, W, H){
  const cv = $("arRib"), w = cv.clientWidth, h = cv.clientHeight, px = Math.min(2, devicePixelRatio || 1);
  if (!w || !arBody) return;
  const c = arUnproject(W / 2, H / 2, R, W, H), half = Math.atan(W / 2 / arFocal(W, H)) * 180 / Math.PI;
  const bodies = [["sun", arBody.sun], ["moon", arBody.moon]].filter(([k, b]) => b.el > -.5 && !(k === "moon" && b.lit < .04));
  const sig = [w, Math.round(c.az * 4), Math.round(half), ...bodies.map(([k, b]) => k + Math.round(b.az * 2) + "," + Math.round(b.el))].join("|");
  if (sig === arRibSig) return;
  arRibSig = sig;
  if (cv.width !== Math.round(w * px) || cv.height !== Math.round(h * px)) { cv.width = Math.round(w * px); cv.height = Math.round(h * px); }
  const g = cv.getContext("2d"), k = (w - 16) / 360, X = az => w / 2 + wrap180(az - c.az) * k, top = 16;
  g.setTransform(px, 0, 0, px, 0, 0); g.clearRect(0, 0, w, h);
  g.fillStyle = "rgba(11,11,12,.6)"; rr(g, 0, top, w, h - top, 9); g.fill();
  g.save(); rr(g, 0, top, w, h - top, 9); g.clip();
  g.strokeStyle = "rgba(255,255,255,.55)"; g.lineWidth = 1; g.beginPath();
  for (let a = 0; a < 360; a += 15) { const x = X(a), big = a % 45 === 0; g.moveTo(x, h - (big ? 9 : 5)); g.lineTo(x, h); }
  g.stroke();
  g.font = `700 11px ${FONT}`; g.textAlign = "center";
  AR_RIB.forEach((n, i) => { g.fillStyle = i ? "#e6e1d4" : "#ff5a4f"; g.fillText(T(n), X(i * 45), h - 12); });
  g.strokeStyle = "#f0b429"; g.lineWidth = 2; g.fillStyle = "rgba(240,180,41,.14)";   // the picture's width
  g.fillRect(w / 2 - half * k, top + 2, 2 * half * k, h - top - 4); g.strokeRect(w / 2 - half * k, top + 2, 2 * half * k, h - top - 4);
  g.restore();
  g.textAlign = "center"; g.shadowColor = "rgba(0,0,0,.6)"; g.shadowBlur = 3;
  for (const [n, b] of bodies) {
    const x = Math.max(10, Math.min(w - 10, X(b.az)));
    g.fillStyle = "#f0b429"; g.font = `700 15px ${FONT}`; g.fillText(n === "sun" ? "☀" : "☾", x, top + 17);
    g.font = `600 11px ${FONT}`; g.fillText(T("{n}° up", {n: Math.max(0, Math.round(b.el))}), x, top - 4);
  }
  g.shadowBlur = 0;
}
// 1.75.2: how far a plane has come since its position: along its track, round its turn (the rate it sends, or the one
// measured between two updates; at most 20 s of it) and up or down at its climb or descent rate. [east, north, up] m.
function arMove(ac, t){
  const v = (ac.gs || 0) * .5144, th = (ac.track || 0) * Math.PI / 180, tt = Math.min(t, 20);
  const vr = typeof ac.geom_rate === "number" ? ac.geom_rate : typeof ac.baro_rate === "number" ? ac.baro_rate : 0, up = vr * .3048 / 60 * tt;
  if (!v || ac.track == null) return [0, 0, up];
  const tr = typeof ac.track_rate === "number" ? ac.track_rate : (arTurns.get(ac.hex) || {}).rate || 0, w = Math.abs(tr) < .2 ? 0 : tr * Math.PI / 180;
  if (!w) return [v * t * Math.sin(th), v * t * Math.cos(th), up];
  const th2 = th + w * tt;
  return [v / w * (Math.cos(th) - Math.cos(th2)) + v * (t - tt) * Math.sin(th2), v / w * (Math.sin(th2) - Math.sin(th)) + v * (t - tt) * Math.cos(th2), up];
}
// 1.75.2: the home airport's METAR (relay /sky; with live location the airport nearest the phone): its elevation (m),
// QNH and temperature, for true heights.
function arWeather(){
  const raw = sky && sky.raw || "", q = /\bQ(\d{4})\b/.exec(raw), a = /\bA(\d{4})\b/.exec(raw), tc = /\s(M?\d{2})\/M?\d{2}\s/.exec(" " + raw + " ");
  const qnh = q ? +q[1] : a ? +a[1] / 100 * 33.8639 : 0;
  return {elev: sky && sky.elevation ? sky.elevation * .3048 : 0, qnh: qnh > 900 && qnh < 1100 ? qnh : 0, temp: tc ? +tc[1].replace("M", "-") : null};
}
// A plane's height above the sea in metres (1.76.1; was above the airport). Its pressure altitude (altimeters on 1013 hPa)
// is moved to the day's QNH (some 8 m a hectopascal) and, above the airport, scaled for the air's temperature (cold air:
// lower than it says); without a METAR as it is, and without a pressure altitude its GPS height.
function arHeight(ac, wx){
  let ft;
  if (typeof ac.alt_baro === "number") ft = ac.alt_baro - (wx.qnh ? 145366.45 * (1 - Math.pow(wx.qnh / 1013.25, .190284)) : 0);
  else if (typeof ac.alt_geom === "number") ft = ac.alt_geom;
  else return null;
  const m = ft * .3048, up = m - wx.elev;
  return wx.temp != null && up > 0 ? wx.elev + up * (wx.temp + 273.15) / (288.15 - .0065 * wx.elev) : m;
}
// The ring: the plane nearest its middle within it is aimed at; after AR_AIM_MS it opens (once, until the ring empties).
function arAimDraw(g, W, H){
  const cx = W / 2, cy = H / 2, now = Date.now();
  // 1.99: zoomed, the ring catches the same piece of sky as at ×1 (as many times wider); drawn no wider than the screen
  const catchR = AR_AIM_R * arZk * arZc, R0 = Math.min(catchR, Math.min(W, H) / 2 - 16);
  const hit = arHits.reduce((a, h) => { const d = Math.hypot(h.x - cx, h.y - cy); return d < catchR && (!a || d < a.d) ? {hex: h.hex, d} : a; }, null);
  const hex = hit ? hit.hex : "";
  if (hex !== arAim.hex) arAim = {hex, since: now, done: hex && hex === arAim.done ? hex : ""};
  const sel = arSel === arWant ? "" : arSel;           // 1.97: the plane Sky view was opened at is picked out, not yet scanned
  const k = hex && hex !== arAim.done && hex !== sel ? Math.min(1, (now - arAim.since) / AR_AIM_MS) : hex === sel && hex ? 1 : 0;
  g.lineWidth = 3; g.strokeStyle = "rgba(255,255,255,.85)";
  g.beginPath(); g.arc(cx, cy, R0, 0, Math.PI * 2); g.stroke();
  g.beginPath(); g.moveTo(cx, cy - R0 - 12); g.lineTo(cx, cy - R0 + 6); g.moveTo(cx, cy + R0 - 6); g.lineTo(cx, cy + R0 + 12);
  g.moveTo(cx - R0 - 12, cy); g.lineTo(cx - R0 + 6, cy); g.moveTo(cx + R0 - 6, cy); g.lineTo(cx + R0 + 12, cy); g.stroke();   // 1.76.1: all four sides
  if (k > 0) {
    g.strokeStyle = "#f0b429"; g.lineWidth = 5;
    g.beginPath(); g.arc(cx, cy, R0, -Math.PI / 2, -Math.PI / 2 + k * Math.PI * 2); g.stroke();
  }
  arPeekWatch(hex);
  if (hex && k >= 1 && hex !== sel && hex !== arAim.done) {
    if (hex === arWant) arWant = "";
    arAim.done = hex; arSel = hex; arLocked = hex; arFull = false; arAwayAt = 0; arCardSig = ""; ctlSound.nav(); arCardRender();
    gLockOn(hex);                                    // 1.72: the game's bonus, and its boarding pass
  }
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
function arDragStart(e){ arDrag = {x: e.clientX, y: e.clientY, h: arOff.h, p: arOff.p, moved: false}; e.target.setPointerCapture && e.target.setPointerCapture(e.pointerId); }
function arDragMove(e){
  if (!arDrag) return;
  if (!arDrag.moved && Math.hypot(e.clientX - arDrag.x, e.clientY - arDrag.y) < 8) return;       // still a tap
  arDrag.moved = true;
  const cv = $("arCv"), f = arFocal(cv.clientWidth, cv.clientHeight);
  arOff.h = arDrag.h - Math.atan((e.clientX - arDrag.x) / f) * 180 / Math.PI;
  arOff.p = arDrag.p + Math.atan((e.clientY - arDrag.y) / f) * 180 / Math.PI;
}
function arDragEnd(e){
  if (!arDrag) return;
  const tap = !arDrag.moved; arDrag = null;
  if (tap && e && e.type === "pointerup") return arTap(e);
  arOffSave();
  arAutoFinds = []; arAutoLock = null; arAutoPause = Date.now() + 5000;   // 1.76: the finger wins; AUTO waits
  arHold("by hand");
  arMovedNote();
}
// 1.72.7: after a drag, a note by ⟲ for a moment: the labels sit where the finger put them, not where the compass says.
function arMovedNote(){
  const n = $("arMoved");
  n.textContent = T("Labels moved by hand · ⟲ to undo"); n.hidden = false;
  clearTimeout(arMovedNote.t); arMovedNote.t = setTimeout(() => { n.hidden = true; }, 3500);
}
// 1.72.7: the walkthrough, the first time Sky view opens and from ⓘ: the ring, the drag, the buttons.
const AR_TOUR = [["ring", "Hold a plane in the ring", "Point the ring at a plane and keep it there for a moment: its card opens. With live location on, it pays a bonus too."],
  ["drag", "Labels beside the planes?", "Phone compasses drift. Drag the sky sideways, or up and down, until the labels sit on the planes, or the sun or the moon in its dashed ring."],
  ["btns", "The buttons", "AUTO looks for the sun and nearby planes in the picture and lines the labels up by itself (tap it to switch it off). ⟲ puts the labels back where the compass says (it lights up once they've moved). ⓘ shows these tips again. ✕ closes Sky view."]];
function arTour(step){
  const box = $("arTour");
  if (step >= AR_TOUR.length) {
    box.hidden = true; $("arView").classList.remove("tourBtns");
    try { localStorage.setItem("od.ar.tour", "1"); } catch {}
    return;
  }
  const [k, h, p] = AR_TOUR[step];
  $("arView").classList.toggle("tourBtns", k === "btns");
  // 1.72.8: the drag step acts it out: a plane in the ring, its label beside it, a finger dragging the label onto it
  const drag = `<div class="arTourDrag"><svg class="arTourPlane" viewBox="0 0 24 24" aria-hidden="true"><path d="M21 16v-2l-8-5V3.5a1.5 1.5 0 0 0-3 0V9l-8 5v2l8-2.5V19l-2 1.5V22l3.5-1 3.5 1v-1.5L13 19v-5.5z" fill="currentColor"/></svg>` +
    `<div class="arTourLab"><b>OS 411</b><small>A320 · 2,300 m · 6.8 km</small><i class="arTourFinger"></i></div></div>`;
  box.innerHTML = (k === "ring" ? '<i class="arTourRing"></i>' : k === "drag" ? drag : "") +
    `<div class="arTourBox" role="dialog" aria-live="polite"><h3>${escH(T(h))}</h3><p>${escH(T(p))}${k === "btns" ? " " + escH(T("×2 and ×5 zoom in; a second tap goes back.")) : ""}</p><div class="arTourAct"><span>${step + 1} / ${AR_TOUR.length}</span>` +
    (step < AR_TOUR.length - 1 ? `<button class="arTourSkip" type="button">${escH(T("Skip"))}</button>` : "") +
    `<button class="cBtn arNext" type="button">${escH(T(step < AR_TOUR.length - 1 ? "Next" : "Got it"))}</button></div></div>`;
  box.hidden = false;
  box.querySelector(".arNext").onclick = () => { ctlSound.click(); arTour(step + 1); };
  const sk = box.querySelector(".arTourSkip"); if (sk) sk.onclick = () => { ctlSound.click(); arTour(AR_TOUR.length); };
}
$("arInfo").onclick = () => { ctlSound.nav(); arTour(0); };
/* 1.78: the cards (an airline, a type, an aircraft, a place …) are sheets, the way Sky view's card is: up from the bottom,
   floating, with a grip; dragged down (or flicked) past the mark, or tapped beside, one slides away; a card that changes
   while it is open fades into its new content and height. The board's cardOpen and cardClose call these. */
let cardSheetHtml = "";
function cardSheetPre(box, html){
  const ci = box.querySelector(".cardIn"), open = !box.hidden && box.classList.contains("in") && !box.classList.contains("closing");
  return {open, h: open && ci ? ci.offsetHeight : 0, same: open && html === cardSheetHtml, html};
}
function cardSheetPost(box, pre){
  const ci = box.querySelector(".cardIn");
  cardSheetHtml = pre.html; clearTimeout(cardSheetClose.t);
  box.classList.remove("closing", "drag");
  if (!pre.open) { box.classList.remove("in"); void box.offsetWidth; box.classList.add("in"); return; }   // up from below
  if (pre.same || REDUCED) return;
  const h1 = ci.offsetHeight;                        // another card in its place: from the old height to the new one
  if (Math.abs(h1 - pre.h) > 2) {
    ci.style.height = pre.h + "px"; void ci.offsetWidth; ci.style.height = h1 + "px";
    setTimeout(() => { if (ci.isConnected) ci.style.height = ""; }, 320);
  }
  ci.classList.add("swap");
}
// 1.94: a card that grows while it is open (More info): the sheet from its old height up to its new one.
function cardSheetGrow(ci, h0){
  const h1 = ci.offsetHeight;
  if (REDUCED || Math.abs(h1 - h0) < 3) return;
  ci.style.height = h0 + "px"; void ci.offsetWidth; ci.style.height = h1 + "px";
  setTimeout(() => { if (ci.isConnected) ci.style.height = ""; }, 320);
}
function cardSheetClose(b){
  if (b.hidden || !b.classList.contains("in")) return false;
  const ci = b.querySelector(".cardIn");
  if (ci) ci.style.transform = "";                   // from where the finger left it
  b.classList.remove("in", "drag"); b.classList.add("closing"); cardSheetHtml = "";
  clearTimeout(cardSheetClose.t);
  cardSheetClose.t = setTimeout(() => { if (b.classList.contains("closing")) { b.hidden = true; b.classList.remove("closing"); } }, 270);
  return true;
}
// The finger on a card: down from its top (when it isn't scrolled) drags it; let go past 90 px, or flicked, it goes,
// else it springs back. 1.78.1: pulled up where it can't scroll any further (a short card, or at its end) it gives a
// little against a spring and comes back when let go; both ways in one movement. A scrolling card keeps its scroll to
// itself, and a finger on the dark beside it moves nothing: the page behind never scrolls.
{ let drag = null, dragged = 0;
  document.addEventListener("touchstart", e => {
    const box = $("cardBox");
    if (!box || box.hidden) { drag = null; return; }
    const ci = e.target.closest && e.target.closest("#cardBox .cardIn"), y = e.touches[0].clientY;
    drag = !ci ? {beside: true}
      : {ci, y0: y, on: false, top: ci.scrollTop <= 0, end: ci.scrollTop + ci.clientHeight >= ci.scrollHeight - 1, dy: 0, v: 0, lt: performance.now(), ly: y};
  }, {passive: true});
  document.addEventListener("touchmove", e => {
    if (!drag) return;
    if (drag.beside) { if (e.cancelable) e.preventDefault(); return; }
    const y = e.touches[0].clientY;
    if (!drag.on) {
      if (Math.abs(y - drag.y0) < 6) return;
      if (y > drag.y0 ? !drag.top : !drag.end) { drag = null; return; }   // the card scrolls
      drag.on = true; drag.y0 = y; $("cardBox").classList.add("drag");
    }
    if (e.cancelable) e.preventDefault();
    const now = performance.now(), d = drag.dy = y - drag.y0;
    drag.v = (y - drag.ly) / Math.max(1, now - drag.lt); drag.ly = y; drag.lt = now;
    drag.ci.style.transform = `translateY(${(d > 0 ? d : d * .5 / (1 - d / 220)).toFixed(1)}px)`;   // up: ever harder, at most ~110 px
  }, {passive: false});
  const end = () => {
    const d = drag; drag = null;
    if (!d || d.beside || !d.on) return;
    dragged = Date.now();
    $("cardBox").classList.remove("drag");
    if (d.dy > 90 || (d.v > .5 && d.dy > 20)) { ctlSound.click(); cardClose(); }
    else d.ci.style.transform = "";                  // springs back
  };
  document.addEventListener("touchend", end); document.addEventListener("touchcancel", end);
  document.addEventListener("click", e => {          // the tap that ends a drag isn't a tap on the card
    if (Date.now() - dragged < 400 && e.target.closest && e.target.closest("#cardBox")) { e.stopPropagation(); e.preventDefault(); }
  }, true); }
// 1.62.1: a tap on a plane or its label opens its card (as on the radar) over the picture; a tap elsewhere closes it.
function arTap(e){
  const r = $("arCv").getBoundingClientRect(), x = e.clientX - r.left, y = e.clientY - r.top;
  const hit = arHits.find(h => x >= h.box[0] && x <= h.box[0] + h.box[2] && y >= h.box[1] && y <= h.box[1] + h.box[3])
    || arHits.reduce((a, h) => { const d = Math.hypot(h.x - x, h.y - y); return d < 32 && (!a || d < a.d) ? {hex: h.hex, d} : a; }, null);
  const was = arSel;
  if (!hit && was) return arCardDismiss();           // 1.72.2: a tap on the sky slides the card away
  arSel = hit && hit.hex !== was ? hit.hex : "";
  arFull = !!arSel;                                  // a plane tapped: its whole card
  if (arSel || was) ctlSound.nav();
  arCardRender();
}
let arCardSig = "";
// 1.72.2: a lock-on opens the small card (the essentials, so the sky stays free); it goes by itself when the ring holds
// another plane, or none for AR_PEEK_MS. 1.72.3: swiped up it grows into the whole card under the finger (the
// thumbnail into the photo, the rest fading in); a plane tapped opens the whole card at once.
const AR_PEEK_MS = 3000;
let arFull = false, arAwayAt = 0, arP = 0;           // arP: 0 the small card, 1 the whole card, in between while dragged
function arPeekHtml(o){
  const ac = o.ac, info = (infoCache.get(ac.hex + "|" + String(ac.flight || "").trim().toUpperCase()) || enrich(ac)).info || baseInfo(ac);
  lookupDetails(ac.hex);
  const d = detailsOf(ac.hex) || {}, badge = badgeFor(liveFacts(ac, info)) || radarStatus(o);
  // 1.93: the thumbnail has no room for Planespotters' credit and link, so it shows the next photo (the whole card has theirs)
  const pic = planePic(ac, info, d, () => { if (arOn && arSel === ac.hex) { arCardSig = ""; arCardRender(); } }, true).src;
  const name = info.flightNo || String(ac.flight || "").trim() || ac.r || ac.hex.toUpperCase();
  const type = shortType(d.type || info.type || TYPES[String(ac.t || "").toUpperCase()] || ac.t || "");
  const sub = [o.alt != null ? altitudeStr(o.alt).toLowerCase() : "", o.dist != null ? `${o.dist < 10 ? o.dist.toFixed(1) : Math.round(o.dist)} km ${o.dir || ""}` : "", badge ? T(badge) : ""].filter(Boolean).join(" · ");
  const html = `<i class="arGrip"></i><div class="arPeek">${pic ? `<img class="arThumb" src="${escH(pic)}" alt="" referrerpolicy="no-referrer">` : `<span class="arThumb"></span>`}` +
    `<div class="arPeekT"><b>${escH([name, type].filter(Boolean).join(" · "))}</b><span>${escH(sub)}</span></div></div>` +
    `<p class="arSwipe"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 15l6-6 6 6" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"/></svg>${escH(T("Swipe up for more"))}</p>` +
    "";
  return {html, pic, sig: [ac.hex, pic, name, type, sub].join("|")};
}
function arCardRender(){
  const box = $("arCard"), ac = arSel && arList.find(a => a.hex === arSel);
  if (!ac) { box.hidden = true; $("arHint").hidden = false; $("arRib").hidden = false; arCardSig = ""; arP = 0; return; }
  if (box.classList.contains("drag") || box.classList.contains("anim")) return;   // not under the finger
  const o = radar.planes.find(p => p.ac.hex === arSel) || {ac, alt: typeof ac.alt_baro === "number" ? ac.alt_baro : null};
  const pk = arPeekHtml(o), b = planeBody(o, true), sig = pk.sig + "|" + b.sig;
  $("arHint").hidden = true; $("arRib").hidden = true;   // 1.90: the ribbon goes with the hint
  if (sig === arCardSig && !box.hidden) {
    for (const el of box.querySelectorAll("[data-dyn]")) if (el.textContent !== b.dyn[el.dataset.dyn]) el.textContent = b.dyn[el.dataset.dyn];
    return;
  }
  arCardSig = sig;
  box.innerHTML = `<div class="arL arPeekL">${pk.html}</div><div class="arL arFullL"><i class="arGrip"></i>${b.html}</div>` +
    (pk.pic ? `<img class="arGhost" src="${escH(pk.pic)}" alt="" referrerpolicy="no-referrer">` : "");
  box.hidden = false;
  b.wire(box.querySelector(".arFullL"));
  box.querySelector(".arPeekL").onclick = () => { if (!arP) { ctlSound.nav(); arTo(1); } };
  arSet(arFull ? 1 : 0);
  for (const im of box.querySelectorAll("img")) im.addEventListener("load", () => { if (!box.classList.contains("drag")) arSet(arP); }, {once: true});
}
// Lays the card out at p (0 small, 1 whole): its height, the two layers' fades, and the thumbnail on its way to the photo.
function arSet(p){
  const box = $("arCard"), pk = box.querySelector(".arPeekL"), fl = box.querySelector(".arFullL");
  if (!pk || !fl) return;
  arP = p = Math.max(0, Math.min(1, p));
  const PH = pk.offsetHeight, FH = Math.max(PH, Math.min(fl.offsetHeight, arRoom()));
  box.style.height = (PH + (FH - PH) * p).toFixed(1) + "px";
  box.style.overflowY = p >= 1 ? "auto" : "hidden";
  if (p >= 1) { const more = box.scrollHeight - box.clientHeight; if (more > 0) box.style.height = Math.min(arRoom(), FH + more + 2) + "px"; }   // margins and borders too
  if (p < 1) box.scrollTop = 0;
  pk.style.opacity = Math.max(0, 1 - p * 2.5).toFixed(3); pk.style.pointerEvents = p > .4 ? "none" : "";
  fl.style.opacity = Math.max(0, (p - .45) / .55).toFixed(3); fl.style.pointerEvents = p >= 1 ? "" : "none";
  const th = pk.querySelector("img.arThumb"), ph = fl.querySelector(".cPicW"), gh = box.querySelector(".arGhost");
  if (ph) ph.style.visibility = p >= 1 || !gh ? "" : "hidden";
  if (th) th.style.visibility = p > 0 && gh ? "hidden" : "";
  if (gh && th && ph) {
    const a = {l: th.offsetLeft + pk.offsetLeft, t: th.offsetTop + pk.offsetTop, w: th.offsetWidth, h: th.offsetHeight};
    const z = {l: ph.offsetLeft + fl.offsetLeft, t: ph.offsetTop + fl.offsetTop, w: ph.offsetWidth, h: ph.querySelector("img") ? ph.querySelector("img").offsetHeight : ph.offsetHeight};
    const m = (x, y) => (x + (y - x) * p).toFixed(1) + "px";
    Object.assign(gh.style, {display: p > 0 && p < 1 ? "block" : "none", left: m(a.l, z.l), top: m(a.t, z.t), width: m(a.w, z.w), height: m(a.h, z.h)});
  }
  arFull = p >= 1;
}
// 1.72.5: the whole card may take the screen up to Sky view's top bar, so it shows everything without scrolling.
function arRoom(){
  const top = document.querySelector("#arView .arTop"), box = $("arCard");
  const b = box.getBoundingClientRect(), t = top ? top.getBoundingClientRect().bottom : 60;
  return Math.max(220, b.bottom - t - 12);
}
// Eases the card to the small or the whole one (after a release, a tap).
function arTo(p){
  const box = $("arCard");
  box.classList.add("anim"); arSet(p);
  clearTimeout(arTo.t); arTo.t = setTimeout(() => { box.classList.remove("anim"); arSet(p); arAwayAt = 0; }, 320);
}
// Called every frame from arAimDraw: the small card goes when the ring holds another plane, or none for AR_PEEK_MS.
function arPeekWatch(hex){
  const box = $("arCard");
  if (!arSel || arP > 0 || box.hidden || box.classList.contains("drag")) { arAwayAt = 0; return; }
  if (hex === arSel) { arAwayAt = 0; return; }
  if (hex) return arCardDismiss();
  const now = Date.now();
  if (!arAwayAt) arAwayAt = now;
  const left = 1 - (now - arAwayAt) / AR_PEEK_MS;
  if (left <= 0) { arAwayAt = 0; arCardDismiss(); }
}
// The card slides away (a drag down, a tap on the sky, the timer).
function arCardDismiss(){
  const box = $("arCard");
  if (box.hidden || box.classList.contains("out")) return;
  ctlSound.click();
  box.classList.remove("drag", "anim"); box.style.transform = ""; box.classList.add("out");
  const was = arSel;
  setTimeout(() => { box.classList.remove("out"); if (arSel === was) { arSel = ""; arFull = false; } arCardSig = ""; arCardRender(); }, 260);   // a new lock-on meanwhile keeps its card
}
// The finger: up on the small card grows it (released past 30 %, or flicked up, it opens; else it shrinks back); down
// on the small card puts it away; down on the whole card shrinks it back to the small one, or further puts it away.
{ const box = $("arCard"); let drag = null, dragged = 0;
  const start = y => { drag = {y0: y, p0: arP, on: false, top: box.scrollTop <= 0, dy: 0, v: 0, lt: performance.now(), ly: y}; };
  const move = (y, e) => {
    if (!drag) return;
    const dy = y - drag.y0;
    if (!drag.on) {
      if (Math.abs(dy) < 6) return;
      if (drag.p0 >= 1 && (dy < 0 || !drag.top)) { drag = null; return; }   // the whole card scrolls
      drag.on = true; drag.y0 = y; box.classList.add("drag"); arAwayAt = 0;
    }
    if (e.cancelable) e.preventDefault();
    const now = performance.now(); drag.v = (y - drag.ly) / Math.max(1, now - drag.lt); drag.ly = y; drag.lt = now;
    const d = drag.dy = y - drag.y0, pk = box.querySelector(".arPeekL"), fl = box.querySelector(".arFullL");
    const span = Math.max(1, Math.max(pk.offsetHeight, Math.min(fl.offsetHeight, arRoom())) - pk.offsetHeight);
    const p = drag.p0 - d / span;
    if (p >= 0) { arSet(Math.min(1, p)); box.style.transform = p > 1 ? `translateY(${(-(p - 1) * span / 6).toFixed(1)}px)` : ""; }
    else { arSet(0); box.style.transform = `translateY(${(-p * span).toFixed(1)}px)`; }   // below the small card: on its way out
  };
  const end = () => {
    const d = drag; drag = null;
    if (!d || !d.on) return;
    dragged = Date.now();                            // the tap that ends a drag isn't a tap on the card
    box.classList.remove("drag");
    const over = parseFloat((box.style.transform.match(/translateY\(([-\d.]+)px/) || [])[1] || 0);
    if (over > 50 || (arP === 0 && d.v > .5 && d.dy > 0)) return arCardDismiss();
    box.style.transform = "";
    if (d.p0 < 1) arTo(arP > .3 || d.v < -.5 ? 1 : 0);
    else arTo(arP < .7 || d.v > .5 ? 0 : 1);
  };
  box.addEventListener("click", e => { if (Date.now() - dragged < 400) { e.stopPropagation(); e.preventDefault(); } }, true);
  box.addEventListener("dragstart", e => e.preventDefault());   // the photo isn't picked up, the card is
  box.addEventListener("touchstart", e => start(e.touches[0].clientY), {passive: true});
  box.addEventListener("touchmove", e => move(e.touches[0].clientY, e), {passive: false});
  box.addEventListener("touchend", end); box.addEventListener("touchcancel", end);
  box.addEventListener("pointerdown", e => { if (e.pointerType === "mouse") start(e.clientY); });
  box.addEventListener("pointermove", e => { if (e.pointerType === "mouse") move(e.clientY, e); });
  box.addEventListener("pointerup", e => { if (e.pointerType === "mouse") end(); }); }
setInterval(() => { if (arOn && arSel) arCardRender(); }, 1000);
$("arBtn").onclick = arTry;
// 1.72.4: Sky view can always be opened: when the plane's Where to look card (with its button) isn't there, a row of
// its own under the board takes its place.
$("arBtn2").onclick = arTry;
$("skyCv").onclick = e => { if ($("lookCv").onclick) $("lookCv").onclick(e); };   // a tap lets the tape turn with the phone
// 1.77: Sky view shows the planes around you, so it comes with live location (the app following the phone). With it
// off, a card asks first: go live and open, or not now.
function arTry(){
  if (S.live || S.demo || !liveOk()) return arOpen(true);
  ctlSound.click();
  cardOpen(`<div class="cHead"><div><h3>${escH(T("Sky view needs live location"))}</h3></div></div>` +
    `<p class="note">${escH(T("It shows the planes around you, wherever you are, so the app follows your location while it's open."))}</p>` +
    `<div class="liveAsk"><button class="liveGo" type="button">${escH(T("Go live and open"))}</button><button class="liveNo" type="button">${escH(T("Not now"))}</button></div>`,
    box => { box.querySelector(".liveGo").onclick = arGoLive; box.querySelector(".liveNo").onclick = () => { ctlSound.click(); cardClose(); }; });
}
async function arGoLive(){
  ctlSound.click(); cardClose();
  // iPhones let a page ask for the motion sensors only straight from a tap: asked now, before waiting for the location
  try { if (typeof DeviceOrientationEvent.requestPermission === "function") await DeviceOrientationEvent.requestPermission(); } catch {}
  gGoLive();
  const t0 = Date.now(), wait = setInterval(() => {
    if (S.live && !liveFirst) { clearInterval(wait); arOpen(); }
    else if (!S.live || Date.now() - t0 > 15000) {
      clearInterval(wait); lookErr = T("Couldn't find where you are, so Sky view stays closed."); lookErrAt = Date.now(); lookSoon();
    }
  }, 300);
}
// 1.77: in the Where to look card's style, its tape a compass; with no plane on top it says so.
function skyRowRender(){
  const look = !$("look").hidden && !$("acSec").hidden && !$("arBtn").hidden, box = $("skyRow");
  box.hidden = look || !arPossible() || SIDEWAYS.matches;
  if (box.hidden) return;
  const wait = liveWaiting(), on = lookOn && lookHeading != null, sig = (wait ? "w" : feat ? "f" : "n") + LANG;
  drawTape($("skyCv"), on ? lookHeading : 0, on, null);
  if (box.dataset.sig === sig) return;
  box.dataset.sig = sig;
  $("skyB").textContent = T(feat || wait ? "Sky view" : "No planes around right now");   // 1.90: live location finding you: says so
  $("skySub").textContent = wait ? T("Finding where you are … the planes show once live location has found you.")
    : T(feat ? "Hold your phone up to the sky to see every plane around you." : "Sky view shows the ones farther off too, up to 60 km.");
}
setInterval(skyRowRender, 1000);
$("arClose").onclick = arClose;
$("arShut").onclick = arSnap;
$("arReset").onclick = () => { ctlSound.click(); arOff = {h: 0, p: 0, v: 2}; arAutoFinds = []; arAutoLock = null; $("arMoved").hidden = true; try { localStorage.removeItem("od.ar.off"); } catch {}
  arHeldAt = 0; arGap = null; };                // 1.86: and north from the compass again, at once
$("arZ2").onclick = () => arZoomSet(2); $("arZ5").onclick = () => arZoomSet(5);
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

// Tap a plane on the radar (or a row of Nearest): it is ringed, and its card comes up from the bottom as a sheet, the one a
// plane gets anywhere else in the app (1.83.3; it was a card under the scope). The ring goes with the card.
$("radarCv").addEventListener("click", e => {
  if (Date.now() < pinch.quiet) return;                     // the end of a pinch
  const cv = $("radarCv"), r = cv.getBoundingClientRect(), x = (e.clientX - r.left) * RG.S / r.width, y = (e.clientY - r.top) * RG.S / r.height;
  const hit = (radar.hits || []).reduce((a, h) => { const d = Math.hypot(h.x - x, h.y - y); return d < 26 && (!a || d < a.d) ? {hex: h.hex, d} : a; }, null);
  const dbl = !hit && Date.now() - pinch.tapAt < 350 && Math.hypot(x - pinch.tapX, y - pinch.tapY) < 30;
  pinch.tapAt = dbl ? 0 : Date.now(); pinch.tapX = x; pinch.tapY = y;
  if (dbl) return radarZoomTo(radarZoomCan(1) ? 1 : -9);   // double tap: closer, from the closest back out
  if (hit) radarPlaneCard(hit.hex);
});
$("rvList").addEventListener("click", e => {
  const li = e.target.closest && e.target.closest("[data-hex]");
  if (li) radarPlaneCard(li.dataset.hex);
});
function radarPlaneCard(hex){
  const o = radar.planes.find(p => p.ac.hex === hex);
  if (!o) return;
  radar.sel = hex; rvSig = ""; renderRadarList();
  planeCard(o);
}
// Once a second on the radar: the open card's height, speed and distance keep up with its plane; once the card has gone
// (or the plane), so has the ring.
const radarSelOpen = () => cardOpenNow() && planeShown && planeShown.ac.hex === radar.sel;
setInterval(() => {
  if (tab !== "radar") return;
  $("rvHint").hidden = !radar.planes.length;
  if (!radar.sel) return;
  const o = radar.planes.find(p => p.ac.hex === radar.sel);
  if (!o || !radarSelOpen()) { radar.sel = ""; rvSig = ""; renderRadarList(); return; }
  const dyn = planeBody(o).dyn;
  for (const el of $("cardBox").querySelectorAll("[data-dyn]")) { const v = dyn[el.dataset.dyn]; if (v && el.textContent !== v) el.textContent = v; }
}, 1000);

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
//@L:radar
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
//@L:end
function startRadar(){
  radarSize(); buildRadarLegend();
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
  const g = $("radarCv").getContext("2d");
  g.setTransform(radar.px, 0, 0, radar.px, 0, 0); g.clearRect(0, 0, RG.S, RG.S);
  paintRadar(g, RG.cx, RG.cy, RG.R, 1, t);              // 1.68: the board's own drawing (E25), at the phone's size
}
function buildRadarLegend(){
  // 1.69: the Radar plate. The wheel shows the range to the rim (▲ wider, ▼ closer; also pinch and double-tap), the switch
  // the map. Off in the Airport style until the airport's place is known.
  const off = airportMode() && AP.lat == null, kmB = $("rvZoomKm"), txt = radarRangeText().replace(" km", "");
  $("rvWheel").classList.toggle("off", off); $("rvWheel").setAttribute("aria-valuetext", radarRangeText());
  if (kmB.textContent !== txt) kmB.textContent = txt;
  $("rvZoomOut").disabled = off || !radarZoomCan(-1); $("rvZoomIn").disabled = off || !radarZoomCan(1);
  $("rvReset").disabled = off || !radarZoom; $("rvReset").setAttribute("aria-label", T("Back to the usual range"));
  $("rvZoomOut").setAttribute("aria-label", T("Zoom out")); $("rvZoomIn").setAttribute("aria-label", T("Zoom in"));
  $("rvMap").setAttribute("aria-pressed", String(radarMapOn));
  const cr = $("rvCredit"); cr.textContent = RADAR_MAP_CREDIT; cr.hidden = !radarMapOn;
  $("rLegend").innerHTML = radarLegend().map(([c, t]) => `<li><i style="--c:${c}"></i>${escH(T(t))}</li>`).join("");
}
let rvSig = "";
function renderRadarList(){
  if (tab !== "radar") return;
  const range = +S.radiusKm || 15;
  const rows = radarRows(12).map(({o, dist, dir, st}) => {
    const info = radarInfo(o), name = radarName(o);
    const code = airlineCodeOf(info), L = code ? logo(code, true) : null, g = o.ac.alt_baro === "ground" ? gateFor(info) : "";
    const lg = L && L.state === "ok" ? `<img src="${escH(L.img.src)}" alt="">` : code ? escH(code) : "";
    return `<li class="rv${radar.sel === o.ac.hex ? " sel" : ""}" data-hex="${escH(o.ac.hex)}" style="--lamp:${radarColor(o)}"><span class="rvLogo${L && L.state === "ok" ? " ok" : ""}">${lg}</span><strong>${escH(name)}<span>${escH(String(o.ac.t || ""))}</span></strong>` +
      `<span class="num">${distText(dist)} ${dir}</span><span class="num">${escH(altShort(o.alt))}</span>${chip(st, g && (st ? g : T("GATE {g}", {g})))}</li>`;   // 1.65: with its gate while on the ground
  });
  const html = rows.length ? rows.join("") : `<li class="empty">${escH(T("No planes within {n} km right now.", {n: range}))}</li>`;
  if (html !== rvSig) { rvSig = html; $("rvList").innerHTML = html; }
}

/* ---------- settings: the cockpit plates, stacked for a phone ---------- */
//@L:cockpit
const COCKPIT_FOR = "phone";         // the board's shared Settings (COCKPIT, copied in below) as a phone shows them
//@L:end
// Inside the Android app (android/ in the repository) the page runs in a WebView that offers OverheadAndroid.
const ANDROID = !!(window.OverheadAndroid && window.OverheadAndroid.changeRelay);
if (ANDROID) document.documentElement.classList.add("android");     // 1.69: the app pads the page clear of the phone's bars itself
const APK_URL = "https://github.com/Belstria/overhead-board/releases/latest/download/overhead.apk";
// 1.63.2: the Android app signed in over the Wi-Fi moves to the relay's https address, where TLS proves it's this relay
// (and it works away from home too). At most once a day, so a missing internet connection doesn't loop.
function androidHandover(){
  if (!ANDROID || !window.OverheadAndroid.usePublic || location.protocol !== "http:" || (window.OVERHEAD_RELAY_VERSION || 0) < 54) return;
  try { if (Date.now() - (+localStorage.getItem("od.handover") || 0) < 864e5) return; localStorage.setItem("od.handover", Date.now()); } catch { return; }
  fetch("/handover", {method: "POST"}).then(r => r.ok ? r.json() : null)
    .then(j => { if (j && j.link) window.OverheadAndroid.usePublic(j.link); }).catch(() => {});
}
setTimeout(androidHandover, 4000);
/* 1.97.5: the phone's back gesture (or button). The app (MainActivity) asks the page first: this closes the top layer
   and answers true, or answers false on Now with nothing open, and the app then goes to the background. Quietly:
   back is the system's, so the closings play none of the controls' sounds.
   1.97.7: `backStep()` picks the closing (without doing it) and is shared with the web app's history guard below. */
function backStep(){
  const shown = el => !!el && !el.hidden && el.getClientRects().length > 0;
  if (shown($("welcome"))) return null;                                    // the welcome has no step to go back to
  for (const id of ["medalMo", "gLvUp"]) if (shown($(id))) return () => $(id).click();   // a pop-up: as a tap on it
  const tipL = $("tipLayer");
  if (shown(tipL) && !tipL.style.pointerEvents) return () => tipL.click();      // a first-time tip: "Got it"
  if (cardOpenNow()) return cardClose;                                     // a card or sheet, also over Sky view
  if (arOn) {
    if (shown($("arTour"))) return () => arTour(AR_TOUR.length);           // the walkthrough: skipped
    if (shown($("arCard")) && !$("arCard").classList.contains("out")) return arCardDismiss;
    return arClose;                                                        // Sky view: back to the board
  }
  if (shown($("t-log"))) return logHide;
  if (shown($("t-about"))) return aboutHide;
  if (shown($("t-styles"))) return stylesHide;
  const row = [...document.querySelectorAll(".tline li.fl.open")].find(li => li.getClientRects().length);
  if (row) return () => tlFold(row, true);                                 // a plane opened in place in a list: folded
  if (tab !== "now") return () => showTab("now");
  return null;
}
function backQuiet(step){
  const keep = {};
  for (const k of Object.keys(ctlSound)) if (typeof ctlSound[k] === "function") { keep[k] = ctlSound[k]; ctlSound[k] = () => {}; }
  try { step(); } finally { Object.assign(ctlSound, keep); }
}
function fallblattBack(){
  const step = backStep();
  if (!step) return false;
  backQuiet(step);
  return true;
}
if (ANDROID) window.fallblattBack = fallblattBack;
/* 1.97.7: back in a browser and in an installed web app. The page keeps ONE extra history entry (the guard, state
   {fbGuard}) while anything is open or another tab than Now shows; none on Now with nothing open, so that back leaves as
   usual. Back onto the entry below the guard (popstate) runs the same step as the Android app (`backStep`); if something
   is still open the guard is pushed again. Closing by hand (x, a tap) leaves the guard behind: `guardSync` (every 200 ms
   and after each back) then takes it away with history.back(), its own popstate ignored (`guardSelf`), so the next back
   is never a dead one. showTab only replaces the URL (the hash) of the entry it is on, so tab switches never pile up.
   The entry below keeps the URL it had, so after a back (the user's or our own) its hash is put right (replaceState)
   before hashchange runs.
   Not in the Android app (its own back handler does this). */
let guardOn = !ANDROID && !!(history.state && history.state.fbGuard);   // after a reload the guard may still be there
let guardSelf = false;
function tabHash(){ return tab === "now" ? "" : "#" + tab; }
function guardSync(){
  if (ANDROID || guardSelf || document.hidden) return;
  const need = !!backStep();
  if (need && !guardOn) {
    guardOn = true;
    history.pushState({fbGuard: 1}, "", location.pathname + location.search + tabHash());
  } else if (!need && guardOn) {
    guardOn = false; guardSelf = true;
    setTimeout(() => { guardSelf = false; }, 600);      // in case the browser never answers
    history.back();
  }
}
if (!ANDROID) {
  addEventListener("popstate", e => {
    if (guardSelf) {                                                      // our own history.back(): the entry below may
      guardSelf = false;                                                  // still hold the tab it had (#today), so put the
      history.replaceState(null, "", location.pathname + location.search + tabHash());   // URL right before hashchange
      return;                                                             // runs (1.101.0.1: Now went back to that tab)
    }
    if (e.state && e.state.fbGuard) { guardOn = true; return; }           // forward onto the guard again
    if (!guardOn) return;                                                 // not ours (a typed hash, ...)
    guardOn = false;
    const step = backStep();
    if (!step) { history.back(); return; }                                // stale guard, nothing open: pass through
    backQuiet(step);
    history.replaceState(null, "", location.pathname + location.search + tabHash());
    guardSync();
  });
  setInterval(guardSync, 200);
}
//@E29
//@E32
/* Airport style on the phone: on Now, the plane taking off or landing right now on the flaps with its photo and details,
   then the take-offs and the landings as lists (in place of Recent flights). */
let apSig = "";
function renderAirport(){
  if (tab !== "now" || !airportMode()) return;
  const sub = !AP.code ? T("Set the home airport in Settings.") : AP.lat == null ? T("Looking up {code} …", {code: AP.code}) :
    AP.rwyLine ? AP.rwyLine + "." : "";
  const row = e => [e.t, apFlight(e), apPlace(e), e.st].join("|");
  const sig = [sub, AP.lat != null, AP.deps.map(row).join("~"), AP.arrs.map(row).join("~")].join("#");
  if (sig === apSig) return;
  apSig = sig;
  $("apSub").textContent = sub; $("apSub").hidden = !sub;
  for (const [k, list] of [["d", AP.deps], ["a", AP.arrs]]) for (let i = 0; i < AP_ROWS; i++) {   // upright
    const e = list[i], id = c => `nu${k}${i}${c}`, d = i * 60;
    setChars(id("time"), e && e.t ? hhmm(new Date(e.t)) : "", d);
    setChars(id("flight"), e ? apFlight(e) : "", d + 20);
    setChars(id("city"), e ? apPlace(e) : "", d + 60);
    setWord(id("st"), e ? e.st : i === 0 && AP.lat != null ? "NO TRAFFIC" : "", d + 100);
  }
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
  document.documentElement.style.setProperty("--swFav", JSON.stringify(T("Favourite")));
  document.documentElement.style.setProperty("--swHide", JSON.stringify(T("Hide")));
  for (const el of document.querySelectorAll("[data-t]")) el.textContent = T(el.dataset.t);
  buildTabs(); buildSvTools(); buildRadarLegend();
  if (tab) showTab(tab);
  clearTiles(); refreshPanels(true);
}
// Overhead and Airport in the title: tap one to switch.
function setMode(md){
  if (S.mode === md) return;
  ctlSound.click(); audioInit();                     // 1.97.4: the title is a button, so the button click
  S.mode = md; saveSettings();
  if (tab !== "now") showTab("now"); else applyMode();
  showModes();
  poll(true);                                       // the new style picks its plane from fresh positions
  setTimeout(() => appTips("now"), 900);            // the first time in this style: its pages
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
  const up = tab === "now" && !SIDEWAYS.matches && ap;
  for (const [P, show] of [[RECENTP, lists && !ap], [APP, lists && ap], [ACP, on && isAcPage(nowPage) && !!feat], [APDP, up], [APAP, up]])
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
  return `<div class="plate${p.cls ? " " + p.cls : ""}" data-pid="${p.id}" style="--cols:${p.cols || 2}"><i></i><i></i><i></i><i></i><h3>${escH(T(p.title))}</h3>${p.items.map(itemHtml).join("")}</div>`;
}
function cockpitOpen(){
  draft = cockpitDraft();
  const box = $("cockpit");
  box.innerHTML = PLATES.map(plateHtml).join("");
  $("aboutX").onclick = () => { ctlSound.click(); aboutHide(); };
  $("t-about").querySelector(".tabHead h2").onclick = () => aboutTap();       // 1.49: seven taps on About
  $("aboutX").setAttribute("aria-label", T("Close"));
  wireCockpit(box);
  cockpitShow();
  renderAbout();
  syncShow();
}
// The phone: Save and Cancel stay in Settings, with the controls back as saved; Save says Saved for a moment. The bar
// lights up while there is something to save.
let savedTimer = 0;
function cockpitDone(saved){
  cockpitOpen();
  if (!saved) return;
  const b = $("saveBtn");
  b.textContent = T("Saved"); clearTimeout(savedTimer);
  savedTimer = setTimeout(() => { b.textContent = T("Save"); }, 1600);
}
function cockpitMark(dirty){
  $("saveBtn").setAttribute("aria-pressed", String(dirty));
  $("t-settings").classList.toggle("dirty", dirty);
}
function buildSaveBar(){
  $("saveBtn").onclick = () => { ctlSound.press(); cockpitSave(); };
  $("cancelBtn").onclick = () => { ctlSound.press(); cockpitCancel(); };
}
/* About: a page of its own, opened from Settings. The version and patch notes are the board's (test). */
function aboutOpen(){
  const screws = "<i></i><i></i><i></i><i></i>";
  $("aboutBox").innerHTML =
    `<div class="plate relayP" style="--cols:1" id="relayPlate" hidden>${screws}<h3>${T("Relay")}</h3><p class="owner" id="relaySub"></p><div class="lgbox" id="relayBox"></div></div>` +
    `<div class="plate" style="--cols:1">${screws}<h3>${T("About")}</h3><p class="ver" id="aboutVer"></p><p id="aboutStatus"></p>` +
    `<p class="cBtns"><button class="cBtn" type="button" id="aboutLog">${escH(T("Log"))}</button></p>` +
    (GUEST ? `<p><b>${escH(T("Signed in as {name}.", {name: GUEST.name}))}</b> ${escH(T("Your location, Spotted today and logbook are your own, and this device remembers you."))}</p>` +
        `<p>${escH(T("To keep it like an app: on Android, Chrome's menu → Add to home screen; on an iPhone, Safari → Share → Add to Home Screen."))}</p>` +
        `<p>${siteLinks(escH(T("Privacy: the relay keeps your name, the devices you joined on, your settings and the planes spotted around your location, nothing else. Flight positions come from adsb.lol, adsb.fi and airplanes.live (ODbL) and AvioADSB (CC BY 4.0), routes and aircraft from adsbdb, photos from Planespotters.net and airport-data.com.")))}</p>`
    : (ANDROID ? `<p>${escH(T("The Fallblatt app for Android, showing the relay at {host}.", {host: location.host}))}</p>`
      : `<p>${escH(T("On Android, install the Fallblatt app and open the file (allow installs from your browser once):"))} <a href="${APK_URL}">${T("download it")}</a>. ` +
        `${escH(T("On an iPhone, Safari → Share → Add to Home Screen."))}</p>`)) +
    aboutHtml() + `</div>` +
    `<div class="plate" style="--cols:1">${screws}<h3>${T("Legend")}</h3><div class="lgbox">${legendHtml()}</div></div>` +
    `<div class="plate" style="--cols:1">${screws}<h3>${T("Patch notes")}</h3><div class="log">${changelogHtml()}</div></div>` +
    `<div class="acts"><button class="cap big" type="button" id="aboutBack">${T("Settings")}</button></div>`;
  $("aboutBack").onclick = () => { ctlSound.press(); showTab("settings"); };
  $("aboutLog").onclick = () => { ctlSound.click(); logShow(); };
  renderAbout();
  relayLoad();
}
/* 1.88 (Dave's pick 13 A): the owner's Relay plate at the top of About: the position sources, Flightradar24, the
   nightly backup and the screens online, from the relay's /relayinfo (69+), which answers only the owner. */
let relayTimer = 0;
async function relayLoad(){
  clearTimeout(relayTimer);
  if ((window.OVERHEAD_RELAY_VERSION || 0) < 69 || !relay() || !(GUEST && GUEST.owner) || $("t-about").hidden) return;
  const d = await fetch(`${relay()}/relayinfo`).then(r => r.ok ? r.json() : null).catch(() => null);
  if (!d || !$("relayPlate")) return;
  relayPlate(d);
  relayTimer = setTimeout(relayLoad, 30000);
}
function relayPlate(d){
  const G = "var(--c-good)", A = "var(--amber)", R = "var(--c-bad)", N = "var(--label2)";
  const row = (lamp, name, n, sub = "", pct = null) => `<li style="--lamp:${lamp}"><i class="lamp"></i><span class="name">${escH(name)}${sub ? `<span class="s">${escH(sub)}</span>` : ""}</span><span class="n">${escH(n)}</span>` +
    (pct != null ? `<span class="bar"><i style="width:${Math.min(100, Math.max(0, pct)).toFixed(1)}%;opacity:1"></i></span>` : "") + `</li>`;
  const list = rows => `<ol class="ranks cats">${rows}</ol>`;
  const span = s => s < 3600 ? T("{n} min", {n: Math.max(1, Math.round(s / 60))}) : s < 172800 ? T("{n} h", {n: Math.floor(s / 3600)}) : T("{n} days", {n: Math.floor(s / 86400)});
  const ago = s => s < 120 ? T("{n} s ago", {n: s}) : T("{n} min ago", {n: Math.round(s / 60)});
  const when = t => { const d = new Date(t * 1000);
    return Date.now() - d < 864e5 ? T("Last night, {t}", {t: hhmm(d)}) : d.toLocaleString(LOC(), {day: "numeric", month: "short", hour: "2-digit", minute: "2-digit"}); };
  const ROLE = {first: "first", reserve: "in reserve", emergency: "emergencies only"};
  const sources = d.sources.map(s => {
    const role = T(ROLE[s.role]);
    if (s.state === "resting") return row(A, s.name, T("resting"), role + " · " + T("until {t}", {t: hhmm(new Date(s.until * 1000))}) + (s.http ? " · HTTP " + s.http : ""));
    if (s.state === "failing") return row(R, s.name, T("failing"), role + (s.http ? " · HTTP " + s.http : ""));
    if (s.allow) return row(s.state === "ok" ? G : N, s.name, `${nf.format(s.today)} / ${nf.format(s.allow)}`, role + " · " + T("today"), s.today / s.allow * 100);
    if (s.state === "ok") return row(G, s.name, T("working"), role + (s.okAge != null ? " · " + ago(s.okAge) : ""));
    return row(N, s.name, T("standby"), role);
  }).join("");
  const f = d.fr24;
  const fr24 = !f.on ? row(N, T("Off"), "", T("no key on the relay")) :
    row(A, T("This month"), `${nf.format(f.credits)} / ${nf.format(f.budget)}`, T("credits"), f.credits / f.budget * 100) +
    row(A, T("Today"), nf.format(f.creditsToday), T("credits") + " · " + T(f.lookupsToday === 1 ? "1 lookup" : "{n} lookups", {n: nf.format(f.lookupsToday)})) +
    row(A, T("Gap filler"), nf.format(f.fill), T("this month") + " · " + (f.credits ? Math.round(f.fill / f.credits * 100) : 0) + " %", f.credits ? f.fill / f.credits * 100 : 0);
  const b = d.backup, size = b && b.bytes != null ? (b.bytes >= 1e9 ? (b.bytes / 1e9).toFixed(1) + " GB" : (b.bytes / 1e6).toFixed(1) + " MB") : "";
  const kept = b && b.kept != null ? T(b.kept === 1 ? "1 copy kept" : "{n} copies kept", {n: b.kept}) : "";
  const backup = !b ? row(A, T("No backup reported"), "", T("nothing from the backup job yet")) :
    !b.ok ? row(R, T("Failed"), "", [when(b.t), b.error].filter(Boolean).join(" · ")) :
    b.late ? row(A, when(b.t), size, T("over 36 hours ago")) : row(G, when(b.t), size, kept);
  const screens = d.screens.map(s => { const quiet = s.hidden || s.quiet > 60;
    return row(quiet ? A : G, [s.who, s.device].filter(Boolean).join(" · "), T(s.kind === "app" ? "app" : "board"),
      s.hidden ? T("in the background") : quiet ? T("quiet {t}", {t: span(s.quiet)}) : s.on < 60 ? T("now") : T("on {t}", {t: span(s.on)})); }).join("")
    || row(N, T("None right now"), "");
  $("relaySub").textContent = T("Only you see this · relay {v} · up {t}", {v: d.version, t: span(d.up)});
  $("relayBox").innerHTML = `<h3>${escH(T("Position sources"))}</h3>${list(sources)}<h3>Flightradar24</h3>${list(fr24)}` +
    `<h3>${escH(T("Nightly backup"))}</h3>${list(backup)}<h3>${escH(T("Screens online · {n}", {n: d.screens.length}))}</h3>${list(screens)}`;
  $("relayPlate").hidden = false;
}
/* 1.80 (Dave's to-do 13, his pick B): the log as a page of its own, Settings → About → Log (or Log in the connection
   card), filtered to problems, Sky view or the network, with Copy so it can be pasted into a message. */
const LOG_FILTERS = [["all", "All"], ["bad", "Problems"], ["sky", "Sky view"], ["net", "Network"]];
let logFilter = "all", logRaf = 0;
const logHits = e => logFilter === "all" || (logFilter === "bad" ? e.level === "warn" || e.level === "error" : e.kind === logFilter);
const logTime = t => new Date(t).toLocaleTimeString("en-GB");
function logShow(){
  const box = $("logBox");
  box.innerHTML = `<div class="seg logSeg" role="group">` + LOG_FILTERS.map(([k, l]) => `<button type="button" data-lf="${k}" aria-pressed="${logFilter === k}">${escH(T(l))}</button>`).join("") + `</div>` +
    `<div class="logBar"><button class="cBtn" type="button" id="logCopy">${escH(T("Copy the log"))}</button><span id="logN"></span></div>` +
    `<ol class="logList" id="logList"></ol><p class="sum" id="logNone" hidden></p><textarea id="logText" aria-hidden="true" tabindex="-1"></textarea>`;
  for (const b of box.querySelectorAll("[data-lf]")) b.onclick = () => {
    ctlSound.click(); logFilter = b.dataset.lf;
    for (const x of box.querySelectorAll("[data-lf]")) x.setAttribute("aria-pressed", String(x === b));
    logRender();
  };
  $("logCopy").onclick = logCopy;
  $("t-log").hidden = false; $("t-log").scrollTop = 0; DIAG.page = true;
  document.body.classList.add("aboutOpen");
  logRender();
}
function logHide(){
  if ($("t-log").hidden) return;
  $("t-log").hidden = true; DIAG.page = false;
  if ($("t-about").hidden) document.body.classList.remove("aboutOpen");
}
function logSoon(){ if (!logRaf) logRaf = requestAnimationFrame(() => { logRaf = 0; logRender(); }); }
function logRender(){
  const list = $("logList");
  if (!list || $("t-log").hidden) return;
  const lines = DIAG.log.filter(logHits);
  list.innerHTML = lines.map(e => `<li data-l="${escH(e.level)}"><time>${logTime(e.t)}</time><i></i><span>${escH(e.msg)}</span></li>`).join("");
  $("logNone").hidden = !!lines.length;
  $("logNone").textContent = T(logFilter === "bad" ? "No problems logged." : "Nothing logged yet.");
  $("logN").textContent = T(lines.length === 1 ? "1 line" : "{n} lines", {n: lines.length});
}
function logText(){
  const lines = DIAG.log.filter(logHits).map(e => `${logTime(e.t)}  ${e.level.padEnd(5)}  ${e.msg}`).join("\n");
  return `Fallblatt log${logFilter === "all" ? "" : " (" + LOG_FILTERS.find(f => f[0] === logFilter)[1] + ")"} · ${new Date().toString()}\n` +
    `${versionLine()} · relay ${window.OVERHEAD_RELAY_VERSION || "–"}\n${navigator.userAgent}\n${statusLine()}\n\n${lines || "Nothing logged."}\n`;
}
async function logCopy(){
  ctlSound.click();
  const text = logText(), btn = $("logCopy");
  let ok = false;
  try { if (navigator.clipboard && window.isSecureContext) { await navigator.clipboard.writeText(text); ok = true; } } catch {}
  if (!ok) { const ta = $("logText"); ta.value = text; ta.focus(); ta.select(); try { ok = document.execCommand("copy"); } catch {} }
  btn.textContent = T(ok ? "Copied" : "Couldn't copy");
  setTimeout(() => { btn.textContent = T("Copy the log"); }, 2000);
}
$("logX").onclick = () => { ctlSound.click(); logHide(); };
$("stylesX").onclick = () => { ctlSound.click(); stylesHide(); };
$("stylesX").setAttribute("aria-label", T("Close"));
addEventListener("keydown", e => { if (e.key === "Escape" && !$("t-log").hidden && !cardOpenNow()) { e.stopImmediatePropagation(); logHide(); } }, true);
// Under Settings' plates: the account, notifications, this device and About (1.56: the shared VIEW_PLATES).
function settingsExtra(){
  const box = $("setExtra");
  if (!box) return;
  box.innerHTML = VIEW_PLATES.map(plateHtml).join("");
  wireViews(box);
}
/* 1.88 (Dave's pick 11 A): Settings' plates by name in a bar under the header, the app's segmented style. It scrolls
   sideways; a name scrolls to its plate; the plate on screen is lit while Settings scrolls, its name kept in view.
   The names are the cockpit's (per target, translated); Favourites & hidden is Favourites there. */
const jumpPlates = () => [...document.querySelectorAll("#cockpit > .plate, #favBox:not([hidden]) > .plate, #setExtra > .plate")].filter(p => p.getClientRects().length);
const jumpName = id => id === "favs" ? T("Favourites") : T((PLATES.find(p => p.id === id) || VIEW_PLATES.find(p => p.id === id) || {title: id}).title);
let jumpOn = "", jumpHold = null;
function jumpBuild(){
  const bar = $("setJump"), seg = $("setJumpSeg");
  if (!bar || tab !== "settings") return;
  const ids = jumpPlates().map(p => p.dataset.pid);
  if (seg.dataset.ids !== ids.join() + LANG) {
    seg.dataset.ids = ids.join() + LANG;
    seg.innerHTML = ids.map(id => `<button type="button" data-jump="${id}" aria-pressed="false">${escH(jumpName(id))}</button>`).join("");
    for (const b of seg.children) b.onclick = () => { ctlSound.nav(); jumpGo(b.dataset.jump); };
    seg.setAttribute("aria-label", T("Jump to"));
    jumpOn = "";
  }
  bar.hidden = ids.length < 2;
  jumpSpy();
}
// A plate's top just under the header and the bar (the bar is stuck there once Settings has scrolled).
const jumpLine = () => $("top").offsetHeight + $("setJump").offsetHeight + 10;
function jumpGo(id){
  const p = document.querySelector(`#t-settings .plate[data-pid="${id}"]`);
  if (!p) return;
  jumpHold = id;
  jumpLight(id);
  scrollTo({top: Math.max(0, p.getBoundingClientRect().top + scrollY - jumpLine()), behavior: "smooth"});
}
function jumpSpy(){
  if (tab !== "settings" || $("setJump").hidden) return;
  if (jumpHold) return jumpLight(jumpHold);       // the name tapped stays lit (a plate near the end can't reach the top)
  const plates = jumpPlates(), line = jumpLine() + 14;
  if (!plates.length) return;
  let on = plates[0];
  for (const p of plates) if (p.getBoundingClientRect().top <= line) on = p;
  if (scrollY > 0 && innerHeight + scrollY >= document.documentElement.scrollHeight - 2) on = plates[plates.length - 1];   // the end: About
  jumpLight(on.dataset.pid);
}
function jumpLight(id){
  if (id === jumpOn) return;
  jumpOn = id;
  const seg = $("setJumpSeg");
  let lit = null;
  for (const b of seg.children) { const on = b.dataset.jump === id; b.setAttribute("aria-pressed", String(on)); if (on) lit = b; }
  if (lit) seg.scrollTo({left: lit.offsetLeft - (seg.clientWidth - lit.offsetWidth) / 2, behavior: "smooth"});
}
// The bar sticks under the header, whose height changes with the score strip and the text size.
const topSize = () => document.documentElement.style.setProperty("--topH", $("top").offsetHeight + "px");
if (window.ResizeObserver) new ResizeObserver(topSize).observe($("top")); else topSize();
let jumpRaf = 0;
addEventListener("scroll", () => { if (tab === "settings" && !jumpRaf) jumpRaf = requestAnimationFrame(() => { jumpRaf = 0; jumpSpy(); }); }, {passive: true});
for (const e of ["touchstart", "wheel", "keydown"]) addEventListener(e, () => { jumpHold = null; }, {passive: true, capture: true});   // until Settings is scrolled by hand
//@L:taps
$("hero").addEventListener("click", e => {
  if (!feat || !feat.o) return;
  const r = HERO.el.getBoundingClientRect(), x = (e.clientX - r.left) * HERO.w / r.width, y = (e.clientY - r.top) * HERO.h / r.height;
  const id = ["airline", "fromCode", "fromCity", "toCode", "toCity", "flight", "type", "tier", "reg", "remarks", "seen"].find(k => {
    const f = fields[k]; if (!f || f.x == null || f.hidden) return false;
    const w = f.kind === "chars" ? f.n * f.step : f.wordW || f.n * f.step;
    return x >= f.x - 3 && x <= f.x + w + 3 && y >= f.y - 3 && y <= f.y + f.ch + 3;
  });
  if (!id) return;
  const info = feat.info || baseInfo(feat.o.ac);
  if (id === "airline") airlineCard(liveFacts(feat.o.ac, info));
  else if (id === "fromCode" || id === "fromCity") placeCard(info.from);
  else if (id === "toCode" || id === "toCity") placeCard(info.to);
  else if (id === "type") typeCard({typeCode: feat.o.ac.t, type: info.type, desc: feat.o.ac.desc});
  else planeCard(feat.o);
});
for (const [P, k] of [[APDP, "d"], [APAP, "a"]]) P.el.addEventListener("click", e => {
  const r = P.el.getBoundingClientRect(), y = (e.clientY - r.top) * P.h / r.height, x = (e.clientX - r.left) * P.w / r.width;
  const i = Math.floor((y - 12) / 30), row = (k === "d" ? AP.deps : AP.arrs)[i];
  if (!row || i < 0) return;
  const city = fields[`nu${k}${i}city`], info = row.info || baseInfo(row.ac);
  if (x >= city.x && x <= city.x + city.n * city.step) return placeCard(k === "d" ? info.to : info.from);
  planeCard({ac: row.ac, alt: row.alt});
});
//@L:end
$("where").onclick = () => { if (placesRelay()) placesCard(); };
$("dot").onclick = statusCard;
$("rvMap").onclick = () => { radarMapSet(!radarMapOn); ctlSound.toggle(radarMapOn); buildRadarLegend(); };
for (const [id, d] of [["rvZoomOut", -1], ["rvZoomIn", 1]]) $(id).onclick = () => radarZoomTo(d);
$("rvReset").onclick = () => { ctlSound.click(); radarZoomTo(0); };
$("rvWheel").onkeydown = e => { const d = {ArrowUp: -1, ArrowRight: -1, ArrowDown: 1, ArrowLeft: 1}[e.key]; if (d) { e.preventDefault(); radarZoomTo(d); } };
// d: steps closer (+) or wider (-); 0 (1.82.2, the radar's ⟲; a push button beside the wheel since 1.83.2): back to the
// usual range for the radius, and the middle.
function radarZoomTo(d){
  const was = radarZoom;
  if (d) radarZoomStep(d); else radarZoomSet(0);
  if (radarZoom === was) return;
  ctlSound.wheel(); buildRadarLegend(); rvSig = ""; renderRadarList();
  const b = $("rvZoomKm"); b.className = ""; void b.offsetWidth; b.className = d > 0 ? "down" : "up";     // the wheel rolls, as in Settings
}
// 1.65: pinch the radar to zoom; 1.68.1: really zoom: the range follows the fingers (radar.live, the map stretched
// meanwhile), and stays where they let go (the map is then drawn afresh for it). One finger still scrolls the page.
const pinch = {pts: new Map(), d0: 0, r0: 0, quiet: 0, tapAt: 0, tapX: 0, tapY: 0};
(() => {
  const el = $("scope");
  el.style.touchAction = "pan-y";
  const dist = () => { const [a, b] = [...pinch.pts.values()]; return Math.hypot(a.x - b.x, a.y - b.y); };
  el.addEventListener("pointerdown", e => {
    pinch.pts.set(e.pointerId, {x: e.clientX, y: e.clientY});
    if (pinch.pts.size !== 2) return;
    if (airportMode() && AP.lat == null) return;
    if (!radarZoomed() && airportMode()) { radarZoomSet(radarBase()); }      // the airport's close-up centre, at the usual range
    pinch.d0 = dist(); pinch.r0 = radarRange();
  });
  el.addEventListener("pointermove", e => {
    if (!pinch.pts.has(e.pointerId)) return;
    pinch.pts.set(e.pointerId, {x: e.clientX, y: e.clientY});
    if (pinch.pts.size !== 2 || !pinch.d0) return;
    radar.live = Math.max(RADAR_MIN, Math.min(radarBase(), pinch.r0 * pinch.d0 / Math.max(1, dist())));
    $("rvZoomKm").textContent = radarRangeText().replace(" km", "");
  });
  const end = e => {
    if (!pinch.pts.delete(e.pointerId) || !pinch.d0) return;
    const v = radar.live || pinch.r0;
    pinch.d0 = 0; radar.live = 0; pinch.quiet = Date.now() + 400;
    radarZoomSet(v >= radarBase() * .97 ? 0 : Math.round(v * 10) / 10);
    buildRadarLegend(); rvSig = ""; renderRadarList();
  };
  el.addEventListener("pointerup", end); el.addEventListener("pointercancel", end);
})();
for (const b of $("svPlaces").children) b.onclick = () => {
  const want = b.dataset.all === "1";
  if (want === allPlaces) return;
  ctlSound.click();
  const L = $("svList"), y = scrollY;
  L.style.minHeight = L.offsetHeight + "px";              // the list keeps its height while the other one loads (1.43)
  allPlaces = want; fullDay = {at: 0, rev: null, date: null, list: null}; svSig = todayFactsSig = ""; renderToday();
  scrollTo(0, y);
};
$("lookCv").onclick = () => { if (!lookOn && window.isSecureContext && typeof DeviceOrientationEvent !== "undefined") lookStart(); };
// The compass turns with the phone by itself where no permission is asked (Android): it starts at once, or on the
// first tap where the browser wants one; on an iPhone, tapping the dial asks.
function lookAuto(){
  if (!lookOn && window.isSecureContext && typeof DeviceOrientationEvent !== "undefined" && !/iPhone|iPad|Macintosh/.test(navigator.userAgent)) lookStart(true);
}
lookAuto();
addEventListener("pointerup", function lookFirst(){ removeEventListener("pointerup", lookFirst); lookAuto(); });
/* ---------- favourites and hidden planes (1.31, relay 31) ----------
   The lists live on the relay (userLists, shared code), so the boards and the notifications follow them. Here: a sheet
   to switch a plane's aircraft, type, airline or flight on or off as a favourite or hidden (from the lists' + and
   This aircraft), and the manager in Settings. */
const PUSH_KINDS = [["special", "Special planes (A380, 747, Beluga, Antonov, emergencies)"], ["watch", "Watchlist (police, ambulance, government, historic …)"],
  ["military", "Military planes"], ["fav", "Your favourites"], ["newtype", "Types never seen here"], ["low", "Very low passes"],
  ["quiet", "Quiet at night (22:00–07:00), except emergencies and special planes"]];
const PUSH_KIND_DEFAULTS = {special: true, watch: true, military: true, fav: true, newtype: false, low: false, quiet: true};
// A row of the lists (1.95): a tap opens its card in place. On the card the airline, the places and the Aircraft box
// open their own cards, the photo the whole plane card (its credit is Planespotters' link) and ⌃ folds it back.
const tlFind = k => spotted.concat(fullDay.list || []).find(r => tlKey(r) === k);
document.addEventListener("click", e => {
  const b = e.target && e.target.closest && e.target.closest("[data-more]");
  if (!b) return;
  e.stopPropagation();
  const x = tlFind(b.dataset.more);
  if (!x) return;
  if (!b.classList.contains("open")) { if (Date.now() - swipeEnded > 400) tlTap(b, e.clientX, e.clientY); return; }
  if (e.target.closest("[data-fold], .tlK")) { ctlSound.nav(); return tlFold(b, true); }
  const al = e.target.closest("[data-al]"), pl = e.target.closest("[data-pl]"), ty = e.target.closest("[data-ty]");
  if (al) return airlineCard(x);
  if (ty) return typeCard(x);
  if (pl) return placeCard(x[pl.dataset.pl]);
  if (e.target.closest("[data-full]") && !e.target.closest("a")) planeCard(sightPlane(x));
}, true);
addEventListener("keydown", e => {             // a row with the keyboard's focus: Enter or Space opens it
  const li = (e.key === "Enter" || e.key === " ") && e.target.matches && e.target.matches(".tline li.fl[data-more]:not(.open)") ? e.target : null;
  if (!li) return;
  e.preventDefault();
  const r = li.getBoundingClientRect();
  tlTap(li, r.left + r.width / 2, r.top + r.height / 2);
});
// The whole plane card for a sighting: the plane as the radar has one, with the route and remark its row shows.
const sightPlane = e => ({ac: {hex: e.hex, r: e.reg, t: e.typeCode, flight: e.callsign, desc: e.desc}, remark: remarkFor(e),
  info: {callsign: e.callsign, flightNo: e.flight, airline: e.airline, airlineCode: e.airlineCode, from: e.from, to: e.to, type: e.type, reg: e.reg,
    hex: e.hex, category: e.category, divertedTo: e.divertedTo, fr24: e.fr24, done: e.done !== false}});
/* Opening a card (Dave's option 1, Sky view's easing; since 1.97.1 a plain vertical growth): the row grows downwards
   into the card where it is and the rows below slide down; the row's text fades out, the card's content fades in. No
   circle, nothing glides. One card at a time: another row, or ⌃ or the bar above it, folds it back. With less motion it
   just opens. A redraw of the list waits until the card has settled. */
const TL_MS = 480, TL_EASE = "cubic-bezier(.2,.9,.25,1)", TL_OUT = "cubic-bezier(.33,1,.68,1)";
function tlStart(ms){ tlRunning++; tlCap = Math.max(tlCap, Date.now() + ms + 400); }
function tlEnd(){ tlRunning = Math.max(0, tlRunning - 1); tlDone(); }
async function tlTap(li, x, y){
  const L = li.closest(".tline"), k = li.dataset.more, e = tlFind(k), tok = ++tlTok;
  if (!L || !e) return;
  ctlSound.nav();
  // 1.97.3: it opens at once; its photo window shows a spinner until the photo is in
  if (tok === tlTok && li.isConnected && !li.classList.contains("open")) tlOpen(L, li, e);
}
function tlOpen(L, li, e){
  const old = L.querySelector("li.fl.open");
  if (old && old !== li) tlFold(old, true);
  tlOpenId[L.id] = tlKey(e);
  for (const g of li.querySelectorAll(".tlGone, .tlWas")) g.remove();       // tapped again while it folded
  const anim = !REDUCED && typeof li.animate === "function", h0 = li.offsetHeight;
  const cs0 = getComputedStyle(li), m0 = [cs0.marginTop, cs0.marginBottom], rowIn = li.innerHTML;
  li.className = "fl open"; li.removeAttribute("tabindex"); li.innerHTML = tlCardHtml(e);
  L.dataset.card = tlCardSig(e);
  tlWire(li);
  if (!anim) return tlScroll(li);
  // where it ends up, before anything moves
  const h1 = li.offsetHeight, cs1 = getComputedStyle(li), m1 = [cs1.marginTop, cs1.marginBottom], card = li.querySelector(".tlCard");
  const was = document.createElement("div");     // the row, fading away at the top while the card grows under it
  was.className = "tlWas"; was.innerHTML = rowIn; li.append(was);
  li.classList.add("tlAnim");
  tlStart(TL_MS);
  const go = (el, kf, o) => el.animate(kf, {duration: TL_MS, easing: TL_EASE, fill: "backwards", ...o});
  const grow = go(li, [{height: h0 + "px", marginTop: m0[0], marginBottom: m0[1]}, {height: h1 + "px", marginTop: m1[0], marginBottom: m1[1]}]);
  go(was, [{opacity: 1}, {opacity: 0}], {duration: TL_MS * .22, easing: "linear", fill: "forwards"});
  go(card.querySelector(".tlBg"), [{opacity: 0}, {opacity: 1}], {duration: TL_MS * .35, easing: TL_OUT});
  for (const el of card.querySelectorAll(".tlK, .cInfo"))
    go(el, [{opacity: 0}, {opacity: 1}], {duration: TL_MS * .5, delay: TL_MS * .2, easing: TL_OUT});
  li.tlNow = grow;                               // a folding that starts meanwhile takes over the row's height
  const end = () => { was.remove(); if (li.tlNow === grow) { li.classList.remove("tlAnim"); tlScroll(li); } tlEnd(); };
  grow.finished.then(end, end);
}
function tlFold(li, anim){
  const L = li.closest(".tline"), k = li.dataset.more, e = tlFind(k);
  if (L && tlOpenId[L.id] === k) { tlOpenId[L.id] = ""; L.dataset.card = ""; }
  if (!e) return;
  const h1 = li.offsetHeight, cs1 = getComputedStyle(li), m1 = [cs1.marginTop, cs1.marginBottom], card = li.querySelector(".tlCard");
  li.className = "fl"; li.tabIndex = 0; li.innerHTML = rowInner(e);
  if (!anim || REDUCED || !card || typeof li.animate !== "function") return;
  const h0 = li.offsetHeight, cs0 = getComputedStyle(li), m0 = [cs0.marginTop, cs0.marginBottom];
  card.classList.add("tlGone"); li.append(card);  // the card over the row, fading as it folds
  li.classList.add("tlAnim");
  tlStart(320);
  const shut = li.tlNow = li.animate([{height: h1 + "px", marginTop: m1[0], marginBottom: m1[1]}, {height: h0 + "px", marginTop: m0[0], marginBottom: m0[1]}], {duration: 320, easing: TL_EASE});
  card.animate([{opacity: 1}, {opacity: 0}], {duration: 200, easing: "linear", fill: "forwards"});
  for (const c of [li.querySelector(".l1"), li.querySelector(".l2")]) if (c) c.animate([{opacity: 0}, {opacity: 1}], {duration: 200, delay: 120, easing: TL_OUT, fill: "backwards"});
  const end = () => { card.remove(); if (li.tlNow === shut) li.classList.remove("tlAnim"); tlEnd(); };
  shut.finished.then(end, end);
}
// An open card hidden under the tab bar (or the header) comes into view
function tlScroll(li){
  if (!li.isConnected) return;
  const r = li.getBoundingClientRect(), top = $("top").getBoundingClientRect().bottom + 8, tb = $("tabs");
  const bottom = (tb && tb.getClientRects().length ? tb.getBoundingClientRect().top : innerHeight) - 8;
  const by = r.bottom > bottom ? Math.min(r.bottom - bottom, r.top - top) : r.top < top ? r.top - top : 0;
  if (by) try { scrollBy({top: by, behavior: REDUCED ? "auto" : "smooth"}); } catch { scrollBy(0, by); }
}
/* Swipe a row (1.41): right for a favourite, left to hide. While it moves the row's content slides and a label shows
   what letting go will do; past the threshold it opens that half of the sheet. A mostly vertical move stays a scroll. */
const SWIPE_AT = 72;
let swipe = null, swipeEnded = 0;
const swipeRow = t => t && t.closest && t.closest(".flights li.fl[data-more]:not(.open)");      // 1.95: a row, not an open card
document.addEventListener("touchstart", e => {
  const li = swipeRow(e.target);
  if (!li || !listsOk() || e.touches.length !== 1 || e.target.closest("button")) { swipe = null; return; }
  swipe = {li, x: e.touches[0].clientX, y: e.touches[0].clientY, dx: 0, on: false};
}, {passive: true});
document.addEventListener("touchmove", e => {
  if (!swipe) return;
  const dx = e.touches[0].clientX - swipe.x, dy = e.touches[0].clientY - swipe.y;
  if (!swipe.on) {
    if (Math.abs(dy) > 12 && Math.abs(dy) > Math.abs(dx)) { swipe = null; return; }      // a scroll
    if (Math.abs(dx) < 12) return;
    swipe.on = true; swipe.li.classList.add("swiping");
  }
  e.preventDefault();
  swipe.dx = Math.max(-140, Math.min(140, dx));
  const li = swipe.li, past = Math.abs(swipe.dx) >= SWIPE_AT;
  li.style.setProperty("--dx", swipe.dx + "px");
  li.dataset.swipe = swipe.dx > 0 ? "fav" : "hide";
  li.classList.toggle("armed", past);
  if (past && !swipe.buzzed) { swipe.buzzed = true; if (navigator.vibrate) try { navigator.vibrate(12); } catch {} }
  if (!past) swipe.buzzed = false;
}, {passive: false});
function swipeDone(){
  if (!swipe) return;
  const {li, dx, on} = swipe;
  swipe = null;
  if (!on) return;
  swipeEnded = Date.now();
  li.classList.remove("swiping", "armed");
  li.style.removeProperty("--dx"); delete li.dataset.swipe;
  if (Math.abs(dx) < SWIPE_AT) return;
  const x = spotted.concat(fullDay.list || []).find(r => (r.id || r.hex) === li.dataset.more);
  if (x) listSheet(x, dx > 0 ? "fav" : "hide");
}
document.addEventListener("touchend", swipeDone, {passive: true});
document.addEventListener("touchcancel", swipeDone, {passive: true});
// a swipe isn't also a tap on what it started on
document.addEventListener("click", e => { if (Date.now() - swipeEnded < 400 && swipeRow(e.target)) { e.stopPropagation(); e.preventDefault(); } }, true);
function listsChanged(){ svSig = recentSig = rvSig = ""; renderLists(); renderFeatured(); renderFavBox(); if (tab === "radar") renderRadarList(); }
// A picture found late (planeBody asks): the open plane card takes it while it still shows that plane (1.93.1.1: not
// only the radar's), the radar's with where its plane is now.
function planeAgain(){
  if (!planeShown || planeTok !== cardTok || !cardOpenNow()) return;
  const b = planeBody(radar.sel === planeShown.ac.hex && radar.planes.find(p => p.ac.hex === radar.sel) || planeShown);
  planeTok = cardOpen(b.html, b.wire);
}
// Settings → Favourites & hidden (the manager is shared with the boards' card).
function renderFavBox(){
  const box = $("favBox");
  if (!box) return;
  if (!listsOk()) { box.hidden = true; return; }
  box.hidden = false;
  box.innerHTML = `<div class="plate cardish" data-pid="favs" style="--cols:1"><i></i><i></i><i></i><i></i><h3>${T("Favourites & hidden")}</h3><div data-fm></div></div>`;
  favManager(box.querySelector("[data-fm]"));
  jumpBuild();
}

/* ---------- notifications (relay 25): the evening summary and "worth going to the window" ----------
   Browser push, which only works on https (the public address). The service worker (sw.js next to the app) shows them. */
const PUSH_PREFS = "od.push.prefs";
const SW_DIR = LIGHT ? "../app/" : "./";       // the light version shares the app's service worker (one subscription for both)
// 1.64: the service worker also keeps the app's last copy, so it opens without the relay (https and localhost only)
if (!LIGHT && "serviceWorker" in navigator && window.isSecureContext) setTimeout(() => navigator.serviceWorker.register(SW_DIR + "sw.js", {scope: SW_DIR}).catch(() => {}), 5000);
// 1.70: in the Android app (its WebView has no Web Push) notifications come through Firebase: the app hands over its
// token (OverheadAndroid.pushEnable → window.fallblattPush) and the relay (57+, with its Firebase key) sends to it.
const NATIVE_PUSH = () => ANDROID && !!window.OverheadAndroid.pushEnable && window.OVERHEAD_FCM === true;
const NATIVE_ON = "od.push.native";
const nativeOn = () => { try { return localStorage.getItem(NATIVE_ON) === "1"; } catch { return false; } };
function nativeToken(){
  return new Promise(ok => {
    const t = setTimeout(() => ok(["", T("The phone didn't answer. Try again in a moment.")]), 30000);
    window.fallblattPush = (tok, err) => { clearTimeout(t); ok([tok, err]); };
    window.OverheadAndroid.pushEnable();
  });
}
async function pushSub(){
  if (NATIVE_PUSH()) { const tok = nativeOn() && window.OverheadAndroid.pushToken(); return tok ? {fcm: tok} : null; }
  if (!("serviceWorker" in navigator) || !("PushManager" in window)) return null;
  const reg = await navigator.serviceWorker.getRegistration(SW_DIR);
  return reg ? reg.pushManager.getSubscription() : null;
}
const pushPossible = () => NATIVE_PUSH() || (window.OVERHEAD_RELAY_VERSION || 0) >= 25 && window.isSecureContext && "serviceWorker" in navigator &&
  "PushManager" in window && "Notification" in window && Notification.permission !== "denied";
// The service worker is registered as the app opens, so it is running by the time notifications are turned on (the
// first try used to fail while it was still starting, and the button had to be pressed twice).
let swReady = null;
function swRegister(){
  if (!swReady && pushPossible() && !NATIVE_PUSH()) swReady = navigator.serviceWorker.register(SW_DIR + "sw.js", {scope: SW_DIR}).then(() => navigator.serviceWorker.ready).catch(() => null);
  return swReady || Promise.resolve(null);
}
setTimeout(swRegister, 1500);
// 1.70: Firebase may give the phone a new token now and then: the relay hears the current one each time the app opens
setTimeout(() => { if (NATIVE_PUSH() && nativeOn()) pushSub().then(sub => {
  if (!sub) return;
  let prefs = {summary: true, review: true, window: true, countdown: true, ...PUSH_KIND_DEFAULTS};
  try { prefs = {...prefs, ...JSON.parse(localStorage.getItem(PUSH_PREFS) || "{}")}; } catch {}
  sendSub(sub, prefs, "subscribe").catch(() => {});
}); }, 6000);
// Turn notifications on: permission, the service worker, the subscription, the relay. Returns an error text, or "".
async function enablePush(){
  if (NATIVE_PUSH()) {
    const [tok, err] = await nativeToken();
    if (!tok) return err || T("Notifications couldn't be turned on.");
    let prefs = {summary: true, review: true, window: true, countdown: true, ...PUSH_KIND_DEFAULTS};
    try { prefs = {...prefs, ...JSON.parse(localStorage.getItem(PUSH_PREFS) || "{}")}; } catch {}
    const r = await sendSub({fcm: tok}, prefs, "subscribe");
    if (!r.ok) return `HTTP ${r.status}`;
    try { localStorage.setItem(NATIVE_ON, "1"); } catch {}
    return "";
  }
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
    let prefs = {summary: true, review: true, window: true, countdown: true, ...PUSH_KIND_DEFAULTS};
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
  const native = NATIVE_PUSH();
  if (!native && !window.isSecureContext) { box.innerHTML = say(T("Notifications only work through the https address (the one in your invite link), not at home on the Wi-Fi address.")); return; }
  if (!native && (!("serviceWorker" in navigator) || !("PushManager" in window) || !("Notification" in window))) {
    box.innerHTML = say(T("This browser can't show notifications. On an iPhone, add Fallblatt to the home screen first and open it from there.")); return;
  }
  if (!native && Notification.permission === "denied") { box.innerHTML = say(T("Notifications are blocked for this site in the browser's settings.")); return; }
  let prefs = {summary: true, review: true, window: true, countdown: true, ...PUSH_KIND_DEFAULTS};
  try { prefs = {...prefs, ...JSON.parse(localStorage.getItem(PUSH_PREFS) || "{}")}; } catch {}
  const sub = await pushSub().catch(() => null);
  const sw = (k, label) => `<label class="pushOpt"><input type="checkbox" data-p="${k}"${prefs[k] ? " checked" : ""}> ${escH(T(label))}</label>`;
  box.innerHTML = say(T("A summary of your day at 22:30, and a nudge when something special is about to pass over.")) +
    (sub ? say(T("Notifications are on for this device.")) : "") + sw("summary", "Evening summary") +
    ((window.OVERHEAD_RELAY_VERSION || 0) >= 46 ? sw("review", "Week and month in review") + `<p class="sum">${escH(T("Your week on Sunday at 20:00, your month on the 1st at 9:00."))}</p>` : "") + sw("window", "Worth going to the window") +
    ((window.OVERHEAD_RELAY_VERSION || 0) >= 31 ? `<div class="pushKinds"${prefs.window ? "" : " hidden"}><p class="sum"><b>${escH(T("Which notifications"))}</b> · ${escH(T("At most one every 15 minutes, except emergencies and special planes."))}</p>` +
      PUSH_KINDS.map(([k, l]) => sw(k, l)).join("") +
      ((window.OVERHEAD_RELAY_VERSION || 0) >= 56 ? sw("countdown", "Count down to the plane") + `<p class="sum">${escH(T("The notification counts down until the plane is there, and rings once more when it's time to look up."))}</p>` : "") + `</div>` : "") +
    `<div class="acts"><button class="cap big${sub ? "" : " go"}" type="button" id="pushBtn">${T(sub ? "Turn off" : "Turn on notifications")}</button>` +
    (sub && (window.OVERHEAD_RELAY_VERSION || 0) >= 57 ? `<button class="cap big" type="button" id="pushTest">${T("Send a test")}</button>` : "") + `</div><p class="note" id="pushNote"></p>`;
  if ($("pushTest")) $("pushTest").onclick = async () => {        // 1.70: one right away, to check
    ctlSound.press();
    const r = await fetch(`${relay()}/push/test`, {method: "POST"}).catch(() => null);
    $("pushNote").textContent = r && r.ok ? T("Sent: it should arrive in a few seconds.") : T(SAVE_FAILED);
  };
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
      if (sub) {
        await sendSub(sub, prefs, "unsubscribe");
        if (sub.unsubscribe) await sub.unsubscribe(); else try { localStorage.removeItem(NATIVE_ON); } catch {}
        return renderPush();
      }
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
    maxAltFt: +n.maxAltFt, airtimeMin: +n.airtimeMin, speedPct: +n.speedPct || 85, overKm: +n.overKm || 1};
  const langWas = LANG;
  if (GUEST) S.located = true;                               // a guest who saved Settings has chosen their place
  saveSettings(); audioInit(); nightCheck();
  pickLang(); if (LANG !== langWas) applyLang();
  AP.code = "";                                               // the home airport may have changed
  if (wasDemo !== S.demo) {
    feat = null; infoCache.clear(); sightRev = null; relayStats = null; airtime.clear(); lbCache = null;
    fullDay = {at: 0, rev: null, date: null, list: null};
    spotted = relayV5() ? [] : S.demo ? demoLog() : [];
    if (relayV5()) syncSightings();
  }
  applyTheme(); updateWhere();
  recentSig = svSig = lbSig = ""; shownPhoto = null;
  if (tab === "now") applyMode();
  renderLists(); renderFeatured(); renderAircraftInfo(); updateFooter(); poll(true); sayHello();
}

/* ---------- a guest's first visit: where to watch the sky ---------- */
//@L:greet
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
//@L:end
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
  const start = {...(window.OVERHEAD_DEFAULTS || {}), ...(GUEST.settings || {})};      // 1.49.1: only the relay's city and airport, the spot is the guest's own
  for (const [id, k] of [["wPlace", "place"], ["wHome", "home"]])
    if (start[k] != null) $(id).value = start[k];
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
  $("wPushNo").onclick = () => { ctlSound.nav(); acctStep(); };
  function acctStep(){              // an account, so the logbook comes along to a new phone (https only: passkeys)
    if (!accountsOk() || !passkeysHere()) return pick();
    wSwap([$("wStep1"), $("wPush")], $("wAcct"));
    $("wAcctNo").textContent = T("Not now");
    $("wAcctNo").onclick = () => { ctlSound.nav(); pick(); };
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
  $("wLater").onclick = () => { ctlSound.nav(); box.hidden = true; run(); showTab("settings"); };
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
// 1.45: the ding for a new plane on top only sounds on Now, where that plane shows; the chimes play anywhere.
function onMainPage(){ return tab === "now"; }
function buildTabs(){
  $("tabRow").innerHTML = TABS.map(([t, name]) => `<button class="cap${T(name).length > 9 ? " long" : ""}" type="button" data-tab="${t}">${TAB_ICONS[t]}<span>${T(name)}</span></button>`).join("");
  for (const b of $("tabRow").children) b.onclick = () => { audioInit(); ctlSound.press(); showTab(b.dataset.tab); };
}
function pingNow(on){ const b = $("tabRow").querySelector('[data-tab="now"]'); if (b) b.classList.toggle("ping", on); }
// The tips for a tab (1.42): what the tab is, the first time, then what can be done on it.
const TAB_TIPS = {now: "Now: the plane over you right now, its photo, and today's planes below. Tap the board for its card.",
  today: "Spotted today: every plane that came within your radius today, with the day's numbers.",
  logbook: "Logbook: everything you've ever spotted: types, airlines, aircraft, the year in planes and your week and month.",
  radar: "Radar: the planes around you right now. Tap one for its card.",
  settings: "Settings: your place, what counts as overhead, the look and the sounds. Press Save to keep them."};
// 1.49 (to-do #29): the first time on Now, a walk through the styles, the page buttons and every tab; the first time in
// the Airport style, through its pages.
function appTips(t){
  if (t !== tab || SIDEWAYS.matches || ($("welcome") && !$("welcome").hidden) || !$("t-about").hidden) return;
  const vis = el => el && !el.hidden && el.getClientRects().length ? el : null;
  const tabBtn = x => () => $("tabRow").querySelector(`[data-tab="${x}"]`);
  tip("tab-" + t, tabBtn(t), T(TAB_TIPS[t]));
  if (t === "now") {
    tip("mode", () => $("modes"), T(MODE_TIP));
    const pageBtn = p => () => vis($("apPick").querySelector(`[data-page="${p}"]`)) || vis($("nowPages").querySelector(`[data-page="${p}"]`));
    if (airportMode()) for (const [p, k] of [["lists", "aplists"], ["dep", "apdep"], ["land", "apland"]]) tip("ap-" + p, pageBtn(p), T(PAGE_TIPS[k]));
    else for (const [p, k] of [["lists", "spotted"], ["ac", "aircraft"]]) tip("pg-" + p, pageBtn(p), T(PAGE_TIPS[k]));
    for (const [x] of TABS) if (x !== "now") tip("tab-" + x, tabBtn(x), T(TAB_TIPS[x]));
    tip("swipe", () => $("recent").querySelector("li.fl[data-more]"), T("Swipe a plane to the right to make it a favourite, or to the left to hide it."));
    tip("open", () => $("recent").querySelector("li.fl[data-more]"), T("Tap a plane to open it. Its photo opens the whole card; its airline, places and type open theirs."));
  }
  if (t === "today") tip("allplaces", () => vis($("svPlaces")), T("Switch between the place you're watching and all your places."));
  if (t === "logbook") tip("lbplaces", () => vis($("lbPlaces")), T("Pick a place to see its own numbers, or All for everything."));
  if (t === "settings") {
    tip("setlabel", () => document.querySelector("#cockpit .lblF"), T("Give the place you're watching a name and press its Save to keep it in your saved places."));
    tip("setlive", () => document.querySelector("#cockpit [data-live]"), T("Live location follows this phone while the app is open."));
  }
}
// About is a page over Settings (1.41): Settings stays as it was underneath, scrolled where it was.
function aboutShow(){
  if (tab !== "settings") showTab("settings");
  $("t-about").hidden = false; $("t-about").scrollTop = 0;
  document.body.classList.add("aboutOpen");
  aboutOpen();
}
function aboutHide(){
  if ($("t-about").hidden) return;
  $("t-about").hidden = true;
  document.body.classList.remove("aboutOpen");
}
addEventListener("keydown", e => { if (e.key === "Escape" && !cardOpenNow()) { if (!$("t-styles").hidden) stylesHide(); else if (!$("t-about").hidden) aboutHide(); } });
function showTab(t){
  if (t === "about") { aboutShow(); return; }
  const rv = /^review-(week|month)-(\d{1,2})$/.exec(t || "");      // a review notification (1.52): the Logbook at that week or month
  if (rv) { review.span = rv[1]; review.back = +rv[2]; lbPeriod = rv[1]; t = "logbook"; }
  aboutHide(); stylesHide();
  if ((!TABS.some(x => x[0] === t) && !(t === "game" && gameOk())) || SIDEWAYS.matches) t = "now";
  const was = tab;
  tab = t;
  for (const [x] of TABS) $("t-" + x).hidden = x !== t;
  $("t-game").hidden = t !== "game";                 // 1.72: the Game page, opened from the score strip
  if (t !== "game") gRoute = false;                  // 1.109: the club opens at its top again, not on Your route
  for (const b of $("tabRow").children) { if (b.dataset.tab === (t === "game" ? "logbook" : t)) b.setAttribute("aria-current", "page"); else b.removeAttribute("aria-current"); }   // 1.74: the Spotters' Club is the Logbook's
  HERO.off = t !== "now"; TODAYP.off = t !== "today"; LBP.off = t !== "logbook";
  clearInterval(tabTimer); tabTimer = null;
  stopRadar();
  refreshPanels();
  if (t === "now") { pingNow(false); applyMode(); renderFeatured(); renderAircraftInfo(); renderRecent(); }
  else if (t === "today") { svSig = ""; renderToday(); }
  else if (t === "logbook") { lbSig = ""; fetchLogbook(); tabTimer = setInterval(fetchLogbook, 60000); }
  else if (t === "radar") { rvSig = ""; startRadar(); renderRadarList(); }
  else if (t === "settings") { jumpHold = null; cockpitOpen(); settingsExtra(); renderFavBox(); jumpBuild(); }
  else if (t === "game") { $("gameBox").dataset.h = ""; gRefresh(true); gLeagueLoad(true); fetchLogbook(); renderGame(); tabTimer = setInterval(() => { gLeagueLoad(); renderGame(); }, 30000); }
  const hash = t === "now" ? "" : "#" + t;
  if (location.hash !== hash) history.replaceState(null, "", location.pathname + location.search + hash);
  setTimeout(() => appTips(t), 900);
  if (was !== t) window.scrollTo(0, 0);
}
addEventListener("hashchange", () => { if (location.hash !== tabHash()) showTab(location.hash.slice(1)); });   // 1.97.7: not when it's the page's own back putting the URL right

/* ---------- status: a dot by the clock, a line under the lists ---------- */
function statusLine(){
  if (S.demo) return T("Demo mode · sample flights, not live data");
  if (!relay()) return T("No flight data here: open the app through your home relay, at http://<your computer>:8080/app/");
  if (window.OVERHEAD_OFFLINE && !lastOk) return T("Offline · the app as of {t} · retrying", {t: hhmm(new Date(window.OVERHEAD_OFFLINE))});   // 1.64: the kept copy
  if (isOffline()) return T("No flight data for over a minute · retrying");
  if (!lastOk && snapShown && !failures) return T("Last known board · not live yet");
  if (!lastOk && failures) return T(failures > 1 ? "Waiting for flight data · {n} failed attempts" : "Waiting for flight data · {n} failed attempt", {n: failures});
  if (!lastOk) return T("Connecting…");
  const age = Math.round((Date.now() - lastOk) / 1000), stale = lastFreshness.startsWith("stale");
  return T("Live via {src}", {src: feedName}) + (stale ? " " + T("(last good copy)") : "") + " · " + (age < 3 ? T("updated just now") : T("updated {n} s ago", {n: age})) +
    (failures ? " · " + T("retrying") : "") + " · " + T("{n} aircraft within {km} km", {n: nearbyCount ?? 0, km: QUERY_KM}) + (apiOn() ? " · " + T("flight numbers by Flightradar24") : "");
}
function updateFooter(){
  const dot = $("dot");
  dot.dataset.state = S.demo ? "demo" : !relay() || isOffline() ? "off" : !lastOk ? (failures || snapShown ? "warn" : "") : failures || lastFreshness.startsWith("stale") ? "warn" : "live";
  const line = statusLine();
  for (const el of document.querySelectorAll(".statusText")) if (el.textContent !== line) el.textContent = line;
  document.body.dataset.health = dot.dataset.state || "";          // the line under the lists only shows when it matters
  const bad = ["off", "warn", "demo"].includes(dot.dataset.state), al = $("sideAlert");     // on its side: only when something is wrong
  al.hidden = !bad; al.dataset.state = dot.dataset.state;
  if (bad && al.textContent !== line) al.textContent = line;
  if (!$("t-about").hidden) renderAbout();
}
// The dot opens a card: the relay, the position source, the last update and Flightradar24 (1.38).
function statusCard(){
  ctlSound.nav();
  const ago = t => { const n = Math.round((Date.now() - t) / 1000); return n < 3 ? T("just now") : n < 120 ? T("{n} s ago", {n}) : T("{n} min ago", {n: Math.round(n / 60)}); };
  const ok = (good, text) => `<span class="stOk" data-ok="${good}">●</span> ${escH(text)}`;
  const draw = () => {
    const stale = lastFreshness.startsWith("stale"), rv = window.OVERHEAD_RELAY_VERSION || 0;
    const relayRow = S.demo ? ok("meh", T("Demo mode · sample flights, not live data")) : !relay() ? ok("bad", T("Not connected: open the app through the home relay"))
      : isOffline() ? ok("bad", T("No answer for over a minute · retrying")) : lastOk ? ok("good", T("Connected")) : ok("meh", T("Connecting…"));
    const srcRow = !feedName ? escH(T("None yet")) : ok(stale ? "meh" : "good", stale ? T("{src} · last good copy, {n} s old", {src: feedName, n: lastFreshness.split(" ")[1] || "?"}) : T("{src} · live", {src: feedName}));
    const fr = !USE_API ? T("Not used") : apiOn() ? T("On") : window.OVERHEAD_FR24 === true ? T("On, not answering · free sources for now") : T("Off · free sources");
    return factsHtml([["Relay", relayRow], ["Position source", srcRow],
      ["Last update", escH(lastOk ? ago(lastOk) : T("None yet"))],
      ["Failed attempts", failures ? ok("meh", T("{n} in a row", {n: failures})) : escH(T("None"))],
      ["In range", escH(T("{n} aircraft within {km} km", {n: nearbyCount ?? 0, km: QUERY_KM}))],
      ["Flightradar24", escH(fr)], ["Relay version", rv ? escH(String(rv)) : ""]]);
  };
  const tok = cardOpen(`<h3>${escH(T("Connection"))}</h3><div data-st>${draw()}</div>` +
    `<div class="cBtns"><button class="cBtn" type="button" id="stLog">${escH(T("Log"))}</button></div>`);
  $("stLog").onclick = () => { ctlSound.click(); cardClose(); logShow(); };
  const tick = setInterval(() => {
    const el = cardTok === tok && cardOpenNow() && document.querySelector("#cardBox [data-st]");
    if (!el) return clearInterval(tick);
    const h = draw(); if (el.innerHTML !== h) el.innerHTML = h;
  }, 1000);
}
function updateWhere(){
  const lab = !S.live && S.placeKey && clean(S.placeKey) !== clean(S.place) ? clean(S.placeKey) + "  ·  " : "";
  // 1.90: before the first fix only FINDING YOU … (the place is an old one, and the line fits a phone); 1.93.0.1: then
  // only ON THE GO until live location has the name of where it is (placeNow)
  const name = placeNow();
  $("where").textContent = liveWaiting() ? "◉ " + T("FINDING YOU …") : S.live && !name ? "◉ " + (liveStale() ? T("FINDING YOU …") : clean(T("On the go"))) :
    `${S.live ? "◉ " : ""}${liveStale() ? T("FINDING YOU …") + "  ·  " : ""}${lab}${clean(name)}  ·  ${T("RADIUS {n} KM", {n: +S.radiusKm || 15})}`;
}
function liveShow(){ updateWhere(); renderRecent(); renderToday(); }     // live location found its position, or lost it (1.90: and the lists)
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
watchVersion();
// 1.82.0.1: refreshing (Refresh now, or the notice's own countdown) covers the page at once with the opening, still; the new
// page shows it in place (od.nvGo) until its board is ready. Should the page stay, the cover goes after 20 s.
function nvGoing(){
  try { sessionStorage.setItem("od.nvGo", "1"); } catch {}
  if (NV.el) NV.el.remove();
  if (!window.SPLASH_HTML || $("splash")) return;
  document.body.insertAdjacentHTML("beforeend", window.SPLASH_HTML.replace('<div id="splash"', '<div id="splash" class="still" style="z-index:100"'));
  setTimeout(() => { const c = $("splash"); if (c) c.remove(); NV.going = false; try { sessionStorage.removeItem("od.nvGo"); } catch {} }, 20000);
}                          // the board's notice (with the patch notes); no reload while Settings is open
NV.busy = () => tab === "settings";
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
/* ---------- the game (1.72, relay 59): the score strip, the Points field, the Game page, Sky view's lock-on ----------
   Only planes spotted with live location score, the first time they come within 10 km (15 since 1.98; the relay counts them). The
   strip under the header shows the total on flaps, the level bar and the league place, on every tab; tapping it opens
   the Game page (no tab of its own). When points come in, the rank chip flips to +N, the +N flies into the level bar,
   which fills, and the total rolls up. */
const gameOk = () => !S.demo && !!relay() && (window.OVERHEAD_RELAY_VERSION || 0) >= 59;
// 1.96 (to-do #127): the rules (each rarity's points, the passive points, the limits, the extras, the streak) come from
// the relay (76), the one source; an older relay sends none.
const gRules = () => (gme && gme.rules) || null;
const gBase = t => { const r = gRules(); return r ? r.base[t] != null ? r.base[t] : r.base.uncommon : null; };
const gKm = () => (gme && gme.km) || 10;             // the game's circle, from the relay (10 km since relay 60; 15 since relay 82)
const gScanKm = () => (gme && gme.scanKm) || gKm();  // 1.98 (relay 82): the scan's circle, 10 km (an older relay: the one circle)
// 1.98: the planes a scan counts for now (the relay's list), as a set (made once for each answer)
const gScanSet = () => gme && Array.isArray(gme.scan) ? (gme.scanSet ||= new Set(gme.scan.map(x => x.hex))) : new Set();
const gGoldSet = () => gme && Array.isArray(gme.scan) ? (gme.goldSet ||= new Set(gme.scan.filter(x => x.gold).map(x => x.hex))) : new Set();   // 1.100
let gme = null, gmeAt = 0, gBusy = false, gLeague = null, gLeagueAt = 0, gAll = false, gAnimT = [];
function gStripSetup(){
  const box = $("gStrip");
  box.hidden = !gameOk();
  if (box.hidden || box.dataset.on) return;
  box.dataset.on = "1";
  box.innerHTML = `<button type="button" class="gMain" aria-label="${escH(T(gRecentOk() ? "Recent points" : "Spotters' Club: your points, level and the league"))}"><span class="gTot" id="gTot"></span><span class="gRk" id="gRk"></span>` +
    `<span class="gLv"><small id="gLvTxt"></small><span class="gBar"><i id="gBarI"></i><b id="gBarG"></b></span></span></button>` +
    `<button type="button" class="gChip" id="gChip"><span class="r1" id="gRank"></span><span class="r2" id="gPlus"></span></button><b class="gTok" id="gTok"></b>`;
  box.querySelector(".gMain").onclick = () => { audioInit(); ctlSound.nav(); if (gRecentOk()) gRecentCard(); else showTab("game"); };
  $("gChip").onclick = () => { audioInit(); ctlSound.nav(); if (!S.live && liveOk()) gGoLive(); else showTab("game"); };
}
// 1.74: Logbook and Spotters' Club: the title tabs, and a sideways swipe on either page switches to the other.
for (const b of document.querySelectorAll("[data-lt]")) b.onclick = () => { if (tab !== b.dataset.lt) { ctlSound.nav(); showTab(b.dataset.lt); } };
for (const id of ["t-logbook", "t-game"]) { let sw = null;
  $(id).addEventListener("touchstart", e => { const t = e.touches[0]; sw = e.target.closest("input, .seg, .bingo, .hgRow") ? null : {x: t.clientX, y: t.clientY}; }, {passive: true});
  $(id).addEventListener("touchend", e => {
    if (!sw) return;
    const t = e.changedTouches[0], dx = t.clientX - sw.x, dy = t.clientY - sw.y; sw = null;
    if (Math.abs(dx) < 70 || Math.abs(dy) > Math.abs(dx) * .6) return;
    if (tab === "logbook" && dx < 0 && gameOk()) showTab("game"); else if (tab === "game" && dx > 0) showTab("logbook");
  }, {passive: true}); }
// 1.73.2: a notice goes when swiped to the right (a finger, or a mouse); a short swipe springs back.
{ let sw = null;
  // 1.98: the points passes and the tickets too (their slide-in holds `transform`, so they move by `translate`)
  const shift = (t, x) => { if (t.classList.contains("gAw")) t.style.translate = x ? x + " 0" : ""; else t.style.transform = x ? `translateX(${x})` : ""; };
  const start = (t, x) => { sw = {t, x0: x, dx: 0}; t.style.transition = "none"; };
  const move = x => { if (!sw) return; sw.dx = Math.max(0, x - sw.x0); shift(sw.t, sw.dx + "px"); sw.t.style.opacity = String(Math.max(.2, 1 - sw.dx / 260)); };
  const end = () => {
    if (!sw) return;
    const {t, dx} = sw; sw = null; t.style.transition = "";
    if (dx > 8) t.swiped = true;                      // no tap after a swipe (a mouse)
    if (dx > 60) {
      shift(t, "120%"); t.style.opacity = "0";
      if (t.classList.contains("gAw")) { clearTimeout(t.outT); gTixOut.delete(t); setTimeout(() => { t.remove(); gTixStack(); gTixBack(); }, 260); }
      else setTimeout(() => t.remove(), 260);
    } else { shift(t, ""); t.style.opacity = ""; }
  };
  const toastAt = e => e.target && e.target.closest && (e.target.closest("#gAws .gAw:not(.out)") || !e.target.closest("button") && e.target.closest("#toasts .toast"));
  document.addEventListener("touchstart", e => { const t = toastAt(e); if (t) start(t, e.touches[0].clientX); }, {passive: true});
  document.addEventListener("touchmove", e => { if (sw) move(e.touches[0].clientX); }, {passive: true});
  document.addEventListener("touchend", end); document.addEventListener("touchcancel", end);
  document.addEventListener("pointerdown", e => { const t = e.pointerType === "mouse" && toastAt(e); if (t) start(t, e.clientX); });
  document.addEventListener("pointermove", e => { if (sw && e.pointerType === "mouse") move(e.clientX); });
  document.addEventListener("pointerup", e => { if (e.pointerType === "mouse") end(); }); }
// 1.73.2: Go live: a turning circle in the chip until the phone has found itself (or 15 s), then the strip as it is.
let gGoing = 0;
function gGoLive(){
  if (gGoing) return;
  liveStart();
  const t0 = Date.now();
  gGoing = setInterval(() => {
    if (S.live && !liveFirst || Date.now() - t0 > 15000) { clearInterval(gGoing); gGoing = 0; gRefresh(true); if (gme) gStripRender(gme); }
    else if (gme) gStripRender(gme);
  }, 400);
  if (gme) gStripRender(gme);
}
// The total on flaps: a flap flips over only where the digit changed, right to left.
// 1.73.3: always five flaps (room for 10,000 and up), blank in front
function gTotSet(n, anim){
  const el = $("gTot"), t = String(Math.max(0, Math.round(n || 0))).padStart(5, " ");
  if (el.children.length !== t.length) el.innerHTML = [...t].map(() => "<s></s>").join("");
  [...t].forEach((c, i) => { const s = el.children[i], v = c === " " ? "" : c;
    if (s.textContent === v) return;
    if (!anim) { s.textContent = v; return; }
    setTimeout(() => { s.textContent = v; s.classList.remove("flp"); void s.offsetWidth; s.classList.add("flp"); }, (t.length - i) * 90); });
}
// 1.102 (to-do #154, Dave's pick: round 2's ladder A): the level as a rank insignia, its colour telling the group and
// its mark the step. 1–4 a sky-blue shoulder board with 1–4 silver pips, 5–8 navy with silver chevrons, 9–11 black with
// 2–4 gold stripes, 12–14 gold piping, four stripes and 1–3 stars; 15–20 a pilot's cap (a gold line on the peak, gold
// leaves, the peak gold, cord and piping, 19 a red band, 20 white), past 20 a gold star above it for each Legend. The
// flight school's wings (#153, g.wings) as a pin beside it. The gradients once in the page (#rkDefs), so the same level
// always draws the same markup (renderGame redraws only when its HTML changed).
const RK_MET = {S: ["#ffffff", "#8d949e"], G: ["#ffe7a0", "#b8861c"]};
const RK_CLOTH = {sky: ["#5d9be0", "#2c63a8"], navy: ["#2a3b66", "#111b36"], black: ["#2b2c30", "#0c0c0e"]};
const RK_WF = "M52,14 C38,7 18,5 2,7 C14,12 32,16 52,19 Z M52,19 C38,15 22,14 9,15.5 C21,20 36,22 52,24 Z M52,24 C40,22.5 28,22.5 17,24.5 C28,28 40,29 52,29 Z";
const RK_STAR = "M12 3l2.6 5.6 6.1.7-4.5 4.2 1.2 6L12 16.6 6.6 19.5l1.2-6L3.3 9.3l6.1-.7z";
const RK_PLANE = "M21 16v-2l-8-5V3.5a1.5 1.5 0 0 0-3 0V9l-8 5v2l8-2.5V19l-2 1.5V22l3.5-1 3.5 1v-1.5L13 19v-5.5z";
const RK_LADDER = [null, ["sky", "pip", 1], ["sky", "pip", 2], ["sky", "pip", 3], ["sky", "pip", 4],
  ["navy", "chev", 1], ["navy", "chev", 2], ["navy", "chev", 3], ["navy", "chev", 4],
  ["black", "bar", 2], ["black", "bar", 3], ["black", "bar", 4], ["black", "star", 1], ["black", "star", 2], ["black", "star", 3],
  ["cap", 1], ["cap", 2], ["cap", 3], ["cap", 4], ["cap", 5], ["cap", 6]];
function rkDefs(){
  if ($("rkDefs")) return;
  const grad = (id, [a, b], x2, y2) => `<linearGradient id="${id}" x1="0" y1="0" x2="${x2}" y2="${y2}"><stop offset="0" stop-color="${a}"/><stop offset="1" stop-color="${b}"/></linearGradient>`;
  document.body.insertAdjacentHTML("beforeend", `<svg id="rkDefs" width="0" height="0" style="position:absolute" aria-hidden="true"><defs>` +
    Object.entries(RK_MET).map(([k, c]) => grad("rkM" + k, c, 0, 1)).join("") + Object.entries(RK_CLOTH).map(([k, c]) => grad("rkC" + k, c, 1, 1)).join("") + `</defs></svg>`);
}
const rkStar = (cx, cy, r, fill) => `<path transform="translate(${cx - r} ${cy - r}) scale(${r / 12})" d="${RK_STAR}" fill="${fill}"/>`;
const rkWings = (x, y, w) => `<g transform="translate(${x} ${y}) scale(${w / 120})"><g fill="url(#rkMG)" stroke="${RK_MET.G[1]}" stroke-width="1"><path d="${RK_WF}"/><path d="${RK_WF}" transform="matrix(-1 0 0 1 120 0)"/><circle cx="60" cy="20" r="10.5"/></g>` +
  `<path transform="translate(52 12) scale(.67)" fill="${RK_MET.G[1]}" d="${RK_PLANE}"/></g>`;
function rkCap(st){
  const gold = "url(#rkMG)", leaves = y => Array.from({length: 9}, (_, i) => { const x = 18 + i * 5.5; return `<ellipse cx="${x}" cy="${y}" rx="2.6" ry="1.4" transform="rotate(-30 ${x} ${y})" fill="${st >= 3 ? "#8a5f10" : gold}"/>`; }).join("");
  return `<path d="M6 22 C4 10 20 4 40 4 C60 4 76 10 74 22 Z" fill="${st >= 6 ? "#f5f1e6" : "#16203d"}" stroke="${st >= 6 ? "#cfc6ae" : "none"}"/>` +
    (st >= 4 ? `<path d="M10 17 C14 9 28 6 40 6 C52 6 66 9 70 17" fill="none" stroke="${gold}" stroke-width="2"/>` : "") +
    `<rect x="12" y="20" width="56" height="12" rx="2" fill="${st === 5 ? "#a3202a" : "#0a0f1e"}"/>` +
    (st >= 4 ? `<rect x="12" y="25.5" width="56" height="3" fill="${gold}"/>` : "") +
    `<path d="M10 32 H70 C66 40 50 44 40 44 C30 44 14 40 10 32 Z" fill="${st >= 3 ? gold : "#05070c"}"/>` +
    (st <= 2 ? `<path d="M14 35.5 H66" stroke="${gold}" stroke-width="2.4"/>` : "") + (st === 2 ? leaves(40) : st >= 3 ? leaves(38) : "") +
    `<ellipse cx="40" cy="20" rx="9.5" ry="8.5" fill="#0a0f1e" stroke="${gold}" stroke-width="1.8"/>` + rkWings(27, 14, 26);
}
const rankTitle = lv => lv > 20 ? T("Legend {n}", {n: lv - 19}) : T(GAME_LEVELS[Math.max(1, lv) - 1]);
// A level's insignia, h px tall as a shoulder board (a cap is two thirds of that). o.wings: the wings pin beside it;
// o.label: said by a screen reader ("Rank: Captain"); without it the insignia is hidden from one (its title is beside it).
function rankIns(lv, h, o = {}){
  rkDefs();
  lv = Math.max(1, Math.round(lv) || 1);
  const L = RK_LADDER[Math.min(lv, 20)], leg = Math.max(0, lv - 20);
  let svg;
  if (L[0] === "cap") {
    const ch = h * .66 * (leg ? 55 / 48 : 1), r = 5.5, gap = 13;
    svg = `<svg viewBox="0 ${leg ? -9 : -2} 80 ${leg ? 55 : 48}" height="${ch.toFixed(1)}">${rkCap(L[1])}` +
      Array.from({length: Math.min(leg, 5)}, (_, i) => rkStar(40 + (i - (Math.min(leg, 5) - 1) / 2) * gap, -4, r, "url(#rkMG)")).join("") + `</svg>`;
  } else {
    const [cloth, mark, n] = L, fill = `url(#rkM${mark === "pip" || mark === "chev" ? "S" : "G"})`;
    let b = `<path d="M5 92 V22 L22 5 L39 22 V92 Z" fill="url(#rkC${cloth})" stroke="${mark === "star" ? fill : "#070a14"}" stroke-width="${mark === "star" ? 2.6 : 1.5}" stroke-linejoin="round"/>` +
      `<circle cx="22" cy="19" r="4.4" fill="url(#rkMG)" stroke="#7a5a12" stroke-width=".8"/>`;
    if (mark === "pip") b += Array.from({length: n}, (_, i) => `<circle cx="22" cy="${82 - i * 14}" r="5.4" fill="${fill}" stroke="#5a616b" stroke-width=".8"/>`).join("");
    if (mark === "chev") b += Array.from({length: n}, (_, i) => `<path d="M9 ${74 - i * 12} L22 ${84 - i * 12} L35 ${74 - i * 12}" fill="none" stroke="${fill}" stroke-width="5" stroke-linejoin="miter"/>`).join("");
    if (mark === "bar") b += Array.from({length: n}, (_, i) => `<rect x="7" y="${80 - i * 10}" width="30" height="6" rx="1" fill="${fill}"/>`).join("");
    if (mark === "star") b += Array.from({length: 4}, (_, i) => `<rect x="7" y="${82 - i * 8.5}" width="30" height="5" rx="1" fill="${fill}"/>`).join("") +
      (n === 3 ? rkStar(22, 46, 6.5, fill) + rkStar(14, 33, 6, fill) + rkStar(30, 33, 6, fill) : n === 2 ? rkStar(22, 46, 6.5, fill) + rkStar(22, 32, 6.5, fill) : rkStar(22, 42, 8, fill));
    svg = `<svg viewBox="0 0 44 96" height="${h}">${b}</svg>`;
  }
  const pin = o.wings ? `<svg class="rkW" viewBox="0 4 120 28" height="${Math.max(7, h * .26).toFixed(1)}">${rkWings(0, 0, 120)}</svg>` : "";
  const lab = o.label ? [T("Rank: {t}", {t: rankTitle(lv)}), o.wings ? T("Wings") : ""].filter(Boolean).join(" · ") : "";
  return `<span class="rkI"${lab ? ` role="img" aria-label="${escH(lab)}"` : ' aria-hidden="true"'}>${svg}${pin}</span>`;
}
// 1.109 (to-do #152, Dave's pick of 29 Oct, round 2's B: the route map): the career path, a stop for each level and what
// it opens. CAREER is the one table of unlocks, [level, kind, id, name] by level, that the route, Your level, the strip
// and the level-up all read: the board styles come from STYLES (their {lvl: n} rule decides), the rest from CAREER_MORE,
// where another feature adds its row (its kind gets an icon in careerIco and a label in CAREER_KIND; Try it opens the
// club for a kind that isn't a style). Past level 20 each level is Legend n, one more star on the cap (careerAt).
const CAREER_MORE = [[3, "slot", 1, "Showcase slot {n}"], [5, "slot", 2, "Showcase slot {n}"], [8, "slot", 3, "Showcase slot {n}"],
  [6, "standby", 1, "Standby (one a week)"], [14, "standby", 2, "Standby (two a week)"], [19, "ace", "", "A gold name in the league"],
  [20, "cap", "", "The Legend cap"]];
const CAREER = [...STYLES.flatMap(([kind, , items]) => items.filter(x => x[2] && x[2].lvl).map(([id, nm, r]) => [r.lvl, kind, id, nm])),
  ...CAREER_MORE].sort((a, b) => a[0] - b[0]);
const CAREER_KIND = {palette: "Board colours", finish: "Flaps", badge: "Title badge", theme: "Board style", slot: "Showcase",
  standby: "Standby", ace: "League", cap: "Rank", star: "Rank"};
const careerAt = lv => lv > 20 ? [[lv, "star", "", "Another star on the cap"]] : CAREER.filter(r => r[0] === lv);
const careerName = r => T(r[3], {n: r[2]});
const CU_PLANE = `<svg class="cuP" viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="${RK_PLANE}"/></svg>`;
// The points a level opens at (as the relay's level_of: 500 to level 2, a quarter more for each next one up to level 20,
// from there the same as the last).
function careerPts(lv){
  let t = 0, need = 500;
  for (let i = 1; i < lv; i++) { t += Math.round(need); if (i + 1 < 20) need *= 1.25; }
  return t;
}
// An unlock's small picture, sz px: an "A" flap in the style for colours, flaps and board styles, the badge's own
// silhouette (badgeGlyph, drawn once), the cap and its star as the rank insignia draws them.
const cuBadge = new Map();
function careerIco(r, sz){
  const [, kind, id] = r, box = `width:${sz}px;height:${sz}px;font-size:${Math.round(sz * .62)}px`;
  const flap = (bg, fg, x = "", f = "") => `<span class="cuI flap${x}" style="${box};background:${bg};color:${fg}${f}"><b>A</b></span>`;
  if (kind === "palette") return flap(THEMES.classic.flap[0], (PALETTES[id] || {}).ink || THEMES.classic.ink);
  if (kind === "finish") return id === "white" ? flap("#f3f1ea", "#111") : flap("#1c1d1f", id === "led" ? "var(--amber)" : "#f3f0e8", " " + id);
  if (kind === "theme") { const t = THEMES[id] || THEMES.classic; return flap(t.flap[0], t.ink, "", `;font-family:${escH(t.font)}`); }
  if (kind === "badge") {
    if (!cuBadge.has(id)) {
      let u = "";
      try { const cv = document.createElement("canvas"); cv.width = cv.height = 64; const g = cv.getContext("2d");
        g.translate(32, 32); g.fillStyle = "#f0b429"; badgeGlyph(g, id, 26); u = cv.toDataURL("image/png"); } catch {}
      cuBadge.set(id, u);
    }
    return `<span class="cuI bdg" style="${box}">${cuBadge.get(id) ? `<img src="${cuBadge.get(id)}" alt="">` : ""}</span>`;
  }
  if (kind === "cap") return `<span class="cuI cuCap" style="${box}">${rankIns(20, sz * 1.2)}</span>`;
  if (kind === "star") { rkDefs(); return `<span class="cuI cuCap" style="${box}"><svg viewBox="0 0 24 24" width="${sz * .8}">${rkStar(12, 12, 11, "url(#rkMG)")}</svg></span>`; }
  const inner = {slot: "<i></i>", standby: "<b>SBY</b>", ace: "<b>Aa</b>"}[kind] || "";
  return `<span class="cuI ${kind}" style="${box}">${inner}</span>`;
}
const cuUnl = (rs, sz) => rs.map(r => `<span class="cuUn">${careerIco(r, sz)}${escH(careerName(r))}</span>`).join("");
const cuToGo = g => T("{n} to go", {n: nf.format(Math.max(0, g.need - g.into))});
// The strip's line: the next stop and what it opens (short: it is cut off on a phone).
function gLevelText(g){
  const un = careerAt(g.level + 1);
  return T("Next stop {t} · {u}", {t: rankTitle(g.level + 1), u: un.length ? careerName(un[0]) : cuToGo(g)});
}
// Your level's mini route: your stop, the plane on its way, the next stop; what that opens; the way to the whole route.
function careerMini(g){
  const lv = g.level, p = g.need ? Math.min(1, g.into / g.need) : 0, un = careerAt(lv + 1);
  return `<div class="cuMini" style="--p:${(p * 100).toFixed(1)}%"><div class="cuLn"><span class="cuD cur">${lv}</span><i><b></b>${CU_PLANE}</i><span class="cuD nx">${lv + 1}</span></div>` +
    `<div class="cuLb"><small>${escH(rankTitle(lv))}</small><small class="go">${escH(cuToGo(g))}</small><small>${escH(rankTitle(lv + 1))}</small></div></div>` +
    (un.length ? `<div class="cuStop">${careerIco(un[0], 34)}<span><small>${escH(T("At the next stop"))}</small><b>${escH(un.map(careerName).join(" · "))}</b></span></div>` : "") +
    `<button class="gHow" type="button" id="cuOpen">${escH(T("Your route · all {n} stops", {n: 20}))}<i>›</i></button>`;
}
// The route (a page of the club, from Your level): a stop per level down a line, solid where you've been and dashed
// ahead, each with its insignia, title, the points it opens at (ahead) and its unlocks; the plane between your stop and
// the next with what is left to go. Past Legend: the stops up to your next one.
var gRoute = false;                                     // var: showTab (earlier in the file) resets it
function careerRoute(g){
  const lv = g.level, p = g.need ? Math.min(1, g.into / g.need) : 0;
  const row = n => {
    const c = n < lv ? "done" : n === lv ? "cur" : n === lv + 1 ? "nx" : "lk", un = careerAt(n);
    return `<li class="${c}"${c === "cur" ? ` style="--p:${(p * 100).toFixed(1)}%;--pf:${p.toFixed(3)}"` : ""}><span class="cuD ${c}">${n}</span>` +
      `<span class="cuT"><b>${escH(rankTitle(n))}${c === "cur" ? `<small>${escH(T("You are here"))}</small>` : n > lv ? `<small>${nf.format(careerPts(n))}</small>` : ""}</b>` +
      `<span>${un.length ? cuUnl(un, 18) : `<span class="cuUn">${escH(T("The start"))}</span>`}</span></span>${rankIns(n, 30)}` +
      (c === "cur" ? `<span class="cuPl">${CU_PLANE}<em>${escH(cuToGo(g))}</em></span>` : "") + `</li>`;
  };
  return `<button type="button" class="cuBack" id="cuBack">‹ ${escH(T("Spotters' Club"))}</button>` + secPlate(T("Your route"),
    `<ol class="cuRt">${Array.from({length: Math.max(20, lv + 1)}, (_, i) => row(i + 1)).join("")}</ol>` +
    `<p class="sum">${escH(T("After Legend, a stop every {n} points, each a star on the cap.", {n: nf.format(careerPts(21) - careerPts(20))}))}</p>`, "cuPlate");
}
function careerOpen(){
  ctlSound.nav(); gRoute = true; renderGame();
  const cur = document.querySelector(".cuRt li.cur");
  if (cur) cur.scrollIntoView({block: "center"});
}
/* 1.110 (to-do #160, Dave's pick A): Settings → Styles as a gallery, a page over Settings like About (stylesCard hands
   over to it in the app; the TVs and the light version keep the 1.61 card). Tabs Board · Ticket · Badge (the league's
   switch), each a two-column grid of preview cards with IN USE, ✓ YOURS or 🔒 what unlocks it; Classic's colours and flaps
   have their own section, as they only show with the Classic board. A tap opens a card with a big preview, what it is,
   a bar towards its unlock and Use (off while locked). The board styles are drawn in their own colours and font
   (stLook lends them to the drawing), the tickets are gPassFill's with the era given, scaled down. */
let stTab = "board";
const ST_TABS = [["board", "Board"], ["ticket", "Ticket"], ["badge", "Badge"]];
const ST_TAB_OF = {theme: "board", palette: "board", finish: "board", ticket: "ticket", badge: "badge"};
const ST_SECS = {board: [["Board styles", ["theme"]], ["With the Classic board", ["palette", "finish"], "Colours and flaps only change with the Classic board."]],
  ticket: [["Ticket designs", ["ticket"], "The first medal of each metal wins a design."]], badge: [["Title badges", ["badge"]]]};
const ST_LOCK = `<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="5" y="11" width="14" height="10" rx="2"/><path d="M8 11V7a4 4 0 0 1 8 0v4"/></svg>`;
const ST_MEDAL = ["", "A silver medal", "A gold medal", "A platinum medal", "A diamond medal"];
// The sample plane on each ticket's preview: rarity, flight, airline and type, km.
const ST_TIX = {"": ["rare", "SQ 305", "Singapore Airlines · A350", 6.2], propage: ["uncommon", "LX 1579", "Swiss · A220", 5.4],
  jetage: ["rare", "SQ 305", "Singapore Airlines · A350", 6.2], magcard: ["common", "OS 411", "Austrian · A320", 3.1], holo: ["epic", "LH 9922", "Lufthansa · 747-8", 7.4]};
const ST_TIER_P = {common: 10, uncommon: 30, rare: 100, epic: 250, legendary: 500};
const ST_WHAT = {theme: "A board style: the flaps, the letters and the housing of the whole board.", palette: "Colours for the Classic board's letters and lights.",
  finish: "A finish for the Classic board's flaps.", badge: "A title badge on the board's logo and the app's icon."};
const ERA_WHAT = {"": "The ticket every plane comes in, as it is.", propage: "The 1950s: ruled cream card, red carbon ink, a serif heading and a conductor's punch.",
  jetage: "The 1970s: warm cream with round corners, a sunburst and three stripes.", magcard: "The 1990s: a white boarding pass with a security pattern and the brown magnetic stripe.",
  holo: "Pearl foil with a holographic patch."};
const stRuleShort = r => r.lvl ? T("Level {n}", {n: r.lvl}) : r.champ ? T("Last week's winner") : r.medal ? T(ST_MEDAL[r.medal] || "") : styleRuleText(r);
const stWhat = (k, id) => k === "ticket" ? T(ERA_WHAT[id] || "") + " " + T("Every plane's ticket and scan comes in it; a golden ticket stays gold.") : T(ST_WHAT[k] || "");
const stTag = (on, ok, r) => on ? `<i class="stUse">${escH(T("IN USE"))}</i>` : ok ? `<i class="stHave">✓ ${escH(T("YOURS"))}</i>` : `<i class="stLk">${ST_LOCK}${escH(stRuleShort(r))}</i>`;
function stylesPage(focusKind){
  if (ST_TAB_OF[focusKind]) stTab = ST_TAB_OF[focusKind];
  if (tab !== "settings") showTab("settings");
  $("t-styles").hidden = false; $("t-styles").scrollTop = 0;
  document.body.classList.add("aboutOpen");
  stylesRender();
}
function stylesHide(){
  if ($("t-styles").hidden) return;
  $("t-styles").hidden = true;
  if ($("t-about").hidden && $("t-log").hidden) document.body.classList.remove("aboutOpen");
}
function stylesRender(){
  const box = $("stylesBox"), g0 = styleGame(), kinds = new Map(styleKinds().map(([k, label, o]) => [k, [label, o]]));
  $("stPgCnt").textContent = stylesNote();
  const card = (k, [id, nm, rule]) => {
    const ok = styleOk(rule, g0, id), on = ok && styleVal(k) === id;
    return `<button type="button" class="stCd${on ? " on" : ""}${ok ? "" : " lk"}" data-k="${k}" data-id="${escH(id)}"><span class="stPic">` +
      (k === "ticket" ? stTixHtml(id, .46) : `<canvas data-th="${k}" data-id="${escH(id)}" aria-hidden="true"></canvas>`) +
      `</span><span class="stTx"><b>${escH(T(nm))}</b>${stTag(on, ok, rule)}</span></button>`;
  };
  box.innerHTML = `<div class="seg gSeg" role="group">${ST_TABS.map(([t, l]) => `<button type="button" data-stt="${t}" aria-pressed="${t === stTab}">${escH(T(l))}</button>`).join("")}</div>` +
    ST_SECS[stTab].map(([title, ks, note]) => {
      ks = ks.filter(k => kinds.has(k));
      return ks.length ? `<h4 class="stH4">${escH(T(title))}</h4>` + (note ? `<p class="stNote">${escH(T(note))}</p>` : "") + ks.map(k =>
        (ks.length > 1 ? `<h5 class="stH5">${escH(T(kinds.get(k)[0]))}</h5>` : "") + `<div class="stGrid">${kinds.get(k)[1].map(it => card(k, it)).join("")}</div>`).join("") : "";
    }).join("");
  for (const b of box.querySelectorAll("[data-stt]")) b.onclick = () => { if (stTab === b.dataset.stt) return; ctlSound.click(); stTab = b.dataset.stt; stylesRender(); };
  for (const c of box.querySelectorAll(".stCd")) c.onclick = () => stOpen(c.dataset.k, c.dataset.id);
  stThumbs(box);
}
// A ticket's preview: the sample plane's ticket in that era (gPassFill), scaled by s.
function stTixHtml(era, s){
  const [tier, fl, who, km] = ST_TIX[era] || ST_TIX[""], p = ST_TIER_P[tier];
  const el = gPassFill(document.createElement("div"), {kind: tier, band: T("WITHIN {k} KM", {k: gScanKm()}), bandR: T(TIER_UP[tier]) + " ★", who: [fl, who + " · " + distText(km)],
    lines: [[T("Sky view scan · {t} plane", {t: gTierT(tier)}), p, ""]], p, stub: T("SCAN"), era, life: 1e9});
  clearTimeout(el.outT);
  return `<span class="stTk" style="--s:${s}">${el.outerHTML}</span>`;
}
// An item opened: a sheet with the big preview, what it is, how far to its unlock, and Use.
function stOpen(k, id){
  const g0 = styleGame(), it = ((STYLES.find(x => x[0] === k) || [])[2] || []).find(x => x[0] === id);
  if (!it) return;
  const [, nm, rule] = it, ok = styleOk(rule, g0, id), on = ok && styleVal(k) === id, prog = ok ? null : stProgress(rule, g0);
  ctlSound.nav();
  cardOpen(`<div class="stOpen"><h3>${escH(T(nm))}</h3><p class="stWhat">${escH(stWhat(k, id))}</p>` +
    `<div class="stBig">${k === "ticket" ? stTixHtml(id, .96) : `<canvas data-th="${k}" data-id="${escH(id)}" aria-hidden="true"></canvas>`}</div>` +
    (ok ? "" : `<p class="stWhy">${ST_LOCK}${escH(styleRuleText(rule))}</p>` + (prog ? `<div class="stBar"><i style="width:${(prog[0] * 100).toFixed(1)}%"></i></div><p class="stProg">${escH(prog[1])}</p>` : "")) +
    ((k === "palette" || k === "finish") && !classicLook() ? `<p class="stWhy">${escH(T("Colours and flaps only change with the Classic board."))}</p>` : "") +
    `<button class="cBtn stGo" type="button" data-use${on || !ok ? " disabled" : ""}>${on ? escH(T("In use")) : ok ? escH(T("Use")) : ST_LOCK + escH(T("Locked"))}</button></div>`, el => {
    stThumbs(el);
    el.querySelector("[data-use]").onclick = () => {
      if (!ok || on) return;
      ctlSound.click();
      if (typeof draft !== "undefined" && draft) draft[k] = id;          // an open Settings keeps it on Save
      applySettings({...S, [k]: id});
      cardClose(); stylesRender(); stylesCellRefresh();
    };
  });
}
// How far to a locked item: [0..1, the words], or null (the league winner's has no bar).
function stProgress(rule, g0){
  if (!g0) return null;
  if (rule.lvl) {
    const t = careerPts(rule.lvl), a = Math.min(g0.points || 0, t);
    return [a / t, T("{a} of {b} points to level {n}, {t}", {a: nf.format(a), b: nf.format(t), n: rule.lvl, t: rankTitle(rule.lvl)})];
  }
  if (!rule.medal) return null;
  let best = null;                                       // the ladder closest to its rank of that metal
  for (const L of TROPHY_LADDERS) {
    const t = L[2][rule.medal], st = t && trophyLadder(g0, L);
    if (!st || st.have == null) continue;
    const f = Math.min(1, st.have / t[1]);
    if (!best || f > best[0]) best = [f, t, st.have];
  }
  return best && [best[0], T("Closest: {name}, {a} of {b}", {name: T(best[1][2]), a: nf.format(Math.min(best[2], best[1][1])), b: nf.format(best[1][1])})];
}
// The previews of board styles, colours, flaps and badges (canvas[data-th]); again once the styles' fonts are in.
let stFonts = 0;
function stThumbs(root){
  for (const cv of root.querySelectorAll("canvas[data-th]")) {
    const k = cv.dataset.th, id = cv.dataset.id;
    stylesThumb(cv, k === "badge" ? {theme: S.theme, palette: S.palette, finish: S.finish, badge: id} : {theme: k === "theme" ? id : "classic",
      palette: k === "palette" ? id : "", finish: k === "finish" ? id : "", badge: ""}, k === "badge");
  }
  if (stFonts) return;
  stFonts = 1;
  const again = () => { stFonts = 2; for (const el of [$("t-styles"), $("cardBox")]) if (el && !el.hidden) stThumbs(el); };
  Promise.race([Promise.all([...new Set(Object.values(THEMES).map(t => t.font))].map(f => document.fonts.load(`700 40px ${f}`))), new Promise(r => setTimeout(r, 2500))]).then(again, again);
}
// A look's colours and font: its board style, with a palette only on Classic.
function stTheme(look){
  const t = THEMES[look.theme] || THEMES.classic, P = (!look.theme || look.theme === "classic") && PALETTES[look.palette];
  return P ? {...t, ink: P.ink, accent: P.accent} : t;
}
// Draws with another look for a moment: the settings, flaps, colours and font that tile() and pictogram() read, put back after.
function stLook(look, fn){
  const keep = {S, flap: FLAP.slice(), ink: COL.ink, amber: COL.amber, font: FONT}, Th = stTheme(look);
  S = {...S, theme: look.theme || "classic", palette: look.palette || "", finish: look.finish || ""};
  FLAP.splice(0, 4, ...Th.flap); COL.ink = Th.ink; COL.amber = Th.accent; FONT = Th.font;
  try { return fn(Th); } finally { S = keep.S; FLAP.splice(0, 4, ...keep.flap); COL.ink = keep.ink; COL.amber = keep.amber; FONT = keep.font; }
}
// A preview: the housing's metal, three flaps (the logo square and the title word too when there is room) and a line in
// the accent colour; a badge's: the logo square with it. The flaps go into the tile cache under a key of their own.
function stylesThumb(cv, look, badgeOnly){
  const w = cv.clientWidth, h = cv.clientHeight;
  if (!w || !h) return;
  const d = Math.min(3, window.devicePixelRatio || 1);
  cv.width = Math.round(w * d); cv.height = Math.round(h * d);
  const g = cv.getContext("2d");
  g.setTransform(d, 0, 0, d, 0, 0);
  stLook(look, Th => {
    const m = Th.metal, bg = g.createLinearGradient(0, 0, 0, h);
    bg.addColorStop(0, m[0]); bg.addColorStop(.5, m[1]); bg.addColorStop(1, m[2]);
    g.fillStyle = bg; g.fillRect(0, 0, w, h);
    if (badgeOnly) { const s = h * .62; pictogram(g, (w - s) / 2, (h - s) / 2, s, look.badge || ""); return; }
    const fh = Math.min(h * .56, w / (w > 2.2 * h ? 7.5 : 3.9)), fw = fh * .66, gap = fw * .14, y = (h - fh) / 2 - h * .04, pad = h * .18, logo = w > fh * 5.2;
    const x0 = logo ? w - pad - 3 * fw - 2 * gap : (w - 3 * fw - 2 * gap) / 2;
    if (logo) {
      pictogram(g, pad, y, fh, "");
      const room = x0 - pad - fh - 2 * gap * 2, word = T("Overhead (board style)");
      if (room > fh) {
        g.font = `700 ${Math.round(fh * .5)}px ${Th.font}`; g.fillStyle = Th.accent; g.textBaseline = "middle"; g.textAlign = "left";
        const sx = Math.min(1, room / Math.max(1, g.measureText(word).width));
        g.save(); g.translate(pad + fh + gap * 2, y + fh / 2); g.scale(sx, 1); g.fillText(word, 0, 0); g.restore();
      }
    }
    [..."747"].forEach((ch, i) => {
      const f = {kind: "chars", n: 1, style: `st:${look.theme}/${look.palette}/${look.finish}/${stFonts}`, pw: Math.round(fw * d), ph: Math.round(fh * d), cw: fw, ch: fh};
      g.fillStyle = "#060607"; rr(g, x0 + i * (fw + gap) - 2, y - 2, fw + 4, fh + 4, 3); g.fill();
      g.drawImage(tile(f, ch), x0 + i * (fw + gap), y, fw, fh);
    });
    g.fillStyle = Th.accent; rr(g, x0, y + fh + h * .1, 3 * fw + 2 * gap, Math.max(2, h * .035), 1); g.fill();
  });
}
// 1.78.1: the strip follows live location at once (Settings, a place picked, another device's change, the start); it
// was redrawn only with the next points, up to a minute later.
let gStripLive = null;
setInterval(() => { if (gme && gStripLive != null && gStripLive !== !!S.live) { gStripRender(gme); gRefresh(true); } }, 300);
function gStripRender(g, anim){
  const box = $("gStrip");
  if (box.hidden || !g) return;
  const off = !S.live;
  gStripLive = !off;
  box.classList.toggle("off", off);
  if (!anim) gTotSet(g.points);
  const sby = !off && gSbyUsed(g);                                  // 1.104: the day after a standby, the line says so in amber
  box.classList.toggle("sby", !!sby);
  $("gLvTxt").textContent = off ? T(liveOk() ? "Not scoring · live location is off" : "Points only come with live location")
    : sby ? T("Standby used · streak goes on, day {n}", {n: sby}) : gLevelText(g);
  const rk = rankIns(g.level, 34, {wings: g.wings});                 // 1.102: the rank insignia
  if ($("gRk").dataset.h !== rk) { $("gRk").dataset.h = rk; $("gRk").innerHTML = rk; }
  $("gBarI").style.width = (g.need ? Math.min(100, g.into / g.need * 100) : 0).toFixed(1) + "%";
  $("gRank").innerHTML = gGoing ? `<i class="gSpin"></i>${escH(T("Going live"))}` : off && liveOk() ? escH(T("Go live")) : g.rank ? `#${g.rank}` + (g.was && g.was > g.rank ? ' <em>▲</em>' : g.was && g.was < g.rank ? ' <em class="dn">▼</em>' : "")
    : escH(T("Club"));
}
// Points came in: the chip shows +N, the +N flies to the bar, the bar fills, the total rolls up.
function gGain(prev, g){
  const box = $("gStrip"), n = g.points - prev.points;
  gAnimT.forEach(clearTimeout); gAnimT = [];
  $("gPlus").textContent = "+" + nf.format(n);
  $("gTok").textContent = "+" + nf.format(n);
  const lvUp = g.level > prev.level, from = prev.need ? prev.into / prev.need * 100 : 0, to = lvUp ? 100 : g.need ? g.into / g.need * 100 : 0;
  const bar = $("gBarI").getBoundingClientRect(), chip = $("gChip").getBoundingClientRect();
  box.style.setProperty("--tx", Math.round(bar.left + bar.width * to / 100 - chip.left - chip.width / 2) + "px");
  $("gBarI").style.width = from.toFixed(1) + "%"; $("gBarG").style.left = from.toFixed(1) + "%"; $("gBarG").style.width = "0";
  box.classList.remove("flip", "fly", "gain"); void box.offsetWidth; box.classList.add("flip");
  gAnimT.push(setTimeout(() => box.classList.add("fly"), 1550));
  gAnimT.push(setTimeout(() => {
    box.classList.add("gain"); $("gBarG").style.width = Math.max(0, to - from).toFixed(1) + "%";
    gTotSet(g.points, true); gCoins();
  }, 2050));
  gAnimT.push(setTimeout(() => {
    box.classList.remove("flip", "fly", "gain"); $("gBarG").style.width = "0"; gStripRender(g);
    if (lvUp) gLevelUp(g, prev.level);
  }, 3500));
}
async function gRefresh(force){
  if (!gameOk() || gBusy || document.hidden) return;
  const every = S.live ? 15000 : 60000;
  if (!force && Date.now() - gmeAt < every - 500) return;
  gBusy = true; gmeAt = Date.now();
  try {
    const g = await fetchJSON(`${relay()}/game/me?since=${gAwAt || 1}`, {}, 8000), prev = gme;
    gme = g;
    gAwards(g.aw, !gAwAt);
    fsBar();                                                  // 1.103: the flight school's bar on Now
    gTixSync(g.scan);
    if (prev && g.points > prev.points && tab !== "game") gGain(prev, g);
    else gStripRender(g);
    if (prev && g.rank && prev.rank && g.rank < prev.rank && g.below) toast(T("You passed {n} in the league ▲", {n: g.below}));
    if (prev && g.level > prev.level && !(g.points > prev.points && tab !== "game")) gLevelUp(g, prev.level);
    if (tab === "game") renderGame();
  } catch {} finally { gBusy = false; }
}
/* 1.96 (to-do #127, Dave's pick B): every award as it happens, on a pass like Sky view's boarding pass that slides up
   from below (over the tab bar; in Sky view over its compass): the passive points small (several that come together on
   one), a scan with its extras, the daily streak at the day's first scan, and the first plane past a rarity's limit
   (later ones stay quiet). Recent points lists the same lines (gAwLine). The relay sends the awards since the newest one
   shown (/game/me?since=, relay 76); a scan's come with its answer (gLockOn). A tap puts a pass away. */
let gAwAt = 0;
const BINGO_LINE = ["Top row", "Middle row", "Bottom row", "Left column", "Middle column", "Right column", "Diagonal", "Diagonal"];
const TIER_UP = {common: "COMMON", uncommon: "UNCOMMON", rare: "RARE", epic: "VERY RARE", legendary: "SPECIAL"};
const gPlus0 = n => n ? gPlus(n) : "0";
const gTierT = t => T(TIER_NAME[t] || "Uncommon");
// An award's line, as on its pass and in Recent points: [what, points, class ("x" an extra, "stk" the streak, "lim" none)].
function gAwLine(a, f, tix){
  const t = gTierT(a.tier), R = gRules(), lim = (R && R.limit[a.tier]) || 0;
  if (a.k === "scan" && a.gold && tix) return [T("{t} plane {p} ×2", {t, p: gPlus(a.full || a.p / 2)}), a.p, "gold"];     // 1.101: on its ticket
  if (a.k === "pass") return [T("{t} plane", {t}) + (lim ? " · " + T("{n} of {m} today", {n: nf.format(a.n || 1), m: nf.format(lim)}) : ""), a.p, ""];
  if (a.k === "limit") return [T("{t} limit reached: {m} of {m} today", {t, m: nf.format(lim || (a.n || 1) - 1)}), 0, "lim"];
  if (a.k === "scan" && a.gold) return [T("Sky view scan · {t} plane ×2 golden", {t}), a.p, "gold"];    // 1.101: a golden ticket's
  if (a.k === "scan") return [a.r === 2 ? T("Scan · {t} topped up to {f}", {t, f: nf.format(a.full || 0)}) : T("Sky view scan · {t} plane", {t}), a.p, ""];
  if (a.k === "new") return [T(a.w === "airline" ? "New airline · {n}" : "New type · {n}", {n: a.w === "airline" ? (f && f.airline) || a.n : (f && f.type) || a.n}), a.p, "x"];
  if (a.k === "streak") return [T("Daily streak · day {n}", {n: a.n}), a.p, "stk"];
  if (a.k === "country") return [T("New country · {c}", {c: ppName(a.n)}), a.p, "x"];     // 1.107 (relay 90): the passport
  if (a.k === "loyalty") return [((f && f.airline) || lyName(a.n)) + " · " + T(LY_NAME[a.m] || "Silver"), a.p, "x mst ly" + (a.m || 1)];   // 1.106
  if (a.k === "mastery") return [((f && f.type) || typeLabel(a.n)) + " · " + T(MST_NAME[a.m] || "Bronze"), a.p, "x mst mk" + (a.m || 1)];   // 1.105
  // 1.100 (relay 83, to-do #147): a bingo line, the full card, a trophy (a rank by its medal), paid with this plane
  if (a.k === "bingo") return [T("Bingo line · {l}", {l: T(BINGO_LINE[a.n] || "Line")}), a.p, "x"];
  if (a.k === "card") return [T("Full bingo card"), a.p, "x"];
  if (a.k === "school") { const m = SCHOOL.find(x => x[0] === a.n); return [T("Flight school · {m}", {m: m ? T(m[1]) : a.n}), a.p, "x"]; }   // 1.103
  if (a.k === "trophy") { const tr = TROPHY_TIER.get(a.n), m = TROPHY_MEDALS[a.m];
    return [tr && m ? T("Trophy · {name} · {m}", {name: T(tr.name), m: T(m)}) : T("Trophy · {name}", {name: trophyText(a.n)[0]}), a.p, "x"]; }
  return [T("Points"), a.p, ""];
}
// The passes' box, at the bottom of the screen, or of Sky view while it is open (1.98: moved there when it opens).
function gAwsBox(){
  const host = $("arView") && !$("arView").hidden ? $("arView") : document.body;
  let box = $("gAws");
  if (!box) { box = document.createElement("div"); box.id = "gAws"; }
  if (box.parentNode !== host) host.appendChild(box);
  return box;
}
function gPop(o){
  const box = gAwsBox(), el = gPassFill(document.createElement("div"), o);
  box.appendChild(el);
  // up to three on screen; a plane's ticket pushed out by another pass (not by a newer ticket) comes back (gTixBack)
  while (box.children.length > 3) { const old = box.firstChild; old.remove(); if (old.dataset.tix && !o.tix) gTixOut.add(old); }
  gTixStack();
  return el;
}
// 1.110 (to-do #159): the ticket design in use (Settings → Styles → Ticket; "" the plain ticket), only while it is yours.
function tixEra(){
  const id = S.ticket || "", it = id && STYLES.find(x => x[0] === "ticket")[2].find(x => x[0] === id);
  return it && styleOk(it[2], styleGame(), id) ? id : "";
}
// An era's ornaments, after the band: the 1950s heading and serial number, the 1990s form's head, the sunburst (the
// punch hole and the hologram's patch go on the stub).
function tixEraHtml(era, o){
  if (era === "propage") {
    const n = String(1e9 + Math.abs([...String(o.tix || (o.who && o.who[0]) || o.band)].reduce((h, c) => h * 31 + c.charCodeAt(0) | 0, 7)) % 9e8);
    return `<div class="ttl"><span>${escH(T("Passenger ticket"))}</span><span>No. ${n.slice(1, 5)} ${n.slice(5, 8)} ${n.slice(8)}</span></div>`;
  }
  if (era === "magcard") return `<div class="hd"><span>${escH(T("BOARDING PASS"))}</span><span>ATB 2</span></div>`;
  return era === "jetage" ? `<i class="eo sun"></i>` : "";
}
// A pass's paper (1.98: also a plane's ticket, and that ticket made into the scan's at the scan): o.life ms on screen.
// 1.110: in the ticket design in use (o.era instead, if given; the gallery's previews), a golden ticket always gold foil.
function gPassFill(el, o){
  el.className = "gAw" + (o.tix ? " tix" : "") + (o.rip ? " rip" + (o.rip > 1 ? " rip2" : "") : "");
  if (o.tix) el.dataset.tix = o.tix; else delete el.dataset.tix;
  const nx = o.gold ? ` data-nx="${escH(T("(no ×2)"))}"` : "", era = o.gold ? "" : o.era != null ? o.era : tixEra();
  el.innerHTML = `<div class="pF ${o.kind || "uncommon"}${o.gold ? " gold" : ""}${era ? " e-" + era : ""}"><div class="main"><div class="band"><span>${escH(o.band)}</span><span>${escH(o.bandR || "")}</span></div>` +
    tixEraHtml(era, o) + (o.body || "") + (o.who ? `<div class="who"><b>${escH(o.who[0])}</b><span>${escH(o.who[1] || "")}</span></div>` : "") + (o.route || "") +
    (o.lines && o.lines.length ? `<div class="lns">${o.lines.map(([l, n, x]) => `<div class="${x}"><span${String(x).split(" ")[0] === "x" ? nx : ""}>${escH(l)}</span><b>${gPlus0(n)}</b></div>`).join("")}</div>` : "") +
    (o.note ? `<div class="nt">${escH(o.note)}</div>` : "") +
    (o.ly ? `<div class="lyFF ly${o.ly.t}"><b>${escH(o.ly.code)}</b><i>·</i><em>${escH(T(LY_NAME[o.ly.t]))}</em></div>` : "") + (o.sky ? `<button type="button" class="scn">${SKY_ICO}<span>${escH(T("Scan in Sky view"))}</span><i>›</i></button>` : "") +
    (o.gold ? `<div class="gl"></div><i class="sp" style="left:222px;top:58px">✦</i><i class="sp" style="left:150px;top:12px">✦</i>` : "") +
    `</div><div class="stub"><small>${escH(o.stub || T("POINTS"))}</small><b>${gPlus0(o.p)}</b>${o.gold ? `<i class="x2">×2</i>` : ""}<em></em>${era === "propage" ? `<i class="punch"></i>` : era === "holo" ? `<i class="patch"></i>` : ""}</div></div>`;
  const out = el.out = () => {
    if (!el.isConnected || el.classList.contains("out")) return;
    el.classList.add("out"); setTimeout(() => { el.remove(); gTixStack(); gTixBack(); }, 350);
  };
  el.onclick = () => {
    if (el.swiped) { el.swiped = false; return; }
    if (!o.sky) return out();
    audioInit(); if (arOn) ctlSound.nav(); arOpenAt(o.sky.hex, o.sky.flight);   // the ticket stays; in Sky view it only picks the plane out (opening it sounds by itself)
  };
  const life = o.life || 6500;
  el.until = Date.now() + life; clearTimeout(el.outT); el.outT = setTimeout(out, life);
  return el;
}
const SKY_ICO = `<svg class="skyIco" viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="7.5" fill="none" stroke="currentColor" stroke-width="2"/><path d="M12 2v5M12 17v5M2 12h5M17 12h5" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg>`;
const gWho = (f, km) => [f.flight || NA, [f.airline, f.type, km != null ? distText(km) : ""].filter(Boolean).join(" · ")];
/* 1.98 (to-do #146, Dave's picks): a plane that comes within the scan's circle (10 km; the relay's list, /game/me "scan")
   gets a ticket, once: the boarding pass with what a scan gives now (only what is sure: the plane's full points, a type or
   an airline new to the game), their total on the stub, the daily streak as a line of its own (not in the total) while
   nothing was scanned today, and "Scan in Sky view" (a tap anywhere on it: Sky view with the plane picked out). It folds
   away after 10 s, when it is swiped away or its plane is scanned; it doesn't come back for that plane (its ★ in Sky view
   stays). Newest on top, the older ones peeking out under it; a fourth ticket puts the oldest away, a shorter pass only
   for a while (gTixOut, gTixBack). At the scan the plane's ticket becomes the scan's (gScanPops). */
const TIX_MS = 10000, TIX_KEY = "od.tix";
const gTixOut = new Set();
let gTixSeen = null;                                  // hex → when its ticket came up (kept 2 h, so a reload doesn't show it again)
function gTixSync(list){
  if (!Array.isArray(list)) return;
  const box = $("gAws"), now = Date.now(), on = new Set(list.map(x => x.hex));
  for (const el of box ? [...box.children] : []) if (el.dataset.tix && !on.has(el.dataset.tix)) el.out();    // scanned, or gone
  if (!S.live) return;
  if (!gTixSeen) { try { gTixSeen = new Map(Object.entries(JSON.parse(localStorage.getItem(TIX_KEY) || "{}"))); } catch { gTixSeen = new Map(); } }
  let changed = false;
  for (const [h, t] of gTixSeen) if (now - t > 7200000) { gTixSeen.delete(h); changed = true; }
  for (const x of list.slice().reverse()) {          // the relay's list is newest first: the newest ends on top
    if (gTixSeen.has(x.hex)) continue;
    gTixSeen.set(x.hex, now); changed = true;
    gTixShow(x);
  }
  if (changed) try { localStorage.setItem(TIX_KEY, JSON.stringify(Object.fromEntries(gTixSeen))); } catch {}
}
function gTixShow(x){
  const f = fromRelay(x), R = gRules(), can = x.can || {};
  const gold = !!x.gold, lines = [gAwLine({k: "scan", r: 4, tier: x.tier, p: x.full * (gold ? 2 : 1), full: x.full, gold}, f, true)];   // 1.100: golden, ×2
  if (can.type) lines.push(gAwLine({k: "new", w: "type", p: can.type, n: x.typeCode}, f));
  if (can.airline) lines.push(gAwLine({k: "new", w: "airline", p: can.airline, n: String(x.callsign || "").slice(0, 3)}, f));
  const n = gme && !gme.scannedToday && R ? (gme.streak || 0) + 1 : 0;
  gPop({tix: x.hex, kind: x.tier, band: gold ? T("GOLDEN TICKET · {k} KM", {k: gScanKm()}) : T("WITHIN {k} KM", {k: gScanKm()}), bandR: T(TIER_UP[x.tier] || "UNCOMMON") + " ★", who: gWho(f, x.km), lines,
    note: n ? T("Your first scan today adds the daily streak: +{p}.", {p: nf.format(R.streak * n)}) : "", stub: gold ? T("GOLDEN") : T("SCAN"), gold,
    p: lines.reduce((s, l) => s + l[1], 0), sky: {hex: x.hex, flight: f.flight}, life: TIX_MS, ly: lyTicket(airlineOf(x).icao, (((lbData() || {}).game || {}).wallet || {})[airlineOf(x).icao])});
}
// A ticket pushed out by a shorter pass comes back at the bottom once there is room, while its 10 s and its plane last.
function gTixBack(){
  const box = $("gAws");
  if (!box) return;
  for (const el of [...gTixOut]) {
    if (box.children.length >= 3) break;
    gTixOut.delete(el);
    if (Date.now() > el.until - 1000 || !gScanSet().has(el.dataset.tix) || box.querySelector(`[data-tix="${el.dataset.tix}"]`)) continue;
    box.insertBefore(el, box.firstChild);
    clearTimeout(el.outT); el.outT = setTimeout(el.out, el.until - Date.now());
  }
  gTixStack();
}
// Tickets one on another: the older peeks out 12 px under the newer (and a little smaller, as further back).
function gTixStack(){
  const box = $("gAws");
  if (!box) return;
  const els = [...box.children];
  els.forEach((el, i) => {
    let k = 0;
    for (let j = i + 1; j < els.length && els[j].dataset.tix && el.dataset.tix; j++) k++;
    el.classList.toggle("under", k > 0);
    el.style.marginTop = k ? -el.offsetHeight + "px" : "";
    el.style.scale = k ? String(1 - .05 * k) : "";
    el.style.zIndex = String(i + 1);
  });
}
function gAwards(list, quiet){
  if (!Array.isArray(list) || !list.length) return;
  const fresh = list.filter(a => a.t > gAwAt);
  gAwAt = Math.max(gAwAt, ...list.map(a => a.t));
  if (!quiet) for (const a of fresh.filter(x => x.k === "school")) fsStamp(a);     // 1.103: live location or not
  if (quiet || !S.live) return;
  // 1.98 (to-do #146): the passive points show only on the strip (+N); a plane within the scan's circle gets its ticket
  for (const a of fresh.filter(x => x.k === "limit" && x.first)) {
    const f = fromRelay(a), R = gRules(), m = (R && R.limit[a.tier]) || (a.n || 1) - 1, t = gTierT(a.tier);
    gPop({kind: "no", band: T("NO POINTS · LIMIT"), bandR: `${T(TIER_UP[a.tier] || "UNCOMMON")} ${m}/${m}`, who: gWho(f, a.km), lines: [gAwLine(a, f)],
      note: T("{t} planes score again from {h}. The other rarities still count.", {t, h: gme && gme.resets ? hhmm(new Date(gme.resets)) : "03:00"}), p: 0});
  }
}
// Sky view's scan: the scan's pass (the top-up and the extras), then the streak's on top of it at the day's first scan.
// Returns the passes that tear their stub off, in the order they do (1.97.8: the streak's tears a moment after the scan's).
// 1.98: the plane's ticket, if it is on screen, becomes the scan's pass (on top, 10 s from the scan); both stay 10 s.
function gScanPops(r){
  const f = fromRelay(r), lines = r.lines || [{k: "scan", p: r.bonus, tier: r.tier, full: r.full}];
  const main = lines.filter(a => a.k !== "streak"), stk = lines.find(a => a.k === "streak");
  const o = {kind: r.tier || "uncommon", band: T("SKY VIEW · SCANNED"), bandR: T(TIER_UP[r.tier] || "UNCOMMON") + " ★", who: gWho(f, r.km),
    lines: main.map(a => gAwLine({tier: r.tier, ...a}, f, true)), stub: r.gold ? T("GOLDEN") : T("SCAN"), p: main.reduce((s, a) => s + a.p, 0), rip: true, life: TIX_MS, gold: !!r.gold,
    ly: r.airline ? lyTicket(r.airline.code, r.airline.scans) : null, route: ppRoute(r.route)};    // 1.107: the route, a new country marked
  const w = r.airline && ((lbData() || {}).game || {}).wallet;
  if (w) w[r.airline.code] = r.airline.scans;
  const box = $("gAws"), tix = box && [...box.children].find(el => el.dataset.tix === String(r.hex) && !el.classList.contains("out"));
  let pass;
  if (tix) {
    gTixOut.delete(tix);
    if (tix !== box.lastChild) box.appendChild(tix);
    pass = gPassFill(tix, o); gTixStack();
  } else pass = gPop(o);
  setTimeout(() => ppNew(r), fsStill() ? 0 : 1400);                 // 1.107: a country new to the passport, over the ticket
  if (!stk) return [pass];
  const wd = (new Date(Date.now() - 3 * 3600000).getDay() + 6) % 7, R = gRules(), per = (R && R.streak) || stk.p / stk.n;
  const fmt = new Intl.DateTimeFormat(LANG, {weekday: "narrow"});
  const days = Array.from({length: 7}, (_, i) => `<i class="${i === wd ? "now" : i < wd && i > wd - stk.n ? "on" : ""}">${escH(fmt.format(new Date(2026, 9, 26 + i, 12)))}</i>`).join("");
  const pass2 = gPop({kind: "stk", band: T("DAILY STREAK"), bandR: T("DAY {n} THIS WEEK", {n: stk.n}), body: `<div class="days">${days}</div>`, stub: T("STREAK"), p: stk.p, rip: 2, life: TIX_MS,
    note: wd < 6 ? T("Your first scan today. Scan a plane tomorrow for +{p}.", {p: nf.format(per * (stk.n + 1))}) : T("It starts again on Monday at 03:00, with the league.")});
  return [pass, pass2];
}
// A little shower of coins when points land (with the button sounds on).
function gCoins(){
  if (!S.sound || !actx || actx.state !== "running") return;
  const out = actx.createGain(); out.gain.value = .3; out.connect(sfxOut());
  for (let i = 0; i < 4; i++) {
    const t = actx.currentTime + .02 + i * .07, o = actx.createOscillator(), g = actx.createGain();
    o.type = "triangle"; o.frequency.value = 2600 + (i % 3) * 400;
    g.gain.setValueAtTime(0, t); g.gain.linearRampToValueAtTime(.5, t + .005); g.gain.exponentialRampToValueAtTime(.0001, t + .12);
    o.connect(g).connect(out); o.start(t); o.stop(t + .15);
  }
}
// 1.109 (to-do #152, Dave's pick B): the level-up is an arrival on the route: the plane flies from the last stop to the
// new one, a luggage tag for each thing it opened (from CAREER; the levels passed at once too), the next stop, and Try
// it (a style: the Styles card at its row; anything else: the club). Reduced motion: all of it standing still.
let gLvT = 0;
function gLevelUp(g, from){
  let box = $("gLvUp");
  if (box && !box.hidden && box.classList.contains("fsW")) { setTimeout(() => gLevelUp(g, from), 2000); return; }   // 1.103: after the wings
  if (!box) { box = document.createElement("div"); box.id = "gLvUp"; box.setAttribute("role", "dialog"); document.body.appendChild(box); }
  const lv = g.level, was = Math.max(1, Math.min(lv - 1, from || lv - 1)), got = [];
  for (let n = was + 1; n <= lv; n++) got.push(...careerAt(n));
  const tags = got.slice(0, 3).map((r, i) => `<div class="cuTag" style="--r:${i % 2 ? 1.5 : -2}deg;--d:${(1.1 + i * .25).toFixed(2)}s">${careerIco(r, 48)}` +
    `<span><small>${escH(T("Lv{n} · Unlocked", {n: r[0]}))}</small><b>${escH(careerName(r))}</b><span>${escH(T(CAREER_KIND[r[1]] || ""))}</span></span></div>`).join("");
  box.innerHTML = `<div class="lvBox cuArrive"><span class="eyebrow">${escH(T("Level up"))}</span>${rankIns(lv, 48, {wings: g.wings})}` +
    `<h3>${escH(T("Arrived at {t}", {t: rankTitle(lv)}))}</h3>` +
    `<div class="cuArr"><span class="cuD done">${was}</span><i>${CU_PLANE}</i><span class="cuD now">${lv}</span><i class="f"></i></div>` + tags +
    `<p>${escH(T("Next stop: {t} · {n}", {t: rankTitle(lv + 1), n: nf.format(careerPts(lv + 1))}))}</p>` +
    `<div class="cuTry">${got.length ? `<button class="cBtn" type="button" data-try>${escH(T("Try it"))}</button>` : ""}<button type="button" class="cuLater" data-later>${escH(T("Later"))}</button></div></div>`;
  box.hidden = false;
  gJingle();
  clearTimeout(gLvT);
  const close = () => { clearTimeout(gLvT); box.hidden = true; };
  box.onclick = e => { if (e.target === box) close(); };
  box.querySelector("[data-later]").onclick = () => { ctlSound.click(); close(); };
  const t = box.querySelector("[data-try]");
  if (t) t.onclick = () => {
    const r = got[0], style = STYLES.some(([k]) => k === r[1]);
    close(); ctlSound.nav();
    if (style) stylesCard(r[1]);
    else { gRoute = false; showTab("game"); window.scrollTo(0, 0); }
  };
  gLvT = setTimeout(close, 20000);
}
// The fairground prize jingle (a lock-on, a level up): four rising chime notes and a bright chord.
function gJingle(){
  if (!(S.sound || S.chimes) || !actx || actx.state !== "running") return;
  const out = actx.createGain(), t0 = actx.currentTime + .03; out.gain.value = .45; out.connect(sfxOut());
  const tone = (f, t, dur, vol) => { const o = actx.createOscillator(), g = actx.createGain(); o.type = "triangle"; o.frequency.value = f;
    g.gain.setValueAtTime(0, t); g.gain.linearRampToValueAtTime(vol, t + .006); g.gain.exponentialRampToValueAtTime(.0001, t + dur); o.connect(g).connect(out); o.start(t); o.stop(t + dur + .05); };
  [[1047, 0], [1319, .09], [1568, .18], [2093, .27]].forEach(([f, d]) => tone(f, t0 + d, .35, .3));
  [1568, 2093, 2637].forEach(f => tone(f, t0 + .42, 1.1, .14));
}
function gRip(){
  if (!(S.sound || S.chimes) || !actx || actx.state !== "running") return;
  if (sample("tear", actx.currentTime, .9)) return;                  // 1.97.8: a real paper rip; the noise below until it is decoded
  const n = actx.createBuffer(1, actx.sampleRate * .25, actx.sampleRate), d = n.getChannelData(0);
  for (let i = 0; i < d.length; i++) d[i] = (Math.random() * 2 - 1) * (Math.random() < .35 ? 1 : .25) * (1 - i / d.length);
  const src = actx.createBufferSource(), bp = actx.createBiquadFilter(), g = actx.createGain();
  src.buffer = n; bp.type = "bandpass"; bp.frequency.value = 2400; bp.Q.value = .7; g.gain.value = .5;
  src.connect(bp).connect(g).connect(sfxOut()); src.start();
}
// 1.101 (to-do #148, Dave's pick B, "Bell sparkle"): a golden ticket's tear: the paper rip, then eight bells climbing a
// pentatonic scale (E6 to A7, 55 ms apart) onto a held bright chord with three high glints. Levelled like 1.97.2: the rip
// stays its loudest moment, the bells' loudest 300 ms a touch above the jingle's.
function gGold(){
  if (!(S.sound || S.chimes) || !actx || actx.state !== "running") return;
  const t = actx.currentTime, out = actx.createGain();
  if (!sample("tear", t, .9)) gRip();
  out.gain.value = .56; out.connect(sfxOut());
  const bell = (f, at, amp, dec, parts, type) => {
    for (const [mult, a] of parts) {
      const o = actx.createOscillator(), g = actx.createGain();
      o.type = mult === 1 ? type : "sine"; o.frequency.value = f * mult;
      g.gain.setValueAtTime(0, at); g.gain.linearRampToValueAtTime(amp * a, at + .004); g.gain.exponentialRampToValueAtTime(amp * a * .002, at + dec / mult ** .5);
      o.connect(g).connect(out); o.start(at); o.stop(at + dec + .05);
    }
  };
  [1319, 1568, 1760, 2093, 2349, 2637, 3136, 3520].forEach((f, i) => bell(f, t + .12 + i * .055, .12 + i * .01, .5, [[1, 1], [2.76, .3], [5.4, .08]], "triangle"));
  for (const f of [1047, 1319, 1568, 2093]) bell(f, t + .58, .07, 1.6, [[1, 1], [2, .25], [3, .08]], "triangle");
  [4186, 3520, 4699].forEach((f, i) => bell(f, t + .66 + i * .09, .03, .3, [[1, 1]], "sine"));
}
// The Game page: the level, the league (this week or all time), today, then the collections, bingo and trophies.
async function gLeagueLoad(force){
  if (!gameOk() || (!force && Date.now() - gLeagueAt < 30000)) return;
  gLeagueAt = Date.now();
  try { gLeague = await fetchJSON(`${relay()}/game/league`, {}, 8000); } catch {}
  if (tab === "game") renderGame();
}
function renderGame(){
  if (tab !== "game") return;
  const g = gme, all = lbData() || {}, g0 = all.game;
  if (!g) { $("gameBox").innerHTML = `<p class="sum">${escH(T("Loading …"))}</p>`; return; }
  if (gRoute) {                                              // 1.109: Your route, a page of the club
    const box = $("gameBox"), h = careerRoute(g);
    if (box.dataset.h !== h) { box.dataset.h = h; box.innerHTML = h; }
    $("cuBack").onclick = () => { ctlSound.nav(); gRoute = false; renderGame(); window.scrollTo(0, 0); };
    return;
  }
  // 1.79 (Dave's pick A): one card for the level, then today's points, your place this week and the streak as three
  // numbers; the rules behind How points work (a card). The league under it, its week and all-time switch beside it.
  // 1.83 (Dave): each part on a plate of its own, as Settings' (secPlate)
  let h = secPlate(T("Your level"), `<div class="gBig"><b>${escH(T(g.title))}</b><span class="rkLv">${escH(T("Level {n}", {n: g.level}))}${rankIns(g.level, 40, {wings: g.wings})}</span></div>` +
    careerMini(g) +                                          // 1.109: the mini route, the next stop, Your route
    (S.live ? "" : `<span class="gRule gOff">${escH(T("Points only come with live location (Settings → Location): planes within {k} km of you score, and within {s} km you can scan them.", {k: gKm(), s: gScanKm()}))}</span>`) + gSbyHtml(g) +
    `<div class="gTiles"><div><b>${nf.format(g.today || 0)}</b><span>${escH(T("Points today"))}</span></div>` +
    // 1.96: This week is the week's points, as in the league (it was your place there; that stays beside it)
    `<div><b>${nf.format(g.week || 0)}</b><span>${escH(g.rank ? T("This week · #{n}", {n: g.rank}) : T("This week"))}</span></div><div><b>${g.streak || 0}</b><span>${escH(T("Day streak"))}</span></div></div>` +
    gLimHtml(g) + `<button class="gHow" type="button" id="gHow">${escH(T("How points work"))}<i>›</i></button>`, "gHero");
  const L = gLeague, rows = L ? (gAll ? L.allTime : L.rows) : null;
  let lg = `<div class="seg gSeg" role="group"><button type="button" data-ga="0" aria-pressed="${!gAll}">${escH(T("This week"))}</button><button type="button" data-ga="1" aria-pressed="${gAll}">${escH(T("All time"))}</button></div>`;
  lg += !rows ? `<p class="sum">${escH(T("Loading …"))}</p>` : !rows.length ? `<p class="sum">${escH(T("Nobody has scored this week yet."))}</p>`
    : `<ol class="gLeague">` + rows.map(r => `<li class="${r.me ? "me" : ""}${r.id ? " plTap" : ""}"${r.id ? ` data-player="${escH(r.id)}"` : ""}><b>${r.rank}</b><span>${r.crown ? '<span class="crown">♛</span>' : ""}${r.level ? rankIns(r.level, 30, {wings: r.wings, label: true}) : ""}<span class="${r.level >= 19 ? "rkGold" : ""}">${escH(r.name)}</span></span><em>${nf.format(r.points)}</em>` +
      `<i class="${r.was && r.was > r.rank ? "up" : r.was && r.was < r.rank ? "dn" : ""}">${r.was && r.was > r.rank ? "▲" + (r.was - r.rank) : r.was && r.was < r.rank ? "▼" + (r.rank - r.was) : ""}</i></li>`).join("") + `</ol>`;
  if (L && !gAll) lg += `<p class="sum">${escH(T("The week ends {d}, 03:00.", {d: fmtDay(L.resets - 4 * 3600000)}))}${L.champion ? " · " + escH(T("♛ Last week's winner: {n}", {n: L.champion})) : ""}</p>`;
  h += secPlate(T("League"), lg + `<label class="gOpt"><input type="checkbox" id="gLeagueOpt"${S.league === false ? "" : " checked"}> ${escH(T("Show me in the league"))}</label>`, "lgPlate");
  if (g0) h += collectionHtml(g0) + passportHtml(g0) + walletHtml(g0) + recordsHtml(all, g0);     // 1.106: the member cards; 1.107: the passport
  // 1.103: the flight school's record first while it runs; once signed, at the end (its signature once the font is here)
  const fs = fsState();
  if (fs && !fs.wings) h = secPlate(T("Flight school"), fsRecord(fs), "fsPlate") + h;
  if (fs && fs.wings) { h += secPlate(T("Flight school"), fsRecord(fs, {sig: window.SIG_FONT || sigFailed ? fsSigHtml(fsName()) : ""}), "fsPlate"); if (!window.SIG_FONT) sigFont().then(f => f && renderGame()); }
  h += `<p class="sum lbFoot">${escH(logbookSummary())}</p>`;          // 1.89: the Logbook's footnote, here too
  const box = $("gameBox");
  if (box.dataset.h === h) return;
  if (Date.now() - hgBusy < (hgHeld ? 10000 : 800)) return hgSoon();    // 1.103.0.1: not while a shelf is held or still moving
  const kept = [...box.querySelectorAll(".hgRow")].map(r => [r.dataset.set, r.scrollLeft]);
  box.dataset.h = h; box.innerHTML = h;
  for (const [k, x] of kept) { const r = box.querySelector(`.hgRow[data-set="${CSS.escape(k)}"]`); if (r) r.scrollLeft = x; }
  hgWire(box); lyWire(box, renderGame); ppWire(box);
  for (const li of box.querySelectorAll("[data-player]")) li.onclick = () => playerCard(li.dataset.player);
  for (const b of box.querySelectorAll("[data-ga]")) b.onclick = () => { ctlSound.nav(); gAll = b.dataset.ga === "1"; renderGame(); };
  $("gHow").onclick = gHowCard;
  $("cuOpen").onclick = careerOpen;
  trWire(box, renderGame);
  $("gLeagueOpt").onchange = e => { ctlSound.click(); S.league = e.target.checked; saveSettings(); gLeagueAt = 0; setTimeout(() => gLeagueLoad(true), 1500); };
}
// 1.104 (to-do #157, Dave's pick B): the standby (relay 87). From level 6 one a week keeps the streak through a day
// without a scan, from 14 two; the relay judges the days. The level card's week: Monday to Sunday (sbyDay: the weekday
// of the i-th, from a Monday), the standbys left on the right, and a warning while the streak hangs on today's scan.
const sbyDay = (i, w) => new Date(2026, 9, 26 + i).toLocaleDateString(LOC(), {weekday: w});
// The day after a standby: the streak's day the next scan pays (today's, once scanned); else 0.
const gSbyUsed = g => { const s = g && g.standby; return s && s.today > 0 && s.week[s.today - 1] === "b" ? (g.streak || 0) + (g.scannedToday ? 0 : 1) : 0; };
function gSbyHtml(g){
  const s = g.standby, R = gRules();
  if (!s || !s.week) return "";
  const t = s.today, used = s.week.lastIndexOf("b"), risk = s.allow && !s.left && !g.scannedToday && (g.streak || 0) > 0;
  const from = R && R.standby ? R.standby[R.standby.length - 1][0] : 6;
  const right = !s.allow ? `<em class="used">${escH(T("Standby from level {n}", {n: from}))}</em>`
    : s.left ? `<em>${escH(s.left === 1 ? T("1 standby left") : T("{n} standbys left", {n: s.left}))}</em>`
    : risk ? `<em class="none">${escH(T("No standby left"))}</em>`
    : `<em class="used">${escH(used >= 0 ? T("Standby used {d}", {d: sbyDay(used, "long")}) : T("No standby left"))}</em>`;
  const cls = (c, i) => c === "s" ? (i === t ? "now" : "on") : c === "b" ? "sby" : i === t ? "todo" : i < t ? "miss" : "";
  return `<div class="gRule gSbyH"><span>${escH(T("This week"))}</span>${right}</div>` +
    `<div class="gWk">${s.week.map((c, i) => `<i class="${cls(c, i)}" title="${escH(sbyDay(i, "long"))}">${escH(c === "b" ? T("SBY") : sbyDay(i, "narrow"))}</i>`).join("")}</div>` +
    (risk ? `<span class="gRule">${escH(T("No scan yet today: scan before 03:00 or your streak starts again at day 1."))}</span>` : "");
}
// 1.96 (to-do #127, Dave's L3): today's planes by rarity against their limits on the Game page, five counters, and a
// note for each rarity that reached its limit, with when it starts again.
function gLimHtml(g){
  const R = gRules(), L = g.limits;
  if (!R || !L) return "";
  const tiers = TIER_DRUM.slice(1), full = tiers.filter(t => L[t] && L[t][0] >= L[t][1]);
  const h = g.resets ? hhmm(new Date(g.resets)) : "03:00";
  return `<div class="gLim">${tiers.map(t => { const [n, m] = L[t] || [0, R.limit[t]];
    return `<div class="${n >= m ? "full" : ""}" style="--lamp:${TIER_COL[t]}"><img class="tico" src="${tierIcon(t)}" alt=""><b>${nf.format(Math.min(n, m))}<small>/${nf.format(m)}</small></b>` +
      `<i><u style="width:${Math.min(100, Math.round(n / m * 100))}%"></u></i><span>${escH(gTierT(t))}</span></div>`; }).join("")}</div>` +
    full.map(t => `<div class="gNote"><img class="tico" src="${tierIcon(t)}" alt=""><div>${escH(T("{t} limit reached: {m} of {m} today", {t: gTierT(t), m: nf.format(L[t][1])}))}` +
      `<small>${escH(T("{t} planes score again from {h}. The other rarities still count.", {t: gTierT(t), h}))}</small></div></div>`).join("");
}
// 1.79: How points work, a card. 1.96 (to-do #127): the rules on one screen, from the relay: each rarity's points within
// the circle and with a scan, today's planes against the limits, the extras and the daily streak.
function gHowCard(){
  ctlSound.nav();
  const g = gme || {}, R = gRules(), L = g.limits || {}, k = gKm();
  const rows = R ? TIER_DRUM.slice(1).map(t => { const [n, m] = L[t] || [0, R.limit[t]];
    return `<span><img class="tico" src="${tierIcon(t)}" alt=""></span><span>${escH(gTierT(t))}</span><span class="r">+${nf.format(R.passive[t])}</span>` +
      `<span class="r"><b>+${nf.format(R.base[t])}</b></span><span class="r"><em class="${n >= m ? "full" : ""}">${nf.format(Math.min(n, m))}</em> / ${nf.format(m)}</span>`; }).join("") : "";
  const sd = R ? Array.from({length: 7}, (_, i) => `<i class="${i < (g.streak || 0) ? "on" : ""}">${escH(T("Day {n}", {n: i + 1}))}<b>+${nf.format(R.streak * (i + 1))}</b></i>`).join("") : "";
  const p = (a, b) => `<p class="gRule"><em>${escH(a)}</em> ${escH(b)}</p>`;
  cardOpen(`<div class="cHead"><div><h3>${escH(T("How points work"))}</h3></div></div>` +
    `<p class="gRule">${escH(T("Points come with live location on (Settings → Location), for planes within {k} km of you. Each plane scores once a pass, by how rare it is.", {k}))} ${escH(T("Nothing counts while the app is in the background."))}</p>` +
    (R ? `<div class="gHowTbl"><span class="th"></span><span class="th">${escH(T("Rarity"))}</span><span class="th r">${escH(T("Within {k} km", {k}))}</span>` +
      `<span class="th r">${escH(T("Scanned"))}</span><span class="th r">${escH(T("Today / max"))}</span>${rows}</div>` +
      p(T("Within {k} km:", {k}), T("the points in the first column, for a number of planes of each rarity a day (from 03:00). Past the limit a plane scores nothing; the other rarities still count.")) +
      p(T("Sky view scan:"), T("hold a plane that came within {s} km in the ring for a moment. It gives the plane's full points on top, once a pass, with no limit (past the limit too).", {s: gScanKm()})) +
      p(T("Only with a scan:"), T("a type new to the game +{t}, a new airline +{a}.", {t: nf.format(R.new.type), a: nf.format(R.new.airline)})) +
      (R.mastery ? p(T("Mastery:"), T("the scan that brings a type to {a}, {b} or {c} scans adds +{x}, +{y} or +{z} once, and its hangar card turns bronze, silver or gold.",
        {a: R.mastery[0][0], b: R.mastery[1][0], c: R.mastery[2][0], x: nf.format(R.mastery[0][1]), y: nf.format(R.mastery[1][1]), z: nf.format(R.mastery[2][1])})) : "") +   // 1.105 (relay 88)
      (R.loyalty ? p(T("Member cards:"), T("your first scan of an airline's plane makes you a member; the scan that brings it to {a}, {b} or {c} adds +{x}, +{y} or +{z} once: Silver, Gold, Platinum.",
        {a: R.loyalty[0][0], b: R.loyalty[1][0], c: R.loyalty[2][0], x: nf.format(R.loyalty[0][1]), y: nf.format(R.loyalty[1][1]), z: nf.format(R.loyalty[2][1])})) : "") +   // 1.106 (relay 89)
      (R.country ? p(T("Passport:"), T("a scanned flight with a known route stamps the countries it flies from and to; a country new to your passport adds +{p}.", {p: nf.format(R.country)})) : "") +   // 1.107 (relay 90)
      `<p class="gHowH">${escH(T("Daily streak"))}</p><p class="gRule">${escH(T("Your first scan each day adds +{n} for each day in a row. A day without a scan starts it again at day 1, and so does Monday at 03:00, with the league.", {n: R.streak}))}</p>` +
      `<div class="gStk">${sd}</div>` +
      (R.standby ? p(T("Standby:"), T("from level {a}, one a week keeps your streak through a day without a scan; from level {b}, two. They come fresh each Monday at 03:00 and don't carry over.",
        {a: R.standby[R.standby.length - 1][0], b: R.standby[0][0]})) : "") +              // 1.104 (relay 87)
      (R.bingo ? `<p class="gHowH">${escH(T("Bingo and trophies"))}</p>` +           // 1.100 (relay 83)
        p(T("Weekly bingo:"), T("+{l} for each line, +{c} more for the full card. A new card every Monday at 03:00, with the league.", {l: nf.format(R.bingo.line), c: nf.format(R.bingo.card)})) +
        p(T("Trophies:"), T("a new rank +{a} to +{b} by its medal (bronze to diamond), any other trophy +{s}.", {a: nf.format(R.medal[0]), b: nf.format(R.medal[R.medal.length - 1]), s: nf.format(R.single)})) : "") : ""));
}
/* 1.89 (to-do #91, Dave's pick A): Recent points, from a tap on the strip's points: today's total and planes, then each
   plane that scored, newest first (time, flight, airline, type with its rarity, how close, its total) with its awards
   under it. The relay keeps the awards from relay 71 on (/game/today); planes scored before show their totals without
   times. 1.96: the same lines as the pop-ups (gAwLine), in the order they came, a plane past its limit in grey with the
   reason; planes scored by the rules before keep their reasons (gWhy). */
const gRecentOk = () => gameOk() && (window.OVERHEAD_RELAY_VERSION || 0) >= 71;
const gPlus = n => (n < 0 ? "−" : "+") + nf.format(Math.abs(n));
function gWhy(r, a){
  if (a.k === "lock") return T("Sky view lock-on · +{p}%", {p: Math.round((a.pct || .25) * 100)});
  if (a.k === "fix") return T("Points corrected");
  const d = a.d != null ? a.d : r.km, near = d != null && d <= 1.5 ? 1.5 : d != null && d <= 4 ? 4 : 0;
  if (a.k === "close") return T("Close pass · within {k} km", {k: nf.format(near || 4)});
  const NEW = {type: "New type", airline: "New airline", reg: "New aircraft"};
  const n = r.gn || 1, taper = n <= 25 ? "" : n <= 50 ? "×½" : "×¼";
  return [T(TIER_NAME[r.tier] || "Uncommon") + " +" + nf.format(r.base), ...(r.new || []).map(([k, v]) => T(NEW[k] || k) + " +" + nf.format(v)),
    near ? T("Close pass ×{x}", {x: near === 1.5 ? "1.2" : "1.1"}) : "",
    r.gk > 1 ? T("Streak ×{x}", {x: nf.format(r.gk)}) : "",
    taper ? T("Plane {n} of the day {x}", {n: nf.format(n), x: taper}) : ""].filter(Boolean).join(" · ");
}
async function gRecentCard(){
  const tok = cardLoading();
  let j = null;
  try { j = await fetchJSON(`${relay()}/game/today`, {}, 8000); } catch {}
  if (tok !== cardTok) return;
  if (!j) { cardOpen(`<p class="note">${escH(T("Couldn't load today's points."))}</p>`); return; }
  const at = t => t ? hhmm(new Date(t)) : "";
  let rows = j.rows.map(r => {
    const f = fromRelay(r);                  // named as in Spotted today (FR 3EG, not RYR3EG)
    // a plane scored before relay 71: its totals, the first score and a lock-on without their times
    const aw = r.aw.length ? r.aw : [{k: "first", p: r.gp}, ...(r.lock ? [{k: "lock", p: r.lock}] : [])];
    const col = TIER_COL[r.tier] || TIER_COL.uncommon, hot = r.tier && r.tier !== "common", sum = r.gp + (r.lock || 0) + (r.gs || 0) + (r.gb || 0);
    const lines = aw.map((a, i) => { const [w, p, x] = (r.rule || 1) >= 2 ? gAwLine({tier: r.tier, ...a}, f) : [gWhy(r, a), a.p, ""];
      return `<div class="meta${i ? " top" : ""}${x ? " " + x : ""}"><span>${escH([["new", "streak", "mastery", "loyalty"].includes(a.k) ? "" : at(a.t), w].filter(Boolean).join(" · "))}</span><span>${gPlus0(p)}</span></div>`; }).join("");
    const what = [`<img class="tico" src="${tierIcon(r.tier || "uncommon")}" alt="">${escH(f.type || NA)}`, escH(T(TIER_NAME[r.tier] || "Uncommon")), r.km != null ? escH(distText(r.km)) : ""].filter(Boolean).join("<i>·</i>");
    return `<li class="fl sp${sum ? "" : " lim"}" style="--lamp:${col}${hot && sum ? `;background:${rgba(col, .11)}` : ""}"><div class="tc"><time>${escH(at(r.aw.length ? r.aw[r.aw.length - 1].t : r.ts))}</time></div>` +
      `<div class="who"><strong>${escH(f.flight)}</strong>${f.airline ? `<span>${escH(f.airline)}</span>` : ""}</div><b class="pts">${gPlus0(sum)}</b>` +
      `<div class="rt">${what}</div>${lines}</li>`;
  }).map((h, i) => [Math.max(j.rows[i].ts || 0, ...j.rows[i].aw.map(a => a.t)), h]);
  // 1.103 (relay 85): today's flight school missions, a row of their own (they have no plane), in time with the planes
  const fsAw = j.school || [];
  if (fsAw.length) {
    const sum = fsAw.reduce((n, a) => n + a.p, 0), t = Math.max(...fsAw.map(a => a.t));
    rows.push([t, `<li class="fl sp fsRow"><div class="tc"><time>${escH(at(t))}</time></div><div class="who"><strong>${escH(T("Flight school"))}</strong></div><b class="pts">${gPlus0(sum)}</b>` +
      fsAw.map((a, i) => { const m = SCHOOL.find(x => x[0] === a.n), w = m ? T(m[1]) : gAwLine(a)[0], p = a.p; return `<div class="meta${i ? " top" : ""} x"><span>${escH(at(a.t) + " · " + w)}</span><span>${gPlus0(p)}</span></div>`; }).join("") + `</li>`]);
    rows.sort((a, b) => b[0] - a[0]);
  }
  rows = rows.map(r => r[1]).join("");
  cardOpen(`<div class="cHead"><div><h3>${escH(T("Recent points"))}</h3><span>${escH(T(j.planes === 1 ? "Today {p} · 1 plane · newest first" : "Today {p} · {n} planes · newest first", {p: nf.format(j.today || 0), n: nf.format(j.planes || 0)}))}</span></div></div>` +
    (rows ? `<ul class="flights rpList">${rows}</ul>` : `<p class="sum">${escH(T(S.live ? "No points yet today. Planes score the first time they come within {k} km of you; within {s} km you can scan them." : "Points only come with live location (Settings → Location): planes within {k} km of you score, and within {s} km you can scan them.", {k: gKm(), s: gScanKm()}))}</p>`) +
    `<button class="gHow" type="button" data-club>${escH(T("Spotters' Club: level and league"))}<i>›</i></button>`,
    ci => { ci.querySelector("[data-club]").onclick = () => { ctlSound.nav(); cardClose(); showTab("game"); }; });
}
/* 1.81 (Dave's to-do 6, his pick A): a league player's card, from a tap on their row: level and bar, this week, all time
   and the streak, their medals by metal, the rarest catch and this week's best plane. Never where they are (relay 63). */
// 1.108: the showcase on a player's card (your own: its empty and locked spots, and how to fill it)
function scSection(p){
  const cab = scCab(p.showcase, {mine: p.me});
  return cab ? `<div class="scSc"><h4>${escH(T("Showcase"))}</h4>${cab}` +
    (p.me ? `<p>${escH(T("Others see this when they tap your name. Pin a plane from your hangar."))}</p>` : "") + `</div>` : "";
}
async function playerCard(id){
  ctlSound.nav();
  const tok = cardLoading();
  let p = null;
  try { p = await fetchJSON(`${relay()}/game/player?id=${encodeURIComponent(id)}`, {}, 8000); } catch {}
  if (tok !== cardTok) return;
  if (!p) { cardOpen(`<p class="note">${escH(T("Couldn't load this player."))}</p>`); return; }
  const metals = TROPHY_MEDALS.map(() => 0);
  let singles = 0;
  for (const k of p.trophies || []) {
    const tr = TROPHY_TIER.get(k), L = tr && TROPHY_LADDERS.find(l => l[0] === tr.key);
    if (L) metals[L[2].findIndex(t => t[0] === k)]++; else singles++;
  }
  const medals = metals.map((n, i) => n ? `<span class="plMedal" style="--m:${MEDAL_COL[i]}"><i></i>${escH(nf.format(n) + " " + T(TROPHY_MEDALS[i]).toLowerCase())}</span>` : "").join("") +
    (singles ? `<span class="plMedal">${CUP}${escH(T(singles === 1 ? "1 trophy" : "{n} trophies", {n: singles}))}</span>` : "");
  const ra = p.rarest, b = p.best;
  cardWhenReady(tok, `<div class="plCard"><div class="cHead"><div><h3>${p.crown ? '<span class="crown">♛</span> ' : ""}<b class="${p.level >= 19 ? "rkGold" : ""}">${escH(p.name)}</b></h3>` +
    `<span>${escH(T("Level {n} · {t}", {n: p.level, t: T(p.title)}))}${p.rank ? " · " + escH(T("#{n} this week", {n: p.rank})) : ""}</span></div>` +
    (p.level ? `<span class="plIns">${rankIns(p.level, 46, {wings: p.wings})}</span>` : "") + `</div>` +
    `<div class="gBar"><i style="width:${(p.need ? p.into / p.need * 100 : 0).toFixed(1)}%"></i></div>` +
    `<div class="gTiles"><div><b>${nf.format(p.week || 0)}</b><span>${escH(T("This week"))}</span></div><div><b>${nf.format(p.points || 0)}</b><span>${escH(T("All time"))}</span></div>` +
    `<div><b>${p.streak || 0}</b><span>${escH(T("Day streak"))}</span></div></div>` + scSection(p) + (medals ? `<div class="plMedals">${medals}</div>` : "") +
    `<ul class="ranks plain cups plLines">` +
    (ra ? `<li class="on" style="--lamp:${TIER_COL[ra.tier] || TIER_COL.uncommon}">${CUP}<span class="name">${escH(T("Rarest catch"))} <span class="s">${escH(ra.name || TYPES[ra.code] || ra.code)}</span></span><span class="n">${escH(T(TIER_NAME[ra.tier] || ""))}</span></li>` : "") +
    (b ? `<li class="on">${CUP}<span class="name">${escH(T("Best this week"))} <span class="s">${escH([b.type, b.flight].filter(Boolean).join(" · "))}</span></span><span class="n">${nf.format(b.pts || 0)}</span></li>` : "") + `</ul></div>`, scPics);
}
/* 1.81 (Dave's to-do 5, his picks: B's medal, A's nudge): a rank won swings down as a medal on a ribbon, the rank in Roman
   numerals, its name and what it took under it; it settles and fades after a few seconds (or a tap). Other achievements,
   and the board, keep their card: achNext asks achSpecial first (dry: only whether it is a medal). */
const ROMAN = ["I", "II", "III", "IV", "V"];
let medalT = 0;
function achSpecial(a, dry){
  const id = a && /^tr:/.test(a.k) ? a.k.slice(3) : "", tr = id ? TROPHY_TIER.get(id) : null, L = tr && TROPHY_LADDERS.find(l => l[0] === tr.key);
  if (!L || dry) return !!L;
  const i = L[2].findIndex(t => t[0] === id);
  let box = $("medalMo");
  if (!box) { box = document.createElement("div"); box.id = "medalMo"; box.setAttribute("role", "dialog"); document.body.appendChild(box); }
  box.style.setProperty("--m", MEDAL_COL[i]); box.setAttribute("aria-label", T("New medal"));
  box.innerHTML = `<div class="mmRib"><i></i><b>${ROMAN[i]}</b></div><div class="mmTx"><span>${escH(T("New medal · {m}", {m: T(TROPHY_MEDALS[i])}) + (a.pts ? " · +" + nf.format(a.pts) : ""))}</span>` +
    `<h3>${escH(T(tr.name))}</h3><p>${escH(T(tr.text, {n: nf.format(tr.at)}))} · ${escH(T("rank {i} of {n}", {i: i + 1, n: L[2].length}))}</p></div>`;
  box.hidden = false; box.classList.remove("out");
  fanfare();
  try { navigator.vibrate && navigator.vibrate([30, 40, 60]); } catch {}
  const close = () => { clearTimeout(medalT); box.classList.add("out"); medalT = setTimeout(() => { box.hidden = true; box.classList.remove("out"); }, 600); };
  box.onclick = close; clearTimeout(medalT); medalT = setTimeout(close, 5000);
  return true;
}
// The nudge: when a trophy's next rank is close (two airlines to go, say), a notice from the right, once for each rank.
const NUDGE_UNIT = {planes: ["plane", "planes"], types: ["type", "types"], airlines: ["airline", "airlines"], regs: ["aircraft", "aircraft"],
  countries: ["country", "countries"], points: ["point", "points"], legendary: ["special plane", "special planes"], today: ["plane today", "planes today"],
  friend: ["time", "times"], streak: ["day", "days"]};
function medalNudge(g0){
  if (!g0 || !g0.trophyCounts || S.demo) return;
  let done = [];
  try { done = JSON.parse(localStorage.getItem(ACH_KEY + ".nudge") || "[]"); } catch {}
  for (const L of TROPHY_LADDERS) {
    const st = trophyLadder(g0, L), t = st.next, left = t && st.have != null ? t[1] - st.have : 0;
    if (!t || done.includes(t[0]) || left <= 0 || left > Math.max(2, Math.round(t[1] * .02))) continue;
    try { localStorage.setItem(ACH_KEY + ".nudge", JSON.stringify(done.concat(t[0]).slice(-80))); } catch {}
    const u = NUDGE_UNIT[L[0]] || ["", ""];
    toast(T("{n} more {u} for {name}", {n: nf.format(left), u: T(u[left === 1 ? 0 : 1]), name: T(t[2])}), {ms: 7000});
    return;                                                         // one at a time
  }
}
// Sky view held a plane in its ring for 1.5 s: the scan (relay 76; a lock-on before). Once a pass, without a limit, it
// tops the plane up to its full points, with the extras and the day's streak: their passes slide up from below
// (gScanPops), with a burst in the ring, the prize jingle and a buzz.
// The scan's fireworks: eighteen sparks round a point in Sky view (x, y in #arView), the ring by default.
function gBurst(x, y, gold){
  let burst = $("arBurst");
  if (!burst) { burst = document.createElement("div"); burst.id = "arBurst"; $("arView").appendChild(burst); }
  burst.style.left = x == null ? "" : x + "px"; burst.style.top = y == null ? "" : y + "px";
  burst.className = gold ? "gold" : "";
  // 1.101: a golden ticket throws gold glitter: more, finer pieces in golds and white, and sparkles (✦) among them
  const cols = gold ? ["#fff1b8", "#f0b429", "#ffffff", "#e0aa1f", "#c9921a"] : ["#f0b429", "#c7372d", "#f3f0e8", "#22a058", "#3b7ddd"], n = gold ? 24 : 18;
  burst.innerHTML = Array.from({length: n}, (_, i) => `<i style="--r:${i * 360 / n}deg;background:${cols[i % 5]}"></i>`).join("") +
    (gold ? Array.from({length: 10}, (_, i) => `<b style="--r:${i * 36 + 18}deg;animation-delay:${(i % 3) * .08}s">✦</b>`).join("") : "");
  clearTimeout(gBurst.t); gBurst.t = setTimeout(() => { burst.innerHTML = ""; }, 1200);
}
async function gLockOn(hex){
  if (!gameOk() || !S.live) return;
  let r;
  try { r = await fetchJSON(`${relay()}/game/lockon`, {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({hex})}, 6000); }
  catch (e) { dlog("warn", `Sky view scan: no answer (${netError(e, "relay")})`); return; }
  const ac = arList.find(a => a.hex === hex) || {};
  dlog(r && r.bonus ? "info" : "debug", `Sky view scan: ${String(ac.flight || hex).trim()} ${r && r.bonus ? "+" + r.bonus + (r.streak ? ", streak day " + r.streak : "") : "nothing (" + (r && r.why || "none") + ")"}`);
  if (!r || !r.bonus) {
    if (r && r.why === "far") { $("arHint").hidden = false; $("arHint").textContent = T("Too far for points: they come within {k} km.", {k: gKm()}); }
    if (r && r.why === "closer") { $("arHint").hidden = false; $("arHint").textContent = T("Too far to scan: planes can be scanned within {k} km.", {k: r.scanKm || gScanKm()}); }
    return;
  }
  const passes = gScanPops({hex, callsign: String(ac.flight || "").trim(), reg: ac.r || "", typeCode: ac.t || "", ...r});
  gJingle();
  // 1.97.8: each stub tears off (CSS .rip, 1.97.1.1; the streak's .rip2 0.7 s after the scan's) with the paper sound at the
  // moment it comes off (its animationstart), and the burst starts at the scan's tear line. With reduced motion there is no
  // tear: the burst stays where it was, in the ring, at once, and the sounds come on the same count.
  const still = matchMedia("(prefers-reduced-motion: reduce)").matches;
  // 1.101: a golden ticket's stub tears with its own sound (gGold) and throws gold glitter (none with reduced motion).
  const gold = !!r.gold, rip = i => gold && !i ? gGold : gRip;
  if (still && !gold) gBurst();
  passes.forEach((pass, i) => {
    const stub = pass && pass.querySelector(".stub");
    if (!stub || still) { setTimeout(rip(i), 1050 + i * 700); return; }
    let torn = false;
    const tear = () => {
      if (torn) return;
      torn = true; rip(i)();
      if (i || !stub.isConnected) return;
      const a = stub.getBoundingClientRect(), v = $("arView").getBoundingClientRect();
      gBurst(a.left - v.left, a.top - v.top + a.height / 2, gold);
    };
    stub.addEventListener("animationstart", tear, {once: true});
    setTimeout(tear, 1500 + i * 700);                              // no animationstart (the page hidden): the sound at least
  });
  try { navigator.vibrate && navigator.vibrate([40, 30, 80]); } catch {}
  setTimeout(() => gRefresh(true), 2500);
}
/* 1.103 (to-do #153, Dave's pick of 29 Oct, round 2's C): the flight school. Five first missions that teach the app, +50
   each, once (the relay sees and pays them, relay 85; a plane's card is this app's call, schoolMission); all five earn
   the wings. The Spotters' Club shows a training record: a line per mission, its dated PASSED stamp in its box once done,
   a hint for the next one only, and the WINGS line signed at the end. Now shows a small bar (CHECKLIST 3/5 · NEXT · …,
   five marks) until the wings. A mission done lands a big stamp (fsStamp); the fifth then signs the record with the
   player's first name, written as with a pen (sigWrite: signature.js's single-stroke script, stroke by stroke), and
   Cleared for take-off comes with the wings (fsWings). A profile at level 4 when relay 85 came has its wings without the
   school (school.pre) and never sees it. Reduced motion: the stamps and the signature appear without moving. */
const SCHOOL = [["scan", "Scan a plane", "In Sky view, hold a plane in the ring"], ["card", "Open a plane's card", "Tap a plane on Now or Today"],
  ["bingo", "Fill a bingo square", "Spot a plane on this week's bingo card"], ["fav", "Add a favourite", "Swipe a plane in Today to the right"],
  ["uncommon", "Catch an uncommon", "An uncommon plane within {k} km of you"]];
const fsState = () => { const s = gameOk() && gme && gme.school; return s && !s.pre ? s : null; };
const fsNext = s => SCHOOL.find(([m]) => !s.done[m]);
const fsPts = () => (gRules() || {}).school || 50;
const fsStill = () => matchMedia("(prefers-reduced-motion: reduce)").matches;
const fsDate = t => new Date(t).toLocaleDateString(LOC(), {day: "numeric", month: "short"}).replace(/\.$/, "").toUpperCase();
const fsBox = (t, big) => `<span class="fsBox${big ? " big" : ""}"><small>${escH(T("Flight school"))}</small><b>${escH(T("Passed"))}</b><small>${escH(fsDate(t))} · +${fsPts()}</small></span>`;
// The training record: o.sig the WINGS line's signature (an <svg>), o.next false: no hint (the wings' copy)
function fsRecord(s, o = {}){
  const n = SCHOOL.filter(([m]) => s.done[m]).length, nx = !s.wings && o.next !== false && fsNext(s);
  return `<div class="fsRec"><div class="hd"><span>${escH(T("Training record · pre-flight"))}</span><span>${n} / ${SCHOOL.length}</span></div>` +
    SCHOOL.map(([m, t, h]) => { const d = s.done[m], next = nx && nx[0] === m;
      return `<div class="r${d ? " on" : next ? " nx" : ""}"><span class="t"><b>${escH(T(t))}</b><span>${escH(next ? T(h, {k: gKm()}) : "+" + fsPts())}</span></span>` +
        `<span class="bx">${d ? fsBox(d) : next ? escH(T("Next up")) : ""}</span></div>`; }).join("") +
    `<div class="sg"><span>${escH(T("Wings"))}</span><span class="ln${s.wings || o.sig ? "" : " no"}">${o.sig || ""}</span><span>${s.wings ? escH(fsDate(s.wings)) : `${n} / ${SCHOOL.length}`}</span></div></div>`;
}
// The bar on Now, above the plane overhead, until the wings; a tap opens the club.
function fsBar(){
  const s = fsState(), nx = s && !s.wings && fsNext(s);
  let bar = $("fsBar");
  if (!bar) {
    if (!nx || !$("hero")) return;
    bar = document.createElement("button"); bar.type = "button"; bar.id = "fsBar";
    bar.onclick = () => { ctlSound.nav(); showTab("game"); window.scrollTo(0, 0); };
    $("hero").before(bar);
  }
  bar.hidden = !nx;
  if (!nx) return;
  const n = SCHOOL.filter(([m]) => s.done[m]).length;
  const h = `<b>${escH(T("Checklist {n}/{m}", {n, m: SCHOOL.length}))}</b><span>${escH(T("Next up · {m}", {m: T(nx[1])}))}</span>` +
    `<span class="bx">${SCHOOL.map(([m]) => `<u${s.done[m] ? ' class="on"' : ""}></u>`).join("")}</span>`;
  if (bar.dataset.h !== h) { bar.dataset.h = h; bar.innerHTML = h; }
}
// A plane's card opened (planeCard): the relay is told once; its +50 then comes with /game/me's awards (the stamp).
let fsCardAsked = false;
async function schoolMission(m){
  const s = fsState();
  if (m !== "card" || !s || s.wings || s.done.card || fsCardAsked) return;
  fsCardAsked = true;
  try {
    const r = await fetchJSON(`${relay()}/game/school`, {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({m})}, 6000);
    if (r && r.school && gme) gme.school = r.school;
    gRefresh(true);
  } catch { fsCardAsked = false; }
}
// A mission done: its line slides in at the top and the big stamp lands in its box, with a thud; one at a time, not
// over Sky view or another big notice (they wait).
const fsQ = [];
let fsBusy = false;
function fsStamp(a){ fsQ.push(a); fsShow(); }
function fsShow(){
  if (fsBusy || !fsQ.length) return;
  if (($("arView") && !$("arView").hidden) || ($("gLvUp") && !$("gLvUp").hidden) || document.hidden) { setTimeout(fsShow, 1500); return; }
  const a = fsQ.shift(), m = SCHOOL.find(x => x[0] === a.n);
  if (!m) { fsShow(); return; }
  fsBusy = true;
  const el = document.createElement("div");
  el.id = "fsStamp"; el.setAttribute("role", "status");
  el.innerHTML = `<div class="fsRec"><div class="hd"><span>${escH(T("Checked · {n} of {m}", {n: a.i || 1, m: SCHOOL.length}))}</span><span>+${nf.format(a.p)}</span></div>` +
    `<div class="r on"><span class="t"><b>${escH(T(m[1]))}</b><span>${escH(T("{n} points", {n: "+" + nf.format(a.p)}))}</span></span><span class="bx">${fsBox(a.t, true)}</span></div></div>`;
  document.body.appendChild(el);
  setTimeout(() => { fsThud(); try { navigator.vibrate && navigator.vibrate(30); } catch {} }, fsStill() ? 0 : 640);   // as the stamp hits
  let shut = false;
  const close = () => {
    if (shut) return;
    shut = true; el.classList.add("out");
    setTimeout(() => { el.remove(); fsBusy = false; if (a.wings) fsWings(a); else fsShow(); }, fsStill() ? 0 : 350);
  };
  el.onclick = close; setTimeout(close, 3800);
}
// The stamp's sound (with the button sounds on): a soft low thump and the click of its edge on the paper.
function fsThud(){
  if (!S.sound || !actx || actx.state !== "running") return;
  const t = actx.currentTime + .01, o = actx.createOscillator(), g = actx.createGain();
  o.type = "sine"; o.frequency.setValueAtTime(150, t); o.frequency.exponentialRampToValueAtTime(48, t + .12);
  g.gain.setValueAtTime(0, t); g.gain.linearRampToValueAtTime(.55, t + .004); g.gain.exponentialRampToValueAtTime(.0001, t + .2);
  o.connect(g).connect(sfxOut()); o.start(t); o.stop(t + .22);
  const n = actx.createBuffer(1, actx.sampleRate * .05, actx.sampleRate), d = n.getChannelData(0);
  for (let i = 0; i < d.length; i++) d[i] = (Math.random() * 2 - 1) * (1 - i / d.length) ** 3;
  const src = actx.createBufferSource(), bp = actx.createBiquadFilter(), ng = actx.createGain();
  src.buffer = n; bp.type = "bandpass"; bp.frequency.value = 1500; ng.gain.value = .35;
  src.connect(bp).connect(ng).connect(sfxOut()); src.start(t);
}
// Pilot's wings in gold (the club's and the wings' notice).
const fsWingsSvg = (w = 120) => { const f = "M52,14 C38,7 18,5 2,7 C14,12 32,16 52,19 Z M52,19 C38,15 22,14 9,15.5 C21,20 36,22 52,24 Z M52,24 C40,22.5 28,22.5 17,24.5 C28,28 40,29 52,29 Z";
  return `<svg class="fsWings" width="${w}" height="${w / 3}" viewBox="0 0 120 40" aria-hidden="true"><defs><linearGradient id="fsWg" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#ffe08a"/><stop offset="1" stop-color="#b8861c"/></linearGradient></defs>` +
    `<g fill="url(#fsWg)" stroke="#b8861c" stroke-width=".6"><path d="${f}"/><path d="${f}" transform="matrix(-1 0 0 1 120 0)"/><circle cx="60" cy="20" r="10.5"/></g>` +
    `<path transform="translate(51.5 11.5) scale(.7)" fill="#b8861c" d="M21 16v-2l-8-5V3.5a1.5 1.5 0 0 0-3 0V9l-8 5v2l8-2.5V19l-2 1.5V22l3.5-1 3.5 1v-1.5L13 19v-5.5z"/></svg>`; };
// The signature's font (signature.js, fetched the first time it is needed; tried again a minute after a failure).
let sigLoad = null, sigFailed = 0;
function sigFont(){
  if (window.SIG_FONT) return Promise.resolve(window.SIG_FONT);
  if (!sigLoad && Date.now() - sigFailed > 60000) sigLoad = new Promise(done => {
    const s = document.createElement("script");
    s.src = SIG_JS; s.async = true;
    s.onload = () => done(window.SIG_FONT || null);
    s.onerror = () => { sigLoad = null; sigFailed = Date.now(); s.remove(); done(null); };
    document.head.appendChild(s);
  });
  return sigLoad || Promise.resolve(null);
}
const fsName = () => String((GUEST && GUEST.name) || "").trim().split(/\s+/)[0] || T("Pilot");
// The name as pen strokes: a <path> per stroke (a letter's M … pieces) in writing order, each letter flipped (y is up
// in the font) and set at its place on the line. A letter the font lacks: its base letter (é → e); none: null (the
// name is then written in the phone's script font, uncovered from the left).
function sigSvg(name, F){
  let x = 0;
  const strokes = [];
  for (const ch of name) {
    const g = F[ch] || F[ch.normalize("NFD").replace(/[̀-ͯ]/g, "")];
    if (!g) return null;
    for (const d of g[1].split(/(?=M)/).filter(Boolean)) strokes.push(`<path data-x="${x}" transform="translate(${x} 800) scale(1 -1)" d="${d}"/>`);
    x += g[0];
  }
  return `<svg class="fsSig" viewBox="-60 -20 ${x + 120} 1140" role="img" aria-label="${escH(name)}">${strokes.join("")}</svg>`;
}
const fsSigHtml = name => (window.SIG_FONT && sigSvg(name, window.SIG_FONT)) || `<span class="fsSigT">${escH(name)}</span>`;
// Writing it: each stroke drawn along its length at a pen's pace (a little slower into and out of a stroke), the pen
// lifted for a moment between strokes, a nib of ink at the tip. Reduced motion: all at once.
function sigWrite(el, done){
  const paths = el.tagName === "svg" ? [...el.querySelectorAll("path")] : [];
  el.classList.remove("pre");                              // (unseen until the pen starts: fsWings)
  if (fsStill() || (!paths.length && el.tagName === "svg")) { done(); return; }
  if (!paths.length) { el.classList.add("writing"); setTimeout(done, 1800); return; }     // the script font's text
  const L = paths.map(p => p.getTotalLength()), sum = L.reduce((a, b) => a + b, 0);
  const per = Math.min(3400, Math.max(1500, sum / 5)) / sum, LIFT = 110;        // ms per font unit; a pen lift
  const at = [];
  let t = 0;
  L.forEach((l, i) => { at.push(t); t += l * per + (i < L.length - 1 ? LIFT : 0); });
  paths.forEach((p, i) => { p.style.strokeDasharray = `${L[i]} ${L[i] + 10}`; p.style.strokeDashoffset = L[i]; });
  const nib = document.createElementNS("http://www.w3.org/2000/svg", "circle");
  nib.setAttribute("class", "nib"); nib.setAttribute("r", "17");
  el.appendChild(nib);
  const ease = u => u - Math.sin(2 * Math.PI * u) / (2 * Math.PI) * .35;
  const tip = (i, u) => { const q = paths[i].getPointAtLength(L[i] * u); return [+paths[i].dataset.x + q.x, 800 - q.y]; };
  const t0 = performance.now();
  const step = now => {
    if (!el.isConnected) return;
    const e = now - t0;
    let pos = null;
    paths.forEach((p, i) => {
      const dur = L[i] * per, u = Math.max(0, Math.min(1, (e - at[i]) / dur));
      p.style.strokeDashoffset = L[i] * (1 - ease(u));
      if (e >= at[i] && (u < 1 || i === paths.length - 1)) pos = tip(i, ease(u));
      else if (u >= 1 && i < paths.length - 1 && e < at[i + 1]) {         // the pen moving to the next stroke
        const k = (e - at[i] - dur) / LIFT, [x1, y1] = tip(i, 1), [x2, y2] = tip(i + 1, 0);
        pos = [x1 + (x2 - x1) * k, y1 + (y2 - y1) * k];
      }
    });
    if (pos) { nib.setAttribute("cx", pos[0].toFixed(1)); nib.setAttribute("cy", pos[1].toFixed(1)); }
    if (e < t) requestAnimationFrame(step);
    else { nib.classList.add("off"); done(); }
  };
  requestAnimationFrame(step);
}
// All five: the record, signed as you watch on its WINGS line, then the wings and Cleared for take-off.
function fsWings(a){
  const s = Object.assign({done: {}}, gme && gme.school, {wings: (gme && gme.school && gme.school.wings) || a.t});
  let box = $("gLvUp");
  if (!box) { box = document.createElement("div"); box.id = "gLvUp"; box.setAttribute("role", "dialog"); document.body.appendChild(box); }
  box.innerHTML = `<div class="lvBox fsWin"><span class="eyebrow">${escH(T("Training record signed"))}</span>${fsWingsSvg(190)}<h3>${escH(T("Cleared for take-off"))}</h3>` +
    fsRecord(s, {sig: '<i class="fsSigAt"></i>', next: false}) +
    `<p>${escH(T("Your wings: five missions, +{p} points.", {p: nf.format(fsPts() * SCHOOL.length)}))}</p><button class="cBtn" type="button">${escH(T("Take off"))}</button></div>`;
  box.classList.add("fsW"); box.classList.remove("signed");
  box.hidden = false; box.onclick = null;
  const close = () => { box.hidden = true; box.classList.remove("fsW", "signed"); };
  box.querySelector(".cBtn").onclick = () => { ctlSound.click(); close(); };
  sigFont().then(() => {
    const at = box.querySelector(".fsSigAt");
    if (!at) return;
    at.outerHTML = fsSigHtml(fsName()).replace(/class="fsSig(T?)"/, 'class="fsSig$1 pre"');
    const el = box.querySelector(".fsSig, .fsSigT");
    setTimeout(() => sigWrite(el, () => {
      box.classList.add("signed"); gJingle();
      try { navigator.vibrate && navigator.vibrate([30, 40, 60]); } catch {}
    }), fsStill() ? 0 : 700);
  });
}
function gameStart(){
  gStripSetup();
  for (const b of document.querySelectorAll('[data-lt="game"]')) b.hidden = !gameOk();   // 1.74: no Spotters' Club without relay 59
  if (!gameOk()) return;
  gRefresh(true); gLeagueLoad();
  setInterval(() => gRefresh(), 2500);
  document.addEventListener("visibilitychange", () => { if (!document.hidden) gRefresh(true); });
  setTimeout(() => tip("gstrip", () => $("gStrip"), T("Your points. Only planes you spot with live location on score. Tap for your level and the league.")), 4000);
}
function run(){
  if (booted) return;
  booted = true;
  if (GUEST) $("setSum").textContent = T(LIGHT ? "Change the settings, then press Save. Settings are kept with your profile, on every device you use."
    : "Turn the knobs and flip the switches, then press Save. Settings are kept with your profile, on every device you use.");
  fitSideways();
  if (document.fonts && document.fonts.addEventListener) document.fonts.addEventListener("loadingdone", () => { clearTiles(); refreshPanels(true); });
  if (S.demo || !relayV5()) spotted = S.demo ? demoLog() : [];
  tickClock(); setInterval(tickClock, 1000);
  snapLoad();                                      // the last known board at once, until fresh data comes (1.51)
  renderFeatured(); renderLists(); updateFooter();
  if (relayV5()) syncSightings();
  dlog("info", `App started · ${S.demo ? "demo mode" : relay() ? "using the home relay" : "no relay"} · watching ${S.lat.toFixed(4)}, ${S.lon.toFixed(4)}, radius ${+S.radiusKm || 15} km`, "");
  // Every data source at once, so the board fills as fast as it can (positions, today's list, the logbook the tiers
  // need, the hello that tells the relay where this screen looks); then each on its usual timer.
  poll(true); if (relayV5()) fetchLogbook(); if (airportMode()) airportPos(); sayHello();
  listsLoad(true).then(() => { listsMigrate(); renderFavBox(); svSig = recentSig = ""; renderLists(); });
  gameStart();
  setInterval(sayHello, 60000);
  // Turned on its side or upright again: the flaps take the other arrangement (the page's columns are CSS).
  const turned = () => { sideways(); heroLayout(); buildNowPages(); nowPanels(); fitSideways(); clearTiles(); refreshPanels(true); paintRwy(); if (tab === "radar") radarSize(); };
  SIDEWAYS.addEventListener ? SIDEWAYS.addEventListener("change", turned) : SIDEWAYS.addListener && SIDEWAYS.addListener(turned);
}
//@L:extra
// (the glass version, tools/glass/, adds its own layer here; the app and the light version have none)
//@L:end
start();
})();
</script>
</body>
</html>
