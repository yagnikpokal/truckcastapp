from datetime import datetime, timedelta, timezone

from django.test import SimpleTestCase, TestCase

from routing.services.geo import haversine_miles, simplify
from routing.services.heatmap import corridor_points
from routing.services.polyline import decode_polyline, encode_polyline
from routing.services.recommend import rank_routes
from routing.services.risk import assess_checkpoint, classify_rain, classify_snow, classify_wind
from routing.services.routing_api import RouteGeometry, time_along_shape
from routing.services.sampling import (
    build_segments,
    checkpoint_miles,
    sample_checkpoints,
    score_checkpoints,
    summarize,
)
from routing.services.weather import nearest_hour


class RiskBandTests(SimpleTestCase):
    def test_wind_bands(self):
        self.assertEqual(classify_wind(24.9).name, "LOW")
        self.assertEqual(classify_wind(25).name, "MODERATE")
        self.assertEqual(classify_wind(34.9).name, "MODERATE")
        self.assertEqual(classify_wind(35).name, "HIGH")
        self.assertEqual(classify_wind(44.9).name, "HIGH")
        self.assertEqual(classify_wind(45).name, "SEVERE")
        self.assertEqual(classify_wind(54.9).name, "SEVERE")
        self.assertEqual(classify_wind(55).name, "NO_TRAVEL")

    def test_rain_bands_keep_the_written_no_travel_cutoff(self):
        self.assertEqual(classify_rain(0.09).name, "LOW")
        self.assertEqual(classify_rain(0.10).name, "MODERATE")
        self.assertEqual(classify_rain(0.25).name, "HIGH")
        self.assertEqual(classify_rain(0.50).name, "SEVERE")
        self.assertEqual(classify_rain(1.0).name, "SEVERE")
        self.assertEqual(classify_rain(1.01).name, "NO_TRAVEL")

    def test_snow_bands_keep_the_written_no_travel_cutoff(self):
        self.assertEqual(classify_snow(0.49).name, "LOW")
        self.assertEqual(classify_snow(0.5).name, "MODERATE")
        self.assertEqual(classify_snow(1.0).name, "HIGH")
        self.assertEqual(classify_snow(2.0).name, "SEVERE")
        self.assertEqual(classify_snow(3.0).name, "SEVERE")
        self.assertEqual(classify_snow(3.01).name, "NO_TRAVEL")

    def test_load_rules_only_raise_wind_risk(self):
        light = assess_checkpoint(50, 0, 0, 30_000)
        self.assertEqual(light["risk"], "Severe")
        self.assertFalse(light["load_adjusted"])

        heavy_wind = assess_checkpoint(50, 0, 0, 30_001)
        self.assertEqual(heavy_wind["risk"], "No Travel")
        self.assertTrue(heavy_wind["load_adjusted"])

        at_forty = assess_checkpoint(40, 0, 0, 40_000)
        self.assertEqual(at_forty["risk"], "High")

        over_forty = assess_checkpoint(40, 0, 0, 40_001)
        self.assertEqual(over_forty["risk"], "Severe")
        self.assertTrue(over_forty["load_adjusted"])

        any_load = assess_checkpoint(55, 0, 0, 1_000)
        self.assertEqual(any_load["risk"], "No Travel")

        below_band = assess_checkpoint(34, 0, 0, 80_000)
        self.assertEqual(below_band["risk"], "Moderate")
        self.assertFalse(below_band["load_adjusted"])

    def test_checkpoint_uses_the_worst_hazard(self):
        scored = assess_checkpoint(10, 0.8, 0.1, 10_000)
        self.assertEqual(scored["risk"], "Severe")
        self.assertEqual(scored["drivers"], ["rain"])
        self.assertEqual(scored["wind_risk"], "Low")


class RankingTests(SimpleTestCase):
    def test_preference_order(self):
        routes = [
            _route("fast-severe", severe=20, high=0, average=3.2, seconds=3 * 3600),
            _route("calm-long", severe=0, high=5, average=1.4, seconds=5 * 3600),
            _route("no-travel", severe=0, high=0, average=2, seconds=2 * 3600, no_travel=15),
            _route("tied-weather-faster", severe=0, high=5, average=1.4, seconds=4 * 3600),
        ]
        ranked = rank_routes(routes)
        self.assertEqual(
            [route["id"] for route in ranked],
            ["tied-weather-faster", "calm-long", "fast-severe", "no-travel"],
        )
        self.assertTrue(ranked[0]["is_recommended"])
        self.assertIn("Shortest travel time", ranked[0]["decision"])
        self.assertIsNone(ranked[1]["decision"])

    def test_each_key_can_decide_the_ranking(self):
        no_travel = rank_routes(
            [
                _route("exposed", severe=30, high=0, average=4, seconds=1000, no_travel=0),
                _route("closed", severe=0, high=0, average=1, seconds=1000, no_travel=8),
            ]
        )
        self.assertEqual(no_travel[0]["id"], "exposed")
        self.assertIn("no-travel", no_travel[0]["decision"])

        severe = rank_routes(
            [
                _route("storm", severe=12, high=0, average=1, seconds=1000),
                _route("edge", severe=2, high=40, average=3, seconds=5000),
            ]
        )
        self.assertEqual(severe[0]["id"], "edge")
        self.assertIn("severe", severe[0]["decision"])

        high = rank_routes(
            [
                _route("gusts", severe=0, high=18, average=1.2, seconds=1000),
                _route("cleaner", severe=0, high=4, average=2.2, seconds=4000),
            ]
        )
        self.assertEqual(high[0]["id"], "cleaner")
        self.assertIn("high miles", high[0]["decision"])

    def test_average_risk_breaks_a_mile_tie(self):
        routes = [
            _route("gusty", severe=0, high=10, average=2.4, seconds=1000),
            _route("steadier", severe=0, high=10, average=1.6, seconds=1400),
        ]
        ranked = rank_routes(routes)
        self.assertEqual(ranked[0]["id"], "steadier")
        self.assertIn("average risk", ranked[0]["decision"])

    def test_shortest_time_wins_when_weather_matches(self):
        routes = [
            _route("slow", severe=0, high=0, average=1, seconds=5000),
            _route("fast", severe=0, high=0, average=1, seconds=4000),
        ]
        ranked = rank_routes(routes)
        self.assertEqual(ranked[0]["id"], "fast")
        self.assertIn("travel time", ranked[0]["decision"])

    def test_no_travel_warning(self):
        ranked = rank_routes([_route("only", severe=0, high=0, average=5, seconds=100, no_travel=4)])
        self.assertIn("No Travel", ranked[0]["warning"])


class SamplingTests(SimpleTestCase):
    def test_checkpoint_spacing_includes_both_ends(self):
        self.assertEqual(checkpoint_miles(100, 25), [0, 25, 50, 75, 100])
        self.assertEqual(checkpoint_miles(30, 25), [0, 25, 30])
        self.assertEqual(checkpoint_miles(10.4, 10), [0, 10.4])

    def test_segment_miles_use_the_worse_endpoint(self):
        departure = datetime(2026, 10, 16, 12, tzinfo=timezone.utc)
        route = _eastbound(hours=2, miles=50)
        checkpoints = sample_checkpoints(
            route.coordinates, route.cum_miles, route.cum_seconds, 25, departure
        )

        midpoint = route.coordinates[len(route.coordinates) // 2][1]

        def weather_at(lat, lon, eta):
            wind = 50 if lon >= midpoint else 5
            return {"wind_mph": wind, "rain_in_hr": 0, "snow_in_hr": 0, "forecast_time": eta.isoformat(), "clamped": False}

        scored = score_checkpoints(checkpoints, 10_000, weather_at)
        segments = build_segments(scored, route.coordinates, route.cum_miles)
        stats = summarize(segments, scored)
        self.assertGreater(stats["severe_miles"], 0)
        self.assertAlmostEqual(stats["distance_miles"], route.distance_miles, delta=0.2)
        self.assertAlmostEqual(sum(segment["miles"] for segment in segments), stats["distance_miles"], delta=0.05)
        # The leg that touches the windy end is Severe, even if it started in calm air.
        self.assertEqual(segments[-1]["risk"], "Severe")

    def test_pipeline_prefers_the_calm_route_over_a_faster_gale(self):
        departure = datetime(2026, 10, 16, 12, tzinfo=timezone.utc)
        fast = _eastbound(hours=3, miles=100, label="Fast gale")
        calm = _eastbound(hours=4, miles=120, label="Calm", lat=42)
        built = []
        for route, wind in ((fast, 60), (calm, 8)):
            checkpoints = sample_checkpoints(route.coordinates, route.cum_miles, route.cum_seconds, 25, departure)
            scored = score_checkpoints(
                checkpoints,
                20_000,
                lambda lat, lon, eta, wind=wind: {
                    "wind_mph": wind,
                    "rain_in_hr": 0,
                    "snow_in_hr": 0,
                    "forecast_time": eta.isoformat(),
                    "clamped": False,
                },
            )
            segments = build_segments(scored, route.coordinates, route.cum_miles)
            built.append(
                {
                    "id": route.label,
                    "duration_seconds": route.duration_seconds,
                    "stats": summarize(segments, scored),
                }
            )
        ranked = rank_routes(built)
        self.assertEqual(ranked[0]["id"], "Calm")
        self.assertGreater(ranked[1]["stats"]["no_travel_miles"], 0)


class GeometryTests(SimpleTestCase):
    def test_polyline_roundtrip(self):
        coords = [(41.8781, -87.6298), (41.9, -87.7), (42.0, -88.0)]
        self.assertEqual(decode_polyline(encode_polyline(coords, 6), 6), coords)

    def test_known_precision_five_vector(self):
        encoded = "_p~iF~ps|U_ulLnnqC_mqNvxq`@"
        decoded = decode_polyline(encoded, precision=5)
        self.assertAlmostEqual(decoded[0][0], 38.5, places=5)
        self.assertAlmostEqual(decoded[0][1], -120.2, places=5)
        self.assertAlmostEqual(decoded[-1][0], 43.252, places=3)

    def test_maneuver_time_is_spread_by_distance(self):
        coords = [(0, 0), (0, 0.1), (0, 0.2)]
        maneuvers = [{"begin_shape_index": 0, "end_shape_index": 2, "time": 100, "length": 10}]
        miles, seconds = time_along_shape(coords, maneuvers)
        self.assertAlmostEqual(seconds[0], 0, places=5)
        self.assertAlmostEqual(seconds[1], 50, delta=1)
        self.assertAlmostEqual(seconds[-1], 100, delta=1)
        self.assertGreater(miles[-1], 0)

    def test_one_degree_of_latitude_is_about_69_miles(self):
        self.assertAlmostEqual(haversine_miles((40, -90), (41, -90)), 69.1, delta=0.2)

    def test_straight_line_simplifies_to_its_ends(self):
        points = [(40 + index * 0.01, -90) for index in range(20)]
        simplified = simplify(points, 0.0001)
        self.assertEqual(simplified[0], points[0])
        self.assertEqual(simplified[-1], points[-1])
        self.assertLess(len(simplified), 5)

    def test_corridor_stays_bounded_for_a_long_line(self):
        line = [(40, -100 + index * 0.5) for index in range(30)]
        points = corridor_points([line, line], target=60)
        self.assertGreater(len(points), 5)
        self.assertLessEqual(len(points), 220)

    def test_nearest_hour_clamps_when_the_forecast_does_not_cover_the_eta(self):
        start = datetime(2026, 10, 16, tzinfo=timezone.utc)
        times = [start + timedelta(hours=offset) for offset in range(4)]
        index, clamped = nearest_hour(times, start + timedelta(minutes=70))
        self.assertEqual(index, 1)
        self.assertFalse(clamped)
        _, far = nearest_hour(times, start + timedelta(hours=10))
        self.assertTrue(far)


class ApiValidationTests(TestCase):
    def test_health(self):
        response = self.client.get("/api/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ok")

    def test_analyze_rejects_a_bad_interval(self):
        response = self.client.post(
            "/api/analyze",
            data={
                "origin": "Chicago, IL",
                "destination": "Detroit, MI",
                "departure": "2026-10-16T08:00",
                "timezone": "America/Chicago",
                "load_lbs": 35000,
                "sample_miles": 12,
            },
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("10, 25, or 50", response.json()["error"])

    def test_analyze_rejects_a_non_positive_load(self):
        response = self.client.post(
            "/api/analyze",
            data={
                "origin": {"label": "A", "lat": 41.8, "lon": -87.6},
                "destination": {"label": "B", "lat": 39.7, "lon": -86.1},
                "departure": "2026-10-16T08:00",
                "timezone": "America/Chicago",
                "load_lbs": 0,
                "sample_miles": 25,
            },
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)


def _route(name, severe, high, average, seconds, no_travel=0):
    return {
        "id": name,
        "duration_seconds": seconds,
        "stats": {
            "no_travel_miles": no_travel,
            "severe_miles": severe,
            "high_miles": high,
            "average_risk": average,
        },
    }


def _eastbound(hours: float, miles: float, label: str = "East", lat: float = 41.0) -> RouteGeometry:
    # 1 degree longitude at lat 41 is about 52.6 miles. Step in longitude to cover `miles`.
    miles_per_degree = haversine_miles((lat, -90), (lat, -89))
    span = miles / miles_per_degree
    steps = 11
    coords = []
    for index in range(steps):
        frac = index / (steps - 1)
        coords.append((lat, -90 + span * frac))
    cum = [0.0]
    for index in range(1, steps):
        cum.append(cum[-1] + haversine_miles(coords[index - 1], coords[index]))
    total = cum[-1] or 1
    seconds = [mile / total * hours * 3600 for mile in cum]
    return RouteGeometry(id=label, label=label, coordinates=coords, cum_miles=cum, cum_seconds=seconds, provider="test")
