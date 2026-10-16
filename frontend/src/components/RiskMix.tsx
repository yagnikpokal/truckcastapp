import type { RouteStats } from "../types";
import { RISK_COLORS, RISK_ORDER } from "../format";

const MILES: Record<(typeof RISK_ORDER)[number], keyof RouteStats> = {
  Low: "low_miles",
  Moderate: "moderate_miles",
  High: "high_miles",
  Severe: "severe_miles",
  "No Travel": "no_travel_miles",
};

export function RiskMix({ stats }: { stats: RouteStats }) {
  const total = stats.distance_miles || 1;
  return (
    <div className="mix" aria-hidden="true">
      {RISK_ORDER.map((level) => {
        const miles = stats[MILES[level]] as number;
        if (miles <= 0) return null;
        return <span key={level} style={{ width: `${(miles / total) * 100}%`, background: RISK_COLORS[level] }} />;
      })}
    </div>
  );
}
