"""Turn routed geometry and a forecast into ranked, weather-scored options."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from routing.services.errors import UserError
from routing.services.geocode import resolve_place
from routing.services.recommend import rank_routes
from routing.services.routing_api import get_routes
from routing.services.geo import simplify
from routing.services.sampling import (
    SAMPLE_MILES,
    average_label,
    build_segments,
    sample_checkpoints,
    score_checkpoints,
    summarize,
    worst_checkpoint,
)
from routing.services.weather import load_forecast


def analyze_trip(
    origin,
    destination,
    departure: str,
    timezone_name: str,
    load_lbs,
    sample_miles,
) -> dict:
    load = _parse_load(load_lbs)
    interval = _parse_interval(sample_miles)
    when = _parse_departure(departure, timezone_name or "UTC")
    origin_place = resolve_place(origin)
    destination_place = resolve_place(destination)
    routes, routing_note = get_routes(origin_place, destination_place, load)

    drafted = []
    points = []
    for route in routes:
        checkpoints = sample_checkpoints(
            route.coordinates,
            route.cum_miles,
            route.cum_seconds,
            interval,
            when,
        )
        drafted.append((route, checkpoints))
        points.extend((item["lat"], item["lon"]) for item in checkpoints)

    forecast = load_forecast(points, when, hours=56)
    built = []
    for route, checkpoints in drafted:
        scored = score_checkpoints(checkpoints, load, forecast.at)
        segments = build_segments(scored, route.coordinates, route.cum_miles)
        stats = summarize(segments, scored)
        built.append(
            {
                "id": route.id,
                "label": route.label,
                "provider": route.provider,
                "distance_miles": stats["distance_miles"],
                "duration_seconds": round(route.duration_seconds, 1),
                "stats": stats,
                "average_risk_label": average_label(stats["average_risk"]),
                "worst": worst_checkpoint(scored),
                "checkpoints": scored,
                "segments": segments,
                "overview": [
                    [round(lat, 5), round(lon, 5)] for lat, lon in simplify(route.coordinates, 0.002)
                ],
            }
        )
    ranked = rank_routes(built)
    recommended = next(route["id"] for route in ranked if route["is_recommended"])
    return {
        "origin": origin_place.as_dict(),
        "destination": destination_place.as_dict(),
        "departure": when.isoformat(),
        "timezone": str(when.tzinfo),
        "load_lbs": load,
        "sample_miles": interval,
        "recommended_route_id": recommended,
        "routing_note": routing_note,
        "routes": ranked,
    }


def _parse_load(value) -> float:
    try:
        load = float(value)
    except (TypeError, ValueError) as exc:
        raise UserError("Enter the load weight in pounds.") from exc
    if load <= 0 or load > 200_000:
        raise UserError("Load weight must be between 1 and 200,000 pounds.")
    return load


def _parse_interval(value) -> int:
    try:
        interval = int(value)
    except (TypeError, ValueError) as exc:
        raise UserError("Sample weather every 10, 25, or 50 miles.") from exc
    if interval not in SAMPLE_MILES:
        raise UserError("Sample weather every 10, 25, or 50 miles.")
    return interval


def _parse_departure(value: str, timezone_name: str) -> datetime:
    try:
        zone = ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError as exc:
        raise UserError("Unknown timezone. Reload the page and try again.") from exc
    try:
        parsed = datetime.fromisoformat(str(value))
    except (TypeError, ValueError) as exc:
        raise UserError("Departure time is not a valid date.") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=zone)
    else:
        parsed = parsed.astimezone(zone)
    now = datetime.now(timezone.utc)
    if parsed < now - timedelta(hours=6):
        raise UserError("Departure is too far in the past for a forecast.")
    if parsed > now + timedelta(days=12):
        raise UserError("Departure is outside the 12-day forecast window. Pick an earlier date.")
    return parsed
