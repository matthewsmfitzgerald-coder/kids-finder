# Project: kids-finder

## What this is
A web app that helps parents in Toronto / the GTA discover children's
recreation programs, camps, and activities across multiple sources (the City of
Toronto open data, large private operators, camp providers, and eventually
self-enrolled small businesses), and find out when registration opens. The
long-term product is "discover → register → manage → resell" for the sports
parent; we are building the discovery slice first.

## The data model is the source of truth
- The canonical schema lives in `SCHEMA.md`. Read it before touching any data
  code. Every record from every source must be normalized to that schema.
- Two dimensions are deliberately separate: `category` (the ACTIVITY, e.g.
  Hockey) and `program_type` (the FORMAT, e.g. camp). Never collapse them.
- Geography is a hierarchy: province → municipality → sub_area → location.
  `municipality` is the primary geographic filter. Do NOT treat Toronto's
  internal "District" as the top level — it is `sub_area` and is often blank.
- The app is designed to be multi-source and multi-municipality from the start.
  Never hard-code assumptions that only Toronto exists, or that the only source
  is the City. New sources are merged, each tagged with `source` and
  `source_type`.

## Architecture discipline (important)
- This is a learning project; the builder is not an experienced engineer.
  Explain choices, keep code readable, and work one step at a time, confirming
  each step before moving on.
- Secure by omission, for now: NO user accounts, login, payments, or storage of
  any data about users. The app is read-only over a static JSON file. If a task
  seems to require any of those, STOP and flag it rather than building it — these
  are deliberate, later, security-sensitive decisions.
- Keep discovery neutral: never rank private/paid sources above City programs.
  `source_type` exists partly to enforce this.

## Data freshness
- Some data (hand-maintained private listings, `status`) is a snapshot and goes
  stale. Don't present snapshot data as if it were live. The City open data
  refreshes weekly.
