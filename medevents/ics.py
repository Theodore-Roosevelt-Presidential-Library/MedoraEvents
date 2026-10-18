"""Minimal RFC 5545 writer (UTC times, all-day dates, line folding)."""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from . import config

LABEL = {"in_person": "In person", "virtual": "Virtual", "hybrid": "Hybrid (in person + online)", "unknown": ""}
COST = {"free": "Free", "paid": "Paid", "unknown": ""}


def _esc(s: str) -> str:
    return (s or "").replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\r", "").replace("\n", "\\n")


def _fold(line: str) -> str:
    b = line.encode("utf-8")
    if len(b) <= 75:
        return line
    out, cur = [], b""
    for ch in line:
        c = ch.encode("utf-8")
        if len(cur) + len(c) > (75 if not out else 74):
            out.append(cur.decode("utf-8"))
            cur = b""
        cur += c
    out.append(cur.decode("utf-8"))
    return "\r\n ".join(out)


def _utc(s: str) -> str:
    return datetime.fromisoformat(s).astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _vevent(e: dict, stamp: str) -> list[str]:
    L = ["BEGIN:VEVENT", f"UID:{e['id']}@medoraevents.labs.trlibrary.com", f"DTSTAMP:{stamp}"]
    if e["all_day"]:
        d0 = date.fromisoformat(e["start"][:10])
        d1 = date.fromisoformat(e["end"][:10]) if e.get("end") else d0
        L += [f"DTSTART;VALUE=DATE:{d0:%Y%m%d}", f"DTEND;VALUE=DATE:{d1 + timedelta(days=1):%Y%m%d}"]
    else:
        L.append(f"DTSTART:{_utc(e['start'])}")
        end = e.get("end") or (datetime.fromisoformat(e["start"]) + timedelta(hours=1)).isoformat()
        L.append(f"DTEND:{_utc(end)}")
    tags = [x for x in (LABEL.get(e["attendance"]), COST.get(e["cost"]), e.get("cost_note")) if x]
    head = " · ".join(tags)
    desc = "\n\n".join(x for x in (head, e.get("summary") or "", f"Listed by {e.get('source_name', e['source'])}", e.get("url") or "") if x)
    v = e.get("venue") or {}
    loc = ", ".join(x for x in (v.get("name"), v.get("address"), v.get("city"), v.get("region")) if x)
    if e["attendance"] == "virtual" and not loc:
        loc = "Online"
    L += [f"SUMMARY:{_esc(e['title'])}", f"DESCRIPTION:{_esc(desc)}"]
    if loc:
        L.append(f"LOCATION:{_esc(loc)}")
    if e.get("url"):
        L.append(f"URL:{e['url']}")
    if v.get("lat") and v.get("lon"):
        L.append(f"GEO:{v['lat']};{v['lon']}")
    cats = [c for c in [e.get("source_name"), LABEL.get(e["attendance"]), COST.get(e["cost"]), e.get("kind", "").title()] if c]
    L.append("CATEGORIES:" + ",".join(_esc(c) for c in cats))
    if e.get("status") == "cancelled":
        L.append("STATUS:CANCELLED")
    else:
        L.append("STATUS:CONFIRMED")
    L.append("END:VEVENT")
    return L


def write(path: Path, events: list[dict], name: str, desc: str) -> None:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    L = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Theodore Roosevelt Presidential Library//MedoraEvents//EN",
         "CALSCALE:GREGORIAN", "METHOD:PUBLISH", f"X-WR-CALNAME:{_esc(name)}", f"X-WR-CALDESC:{_esc(desc)}",
         "X-WR-TIMEZONE:America/Chicago", "REFRESH-INTERVAL;VALUE=DURATION:PT6H", "X-PUBLISHED-TTL:PT6H",
         f"SOURCE;VALUE=URI:{config.SITE_URL}/{path.name if path.parent.name != 'ics' else 'ics/' + path.name}"]
    for e in events:
        L += _vevent(e, stamp)
    L.append("END:VCALENDAR")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\r\n".join(_fold(l) for l in L) + "\r\n", encoding="utf-8")
