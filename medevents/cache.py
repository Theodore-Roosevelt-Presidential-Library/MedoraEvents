"""Small JSON caches kept in the repo so detail pages aren't re-fetched every run."""
from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent / "data" / "cache"
TTL_DAYS = 10
KEEP_DAYS = 180


def load(name: str) -> dict:
    p = ROOT / f"{name}.json"
    if p.exists():
        try:
            return json.loads(p.read_text())
        except json.JSONDecodeError:
            return {}
    return {}


def save(name: str, data: dict) -> None:
    cutoff = (date.today() - timedelta(days=KEEP_DAYS)).isoformat()
    data = {k: v for k, v in data.items() if v.get("_fetched", "9999") >= cutoff}
    ROOT.mkdir(parents=True, exist_ok=True)
    (ROOT / f"{name}.json").write_text(json.dumps(data, indent=1, sort_keys=True, ensure_ascii=False))


def stamp(rec: dict) -> dict:
    rec["_fetched"] = date.today().isoformat()
    return rec


def stale(rec: dict) -> bool:
    return rec.get("_fetched", "0000") < (date.today() - timedelta(days=TTL_DAYS)).isoformat()
