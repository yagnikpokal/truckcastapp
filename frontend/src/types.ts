export type RiskLabel = "Low" | "Moderate" | "High" | "Severe" | "No Travel";

export interface Place {
  label: string;
  lat: number;
  lon: number;
}

export interface Checkpoint {
  index: number;
  mile: number;
  lat: number;
  lon: number;
  eta: string;
  elapsed_seconds: number;
  wind_mph: number;
  rain_in_hr: number;
  snow_in_hr: number;
  forecast_time: string | null;
  forecast_clamped: boolean;
  risk: RiskLabel;
  risk_score: number;
  wind_risk: RiskLabel;
  rain_risk: RiskLabel;
  snow_risk: RiskLabel;
  drivers: string[];
  load_adjusted: boolean;
}

export interface Segment {
  start_mile: number;
  end_mile: number;
  miles: number;
  risk: RiskLabel;
  risk_score: number;
  coordinates: [number, number][];
}

export interface RouteStats {
  low_miles: number;
  moderate_miles: number;
  high_miles: number;
  severe_miles: number;
  no_travel_miles: number;
  average_risk: number;
  distance_miles: number;
}

export interface RouteOption {
  id: string;
  label: string;
  provider: string;
  rank: number;
  is_recommended: boolean;
  decision: string | null;
  warning: string | null;
  distance_miles: number;
  duration_seconds: number;
  stats: RouteStats;
  average_risk_label: string;
  worst: { mile: number; risk: RiskLabel; eta: string } | null;
  checkpoints: Checkpoint[];
  segments: Segment[];
  overview: [number, number][];
}

export interface Analysis {
  origin: Place;
  destination: Place;
  departure: string;
  timezone: string;
  load_lbs: number;
  sample_miles: 10 | 25 | 50;
  recommended_route_id: string;
  routing_note: string;
  routes: RouteOption[];
}

export interface Heatmap {
  hours: string[];
  points: { lat: number; lon: number; risk: Array<number | null> }[];
}

export interface PlaceDraft {
  text: string;
  place: Place | null;
}

export interface TripQuery {
  origin: string | Place;
  destination: string | Place;
  departure: string;
  timezone: string;
  load_lbs: number;
  sample_miles: 10 | 25 | 50;
}
