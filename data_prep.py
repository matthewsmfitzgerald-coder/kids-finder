"""
data_prep.py
------------
Pulls City of Toronto "Registered Programs" + "Locations" open data and writes
a single static file, public/programs.json, that the web app reads.

Run it with the project's virtual environment:

    ./.venv/bin/python data_prep.py

What it does, in order:
  1. Downloads all rows from the two CKAN "datastore" resources (paginated).
  2. Builds a lookup of Location ID -> location details.
  3. For each program: joins its location, converts ages from MONTHS to years,
     keeps only child-relevant programs, and reshapes it into the v2 schema
     (see SCHEMA.md) -- including the geography hierarchy and source tagging.
  4. Merges in hand-maintained private/non-city programs from
     data/private_programs.json (already in v2; passed through unchanged).
  5. Geocodes every location and writes the merged list to public/programs.json.

There is no web framework here and nothing secret -- it's just an HTTP client
plus some data cleaning.
"""

import json
import re
import sys
import time
from datetime import date
from pathlib import Path

import requests

# --- Configuration -----------------------------------------------------------

BASE_URL = "https://ckan0.cf.opendata.inter.prod-toronto.ca"
DATASTORE_SEARCH = f"{BASE_URL}/api/3/action/datastore_search"

# Resource IDs discovered from the package metadata (the "datastore_active" ones).
PROGRAMS_RESOURCE_ID = "3bdfdad5-b1d0-4b1b-b56d-c61c317da306"
LOCATIONS_RESOURCE_ID = "f23ac1ad-6f46-4b59-811f-eb34be9b1f7a"

PAGE_SIZE = 1000          # how many rows to request per API call
MONTHS_PER_YEAR = 12
CHILD_MAX_AGE_YEARS = 18  # keep programs whose minimum age is under this

# Where the app expects the data to live.
OUTPUT_PATH = Path(__file__).parent / "public" / "programs.json"

# Geocoding (turning addresses into map coordinates).
# We use Nominatim, OpenStreetMap's free geocoder -- no API key required, but its
# usage policy asks for a descriptive User-Agent and at most 1 request/second.
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
GEOCODE_USER_AGENT = "toronto-kids-finder/1.0 (educational project)"
GEOCODE_DELAY_SECONDS = 1.0
# Results are cached here so re-runs are instant and reproducible. This file is
# committed to the repo on purpose -- it's our coordinate lookup table.
GEOCODE_CACHE_PATH = Path(__file__).parent / "geocode_cache.json"

# Hand-maintained private / non-city programs to merge in.
PRIVATE_PATH = Path(__file__).parent / "data" / "private_programs.json"
CITY_SOURCE = "City of Toronto"

# The v2 schema (see SCHEMA.md). Every record carries these fields; the pipeline
# additionally attaches derived lat/lng for the map. We use this list to
# normalize private records so a missing key never crashes the app.
PROGRAM_FIELDS_V2 = [
    "id", "source", "source_type",
    "activity_title", "course_title", "category", "program_type",
    "age_min_years", "age_max_years",
    "days", "start_time", "end_time", "date_range", "registration_date", "status",
    "province", "municipality", "sub_area", "location_name", "address", "postal_code",
    "price", "activity_url", "last_updated",
]
# The only numeric fields; everything else is text. Drives the default we fill
# in for a missing key (null for numbers, "" for text -- the SCHEMA convention).
NUMBER_FIELDS = {"age_min_years", "age_max_years"}


# --- Small helpers -----------------------------------------------------------

def clean(value):
    """Turn the data's many ways of saying 'missing' into a real None.

    The open data uses the literal string 'None' (and sometimes blanks) for
    missing values, so we normalize all of those to Python's None and strip
    surrounding whitespace from everything else.
    """
    if value is None:
        return None
    text = str(value).strip()
    if text == "" or text.lower() == "none":
        return None
    return text


def text(value):
    """Cleaned text, or '' when missing.

    The v2 schema's convention is: unknown text -> "" (not null). clean() gives
    us None for missing values, so this wrapper turns that into "".
    """
    cleaned = clean(value)
    return cleaned if cleaned is not None else ""


def to_int(value):
    """Parse an int, or return None if it isn't a clean number."""
    text = clean(value)
    if text is None:
        return None
    try:
        return int(float(text))  # float() first tolerates values like '6.0'
    except ValueError:
        return None


def months_to_years(months):
    """Convert an age in months to years, rounded to 1 decimal (6 mo -> 0.5)."""
    if months is None:
        return None
    return round(months / MONTHS_PER_YEAR, 1)


def normalize_district(raw):
    """Collapse spelling variants into one canonical district name."""
    name = clean(raw)
    if name is None:
        return None
    # The dataset contains both "Toronto East York" and "Toronto and East York".
    aliases = {
        "Toronto East York": "Toronto and East York",
        "Toronto and East York": "Toronto and East York",
    }
    return aliases.get(name, name)


def format_time(hour, minute):
    """Build a readable 12-hour time like '9:45 AM' from hour/minute ints."""
    if hour is None or minute is None:
        return None
    suffix = "AM" if hour < 12 else "PM"
    display_hour = hour % 12
    if display_hour == 0:
        display_hour = 12  # midnight and noon both map to 12
    return f"{display_hour}:{minute:02d} {suffix}"


def build_address(loc):
    """Assemble a street address from the location's separate parts."""
    parts = [
        clean(loc.get("Street No")),
        clean(loc.get("Street No Suffix")),
        clean(loc.get("Street Name")),
        clean(loc.get("Street Type")),
        clean(loc.get("Street Direction")),
    ]
    return " ".join(p for p in parts if p) or None


# --- category (ACTIVITY) vs program_type (FORMAT) ----------------------------
# SCHEMA.md rule: a FORMAT value (Camp, Drop-in, After-School) must never land in
# `category`. Sources like the City put "Camps" in their category field, so at
# ingest we move the format to `program_type` and put the real ACTIVITY (or a
# catch-all) in `category`.

# Format words that may hide in a source's category/section field, mapped to the
# v2 program_type they really mean. First match wins.
FORMAT_WORD_TO_TYPE = [
    ("camp", "camp"),
    ("after-school", "after_school"),
    ("after school", "after_school"),
    ("drop-in", "drop_in"),
    ("drop in", "drop_in"),
]
DEFAULT_PROGRAM_TYPE = "registered_program"
CATCHALL_CATEGORY = "General"  # used when a format record states no real activity

# Recover a real ACTIVITY from a title. Grounded in the text only -- we never
# invent a sport that isn't written there. First match wins (order matters).
ACTIVITY_KEYWORDS = [
    ("Swimming", r"swim|aquatic"),
    ("Skating", r"skat"),
    ("Hockey", r"hockey"),
    ("Soccer", r"soccer"),
    ("Basketball", r"basketball"),
    ("Tennis", r"tennis"),
    ("Dance", r"dance|ballet"),
    ("Gymnastics", r"gymnastic"),
    ("Martial Arts", r"karate|judo|taekwondo|martial"),
    ("Arts", r"\bart\b|paint|drawing|craft|music|drama|pottery"),
]


def detect_program_type(*fields):
    """Pick a program_type by scanning category/section text for a format word."""
    haystack = " ".join((f or "") for f in fields).lower()
    for word, ptype in FORMAT_WORD_TO_TYPE:
        if word in haystack:
            return ptype
    return DEFAULT_PROGRAM_TYPE


def category_is_format(raw_category):
    """True if the source put a FORMAT word in its category field (e.g. 'Camps')."""
    low = (raw_category or "").lower()
    return any(word in low for word, _ in FORMAT_WORD_TO_TYPE)


def recover_activity(activity_title, course_title):
    """Find a real ACTIVITY in the titles, or None if none is stated."""
    for title in (activity_title, course_title):
        blob = (title or "").lower()
        for category, pattern in ACTIVITY_KEYWORDS:
            if re.search(pattern, blob):
                return category
    return None


def resolve_category(raw_category, activity_title, course_title):
    """Return an ACTIVITY for `category`, never a format word.

    If the source's category is a real activity (Swimming, Arts...), keep it.
    If it's a format word ("Camps"), recover the activity from the title, or
    fall back to the catch-all -- but never leave the format word in `category`.
    """
    base = clean(raw_category) or ""
    if not category_is_format(base):
        return base
    return recover_activity(activity_title, course_title) or CATCHALL_CATEGORY


# --- Geocoding ---------------------------------------------------------------

def load_geocode_cache():
    """Read the saved coordinate lookups, or start empty if there's no file yet."""
    if GEOCODE_CACHE_PATH.exists():
        return json.loads(GEOCODE_CACHE_PATH.read_text(encoding="utf-8"))
    return {}


def save_geocode_cache(cache):
    """Persist the cache after each lookup so a crash never loses progress."""
    GEOCODE_CACHE_PATH.write_text(
        json.dumps(cache, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def geocode_one(query):
    """Ask Nominatim for the coordinates of one address string.

    Returns {"lat": float, "lng": float} on success, or None if no match.
    """
    response = requests.get(
        NOMINATIM_URL,
        params={"q": query, "format": "json", "limit": 1, "countrycodes": "ca"},
        headers={"User-Agent": GEOCODE_USER_AGENT},
        timeout=30,
    )
    response.raise_for_status()
    results = response.json()
    if not results:
        return None
    return {"lat": float(results[0]["lat"]), "lng": float(results[0]["lon"])}


def attach_coordinates(programs):
    """Add lat/lng to each program by geocoding its (unique) location.

    Many programs share a location, so we geocode each distinct location once,
    cache the result, and copy the coordinates onto every program there.
    """
    # Build "location name -> best address query" for each distinct location.
    # The query is built from the record's own geography (municipality/province)
    # rather than a hard-coded "Toronto" -- the data is GTA-wide now.
    queries = {}
    for p in programs:
        name = p["location_name"]
        if not name or name in queries:
            continue
        address = p.get("address") or ""
        if not address:
            continue  # no street address -> can't geocode; leave it off the map
        bits = [address, p.get("municipality") or "", p.get("province") or ""]
        query = ", ".join(bit for bit in bits if bit)
        postal = p.get("postal_code") or ""
        if postal:
            query += f" {postal}"
        queries[name] = f"{query}, Canada"

    cache = load_geocode_cache()
    pending = [(name, q) for name, q in queries.items() if name not in cache]
    print(
        f"Geocoding {len(pending)} new locations "
        f"({len(queries) - len(pending)} already cached)..."
    )

    for i, (name, query) in enumerate(pending, start=1):
        try:
            cache[name] = geocode_one(query)
        except requests.RequestException as err:
            print(f"  [{i}/{len(pending)}] {name}: ERROR {err}")
            cache[name] = None
        else:
            print(f"  [{i}/{len(pending)}] {name} -> {cache[name]}")
        save_geocode_cache(cache)            # save progress incrementally
        time.sleep(GEOCODE_DELAY_SECONDS)    # be polite to the free service

    # Copy coordinates onto every program (None if the location couldn't be found).
    for p in programs:
        coords = cache.get(p["location_name"])
        p["lat"] = coords["lat"] if coords else None
        p["lng"] = coords["lng"] if coords else None


# --- Private (non-city) programs ---------------------------------------------

def load_private_programs():
    """Read the hand-maintained private programs file, tolerating problems.

    The file is already in the v2 schema, so we PASS VALUES THROUGH UNCHANGED.
    We only ensure every v2 field is present (filling a missing key with "" for
    text or None for a number) so a partial record can't crash the app. Missing
    file, empty file, or invalid JSON all return [] with a friendly message.
    """
    if not PRIVATE_PATH.exists():
        print(f"  No private file at {PRIVATE_PATH} -- skipping.")
        return []

    raw_text = PRIVATE_PATH.read_text(encoding="utf-8").strip()
    if not raw_text:
        print("  Private file is empty -- skipping.")
        return []

    try:
        records = json.loads(raw_text)
    except json.JSONDecodeError as err:
        print(f"  WARNING: private file is not valid JSON ({err}) -- skipping.")
        return []

    if not isinstance(records, list):
        print("  WARNING: private file should be a JSON array -- skipping.")
        return []

    normalized = []
    for raw in records:
        rec = {}
        for field in PROGRAM_FIELDS_V2:
            if field in raw:
                rec[field] = raw[field]  # provided -> pass through untouched
            else:
                rec[field] = None if field in NUMBER_FIELDS else ""
        normalized.append(rec)
    return normalized


# --- Data fetching -----------------------------------------------------------

def fetch_all(resource_id, label):
    """Download every record from a datastore resource, one page at a time.

    The CKAN datastore_search action returns a page of rows plus the grand
    total; we keep asking for the next page (via 'offset') until we have them
    all.
    """
    records = []
    offset = 0
    while True:
        response = requests.get(
            DATASTORE_SEARCH,
            params={"resource_id": resource_id, "limit": PAGE_SIZE, "offset": offset},
            timeout=60,
        )
        response.raise_for_status()
        result = response.json()["result"]
        page = result["records"]
        records.extend(page)
        total = result["total"]
        print(f"  {label}: fetched {len(records)} / {total}")
        offset += PAGE_SIZE
        if offset >= total or not page:
            break
    return records


# --- Main build --------------------------------------------------------------

def main():
    print("Downloading locations...")
    locations = fetch_all(LOCATIONS_RESOURCE_ID, "locations")
    # Index locations by their ID for fast joining.
    location_by_id = {loc["Location ID"]: loc for loc in locations}

    print("Downloading programs...")
    programs = fetch_all(PROGRAMS_RESOURCE_ID, "programs")

    print("Joining, filtering, and reshaping...")
    today = date.today().isoformat()  # last_updated stamp for the city rows
    output = []
    skipped_no_age = 0
    skipped_not_child = 0

    for p in programs:
        # Ages come in MONTHS. Convert to years for everything downstream.
        min_months = to_int(p.get("Min Age"))
        max_months = to_int(p.get("Max Age"))  # often missing -> None (no max)

        if min_months is None:
            skipped_no_age += 1          # can't judge child-relevance, drop it
            continue

        age_min_years = months_to_years(min_months)
        if age_min_years >= CHILD_MAX_AGE_YEARS:
            skipped_not_child += 1       # e.g. older-adult programs
            continue

        loc = location_by_id.get(p.get("Location ID"), {})

        # Separate the ACTIVITY (category) from the FORMAT (program_type). The
        # City leaks formats like "Camps" into its category field, so we detect
        # the format and recover the real activity (see SCHEMA.md rule).
        program_type = detect_program_type(p.get("Program Category"), p.get("Section"))
        category = resolve_category(
            p.get("Program Category"), p.get("Activity Title"), p.get("Course Title")
        )

        # Map the City's fields onto the v2 schema (see SCHEMA.md):
        #  - source_type=city, province=Ontario, municipality=Toronto
        #  - the City's "District" becomes sub_area
        #  - id = "toronto-" + the City's Course_ID
        #  - price is left "" (the City feed has none)
        output.append({
            "id": f"toronto-{p.get('Course_ID')}",
            "source": CITY_SOURCE,
            "source_type": "city",
            "activity_title": text(p.get("Activity Title")),
            "course_title": text(p.get("Course Title")),
            "category": category,
            "program_type": program_type,
            "age_min_years": age_min_years,
            "age_max_years": months_to_years(max_months),  # None == no upper limit
            "days": text(p.get("Days of The Week")),
            "start_time": format_time(to_int(p.get("Start Hour")), to_int(p.get("Start Min"))) or "",
            "end_time": format_time(to_int(p.get("End Hour")), to_int(p.get("End Min"))) or "",
            "date_range": text(p.get("From To")),
            "registration_date": text(p.get("Registration Date")),
            "status": text(p.get("Status / Information")),
            "province": "Ontario",
            "municipality": "Toronto",
            "sub_area": normalize_district(loc.get("District")) or "",
            "location_name": text(loc.get("Location Name")),
            "address": build_address(loc) or "",
            "postal_code": text(loc.get("Postal Code")),
            "price": "",
            "activity_url": text(p.get("Activity URL")),
            "last_updated": today,
        })

    # Merge in the hand-maintained private (non-city) programs.
    print("Reading private (non-city) programs...")
    private = load_private_programs()
    print(f"  Loaded {len(private)} private programs.")

    # Private records bring their own id; only fill a blank one so the app's
    # React keys stay unique. We don't otherwise touch private values.
    for i, rec in enumerate(private, start=1):
        if not rec.get("id"):
            rec["id"] = f"private-{i}"

    combined = output + private

    # Geocode all locations (city + private) so private programs map too.
    print("Adding map coordinates...")
    attach_coordinates(combined)

    # Ensure public/ exists, then write the merged file (compact but valid JSON).
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_PATH.open("w", encoding="utf-8") as f:
        json.dump(combined, f, ensure_ascii=False)

    with_coords = sum(1 for p in combined if p["lat"] is not None)
    print()
    print(f"Kept {len(output)} city + {len(private)} private = {len(combined)} programs.")
    print(f"  Skipped {skipped_no_age} with no readable Min Age.")
    print(f"  Skipped {skipped_not_child} whose min age was {CHILD_MAX_AGE_YEARS}+.")
    print(f"  {with_coords} of {len(combined)} programs have map coordinates.")
    size_kb = OUTPUT_PATH.stat().st_size / 1024
    print(f"Wrote {OUTPUT_PATH} ({size_kb:.0f} KB)")


if __name__ == "__main__":
    try:
        main()
    except requests.RequestException as err:
        print(f"Network error talking to the Toronto API: {err}", file=sys.stderr)
        sys.exit(1)
