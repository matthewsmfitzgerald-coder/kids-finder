"use client";

// Leaflet's own stylesheet (controls, popups, tiles) must be imported once.
import "leaflet/dist/leaflet.css";
import { useEffect, useMemo } from "react";
import { MapContainer, TileLayer, Marker, Popup, useMap } from "react-leaflet";
import L from "leaflet";
import type { Program } from "./types";
import { ageLabel } from "./format";

// Leaflet's default marker images don't resolve through the bundler reliably,
// so we load them from Leaflet's CDN (same idea as the OpenStreetMap tiles).
const LEAFLET_CDN = "https://unpkg.com/leaflet@1.9.4/dist/images";
L.Marker.prototype.options.icon = L.icon({
  iconUrl: `${LEAFLET_CDN}/marker-icon.png`,
  iconRetinaUrl: `${LEAFLET_CDN}/marker-icon-2x.png`,
  shadowUrl: `${LEAFLET_CDN}/marker-shadow.png`,
  iconSize: [25, 41],
  iconAnchor: [12, 41],
  popupAnchor: [1, -34],
  shadowSize: [41, 41],
});

const TORONTO: [number, number] = [43.6532, -79.3832];
const MAX_POPUP_PROGRAMS = 25; // keep popups readable when a site has many

// One marker per location, with the programs running there grouped under it.
type LocationGroup = {
  name: string;
  lat: number;
  lng: number;
  district: string | null;
  programs: Program[];
};

function groupByLocation(programs: Program[]): LocationGroup[] {
  const groups = new Map<string, LocationGroup>();
  for (const p of programs) {
    // Skip programs we couldn't geocode or that have no location name.
    if (p.lat === null || p.lng === null || !p.location_name) continue;
    let group = groups.get(p.location_name);
    if (!group) {
      group = {
        name: p.location_name,
        lat: p.lat,
        lng: p.lng,
        district: p.district,
        programs: [],
      };
      groups.set(p.location_name, group);
    }
    group.programs.push(p);
  }
  return [...groups.values()];
}

// Pans/zooms the map to fit the current markers whenever the filters change.
function FitBounds({ groups }: { groups: LocationGroup[] }) {
  const map = useMap();
  useEffect(() => {
    if (groups.length === 0) return;
    if (groups.length === 1) {
      map.setView([groups[0].lat, groups[0].lng], 14);
      return;
    }
    map.fitBounds(
      groups.map((g) => [g.lat, g.lng] as [number, number]),
      { padding: [30, 30] }
    );
  }, [groups, map]);
  return null;
}

export default function ProgramMap({ programs }: { programs: Program[] }) {
  const groups = useMemo(() => groupByLocation(programs), [programs]);

  return (
    <div className="overflow-hidden rounded-xl border border-gray-200">
      <MapContainer center={TORONTO} zoom={11} scrollWheelZoom className="h-[70vh] w-full">
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        />
        <FitBounds groups={groups} />
        {groups.map((g) => (
          <Marker key={g.name} position={[g.lat, g.lng]}>
            <Popup>
              <div className="max-h-60 w-56 overflow-y-auto">
                <p className="font-semibold text-gray-900">{g.name}</p>
                {g.district && <p className="text-gray-500">{g.district}</p>}
                <p className="mt-1 text-gray-500">
                  {g.programs.length} program{g.programs.length === 1 ? "" : "s"}
                </p>
                <ul className="mt-2 space-y-2">
                  {g.programs.slice(0, MAX_POPUP_PROGRAMS).map((p) => (
                    <li key={p.course_id} className="border-t border-gray-100 pt-2">
                      <div className="font-medium text-gray-900">
                        {p.activity_title ?? p.course_title}
                      </div>
                      <div className="text-gray-500">
                        {ageLabel(p.age_min_years, p.age_max_years)}
                        {p.days && ` · ${p.days}`}
                        {p.start_time && ` · ${p.start_time}–${p.end_time}`}
                      </div>
                      {p.activity_url && (
                        <a
                          href={p.activity_url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-blue-600 underline"
                        >
                          View &amp; register →
                        </a>
                      )}
                    </li>
                  ))}
                </ul>
                {g.programs.length > MAX_POPUP_PROGRAMS && (
                  <p className="mt-2 text-gray-500">
                    +{g.programs.length - MAX_POPUP_PROGRAMS} more — refine filters to narrow down.
                  </p>
                )}
              </div>
            </Popup>
          </Marker>
        ))}
      </MapContainer>
    </div>
  );
}
