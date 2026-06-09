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
