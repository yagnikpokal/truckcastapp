"""Weather and load risk for a single checkpoint.

Bands follow the assignment table. A value that sits on a shared boundary
is placed in the higher band. Rain above 1.00 in/hr and snow above 3.0 in/hr
are No Travel, so 1.00 and 3.0 themselves stay Severe. Wind at or above
55 mph is No Travel.

Load rules adjust wind only, and only upward:

- >= 55 mph is No Travel for every load
- 45–54 mph and a load above 30,000 lb is No Travel
- 35–44 mph and a load above 40,000 lb is Severe
"""

from __future__ import annotations

from enum import IntEnum


class Risk(IntEnum):
    LOW = 1
    MODERATE = 2
    HIGH = 3
    SEVERE = 4
    NO_TRAVEL = 5


RISK_LABELS = {
    Risk.LOW: "Low",
    Risk.MODERATE: "Moderate",
    Risk.HIGH: "High",
    Risk.SEVERE: "Severe",
    Risk.NO_TRAVEL: "No Travel",
}

LABEL_TO_RISK = {label: level for level, label in RISK_LABELS.items()}


def label_for(level: Risk) -> str:
    return RISK_LABELS[level]


def classify_wind(mph: float) -> Risk:
    if mph >= 55:
        return Risk.NO_TRAVEL
    if mph >= 45:
        return Risk.SEVERE
    if mph >= 35:
        return Risk.HIGH
    if mph >= 25:
        return Risk.MODERATE
    return Risk.LOW


def classify_rain(inches_per_hour: float) -> Risk:
    if inches_per_hour > 1.0:
        return Risk.NO_TRAVEL
    if inches_per_hour >= 0.50:
        return Risk.SEVERE
    if inches_per_hour >= 0.25:
        return Risk.HIGH
    if inches_per_hour >= 0.10:
        return Risk.MODERATE
    return Risk.LOW


def classify_snow(inches_per_hour: float) -> Risk:
    if inches_per_hour > 3.0:
        return Risk.NO_TRAVEL
    if inches_per_hour >= 2.0:
        return Risk.SEVERE
    if inches_per_hour >= 1.0:
        return Risk.HIGH
    if inches_per_hour >= 0.5:
        return Risk.MODERATE
    return Risk.LOW


def apply_load(wind_mph: float, load_lbs: float, wind_risk: Risk) -> Risk:
    """Raise wind risk when the load makes that wind unsafe."""
    if wind_mph >= 55:
        return Risk.NO_TRAVEL
    if 45 <= wind_mph < 55 and load_lbs > 30_000:
        return Risk.NO_TRAVEL
    if 35 <= wind_mph < 45 and load_lbs > 40_000:
        return max(wind_risk, Risk.SEVERE)
    return wind_risk


def assess_checkpoint(wind_mph: float, rain_in_hr: float, snow_in_hr: float, load_lbs: float) -> dict:
    """Combine wind, rain, and snow. The checkpoint takes the worst level."""
    base_wind = classify_wind(wind_mph)
    wind_risk = apply_load(wind_mph, load_lbs, base_wind)
    rain_risk = classify_rain(rain_in_hr)
    snow_risk = classify_snow(snow_in_hr)
    overall = max(wind_risk, rain_risk, snow_risk)
    drivers = []
    if wind_risk == overall:
        drivers.append("wind")
    if rain_risk == overall:
        drivers.append("rain")
    if snow_risk == overall:
        drivers.append("snow")
    return {
        "risk": label_for(overall),
        "risk_score": int(overall),
        "wind_risk": label_for(wind_risk),
        "rain_risk": label_for(rain_risk),
        "snow_risk": label_for(snow_risk),
        "drivers": drivers,
        "load_adjusted": wind_risk != base_wind,
    }


def worse_label(left: str, right: str) -> str:
    left_level = LABEL_TO_RISK[left]
    right_level = LABEL_TO_RISK[right]
    return label_for(max(left_level, right_level))
