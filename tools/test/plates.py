"""The Settings plates' overflow check (1.58, #47 step 5), shared by smoke.py and shoot.py (step `plates`).

A board's plates have a fixed size and clip what sticks out (a TV can't scroll), so every child of a plate must end
inside it. OVERFLOW_JS lists the plates on the page whose content runs past their bottom or right edge (empty: all fit).
"""

OVERFLOW_JS = r"""() => [...document.querySelectorAll("#cockpit .plate")].map(p => {
  const r = p.getBoundingClientRect();
  let bottom = 0, right = 0;
  for (const c of p.children) {
    if (c.matches("i")) continue;
    const b = c.getBoundingClientRect();
    bottom = Math.max(bottom, b.bottom); right = Math.max(right, b.right);
  }
  const h = (p.querySelector("h3") || {}).textContent || "?";
  return bottom > r.bottom + .5 ? `${h}: ${(bottom - r.bottom).toFixed(1)} px below` : right > r.right + .5 ? `${h}: ${(right - r.right).toFixed(1)} px right` : "";
}).filter(Boolean)"""

FIRE_TV = {"viewport": {"width": 960, "height": 540}, "device_scale_factor": 2,
           "user_agent": "Mozilla/5.0 (Linux; Android 9; AFTKA Build/PS7633) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Mobile Safari/537.36"}
