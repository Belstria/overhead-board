# The board's sounds

Since 1.17 the Settings controls play short recordings (the flaps did too until 1.19.1, when their synthesised clack
came back), embedded in the boards (the `@sounds-begin` /
`@sounds-end` block) and copied into the phone app. Settings → Sounds → CLASSIC plays the earlier synthesised sounds
instead (they stay in the code as the fallback, also while the recordings are still being decoded).

## Where they come from

| Sound | Recording | Author | License |
|-------|-----------|--------|---------|
| Flip switches | [rocker_switch.wav](https://freesound.org/people/joedeshon/sounds/119415/) | joedeshon | CC BY 4.0 |
| Rotary knobs | [Clicky Knob Turning.wav](https://freesound.org/people/shewbox/sounds/30827/) | shewbox | CC BY 3.0 |
| Thumbwheels | [push_button_switch_07.wav](https://freesound.org/people/joedeshon/sounds/139061/) | joedeshon | CC BY 4.0 |
| Page and view buttons | [Switching button 2](https://pixabay.com/sound-effects/switching-button-2-461629/) | EAGLAXLE | Pixabay Content License |

All are credited in About.

## Rebuilding them

The original files are not in the repository. Download them (Freesound needs a free account) into `sounds-src/`
(git-ignored) and run from the repository root:

```bash
py tools/sounds/build_sounds.py
```

It finds the single clicks in the long recordings (the cleanest: loud, quiet just before, not overlapping the next),
cuts them with short fades, evens out their level, halves the sample rate (22 kHz mono is plenty: everything above
6.5 kHz is filtered on playback anyway) and writes them into `test-api/` and `test/`, plus listening copies in
`sounds-src/out/`. The Pixabay file is an MP3: decode it to `sounds-src/eaglaxle-switching-button-2.wav` first (the
script `audio.py` has no MP3 decoder; Chromium's `decodeAudioData` was used). Then rebuild the app
(`py tools/app/build.py`).
