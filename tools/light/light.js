// The light version's code for the parts of tools/app/main.js marked //@L:name ... //@L:end (the split flaps, the
// metal, the flap greeting). tools/light/build.py puts each region below in place of the app's; everything else is
// the app's own code. Every region in main.js needs one here.

//@L:flag
const LIGHT = true;                   // the light version: the same app without the split flaps
//@L:end

//@L:engine1
/* ---------- the light version: plain fields in place of the flaps ----------
   The app's panels and fields (makePanel, def, placeRow and their layouts) are kept, but each field is an element: its
   label above its value, the value in the board's fonts and colours. A new value slides in with a quick fade; nothing
   turns. Status words are coloured pills (chip()), the airline its logo and name, the tier its sign and name. */
const LITE = () => false;
const fields = {}, allCells = [], panels = [];
function makePanel(el, w, h){
  const P = {el, w, h, ids: [], off: false, cssW: 1};
  el.classList.remove("panel"); el.classList.add("lp");
  el.removeAttribute("role"); el.removeAttribute("aria-label");      // its text is real text now
  el.textContent = "";
  panels.push(P);
  return P;
}
function def(P, id, o){
  const f = fields[id] = {id, align: "left", panel: P, ...o, cur: "", html: null, tok: 0, cells: []};
  P.ids.push(id);
  const el = f.el = document.createElement("div");
  el.className = "lf" + (f.kind === "word" ? " w-" + f.words : "") + (f.style === "amber" ? " amb" : "") + (f.align === "right" ? " r" : "");
  el.dataset.f = id;
  el.style.setProperty("--n", f.n || 1);
  el.innerHTML = (f.label ? `<span class="ll"></span>` : "") + `<span class="lv"></span>`;
  f.v = el.lastChild; f.ll = f.label ? el.firstChild : null;
  let hid = false;
  Object.defineProperty(f, "hidden", {get: () => hid, set: v => { hid = !!v; el.hidden = hid; }});
  P.el.appendChild(el);
  lfLabel(f); lfPaint(f, false);
}
const lfLabel = f => { if (f.ll) f.ll.textContent = T(f.label[0]); };
// A row of fields, in the order given; the app's layouts call it again when the phone turns.
function placeRow(ids){
  const fs = ids.map(id => fields[id]).filter(Boolean);
  if (!fs.length) return;
  const P = fs[0].panel, row = document.createElement("div");
  row.className = "lrow"; row.dataset.r = fs[0].id;
  for (const f of fs) row.appendChild(f.el);
  P.el.appendChild(row);
  for (const r of [...P.el.children]) if (r.classList.contains("lrow") && !r.children.length) r.remove();
}
//@L:end

//@L:engine2
//@E3
function drawCell(){}
function redrawAll(){ for (const f of Object.values(fields)) if (f.words === "airline") lfPaint(f, false); }   // a logo came in
// The values: text as it comes (no flap alphabet), shown a moment after `delay` so a row still fills in from the left.
function setChars(id, text, delay = 0){
  const f = fields[id];
  if (f) lfSet(f, String(text ?? "").replace(/\s+/g, " ").trim(), delay);
}
function setWord(id, text, delay = 0){
  const f = fields[id];
  if (f) lfSet(f, f.words === "airline" && /^-?\|?$/.test(String(text || "")) ? "" : String(text || ""), delay);   // "-|": no airline
}
function lfSet(f, v, delay){
  if (v === f.cur) return;
  f.cur = v;
  const tok = ++f.tok, go = () => { if (tok === f.tok) lfPaint(f, true); }, d = REDUCED ? 0 : Math.min(420, delay * .3);
  if (d) setTimeout(go, d); else go();
}
function lfPaint(f, anim){
  const html = lfHtml(f, f.cur);
  if (html === f.html) return;
  f.html = html; f.v.innerHTML = html;
  f.el.classList.toggle("nil", !f.cur);
  if (anim && !REDUCED && f.v.animate && f.el.offsetParent)
    f.v.animate([{opacity: 0, transform: "translateY(30%)", filter: "blur(2px)"}, {opacity: 1, transform: "none", filter: "none"}],
      {duration: 260, easing: "cubic-bezier(.2,.8,.25,1)"});
}
const TREND_ARROW = {UP: "↗", DOWN: "↘", LEVEL: "→"}, TREND_NAME = {UP: "Climbing", DOWN: "Descending", LEVEL: "Level"};
function lfHtml(f, v){
  if (!v) return "";
  if (f.kind !== "word") return escH(v);
  if (f.words === "remarks") return chip(v);
  if (f.words === "trend") return TREND_ARROW[v] ? `<span class="trend t-${v.toLowerCase()}" title="${escH(T(TREND_NAME[v]))}">${TREND_ARROW[v]}</span>` : "";
  if (f.words === "tier") return TIER_COL[v] ? `<span class="tierP" style="--c:${TIER_COL[v]}"><img src="${tierIcon(v)}" alt="">${escH(T(TIER_NAME[v]))}</span>` : "";
  if (f.words === "airline") {
    const [code, name] = v.split("|"), L = code && code !== "-" ? logo(code) : null;
    return (L && L.state === "ok" ? `<img class="alogo" src="${escH(L.img.src)}" alt="">` : "") + `<span>${escH(name || (code !== "-" ? code : ""))}</span>`;
  }
  return escH(v);
}
function sizePanel(){ return true; }
function showPanel(){}
// The labels and words again in a new language.
function refreshPanels(force){
  if (!force) return;
  for (const f of Object.values(fields)) { lfLabel(f); if (f.kind === "word") { f.html = null; lfPaint(f, false); } }
}
//@L:end

//@L:static
//@L:end

//@L:metal
function metalTile(){}                  // no metal: a plain dark background
//@L:end

//@L:radar
// The scope without the instrument's bezel and screws: a flat disc with a thin rim.
function radarStatic(){
  const g = $("radarBg").getContext("2d"), {cx, cy, R} = RG;
  g.setTransform(1, 0, 0, 1, 0, 0); g.clearRect(0, 0, g.canvas.width, g.canvas.height);
  g.setTransform(radar.px, 0, 0, radar.px, 0, 0);
  g.fillStyle = "#0d0f11"; g.beginPath(); g.arc(cx, cy, R, 0, Math.PI * 2); g.fill();
  g.strokeStyle = "rgba(255,255,255,.1)"; g.lineWidth = 1; g.beginPath(); g.arc(cx, cy, R + 6, 0, Math.PI * 2); g.stroke();
}
//@L:end

//@L:cockpit
// The light version's Settings: the app's, without the flap settings (`flaps: true` in the board's COCKPIT) and with the
// changes its `light: {…}` entries make (Sounds for the buttons and switches, wider cells).
const COCKPIT_FOR = "light";
//@L:end

//@L:taps
// A tap on the plane's fields opens a card: the airline's, a place's, the model's, or the plane's.
HINTS.sound = "Clicks when you press buttons and switches.";
$("hero").addEventListener("click", e => {
  const el = e.target.closest && e.target.closest("[data-f]");
  if (!el || !feat || !feat.o) return;
  const id = el.dataset.f, info = feat.info || baseInfo(feat.o.ac);
  if (id === "airline") airlineCard(liveFacts(feat.o.ac, info));
  else if (id === "fromCode" || id === "fromCity") placeCard(info.from);
  else if (id === "toCode" || id === "toCity") placeCard(info.to);
  else if (id === "type") typeCard({typeCode: feat.o.ac.t, type: info.type});
  else planeCard(feat.o);
});
// The take-offs and landings upright: a row opens the plane's card, its city the place's.
for (const k of ["d", "a"]) $(k === "d" ? "apDP" : "apAP").addEventListener("click", e => {
  const el = e.target.closest && e.target.closest("[data-f]"), m = el && /^nu[da](\d+)(\w+)$/.exec(el.dataset.f);
  const row = m && (k === "d" ? AP.deps : AP.arrs)[+m[1]];
  if (!row) return;
  const info = row.info || baseInfo(row.ac);
  if (m[2] === "city") return placeCard(k === "d" ? info.to : info.from);
  planeCard({ac: row.ac, alt: row.alt});
});
//@L:end

//@L:greet
// The welcome's greeting: FALLBLATT, then "Hi Anna!" sliding in letter by letter (the app turns flaps here).
let greeted = false;
function greetSay(text, step){
  const el = $("wHello");
  el.innerHTML = [...text].map((ch, i) => `<span style="animation-delay:${i * step}ms">${ch === " " ? "&nbsp;" : escH(ch)}</span>`).join("");
}
function greetFlaps(){
  $("wHello").classList.add("lgreet");
  setTimeout(() => { if (!greeted) greetSay("FALLBLATT", 45); }, splashLeft() + 300);
}
const splashLeft = () => Math.max(0, (window.SPLASH_END || 0) - performance.now());
function greetRoll(){
  greeted = true;
  greetSay(T("Hi {name}!", {name: String(GUEST.name || "").trim().split(/\s+/)[0] || ""}), 55);
  setTimeout(() => { soundForced = false; }, 2500);
}
//@L:end

//@L:extra
//@L:end
