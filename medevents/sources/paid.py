"""Sources that go through paid services: ND Tourism (Firecrawl) and Facebook (Apify).

Both run on a slower cadence (SOURCE["every_days"]) to keep credits down; between runs the
build reuses the last good results.
"""
from __future__ import annotations

import os
import re
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

import requests

from ..http import FetchError, firecrawl_get
from ..model import Event, Venue, at, clean_text, guess_attendance, guess_cost
from .generic import TZ

# Towns that count as "Medora and the connected region"
REGION_TOWNS = ["medora", "belfield", "beach", "sentinel butte", "golva", "fryburg", "dickinson", "south heart",
                "gladstone", "taylor", "richardton", "killdeer", "dunn center", "halliday", "grassy butte",
                "watford city", "amidon", "bowman", "marmarth", "rhame", "scranton", "new england", "mott",
                "hettinger", "wibaux", "glendive", "trotters", "theodore roosevelt national park"]
REGION_SLUGS = {t.replace(" ", "-") for t in REGION_TOWNS}
M_RX = r"(January|February|March|April|May|June|July|August|September|October|November|December) (\d{1,2}), (\d{4})"


def in_region(*texts) -> bool:
    t = " ".join(x or "" for x in texts).lower()
    return any(re.search(r"\b" + re.escape(town) + r"\b", t) for town in REGION_TOWNS)


# ---------------------------------------------------------------- ND Tourism
class ndtourism:
    SOURCE = {"id": "ndtourism", "name": "North Dakota Tourism", "short": "ND Tourism",
              "url": "https://www.ndtourism.com/listings/events", "type": "regional", "region": "North Dakota",
              "every_days": 3}
    LIST = "https://www.ndtourism.com/listings/events?field_start_date=&field_start_date_1=&search_api_fulltext=&page={}"

    @staticmethod
    def parse(md: str):
        """Cards look like: 'October 18, 2026' ['to November 2, 2026'] '### [Title](url)' phone, address, links."""
        out = []
        for m in re.finditer(r"###\s*\[([^\]]+)\]\((https://www\.ndtourism\.com/([a-z0-9-]+)/events/[^)\s]+)\)", md):
            title, url, slug = m.group(1), m.group(2), m.group(3)
            before = md[max(0, m.start() - 260): m.start()]
            dates = re.findall(M_RX, before)
            if not dates:
                continue
            after = md[m.end(): m.end() + 700].split("###")[0]
            lines = [l.strip() for l in after.split("\n") if l.strip()]
            addr = next((l for l in lines if re.search(r",\s*(ND|MT|SD)\s*\d{5}", l)), "").replace("\\|", "·")
            site = re.search(r"\[Visit Website\]\(([^)]+)\)", after)
            out.append({"title": clean_text(title), "url": url, "slug": slug, "dates": dates[-2:], "addr": addr,
                        "site": site.group(1) if site else None})
        return out

    @staticmethod
    def fetch():
        out, seen = [], set()
        for page in range(0, 60):
            resp = firecrawl_get(ndtourism.LIST.format(page))
            cards = ndtourism.parse(getattr(resp, "markdown", "") or "")
            if not cards:
                break
            for c in cards:
                if c["url"] in seen or not (c["slug"] in REGION_SLUGS or in_region(c["addr"])):
                    continue
                seen.add(c["url"])
                d = [datetime.strptime(f"{a} {b} {y}", "%B %d %Y").date() for a, b, y in c["dates"]]
                d0, d1 = d[0], d[-1]
                if d1 < date.today():
                    continue
                parts = [p.strip() for p in c["addr"].split(",")]
                out.append(Event(
                    source="ndtourism", source_event_id=c["url"].rsplit("/", 1)[-1], title=c["title"],
                    start=at(d0, None, TZ), end=at(d1, None, TZ) if d1 > d0 else None, all_day=True, timezone=TZ,
                    url=c["site"] or c["url"], description="", attendance="in_person",
                    venue=Venue(name=parts[0] if parts else None, address=", ".join(parts[1:]) or None,
                                city=parts[-2] if len(parts) >= 3 else c["slug"].replace("-", " ").title(),
                                region="ND"),
                    organizer=None, categories=[c["url"].split("/events/")[1].split("/")[0].replace("-", " ").title()],
                    extra={"ndtourism_url": c["url"]},
                ))
        return out


# ---------------------------------------------------------------- Facebook (Apify)
class facebook:
    SOURCE = {"id": "facebook", "name": "Facebook events near Medora", "short": "Facebook",
              "url": "https://www.facebook.com/events/search?q=medora", "type": "regional", "region": "Medora, ND",
              "every_days": 2}
    # Matt's search: events for "medora" filtered to the Medora, ND location
    START_URLS = [
        "https://www.facebook.com/events/search?q=medora&filters=eyJycF9ldmVudHNfbG9jYXRpb246MCI6IntcIm5hbWVcIjpcImZpbHRlcl9ldmVudHNfbG9jYXRpb25cIixcImFyZ3NcIjpcIjExMzU1ODY1NTMyMTYwOVwifSJ9",
    ]
    MAX_EVENTS = int(os.environ.get("MEDEVENTS_FB_MAX", "80"))

    @staticmethod
    def fetch():
        token = os.environ.get("APIFY_TOKEN")
        if not token:
            raise FetchError("APIFY_TOKEN not set")
        r = requests.post(
            "https://api.apify.com/v2/acts/apify~facebook-events-scraper/run-sync-get-dataset-items",
            params={"token": token, "timeout": 600},
            json={"startUrls": [{"url": u} for u in facebook.START_URLS], "maxEvents": facebook.MAX_EVENTS},
            timeout=660,
        )
        if not r.ok:
            raise FetchError(f"Apify {r.status_code}: {r.text[:200]}")
        out = []
        for it in r.json():
            if it.get("isPast"):
                continue
            start_s = it.get("utcStartDate") or it.get("startDate")
            if not start_s:
                continue
            start = datetime.fromisoformat(start_s.replace("Z", "+00:00")).astimezone(ZoneInfo(TZ))
            end_s = it.get("utcEndDate") or it.get("endDate")
            end = datetime.fromisoformat(end_s.replace("Z", "+00:00")).astimezone(ZoneInfo(TZ)) if end_s else None
            loc = it.get("location") or {}
            addr = it.get("address") or loc.get("name") or ""
            online = bool(it.get("isOnline"))
            if not online and not in_region(addr, loc.get("city") if isinstance(loc, dict) else "", it.get("name"), it.get("description")):
                continue
            desc = clean_text(it.get("description"))
            tickets = it.get("ticketsInfo") or {}
            cost, pmin, pmax, note = guess_cost(" ".join([desc, str(tickets)]))
            orgs = it.get("organizators") or []
            out.append(Event(
                source="facebook", source_event_id=str(it.get("id") or it.get("url")), title=clean_text(it.get("name")),
                start=start, end=end if (end and end > start) else None, timezone=TZ, url=it.get("url"),
                description=desc, image=it.get("imageUrl"),
                attendance="virtual" if online else guess_attendance(desc, bool(addr)),
                cost=cost, cost_note=note, price_min=pmin, price_max=pmax,
                registration_url=(tickets.get("buyUrl") if isinstance(tickets, dict) else None),
                venue=Venue(name=(loc.get("name") if isinstance(loc, dict) else None) or (addr.split(",")[0] if addr else None),
                            address=addr or None, city=(loc.get("city") if isinstance(loc, dict) else None),
                            lat=(loc.get("latitude") if isinstance(loc, dict) else None),
                            lon=(loc.get("longitude") if isinstance(loc, dict) else None)),
                organizer=", ".join(o.get("name", "") for o in orgs if isinstance(o, dict)) or None,
                status="cancelled" if it.get("isCanceled") else "scheduled",
                extra={"going": it.get("usersGoing"), "interested": it.get("usersInterested")},
            ))
        return out
