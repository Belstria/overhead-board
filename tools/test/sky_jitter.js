// Sky view's label jitter with a made-up sensor stream (1.90): node tools/test/sky_jitter.js [main.js]
// Runs main.js's own sensor code (arOrient and what it calls) on Android's two readings at 60 Hz: the gyroscope's
// (turns as the phone does, its zero anywhere, drifting .02°/s, a little noise) and the compass's (noisy; indoors it also swings with
// where the phone is). The phone is held still, turned, held still, panned slowly and held still again. Prints how
// much the labels move while the phone is still (frame to frame and over each still spell) and how far off north is.
"use strict";
const fs = require("fs"), path = require("path");
const src = fs.readFileSync(process.argv[2] || path.join(__dirname, "../app/main.js"), "utf8");
const a = src.indexOf("const arPossible"), b = src.indexOf("async function arOpen(){");
const c = src.indexOf("function arCalCheck("), d = src.indexOf("function arClose(){");
if (a < 0 || b < 0 || c < 0 || d < 0) throw new Error("main.js changed: Sky view's sensor code not found");
const PX = 844 / 2 / Math.tan(32 * Math.PI / 180) * Math.PI / 180;   // screen px per degree on a 390x844 phone

function run(world, seed){
  let clock = 0, rnd = seed;
  const rand = () => { rnd = (rnd * 16807) % 2147483647; return rnd / 2147483647; };
  const gauss = () => Math.sqrt(-2 * Math.log(rand() + 1e-12)) * Math.cos(2 * Math.PI * rand());
  const el = {hidden: true, innerHTML: "", textContent: ""};
  const sandbox = {
    window: {}, performance: {now: () => clock}, Date: {now: () => 1.8e12 + clock}, $: () => el, dlog(){}, T: s => s, escH: s => s,
    DeviceOrientationEvent: function(){}, navigator: {}, localStorage: {getItem(){ return null; }, setItem(){}},
  };
  const code = src.slice(a, b) + src.slice(c, d) + "\n;({arOrient, get arQ(){ return arQ; }, arQMatrix, arYaw});";
  const ar = new Function(...Object.keys(sandbox), "return eval(" + JSON.stringify(code) + ")")(...Object.values(sandbox));
  const I = [[1, 0, 0], [0, 1, 0], [0, 0, 1]], shown = [], dt = 1000 / 60;
  for (let i = 0; clock < 40000; i++, clock += dt) {
    const t = clock / 1000, yaw = world.yaw(t), beta = 70;
    // the compass's reading a moment before the gyroscope's, as on Android
    ar.arOrient({type: "deviceorientationabsolute", absolute: true, alpha: (yaw + world.compass(t, yaw, gauss) + 360) % 360, beta, gamma: 0});
    ar.arOrient({type: "deviceorientation", absolute: false, alpha: (yaw + 77 + .02 * t + .05 * gauss() + 360) % 360, beta, gamma: 0});
    if (ar.arQ) shown.push([t, yaw, ar.arYaw(ar.arQMatrix(ar.arQ), I), world.still(t)]);
  }
  const w = d => ((d % 360) + 540) % 360 - 180;
  let step = 0, n = 0, span = 0, err = 0, ne = 0, spells = [], cur = null;
  for (let i = 1; i < shown.length; i++) {
    const [t, yaw, s, still] = shown[i];
    if (t > 2) { err += Math.abs(w(s - yaw)); ne++; }
    if (!still || t < 2) { cur = null; continue; }
    step += w(s - shown[i - 1][2]) ** 2; n++;
    if (!cur) spells.push(cur = {lo: Infinity, hi: -Infinity});
    const e = w(s - yaw); cur.lo = Math.min(cur.lo, e); cur.hi = Math.max(cur.hi, e);
  }
  for (const c of spells) span = Math.max(span, c.hi - c.lo);
  return {frame: Math.sqrt(step / n), span, err: err / ne};
}
// the phone: still 0-10 s at 30°, turned to 120° in 2 s, still, panned slowly back to 60° in 5 s, still
const ease = x => x <= 0 ? 0 : x >= 1 ? 1 : (1 - Math.cos(Math.PI * x)) / 2;
const yaw = t => 30 + 90 * ease((t - 10) / 2) - 60 * ease((t - 25) / 5);
const still = t => !(t > 9.9 && t < 12.6) && !(t > 24.9 && t < 30.6);
const worlds = {
  "outdoors (compass ±1.5°)": {yaw, still, compass: (t, y, g) => 1.5 * g()},
  "indoors (±3°, swinging ±8° with time and heading)": {yaw, still, compass: (t, y, g) => 3 * g() + 5 * Math.sin(t * 2 * Math.PI / 5.3) + 3 * Math.sin(t * 2 * Math.PI / 2.9 + 1) + 6 * Math.sin(y * Math.PI / 180)},
};
for (const [name, world] of Object.entries(worlds)) {
  const r = [1, 2, 3, 4, 5].map(s => run(world, s * 7919));
  const avg = k => r.reduce((x, o) => x + o[k], 0) / r.length;
  console.log(`${name}:\n  still, frame to frame ${avg("frame").toFixed(3)}° (${(avg("frame") * PX).toFixed(2)} px)` +
    ` · still, most a label wanders in one spell ${avg("span").toFixed(2)}° (${(avg("span") * PX).toFixed(1)} px) · north off by ${avg("err").toFixed(2)}° on average`);
}
