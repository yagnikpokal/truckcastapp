"""Google-style polyline encode/decode. Valhalla shapes use precision 6."""

from __future__ import annotations


def decode_polyline(encoded: str, precision: int = 6) -> list[tuple[float, float]]:
    factor = 10**precision
    coords: list[tuple[float, float]] = []
    index = 0
    lat = 0
    lon = 0
    length = len(encoded)
    while index < length:
        lat_delta, index = _decode_value(encoded, index)
        lon_delta, index = _decode_value(encoded, index)
        lat += lat_delta
        lon += lon_delta
        coords.append((lat / factor, lon / factor))
    return coords


def encode_polyline(coords: list[tuple[float, float]], precision: int = 6) -> str:
    factor = 10**precision
    output: list[str] = []
    prev_lat = 0
    prev_lon = 0
    for lat, lon in coords:
        ilat = int(round(lat * factor))
        ilon = int(round(lon * factor))
        output.append(_encode_value(ilat - prev_lat))
        output.append(_encode_value(ilon - prev_lon))
        prev_lat, prev_lon = ilat, ilon
    return "".join(output)


def _decode_value(encoded: str, index: int) -> tuple[int, int]:
    result = 0
    shift = 0
    while True:
        chunk = ord(encoded[index]) - 63
        index += 1
        result |= (chunk & 0x1F) << shift
        shift += 5
        if chunk < 0x20:
            break
    delta = ~(result >> 1) if result & 1 else result >> 1
    return delta, index


def _encode_value(value: int) -> str:
    value = ~(value << 1) if value < 0 else value << 1
    chunks: list[str] = []
    while value >= 0x20:
        chunks.append(chr((0x20 | (value & 0x1F)) + 63))
        value >>= 5
    chunks.append(chr(value + 63))
    return "".join(chunks)
