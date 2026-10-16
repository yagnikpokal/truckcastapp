"""Pick the route that keeps the truck out of the worst weather.

No Travel sits above Severe on the scale, so those miles are compared first.
After that the order is the one in the assignment:

1. Fewest Severe miles
2. Fewest High miles
3. Lowest average risk (mile-weighted)
4. Shortest travel time
"""

from __future__ import annotations


def sort_key(route: dict) -> tuple:
    stats = route["stats"]
    return (
        round(float(stats["no_travel_miles"]), 2),
        round(float(stats["severe_miles"]), 2),
        round(float(stats["high_miles"]), 2),
        round(float(stats["average_risk"]), 3),
        int(round(float(route["duration_seconds"]))),
    )


def rank_routes(routes: list[dict]) -> list[dict]:
    ordered = sorted(routes, key=sort_key)
    for index, route in enumerate(ordered):
        route["rank"] = index + 1
        route["is_recommended"] = index == 0
        route["decision"] = None
        route["warning"] = None
    if ordered:
        ordered[0]["decision"] = deciding_factor(ordered[0], ordered[1:])
        ordered[0]["warning"] = warning_for(ordered[0]["stats"])
    return ordered


def deciding_factor(winner: dict, others: list[dict]) -> str:
    """Explain the first sort key that separates the winner from the runner-up.

    `others` is the rest of the field in rank order, so the runner-up is first.
    Comparing only with that route matches the lexicographic order: a route that
    already lost on an earlier key is not allowed to steal a later one.
    """
    if not others:
        return "Only drivable option returned for this trip."
    runner = others[0]
    comparisons = (
        ("no_travel_miles", "Fewest no-travel miles", _miles),
        ("severe_miles", "Fewest severe miles", _miles),
        ("high_miles", "Fewest high miles", _miles),
        ("average_risk", "Lowest average risk", lambda value: f"{float(value):.2f}"),
        ("duration_seconds", "Shortest travel time", _minutes),
    )
    for key, label, fmt in comparisons:
        winner_value = _value(winner, key)
        runner_value = _value(runner, key)
        if winner_value < runner_value - 1e-9:
            return f"{label} ({fmt(winner_value)} vs {fmt(runner_value)})."
    return "Tied on weather and travel time."


def warning_for(stats: dict) -> str | None:
    if stats["no_travel_miles"] > 0:
        return (
            "This is the safest option, and it still crosses No Travel weather. "
            "Delay the departure or wait for a calmer window."
        )
    if stats["severe_miles"] > 0:
        return "This is the safest option, and it still includes Severe miles. Review those checkpoints before rolling."
    return None


def _value(route: dict, key: str) -> float:
    if key == "duration_seconds":
        return float(route["duration_seconds"])
    return float(route["stats"][key])


def _miles(value: float) -> str:
    return f"{value:.0f} mi" if value >= 10 else f"{value:.1f} mi"


def _minutes(seconds: float) -> str:
    minutes = int(round(seconds / 60))
    hours, mins = divmod(minutes, 60)
    if hours <= 0:
        return f"{mins} min"
    return f"{hours} h {mins} min"
