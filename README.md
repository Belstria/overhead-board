# Fallblatt

An airport-style split-flap board (*Fallblatt* is German for split-flap) that shows the planes flying over a
chosen spot, live. It has two styles: **Overhead**, the planes flying over you, and **Airport**, the planes taking
off and landing at an airport.
It is a static page: open `index.html` in any modern browser, or serve it from GitHub Pages. Its translations and
recorded sounds are two files next to it (`i18n.js`, `sounds.js`; since 1.53.1), which a screen keeps after the
first visit, so later visits load half as much; without them the board still works, in English with synthesised sounds.

## Choosing the location

The page ships with central Vienna as its location. Set your own through the address, so the
location never has to live in this repository:

```
https://<user>.github.io/overhead-board/?lat=48.2085&lon=16.3731&place=Vienna
```

| Parameter | What it does | Example |
|-----------|--------------|---------|
| `lat`, `lon` | Spot to watch over | `lat=48.2085&lon=16.3731` |
| `place` | Name printed under the title | `place=Vienna` |
| `radius` | Spotting radius in km: planes within it are added to Spotted today (default 15) | `radius=8` |
| `over` | Counts as directly overhead within this many km (default 3) | `over=2` |
| `home` | Home airport IATA code, for Arriving / Departing | `home=VIE` |
| `maxalt` | Ignore planes above this altitude in feet | `maxalt=15000` |
| `units` | `aviation` for feet and knots (default metres and km/h) | `units=aviation` |
| `refresh` | Seconds between position updates (default 10) | `refresh=15` |
| `speed` | Flap speed in percent: 100 is fastest, 10 is ten times slower (default 85) | `speed=50` |
| `hd` | Render at 4K even if the screen reports a lower resolution | `hd` |
| `sound` | Flap sound on (`1`, the default) or off (`0`) | `sound=0` |
| `logos` | Airline logos on (`1`) or off (`0`) | `logos=0` |
| `theme` | `classic`, `frankfurt` or `blue` | `theme=frankfurt` |
| `rotate` | seconds per page, `0` to stay on one page (default 30) | `rotate=0` |
| `favs` | favourites, separated by commas | `favs=Austrian,A380` |
| `chimes` | chimes on (`1`, the default) or off (`0`) | `chimes=0` |
| `night` | night mode on (`1`, the default) or off (`0`) | `night=0` |
| `airtime` | minutes an hour a helicopter or circling plane may hold the top half, `0` for no limit (default 3) | `airtime=5` |
| `quality` | `auto` (default), `high`, `1440`, or `1080` (lighter, for TVs) | `quality=1080` |
| `demo` | Sample flights instead of live data | `demo` |
| `debug` | Open the diagnostics panel at start | `debug` |

Anything changed in the on-screen Settings is saved in that device's browser only, and only the
values you changed are kept, so new defaults from the relay still reach that screen.

## What the board shows

The top half shows one plane and how it relates to you, worked out from its position, heading and speed:

- **Overhead**: directly above, within the overhead distance (3 km by default).
- **Approaching** (called Inbound before 1.55): on course to pass over within three minutes; Position counts down to the pass.
- **Flying by**: getting closer, but its closest approach will be further than the overhead distance.
- **Leaving** (Outbound before 1.55): moving away, soft red on the radar. **Passed** is shown for a little while after an overhead pass.

Planes that are overhead or approaching always take the top spot; otherwise the board shows the plane in the
spotting radius that is coming closer. Every plane that enters the spotting radius is added to
**Spotted today** once per pass. The list marks the ones that flew directly overhead and otherwise shows
Arriving or Departing for your home airport. The Spotted today panel also lists each plane's closest distance.

## The three boards

| Address | What it is |
|---------|------------|
| `/` | **Main board**: the version for everyday use, with Flightradar24 when the relay has a key (a copy of the test board). |
| `/test/` | **Test board**: where changes are tried before they go to the main board, Flightradar24 features included. (Since 1.35.2 the only test board: `/test-api/` forwards here.) |
| `/app/` | **Phone app**: the board laid out for a phone, to add to the home screen (see below). |
| `/light/` | **Light version** of the phone app (1.39): the same, without split flaps (see below). |

Changes are tried on the test board first and copied to the main board when they're ready. If the Flightradar24
subscription ends, the boards keep working: they fall back to the free sources by themselves.

### Flightradar24 on the main board and the test board

With a [Flightradar24 API](https://fr24api.flightradar24.com) key on the relay (version 8 or newer), the main board,
`/test/` and the phone app show the real flight number and route for airline flights: RYR3EG becomes FR 1234 Vienna to London instead of a
guess from a callsign database. Add the key once on the relay computer (it is saved in `overhead.json` there and
never leaves that computer):

```powershell
py serve.py --fr24-key YOUR_KEY --save
```

- Remarks from Flightradar24: **DIVERTED** (the Spotted today tab shows where to), **CARGO**, **BIZJET**, **PRIVATE**,
  and military and helicopter flights by Flightradar24's own category. Flightradar24's API has no schedules, so delays
  aren't available from it.
- Lookups happen only while a board that uses them is open, once per flight, shared by every screen, at most 10 a
  minute.
- Each lookup costs 1 to 3 credits. The relay stops at 27,000 credits a month (the Explorer plan includes 30,000);
  change that with `--fr24-budget 50000 --save`, or on the admin page. Diagnostics on the board shows what has been used.
- The admin page (relay 40) shows the credits used and left this month, the day the plan renews and a breakdown of
  who used them (each account and device, plus "Lists and alerts" for the lookups the relay makes for Spotted today).
  Set the day your plan renews and the monthly budget there (**Plan renews on day … · spend at most …**); the month
  then runs from that day (`--fr24-reset-day 9 --save` does the same). **For a while** sets a higher budget until a
  date (a promotion, e.g. 54,000 until 8 Jan 2027); after that day the normal budget applies again by itself
  (`--fr24-budget-promo 54000 --fr24-promo-until 2027-01-08 --save`).
- The budget is spread over the month (relay 13 or newer): each day may spend its share of what is left, and unspent
  credits carry over. Past the day's share only the plane on the top half is still looked up; past one and a half
  shares nothing is, until the next day. A busy day can't use up the month, and the free sources fill in meanwhile.
- If the key is refused (the subscription ended) or the budget is used up, the boards quietly use the free sources.
- To turn it off: `py serve.py --fr24-key off --save`.
- Flightradar24 data is kept for two days at most (their terms allow 30); the lifetime logbook doesn't use it.
- Fewer credits (1.51, relay 45): an answer serves every later sighting of the same aircraft under the same callsign
  that day (another aircraft with that callsign is looked up on its own), and planes that only pass through the outer
  quarter of the spotting radius aren't looked up unless they come closer or are on the top half. The admin page
  shows how many lookups this saved.

## Board features

The main board has everything below. New features are tried on `/test/` first; open them through the relay at `http://<computer-name>:8080/test/`.

- **Not known: /** (1.48): a detail that isn't known (no route, no departure time, no operator ...) shows a "/"
  instead of blank flaps, on the plane on top, in Recent flights, Spotted today and the airport lists, and in the app.
  It appears only once every lookup for that plane has answered or given up, so while they run the field stays blank.
- **Flight times** in a fourth row of the top half: departure, arrival and the flight time (1.35.1: the whole
  flight, departure to arrival, once both are known; before, the time since take-off). Vienna Airport
  publishes its arrivals and departures with planned and expected times, and the relay (version 11 or newer) reads
  them, so flights to and from Vienna get an arrival or departure time. On the test API board Flightradar24 adds the
  take-off time for any flight. When there is no arrival time but the destination is
  known, the board estimates one from the distance still to fly and the plane's speed, plus a few minutes to land.
  **Delay and gate** (1.52, relay 46): a flight to or from Vienna shows in the Remarks DELAY 25 MIN or ON TIME (within
  four minutes; planned against expected or actual time, from Vienna Airport) and, when leaving Vienna, GATE F07 (the
  pier letter until the gate is given out). "/" where the airport doesn't say. Arrivals have no gate in its lists.
  Next to them (1.27, relay 28): **To go**, the distance still to fly to the destination, and **Seen here**, how
  often this airframe was seen from here before: FIRST TIME EVER, SEEN 4 TIMES, or BACK AFTER 7 MONTHS when it had
  been away for two months or more. The phone app shows both under This aircraft.
- **ABOVE CLOUD** (1.27, relay 28; a remark since 1.49): the relay reads the home airport's weather report (METAR) every
  ten minutes; a plane above the cloud base (the lowest broken or overcast layer) that is worth going to the window for
  (a special plane, one on the watchlist, a military plane or a favourite) says ABOVE CLOUD in the Remarks, since
  you'll hear it rather than see it. It is no longer a status.
- **Painted as** (test API board, 1.27): when Flightradar24 says a plane flies in another airline's colours (a wet
  lease, or a group airline in the parent's livery), This aircraft's Operator line says so, e.g. "LAUDA · PAINTED AS RYANAIR".
  Overflights without a known route show what is known, often nothing.
- **Special planes take the board**: when a plane rings the bell (an emergency, a special or military aircraft, a
  favourite), it goes straight onto the top half and the lower half turns to **This aircraft**, and both stay with it
  while it is within the spotting radius. Without a photo, the screen there says so.
- **Rotating pages** in the lower half, every 30 seconds by default (Settings → Change pages every, or `?rotate=0`
  to stay on one page): **Recent flights** (the last eight planes that were on the top half, kept per screen),
  **This aircraft** (a photo and registration details of the plane on the board, when one exists) and **Today in
  numbers** (counted over the whole day by the relay). They go Recent flights, This aircraft, Recent flights, This
  aircraft, Today in numbers, and round again, so Today in numbers comes up every second round. When This aircraft
  has nothing to show, Recent flights stays up for that turn. Pages change like one giant
  split flap: the whole lower half tips forward, falls and settles with a small bounce, revealing the next page; flaps
  still turning on the old page keep turning as it falls. A rail of backlit push buttons runs along the bottom of the
  board: the pages on the left, the views on the right. The button for what is on show is lit, with a small flicker as
  the lamp comes on. To pick a page yourself, press its button, or use the left and right arrow keys or the keys 1 to 3;
  a page you pick stays for at least a minute, and the rotation carries on from there.
- **Views on the board**: Spotted today, Logbook, Radar and Settings take over the whole board below the header at
  once, without the falling page, and show on the board itself: lists and numbers on split flaps or engraved into the
  panel. Press the button again, Esc, or a page button to turn back; left alone for five minutes, a view turns back by itself. Add
  `#spotted`, `#logbook`, `#radar` or `#settings` to the address to open one at start.
- **The aircraft photo** sits on a small screen set into the board, in a housing with screws and a power light; the
  screen is off while the page falls into place and warms up after it lands.
- **Special aircraft**: A380s, 747s, Belugas, Antonovs, military and government aircraft, helicopters and
  emergency squawks (7500, 7600, 7700) get their own remark. The status flap alternates between the plane's
  status and that remark.
- **Cards** (1.34): tap (or click) an airline's logo or name for a card about the airline (codes, how often seen here,
  today's planes, its country and radio callsign, a few words from Wikipedia (1.50: also found under a shorter name or
  by Wikipedia's search), its logo once loaded, Favourite / Hide), a place (From, To) for its airport (name, codes,
  distance from you, runways, today's flights there, Wikipedia), and a plane for its card (photo, route, details,
  Remarks). In the phone app and on the full board alike. What opens a card is marked: in the app's lists the airline,
  the places and the aircraft type each sit in a thin grey outline (1.40; before, a dotted underline), and on the board
  a thin dotted line runs under those flaps (1.38).
  On the board a plane on the radar opens its card and the airline field the airline, and the **⋮** (three dots, 1.55; a + before) at the end of a row
  of Recent flights or Spotted today opens the favourite/hide sheet (a tap elsewhere on the row no longer does); a
  **double tap** goes full screen (one tap used to). Settings → Traffic → **Favourites & hidden** opens the manager on the board too.
- **Model card** (1.35): tap an aircraft type (the Aircraft field, a row's type, the plane card's Aircraft) for the
  model: its picture and a few words from Wikipedia, about how many are in service, how rare it is, how often you've seen
  it and today's count, with Favourite / Hide for the type. In the app, Settings → Account → Change password opens a
  window with the new password twice.
- **Remarks** (top half, last row; 1.34, was Seen here): the interesting things about the plane in turn: how often it
  was seen here, another airline's colours (Flightradar24), who flies it when it's on the watchlist, and "ONLY ~40 IN
  SERVICE" for rare types.
- **Model photos** (1.34): a plane with no photo of its own shows its model's picture from Wikipedia (Wikimedia
  Commons), credited as such.
- **Favourites and hidden planes** (1.31, relay 31): in the phone app, **swipe a row right** to make it a favourite or
  **left** to hide it (1.41: the row slides and shows ★ Favourite or Hide ⊘ in grey, turning yellow or red once letting
  go will do it; that half of the sheet opens; the + ring on the app's rows is gone since 1.42, the boards keep their
  +), or
  **Favourite… / Hide…** under This aircraft, opens a sheet to make its aircraft, type, airline or flight a favourite or
  hide it from now on; Settings → **Favourites & hidden** lists them with a × each and adds new ones (airlines and
  types to pick from). The lists are kept on the relay for your profile, so every board, the app and the notifications
  follow them. Favourites are marked FAVOURITE, chime and can notify; hidden planes stay off the board's top half,
  the lists, the radar and the notifications (still counted in the logbook). The board's old Favourites text in
  Settings still works and moves into the list the first time the app opens.
- **Updates every 5 seconds in the app** (boards: 10, Settings → Update every), and planes on the radar glide: each is
  moved on along its track, and a new position is blended in over a second instead of a jump.
- **Chimes**: a two-note chime when a special aircraft enters the spotting radius, three rising notes for a
  favourite, and a separate alert for emergencies. Needs a first click or key press, like the flap sound.
  The chime for special planes is the **airport bell** by default (1.32): three soft notes rising, like the chime before
  an announcement in a terminal. Settings → Flaps & sound → **Special bell** switches between AIRPORT and the old
  CLASSIC chime, and plays the one you switch to.
- **The day runs from 03:00 to 03:00**, so late-evening flights count to the evening they belong to.
- **Airtime limit**: a plane that hangs around (a police helicopter over an incident, a light aircraft circling) gets at
  most 3 minutes an hour on the top half while other planes are within the spotting radius, then gives them a turn.
  It counts helicopters and anything slower than 140 knots; other planes only after six minutes, so an airliner
  passing over is never cut short. With nothing else around it stays on the board. Settings → Limit hovering planes,
  or `?airtime=5`; Diagnostics notes each time it happens.
- **Spotted today** (press **T**): every plane that came within the spotting radius today, seventeen rows to a page
  as plain text engraved into the panel, like the legend: time, flight, airline, route, aircraft and registration,
  closest distance, altitude and remarks. Special planes get a lamp and a tinted row in the remark's colour. Buttons above it filter to overhead or special planes, turn the pages (or the arrow keys), and
  show the **Legend** of every remark. It covers the whole day (relay 10 or newer; older relays send the newest 400).
  On a computer (not on the TVs) a **filter** box sits beside the buttons (1.50): type an airline, flight number, city
  or airport (name or code), aircraft type, registration or remark (OVERFLIGHT, JUMBO, NEW AIRLINE ..., in English or the
  board's language; 1.55); words separated by commas must all match ("Austrian, VIE"
  is Austrian's flights from or to Vienna). × clears it; it is per device and empty again after a reload.
- **Logbook** (press **L**): totals, the most seen model, the categories, and the top aircraft types, airlines and
  individual aircraft, with the newest ones, all on flaps. How many were passenger, cargo, business jet, private and light, helicopter,
  military or other flights (sorted by the relay from the free data, so the numbers are the same on every board;
  relay 10 or newer, which also counts the days already saved). The first sighting of a new type or airline is
  marked NEW TYPE or NEW AIRLINE on the board.
- **The Logbook's buttons** (1.55): one row at the top right, always in the same order (Logbook, Collection, Records,
  Week & month), the view on show lit; under it what that view offers: the place buttons and CSV under Logbook, Week /
  Month and ◀ ▶ under Week & month. The place buttons are your saved places and On the go; planes seen from a removed
  place, or from the unnamed spot before you saved places, count under All (that spot joins a saved place called Home).
- **Records & trophies** (from the Logbook's buttons, 1.27, relay 28): the logbook's lifetime records: the closest,
  lowest and fastest pass ever and the route from farthest away. The relay keeps them as planes come in and counts
  them once from the saved days of an older logbook. The phone app shows them in its Logbook.
- **Week & month** (from the Logbook's buttons, 1.52, relay 46): the week (Monday to Sunday) or month in review, like
  Today in numbers: planes, types, airlines, aircraft, new types, rare planes and points; the busiest day, the rarest
  plane, the most seen airline and aircraft, the farthest route, the lowest, closest and fastest pass, and the new types.
  **Week** / **Month** switch, ◀ ▶ go to earlier ones. A finished week or month is compared with the one before.
  Under them (1.28, relay 29): **this week's bingo**, nine things to spot between Monday and Sunday (a helicopter, an
  A380, something below 760 m, a plane after 23:00 ...), drawn afresh each week (on Monday at 03:00; next to the card
  it says when, and how long until then), and **48 trophies** (1.55, relay 50) that are won once and kept for good;
  nothing ever resets. Most come in tiers, a row each with a lamp per tier and a bar to the next one ("6,900 of
  10,000"): planes (100 to 100,000), aircraft types, airlines, different aircraft, countries the aircraft are registered
  in, points, special planes, planes in one day, the same aircraft again, days running with something rare. The others
  are one-offs: Odd couple (a 747 and a helicopter on the same day), Night owl, Bullseye, Stratosphere, Whale watcher
  (a Beluga), Heavy lifter (an Antonov), Completionist (every collection) ... An older logbook wins its trophies once
  from its saved days, on the day they were earned (relay 50 does this again for the new ones, keeping the old).
- **Achievements** (1.38; boards and phone app): when a collection is complete, a bingo line is made or a trophy is won,
  a card pops up with a little confetti and the bell (if chimes are on), and closes by itself after 10 seconds (or tap
  ×). Each one shows once on each screen; a screen opening the board for the first time doesn't celebrate everything
  won before.
- **Watchlist** (1.28, relay 29): the relay downloads [plane-alert-db](https://github.com/sdr-enthusiasts/plane-alert-db)
  once a day, about 17,000 aircraft worth a look, and a plane on it says what it is in its status and the lists:
  POLICE, AMBULANCE, RESCUE, FIREFIGHTER, GOVERNMENT, ROYAL, HISTORIC, CELEBRITY, VIP, SKYDIVING, AEROBATIC, SURVEY or
  UNUSUAL (air forces stay MILITARY). The list is © its contributors, under the ODbL 1.0 / DbCL 1.0.
- **Day in review** (1.28): from 21:00 until the day ends, Today in numbers is called Your day in planes, and its last
  row shows the rarest plane of the day and the day's points.
- **Radar** (press **R**): a plan view of everything around you in an instrument set into the board, with trails,
  the spotting radius and the airport's runways, and the planes within the spotting radius on flaps beside it. In the
  Airport style (1.33) it is centred on the home airport, with the spotting radius around the airport and the logo
  marking your place, and the list gives distances from the airport and the airport statuses (TAKE-OFF, FINAL ...).
  **Map** (1.55; board, app and light) puts a plain dark map underneath: built-up areas, water, rivers, main roads and
  runways, no text, from [OpenFreeMap](https://openfreemap.org) (© OpenMapTiles, © OpenStreetMap contributors, credited
  under the radar). Each screen remembers it.
  Planes glide between updates, counted from when each position was reported, so a late or repeated update doesn't
  pull them back; the Take-off and Landing runway screen moves its plane the same way.
- **Settings** (press **S**): a cockpit panel. Rotary selectors, flip switches, thumbwheels and amber read-outs on
  painted plates with screws; nothing changes until **Save**, and Cancel leaves everything as it was. On the test
  board and in the phone app, every control sits in its own cell with its name engraved above it, the flip switches
  are aircraft toggles, and the controls make their sound (knobs and switches a small click, thumbwheels a ratchet
  tick, push buttons a thock) when the flap sound or the chimes are on.
- **About** (Settings → About, or press **A**): what changed in each version, the keys, and
  who made it. Versions count new features (1.8), small changes (1.8.1) and bug fixes (1.8.1.1); About also shows when
  this version was published (relay 17 or newer) and the relay's version. A screen that still shows an older time needs
  a reload.
- **Languages** (Settings → Display → Language, or `?lang=de`): English, German, French,
  Spanish and Dutch. AUTO follows the browser's language. Everything on the board follows it, the status words on the
  flaps too; the patch notes and the connection log stay in English.
- **Airport style** (tap **Airport** in the title, or `?mode=airport`): for watching from the
  airport. The board follows the planes taking off from the home airport (rolling for take-off, climbing away) and the
  ones coming in to land (approach, final, landed). The top half shows the plane taking off or landing right now;
  its status flap shows a plane climbing away from or coming down onto a runway in front of the word. Below, the pages
  turn between the take-offs and landings (two lists side by side), the departing plane and the landing plane (photo
  and details, like This aircraft). Every page button works; a page with no plane on it says so (and the automatic page turning
  skips it). The two styles sit in the title as a switch: tap the other one to change (since 1.47 the one you're in
  shows in amber, the other faded, with a swap sign between them). Each device remembers the style
  it was last left in (1.40; it no longer follows your other devices), Overhead the first time. Set the home airport first (Use current location offers the nearest one). Vienna works with any relay;
  other airports need relay 18 or newer. In the app, Now shows the plane, its details and the two lists.
- **The full board has what the app has** (1.44), except what needs a phone (Sky view, compass, notifications):
  Settings → Control → **Account & device** (who the screen is signed in as, passkeys, password, Sign out of this device,
  links to the phone app and its light version, the tips again, the privacy note); Spotted today's **This place / All
  places** button; the Logbook's place buttons (All and your saved places) and a **CSV** download. Nothing on the board needs
  scrolling (TVs can't): address results and airport choices open as a window, Update location fits its cell, and
  About's patch notes and legend move with **▲ ▼** buttons.
- **New plane ding** (1.43): a soft, subtle cabin "ding" when a new plane comes on top, so you know when to look up
  (not for special planes, which have their own chime; not at night; at most every 15 seconds). Settings → Traffic
  (board) or Sounds (app) → **New plane ding**; switching it on plays it. Since 1.45 it is a recorded Airbus cabin
  chime (its first tone; both tones since 1.46), and it only sounds where the plane on top shows (the board without a view open, the app's
  Now), not in Settings, the radar or the lists; the chimes for special planes and favourites still sound everywhere.
  Achievements have their own short festive flourish (1.45).
- **Today in numbers** (1.43) comes round only after every tenth round of the board's pages (about every 20 minutes
  with 30-second pages); Settings → Traffic → **Today in numbers** OFF keeps it out of the rotation (it still opens when
  picked).
- **Model photos** (1.43) carry an amber tag "MODEL PHOTO · NOT THIS AIRCRAFT" on the board, in the app and in cards.
- **Remarks: what's new** (1.43, relay 38): instead of a general "first time ever", the Remarks flap names it: **FIRST
  EVER: TYPE** (the model), **PLANE** (this aircraft), **AIRLINE** or **FLIGHT** (this flight number; the relay counts
  flight numbers since relay 38 and learned the old ones from the saved days). Nothing during a new logbook's first day.
- **Tips** (1.42): the first time you open each page (and for the less obvious things: swiping a row, tapping an
  airline, place or type, the place switches, Place name's Save, live location) a short tip rings the thing it explains
  and gently fades the rest; tap anywhere to close it. Each shows once per device; Settings → Device (the board: the
  Control plate) → **Show the tips again** brings them back. On the full board they close by themselves after 11 seconds.
  Since 1.49 the first visit walks through everything on the main page at once: the two styles (Overhead and Airport,
  and what each shows), each page button and each view (the board) or tab (the app); the first switch to Airport walks
  through its pages. On the board the tips scale with the screen. The next tip follows right after one is closed (1.50).
- **Take-off and landing pictograms** (1.49): TAKE-OFF and CLIMBING show a filled plane climbing away from a runway line,
  APPROACH and FINAL one coming down to it, LANDED the plane level on the runway (after [Tabler Icons](https://tabler.io/icons)'
  plane-departure and plane-arrival, MIT licence, © Paweł Kuna), on the flaps, in the app's chips and on the page buttons.
- **Tap About seven times** (1.49) within a few seconds (the board: the About button, then the About heading; the app:
  About, then the page's title) and the Airbus "barking dog" plays: the hydraulic power transfer unit's bark.
- **Emirates boarding music** (1.49, relay 42): opening the Emirates airline card plays the first 30 seconds of the
  boarding music, fading in and, over the last four seconds, out; closing the card fades it out at once. The recording
  is copyrighted, so it isn't in the repository: the relay serves it to signed-in screens from
  `data/media/emirates-boarding.m4a` (`/media/<name>`, only names it knows). Without that file the card stays silent.
- **Logbook by place** (1.42, relay 37; the app and the light version): when planes were seen from more than one place,
  chips above the Logbook pick **All** or one place (with its count); a place shows its own numbers, top types, airlines
  and aircraft and its records (the collection, bingo, trophies and the year card count every place, so they show
  under All). Since 1.47 (relay 40) only places you still have get a chip: a removed place, or a spot without a name,
  counts under All. Since 1.49 the profile's own place (a location without a name) is the "Home" chip.
- **Today, This place | All places** (1.42): a two-way switch; the counters and the list switch together.
- **Cards** (1.42) open as a short loading window and appear complete once the words, the airport and the pictures are
  in (at most a few seconds), instead of filling in piece by piece.
- **Settings → Account** (1.41; more compact in 1.42): who this device is signed in as, plainly at the top (initial, name, account), then
  the passkeys and the password, and **Sign out of this device** at the foot (it was under Device; since 1.46 a small
  red **Sign out** next to the name, and Passkeys and Password each a row with its button beside it). **About** (from Settings) opens as a page over Settings: its close button stays at the top while it
  scrolls, and closing it leaves Settings as it was.
- **Settings → Location** (reworked in 1.40; relay 33 for the place and address parts):
  - **Place name** is the name of the place being watched (Home, Parents, Vacation …). Type a new one and a **Save**
    appears inside the field: it saves the location being watched under that name. A name that is saved already
    shows a ✓.
  - **City** is the town shown under the title. It fills itself in whenever the location changes (an address, the
    current location, typed latitude and longitude, a saved place, live location) and can still be typed over.
  - **Airport** (was Home airport): when there are several airports with scheduled flights within 100 km, a short list
    to pick from (code, name, distance) appears; with one, it is taken.
  - **Update location**: **Use current location** and **Live location** side by side. Live location (the app through
    the https address, or the Android app) makes the board watch where the phone is while the app is open, names the
    town and picks the nearest airport as it moves; its planes count as "On the go", the title shows ◉, and Place name
    reads "On the go". Turning it off goes back to the place before. The TVs can't follow (browsers only share their
    location with https pages).
  - **Saved places** opens the list: tap one to watch it (Settings follow at once), **Update** moves it to where the
    board is watching now, **×** deletes it. All names are alike, Home too, and nothing is saved by itself.
  - **Find an address**: type an address or a place and pick it from the list (OpenStreetMap's Nominatim, through the
    relay, no key needed); the town and the airports follow.
  - On the full board, whose panels have a fixed height, Saved places and the address search sit in the Update
    location cell.

  Saved places are kept on the relay, so all of a person's devices (or all screens at home) share them; each device
  watches its own choice. Every place's planes go into the **one logbook** (collection, trophies, bingo and records
  count them all), and **Spotted today shows the place being watched**, so the TVs keep showing the sky over home while a
  phone shows where it is. A plane seen from two places in the same pass is one sighting. The app's Today has a switch to
  show every place at once, with each plane's place. Sightings carry their place in the logbook's CSV.
- **Use current location** (Settings → Location → Update location; boards and phone app): fills in latitude and
  longitude, the town and the airports nearby (relay 16 or newer). Browsers only share their
  location with https pages or a page opened on the relay's own computer (`http://localhost:8080`), so it doesn't work
  on the TVs; in the Android app it asks for the phone's location.
- **Rarity and the Collection** (1.21, relay 24; by fleet size since 1.25, relay 26): every plane gets a tier, shown in
  colour with an icon on the flap after its type, from how many of its type fly today: common (grey: 1,000 or more),
  uncommon (green: 250 or more, or a type the table doesn't know), rare (blue: 50 or more), very rare (purple: fewer)
  and special (gold: the special planes, military and emergencies). Sightings score 1, 3, 10, 25 and 50 points; Today in
  numbers shows the day's points and the best day, the Logbook the total and the streak of days with something rare,
  and Logbook → **Collection** shows the points, the tiers seen (with their icons in the app) and nine sets of types to complete. Guests have their
  own.
- **Runways in use** (Airport style, 1.20): worked out from the planes lined up with each runway; shown next to the
  lists' title ("Landing 29 · departing 16") and lit on the radar. The Take-off and Landing pages show the plane on a
  runway screen with how far it is to touchdown or how high it has climbed. Far out (a landing before its final
  approach, a take-off climbing away) the screen shows the plane's photo full size, with "Expected in … min" for a
  landing; close in, the photo slides into a corner and the radar shows the runways up close (1.26). Home airports
  other than Vienna need relay 23.
- **Board styles**: classic white on black, Frankfurt yellow on black, or white on blue, each with its own typeface
  (Settings → Styles, or `?theme=frankfurt` / `?theme=blue`).
- **Styles to unlock** (1.59, relay 51; Settings → Styles on the board, in the app and the light version): every choice
  shows, the locked ones with what unlocks them, and picking an unlocked one applies at once. The default look stays
  until someone picks something. Unlocks are the profile's own, from its logbook's game:
  - **Colours** for points: Heathrow yellow 5,000, Solari green 25,000, Ice blue 50,000, Sunset 100,000.
  - **Flaps** for trophies: Black on white (Type collector), Brass trim (Rare breed), Worn enamel (Regular), LED dots
    (Around the clock). Not in the light version.
  - **Title badge** by the title, one more for each full bingo card (all nine in a week): Star, Propeller, Helicopter,
    Jumbo, Fighter jet, Concorde. The relay counts the full cards, older weeks once from the saved days.
  - **Board styles** for the rarest trophies: Frankfurt 1970s (Unstoppable) and Tokyo night (Completionist), next to
    Classic, Frankfurt and Blue. Not in the light version.
  A new unlock pops up like an achievement.
- **Sounds** (1.17): the Settings controls play short recordings of the real things: a rotary switch, a rocker
  switch, a thumbwheel and a push button; the flaps keep their synthesised clack (credited in About; see
  [tools/sounds/](tools/sounds/README.md)). (The Sounds switch for the older synthesised ones was removed in 1.33.)
- **Realistic look** (Settings → Display, on by default): flaps printed on two cards, a fine grain on the plastic,
  light from above, a turning flap catching the light, glass over the board, brushed metal plates and metal knob caps.
- **Worn hardware**: modules sit very slightly out of line and the odd flap hesitates or catches, and the panel has
  some honest wear: fine scratches, polish marks, grime in the corners, paint rubbed off the edges, a few small dings.
  Can be turned off.
- **Quick flaps** (Settings → Display, 1.14): every flap still turns through its letters and words, but as a blur,
  and the whole board lands on the new text in about 1.5 seconds. Flap speed % doesn't apply while it is on.
- **Night mode**: dims the board and mutes it between set times (22:30 to 07:00 by default; `?night=0` turns it off).
  **At night** (Settings → Night, 1.53) picks DIM (the dimmed board) or NIGHT VIEW: during those hours a black page
  with just the clock, the plane on top (flight, route, type) and today's count in dark red, so it doesn't light up
  the room. Any key, tap or click brings back the (dimmed) board for a minute; that first input does nothing else.
  `?nightview=1` (or `0`) sets it from the address.
- **Share a plane** (1.53): the plane card's **Share** (on a computer, in the phone app and the light version; not on
  TVs) makes a picture: the plane's photo (or its model's) over a split-flap panel with the flight and airline, the
  route, the aircraft, the registration and the time, and a small Fallblatt mark (no link). Then **Share** opens the
  phone's share sheet (WhatsApp and the like; in the Android app its own) and **Save picture** downloads it. The
  photo comes through the relay (relay 47) so the picture can be saved; with an older relay a model photo from
  Wikimedia still works, an aircraft's own photo is left out.
- **Screens**: the relay lists every screen using it by device (relay 12 or newer, see below); boards also tell it how
  big they are drawn and at what quality.
- **Drawing quality** (Settings, or `?quality=`): Automatic draws as sharp as the screen allows, up to 4K, except on
  Fire TV and LG TVs, which get `1080`: drawn at 1080p, 30 frames a second, shorter flap runs and a smaller image cache,
  because their graphics chips struggle with the full board. `1440` sits in between, `high` forces the sharpest. The
  falling page is always drawn at 1080p at most; it moves too fast to need more.

The logbook and a Spotted today list shared by every screen need relay version 5 or newer (see below).

## Phone app

`/app/` is the board laid out for a phone held upright, with the same flaps, metal, push buttons and engraving.
It opens with the logo, whose plane takes off into the board (not again on a reload within a minute).

**On Android**, install the Fallblatt app: on the phone, download
[overhead.apk](https://github.com/Belstria/overhead-board/releases/latest/download/overhead.apk) and open it (Android
asks once to allow installs from the browser). On first start it looks for the relay on the Wi-Fi by itself; if it
can't find it, type the address the relay prints, such as `http://192.168.1.20:8080`. Settings → About → Change relay
picks another one later. The app shows `/app/` from the relay full screen, so it is always the current version; a new
APK is only needed when the app itself changes (see [android/](android/)). Chrome can't install `/app/` itself as an
app, because it installs web apps only from https addresses and the relay is plain http.

**On an iPhone**, open `http://<computer-name>:8080/app/` in Safari, then Share → Add to Home Screen. Opened from the
home screen it has no browser bars, so on its side the board gets the whole height.

**On its side** (on a charging stand on the desk, say), the app is only the board, full screen and as big as the
screen allows: the plane's flaps across the top, and under them one page at a time, on flaps like the board's lower
half: Recent flights and This aircraft, or in the Airport style the board's Take-offs & landings, Take-off and
Landing (the last two put that plane on top, with the runway screen). Lamp buttons in the title strip pick the page; it
turns by itself every 20 seconds, and a page you pick stays a minute. On a screen that is short for its width (a
browser's bars, a wide phone) the lists show fewer rows (at least four), so the flaps fill the width. There are no tab buttons (Today, Logbook, Radar
and Settings are for upright; the one you had open comes back when you turn the phone upright again), and the status
line only pops up when something is wrong. The Android app goes full screen, draws under the camera (1.13.3 or newer)
and keeps the screen on as long as it is open (1.13.3.1 or newer). Auto-rotate has to be on.

Five buttons along the bottom:

- **Now**: the plane overhead on flaps (flight, status, airline, route, aircraft, registration, altitude, speed,
  position, departure, arrival, flight time and Remarks), its photo on a small screen (1.35.1: the list of details
  under it is gone since 1.36; tap the flaps for cards and Favourite / Hide), and the
  latest planes spotted. In the Airport style a Take-off / Landing switch picks the plane on top (it alternates by
  itself every 20 seconds; it stays when one side has no plane), with the runway screen in place of the photo, and the
  take-offs and landings below as split-flap rows (1.36; tap a row for the plane, its place for the airport).
- **Today**: today's numbers on flaps, the day's highlights (busiest hour, lowest and highest pass, fastest, most seen
  airline), and every plane spotted today, with the same filters and legend as the board, and the same filter box.
- **Logbook** (1.55): a switch at the top for the same four views as the board (Logbook, Collection, Records, Week &
  month); the place buttons only under Logbook. Logbook: the totals, most seen model, categories, top aircraft types and airlines, most seen and newest aircraft.
  At the top (1.28, relay 29), **the year in planes**: planes, types, airlines, airframes, countries and days, the
  busiest day, the most seen aircraft and the rarest, with **Share** (a picture of the card) and **Download the
  logbook (CSV)**, every sighting as a spreadsheet. Collection: points, tiers and the collections. Records: the
  records, this week's bingo and the trophies with their bars. Week & month (1.52, relay 46): **this week or month in
  review**, with Week / Month and ◀ ▶.
- **Where to look** (Now, upright, 1.28): the direction and height of the plane on top ("LOOK SE · 32° UP") on a dial
  with north up, under This aircraft's picture. On https (the public address) it turns with the phone so the arrow
  points at the plane: by itself on Android, after tapping the dial once on an iPhone (which asks first).
- **Sky view** (Now → Where to look → Sky view, 1.30; https only): the camera full screen, with a label on every plane
  within 60 km that is in the picture (flight, type, height, distance; the plane on top in amber, and an arrow at the
  edge when it is out of the picture). It works from the phone's own location (or the place in Settings), the compass
  and the tilt, and moves each plane on along its track since the last position. Phone compasses are often a few
  degrees off: drag the picture to line the labels up with the planes (kept on the phone; **Reset** undoes it).
  The phone asks for the camera and the motion sensors the first time.
- **Settings** also holds (1.34) Account, Notifications and this device (Full board, Sign out, Change relay); About keeps
  the version, the legend and the patch notes. The app doesn't zoom on a double tap.
- **Radar**: the radar instrument and the planes within the spotting radius. Tap a plane on the radar (or its row)
  for a card with its photo, route, aircraft, registration, operator, height, speed and distance, and Favourite… /
  Hide… (1.33). Leaving planes are soft red (1.55), apart from the dark grey of the ones too high to count. **Map**
  under the radar shows the map (as on the board).
- **Connection** (1.38): the small dot by the clock is green while live, amber when the data is late or a demo, red when
  there is none. Tap it for a card: connected to the relay or not, the position source and whether its data is live or
  the last good copy, when the last update came, failed attempts, planes in range, Flightradar24 on or off and the
  relay's version.
- **Settings**: the cockpit plates, kept on the phone only. Flap sound is on from the start (it plays after the first tap); chimes play for special planes and
  favourites while the app is open. When a special plane rings the bell while another tab is open, the Now button
  shows a red light.

The flight data comes through the relay (version 13 or newer serves its icons), so the phone needs the home Wi-Fi.
It checks for planes every 10 seconds while it's on screen and once a minute in the background. The relay lists it
among its screens as the APP board. `?demo` shows sample flights.

### Light version

`/light/` (1.39) is the phone app without split flaps: the same tabs, plane, lists, cards, places, notifications and
Settings, in the app's colours and fonts but as a plain, modern display. The plane overhead is a card of labelled
fields (the label in amber, the value under it); a new value slides in with a quick fade instead of flapping. Status
words are coloured pills, the airline shows its logo, the tier its sign. No metal, screws, glass or lamps: flat
cards, flat buttons, and Settings as segmented switches and steppers. Its Settings leave out everything about the
flaps (speed, quick flaps, worn hardware, realistic look, board style and flap finish; its Styles offer colours and
badges); Sounds keeps Button sounds, Chimes and the
Special bell. It keeps its own settings on the device, but a guest's place still goes to their profile as in the
app. On its side it is laid out like the app's, with the fields in place of the flaps.

Switch to it in Settings → Device → **Switch to the light version**, and back with **Back to the full app**. The
choice stays on the device: `/app/` (and so the Android app and a phone's home-screen icon) then opens the light
version. Notifications are shared with the app.

**Remote key test**: `http://<relay>:8080/keys/` lights up each remote button that reaches a web page (arrows, OK,
Back, colour keys), to see whether a TV's browser passes them on (the first step towards navigating the board with
the remote).

## Controls

- Click the board, or press **F**, for fullscreen.
- Press **S** for settings.
- Press **A** for About: patch notes, the keys and who made it.
- Press **D**, or use **Diagnostics** in the corner, for the connection log: which source the data
  comes from, recent failures, the closest plane and why it was or wasn't added to Spotted today.
  **Copy log** puts everything on the clipboard. Add `?debug` to the address to open it at start.
- The footer shows the name and a quiet lamp with "Live · 12 aircraft nearby" while all is well; when the data is
  late, comes from a fallback copy or doesn't arrive, it says so in full (the phone app shows that line under its
  lists only then). Diagnostics always has the details.
- Flap sound is on by default but starts after the first click or key press (browsers block it until then);
  the status line reminds you. Turn it off in Settings, with `?sound=0`, or with the relay's `--mute`.

## Data

- Live aircraft positions: [adsb.lol](https://adsb.lol), [adsb.fi](https://adsb.fi) and [airplanes.live](https://airplanes.live)
  (ODbL), tried in that order, with [AvioADSB](https://avioadsb.org) (data [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/))
  as an emergency backup. The boards' About links to each of them, as their terms ask.
- Routes, airlines and aircraft details: [adsbdb](https://www.adsbdb.com) and the adsb.lol route service.
  These are looked up by callsign, and airlines reuse callsigns (Ryanair especially), so a listed route is only
  shown when the plane is actually along it and heading towards its destination; otherwise the route stays blank.
- The watchlist: [plane-alert-db](https://github.com/sdr-enthusiasts/plane-alert-db) (ODbL 1.0 / DbCL 1.0).
- Cloud base at the home airport: its METAR from [aviationweather.gov](https://aviationweather.gov), through the relay.
- Planned and expected times : [Vienna Airport](https://www.viennaairport.com/en/passengers/arrival__departure)'s
  own arrivals and departures lists, read by the relay at most every three minutes while a board is open.
- Airline logos: the public airline logo service from Aviasales. When an airline has no logo there, its
  code is shown instead; flights without an airline (private, military, unlisted) get a plain aircraft mark.

The position services don't let browsers on other websites read their data, and they turn away
requests from cloud servers. So the live data has to come through a small relay running on a computer
in your home: [`relay/serve.py`](relay/serve.py). Opened directly from GitHub Pages, the board can't get
positions and says so in its status line.

## Running the home relay

The relay serves the board and fetches the flight data from your home connection. It needs Python 3.8
or newer and nothing else.

**Windows**

```powershell
winget install Python.Python.3.13          # skip if `py --version` already works
mkdir $HOME\overhead-relay; cd $HOME\overhead-relay
curl.exe -O https://raw.githubusercontent.com/Belstria/overhead-board/main/relay/serve.py
py serve.py --lat 48.2085 --lon 16.3731 --place Vienna --save
```

`--save` stores your settings in `overhead.json` next to the script (it never goes into this repository),
so from then on `py serve.py` on its own starts the relay with your location. Anything you pass on the
command line still wins over the saved file. Other relay options: `--units aviation`, `--radius 8`, `--mute`,
`--home VIE`, `--port 8080`.

When Windows Firewall asks, allow Python on **private** networks so other screens at home can reach it.

**Linux / homelab (always on)**

On a Debian or Ubuntu machine, or a small LXC container on Proxmox (1 core, 512 MB, 4 GB is plenty), as root:

```bash
curl -fsSL https://raw.githubusercontent.com/Belstria/overhead-board/main/relay/install.sh | sh
cd /opt/overhead-relay && sudo -u overhead python3 serve.py --lat 48.2085 --lon 16.3731 --place Vienna --save
systemctl restart overhead-relay
```

`install.sh` puts the relay in `/opt/overhead-relay` and runs it as a service (`overhead-relay`) that starts at boot
and restarts itself; the second line saves your location (press Ctrl+C once it has started). Running `install.sh`
again updates the relay and keeps your settings and logbook. Set the machine's time zone (`timedatectl
set-timezone Europe/Vienna`): the logbook's days follow it. The relay's messages: `journalctl -u overhead-relay -f`.
Moving from another computer: stop the relay there and copy its `overhead.json` and `data` folder into
`/opt/overhead-relay` (then `chown -R overhead:overhead /opt/overhead-relay` and restart the service).

Then open `http://localhost:8080`, or `http://<computer-name>:8080` from the TV, tablet or phone.
The relay prints the addresses when it starts. Your location stays on the relay machine: it is handed
to the board when the page loads, so nothing personal lives in this repository.

Positions come from adsb.lol, adsb.fi and airplanes.live, tried in that order. A source that answers
"too many requests" or "forbidden" is rested for a while and the next one is used; if all of them fail,
the relay keeps serving the last good data for up to two minutes. Only when all three fail or rest does it ask
AvioADSB, the emergency backup: its free tier allows one request every 10 seconds and 100 a day, so the relay asks it
at most every 15 seconds and 90 times a day (its day starts at midnight UTC) and serves the last good data in between. Problems are printed in the relay's
window and appear in the board's diagnostics panel.

**Friends and family (relay version 19).** The phone app can be shared with friends and family over the internet,
each with a profile of their own: their own location, settings, Spotted today and lifetime logbook. Open
`http://<relay>:8080/admin` at home, type a name and press **Make a link**, and send them the link. Opening it shows "A board for …"
with an **Open Fallblatt** button, which sets up that phone or computer (it works once, on the first device that presses
it, within two weeks; for another device press **New link**). Chat apps such as WhatsApp fetch the link for its preview;
since relay 27 that no longer uses it up, and devices that were only a preview are dropped from the list. They get a short welcome: its flaps show Fallblatt until a tap opens it (browsers only play sound after a
tap), then turn to their name letter by letter, with sound, within about two seconds. The board stays hidden until the welcome is done, then loads in with its flaps turning. They then type in their place, airport and coordinates
(the fields show an example), or let **Use my location**
fill them in to check, are asked about notifications (where the browser supports them), and choose the **phone app**
(which they can add to their home screen from the browser) or the **full board** (for a computer or TV); their
settings follow them between the two and to other devices. Settings → Account → **Sign out** forgets a device again
(the profile stays). Testing links yourself? Use a private/incognito window, so your own browser keeps its profile.

**Every screen is a profile's (relay 42, 1.49).** There is no "Home" any more: a screen at home without a profile
gets the private page with its QR code too (sign it in with your phone, below). The admin pages (`/admin`, `/screens`,
`/status`) open only on the home network, and since relay 43 only for the profile named David or a device that isn't
signed in at all (so a new relay can make its first invite); other guests get "Only for the owner". On its first start relay 42 merges the old Home into the
profile named David, once: its days of sightings are joined with his (a plane both recorded in the same pass counts
once), the logbook is counted again from the joined days (scores, records, trophies, flights), and Home's saved places,
favourites and hidden planes, notification subscriptions and linked devices move to his profile, with the relay's own
location filling in what his settings lack. The old files stay in `data/home-before-merge/`. If there isn't exactly one
profile of that name, nothing changes and the relay's log says so. A new profile's welcome starts from the relay's
city and airport (since relay 43 never its coordinates: the guest sets their own spot).

**The admin page (relay 42).** Since relay 46 each profile also shows its numbers: planes today, this week and in all,
the aircraft and types new this week and this month, its rare planes this month and its screens on now (no ranking).
Each profile is a **Guest** (no account yet: **New invite link** brings in another
device) or an **Account** (its username; there is no invite link any more, its devices sign in with the account, and
creating the account voids any unused link). For each: the devices with how they joined and when they were last seen
(each with **Sign out**), Flightradar24 on or off, the credits it used today and this month and its daily limit (an
empty field is automatic; type a number to set it), and under **Account**: create or change the username, set a new
password, and **Reset sign-in** (removes passkeys and password). **Remove** deletes a profile with its sightings.
Flightradar24 per profile and day: 500 credits for a guest, 2,000 with an account (a fallback against a bug or a lost
device, not a limit anyone should reach); past it their boards still show what has already been looked up.
**Hue lights (relay 47, a test, the owner's only).** When a special plane or a favourite is about to pass the
owner's place (the moments the "worth going to the window" alerts ring for), chosen Philips Hue lamps glow for about
four seconds in the airline's colour (amber for others) and then go back to how they were (brightness, colour, off
again if they were off). Through the Hue Bridge on the home network (its local API, no cloud); at most once per plane
and once a minute, and not between 22:00 and 07:00 unless **Quiet** is turned off. Set it up at the bottom of the
admin page: **Find the bridge** (asks Philips' discovery service, which lists the bridges on the network the relay
is on) or type its address (Hue app: Settings → Hue Bridges → ⓘ), then press the round link button on top of the
bridge and click **Pair** within 30 seconds (or click Pair first: the page waits 30 seconds for the button). Then tick
the lamps, **Save lamps**, turn **Pulse** on, and **Test pulse** to see it. The bridge's username is kept in
`data/hue.json` only. To try it without a bridge: `py tools/test/run_test_relay.py --hue` (a fake bridge).
The relay needs a public https address for this, through a Cloudflare tunnel, and to know it:
`--public-url https://overhead.example.com` (saved with `--save`) makes the admin page hand out full links.

**Names the relay answers to (relay 33).** So that no other website can talk to the relay through a browser at home
(by pointing its own name at the relay's address, "DNS rebinding"), the relay only answers requests made to one of its
own names: an IP address, `localhost`, a name without a dot (`overhead-relay`), a home-network name (`.local`, `.lan`,
`.home.arpa`, `.fritz.box` …), the public address, and whatever comes through the tunnel. A screen that opens it under
another name gets "This relay doesn't answer to that name" and the relay's status shows a warning naming it; let it in
with `py serve.py --allow-host that.name --save` (several names separated by commas). Also since relay 33: password
sign-in waits after five wrong passwords in a row (1 minute, then doubling up to an hour) and takes as long for an
unknown username as for a wrong password, notifications are only sent to the browsers' push services, a failed
download from GitHub isn't retried on every page load, and the positions it keeps for places nobody watches are
dropped after two minutes.

**Accounts (relay version 30, app 1.29).** An invite link makes a profile under the guest's name; an account is their
own choice on top: at the end of the welcome, or in the app's About → Account, they pick a username and add a
**passkey** (Face ID, a fingerprint or the phone's screen lock; passkeys sync through iCloud or Google, so a new phone
often signs in with one tap) and, as a backup, a **password**. On a new phone or computer they open `<public
address>/signin` (the "private" page links to it) and sign in with either: their place, logbook and settings are
there. The relay keeps only each passkey's public key and a salted scrypt hash of the password; sign-in tries are
rate-limited. Passkeys need the https address.

**Sign in a TV with your phone** (1.46, relay 39): a TV (or any screen) that opens the public address without being
signed in shows the "private" page with a **QR code** and a six-letter code. Scan it with a phone that is signed in
(or type the code at `<public address>/pair`), confirm "Sign in the screen as …", and the TV opens the board by
itself within a few seconds, as a device of that profile. A phone that isn't signed in is asked to sign in first; a
phone has to be signed in itself (since relay 42 there is no Home to sign in as). Codes last ten minutes (the screen shows a new one by itself) and are
rate-limited; only confirm a code on a screen in front of you. The admin page shows who has an account and **Reset sign-in** removes
someone's passkeys and password (they set new ones from a device that is still signed in, or come back through a
new invite link).

**Notifications (relay version 25).** Through the public https address, the phone app can send an evening summary
(22:30: planes, points, the rarest and the lowest), the week in review (relay 46: Sunday at 20:00) and the month before
(the 1st at 9:00; tapping either opens it in the Logbook; its own switch), and a "worth going to the window" nudge when something special, a
first-ever type, a favourite or a very low plane will pass within about 5 km in the next three minutes; the relay
watches for these even when no screen is open. Turn them on in the app under About → Notifications (Chrome on Android
and computers; on an iPhone after adding Fallblatt to the home screen). The relay needs the `cryptography` package for
this (`install.sh` installs `python3-cryptography`). They follow the profile the phone is signed in as.
Since relay 31 each alert says why (a special plane, on the watchlist: police, a military plane, one of your
favourites, a type never seen here, passing very low), and About → Notifications chooses which kinds you get (special
planes, the watchlist, military and favourites are on; new types and very low passes off). At most one every 15
minutes and none from 22:00 to 07:00, except emergencies and special planes; hidden planes never notify.
Since 1.32 only one notification shows at a time (a new one replaces the last), so Android never stacks them into a
group with its own icon. With the app open, an alert plays the airport bell instead of the phone's sound; with the app
closed the phone plays its own notification sound (the "Save the bell" download was removed in 1.40).

**New versions (1.51).** When a newer version has been published (the relay checks GitHub at most once a minute and
screens ask it every two minutes), a notice says so and counts down a minute, then the screen refreshes by itself.
Any key, tap or click stops the countdown; the notice then stays with **Refresh now** (on a TV, OK on the remote
presses it), and a screen nobody touches for half an hour refreshes then. It never refreshes while a card is open or
Settings has unsaved changes. The board's footer lamp stays too.

**The first picture (1.51).** Each screen keeps the last known board in the browser (the plane on top if it was there
in the last half hour, Spotted today and Today in numbers of the same day), per profile, and shows it at once when it
loads, marked **Last known board · not live yet**, until fresh data comes a moment later.

**Health watch (relay 45).** The relay sends its owner (the profile named David) a notification when every position
source has failed for more than 15 minutes, Flightradar24 refuses the key, the data disk is over 90% full, or the relay
restarted unexpectedly (not after a normal stop or update), and once when the problem is gone; at most one alert an
hour of each kind. Each is in the relay's log too, and `/status` lists the state under `health`.

**Screens (relay version 12).** The relay keeps track of which screens are using it and prints them in its window
as they connect, reload the board and go away, with what it knows about each: the screen's name, the device (Samsung
TV, Fire TV, LG TV, a PC or phone and its browser), its address and network name, which board it shows, how big it is
drawn and how long it has been on. Press **Enter** in the relay's window for the current list, or open
`http://<computer-name>:8080/screens`; the board's diagnostics panel lists them too. The boards and the phone app send their
name, size and drawing quality; a screen that hasn't asked for anything for a minute counts as gone.

**Shared history (relay version 5).** The relay records every plane that comes within its spotting radius
itself, so every screen shows the same Spotted today list and nothing is lost when a browser is closed. It
also keeps a lifetime logbook. Both live in a `data` folder next to `serve.py` (`sightings-<date>.json` and
`logbook.json`). A new logbook spends its first day learning what normally flies over, so NEW TYPE and
NEW AIRLINE marks start the day after. The spotting radius the relay uses is `--radius` (15 km by default).

The relay always serves the latest published board from GitHub Pages (it checks for a newer one at most once
a minute, so a change shows up a minute or two after it is published; a local copy is kept for when GitHub is
unreachable). Since relay 48 it lets screens keep the board's translations and sounds for good: the board names
them by version, so a changed file has a new address. Use `--local path/to/index.html` to serve a
local file instead, `--local-root path/to/overhead-board` to serve every board, the phone app and its icons from a
copy of this repository, `--source URL` to read positions from your own receiver (a URL with `{lat}`, `{lon}` and
`{nm}` placeholders, or a local `aircraft.json`), and `--help` for all options.

## Working on the board

`CLAUDE.md` has the working rules and how the pieces fit together. To try a change without touching the real relay,
`py tools/test/run_test_relay.py` runs a test relay with made-up flights at `http://localhost:8096/` (with a signed-in
test profile: open `http://localhost:8096/test-signin` once in a browser; the made-up flights play out in the first few
minutes after it starts; `--port 8296` runs it on other ports, so test relays of several checkouts don't answer for
each other, and `smoke.py` takes `--port` too);
`tools/test/shoot.py` takes screenshots of it, and `py tools/test/smoke.py` loads every page against it and fails on
a page error (`--syntax` checks that the scripts parse, with Node). GitHub Actions runs both, the relay's compile check
and an up-to-date check of the app on every pull request (`.github/workflows/check.yml`). The phone app is built from the test board's code with
`py tools/app/build.py`, so it gets new features together with that board; its light version from the app with
`py tools/light/build.py`.
