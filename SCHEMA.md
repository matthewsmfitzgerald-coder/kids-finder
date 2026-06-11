# kids-finder — data schema (v2)

**One record = one specific, registerable offering, at one location, on one day/time pattern, over one date range.** Both City of Toronto and private/camp sources map onto these same fields.

**Conventions**
- Unknown text → `""`. Unknown number → `null`. **Never guess or invent a value.**
- Ages in **years** (the City source stores months — convert).
- `registration_date` and `last_updated` use `YYYY-MM-DD`. Other dates may stay in the source's human form.
- If one program runs at several locations or several day/time slots, that's **several records**, one per combination.

---

## Fields

### Identity & source
| field | meaning | example |
|---|---|---|
| `id` | Stable unique key. Convention: `source-slug` + provider's own numeric id (from the registration URL if present). Lets you refresh without creating duplicates. | `canlan-78441` |
| `source` | Provider/operator name. | `City of Toronto` |
| `source_type` | One of `city`, `private`, `self_serve`. Drives neutral ranking and, later, tagging of self-enrolled providers. | `private` |

### What it is
| field | meaning | example |
|---|---|---|
| `activity_title` | The specific offering name a parent sees. | `Learn to Skate - Level 1` |
| `course_title` | Broader course/program name (may equal `activity_title`). | `Learn to Skate` |
| `category` | The **activity** — what the child does. Broad, reusable: Hockey, Skating, Swimming, Soccer, Dance, Arts, Martial Arts, STEM, Multi-sport… | `Skating` |
| `program_type` | The **format**. One of `registered_program`, `drop_in`, `camp`, `after_school` (extensible later: `league`, `membership`). Kept separate from `category` so a hockey camp shows under both **Hockey** and **Camp**. | `camp` |

**Rule:** `category` holds the ACTIVITY only and `program_type` holds the FORMAT only. A format value (e.g. Camp, Drop-in) must never appear in `category`. When a source puts a format into its activity/category field, map the format to `program_type` and set `category` to the real activity, or to a catch-all (Multi-sport / General) when no activity is stated — never the format word.

### Who it's for
| field | meaning | example |
|---|---|---|
| `age_min_years` | Minimum age in years; `null` if unstated. | `3` |
| `age_max_years` | Maximum age in years; `null` if unstated. | `6` |

### When
| field | meaning | example |
|---|---|---|
| `days` | Day(s). Weekly class → `Wednesday`. Camp → `Mon–Fri`. | `Wednesday` |
| `start_time` | Clock time. | `4:30 PM` |
| `end_time` | Clock time. | `5:20 PM` |
| `date_range` | Start–end of the offering. Weekly → the term. Camp → the week. | `Mar 16, 2026–Mar 20, 2026` |
| `registration_date` | When **registration opens** (the moat datum). Blank if unknown/prose-only. | `2026-08-15` |
| `status` | Availability **as of capture**: `Open`, `Waitlist`, `Full`, `Closed`, `Started`, or `""`. **Volatile — treat as a snapshot, not live truth.** | `Open` |

### Where (the new hierarchy — top to bottom)
| field | meaning | example |
|---|---|---|
| `province` | Region. | `Ontario` |
| `municipality` | The city a parent thinks in. **Primary geographic filter.** | `Toronto` |
| `sub_area` | Finer area *within* a municipality. For Toronto = the City's "District". Blank for sources that don't carve themselves up. | `Etobicoke York` |
| `location_name` | Venue/facility. | `Cwench Centre - Etobicoke` |
| `address` | Street address (needed for the map pin). | `123 Example Rd` |
| `postal_code` | Optional; helps geocoding and "near me". | `M9C 1A1` |

### Cost & link
| field | meaning | example |
|---|---|---|
| `price` | Free text, to allow bands and per-week pricing. | `$225/week` |
| `activity_url` | Link **out** to the provider's own registration/info page. | `https://…` |

### Housekeeping
| field | meaning | example |
|---|---|---|
| `last_updated` | Date this row was captured/verified, so you know what's gone stale. | `2026-06-08` |

---

## How existing data maps onto v2

**City of Toronto rows:** `source = "City of Toronto"`, `source_type = "city"`, `province = "Ontario"`, `municipality = "Toronto"`, `sub_area =` the City's existing District value, `program_type =` `registered_program` (from the Registered Programs resource) or `drop_in` (from the Drop-in resource).

**Existing Canlan rows:** `source_type = "private"`, `province = "Ontario"`, `municipality =` the real city (Toronto / Oakville / Oshawa — fixing the rows where a city name was sitting in the old `district` field), `sub_area = ""` (Canlan doesn't use Toronto's districts), plus the rink street address and a `price` where shown.

> Add the **fields** everywhere now; only **populate** them for the pilot scope (city + your handful of private rows). Don't chase data for every source yet.

---

## Reformatter prompt (v2)

Paste this into a fresh chat, then paste a provider's raw listings text after it.

```
You convert kids' activity, camp, and program listings into structured JSON for
a Toronto/GTA activity finder. I'll paste the raw text of a provider's listings
page. Output ONLY a JSON array — no commentary before or after — with one object
per distinct offering (a unique combination of program + location + day/time +
date range), in EXACTLY this schema:

{
  "id": "", "source": "", "source_type": "private",
  "activity_title": "", "course_title": "", "category": "", "program_type": "",
  "age_min_years": null, "age_max_years": null,
  "days": "", "start_time": "", "end_time": "", "date_range": "",
  "registration_date": "", "status": "",
  "province": "Ontario", "municipality": "", "sub_area": "",
  "location_name": "", "address": "", "postal_code": "",
  "price": "", "activity_url": "", "last_updated": ""
}

RULES:
- Use ONLY information present in the text. Unknown text → "", unknown number →
  null. NEVER invent, guess, or "fill in what's probably true."
- Ages in YEARS. If the source gives months, convert. If it gives hockey
  divisions (U7, U9…), put the division in course_title and leave ages null
  unless an explicit age is also stated.
- program_type: choose registered_program, drop_in, camp, or after_school based
  on the text. A week-long full-day offering is a camp; a recurring weekly class
  is a registered_program.
- category is the ACTIVITY (Hockey, Skating, Dance…), NOT the format.
- municipality = the CITY the venue is in (Toronto, Mississauga, Oakville,
  Oshawa…), not the neighbourhood. sub_area only if the source states a
  Toronto-style district; otherwise "".
- One object per location AND per day/time AND per date range. Do not collapse.
- activity_url = the provider's own registration/info page.
- id = a short source slug + the provider's own numeric id from the URL if
  present (e.g. "canlan-78441"); otherwise "".
- status only if the text states it (Open / Waitlist / Full / Closed / Started).
- last_updated = today's date in YYYY-MM-DD.

After the JSON array, list: (a) every field you left blank, and (b) anything
ambiguous you had to make a judgment call on — so I can verify it by hand.
```

---

## Known inconsistencies / future work

- City non-camp categories are coarser (e.g. `Sports`) than the finer activity values the camp mapping introduces (e.g. `Soccer`); unify in a later normalization pass if user feedback warrants.
- The finder's default (unfiltered) order round-robins per operator (N-way), which surfaces tiny sources high. Once there are many operators of very different sizes, the default ordering may need to balance per-operator fairness against over-surfacing tiny sources — revisit when real operator data exists.
