# Copyright (c) 2026 Martial Systems LLC. All rights reserved.
"""CRS refuse helpers."""

from __future__ import annotations

from floodmap.config import TEMPLATE_CRS
from floodmap.errors import CrsMismatchError, CrsMissingError


def require_epsg(wkid: int | None, *, expected: int = TEMPLATE_CRS) -> int:
    if wkid is None:
        raise CrsMissingError("layer has no CRS")
    if int(wkid) != expected:
        raise CrsMismatchError(f"CRS EPSG:{wkid} != EPSG:{expected}")
    return int(wkid)


def epsg_from_rasterio(crs: object) -> int | None:
    if crs is None:
        return None
    try:
        if getattr(crs, "is_epsg_code", False):
            return int(crs.to_epsg())  # type: ignore[union-attr]
    except Exception:
        return None
    to_epsg = getattr(crs, "to_epsg", None)
    if callable(to_epsg):
        code = to_epsg()
        if code is not None:
            return int(code)
    text = str(crs)
    if "5070" in text:
        return 5070
    if "4269" in text:
        return 4269
    return None
