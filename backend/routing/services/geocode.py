"""Geocoding via Photon, with Nominatim as a fallback. Coordinates can be typed directly."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass

from routing.services.errors import UpstreamError, UserError
from routing.services.http import TTLCache, request_json

PHOTON_URL = os.environ.get("PHOTON_URL", "https://photon.komoot.io/api/")
NOMINATIM_URL = os.environ.get("NOMINATIM_URL", "https://nominatim.openstreetmap.org/search")
_CACHE = TTLCache(max_items=500, ttl_seconds=60 * 60 * 24)
_COORD = re.compile(r"^\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*$")


@dataclass(frozen=True)
class Place:
    label: str
    lat: float
    lon: float

    def as_dict(self) -> dict:
        return {"label": self.label, "lat": self.lat, "lon": self.lon}


def search_places(query: str, limit: int = 5) -> list[Place]:
    text = _clean_query(query)
    cached = _CACHE.get(("search", text, limit))
    if cached is not None:
        return cached
    try:
        places = _photon(text, limit)
    except UpstreamError:
        places = []
    if not places:
        places = _nominatim(text, limit)
    _CACHE.set(("search", text, limit), places)
    return places


def resolve_place(value) -> Place:
    """Accept a geocoder selection `{label, lat, lon}` or a free-text query."""
    if isinstance(value, dict):
        try:
            lat = float(value["lat"])
            lon = float(value["lon"])
        except (KeyError, TypeError, ValueError) as exc:
            raise UserError("Choose an origin and destination from the suggestions.") from exc
        _check_coordinate(lat, lon)
        label = str(value.get("label") or f"{lat:.4f}, {lon:.4f}").strip()
        return Place(label=label[:180], lat=lat, lon=lon)
    if not isinstance(value, str):
        raise UserError("Origin and destination must be places or coordinates.")
    text = value.strip()
    parsed = _parse_coordinates(text)
    if parsed:
        return parsed
    matches = search_places(text, limit=1)
    if not matches:
        raise UserError(f"No location found for “{text[:80]}”.")
    return matches[0]


def _photon(query: str, limit: int) -> list[Place]:
    payload = request_json("GET", PHOTON_URL, params={"q": query, "limit": limit, "lang": "en"}, timeout=12)
    places = []
    for feature in payload.get("features") or []:
        geometry = feature.get("geometry") or {}
        coords = geometry.get("coordinates") or []
        if len(coords) < 2:
            continue
        lon, lat = float(coords[0]), float(coords[1])
        label = _photon_label(feature.get("properties") or {})
        if label:
            places.append(Place(label=label, lat=lat, lon=lon))
    return places


def _nominatim(query: str, limit: int) -> list[Place]:
    payload = request_json(
        "GET",
        NOMINATIM_URL,
        params={"q": query, "format": "jsonv2", "limit": limit, "addressdetails": 1},
        timeout=12,
    )
    places = []
    for item in payload if isinstance(payload, list) else []:
        label = item.get("display_name")
        if not label:
            continue
        places.append(Place(label=label, lat=float(item["lat"]), lon=float(item["lon"])))
    return places


def _photon_label(props: dict) -> str:
    name = props.get("name") or props.get("street") or ""
    parts = [name]
    for key in ("city", "state", "country"):
        value = props.get(key)
        if value and value not in parts:
            parts.append(value)
    label = ", ".join(part for part in parts if part)
    return label[:180]


def _clean_query(query: str) -> str:
    text = " ".join(str(query).split())
    if len(text) < 2:
        raise UserError("Enter at least two characters to search.")
    if len(text) > 180:
        raise UserError("That place name is too long.")
    return text


def _parse_coordinates(text: str) -> Place | None:
    match = _COORD.match(text)
    if not match:
        return None
    lat, lon = float(match.group(1)), float(match.group(2))
    _check_coordinate(lat, lon)
    return Place(label=f"{lat:.4f}, {lon:.4f}", lat=lat, lon=lon)


def _check_coordinate(lat: float, lon: float) -> None:
    if not -90 <= lat <= 90 or not -180 <= lon <= 180:
        raise UserError("Coordinates are out of range. Use latitude, longitude.")
