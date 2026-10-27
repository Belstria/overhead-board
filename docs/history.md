# Fallblatt: version-by-version details

Moved out of `CLAUDE.md` (which holds the rules and the current architecture in short) so that every session
doesn't have to read it with every step. Read the part for the area you are touching: it says what each version
added and names the functions and fields involved. Text from before 1.49 / relay 42 is history: **"Home" as a
profile or identity no longer exists** (every screen is a profile's device since relay 42; `at_home()` only opens the
admin paths), the Flightradar24 budget is not 27,000 but 54,000 a month until 2027-01-08 and 27,000 after, and the
`homelink` / "Link a device to Home" idea went with Home. Where this file and the code disagree, the code wins.
The repository is public: no addresses, keys or personal data here either.

## How the board works (index.html and the test board)

- 1.94 (to-do #113 and #114, Dave's mockup A with his More info; relay 74): **the info cards in Sky view's card
  style**, with more facts for spotters. Shared (cards block, so the app too): `infoCard(o)` draws every one: the photo
  (`picHtml(pic, " cSkyPic", over)`, its credit at the top-left, clear of the round ×: `.cardIn.info`, set by `cardOpen`
  when the html starts with `.cInfo`), the title, sub (a button with `subAttr`) and chip on it (`.cOv`; `.cOvPlain`
  without a photo); the band (`.cRouteB`, ends as buttons when they lead somewhere); three boxes (`.cTiles`); the first
  of `facts` as Fun fact (`.cFun`); the facts in two columns (`.cDet`); Wikipedia's first paragraph in three lines
  (`.cWiki.clamp`) with the small "Wikipedia ↗" link to the page (`.cSrc`: its words are CC BY-SA); More info
  (`.cMoreB`, `data-info-more`: the app's list rows already use `data-more`) and, hidden, the rest of the paragraphs
  (`.cMoreT`) and Did you know (`.cMoreX`, `.cKnow`: facts 2 to 4, each with its source); the buttons. `cardMore` opens
  it where it is (the clamp off, the parts shown, the button hidden; a ring that was on it goes to the Wikipedia link),
  lets the app's sheet grow (`cardSheetGrow`) and scrolls the card to the words, smoothly unless `REDUCED` or `LITE()`.
  The cards: `typeCard` (photo, name, maker · code, rarity `tierChip`; first flight → in service; Built with "{name}
  family" when the page is a family's (`familyName`), In service ≈ `FLEET`, Spotted; Code, Engines, Seats, Wingspan,
  Length, Range, Main user, Built (years), Developed from › (a model card by its page: `typeCard({page, type})`),
  Planes spotted, Today), `airlineCard` (its plane from Commons with the logo; founded → main base (a place card);
  Fleet, Destinations, Spotted; Radio callsign, Headquarters, Hubs (two or more), Owner (with shares), Employees,
  Alliance, Planes spotted "m of n", Today; the late logo now joins: the shown card's token, not the loading one),
  `placeCard` (Wikidata's photo, not the logo the summary gave DXB; city · country, codes as the chip; your airport →
  there with the distance between them; Passengers (and year), Runways, Opened; Codes, Elevation, Operator, Distance
  (from here), Spotted (flights to or from it), Today) and the plane card (`planeBody` outside Sky view: the flight,
  airline and status on the photo, the route as the band, `planeTiles` from `planeLog`: Spotted, Closest (at its
  height), Flights; the live numbers stay `data-dyn` spans among the facts for the radar's updates, with Registered;
  `planeCard` waits up to 1.5 s more for the row). Data: `factsGet(kind, key)` (relay 74 `/facts`, kept per page),
  `spottedGet(part, key)` (`/logbook/spotted`, two minutes), `planeLog(reg, onReady)` (the logbook search, relay 55;
  undefined while asking, null never spotted, false can't ask; five minutes), `airportGet(code)` (`/airport`, relay 18).
  Older relays: the same layout with what there is (the summary's words, `airlineWiki`, `wikiFind`). Fun facts, only
  from real data, in order: `modelFunFacts` (first flew N years ago today; one of N built, you've seen K; wingspan
  against a football pitch 105 m, an Olympic pool 50 m or a tennis court 23.77 m; range: the farthest of
  `RANGE_CITIES` (40) under 90 % of it, from the screen's place; first flew N years ago; still being built),
  `airlineFunFacts` (flying for N years from its first flight, or founded; you've spotted M of its N planes; its main
  base's distance), `placeFunFacts` (passengers against your airport's, both Wikidata's; opened N years ago),
  `planeFunFacts` (back after N months, two months or more; first spotted). #114: "Seen here" (since a date) is
  Spotted: Once or N times (`timesText`; "Not yet"). `wikiHtml` went (More info took its link). TV: the cards stay
  pop-ups; the Logbook's ring (`lbKey`) reaches every button and link of them (More info too: OK opens it, Back
  closes); `.cInfo` buttons and links have the amber ring (`:focus-visible`), toggles a box-shadow ring so their
  "on" outline stays; sizes are `calc(Npx*var(--ck,1))` in the app's type scale.
- 1.93.1.1 (to-do #112: Dave's BE20 "BEECH 200 Super King Air" and C210 "CESSNA 201 Centurion" had no picture):
  **model pictures for nearly every type, never another model's**. Measured over Dave's 122 logbook types with their
  names as the sources gave them (`tools/test/model_pics.js`): before, 87 had a picture for every name, two of them
  wrong (BALL got "Ball turret": the code itself was searched; E35L's "EMBRAER EMB-135 Legacy" the Embraer company
  page); now 121, none wrong (checked by eye on a contact sheet and against the pictures' file names); the miss is PULS
  ("Aero Pulsar XP-II"; Wikipedia's page is "Aero Designs Pulsar"). Every code in MODEL_PAGES and TYPES: 428 of 428.
  Shared (cards block, so the app too): `modelPage(names, code)` checks in one action-API request (`wikiPages`, `WIKI_API`:
  up to 50 titles with their redirects, disambiguation flag, short description, intro extract (20 pages at most),
  picture and Wikidata id) the code's page (`MODEL_PAGES`) and the names' spellings (`modelTitles`, `modelSplit`: the
  maker as Wikipedia writes it (title case, `MODEL_MAKERS`: BEECH → Beechcraft, TEXTRON → Cessna, AGUSTA →
  AgustaWestland ...), `numForms` ("PA-28R-201T" ... "PA-28"), the words without the number, the number without the
  words, the model without its maker ("Learjet 45"), another name's maker ("Cessna" + "Citation CJ2"), "Cessna NNN" from
  a C+3-digit code); Wikipedia's search (generator=search, two names at most) only when none fits. The code's page and
  whole names are taken as they come; a title made from part of a name must not contradict the rest (`modelClash`:
  numbers by their start, `numCore` a320 / pa28 / 737, the code's digits count as the model's; words: the page has its
  own while the name has others) nor be a family's page without a number ("Cessna Citation" leads to the family's,
  which shows a CJ3); a search hit (`modelHit`) needs the maker and the number (all words when there is none). Every
  page must be about an aircraft (`modelOk`: `MODEL_LIKE` on description and extract, `MODEL_NOT` (company, airline,
  list ...) on the description without brackets: the YS-11's names its maker's Corporation). The first fitting page
  wins; without a picture of the aircraft (none: the Cessna 150's, for now; a file named "logo": the BAe 146's;
  `MODEL_OTHER`: the Citation Latitude's is a Citation XLS) `wikidataPic` takes its Wikidata picture (P18) as a 500 px
  Commons thumbnail (imageinfo). The code is never a name (`modelPage` drops a name equal to it). `MODEL_PAGES` comes
  from `tools/model_pages.py`: the list's link per code, its mistakes fixed (PAY2 is the PA-31T, C130 the military
  Hercules, AC90 linked the company, H25B shows the Hawker 800), common light aircraft, helicopters and military types
  added (codes checked against ICAO Doc 8643), every title checked; a code whose TYPES name leads to a page is left out;
  BALL, GLID, GYRO, SHIP and ULAC are kinds ("*"), tried after the names. One request per model as a rule, three at
  most (Wikidata), 9 s each; Wikimedia allows a browser 200 a minute, a script without a proper User-Agent 10 (the
  tools send one). `modelLook` keeps each lookup by `modelKey(names, code)` (main.js's `modelPicNow(names, code)` too);
  one that failed is asked again a minute later. `modelPic(names, onReady, code)` calls every caller waiting
  (`modelAsk`), not only the first. Late pictures: `cardWhenReady` returns the opened card's number (`cardTok`);
  `typeCard` redraws when `modelWiki` answers after its 4.5 s, while that card is open; `planeCard` keeps `planeTok`
  and `planeAgain` redraws only that card (one opened from it stays), and a photo found while the card waited for its
  pictures goes in at once; `planeLate` is the one callback (`psPhoto` keeps it once too).
- 1.93.1 (to-do #111, the second try at #108: a phone's Chrome kept showing a village far away where it had been days
  before, and the relay ran the gap filler around it): **live location takes no old position**. The cause, from Chromium's source (155, the
  Android stable then): with `kApproximateGeolocationPermission` (on by default on Android since May 2026) a page that
  asks without `enableHighAccuracy` is an approximate client (`GeolocationImpl`: hint and precise permission);
  `GeolocationProviderImpl` keeps the last approximate position across page loads (`low_accuracy_result_` isn't
  cleared when the last page stops) and hands it at once to every new watcher, whatever its age, with its own
  timestamp; a new approximate one is passed on at most every 15 minutes (`kApproximateGeolocationUpdateInterval`).
  `liveRun` asked without high accuracy, and `liveFix` set `liveAt = Date.now()` for whatever came: that old position
  counted as a fresh fix at every page load and at every `liveStart`. Seen that way in the test relay: the old point in
  the title and `fix=0` around it, so the gap filler started. Now (places block, E33): `liveRun` asks with
  `enableHighAccuracy: true` (watch and the minute's re-ask; Chrome stops watching while the page is hidden), and a
  position older than `LIVE_OLD_MS` (2 min) by `geoPos(p).age` is no fix: logged once a minute at most (`liveOldSaid`)
  with `geoNote()` (age, ±accuracy, km from `S.lat/S.lon`), its accuracy kept in `liveOldAcc` (0 after `liveHalt`).
  FINDING YOU … and `fix=-1` stay until a fresh one. `liveFix` logs each run's first position. The one-minute note says
  to allow precise location in the browser's site settings when the last old one was approximate (±1,500 m or more).
  `hereNow` (Settings' Here, the welcome) waits on a `watchPosition` for a fresh position (20 s) instead of taking
  `getCurrentPosition`'s first answer; Sky view's watch (main.js) skips old ones too. With an Approximate-only site
  permission, a page reopened within Chrome's 15 minutes waits for the next one (up to ~13 min); Dave and the main chat
  chose that over taking approximate positions up to 15 min old.
- 1.93.1 (Dave: "Ask each time"): **turning live location off asks where to watch**. Settings → Location's Live button
  (`wireLocation`) calls `liveAsk()` first: with a fresh fix (`liveAt`, not `liveStale()`) and a `S.livePrev` it opens a
  card (`cardOpen`, `.pickList.lvAsk` with two `.cBtn`s): **Stay here** (`liveStay()`: the last live point, its name from
  `S.liveNamed` and airport from `S.liveAir` when `liveNameOk()`/`liveAirOk()`, else "Here" and the old airport until
  `geoReverse`/`nearestAirport` answer; no `placeKey`, so the profile's own place) or **Back to {label or name}**
  (`liveStop()`, unchanged). Without a fresh fix or a place before, `liveAsk()` returns false and the button calls
  `liveStop()` as before. Closing the card keeps live location on. The remote: the first option has focus, the arrows
  move between the two (the Logbook cards' focus ring, `#cardBox .lvAsk .cBtn:focus`), OK picks, Back closes (the
  cards' capture listener). `usePlace`, `locatedAt` and the start-up `liveOk()` check still turn it off without asking.
  `settingsSync` now copies `live` and `livePrev` into Settings' draft, so its Save no longer turns live location back
  on (or off) after the switch was used with Settings open.
- 1.93.0.1 (to-do #108, a phone back from a trip showed the trip's village as it opened): **live location never shows an
  old town**. Shared (places block, E33): the town's name and the airport are kept with the point they were found for,
  `S.liveNamed` `[lat, lon, name]` ("" where Nominatim has none) and `S.liveAir` `[lat, lon, code]`, saved on the device
  only (`meSend` drops both keys); `liveNameOk()` (a name, within 2 km of `S.lat`/`S.lon`) and `liveAirOk()` (15 km)
  are true when not live. `placeNow()` is the name to show, "" while live and waiting or not `liveNameOk()`: the board's
  title and the app's `updateWhere` say ON THE GO then (the app without the radius, as with FINDING YOU …, so it fits
  390 px), the radar's close-up subtitle On the go, a Sky view picture "Sky view", `placeOfS` (Saved places' Update)
  no name, and Settings' City field is empty and disabled with the placeholder On the go (`itemHtml`, `settingsSync`,
  which also copies both keys into Settings' draft, so its Save doesn't bring back older ones).
  `meSend` leaves out `place` while `!liveNameOk()` and `home` while `!liveAirOk()`, so the relay's profile never gets
  an old one. `liveFix`: `liveShow()` at the first fix (FINDING YOU … used to stay until the lookups ended: the 2 s
  check could miss the change) and when the name turns old; `geoReverse` returns null when the relay didn't answer;
  the name and the airport are asked side by side (`Promise.all`) when the fix is past 2 / 15 km from their point and
  the last unanswered lookup is `LIVE_RETRY_MS` (a minute) back (`liveNameAsk`/`liveAirAsk`: its time, Infinity while
  one is on its way, 0 after an answer); a point is marked only after an answer. A result for an older `liveRunAt` is
  dropped. `liveStart` deletes both (a place set by hand isn't named for the phone's point). `tools/test/fakesrc.py`
  `SLOW_NAMES=1` (`run_test_relay.py --slow-names`): names take 5 s and the first lookup of each point fails.
- 1.93.0.1 (to-do #107): **About on the boards in two halves**. In Settings' third column (630 board px) the About
  plate ran 73 px past its edge on every screen (92 at 1366x768, where text wraps differently) and Keys 5, cutting off
  the radar map's and the World Magnetic Model's credits. `aboutOpen` sets `#cockpit.about` (`cockpitOpen` and
  `accountOpen` clear it): two equal columns, rows `auto minmax(0,1fr)`; Patch notes (`.plate.notes`, both rows, ▲ ▼
  as before) on the left, Keys as tall as it needs over the About plate on the right. `dl.keys` has four tracks (two
  keys a row) and `KEYS` the photo link's row again (↑ ↓ "This aircraft: the photo's link (OK opens it)", 1.93 left it
  out for room). About has 111 px to spare in English, 77 or more in the other languages, at every size tried (Fire TV,
  1080p, 1280x720 to 1920x1200). smoke.py opens About at the Fire TV's size too and fails on an overflowing plate.
- 1.93 (to-do #95, Dave's mockup A and wording B; relay 73): **the plane's own photo from Planespotters.net**. Shared
  (cards block, so the app has it too): `psPhoto(reg, hex, onReady)` asks the relay's `/planephoto` once per
  registration (`psPhotos`: `{at, photo, cbs}`, photo `undefined` while asking and `null` for none, kept `PS_KEEP_MS`,
  an hour; not answered: asked again after two minutes; `psOk()`: relay 73+, not in demo mode). `planePic(ac, info, d,
  onReady, noPs)` gives `{src, kind: "ps" | "own" | "model" | "", by, link}` in the order Planespotters → adsbdb
  (`d.photo`) → `modelPic`; while Planespotters is being asked there is no photo yet, so a screen doesn't change twice.
  `picCreditParts`/`picCredit`/`picCreditHtml`: "© name · Planespotters.net ↗", "Photo · airport-data.com", "Model only
  · Wikimedia Commons" (the first part, `.crBy`, gives way on a narrow screen; `.crSrc` stays whole). `picHtml(p, cls,
  over)` is a card's photo: `.cPicW` with the credit `.cCr` on it, a Planespotters photo inside `a.cPicA` to its page
  (target _blank); `picFailed` puts a Planespotters photo that doesn't load in `psBad`, and the next one shows. The amber
  "MODEL PHOTO · NOT THIS AIRCRAFT" tag is gone everywhere (`modelTag`, `.cTag`, the app's `.mtag`, `isModelPic`).
  Board: `featPic()` (`rwyFeat()`: the runway screen of the Landing and Take-off pages has no room for the credit and
  link, so no Planespotters there), `featPhoto()` its src. `paintScreen` no longer draws a credit: `#photoLink` (`.pLink`,
  an `<a>` over the whole screen in `#photoFrame`; `#photoCr` the credit, in `FONT`) is set by `photoLinkSet(p)` from
  `placePhoto`, with an href only for Planespotters (without one it is plain text and takes no clicks). The remote
  (Dave, 26 Oct: no QR code, the credit is the link): `photoKey(e)`, from the board's keydown, puts the ring (the Logbook
  plates' amber one, on `:focus` for the older TV browsers) on the credit with Up or Down and takes it off again; OK is
  the link's own, and its click takes the ring off (a mouse click left the focus there); the rotation's 1 s tick holds
  the page while the credit has the ring. The share picture
  (`shareCanvas`): `x.pic` is `planePic` without Planespotters (their terms), its credit in the same small caps;
  `shareImg` also loads `thumb.wikimedia.org` directly (Wikipedia's thumbnails come from there now). `planeCard` waits
  for a photo (up to 2.5 s) whatever adsbdb has.
- 1.92 (to-do #103, Dave's mockup C without Newest aircraft): **the Logbook on one screen**. The Records and Week &
  month views went into it (`VIEW_NAMES`/`VIEW_FIELDS` lose `records` and `review`, with `renderRecords`,
  `renderReview`, `reviewFetch` and the `rc*`/`rw*` flaps; `LB_VIEWS` stays for the app). `LB_BOX`: seven plates, four
  above (266 to 620, Settings' first row: totals, period, cats, records) and three below to the rail (types, airlines,
  regs, a third of the width each). `lbPlates` draws them from `drawStatic` before `slots` (`plateDraw`: Settings'
  `.plate` on the canvas, its gradient, shadow, screws, `body.real` brushing and the engraved title between two lines).
  Their flaps: `lvSight`, `lvRegs`, `lvTypes`, `lvAirlines`, `lvModel`; `lp0-5` (the period's numbers, `LB_NUMS` for
  a year or a week/month) and `lf0-2` (busiest day, most seen aircraft, rarest: `reviewFacts`, which reads `/year`'s
  answer too); `lvl_*`/`lvn_*`; `lrc0-3` (`LB_RECS`); seven rows of `lt*`/`la*` (names 19 flaps, `lbModel` drops the
  maker only when it doesn't fit) and `lr*`. `lbStatic` engraves the rest: the labels (`lbLabels`, `lbLabel` squeezes
  one to end before the next field), the model's count, the categories' names, each record's date and plane;
  `renderLogbookBoard` draws it again when `lbStaticSig` changes. The period: `lbPer` ("year" at first), `lbYearBack` or
  the shared `review.back`; `lbYearFetch` (relay 29, kept in `lbYears`, 5 min) and `fetchReview`; `lbFetch` every
  30 s while the view is open; `lbPerSet` from the buttons and the card; `demoYear()` in demo mode. `/year` and
  `/review` count every place, so with a place picked (`lbPick`) the plate's title adds "· All places".
  `#viewTools` (`lbToolsHtml`, `lbToolsWire`, `lbToolsSync`, which lights buttons without building them again): the
  search (`HAS_KEYS`, relay 55; Enter runs `lbSearch`), All and the places, the CSV; then Week · Month · Year and ◀ ▶.
- 1.92: **the Logbook's cards** (`lbCard(k)`, `lbCardHtml`, `lbCardWire`): Totals (and Logbook for: the places as
  buttons), the period (Week · Month · Year, ◀ ▶, the numbers, every fact, the new types; "Counted over every place."
  with a place picked), Categories (each a button that opens its top ten, Types · Aircraft · Operators, from
  `/logbook/category`, relay 61: `lbCatFetch`, `lbCatData`), Records (with plane and day, and the period's), and the
  three lists in full (`lbRow`). A type's row opens `typeCard`, an airline's `airlineCard`, an aircraft's its sightings
  (`lbSearch`, which `lbFoundHtml` lists like the app's search); `lbBackTo` (`lbCardBack()`) brings back the list on
  Back. `lbCardAgain` draws an open card again where it was (scroll, and the button that had the ring, by `data-lk`);
  `lbCardWait` marks a card still loading, which new data fills in. Chosen buttons in these cards are `.cBtn.go` (gold),
  so the remote's ring (an amber outline) stays clear.
- 1.92: **the Logbook with a remote**: `#lbHits` holds a transparent button per plate (pointer-events none, so a
  click still reaches `boardTap`, which opens the plate under it via `lbBoxAt`; `.hov` and `#fx.lbHov` show the mouse
  what is clickable). `lbKey`, called by the board's keydown in the Logbook, moves the focus with `lbNear` (the nearest
  past the edge in that direction, off to the side counting three times) among the plates and `#viewTools`'s buttons,
  or among an open card's buttons and rows, only to what is in sight (else the card scrolls). OK is the focused
  button's own click (`lbCard` then focuses the card). Backspace, Samsung's 10009 or LG's 461 with no card open leave
  the view, as Esc does. A capture keydown before cardOpen's own puts the ring back on its plate when a card closes, or
  runs `lbBackTo`. On a TV (no `HAS_KEYS`) `lbHitsShow` puts the ring on the last plate as the view opens. The board's
  first-run tip takes the first key, as everywhere.
- 1.92 (to-do #106): Spotted today's PAGE x OF y is drawn at the end of the line under the title (`W - M`, 248), under
  ◀ ▶; it stood at a fixed place left of the filter box, and with the place button the box covered it.
- 1.90 (to-do #92, Dave's picks "A + the compass from B", relay 72): **Sky view's sun and moon pointers, compass ribbon
  and report**. `arBodyEdge()`: a body above the horizon whose ring is out of the picture gets a dashed arrow at the
  edge (the shape of `arEdge`'s) with "☀ SUN" and how far to turn (left/right when beyond half the picture's width,
  else up/down), from `arUnproject` of the picture's middle. `arRibbon()` draws `#arRib` (a canvas in `.arBot` above
  the hint, hidden with the hint while a card is open): 360° centred on the way the picture faces, ticks every 15°,
  `AR_RIB` letters (N red, through `T()`), the picture's width bracketed, ☀/☾ at their azimuths with "{n}° up"; it
  redraws only when its signature changes. The flag `#arFlag` (`arReportOk()`: relay 72+, `GUEST.owner`) posts
  `arReport()` to `/skyreport`: app version, OS, event counts per kind (`arEvN`: abs/rel/ios, to see whether a phone
  sends the gyroscope's reading at all), `arGap`, declination, `arOff`, held (`arHeldWhy`), unsure, turn rate, facing,
  the quaternion, `arGapLog` (every 4th) and `arRaw`, AUTO's lock and finds, the sun and moon and `arSunLast` (the sun's
  ring offset from AUTO's last sun find), screen and video size, focal length. `arNote` keeps the hint's answer for 8 s.
  The relay (`sky_report_clean`: numbers, flags, short strings, 3 levels, place-like keys dropped; `sky_report_save`)
  keeps them in `data/profiles/<id>/skyreports.jsonl`, the newest `SKY_REPORTS_MAX` (200), owner only, same origin,
  1 per 10 s (burst 3).
- 1.90 (to-do #93): **steadier labels**: a complementary filter in `arGapStep`. North (`arGap`) follows the compass
  always, not only when still, but slowly: `AR_GAP_TAU` 6 s, ×3 while turning (`arMovedAt` within `AR_STILL_MS`), ×4
  while unsure (iOS accuracy poor, or `arCalAt` within 4 s), at most `AR_GAP_MAX` 1°/s (a quarter unsure); the first
  `AR_GAP_SETTLE` 1.5 s after the first reading settle with τ 0.4 s. A steady difference is no swing: while still,
  when the compass's last `AR_GAP_STEADY` 1.5 s agree among themselves (sd < 2.5°) but differ from north in use by over
  4°, `arGapFast` glides there with τ 1.5 s, all the way (within 1°) unless the phone moves or the compass wavers (a
  compass that comes right after Sky view opens, north carried over wrongly). `arGapLog` now keeps the compass against
  the gyroscope from the first reading (`arGapRef`; cleared when the gyroscope's zero jumps), not against north in use,
  so the 12° swing check sees only the compass. `arCalCheck(…, gyro)`: with the gyroscope's reading the 1.66 check
  (heading swinging while the tilt holds) is left out, as a smooth pan looked just like it ("Compass unsure" while
  turning). Held (AUTO or a drag) is as in 1.86.
  `tools/test/sky_jitter.js` runs main.js's own sensor code on a made-up Android stream (60 Hz, gyroscope drifting
  .02°/s; outdoors compass ±1.5°, indoors ±3° plus ±8° swings with time and heading; a compass 25° off for its first
  4 s; the gyroscope's zero jumping 40°) and prints the label movement while still and how long north takes to come
  right. 1.89 → 1.90: indoors the most a label wandered in a still spell 6.4° (75 px) → 0.7° (9 px), frame to frame
  0.031° → 0.005°; outdoors 1.45° → 0.21°; the 25°-off start right (within 2°) after 9.3 s → 9.4 s; the zero jump
  unseen in both. North's average error indoors rose 3.9° → 5.9° (it follows the swinging compass less; that
  compass's own error is about 4.5° there).
- 1.90 (to-do #94): **the picture button only once locked on**: `arShotAt` is set while `arLocked` (the plane the ring
  last filled on in this Sky view, set in `arAimDraw`; a tapped plane doesn't count) is in the picture, no longer for
  any plane the game had locked on earlier today (`s.locked`); it still stays 5 s after the plane leaves the picture.
  While the small card is open the shutter sits above it (`--ar-lift` on `.arBot`, the card's height; it was behind it).
- 1.90: **no planes before live location's first fix** (a phone whose Chrome never got a fix at home showed a trip's
  planes 1,100 km away): `liveWaiting()` (live and no `liveAt` yet) empties the list in `poll()` (with its `now`);
  the title line says only "◉ FINDING YOU …" (app `updateWhere`; board `drawStatic` without the place); after a minute
  from `liveRun` (`liveRunAt`) a red toast once says live location isn't working on this device, its Settings button
  `switchView("settings")` on the board, `showTab("settings")` in the app. Relay 72: `live_stale()` treats a live
  request without `fix` as stale too (only an old cached app leaves it out). The app's red toast button was red on red.
  Nothing from before stays while finding: `liveBlank()` (from `liveRun`: going live, or the page opening live) drops
  the plane on top, `recent` (the planes' last positions, which the 30 s missing grace kept on), `lastList` (the 2 s
  look-again re-ran the old place's update) and the snapshot, resets `emptyStreak`/`lastCount` (an empty sky isn't taken
  for a source's glitch), then `process([])` and each page's `liveShow()`, which now redraws the lists too. `snapLoad`
  shows no last known board in live mode and `snapSave` saves none while finding. `dayList()` (board and app) and the
  board's `recentShown()` are empty and Today in numbers leaves out the relay's numbers while `liveWaiting()`; the
  status flap is blank (not NO TRAFFIC); the Now list, Spotted today and the Where to look card say "Finding where you
  are … the planes show once live location has found you."

- 1.89.1 (to-do #102, Dave: "the big main boards should just be about the overhead/airport stuff"): **no game on the
  board** (test/index.html, so the TVs and the PC); the app keeps all of it. Board-only code removed: the `league` page
  (`LEAGUE_ROWS` fields, `leagueLoad`/`renderLeague`, `/game/league` fetch, rail key, icon and tip; `ROTATION_OVERHEAD`
  back to four steps), the Collection view (`cv*`/`cs*` fields, `renderCollection`, `collectionStatic`; `LB_VIEWS` is
  shared, so `buildViewTools` filters "collection" out), the Records view's bingo and trophies (`recordsStatic`,
  `drawTrophy`; the view is "Records", four flaps), Today in numbers' points (header line and the evening's Points today
  row: in review time `stNew` keeps New in the logbook), the Week & month Points flap (`rw_points`; `renderReview` skips
  REVIEW_NUMS without a field) and the achievement pop-ups (`fetchLogbook` calls only `stylesCellRefresh`). Shared code
  checks `COCKPIT_FOR === "tv"`: `logbookSummary` leaves out points and streak, `stylesNote` is empty, `stylesCard`
  offers only unlocked choices (`styleOk`) with no hints or count, and the Styles hint is `HINTS.stylesTv`. The rarity
  tier flap stays (it is about the plane).
- 1.89 (to-do #90, Dave's mockup picks): **the app's Logbook places**: the chips went; `#lbPlaces` is a `.seg
  lbPlaceSeg` bar (the Week · Month · Year style) with All, On the go (the "live" chip of `lbChips()`) and Saved places
  (each part only when it has sightings; no bar with only All). Saved places opens `lbPlaceSheet()` (a card sheet:
  lamp rows with counts, the one picked lit, "Places are saved in Settings → Places."); once one is picked the third
  part shows its name with ⌄. `lbPick(id)` sets `lbPlace` and fetches its numbers. `logbookSummary()` (Counting since
  … · N points) moved from `#lbSum` to a footnote at the bottom of the Logbook (`.sum.lbFoot`), under a place's own
  "N planes seen from X since …" line; `renderGame` puts the same footnote under the Spotters' Club. The board's
  logbook view is unchanged.
- 1.89 (to-do #91, relay 71): **Recent points**: the strip's points (`.gMain`) open `gRecentCard()` (relay 71, else the
  club as before): today's total and planes, each scored plane newest first (`.fl` rows in `.rpList`: newest award's
  time, flight, airline, tier icon, type, rarity, distance, total) with its awards under it, explained by `gWhy()`:
  the first score (rarity +base, New type/airline/aircraft +n; close pass, streak and taper multipliers only when they
  apply), "Close pass · within 4 km" top-ups, "Sky view lock-on · +25%" (the combo's real share), a lowered score as
  "Points corrected". The relay keeps `ga` on each sighting (`_game_award`: `t` ms, `k` first/close/fix/lock, `p`
  points, `d` km or `pct`/`c` for a lock-on; last 8) from `game_note()` and `game_lockon()`; `/game/today`
  (`game_today()`, the profile's own, like `/game/me`) hands today's scored planes (with the fields `fromRelay()` names them from, so they read as in Spotted today) with `base`, `new`, `gk`, `gn` and
  `aw`. Planes scored before relay 71 have no `aw` and show their first score and lock-on without times.

- 1.88.0.1 (to-do #88): **a live position counts only while it is fresh**. On 26 Oct a phone's Chrome loaded in live mode
  with S.lat/S.lon still saved from a trip and asked around there as "live" before (or without) its first fix: far planes
  became live sightings with points, and the relay ran the gap filler for them. Now `liveAt` (set by `liveFix`, 0 after
  `liveHalt`, so never a saved fix) and `liveStale()` (live and no fix for `LIVE_FRESH_MS`, 5 min: the Android app asks
  every minute, browsers get a `getCurrentPosition` after 2 min without a fix as a lying-still phone may not report;
  at motorway speed 5 min is about the game's circle). `placeQs()` adds `&fix=<age s>` (-1: none yet) to live
  position requests. While stale the line under the title (board `drawStatic`, app `updateWhere`) starts "FINDING YOUR
  POSITION …"; a 2 s check calls `liveShow()` (each page its own) when that changes. Planes around the old spot still show.
- 1.88.0.1 (to-do #89): **"@" callsigns**: the sources fill a blank callsign with "@@@@@@@@". `noAt()`/`noAtList()`
  clean the position lists in `getAircraft` and the relay's sightings in `fromRelay`, so such planes show their
  registration, then hex.
- 1.88 (Dave, 26 Oct): **Remarks by style**: `seenLook()` (called at the top of `renderFeatured`, shared with the app)
  sets `fields.seen.style` to amber in the Airport style and plain (white) in the Overhead style, and redraws its
  cells when that changes (the tile cache keys on the style). `vieLines(info)` in the Overhead style returns only
  "DELAY n MIN" for a delay over 30 minutes (no ON TIME, no "DELAY /", no GATE); the Airport style is unchanged. The
  plane card's Remarks follow (they use `remarkLines`). Checked by flows.py's browser checks.
- 1.88: **model pictures** (Dave's Black Hawk, H60, had none: Wikipedia's "Black Hawk" is a disambiguation page, which
  `wikiPage` drops). `modelWiki(names)` (now async, `MODEL_LIKE`) tries `modelTitles` as before; when nothing fits it
  asks Wikipedia's search ("<name> aircraft", cached in `modelSearches`) for each name and tries the results whose
  title holds the name (or the other way round). The callers also pass the source's description (`ac.desc`,
  `fromRelay`'s new `desc`, `typeCard`'s `x.desc`), e.g. "SIKORSKY UH-60 Black Hawk". Checked against Wikipedia on
  26 Oct: Black Hawk → Sikorsky UH-60 Black Hawk, Hercules → Lockheed C-130 Hercules, now with pictures; Super Puma,
  A320, 737-800, A320neo, E195, 787-9, Cessna 172, A350-900, R44 and ATR 72-600 find the same pages as before.
  A "NEW AIRLINE" seen on BLACK71's Status was the word drum passing it (NEW TYPE → NEW AIRLINE → ... on the turn back
  to the mode word every 6 s), not a mark: the relay only marks `^[A-Z]{3}\d` callsigns.
- 1.73.3: `gTotSet` pads to five flaps, blank (no leading zeros).
- 1.87.2.1 (Dave's small fixes, 25 Oct): **radar names** come from `radarInfo(o)`/`radarName(o)` (next to
  `radarLabels`, shared with the app): the cached details or `baseInfo(o.ac)`, so the scope says OS 411 like Nearest
  also before the route lookup is back (it fell back to the callsign). A plane not in `infoCache` whose airline
  `AIRLINES` lacks (EIN) asks `airlineAsk(code)` once per code (`radarAsked`, as the scope draws every frame); the answer
  calls `renderRadarList()`, and `baseInfo` then gives "EI 6AB" and the logo (it was only asked for the featured plane). The app's Nearest puts the type on a line of its
  own under the flight number (`.rv strong span`, block), no longer cut to "A…". **Most seen** needs a count of two:
  Today in numbers' airline says "No airline twice yet" (board `stTop`, app `todayNumbers`), the types
  (`topTypesFlaps`, app `topTypes`) keep only types seen twice ("No type twice yet"), and the period cards
  (`reviewFacts`, app `yearFacts`) and the Logbook's model (`lvModel`, app `lbModel`) leave the fact out; so "1 times"
  can no longer show there. `T("Once")` (the collection card's Caught) got its translation row.
- 1.87.2 (relay 68; Dave's logbook since 9 Oct: 263 of 3,118 airline flights without an airline name, as adsbdb names
  the airline only with a route; Flightradar24's routes lived only in its rolling cache). **Airline names:** the relay
  keeps Virtual Radar Server's standing data (`AIRLINES_CSV`, CC0; BOM, columns Code,Name,ICAO,IATA,...) as
  `data/airlines.json` (`{"v":1,"fetched","codes":{ICAO:[name, IATA]}}`); `_airlines_worker` loads it at start,
  downloads when it is over `AIRLINES_EVERY_S` (a week) old or missing, keeps the old copy when a download fails or
  holds under 100 airlines, and runs without it. `airline_fields(cs)` (callsigns `^[A-Z]{3}\d`) fills
  `airlineName`/`airlineIata`/`airlineIcao` in `_enricher` where the route lookup brought none (also keys a route left
  empty), and the logbook's `airlines[code]` name and IATA code. Once per profile (`airlinesV: 1` in the logbook,
  `_backfill_airlines`, every profile's spot via `_all_profile_spots`) the saved days get the missing names
  (`_airline_fill`: only those three keys, only where `airlineName` is empty), written by the saver: `Spot.days`
  (`day_entries`, `day_changed`) holds older days changed after the fact, and `_days_of` reads through it.
  `/airlines?c=EIN,SXS` (up to 40 codes, profiles only) answers `{code: [IATA, name] | null}`; the board's
  `airlineAsk(code)` (relay ≥ 68, batched 300 ms) adds the answer to `AIRLINES`, and `enrich()` sets the plane's
  airline and flight number ("EI 6AB") from it when the route lookup brought none. `fromRelay()` makes the flight
  number from the relay's `airlineIata` when `AIRLINES` lacks the code. About credits "airline names from Virtual
  Radar Server". Routes from the standing data are not used (they matched Flightradar24's real routes less often than
  ours on 25 Oct; to re-check in early November). **Flightradar24 kept:** `fr24_keep(key, info)` (called by
  `_fr24_worker` for every answer, and once at start by `_fr24_keep_cached` for the cache) writes `flightIata`,
  `from`/`to` (over adsbdb's) and `divertedTo` into the sightings of that aircraft and callsign that are the same flight
  by fr24_info's rules (`_fr24_same_flight`: same day or within `FR24_REUSE_S`; the answer's board day and the one
  `FR24_REUSE_S` before), marks them `routeSrc: "fr24"` (only for profiles with `fr24` on, like `fr24_overlay`), runs `note_records` and saves (`day_changed`, "book"). The
  airline and `fr24` (the overlay's flag, which `marketedBy` follows) are left alone; `_enricher` no longer lays
  adsbdb's route over a `routeSrc: "fr24"` one. No extra lookups. **Also relay 68:** `SOURCES` starts with adsb.fi;
  adsb.lol (500 a UTC day) is kept in reserve. `install.sh` saves `data/` as `/root/data-before-relay<new N>.tgz`
  before replacing serve.py and keeps the newest 3. `Handler.handle`/`finish` drop BrokenPipe/ConnectionReset (a
  client gone before its answer; ~24 tracebacks in 3 days, from `profile_post`), one line under `--verbose`.
  Test: fakesrc.py serves `/airlines.csv` (5 real rows, 120 made-up) and EIN6AB (no route; the board's table has no
  EIN); run_test_relay.py starts the Test profile with yesterday's EIN1XY (no name) and AUA9 (named), and EIN1XY's
  answer in `fr24.json`; flows.py checks the names, the backfill, the CSV and the written answers.
- 1.87.1 (the gap filler on the real Flightradar24, the first evening: it filled in RYR4328 landing at 4,400 ft, but two
  short looks cost 112 credits, not the 5–8 the old estimate implied): relay 67 trims it. **One record per profile**
  (`fill_want` finds it by `pid` and moves it to each asking screen; more than `FILL_KM` away it starts afresh, asking
  at once). Relay 66 kept one per place within 3 km, and a phone finding itself (from where the app was last opened to
  where it is) made three in 20 s, each paying for the same plane; the app and Chrome on one phone could do the same.
  `fill_merge(body, rec, lat, lon, km)` only adds planes inside the asking screen's circle, for a profile with screens
  in two places. **Not from the background:** a page that is hidden asks for positions with `bg=1` (`getAircraft`; it
  polls every 60 s then) and the handler skips `fill_want` for it, so the record stops asking 30 s after the last look.
  **Cheaper answers:** `FILL_FT` 10,000 (adsb.fi hears the island's planes from about 9,000 ft, and each plane in an
  answer costs 6 credits even when the free answer has it), `FILL_EVERY_S` 30, `FILL_FAST_S` 15, slow after 20 answers
  that held nothing new (still ten minutes). Measured on the test relay: asks 15 s apart while TST353 is within 10 km,
  30 s after. The app: `#snapTag` (Last known board · not live yet) at `z-index:55`, under the opening (`#splash`, 60),
  so after Refresh now it no longer shows over the logo; it shows on the board when the data is still not live once
  the opening has gone.
- 1.87 (Dave on an island: two Sky Express ATRs, SEH353 and SEH8TR, took off over him and the app showed nothing):
  adsb.fi, the only free source still answering the relay, first had them at about 9,000 ft and 22 km out (its map's
  trace); airplanes.live's map had them from 1,500 ft right overhead, but it answers the relay 403 (contributors only,
  Dave was told); adsb.lol now allows 500 requests a UTC day per address (`x-ratelimit-limit: 500, 4;w=1, 60;w=60,
  500;w=86400`) and the relay had used them up. Relay 66, the Flightradar24 gap filler (`fill_for`, `fill_want`,
  `fill_merge`, `_fill_ask`, `_fill_worker`, `FILL_*`): for screens of the owner's profile (`fill_for`: `HOME_OWNER`,
  Flightradar24 on, under `FILL_SHARE` 0.8 of `fr24_limit`, not `fr24_paced(1)`) more than `FILL_AWAY_KM` 30 km from
  `fill_home()` (the relay's --lat/--lon), the /aircraft handler keeps a record per place (one within 3 km moves along)
  and merges the planes of its last answer (under 60 s old) that the free answer lacks: by hex, aged to the answer's
  `now` as `seen_pos`, `src: "fr24"`, `t`/`r` from `fr24_info`. The body for the sightings holds a new plane back for up
  to 20 s until its flight summary is in (the worker asks `fr24_want(..., 0)` when it first sees it), so its logbook
  entry has its type. The request: `/live/flight-positions/light`, bounds ±`FILL_KM` 20 km, `altitude_ranges=100-15000`,
  `data_sources=ADSB,MLAT,UAT`, `limit=10`; 6 credits a plane, 1 for none, counted by `fr24_spent` (the lookups use it
  too) as "<name> · Gap filler". Every 20 s, `FILL_FAST_S` 10 s while a plane it filled in is within `GAME_KM`,
  `FILL_SLOW_S` 300 s once 30 answers in a row with planes held nothing new (`useless`); a place nobody asked about for
  two minutes is dropped. `fr24_slot()` paces the lookups and the gap filler together (6.5 s apart; `pause=60` after a
  429). `_record` marks such sightings `src: "fr24"`; they are kept like the rest (Dave: "We're not sharing this data
  externally so we can keep it longer", although Flightradar24's storage rule says 30 days). `/status` `fr24.fill`
  (places, filled, filledToday); `X-Relay-Fill: n` on /aircraft, and the board's connection log says "Flightradar24
  filled in a plane the free sources can't hear" (`lastFill`). `apiLookup` fills `info.type`/`info.reg` from the
  answer's `type`/`reg` when the free databases had none (adsbdb doesn't know Sky Express's ATRs). Sources:
  `rest_for(..., reset)` rests a source until `X-RateLimit-Reset` when a 429 says `X-RateLimit-Remaining: 0` (seconds
  or a time; 60 s to a day). Test: fakesrc.py's `away()` (more than 30 km from the test point the source has only
  TST477 at 8,000 ft; Flightradar24 also TST353, climbing out over the place every 6 minutes); checked as David
  (owner-device) at 47.21, 15.37 with Live location: filled in, not doubled, every 10 s when close, ATR 72-600 and
  TS-TST on the board, the sighting with its type; the Test profile and home get nothing.
- 1.86 (Sky view on a real sky, Dave on an island: the sun's ring 24° beside the sun from the start, and sliding
  sideways as the phone tilted, back when held still): **the gyroscope turns the labels.** Android (Chrome, WebView)
  sends `deviceorientationabsolute` (rotation vector: gyro, gravity and compass fused) and, with a gyroscope,
  `deviceorientation` with `absolute` false (game rotation vector: gyro and gravity, its zero anywhere); `arOpen` listens
  to both. `arOrient` keeps the compass's matrix (`arAbsR`) and, while the gyroscope's reading comes (`arRelT` within
  400 ms), turns the labels with that one plus `arGap`, the turn about the vertical between the two (`arYaw(A, B)` of
  A·Bᵀ). `arGapStep` takes the first gap at once, then follows the compass only while the phone is held still
  (`AR_STILL_MS` 1.5 s after `arGyroStep` last saw it turn faster than 6°/s, smoothed; then τ `AR_GAP_TAU` 2 s, 4 s when
  an iPhone says its compass is poor), and not at all once lined up. iPhones go the same way (gyro alpha + the compass
  heading's gap). Without the gyroscope's reading, the compass's turns the labels as before. `arGyroStep` also carries
  north over a jump no hand makes (over 20° at over 1000°/s: the gyroscope's zero reset). `arTurn` is the old 1€-like
  smoothing; `arLastQ` the last orientation fed. **Lined up, north is held** (`arHold`, `arHeldAt`): an AUTO lock or a
  drag stops the compass's part until ⟲ (which also drops `arGap`, so the compass's north comes back at once) or Sky view
  closes. **The compass check** also fires when the compass swings 12° or more against the gyroscope within 4 s (not
  in a flick over 60°/s; not once lined up). **AUTO finds the sun** (`arSunFind`, every AUTO step while it is 1° to 75°
  up): the whole video at 160 samples on its long side; with something burnt out (≥ 245), the patches within 10 of the
  brightest (8-connected) are filled out, each placed in the sky with `arUnproject` (the screen back to azimuth and
  height, `arProject`'s inverse); patches more than 6° off the sun's height are left out (the tilt is right even when
  the compass isn't: the glint on the sea, lamps, walls); the largest must be 3 times the next, not cut by the
  picture's edge, 0.7° to 20° across, at least 45 % of its box and at most 1.8 times as long as wide, and at most 45° off
  the sun's azimuth. A find is the offset that puts the sun's ring on it (`hex` "sun"); 4 finds in 2.5 s, 80 % within
  1.2°, make a lock, and the sun then decides alone (`arAutoLock.sun`). The chip says "lined up · sun", gold corners
  (`arBrackets(g, x, y, r, arm)`, 32/10) frame the ring, and until lined up the hint asks to point the phone near the
  sun. Tested headless with a synthetic camera (the sun's glare, a glint on the sea, a bright cloud, a lens flare,
  drawn where they really are) and synthetic sensors (a compass 26° off, plus 0.5° per degree of tilt, 12° with heading
  and a swing while moving that settles in 1.5 s): tilting 20° up, the ring stayed 25° off the sun (main: slid from 25
  to 45°); AUTO lined up on the sun within about a second, 0.05° off after 4 s; turned 90° away and 30° up with the
  compass swinging up to 100° off, the labels stayed within 1° (0.0° once still); pointed 120° away, nothing locked.
- 1.85 (Dave's pick A of the quiet-sky mockups, "anywhere in view"; the where-to-look options were declined): with no
  alert, over, soon or PASSED hold, `process()` puts the plane with the smallest finite `o.tin` above 180 s (kind "by",
  any distance in the 46 km answer; the one on top stays while it is still due) on top as mode "next" (status NEXT, a
  plain word in `REMARKS`, `MODE_REMARK.next`); Position counts down `o.tin`; no ding until it turns soon (`feat.dinged`);
  `noteFeatured` leaves NEXT out of Recent flights. With none, NO TRAFFIC: the old fallback (the nearest closing plane
  in the radius kept 60 s, else the nearest up to 46 km) is gone. Legend row NEXT.
- 1.84 (the tracking review, Dave's answers of 24 Oct; the review is a Claude Doc, "Fallblatt Plane Tracking Review"):
  OVERHEAD is within `overKm()` (Settings → Overhead within, now 1 km by default; `overRule` moves a saved 3 to 1 once)
  at any height, or `OVER_DEG` (45°) or more up: `overR(alt)` is that circle (as wide as the plane flies high, at most the
  radius), `overIn(o)` the seconds until a plane's straight line takes it in (0 inside, Infinity when it won't),
  `overEntry(e)` the same for a sighting (minDist against altAtMin) in the lists, Today in numbers and the Spotted
  filter. `process()` gives every plane `o.tin` and the kind from it (APPROACHING = in within 180 s, sorted and counted
  down by `tin`), and judges positions moved on to now: `ageOf(ac, list)` (seen_pos + the relay's answer age against its
  `now`, at most 6 s, + the time since it came; `list.recvAt`) and `movedOn(ac, s)`, straight on, at most 60 s;
  `o.ac` stays as reported (Sky view and Where to look move it on themselves). Every 2 s a timer under `poll()` calls
  `process(lastList, true)`: the same update with the planes moved further on (no glitch check, rates, radar track;
  not in the Airport style, while hidden or when the update is 30 s old). The ding (`setFeat`, board and app) rings
  once per plane on top as it becomes over or soon (`feat.dinged`), not for every new plane on top. Favourites take
  the board (`alertOn`) and chime (`checkChimes`) only when over or soon; special planes and emergencies as before.
  Relay 65: `/sightings?deg=45` makes `day_stats` count overhead by the same rule. Checked with a scripted traffic
  harness (the test board's /aircraft answers replaced in the browser, five scenarios at once, before and after).
- 1.83.3 (Dave: a plane tapped on the radar should bring up the same panel and animations as elsewhere): a tap on
  the scope or a Nearest row (`radarPlaneCard`) rings the plane (`radar.sel`) and opens `planeCard(o)`, the shared
  sheet (`#cardBox`, 1.78), instead of the inline `#rvCard` under the scope (gone, with `renderRadarCard`, `rcardSig`
  and the `.rcX`/`.rcHead`/`.rcRoute`/`.rcPic` styles). Once a second on the radar tab the sheet's `[data-dyn]` numbers
  follow the plane, and the ring clears once the card is closed (`radarSelOpen`: `cardOpenNow()` and `planeShown`).
  The app's `planeAgain` re-opens the radar's card with a model picture found late. A tap on empty scope no longer
  deselects (the sheet's backdrop closes it); a double tap still zooms.
- 1.83.2 (Dave: a cockpit push button for the radar's reset, on the Range km cell; his pick Y3 of yellow, realistic
  versions): `#rvReset` moved from `#scope`'s corner (`.arIb`) into the Radar plate's first cell (`.inst.rvRange`, a row
  under its label) beside `#rvWheel`, as a `.litKey`: a square bezel and dark lens (head.html) whose ⟲ glows yellow while
  enabled; disabled (at the usual range, `buildRadarLegend` as before) it stays dark. Pressing it plays `ctlSound.press()`,
  then `radarZoomTo(0)` rolls the wheel back with its own sound.
- 1.83.1 (Dave: keep the title as it was, but level with the screws, with what follows moving up too, and the lines
  ending the same distance from the screws everywhere): every plate keeps its top and side padding in `--pt` and `--px`
  (the board's `.plate`; the app's `#cockpit .plate`, `#aboutBox .plate` and `.secPlate`), and `.plate>h3` works its
  margins out from them: the title's middle at the top screws' (8 + 9/2) and its lines ending 6 short of the screws
  (8 + 9 + 6, all times `--k`), so what follows moves up with it (8 px on the phone's plates, 4 on the radar's and the
  board's). The app's own `#cockpit .plate h3` and `.secPlate>h3` margins are gone; a plate with a padding of its own
  sets `--pt` and `--px` with it.
- 1.83 (Dave: each header category on a panel like Settings' or the Radar plate; he confirmed the look and "the tops
  too"): `secPlate(title, body, cls)` wraps a section in Settings' `.plate` (`--cols:1`, four screws, the title engraved
  between two lines; `.secPlate` sets its padding). The Logbook's period card (`perCard`: the switch and ◀ ▶ in
  `.perHead`), Categories, Aircraft types, Airlines and Most seen aircraft; the club's Your level (`gHero`), League
  (`lgPlate`, with Show me in the league), Your catch, Sets or Your hangar (`hgPlate`, shelves bleeding to the plate's
  edges), Records, This week's bingo and Trophies; in the markup the Logbook's totals and Most seen model (`#lbTop`,
  "Totals"), Spotted today's flaps and highlights (`#todayTop`, "Today in numbers") and the radar's Nearest.
- 1.82.2 (Dave's reports of 23 Oct): the radar's reset (his pick B, but faded at the usual range rather than gone):
  `#rvReset` is Sky view's `.arIb` round button in `#scope`'s corner, disabled (faded, `.rvReset:disabled`) while
  `radarZoom` is 0 (`buildRadarLegend`); `radarZoomTo(0)` sets `radarZoomSet(0)`, the usual range (`radarBase`, from the
  radius) and the middle. A tapped plane's card (`#rvCard`, with `#rvHint`) sits right under the scope again, above the
  plate (1.69 had put the plate between them, so on a phone the card opened off the screen), and is scrolled into view.
  The Now board's Points field (`fields.pts`, `gPtsRender`, `gPoints`, `gPtsWhy`, 1.73.1) is gone; the Remarks are 19
  flaps again. The radar's − and + (the app's wheel) step through `radarSteps()`: every 5 km from `radarBase` down to 5, then
  `RADAR_CLOSEST` 2.5 km (was `RADAR_ZOOMS` 10, 5, 2.5). The hangar names and looks up models by the app's own type names
  (`hgNames`: `TYPES[code]`, then the relay's, which are "AIRBUS A-320neo" and found nothing on Wikipedia; `typeLabel` for
  the card). The Spotters' Club has no Styles button (`#gStyles`); Settings → Styles stays.
- 1.82.1 (Dave: the shared pictures should show whose they are): `spottedBy()` (board, next to `shareCard`) is "Spotted by"
  and the profile's first name (`GUEST.name`), or nothing. A sighting's picture (`shareCanvas`, 40 px taller) has it at
  the foot, level with the FALLBLATT mark; the year, week and month (`periodPicture`) under FALLBLATT by the logo; Sky
  view's snapshot (`arSnap`) on the band's right, or after the date when the place's name leaves no room.
- 1.82.0.1 (Dave: "Refresh now" didn't refresh at once, another box showed first): the tap's pointerdown went to
  `nvInput`, which stopped the countdown and redrew the notice shorter before the click reloaded, and the old page then
  stayed until the new one came over the tunnel. `nvInput` now ignores presses on the notice; `nvReload` (the button,
  Enter, the countdown, the half-hour refresh, the board's New version button) sets `NV.going` and calls the app's
  `nvGoing`: the notice goes, the opening (`SPLASH_HTML`, kept by the splash script) covers the page, `od.nvGo` in
  sessionStorage makes the new page show it already in place (`#splash.still`: no intro, no sound, even within the
  minute) until `splashGo`; a page still there after 20 s drops the cover. The board says Refreshing … in the notice.
  `sw.js` raced the 3 s against the whole page being downloaded and kept, so a slow line got the old copy marked
  offline: it races the relay's answer now, and keeps the copy in `waitUntil` from a clone taken first.
- 1.82 (Dave's to-do 10 and 11, his picks A and A): the board's Today in numbers has no `stHour`; the four counters
  spread across (gaps of 7 steps) and `stFirst` shows the day's top three types (`topTypesFlaps`, "A320 12 B738 7 E195
  5", by type code from the day's list), still Rarest today in the evening review. The Records & trophies page draws
  each ladder's cup in its rank's metal (`drawTrophy(g, x, y, s, on, col)`: outlined, filled once won) with an outlined
  metal tag after the name; `TROPHY_MEDALS` and `MEDAL_COL` moved into the board's trophy block, shared with the app
  (its medal moment and player card take `--m` from `MEDAL_COL`).
- 1.81 / relay 64 (Dave's to-do list of 23 Oct, the relay 63 part; his picks 3A, 4 a mix of C and B, 5 B with A's
  nudge, 6A): **Where it was spotted** (3): `lbfPlaces(g)` names a search row's `places` (a saved place by `lbPlaceName`,
  on the go its town and area, a guessed one its country) as a pin line (`.lbfPin`, `PIN`) and Seen from in
  `foundCard`; the hint names a place with relay 63. Relay 64: `where_of` gives a sighting without `at` (from before
  relay 63, its place only guessed from the day's planes, which on Santorini fell across the caldera) only its
  country, Dave's choice; the search's place key carries the country. `game3_json` sends the week's best plane as
  `weekBest`: as `best` it had replaced `game_json`'s best day since relay 59, so the board's Today in numbers said
  "best NaN". **Your hangar** (4): with `/game/hangar`
  (`hangarLoad`, five minutes) the club's Sets list becomes `hangarHtml`: a `.hgShelf` per set (`.hgRow` scrolls
  sideways, snapping; the page swipe leaves it alone; its scroll is kept across `renderGame`'s redraws), a `.hgCard` per
  type caught (relay 64's `thumb`/`photo` of the first one, else `modelPicNow`, asked for as cards come into view by an
  IntersectionObserver in `hgWire`; a photo that fails goes in `hgBad`), the missing ones face down (`.back`), and Other
  types; `hangarCard` (Caught, First, Aircraft, Flight, Airline, About this model → `typeCard`; a missing one opens
  `typeCard`). **Medal moments** (5): `achNext` (board) first asks `achSpecial(a, dry)` (app) whether a queued
  achievement is a ladder rank: then `#medalMo` swings down (`.mmRib`, Roman numerals, `mmSwing`) with `fanfare()`, and
  fades after 5 s; singles and the board keep the card. `medalNudge(g0)` toasts once per rank when the next is within 2
  or 2 % (`NUDGE_UNIT`, kept in `ACH_KEY + ".nudge"`). **Player cards** (6): league rows with an `id` (`data-player`;
  `data-pl` is a place link elsewhere) open `playerCard`: `/game/player`, the club's bar and tiles (`.plCard`), medals
  by metal (`.plMedal.m0`–`m4`) and one-offs, rarest catch and this week's best as trophy rows.
- 1.80 (Dave's to-do list of 23 Oct, the app's quick ones; his picks 13B, 14A, 7A, 8A, 1A): **Log** (13): `dlog(level,
  msg, kind)` keeps 400 lines, each with a kind for the filters ("net", "sky" or ""; guessed by `LOG_NET` and a "Sky view"
  / "Where to look" start when not given); `#t-log` is a page like About (`logShow`, `logHide`, `logRender`, `logCopy`:
  the clipboard on https, else a hidden textarea and `execCommand`), opened by Log in About and in the connection card,
  with a `.seg.logSeg` switch (All, Problems, Sky view, Network). Sky view now logs opening and closing, refused
  sensors, no compass, AUTO lining up (`arAutoStep`) and each lock-on's answer. `body.aboutOpen main{z-index:6}`: main's
  stacking (z-index 1, under the header's 5) had always kept About's own title and × under the top bar. **Where to
  look** (14): with a plane on top but no direction (`lookWhy`), `lookWhyDraw` keeps the card (`.look.why`): the flight
  and the reason in the big line, dimmed, a sentence under it, the tape grey, Sky view's button dimmed. **Rarity star**
  (7): Sky view's chip is "★ n" in `TIER_COL` (n: the sighting's `gp` once scored, else `G_BASE` × the close-pass factor;
  a special plane's chip on the gold label of the plane on top stays dark), ✓ and NO PTS as before. **Week and month**
  (8): the period card's Share (`#pShare`, `sharePeriod`) and the year's use one `periodPicture` (title, dates, six
  numbers, three facts; singular words from `PIC_ONE`). **Snapshot** (1): `#arShut` in `.arBot` (with the hint) shows
  while a scanned plane (`locked`, ✓) is in the picture and 5 s after; `arSnap` draws the video as it covers the
  screen, the label canvas and a band (the mark, "Sky over" the place, date, time, planes). All three pictures, and a
  sighting's (`shareCard`), open in `picCard` (the board's): Share (the share sheet or `OverheadAndroid.shareImage`) and
  Save picture; the year's Share used to call the share sheet directly, which the Android app lacks.
- Relay 63 (Dave's to-do list of 23 Oct: 3, 4, 6; the app's side follows his picks): a new sighting on the go keeps
  the phone's place to about a kilometre (`at`); `where_name` names each 0.02° cell once (`_where_worker`, Nominatim
  at zoom 13 in English, `geo_where`: the town, the area round it, the country; `data/where.json`). Older sightings on
  the go stand in with their day's planes grouped within 30 km (`where_estimates`). `search_json` matches the place
  too (a saved place's key, "home", or the town, area or country; accents folded, `_fold`) and each row carries
  `places` (`{k, n, a, c}`, newest first, at most four). `/game/hangar` (`hangar_json`): the game's types with the
  first aircraft of each (reg, hex, flight, for a photo) and its tier, and the sets with all their types.
  `/game/player?id=` (`player_json`): a league player's card (level, week and all time, trophies won, tiers, counts,
  the rarest type, the week's best plane, streak, lock-ons); league rows carry `id` (`_league_id`, salted afresh at
  every start), never places. The test relay answers Nominatim from the fake source (`/nominatim/reverse`).
- Push to main (Dave's to-do 12, 23 Oct 2026): the main board goes from 1.37 to the test board's 1.79.2, with `i18n.js` and
  `sounds.js` next to it for the first time; `push_main.py` points the main copy at `fonts/fonts.css` (the test board's
  `../fonts/` works through the relay, but on GitHub Pages' own address it leaves the project).
- 1.79.2 (Dave's picks: medals without coloured dots, and the switch): `trophiesHtml` has a `.seg.trSeg` switch
  (`gTrTab`: near, won, todo; kept across redraws, wired by `trWire` on the club page and the Logbook's Records) in
  place of the `trFold` folds and `gTrOpen`. Closest is the three ladders nearest their next rank; Still to win is
  every ladder by progress (bar, as Closest) then the one-offs; Won is each ladder's highest rank won, with "Next: …"
  when more are left, then the one-offs. A ladder row's rank is a medal by its index (`TROPHY_MEDALS`, bronze to
  diamond; `li.medal.m0`–`m4` set `--m`, darker under daylight): the cup's outline in that metal, filled once won,
  and a `.metal` tag before the dots, which keep their gold. Names are no longer dimmed (each list is all won or all
  to win). Dave had asked why High scorer sat under Won with two ranks left: each rank is a trophy of its own (48).
- 1.79.1 / relay 62: `geo_reverse` asks Nominatim at zoom 13 (villages and suburbs; 12 stopped at the area above a
  village) and `_geo_name` passes over names that are an administrative area (`_GEO_ADMIN`: Greece's municipal units
  come as "city", "Ia Municipal Unit" over the village Oia), using them cleaned (`_geo_admin_clean`, "Ia") only when
  no place is named. Checked on Nominatim's answers: Oia → Oia, the Fira rim → Firostefani, central Vienna → Vienna.
- 1.79 (Dave's picks A, B, B from the club options): `renderGame` starts with one `.gHero` card (level, bar,
  `into / need`, the live-off note inside, `.gTiles` with today's points, `g.rank` and the streak, the `#gHow` button);
  `gHowCard` holds the rules (tier values with their icons, the extras, today's `gTaper`, the Sky view bonus); the
  league's heading carries its switch (`.gHead`). `collectionHtml` says "Your catch" and "Sets" without the points line
  (the board's view name and its Sets label too; the Completionist trophy says "Every set complete"). `trophiesHtml`:
  the three ladders closest to their next tier (`.trNear`, bright, the requirement inline, pips and bar), then
  `<details class="trFold">` for Won and Still to win, one line each, their state kept in `gTrOpen` across redraws.
  The page went from about 3,400 to 2,200 px.
- 1.78.2: the app's Spotted today facts (`todayNumbers`) drop Busiest hour and First of the day and gain Most seen
  types (`topTypes`: the day's list counted by type, the top three as "A320 ×12").
- 1.78.1: the score strip follows `S.live` at once (`gStripLive`, checked every 300 ms; a change redraws it and forces
  `gRefresh`): it waited for the next points, up to a minute (Dave: 30 s after live went off). Remarks "FIRST: TYPE"
  etc. (keys in i18n.js too; the translations had the colon already). Cards: a finger going up where the card can't
  scroll (short, or at its end) pulls it against a spring (`d·0.5/(1 − d/220)`, at most ~110 px) and it springs back;
  both ways in one movement; a finger beside the card is swallowed; `overscroll-behavior: contain` keeps a scrolling
  card's scroll to itself. Where to look logs why a plane on top has no direction (`lookWhy`, once a plane: no
  position, no height, too far, or an error caught).
- 1.78: the app's cards are sheets like Sky view's card. The board's `cardOpen`/`cardClose` call the app's
  `cardSheetPre`/`cardSheetPost`/`cardSheetClose` (typeof-guarded, in lint's OPTIONAL; the TV boards keep their cards):
  `#cardBox.in` slides `.cardIn` up (0.38 s, Sky view's spring) and fades the dark in; `.closing` slides it down (0.26 s)
  and hides it after; `cardOpenNow` is false while closing. A card replaced while open glides from its old height to the
  new one and fades its content in (`.swap`); the same card again does nothing. Touch: down from the top of an
  unscrolled card drags it (`.drag`, above the start a sixth of the way), let go past 90 px or flicked (0.5 px/ms) it
  closes, else springs back; the click ending a drag is swallowed. Floating 10 px from the sides and the bottom, with a
  grip (`.cardIn::before`).
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

- 1.94 (to-do #113): the Logbook's aircraft card (`foundCard`, now async: a loading card while Planespotters' or the
  model's photo comes, at most 2.5 s, a later photo joins) and the hangar's (`hangarCard`: Caught, First, Aircraft) in
  the board's `infoCard`; the search row brings the last route as the band, `planeTiles` and `planeFunFacts` (relay 74
  adds the closest pass's height, the sighting before the latest, the hex, owner and country). `cardSheetGrow(ci, h0)`:
  a card growing while open (More info) goes from its old height to the new one (as `cardSheetPost`); `lint.py`'s
  OPTIONAL has it. The info cards' CSS is the board's (`#cardBox .cInfo …`, copied by the build); `.cDet span[data-dyn]`
  undoes head.html's `.cDet span` label look for the live numbers.
- 1.93.1.1 (to-do #112): `planeAgain` redraws any plane card `planeCard` opened (Now, the airport lists, the radar)
  while it shows (`planeTok === cardTok`), not only the radar's, and a plane on the radar with where it is now; the
  hangar asks for model pictures with the type's code (`hgWire`, `modelPicNow(names, code)`), and `hangarCard(code,
  again)` asks for its model's picture and redraws with it (`again`: no click sound).
- 1.93 (to-do #95): Now's screen takes `planePic` in `renderAircraftInfo` (none from Planespotters on the runway
  screen: `rwyE()`, which `paintRwy` uses too), with `#photoLink` (`a.plink` over the whole screen, an href for
  Planespotters) and `#photoCr` (`picCreditHtml`); `.screen .mtag` is gone. Sky view: the whole card's photo is
  `picHtml`'s (the credit at the top, `.arFullL .cSkyPic .cCr`, clear of `.cOv`); the small card's thumbnail
  (`arPeekHtml`) has no room for a credit or a link, so it takes `planePic(..., true)` (adsbdb's or the model's).
- 1.91 (to-do #104): **the Logbook and Spotters' Club tabs stay at the top**: `.lbTabs` is sticky at `top: var(--topH)`
  under the header, with `#setJump`'s metal and shadow (negative margins and padding to the screen's edges; the line
  under the tabs is an `::after`, in from the edges as before). On `#t-logbook` the tabs are now a child of the section,
  no longer of `.lcol`: sticky only holds within its parent, and `.lcol` ends above the lists. A switch (`showTab`)
  still scrolls to the top, so the other page starts under the tabs.
- 1.91 (to-do #105, Dave's pick C at 14 px): **the dropdown arrow**: `DD` (next to `PIN`), a chevron in `currentColor`
  inside a grey ring (#4a4c52), `.dd`, 14 px. The place bar's Saved places part is the name in `.ddL` (it keeps the
  ellipsis) and `DD` (always whole), with `aria-haspopup="dialog"`; Categories' `.chev` holds `DD`, and `.catTap.open`
  turns it up and makes the ring amber (they were "⌄" and "⌃"). The Favourites & hidden list picker (`favManager`'s
  `<select>`) draws the same as a background picture, `appearance: none`, in the board's `#cardBox .favAdd select,
  .cardish .favAdd select` rule (scaled by `--ck` on the TVs), which the app build copies with the Settings CSS.
- 1.91 (to-do #103, the app's part): the app's Logbook lost Newest aircraft in 1.75.1; `renderLogbook`'s signature no
  longer carries `regsRecent`.
- 1.88 (Dave's picks 11 A and 13 A, 26 Oct): **Settings jump bar**: `#setJump` (sticky at `top: var(--topH)`, which a
  ResizeObserver on `#top` keeps at the header's height, score strip included) holds `.seg.jumpSeg`, added to the
  shared segmented-filter rules (flex:none buttons, so it scrolls sideways). `jumpBuild()` (after `showTab("settings")`
  and `renderFavBox`) lists the visible plates by `data-pid` (`plateHtml` adds it; the favourites plate is "favs"),
  named from `PLATES`/`VIEW_PLATES` (`jumpName`, Favourites & hidden as Favourites). `jumpGo(id)` scrolls the plate to
  just under the header and the bar; `jumpSpy()` (window scroll, rAF) lights the last plate whose top passed that line,
  the last plate at the page end; a tapped name stays lit (`jumpHold`) until a touch, wheel or key (a plate near the end
  can't reach the top). `jumpLight` centres the lit name in the bar. **Relay plate**: `#relayPlate` at the top of
  `aboutOpen()`, hidden until `relayLoad()` gets `/relayinfo` (relay 69+, only when `GUEST.owner`; every 30 s while
  About is open); `relayPlate(d)` draws `.ranks.cats` lamp rows with 6-px bars under the Legend's amber `.lgbox h3`
  headings. Backup: amber when missing or `late`, red when not ok.

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

- Relay 74 (1.94, to-do #113): **`/facts?model=<Wikipedia page>|airline=<ICAO>|airport=<IATA>`** (profiles only,
  `allow("facts:"…, 2, 20)`, `Cache-Control: private, max-age=3600`; 503 with Retry-After 300 when Wikimedia can't be
  asked and nothing older is kept) → `facts_json(kind, key)`: one lookup per page (`_facts_busy`: a second screen waits
  for the first), kept `FACTS_KEEP` (30 days) in `data/facts.json` (`_facts_cache`, `_dirty` "facts", the saver; 4,000
  at most), a failure `FACTS_FAIL` (15 min, the old answer meanwhile). `_wm_get` asks Wikimedia with `WM_AGENT` (a name
  and a contact, as they ask) at most five a second. `model_facts(title)`: one request (`_wiki_page`: wikitext,
  introduction and disambiguation flag) → the infobox (`_infobox`: every "Infobox aircraft…" template of the
  introduction; `_wt_templates`, `_wt_split`, `_wt_params`, `_wt_text` (refs, comments, notes and markup off; dates,
  "as of", lists, convert, `#expr` sums (+ and − only) as text; links as their words), `_wt_link`, `_num`, `_date`):
  first flight, introduction, status, main and more users, number built (with "as of" and "+"), production years,
  developed from (name and page); the specs template's capacity (`_seats`: the most passengers, words as numbers,
  units and classes off), length, span, height, rotor, range (km, nmi, mi), speed and engines, or without it the
  Specifications table's first column (`_spec_rows`, `_qty`: airliners). `airline_facts(icao)`: Wikidata by P230
  (`_wd_find`: haswbstatement search; `_wd_pick`: the one still going, with an English page, most statements; a
  dissolved one only (AZA) gives none) → inception, hubs (P113 with their IATA codes), alliance (P114, the three
  alliances only: TUI fly's P114 is TUI Travel), headquarters, owners (P127 with P1107 shares, current only), employees,
  photo (P18 → `_commons`, Special:FilePath 640 px) and the English page's infobox (fleet size, destinations, founded,
  commenced, num employees, callsign, hubs/alliance/parent as fallbacks). `airport_facts(iata)`: Wikidata by P238 →
  passengers (P3872, the latest year), elevation (P2044, feet to metres), opened (P1619, else P571), runways (P529),
  operator, city and country (labels), position, photo, and the page's introduction. **`/logbook/spotted?airline=|type=|
  airport=`** (`allow("spotted:"…, 2, 10)`) → `spotted_json(spot, part, key)`: sightings, planes (different airframes,
  by registration, else hex), first, last over every saved day (`_spotted_summary` per day, kept in `_spotted_days`
  like `_place_days`; today's fresh); an airport counts flights with it as `from` or `to`. `search_json`'s rows add
  `hex`, `prev` (the sighting before the latest), `altAtMin` (the closest pass's height), `route` (the newest one's
  from/to), `nOther` (how many different flights or aircraft), `owner`, `ownerCountry`. Coverage (27 Oct, real
  Wikipedia/Wikidata): Dave's 122 logbook types (the pages the board's lookup found, 121 of 122): first flight 97 %,
  in service 71 %, built 97 %, production years 95 %, main user 59 %, developed from 53 %, seats 83 %, length 93 %,
  wingspan 89 %, range 89 %, engines 79 %; the app's 85 AIRLINES codes: page 96 % (none for AZA and LDM, whose
  companies no longer fly, and HNA, which isn't Hainan's code), photo 95 %, founded 96 %, first flight 66 %, hubs 92 %,
  alliance 44 %, headquarters 95 %, owners 82 %, fleet 95 %, destinations 91 %, employees 69 %; 50 common airports:
  passengers 98 %, elevation, opened and runways 100 %, photo 98 %, operator 70 %. Tests: fakes in
  fakesrc.py (`WIKI`, `WIKIDATA`, `/wiki/w/api.php`, `/wikidata/w/api.php`, `/commons/`, `/wm/asked`), checks in flows.py,
  `run_test_relay.py --live-facts` for the real ones.
- Relay 73 (1.93, to-do #95): `/planephoto?reg=&hex=` (profiles only, `allow("pphoto:"…, 2, 30)`, `Cache-Control:
  no-store`; 503 with Retry-After 120 when Planespotters.net can't be asked) → `plane_photo(reg, hex)`: `_ps_ask("reg")`,
  then by hex only when that has no photo. `_ps_first` keeps the first photo whose page name (`/photo/<id>/<reg>-…`)
  starts with the registration (`_ps_like`: its letters and digits in order, a dash allowed between them, then a dash or
  the end), with their own https addresses, and gives src (`thumbnail_large`, the biggest they give: 420x280 or so), w,
  h, link (unchanged, `?utm_source=api` and all) and by. `_ps_cache` (3,000 registrations, memory only): answers for
  `PS_KEEP` (23 h: their limit is 24 h and the boards keep theirs an hour), failures `PS_FAIL` (10 min). `_ps_ask` makes
  one request a second (`PS_GAP`; a lookup that would wait more than `PS_WAIT`, 4 s, isn't made), sends `PS_AGENT`
  ("Fallblatt/<relay version> (+https://github.com/Belstria/overhead-board)": they refuse library defaults), and after a
  403 or 429 asks nothing for `PS_REST` (30 min, one warning). `PHOTO_HOSTS` loses `.plnspttrs.net` (their photos must
  not be passed on) and gains `thumb.wikimedia.org`. Their terms (planespotters.net/photo/api, 26 Oct 2026): the
  photographer named next to the photo, the photo a plain link to its page (on a screen nobody can tap, a QR code or
  NFC; Dave chose the credit as a link the remote reaches), images loaded only by the screen showing them and never
  kept or passed on, every address unchanged, answers kept 24 h at most. Test relay: fakesrc's `/ps/pub/photos/…`
  (OE-LBN by registration, the A380 by hex, the C-130's hex with OO-TEK's photo; a User-Agent without a contact is
  refused; `/ps/asked` counts the lookups), `PS_IMG` allows 127.0.0.1, `PS_GAP` 0.1 s; `--live-photos` asks the real
  Planespotters.net (for screenshots). The fake photos have a size now: an SVG without one has naturalWidth 0, so the
  board never showed them.
- Relay 70 (1.88.0.1): `live_stale(q, place)`: a "live" position request with `fix` older than `LIVE_FRESH_S` (300),
  negative or not a number skips `fill_want` and `Spot.take` (no sightings, points, liveSeen for lock-ons, gap filler);
  without `fix` (older boards) nothing changes. `no_cs()` treats an all-"@" callsign as none (`_record`, the
  approach/hide checks, `/flightinfo`), `AT_CS` blanks `"flight":"@@@…"` in the sources' answers before they are cached,
  and `_scrub_at_all()` (a thread at start, once per profile: logbook `atCsV`) blanks such "callsign"/"flight" values
  and drops such keys (the logbook's and game's "flights") in every saved day and the logbook.
- Relay 69 (1.88): `/relayinfo` (`relay_panel_json()`): `owner_ok()` only, also through the tunnel (not in
  `ADMIN_PATHS`); 403 for other profiles, strangers refused as usual. Sources in `SOURCES` order with role (first,
  reserve, emergency for `day_cap` sources), state (ok, resting with `until` and `http`, failing, standby) and
  requests this UTC day (`STATE` `asked`/`askedDay`, counted before each fetch; adsb.lol's `allow: 500`). Flightradar24:
  month credits/budget, today's credits and lookups, and the gap filler's credits (the `usage.by` rows ending
  " · Gap filler"; they are cleared with the month total in `_fr24_usage`, so no month counter is needed). Backup from
  `data/backup.json` (`BACKUP_FILE`, written by the host's nightly job: t, ok, bytes, kept, error; `late` past 36 h).
  Screens from `screens_list()` without ip, host or user agent. The page's `OVERHEAD_GUEST` gets `owner: true` for the
  `HOME_OWNER` profile, so other guests don't ask. Fixed with it: `--source` (the test relay) built a `STATE` entry
  without the new keys.

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
