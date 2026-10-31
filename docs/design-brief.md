# Fallblatt: the design brief

The one design document for the phone app and the board. **Read it before any visible change or mockup.** Part 1 is
the rules that keep the app simple; they are checks and budgets, not taste, and they win over anything below them.
Part 2 is the identity that stays, part 3 the app as it is today, part 4 where the code is and what the screens can
bear. Where this document and the code disagree about what exists, the code wins; about what is allowed, this wins.

## 1. Rules for staying simple (Dave, Oct 2026)

Why: a new user got lost in "a lot going on on the screen" (29 Oct); every screen was redesigned (1.115–1.119.1), and
two days later mockups again carried sentences and a second row of tabs. These rules are budgets, so that it stops.

**Text**

1. **At rest, a state shows a label and a value, nothing else.** A label is at most three words ("Standby ready",
   "Standby used Saturday"); a warning may add what to do on the same line ("No standby left: scan by 23:59"). No
   sentence on a card, row, chip, ticket or pill at rest. Shorten before truncating.
2. **The label opens its own explanation when tapped** (a bottom sheet). Sentences live only in there, and the sheet
   is two short lines: what it does, then what you will see ("Miss a day, and your Standby is automatically consumed
   to keep your streak going" / "That day shows SBY and pays no points. Resets on Monday 00:00"). The (i) by a title
   explains a whole screen or panel (the Radar, How points work on the Level plate), never one label. "It isn't
   clear" is answered with a tap target, never with a sentence added to the card.
3. **At most one line of help per screen, and only in an empty state.** Everything longer goes behind the (i).
   Dave's exceptions: the welcome and the tips speak unasked, one step at a time.
4. **Every number carries its name** (a small label above or beside it); never two bare numbers side by side.
5. **A notice that names a mechanic says what kind of thing it is and what to do**, in that order, and opens its
   explanation on a tap: "Trophy On a roll: points 2 more days", not "2 more days for On a roll". Test: someone who
   has never opened the Club understands it.
6. **Three vocabularies, three looks.** A flight's status is a pill: Recent flights on Now shows every status word, and
   Today's rows show none (TAKE-OFF and LANDED on Airport). A logbook note is a mark at the row's end, no words: Sky
   view's amber target for a scanned plane, ★ new type or airline, ⚑ unusual (red for EMERGENCY, orange for DIVERTED on
   Today), pink ♥ favourite; Recent flights drops the mark its pill repeats and has no target. Today's bubble is the
   plane's rarity colour, Recent flights' its status colour; the word is on the card. Game words (points, level,
   standby, league) stay off a flight's row; they live in the Club, the header chip, and the tickets and notices about
   them.
7. **Plain words, no cut-offs.** Screen titles in sentence case; every sheet carries the plate with its engraved
   title, like the Settings and Logbook panels; section headings as small-caps labels. No addresses, codes or
   internals ("from the home relay", not a host name). Dave's exception (31 Oct): Recent flights' route and type may
   cut off at 360 px, beside the pill. A panel may carry one small footnote engraved like its title (`.plFoot`) for a
   fact that belongs to the whole panel ("Resets Mon 00:00"); it is no sentence and opens nothing.

**Navigation**

8. **Five keys in the bottom bar.** Never a sixth; a new area lives inside one of the five.
9. **One row of tabs or segments under the header at most.** No exception.
10. **Three taps from the bottom bar to any fact at most**: a key, a tab, a row or card. A fourth level means a level
    has to go.
11. **Panels, not pages.** Anything that opens rises as the bottom sheet with the original plate inside (screws,
    engraved title): no sliding pages, no back header, no new routes. Things that expand in place keep doing so. A
    card with a detail panel opens it on a tap anywhere on the card, with no extra "All N ›" row for it; index rows
    (a label and a one-line state) stay, they are the way into a panel of their own. The Logbook's All time numbers
    open their lists, so that index is gone (Dave, 31 Oct).
12. **The first screenful answers the screen's question.** Now: what is over me. The Logbook, one screen: what came and what I have ever
    seen, Today's plate first. Club: how am I doing. Radar: what is around.
    Settings: what can I change. The rest after a scroll or a tap.
13. **Empty things fold away.** A category with 0 is hidden or folded with a count. A list inside a card or panel stops
    at five rows and "All N ›" opens the rest; the list a screen exists to show (Today, the league, search) runs on.
14. **A feature that wants more room gets none by default.** It gets a row in an existing index (label and a one-line
    state) that opens a panel, or a line in an existing panel. A new page, tab, key, row or setting must name the one
    question of its screen that nothing answers today, and must replace or absorb something; a new setting also needs
    a default that spares most people the setting.

**Looks and working rules**

15. **Reuse before you style.** A new element takes the class of the existing one with the same job (index row, chip,
    (i), cBtn, bottom sheet, pill, segmented filter); two similar elements that differ are reported, not joined by a
    third. Nothing moves unless a state changed, and `prefers-reduced-motion` is honoured. An
    **amber name on a number means the number opens something** (Dave, 31 Oct).
16. **Panels of one kind are twins**: the week, month and year panels show the same facts in the same order at the
    same height; the same for any other repeated panel.
17. **Three options for every design choice** (PNGs at phone size, an MP4 where it moves, with a recommendation), sent
    before building. Plain bug fixes need none.
18. The process rules live in `CLAUDE.md` and are not repeated here: test first, every visible text through `T()`
    and no new translations, don't rename statuses or remarks, versions and patch notes, removed on request, no
    secrets, the focus on the phone app and the board in English and the default look.

**The check** (before sending a mockup, before opening a PR)

- Read every card at rest: a sentence? Move it behind a tap. A number without a name? Name it.
- Count: keys = 5, rows of tabs ≤ 1, taps to any fact ≤ 3, help lines per screen ≤ 1.
- Each new page, tab, key, row or setting: what did it replace, or which row does it sit behind?
- Each notice or ticket: does a stranger know what kind of thing is named and what to do?
- Each new element: which existing class? Repeated panels: same facts, same height? `CLAUDE.md`'s rules kept?

Dave settled these on 30 Oct 2026; earlier notes saying otherwise are superseded: panels, not pages; a star only for a
logbook note; pills only as in rule 6; the Club's own key with five kept; `CLAUDE.md`'s version rule; sentences only
in the sheet a tap opens; the engraved plate title on every sheet.

## 2. What stays (the identity)

- The **split-flap look**: flaps turning through a drum of characters, with sound. It is the product; refine it, don't
  replace it. The board, the flaps, the metal and the colours stay as they are.
- **Amber on black**: `--amber:#f0b429`, `--housing:#0b0b0c`, `--ink:#f3f0e8` (in `tools/app/head.html`); the board's
  `THEMES` (classic, frankfurt, blue) in `test/index.html`.
- **The logo**: an amber rounded square with a dark plane (app icons in `app/`, the splash and the welcome in
  `tools/app/head.html`). No emoji for it; iPhones draw them in colour.
- The **status words and remarks** (OVERHEAD, INBOUND, SUPERJUMBO, …): words and order stay; colours and drawing may
  change (`REMARK_LOOK`). The **rarity tiers** and their colours and icons (`TIER_COL`, `drawTierIcon`): common,
  uncommon, rare, very rare, special.
- The engraved plate titles (gold capitals) on the cockpit, the lists and every sheet; the plain checkboxes.
- **Removed on request, don't bring back**: the list in `CLAUDE.md`. The flap clock left the app's header on 30 Oct
  (Dave's pick) and doesn't return.

## 3. The app today (1.123, 31 Oct 2026)

- **Header**: the logo, the style name with the switch to the other style (Overhead ⇄ Airport), the place and radius,
  the points-and-level chip top right ("9,950 pts · paused", "LEVEL 9", the rank's lapel in a progress ring to the next
  level), the connection dot. Nothing else goes in the header.
- **Bottom bar**: Now, Logbook, Club, Radar, Settings (four without the Club when there is no game: demo mode, no relay, an old relay).
- **Now**: the checklist bar for a new user, the plane overhead on the flaps, its picture, the Sky view row, recent
  flights, the notices bar; scan tickets and undo notices rise from below.
- **Logbook** (1.123): one screen. The search with the filter icon at its end, stuck under the header; a sideways strip of three
  twin plates, each a gold name and four named numbers: Today (a tap opens "Today in numbers"), All time (amber names: each number
  opens its list; Categories, Most seen aircraft, Aircraft types, Airlines, with Counting since as a footnote) and the period (a tap
  opens Week · Month · Year, with the CSV under More). The icon opens the segmented filters, this place / All places and Saved
  places in place under the strip. Then the timeline rows (a rarity bubble, time, flight, route, type, marks at the end, no pills).
- **Club**: sub-tabs Level, League (with Bingo and Trophies under it; League and Bingo with the weekly reset as a
  footnote, Trophies' counts on its switch), Hangar, Passport, Cards. The week on the level card opens the Streak panel.
- **Radar**: title, (i), a cogwheel chip with the range that opens the range-and-map plate, the radar, the Nearest table.
- **Sky view**: from Now; the align button in the top row (a circle, the camera or the Align button lines the labels up on the
  sun or moon), a mini radar bottom left, edge chips for at most three off-screen planes, the count "4 around".
- **Settings**: an index of sections (Location, Traffic, Display, Flaps & sound, Night, …) each opening a cockpit
  plate as a panel with Save; closing unsaved asks. About: rows that open panels (versions, log, connection).
- **Welcome and tips**: one question with one big button per step, the alternative a plain link, Skip small.
- **Sideways**: the board only, full screen. **Android app**: a WebView of the phone app.

## 4. Where the code is, and what the screens can bear

| File | What is there |
|------|---------------|
| `tools/app/head.html` | The phone app's markup and CSS: colour and `--fs-*` type tokens on `:root`, the welcome, the splash, tabs, lists, panels. |
| `tools/app/main.js` | The phone app's layout and glue (`heroLayout`, `fitSideways`, `buildTabs`, `TABS`, the welcome, the lists, the row model). |
| `test/index.html` | The whole board in one file: flap engine, `drawStatic`, `THEMES`, `REMARK_LOOK`, `drawRadar`, `COCKPIT`, `CHANGELOG`; translations in `test/i18n.js`, sounds in `test/sounds.js`. |
| `app/index.html` | **Generated** by `py tools/app/build.py` from the three above. |
| `index.html` | The main board (`CLAUDE.md`: test first). |

Find things with `py tools/codemap.py AREA` and read small ranges; never a big file whole (`docs/code-map.md`); the
full Files table is in `docs/architecture.md`.

- **TVs are weak.** Fire TV and LG run at 1080p and 30 fps (`WEAK_TV`, `LITE()`). Anything heavy (blur, big shadows,
  per-frame gradients, canvas filters) needs a light path. Flap faces are pre-rendered and cached by `tile()`; keep
  per-frame drawing cheap.
- **Phones**: upright and sideways (`(orientation: landscape) and (max-height: 600px)`), from a small Android phone to
  an iPhone Pro Max, notch and home bar included (`env(safe-area-inset-*)`, `--cut-l`, `--cut-r`). The page itself
  never scrolls sideways (once an icon drawn past the edge gave the whole app a sideways scroll); elements that move
  sideways, like the hangar's shelves and the member cards, are fine, and more may come where they fit. Font sizes
  only from the `--fs-*` tokens (`smoke.py --syntax` checks).
- **Fonts and libraries**: the typefaces are served from `fonts/` (no Google Fonts at run time); plain HTML, CSS and JS,
  no frameworks.
- **Trying it**: `py tools/test/run_test_relay.py`, then `http://localhost:8096/app/`; `PHONE=390x844 py
  tools/test/shoot.py URL OUT …` for screenshots; details in `CLAUDE.md`, "Testing a change".
