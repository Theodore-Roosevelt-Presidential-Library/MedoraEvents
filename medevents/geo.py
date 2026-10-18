"""Put every in-person event on the map.

Order of precedence for an event's coordinates:
  1. config/venues.yaml        hand-checked pins (always wins; staff can fix any pin here)
  2. coordinates the calendar itself published (CitySpark, Facebook), if they fall in the region
  3. OpenStreetMap Nominatim   "<venue>, <town>, ND", cached in data/geocode.json
  4. the town's center          marked geo_precision="town" so the map can say "location approximate"

Nominatim's usage policy allows one request a second with an identifying User-Agent; results are cached
forever, so after the first run only new venues are looked up (capped per run).
"""
from __future__ import annotations

import json
import math
import re
import time
from pathlib import Path

import requests
import yaml

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "data" / "geocode.json"
VENUES = ROOT / "config" / "venues.yaml"
MEDORA = (46.9139, -103.5244)
MAX_KM = 260          # anything farther than this from Medora is not "the region"
MAX_LOOKUPS = 80      # new Nominatim queries per run
UA = "MedoraEvents/1.0 (+https://medoraevents.labs.trlibrary.com)"
VIEWBOX = "-106.5,48.9,-100.5,45.4"   # western ND, eastern MT, northwest SD
VAGUE = re.compile(r"^(throughout|downtown|various|tbd|tba|online|virtual|medora city|city of)\b", re.I)


def km(a, b) -> float:
    la1, lo1, la2, lo2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 6371 * 2 * math.asin(math.sqrt(h))


def _key(s: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", (s or "").lower().replace("&", "and"))).strip()


class Geocoder:
    def __init__(self):
        try:
            self.cache = json.loads(CACHE.read_text())
        except (OSError, ValueError):
            self.cache = {}
        try:
            raw = yaml.safe_load(VENUES.read_text()) or {}
        except OSError:
            raw = {}
        self.pins = {}
        for name, v in (raw.get("venues") or {}).items():
            for alias in [name] + (v.get("aliases") or []):
                self.pins[_key(alias)] = (float(v["lat"]), float(v["lon"]))
        self.lookups = 0
        self.dirty = False
        self._last = 0.0

    def _nominatim(self, q: str):
        if q in self.cache:
            return self.cache[q]
        if self.lookups >= MAX_LOOKUPS:
            return None
        self.lookups += 1
        wait = 1.1 - (time.time() - self._last)
        if wait > 0:
            time.sleep(wait)
        self._last = time.time()
        try:
            r = requests.get("https://nominatim.openstreetmap.org/search", timeout=20, headers={"User-Agent": UA},
                             params={"q": q, "format": "jsonv2", "limit": 1, "countrycodes": "us",
                                     "viewbox": VIEWBOX, "bounded": 1})
            r.raise_for_status()
            d = r.json()
            hit = [float(d[0]["lat"]), float(d[0]["lon"]), d[0].get("display_name", "")[:120]] if d else None
        except (requests.RequestException, ValueError, KeyError, IndexError):
            return None        # not cached, so it's retried next run
        self.cache[q] = hit
        self.dirty = True
        return hit

    def town(self, city: str, region: str | None):
        if not city:
            return None
        hit = self._nominatim(f"{city}, {region or 'ND'}")
        return (hit[0], hit[1]) if hit else None

    def locate(self, e: dict):
        """Returns (lat, lon, precision) or None."""
        if e.get("attendance") == "virtual":
            return None
        v = e.get("venue") or {}
        name, city, region = (v.get("name") or "").strip(), (v.get("city") or "").strip(), (v.get("region") or "ND").strip()
        for k in (_key(f"{name} {city}"), _key(name)):
            if k and k in self.pins:
                return (*self.pins[k], "venue")
        if v.get("lat") and v.get("lon"):
            p = (float(v["lat"]), float(v["lon"]))
            if km(p, MEDORA) <= MAX_KM:
                return (*p, "venue")
        if name and not VAGUE.search(name) and _key(name) != _key(city):
            q = ", ".join(x for x in (name, v.get("address"), city, region) if x)
            hit = self._nominatim(q)
            if hit and km(hit, MEDORA) <= MAX_KM:
                return (hit[0], hit[1], "venue")
        city = re.sub(r"^(throughout|downtown|around|historic)\s+", "", city, flags=re.I)
        if (not city or VAGUE.search(city)) and e.get("area") == "medora":
            city = "Medora"
        t = self.town(city, region)
        if t and km(t, MEDORA) <= MAX_KM:
            return (*t, "town")
        return None

    def save(self):
        if self.dirty:
            CACHE.parent.mkdir(exist_ok=True)
            CACHE.write_text(json.dumps(self.cache, indent=1, sort_keys=True))
