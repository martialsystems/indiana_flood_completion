# Copyright (c) 2026 Martial Systems LLC. All rights reserved.
"""Load a HUC polygon. Refuse empty geometry."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from shapely.geometry import shape
from shapely.geometry.base import BaseGeometry

from floodmap.config import HUC8, VECTOR_CRS
from floodmap.crs import require_epsg
from floodmap.errors import CrsMissingError, EmptyHucError


@dataclass(frozen=True)
class HucLayer:
    geom: BaseGeometry
    huc8: str
    crs: int
    n_features: int


def _crs_from_geojson(doc: dict[str, Any]) -> int | None:
    crs = doc.get("crs")
    if isinstance(crs, dict):
        props = crs.get("properties") or {}
        name = str(props.get("name") or "")
        if "4269" in name:
            return 4269
        if "5070" in name:
            return 5070
        if name.upper().startswith("EPSG:"):
            try:
                return int(name.split(":", 1)[1])
            except ValueError:
                return None
        wkid = props.get("wkid")
        if wkid is not None:
            try:
                return int(wkid)
            except (TypeError, ValueError):
                return None
    return None


def _huc_code(props: dict[str, Any]) -> str:
    for key in ("huc8", "HUC8", "huc", "HUC"):
        val = props.get(key)
        if val is not None and str(val).strip():
            return str(val).strip()
    return ""


def load_huc(
    path: Path,
    *,
    wkid: int | None = None,
    expected_huc: str = HUC8,
) -> HucLayer:
    doc = json.loads(path.read_text(encoding="utf-8"))
    file_crs = _crs_from_geojson(doc)
    crs = require_epsg(
        file_crs if file_crs is not None else wkid,
        expected=VECTOR_CRS,
    )
    features = doc.get("features") or []
    geoms: list[BaseGeometry] = []
    codes: list[str] = []
    for feat in features:
        geom_doc = feat.get("geometry")
        if not geom_doc:
            continue
        geom = shape(geom_doc)
        if geom.is_empty:
            continue
        geoms.append(geom)
        codes.append(_huc_code(feat.get("properties") or {}))
    if not geoms:
        raise EmptyHucError(f"no HUC polygons in {path}")
    merged = geoms[0]
    for extra in geoms[1:]:
        merged = merged.union(extra)
    if merged.is_empty:
        raise EmptyHucError(f"empty union in {path}")
    code = next((c for c in codes if c), expected_huc)
    if code != expected_huc:
        raise EmptyHucError(f"HUC {code!r} != {expected_huc!r}")
    return HucLayer(geom=merged, huc8=code, crs=crs, n_features=len(geoms))


def require_huc_crs(wkid: int | None, *, expected: int = VECTOR_CRS) -> int:
    if wkid is None:
        raise CrsMissingError("HUC layer has no CRS")
    return require_epsg(wkid, expected=expected)
