"""Collapse the same event listed by several organizations into one record.

Medora events are re-posted everywhere — the Foundation, the Chamber, the visitors bureau,
ND Tourism, the Dickinson Press and Facebook all carry the same Cowboy Christmas. Two listings
are treated as one event when their dates overlap, their start times (if both have one) are
within 90 minutes, and their titles match closely enough after normalising.

The copy from the higher-priority source is kept; gaps in it (image, description, price, time,
venue) are filled from the duplicates, and every other listing is recorded in `also_listed`.
"""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from difflib import SequenceMatcher

GENDER = {"mens", "womens", "men", "women", "boys", "girls", "jv", "varsity"}
STOP = {"dickinson", "state", "university", "dsu", "the", "a", "an", "and", "of", "at", "in", "on", "for", "with", "to", "by", "nd", "north", "dakota",
        "medora", "medoras", "annual", "live", "music", "event", "events", "presents", "featuring", "feat", "ft",
        "night", "tour", "tours", "show", "2026", "2027", "2028", "s"}


def tokens(title: str) -> list[str]:
    t = title.lower().replace("&", " and ")
    t = re.sub(r"[’'`]", "", t)
    t = re.sub(r"[^a-z0-9]+", " ", t)
    return [w for w in t.split() if w not in STOP and not re.fullmatch(r"\d{1,2}(st|nd|rd|th)?", w)]


def similar(a: str, b: str) -> float:
    ta, tb = tokens(a), tokens(b)
    if not ta or not tb:
        return SequenceMatcher(None, a.lower(), b.lower()).ratio()
    sa, sb = set(ta), set(tb)
    jacc = len(sa & sb) / len(sa | sb)
    contain = len(sa & sb) / min(len(sa), len(sb))
    seq = SequenceMatcher(None, " ".join(ta), " ".join(tb)).ratio()
    score = max(jacc, seq)
    if contain == 1 and min(len(sa), len(sb)) >= 2:   # "Cowboy Christmas" inside "Old Fashioned Cowboy Christmas"
        score = max(score, 0.85)
    return score


def _span(e):
    s = date.fromisoformat(e["start"][:10])
    en = date.fromisoformat((e.get("end") or e["start"])[:10])
    return s, max(s, en)


def _minutes(e):
    if e.get("all_day") or len(e["start"]) <= 10:
        return None
    d = datetime.fromisoformat(e["start"])
    return d.hour * 60 + d.minute


def same_event(a, b) -> bool:
    (a0, a1), (b0, b1) = _span(a), _span(b)
    if a1 < b0 or b1 < a0:
        return False
    ma, mb = _minutes(a), _minutes(b)
    if ma is not None and mb is not None and a0 == b0 and abs(ma - mb) > 90:
        return False
    ta, tb = set(tokens(a["title"])), set(tokens(b["title"]))
    if (ta & GENDER) != (tb & GENDER):          # men's vs women's game, JV vs varsity
        return False
    loose = ta and tb and len(ta & tb) / len(ta | tb) < 0.34 and not (ta <= tb or tb <= ta)
    if loose and not (ma is not None and mb is not None and a0 == b0 and abs(ma - mb) <= 60 and len(ta & tb) >= 2):
        return False
    sim = similar(a["title"], b["title"])
    if ma is not None and mb is not None and a0 == b0 and abs(ma - mb) <= 60 and len(ta & tb) >= 2:
        return True   # same day, same hour, two or more distinctive words in common
    if sim >= 0.8:
        return True
    if sim >= 0.6:  # looser title match needs the same place
        va, vb = (a.get("venue") or {}), (b.get("venue") or {})
        ca, cb = (va.get("city") or "").lower(), (vb.get("city") or "").lower()
        na, nb = (va.get("name") or "").lower(), (vb.get("name") or "").lower()
        return bool((ca and ca == cb) or (na and nb and SequenceMatcher(None, na, nb).ratio() > 0.7))
    return False


FILL = ("image", "description", "summary", "registration_url", "online_url", "price_min", "price_max", "cost_note")


def merge(keep, dup):
    for k in FILL:
        if not keep.get(k) and dup.get(k):
            keep[k] = dup[k]
    if keep.get("cost") == "unknown" and dup.get("cost") != "unknown":
        keep["cost"], keep["price_min"], keep["price_max"] = dup["cost"], dup.get("price_min"), dup.get("price_max")
    if keep.get("attendance") == "unknown" and dup.get("attendance") != "unknown":
        keep["attendance"] = dup["attendance"]
    if not keep.get("all_day") and not dup.get("all_day") and keep["start"][:16] != dup["start"][:16]:
        keep.setdefault("extra", {}).setdefault("time_conflicts", []).append({"source": dup["source"], "start": dup["start"]})
    if keep.get("all_day") and not dup.get("all_day") and keep["start"][:10] == dup["start"][:10]:
        keep["start"], keep["end"], keep["all_day"] = dup["start"], dup.get("end"), False
    kv, dv = keep.get("venue") or {}, dup.get("venue") or {}
    for k, v in dv.items():
        if not kv.get(k) and v:
            kv[k] = v
    keep["venue"] = kv
    if dup["source"] != keep["source"] and dup["source"] not in {x["source"] for x in keep.setdefault("also_listed", [])}:
        keep["also_listed"].append({"source": dup["source"], "url": dup.get("url"), "title": dup["title"]})


def dedupe(events: list[dict], priority: dict) -> list[dict]:
    events = sorted(events, key=lambda e: (priority.get(e["source"], 99), e["start"]))
    by_day: dict[date, list] = {}
    out = []
    for e in events:
        s, en = _span(e)
        days = [s + timedelta(days=i) for i in range(min((en - s).days, 14) + 1)]
        match = None
        for d in days:
            for k in by_day.get(d, []):
                if k is not e and not (e.get("recurring") and k.get("recurring") and k["source"] == e["source"]) and same_event(k, e):
                    match = k
                    break
            if match:
                break
        if match and not (match["source"] == e["source"] and match["start"] != e["start"]):
            merge(match, e)
            continue
        e.setdefault("also_listed", [])
        out.append(e)
        for d in days:
            by_day.setdefault(d, []).append(e)
    return out
