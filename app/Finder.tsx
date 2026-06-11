// The "use client" directive marks this as a Client Component: it runs in the
// browser, so it can use state (useState), effects (useEffect), and respond to
// typing/clicks. The rest of our app stays as server-rendered HTML.
"use client";

import { useEffect, useMemo, useState } from "react";
import dynamic from "next/dynamic";
import type { Program } from "./types";
import { ageLabel, programTypeLabel, dayMatches } from "./format";

// Day options in calendar order. Our data stores days as "Mon,Wed,Fri", so we
// match by checking whether the chosen day is one of those tokens.
const DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

// We never render more than this many cards at once. Filtering still considers
// ALL programs (so the count is accurate), but the DOM stays small and snappy.
const RENDER_CAP = 150;

// Reorder the merged list so the default view doesn't lead with all City rows
// then all private rows (which buries private listings and violates neutral
// ranking). We round-robin across sources: one record from each source in turn,
// repeating until all are drained. It's deterministic (buckets keep their
// stable input order), so the list never reshuffles between loads. See SCHEMA.md
// "Known inconsistencies / future work" for the multi-operator caveat.
function interleaveBySource(programs: Program[]): Program[] {
  const buckets = new Map<string, Program[]>();
  for (const p of programs) {
    const key = p.source || "";
    if (!buckets.has(key)) buckets.set(key, []);
    buckets.get(key)!.push(p);
  }
  const lists = [...buckets.values()];
  const result: Program[] = [];
  for (let round = 0, added = true; added; round++) {
    added = false;
    for (const list of lists) {
      if (round < list.length) {
        result.push(list[round]);
        added = true;
      }
    }
  }
  return result;
}

// The map is loaded only in the browser (Leaflet needs the DOM/window), so we
// import it dynamically with server-side rendering turned off.
const ProgramMap = dynamic(() => import("./ProgramMap"), {
  ssr: false,
  loading: () => <p className="text-gray-600">Loading map…</p>,
});

export default function Finder() {
  // --- Loaded data ----------------------------------------------------------
  const [programs, setPrograms] = useState<Program[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // --- Filter inputs (what the parent types/selects) ------------------------
  const [query, setQuery] = useState("");
  const [municipality, setMunicipality] = useState(""); // primary geographic filter
  const [category, setCategory] = useState("");
  const [programType, setProgramType] = useState("");
  const [age, setAge] = useState(""); // kept as text so the box can be empty
  const [day, setDay] = useState("");
  const [source, setSource] = useState("");

  // Which view is showing: the card list or the map. Both use the same filters.
  const [view, setView] = useState<"list" | "map">("list");

  // Load the static JSON once, when the component first appears in the browser.
  useEffect(() => {
    fetch("/programs.json")
      .then((res) => {
        if (!res.ok) throw new Error(`Failed to load data (${res.status})`);
        return res.json();
      })
      .then((data: Program[]) => setPrograms(data))
      .catch((err: Error) => setError(err.message))
      .finally(() => setLoading(false));
  }, []);

  // Build the dropdown option lists from the data itself, sorted alphabetically.
  // useMemo caches the result so we don't redo this work on every keystroke.
  const municipalities = useMemo(
    () => [...new Set(programs.map((p) => p.municipality).filter(Boolean))].sort(),
    [programs]
  );
  const categories = useMemo(
    () => [...new Set(programs.map((p) => p.category).filter(Boolean))].sort(),
    [programs]
  );
  const programTypes = useMemo(
    () => [...new Set(programs.map((p) => p.program_type).filter(Boolean))].sort(),
    [programs]
  );
  // Sorted alphabetically so no provider is presented above another.
  const sources = useMemo(
    () => [...new Set(programs.map((p) => p.source).filter(Boolean))].sort(),
    [programs]
  );

  // Source-neutral default order: round-robin across sources so the unfiltered
  // list interleaves City and private instead of leading with all City rows.
  // Computed once per data load; filtering preserves this order.
  const orderedPrograms = useMemo(() => interleaveBySource(programs), [programs]);

  // The actual filtering. useMemo means this only recomputes when the data or
  // one of the filter inputs changes -- not on every re-render.
  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    const ageText = age.trim();
    const ageNum = ageText === "" ? null : Number(ageText);

    return orderedPrograms.filter((p) => {
      // Search box: match against activity + course title.
      if (q) {
        const haystack = `${p.activity_title ?? ""} ${p.course_title ?? ""}`.toLowerCase();
        if (!haystack.includes(q)) return false;
      }
      // Dropdown filters ("" means "All").
      if (municipality && p.municipality !== municipality) return false;
      if (category && p.category !== category) return false;
      if (programType && p.program_type !== programType) return false;
      if (source && p.source !== source) return false;
      // Day of week: tolerant of "Mon,Tue", "Saturday", and "Mon–Fri" formats.
      if (day && !dayMatches(p.days, day)) return false;
      // Child's age: keep programs whose age range includes the entered age.
      if (ageNum !== null && !Number.isNaN(ageNum)) {
        if (p.age_min_years !== null && ageNum < p.age_min_years) return false;
        if (p.age_max_years !== null && ageNum > p.age_max_years) return false;
      }
      return true;
    });
  }, [orderedPrograms, query, municipality, category, programType, age, day, source]);

  const shown = filtered.slice(0, RENDER_CAP);

  // How many distinct locations the map can plot for the current filters.
  const locationCount = useMemo(
    () =>
      new Set(
        filtered.filter((p) => p.lat !== null && p.lng !== null).map((p) => p.location_name)
      ).size,
    [filtered]
  );

  // Any filter set? Drives whether we show the "Clear filters" button.
  const hasActiveFilters = Boolean(
    query || municipality || category || programType || age || day || source
  );

  // Reset every filter back to its empty state.
  function clearFilters() {
    setQuery("");
    setMunicipality("");
    setCategory("");
    setProgramType("");
    setAge("");
    setDay("");
    setSource("");
  }

  // Shared Tailwind classes for the form controls, to avoid repetition.
  const control =
    "w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-base " +
    "focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-200";

  return (
    <main className="mx-auto w-full max-w-3xl px-4 py-6">
      <header className="mb-5">
        <h1 className="text-2xl font-bold text-gray-900">
          GTA Kids&apos; Activity Finder
        </h1>
        <p className="mt-1 text-sm text-gray-600">
          Search children&apos;s programs, camps, and activities across the GTA, from
          the City of Toronto and other providers.
        </p>
      </header>

      {/* Filter controls. They stack on phones and form a grid on wider screens. */}
      <section className="mb-5 grid grid-cols-1 gap-3 sm:grid-cols-2">
        <input
          type="search"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search by activity (e.g. swimming)"
          className={`${control} sm:col-span-2`}
        />
        <select value={municipality} onChange={(e) => setMunicipality(e.target.value)} className={control}>
          <option value="">All municipalities</option>
          {municipalities.map((m) => (
            <option key={m} value={m}>
              {m}
            </option>
          ))}
        </select>
        <select value={category} onChange={(e) => setCategory(e.target.value)} className={control}>
          <option value="">All categories</option>
          {categories.map((c) => (
            <option key={c} value={c}>
              {c}
            </option>
          ))}
        </select>
        <select value={programType} onChange={(e) => setProgramType(e.target.value)} className={control}>
          <option value="">All program types</option>
          {programTypes.map((t) => (
            <option key={t} value={t}>
              {programTypeLabel(t)}
            </option>
          ))}
        </select>
        <input
          type="number"
          min={0}
          value={age}
          onChange={(e) => setAge(e.target.value)}
          placeholder="Child's age (years)"
          className={control}
        />
        <select value={day} onChange={(e) => setDay(e.target.value)} className={control}>
          <option value="">Any day</option>
          {DAYS.map((d) => (
            <option key={d} value={d}>
              {d}
            </option>
          ))}
        </select>
        <select value={source} onChange={(e) => setSource(e.target.value)} className={control}>
          <option value="">All sources</option>
          {sources.map((s) => (
            <option key={s} value={s!}>
              {s}
            </option>
          ))}
        </select>
      </section>

      {/* View toggle + status line: loading, error, or the count. */}
      {loading && <p className="text-gray-600">Loading programs…</p>}
      {error && <p className="text-red-600">Couldn’t load programs: {error}</p>}
      {!loading && !error && (
        <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
          <p className="text-sm text-gray-600">
            {view === "list" ? (
              <>
                Showing {shown.length} of {filtered.length} matching programs
                {filtered.length > RENDER_CAP && " (refine to see more)"}.
              </>
            ) : (
              <>
                {filtered.length} matching programs at {locationCount} locations.
              </>
            )}
          </p>
          <div className="flex items-center gap-2">
            {hasActiveFilters && (
              <button
                onClick={clearFilters}
                className="shrink-0 rounded-lg border border-gray-300 bg-white px-3 py-1.5 text-sm font-medium text-gray-700 hover:bg-gray-50"
              >
                Clear filters
              </button>
            )}
            {/* Segmented List / Map control */}
            <div className="inline-flex overflow-hidden rounded-lg border border-gray-300 text-sm">
              {(["list", "map"] as const).map((v) => (
                <button
                  key={v}
                  onClick={() => setView(v)}
                  className={
                    "px-3 py-1.5 font-medium capitalize " +
                    (view === v
                      ? "bg-blue-600 text-white"
                      : "bg-white text-gray-700 hover:bg-gray-50")
                  }
                >
                  {v}
                </button>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* Map view */}
      {!loading && !error && view === "map" && <ProgramMap programs={filtered} />}

      {/* List view */}
      {view === "list" && (
      <ul className="space-y-3">
        {shown.map((p) => (
          <li
            key={p.id}
            className="overflow-hidden rounded-xl border border-gray-200 bg-white p-4 shadow-sm"
          >
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <h2 className="font-semibold text-gray-900 break-words">
                  {p.activity_title ?? p.course_title}
                </h2>
                <div className="mt-1 flex flex-wrap gap-1.5">
                  {p.category && (
                    <span className="inline-block rounded-full bg-blue-50 px-2 py-0.5 text-xs font-medium text-blue-700">
                      {p.category}
                    </span>
                  )}
                  {p.program_type && (
                    <span className="inline-block rounded-full bg-indigo-50 px-2 py-0.5 text-xs font-medium text-indigo-700">
                      {programTypeLabel(p.program_type)}
                    </span>
                  )}
                  <span className="inline-block rounded-full bg-gray-100 px-2 py-0.5 text-xs font-medium text-gray-600">
                    {p.source}
                  </span>
                </div>
              </div>
              <span className="whitespace-nowrap text-sm text-gray-500">
                {ageLabel(p.age_min_years, p.age_max_years)}
              </span>
            </div>

            <dl className="mt-3 space-y-1 text-sm text-gray-700">
              <div>
                <span className="text-gray-500">Where: </span>
                {p.location_name}
                {p.municipality && ` · ${p.municipality}`}
                {p.sub_area && ` (${p.sub_area})`}
              </div>
              <div>
                <span className="text-gray-500">When: </span>
                {p.days}
                {p.start_time && ` · ${p.start_time}–${p.end_time}`}
              </div>
              {p.date_range && (
                <div>
                  <span className="text-gray-500">Dates: </span>
                  {p.date_range}
                </div>
              )}
              {p.price && (
                <div>
                  <span className="text-gray-500">Price: </span>
                  {p.price}
                </div>
              )}
              {p.status && <div className="text-gray-500">{p.status}</div>}
            </dl>

            {p.activity_url && (
              <a
                href={p.activity_url}
                target="_blank"
                rel="noopener noreferrer"
                className="mt-3 inline-block rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700"
              >
                View &amp; register →
              </a>
            )}
          </li>
        ))}
      </ul>
      )}

      {!loading && !error && filtered.length === 0 && (
        <p className="text-gray-600">No programs match your filters. Try widening them.</p>
      )}
    </main>
  );
}
