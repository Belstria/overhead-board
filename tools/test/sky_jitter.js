// Sky view's label jitter with a made-up sensor stream (1.90): node tools/test/sky_jitter.js [main.js]
// Runs main.js's own sensor code (arOrient and what it calls) on Android's two readings at 60 Hz: the gyroscope's
// (turns as the phone does, its zero anywhere, drifting .02°/s, a little noise) and the compass's (noisy; indoors it
// also swings with time and where the phone points). The phone is held still, turned, held still, panned slowly and
// held still again. Prints how much the labels move while the phone is still (frame to frame, and the most within one
// still spell), how far off north is on average, and when north was last more than 2° off (after a wrong start or the
// gyroscope's zero jumping, how long it takes to come right).
"use strict";
const fs = require("fs"), path = require("path");
const src = fs.readFileSync(process.argv[2] || path.join(__dirname, "../app/main.js"), "utf8");
const a = src.indexOf("const arPossible"), b = src.indexOf("async function arOpen(){");
const c = src.indexOf("function arCalCheck("), d = src.indexOf("function arClose(){");
if (a < 0 || b < 0 || c < 0 || d < 0) throw new Error("main.js changed: Sky view's sensor code not found");
const PX = 844 / 2 / Math.tan(32 * Math.PI / 180) * Math.PI / 180;   // screen px per degree on a 390x844 phone
const w180 = d => ((d % 360) + 540) % 360 - 180;

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
  for (; clock < 40000; clock += dt) {
    const t = clock / 1000, yaw = world.yaw(t), beta = 70, zero = 77 + (world.jump ? world.jump(t) : 0);
    // the compass's reading a moment before the gyroscope's, as on Android
    ar.arOrient({type: "deviceorientationabsolute", absolute: true, alpha: (yaw + world.compass(t, yaw, gauss) + 360) % 360, beta, gamma: 0});
    ar.arOrient({type: "deviceorientation", absolute: false, alpha: (yaw + zero + .02 * t + .05 * gauss() + 360) % 360, beta, gamma: 0});
    if (ar.arQ) shown.push([t, yaw, ar.arYaw(ar.arQMatrix(ar.arQ), I), world.still(t)]);
  }
  let step = 0, n = 0, span = 0, err = 0, ne = 0, last = 0, cur = null;
  const spells = [];
  for (let i = 1; i < shown.length; i++) {
    const [t, yaw, s, still] = shown[i], e = w180(s - yaw);
    if (t > 2) { err += Math.abs(e); ne++; }
    if (Math.abs(e) > 2) last = t;
    if (!still || t < 2) { cur = null; continue; }
    step += w180(s - shown[i - 1][2]) ** 2; n++;
    if (!cur) spells.push(cur = {lo: Infinity, hi: -Infinity});
    cur.lo = Math.min(cur.lo, e); cur.hi = Math.max(cur.hi, e);
  }
  for (const sp of spells) span = Math.max(span, sp.hi - sp.lo);
  return {frame: Math.sqrt(step / n), span, err: err / ne, last};
}
// the phone: still 0-10 s at 30°, turned to 120° in 2 s, still, panned slowly back to 60° in 5 s, still
const ease = x => x <= 0 ? 0 : x >= 1 ? 1 : (1 - Math.cos(Math.PI * x)) / 2;
const yaw = t => 30 + 90 * ease((t - 10) / 2) - 60 * ease((t - 25) / 5);
const still = t => !(t > 9.9 && t < 12.6) && !(t > 24.9 && t < 30.6);
const outdoors = (t, y, g) => 1.5 * g();
const worlds = {
  "outdoors (compass ±1.5°)": {yaw, still, compass: outdoors},
  "indoors (±3°, swinging ±8° with time and heading)": {yaw, still, compass: (t, y, g) => 3 * g() + 5 * Math.sin(t * 2 * Math.PI / 5.3) + 3 * Math.sin(t * 2 * Math.PI / 2.9 + 1) + 6 * Math.sin(y * Math.PI / 180)},
  "outdoors, the compass 25° off for its first 4 s": {yaw, still, compass: (t, y, g) => (t < 4 ? 25 : 0) + 1.5 * g()},
  "outdoors, the gyroscope's zero jumping 40° at 20 s": {yaw, still, compass: outdoors, jump: t => t > 20 ? 40 : 0},
};
for (const [name, world] of Object.entries(worlds)) {
  const r = [1, 2, 3, 4, 5].map(s => run(world, s * 7919));
  const avg = k => r.reduce((x, o) => x + o[k], 0) / r.length;
  console.log(`${name}:\n  still, frame to frame ${avg("frame").toFixed(3)}° (${(avg("frame") * PX).toFixed(2)} px)` +
    ` · most in one still spell ${avg("span").toFixed(2)}° (${(avg("span") * PX).toFixed(1)} px)` +
    ` · north off ${avg("err").toFixed(2)}° on average, last more than 2° off at ${avg("last").toFixed(1)} s`);
}
