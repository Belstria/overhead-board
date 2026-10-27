// Sky view's label jitter with a made-up sensor stream (1.90; turning with real reading times, 1.95.0.2): node tools/test/sky_jitter.js [main.js]
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

// main.js's sensor code on a clock of the test's (ms), and a seeded noise
function load(now, seed){
  let rnd = seed;
  const rand = () => { rnd = (rnd * 16807) % 2147483647; return rnd / 2147483647; };
  const gauss = () => Math.sqrt(-2 * Math.log(rand() + 1e-12)) * Math.cos(2 * Math.PI * rand());
  const el = {hidden: true, innerHTML: "", textContent: ""};
  const sandbox = {
    window: {}, performance: {now}, Date: {now: () => 1.8e12 + now()}, $: () => el, dlog(){}, T: s => s, escH: s => s,
    DeviceOrientationEvent: function(){}, navigator: {}, localStorage: {getItem(){ return null; }, setItem(){}},
  };
  const code = src.slice(a, b) + src.slice(c, d) + "\n;({arOrient, arFrame: typeof arFrame === \"function\" ? arFrame : null, arMotion: typeof arMotion === \"function\" ? arMotion : null, get arQ(){ return arQ; }, arQMatrix, arYaw});";
  return [new Function(...Object.keys(sandbox), "return eval(" + JSON.stringify(code) + ")")(...Object.values(sandbox)), gauss];
}
const I = [[1, 0, 0], [0, 1, 0], [0, 0, 1]];

function run(world, seed){
  let clock = 0;
  const [ar, gauss] = load(() => clock, seed), shown = [], dt = 1000 / 60;
  for (; clock < 40000; clock += dt) {
    const t = clock / 1000, yaw = world.yaw(t), beta = 70, zero = 77 + (world.jump ? world.jump(t) : 0);
    // the compass's reading a moment before the gyroscope's, as on Android
    ar.arOrient({type: "deviceorientationabsolute", absolute: true, alpha: (yaw + world.compass(t, yaw, gauss) + 360) % 360, beta, gamma: 0});
    ar.arOrient({type: "deviceorientation", absolute: false, alpha: (yaw + zero + .02 * t + .05 * gauss() + 360) % 360, beta, gamma: 0});
    if (ar.arFrame) ar.arFrame(clock);                // 1.95.0.2: the labels are placed each frame
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

// 1.95.0.2 (to-do #125): turning, with the readings coming in when they did in Dave's recording (27 Oct 2026, Android,
// Chrome): the gaps (ms) between the moments its labels moved, while one stayed in view. Chrome hands the readings over
// on the page's own thread, so a busy page gets them late and bunched; and none while no angle changes by 0.1°. The
// phone is held still 3 s, looks round for 6 s (up to 50°/s), pans 30° at 37°/s and stops dead, and is held still.
// Each frame (60 Hz) the labels are drawn: how unevenly they move while turning (the change of their step from frame to
// frame), the frames they stand still while the sky moves, how far behind the sky they are, and after the stop how far
// they run on and when they are back within 0.2° for good.
const GAPS = [10,19,30,15,35,16,37,63,33,34,15,107,10,84,49,17,49,18,15,134,33,16,119,32,17,49,16,18,99,35,14,18,119,13,33,
  35,85,16,33,18,17,99,33,133,34,17,16,84,33,33,16,18,49,37,30,18,17,15,66,19,55,25,68,16,84,100,120,46,86,67,100,19,62,85,34,
  49,68,33,132];
const look = t => t < 3 ? 30 : t < 9 ? 30 + ease((t - 3) / .4) * (25 * Math.sin(1.3 * (t - 3)) + 6 * Math.sin(3.1 * (t - 3))) : look(8.999) + 37.5 * Math.min(.8, t - 9);
function turning(gaps, seed){
  let clock = 0, next = 0, gi = 0, sent = null;
  const [ar, gauss] = load(() => clock, seed), shown = [];
  for (let f = 0; f < 12000; f += 1000 / 60) {
    for (; next <= f; next += gaps[gi++ % gaps.length]) {     // the readings handed over before this frame
      clock = next;
      const t = next / 1000, yaw = look(t), alpha = (yaw + 77 + .05 * gauss() + 360) % 360;
      // the gyroscope's rate comes every time (devicemotion); the orientation only once an angle changed by 0.1°
      if (ar.arMotion) ar.arMotion({rotationRate: {alpha: (look(t + .001) - yaw) / .001 + .3 * gauss(), beta: .3 * gauss(), gamma: .3 * gauss()}});
      if (sent != null && Math.abs(w180(alpha - sent)) < .1) continue;
      // (the compass right: north stays put, so the labels' own motion is what is measured)
      ar.arOrient({type: "deviceorientationabsolute", absolute: true, alpha: (yaw + 360) % 360, beta: 70, gamma: 0});
      ar.arOrient({type: "deviceorientation", absolute: false, alpha, beta: 70, gamma: 0});
      sent = alpha;
    }
    clock = f;
    if (ar.arFrame) ar.arFrame(clock);
    if (ar.arQ) shown.push([f / 1000, look(f / 1000), ar.arYaw(ar.arQMatrix(ar.arQ), I)]);
  }
  const mean = xs => xs.reduce((x, y) => x + y, 0) / xs.length;
  const e0 = mean(shown.filter(s => s[0] > 2 && s[0] < 3).map(s => w180(s[2] - s[1])));
  const eEnd = mean(shown.filter(s => s[0] > 11.5).map(s => w180(s[2] - s[1])));
  let uneven = [], held = 0, moving = 0, behind = [], runOn = 0, back = 0;
  for (let i = 2; i < shown.length; i++) {
    const [t, yaw, s] = shown[i], ls = w180(s - shown[i - 1][2]) * PX, ts = w180(yaw - shown[i - 1][1]) * PX;
    if (t > 3.1 && t < 9.8) {
      uneven.push(Math.abs(ls - w180(shown[i - 1][2] - shown[i - 2][2]) * PX));
      if (Math.abs(ts) > 3) { moving++; if (Math.abs(ls) < .3) held++; }
      behind.push(Math.abs(w180(s - yaw) - e0) * PX);
    }
    if (t >= 9.8) {
      const ahead = w180(s - yaw) - eEnd, e = Math.abs(ahead);   // (the pan turns alpha up: ahead of the sky is +)
      if (t < 10.8) runOn = Math.max(runOn, ahead * PX);
      if (e >= .2) back = t - 9.8;
    }
  }
  return {uneven: mean(uneven), worst: Math.max(...uneven), held: held / moving, behind: mean(behind), runOn, back};
}
for (const [name, gaps] of [["readings as late and bunched as in Dave's recording", GAPS], ["a reading every frame", [1000 / 60]]]) {
  const r = [1, 2, 3, 4, 5].map(s => turning(gaps, s * 7919));
  const avg = k => r.reduce((x, o) => x + o[k], 0) / r.length;
  console.log(`turning, ${name}:\n  uneven ${avg("uneven").toFixed(1)} px from frame to frame (worst ${avg("worst").toFixed(0)} px)` +
    ` · still while the sky moves in ${(avg("held") * 100).toFixed(0)}% of frames · ${avg("behind").toFixed(1)} px behind on average` +
    ` · after a stop runs on past the sky ${avg("runOn").toFixed(1)} px, back within 0.2° after ${avg("back").toFixed(2)} s`);
}
