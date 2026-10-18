"""The common event record and the classifiers every source shares."""
from __future__ import annotations

import hashlib
import html
import re
from dataclasses import dataclass, field, asdict
from datetime import date, datetime, time, timedelta
from typing import Optional
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup

ATTENDANCE = ("in_person", "virtual", "hybrid", "unknown")
COST = ("free", "paid", "unknown")
KINDS = ("event", "tour", "exhibition", "program", "closure")


@dataclass
class Venue:
    name: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    region: Optional[str] = None
    postal_code: Optional[str] = None
    country: Optional[str] = "US"
    lat: Optional[float] = None
    lon: Optional[float] = None


@dataclass
class Event:
    source: str                      # source id, e.g. "trpl"
    source_event_id: str             # the source's own id or URL slug
    title: str
    start: datetime                  # tz-aware, or a date for all-day
    end: Optional[datetime] = None
    all_day: bool = False
    timezone: str = "America/New_York"
    url: Optional[str] = None
    description: str = ""
    image: Optional[str] = None
    attendance: str = "unknown"
    online_url: Optional[str] = None
    cost: str = "unknown"
    cost_note: Optional[str] = None
    price_min: Optional[float] = None
    price_max: Optional[float] = None
    registration_required: Optional[bool] = None
    registration_url: Optional[str] = None
    venue: Venue = field(default_factory=Venue)
    organizer: Optional[str] = None
    kind: str = "event"
    categories: list = field(default_factory=list)
    audiences: list = field(default_factory=list)
    recurring: bool = False
    series_id: Optional[str] = None
    status: str = "scheduled"
    relevance: str = "core"          # core = TR organization; matched/possible = keyword match
    matched_terms: list = field(default_factory=list)
    accessibility: Optional[str] = None
    extra: dict = field(default_factory=dict)

    @property
    def id(self) -> str:
        key = f"{self.source}|{self.source_event_id}|{self.start.isoformat()}"
        return hashlib.sha1(key.encode()).hexdigest()[:16]

    def to_dict(self) -> dict:
        d = asdict(self)
        d["id"] = self.id
        tz = ZoneInfo(self.timezone)
        if self.all_day:
            d["start"] = self.start.date().isoformat() if isinstance(self.start, datetime) else self.start.isoformat()
            if self.end:
                d["end"] = self.end.date().isoformat() if isinstance(self.end, datetime) else self.end.isoformat()
        else:
            d["start"] = self.start.astimezone(tz).isoformat()
            d["end"] = self.end.astimezone(tz).isoformat() if self.end else None
        d["series_id"] = self.series_id or hashlib.sha1(f"{self.source}|{self.source_event_id}".encode()).hexdigest()[:12]
        d["summary"] = summarize(self.description)
        return d


# ---------- text helpers ----------

def clean_text(s: Optional[str]) -> str:
    """HTML or messy text -> tidy plain text with paragraph breaks."""
    if not s:
        return ""
    s = html.unescape(s)
    if "<" in s and ">" in s:
        soup = BeautifulSoup(s, "lxml")
        for br in soup.find_all("br"):
            br.replace_with("\n")
        for p in soup.find_all(["p", "div", "li", "h1", "h2", "h3", "h4"]):
            p.insert_after("\n\n")
        s = soup.get_text()
    s = s.replace("\xa0", " ")
    s = re.sub(r"[ \t]+", " ", s)
    s = re.sub(r"\s*\n\s*\n\s*", "\n\n", s)
    s = re.sub(r"(?<!\n)\n(?!\n)", " ", s)
    return s.strip()


def summarize(s: str, n: int = 220) -> str:
    s = re.sub(r"\s+", " ", s or "").strip()
    if len(s) <= n:
        return s
    cut = s[:n].rsplit(" ", 1)[0]
    return cut.rstrip(",;:—-") + "…"


# ---------- relevance ----------

STRONG_TERMS = [
    r"theodore roosevelt", r"teddy roosevelt", r"\bt\.\s?r\.(?=\W)", r"edith (kermit )?(carow )?roosevelt",
    r"alice (lee )?roosevelt", r"alice roosevelt longworth", r"kermit roosevelt", r"ethel roosevelt",
    r"quentin roosevelt", r"archibald roosevelt", r"theodore roosevelt jr", r"sagamore hill", r"rough riders?",
    r"bull moose", r"elkhorn ranch", r"maltese cross cabin", r"roosevelt island", r"\bteddy bear",
    r"strenuous life", r"square deal", r"man in the arena", r"roosevelt[–-]rondon", r"river of doubt",
    r"great white fleet", r"\btr\b(?= (center|site|association|library|birthplace|presidential))",
]
WEAK_TERMS = [r"\broosevelt\b", r"panama canal", r"progressive party", r"badlands"]
EXCLUDE_TERMS = [r"franklin (delano )?roosevelt", r"\bfdr\b", r"eleanor roosevelt", r"franklin d\. roosevelt",
                 r"roosevelt (hotel|university|field|high school)"]


def relevance(*texts: str) -> tuple[Optional[str], list]:
    """Return ("matched"|"possible"|None, matched_terms) for keyword-filtered sources."""
    t = " ".join(x or "" for x in texts).lower()
    strong = sorted({m.group(0).strip() for p in STRONG_TERMS for m in re.finditer(p, t)})
    if strong:
        return "matched", strong
    weak = sorted({m.group(0).strip() for p in WEAK_TERMS for m in re.finditer(p, t)})
    if not weak:
        return None, []
    if any(re.search(p, t) for p in EXCLUDE_TERMS):
        return None, []
    if weak == ["badlands"] or weak == ["progressive party"]:
        return None, []
    return "possible", weak


# ---------- attendance / cost ----------

VIRTUAL_RX = re.compile(r"\b(virtual(ly)?|online|zoom|webinar|livestream(ed)?|live ?stream(ed)?|facebook live|youtube live|streamed|streaming)\b", re.I)
INPERSON_RX = re.compile(r"\b(in[- ]person|on[- ]site|onsite|join us at|meet at|located at)\b", re.I)


NOT_VIRTUAL_RX = re.compile(
    r"\b(register|registration|tickets?|purchase|buy|book|reserve|available|sign up|rsvp|shop|store|order)\w*\s+(\w+\s+){0,2}online\b|\bonline (registration|tickets?|store|shop|catalog|exhibit(ion)?)\b",
    re.I,
)
STREAM_RX = re.compile(r"\b(livestream(ed)?|live ?stream(ed)?|streamed|simulcast|also (available )?(online|virtually)|watch online|hybrid|zoom link)\b", re.I)


def guess_attendance(text: str, has_physical_venue: bool) -> str:
    """Classify as in_person / virtual / hybrid from free text plus whether a real venue is listed."""
    text = NOT_VIRTUAL_RX.sub(" ", text or "")
    v = bool(VIRTUAL_RX.search(text))
    p_explicit = bool(INPERSON_RX.search(text))
    p = p_explicit or has_physical_venue
    if v and p:
        if p_explicit or STREAM_RX.search(text):
            return "hybrid"
        return "in_person"
    if v:
        return "virtual"
    if p:
        return "in_person"
    return "unknown"


PRICE_RX = re.compile(r"\$\s?(\d{1,3}(?:,\d{3})*(?:\.\d{2})?)")
FREE_RX = re.compile(r"\b(free(?! for members)( and open to the public| admission| of charge| event| program)?|no (charge|cost|fee)|admission is free|complimentary)\b", re.I)


def guess_cost(text: str) -> tuple[str, Optional[float], Optional[float], Optional[str]]:
    text = text or ""
    prices = [float(p.replace(",", "")) for p in PRICE_RX.findall(text)]
    nonzero = [p for p in prices if p > 0]
    if nonzero:
        return "paid", min(nonzero), max(nonzero), None
    if re.search(r"included with (general )?(museum )?admission", text, re.I):
        return "paid", None, None, "Included with admission"
    if FREE_RX.search(text) or (prices and not nonzero):
        return "free", 0.0 if prices else None, 0.0 if prices else None, None
    if re.search(r"\b(tickets?|registration fee|purchase|admission)\b", text, re.I):
        return "unknown", None, None, None
    return "unknown", None, None, None


# ---------- date helpers ----------

def at(d: date, t: Optional[time], tz: str) -> datetime:
    return datetime.combine(d, t or time(0, 0), tzinfo=ZoneInfo(tz))


def parse_clock(s: str) -> Optional[time]:
    """'9:00 am', '5:30pm', '12 Noon', '7 pm', '6:30 p.m.' -> time."""
    if not s:
        return None
    s = s.strip().lower().replace(".", "")
    if "noon" in s:
        return time(12, 0)
    if "midnight" in s:
        return time(0, 0)
    m = re.search(r"(\d{1,2})(?::(\d{2}))?\s*(am|pm)?", s)
    if not m:
        return None
    h, mi, ap = int(m.group(1)), int(m.group(2) or 0), m.group(3)
    if ap == "pm" and h < 12:
        h += 12
    if ap == "am" and h == 12:
        h = 0
    if h > 23 or mi > 59:
        return None
    return time(h, mi)


def nearest_year(month: int, day: int, today: Optional[date] = None) -> int:
    """For dates printed without a year: pick the year that puts the date nearest to today."""
    today = today or date.today()
    best = None
    for y in (today.year - 1, today.year, today.year + 1):
        try:
            d = date(y, month, day)
        except ValueError:
            continue
        if best is None or abs((d - today).days) < abs((best - today).days):
            best = d
    return best.year if best else today.year


def daterange(a: date, b: date):
    d = a
    while d <= b:
        yield d
        d += timedelta(days=1)
