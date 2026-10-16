"""Distance, bearing, and point-along-line helpers. Distances are statute miles."""

from __future__ import annotations

import math

EARTH_MILES = 3958.7613


def haversine_miles(a: tuple[float, float], b: tuple[float, float]) -> float:
    lat1, lon1 = math.radians(a[0]), math.radians(a[1])
    lat2, lon2 = math.radians(b[0]), math.radians(b[1])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * EARTH_MILES * math.asin(min(1.0, math.sqrt(h)))


def bearing_degrees(a: tuple[float, float], b: tuple[float, float]) -> float:
    lat1, lon1 = math.radians(a[0]), math.radians(a[1])
    lat2, lon2 = math.radians(b[0]), math.radians(b[1])
    y = math.sin(lon2 - lon1) * math.cos(lat2)
    x = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(lon2 - lon1)
    return (math.degrees(math.atan2(y, x)) + 360) % 360


def destination(lat: float, lon: float, bearing_deg: float, miles: float) -> tuple[float, float]:
    d = miles / EARTH_MILES
    br = math.radians(bearing_deg)
    lat1 = math.radians(lat)
    lon1 = math.radians(lon)
    lat2 = math.asin(math.sin(lat1) * math.cos(d) + math.cos(lat1) * math.sin(d) * math.cos(br))
    lon2 = lon1 + math.atan2(
        math.sin(br) * math.sin(d) * math.cos(lat1),
        math.cos(d) - math.sin(lat1) * math.sin(lat2),
    )
    return math.degrees(lat2), (math.degrees(lon2) + 540) % 360 - 180


def cumulative_miles(coords: list[tuple[float, float]]) -> list[float]:
    miles = [0.0]
    for index in range(1, len(coords)):
        miles.append(miles[-1] + haversine_miles(coords[index - 1], coords[index]))
    return miles


def interpolate(
    coords: list[tuple[float, float]],
    cum_miles: list[float],
    cum_seconds: list[float],
    target_miles: float,
) -> tuple[tuple[float, float], float]:
    """Point and elapsed seconds at a distance along the polyline."""
    if not coords:
        raise ValueError("Route has no coordinates")
    if target_miles <= 0:
        return coords[0], float(cum_seconds[0])
    total = cum_miles[-1]
    if target_miles >= total:
        return coords[-1], float(cum_seconds[-1])
    high = 1
    while high < len(cum_miles) and cum_miles[high] < target_miles:
        high += 1
    low = high - 1
    span = cum_miles[high] - cum_miles[low]
    frac = 0.0 if span <= 0 else (target_miles - cum_miles[low]) / span
    lat = coords[low][0] + (coords[high][0] - coords[low][0]) * frac
    lon = coords[low][1] + (coords[high][1] - coords[low][1]) * frac
    seconds = cum_seconds[low] + (cum_seconds[high] - cum_seconds[low]) * frac
    return (lat, lon), seconds


def slice_line(
    coords: list[tuple[float, float]],
    cum_miles: list[float],
    start_mile: float,
    end_mile: float,
) -> list[tuple[float, float]]:
    """Coordinates covering the inclusive mile range, with clipped endpoints."""
    if len(coords) < 2:
        return list(coords)
    start_mile = max(0.0, start_mile)
    end_mile = min(cum_miles[-1], max(start_mile, end_mile))
    dummy_seconds = [0.0] * len(coords)
    start_pt, _ = interpolate(coords, cum_miles, dummy_seconds, start_mile)
    end_pt, _ = interpolate(coords, cum_miles, dummy_seconds, end_mile)
    line = [start_pt]
    for index, point in enumerate(coords):
        if cum_miles[index] > start_mile + 1e-6 and cum_miles[index] < end_mile - 1e-6:
            line.append(point)
    line.append(end_pt)
    return _dedupe(line)


def _dedupe(points: list[tuple[float, float]]) -> list[tuple[float, float]]:
    cleaned = [points[0]]
    for point in points[1:]:
        if abs(point[0] - cleaned[-1][0]) > 1e-7 or abs(point[1] - cleaned[-1][1]) > 1e-7:
            cleaned.append(point)
    return cleaned


def simplify(points: list[tuple[float, float]], epsilon: float = 0.0008) -> list[tuple[float, float]]:
    """Douglas–Peucker in degrees. Keeps the road shape, drops dense vertices."""
    if len(points) < 3:
        return list(points)
    keep = [False] * len(points)
    keep[0] = True
    keep[-1] = True
    stack = [(0, len(points) - 1)]
    while stack:
        start, end = stack.pop()
        ax, ay = points[start]
        bx, by = points[end]
        max_dist = 0.0
        winner = None
        for index in range(start + 1, end):
            dist = _perpendicular(points[index], (ax, ay), (bx, by))
            if dist > max_dist:
                max_dist = dist
                winner = index
        if winner is not None and max_dist > epsilon:
            keep[winner] = True
            stack.append((start, winner))
            stack.append((winner, end))
    return [point for point, flagged in zip(points, keep) if flagged]


def _perpendicular(
    point: tuple[float, float],
    start: tuple[float, float],
    end: tuple[float, float],
) -> float:
    dx = end[0] - start[0]
    dy = end[1] - start[1]
    if dx == 0 and dy == 0:
        return math.hypot(point[0] - start[0], point[1] - start[1])
    t = ((point[0] - start[0]) * dx + (point[1] - start[1]) * dy) / (dx * dx + dy * dy)
    t = max(0.0, min(1.0, t))
    return math.hypot(point[0] - (start[0] + t * dx), point[1] - (start[1] + t * dy))
