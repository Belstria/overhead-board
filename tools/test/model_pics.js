// The model pictures' lookup (1.93.1.1, to-do #112) over a list of type codes: which get a picture, from which page and
// in how many requests. node tools/test/model_pics.js [list.json] [--sheet sheet.html]
// list.json: [{"code": "BE20", "names": ["BEECH 200 Super King Air"]}, ...], the names as the sources give them (a
// logbook's types, say); each name is looked up as a type card would ask (the board's TYPES name first, then that one).
// Without a list: the board's TYPES. Runs test/index.html's own code against Wikipedia, one request at a time (Wikimedia
// allows 200 a minute), so a long list takes minutes. --sheet writes a page of every picture found, to check by eye.
"use strict";
const fs = require("fs"), path = require("path");
const src = fs.readFileSync(path.join(__dirname, "../../test/index.html"), "utf8");
const cut = (a, b) => { const i = src.indexOf(a), j = src.indexOf(b, i); if (i < 0 || j < 0) throw new Error("test/index.html changed: " + a + " not found"); return src.slice(i, j); };
const code = cut("const TYPES = {", "function typeName(") + cut("// Wikipedia's summary of a page", "/* 1.93 (to-do #95");
const args = process.argv.slice(2), sheetAt = args.indexOf("--sheet"), sheet = sheetAt >= 0 ? args.splice(sheetAt, 2)[1] : "";
const UA = "Fallblatt-model-pics/1.0 (https://github.com/Belstria/overhead-board)";      // Wikimedia asks for a name and a contact
let asked = 0, next = 0;
async function fetchJSON(url){
  for (let i = 0; i < 6; i++) {
    await new Promise(r => setTimeout(r, Math.max(0, next - Date.now())));
    next = Date.now() + 350; asked++;
    const r = await fetch(url, {headers: {"User-Agent": UA}});
    if (r.status === 429) { next = Date.now() + 1000 * (+r.headers.get("retry-after") || 10); continue; }
    if (!r.ok) throw new Error("HTTP " + r.status);
    return r.json();
  }
  throw new Error("Wikipedia keeps saying: too many requests");
}
const S = {demo: false};
const api = new Function("fetchJSON", "fetch", "S", code + "\n;return {TYPES, modelPage, modelLooks, wikiImg};")(fetchJSON, (u, o) => fetch(u, {...o, headers: {"User-Agent": UA}}), S);
const list = args[0] ? JSON.parse(fs.readFileSync(args[0], "utf8")) : Object.entries(api.TYPES).map(([c, n]) => ({code: c, names: [n]}));
const esc = s => String(s).replace(/[&<>"]/g, c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;"})[c]);
(async () => {
  const rows = [];
  let all = 0, some = 0, most = 0;
  for (const {code: c, names} of list) {
    const t = api.TYPES[c], found = [];
    for (const n of names.length ? names : [""]) {
      api.modelLooks.clear();
      const a0 = asked, p = await api.modelPage([t || n || c, n || t || c], c).catch(e => ({title: "", err: e.message}));
      most = Math.max(most, asked - a0);
      found.push({name: n || t || c, title: p ? p.title : "", img: p && p.img ? api.wikiImg(p.img, 500) : "", err: p && p.err, n: asked - a0});
    }
    const ok = found.filter(f => f.img).length;
    all += ok === found.length; some += ok > 0;
    console.log(`${ok === found.length ? "OK  " : ok ? "PART" : "MISS"} ${c.padEnd(5)} ${found.map(f => `${f.name} -> ${f.title || "-"}${f.title && !f.img ? " (no picture)" : ""}${f.err ? " (" + f.err + ")" : ""}`).join(" | ")}`);
    rows.push(...found.filter(f => f.img).map(f => ({code: c, ...f})));
  }
  console.log(`\n${all} of ${list.length} codes have a picture for every name, ${some} for at least one; ${asked} requests, at most ${most} for one`);
  if (sheet) fs.writeFileSync(sheet, `<!doctype html><meta charset="utf-8"><title>Model pictures</title><style>body{font:13px sans-serif;margin:12px;background:#fff}
.g{display:grid;grid-template-columns:repeat(auto-fill,220px);gap:10px}figure{margin:0;border:1px solid #ccc;padding:4px}img{width:210px;height:140px;object-fit:cover;display:block}
b{font-size:14px}small{display:block;color:#555}</style><div class="g">` + rows.map(r => `<figure><img src="${esc(r.img)}" referrerpolicy="no-referrer" alt=""><b>${esc(r.code)}</b> ${esc(r.name)}<small>${esc(r.title)}</small></figure>`).join("") + "</div>");
})();
