"""Hand-built pages from Medora partners (no feed or API behind them)."""
from __future__ import annotations

import re
from datetime import date, datetime

from bs4 import BeautifulSoup

from ..http import FetchError, get
from ..model import Event, Venue, at, clean_text, guess_cost, nearest_year, parse_clock
from .generic import TZ, _venue_from_text

MONTHS = ["january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november", "december"]
M_RX = r"(January|February|March|April|May|June|July|August|September|October|November|December)"


def _md(mon: str, day: str, year: str | None) -> date:
    m = MONTHS.index(mon.lower()) + 1
    return date(int(year) if year else nearest_year(m, int(day)), m, int(day))


# ---------------------------------------------------------------- Discover Medora (Medora CVB)
class discover:
    SOURCE = {"id": "discover", "name": "Discover Medora (Medora Convention & Visitors Bureau)", "short": "Discover Medora",
              "url": "https://discovermedora.com/events/", "type": "partner", "region": "Medora, ND"}

    @staticmethod
    def fetch():
        soup = BeautifulSoup(get(discover.SOURCE["url"]).text, "lxml")
        out = []
        for a in soup.select("a.post"):
            h3 = a.find("h3")
            dt = a.select_one(".event-date")
            if not h3 or not dt:
                continue
            title = clean_text(h3.get_text(" ", strip=True))
            dtxt = dt.get_text(" ", strip=True)
            m = re.match(M_RX + r" (\d{1,2})(?:st|nd|rd|th)?(?:\s*-\s*(?:" + M_RX + r" )?(\d{1,2})(?:st|nd|rd|th)?)?,\s*(\d{4})", dtxt)
            if not m:
                continue
            d0 = _md(m.group(1), m.group(2), m.group(5))
            d1 = _md(m.group(3) or m.group(1), m.group(4), m.group(5)) if m.group(4) else d0
            if d1 < date.today():
                continue
            loc = (a.select_one(".event-loc") or BeautifulSoup("", "lxml")).get_text(" ", strip=True)
            phone = (a.select_one(".phone") or BeautifulSoup("", "lxml")).get_text(" ", strip=True)
            thumb = a.select_one(".thumbnail")
            img = re.search(r"url\(([^)]+)\)", thumb.get("style", "")) if thumb else None
            out.append(Event(
                source="discover", source_event_id=re.sub(r"\W+", "-", f"{title}-{d0}".lower()), title=title,
                start=at(d0, None, TZ), end=at(d1, None, TZ) if d1 > d0 else None, all_day=True, timezone=TZ,
                url=a.get("href"), description="", image=img.group(1) if img else None, attendance="in_person",
                venue=Venue(name=loc or None, city="Medora", region="ND"), organizer=None,
                categories=[], extra={"phone": phone or None, "category_id": a.get("data-cat-id")},
            ))
        return out


# ---------------------------------------------------------------- North Dakota Cowboy Hall of Fame
class cowboy:
    SOURCE = {"id": "ndchf", "name": "North Dakota Cowboy Hall of Fame", "short": "ND Cowboy Hall of Fame",
              "url": "https://northdakotacowboy.org/events/", "type": "partner", "region": "Medora, ND"}

    @staticmethod
    def fetch():
        soup = BeautifulSoup(get(cowboy.SOURCE["url"]).text, "lxml")
        main = soup.find("main") or soup.body
        if main is None:
            raise FetchError("no page body (likely blocked)")
        for t in main(["script", "style", "noscript", "svg"]):
            t.decompose()
        links = [(a.get_text(" ", strip=True).lower(), a.get("href")) for a in main.find_all("a", href=True)]
        lines = [l.strip() for l in main.get_text("\n").split("\n") if l.strip()]
        out, year = [], None
        i = 0
        while i < len(lines):
            l = lines[i]
            ym = re.fullmatch(M_RX + r"\s+(\d{4})", l, re.I)
            if ym:
                year = ym.group(2)
            dm = re.fullmatch(r"(\d{1,2})(?:\s*[–-]\s*(\d{1,2}))?\s+" + M_RX, l, re.I)
            if dm and i + 2 < len(lines):
                title_line = lines[i + 2]
                title, _, venue = title_line.partition(", ")
                d0 = _md(dm.group(3), dm.group(1), year)
                d1 = _md(dm.group(3), dm.group(2), year) if dm.group(2) else d0
                if d1 >= date.today():
                    link = next((h for t, h in links if "detail" in t or "ticket" in t), cowboy.SOURCE["url"])
                    out.append(Event(
                        source="ndchf", source_event_id=re.sub(r"\W+", "-", f"{title}-{d0}".lower()), title=title.strip(),
                        start=at(d0, None, TZ), end=at(d1, None, TZ) if d1 > d0 else None, all_day=True, timezone=TZ,
                        url=cowboy.SOURCE["url"], description="", attendance="in_person",
                        venue=_venue_from_text(venue) if venue else Venue(), organizer=cowboy.SOURCE["name"],
                        extra={"day_text": lines[i + 1], "links": [h for t, h in links if "ticket" in t][:2]},
                    ))
                i += 3
                continue
            i += 1
        return out


# ---------------------------------------------------------------- Boots Bar & Grill live music
class boots:
    SOURCE = {"id": "boots", "name": "Boots Bar & Grill", "short": "Boots Bar & Grill",
              "url": "https://bootsbarmedora.com/livemusic", "type": "partner", "region": "Medora, ND"}
    VENUE = Venue(name="Boots Bar & Grill", city="Medora", region="ND")

    @staticmethod
    def fetch():
        soup = BeautifulSoup(get(boots.SOURCE["url"]).text, "lxml")
        main = soup.find("main") or soup.body
        lines = [l.strip() for l in main.get_text("\n").split("\n") if l.strip()]
        out = []
        for i, l in enumerate(lines):
            m = re.fullmatch(r"\w+day,\s+" + M_RX + r"\s+(\d{1,2}),\s+(\d{4})", l)
            if not m or i + 1 >= len(lines):
                continue
            d = _md(m.group(1), m.group(2), m.group(3))
            if d < date.today():
                continue
            act, _, t = lines[i + 1].partition("@")
            slug = re.sub(r"\W+", "-", act.strip().lower())
            out.append(Event(
                source="boots", source_event_id=f"{d}-{slug}",
                title=f"Live music: {act.strip()}", start=at(d, parse_clock(t) if t else None, TZ),
                all_day=not t, timezone=TZ, url=boots.SOURCE["url"], description=f"{act.strip()} plays Boots Bar & Grill.",
                attendance="in_person", venue=boots.VENUE, organizer=boots.SOURCE["name"], categories=["Live music"],
            ))
        return out


# ---------------------------------------------------------------- Badlands Ministries (Wix page)
class badlandsministries:
    SOURCE = {"id": "badlandsministries", "name": "Badlands Ministries", "short": "Badlands Ministries",
              "url": "https://www.badlandsministries.org/events", "type": "partner", "region": "Medora, ND"}

    @staticmethod
    def fetch():
        soup = BeautifulSoup(get(badlandsministries.SOURCE["url"]).text, "lxml")
        main = soup.find("main") or soup.body
        lines = [l.strip() for l in main.get_text("\n").split("\n") if l.strip()]
        out = []
        # sections are introduced by "Anchor N" markers: title, then date somewhere in the next few lines
        for i, l in enumerate(lines):
            if not re.fullmatch(r"Anchor \d+", l) or i + 1 >= len(lines):
                continue
            title = lines[i + 1]
            block = lines[i + 2: i + 9]
            dl = next((x for x in block if re.match(M_RX + r"\s+\d{1,2}(?:st|nd|rd|th)?,\s*\d{4}", x)), None)
            if not dl:
                continue
            m = re.match(M_RX + r"\s+(\d{1,2})(?:st|nd|rd|th)?,\s*(\d{4})(?:\s*@\s*(.+))?", dl)
            d = _md(m.group(1), m.group(2), m.group(3))
            if d < date.today():
                continue
            t0 = parse_clock(m.group(4)) if m.group(4) else None
            desc = " ".join(x for x in block if x != dl and not x.lower().startswith(("link to", "anchor")))
            cost, pmin, pmax, note = guess_cost(desc)
            slug = re.sub(r"\W+", "-", title.lower())
            out.append(Event(
                source="badlandsministries", source_event_id=f"{d}-{slug}", title=title,
                start=at(d, t0, TZ), all_day=t0 is None, timezone=TZ, url=badlandsministries.SOURCE["url"],
                description=desc, attendance="virtual" if "online" in desc.lower() and "giving" in title.lower() else "in_person",
                cost=cost, cost_note=note, venue=Venue(city="Medora", region="ND"),
                organizer=badlandsministries.SOURCE["name"], categories=["Church & faith"],
            ))
        return out
