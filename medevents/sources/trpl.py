"""Theodore Roosevelt Presidential Library — trlibrary.com/calendar (Drupal).

Event pages are discovered from the sitemap. Each page carries schema.org Event JSON-LD
(attendance mode, status, place) and an "All Hours" table of date ranges, days and times,
which is what gets expanded into individual occurrences.
"""
from __future__ import annotations

import json
import re
from datetime import date, datetime

from bs4 import BeautifulSoup

from .. import config
from ..http import get
from ..model import Event, Venue, at, clean_text, guess_cost, parse_clock

SOURCE = {
    "id": "trpl",
    "name": "Theodore Roosevelt Presidential Library",
    "short": "TR Presidential Library",
    "url": "https://www.trlibrary.com/calendar",
    "type": "partner",
    "region": "Medora, ND",
}
TZ = "America/Denver"
BASE = "https://www.trlibrary.com"
KIND = {"special-event": "event", "specialty-tour": "tour", "daily-activity": "program"}
MONTHS = {m: i for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}
DOW = {"mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6}
ATTEND = {
    "OfflineEventAttendanceMode": "in_person",
    "OnlineEventAttendanceMode": "virtual",
    "MixedEventAttendanceMode": "hybrid",
}


def event_urls() -> list[str]:
    xml = get(f"{BASE}/sitemap.xml").text
    urls = re.findall(r"<loc>(https://www\.trlibrary\.com/calendar/[a-z-]+/[^<]+)</loc>", xml)
    return sorted(set(urls))


def _md(s: str, default_year: int | None = None) -> date | None:
    m = re.match(r"([A-Za-z]{3})\w*\.? (\d{1,2})(?:, (\d{4}))?", s.strip())
    if not m:
        return None
    y = int(m.group(3)) if m.group(3) else default_year
    if not y:
        return None
    return date(y, MONTHS[m.group(1).lower()[:3]], int(m.group(2)))


def parse_range(s: str) -> tuple[date, date] | None:
    """'Oct 2 – Nov 30, 2026' | 'Aug 8, 2026' | 'Dec 2, 2026 – Jan 10, 2027'"""
    parts = re.split(r"\s+[–-]\s+", s.strip())
    if len(parts) == 1:
        d = _md(parts[0])
        return (d, d) if d else None
    end = _md(parts[1])
    if not end:
        return None
    ym = re.search(r"\d{4}", parts[0])
    start = _md(parts[0], None if ym else end.year)
    if start and start > end and not ym:
        start = start.replace(year=end.year - 1)
    return (start, end) if start else None


def day_matcher(spec: str):
    """'Tue – Fri' | 'Sun, Wed – Sat' | '3rd, 10th, 17th' | 'Daily' -> predicate(date)."""
    spec = spec.strip().lower()
    if not spec or spec in ("daily", "every day", "all days"):
        return lambda d: True
    if re.search(r"\d", spec):
        days = {int(x) for x in re.findall(r"(\d{1,2})(?:st|nd|rd|th)", spec)}
        return lambda d: d.day in days
    allowed = set()
    for chunk in spec.split(","):
        ends = [DOW.get(x.strip()[:3]) for x in re.split(r"[–-]", chunk)]
        ends = [e for e in ends if e is not None]
        if len(ends) == 2:
            a, b = ends
            i = a
            while True:
                allowed.add(i)
                if i == b:
                    break
                i = (i + 1) % 7
        elif ends:
            allowed.add(ends[0])
    return lambda d: d.weekday() in allowed


def parse_schedule(soup: BeautifulSoup) -> list[tuple]:
    """Return unique (start_date, end_date, dayspec, time_text) rows from the All Hours table."""
    rows = []
    for h3 in soup.find_all("h3"):
        rng = parse_range(h3.get_text(" ", strip=True))
        if not rng:
            continue
        sib = h3.find_next_sibling()
        while sib is not None and sib.name == "div":
            spans = sib.find_all("span")
            if len(spans) >= 2:
                rows.append((rng[0], rng[1], spans[0].get_text(" ", strip=True), spans[-1].get_text(" ", strip=True)))
            sib = sib.find_next_sibling()
    seen, out = set(), []
    for r in rows:
        if r not in seen:
            seen.add(r)
            out.append(r)
    return out


def _label_block(text_lines: list[str], label: str, n: int = 2) -> list[str]:
    try:
        i = text_lines.index(label)
    except ValueError:
        return []
    return text_lines[i + 1 : i + 1 + n]


def fetch() -> list[Event]:
    events: list[Event] = []
    today = date.today()
    for url in event_urls():
        typ, slug = url.split("/calendar/")[1].split("/", 1)
        html = get(url).text
        soup = BeautifulSoup(html, "lxml")
        ld = None
        for s in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(s.string or "{}")
            except json.JSONDecodeError:
                continue
            for g in data.get("@graph", []):
                if g.get("@type") == "Event" and "superEvent" not in g:
                    ld = g
        if not ld:
            continue  # page with no schedule (past or unpublished event)

        for t in soup(["script", "style", "svg", "noscript"]):
            t.decompose()
        main = soup.find("main") or soup.body
        lines = [l for l in main.get_text("\n", strip=True).split("\n") if l.strip()]
        text = "\n".join(lines)

        price_txt = " ".join(_label_block(lines, "Price", 8)) + " " + " ".join(_label_block(lines, "Admission", 2))
        cost, pmin, pmax, note = guess_cost(price_txt)
        if "included with general admission" in text.lower():
            note = note or "Included with general admission"
        loc = _label_block(lines, "Location", 2)
        audience = _label_block(lines, "Audience", 1)
        access = _label_block(lines, "Accessibility", 1)
        place = ld.get("location", {}) or {}
        addr = place.get("address", {}) or {}
        geo = place.get("geo", {}) or {}
        venue = Venue(
            name=place.get("name") or SOURCE["name"],
            address=addr.get("streetAddress"),
            city=addr.get("addressLocality"),
            region=addr.get("addressRegion"),
            postal_code=addr.get("postalCode"),
            country=addr.get("addressCountry", "US"),
            lat=float(geo["latitude"]) if geo.get("latitude") else None,
            lon=float(geo["longitude"]) if geo.get("longitude") else None,
        )
        imgs = ld.get("image") or []
        image = imgs[-1] if isinstance(imgs, list) and imgs else (imgs if isinstance(imgs, str) else None)
        description = clean_text(ld.get("description") or "")
        attendance = ATTEND.get((ld.get("eventAttendanceMode") or "").rsplit("/", 1)[-1], "in_person")
        status = (ld.get("eventStatus") or "").rsplit("/", 1)[-1]
        status = {"EventCancelled": "cancelled", "EventPostponed": "postponed", "EventRescheduled": "scheduled"}.get(status, "scheduled")
        kind = KIND.get(typ, "event")
        if kind == "program" and re.search(
            r"\b(special|temporary|traveling|new|featured) exhibit(ion)?\b|\bexhibit(ion)? (opens|runs|is on view)\b|\bon view\b",
            f"{ld.get('name', '')} {description[:600]}", re.I):
            kind = "exhibition"

        base = dict(
            source="trpl", title=ld.get("name", "").strip(), timezone=TZ, url=url, description=description,
            image=image, attendance=attendance, cost=cost, cost_note=note, price_min=pmin, price_max=pmax,
            registration_required=None, registration_url=url, venue=venue, organizer=SOURCE["name"],
            kind=kind, categories=[typ.replace("-", " ").title()], audiences=audience,
            status=status, accessibility=access[0] if access else None,
            extra={"room": loc[1] if len(loc) > 1 else None, "setting": loc[0] if loc else None},
        )

        occurrences = []
        sched = parse_schedule(soup)
        if sched:
            for d0, d1, dayspec, times in sched:
                match = day_matcher(dayspec)
                tparts = re.split(r"\s+[–-]\s+", times)
                t0 = parse_clock(tparts[0]) if tparts else None
                t1 = parse_clock(tparts[1]) if len(tparts) > 1 else None
                horizon = config.horizon(recurring=(d1 - d0).days > 0)
                d = max(d0, today)
                while d <= min(d1, horizon):
                    if match(d):
                        occurrences.append((d, t0, t1))
                    d = date.fromordinal(d.toordinal() + 1)
        else:
            sd = datetime.fromisoformat(ld["startDate"]) if ld.get("startDate") else None
            ed = datetime.fromisoformat(ld["endDate"]) if ld.get("endDate") else None
            if sd and (ed or sd).date() >= today:
                occurrences.append((sd.date(), sd.timetz(), ed.timetz() if ed else None))

        # an exhibition open for weeks is one long event, not one per day
        if kind == "exhibition" and sched:
            d0 = min(r[0] for r in sched)
            d1 = max(r[1] for r in sched)
            if d1 >= today:
                events.append(Event(source_event_id=slug, start=at(d0, None, TZ), end=at(d1, None, TZ), all_day=True,
                                    recurring=False, extra={**base.pop("extra"), "hours": [f"{a:%b %d}–{b:%b %d}: {s} {t}" for a, b, s, t in sched]},
                                    **base))
            continue

        recurring = len(occurrences) > 1
        for d, t0, t1 in occurrences:
            start = at(d, t0.replace(tzinfo=None) if t0 else None, TZ)
            end = at(d, t1.replace(tzinfo=None), TZ) if t1 else None
            events.append(Event(source_event_id=slug, start=start, end=end, all_day=t0 is None,
                                recurring=recurring, **{**base, "extra": dict(base["extra"])}))
    return events
