"""Regional calendars beyond Medora: Dickinson, Watford City and statewide lists filtered to the area."""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta, timezone
from xml.etree import ElementTree as ET
from zoneinfo import ZoneInfo

from .. import config
from ..http import get, get_json, _session
from ..model import Event, Venue, at, clean_text, guess_attendance, guess_cost, parse_clock
from .generic import TZ
from .paid import in_region
from ..geo import MEDORA, MAX_KM, km

CT = "America/Chicago"  # Dickinson/Stark County and Watford City/McKenzie County are Mountain/Central respectively


# ---------------------------------------------------------------- RunSignup (races)
class runsignup:
    SOURCE = {"id": "runsignup", "name": "RunSignup (races near Medora)", "short": "RunSignup",
              "url": "https://runsignup.com", "type": "regional", "region": "Medora region"}

    @staticmethod
    def fetch():
        d = get_json("https://runsignup.com/Rest/races", params={
            "format": "json", "zipcode": "58645", "radius": 90, "results_per_page": 100,
            "start_date": date.today().isoformat(), "events": "F"})
        out = []
        for x in d.get("races", []):
            r = x["race"]
            try:
                d0 = datetime.strptime(r["next_date"], "%m/%d/%Y").date()
            except (KeyError, ValueError):
                continue
            if d0 < date.today():
                continue
            d1 = datetime.strptime(r["next_end_date"], "%m/%d/%Y").date() if r.get("next_end_date") else d0
            a = r.get("address") or {}
            st = a.get("state") or ""
            tz = TZ if a.get("city") in ("Medora", "Beach", "Belfield", "Dickinson", "Sentinel Butte") or st == "MT" else CT
            out.append(Event(
                source="runsignup", source_event_id=str(r["race_id"]), title=clean_text(r["name"]).title() if r["name"].isupper() else clean_text(r["name"]),
                start=at(d0, None, tz), end=at(d1, None, tz) if d1 > d0 else None, all_day=True, timezone=tz,
                url=r.get("url"), description=clean_text(r.get("description"))[:1500], image=r.get("logo_url"),
                attendance="in_person", cost="paid", cost_note="Race registration fee",
                registration_required=True, registration_url=r.get("url"),
                venue=Venue(name=None, address=a.get("street") or None, city=a.get("city"), region=st,
                            postal_code=a.get("zipcode")),
                organizer=None, categories=["Races"], extra={"runsignup_id": r["race_id"]},
            ))
        return out


# ---------------------------------------------------------------- Trumba (Dickinson State University)
class dsu:
    SOURCE = {"id": "dsu", "name": "Dickinson State University", "short": "Dickinson State",
              "url": "https://dickinsonstate.edu/events", "type": "regional", "region": "Dickinson, ND"}
    FEED = "https://www.trumba.com/calendars/dickinson-state-university-events.json"
    SKIP_CATS = ("Other Events",)   # meetings, room bookings, weekly services
    # academic-calendar dates and standing services aren't things a visitor drives in for
    SKIP_TITLE = re.compile(r"\b(first day|last day|preregistration|registration (opens|begins|ends)|courses?\b|classes|"
                            r"deadline|grades due|finals|midterm|commencement rehearsal|church|bible study|worship|chapel|"
                            r"meeting|office hours|advising)\b", re.I)

    @staticmethod
    def fetch():
        out = []
        for r in get_json(dsu.FEED, timeout=90):
            cat = (r.get("categoryCalendar") or "").split("|")[-1]
            if cat in dsu.SKIP_CATS or r.get("canceled") or dsu.SKIP_TITLE.search(r.get("title") or ""):
                continue
            off = r.get("startTimeZoneOffset") or "-0600"
            tzinfo = timezone(timedelta(hours=int(off[:3]), minutes=int(off[0] + off[3:5])))
            s = datetime.fromisoformat(r["startDateTime"]).replace(tzinfo=tzinfo)
            e = datetime.fromisoformat(r["endDateTime"]).replace(tzinfo=tzinfo) if r.get("endDateTime") else None
            all_day = bool(r.get("allDay"))
            if all_day and e:
                e = e - timedelta(days=1)
            if (e or s).date() < date.today() or s.date() > config.horizon():
                continue
            cf = {f.get("label"): clean_text(f.get("value")) for f in r.get("customFields") or []}
            desc = clean_text(r.get("description"))
            cost, pmin, pmax, note = guess_cost(" ".join([desc, cf.get("Cost", ""), cf.get("Admission", "")]))
            loc = clean_text(r.get("location")) or cf.get("Building") or ""
            # athletics list away games by opponent town ("Billings, Mont."); home games read "Dickinson, N.D., Scott Gymnasium"
            loc = re.sub(r"^(Dickinson|Dickson)\s*,\s*(N\.\s?D\.)?\s*,?\s*", "", loc).strip(" ,")
            away = re.fullmatch(r"([A-Z][A-Za-z .']+),\s*([A-Z][a-z]{1,4}\.?|[A-Z]\.\s?[A-Z]\.?)", loc or "")
            if away:
                continue   # road game: it isn't happening in Dickinson
            out.append(Event(
                source="dsu", source_event_id=str(r["eventID"]), title=clean_text(r.get("title")), start=s,
                end=e if (e and e > s) else None, all_day=all_day, timezone="America/Denver",
                url=r.get("permaLinkUrl"), description=desc, image=(r.get("eventImage") or {}).get("url"),
                attendance=guess_attendance(desc, True), cost=cost, cost_note=note, price_min=pmin, price_max=pmax,
                venue=Venue(name=loc or "Dickinson State University", city="Dickinson", region="ND"),
                organizer="Dickinson State University", categories=[cat] if cat else [],
            ))
        return out


# ---------------------------------------------------------------- Watford City events (TRNP North Unit gateway)
class watford:
    SOURCE = {"id": "watford", "name": "Watford City events", "short": "Watford City",
              "url": "https://www.visitwatfordcity.com/Calendar/List", "type": "regional", "region": "Watford City, ND"}

    @staticmethod
    def fetch():
        out = []
        for r in get_json("https://www.watfordcityevents.com/Calendar/GetCalendarExternal/5"):
            s = datetime.fromisoformat(r["StartString"].replace("Z", "+00:00")).astimezone(ZoneInfo(CT))
            e = datetime.fromisoformat(r["EndString"].replace("Z", "+00:00")).astimezone(ZoneInfo(CT)) if r.get("EndString") else None
            if (e or s).date() < date.today():
                continue
            all_day = str(r.get("IsAllDay")).lower() == "true"
            desc = clean_text(r.get("Description") or r.get("ShortDescription"))
            cost, pmin, pmax, note = guess_cost(desc)
            out.append(Event(
                source="watford", source_event_id=str(r["Id"]), title=clean_text(r.get("Title")),
                start=at(s.date(), None, CT) if all_day else s, end=(at(e.date(), None, CT) if all_day else e) if e and e > s else None,
                all_day=all_day, timezone=CT,
                url=f"https://www.visitwatfordcity.com/Calendar/Details/{r['Id']}/{r.get('NavigationTitle') or ''}".rstrip("/"),
                description=desc, image=r.get("HeaderImage") or None, attendance=guess_attendance(desc, True),
                cost=cost, cost_note=note, price_min=pmin, price_max=pmax,
                venue=Venue(name=clean_text(r.get("Location")) or None, city="Watford City", region="ND"),
                organizer=None, categories=[c for c in (r.get("Categories") or []) if c != "Events"],
                recurring=bool(r.get("RecurrenceRule")),
            ))
        return out


# ---------------------------------------------------------------- CitySpark (Dickinson Press community calendar)
class cityspark:
    SOURCE = {"id": "cityspark", "name": "The Dickinson Press community calendar", "short": "Dickinson Press calendar",
              "url": "https://www.thedickinsonpress.com/calendar", "type": "regional", "region": "Southwest North Dakota"}
    NOISE = re.compile(r"\b(meeting|board of|commission|council|bible study|church service|worship|mass\b|aa\b|al-anon|"
                       r"support group|blood drive|wedding|private|class reunion|office hours|tutoring|auction|church at|sunday school)\b", re.I)

    @staticmethod
    def fetch():
        out, skip = [], 0
        start = date.today()
        while skip < 1000:
            body = {"ppid": 9048, "start": f"{start}T00:00:00", "end": f"{config.horizon()}T00:00:00",
                    "lat": 46.9139, "lng": -103.5244, "distance": 60, "sort": "Date", "skip": skip, "labels": [],
                    "pick": False, "tps": "", "sparks": False, "search": "", "defFilter": "all"}
            r = _session.post("https://portal.cityspark.com/api/events/GetEvents/DickinsonPress", json=body, timeout=60)
            r.raise_for_status()
            items = (r.json() or {}).get("Value") or []
            if not items:
                break
            for it in items:
                name = clean_text(it.get("Name"))
                if cityspark.NOISE.search(name + " " + (it.get("Summary") or "")):
                    continue
                links = it.get("Links") or []
                if any("dickinsonstate.edu" in (l.get("url") or "") for l in links) or "dickinsonstate.edu" in (it.get("PrimaryUrl") or ""):
                    continue  # read straight from DSU's own calendar
                if it.get("latitude") and it.get("longitude") and km((float(it["latitude"]), float(it["longitude"])), MEDORA) > 200:
                    continue   # the Press's radius search leaks far-off listings (Arizona, the UK)
                tz = CT if "Watford" in (it.get("CityState") or "") else TZ
                has_time = str(it.get("HasTime")).lower() == "true" and str(it.get("AllDay")).lower() != "true"
                su = it.get("StartUTC") or it.get("DateStart")
                s = datetime.fromisoformat(su.replace("Z", "+00:00")).astimezone(ZoneInfo(tz))
                eu = it.get("EndUTC") or it.get("DateEnd")
                e = datetime.fromisoformat(eu.replace("Z", "+00:00")).astimezone(ZoneInfo(tz)) if eu else None
                if not has_time:
                    s = at(datetime.fromisoformat(it["Date"].replace("Z", "")).date(), None, tz)
                    e = None
                city, _, st = (it.get("CityState") or "").partition(", ")
                desc = clean_text(it.get("Description") or it.get("Summary"))
                free = str(it.get("Free")).lower() == "true"
                cost, pmin, pmax, note = ("free", None, None, None) if free else guess_cost(" ".join([desc, str(it.get("PriceText") or ""), str(it.get("Price") or "")]))
                out.append(Event(
                    source="cityspark", source_event_id=str(it.get("Id") or it.get("PId")), title=name,
                    start=s, end=e if (e and e > s) else None, all_day=not has_time, timezone=tz,
                    url=it.get("PrimaryUrl") or (links[0].get("url") if links else None) or cityspark.SOURCE["url"],
                    description=desc, image=it.get("LargeImg") or it.get("MediumImg"),
                    attendance="virtual" if str(it.get("isVirtual")).lower() == "true" else "in_person",
                    cost=cost, cost_note=note, price_min=pmin, price_max=pmax,
                    registration_url=it.get("TicketUrl") or None,
                    venue=Venue(name=it.get("Venue") or None, address=it.get("Address") or None, city=city or None,
                                region=st or None, postal_code=it.get("Zip") or None,
                                lat=float(it["latitude"]) if it.get("latitude") else None,
                                lon=float(it["longitude"]) if it.get("longitude") else None),
                    organizer=it.get("Sponsor") or None,
                ))
            skip += len(items)
        return out


# ---------------------------------------------------------------- ND Parks & Recreation
class ndparks:
    SOURCE = {"id": "ndparks", "name": "North Dakota Parks & Recreation", "short": "ND Parks & Rec",
              "url": "https://www.parkrec.nd.gov/events", "type": "regional", "region": "North Dakota"}
    PARKS = ("sully creek", "little missouri state park", "maah daah hey", "medora")

    @staticmethod
    def fetch():
        root = ET.fromstring(get("https://www.parkrec.nd.gov/rss/events").content)
        out = []
        for it in root.iter("item"):
            title = clean_text(it.findtext("title"))
            desc = clean_text(it.findtext("description"))
            link = (it.findtext("link") or "").strip()
            if not any(p in f"{title} {desc}".lower() for p in ndparks.PARKS):
                continue
            m = re.search(r"(\w+ \d{1,2}, \d{4})(?:[^\d]+(\d{1,2}(?::\d{2})?\s*[ap]\.?m\.?))?", desc, re.I)
            if not m:
                continue
            d = datetime.strptime(m.group(1), "%B %d, %Y").date()
            if d < date.today():
                continue
            t = parse_clock(m.group(2)) if m.group(2) else None
            out.append(Event(
                source="ndparks", source_event_id=link or title, title=title, start=at(d, t, TZ), all_day=t is None,
                timezone=TZ, url=link, description=desc, attendance="in_person",
                venue=Venue(name="Sully Creek State Park" if "sully" in (title + desc).lower() else None, region="ND"),
                organizer=ndparks.SOURCE["name"],
            ))
        return out
