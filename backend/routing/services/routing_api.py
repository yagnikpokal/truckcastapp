"""Three route options.

Valhalla's truck profile is preferred because it returns timed maneuvers and
alternate corridors. If that service cannot produce three distinct routes, the
missing corridors are requested through perpendicular via points. OSRM is the
fallback when Valhalla is unreachable.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from routing.services.errors import UpstreamError, UserError
from routing.services.geo import (
    bearing_degrees,
    cumulative_miles,
    destination,
    haversine_miles,
    interpolate,
)
from routing.services.geocode import Place
from routing.services.http import request_json
from routing.services.polyline import decode_polyline

VALHALLA_URL = os.environ.get("VALHALLA_URL", "https://valhalla1.openstreetmap.de/route")
OSRM_URL = os.environ.get("OSRM_URL", "https://router.project-osrm.org")


@dataclass
class RouteGeometry:
    id: str
    label: str
    coordinates: list[tuple[float, float]]
    cum_miles: list[float]
    cum_seconds: list[float]
    provider: str

    @property
    def distance_miles(self) -> float:
        return self.cum_miles[-1] if self.cum_miles else 0.0

    @property
    def duration_seconds(self) -> float:
        return self.cum_seconds[-1] if self.cum_seconds else 0.0


def get_routes(origin: Place, destination_place: Place, load_lbs: float) -> tuple[list[RouteGeometry], str]:
    apart = haversine_miles((origin.lat, origin.lon), (destination_place.lat, destination_place.lon))
    if apart < 2:
        raise UserError("Origin and destination are too close. Pick places at least a few miles apart.")
    if apart > 2200:
        raise UserError("That trip is too long to sample reliably in one request. Split it into shorter legs.")

    note = "Truck profile via Valhalla on OpenStreetMap. Arrival times follow that profile."
    routes: list[RouteGeometry] = []
    try:
        routes, costing = _valhalla_routes(origin, destination_place, load_lbs)
        if costing == "auto":
            note = "Driving profile via Valhalla. The truck profile could not route this pair."
    except UpstreamError:
        routes = []
    if not routes:
        routes = _osrm_routes(origin, destination_place)
        note = "Driving profile via OSRM. Truck routing was unavailable, so times are car-profile estimates."

    routes = _fill_until_three(routes, origin, destination_place, load_lbs)
    if not routes:
        raise UpstreamError("No drivable route was found between those places.")
    _assign_ids(routes)
    return routes[:3], note


def _valhalla_routes(origin: Place, destination_place: Place, load_lbs: float) -> tuple[list[RouteGeometry], str]:
    errors: list[UpstreamError] = []
    for costing in ("truck", "auto"):
        try:
            payload = _valhalla_call(
                [
                    {"lat": origin.lat, "lon": origin.lon},
                    {"lat": destination_place.lat, "lon": destination_place.lon},
                ],
                load_lbs,
                alternates=2,
                costing=costing,
            )
            candidates = [_from_valhalla_trip(payload["trip"], costing)]
        except (UpstreamError, KeyError, ValueError) as exc:
            errors.append(exc if isinstance(exc, UpstreamError) else UpstreamError("The routing service returned an unreadable trip."))
            continue
        for alternate in payload.get("alternates") or []:
            trip = alternate.get("trip")
            if not trip:
                continue
            try:
                candidates.append(_from_valhalla_trip(trip, costing))
            except (UpstreamError, KeyError, ValueError):
                continue
        routes = _distinct(candidates)
        if routes:
            return routes, costing
    if errors:
        raise errors[-1]
    return [], "auto"


def _fill_until_three(
    routes: list[RouteGeometry],
    origin: Place,
    destination_place: Place,
    load_lbs: float,
) -> list[RouteGeometry]:
    if len(routes) >= 3 or not routes:
        return routes
    primary = routes[0]
    offset = max(8.0, min(35.0, primary.distance_miles * 0.12))
    candidates = []
    for fraction in (0.5, 0.35, 0.65):
        for side in (1, -1):
            via = _offset_via(primary, fraction, side, offset)
            if via:
                candidates.append(via)
    for via in candidates:
        if len(routes) >= 3:
            break
        extra = _via_route(origin, destination_place, via, load_lbs, primary.provider)
        if extra and _distinct(routes + [extra])[-1] is extra:
            routes.append(extra)
    return routes


def _via_route(
    origin: Place,
    destination_place: Place,
    via: tuple[float, float],
    load_lbs: float,
    provider: str,
) -> RouteGeometry | None:
    locations = [
        {"lat": origin.lat, "lon": origin.lon},
        {"lat": via[0], "lon": via[1]},
        {"lat": destination_place.lat, "lon": destination_place.lon},
    ]
    if provider.startswith("valhalla") or provider in {"truck", "auto"}:
        costing = "truck" if provider in {"truck", "valhalla-truck"} else "auto"
        try:
            payload = _valhalla_call(locations, load_lbs, alternates=0, costing=costing if costing in {"truck", "auto"} else "auto")
            return _from_valhalla_trip(payload["trip"], costing if costing in {"truck", "auto"} else "auto")
        except (UpstreamError, UserError, KeyError, IndexError, ValueError):
            pass
    try:
        return _osrm_via(origin, via, destination_place)
    except UpstreamError:
        return None


def _valhalla_call(locations: list[dict], load_lbs: float, alternates: int, costing: str) -> dict:
    body: dict = {
        "locations": locations,
        "costing": costing,
        "units": "miles",
        "alternates": alternates,
    }
    if costing == "truck":
        tonnes = max(load_lbs, 2000) * 0.00045359237
        body["costing_options"] = {
            "truck": {
                "weight": round(tonnes, 2),
                "height": 4.11,
                "width": 2.6,
                "length": 21.64,
                "axle_load": 9.07,
            }
        }
    payload = request_json("POST", VALHALLA_URL, json=body, timeout=35)
    if not isinstance(payload, dict) or "trip" not in payload:
        detail = ""
        if isinstance(payload, dict) and isinstance(payload.get("error"), str):
            detail = payload["error"][:180]
        raise UpstreamError(detail or "The routing service did not return a trip.")
    return payload


def _from_valhalla_trip(trip: dict, costing: str) -> RouteGeometry:
    coords: list[tuple[float, float]] = []
    miles: list[float] = []
    seconds: list[float] = []
    for leg in trip.get("legs") or []:
        leg_coords = decode_polyline(leg.get("shape") or "", precision=6)
        leg_miles, leg_seconds = time_along_shape(leg_coords, leg.get("maneuvers") or [])
        _append_leg(coords, miles, seconds, leg_coords, leg_miles, leg_seconds)
    if len(coords) < 2:
        raise UpstreamError("The routing service returned an empty path.")
    label = _highway_label(trip) or "Alternate corridor"
    return RouteGeometry(
        id="",
        label=label,
        coordinates=coords,
        cum_miles=miles,
        cum_seconds=seconds,
        provider=f"valhalla-{costing}",
    )


def time_along_shape(
    coords: list[tuple[float, float]],
    maneuvers: list[dict],
) -> tuple[list[float], list[float]]:
    """Spread each maneuver's duration across its shape vertices by distance."""
    miles = cumulative_miles(coords)
    seconds: list[float | None] = [None] * len(coords)
    if coords:
        seconds[0] = 0.0
    for maneuver in maneuvers:
        start = _clamp_index(maneuver.get("begin_shape_index", 0), len(coords))
        end = _clamp_index(maneuver.get("end_shape_index", start), len(coords))
        if end < start:
            continue
        if seconds[start] is None:
            seconds[start] = _previous_known(seconds, start)
        base = float(seconds[start] or 0)
        span = miles[end] - miles[start]
        duration = float(maneuver.get("time") or 0)
        for index in range(start, end + 1):
            frac = 0.0 if span <= 0 else (miles[index] - miles[start]) / span
            seconds[index] = base + duration * frac
    _fill_time_gaps(miles, seconds)
    return miles, [float(value or 0) for value in seconds]


def _fill_time_gaps(miles: list[float], seconds: list[float | None]) -> None:
    known = [index for index, value in enumerate(seconds) if value is not None]
    if not known:
        total_miles = miles[-1] if miles else 0
        speed = 50 / 3600  # miles per second, a conservative highway guess
        for index, mile in enumerate(miles):
            seconds[index] = 0 if speed == 0 else mile / speed
        return
    for index in range(known[0]):
        seconds[index] = seconds[known[0]]
    for left, right in zip(known, known[1:]):
        gap = right - left
        if gap <= 1:
            continue
        for step in range(1, gap):
            frac = step / gap
            seconds[left + step] = float(seconds[left]) + (float(seconds[right]) - float(seconds[left])) * frac
    for index in range(known[-1] + 1, len(seconds)):
        prev = index - 1
        hop = miles[index] - miles[prev]
        window = miles[known[-1]] - miles[max(0, known[-1] - 1)]
        rate = 0.0
        if window > 0 and seconds[known[-1]] is not None and seconds[max(0, known[-1] - 1)] is not None:
            rate = (float(seconds[known[-1]]) - float(seconds[max(0, known[-1] - 1)])) / window
        if rate <= 0:
            rate = 3600 / 50
        seconds[index] = float(seconds[prev] or 0) + hop * rate


def _previous_known(seconds: list[float | None], index: int) -> float:
    for cursor in range(index - 1, -1, -1):
        if seconds[cursor] is not None:
            return float(seconds[cursor])
    return 0.0


def _clamp_index(value, size: int) -> int:
    try:
        index = int(value)
    except (TypeError, ValueError):
        index = 0
    return max(0, min(index, max(0, size - 1)))


def _append_leg(coords, miles, seconds, leg_coords, leg_miles, leg_seconds) -> None:
    if not leg_coords:
        return
    if not coords:
        coords.extend(leg_coords)
        miles.extend(leg_miles)
        seconds.extend(leg_seconds)
        return
    mile_base = miles[-1]
    second_base = seconds[-1]
    for index in range(1, len(leg_coords)):
        coords.append(leg_coords[index])
        miles.append(mile_base + leg_miles[index])
        seconds.append(second_base + leg_seconds[index])


def _highway_label(trip: dict) -> str:
    totals: dict[str, float] = {}
    for leg in trip.get("legs") or []:
        for maneuver in leg.get("maneuvers") or []:
            names = maneuver.get("street_names") or []
            if not names:
                continue
            name = str(names[0])
            if not any(character.isdigit() for character in name):
                continue
            totals[name] = totals.get(name, 0.0) + float(maneuver.get("length") or 0)
    top = sorted(totals, key=lambda name: totals[name], reverse=True)
    chosen: list[str] = []
    for name in top:
        if any(_same_road(name, other) for other in chosen):
            continue
        chosen.append(name)
        if len(chosen) == 2:
            break
    return " · ".join(chosen)


def _same_road(left: str, right: str) -> bool:
    return left == right or left.startswith(right + " ") or right.startswith(left + " ")


def _offset_via(route: RouteGeometry, fraction: float, side: int, offset_miles: float) -> tuple[float, float] | None:
    total = route.distance_miles
    if total <= 0:
        return None
    target = total * fraction
    point, _ = interpolate(route.coordinates, route.cum_miles, route.cum_seconds, target)
    before, _ = interpolate(route.coordinates, route.cum_miles, route.cum_seconds, max(0.0, target - 1))
    after, _ = interpolate(route.coordinates, route.cum_miles, route.cum_seconds, min(total, target + 1))
    if before == after:
        return None
    heading = bearing_degrees(before, after)
    return destination(point[0], point[1], heading + (90 * side), offset_miles)


def _osrm_routes(origin: Place, destination_place: Place) -> list[RouteGeometry]:
    payload = _osrm_call([(origin.lon, origin.lat), (destination_place.lon, destination_place.lat)], alternatives=2)
    routes = [_from_osrm(route) for route in payload.get("routes") or []]
    return _distinct(routes)


def _osrm_via(origin: Place, via: tuple[float, float], destination_place: Place) -> RouteGeometry:
    payload = _osrm_call(
        [(origin.lon, origin.lat), (via[1], via[0]), (destination_place.lon, destination_place.lat)],
        alternatives=0,
    )
    routes = payload.get("routes") or []
    if not routes:
        raise UpstreamError("No via-route was found.")
    route = _from_osrm(routes[0])
    route.label = route.label if route.label != "Driving route" else "Detour corridor"
    return route


def _osrm_call(lonlat_points: list[tuple[float, float]], alternatives: int) -> dict:
    path = ";".join(f"{lon:.6f},{lat:.6f}" for lon, lat in lonlat_points)
    url = f"{OSRM_URL.rstrip('/')}/route/v1/driving/{path}"
    params = {
        "alternatives": str(alternatives) if alternatives else "false",
        "overview": "full",
        "geometries": "geojson",
        "annotations": "duration,distance",
        "steps": "false",
    }
    payload = request_json("GET", url, params=params, timeout=30)
    if not isinstance(payload, dict) or payload.get("code") != "Ok":
        message = payload.get("message") if isinstance(payload, dict) else ""
        raise UpstreamError(message or "OSRM could not route this trip.")
    return payload


def _from_osrm(route: dict) -> RouteGeometry:
    coords = [(float(lat), float(lon)) for lon, lat in route["geometry"]["coordinates"]]
    distances: list[float] = []
    durations: list[float] = []
    for leg in route.get("legs") or []:
        annotation = leg.get("annotation") or {}
        distances.extend(annotation.get("distance") or [])
        durations.extend(annotation.get("duration") or [])
    if len(distances) == len(coords) - 1 and len(durations) == len(coords) - 1:
        miles = [0.0]
        seconds = [0.0]
        for meters, duration in zip(distances, durations):
            miles.append(miles[-1] + float(meters) / 1609.344)
            seconds.append(seconds[-1] + float(duration))
    else:
        miles = cumulative_miles(coords)
        total = miles[-1] or 1
        duration = float(route.get("duration") or 0)
        seconds = [mile / total * duration for mile in miles]
    return RouteGeometry(
        id="",
        label="Driving route",
        coordinates=coords,
        cum_miles=miles,
        cum_seconds=seconds,
        provider="osrm",
    )


def _distinct(routes: list[RouteGeometry]) -> list[RouteGeometry]:
    kept: list[RouteGeometry] = []
    for route in routes:
        if route.distance_miles <= 0 or len(route.coordinates) < 2:
            continue
        if any(_similar(route, existing) for existing in kept):
            continue
        kept.append(route)
    return kept


def _similar(left: RouteGeometry, right: RouteGeometry, samples: int = 14) -> bool:
    if left.distance_miles <= 0 or right.distance_miles <= 0:
        return False
    close = 0
    step = left.distance_miles / samples
    right_samples = []
    right_step = max(right.distance_miles / 30, 1)
    mile = 0.0
    while mile <= right.distance_miles:
        point, _ = interpolate(right.coordinates, right.cum_miles, right.cum_seconds, mile)
        right_samples.append(point)
        mile += right_step
    for index in range(samples + 1):
        point, _ = interpolate(left.coordinates, left.cum_miles, left.cum_seconds, min(left.distance_miles, step * index))
        if any(haversine_miles(point, other) <= 4 for other in right_samples):
            close += 1
    return close / (samples + 1) >= 0.8


def _assign_ids(routes: list[RouteGeometry]) -> None:
    seen: dict[str, int] = {}
    for index, route in enumerate(routes):
        label = route.label.strip() or f"Route {index + 1}"
        count = seen.get(label, 0) + 1
        seen[label] = count
        route.label = label if count == 1 else f"{label} ({count})"
        route.id = f"route-{index + 1}"
