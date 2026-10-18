"""Where an event is relative to Medora: in town, or a drive out (with an approximate drive time)."""
from __future__ import annotations

import re

# Approximate one-way drive minutes from Medora (Google Maps typical, rounded). Estimates, not promises.
DRIVE_MINUTES = {
    "sentinel butte": 20, "fryburg": 15, "belfield": 20, "beach": 25, "golva": 40, "south heart": 25,
    "dickinson": 35, "gladstone": 45, "taylor": 50, "richardton": 55, "hebron": 70, "killdeer": 75,
    "dunn center": 80, "halliday": 90, "grassy butte": 70, "watford city": 110, "amidon": 55, "bowman": 85,
    "marmarth": 75, "rhame": 85, "scranton": 100, "new england": 70, "mott": 90, "hettinger": 120,
    "wibaux": 45, "glendive": 75, "sidney": 120, "williston": 140, "bismarck": 135, "mandan": 130,
    "painted canyon": 10, "north unit": 105, "elkhorn ranch": 60, "little missouri state park": 90,
    "sully creek": 5, "bully pulpit": 5,
}
# Inside Medora or the South Unit of the national park, which starts at the edge of town
MEDORA_RX = re.compile(r"\b(medora|chateau de mor[eè]s|burning hills amphitheat|pitchfork steak|bully pulpit|"
                       r"south unit|old town hall theat|sully creek|cottonwood campground|peaceful valley|"
                       r"theodore roosevelt presidential library|tr presidential library|cowboy hall of fame)\b", re.I)
MEDORA_SOURCES = {"trpl", "chateau", "medora", "chamber", "discover", "uncorkd", "littlemo", "boots",
                  "badlandsministries", "ndchf"}


# Time zones for towns people drive to from Medora. Southwest ND (Adams, Billings, Bowman, Golden Valley,
# Grant, Hettinger, Slope, Stark, southern Dunn and McKenzie) and eastern Montana are Mountain; the rest of
# ND, including Watford City and northern Dunn/McKenzie, is Central.
CENTRAL = {"watford city", "halliday", "dunn center", "new town", "williston", "beulah", "hazen", "stanton",
           "center", "bismarck", "mandan", "new salem", "glen ullin", "hebron", "minot", "garrison", "tioga",
           "stanley", "parshall", "mandaree", "alexander", "arnegard", "keene", "north unit"}
MOUNTAIN = "America/Denver"


def town_tz(e: dict) -> str | None:
    v = e.get("venue") or {}
    city = (v.get("city") or "").lower().strip()
    region = (v.get("region") or "").upper()
    if city:   # the city field is authoritative ("Student Center" in Dickinson is not Center, ND)
        if city in CENTRAL:
            return "America/Chicago"
        if region == "MT" or city == "medora" or city in DRIVE_MINUTES:
            return MOUNTAIN
        return None
    text = " ".join(x for x in (v.get("address"), v.get("name")) if x).lower()
    if not text:
        return None
    if any(re.search(r"\b" + re.escape(t) + r"\b", text) for t in CENTRAL - {"center"}):
        return "America/Chicago"
    if region == "MT" or "medora" in text or any(re.search(r"\b" + re.escape(t) + r"\b", text) for t in DRIVE_MINUTES):
        return MOUNTAIN
    return None


def classify(e: dict) -> dict:
    v = e.get("venue") or {}
    where = " ".join(x for x in (v.get("name"), v.get("address"), v.get("city")) if x)
    text = f"{where} {e.get('title', '')}".lower()
    if e.get("attendance") == "virtual" and not where:
        return {"area": "online", "area_label": "Online", "drive_minutes": None}
    if "north unit" in text:
        return {"area": "nearby", "area_label": "Out of Medora", "drive_minutes": DRIVE_MINUTES["north unit"]}
    city = (v.get("city") or "").lower().strip()
    if city == "medora" or MEDORA_RX.search(where) or (not where and e["source"] in MEDORA_SOURCES):
        return {"area": "medora", "area_label": "In Medora", "drive_minutes": 0}
    if e["source"] == "nps" and not city:
        return {"area": "medora", "area_label": "In Medora", "drive_minutes": 0}
    mins = None
    for place, m in DRIVE_MINUTES.items():
        if re.search(r"\b" + re.escape(place) + r"\b", text):
            mins = m if mins is None else min(mins, m)
    if mins is None and e["source"] in MEDORA_SOURCES and not city:
        return {"area": "medora", "area_label": "In Medora", "drive_minutes": 0}
    return {"area": "nearby", "area_label": "Out of Medora", "drive_minutes": mins}


def drive_label(mins, tz=None):
    note = " · Central time, an hour ahead of Medora" if tz == "America/Chicago" else ""
    if not mins:
        return note[3:] if note else None
    if mins < 60:
        return f"About {round(mins / 5) * 5} min from Medora{note}"
    h, m = divmod(mins, 60)
    return (f"About {h} hr{'' if m < 8 else f' {round(m / 15) * 15} min'} from Medora".replace(" 60 min", "")) + note
