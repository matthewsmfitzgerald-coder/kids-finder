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
     keeps only child-relevant programs, and reshapes it into a tidy object.
  4. Writes the resulting list to public/programs.json.

There is no web framework here and nothing secret -- it's just an HTTP client
plus some data cleaning.
"""

import json
import sys
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

        output.append({
            "course_id": p.get("Course_ID"),
            "activity_title": clean(p.get("Activity Title")),
            "course_title": clean(p.get("Course Title")),
            "category": clean(p.get("Program Category")),
            "section": clean(p.get("Section")),
            "district": normalize_district(loc.get("District")),
            "location_name": clean(loc.get("Location Name")),
            "address": build_address(loc),
            "postal_code": clean(loc.get("Postal Code")),
            "age_min_years": age_min_years,
            "age_max_years": months_to_years(max_months),  # None == no upper limit
            "days": clean(p.get("Days of The Week")),
            "start_time": format_time(to_int(p.get("Start Hour")), to_int(p.get("Start Min"))),
            "end_time": format_time(to_int(p.get("End Hour")), to_int(p.get("End Min"))),
            "date_range": clean(p.get("From To")),
            "registration_date": clean(p.get("Registration Date")),
            "activity_url": clean(p.get("Activity URL")),
            "status": clean(p.get("Status / Information")),
        })

    # Ensure public/ exists, then write the file (compact but valid JSON).
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_PATH.open("w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False)

    print()
    print(f"Kept {len(output)} child-relevant programs.")
    print(f"  Skipped {skipped_no_age} with no readable Min Age.")
    print(f"  Skipped {skipped_not_child} whose min age was {CHILD_MAX_AGE_YEARS}+.")
    size_kb = OUTPUT_PATH.stat().st_size / 1024
    print(f"Wrote {OUTPUT_PATH} ({size_kb:.0f} KB)")


if __name__ == "__main__":
    try:
        main()
    except requests.RequestException as err:
        print(f"Network error talking to the Toronto API: {err}", file=sys.stderr)
        sys.exit(1)
