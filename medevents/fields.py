"""The metadata dictionary for every event record (published as /api/v1/fields.json)."""

FIELDS = [
    ("id", "string", "Stable ID for this occurrence (source + source event + start time)."),
    ("series_id", "string", "Shared by every occurrence of the same program or tour."),
    ("source", "string", "Source ID (see /api/v1/sources.json)."),
    ("source_name", "string", "Display name of the organization that lists the event."),
    ("source_event_id", "string", "The source's own ID or URL slug."),
    ("also_listed", "array", "Other calendars that list the same event: [{source, url, title}]. Each event appears once."),
    ("title", "string", "Event title as published."),
    ("description", "string", "Plain-text description."),
    ("summary", "string", "First ~220 characters of the description."),
    ("url", "string", "Event page on the source site."),
    ("image", "string|null", "Image URL from the source."),
    ("start", "string", "ISO 8601 start, in the event's local time zone (date only when all_day)."),
    ("end", "string|null", "ISO 8601 end, same rules as start."),
    ("all_day", "boolean", "True when no start time is published."),
    ("timezone", "string", "IANA time zone of the venue, e.g. America/Denver."),
    ("attendance", "enum", "How people attend.", ["in_person", "virtual", "hybrid", "unknown"]),
    ("online_url", "string|null", "Livestream or online link, when published."),
    ("cost", "enum", "Whether attending costs money.", ["free", "paid", "unknown"]),
    ("cost_note", "string|null", "Wording such as 'Included with admission' or 'Timed-entry pass required'."),
    ("price_min", "number|null", "Lowest listed price in USD."),
    ("price_max", "number|null", "Highest listed price in USD."),
    ("registration_required", "boolean|null", "True when the source says registration or tickets are required."),
    ("registration_url", "string|null", "Where to register or buy tickets."),
    ("venue", "object", "{name, address, city, region, postal_code, country, lat, lon}."),
    ("organizer", "string|null", "Organizing body (park unit, museum department, etc.)."),
    ("kind", "enum", "Type of listing.", ["event", "tour", "exhibition", "program", "closure"]),
    ("categories", "array", "Source categories or program types."),
    ("audiences", "array", "Audience labels from the source (e.g. All Ages)."),
    ("recurring", "boolean", "True for repeating tours and programs (one record per occurrence)."),
    ("status", "enum", "Listing status.", ["scheduled", "cancelled", "postponed", "sold_out"]),
    ("accessibility", "string|null", "Accessibility note from the source."),
    ("region_label", "string", "Short place label for display, e.g. 'Dickinson, ND'."),
    ("area", "enum", "In town, a drive out of Medora, or online.", ["medora", "nearby", "online"]),
    ("area_label", "string", "'In Medora', 'Out of Medora' or 'Online'."),
    ("drive_minutes", "number|null", "Approximate one-way drive time from Medora in minutes (estimate; 0 in town)."),
    ("drive_label", "string|null", "Display text, e.g. 'About 35 min from Medora'."),
    ("lat", "number|null", "Map latitude (WGS84). Null for online events or places that couldn't be located."),
    ("lon", "number|null", "Map longitude (WGS84)."),
    ("geo_precision", "string|null", "'venue' when the pin is the venue itself; 'town' when it is the town center (approximate)."),
    ("first_seen", "string", "Date this calendar first picked up the event."),
    ("last_seen", "string", "Date of the most recent run that still found it."),
    ("extra", "object", "Source-specific fields (park code, room, capacity, presenter, ...)."),
]


def as_json():
    out = []
    for f in FIELDS:
        d = {"name": f[0], "type": f[1], "description": f[2]}
        if len(f) > 3:
            d["values"] = f[3]
        out.append(d)
    return out
