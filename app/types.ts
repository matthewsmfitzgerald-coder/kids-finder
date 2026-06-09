// Describes the shape of one program record in public/programs.json.
//
// `string | null` means the field is either text or missing (our data script
// writes null for missing values). `number | null` is the same idea for ages.
// This type doesn't create any runtime code -- it only helps the editor and
// catches mistakes while we write the app.

export type Program = {
  course_id: number | null;
  activity_title: string | null;
  course_title: string | null;
  category: string | null;
  section: string | null;
  district: string | null;
  location_name: string | null;
  address: string | null;
  postal_code: string | null;
  age_min_years: number | null; // in YEARS (already converted from months)
  age_max_years: number | null; // null means "no upper age limit"
  days: string | null; // e.g. "Mon,Wed,Fri"
  start_time: string | null; // e.g. "9:45 AM"
  end_time: string | null;
  date_range: string | null; // e.g. "Apr-13-2026 to Jun-15-2026"
  registration_date: string | null;
  activity_url: string | null; // ActiveCommunities registration link
  status: string | null;
  lat: number | null; // map latitude (null if the address couldn't be geocoded)
  lng: number | null; // map longitude
};
