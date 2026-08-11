"""Position helpers shared by every execution environment.

Lifted verbatim from ``gradys_embedded/protocol/position.py``, which was already
byte-identical to the simulator's copy apart from the embedded-only
``x_axis_degrees`` frame rotation. Kept here so the two projects cannot drift.
"""

from __future__ import annotations

import math
from typing import Tuple

Position = Tuple[float, float, float]
"""A node's euclidean position: ``(x, y, z)`` in metres.

In the embedded frame this is NEU rotated by ``x_axis_degrees``: x=North, y=East,
z=Up when the rotation is zero.
"""

GeoPosition = Tuple[float, float, float]
"""A geographic position: ``(latitude, longitude, altitude)``."""

_EARTH_RADIUS_M = 6371000


def _haversine_distance(coord1: Tuple[float, float], coord2: Tuple[float, float]) -> float:
    """Great-circle distance in metres between two ``(lat, lon)`` pairs."""
    lat1, lon1 = math.radians(coord1[0]), math.radians(coord1[1])
    lat2, lon2 = math.radians(coord2[0]), math.radians(coord2[1])

    dlat = lat2 - lat1
    dlon = lon2 - lon1

    a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    return _EARTH_RADIUS_M * c


def geo_to_cartesian(
    ref_coord: GeoPosition,
    target_coord: GeoPosition,
    x_axis_degrees: float = 0.0,
) -> Position:
    """Convert a geographic position into the local cartesian frame.

    Args:
        ref_coord: origin of the local frame, as ``(lat, lon, alt)``.
        target_coord: the point to convert, as ``(lat, lon, alt)``.
        x_axis_degrees: clockwise rotation of the local x axis from true north.

    Returns:
        The target as ``(x, y, z)`` metres relative to ``ref_coord``.
    """
    dn = _haversine_distance((ref_coord[0], ref_coord[1]), (target_coord[0], ref_coord[1]))
    de = _haversine_distance((ref_coord[0], ref_coord[1]), (ref_coord[0], target_coord[1]))

    north = dn if target_coord[0] >= ref_coord[0] else -dn
    east = de if target_coord[1] >= ref_coord[1] else -de
    z = target_coord[2] - ref_coord[2]

    theta = math.radians(x_axis_degrees)
    cos_t, sin_t = math.cos(theta), math.sin(theta)
    x = north * cos_t + east * sin_t
    y = -north * sin_t + east * cos_t

    return x, y, z


def cartesian_to_geo(
    ref_coord: GeoPosition,
    target_coord: Position,
    x_axis_degrees: float = 0.0,
) -> GeoPosition:
    """Inverse of :func:`geo_to_cartesian`.

    Args:
        ref_coord: origin of the local frame, as ``(lat, lon, alt)``.
        target_coord: the point to convert, as ``(x, y, z)`` in the local frame.
        x_axis_degrees: clockwise rotation of the local x axis from true north.

    Returns:
        The target as ``(lat, lon, alt)``.
    """
    x, y, z = target_coord
    theta = math.radians(x_axis_degrees)
    cos_t, sin_t = math.cos(theta), math.sin(theta)
    north = x * cos_t - y * sin_t
    east = x * sin_t + y * cos_t

    dlat = north / 111320
    dlon = east / (111320 * math.cos(math.radians(ref_coord[0])))

    return ref_coord[0] + dlat, ref_coord[1] + dlon, ref_coord[2] + z


def squared_distance(start: Position, end: Position) -> float:
    """Squared euclidean distance between two positions.

    Squared, so callers comparing against a tolerance can avoid the square root.
    """
    return (end[0] - start[0]) ** 2 + (end[1] - start[1]) ** 2 + (end[2] - start[2]) ** 2


def distance(start: Position, end: Position) -> float:
    """Euclidean distance between two positions, in metres."""
    return math.sqrt(squared_distance(start, end))
