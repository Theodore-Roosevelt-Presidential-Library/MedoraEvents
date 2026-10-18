"""Registry of event sources, in de-duplication priority order (first wins).

When the same event appears in several calendars, the copy from the source listed first is kept
and the others are recorded in its `also_listed` field. Organizers' own calendars come first,
then visitor bureaus, then aggregators.
"""
from . import trpl, nps
from .generic import TZ, _src, ics_source, squarespace_source, tribe_source
from .local import badlandsministries, boots, cowboy, discover
from .paid import facebook, ndtourism
from .regional import cityspark, dsu, ndparks, runsignup, watford

SHSND_FEED = "https://calendar.google.com/calendar/ical/iut66rvg94oar0tbbldnvjld2o%40group.calendar.google.com/public/basic.ics"
SHSND_MAIN = "https://calendar.google.com/calendar/ical/history.nd%40gmail.com/public/basic.ics"

medora = ics_source(
    _src("medora", "Theodore Roosevelt Medora Foundation", "Medora Foundation", "https://medora.com/calendar/"),
    "https://medora.com/?mec-ical-feed=1",
    # standing "things to do" entries that repeat every day all season
    recurring_titles=(r"^take a trail ride", r"^explore theodore roosevelt national park", r"^(breakfast|dinner|lunch) at",
                      r"^get a cocktail", r"^shop ", r"gift shop"),
)
chateau = ics_source(
    _src("chateau", "Chateau de Morès State Historic Site (State Historical Society of North Dakota)", "Chateau de Morès",
         "https://www.history.nd.gov/events/calendar.html"),
    SHSND_FEED,
)
shsnd = ics_source(
    _src("shsnd", "State Historical Society of North Dakota", "State Historical Society",
         "https://www.history.nd.gov/events/calendar.html", region="North Dakota", kind="regional"),
    SHSND_MAIN, tz="America/Chicago",
    keep=lambda title, desc, loc: "medora" in f"{title} {desc} {loc}".lower() or "mores" in f"{title} {loc}".lower(),
)
chamber = tribe_source(_src("chamber", "Medora Area Chamber of Commerce", "Medora Chamber", "https://medorachamber.org/events/"),
                       "https://medorachamber.org")
uncorkd = tribe_source(_src("uncorkd", "Medora Uncork'd", "Medora Uncork'd", "https://www.medorauncorkd.wine/events/category/uncorkd/"),
                       "https://www.medorauncorkd.wine")
littlemo = squarespace_source(_src("littlemo", "Little Missouri Saloon", "Little Mo Saloon", "https://www.littlemosaloon.com/upcoming-events"),
                              "https://www.littlemosaloon.com/upcoming-events", categories=("Live music",))

ALL = [
    trpl, nps, medora, chateau, chamber, discover, cowboy, uncorkd, littlemo, boots, badlandsministries,
    shsnd, runsignup, dsu, watford, ndparks, cityspark, ndtourism, facebook,
]
BY_ID = {m.SOURCE["id"]: m for m in ALL}
