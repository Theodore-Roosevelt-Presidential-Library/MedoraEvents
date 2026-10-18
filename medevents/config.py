"""Run-wide settings, overridable with environment variables."""
import os
from datetime import date, timedelta

HORIZON_DAYS = int(os.environ.get("MEDEVENTS_HORIZON_DAYS", "400"))      # how far ahead one-off events are kept
RECURRING_DAYS = int(os.environ.get("MEDEVENTS_RECURRING_DAYS", "120"))  # how far ahead repeating tours are expanded
STALE_DAYS = int(os.environ.get("MEDEVENTS_STALE_DAYS", "7"))            # keep a failed source's last good data this long
SITE_URL = os.environ.get("MEDEVENTS_SITE_URL", "https://medoraevents.labs.trlibrary.com")
NPS_API_KEY = os.environ.get("NPS_API_KEY") or "DEMO_KEY"


def horizon(recurring: bool = False) -> date:
    return date.today() + timedelta(days=RECURRING_DAYS if recurring else HORIZON_DAYS)
