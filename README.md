# MedoraEvents

Everything happening in Medora, North Dakota, and the towns around it, in one calendar. GitHub Actions pulls from local partners' calendars every day, removes the duplicates (the same event is often posted in five places), and publishes **https://medoraevents.labs.trlibrary.com**:

| Output | URL |
|---|---|
| Widgets | `/widgets/upcoming.html`, `/widgets/browse.html` (search + filters + load more), `/widgets/month.html`, `/widgets/week.html` |
| Embed loader | `/embed.js` |
| iCal | `/calendar.ics` (special events), `/calendar-all.ics` (incl. daily activities), `/ics/medora.ics` (in town), `/ics/nearby.ics` (out of Medora), `/ics/free.ics`, `/ics/{source}.ics` |
| JSON API | `/api/v1/events.json`, `upcoming.json`, `months/YYYY-MM.json`, `sources/{id}.json`, `sources.json`, `fields.json`, `review.json` |

Sister project: [TREvents](https://github.com/Theodore-Roosevelt-Presidential-Library/TREvents) (Theodore Roosevelt events nationwide). Same engine and widgets.

## Sources (priority order — when the same event appears in several, the first one listed wins)

| id | Source | How it's read |
|---|---|---|
| `trpl` | Theodore Roosevelt Presidential Library | sitemap → event pages |
| `nps` | Theodore Roosevelt National Park | NPS Data API (`NPS_API_KEY`) |
| `medora` | Theodore Roosevelt Medora Foundation (medora.com) | Modern Events Calendar iCal feed |
| `chateau` | Chateau de Morès State Historic Site (SHSND) | public Google Calendar ICS |
| `chamber` | Medora Area Chamber of Commerce | The Events Calendar REST API |
| `discover` | Discover Medora (CVB) | events page |
| `ndchf` | ND Cowboy Hall of Fame | events page |
| `uncorkd` | Medora Uncork'd | The Events Calendar REST API |
| `littlemo` | Little Missouri Saloon | Squarespace events JSON |
| `boots` | Boots Bar & Grill | live-music page |
| `badlandsministries` | Badlands Ministries | events page |
| `shsnd` | State Historical Society (main calendar) | Google Calendar ICS, filtered to Medora |
| `runsignup` | Races within 90 miles (Maah Daah Hey 100, trail runs) | RunSignup API |
| `dsu` | Dickinson State University | Trumba JSON (meetings and room bookings skipped) |
| `watford` | Watford City events | calendar JSON |
| `ndparks` | ND Parks & Recreation | RSS, filtered to Sully Creek / Little Missouri SP |
| `cityspark` | The Dickinson Press community calendar | CitySpark API, 60 mi around Medora, meetings/services filtered out |
| `ndtourism` | North Dakota Tourism | Firecrawl (`FIRECRAWL_API_KEY`), filtered to area towns; every 3 days |
| `facebook` | Facebook events near Medora | Apify `apify/facebook-events-scraper` (`APIFY_TOKEN`); every 2 days |

Churches: Badlands Ministries is read automatically. St. Mary's Catholic Church (Saturday Mass in season) and the other Medora congregations have no online calendar; add their schedules to `config/manual_events.yaml` once confirmed.

## Where things are

Every event gets `area`: **In Medora** (town and the South Unit of the national park), **Out of Medora** (with an approximate drive time, e.g. "About 35 min from Medora"), or Online. Drive times are estimates in `medevents/places.py`.

Time zones: southwest ND (Billings, Golden Valley, Stark, Slope, Bowman, Adams, Hettinger, Grant, southern Dunn and McKenzie) and eastern Montana are Mountain; Watford City, northern Dunn/McKenzie and the rest of ND are Central. Each event shows its own town's clock, and Central-time events say so.

## Duplicates

`medevents/dedupe.py` treats two listings as one event when dates overlap, start times are within 90 minutes, and titles match after normalising ("Medora's Annual Hunters Feed" = "Annual Medora's Hunters Feed"; men's vs women's games never merge). The kept record fills its gaps from the others and lists them in `also_listed`. Listings that merged but disagree on the start time land in `/api/v1/review.json`.

## Embedding

```html
<div data-medora-events="browse" data-limit="10" data-area="medora"></div>
<script src="https://medoraevents.labs.trlibrary.com/embed.js" async></script>
```

Views: `upcoming | browse | month | week`. Options: `data-area` (`medora`, `nearby`), `data-source`, `data-cost`, `data-kind`, `data-q`, `data-when`, `data-limit`, `data-more`, `data-recurring` (`hide` default = leave out daily activities like trail rides and dining), `data-filters`, `data-title`, `data-theme`, `data-bg`, `data-compact`, `data-date`.

## Running

```bash
pip install -r requirements.txt
python -m medevents.build
python -m medevents.build --only medora,chamber
```

Repo secrets: `NPS_API_KEY`, `FIRECRAWL_API_KEY`, `APIFY_TOKEN`. Pages: deploy from `main` / `/docs`, custom domain `medoraevents.labs.trlibrary.com` (covered by the `*.labs` wildcard DNS).

Hand corrections: `config/overrides.yaml`; hand-added events: `config/manual_events.yaml`.
