import { useEffect, useMemo, useState } from "react";
import { MapContainer, TileLayer, Marker, Popup, Polyline, useMap } from "react-leaflet";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import { LocateFixed } from "lucide-react";

import type { GeoPoint, ItineraryStop } from "@/types/api";
import { Companion } from "@/components/decor/Companion";

interface Props {
  source?: GeoPoint;
  destination?: GeoPoint;
  itinerary?: ItineraryStop[];
}

type LatLng = [number, number];

function pin(bg: string, label: string, ring = "#fff") {
  return L.divIcon({
    className: "marker-drop",
    html: `<span style="
      display:grid;place-items:center;width:26px;height:26px;border-radius:9999px;
      background:${bg};color:#fff;font:700 11px/1 Inter,system-ui;
      box-shadow:0 0 0 3px ${ring},0 4px 10px rgba(36,27,46,.35)">${label}</span>`,
    iconSize: [26, 26],
    iconAnchor: [13, 13],
  });
}

const youIcon = L.divIcon({
  className: "",
  html: `<span style="display:block;width:16px;height:16px;border-radius:9999px;
    background:#5B8DEF;box-shadow:0 0 0 4px rgba(91,141,239,.3),0 0 0 8px rgba(91,141,239,.15)"></span>`,
  iconSize: [16, 16],
  iconAnchor: [8, 8],
});

function FitBounds({ points }: { points: LatLng[] }) {
  const map = useMap();
  useEffect(() => {
    if (points.length === 0) return;
    if (points.length === 1) {
      map.setView(points[0], 9);
      return;
    }
    map.fitBounds(L.latLngBounds(points), { padding: [40, 40] });
  }, [map, points]);
  return null;
}

export function MapPanel({ source, destination, itinerary = [] }: Props) {
  const [you, setYou] = useState<LatLng | null>(null);

  useEffect(() => {
    if (!navigator.geolocation) return;
    navigator.geolocation.getCurrentPosition(
      (p) => setYou([p.coords.latitude, p.coords.longitude]),
      () => {},
      { enableHighAccuracy: false, timeout: 8000, maximumAge: 300000 },
    );
  }, []);

  const stops: LatLng[] = useMemo(
    () => itinerary.map((s) => [s.lat, s.lon] as LatLng),
    [itinerary],
  );

  const all: LatLng[] = useMemo(() => {
    const pts: LatLng[] = [];
    if (source) pts.push([source.lat, source.lon]);
    if (destination) pts.push([destination.lat, destination.lon]);
    pts.push(...stops);
    if (you) pts.push(you);
    return pts;
  }, [source, destination, stops, you]);

  const hasData = !!source || !!destination || stops.length > 0;

  return (
    <div className="card relative overflow-hidden">
      <div className="h-[340px] w-full sm:h-[380px]">
        <MapContainer
          center={all[0] ?? [20.6, 78.9]}
          zoom={all.length ? 6 : 4}
          scrollWheelZoom={false}
          className="h-full w-full"
        >
          <TileLayer
            attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
            url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
          />
          <FitBounds points={all} />

          {you && (
            <Marker position={you} icon={youIcon}>
              <Popup>You are here</Popup>
            </Marker>
          )}

          {source && (
            <Marker position={[source.lat, source.lon]} icon={pin("#6C4CF1", "A")}>
              <Popup>Start · {source.name}</Popup>
            </Marker>
          )}

          {destination && stops.length === 0 && (
            <Marker position={[destination.lat, destination.lon]} icon={pin("#1FCBDE", "B")}>
              <Popup>Destination · {destination.name}</Popup>
            </Marker>
          )}

          {itinerary.map((s, i) => (
            <Marker key={s.name} position={[s.lat, s.lon]} icon={pin("#1FCBDE", String(i + 1))}>
              <Popup>
                <strong>Day {s.day}</strong> · {s.name}
                {s.blurb && <div style={{ marginTop: 4, maxWidth: 200 }}>{s.blurb}</div>}
              </Popup>
            </Marker>
          ))}

          {stops.length > 1 && (
            <Polyline positions={stops} pathOptions={{ color: "#6C4CF1", weight: 3, dashArray: "6 8" }} />
          )}
          {source && stops.length > 0 && (
            <Polyline
              positions={[[source.lat, source.lon], stops[0]]}
              pathOptions={{ color: "#9C96BC", weight: 2, dashArray: "2 8" }}
            />
          )}
          {source && destination && stops.length === 0 && (
            <Polyline
              positions={[[source.lat, source.lon], [destination.lat, destination.lon]]}
              pathOptions={{ color: "#9C96BC", weight: 2, dashArray: "2 8" }}
            />
          )}
        </MapContainer>
      </div>

      {!hasData && (
        <div className="pointer-events-none absolute inset-0 grid place-items-center bg-cream/70 backdrop-blur-[1px]">
          <div className="flex flex-col items-center gap-1">
            <Companion mood="idle" size={56} />
            <p className="flex items-center gap-1.5 rounded-full bg-paper px-3 py-1.5 text-xs font-medium text-ink-soft shadow-soft">
              <LocateFixed className="h-3.5 w-3.5" />
              Plan a trip to see it on the map
            </p>
          </div>
        </div>
      )}
    </div>
  );
}
