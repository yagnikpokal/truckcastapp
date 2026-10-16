"""Timed HTTP helpers and a small in-process cache for forecast cells."""

from __future__ import annotations

import time
from urllib.parse import urlparse

import requests

from routing.services.errors import UpstreamError

SESSION = requests.Session()
SESSION.headers["User-Agent"] = "truckcast/1.0 (weather-aware truck routing; educational)"


class TTLCache:
    def __init__(self, max_items: int = 4000, ttl_seconds: int = 1800):
        self.max_items = max_items
        self.ttl = ttl_seconds
        self._store: dict = {}

    def get(self, key):
        item = self._store.get(key)
        if not item:
            return None
        stored_at, value = item
        if time.time() - stored_at > self.ttl:
            self._store.pop(key, None)
            return None
        return value

    def set(self, key, value):
        if len(self._store) >= self.max_items:
            oldest = min(self._store, key=lambda item: self._store[item][0])
            self._store.pop(oldest, None)
        self._store[key] = (time.time(), value)


def request_json(method: str, url: str, *, timeout: float = 25, **kwargs):
    last_error: Exception | None = None
    for attempt in range(2):
        try:
            response = SESSION.request(method, url, timeout=timeout, **kwargs)
        except requests.RequestException as exc:
            last_error = exc
            if attempt == 0:
                time.sleep(0.4)
                continue
            host = urlparse(url).netloc or "the map service"
            raise UpstreamError(f"Could not reach {host}. Try again in a moment.") from exc
        if response.status_code in {429, 502, 503, 504} and attempt == 0:
            time.sleep(0.7)
            continue
        if response.status_code >= 400:
            raise UpstreamError(_safe_upstream_message(response))
        try:
            return response.json()
        except ValueError as exc:
            host = urlparse(url).netloc or "the map service"
            raise UpstreamError(f"{host} returned an unreadable response.") from exc
    host = urlparse(url).netloc or "the map service"
    raise UpstreamError(f"{host} is busy. Try again in a moment.") from last_error


def _safe_upstream_message(response: requests.Response) -> str:
    host = urlparse(response.url).netloc or "the map service"
    detail = ""
    try:
        body = response.json()
    except ValueError:
        body = None
    if isinstance(body, dict):
        raw = body.get("error") or body.get("reason") or body.get("message")
        if isinstance(raw, str):
            detail = " ".join(raw.split())[:180]
    if detail:
        return f"{host}: {detail}"
    return f"{host} returned status {response.status_code}."
