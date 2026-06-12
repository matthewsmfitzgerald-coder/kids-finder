// Small display helpers shared by the list and map views.

// Format one age (in whole years) with a unit, e.g. "4 yrs" or "1 yr".
export function formatAge(years: number): string {
  return `${years} yr${years === 1 ? "" : "s"}`;
}

// Turn an age range into a short human label, e.g. "Ages 3–5 yrs".
export function ageLabel(min: number | null, max: number | null): string {
  if (min !== null && max !== null) return `Ages ${min}–${max} yrs`;
  if (min !== null) return `Ages ${formatAge(min)}+`;
  if (max !== null) return `Up to ${formatAge(max)}`;
  return "All ages";
}

// program_type is stored snake_case; show it as a friendly label.
const PROGRAM_TYPE_LABELS: Record<string, string> = {
  registered_program: "Registered Program",
  drop_in: "Drop-in",
  camp: "Camp",
  after_school: "After-School",
  clinic: "Clinic",
};
export function programTypeLabel(value: string): string {
  return PROGRAM_TYPE_LABELS[value] ?? value;
}

// gender is stored lowercase ("coed"/"female"/"male"); show it capitalized.
const GENDER_LABELS: Record<string, string> = {
  coed: "Coed",
  female: "Girls",
  male: "Boys",
};
export function genderLabel(value: string): string {
  return GENDER_LABELS[value] ?? value;
}

// --- Day-of-week matching ----------------------------------------------------
// Days arrive in two shapes: the City's abbreviations ("Mon,Tue,Wed") and the
// v2 schema's full names / ranges ("Saturday", "Mon–Fri"). The day filter works
// in abbreviations (Mon…Sun), so we normalize any token to those.

const DAY_ORDER = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

// Map a day name (full or abbreviated, any case) to its 3-letter abbreviation.
function toAbbrev(name: string): string | null {
  const key = name.trim().toLowerCase().slice(0, 3);
  const lookup: Record<string, string> = {
    mon: "Mon", tue: "Tue", wed: "Wed", thu: "Thu", fri: "Fri", sat: "Sat", sun: "Sun",
  };
  return lookup[key] ?? null;
}

// Does this program's `days` string include the selected day (e.g. "Sat")?
export function dayMatches(days: string, selected: string): boolean {
  if (!selected) return true; // no day filter applied
  if (!days) return false;

  for (const token of days.split(",").map((t) => t.trim()).filter(Boolean)) {
    // A range like "Mon–Fri" or "Monday-Friday" (en-dash or hyphen).
    const ends = token.split(/[–-]/).map((s) => s.trim());
    if (ends.length === 2) {
      const start = toAbbrev(ends[0]);
      const end = toAbbrev(ends[1]);
      if (start && end) {
        const i = DAY_ORDER.indexOf(start);
        const j = DAY_ORDER.indexOf(end);
        if (i !== -1 && j !== -1 && i <= j && DAY_ORDER.slice(i, j + 1).includes(selected)) {
          return true;
        }
        continue;
      }
    }
    // A single day ("Sat" or "Saturday").
    if (toAbbrev(token) === selected) return true;
  }
  return false;
}
