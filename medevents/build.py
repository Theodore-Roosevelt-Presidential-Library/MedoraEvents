"""Run every source, merge, de-duplicate and publish the JSON API, iCal feeds and widget data.

    python -m medevents.build              # all sources
    python -m medevents.build --only trpl  # one or more sources (others reuse their last good data)
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import time
import traceback
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import yaml

from . import config, ics
from .fields import as_json as fields_json
from .model import Event, Venue, at, clean_text, guess_attendance, guess_cost
from .dedupe import dedupe
from zoneinfo import ZoneInfo

from .places import classify, drive_label, town_tz
from .geo import Geocoder
from .sources import ALL, BY_ID

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"
DATA = ROOT / "data"
API = DOCS / "api" / "v1"

MANUAL_SOURCE = {"id": "manual", "name": "Added by the TR Presidential Library", "short": "Added by TRPL",
                 "url": config.SITE_URL, "type": "core", "region": ""}


def _read_json(p: Path, default):
    try:
        return json.loads(p.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def _write_json(p: Path, obj, compact=False):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, ensure_ascii=False, separators=(",", ":")) if compact
                 else json.dumps(obj, ensure_ascii=False, indent=1))


def norm_title(t: str) -> str:
    t = t.lower()
    t = re.sub(r"\b(the|a|an|and|of|at|with|in|for|on)\b", " ", t)
    return re.sub(r"[^a-z0-9]+", "", t)


def load_overrides() -> dict:
    p = ROOT / "config" / "overrides.yaml"
    return (yaml.safe_load(p.read_text()) if p.exists() else None) or {}


def manual_events() -> list[dict]:
    p = ROOT / "config" / "manual_events.yaml"
    rows = (yaml.safe_load(p.read_text()) if p.exists() else None) or []
    out = []
    for i, r in enumerate(rows):
        tz = r.get("timezone", "America/New_York")
        def dt(v):
            if isinstance(v, datetime):
                return v if v.tzinfo else v.replace(tzinfo=__import__("zoneinfo").ZoneInfo(tz))
            if isinstance(v, date):
                return at(v, None, tz)
            return datetime.fromisoformat(str(v)).replace(tzinfo=__import__("zoneinfo").ZoneInfo(tz))
        start = dt(r["start"])
        all_day = r.get("all_day", isinstance(r["start"], date) and not isinstance(r["start"], datetime))
        desc = clean_text(r.get("description", ""))
        cost = r.get("cost") or guess_cost(desc)[0]
        e = Event(source="manual", source_event_id=r.get("id") or f"manual-{i}", title=r["title"], start=start,
                  end=dt(r["end"]) if r.get("end") else None, all_day=all_day, timezone=tz, url=r.get("url"),
                  description=desc, image=r.get("image"),
                  attendance=r.get("attendance") or guess_attendance(desc, bool(r.get("venue"))),
                  cost=cost, cost_note=r.get("cost_note"), registration_url=r.get("registration_url"),
                  venue=Venue(**(r.get("venue") or {})), organizer=r.get("organizer"), kind=r.get("kind", "event"),
                  categories=r.get("categories", []))
        d = e.to_dict()
        d["source_name"] = MANUAL_SOURCE["name"]
        out.append(d)
    return out


def run_sources(only: set[str] | None) -> tuple[list[dict], list[dict]]:
    today = date.today().isoformat()
    store_dir = DATA / "store"
    all_events, statuses = [], []
    prev_status = {s["id"]: s for s in _read_json(API / "sources.json", {}).get("sources", [])}
    for mod in ALL:
        src = mod.SOURCE
        sid = src["id"]
        status = {**src, "ok": False, "count": 0, "error": None, "last_success": prev_status.get(sid, {}).get("last_success"),
                  "checked": datetime.now(timezone.utc).isoformat(timespec="seconds")}
        stored = _read_json(store_dir / f"{sid}.json", {})
        every = src.get("every_days")
        fresh = stored.get("fetched") and (date.today() - date.fromisoformat(stored["fetched"])).days < (every or 0)
        if (only and sid not in only) or (fresh and not (only and sid in only)):
            evs = stored.get("events", [])
            status.update({k: prev_status.get(sid, {}).get(k) for k in ("ok", "error", "checked", "seconds")})
            status["count"] = len(evs)
            all_events += evs
            statuses.append(status)
            continue
        t0 = time.time()
        try:
            evs = [e.to_dict() for e in mod.fetch()]
            for e in evs:
                e["source_name"] = src["name"]
            status.update(ok=True, count=len(evs), last_success=today)
            _write_json(store_dir / f"{sid}.json", {"fetched": today, "events": evs})
        except Exception as ex:  # keep the last good data for a while instead of blanking the source
            status["error"] = f"{type(ex).__name__}: {ex}"[:400]
            traceback.print_exc()
            age = (date.today() - date.fromisoformat(stored["fetched"])).days if stored.get("fetched") else 999
            evs = stored.get("events", []) if age <= config.STALE_DAYS else []
            status["count"] = len(evs)
            status["using_cached_from"] = stored.get("fetched") if evs else None
        status["seconds"] = round(time.time() - t0, 1)
        print(f"{sid:12} {'ok ' if status['ok'] else 'ERR'} {status['count']:5} events  {status['seconds']}s  {status['error'] or ''}")
        all_events += evs
        statuses.append(status)
    return all_events, statuses


def finalize(events: list[dict], statuses: list[dict]) -> list[dict]:
    today = date.today()
    ov = load_overrides()
    excl = ov.get("exclude") or []
    edits = ov.get("edits") or {}
    region = {s["id"]: s.get("region", "") for s in statuses}

    def excluded(e):
        for rule in excl:
            if rule.get("id") in (e["id"], e["series_id"]) or (rule.get("url") and rule["url"] == e.get("url")):
                return True
            if rule.get("title") and re.search(rule["title"], e["title"], re.I) and rule.get("source", e["source"]) == e["source"]:
                return True
        return False

    # drop past events (ended before today)
    keep = []
    for e in events:
        end = (e.get("end") or e["start"])[:10]
        if end >= today.isoformat() and not excluded(e):
            keep.append(e)

    # de-duplicate the same event listed by several organizations (sources are in priority order)
    order = {m.SOURCE["id"]: i for i, m in enumerate(ALL)}
    order["manual"] = -1
    out = dedupe(keep, order)

    # first_seen / last_seen bookkeeping
    state = _read_json(DATA / "state.json", {})
    t = today.isoformat()
    geo = Geocoder()
    for e in out:
        e.setdefault("also_listed", [])
        e["first_seen"] = state.get(e["id"], t)
        e["last_seen"] = t
        state[e["id"]] = e["first_seen"]
        v = e.get("venue") or {}
        e["region_label"] = ", ".join(x for x in (v.get("city"), v.get("region")) if x) or region.get(e["source"], "")
        tz = town_tz(e)
        if tz and tz != e.get("timezone"):
            # same moment in time, shown on the clock of the town where it happens
            z = ZoneInfo(tz)
            if not e.get("all_day") and len(e["start"]) > 10:
                e["start"] = datetime.fromisoformat(e["start"]).astimezone(z).isoformat()
                if e.get("end") and len(e["end"]) > 10:
                    e["end"] = datetime.fromisoformat(e["end"]).astimezone(z).isoformat()
            e["timezone"] = tz
        e.update(classify(e))
        e["drive_label"] = drive_label(e["drive_minutes"], e.get("timezone"))
        pin = geo.locate(e)
        e["lat"], e["lon"], e["geo_precision"] = pin if pin else (None, None, None)
        for key in (e["id"], e["series_id"]):
            if key in edits:
                e.update(edits[key])
    cutoff = (today - timedelta(days=60)).isoformat()
    live = {e["id"] for e in out}
    state = {k: v for k, v in state.items() if k in live or v >= cutoff}
    _write_json(DATA / "state.json", state)
    geo.save()
    out.sort(key=lambda e: (e["start"] if "T" in e["start"] else e["start"] + "T00:00", e["title"]))
    return out


def collapse_series(events: list[dict]) -> list[dict]:
    """One row per recurring series (its next occurrence, with a count); one-offs pass through."""
    seen, out = {}, []
    for e in events:
        if not e.get("recurring"):
            out.append(e)
            continue
        if e["series_id"] in seen:
            seen[e["series_id"]]["occurrences"] += 1
            continue
        row = {**e, "occurrences": 1}
        seen[e["series_id"]] = row
        out.append(row)
    return out


def publish(events: list[dict], statuses: list[dict]) -> None:
    gen = datetime.now(timezone.utc).isoformat(timespec="seconds")
    meta = {"generated": gen, "site": config.SITE_URL, "fields": f"{config.SITE_URL}/api/v1/fields.json",
            "sources": f"{config.SITE_URL}/api/v1/sources.json"}
    if API.exists():
        shutil.rmtree(API)
    API.mkdir(parents=True)
    visible = [e for e in events if e["kind"] != "closure"]
    _write_json(API / "events.json", {**meta, "count": len(events), "events": events})
    _write_json(API / "events.min.json", {**meta, "count": len(events), "events": events}, compact=True)
    up = collapse_series(visible)[:200]
    _write_json(API / "upcoming.json", {**meta, "count": len(up), "events": up})
    # lightweight index the widgets load
    slim_keys = ["id", "series_id", "source", "title", "summary", "url", "image", "start", "end", "all_day", "timezone",
                 "attendance", "cost", "cost_note", "price_min", "kind", "recurring", "status", "region_label", "relevance",
                 "registration_url", "area", "area_label", "drive_minutes", "drive_label", "categories", "lat", "lon", "geo_precision"]
    slim = [{k: e.get(k) for k in slim_keys} | {"venue": (e.get("venue") or {}).get("name"),
                                                 "times": (e.get("extra") or {}).get("times")} for e in events]
    _write_json(API / "widget.json", {**meta, "sources": [{k: s[k] for k in ("id", "name", "short", "url", "type", "region")} for s in statuses + [MANUAL_SOURCE]],
                                      "events": slim}, compact=True)
    months = defaultdict(list)
    for e in events:
        months[e["start"][:7]].append(e)
    for m, evs in months.items():
        _write_json(API / "months" / f"{m}.json", {**meta, "month": m, "count": len(evs), "events": evs})
    by_src = defaultdict(list)
    for e in events:
        by_src[e["source"]].append(e)
    for s in statuses:
        _write_json(API / "sources" / f"{s['id']}.json", {**meta, "source": s, "count": len(by_src[s["id"]]), "events": by_src[s["id"]]})
    _write_json(API / "sources.json", {**meta, "sources": statuses})
    _write_json(API / "fields.json", {**meta, "fields": fields_json()})
    review = [e for e in events if (e.get("extra") or {}).get("time_conflicts") or (e.get("extra") or {}).get("date_from_text")]
    _write_json(API / "review.json", {**meta, "note": "Events where calendars disagree on the start time (see extra.time_conflicts), and dates read from prose. "
                                      "Fix in config/overrides.yaml.", "count": len(review), "events": review})

    # iCal feeds
    feeds = DOCS / "ics"
    if feeds.exists():
        shutil.rmtree(feeds)
    feeds.mkdir(parents=True)
    special = [e for e in visible if not (e.get("recurring") and e["kind"] in ("tour", "program"))]
    ics.write(DOCS / "calendar.ics", special, "Medora Events", "Events in Medora and the nearby Badlands: concerts, talks, races, festivals and more.")
    ics.write(DOCS / "calendar-all.ics", visible, "Medora Events (everything)", "Every Medora-area listing, including daily activities and tours.")
    ics.write(feeds / "medora.ics", [e for e in special if e.get("area") == "medora"], "Medora Events — in town", "Events in Medora and the South Unit of Theodore Roosevelt National Park.")
    ics.write(feeds / "nearby.ics", [e for e in special if e.get("area") == "nearby"], "Medora Events — worth the drive", "Events out of Medora: Dickinson, Belfield, Beach, Watford City and the region.")
    ics.write(feeds / "free.ics", [e for e in special if e["cost"] == "free"], "Medora Events — free", "Free events in and around Medora.")
    for s in statuses:
        ics.write(feeds / f"{s['id']}.ics", [e for e in visible if e["source"] == s["id"]], f"Medora Events — {s['short']}", f"Events from {s['name']}.")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", help="comma-separated source ids to refresh")
    args = ap.parse_args()
    only = set(args.only.split(",")) if args.only else None
    if only and not only <= set(BY_ID):
        raise SystemExit(f"unknown source(s): {only - set(BY_ID)}")
    events, statuses = run_sources(only)
    events += manual_events()
    events = finalize(events, statuses)
    publish(events, statuses)
    print(f"published {len(events)} events")


if __name__ == "__main__":
    main()
