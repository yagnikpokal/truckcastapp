import type { RouteOption } from "../types";
import { formatDuration, formatMiles } from "../format";
import { RiskMix } from "./RiskMix";

interface RouteListProps {
  routes: RouteOption[];
  selectedId: string | null;
  onSelect: (id: string) => void;
  onZoom: (id: string) => void;
}

export function RouteList({ routes, selectedId, onSelect, onZoom }: RouteListProps) {
  return (
    <div className="routes">
      {routes.map((route) => {
        const selected = route.id === selectedId;
        return (
          <article key={route.id} className={selected ? "route is-selected" : "route"}>
            <button type="button" className="route-select" onClick={() => onSelect(route.id)} aria-pressed={selected}>
              <div className="route-top">
                <span className="rank">#{route.rank}</span>
                {route.is_recommended && <span className="badge">Recommended</span>}
              </div>
              <h3>{route.label}</h3>
              <p className="meta">
                {formatDuration(route.duration_seconds)} · {formatMiles(route.distance_miles)}
              </p>
              <RiskMix stats={route.stats} />
              <p className="stat-line">
                No travel {route.stats.no_travel_miles.toFixed(0)} · Severe {route.stats.severe_miles.toFixed(0)} · High{" "}
                {route.stats.high_miles.toFixed(0)} · Avg {route.stats.average_risk.toFixed(2)}
              </p>
              {route.worst && (
                <p className="worst">
                  Worst checkpoint: {route.worst.risk} at mile {Math.round(route.worst.mile)}
                </p>
              )}
            </button>
            {route.decision && <p className="decision">{route.decision}</p>}
            {route.warning && <p className="warning">{route.warning}</p>}
            <button type="button" className="zoom" onClick={() => onZoom(route.id)}>
              Zoom to route
            </button>
          </article>
        );
      })}
    </div>
  );
}
