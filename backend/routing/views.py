"""JSON endpoints for geocoding, route analysis, and the corridor forecast."""

from __future__ import annotations

import json
import logging

from django.http import FileResponse, HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from routing.services.analyze import analyze_trip
from routing.services.errors import UpstreamError, UserError
from routing.services.geocode import search_places
from routing.services.heatmap import build_heatmap
from routing.services.analyze import _parse_departure, _parse_load

logger = logging.getLogger(__name__)


def health(request):
    return JsonResponse({"status": "ok"})


@require_GET
def geocode(request):
    query = request.GET.get("q", "")
    try:
        places = search_places(query, limit=5)
    except UserError as exc:
        return _error(400, str(exc))
    except UpstreamError as exc:
        return _error(502, str(exc))
    return JsonResponse({"results": [place.as_dict() for place in places]})


@csrf_exempt
@require_POST
def analyze(request):
    try:
        body = _body(request)
        result = analyze_trip(
            origin=body.get("origin"),
            destination=body.get("destination"),
            departure=body.get("departure"),
            timezone_name=str(body.get("timezone") or "UTC"),
            load_lbs=body.get("load_lbs"),
            sample_miles=body.get("sample_miles"),
        )
    except UserError as exc:
        return _error(400, str(exc))
    except UpstreamError as exc:
        logger.warning("analyze upstream failure: %s", exc)
        return _error(502, str(exc))
    except Exception:
        logger.exception("analyze failed")
        return _error(500, "Something went wrong while planning the trip.")
    return JsonResponse(result)


@csrf_exempt
@require_POST
def heatmap(request):
    try:
        body = _body(request)
        load = _parse_load(body.get("load_lbs"))
        departure = _parse_departure(body.get("departure"), str(body.get("timezone") or "UTC"))
        polylines = _polylines(body.get("routes"))
        result = build_heatmap(polylines, departure, load)
    except UserError as exc:
        return _error(400, str(exc))
    except UpstreamError as exc:
        logger.warning("heatmap upstream failure: %s", exc)
        return _error(502, str(exc))
    except Exception:
        logger.exception("heatmap failed")
        return _error(500, "The corridor forecast could not be built.")
    return JsonResponse(result)


def spa_index(request):
    from django.conf import settings

    index = settings.FRONTEND_DIST / "index.html"
    if not index.is_file():
        return HttpResponse(
            "Frontend is not built yet. From the frontend folder run npm install and npm run build, "
            "or use the Vite dev server on port 5173.",
            status=503,
            content_type="text/plain",
        )
    return FileResponse(index.open("rb"))


def _polylines(routes) -> list[list[tuple[float, float]]]:
    if not isinstance(routes, list) or not routes:
        raise UserError("Heatmap needs the planned routes.")
    lines = []
    for route in routes[:3]:
        if not isinstance(route, dict):
            continue
        coords = route.get("coordinates") or []
        line = []
        if not isinstance(coords, list):
            continue
        for pair in coords[:5000]:
            if not isinstance(pair, (list, tuple)) or len(pair) < 2:
                continue
            try:
                lat = float(pair[0])
                lon = float(pair[1])
            except (TypeError, ValueError) as exc:
                raise UserError("A route coordinate was not a number.") from exc
            if not -90 <= lat <= 90 or not -180 <= lon <= 180:
                raise UserError("A route coordinate is out of range.")
            line.append((lat, lon))
        if len(line) >= 2:
            lines.append(line)
    if not lines:
        raise UserError("Heatmap needs the planned routes.")
    return lines


def _body(request) -> dict:
    try:
        body = json.loads(request.body.decode() or "{}")
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise UserError("Request body must be JSON.") from exc
    if not isinstance(body, dict):
        raise UserError("Request body must be a JSON object.")
    return body


def _error(status: int, message: str) -> JsonResponse:
    return JsonResponse({"error": message}, status=status)
