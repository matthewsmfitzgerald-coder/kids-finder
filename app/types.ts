// Describes the shape of one program record in public/programs.json (v2 schema;
// see SCHEMA.md). Text fields are always present as strings ("" when unknown);
// the two age fields are numbers or null. lat/lng are derived by data_prep for
// the map and are null when a location couldn't be geocoded.

export type Program = {
  // Identity & source
  id: string; // stable unique key (e.g. "toronto-129516", "demo-oakville-1")
  source: string; // provider/operator name, e.g. "City of Toronto"
  source_type: string; // "city" | "private" | "self_serve"

  // What it is
  activity_title: string;
  course_title: string;
  category: string; // the ACTIVITY (Swimming, Skating, Hockey…)
  program_type: string; // the FORMAT (registered_program | drop_in | camp | after_school)

  // Who it's for
  age_min_years: number | null;
  age_max_years: number | null;

  // When
  days: string; // "Mon,Wed,Fri" (city) or "Saturday" / "Mon–Fri" (v2)
  start_time: string;
  end_time: string;
  date_range: string;
  registration_date: string;
  status: string;

  // Where (province → municipality → sub_area → location)
  province: string;
  municipality: string; // primary geographic filter
  sub_area: string; // finer area within a municipality; "" if none
  location_name: string;
  address: string;
  postal_code: string;

  // Cost & link
  price: string; // free text, "" if unknown
  activity_url: string;

  // Housekeeping
  last_updated: string; // YYYY-MM-DD

  // Derived (added by data_prep for the map)
  lat: number | null;
  lng: number | null;
};
