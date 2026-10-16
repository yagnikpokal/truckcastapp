"""Hourly wind, rain, and snow from Open-Meteo, keyed by snapped coordinate."""

from __future__ import annotations

import os
from datetime import datetime, timezone

from routing.services.errors import UpstreamError
from routing.services.http import TTLCache, request_json

OPEN_METEO_URL = os.environ.get("OPEN_METEO_URL", "https://api.open-meteo.com/v1/forecast")
_CACHE = TTLCache(max_items=4000, ttl_seconds=20 * 60)


def snap(lat: float, lon: float) -> tuple[float, float]:
    """~0.7 mile cells. Checkpoints are much farther apart than this."""
    return (round(lat, 2), round(lon, 2))


class ForecastTable:
    """Hourly series for a set of cells. `at()` picks the hour nearest an ETA."""

    def __init__(self, series_by_cell: dict[tuple[float, float], dict]):
        self.series_by_cell = series_by_cell

    def at(self, lat: float, lon: float, eta: datetime) -> dict:
        cell = snap(lat, lon)
        series = self.series_by_cell.get(cell)
        if not series:
            return _empty(True)
        index, clamped = nearest_hour(series["times"], eta)
        wind = series["wind"][index]
        rain = series["rain"][index]
        snow = series["snow"][index]
        missing = wind is None and rain is None and snow is None
        return {
            "wind_mph": _number(wind),
            "rain_in_hr": _number(rain),
            "snow_in_hr": _number(snow),
            "forecast_time": series["times"][index].isoformat(),
            "clamped": clamped or missing,
        }


def load_forecast(points: list[tuple[float, float]], start: datetime, hours: int = 56) -> ForecastTable:
    cells = []
    seen = set()
    for lat, lon in points:
        cell = snap(lat, lon)
        if cell in seen:
            continue
        seen.add(cell)
        cells.append(cell)
    series: dict[tuple[float, float], dict] = {}
    missing = []
    for cell in cells:
        cached = _CACHE.get(("wx", cell, hours))
        if cached is not None:
            series[cell] = cached
        else:
            missing.append(cell)
    if missing:
        fetched = _fetch_cells(missing, start, hours)
        for cell, payload in fetched.items():
            _CACHE.set(("wx", cell, hours), payload)
            series[cell] = payload
    return ForecastTable(series)


def nearest_hour(times: list[datetime], eta: datetime) -> tuple[int, bool]:
    if not times:
        return 0, True
    target = _as_utc(eta)
    best = 0
    best_delta = abs((_as_utc(times[0]) - target).total_seconds())
    for index, moment in enumerate(times[1:], start=1):
        delta = abs((_as_utc(moment) - target).total_seconds())
        if delta < best_delta:
            best = index
            best_delta = delta
    # More than 90 minutes away means the forecast does not really cover this ETA.
    return best, best_delta > 90 * 60


def _fetch_cells(cells: list[tuple[float, float]], start: datetime, hours: int) -> dict[tuple[float, float], dict]:
    found: dict[tuple[float, float], dict] = {}
    days = _forecast_days(start, hours)
    for batch in _batches(cells, 80):
        params = {
            "latitude": ",".join(str(lat) for lat, _ in batch),
            "longitude": ",".join(str(lon) for _, lon in batch),
            "hourly": "wind_speed_10m,rain,snowfall",
            "wind_speed_unit": "mph",
            "precipitation_unit": "inch",
            "timezone": "UTC",
            "forecast_days": days,
        }
        payload = request_json("GET", OPEN_METEO_URL, params=params, timeout=40)
        records = payload if isinstance(payload, list) else [payload]
        if len(records) != len(batch):
            raise UpstreamMismatch(len(batch), len(records))
        for cell, record in zip(batch, records):
            found[cell] = _parse_record(record)
    return found


class UpstreamMismatch(UpstreamError):
    def __init__(self, expected: int, actual: int):
        super().__init__(f"Weather service returned {actual} locations for {expected} requested.")


def _parse_record(record: dict) -> dict:
    hourly = record.get("hourly") or {}
    times = []
    for stamp in hourly.get("time") or []:
        times.append(datetime.fromisoformat(stamp).replace(tzinfo=timezone.utc))
    return {
        "times": times,
        "wind": list(hourly.get("wind_speed_10m") or []),
        "rain": list(hourly.get("rain") or []),
        "snow": list(hourly.get("snowfall") or []),
    }


def _forecast_days(start: datetime, hours: int) -> int:
    end = _as_utc(start).timestamp() + hours * 3600
    now = datetime.now(timezone.utc).timestamp()
    days = int((end - now) / 86400) + 2
    return min(16, max(2, days))


def _batches(items: list, size: int):
    for index in range(0, len(items), size):
        yield items[index : index + size]


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _number(value) -> float:
    if value is None:
        return 0.0
    return float(value)


def _empty(clamped: bool) -> dict:
    return {
        "wind_mph": 0.0,
        "rain_in_hr": 0.0,
        "snow_in_hr": 0.0,
        "forecast_time": None,
        "clamped": clamped,
    }
