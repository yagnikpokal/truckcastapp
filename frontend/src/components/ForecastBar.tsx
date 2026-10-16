import type { Heatmap } from "../types";
import { RISK_COLORS, RISK_ORDER, formatClock } from "../format";
import type { RiskLabel } from "../types";

const SCORE_LABEL: Record<number, RiskLabel> = {
  1: "Low",
  2: "Moderate",
  3: "High",
  4: "Severe",
  5: "No Travel",
};

interface ForecastBarProps {
  heatmap: Heatmap | null;
  status: "idle" | "loading" | "ready" | "error";
  error: string | null;
  showHeat: boolean;
  hour: number;
  playing: boolean;
  timeZone: string;
  onToggle: (show: boolean) => void;
  onHour: (hour: number) => void;
  onPlay: () => void;
}

export function ForecastBar({
  heatmap,
  status,
  error,
  showHeat,
  hour,
  playing,
  timeZone,
  onToggle,
  onHour,
  onPlay,
}: ForecastBarProps) {
  const max = Math.max(0, (heatmap?.hours.length ?? 49) - 1);
  const stamp = heatmap?.hours[Math.min(hour, max)];
  const summary = heatmap ? summarize(heatmap, Math.min(hour, max)) : null;
  return (
    <section className="forecast" aria-label="Corridor forecast">
      <div className="forecast-top">
        <label className="check">
          <input type="checkbox" checked={showHeat} onChange={(event) => onToggle(event.target.checked)} />
          Corridor forecast
        </label>
        <p className="forecast-when">
          {status === "loading" && "Building the 48-hour corridor…"}
          {status === "error" && error}
          {status === "ready" && stamp && (
            <>
              Hour {Math.min(hour, max)} · {formatClock(stamp, timeZone)}
            </>
          )}
          {status === "idle" && "Plan a trip to load the forecast."}
        </p>
        <button type="button" className="play" onClick={onPlay} disabled={!heatmap}>
          {playing ? "Pause" : "Play"}
        </button>
      </div>
      <input
        className="slider"
        type="range"
        min={0}
        max={max}
        step={1}
        value={Math.min(hour, max)}
        disabled={!heatmap}
        aria-label="Forecast hour after departure"
        onChange={(event) => onHour(Number(event.target.value))}
      />
      <div className="forecast-scale">
        <span>Departure hour</span>
        <span>+{max} h</span>
      </div>
      {summary && summary.total > 0 && (
        <p className="forecast-mix">
          {RISK_ORDER.map((level) => {
            const count = summary.counts[level];
            if (!count) return null;
            const pct = Math.round((count / summary.total) * 100);
            return (
              <span key={level}>
                <i style={{ background: RISK_COLORS[level] }} />
                {level} {pct}%
              </span>
            );
          })}
        </p>
      )}
    </section>
  );
}

function summarize(heatmap: Heatmap, hour: number) {
  const counts: Record<RiskLabel, number> = {
    Low: 0,
    Moderate: 0,
    High: 0,
    Severe: 0,
    "No Travel": 0,
  };
  let total = 0;
  for (const point of heatmap.points) {
    const score = point.risk[hour];
    if (score == null) continue;
    const label = SCORE_LABEL[score];
    if (!label) continue;
    counts[label] += 1;
    total += 1;
  }
  return { counts, total };
}
