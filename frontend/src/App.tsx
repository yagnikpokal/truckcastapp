import { FormEvent, useEffect, useState } from "react";
import { analyzeTrip, fetchHeatmap } from "./api";
import { CheckpointTable } from "./components/CheckpointTable";
import { ForecastBar } from "./components/ForecastBar";
import { MapView } from "./components/MapView";
import { PlaceField } from "./components/PlaceField";
import { RouteList } from "./components/RouteList";
import { RISK_COLORS, browserTimeZone, defaultDeparture } from "./format";
import type { Analysis, Heatmap, PlaceDraft } from "./types";

const SAMPLES = [
  { label: "Chicago → Indianapolis", origin: "Chicago, Illinois", destination: "Indianapolis, Indiana", load: 32000 },
  { label: "Dallas → Oklahoma City", origin: "Dallas, Texas", destination: "Oklahoma City, Oklahoma", load: 45000 },
  { label: "Seattle → Spokane", origin: "Seattle, Washington", destination: "Spokane, Washington", load: 28000 },
];

const LOAD_PRESETS = [15000, 32000, 45000, 62000];

export function App() {
  const [origin, setOrigin] = useState<PlaceDraft>({ text: "", place: null });
  const [destination, setDestination] = useState<PlaceDraft>({ text: "", place: null });
  const [departure, setDeparture] = useState(defaultDeparture);
  const [loadLbs, setLoadLbs] = useState(35000);
  const [sampleMiles, setSampleMiles] = useState<10 | 25 | 50>(25);
  const [planning, setPlanning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [analysis, setAnalysis] = useState<Analysis | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [selectedCheckpoint, setSelectedCheckpoint] = useState<number | null>(null);
  const [heatmap, setHeatmap] = useState<Heatmap | null>(null);
  const [heatStatus, setHeatStatus] = useState<"idle" | "loading" | "ready" | "error">("idle");
  const [heatError, setHeatError] = useState<string | null>(null);
  const [showHeat, setShowHeat] = useState(true);
  const [hour, setHour] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [zoomToken, setZoomToken] = useState(0);
  const [zoomId, setZoomId] = useState<string | null>(null);

  const selected = analysis?.routes.find((route) => route.id === selectedId) ?? null;

  useEffect(() => {
    if (!playing || !heatmap) return;
    const timer = window.setInterval(() => {
      setHour((current) => {
        const max = heatmap.hours.length - 1;
        return current >= max ? 0 : current + 1;
      });
    }, 480);
    return () => window.clearInterval(timer);
  }, [playing, heatmap]);

  async function plan(event?: FormEvent, draft?: { origin: PlaceDraft; destination: PlaceDraft; load: number }) {
    event?.preventDefault();
    const originDraft = draft?.origin ?? origin;
    const destinationDraft = draft?.destination ?? destination;
    const load = draft?.load ?? loadLbs;
    if (!originDraft.text.trim() || !destinationDraft.text.trim()) {
      setError("Enter an origin and a destination.");
      return;
    }
    setPlanning(true);
    setError(null);
    setHeatmap(null);
    setHeatStatus("loading");
    setHeatError(null);
    setPlaying(false);
    setHour(0);
    try {
      const result = await analyzeTrip({
        origin: originDraft.place ?? originDraft.text.trim(),
        destination: destinationDraft.place ?? destinationDraft.text.trim(),
        departure,
        timezone: browserTimeZone(),
        load_lbs: load,
        sample_miles: sampleMiles,
      });
      setAnalysis(result);
      setSelectedId(result.recommended_route_id);
      setSelectedCheckpoint(null);
      setPlanning(false);
      try {
        const grid = await fetchHeatmap(result);
        setHeatmap(grid);
        setHeatStatus("ready");
      } catch (heatFailure) {
        setHeatStatus("error");
        setHeatError(heatFailure instanceof Error ? heatFailure.message : "The corridor forecast is unavailable.");
      }
    } catch (failure) {
      setPlanning(false);
      setHeatStatus("idle");
      setError(failure instanceof Error ? failure.message : "Could not plan that trip.");
    }
  }

  function useSample(sample: (typeof SAMPLES)[number]) {
    const nextOrigin = { text: sample.origin, place: null };
    const nextDestination = { text: sample.destination, place: null };
    setOrigin(nextOrigin);
    setDestination(nextDestination);
    setLoadLbs(sample.load);
    void plan(undefined, { origin: nextOrigin, destination: nextDestination, load: sample.load });
  }

  const loadHint =
    loadLbs > 40000
      ? "Above 40,000 lb, 35–44 mph wind is Severe. Above 30,000 lb, 45–54 mph wind is No Travel."
      : loadLbs > 30000
        ? "Above 30,000 lb, 45–54 mph wind is No Travel."
        : "Wind at 55 mph or more is No Travel for every load.";

  return (
    <div className="app">
      <aside className="panel">
        <header className="brand">
          <span className="mark" aria-hidden="true" />
          <div>
            <p className="eyebrow">Dispatch</p>
            <h1>Truckcast</h1>
          </div>
        </header>
        <p className="lede">Three corridors, scored by the weather the truck will actually meet and the weight it is carrying.</p>

        <form
          onSubmit={(event) => {
            void plan(event);
          }}
        >
          <PlaceField id="origin" label="Origin" value={origin} onChange={setOrigin} />
          <PlaceField id="destination" label="Destination" value={destination} onChange={setDestination} />
          <div className="split">
            <div className="field">
              <label htmlFor="departure">Departure</label>
              <input id="departure" type="datetime-local" value={departure} onChange={(event) => setDeparture(event.target.value)} required />
            </div>
            <div className="field">
              <label htmlFor="load">Load (lb)</label>
              <input
                id="load"
                type="number"
                min={1}
                max={200000}
                step={1}
                value={loadLbs}
                onChange={(event) => setLoadLbs(Number(event.target.value))}
                required
              />
            </div>
          </div>
          <div className="presets" role="group" aria-label="Load presets">
            {LOAD_PRESETS.map((preset) => (
              <button key={preset} type="button" className={preset === loadLbs ? "chip is-on" : "chip"} onClick={() => setLoadLbs(preset)}>
                {(preset / 1000).toFixed(0)}k
              </button>
            ))}
          </div>
          <p className="hint">{loadHint}</p>
          <fieldset className="interval">
            <legend>Sample weather every</legend>
            <div className="segmented">
              {([10, 25, 50] as const).map((miles) => (
                <label key={miles} className={sampleMiles === miles ? "is-on" : undefined}>
                  <input
                    type="radio"
                    name="sample"
                    value={miles}
                    checked={sampleMiles === miles}
                    onChange={() => setSampleMiles(miles)}
                  />
                  {miles} mi
                </label>
              ))}
            </div>
          </fieldset>
          <button className="primary" type="submit" disabled={planning}>
            {planning ? "Planning routes…" : "Compare routes"}
          </button>
          <div className="samples">
            {SAMPLES.map((sample) => (
              <button key={sample.label} type="button" onClick={() => useSample(sample)} disabled={planning}>
                {sample.label}
              </button>
            ))}
          </div>
        </form>

        {error && (
          <p className="alert" role="alert">
            {error}
          </p>
        )}

        {analysis && selected && (
          <div className="results">
            <div className="section-head">
              <h2>Routes</h2>
              <p>
                {analysis.load_lbs.toLocaleString()} lb · every {analysis.sample_miles} mi
              </p>
            </div>
            <RouteList
              routes={analysis.routes}
              selectedId={selectedId}
              onSelect={(id) => {
                setSelectedId(id);
                setSelectedCheckpoint(null);
              }}
              onZoom={(id) => {
                setSelectedId(id);
                setZoomId(id);
                setZoomToken((value) => value + 1);
              }}
            />
            <CheckpointTable
              checkpoints={selected.checkpoints}
              timeZone={analysis.timezone}
              selectedIndex={selectedCheckpoint}
              onSelect={setSelectedCheckpoint}
            />
            <details className="rules">
              <summary>How a route is scored</summary>
              <p>
                Weather is sampled every {analysis.sample_miles} miles at the truck’s estimated arrival. Each leg takes the worse risk of its
                two ends.
              </p>
              <ul>
                <li>Wind: below 25 Low, 25–34 Moderate, 35–44 High, 45–54 Severe, 55+ No Travel.</li>
                <li>Rain, in/hr: below 0.10, then 0.10, 0.25, 0.50. Above 1.00 is No Travel. 1.00 stays Severe.</li>
                <li>Snow, in/hr: below 0.5, then 0.5, 1.0, 2.0. Above 3.0 is No Travel. 3.0 stays Severe.</li>
                <li>A shared boundary uses the higher band. The checkpoint keeps the worst of wind, rain, and snow.</li>
                <li>Load raises wind only: 45–54 mph above 30,000 lb is No Travel, and 35–44 mph above 40,000 lb is Severe.</li>
              </ul>
              <p>
                Recommendation order: fewest No Travel miles, fewest Severe miles, fewest High miles, lowest mile-weighted average, shortest
                time. No Travel is ranked first because it sits above Severe.
              </p>
            </details>
            <p className="routing-note">{analysis.routing_note}</p>
          </div>
        )}
        <footer className="credits">
          Routes: Valhalla / OSRM · Places: Photon · Weather: Open-Meteo · Map © Esri
        </footer>
      </aside>

      <main className="stage">
        {planning && <div className="progress" />}
        <MapView
          analysis={analysis}
          selectedId={selectedId}
          selectedCheckpoint={selectedCheckpoint}
          onSelectRoute={(id) => {
            setSelectedId(id);
            setSelectedCheckpoint(null);
          }}
          onSelectCheckpoint={setSelectedCheckpoint}
          heatmap={heatmap}
          showHeat={showHeat}
          hour={hour}
          zoomToken={zoomToken}
          zoomId={zoomId}
        />
        {!analysis && !planning && (
          <div className="empty">
            <p>Enter a haul to lay three routes on the map.</p>
          </div>
        )}
        <div className="legend" aria-label="Risk colors">
          {(["Low", "Moderate", "High", "Severe", "No Travel"] as const).map((level) => (
            <span key={level}>
              <i style={{ background: RISK_COLORS[level] }} />
              {level}
            </span>
          ))}
        </div>
        <ForecastBar
          heatmap={heatmap}
          status={heatStatus}
          error={heatError}
          showHeat={showHeat}
          hour={hour}
          playing={playing}
          timeZone={analysis?.timezone ?? browserTimeZone()}
          onToggle={setShowHeat}
          onHour={(value) => {
            setPlaying(false);
            setHour(value);
          }}
          onPlay={() => setPlaying((value) => !value)}
        />
      </main>
    </div>
  );
}
