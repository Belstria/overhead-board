# Fallblatt: version-by-version details

Moved out of `CLAUDE.md` (which holds the rules and the current architecture in short) so that every session
doesn't have to read it with every step. Read the part for the area you are touching: it says what each version
added and names the functions and fields involved. Text from before 1.49 / relay 42 is history: **"Home" as a
profile or identity no longer exists** (every screen is a profile's device since relay 42; `at_home()` only opens the
admin paths), the Flightradar24 budget is not 27,000 but 54,000 a month until 2027-01-08 and 27,000 after, and the
`homelink` / "Link a device to Home" idea went with Home. Where this file and the code disagree, the code wins.
The repository is public: no addresses, keys or personal data here either.

## How the board works (index.html and the test board)

- 1.73.3: `gTotSet` pads to five flaps, blank (no leading zeros).
- 1.77: **Opening sound** (head.html's splash script, `splashSound`): with sound on and outside quiet hours (read
  straight from the stored settings, the profile's or the relay defaults), where the phone lets a page play before a tap
  (the Android app: `mediaPlaybackRequiresUserGesture = false` already; a home-screen web app on Android; never an
  iPhone): a context of its own (closed after; given up if not running within 0.4 s), the board's clack for each letter
  as it lands (0.46 s into the `spFlap` animations, 45 ms apart, timed from their real start via
  `getAnimations().ready`, less the output latency) and a 1.05 s band-swept whoosh panned left to right at the
  take-off; the app's output chain (110 Hz/6.5 kHz cut, a 0.22 s room, a limiter). The letters flip in (`spFlap`:
  rotateX 90° → −14° → 5° → 0 in 0.32 s) instead of rising. **Sky view with live location**: `arTry` opens it with live
  on, else a card asks (`liveGo` green like the strip's Go live, `liveNo`); `arGoLive` asks iPhones for the motion
  sensors within the tap, runs `gGoLive` and opens Sky view at the first fix (15 s, then a note). **No plane on top**:
  `#skyRow` is now a `.look` card (heading, `#skyCv` tape as a compass via `drawTape`, split out of `drawLook`, the Sky
  view button, "No planes around right now").
- 1.76.1: Sky view's ring got E and W ticks (`arAimDraw`). Heights are above the sea now (`arHeight`; `arWeather` gives
  the METAR airport's `elev`), and the eye is the phone's own GPS height (`arAlt`, smoothed, used when its accuracy is
  60 m or better; else the airport's): on Santorini's caldera rim (260 m) a plane on final 5 km out was drawn 3.4° up,
  really 0.8°. Planes below you show below the horizon; a descent isn't carried on below the airport. With live location
  the airport (and its METAR) is the one nearest the phone, so all of Sky view follows a trip.
- 1.76 (Sky view lines up): **true north**: `magField`/`magDecl` evaluate the World Magnetic Model (WMM2025, NOAA NCEI,
  public domain; `tools/app/WMM.COF`, its g h ġ ḣ packed into `WMM_C`), checked against NOAA's 100 test values (to
  0.005°; Vienna 5.4° E in 2026). Added to the heading in `arProject` (`arDec`) and in Where to look's `lookHeadingFrom`.
  Drags saved before carry the declination: taken out once (`od.ar.off` gets `v: 2`, `arOffSave`). **Sun and moon**:
  `skyBodies` (the Astronomical Almanac's low-precision formulas, refraction, the moon seen from here; at three total
  eclipses sun and moon land within 0.2°), drawn by `arBodiesDraw` as dashed rings (the moon only when 4 % lit or
  more); the hint at the bottom asks to drag them into place. **AUTO** (`arAutoStep`, `arFind`, `arAutoChip`,
  `arBrackets`; `od.ar.auto`, on by default): every 160 ms the camera picture within 9° of each plane's label (planes
  under 15 km, over 2° up, not near another label or the sun) is scaled so the plane comes out ~3 samples across (span by
  ADS-B category), and searched for a spot that stands out from the 13×13 around it by 5× the noise, alone (a ring 5
  out stays quiet: no edges) and round (no line through it), with no second spot nearly as strong. Finds are kept as
  the offset that would put the label there; a plane counts with 5 finds in 2.5 s, 80 % within 0.7°; the planes counted
  must agree within 1.5°; the offset then glides there (τ 0.7 s) and is saved every 5 s. A drag pauses it 5 s. Tested
  with a synthetic camera: a compass 4–5° off ends 0.0–0.3° from the plane; an empty sky, a cloud edge or a contrail
  move nothing.
- 1.75.2 (Sky view accuracy): the board's `getAircraft` keeps the source's `now` on the list (`list.now`, `srcTime`:
  ms or s); `arFeed` dates the data from it (the relay keeps positions up to `FRESH_S`; clocks more than 2 min off fall
  back to arrival) and measures each plane's turn rate between updates (`arTurns`). `arMove` moves a plane on along its
  turn (`track_rate`, else the measured one; at most 20 s of it) and climb (`geom_rate`/`baro_rate`); `arHeight` makes
  the pressure altitude true with the home airport's METAR (`arWeather`: QNH from Q/A groups, temperature) and falls
  back to `alt_geom`. The orientation is a quaternion (`arQuat`, `arQMatrix`) smoothed as a whole, 1€-style (τ 0.2 s
  held still, 0.03 s turning): the per-angle smoothing broke where beta wraps (straight up) and gamma wraps (sideways).
  iPhones: gyro alpha plus a slowly followed gap to the compass (`arGap`; big gaps taken at once). `arProject` turned
  the screen the wrong way (sideways labels mirrored); `arFocal` takes the scale from the video's size (cover; a stream
  narrower than 4:3 sees less). `lookAt` (Where to look) uses `arMove`/`arHeight` too. The camera's size goes to the log.
- 1.75.1: the app's Logbook drops the Newest aircraft list (the board keeps it).
- 1.75 / relay 61: `CATEGORY_WORDS` in `search_json` (a category word narrows to `category_of`; alone it lists the
  category; the answer says `category` and `text`), rows carry `typeCode`, `callsign`, `airlineIata`.
  `/logbook/category?c=&place=` → `category_top_json` (top ten types, regs, operators over `_logbook_entries`, cached
  by `rev // 5` and 2 min). App: `.catTap` categories open in place (`lbCat`, `lbCatView`, `catOpenHtml`, `catFetch`;
  a type opens `typeCard`, an operator `airlineCard`, an aircraft fills the search); search shows `.lbfRead` chips and
  pills (`data-fp`) opening `typeCard`, `airlineCard` or `foundCard` (an aircraft card from the search row).
- 1.74: Spotters' Club (was the Game page, still `#t-game` / `showTab("game")`): `.lbTabs` title tabs on `#t-logbook`
  and `#t-game` (`data-lt`), a sideways swipe switches, the tab bar lights Logbook for both; hidden without relay 59.
  `periodHtml()` replaces `yearHtml()` and the Week & month view: `lbPeriod` (week / month / year) with a `.seg.lbPer`,
  ◀ ▶ (`data-pb`: `yearBack` or `review.back`), the year from `yearCache` per year, week and month from `/review`.
- 1.73.2: `locatedAt` (Here, an address, typed coordinates) ends live location (`liveHalt`, `S.live` and `draft.live`
  false): before, live kept running and a Settings save turned it back on, so a phone set to another address still
  scored where it was. `gGoLive` (a `.gSpin` in the chip until `liveFirst` clears, 15 s at most). Toasts in the app are
  dark pills (`--box-bg`, white border) from the right under the strip, swiped right to go (`touchstart`/`pointer`
  handlers on `#toasts .toast`). `gTotSet` pads to four flaps with dimmed zeros (`.z`). Sky view buttons get `.skyIco`.
  Remarks FIRST TYPE / PLANE / AIRLINE / FLIGHT (no "EVER").
- 1.73.1: the points for the plane on top are a HERO flap field `pts` (n 4, `PTS_ON` with relay 59; `seen` 15 then)
  beside the remarks; `gPtsRender` fills it, a tap on it (`#hero` click, before the other fields) toasts `gPtsText`.
  `#gPts` is gone. Where to look: `drawLook` draws a heading tape on `#lookCv` (±60°, ticks every 5°, names every 45°,
  the gold line where you face, the plane or an arrow at the end); with the compass the words say which way to turn;
  Sky view sits left of the words (`.lookRow`).
- 1.73: one look per kind in the app (the consistency check, https://claude.ai/artifact/GqHPCWGz21JFjmepi4S3j7):
  `--box-bg`/`--box-bd` for boxes (`.gPts`, `.skyRow`, `.look`, `.gCard`, `.rvCard`, `.yearCard`), `--sheet-bg` for
  `#cardBox .cardIn`, toasts, `#arCard`, `.arTourBox`; `.cBtn` app-wide (Sky view, Open, Styles, Share, CSV, tips'
  Next; the board's `.cap` stays in Settings); `.rcX`/`.cardX` round like `.tabX`; Today's filters a `.seg.svFilters`;
  bars 6 px; `.gLeague` rows as lines. Pop-up titles (gold capitals) and the checkboxes stayed, by Dave's choice.
- 1.72.8: `arTour`'s drag step acts it out (`.arTourDrag`: a plane in the ring, `.arTourLab` dragged onto it by
  `.arTourFinger`, green once in place).
- 1.72.7: Sky view's top bar: `.arTitle` pill and round frosted `.arIb` buttons `#arInfo` ⓘ, `#arReset` ⟲ (`.moved`, a gold
  ring and dot, while `arOff` isn't zero), `#arClose` ✕; `arMovedNote` after a drag; `arTour` (`AR_TOUR`: ring, drag,
  buttons; `od.ar.tour` once seen) the first time and from ⓘ.
- 1.72.6: `planeBody(o, sky)` → `skyBody()` for Sky view's whole card: `.cOv` (flight, airline `data-al`, status) on the
  photo `.cSkyPic` (plain when there's no photo), `.cRouteB` (from/to `data-pl`), `.cTiles` (alt, speed, dist via
  `data-dyn`), `.cDet` (aircraft `data-ty`, registration, operator, gate, remarks), buttons sharing the width.
- 1.72.5: the whole Sky view card opens up to the top bar (`arRoom()`, was 62 % of the screen), the photo in it at most
  32vh; the small card's countdown line (`#arTimer`) is gone (the 3 s still run).
- 1.72.4: `#skyRow` (under the board on Now, `#arBtn2`) whenever the Where to look card with `#arBtn` isn't shown
  (`skyRowRender`, from `drawLook`, `renderAircraftInfo` and every second); `arOk` is `arPossible()`.
- 1.72.3: the Sky view card's two layers (`.arPeekL` over `.arFullL`, both rendered) and `arSet(p)`: height between
  them, the layers' fades, `.arGhost` (the photo) flying from the thumbnail to `.cPicW`; the drag sets p (up from the
  small card, down from the whole one; below the small card it translates out), `arTo` eases to 0 or 1 on release
  (past 30 % or a flick), `.anim` while it does. "Swipe up for more" replaces More; a tap on the small card opens it too.
- 1.72.2: Sky view's card. A lock-on opens a peek (`arPeekHtml`: thumbnail, flight · type, height · distance ·
  status, More, `#arTimer`); `arPeekWatch` (every frame from `arAimDraw`) dismisses it when the ring holds another
  plane, or none for `AR_PEEK_MS` (3 s, the line runs down). Tapping the peek sets `arFull` (`planeBody`); a plane
  tapped opens full at once. `#arCard` is a sheet: `arSheetIn` slides it up, touch/mouse drag moves it (`.drag`), a
  release past a quarter of its height (140 px at most) or a flick (> .5 px/ms) calls `arCardDismiss` (`.out`; a new
  lock-on meanwhile keeps its card), else it springs back; a tap on the sky (`arTap`) dismisses too. No ×.
- 1.72.1 / relay 60: `GAME_KM` 10. Sky view labels get a chip from `arLoop` (★ / ★ POINTS on top within `gKm()`, ✓ +N
  locked on, NO PTS dimmed beyond; live location only); `#arCard` closes on a swipe down, a bigger round × and a handle.
- 1.72 / relay 59, the game redesigned (plan: claude.ai artifact WfByuzJYgym9THBEH9r3By): `game_book(book)` makes the
  logbook's `game3` part, a small logbook of its own (its keys are the logbook's, so `trophy_check`, `note_records`,
  `_streak`, `game_json` work on it; its `rareDays` are days with a live plane). `_record` tracks `liveMin`/`liveSeen`
  for place "live" (also on a pass first logged from another place) and calls `game_note`: the first time within
  `GAME_KM` (8) it scores (`gn` plane of the day, `gk` streak multiplier, `gNewType/gNewAirline/gNewReg`, `gp`), later
  only the close bonus changes `gp`. `game_points`: `TIER_BASE` × close (≤1.5 km 1.2, ≤4 km 1.1) + new, × streak, ×
  taper (26–50 ½, 51+ ¼). `game_lockon` (POST /game/lockon): +25/30/40/50 % (combo within 180 s), min 15, once per
  plane, seen live in the last 120 s. `level_of`: 500 × 1.25ⁿ, 20 titles (`LEVEL_TITLES`, the board's `GAME_LEVELS`).
  `league_json` (GET /game/league, cached 30 s): week (Mon 03:00) and all time, first names, `was` (rank before today),
  crown for last week's winner (`championMe` → `game.champion`), settings `league: false` leaves it. GET /game/me for
  the strip. Bingo counts live planes only (`_bingo_week(live=True)`), its cards and trophies in game3; reviews and
  the evening summary count `gp + lock`.
  App: `#gStrip` in the header (`gStripSetup`, `gStripRender`, `gGain`: chip flips to +N, `.gTok` flies to the bar,
  `#gBarG` fills, `gTotSet` rolls the flaps; `gRefresh` every 15 s live, 60 s not), `#gPts` under the board
  (`gPoints`), the Game page `#t-game` (`showTab("game")`, `renderGame`, `collectionHtml`/`recordsHtml` moved out of
  `renderLogbook`; the Logbook loses Collection and Records), level-up `#gLvUp`, Sky view `gLockOn` (from
  `arAimDraw`) → `#arPass` (`.pF` in the rarity colour, the stub tears off), `gJingle`, `gRip`, `gCoins`. Board: the
  `league` page (`LEAGUE_ROWS`, `renderLeague`, `leagueLoad`, in `ROTATION_OVERHEAD`). Styles: rules `{lvl}`/`{champ}`;
  themes `goldleaf` (`gilt`: gold rim) and `firstclass` (`leather`: `leatherGrain`, `leatherSeam`; the app's
  `html.leather` seams). `isSpecialPlane` for Today's Special; Favourites a filter of its own. `fromRelay` keeps the
  game fields.
- 1.71.3: light/ and glass/ parked: forwarders to /app/ (clear `od.ui`), the app's `od.ui` redirect and the Device tiles
  for them gone, out of check.yml, smoke.py, lint.py, tokens.py, cockpit_list.py. Source kept in tools/light, tools/glass.
- 1.71.2: the update offer shows on every resume (no 3 h wait, no skip memory); buttons Update / Skip.
- 1.71.1: the Android app updates itself (`Updater.kt`): `check()` on resume, at most every 3 h, asks GitHub's
  `releases/latest` (tag `android-build-N` = versionCode); newer → dialog Update / Later (Later skips that build 24 h).
  Update: `canRequestPackageInstalls` (else the phone's settings, `resume()` carries on), downloads overhead.apk (only
  from the repository's release downloads) into a `PackageInstaller` session, commit's answer comes back through
  `onNewIntent` (`ACTION_INSTALLED`; pending user action starts Android's prompt). `UPDATE_PACKAGES_WITHOUT_USER_ACTION`
  lets later updates skip the prompt where Android allows it. Bridge `checkUpdate()`; Device link `updBtn`.
- 1.71 Glass (designed with Gemini 3.1 Pro: rounds 1–3 in its chat, "Glasshouse"): `tools/glass/build.py` builds the
  light version with glass.js's regions over light.js's (main.js gained an empty `//@L:extra` region before
  `start()`) and glass.css after light.css. glass.js: `G` state; the map's colours by mutating `RADAR_MAP_LOOK` and
  `RADAR_COL`; `glassVars()` keeps Inter and light colours on the root and `html.daylight` on (a MutationObserver
  undoes applyTheme); `glassPaint()` draws the full-screen map (radarMapDraw with a radius reaching every corner,
  rings, radius, runways, planes with a white edge, `glassNames()` labels, your place); `glassCard()` the floating card
  (feat, or `G.sel` from a tap), `G.pill` shrinks it while pinching; the map's pointer handling (tap select, swipe to
  Today/Logbook, pinch with `radar.live`, double tap). Every tab but Now is a fixed page with a `.gBack`; Now's own
  content is hidden. `radarMapOn` follows whether the map shows, so the radar page's hidden scope doesn't refetch tiles.
  Inter added to fonts/ (tools/fonts.py). Device tiles: "Glass (preview)" in the app and the light version.
- 1.70.2: the Android WebChromeClient passes Sky view's camera request on (CAMERA asked the first time, REQ_CAMERA, the relay's own page only). `radarMapDraw` draws only with Map on (zoomed in it used to draw anyway). Notification channel `alerts_pa` (the old `alerts` is deleted) rings `res/raw/pa_bell.wav` (a copy of
  app/airport-bell.wav); the small icon is `drawable-nodpi/ic_notify.png` (a copy of app/badge-96.png).
- 1.70 / relay 57: Android notifications through Firebase Cloud Messaging. Relay: `fcm_ready()` (data/fcm.json, the
  service account key, copied onto the relay by hand; relay 57's `/fcm` upload page was removed in 58), `_fcm_token()` (RS256
  JWT → OAuth token, kept ~55 min), `fcm_send()` (v1 API, data message; unregistered → 410 so the sub is dropped);
  `/push/subscribe` takes `{subscription: {fcm: token}}` (endpoint `fcm:<token>`); pages get `OVERHEAD_FCM`;
  `/push/test` sends a test to the profile's devices. App: `PushService.kt` (shows the data message like sw.js; an
  `update` with `setOnlyAlertOnce`), bridge `pushEnable()` (POST_NOTIFICATIONS on Android 13+, then the token to
  `window.fallblattPush`) and `pushToken()`; a tap opens `OPEN_URL`. Build: the google-services plugin applies only
  when `android/app/google-services.json` exists, written by CI from the secret `GOOGLE_SERVICES_JSON`. main.js:
  `NATIVE_PUSH()`, `od.push.native`, the token re-sent 6 s after each start.
- 1.69: the app's radar controls are a `.plate.rvPlate` (head.html) with Settings' own `.wheel` (`#rvWheel`, ▲ `#rvZoomOut`
  wider, ▼ `#rvZoomIn` closer, `#rvZoomKm` the range; arrow keys too) and `.toggle` (`#rvMap`); `buildRadarLegend` sets
  them. Pinch (1.68.1): `radar.live` is the range under the fingers (`radarRange()` uses it, `RADAR_MIN` 1.5 km to
  `radarBase()`), the map's last image is stretched meanwhile (`radarMapDraw` keeps `radarMap.last`), and on release
  `radarZoomSet` keeps the range (any value; `radarZoomStep` goes to the next of 10 / 5 / 2.5, `radarZoomCan`).
  Styles cell: caps at 84 %, `.stN` ellipsis and `lcdMarquee()` (every 4.5 s, slides an overflowing word left, back
  to the dots after 1.4 s). Safe areas in head.html/light.css go through `--sa-top`/`--sa-bottom`; `html.android`
  (set by main.js in the Android app, whose MainActivity already pads the page clear of the bars) zeroes them.
  Tips: the layer stops touchmove/wheel, `place()` runs every frame, the ring is clipped by `tipBand()` (the app's
  fixed header and tab bar).
- 1.68 (structure): `paintRadar(g, cx, cy, R, z, t, o)` (E25, before `drawRadar`) is the one radar drawing; the
  board's `drawRadar` calls it at z 1.5 with `{engrave: true}` (range and map credit in the rim), the app's at 1;
  `radar.hits` carry both `o` and `hex`. `settingsChanged(changed)`, `locSet()` and `cockpitKeys()` (E12, function
  declarations so they hoist) are the save rules for both `saveSettings`. Type scale: `--fs-tag … --fs-hero` and fixed
  colours (`--c-gold`, `--c-paper`, …) in head.html's `:root`; `tools/test/tokens.py` fails on a font size off the
  scale in head.html or light.css. `tools/test/lint.py` (ESLint 9 in `.cache/lint`) fails on undefined or redeclared
  names in the three pages' scripts; names that exist on one page only and are reached behind a guard are `OPTIONAL`.
  Both run in `smoke.py --syntax`. Removed unused `POLL_MS`, `VIEWR`, `SET_NAMES`, `apName`.
- 1.67 / relay 56: the widgets. `/now` (`now_json`) gives the nearest airborne plane within the profile's radius
  (hidden ones left out), status OVERHEAD (within overKm) / APPROACHING / LEAVING by its track, route from
  `_route_for` when `_route_fits`, distance, direction, height in metres and today's count. Android: `NowWidget.kt`
  (`NowWidgetCard` 4×2 with `flaps()` and `pill()` bitmaps, `NowWidgetLine` 4×1), layouts `widget_card`/`widget_line`,
  `xml/widget_*_info`; the WebView's cookie for the relay (prefs `public`, else `relay`); a non-waking 60 s alarm
  (`ACTION_TICK`) refreshes only while the screen is on; tapping opens MainActivity.
- 1.67 / relay 56: the live countdown. `window_check` remembers each alert in `_countdown` (subscription pref
  `countdown`, default on) and, while `window_planes` still lists the plane, `countdown_send` replaces it every 25 s
  under the same tag: title "{what} · overhead/passing in m:ss" (`cd_over`/`cd_pass`), body why · direction · height
  and a ten-step bar; `update: true` makes sw.js show it silently (no renotify, no bell in the open app). Under 50 s
  the title turns "Look up now: …" (`cd_now`) and rings once. Planes that left `window_planes` drop out.
- 1.66: Sky view aiming: `arAimDraw()` (end of `arLoop`) draws the ring (`AR_AIM_R` 56 px) and fills it while the
  nearest `arHits` marker stays inside; after `AR_AIM_MS` (1.5 s) it sets `arSel` and opens the card; `arAim.done`
  keeps it from reopening until the ring empties. `arCalCheck()` (from `arOrient`) keeps 1.5 s of raw readings: heading
  spread over 12° while beta/gamma move under 3°, or `webkitCompassAccuracy` over 25, shows `#arCal` for 4 s.
- 1.66 Daylight: `S.daylight` (COCKPIT Display switch, `for: "phone"`; device-own: left out of `/me` and of the
  profile's settings in `loadSettings`). `daylightOn()` (app and light only: `typeof LIGHT`) makes `themeNow()` lay
  `DAYLIGHT` over the board style (cream metal, black flaps, white ink, bright amber for flap text, `pageAccent` dark
  orange for labels via `COL.labelInk` and the page's `--amber`); the app's `applyTheme` sets `--ink` dark and
  `html.daylight`, which head.html and light.css restyle (cards, lists, fields, toasts).
- 1.65 / relay 55: `toast(text, {err, action, run, ms})` (cards block, shared) puts a notice in `#toasts` (above the
  tab bar in the app via `--toast-b`, over the rail on the board, at the top while a card is open); card toggles toast
  with Undo, failures with Retry; `meFlush` toasts on the second failure and when it gets through after. Radar zoom in
  both styles: `radarZoomed()` no longer needs the Airport style (Overhead zooms around your place; `radar.zc` only in
  the Airport style); the app's `pinch` (pointer events on `#scope`, `touch-action: pan-y`, the canvases scaled live,
  then `radarZoomTo(±1/2)`) and a double tap on empty radar. `gateFor(info)` (Vienna's departures, `timesFor`) adds a
  Gate fact to `planeBody` and the gate to the app's radar list chip for planes on the ground. `/search?q=` (relay 55,
  `search_json`) scans every `sightings-*.json` of the profile, grouped by flight (when the words name one) or by
  aircraft; the app's Logbook tab has `#lbFindBox` (`lbFindSetup`, `lbFind`), `#t-logbook.finding` hides the rest.
- 1.64 (sync you can trust): `meSend(settings, now)` / `meFlush(leaving)` in the network block (E12, so board, app and
  light share it) keep a profile's settings in `od.mePending.<id>` until `/me` answers (4xx other than 408/429 drop
  them), retry with doubling pauses (2 s … 60 s), flush on `online`, with `keepalive` when the page is hidden, and 3 s
  after load for what was left over. `meUnsynced()` and `syncShow()` fill `[data-syncnote]` (the app's Settings, the
  board's cockpit). `saveSettings` also sends every key that changed since `meBase` (the settings as last saved).
  Lists: `listOps(ops)` shows the change at once (`listsWaiting` over `listsServer`), queues the POSTs (`listsQ`),
  sends `{ops}` to relay 54+ (whole lists to older ones) and falls back to the relay's lists on failure;
  `cardToggle` marks the button `.busy`, the favourites manager re-renders at once; failures say `SAVE_FAILED`.
  `tools/test/flows.py` `browser_checks()` (run by smoke.py) checks both in the app through a hooked page (`__e`).
  Offline start: `app/sw.js` answers navigations to `/app/` from the relay when it answers within 3 s (status < 500),
  else from cache `fallblatt-shell` (kept with `X-Kept`), with `window.OVERHEAD_OFFLINE = <kept ms>` put into the head;
  a 401/403 forgets the copy. main.js registers the worker on load (https/localhost, not the light version, whose
  pages are outside the worker's /app/ scope); `statusLine()` says "Offline · the app as of …".
  Accessibility: `panelSpeech()` (main.js, every 4 s) sets each flap panel's aria-label to its name plus its fields'
  targets with their labels (logo, tier, trend and lamp fields and "/" left out); the app's smallest text is 12 px (tab
  labels 11 px under 380 px wide); the card's × (`.rcX`) is 44 px. `radarZoom` and `radar.zc` kept in `od.radarZoom`
  (`radarZoomKeep`). Fonts: `fonts/` (tools/fonts.py) replaces Google Fonts; relay 54's `BOARD_FILE` serves css
  (no-cache) and woff2 (a year, immutable: names carry a content hash). Removed unused `drawBadge`, `blankRow`, `styleRuleShort` and the relay's `_backfill_categories`.
- 1.63.2 / relay 54 (the code review's security and speed fixes): `owner_ok()` lets a device without a profile in only
  while no `HOME_OWNER` profile exists or from the relay's own computer (`on_this_computer()`: loopback, no
  Cf-Connecting-IP/X-Forwarded-For); before, any device at home without a cookie had the admin pages. `reply()` packs
  (`_gzip`, lru-cached) and tags (`ETag`, sha256) bodies over 1 KB of `PACKED_TYPES`; pages are `private, no-cache`
  and answer `If-None-Match` with 304. `/me` POSTs need the same origin when the browser names one. `/lists` takes
  `{op: "add"|"remove", list, item}` (one change; whole lists still work). `/handover` (POST, signed in, over http,
  `public_url` https only) makes a one-time `/join/` link for the profile; the app's `androidHandover()` hands it to
  `OverheadAndroid.usePublic`, which keeps the https base in prefs `public`, submits the join form and falls back to
  the Wi-Fi address (`relay`) when the https one can't be reached. CI: actions pinned to commits, the APK release in
  its own job (the only one with write access), the keystore removed at the end. `tools/test/flows.py` checks it all.
- 1.63.1: `saveSettings` (board and app) always stores and sends theme, palette, finish and badge, defaults included:
  one switched back to its default was left out, and the relay's `/me` merge kept the profile's old value, which came
  back on the next load (the same as 1.54's cockpit keys).
- 1.63: Sky view taps (`arTap`, `arHits` from `arLoop`, `arCardRender` with `planeBody` into `#arCard`; a move under
  8 px is a tap, not a drag; `#sheet` above `#arView` while it is open). The board's radar buttons are placed in
  `radarBox()` corners (`#viewTools.rdr`), the range engraved on the bezel in `drawRadar`.
- 1.62.1 (shipped in 1.63): `radarStatus(o)` is the one status for the radar's list (`radarRows`), the plane card (`planeBody`) and
  `radarColor`: in the Airport style the airport status (TAKE-OFF ... from `AP.deps`/`AP.arrs`, TAXIING/PARKED on the
  ground, else OVERFLIGHT), never OVERHEAD; colours `RADAR_COL.dep`/`arr`/`by`/`ground`; `radarLegend()` for both legends.
- 1.62 (radar zoom, logos, landed planes linger): `radarZoom` (km to the rim, 0 the usual range) steps through
  `RADAR_ZOOMS` with `radarZoomStep()`; `radarZoomed()` only in the Airport style once `AP.lat` is known. `radarZoomSet()`
  fixes the centre `radar.zc` on the planes on the ground within 3 km (else the airport), so the map isn't rebuilt as
  planes come and go. Zoomed, `radarMapDraw` draws even with Map off, tiles go to zoom 15, and `RADAR_MAP_LOOK` entries with
  a fifth value (km) only draw at that range or closer (aprons, buildings, taxiways). Rings step by `radarRing(range)`.
  Ground planes: `RADAR_COL.ground`, statuses TAXIING/PARKED (new REMARKS words) in `radarRows`, labels show the type
  instead of the altitude. The radar list has a logo flap `rv<i>logo`; the app's list a `.rvLogo` from `logo(code, true)`.
  Board: − / km / + caps in `viewTools`; app: `#rvZoom` beside Map. `apFocus()` keeps the newest LANDED arrival on top
  until the next arrival is within `AP_LINGER_KM` (6) or a take-off rolls. Test data: `APRON` in `fakesrc.py` (parked
  planes at VIE's gates); `shoot.py` takes `NOTIPS=1`.
- 1.61 additions (to-do #76 and Dave's feedback): the board's `cockpitDone(saved)` keeps Settings open after Save
  (`cockpitOpen()` again, "Saved" on the Save cap for 1.6 s); Cancel still goes back to the board. Favourites and Styles
  caps are 30 px tall and 86% wide (Styles 100% with smaller text, as the Display cell is narrow).
- 1.61 / relay 53 (Styles redesign): the Styles cell is two `favCap` caps (`data-styles="theme"|"badge"`, `palette` in
  the light version via `lookKind()`; `.stN` display from `styleShort()`/`STYLE_SHORT`) and a count (`.stCnt`;
  `stylesCellRefresh()`, also called by `achCheck`). `stylesCard(focusKind)`: `STYLE_ROWS` (theme, palette, finish,
  badge) as `.stLine` rows (tabindex 0; arrows are tabindex -1 so a remote moves row to row; Left/Right/Enter step,
  Up/Down move, Up from the top focuses the ×); locked choices are stepped onto and shown dimmed with a lock and
  `styleRuleText` under the row, but never applied; `stylesPreview(cv)` draws the logo, title word and three `tile()`
  flaps. `classicLook()`: `themeNow()` lays a palette and `FINISH()` returns a finish only with the Classic board (or
  LIGHT). LED dots: `LED_FONT` (5x7, hex per row), `ledText()` lays the hinge between rows 3 and 4, `LED_FLAP` dark
  faces, glow when the pitch is ≥ 4 px, square dots below 3.2 px; text with other letters is sampled into the same grid.
  Badge: `badgeGlyph(g, id, k)` (the silhouette; jumbo nose up), `pictogram(g, x, y, s, badge)` draws it instead of the
  plane (board title, app/light `drawMark`; the title roundel and the app's `#badge` canvas went), `badgeIcons()` sets
  the favicon (canvas PNG via `iconDraw`) and the apple-touch-icon (`apple-touch-icon-<id>.png`).
  `tools/app/make_icons.py` (Playwright) renders `app/icon-192|512|maskable-512-<id>.png` and `apple-touch-icon-<id>.png`
  with the board's own `badgeGlyph`/`iconDraw`. Relay 53: `BADGES`, `badge_manifest()`: `/app/manifest.webmanifest`
  for a profile whose settings have a badge names those icons (no-cache, Vary: Cookie); the app's manifest link has
  `crossorigin="use-credentials"` so the cookie goes along; the manifest got `"id": "./"` so the installed app keeps
  its identity. The Android APK's launcher icon can't change without a new APK (activity-alias), so it stays.
- 1.60 / relay 52: the Styles cell is a progress ring (`.stRing`, built in `itemHtml` for `type: "styles"`). Styles granted by hand: profile field `styleGrants` ("all" or ids, `STYLE_GRANTS`, `style_grants()`), set from the admin card's Styles line (`POST /admin/styles`: `pid`, `mode` = `all` | `earned` | `pick`, `grant` = ids, repeated or comma-separated), sent in `/logbook` as `game.styleGrants`; `styleOk(rule, g0, id)` counts them, `achList` calls it without an id so grants raise no pop-up.
- 1.59 / relay 51 (to-do #66, stacked on 1.55): `STYLES` ([kind, name, [[id, name, rule]]], rules `{pts}`/`{tr}`/
  `{cards}`), `styleOk(rule, g0)` with `styleGame()` (lbData's game), `PALETTES` laid over the theme by `themeNow()`
  (both applyThemes), `THEMES.frankfurt70`/`tokyo`, `FINISH()` in `tile()` (key includes it; `WHITE_FLAP`, enamel
  `mix`, brass frame, `ledText` samples the text at 6x into an 11-row dot grid), `drawBadge(g, id, x, y, s)` after
  the title's second word and on the app's `#badge` canvas (drawMark). Settings: the Display plate's `theme` knob became
  `{type: "styles"}` (itemHtml + `[data-styles]` → `stylesCard()`, which also sets `draft[k]`); `styleKinds()` drops
  theme/finish when `LIGHT`. `achList` adds "style:<id>" when a rule is met. Relay 51: `_bingo_week`, `book.bingoCards`
  {monday: ts} (bingo_json; `_backfill_cards`, `cardsV`), game_json `bingoCards`.
- 1.55 / relay 50 (build G):
  - #54 `lbChips()`: chips are `places.list` labels and "live" only; the unnamed "home" key (sightings before any
    saved place) joins a label called Home/home/T("Home") (`id` "Home\nhome"), else only All counts it.
  - #55 `TROPHY_LADDERS` ([key, description template, [[id, at, name]...]]) + `TROPHY_SINGLES` make `TROPHY_IDS`;
    `trophyLadder(g0, L)` (done, next, have from `g0.trophyCounts[key]`, or `g0.trophyToday` for "today"). Relay:
    `TROPHY_LADDER` {id: (count, n)}, `trophy_counts()` (game_json's `trophyCounts`), `TROPHIES_V = 2` reruns
    `_backfill_trophies` keeping won ones and building `book["countries"]` (ownerCountry, also counted in `_enricher`,
    which re-runs `trophy_check`). streak7/streak30 are now also won live (before only in the backfill).
  - #65 board `buildViewTools`: `#viewTools.two` (column) with `.vtRow`s: `LB_VIEWS` (aria-current) and the view's
    options. App `lbView` + `lbViewsBar()` (`#lbViews`, `.seg`), `renderLogbook` builds one view; `trophiesHtml(g0)`.
  - #67 `logo(code, any)`: a failed logo retries after 10 min; cards load logos even with flap logos off and add a
    slow one when it arrives. AIRLINES gained CAI/CXI/CND (Corendon), FHY, TOM, TFL, EXS, BOX, HFY, NOS, MAC, SBI.
  - #68 `radarMapDraw/radarMapBuild/mvtRead/mvtPath`, `RADAR_MAP_LOOK` (shared via the app's E25 block): OpenFreeMap
    vector tiles (TileJSON `tiles.openfreemap.org/planet`, then `.pbf`), decoded and drawn into one offscreen canvas per
    centre/range/size; `od.radarMap` per device. CARTO raster tiles need a key now ("API KEY REQUIRED" images) and
    Esri's dark grey base has region names baked in, so neither was used.
  - #69 statuses APPROACHING / LEAVING (keys renamed, REMARKS drum order unchanged), `RADAR_COL.away` #c8645c,
    LEAVING flap soft red. #72 app `renderToday` keeps the old list dimmed (`#svList.wait`) until All places arrives.
    #70 `plusBtn(g, x, y, w, h, on)` draws three grey dots, amber while `plusOn` (the entry whose sheet `plusOpen`
    opened; `cardClose` clears it); Recent flights rows: pitch 40, flap ratio 1.3 (was 39, 1.45).
    #73 `spotMatch` also matches `remarkFor`, special, watch, NEW TYPE/AIRLINE, FAVOURITE and their `T()` words.

- Fixed 1920x1080 layout in board units, scaled to the screen. Two canvases: `bg` (static: metal, wear, slots,
  engraved labels; `drawStatic()`) and `fx` (the flaps).
- Flap engine: `def()` fields with cells; `tile()` pre-renders each flap face (cached, byte-budgeted);
  `setChars(id, text, delay)` / `setWord(id, word, delay)` queue the drum path (`retarget`; with Quick flaps, `S.quick`, each flip gets `c.qdur` so the run ends within `QUICK_MS`, and `frame()` chains and skips flips), `frame()` animates and
  `paintCell()` draws a flap mid-flip. Sounds (1.17): recordings in `SOUND_DATA` (embedded until 1.53.1, now `test/sounds.js`; made by
  `tools/sounds/build_sounds.py`), decoded by `loadSounds()`, played by `sample()` from `clack()` and `ctlSound`; with
  `S.soundSet === "classic"` or before decoding, the old synthesised sounds play. The flaps always clack synthesised
  (1.19.1, Dave's choice; the flap recording was dropped). The board's rail buttons carry the app's tab icons (`RAIL_ICONS`). Drums: `DRUM_ALPHA`, `DRUM_DIGIT`, `DRUM_ALT`, `DRUM_POS`, `REMARKS`.
- Top half: the plane overhead (`process()` picks it: alerts first, then overhead, inbound, flying by; airtime limit
  for hovering planes) rendered by `renderFeatured()` and `renderTimes()`.
- Lower half: rotating pages (Recent flights, This aircraft, Today in numbers; `ROTATION`), turned by one giant
  falling flap (`startBigFlap`). Views (Spotted today, Logbook, Radar, Settings) take over below the header at once
  (`switchView`). The rail of lamp buttons is DOM (`.cap`), as is the Settings cockpit (`COCKPIT`, `cockpitOpen`).
- Look (1.18): the footer and the app's status line stay quiet while live (`updateFooter`, `body[data-health]` in
  the app), the radar's labels go through `radarLabels()` (no overlaps, inside the scope), the app's Save bar only
  shows when `#t-settings.dirty`, the app's tabs carry line icons (`TAB_ICONS`), and altitudes below zero show as 0.
- Realistic look (1.19, `S.real`, `REAL()`): extra layers in `tile()` (two-card print, grain, lighting) and
  `paintCell()` (light and edge on a turning flap), `#glass` over the stage and `body.real` CSS for the cockpit. Settings
  show a description per control (`HINTS`, hover; press and hold on touch).
- Drawing quality: Fire TV and LG TVs (`WEAK_TV`) draw at 1080p, 30 fps, shorter flap runs (`LITE()`).
- Data: positions from the relay (`/aircraft/...`), routes and aircraft from adsbdb (browser) and adsb.lol's
  routeset (through the relay), Spotted today and the logbook from the relay (`/sightings`, `/logbook`), times from
  Vienna Airport via the relay (`/times`), Flightradar24 via the relay (`/flightinfo`). Features check
  `window.OVERHEAD_RELAY_VERSION` before using newer relay endpoints.
- 1.50 (to-do #36-#40): Spotted today's filter (`svQuery`, `spotMatch`, `svFindHtml`/`svFindWire`; the board shows it
  only where `HAS_KEYS`, a computer, not the TVs; the app and light always); the bingo's next card (`bingoReset`, from
  the relay's `bingo.resets` since relay 44, else the Monday after `week` at 03:00); airline cards look further on
  Wikipedia (`airlineWiki`: shorter names via `AIRLINE_TAIL`, then Wikipedia's search) and show adsbdb's country and
  radio callsign (`airlineInfo`), and wait for the logo (`logoReady`); tips follow each other within ~60 ms (fade .18 s).

## The phone app

`app/index.html` is generated: `py tools/app/build.py` copies the flap engine, reference tables, network, tracking,
times, specials, logbook, radar and Settings control code out of `test/index.html` by marker strings and wraps them in the phone layout
from `tools/app/head.html` and `tools/app/main.js`. Never hand-edit `app/index.html`. Change `main.js`/`head.html`
(or the board) and rebuild. If the build stops on a marker, the board's code moved: update the marker in `build.py`.
The app keeps its settings under its own key (`od.app.settings`) and needs the relay (relay 13+ serves its icons).

The light version (1.39, `/light/`, Dave's wish: the phone app without split flaps, same content, colours and fonts,
plain and modern; phone only for now): `py tools/light/build.py` builds `light/index.html` from the app's own
head.html/main.js and the board's code (`extract`/`assemble` in `tools/app/build.py`), replacing the regions main.js
marks `//@L:name` ... `//@L:end` with `tools/light/light.js` (the app build keeps them): `flag` (`LIGHT`), `engine1`/
`engine2` (makePanel/def/placeRow/setChars/setWord as DOM fields: label above value, `lfPaint` slides a new value in;
words: `chip()`, trend arrows, tier pill, airline logo; E4/E5 left out), `static`, `metal`, `radar` (flat scope),
`cockpit` (since 1.53.2 only `COCKPIT_FOR = "light"`: the board's COCKPIT without `flaps: true`, with its `light: {…}`), `taps` (cards by `data-f`), `greet`
(welcome text slides in). `tools/light/light.css` comes after the app's styles. Settings under `od.light.settings`
(`.g.<id>` per guest); `LIGHT_FIXED` (real, imperfect, quick, theme, soundSet) and `sound` stay out of `/me`. It uses
the app's manifest, icons and service worker (`SW_DIR` = `../app/`; `sw.js` matches `/light/` too). Settings → Device
switches (`#uiBtn`, `localStorage` `od.ui`); `/app/`'s head script then opens `/light/`. A new region in main.js needs
one in light.js, or the light build stops.

Airport style (`S.mode === "airport"`, switched by tapping Overhead/Airport in the title; the "airport mode" block,
copied by the app): `pageOrder()` = aplists (take-offs and landings side by side), apland, apdep, under the plane on
top, which `apFeature` picks (`apFocus`); apland/apdep reuse the This aircraft page (`isAc(page)`). The airport
statuses (`AP_ICON`) carry a plane pictogram in front of the word, in the flap tile and the app's chips (Dave's choice
over a header sign, which was tried in 1.12.1). Since 1.49 (to-do #33, Dave approved the look) they are Tabler Icons'
plane-departure/plane-arrival (MIT), filled, over a solid runway (`AP_PATH`, `apSvg`/`apSvgInner` for the app's chips and
the rail's up/down icons, `drawApIcon` in `tile()` via Path2D); `landed` is the departure plane turned level (`AP_LEVEL`).
Dave chose this pages layout on 12 Oct 2026; the screens layout (full-screen lists) was removed.
The game (1.21, relay 24): the relay scores each sighting when it is recorded (`tier_of`, `score`: `e.tier`,
`book.points/days/tiers/rareDays`; `game_json` in `/logbook` with the `SETS`); the board's `tierOf()` gives the plane on
top its tier (the relay's for planes on today's list, else `fleetTier`) on the `tier` flap
(`TIER_COL`, `drawTierIcon`; the app's Collection list shows them via `tierIcon`), and the `collection` view (from Logbook's view tools) shows `game`.
Since 1.25 (relay 26) the tier goes by fleet size: `FLEET` (types in service worldwide) is the same table in the relay and
the board, keep them equal. The keys stay `common/uncommon/rare/epic/legendary` (stored in sightings); shown as Common,
Uncommon, Rare, Very rare, Special. A logbook scored under an older rule (`gameV` < `GAME_V`) is scored again from its
saved days when loaded (`_rescore`).
Spotter facts (1.27, relay 28): `seenText()` (relay `/seen?reg=`, from the logbook's `regs`: count, first, last and `prev`,
the sighting before the last) and `toGoText()` fill the top half's `seen` and `toGo` flaps (row 3; in `TOP_IDS`) and
the app's This aircraft facts; `skyCheck()` reads `/sky?code=` (the home airport's METAR: the lowest BKN/OVC/VV layer
plus the airport's elevation, from the airport list's v3) every ten minutes and `remarkLines` shows ABOVE CLOUD (1.49,
to-do #32: no longer a status; only when `windowWorthy()`: special, watchlist, military or favourite);
`liveryLine()` (Flightradar24) puts Flightradar24's `painted_as` on the Operator line; the relay keeps lifetime
`records` in the logbook (`note_records`, backfilled once by `_backfill_records`, `recordsV`) for the `records` view
("Records & trophies", from the Logbook and Collection buttons) and the app's Logbook; the admin page shows
Flightradar24's credits this month and what it added (`fr24_admin_html`, `usage.found/wetLease/diverted`).
More of the game (1.28, relay 29): the watchlist (`watch_of`, plane-alert-db downloaded daily to `data/plane-alert.json`,
categories mapped to remark words by `WATCH_WORDS`; `/watch?hex=` (503 while loading) for the board's `watchAsk`/`watchOf`,
`e.watch` on sightings; `badgeFor` shows it after the big specials); trophies (`TROPHY_IDS`, `trophy_check`/`trophy_pass`,
`book.trophies`, backfilled once by `_backfill_trophies`, `trophiesV`) and the weekly bingo (`BINGO` goals, `bingo_json`
in `/logbook`'s `game.bingo`), drawn by `recordsStatic` and the app's Logbook (`GOAL_TEXT`, `TROPHY_TEXT`, shared); the
day in review (`reviewTime()`, Today in numbers after 21:00); `/year?y=` (`year_json`) for the app's year card and
`/logbook.csv` (`logbook_csv`); the app's Where to look (`lookAt`, `drawLook`, `lookStart`: deviceorientation(absolute)
or `webkitCompassHeading`, https only). Sky view (1.30, app only): `arOpen` (camera via getUserMedia, motion permission,
`watchPosition`), `arOrient` (absolute alpha, or 360 - `webkitCompassHeading` on iPhones; smoothed), `arMatrix` (W3C
Z-X'-Y'' rotation), `arProject` (east-north-up to the screen, the camera along -z, `AR_VFOV` 64°, drag offsets `arOff` in
`od.ar.off`), `arLoop` draws the labels; the planes come from `arFeed(list)` in the board's `poll`. Test it headless with
`--use-fake-device-for-media-stream` and synthetic `deviceorientationabsolute` events (grant camera, accelerometer,
gyroscope, magnetometer). `run_test_relay.py --hover` puts a real watchlisted police helicopter (OE-BXB) overhead.
Runways (1.20, relay 23): `AP.rwys` from `AIRPORTS[code].runways` (Vienna) or the relay's `/airport` (OurAirports
runways.csv, cached per airport); `rwyTrack()` matches each take-off and landing to the runway it is lined up with,
`rwyInUse()`/`rwyLine()` give the ones used in the last 15 minutes (shown next to the lists' title and lit on the radar),
and the Take-off and Landing pages paint `paintRunwayScreen()` on the photo screen (1.26: the photo full size far out, with
`EXPECTED IN {n} MIN` for landings from `e.t`; close in, `rwyClose(e)`, it slides into the corner away from the plane and the
radar zooms to the runways; `rwyMix` eases it and returns `moving`, so `placePhoto`/the app's `paintRwy` paint again next frame;
`run_test_relay.py --far` starts the landing 32 km out).

Settings cockpit (shared by the boards and the app): `COCKPIT` plates are CSS grids of `cols` cells, items take `span`
cells or `wide`. Since 1.53.2 (to-do #47, steps 1-2) there is one `COCKPIT`, in the test board, for every screen:
plates have an `id`; `for: "tv"|"phone"` keeps a plate or control to one side, `flaps: true` leaves it out of the light
version, `phone: {…}`/`light: {…}` override (span, label, title, `places`/`search`; `plate` + `before` moves a control:
New plane ding sits in Traffic on the board, in Flaps & sound on the phone), `dflt` is the value shown for a setting
never set (quality: auto). `cockpitFor(target)` resolves it ("tv", "phone", "light"; phone plates have 2 columns) into
`PLATES`/`ITEMS` from the page's `COCKPIT_FOR` (the board's line before the shared block; main.js's and light.js's
`//@L:cockpit` region). Shared too (E29, from "/* Settings, once for every screen" to `plateHtml`): `cockpitDraft()`,
`wireCockpit(box)` (the controls; the mouse wheel turns knobs only on the board, where Settings never scroll; arrow keys
everywhere), `cockpitShow`, `cockpitUnsaved`, `cockpitDirty`, `cockpitSave`, `cockpitCancel`. Each page has its own
`plateHtml`, `cockpitOpen` and two hooks: `cockpitDone(saved)` (board: back to the board; app: Settings again, "Saved"
on the bar) and `cockpitMark(dirty)` (board: the Save plate button; app: `#saveBtn` and `#t-settings.dirty`).
`tools/test/cockpit_list.py` lists every control per target (and a hash of the markup): compare before and after a
Settings change. `itemHtml()` puts each control in a `.inst` cell with its name above it. Control sounds are
`ctlSound.rotary(steps)/toggle(on)/wheel()/press()` (they play when `S.sound || S.chimes`). "Use current location"
(`wireLocate`, `hereNow`, `nearestAirport`) uses `navigator.geolocation` (secure contexts only, so not on the TVs) or the
Android app's `OverheadAndroid.locate()`, and the relay's `/airports/near` (relay 16+) for the home airport.

On Android it is installed as the Overhead app (`android/`), because Chrome installs web apps only from https and the
relay is plain http (Tailscale was tried and dropped on 11 Oct 2026; don't suggest it again). The app is a full-screen
WebView of `<relay>/app/`, so web app changes need no new APK. It finds the relay by asking `/health` on every
address of the phone's /24 (port 8080, `Server: OverheadRelay`), or takes a typed address; Settings → About →
Change relay calls `window.OverheadAndroid.changeRelay()` (`ANDROID` in `main.js`). Its user agent ends in
`OverheadAndroid/<version>`. On its side the app page itself takes its landscape layout (CSS for
`(orientation: landscape) and (max-height: 600px)`): only Now, full screen, no tab buttons (`sideways()` switches to
Now and back; `showTab` refuses other tabs on its side), the status line only as a pop-up when something is wrong
(`#sideAlert`). Now is the board (1.13.2/1.13.3, Dave's choice): `heroLayout()` puts the flaps in three rows across the
width, and under them one page at a time, `nowPage` "lists" or "ac", picked by lamp buttons in the title strip
(`buildNowPages`; in the Airport style `lists`/`dep`/`land`, the board's pages, `appApPage()` telling `apFeature` which plane, `paintRwy()` the runway screen; upright a `#apPick` switch above the plane's section, so it stays without a plane, and the lists as flap panels `APDP`/`APAP` (1.36, `nu{d|a}{i}*` fields; tap a row for `planeCard`, its city for `placeCard`)), turning every 20 s, drawn on their own flap panels (`RECENTP`, `APP`, `ACP`, switched by
`nowPanels()`) in place of the text lists; `fitSideways()` sizes it all to fill the screen (`--fitW`, `--lowH`), with fewer list rows (`setNowRows`, 6 down to 4) on a screen short for its width. The
Android app goes immersive, draws under the camera cutout and tells the page how far it reaches (`--cut-l`, `--cut-r`),
and keeps the screen on while it is open (`FLAG_KEEP_SCREEN_ON`, since 1.13.3.1; before only on its side and charging). (1.9–1.12.2 showed the board instead; Dave preferred a layout of the app's own.) GitHub Actions builds it on every push touching `android/` (no Gradle wrapper; Gradle
8.10.2 from the workflow) and, on `main`, publishes a release `android-build-<run>` named "Android app <version> (build <run>)" with `overhead.apk`
(`releases/latest/download/overhead.apk`). The signing key is in the Actions secrets `ANDROID_KEYSTORE_B64` and
`ANDROID_KEYSTORE_PASSWORD`, with a backup in `%USERPROFILE%\overhead-android-key` on Dave's PC: never commit or print
it, and never replace it, or phones refuse the update. Bump nothing by hand: the APK is named after the newest patch-notes entry plus the build number.

## The relay

- Since 12 Oct 2026 it runs on Dave's homelab: a Debian LXC container on Proxmox (`overhead-relay`, always on), as the
  systemd service `overhead-relay` (`relay/overhead-relay.service`) in `/opt/overhead-relay`, which also holds
  `overhead.json` (settings and the API key) and `data/` (sightings per day, logbook, Flightradar24 cache). Port 8080.
  The container's address and how to reach it are in Claude's memory for this project, not here (the repository is
  public). Claude logs in as root with the key `~/.ssh/overhead_homelab` on Dave's PC. The old copy in
  `%USERPROFILE%\overhead-relay` on the PC stays stopped: two relays on one network confuse the Android app's search.
- The container is kept to a standard (13 Oct 2026): security updates install themselves (unattended-upgrades), SSH
  takes keys only (`/etc/ssh/sshd_config.d/10-overhead.conf`; `ssh.socket` is off, as with both on a reload leaves SSH
  dead), nftables lets in only 22 and 8080 from private addresses (`/etc/nftables.conf`), the journal is capped at
  100 MB, and the service runs in a tight systemd sandbox (`systemd-analyze security overhead-relay`: 1.3). Change SSH
  or the firewall only with a `systemd-run --on-active=180` rollback armed, cancelled once a fresh login works.
- From outside it is reached through a Cloudflare Tunnel (since 13 Oct 2026; the address is in Claude's memory, not
  here): `cloudflared` from Cloudflare's apt repository (also updated by unattended-upgrades), the tunnel's token in
  `/etc/cloudflared/token` (root only; Dave pasted it in the console, it never passes through chat), and a sandbox
  drop-in `cloudflared.service.d/10-sandbox.conf` (DynamicUser, the token handed over with LoadCredential). The tunnel
  sends the hostname to `http://localhost:8080`; Cloudflare Access is off, as the relay's invite links decide who gets
  in. The relay's `public_url` in `overhead.json` makes the admin page hand out full links.
- To update it: `py -m py_compile relay/serve.py`, copy `relay/serve.py`, `relay/overhead-relay.service` and
  `relay/install.sh` to the container (scp, to `/root/overhead-install/`) and run `sh /root/overhead-install/install.sh`
  there: it checks the file compiles, replaces it, keeps the settings and data, and restarts the service. (After the
  change is on `main`, `curl -fsSL .../relay/install.sh | sh` on the container does the same from GitHub.) Bump
  `RELAY_VERSION` with every relay change and gate board features that need the new version on
  `OVERHEAD_RELAY_VERSION`.
- Friends and family (relay 19, app 1.15; no Home since relay 42): every visitor is a profile's device (a cookie from a
  personal invite link: GET `/join/<code>` shows a page, its button POSTs to take it
  (relay 27: chat apps' link previews used links up; `PREVIEW_BOT`); from an account's sign-in; or from a QR pairing;
  profiles, invite and cookie hashes in `data/profiles.json`) or a stranger (only the "private" page with the QR
  sign-in, `/health`, the app's icons and manifest). `at_home()` now only opens `ADMIN_PATHS` (`/admin`, `/screens`,
  `/status`, and the `/admin/*` POSTs), for anyone on the home network, signed in or not. Each profile has a `Spot`
  (sightings and logbook in `data/profiles/<id>/`), and
  a screen's positions are recorded into its own spot (`Spot.take`) if they cover the spot's place. Profiles get
  `OVERHEAD_GUEST` (id, name, settings) and, until they are `located`, the relay's own location in `OVERHEAD_DEFAULTS`
  (the welcome starts from it, relay 42), their settings back via `/me`
  (merged, so the app and the board don't wipe each other's), the boards too (1.16; the welcome's "Phone app / Full
  board" choice; a board sends a guest without `located` to the app's welcome), per-guest storage keys
  (`od.app.settings.g.<id>`, `od.settings.g.<id>`), `/signout` (About), rate limits (`allow`; per profile `guest:` 8/s,
  `pos:` 2/s, as one profile may be a house of screens), and Flightradar24 only if turned on for them (relay 42:
  `fr24_limit(p)` credits a day, `FR24_DAY_GUEST` 500 / `FR24_DAY_ACCOUNT` 2,000 unless `p["fr24Limit"]`; counted per
  profile in `p["fr24Use"]` by `fr24_use()` from the worker, as `fr24_want(..., pid)` queues the profile with the
  lookup). `/admin` (home network only, same-origin POSTs, `admin_post`) makes invite links; `--public-url` gives them the public
  address. The app's welcome (`welcome()`, `located()`, `S.located`) asks a new guest for their place. The app opens with `#splash` (head.html; `splashGo()` once the board is ready).
- Accounts (relay 30, app 1.29): `p["account"]` = `user` (unique, lower case), `pw` (scrypt, `_pw_hash`/`_pw_ok`) and
  `passkeys` (WebAuthn: id, public key as SPKI, alg ES256/RS256, sign count; registered by `passkey_register`, checked
  by `passkey_signin`, a small CBOR reader `_cbor`, challenges in memory for 5 min). Guests use `/account` (GET) and
  `/account/user|password|passkey/begin|finish|remove` (same-origin JSON POSTs); anyone can open `/signin` and POST
  `/signin/begin|passkey|password` (rate-limited), which adds a device to that profile (`add_device`) and sets the
  cookie. The relying party is the Host (the public address; localhost while testing, `secure()`). The app's `accountBox()`
  serves About → Account and the welcome's `wAcct` step (after notifications; https only).
- Favourites and hidden (relay 31, app 1.31): `lists` per profile (`/lists` GET/POST, `_clean_list`, `lists_of`,
  `_list_hit`); the boards' `userLists`/`listsLoad()` (every 5 min), `favList()` adds the favourites, `isHidden`/`hiddenAc`
  keep hidden planes out of `process()`'s candidates, chimes, `dayList()`, Recent flights and the radar; the app's
  `listSheet()` (rows' ⋯, This aircraft), `renderFavBox()` (Settings), `listsMigrate()` (the old `S.favs` text). Window
  alerts (`window_check`) pick their reason (`why_*` texts), honour per-device `_push_prefs` kinds and quiet hours, and
  `WINDOW_GAP_S` (15 min) for anything but emergencies and special planes. The radar draws `radarPos()` (dead
  reckoning from when each position was reported, `radar.rep`, so a repeated stale update doesn't pull planes back; gaps
  closed over ~1 s), also for the runway screen's plane (`paintRunwayScreen` keeps repainting through `rwyAgain`);
  positions every 5 s in the app (`refreshS`), relay `FRESH_S` 4. Since 1.33 every plane's `kind` is set before
  `radarTrack` in both styles; `radarCentre()` is the home airport in the Airport style and `radarRows()` gives the list
  beside the radar (spotting radius around the centre, airport statuses); the app's radar ringing a tapped plane
  (`radar.sel`, `radar.hits`) and showing `renderRadarCard()`; Today rows are tappable (`data-more` on the `li`).
- Cards (1.34, shared: the board's "cards" block before the airport mode, copied by the app; styles at the end of the
  board's `<style>`, scoped to `#cardBox` and `.cardish`): `cardOpen`/`cardClose`, `airlineCard`, `placeCard` (relay
  `/airport`), `planeBody`/`planeCard`, `listSheet`, `favManager`/`favCard`, `listsSave` (calls each side's
  `listsChanged`), Wikipedia summaries (`wikiPage`, `wikiFind`, English pages) and model pictures (`modelPic`,
  `isModelPic`; `featPhoto` on the board; 1.35: `modelTitles`/`modelWiki` try several spellings, and pictures are asked
  at 500 px: Wikimedia only serves standard thumbnail widths and answers 400 to others such as 800), `typeCard` (the
  model). The app's `pwCard` sets or changes the password. The board maps a click to its own units (`fieldAt`, `boardTap`; a double
  tap is `toggleFullscreen`), the app its hero panel. `remarkLines()` fills the Remarks flap (`seen` field) and facts.
  `keys/index.html` is the remote key test.
- Places (relay 33, app 1.37, simplified in 1.38 on Dave's word; shared "places" block before the airport mode, copied
  by the app): `places` per profile (`/places` GET/POST, `_clean_places`: `{k: label, n, lat, lon, home, r}`, any label
  but "live"), `placesLoad`/`placesSave`. All labels are alike (no special or automatic
  Home: `ensureHome`/`homePlace`/`placeSync` are gone). Since 1.40 a label is saved from Settings → Location → Place name (see 1.40 below); the card (`placesCard()`) only lists the saved ones (tap: `usePlace()`, applySettings + `placeAfter()`, which resets Spotted today; Update: overwrite with the current S; ×: delete); the live switch and the address search are in Settings. `S.placeKey` is the label being watched (`placeKeySet()`); a Settings save runs `placeCheck()`, which
  drops the label when the point no longer matches it. The key sent (`placeKeyNow()`): "live", else the label, else
  "home" (no `pl`: the profile's own place; `ownSpot` and "here" went with Home in 1.49); `placeLabel()`
  is what to show. A screen names its place on each position request (`placeQs()`: `?pl=key&pc=lat,lon&pr=km`;
  `screen_place`), `Spot.take(..., place)` records around that place with `e.place` (absent = home), and a plane already
  logged today from another place in the same pass only extends that pass (no double entries). `/sightings?place=`
  filters (`sightPlaceQ()`; the app's Today `#svPlaces`/`allPlaces` asks for all). Live location (`S.live`, `S.livePrev`,
  device-only: kept out of `/me`; `S.livePrev` is the label and point watched before, `liveStop` goes back to it):
  `liveStart/liveStop/liveRun/liveFix` (watchPosition, or `hereNow()` every minute in
  the Android app; moves over 300 m move the point, new names via `/geo/reverse` over 2 km, nearest airport over 15 km),
  key "live", shown as "On the go". Address search: `/geo/search` and `/geo/reverse` (Nominatim, one request a second,
  cached a day; `geo_search`, `geo_reverse`), the cards' `placesCard()` and Settings' `wireSearch()` (`type: "search"`).
- Hardening (relay 33, from the code review): `host_ok()` refuses requests for names that aren't the relay's (DNS
  rebinding; loopback, i.e. the tunnel, always passes; `--allow-host`, saved), `https()` only believes the tunnel,
  password sign-in has `pw_wait`/`pw_failed` backoff and a dummy check for unknown users, `allow()` trims its table
  instead of emptying it, `/push/subscribe` needs same-origin and a push-service endpoint (`push_endpoint_ok`),
  `cached_or_stale` keeps a failed GitHub download from being retried on every request, `_positions` and `_cache` drop
  old entries and position requests are rounded to 0.01°, passkeys are removed by their whole id, the CSV defuses
  formulas (`_csv_safe`). Board: `poll()` numbers its updates (`pollSeq`) and draws outside the try; the app's radar card
  only updates its numbers (`planeBody(...).sig/dyn`). `tools/test/smoke.py` and `.github/workflows/check.yml` check
  pull requests.
- 1.38: the app's status dot (`#dot`, a button) opens `statusCard()` (main.js; relay, source and freshness,
  last update, failures, Flightradar24, relay version; refreshed every second while open). List rows: the app's
  `rowHtml` has a `+` (`.flAdd`, `data-add`) as the only way to the favourite/hide sheet, and the airline, places and
  type are `.tap` (dotted underline); the board draws the same on its static layer (`listHints`, `plusBtn`, `plusBox`,
  `tapLine`; the Recent flights flaps leave `PLUS_W` at the row end, `renderSpotted` redraws when the number of rows
  changes; Spotted today has `SV_X.plus`), and `boardTap` only opens the sheet from the `+`. Achievements (shared
  block before the places): `achCheck(game)` from both `fetchLogbook`s compares `achList()` (complete sets, bingo
  lines and full card per week, trophies) with what this browser celebrated (`od.ach`, per guest `od.ach.g.<id>`;
  seeded quietly the first time), and `achNext()` shows a card (confetti(), `chime("special")`) that closes after
  `ACH_MS` (10 s) and waits while another card is open. `RADAR_COL.away` (Outbound) is violet.
  Relay 35 fixed relay 34's custom `--source` state (no `last_call`: every position request failed).
- 1.40 (Dave's list, built in the main chat): Settings → Location has `placeKey` as a field (`type: "label"`, "Place
  name", with a Save inside it, `[data-lsave]`, when the label isn't saved; `[data-lok]` ✓ when it is), `place` shown as
  "City", `home` as "Airport", `type: "update"` (Use current location `[data-loc]` + Live location `[data-live]`; on the
  board also Saved places and the address search, `places`/`search` flags, as its plates have a fixed height) and
  `type: "places"` (the list). `wireLocation(box)` wires them all (replaces wireLocate; calls `wireSearch`);
  `locatedAt(box, lat, lon, name, why)` is what every new location goes through: draft lat/lon, the town via
  `/geo/reverse` into City, `nearbyAirports()` (relay `/airports/near`, up to 3 within 100 km) as a pick list
  (`[data-lask]`) when there are several. Typed coordinates trigger it on `change`. `settingsSync()` puts S's location
  into the open Settings (after `usePlace`, live start/stop/fix, Update, ×). The places card is only the list now.
  The style (`mode`) and `live`/`livePrev` stay out of `/me` and out of a guest's profile settings on load, so each
  device keeps its own. The app's rows: `.tc` holds the time and the `+` ring (`.flAdd`) in column 1 over all three
  rows; `.tap` is an outlined pill. About has `#aboutX`. `html,body{overflow-x:clip}` and the status dot's tap area no
  longer reaching past the screen fixed the sideways scroll; the light hero's stat rows (`data-r` reg, speed, depTime)
  are a three-column grid. The "Save the bell" download is gone (the wav file stays).
- 1.41: About is an overlay over Settings (`aboutShow`/`aboutHide`; `showTab("about")` calls aboutShow; `#t-about` is
  fixed with a sticky `.tabHead`), Settings stays rendered and scrolled underneath. Rows swipe (main.js, touch events on
  `.flights li.fl[data-more]`: past `SWIPE_AT` 72 px right opens `listSheet(x, "fav")`, left `listSheet(x, "hide")`;
  `.swiping` slides the row's children by `--dx`, `::after` shows the label from `--swFav`/`--swHide` set in
  `applyLang`); `listSheet(x, only)` can show one half. Cards' `.cLink` are outlined pills. The Account plate
  (`settingsExtra`: `.acHead` with `.acAv` initial, `#acSub`, `accountBox(el, onChange, plate=true)` with Passkeys and
  Password headings, `#signOut` in `.acOut`) replaced the sign-out button under Device.
- 1.42 (relay 37): tips (shared block before the places: `tip(id, target, text, auto)` queues one, `tipNext` shows
  `#tipLayer` with `.tipShade` (a radial gradient around the target), `.tipRing` and `.tipBub`; seen ids in `od.tips`
  (per guest `.g.<id>`), `tipsReset()`; the app's `appTips(tab)` from `showTab`, the board's `boardTips(view)` from
  `switchView` and once 20 s after start, auto-closing after 11 s). Cards: `cardLoading()` then `cardWhenReady(tok,
  html, wire)` (waits for the pictures, `imgsReady`); airline, place, type and plane cards build their HTML first.
  Logbook by place: relay `place_logbook(spot, place)` sums per-place summaries of each saved day (`_place_summary`,
  past days cached in `_place_days`), `/logbook?place=` (`place_logbook_json`), `/logbook`'s `places` ([key, count]);
  the app's `lbPlace`/`lbPlaceData`, `#lbPlaces` chips, the game/year parts only under All. Today: `fullDay.all` and
  `fullDay.stats`; `todayList()` for Today (empty until the whole day of all places is in), `dayList()` ignores an
  all-places day, `relayStats` only from this place; `#svPlaces` is a two-button switch. The app's rows have no `+`
  (`.tc` holds only the time); the swipe's favourite side is grey until `.armed`. About is the last plate of Settings
  (in `settingsExtra`), with Show the tips again under Device.
- 1.43 (relay 38): `seatbeltDing()` (sound block, synthesised E6 bell, gain .16) from both `setFeat`s for a new plane on
  top unless it rang the special chime (`S.ding`, not at night, 15 s apart, not in the first 8 s). The overhead rotation
  no longer has `stats`: `nextPage()` puts Today in numbers after every tenth round (`rotLoops`, `statsTurn`,
  `S.statsPage`). `modelTag()` on the board's photo, `.mtag` on the app's screen (`.screen.model`), `.cTag` in plane
  cards. Remarks: `seenGet(kind, key)` (relay `/seen?reg=` or `?cs=`, the latter from `book["flights"]`, counted in
  `_record` and backfilled once by `_backfill_flights`, `flightsV`), `firstLines()` names the first (type, plane,
  airline, flight) and is skipped while the logbook is learning; the app's `seen` flap is 19 cells. Today's switch keeps
  the list's height and the scroll position while the other list loads.
- 1.44 (the board catches up with the app): the account code (`accountBox`, `pwCard`, `passkeyAdd`, `acctPost`,
  `accountsOk`, …) moved from main.js into the board's shared block; the board's `account` view (`accountOpen`, from
  Settings' Control plate) shows the Account, Device and Privacy plates (each `grid-row: 1 / span 2`). The board's
  `todayList()`/`fullDay.all` and the `places` button in Spotted today's view tools; `lbPlace`/`lbPlaceData`/
  `lbPlaceOk` now live in the board's code (copied by the app) with place buttons and a CSV link in the Logbook's view
  tools. No scrolling on the board (TVs): `locatedAt`/`wireSearch` open a pick card when the cell is `.updAll`, and About
  has ▲ ▼ (`[data-sc]`, `scrollBy`) for the log.
  The status word flaps turn faster (1.38: `dur` 70 for the plane on top, 60 in the lists and the radar list).
- 1.45: the ding is the recorded Airbus cabin tone (`SND.ding`, its first note; Pixabay, cut by `build_sounds.py`),
  synthesised until decoded; switching it on in Settings plays it. `onMainPage()` (board: no `view`; app: `tab` "now")
  keeps `seatbeltDing()` quiet elsewhere (the chimes play anywhere, Dave's choice). Achievements play `fanfare()`
  (synthesised arpeggio, chord and sparkle), not the bell.
- 1.46 (relay 39, Dave's list in the private `fallblatt-todo` issues): QR sign-in for screens. `refuse()`'s private
  page includes `pair_page_js()`: POST `/pair/new` (stranger, same-origin, rate-limited) gives a six-letter code
  (`PAIR_ALPHA`), a secret and `qr_svg()` of `<public_url>/pair/<code>` (`qr_matrix`: a stdlib QR encoder, byte mode,
  level M, versions 1-10); the page polls `/pair/wait` and reloads once `signed_in()` set the cookie. The phone's GET
  `/pair/<code>` (`pair_page`; `/pair` to type it) asks `pair_who()` (the phone's profile; else
  `signin_html(next)`), POST `/pair/<code>` approves. `_pairs` lives in memory, `PAIR_S` 10 min. Account plate: `.acOutBtn` Sign out chip in `.acHead`, `.acSec` rows (name + state left, button right). The
  ding is the whole chime again (both tones).
- 1.47 (relay 40, to-do #20, #22, #23): the title's styles: the active word in `COL.amber`, the other at .45 alpha,
  `swapSign()` (two arrows) instead of "/" (the app's `#modes` `.sl` is an inline SVG). Logbook chips: `lbChips()`
  (board code, copied by the app) gives `{id, keys, name, n}` for home (merged with a saved label at the relay's own
  point, relay 40), live and the saved labels only; `lbPlaceUrl(id)` asks `/logbook?place=a&place=b` (the relay merges
  a tuple of keys in `place_logbook`; labels may contain commas, hence repeated parameters), `lbPlaceName(id)`.
  Flightradar24: `fr24_period()` from `--fr24-reset-day` (saved; Dave's plan renews on the 9th, 60,000 credits),
  `_fr24_usage` keyed by the period's first day (an older calendar-month or other-day count carries over while it
  started within the period), `usage["by"]` per asker (`fr24_want(..., who)`; /flightinfo passes name · device,
  else "Lists and alerts"), the admin page's renewal line, breakdown table and `/admin/fr24plan` form (`save_config()`
  writes overhead.json the way `--save` does). A temporary budget: `fr24_budget_promo` until `fr24_promo_until`
  (`_fr24_promo()`; `_fr24_budget()` returns it while it runs, else `_fr24_base_budget()`). Dave's Explorer plan is
  30,000 a month, doubled to 60,000 for billing months starting up to 31 Dec 2026 (9 Oct, 9 Nov, 9 Dec); nothing rolls
  over. His choice: 54,000 until 2027-01-08, then 27,000.
- 1.49 (relay 42, Dave's list of 18 Oct 2026, to-do #25, #29-#34): no Home (above; `merge_home()` runs once at start
  under `_data_lock`: `HOME_OWNER` "David" must be exactly one profile's name, else it logs and changes nothing;
  `_merge_day` joins a day's lists (same hex within `SAME_PASS_S` is one pass), `_rebuild_book` counts the logbook
  again from the joined days and leaves the scores, records, trophies and flights to `Spot.book`'s backfills; places,
  lists, push, devices and the relay's location move to the profile; the old files go to `data/home-before-merge/`;
  `profiles.json` `homeMerged` marks it done). The admin page (`admin_html`, `_pform`, `ADMIN_CSS`): a card per profile,
  Guest (invite link) or Account (no link; `/account/user` and `/admin/username` void its unused invites), devices with
  `/admin/device` (first 16 hex of the token hash), `/admin/limit`, `/admin/password`, `/admin/username`. Tips
  (`MODE_TIP`, `PAGE_TIPS` in the tips block; `boardTips(null)` walks styles, pages (`b-p-<page>`) and views; the app's
  `appTips("now")` walks `mode`, `pg-`/`ap-` pages and every tab, also after `setMode`); the board's tips scale with
  `--tipK`. The barking dog: `aboutTap()` (sound block; 7 taps within 4 s; board: Settings' About button and the About
  plate's `#abAbout`; app: `#aboutBtn` and the About page's title) plays `SND.dog` (`build_sounds.py` `barks()`:
  high-pass, `audio.gate`, `audio.fade_out`, 11 kHz). Card music: `cardMusicStart(name)`/`cardMusicStop()` (cards
  block; Web Audio gain on a media element, `MUSIC_S` 30, `MUSIC_FADE_S` 4; a card keeps it while its HTML has
  `data-music`; `cardClose` stops it); relay `/media/<name>` (`MEDIA` allowlist, `MEDIA_DIR` = `data/media/`, Range,
  signed-in only, 404 when absent). The Emirates file never goes into the repository.
- 1.45.1: board CSS inside the cockpit and views must scale with `calc(Npx*var(--k))`: the Fire TV lays out at
  960×540 (K = .5), so fixed px came out twice as big (Update location's buttons, the Place name's Save padding).
- Notifications (relay 25, app 1.22): Web Push with the relay's VAPID key (`data/vapid.pem`), encrypted per RFC 8291
  (`push_send`, needs the `cryptography` package, `PUSH_OK`); subscriptions per profile (`p["push"]`, home in
  `profiles["home"]`), from the app's About → Notifications (`renderPush`, `enablePush`, also asked in the welcome; `app/sw.js`, registered as the app opens; https only; its status-bar badge is `app/badge-96.png`, a white plane on transparent from `tools/app/make_badge.py`, as Android uses only the shape). `_push_watch`
  runs `window_check` (passes within 5 km in 20–180 s: special, first-ever, favourite or below 3,000 ft) and
  `summary_check` (once a day at `SUMMARY_AT`) every 30 s. Since 1.32 (relay 32) `sw.js` shows one notification at a
  time (tag `fallblatt`, older ones closed: Android's group summary showed its own icon) and, with the app in front,
  stays silent and posts `{type: "bell", kind}` (the alert's `kind` from the relay) so the page plays `chime()`;
  `app/airport-bell.wav` (from `tools/sounds/make_bell.py`, same notes as `BELL_NOTES`/`airportBell()`; served as a
  board file, `wav` in `BOARD_FILE`) can be set as the Android notification sound. `S.bell` airport|classic picks the
  special chime; toggling it in Settings plays it (`chime(kind, {force, set})`). (The "Link a device to Home"
  pseudo-profile went with Home in relay 42.)
- Useful: `http://<relay>:8080/status` (JSON), `/screens` (screens using it); on the container
  `journalctl -u overhead-relay -f` is the relay's window (Enter-for-screens only works when run in a terminal).
- Position sources (`SOURCES`, tried in order): adsb.lol, adsb.fi (v3 since relay 36; 1 request a second, so
  `SOURCE_GAP_S`; failed requests count towards a temporary IP block), airplanes.live (403 until Dave's email is
  answered), then AvioADSB (relay 36, emergency only: anonymous tier 1 request/10 s and 100/day per network, personal
  non-commercial use, CC BY 4.0; the source's `gap` 15 s is skipped rather than waited for, `day_cap` 90 per UTC day,
  also stopped by `X-RateLimit-Remaining: 0`; `/status` shows `used_today`). Their terms want a credit with a link:
  the board's `siteLinks()` turns the names in About's credits (and the app's privacy line) into links (`SITE_LINKS`).
  OpenSky is ruled out (needs a written licence).
- Flightradar24 (Explorer plan, Dave may stop after the first month): at most 10 lookups a minute, 27,000 credits a
  month, spread as a daily share (`fr24_paced`). Boards fall back to the free sources when the key is off or refused.
  Relay 41 / 1.48: `/flightinfo` hands out cached answers to anyone allowed Flightradar24 even past a profile's
  daily limit or the budget (then "none", not "off"); since relay 42 the limit is in credits, counted when the lookup
  is made (not on the board's retries). "off" pauses a board's lookups for `API_PAUSE_MS` (10 min,
  `apiOff`), not until a reload; `/sightings` keeps asking `api=1` (`apiWanted`). `recentInfo` (from `infoChanged`,
  `info.hex`) fills a Recent flights row when an answer comes after the plane left the top half, and `withShared` takes
  Flightradar24's flight and route from the shared list for rows that didn't get them.
- "/" for what isn't known (1.48, to-do #24): `NA`/`orNA(v, done)` (network block). `info.done` is set when enrich's
  free lookups are in and Flightradar24 answered or gave up (`lookedUp(info)` from every exit of `apiLookup`; at once
  without it), and calls `infoChanged` (which also runs `scheduleAirport`). Sightings: the relay (41) sets `e.looked`
  after the enricher and `fr24Wait` in `fr24_overlay` while a lookup is queued; `sightDone()` (also true ten minutes
  after the sighting) gives `done` in `fromRelay`; Recent flights rows carry `done` from `fillEntry` (missing = done).
  Times need `timesSettled(info)` too, This aircraft `detailsDone(hex)` (adsbdb answered; not found is `{}`).
  `DRUM_DIGIT` has "/" for the time flaps.
- Relay 45 / 1.51 (to-do #43), fewer Flightradar24 credits: `fr24_info` keeps an answer (key `hex|callsign`) for
  the rest of the local day or `FR24_REUSE_S` (6 h); `fr24_overlay(entries, radius, over_km)` skips sightings whose
  `minDist` stayed above `max(over_km, radius * FR24_EDGE)` (0.75) and counts each sighting once in `_fr24_saved`
  (`e.fr24Saved`, `usage.savedReuse/savedEdge` and `...Today`; shown in `fr24_admin_html`). The board does the same
  for its own `/flightinfo` asks: `enrich(ac, far)` from `logPlanes` (`edgeKm()`), `info.far`/`info.apiLater`, looked
  up when a later `enrich(ac)` comes (closer, or `setFeat`).
- Relay 45 (to-do #49), health watch: `_health_watch` thread writes `data/alive.json` every minute (`clean` true on a
  SIGTERM/Ctrl+C stop) and runs `health_check()`: "sources" (`_health_seen.posFail` set by `aircraft()` when every
  source failed, last `last_ok` over 15 min ago), "fr24" (`_fr24_state` refused), "disk" (`shutil.disk_usage`, 90%,
  back under 88%), and "restart" at start (not clean; `restartSent` keeps it to one an hour across restarts).
  `_health_set` alerts at most once an hour per kind and once on recovery after an alert; `_health_say` logs and
  pushes to `_owner_push()` (HOME_OWNER's subscriptions). `/status` has `health`.
- Relay 46 / 1.52 (to-do #44): `review_range(span, back, day)` (calendar week Mon-Sun or month, board days) and
  `review_json(spot, span, back)` (`/review?span=week|month&back=N`): counts, `newTypes`/`newAircraft` (the entries'
  newType/newReg flags), `rare`, busiest day, top airline, most seen reg, rarest, `note_records` with the spot's centre
  (so `farthest`), `prevPlanes` (the period before). Finished periods cached in `_reviews`, the current one per
  `spot.rev` in `spot._review`. `review_check()` in `_push_watch`: week Sunday >= 20:00, month (back 1) on the 1st
  >= 9:00, once per subscription (`reviewWeek`/`reviewMonth` = the period's start), pref `review` (default on), url
  `/app/#review-<span>-<back>` (the app's `showTab` opens the Logbook there). Board: view `review` (fields `rw_*`,
  `rwf0-7`, `rwNew`; Logbook tools button "Week & month", Week/Month/◀▶ via `data-s`/`data-b`), shared helpers after
  `logbookSummary()` (E24: `review`, `fetchReview`, `reviewData`, `demoReview`, `reviewTitle`, `reviewSummary`,
  `reviewFacts`, `REVIEW_NUMS`); app `reviewHtml()` above the year card.
- 1.53 (to-do #51): the plane card (`planeBody`, cards block, so also app and light) has **Share** when `SHARE_OK`
  (not a TV user agent). `shareCard(x)` → `shareCanvas(x)`: 1200 wide, the photo 630 high on top (cover) when
  `shareImg` gets it (relay 47 `/photo?u=` as a blob → object URL, so the canvas stays clean; else Wikimedia with
  `crossOrigin`; else none), then flaps drawn by `flaps()` (flight, route codes + cities, aircraft, registration, time)
  and FALLBLATT on tiny flaps. The card shows the PNG; Share = `navigator.share({files})` or the Android app's
  `OverheadAndroid.shareImage(base64, name)` (`ShareProvider`, content://<app>.share/, cache/share/), Save = download
  (not in the Android WebView). Relay `photo_get`: `PHOTO_HOSTS`/`PHOTO_TYPES` only, 4 MB, last 30 cached an hour;
  the test relay adds 127.0.0.1 and SVG (the fake photos).
- 1.53 (to-do #52): `S.nightView` "dim"/"view" (Settings → Night, `cols: 3`; `?nightview=1`). `#nightView` (in #stage,
  z 6, board units via `--k`) is drawn by `renderNightView()` (from `applyNight`, every 2 s; not while a card is
  open). A capture listener (keydown/pointerdown/touchstart/wheel) calls `nightPeek()` (60 s) and swallows the key
  that uncovers it; a pointer lands on the fading overlay. The app and light have no night mode, so no night view.
- 1.53.1 / relay 48 (to-do #42), a lighter board file: the translations (`I18N_ROWS`, 152 KB) and the sounds
  (`SOUND_DATA`, 260 KB) moved to `test/i18n.js` and `test/sounds.js` (`window.I18N_ROWS`, `window.SOUND_DATA`); the
  board went from 903 KB to 483 KB. i18n.js is a plain `<script src="i18n.js?v=…">` before the main script (without
  it `I18N_ROWS = []` and `T()` falls back to `I18N.en`, then the key: English); sounds.js is added by `soundFile()`
  5 s after the start when `S.sound || S.chimes`, or by `loadSounds()` when sound starts (a failure: synthesised
  sounds, tried again after a minute). `?v=` is the start of the file's SHA-256, stamped by `tools/assets.py`
  (`tools/app/build.py`, light's build and `build_sounds.py` call it; smoke.py --syntax and CI check it). The app and
  light load `../test/i18n.js` / `../test/sounds.js` (build.py patches `SOUNDS_JS` in E10 and puts the script tag
  before main.js). Relay 48: `board_file(sub, name, ext, want)` refetches a copy whose hash isn't `want` (at most
  every 20 s) and answers `Cache-Control: public, max-age=31536000, immutable` when it matches; `reply()` takes
  Cache-Control from `extra`. `app/sw.js` keeps the versioned files in cache `fallblatt-files` (cache first, older
  versions dropped); the light page isn't in its scope and relies on the browser cache. Main board: its own root
  copies, made by `tools/push_main.py`. Measured at 960x540 on the test relay: first load 888 KB as before (875),
  later loads 486 KB; first flap at 5 Mbps 1.57 s before, 1.19 s first / 0.90 s later after (20 Mbps: 0.50 s →
  0.44 / 0.31 s). AIRPORTS, AIRLINES, TYPES, FLEET stay in the board (a few KB together).
- 1.58 (to-do #47 step 5): Location's last cell is one item, `{type: "location", layout: "combined", phone: {layout:
  "split"}}`: `itemHtml` makes it the board's combined Update location cell (`update` with `places`/`search`, pop-ups)
  or a phone's three cells (`update`, `places`, `search`), the same markup as before (golden list and app/light HTML
  hashes unchanged). Clean-up: plate titles are plain strings (the unused German second titles went; `plateHtml` reads
  `p.title`), the unused `locate` control and its hint went. `tools/test/plates.py`: `OVERFLOW_JS` (plates whose
  children end past the plate) and `FIRE_TV` (960x540 @2x, a Fire TV's user agent); smoke.py opens the board's
  Settings and Account & device at that size and fails on any overflow; shoot.py has a `plates` step.
- 1.57 (to-do #47 step 4, settings on both sides only where it makes sense): the Night plate is on both; on a phone
  Night mode, Quiet from (`phone: {label}`) and Until, with its own hint (`phone: {hint}`; `itemHtml` takes `it.hint`
  first); At night and Brightness `for: "tv"`. main.js: `nightCheck()` sets `nightOn` (which the copied sound code
  already checks) at load, every 30 s and in `applySettings`; DEFAULTS night/nightFrom/nightTo as the board's. Kept
  as they were, decided item by item: Today in numbers and Change pages TV-only (the app has no turning pages; its
  Today tab always shows the day's numbers); Update every and Drawing quality TV-only (Dave); the Favourites cell
  TV-only (a phone has the Favourites & hidden plate); Notifications and About plates phone-only, Privacy TV-only
  (a phone has it in About); the Control plate TV-only (a phone's Save bar); dimming and the night view TV-only.
- 1.56 (to-do #47 step 3, #71, #74, #75): Account, Notifications, Device, Privacy and About are `view: true` plates in
  the shared `COCKPIT` (items `{type: "account"|"push"|"device"|"privacy"|"about"}`, `cls`, `cols: 1`; `push` and
  `about` phone-only, `privacy` TV-only). `cockpitFor()` keeps them (phone: no 2 columns); `PLATES` leaves them out,
  `VIEW_PLATES` has them. `itemHtml` hands these types to `viewItemHtml(it)` (no `.inst` cell); `wireViews(box)` wires
  Sign out (`acctHas`), the tips link, Back to Settings (TV), `uiBtn` (`od.ui`), Change relay (Android), `renderPush`
  (phone) and `accountBox`. The board's `accountOpen()` and the app's `settingsExtra()` are now three lines each;
  the board's `plateHtml` adds `cls` and `grid-row: 1 / span 2` for view plates. #74: `accountBox` (plate) draws
  `.acCheck` rows with `acRow(done, name, line, button)`, `.acTick`, `.acGo` (Add / Change ›), saved passkeys in
  `.acKeysRow`. #75: `.devTiles` of two `.devTile` links (`DEV_ICON` SVGs; TV: Phone app + Light version; app: Light
  version + Full board; light: Full app + Full board), `.devLinks` of `.lnk` buttons. #71: `#recent li` in head.html
  (14 px padding, a white line at .13). `tools/test/cockpit_list.py` also lists the view plates (`VIEW` lines: the
  board's Account & device view, the app's and light's `#setExtra`).
- 1.54 (to-do #53, #56-#64): `saveSettings` (board, app, light) always sends and keeps every key of this screen's
  Settings (`cockpitKeys()`: `ITEMS` without the place keys, which go by `locSet`), so a setting back at its default
  overrides the profile's merged old value. Favicon: an inline SVG data URI in the board (the app and light use
  icon-192.png). Cards scale with the board through `--ck` (`max(.5, K)`, set in `resize()`; the app leaves it 1):
  all `#cardBox` px are `calc(Npx*var(--ck,1))`. Card music (`cardMusicStart`): with Web Audio, `musicBuf(name)`
  fetches the first `MUSIC_BYTES` (900 KB, ~45 s) in one Range request, decodes and plays an AudioBufferSource
  (cached per name); the audio element (which read the fragmented m4a in ~15 small range requests, seconds through
  the tunnel) is the fallback. `S.logos` is forced true (switch, hint, `?logos` gone). Hints with a mouse or remote:
  one `#hintTip` (fixed, `--tipK`), placed above the control or below it, clamped to the screen; touch keeps the
  in-cell `::after`. Rotary labels sit at `--r` per position (at least 44: 32 + 5.5·|cos a| + 3.15·chars·|sin a|); toggles
  are 96 tall (was 90). `maxAltFt` has `metric` steps (8200/16400/24600 ft shown as 2.5K M/5K/7.5K; `rotOpts(it)` by `draft.units`,
  labels swap in `cockpitShow`). The Control plate (`.plate.ctl`) centres its texts; the app's favourites Add is a
  `.cap` inside a plate.
- Relay 47 (to-do #46): `window_check` split into `window_planes(who, centre, spot, st)` (the planes worth a look with
  `kinds`, `airline`) and the alerts. `hue_check` (thread `_hue_watch`, every 15 s) takes the owner profile's place,
  pulses for the first plane with kind special/fav not in `_hue_seen` (3 h), at most every `HUE_GAP_S` (60 s), not in
  the quiet hours. `hue_pulse(rgb, what)` saves each lamp's state, 3 steps (254/110/254), restores bri + xy/ct/hs,
  then off for lamps that were off. Colours `HUE_COLOURS` by ICAO, else `HUE_AMBER`. Admin: `hue_admin_html`,
  `/admin/hue/{find,use,pair,forget,switch,quiet,lamps,test}` (`hue_admin_post`); `hue_find` uses
  `HUE_DISCOVERY` and checks `/api/config`; `hue_addr` only private/loopback IPv4; `hue_pair` asks every 2 s for 30 s
  (error 101 = button not pressed) and the admin page refreshes itself meanwhile (`plain_page(refresh=)`).
  `tools/test/fakehue.py`: pairing works on the second try, `/log` lists lamp changes, `/discovery`.
- Relay 46 (to-do #45): `admin_stats(pid, p, live)` per profile card on `/admin`: today/week/total, new aircraft and
  types this week/month (from `review_json`), rare this month, live screens whose hello name is the profile's.
- Relay 46 / 1.52 (to-do #50): `_vie_load` keeps `gate`/`gateArea` (departures) and `belt` (arrivals) from Vienna's
  lists; the board's `vieLines(info)` adds "DELAY n MIN"/"ON TIME"/"DELAY /" and, for departures, "GATE x" to
  `remarkLines` (two lines: `clean()` drops "+"; the old Delay flap stays gone). Fake source departures have gates.
- Relay 45 / 1.51 (to-do #41): `/pageversion?p=<sub>` gives the newest published version of a board (`board_html`,
  first `{v: "` in the page). The shared `watchVersion()` (patch-notes block) asks it every 2 min (older relays: the
  page every 10 min) and calls `nvShow`: `#nvBox` with a 60 s countdown; `nvInput` (capture keydown/pointerdown/
  touchstart/wheel) stops it, Enter on the focused button or body reloads; `nvTick` reloads at the end or after 30 min
  without input, never while `nvBusy()` (card, text field, `NV.busy`: the board's unsaved Settings via
  `cockpitUnsaved()`, the app's Settings tab).
- 1.51 (to-do #48), the first picture: `snapLoad`/`snapSave`/`snapLive` (E15 block, after `relayStats`), key
  `od.snap.<profile>:<path>`: feat (last 30 min), spotted (40, same `boardDay`), relayStats, nearbyCount; saved after
  `process` at most every 20 s; `snapLive` on the first positions drops the stored plane and `#snapTag`.
- Tools (1.51): `run_test_relay.py --port` (env `PORT`; the fake source on port-1 via `FAKE_PORT`), `smoke.py --port`,
  `shoot.py` takes the fake source's port from the URL. smoke.py kills the test relay's process tree (a plain
  terminate left its two children running on Windows, answering later runs on the same port).
- Behind a proxy on the same computer, the relay (14+) takes a screen's address from `X-Forwarded-For`.
- It serves the published boards from GitHub Pages (refreshed at most once a minute), so pushing to `main` reaches
  the screens a minute or two later, when they reload. `--local-root <repo>` serves a local checkout instead.


## Ideas Dave hasn't picked yet (Oct 2026)

Wake The Frame and reopen the board when it drops off,
Art Mode at night (Samsung's local TV API); a spotter's
collection page and weekly bingo of rare planes; rarity marks ("first time ever", "seen 4 times"); worth going to
the window (cloud base vs altitude, sunset, which window); runways in use at Vienna; a day in review at night; phone push via ntfy; a Vestaboard-style 6x22 view; a report of
what Flightradar24 added, to decide on renewing.
