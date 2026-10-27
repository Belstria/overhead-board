# The board's sounds

Since 1.17 the Settings controls play short recordings (the flaps did too until 1.19.1, when their synthesised clack
came back), since 1.53.1 in `test/sounds.js` next to the test board (before, embedded in the board), loaded by
the boards and the phone app when sound is on. If it can't be loaded, the synthesised sounds play. Settings → Sounds → CLASSIC plays the earlier synthesised sounds
instead (they stay in the code as the fallback, also while the recordings are still being decoded).

## Where they come from

| Sound | Recording | Author | License |
|-------|-----------|--------|---------|
| Flip switches | [rocker_switch.wav](https://freesound.org/people/joedeshon/sounds/119415/) | joedeshon | CC BY 4.0 |
| Rotary knobs | [Clicky Knob Turning.wav](https://freesound.org/people/shewbox/sounds/30827/) | shewbox | CC BY 3.0 |
| Thumbwheels | [push_button_switch_07.wav](https://freesound.org/people/joedeshon/sounds/139061/) | joedeshon | CC BY 4.0 |
| Page and view buttons | [Switching button 2](https://pixabay.com/sound-effects/switching-button-2-461629/) | EAGLAXLE | Pixabay Content License |
| Small buttons, chips, × (1.97.2) | [technology click 0](https://pixabay.com/sound-effects/) (Pixabay 481191) | Pixabay | Pixabay Content License |
| Navigation: cards, rows, tabs, links (1.97.2) | [immersivecontrol button click](https://pixabay.com/sound-effects/) (Pixabay 463065) | Pixabay | Pixabay Content License |
| New plane ding (1.45; both tones since 1.46) | [Airbus Cabin PA Beep Tone](https://pixabay.com/sound-effects/film-special-effects-airbus-cabin-pa-beep-tone-passenger-announcement-chime-358248/) | arunangshubanerjee | Pixabay Content License |
| Barking dog (1.49: About tapped seven times) | [Airbus PTU barking dog](https://pixabay.com/sound-effects/nature-airbus-ptu-barking-dog-297945/) | arunangshubanerjee | Pixabay Content License |

All are credited in About.

## Rebuilding them

The original files are not in the repository. Download them (Freesound needs a free account) into `sounds-src/`
(git-ignored) and run from the repository root:

```bash
py tools/sounds/build_sounds.py
```

It finds the single clicks in the long recordings (the cleanest: loud, quiet just before, not overlapping the next),
cuts them with short fades, evens out their level, halves the sample rate (22 kHz mono is plenty: everything above
6.5 kHz is filtered on playback anyway) and writes them to `test/sounds.js` (and stamps its new version into the test board: `tools/assets.py`), plus listening copies in
`sounds-src/out/`. The Pixabay file is an MP3: decode it to `sounds-src/eaglaxle-switching-button-2.wav` first (and the cabin chime to
`sounds-src/arunangshubanerjee-airbus-cabin-pa-beep.wav`, and the barking dog to
`sounds-src/arunangshubanerjee-airbus-ptu-barking-dog.wav`) (the
script `audio.py` has no MP3 decoder; Chromium's `decodeAudioData` was used). Then rebuild the app
(`py tools/app/build.py`).

The two clicks (1.97.2) are MP3s too: decoded in Chromium to `sounds-src/tech-click.wav` and `sounds-src/nav-click.wav` (mono, 44.1 kHz).
`click()` in `build_sounds.py` cuts them right at the click (357 ms and 24 ms in; no leading silence) with a fade-out and
the quiet end dropped. A sound whose recording isn't in `sounds-src/` keeps its line in `test/sounds.js`, so a single
sound can be rebuilt on its own.

The barking dog (1.49) is the steady bark-bark-bark from 3.9 to 7.25 s of the recording: a 150 Hz high-pass takes the
cabin's rumble away, a gentle gate (`audio.gate`: below the level between the barks it turns the background down to
15%, smoothly) softens the hum between the barks, the last second fades out (`audio.fade_out`) so it doesn't stop
abruptly, and it is kept at 11 kHz (it is all below 4 kHz), about 3.4 s.

The Emirates airline card's boarding music (1.49) is not here and never goes into the repository (it is copyrighted):
the relay serves it to signed-in screens from its own `data/media/emirates-boarding.m4a`.
