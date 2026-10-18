"""Theodore Roosevelt National Park events, via the official NPS Data API.

developer.nps.gov/api/v1/events (set NPS_API_KEY; DEMO_KEY works but is rate-limited).
The API returns each event's expanded `dates` and `times`, plus an `isfree` flag.
"""
from __future__ import annotations

import re
from datetime import date, datetime

from .. import config
from ..http import get_json
from ..model import Event, Venue, at, clean_text, guess_attendance, parse_clock

SOURCE = {
    "id": "nps",
    "name": "Theodore Roosevelt National Park",
    "short": "TR National Park",
    "url": "https://www.nps.gov/planyourvisit/event-search.htm#/?parkCode=thro",
    "type": "partner",
    "region": "Medora, ND",
}
PARKS = {
    "thro": ("Theodore Roosevelt National Park", "America/Denver", "Medora", "ND"),
}
API = "https://developer.nps.gov/api/v1/events"


def fetch() -> list[Event]:
    today = date.today()
    rows, page = [], 1
    while True:
        d = get_json(API, params={
            "parkCode": ",".join(PARKS), "api_key": config.NPS_API_KEY, "pageSize": 50, "pageNumber": page,
            "dateStart": today.isoformat(), "dateEnd": config.horizon().isoformat(),
        })
        data = d.get("data", [])
        rows += data
        if not data or len(rows) >= int(d.get("total") or 0):
            break
        page += 1

    events = []
    for r in rows:
        code = r.get("sitecode")
        park, tz, city, region = PARKS.get(code, (r.get("parkfullname"), "America/New_York", None, None))
        title = (r.get("title") or "").strip()
        is_closure = bool(re.match(r"^\s*(closed|closure|park closed)\b", title, re.I))
        cancelled = set(r.get("cancelleddatelist") or [])
        dates = sorted(set(r.get("dates") or []))
        recurring = str(r.get("isrecurring")).lower() == "true" and len(dates) > 1
        limit = config.horizon(recurring=recurring)
        times = r.get("times") or [{}]
        allday = str(r.get("isallday")).lower() == "true"
        desc = clean_text(r.get("description"))
        free = str(r.get("isfree")).lower() == "true"
        fee = clean_text(r.get("feeinfo"))
        loc = clean_text(r.get("location"))
        text = f"{title} {desc} {loc}"
        attendance = guess_attendance(text, True)
        images = r.get("images") or []
        image = images[0].get("url") if images else None
        if image and image.startswith("/"):
            image = "https://www.nps.gov" + image
        venue = Venue(name=park, address=loc or None, city=city, region=region,
                      lat=float(r["latitude"]) if r.get("latitude") else None,
                      lon=float(r["longitude"]) if r.get("longitude") else None)
        url = r.get("infourl") or f"https://www.nps.gov/planyourvisit/event-details.htm?id={r.get('id')}"
        for ds in dates:
            d = datetime.strptime(ds, "%Y-%m-%d").date()
            if d < today or d > limit:
                continue
            for t in times:
                t0 = None if allday else parse_clock(t.get("timestart", ""))
                t1 = None if allday else parse_clock(t.get("timeend", ""))
                events.append(Event(
                    source="nps", source_event_id=str(r.get("id")), title=title,
                    start=at(d, t0, tz), end=at(d, t1, tz) if t1 else None, all_day=t0 is None, timezone=tz,
                    url=url, description=desc, image=image, attendance=attendance,
                    cost="free" if free else ("paid" if fee or re.search(r"\$\d", desc) else "unknown"),
                    cost_note=fee or None, registration_required=str(r.get("isregresrequired")).lower() == "true",
                    registration_url=r.get("regresurl") or None, venue=venue, organizer=park,
                    kind="closure" if is_closure else ("tour" if any("tour" in x.lower() for x in r.get("types") or []) else "event"),
                    categories=r.get("types") or [], recurring=recurring,
                    status="cancelled" if ds in cancelled else "scheduled",
                    extra={"park_code": code, "nps_category": r.get("category"), "reservation_info": clean_text(r.get("regresinfo")) or None,
                           "contact": r.get("contactemailaddress") or r.get("contacttelephonenumber") or None},
                ))
    return events
