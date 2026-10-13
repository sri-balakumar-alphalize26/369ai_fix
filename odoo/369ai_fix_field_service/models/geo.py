# -*- coding: utf-8 -*-
"""Small map helpers: distance between two points, a sane GPS fix, and
reading a point out of a pasted map link."""
import math
import re
from urllib.parse import unquote

EARTH_RADIUS_M = 6371008.8

_NUM = r'(-?\d{1,3}(?:\.\d+)?)'
# Most specific first: the "!3d..!4d.." pair is the dropped pin itself, while
# "@lat,lng" is only where the map was centred.
_LINK_PATTERNS = [
    re.compile(r'!3d' + _NUM + r'!4d' + _NUM),
    re.compile(r'[?&](?:q|query|ll|destination|daddr|center)=(?:loc:)?' + _NUM + r'\s*,\s*' + _NUM),
    re.compile(r'@' + _NUM + r',' + _NUM),
    re.compile(r'geo:' + _NUM + r',' + _NUM),
    re.compile(r'^\s*' + _NUM + r'\s*,\s*' + _NUM + r'\s*$'),
]


def valid_fix(lat, lng):
    """(lat, lng) as floats, or None for missing, out-of-range or 0,0 values."""
    try:
        lat, lng = float(lat), float(lng)
    except (TypeError, ValueError):
        return None
    if not (-90.0 <= lat <= 90.0 and -180.0 <= lng <= 180.0):
        return None
    if not lat and not lng:
        return None
    return lat, lng


def metres(lat1, lng1, lat2, lng2):
    """Great-circle distance in metres (haversine)."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(min(1.0, math.sqrt(a)))


def parse_map_link(text):
    """The point in a Google/Apple/OSM map link or a plain "lat, lng", or None."""
    if not text:
        return None
    text = unquote(str(text).strip())
    for pattern in _LINK_PATTERNS:
        match = pattern.search(text)
        if match:
            fix = valid_fix(match.group(1), match.group(2))
            if fix:
                return fix
    return None


def osm_embed(lat, lng, span=0.006):
    """An OpenStreetMap embed URL centred on the point, with a marker."""
    return ('https://www.openstreetmap.org/export/embed.html?bbox=%.6f,%.6f,%.6f,%.6f'
            '&layer=mapnik&marker=%.6f,%.6f' % (lng - span, lat - span, lng + span, lat + span, lat, lng))
