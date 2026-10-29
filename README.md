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
| `over` | Counts as overhead at any height within this many km (default 1; higher planes count from 45° up) | `over=2` |
| `home` | Home airport IATA code, for Arriving / Departing | `home=VIE` |
| `maxalt` | Ignore planes above this altitude in feet (Settings shows metres when the units are metric) | `maxalt=15000` |
| `units` | `aviation` for feet and knots (default metres and km/h) | `units=aviation` |
| `refresh` | Seconds between position updates (default 10) | `refresh=15` |
| `speed` | Flap speed in percent: 100 is fastest, 10 is ten times slower (default 85) | `speed=50` |
| `hd` | Render at 4K even if the screen reports a lower resolution | `hd` |
| `sound` | Flap sound on (`1`, the default) or off (`0`) | `sound=0` |
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

- **Overhead** (1.84): within the overhead distance at any height (Settings → Overhead within, 1 km by default), or 45°
  or more up in the sky, so a cruiser at 11 km counts from about 11 km out. Until 1.84 it was within 3 km at any height.
- **Approaching** (called Inbound before 1.55): on course to be overhead within three minutes; Position counts down to the
  moment it gets there.
- **Flying by**: getting closer, but it won't be overhead.
- **Leaving** (Outbound before 1.55): moving away, soft red on the radar. **Passed** is shown for a little while after an overhead pass.

Since 1.84 the board works out where each plane is right now: positions are a few seconds old when they arrive, so it
moves them on along their track, and between updates it looks again every 2 seconds, so OVERHEAD, APPROACHING and
PASSED change when they happen. Planes that are overhead or approaching always take the top spot (special planes and
emergencies take it from anywhere in the radius; favourites once they are overhead or approaching, since 1.84).
Otherwise, since 1.85, it shows the **Next** plane on course to pass overhead, from anywhere the board can see, with
Position counting down until it gets there (it turns Approaching three minutes out, with the ding); with none on its
way it says **No traffic**. Before 1.85 it showed the nearest plane flying by, even one far outside the radius. Every plane that enters the spotting radius is added to
**Spotted today** once per pass. The list marks the ones that came overhead (by the same rule) and otherwise shows
Arriving or Departing for your home airport. The Spotted today panel also lists each plane's closest distance.

## The three boards

| Address | What it is |
|---------|------------|
| `/` | **Main board**: the version for everyday use, with Flightradar24 when the relay has a key (a copy of the test board). |
| `/test/` | **Test board**: where changes are tried before they go to the main board, Flightradar24 features included. (Since 1.35.2 the only test board: `/test-api/` forwards here.) |
| `/app/` | **Phone app**: the board laid out for a phone, to add to the home screen (see below). |
| `/light/`, `/glass/` | Parked (1.71.3): open the phone app (see below). |

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
- Flightradar24's answers are cached for two days at most (their terms allow 30). Since relay 68 an answer is also
  written into the sighting it was asked for (flight number, route, diversion), so the logbook, search, the CSV and the
  records keep the flight actually flown, on every board; the airline stays the one the callsign names. No extra
  lookups are made for it. Planes only the gap filler found
  (below) stay in Spotted today and the logbook like any other sighting, marked as found through Flightradar24.
- **Away from home, Flightradar24 fills the gaps (1.87, relay 66).** Far from big cities the free networks can be deaf
  down low: on an island they first heard the planes leaving its airport at 9,000 ft and 22 km out, minutes after
  they had flown over. While a screen of the owner's profile watches a place more than 30 km from the relay's home,
  the relay also asks Flightradar24's live positions for the planes below 10,000 ft within 20 km, and adds the ones
  the free sources don't have: on the board, the radar, in Sky view and in Spotted today, with their type and
  registration looked up first. It asks every 30 seconds, every 15 while such a plane is within 10 km (the scan's circle), and every
  5 minutes where ten minutes of answers brought nothing new; only while a screen is looked at (not from the
  background), once for all the profile's screens, never at home or for other profiles. An answer costs 6 credits for
  each plane in it (1 when there is none): a plane passing close costs in the order of 100 credits, a quiet hour with
  the app open about 120 (1.87.1, relay 67: about half of before). It stops for the day at 80% of the profile's daily
  credits (2,000 with an account unless set on the admin page), so routes keep working. The connection log says "Flightradar24 filled in a plane the free sources can't hear"; the
  admin page lists the credits as "David · Gap filler"; `/status` counts the planes it filled in.
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
  **Delay and gate** (1.52, relay 46): in the Airport style a flight to or from Vienna shows in the Remarks DELAY 25 MIN
  or ON TIME (within four minutes; planned against expected or actual time, from Vienna Airport) and, when leaving
  Vienna, GATE F07 (the pier letter until the gate is given out). "/" where the airport doesn't say. Arrivals have no
  gate in its lists. In the Overhead style (1.88) the Remarks are white, not amber, and only say DELAY 45 MIN when a
  flight is more than 30 minutes late: no ON TIME and no gate.
  Next to them (1.27, relay 28): **To go**, the distance still to fly to the destination, and how often this airframe
  was spotted from here before (a remark since 1.34): FIRST TIME EVER, SEEN 4 TIMES, or BACK AFTER 7 MONTHS when it had
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
- **Whose photo** (1.93, relay 73): the plane's own photo from **Planespotters.net** comes first, looked up by its
  registration through the relay (and only kept when the photo shows that registration and, since 1.111.0.1, not an
  aircraft of another maker that had it before); then its own photo from
  airport-data.com (through adsbdb); then its model's picture. Each says where it comes from on the photo, in small
  capitals: "© photographer · Planespotters.net ↗", "Photo · airport-data.com" or "Model only · Wikimedia Commons".
  A Planespotters photo is a link to its page there (their terms): click or tap the photo, in the app, on the board and
  in the cards. On a TV, Up or Down on the remote puts the yellow ring on the credit and OK opens the photo's page (in a
  new tab where the TV's browser has tabs; Back comes back where it doesn't); opening it, or Up or Down again, takes the
  ring away. The page doesn't turn while the credit has the ring. The runway screen of Take-off and Landing and Sky view's small card
  have no room for the credit, so they show the next photo.
- **Special aircraft**: A380s, 747s, Belugas, Antonovs, military and government aircraft, helicopters and
  emergency squawks (7500, 7600, 7700) get their own remark. The status flap alternates between the plane's
  status and that remark.
- **Cards** (1.34): tap (or click) an airline's logo or name for a card about the airline (codes, how often spotted,
  today's planes, its country and radio callsign, a few words from Wikipedia (1.50: also found under a shorter name or
  by Wikipedia's search), its logo once loaded, Favourite / Hide), a place (From, To) for its airport (name, codes,
  distance from you, runways, today's flights there, Wikipedia), and a plane for its card (photo, route, details,
  Remarks). In the phone app and on the full board alike.
- **Info cards like Sky view's** (1.94): every card of a model, an airline, a plane and an airport looks like Sky view's
  card: a big photo with its credit at the top and the name, a line under it and a chip (rarity, codes, status) on it;
  a band (first flight → in service, founded → main base, the plane's route, your airport → there) with a gold chip in
  its middle saying what the card is (Model, Airline, Airport with a small picture; a flight's a plane in a gold disc,
  1.96.1; your airport's distance to there is the Flight distance fact since);
  three boxes (a model: Built, In service, Spotted; an airline: Fleet, Destinations, Spotted; a plane: Spotted,
  Closest, Flights; an airport: Passengers, Runways, Opened); one **Fun fact**; more facts in two columns (a model's
  engines, seats, wingspan, length, range, main user, years built and the model it was developed from, which opens its
  own card; an airline's headquarters, owner, employees, alliance and how many of its planes you've spotted; an
  airport's elevation, operator and flights to or from it you've spotted); Wikipedia's words in three lines with a
  small Wikipedia link to the page. **More info** opens the card further where it is: the rest of Wikipedia's words and
  **Did you know**, two or three more facts, each with its source in small type. The facts come from Wikipedia and
  Wikidata through the home relay (version 74; with an older relay a card shows what it has, in the same layout), the
  fun facts are worked out from them and your logbook (one of 199 built and you've seen 2; wings longer than an
  Olympic pool; the farthest of 40 cities its range reaches from here; flying for 70 years; back after 4 months), and
  "Spotted" says how often you spotted it: Once, or so many times. An airline flying under its group's name (Wizz Air
  Malta, easyJet Europe, Eurowings Europe) shows the brand's card, with the whole brand's fleet, and **Flown by Wizz
  Air Malta ›** under the band opens the company's own card; an airline with its own name (Austrian, Lauda Europe)
  keeps its card and **Part of Lufthansa Group ›** opens the group's (1.96.1, relay 77). On a TV the cards stay pop-ups: the remote's ring
  reaches every button, More info too (OK opens it, Back closes the card). What opens a card is marked: in the app's lists
  a tap opens the plane's own card right in the list (1.95; before, the airline, the places and the type sat in thin grey
  outlines), where the airline, the places and the Aircraft box open theirs, and on the board a thin dotted line runs
  under those flaps (1.38).
  On the board a plane on the radar opens its card and the airline field the airline, and the **⋮** (three dots, 1.55; a + before) at the end of a row
  of Recent flights or Spotted today opens the favourite/hide sheet (a tap elsewhere on the row no longer does); a
  **double tap** goes full screen (one tap used to). Settings → Traffic → **Favourites & hidden** opens the manager on the board too.
- **Model card** (1.35): tap an aircraft type (the Aircraft field, a row's type, the plane card's Aircraft) for the
  model: its picture and a few words from Wikipedia, about how many are in service, how rare it is, how often you've
  spotted it and today's count, with Favourite / Hide for the type (1.94: in Sky view's style, with its numbers). In the app, Settings → Account → Change password opens a
  window with the new password twice.
- **Remarks** (top half, last row; 1.34, was Seen here): the interesting things about the plane in turn: how often it
  was seen here, another airline's colours (Flightradar24), who flies it when it's on the watchlist, and "ONLY ~40 IN
  SERVICE" for rare types.
- **Model photos** (1.34): a plane with no photo of its own shows its model's picture from Wikipedia (Wikimedia
  Commons), credited as such ("Model only · Wikimedia Commons" since 1.93). Since 1.93.1.1 nearly every type has one:
  the model is found by its type code first (a table made from Wikipedia's list of type designators, with the common
  light aircraft and helicopters added), then by its names as Wikipedia spells them ("BEECH 200 Super King Air" is the
  Beechcraft Super King Air), and only then by Wikipedia's search. A page found from part of a name must agree with the
  rest of it, so a type gets no picture rather than another model's; a page whose own picture isn't the aircraft (a
  logo, another model) shows Wikidata's picture of it instead. A balloon, glider, autogyro, airship or ultralight
  without a better name (codes BALL, GLID, GYRO, SHIP, ULAC) shows a picture of its kind. A card that opened before
  its model's picture was found takes it when it comes.
- **Favourites and hidden planes** (1.31, relay 31): in the phone app, **swipe a row right** to make it a favourite or
  **left** to hide it (1.41: the row slides and shows ★ Favourite or Hide ⊘ in grey, turning yellow or red once letting
  go will do it; that half of the sheet opens; the + ring on the app's rows is gone since 1.42, the boards keep their
  +), or
  **Favourite… / Hide…** under This aircraft, opens a sheet to make its aircraft, type, airline or flight a favourite or
  hide it from now on; Settings → **Favourites & hidden** lists them with a × each and adds new ones (airlines and
  types to pick from). The lists are kept on the relay for your profile, so every board, the app and the notifications
  follow them. Favourites are marked FAVOURITE, chime and can notify (since 1.84 they take the top half and chime once
  they are overhead or approaching); hidden planes stay off the board's top half,
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
- **Logbook** (press **L**; on one screen since 1.92): seven plates like Settings', the numbers on flaps: **Totals**
  (sightings, individual aircraft, types, airlines and the most seen model), the **week, month or year in planes**,
  **Categories**, **Records**, and the top seven **aircraft types**, **airlines** and **aircraft**. How many were
  passenger, cargo, business jet, private and light, helicopter, military or other flights is sorted by the relay from
  the free data, so the numbers are the same on every board (relay 10 or newer, which also counts the days already
  saved). Click a plate, or press OK on the remote, for its whole list as a card: every type, airline or most seen
  aircraft (a row opens the model's or the airline's card, or the aircraft's sightings, and Back comes back to the
  list), every fact of the period, each category's top ten types, aircraft and operators (relay 61), the records with
  their plane and day. On a remote (or with the arrow keys) the arrows move a yellow ring from plate to plate and up to
  the buttons; Back (or Esc) closes a card, then the Logbook. The first sighting of a new type or airline is marked
  NEW TYPE or NEW AIRLINE on the board.
- **The game stays in the phone app** (1.89.1): the TV boards (and the board on a computer) show only the planes:
  no League page, points, levels, streak, Collection, bingo, trophies or achievement pop-ups. Settings → Styles there
  offers the styles the profile already has, without how to unlock more. The relay keeps scoring for the app.
- **The Logbook's buttons** (1.55; the Logbook, Records and Week & month views until 1.92): at the top right, All and
  a button for each of your saved places and On the go (planes seen from a removed place, or from the unnamed spot
  before you saved places, count under All; that spot joins a saved place called Home), the CSV, and on a computer a
  **search** through the whole logbook, as in the app (Enter shows what it found; relay 55). Under them **Week** ·
  **Month** · **Year** and ◀ ▶ for the period plate.
- **Records** (a plate of the Logbook; 1.27, relay 28): the logbook's lifetime records: the closest,
  lowest and fastest pass ever and the route from farthest away. The relay keeps them as planes come in and counts
  them once from the saved days of an older logbook. The phone app shows them in its Logbook.
- **Week, month and year** (the Logbook's period plate; 1.52, relay 46; the year relay 29): the week
  (Monday to Sunday), month or year in review, like Today in numbers: planes, types, airlines, aircraft, new types and
  rare planes (a year: countries and days; and points, in the app); on the plate the busiest day, the most seen aircraft
  and the rarest plane, in its card also the most seen airline, the farthest route, the lowest, closest and fastest
  pass, and the new types. **Week** / **Month** / **Year** switch, ◀ ▶ go to earlier ones. A finished week or month is
  compared with the one before. They count every place.
  In the app's Spotters' Club (on the boards until 1.89.1; 1.28, relay 29): **this week's bingo**, nine things to spot between Monday and Sunday (a helicopter, an
  A380, something below 760 m, a plane after 23:00 ...), drawn afresh each week (on Monday at 03:00; next to the card
  it says when, and how long until then), and **48 trophies** (1.55, relay 50) that are won once and kept for good;
  nothing ever resets. Most come in tiers, a row each with a lamp per tier and a bar to the next one ("6,900 of
  10,000"): planes (100 to 100,000), aircraft types, airlines, different aircraft, countries the aircraft are registered
  in, points, special planes, planes in one day, the same aircraft again, days running with points. The others
  are one-offs: Odd couple (a 747 and a helicopter on the same day), Night owl, Bullseye, Stratosphere, Whale watcher
  (a Beluga), Heavy lifter (an Antonov), Completionist (every collection) ... An older logbook wins its trophies once
  from its saved days, on the day they were earned (relay 50 does this again for the new ones, keeping the old).
- **Achievements** (1.38; the phone app, and the boards until 1.89.1): when a collection is complete, a bingo line is made or a trophy is won,
  a card pops up with a little confetti and the bell (if chimes are on), and closes by itself after 10 seconds (or tap
  ×). Each one shows once on each screen; a screen opening the board for the first time doesn't celebrate everything
  won before.
- **Watchlist** (1.28, relay 29): the relay downloads [plane-alert-db](https://github.com/sdr-enthusiasts/plane-alert-db)
  once a day, about 17,000 aircraft worth a look, and a plane on it says what it is in its status and the lists:
  POLICE, AMBULANCE, RESCUE, FIREFIGHTER, GOVERNMENT, ROYAL, HISTORIC, CELEBRITY, VIP, SKYDIVING, AEROBATIC, SURVEY or
  UNUSUAL (air forces stay MILITARY). The list is © its contributors, under the ODbL 1.0 / DbCL 1.0.
- **Day in review** (1.28): from 21:00 until the day ends, Today in numbers is called Your day in planes and shows
  the Plane of the day, the rarest plane seen (the day's points only until 1.89.1). On the board it takes the most
  seen's place; on the phone (1.111) it opens the plate, with the day's span under it: the first and the last plane and
  the busiest hour.
- **Radar** (press **R**): a plan view of everything around you in an instrument set into the board, with trails,
  the spotting radius and the airport's runways, and the planes within the spotting radius on flaps beside it. In the
  Airport style (1.33) it is centred on the home airport, with the spotting radius around the airport and the logo
  marking your place, and the list gives distances from the airport and the airport statuses (TAKE-OFF, FINAL ...).
  **Map** (1.55; board, app and light) puts a plain dark map underneath: built-up areas, water, rivers, main roads and
  runways, no text, from [OpenFreeMap](https://openfreemap.org) (© OpenMapTiles, © OpenStreetMap contributors, credited
  under the radar). Each screen remembers it.
  **− and +** (1.62, Airport style) zoom in on the home airport in steps (10, 5 and 2.5 km to the rim), centred on where
  the planes stand: with Map on the close-up shows taxiways, aprons and buildings (since 1.70.2 Map off hides the map at every zoom), and the planes on the ground are
  grey and listed as **TAXIING** or **PARKED**. The list beside the radar shows each airline's logo (1.62). On the
  full board − and + sit at the radar's top corners, Map at its bottom left, and the range is engraved in the dial (1.63).
  In the Airport style the list, the plane card and the colours say what each plane does at the airport: taking off,
  landing, passing or on the ground (1.63).
  Since 1.65 zooming works in the Overhead style too, around your place. On the phone (1.69) the controls sit on a
  **Radar** plate like Settings: the **Range km** thumbwheel (▲ wider, ▼ closer; since 1.82.2 every 5 km down to 5, then
  2.5 km, the closest; it was 10, 5 and 2.5 km) and the **Map**
  switch; pinching zooms smoothly to any range and stays there, a double tap steps closer (from the closest, back out). The zoom is kept per screen (1.64).
  In the app (1.82.2) the reset goes straight back to the usual range for your radius (25 km for 15 km) and the middle.
  Since 1.83.2 it is a square push button beside the Range km wheel, like an airliner's: its ⟲ arrow lights up yellow
  when there's a zoom to undo and stays dark while the radar is at the usual range (it was a round ⟲ in the radar's corner).
  A plane tapped on the radar or in Nearest stays ringed while its card is open: since 1.83.3 the same card as anywhere
  else in the app, up from the bottom, with its height, speed and distance keeping up (it was a card under the radar). A departure from Vienna shows
  its gate on the plane card, and in the app's radar list while the plane stands at the airport (1.65).
  Planes glide between updates, counted from when each position was reported, so a late or repeated update doesn't
  pull them back; the Take-off and Landing runway screen moves its plane the same way.
- **Settings** (press **S**): a cockpit panel. Rotary selectors, flip switches, thumbwheels and amber read-outs on
  painted plates with screws; nothing changes until **Save**, and Cancel leaves everything as it was. On the test
  board and in the phone app, every control sits in its own cell with its name engraved above it, the flip switches
  are aircraft toggles, and the controls make their sound (knobs and switches a small click, thumbwheels a ratchet
  tick, push buttons a thock) when the flap sound or the chimes are on.
- **About** (Settings → About, or press **A**): what changed in each version, the keys, and
  who made it. On the boards (1.93.0.1) the patch notes take the left half (▲ ▼ scroll them), the keys (two to a row)
  and who made it the right half, so every credit fits on every screen. In the app, **Log** (1.80; also in the connection card, the dot by the clock) opens the app's log on a
  page of its own: All, Problems, Sky view or Network, and **Copy the log** to paste it into a message. Versions count new features (1.8), small changes (1.8.1) and bug fixes (1.8.1.1); About also shows when
  this version was published (relay 17 or newer) and the relay's version. A screen that still shows an older time needs
  a reload.
- **Languages** (Settings → Display → Language, or `?lang=de`): English, German, French,
  Spanish and Dutch. AUTO follows the browser's language. Everything on the board follows it, the status words on the
  flaps too; the patch notes and the connection log stay in English.
- **Airport style** (tap **Airport** in the title, or `?mode=airport`): for watching from the
  airport. The board follows the planes taking off from the home airport (rolling for take-off, climbing away) and the
  ones coming in to land (approach, final, landed). The top half shows the plane taking off or landing right now; a plane
  that just landed stays there while it taxies in, until the next landing is about 6 km out or a take-off starts (1.62);
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
- **New plane ding** (1.43): a soft, subtle cabin "ding" when the plane on top becomes overhead or approaching (since
  1.84; it used to ring for every new plane on top, mostly ones flying by), so you know when to look up
  (not for special planes, which have their own chime; not at night; at most every 15 seconds). Settings → Traffic
  (board) or Sounds (app) → **New plane ding**; switching it on plays it. Since 1.45 it is a recorded Airbus cabin
  chime (its first tone; both tones since 1.46), and it only sounds where the plane on top shows (the board without a view open, the app's
  Now), not in Settings, the radar or the lists; the chimes for special planes and favourites still sound everywhere.
  Achievements have their own short festive flourish (1.45).
- **Today in numbers** on the board (1.82) is laid out like the phone's: planes, airlines, types and overhead across
  the top. Since 1.111 the lowest and highest pass and the fastest sit side by side under them, the figure on flaps and
  the plane (flight, type, time) engraved under it; then the most seen (the airline and the top types, "AUSTRIAN 8 -
  A320 6") and the newest plane new to the logbook. The Records & trophies page shows each
  rank's medal as on the phone: the cup in its metal (filled once won) and a tag after the name.
- **Today in numbers** (1.43) comes round only after every tenth round of the board's pages (about every 20 minutes
  with 30-second pages); Settings → Traffic → **Today in numbers** OFF keeps it out of the rotation (it still opens when
  picked).
- **Model photos** (1.43) carried an amber tag "MODEL PHOTO · NOT THIS AIRCRAFT"; since 1.93 only their credit line
  says so ("Model only").
- **Remarks: what's new** (1.43, relay 38): instead of a general "first time ever", the Remarks flap names it: **FIRST:
  TYPE** (the model), **PLANE** (this aircraft), **AIRLINE** or **FLIGHT** (this flight number; the relay counts
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
- **Typefaces** (1.64): Archivo Narrow, Oswald and Barlow Condensed (SIL Open Font License, `fonts/OFL.txt`) come
  from the relay (`fonts/`, made by `tools/fonts.py`), not from Google Fonts: opening a board tells Google nothing, and
  the TVs draw their first flaps sooner. The flight school's signature (1.103) is written in EMS Allure, a single-stroke
  script (the same licence; `test/signature.js`, made by `tools/sig_font.py`, 31 KB, fetched only when it is drawn).
  The 1950s ticket (1.110) sets its heading and flight number in Old Standard TT Bold (the same licence, in `fonts/`
  like the others, 24 KB; a phone loads it only when that ticket shows).
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
  counts under All. Since 1.49 the profile's own place (a location without a name) is the "Home" chip. Since 1.89 the
  app picks in a bar instead of chips: **All**, **On the go** and **Saved places**, which opens a list of your saved
  places with their counts; the one picked then names the third part ("Parents ⌄"; tap it to pick another). Since
  1.96.1 (relay 77) places at the same spot (a centre within 1 km, a radius no larger: "Home" and the profile's "home")
  are one place, each sighting counted once. "Counting
  since … · N points" is a footnote at the bottom of the Logbook (with a place's own line) and of the Spotters' Club.
- **Today, This place | All places** (1.42): a two-way switch; the counters and the list switch together. This place
  includes your saved places at the same spot (1.95.0.1, relay 75): a phone on your own place and a board on a saved
  place there named Home share one list, each plane once.
- **Cards** (1.78, app) slide up from the bottom like Sky view's card, with a grip on top: drag one down (or flick it), or
  tap beside it, and it slides away; one opened over another glides to its new size. Pulled up where it can't scroll
  further (1.78.1) a card gives a little and springs back; the page behind never scrolls while one is open.
- **Cards** (1.42) open as a short loading window and appear complete once the words and the airport are in (at most
  a few seconds), instead of filling in piece by piece. Since 1.97.3 the photos don't hold a card back: it opens at
  once, its photo window keeps its size and shows the loading spinner, and the photo fades in when it has loaded (a
  photo already in the browser shows at once; with reduced motion and on the TVs it just appears).
- **Settings → Account** (1.41; more compact in 1.42): who this device is signed in as, plainly at the top (initial, name, account), then
  the passkeys and the password, and **Sign out of this device** at the foot (it was under Device; since 1.46 a small
  red **Sign out** next to the name; since 1.56 Passkey and Password as a checklist: an empty circle or a green tick,
  a line on what each is, and **Add** / **Change** on the right). **About** (from Settings) opens as a page over Settings: its close button stays at the top while it
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
    town or village (relay 62: the village itself, not the area round it, e.g. Oia rather than "Ia Municipal Unit")
    and picks the nearest airport as it moves; its planes count as "On the go", the title shows ◉, and Place name
    reads "On the go". Until the phone has found where it is (and if it hasn't for five minutes), the line under the
    title says FINDING YOU … and its planes don't count or score; since 1.90 the board stays empty until this page has
    found the phone once (the saved spot may be far away): no plane on top, no last known board, no rows in the lists,
    just "Finding where you are …"; after a minute without a position a note says live
    location isn't working on this device, with a button to Settings. Since 1.93.0.1 a town's name only shows within
    2 km of where it was found (the airport within 15 km): until the new name comes, the title says ON THE GO and City
    reads "On the go", and neither an old name nor an old airport goes to the profile; a lookup the relay didn't answer
    is made again on a later position, a minute on. Since 1.93.1 live location asks the browser for the precise
    position (Chrome on Android otherwise shares only an approximate one, a new one at most every 15 minutes) and takes
    no position more than two minutes old: a browser hands over the last one it kept, which can be days old and far
    away, say from a trip, so FINDING YOU … stays until a fresh one comes, and the Log (Settings → About → Log) says
    how old, how exact and how far away each refused one was. When only an old approximate position came, the note
    after a minute says to allow precise location for the site in the browser's site settings (in Chrome: ⋮ →
    Settings → Site settings → Location: "Allowed • Precise"). **Use current location** waits for a fresh position too.
    Turning live location off asks (1.93.1): **Stay here** watches the last position live location found, with its
    town and airport and no place name, **Back to …** goes back to the place before; closing the card (×, Back, beside
    it) keeps live location on. Without a fresh position it goes straight back to the place before. Picking a saved
    place or setting a location while live just goes there. The TVs can't follow (browsers only share their location
    with https pages).
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
- **Only with the app on screen** (1.97.6, relay 81): nothing counts while the app is in the background. A page that is
  hidden says so with its position requests and the relay records no sightings, scores nothing and fills no bingo square,
  medal or level from them; it all resumes the moment the app is on screen again (it looks at once, so a plane overhead
  then counts). Home and saved places (the TV boards) and push notifications are unchanged.
- **The game** (1.72, relay 59): only planes spotted **with live location** on a phone score, the first time they
  come within **15 km** since 1.98 (relay 82; 10 km from 1.72.1, 8 km before; the same for everyone, whatever the radius), and
  only planes that came within **10 km** can be scanned; a board at home doesn't score. Everyone started
  again from zero. **Points since 1.96** (relay 76, to-do #127; earlier points stay as they were): each rarity has
  its full points (common 10, uncommon 30, rare 100, very rare 250, special 500). A plane that comes within 15 km gives
  a fixed amount (**5, 10, 15, 25, 50** since 1.97.4, relay 80, rule 4; a tenth of them, 1, 3, 10, 25, 50, before, and those
  awards stay as they were), once a pass, for up to a **daily limit per rarity** (common 50, uncommon 30,
  rare 15, very rare 5, special 3 planes; the day runs from 03:00); past the limit a plane scores nothing. A **Sky view
  scan** (a plane held in the ring for 1.5 s that came within 10 km, seen live in the last 2 minutes, once a pass, no limit)
  gives the plane's **full points on top** since 1.97 (relay 79; a common gives 1 + 10 = 11, one past the limit 0 +
  10; 1.96 topped it up to its full points, and its scans stay as they were). **Only scans** earn the extras: a type new to
  the game +50, a new airline +25 (at its first scan), and the **daily streak**: the day's first scan adds +25 × the
  day of the streak (25, 50 … 175); a day without a scan starts it again at day 1, and so does Monday 03:00, with the
  league. Since 1.104 a **standby** keeps the streak through a day without a scan: one a week from level 6, two from
  level 14, fresh each Monday 03:00 (they don't carry over). The covered day counts as a streak day but pays nothing,
  and the next scan goes on (Mon–Wed scanned, no scan Thursday: Friday's first scan is day 5, +125). The Spotters'
  Club's level card shows the week (scanned days amber, a covered day SBY) and the standbys left; the score strip says
  "Standby used" the day after, and warns in the club when none is left and today has no scan yet. No more close-pass factors, taper, streak multiplier or combo. Since 1.100 **bingo and trophies pay** too
  (from then on; earlier wins stay unpaid): +50 for each line on the weekly bingo card (rows, columns and diagonals) and +500 more for the full card,
  a new trophy rank +50 to +250 by its medal (bronze 50, silver 100, gold 150, platinum 200, diamond 250) and any other
  trophy +100. They count like every point (the day, the week's league, the level), show their +N on the achievement
  card or the medal, and stand in Recent points under the plane that won them ("Bingo line · Top row +50",
  "Trophy · Globetrotter · Bronze +50"). Since 1.98 the **passive points show only on the
  score strip** (its +N). A plane that comes **within 10 km** gets a **ticket** sliding up from below (once a plane): the
  boarding pass with the plane, what a scan gives now on the left (the plane's full points, +50 for a new type, +25 for a
  new airline: only what is sure), their total on the stub, a line for the daily streak while nothing was scanned today
  ("Your first scan today adds the daily streak: +25"; not in the total) and **Scan in Sky view**: a tap anywhere on the
  ticket opens Sky view with that plane picked out, its ring on it and the edge arrow pointing to it (in Sky view the tap
  only picks it out). A ticket stays **10 seconds**, or until it is swiped away sideways or its plane is scanned, and
  doesn't come back for that plane (its gold ★ in Sky view stays). Several planes: one ticket each, up to three on screen,
  **newest on top** with the older ones peeking out under it; a fourth puts the oldest away, a shorter pass only for a
  while (the ticket comes back while its 10 s last). In Sky view the tickets sit at its bottom. **At the scan** the
  plane's ticket, if it is still up, becomes the scan's ticket (what the scan really gave) and tears, then the streak's;
  both stay 10 s. The first plane past a limit still shows a grey pass, "+0 · Common limit reached" (later ones stay
  quiet); a scan brings a prize jingle and a buzz. **Golden tickets** (1.101): now and then (about one plane in 20) a
  plane's ticket comes up **gold**: gold foil with a sheen, "GOLDEN TICKET · 10 KM", the stub "GOLDEN" with ×2. Its scan
  pays the plane's points **twice** (a common 10 → 20, a rare 100 → 200; the ticket reads "Rare plane +100 ×2"); the
  extras (new type, new airline), the streak, bingo and trophies don't double (they say "(no ×2)"), nor do the passive
  points. The relay picks them, so nobody can pick or re-roll one, and any plane can be one, even a common one; the same
  plane is gold for everyone that day. In Sky view its label has a gold edge and a "GOLDEN ×2" tab, its ★ shows the
  doubled points; its stub tears off throwing gold glitter, with a sound of its own (the paper rip, then bells climbing
  to a bright chord). Recent points: "Sky view scan · Rare plane ×2 golden". With reduced motion it stays gold, without
  the sheen or the glitter. **Flight school** (1.103, relay 85): a new player gets five first missions that teach the
  app: scan a plane, open a plane's card, fill a bingo square (a square new to the week's card), add a favourite and
  catch an uncommon (or rarer) plane that scores. Each pays **+50 once** (in the day, the week's league and the level);
  all five earn the **wings** (nothing more paid; the rank shows a wings pin). The Spotters' Club shows a cream training
  record: a line per mission with its stamp box (a red "FLIGHT SCHOOL · PASSED · 29 OCT · +50" stamp once done, a hint
  for the next one only); Now shows a small bar "CHECKLIST 2/5 · NEXT UP · SCAN A PLANE" with five marks until the
  wings. A mission done slides its line in at the top and a big stamp comes down on it with a thud; the fifth then signs
  the record's WINGS line with your first name, written stroke by stroke as with a pen, and "Cleared for take-off"
  comes with the wings; the signed record moves to the end of the club. Recent points lists the missions in a Flight
  school row. With reduced motion the stamps and the signature appear without moving. A player already at level 4 when
  relay 85 came got the wings at once, without points, and never sees the school; below that the school started then
  (nothing from before counts). (Until 1.96 a lock-on paid +25 % of the
  plane's points, more in a combo, a close pass ×1.1 or ×1.2, a streak up to ×1.2, and planes 26–50 counted half.)
  Sky view's labels (1.72.1) carry a ★ for the planes
  a scan counts for (since 1.80 in the plane's rarity colour; since 1.96 with what a scan gives: ★ 30; since 1.98 only
  within 10 km), ✓ and what the scan gave once scanned, a dimmed CLOSER TO SCAN for planes 10–15 km out (they scored
  their passive points) and a dimmed NO PTS beyond 15 km; a lock-on (1.72.2)
  opens a small card with the essentials that slides away by itself when you aim at another plane or away for 3
  seconds; swipe it up (1.72.3) and it grows into the whole card, its picture growing with it; dragged down it shrinks back,
  and further down (or a tap on the sky) it goes. In the phone app a **score strip** under the header shows
  the total on flaps, your **rank insignia** (1.102: levels 1–4 a sky-blue shoulder board with 1–4 silver pips, 5–8
  navy with silver chevrons, 9–11 black with 2–4 gold stripes, 12–14 gold piping, four stripes and 1–3 stars, 15–20 a
  pilot's cap whose peak turns gold step by step, the Ace's with a red band, the Legend's white, and a gold star above
  it for each Legend after that; also on Your level and a player's card), the level bar and the league place on every tab (grey with Go live when live location is off);
  when points come in the place chip flips to +N, which flies into the level bar, and the total rolls up. (The board's
  **Points** field beside the remarks, 1.73.1, went in 1.82.2: the strip shows points as they come in.) Tap the points for **Recent points** (1.89, relay 71): today's
  total and every plane that scored, newest first, with when and why (since 1.96 the same lines as the pop-ups, so they
  add up; a plane past its limit in grey with the reason; points from before relay 71 show without times); at its foot a link to the club. Tap the place
  chip (or, before relay 71, the points) for the **Spotters' Club** (1.74: next to the Logbook, as a title tab): the
  level, the **league** (this week from Monday 03:00, or all time, by first name; Show me in the league switches you
  out; since 1.102 each player's **rank insignia** beside their name, from level 19 the name in gold), today, how points work, the collections, records, bingo and trophies (no longer in the
  Logbook), and Styles. **Career path** (1.109): the strip's line names the next stop and what it opens ("Next stop
  Logkeeper · Black on white"); Your level shows a mini route (your stop, the plane with the points still to go, the
  next stop) with what the next stop opens, and **Your route · all 20 stops** opens the route: a stop per level down a
  line, solid where you've been and dashed ahead, each with its rank insignia, title, the points it opens at and what
  it unlocks (the board colours, flaps, badges and board styles; showcase slots at 3, 5 and 8; standby at 6 and 14; a
  gold name in the league at 19; the Legend cap at 20; then a stop every 27,756 points, each a star on the cap). A
  level-up is an arrival there: "Arrived at Logkeeper", a luggage tag for each thing it opened, the next stop, and
  **Try it** (a style opens Styles at its row, anything else the club). With reduced motion nothing moves. Since 1.79 the top is one card (the level; today's points, this week's points with your place
  and the streak as three numbers; since 1.96 **today's limits** as five counters, "18/30 Uncommon", with a note for
  each rarity that reached its limit and when it starts again; **How points work** opens a card with all the rules on
  one screen: each rarity within 15 km and scanned (within 10 km), today against the limits, the extras and the streak's days; since 1.100 bingo and trophies), the league's switch
  sits beside its heading, **Your catch** (by rarity) and **Sets** (to complete) replace Collection and Collections,
  and the trophies show the three closest to winning, with a switch to the ones won and the ones still to win (nearest
  first). Since 1.79.2 a trophy with ranks shows its rank as a medal (bronze, silver, gold, platinum, diamond) on its
  cup and beside its dots, and a won one with more ranks names the next. Since 1.81 (app) a new rank swings down as
  its medal on a ribbon, with its rank in Roman numerals, and a notice from the right says when the next rank is close
  ("2 more airlines for Globetrotter"; once a rank). **Your hangar** (1.81, relay 63) replaces the Sets list: a shelf
  per set you swipe sideways, with a collectible card for each type seen (since 1.96 any sighting, on any screen; until
  then only those caught on the go) (the photo of the first one you saw, or of its model; the rarity in its colour,
  the name, when and which; since 1.97 a line under it, "★ Scored 6× · 2 scanned" or "Not scored yet": how often
  the game scored the type within 15 km (10 km until 1.98) and how often Sky view scanned it), the missing types face down with their
  model's picture dimmed, and the types in no set on a shelf of their own; tap a card for its details (seen, scored,
  scanned) and the model. Since 1.103.0.1 the pictures load ahead (each shelf's first cards at once, the rest of a
  shelf as soon as you touch it), a shelf no longer jumps back while you swipe it, and a helicopter with no picture
  found shows a helicopter. Since 1.105 a card climbs with your **scans** of its type (mastery): **bronze at 5, silver
  at 25, gold at 100**, its frame in that metal and a thin bar under it to the next step. The scan that reaches a step
  pays **+25, +100 or +250** once (in the day, the week and the level), and its ticket says so ("Airbus A321 ·
  Silver +100"); the opened card shows the three steps with their bonuses and how far the next is ("13 of 25 scans to
  silver"). Scans from before count for the frames; a step already passed then pays nothing. Since 1.106 the club has
  **member cards**, one for every airline you caught live (the same count as the airline trophies, e.g. "32 airlines ·
  Frequent flyer at 50"): your first scan of an airline's plane makes you a **Member**, its **10th, 50th and 200th
  Silver, Gold and Platinum**, paying **+25, +100 or +250** once ("Austrian · Gold +100" on the ticket). The best card is
  in front with a bar to the next tier, the others' tops peek out above it (tap one to bring it forward). A plane's
  ticket prints your tier with its airline ("OS · GOLD"). Scans from before count; a tier already passed pays nothing. Since 1.107 the club
has a **passport** under Your hangar: every scanned flight with a known route stamps the countries it flew from and
to, and a country **new to your passport pays +25** at the scan (its ticket shows the route, "BCN ✈ VIE", the new
country marked). A card then shows the stamp coming down and the country soaking up its ink, or **rub it in with your
finger** ("Scratch Spain in"). The plate shows the map with each country inked in its stamp's colour (never where you
are; tap it for Europe or the whole world and a bar per region) and a shelf of stamps per region, with nearby
countries still to stamp face down. Countries of earlier scans are stamped too, without points. **Tap a name in the league**
  (1.81) for that player's card: level, this week, all time, the streak, medals by metal, the rarest catch and the
  week's best plane, never where they are. Since 1.108 a card has a **showcase**: up to three of the player's best
  catches pinned behind glass, each as its hangar card in miniature with the airline, the day and the route ("DXB → VIE").
  The spots open at **levels 3, 5 and 8**; on your own card a locked spot says when it opens and how many points are
  still to go. Pin from a plane's card in Your hangar (**Put in your showcase**; when every open spot is full, tap the
  one to swap); the plane pinned is that type's best catch: a scanned one first, then one the game scored, then any,
  one with a known route before one without, then the first. **Levels** (20 titles, Plane Watcher to Legend) unlock the styles one by one; a level up
  shows full screen. Last week's winner wears the crown and may use the **First Class** style that week. The board
  showed the week's league as a **League** page in its rotation until 1.89.1. Collections, bingo, trophies and records count live
  planes only; the logbook keeps every plane.
- **Rarity and the Collection** (1.21, relay 24; by fleet size since 1.25, relay 26): every plane gets a tier, shown in
  colour with an icon on the flap after its type, from how many of its type fly today: common (grey: 1,000 or more),
  uncommon (green: 250 or more, or a type the table doesn't know), rare (blue: 50 or more), very rare (purple: fewer)
  and special (gold: the special planes, military and emergencies). Points: see The game above (until 1.72 every
  sighting scored 1, 3, 10, 25 and 50). The Collection shows the points, the tiers seen and nine sets of types to
  complete. Guests have their own.
- **Runways in use** (Airport style, 1.20): worked out from the planes lined up with each runway; shown next to the
  lists' title ("Landing 29 · departing 16") and lit on the radar. The Take-off and Landing pages show the plane on a
  runway screen with how far it is to touchdown or how high it has climbed. Far out (a landing before its final
  approach, a take-off climbing away) the screen shows the plane's photo full size, with "Expected in … min" for a
  landing; close in, the photo slides into a corner and the radar shows the runways up close (1.26). Home airports
  other than Vienna need relay 23.
- **Board styles**: classic white on black, Frankfurt yellow on black, or white on blue, each with its own typeface
  (Settings → Styles, or `?theme=frankfurt` / `?theme=blue`).
- **Styles to unlock** (1.59, relay 51; Settings → Styles on the board, in the app and the light version). Since 1.61
  the Styles cell has two buttons, Look (the board style) and Badge, each with its choice on a small display, and the
  count unlocked under them; both open the Styles card: a live preview on top (the logo with the badge, the title in
  the chosen colours, three flaps in the chosen finish), then the rows Board, Colours, Flaps and Badge, each stepped
  through with ◀ ▶ (on a remote: Up/Down picks the row, Left/Right or OK steps). Locked choices show dimmed with a lock
  and what unlocks them under the row; unlocked ones apply at once. **Colours and flaps only change with the Classic
  board**: with another board style those rows are greyed out and the board keeps its own colours and flaps (the
  choice stays saved for when you go back to Classic). The default look stays until someone picks something. Unlocks
  are the profile's own, from its logbook's game:
  - The owner can also unlock styles by hand for a profile on the admin page (relay 52: Unlock all, Back to earned only, or pick styles); they count like earned ones, without a pop-up.
  - Since 1.72 by **level**: Heathrow yellow 2, Star 3, Black on white 4, Solari green 5, Propeller 6, Brass trim 7,
    Frankfurt 1970s 8, Ice blue 9, Helicopter 10, Worn enamel 11, Sunset 12, Jumbo 13, Tokyo night 14, LED dots 15,
    Fighter jet 16, Concorde 17 and **Gold leaf** 18 (black lacquer flaps, gold-leaf letters, a gilded rim). **First
    Class** (claret leather with a stitched seam, cream flaps with claret letters) is for last week's league winner,
    that week only. Styles picked before 1.72 stay.
  - LED dots: since 1.61 a real 5x7 dot font on dark flaps, readable on a TV.
  - **In the app since 1.110**, Settings → Styles (Look or Badge, or Try it after a level-up) is a **gallery** on a page
    of its own: tabs **Board · Ticket · Badge**, each a two-column grid of preview cards (the style in its own colours
    and font, the ticket in its design) marked IN USE, ✓ YOURS or 🔒 with what unlocks it ("Level 14", "A gold medal",
    "Last week's winner"). Board has the board styles, then Classic's colours and flaps in a section of their own
    (they only show with Classic). A tap slides up a card with a big preview, what it is, a bar towards its unlock (the
    points to that level, or the trophy closest to a medal of that metal) and **Use** (off while locked). The TVs keep
    the card with rows.
  - **Ticket designs** (1.110, the app): the eras of flying, each won with the **first medal of its metal** in any
    trophy ladder: **Propeller age** (1950s: ruled cream card, red carbon ink, a serif heading and flight number, a
    serial number and a conductor's punch) with the first silver, **Jet age** (1970s: warm cream, round corners, a
    sunburst and three stripes) with the first gold, **Magnetic card** (1990s: a white boarding pass in capitals with a
    security pattern and the brown magnetic stripe) with the first platinum, **Hologram** (pearl foil, a holographic
    patch on the stub) with the first diamond. Every pass comes in it (a plane's ticket, the scan's, the streak's, the
    limit's); the band and the stub keep the plane's rarity, a **golden ticket stays gold foil**. The owner can grant
    them by hand like the other styles (relay 93).
  - **Title badges**: Star, Propeller, Helicopter, Jumbo, Fighter jet, Concorde. Since 1.61 the
    badge takes the plane's place in the yellow logo square, the browser tab's icon and the web app's home-screen icon
    (relay 53 gives the profile a manifest with that badge's icons; an installed icon changes when the phone next
    refreshes the app's manifest, which the browser decides, often within a day of using it; adding it to the home
    screen again changes it at once). The Android app's own launcher icon stays the plane (it is part of the APK).
  - **Board styles** for the rarest trophies: Frankfurt 1970s (Unstoppable) and Tokyo night (Completionist), next to
    Classic, Frankfurt and Blue. Not in the light version.
  A new unlock pops up like an achievement.
- **Sounds** (1.17): the Settings controls play short recordings of the real things: a rotary switch, a rocker
  switch, a thumbwheel and a push button (1.97.2: the big push buttons, the rail and the bottom bar keep their thock; small
  buttons, chips and × have a crisp click, and opening a card, a row or a tab a light tick; since 1.97.4 the Logbook's Saved places button, the Sky view buttons and the title's Overhead / Airport switch
  have the crisp click too; 1.97.8: a scan's ticket tears with a recorded paper rip, and the daily streak's ticket tears
  off after it, the fireworks bursting from the first tear); the flaps keep their synthesised clack (credited in About; see
  [tools/sounds/](tools/sounds/README.md)). (The Sounds switch for the older synthesised ones was removed in 1.33.)
- **Realistic look** (Settings → Display, on by default): flaps printed on two cards, a fine grain on the plastic,
  light from above, a turning flap catching the light, glass over the board, brushed metal plates and metal knob caps.
- **Worn hardware**: modules sit very slightly out of line and the odd flap hesitates or catches, and the panel has
  some honest wear: fine scratches, polish marks, grime in the corners, paint rubbed off the edges, a few small dings.
  Can be turned off.
- **Quick flaps** (Settings → Display, 1.14): every flap still turns through its letters and words, but as a blur,
  and the whole board lands on the new text in about 1.5 seconds. Flap speed % doesn't apply while it is on.
- **Night mode**: dims the board and mutes it between set times (22:30 to 07:00 by default; `?night=0` turns it off).
  In the app and the light version (1.57) it is quiet hours: no chimes, dings or flap sounds while the app is open
  (Settings → Night: Night mode, Quiet from, Until); the screen isn't dimmed.
  **At night** (Settings → Night, 1.53) picks DIM (the dimmed board) or NIGHT VIEW: during those hours a black page
  with just the clock, the plane on top (flight, route, type) and today's count in dark red, so it doesn't light up
  the room. Any key, tap or click brings back the (dimmed) board for a minute; that first input does nothing else.
  `?nightview=1` (or `0`) sets it from the address.
- **Share a plane** (1.53): the plane card's **Share** (on a computer, in the phone app and the light version; not on
  TVs) makes a picture: the plane's photo (or its model's) over a split-flap panel with the flight and airline, the
  route, the aircraft, the registration and the time, and a small Fallblatt mark (no link). Then **Share** opens the
  phone's share sheet (WhatsApp and the like; in the Android app its own) and **Save picture** downloads it. Since 1.82.1
  every picture made to share (a plane, the year, week and month, Sky view's snapshot) says **Spotted by** and your first
  name. The
  photo comes through the relay (relay 47) so the picture can be saved; with an older relay a model photo from
  Wikimedia still works, an aircraft's own photo is left out. Since 1.93 a Planespotters.net photo is never in it
  (their photos may not be passed on): the picture takes the plane's airport-data.com photo or its model's, with its
  credit.
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
APK is only needed when the app itself changes (see [android/](android/)). Since 1.71.1 the app fetches those
itself: every time it opens it offers a newer build when GitHub has one (Update or Skip), and Settings → Device → Check for app
updates looks at once; Android asks once to allow installs from Fallblatt, then confirms each update. Chrome can't install `/app/` itself as an
app, because it installs web apps only from https addresses and the relay is plain http.

In the Android app (1.97.5) the back gesture or button closes what is open first, one layer at a time: a pop-up, a first-time
tip, a card, then Sky view's card or Sky view itself (back to the board), About or the Log, a plane opened in a list, and then
any tab other than Now (back to Now). On Now with nothing open it leaves the app, which stays in the background; the
welcome does the same. Back makes no sound. The web app (1.97.7, in a browser or added to the home screen, an iPhone too) does the
same with the browser's back: it closes the same layers one by one, and on Now with nothing open back leaves the page as usual
(closing an installed web app). The tab stays in the address (`#logbook`), and switching tabs does not add steps to back.

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
  latest planes spotted. **Recent flights** (1.95) is a timeline: a line down the left with a dot for each plane in the
  colour of its remark, grouped by quarter hour ("Now · 14:45 – 15:00"), each plane in its own box (1.103.1), two slim lines a plane (time, flight, route,
  remark; then airline, type, closest distance and height), "8 in the last hour" at the top and "All 64 planes today ›"
  at the end, which goes to Today. A plane without a flight number shows its registration (or its owner); without a
  route the row says "No route: private or local flight" or "Route not known". **Tap a plane** and its card opens right
  there: the row grows downwards into the card, the rows below slide down and the card's content fades in (since
  1.97.1; just opens with less motion on); the photo (Planespotters' first, its credit a link to the photo's page) opens the
  plane's whole card, the airline, the places and the Aircraft box theirs, and ⌃, the bar it sits in or another plane folds it back.
  In the Airport style a Take-off / Landing switch picks the plane on top (it alternates by
  itself every 20 seconds; it stays when one side has no plane), with the runway screen in place of the photo, and the
  take-offs and landings below as split-flap rows (1.36; tap a row for the plane, its place for the airport).
- **Today**: today's numbers on flaps, the day's highlights (1.111: the lowest and highest pass and the fastest side by
  side, the figure first and the plane under it; the most seen airline and aircraft types as bars, counting only what
  came at least twice; the newest plane new to the logbook; from 21:00 the Plane of the day first). Tap a plane named
  there and the list below scrolls to it and lights its row for a moment (a filter that hides it is cleared). Then every
  plane spotted today, with the same filters and legend as the board, and the same filter box.
  Since 1.95 the list is the same timeline as Recent flights, grouped by the hour, and a tap opens a plane's card in place.
  Since 1.72 Special lists special planes only, and Favourites has a filter of its own.
- **Panels** (1.83): every part of the Logbook (Totals, the year, week or month, Categories, Aircraft types, Airlines,
  Most seen aircraft), Spotted today (Today in numbers), the Spotters' Club (Your level, League, Your catch, Your
  hangar, Records, This week's bingo, Trophies) and the radar's Nearest list sits on a plate of its own, like Settings':
  screws in the corners, its name engraved between two lines, level with the top screws (1.83.1).
- **Logbook** (1.55): a switch at the top for the views (Logbook and Week & month; Collection and Records moved to the
  Game page in 1.72); the place buttons only under Logbook. Logbook: the totals, most seen model, categories, top aircraft types and airlines, most seen aircraft.
  Since 1.91 the **Logbook and Spotters' Club tabs stay at the top**, under the header, while either page scrolls, and
  whatever opens has a chevron in a small ring: Saved places, the categories (turned up, the ring amber, while one is
  open) and the Favourites & hidden list picker.
  The search (1.65) finds places too since 1.81 (relay 63): a town, an island, a country or a saved place, and each
  result has a line with a pin naming where it was seen, newest first (the aircraft's card says Seen from). Sightings
  on the go from before relay 63 only know their country (their place was guessed from the day's planes).
  At the top (1.28, relay 29), **the year in planes**: planes, types, airlines, airframes, countries and days, the
  busiest day, the most seen aircraft and the rarest, with **Share** (a picture of the card) and **Download the
  logbook (CSV)**, every sighting as a spreadsheet. Collection: points, tiers and the collections. Records: the
  records, this week's bingo and the trophies with their bars. Week & month (1.52, relay 46): **this week or month in
  review**, with Week / Month and ◀ ▶, and since 1.80 its own **Share**: the year's picture with the week's or month's
  dates, numbers and facts. The pictures open in a card with Share and Save picture, as a plane's does.
- **Where to look** (Now, upright, 1.28): the direction and height of the plane on top ("LOOK SE · 32° UP") on a dial
  with north up, under This aircraft's picture. On https (the public address) it turns with the phone so the arrow
  points at the plane: by itself on Android, after tapping the dial once on an iPhone (which asks first). When it
  can't point (1.80), it says why in its place, dimmed, with the tape grey: no position yet, no height yet, too far
  (over 80 km) or a position that doesn't add up.
- **Sky view** (Now → Where to look → Sky view, 1.30; https only; since 1.72.4 a Sky view card under the board when there
  is no plane on top, so it can always be opened; 1.77: in Where to look's style, saying "No planes around right now",
  its tape a compass). It comes with live location (1.77): with live location off, a card asks first ("Go live and
  open" or "Not now"), since Sky view shows the planes around you wherever you are: the camera full screen, with a label on every plane
  within 60 km that is in the picture (flight, type, height, distance; the plane on top in amber, and an arrow at the
  edge when it is out of the picture). It works from the phone's own location (or the place in Settings), the compass
  and the tilt, and moves each plane on along its track since the last position. Since 1.75.2 it counts from when the
  data was made (the relay may keep it a few seconds), follows a plane round its turn and up or down its climb, and
  makes heights true with the home airport's air pressure and temperature (from its METAR; with live location the airport
  nearest you), looking from the phone's own height above the sea (its GPS, 1.76.1: on a hill or a cliff top planes
  below you show below the horizon); the ring has marks on all four sides; it works upright or
  sideways and keeps steady pointed straight up. Since 1.86 the phone's gyroscope moves the labels, so they stay on the
  sky as you tilt and turn; the compass only says where north is. Since 1.90 north only glides towards the compass
  slowly (over several seconds, even slower while the phone turns or the compass is unsure), so labels stay put while
  you hold the phone still, also indoors where compasses swing; when the compass settles steadily somewhere else (it
  often comes right a few seconds after Sky view opens), north glides there within a few seconds. Since 1.95.0.2 the
  labels are placed on every frame from where the phone points at that moment (its last reading carried on at its
  turning speed), so they move smoothly while you turn the phone even when the browser hands the readings over late.
  Since 1.76 the compass's magnetic north is turned into true north (NOAA's World
  Magnetic Model; about 5° here). Phone compasses are often a few degrees off, sometimes far more: drag the picture to
  line the labels up with the planes (kept on the phone; **Reset** undoes it). The sun and the moon (1.76) sit in dashed
  rings where they really are: drag until the real one is in its ring, and every label lines up too (on the screen;
  don't look into the sun). Since 1.90, when the sun or the moon is up but out of the picture, a dashed arrow at the
  edge points to it with how far to turn ("☀ SUN · 139° right"), and a **compass ribbon** above the hint shows the
  whole compass round the way you face, the picture's width in a gold frame and the sun and the moon at their bearings
  with how high they are. Once lined up (a drag or AUTO), north stays put and the compass is left out until Reset or
  Sky view closes. **AUTO** (1.76, the pill under the title; tap to switch it off) lines the labels up by itself. Since
  1.86 it finds the sun anywhere in the picture, however far off the compass is (up to 45°): while the sun is up and
  nothing is lined up yet, the hint asks you to point the phone near it for a moment; gold corners then frame the sun's
  ring ("lined up · sun"). It also looks for nearby planes: where it keeps finding one close to its label it slides
  the labels onto it (gold corners mark the plane; "lined up · 1 plane"). It skips planes too far to see, labels close
  together and the sun's glare, and ignores cloud edges and contrails; a drag takes over for a few seconds.
  Since 1.66 a ring sits in the middle: keep a plane in it for a second and a half and its card opens (the ring fills
  meanwhile; it opens again only after the ring was empty). When the heading jumps about while the phone is held still (1.90: only on phones without a gyroscope reading),
  the compass swings against the gyroscope (1.86), or the iPhone says its compass is poor, a note asks for a figure of
  eight or a drag (not once the labels are lined up). **Report** (1.90, the flag in the top bar, the owner's phones
  only): sends the relay what Sky view knows about the compass (the sensors' readings, north as in use, what AUTO found
  and how far off the sun's ring was; no picture and no place), to tune Sky view from real phones; the hint says what
  was sent.
  **×2 and ×5** (1.99, the round buttons on the right under the top bar): zoom in for a closer look; the one on is lit
  gold, a second tap goes back to ×1, and so does leaving Sky view. Where the phone's browser offers it (Chrome on most
  Android phones) the camera zooms itself (sharper); elsewhere (iPhones, other browsers) the picture is enlarged. The
  labels, rings and arrows stay on the sky, a drag moves them as far as the finger, and the ring catches as much sky as
  at ×1 (so it is drawn bigger).
  The phone asks for the camera and the motion sensors the first time. Tap a plane or its label (1.63) for its card:
  photo, route, details, Favourite and Hide, as on the radar; tap it again or × to close. **Snapshot** (1.80): once a
  plane in the picture is locked on (1.90: once the ring has filled on it in this Sky view), a round shutter appears above the hint (or above the plane's small card): it keeps the sky as on the
  screen, labels and all, with a band under it (Fallblatt, "Sky over" the place, the date, time and how many planes),
  to share or save.
- **The opening** (app): the logo, FALLBLATT flipping in letter by letter like split flaps (1.77), and the plane taking
  off as the board shows through. With sound on it plays the board's clack for each letter and a whoosh for the
  take-off, where the phone lets a page play sound before the first tap (the Android app; never on an iPhone); not in
  quiet hours.
- **Daylight** (1.66; app and light version, Settings → Display): a cream page with black flaps and white letters, dark
  text and darker labels, easier to read outdoors in the sun. Each phone keeps its own choice (not shared with the
  profile); the boards on the TVs don't have it.
- **Search the logbook** (1.65, relay 55): the field at the top of the Logbook tab searches every sighting since the
  start, by registration, flight, type or airline (several words narrow it). Each match says how often and when it was
  seen and how close it came; a flight lists the aircraft that flew it, an aircraft the flights it flew. Since relay 63
  it also finds where a plane was seen: a saved place's name, or on the go the town, the area round it or the country
  ("Oia", "Santorini", "Greece"; the relay names the phone's place, to about a kilometre, in the background).
- **Notices** (1.65): saving answers with a short notice above the tabs (at the top while a card is open): Favourite and
  Hide with **Undo**, a failed save with **Retry**. Settings that can't reach the relay wait on the device and are sent
  again (1.64); Settings say **Not synced yet** meanwhile.
- **Home-screen widgets** (1.67, Android app, relay 56): long-press the home screen → Widgets → Fallblatt. **Plane
  overhead** (4×2) shows the flight on split flaps, its status, airline and type, route, distance, direction and
  height, and today's count; **Plane overhead, one line** (4×1) the flight, type, route and distance, its plane mark in
  the status colour. Both use the app's sign-in, refresh about once a minute while the screen is on, and open the app
  when tapped. They show the profile's place (the relay's `/now`).
- **Look up now** (1.67, relay 56): a "worth going to the window" notification counts down after it rings: every half
  minute it is replaced, silently, by "… · overhead in 1:30" with a bar of the wait, and under 50 seconds it rings once
  more as **Look up now**, with where to look and how high. Settings → Notifications → **Count down to the plane**.
- **Settings** also holds (1.34) Account, Notifications and this device (Full board, Sign out, Change relay); About keeps
  the version, the legend and the patch notes. The app doesn't zoom on a double tap.
- **Jump bar** (1.88): under the header, Settings has a bar with the names of its parts (Location, Traffic, Display,
  Flaps & sound, Night, Favourites, Account, Notifications, Device, About). It stays at the top while Settings scrolls
  and scrolls sideways; tap a name to go to that part. The part on screen is lit.
- **Relay** (1.88, relay 69): only the relay's owner sees this plate at the top of Settings → About: each position
  source with its role (first, in reserve, emergencies only) and state (working, resting until a time with the error
  code, standby, failing), adsb.lol's requests today of its daily 500; Flightradar24's credits this month of the
  budget, today's credits and lookups and the gap filler's share; last night's backup (amber when none is reported or
  it is over 36 hours old, red when it failed); and the screens online, by profile and device. It refreshes every
  30 seconds while About is open.
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

### Light version and Glass (parked)

The light version (`/light/`, 1.39, the phone app without split flaps) and the Glass preview (`/glass/`, 1.71, a
light, map-first design made with Google's Gemini) are parked since 1.71.3: their addresses open the phone app, and
Settings → Device no longer offers them. Their source stays in `tools/light/` and `tools/glass/` for later; reviving
them means bringing `light.js`/`glass.js` up to date with the app and building again (`py tools/light/build.py`,
`py tools/glass/build.py`, which overwrite the forwarding pages).

**Remote key test**: `http://<relay>:8080/keys/` lights up each remote button that reaches a web page (arrows, OK,
Back, colour keys), to see whether a TV's browser passes them on (the first step towards navigating the board with
the remote).

## Controls

- Click the board, or press **F**, for fullscreen.
- Press **S** for settings.
- Press **A** for About: patch notes, the keys and who made it.
- In the Logbook the arrow keys move a ring from plate to plate (and up to the buttons); Enter opens the plate's list,
  Esc closes it.
- On This aircraft, the up or down arrow puts the ring on a Planespotters.net photo's credit and Enter opens the photo's
  page (1.93).
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
- The cards' facts (1.94, relay 74): [Wikipedia](https://en.wikipedia.org) (its words are
  [CC BY-SA](https://creativecommons.org/licenses/by-sa/4.0/): each card links the page) and
  [Wikidata](https://www.wikidata.org) (CC0), read by the relay's `/facts` once per page and kept about 30 days: a
  model by the Wikipedia page the board found for it (its infobox and specifications), an airline by its ICAO code, an
  airport by its IATA code. Photos for airlines and airports from Wikimedia Commons. `/logbook/spotted` counts, over
  your whole logbook, the sightings and different aircraft of an airline or a model and the flights to or from an airport.

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
again updates the relay and keeps your settings and logbook; first it saves `data/` as
`/root/data-before-relay<new version>.tgz` and keeps the newest three of those copies (relay 68). Set the machine's time zone (`timedatectl
set-timezone Europe/Vienna`): the logbook's days follow it. The relay's messages: `journalctl -u overhead-relay -f`.
Moving from another computer: stop the relay there and copy its `overhead.json` and `data` folder into
`/opt/overhead-relay` (then `chown -R overhead:overhead /opt/overhead-relay` and restart the service).

Then open `http://localhost:8080`, or `http://<computer-name>:8080` from the TV, tablet or phone.
The relay prints the addresses when it starts. Your location stays on the relay machine: it is handed
to the board when the page loads, so nothing personal lives in this repository.

Airline names (relay 68): the route database names the airline only together with a route, so the relay also keeps
Virtual Radar Server's airline list (public domain) in `data/airlines.json`, downloaded at start and refreshed weekly
(the old copy stays if a download fails; without it, flights simply have no name). A flight with no route listed gets
its airline's name and code from it, in Spotted today, the logbook, search and the CSV, and the live views ask the
relay for airlines the board's own table lacks (AER LINGUS instead of NO AIRLINE LISTED). Older sightings got their
names once, on the first start of relay 68.

The cards' facts (relay 78): the relay keeps the facts of every airline still flying, every airport with an IATA
code and the board's aircraft models in `data/facts.db` (SQLite, read card by card, about 15 MB), so a card opens at
once. Once a month, between 04:10 and 06:00, it refreshes them from Wikipedia, Wikidata and Commons in the
background (in batches, one request at a time; about 40 minutes and 400 MB). What one night doesn't finish goes on
the next. Anything it doesn't have yet (a rare model) is looked up on the card's first tap and kept. On its first
start relay 78 moves the facts relay 74–77 kept in `data/facts.json` into the database (the file stays as it was).
The owner can see the database at `/facts?status=1` and start a refresh with `/facts?refresh=1`.

Positions come from adsb.fi, adsb.lol and airplanes.live, tried in that order (since relay 68 adsb.lol is kept in
reserve for when adsb.fi fails, so its 500 requests a day last). A source that answers
"too many requests" or "forbidden" is rested for a while and the next one is used; if all of them fail,
the relay keeps serving the last good data for up to two minutes. adsb.lol allows each address 500 requests a UTC
day (since October 2026; more only for its feeders), and airplanes.live answers only those it has let in. When a
source says its day's allowance is gone, the relay rests it until the allowance starts again (relay 66) instead of
asking every 10 minutes. Only when all three fail or rest does it ask
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
Settings has unsaved changes. The board's footer lamp stays too. Since 1.82.0.1 a press on the notice itself doesn't stop
its countdown, and refreshing shows at once: the phone app covers the page with its opening (the logo and FALLBLATT),
which the new version carries on until its board is ready; a board says Refreshing … in the notice.

**The first picture (1.51).** Each screen keeps the last known board in the browser (the plane on top if it was there
in the last half hour, Spotted today and Today in numbers of the same day), per profile, and shows it at once when it
loads, marked **Last known board · not live yet**, until fresh data comes a moment later. In the phone app the tag
stays under the opening (1.87.1), so it only shows when the board still isn't live once the opening has gone.

**Health watch (relay 45).** The relay sends its owner (the profile named David) a notification when every position
source has failed for more than 15 minutes, Flightradar24 refuses the key, the data disk is over 90% full, or the relay
restarted unexpectedly (not after a normal stop or update), and once when the problem is gone; at most one alert an
hour of each kind. Each is in the relay's log too, and `/status` lists the state under `health`.

**Screens (relay version 12).** The relay keeps track of which screens are using it and prints them in its window
as they connect, reload the board and go away, with what it knows about each: the screen's name, the device (Samsung
TV, Fire TV, LG TV, a PC or phone and its browser), its address and network name, which board it shows, how big it is
drawn and how long it has been on. Press **Enter** in the relay's window for the current list, or open
`http://<computer-name>:8080/screens`; the board's diagnostics panel lists them too. The boards and the phone app send their
name, size and drawing quality; a screen that hasn't asked for anything for a minute counts as gone. Since relay 80 an
app in the background (its latest hello says hidden) counts as left after 15 seconds, whatever it asks for meanwhile: it goes
to "Recently gone" (left at the time it went to the background) without a log line, and when it comes back (a hello saying
visible) it is a new visit that isn't announced again.

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

`CLAUDE.md` has the working rules, `docs/architecture.md` how the pieces fit together. To try a change without touching the
real relay, `py tools/test/run_test_relay.py` runs a test relay with made-up flights at `http://localhost:8096/` (with a signed-in
test profile: open `http://localhost:8096/test-signin` once in a browser; the made-up flights play out in the first few
minutes after it starts; `--port 8296` runs it on other ports, so test relays of several checkouts don't answer for
each other, and `smoke.py` takes `--port` too);
`tools/test/shoot.py` takes screenshots of it, and `py tools/test/smoke.py` loads every page against it and fails on
a page error (`--syntax` checks that the scripts parse, with Node). GitHub Actions runs both, the relay's compile check
and an up-to-date check of the app on every pull request (`.github/workflows/check.yml`). The phone app is built from the test board's code with
`py tools/app/build.py`, so it gets new features together with that board. `py tools/codemap.py` shows where each
part of the code lives, area by area, in every file (`docs/code-map.md`); `smoke.py --syntax` also checks that every
function and CSS rule is on that map.
