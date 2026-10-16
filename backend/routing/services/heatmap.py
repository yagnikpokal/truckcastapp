"""A corridor grid of weather risk for each hour from departure through +48h."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from routing.services.errors import UserError
from routing.services.geo import bearing_degrees, cumulative_miles, destination, interpolate
from routing.services.risk import assess_checkpoint
from routing.services.weather import load_forecast, snap


def build_heatmap(polylines: list[list[tuple[float, float]]], departure: datetime, load_lbs: float) -> dict:
    points = corridor_points(polylines)
    if len(points) < 2:
        raise UserError("The corridor does not have enough road to map a forecast.")
    forecast = load_forecast(points, departure, hours=56)
    hours = _hour_axis(departure)
    rows = []
    for lat, lon in points:
        scores = []
        for hour in hours:
            weather = forecast.at(lat, lon, hour)
            if weather.get("forecast_time") is None or weather.get("clamped"):
                scores.append(None)
                continue
            scored = assess_checkpoint(weather["wind_mph"], weather["rain_in_hr"], weather["snow_in_hr"], load_lbs)
            scores.append(scored["risk_score"])
        rows.append({"lat": lat, "lon": lon, "risk": scores})
    hours, rows = _trim_empty_hours(hours, rows)
    return {
        "hours": [hour.isoformat() for hour in hours],
        "points": rows,
    }


def corridor_points(polylines: list[list[tuple[float, float]]], target: int = 150) -> list[tuple[float, float]]:
    """Sample the trip corridor: the road itself plus a band on either side.

    Spacing grows with the length of the trip so a cross-country run stays near
    `target` weather cells instead of thousands.
    """
    profiles = []
    total = 0.0
    for line in polylines:
        if len(line) < 2:
            continue
        miles = cumulative_miles(line)
        if miles[-1] <= 0:
            continue
        profiles.append((line, miles))
        total += miles[-1]
    if not profiles or total <= 0:
        return []
    stations = max(8, target // 3)
    step = max(8.0, total / stations)
    seen: set[tuple[float, float]] = set()
    points: list[tuple[float, float]] = []
    zeros = None
    for line, miles in profiles:
        if zeros is None or len(zeros) != len(line):
            zeros = [0.0] * len(line)
        mile = 0.0
        offset = 6.0 if miles[-1] < 80 else 12.0
        while mile <= miles[-1] + 1e-6:
            point, _ = interpolate(line, miles, zeros, min(mile, miles[-1]))
            before, _ = interpolate(line, miles, zeros, max(0.0, mile - 1))
            after, _ = interpolate(line, miles, zeros, min(miles[-1], mile + 1))
            heading = bearing_degrees(before, after) if before != after else 0.0
            for shift in (0, 90, -90):
                if shift == 0:
                    lat, lon = point
                else:
                    lat, lon = destination(point[0], point[1], heading + shift, offset)
                cell = snap(lat, lon)
                if cell not in seen:
                    seen.add(cell)
                    points.append(cell)
            mile += step
        if len(points) >= 220:
            break
    return points[:220]


def _hour_axis(departure: datetime) -> list[datetime]:
    """Forty-nine hours beginning at the departure clock hour, in that timezone."""
    if departure.tzinfo is None:
        departure = departure.replace(tzinfo=timezone.utc)
    local = departure.astimezone(departure.tzinfo)
    start = local.replace(minute=0, second=0, microsecond=0)
    now = datetime.now(timezone.utc)
    if start < now - timedelta(hours=1):
        start = now.astimezone(departure.tzinfo).replace(minute=0, second=0, microsecond=0)
    return [start + timedelta(hours=offset) for offset in range(49)]


def _trim_empty_hours(hours: list[datetime], rows: list[dict]) -> tuple[list[datetime], list[dict]]:
    last = len(hours) - 1
    while last > 0 and all(row["risk"][last] is None for row in rows):
        last -= 1
    kept = hours[: last + 1]
    for row in rows:
        row["risk"] = row["risk"][: last + 1]
    return kept, rows
