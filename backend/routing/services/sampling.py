"""Place a checkpoint every N miles and score the miles between them."""

from __future__ import annotations

from datetime import datetime, timedelta

from routing.services.geo import interpolate, simplify, slice_line
from routing.services.risk import LABEL_TO_RISK, Risk, assess_checkpoint, label_for, worse_label

SAMPLE_MILES = (10, 25, 50)


def checkpoint_miles(total_miles: float, interval: float) -> list[float]:
    """Origin, every `interval` miles, and the destination.

    A sample that would fall within a mile of the destination is dropped so the
    last two checkpoints are not stacked on top of each other.
    """
    if total_miles <= 0:
        return [0.0]
    miles = [0.0]
    cursor = float(interval)
    # Keep the destination, and skip a sample that would land within a mile of it.
    while cursor < total_miles - 1:
        miles.append(cursor)
        cursor += interval
    if total_miles - miles[-1] > 1e-6:
        miles.append(total_miles)
    return miles


def sample_checkpoints(
    coords: list[tuple[float, float]],
    cum_miles: list[float],
    cum_seconds: list[float],
    interval: float,
    departure: datetime,
) -> list[dict]:
    total = cum_miles[-1] if cum_miles else 0.0
    checkpoints = []
    for mile in checkpoint_miles(total, interval):
        (lat, lon), elapsed = interpolate(coords, cum_miles, cum_seconds, mile)
        eta = departure + timedelta(seconds=elapsed)
        checkpoints.append(
            {
                "mile": round(mile, 3),
                "lat": lat,
                "lon": lon,
                "elapsed_seconds": round(elapsed, 1),
                "eta": eta,
            }
        )
    return checkpoints


def score_checkpoints(checkpoints: list[dict], load_lbs: float, weather_at) -> list[dict]:
    scored = []
    for index, checkpoint in enumerate(checkpoints):
        weather = weather_at(checkpoint["lat"], checkpoint["lon"], checkpoint["eta"])
        risk = assess_checkpoint(
            weather["wind_mph"],
            weather["rain_in_hr"],
            weather["snow_in_hr"],
            load_lbs,
        )
        scored.append(
            {
                "index": index,
                "mile": checkpoint["mile"],
                "lat": round(checkpoint["lat"], 5),
                "lon": round(checkpoint["lon"], 5),
                "eta": checkpoint["eta"].isoformat(),
                "elapsed_seconds": checkpoint["elapsed_seconds"],
                "wind_mph": round(weather["wind_mph"], 1),
                "rain_in_hr": round(weather["rain_in_hr"], 3),
                "snow_in_hr": round(weather["snow_in_hr"], 3),
                "forecast_time": weather.get("forecast_time"),
                "forecast_clamped": bool(weather.get("clamped")),
                **risk,
            }
        )
    return scored


def build_segments(
    checkpoints: list[dict],
    coords: list[tuple[float, float]],
    cum_miles: list[float],
) -> list[dict]:
    """Each leg takes the worse risk of its two endpoints.

    Miles are the distance the truck drives while approaching the next
    checkpoint, so a severe arrival colors the miles leading into it as well
    as the miles leaving a severe origin.
    """
    segments = []
    for index in range(len(checkpoints) - 1):
        start = checkpoints[index]
        end = checkpoints[index + 1]
        risk = worse_label(start["risk"], end["risk"])
        line = slice_line(coords, cum_miles, start["mile"], end["mile"])
        line = simplify(line)
        segments.append(
            {
                "start_mile": start["mile"],
                "end_mile": end["mile"],
                "miles": round(end["mile"] - start["mile"], 3),
                "risk": risk,
                "risk_score": int(LABEL_TO_RISK[risk]),
                "coordinates": [[round(lat, 5), round(lon, 5)] for lat, lon in line],
            }
        )
    return segments


def summarize(segments: list[dict], checkpoints: list[dict]) -> dict:
    buckets = {"Low": 0.0, "Moderate": 0.0, "High": 0.0, "Severe": 0.0, "No Travel": 0.0}
    weighted = 0.0
    total = 0.0
    for segment in segments:
        miles = float(segment["miles"])
        buckets[segment["risk"]] += miles
        weighted += segment["risk_score"] * miles
        total += miles
    if total <= 0 and checkpoints:
        # A zero-length trip still has a risk at the origin.
        score = checkpoints[0]["risk_score"]
        return {
            "low_miles": 0.0,
            "moderate_miles": 0.0,
            "high_miles": 0.0,
            "severe_miles": 0.0,
            "no_travel_miles": 0.0,
            "average_risk": float(score),
            "distance_miles": 0.0,
        }
    average = weighted / total if total else 0.0
    return {
        "low_miles": round(buckets["Low"], 2),
        "moderate_miles": round(buckets["Moderate"], 2),
        "high_miles": round(buckets["High"], 2),
        "severe_miles": round(buckets["Severe"], 2),
        "no_travel_miles": round(buckets["No Travel"], 2),
        "average_risk": round(average, 3),
        "distance_miles": round(total, 2),
    }


def worst_checkpoint(checkpoints: list[dict]) -> dict | None:
    if not checkpoints:
        return None
    worst = max(checkpoints, key=lambda item: (item["risk_score"], item["mile"]))
    return {"mile": worst["mile"], "risk": worst["risk"], "eta": worst["eta"]}


def average_label(score: float) -> str:
    rounded = min(5, max(1, int(round(score))))
    return label_for(Risk(rounded))
