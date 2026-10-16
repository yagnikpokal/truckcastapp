import { useEffect, useRef } from "react";
import L from "leaflet";
import type { Analysis, Checkpoint, Heatmap, RiskLabel } from "../types";
import { RISK_COLORS, escapeHtml, formatClock } from "../format";
import { corridorHeat, type CorridorHeat } from "../heatLayer";

interface MapViewProps {
  analysis: Analysis | null;
  selectedId: string | null;
  selectedCheckpoint: number | null;
  onSelectRoute: (id: string) => void;
  onSelectCheckpoint: (index: number) => void;
  heatmap: Heatmap | null;
  showHeat: boolean;
  hour: number;
  zoomToken: number;
  zoomId: string | null;
}

export function MapView({
  analysis,
  selectedId,
  selectedCheckpoint,
  onSelectRoute,
  onSelectCheckpoint,
  heatmap,
  showHeat,
  hour,
  zoomToken,
  zoomId,
}: MapViewProps) {
  const nodeRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<L.Map | null>(null);
  const routesLayer = useRef<L.LayerGroup | null>(null);
  const heatRef = useRef<CorridorHeat | null>(null);
  const selectRouteRef = useRef(onSelectRoute);
  const selectCheckpointRef = useRef(onSelectCheckpoint);
  selectRouteRef.current = onSelectRoute;
  selectCheckpointRef.current = onSelectCheckpoint;

  useEffect(() => {
    if (!nodeRef.current || mapRef.current) return;
    const map = L.map(nodeRef.current, {
      zoomControl: true,
      preferCanvas: true,
    }).setView([39.5, -96.5], 4);
    L.tileLayer("https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{z}/{y}/{x}", {
      attribution: "Tiles &copy; Esri",
      maxZoom: 19,
    }).addTo(map);
    map.createPane("heat");
    const heatPane = map.getPane("heat");
    if (heatPane) {
      heatPane.style.zIndex = "350";
      heatPane.style.pointerEvents = "none";
    }
    map.createPane("routes");
    const routePane = map.getPane("routes");
    if (routePane) routePane.style.zIndex = "450";
    routesLayer.current = L.layerGroup().addTo(map);
    mapRef.current = map;
    const onResize = () => map.invalidateSize();
    window.addEventListener("resize", onResize);
    return () => {
      window.removeEventListener("resize", onResize);
      map.remove();
      mapRef.current = null;
    };
  }, []);

  useEffect(() => {
    const map = mapRef.current;
    const layer = routesLayer.current;
    if (!map || !layer) return;
    layer.clearLayers();
    if (!analysis) return;
    const activeId = selectedId ?? analysis.recommended_route_id;
    const ordered = [...analysis.routes].sort((left, right) => Number(left.id === activeId) - Number(right.id === activeId));
    for (const route of ordered) {
      const active = route.id === activeId;
      for (const segment of route.segments) {
        const line = L.polyline(segment.coordinates, {
          pane: "routes",
          color: RISK_COLORS[segment.risk],
          weight: active ? 6 : 3,
          opacity: active ? 0.95 : 0.38,
          lineCap: "round",
          lineJoin: "round",
        });
        line.on("click", () => selectRouteRef.current(route.id));
        line.addTo(layer);
      }
      route.checkpoints.forEach((checkpoint, index) => {
        const highlighted = active && index === selectedCheckpoint;
        const marker = L.circleMarker([checkpoint.lat, checkpoint.lon], {
          pane: "routes",
          radius: highlighted ? 8 : active ? 5.5 : 3.5,
          color: highlighted ? "#f4f7ef" : "#10140f",
          weight: highlighted ? 3 : 1.5,
          fillColor: RISK_COLORS[checkpoint.risk],
          fillOpacity: active ? 1 : 0.75,
        });
        marker.bindPopup(popupHtml(checkpoint, analysis.timezone), { className: "risk-popup", maxWidth: 260 });
        marker.on("click", () => {
          selectRouteRef.current(route.id);
          selectCheckpointRef.current(index);
        });
        marker.addTo(layer);
        if (highlighted) marker.openPopup();
      });
    }
    const origin = L.circleMarker([analysis.origin.lat, analysis.origin.lon], {
      pane: "routes",
      radius: 7,
      color: "#d6f25c",
      weight: 2,
      fillColor: "#d6f25c",
      fillOpacity: 1,
    });
    origin.bindTooltip("Origin", { direction: "top" });
    origin.addTo(layer);
    const destination = L.circleMarker([analysis.destination.lat, analysis.destination.lon], {
      pane: "routes",
      radius: 7,
      color: "#d6f25c",
      weight: 2,
      fillColor: "#10140f",
      fillOpacity: 1,
    });
    destination.bindTooltip("Destination", { direction: "top" });
    destination.addTo(layer);
    if (selectedCheckpoint != null) {
      const activeRoute = analysis.routes.find((route) => route.id === activeId);
      const checkpoint = activeRoute?.checkpoints[selectedCheckpoint];
      if (checkpoint) map.panTo([checkpoint.lat, checkpoint.lon], { animate: true });
    }
  }, [analysis, selectedId, selectedCheckpoint]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !analysis) return;
    const bounds = L.latLngBounds([]);
    for (const route of analysis.routes) {
      for (const pair of route.overview) bounds.extend(pair);
    }
    if (!bounds.isValid()) return;
    map.invalidateSize();
    map.fitBounds(bounds, { paddingTopLeft: [36, 36], paddingBottomRight: [36, 140], maxZoom: 10 });
  }, [analysis]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !analysis || !zoomToken || !zoomId) return;
    const route = analysis.routes.find((item) => item.id === zoomId);
    if (!route) return;
    const bounds = L.latLngBounds(route.overview);
    if (bounds.isValid()) {
      map.fitBounds(bounds, { paddingTopLeft: [36, 36], paddingBottomRight: [36, 140], maxZoom: 12 });
    }
  }, [zoomToken, zoomId, analysis]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    if (heatRef.current) {
      map.removeLayer(heatRef.current);
      heatRef.current = null;
    }
    if (!showHeat || !heatmap) return;
    const layer = corridorHeat(toHeat(heatmap, hour), {
      pane: "heat",
      radius: radiusForZoom(map.getZoom()),
      blur: 16,
    });
    layer.addTo(map);
    heatRef.current = layer;
    const onZoom = () => layer.setOptions({ radius: radiusForZoom(map.getZoom()) });
    map.on("zoomend", onZoom);
    return () => {
      map.off("zoomend", onZoom);
    };
  }, [heatmap, showHeat]);

  useEffect(() => {
    if (!heatRef.current || !heatmap || !showHeat) return;
    heatRef.current.setLatLngs(toHeat(heatmap, hour));
  }, [hour, heatmap, showHeat]);

  return <div ref={nodeRef} className="map" />;
}

function toHeat(heatmap: Heatmap, hour: number): Array<[number, number, number]> {
  const points: Array<[number, number, number]> = [];
  const index = Math.min(hour, Math.max(0, heatmap.hours.length - 1));
  for (const point of heatmap.points) {
    const score = point.risk[index];
    if (score == null) continue;
    const intensity = 0.16 + ((score - 1) / 4) * 0.84;
    points.push([point.lat, point.lon, intensity]);
  }
  return points;
}

function radiusForZoom(zoom: number): number {
  if (zoom <= 5) return 18;
  if (zoom <= 7) return 26;
  if (zoom <= 9) return 34;
  return 42;
}

function popupHtml(checkpoint: Checkpoint, timeZone: string): string {
  const rows: Array<[string, string, RiskLabel]> = [
    ["Wind", `${Math.round(checkpoint.wind_mph)} mph`, checkpoint.wind_risk],
    ["Rain", `${checkpoint.rain_in_hr.toFixed(2)} in/hr`, checkpoint.rain_risk],
    ["Snow", `${checkpoint.snow_in_hr.toFixed(2)} in/hr`, checkpoint.snow_risk],
  ];
  const detail = rows
    .map(
      ([name, value, risk]) =>
        `<div class="pop-row"><span>${name}</span><strong>${value}</strong><em style="color:${RISK_COLORS[risk]}">${risk}</em></div>`,
    )
    .join("");
  const note = checkpoint.load_adjusted ? `<p class="pop-note">Load rule raised the wind risk.</p>` : "";
  const clamped = checkpoint.forecast_clamped ? `<p class="pop-note">Nearest forecast hour is outside the usual window.</p>` : "";
  return `<div class="pop">
    <p class="pop-kicker">Mile ${checkpoint.mile.toFixed(0)}</p>
    <h4>${escapeHtml(checkpoint.risk)}</h4>
    <p class="pop-eta">${escapeHtml(formatClock(checkpoint.eta, timeZone))}</p>
    ${detail}
    ${note}
    ${clamped}
  </div>`;
}
