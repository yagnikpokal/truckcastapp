import type { Checkpoint } from "../types";
import { RISK_COLORS, formatClock } from "../format";

interface CheckpointTableProps {
  checkpoints: Checkpoint[];
  timeZone: string;
  selectedIndex: number | null;
  onSelect: (index: number) => void;
}

export function CheckpointTable({ checkpoints, timeZone, selectedIndex, onSelect }: CheckpointTableProps) {
  const adjusted = checkpoints.some((checkpoint) => checkpoint.load_adjusted);
  return (
    <div className="checkpoints">
      <div className="section-head">
        <h3>Checkpoints</h3>
        <p>Weather at the estimated arrival.</p>
      </div>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Mile</th>
              <th>ETA</th>
              <th>Wind</th>
              <th>Rain</th>
              <th>Snow</th>
              <th>Risk</th>
            </tr>
          </thead>
          <tbody>
            {checkpoints.map((checkpoint) => (
              <tr
                key={checkpoint.index}
                className={checkpoint.index === selectedIndex ? "is-active" : undefined}
                onClick={() => onSelect(checkpoint.index)}
              >
                <td>{checkpoint.mile.toFixed(0)}</td>
                <td>{formatClock(checkpoint.eta, timeZone)}</td>
                <td>{Math.round(checkpoint.wind_mph)}</td>
                <td>{checkpoint.rain_in_hr.toFixed(2)}</td>
                <td>{checkpoint.snow_in_hr.toFixed(2)}</td>
                <td>
                  <span className="pill" style={{ background: RISK_COLORS[checkpoint.risk] }}>
                    {checkpoint.risk}
                  </span>
                  {checkpoint.load_adjusted ? <span title="Load rule raised the wind risk"> *</span> : null}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="footnote">Wind is mph. Rain and snow are inches per hour.{adjusted ? " * Load rule raised the wind risk." : ""}</p>
    </div>
  );
}
