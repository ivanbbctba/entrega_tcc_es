"""Geospatial helpers.

Provides geohash_from_latlng suitable for clustering/search. Implementation
is a simple pure-Python geohash encoder.
"""
from __future__ import annotations

from typing import Tuple

_BASE32 = "0123456789bcdefghjkmnpqrstuvwxyz"


def geohash_from_latlng(lat: float, lng: float, precision: int = 10) -> str:
    """Encode latitude/longitude into a geohash string.

    Args:
        lat: latitude in degrees
        lng: longitude in degrees
        precision: number of characters in resulting geohash
    """
    lat_interval = [-90.0, 90.0]
    lon_interval = [-180.0, 180.0]
    geohash = []
    bits = [16, 8, 4, 2, 1]
    bit = 0
    ch = 0
    even = True

    while len(geohash) < precision:
        if even:
            mid = (lon_interval[0] + lon_interval[1]) / 2
            if lng > mid:
                ch |= bits[bit]
                lon_interval[0] = mid
            else:
                lon_interval[1] = mid
        else:
            mid = (lat_interval[0] + lat_interval[1]) / 2
            if lat > mid:
                ch |= bits[bit]
                lat_interval[0] = mid
            else:
                lat_interval[1] = mid
        even = not even
        if bit < 4:
            bit += 1
        else:
            geohash.append(_BASE32[ch])
            bit = 0
            ch = 0
    return "".join(geohash)
