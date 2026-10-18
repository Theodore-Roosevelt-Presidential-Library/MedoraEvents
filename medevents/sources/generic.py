"""Reusable readers for the calendar platforms partner sites run on.

Each factory returns a small source object with a SOURCE dict and a fetch() method,
so a new partner on a known platform is one line in sources/__init__.py.
"""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from .. import config
from ..http import get, get_json
from ..model import Event, Venue, at, clean_text, guess_attendance, guess_cost, parse_clock

TZ = "America/Denver"  # Medora, Billings and Golden Valley counties are Mountain time


def _src(id, name, short, url, region="Medora, ND", kind="partner"):
    return {"id": id, "name": name, "short": short, "url": url, "type": kind, "region": region}


def _venue_from_text(loc: str) -> Venue:
    parts = [p.strip() for p in re.split(r",|·|\|", loc or "") if p.strip()]
    if not parts:
        return Venue()
    st = next((p for p in parts if re.fullmatch(r"(ND|MT|SD|North Dakota|Montana)( \d{5})?", p)), None)
    city = parts[parts.index(st) - 1] if st and parts.index(st) > 0 else None
    return Venue(name=parts[0], address=", ".join(parts[1:]) or None, city=city,
                 region=(st or "")[:2].upper() if st else None)


# ---------------------------------------------------------------- iCal feeds
def ics_source(SOURCE, url, *, tz=TZ, recurring_titles=(), drop_titles=(), kind_map=None, keep=None, venue_default=None,
               fixed_offset_hours=None):
    """Any public .ics feed (Modern Events Calendar, Google Calendar, Tribe ?ical=1, ...)."""
    def fetch():
        import icalendar
        import recurring_ical_events
        raw = get(url, timeout=90).content.decode("utf-8", "replace")
        raw = re.sub(r"DURATION:P0S", "DURATION:PT0S", raw)  # MEC writes an invalid zero duration
        cal = icalendar.Calendar.from_ical(raw)
        today = date.today()
        occ = recurring_ical_events.of(cal, skip_bad_series=True).between(today, config.horizon())
        # how many different days each title runs on (daily activities run on dozens)
        days_by_title = {}
        for c in occ:
            d0 = c["DTSTART"].dt
            days_by_title.setdefault(str(c.get("SUMMARY")), set()).add(d0.date() if isinstance(d0, datetime) else d0)
        counts = {k: len(v) for k, v in days_by_title.items()}
        out = []
        z = ZoneInfo(tz)
        for c in occ:
            title = clean_text(str(c.get("SUMMARY", ""))).strip()
            if not title or any(re.search(p, title, re.I) for p in drop_titles):
                continue
            s, e = c["DTSTART"].dt, (c["DTEND"].dt if c.get("DTEND") else None)
            all_day = not isinstance(s, datetime)
            if all_day:
                start = at(s, None, tz)
                end = at(e - timedelta(days=1), None, tz) if e and (e - s).days > 1 else None
            else:
                start = s if s.tzinfo else s.replace(tzinfo=z)
                end = (e if e.tzinfo else e.replace(tzinfo=z)) if e else None
                if fixed_offset_hours is not None:
                    # the feed wrote wall-clock times at a fixed offset (e.g. MST all year); re-read them as local time
                    fix = lambda d: (d.astimezone(timezone.utc) + timedelta(hours=fixed_offset_hours)).replace(tzinfo=None).replace(tzinfo=z)
                    start = fix(start)
                    end = fix(end) if end else None
                if end and end <= start:
                    end = None
            if (end or start).date() < today if isinstance(end or start, datetime) else False:
                continue
            desc = clean_text(str(c.get("DESCRIPTION", "")))
            loc = clean_text(str(c.get("LOCATION", "")))
            if keep and not keep(title, desc, loc):
                continue
            cats = c.get("CATEGORIES")
            cats = [str(x) for x in (cats.cats if hasattr(cats, "cats") else [])] if cats else []
            standing = any(re.search(p, title, re.I) for p in recurring_titles)   # trail rides, dining: hidden by default
            recurring = standing or counts.get(str(c.get("SUMMARY")), 0) > 3                 # show runs: grouped, still shown
            cost, pmin, pmax, note = guess_cost(desc)
            img = c.get("ATTACH")
            out.append(Event(
                source=SOURCE["id"], source_event_id=str(c.get("UID") or title), title=title, start=start, end=end,
                all_day=all_day, timezone=tz, url=str(c.get("URL") or SOURCE["url"]), description=desc,
                image=str(img) if img and str(img).startswith("http") else None,
                attendance=guess_attendance(f"{title} {desc}", bool(loc)), cost=cost, cost_note=note,
                price_min=pmin, price_max=pmax, venue=_venue_from_text(loc) if loc else (venue_default or Venue()), organizer=SOURCE["name"],
                kind=(kind_map or {}).get(title, "program" if standing else "event"), categories=cats, recurring=recurring,
            ))
        return merge_slots(out)
    return SimpleNamespace(SOURCE=SOURCE, fetch=fetch)


def merge_slots(events):
    """Several start times for the same thing on the same day ("tours at 6:30, 7, 7:30...") become one listing."""
    groups, out = {}, []
    for e in events:
        if e.all_day or e.recurring:
            out.append(e)
            continue
        groups.setdefault((e.title.lower(), e.start.date()), []).append(e)
    for evs in groups.values():
        evs.sort(key=lambda x: x.start)
        first = evs[0]
        if len(evs) > 1:
            ends = [x.end or x.start for x in evs]
            first.end = max(ends)
            first.extra["times"] = [x.start.strftime("%-I:%M %p").replace(":00", "") for x in evs]
        out.append(first)
    return out


# ---------------------------------------------------------------- The Events Calendar (WordPress)
def tribe_source(SOURCE, base, *, tz=TZ):
    """WordPress sites running The Events Calendar: /wp-json/tribe/events/v1/events."""
    def fetch():
        out, page = [], 1
        while page <= 20:
            d = get_json(f"{base.rstrip('/')}/wp-json/tribe/events/v1/events",
                         params={"per_page": 50, "page": page, "start_date": date.today().isoformat(),
                                 "end_date": config.horizon().isoformat()})
            for e in d.get("events", []):
                z = ZoneInfo(e.get("timezone") or tz)
                all_day = bool(e.get("all_day"))
                s = datetime.strptime(e["start_date"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=z)
                en = datetime.strptime(e["end_date"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=z) if e.get("end_date") else None
                v = e.get("venue") if isinstance(e.get("venue"), dict) else {}
                desc = clean_text(e.get("description"))
                cost_txt = clean_text(e.get("cost") or "")
                cost, pmin, pmax, note = guess_cost(cost_txt or desc)
                if (e.get("cost_details") or {}).get("values") and cost == "unknown":
                    vals = [float(x) for x in e["cost_details"]["values"] if str(x).replace(".", "").isdigit()]
                    if vals:
                        cost = "free" if max(vals) == 0 else "paid"
                        pmin, pmax = min(vals), max(vals)
                img = (e.get("image") or {}).get("url") if isinstance(e.get("image"), dict) else None
                out.append(Event(
                    source=SOURCE["id"], source_event_id=str(e["id"]), title=clean_text(e.get("title")),
                    start=s, end=en if (en and en > s) else None, all_day=all_day, timezone=str(z), url=e.get("url"),
                    description=desc, image=img, attendance=guess_attendance(desc, bool(v)), cost=cost,
                    cost_note=cost_txt or note, price_min=pmin, price_max=pmax,
                    registration_url=e.get("website") or None,
                    venue=Venue(name=clean_text(v.get("venue")) or None, address=v.get("address") or None,
                                city=v.get("city") or None, region=(v.get("stateprovince") or v.get("state") or "")[:2] or None,
                                postal_code=v.get("zip") or None,
                                lat=float(v["geo_lat"]) if v.get("geo_lat") else None,
                                lon=float(v["geo_lng"]) if v.get("geo_lng") else None),
                    organizer=clean_text(((e.get("organizer") or [{}])[0] or {}).get("organizer")) or SOURCE["name"],
                    categories=[c.get("name") for c in e.get("categories") or [] if c.get("name")],
                ))
            if not d.get("next_rest_url"):
                break
            page += 1
        return out
    return SimpleNamespace(SOURCE=SOURCE, fetch=fetch)


# ---------------------------------------------------------------- Squarespace events collections
def squarespace_source(SOURCE, page_url, *, tz=TZ, default_venue=None, categories=()):
    """Squarespace event collections expose their items at <page>?format=json."""
    def fetch():
        d = get_json(page_url, params={"format": "json"})
        items = d.get("upcoming") or []
        if not items and d.get("collection", {}).get("typeName") == "events":
            items = d.get("items") or []
        base = re.match(r"https?://[^/]+", page_url).group(0)
        out = []
        for it in items:
            s = datetime.fromtimestamp(int(it["startDate"]) / 1000, tz=timezone.utc).astimezone(ZoneInfo(tz))
            en = datetime.fromtimestamp(int(it["endDate"]) / 1000, tz=timezone.utc).astimezone(ZoneInfo(tz)) if it.get("endDate") else None
            if (en or s).date() < date.today():
                continue
            loc = it.get("location") or {}
            named = loc.get("addressTitle") or ""
            venue = Venue(name=named or None, address=loc.get("addressLine1") or None, city=None,
                          region=None) if named else (default_venue or Venue())
            desc = clean_text(it.get("excerpt") or it.get("body"))
            cost, pmin, pmax, note = guess_cost(desc)
            out.append(Event(
                source=SOURCE["id"], source_event_id=it.get("id") or it.get("urlId") or it["fullUrl"],
                title=clean_text(it.get("title")), start=s, end=en if (en and en > s) else None, timezone=tz,
                url=base + it["fullUrl"] if it.get("fullUrl", "").startswith("/") else it.get("fullUrl"),
                description=desc, image=it.get("assetUrl") or None, attendance="in_person",
                cost=cost, cost_note=note, price_min=pmin, price_max=pmax, venue=venue,
                organizer=SOURCE["name"], categories=list(categories) + list(it.get("categories") or []),
            ))
        return out
    return SimpleNamespace(SOURCE=SOURCE, fetch=fetch)
