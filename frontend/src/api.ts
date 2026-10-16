import type { Analysis, Heatmap, Place, TripQuery } from "./types";

async function readBody(response: Response): Promise<Record<string, unknown>> {
  const text = await response.text();
  if (!text) return {};
  try {
    return JSON.parse(text) as Record<string, unknown>;
  } catch {
    throw new Error(text.slice(0, 180));
  }
}

function errorMessage(body: Record<string, unknown>, fallback: string): string {
  return typeof body.error === "string" ? body.error : fallback;
}

export async function geocode(query: string): Promise<Place[]> {
  const response = await fetch(`/api/geocode?q=${encodeURIComponent(query)}`);
  const body = await readBody(response);
  if (!response.ok) throw new Error(errorMessage(body, "Place search failed."));
  return (body.results as Place[]) ?? [];
}

export async function analyzeTrip(query: TripQuery): Promise<Analysis> {
  const response = await fetch("/api/analyze", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(query),
  });
  const body = await readBody(response);
  if (!response.ok) throw new Error(errorMessage(body, "Could not plan that trip."));
  return body as unknown as Analysis;
}

export async function fetchHeatmap(analysis: Analysis): Promise<Heatmap> {
  const response = await fetch("/api/heatmap", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      departure: analysis.departure,
      timezone: analysis.timezone,
      load_lbs: analysis.load_lbs,
      routes: analysis.routes.map((route) => ({ coordinates: route.overview })),
    }),
  });
  const body = await readBody(response);
  if (!response.ok) throw new Error(errorMessage(body, "The corridor forecast is unavailable."));
  return body as unknown as Heatmap;
}
