# Copyright (c) 2026 Martial Systems LLC. All rights reserved.
"""WBD 10-digit watersheds for Stage C spatial blocks."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from urllib.parse import quote

import numpy as np
from rasterio.crs import CRS
from rasterio.features import rasterize
from rasterio.warp import transform_geom
from scipy.ndimage import binary_dilation
from shapely.geometry import mapping, shape

from floodmap.align import require_live_template, write_aligned
from floodmap.config import (
    HUC8,
    TEMPLATE_CRS,
    VECTOR_CRS,
    WBD_GEOMETRY_PRECISION,
    WBD_HUC10_LAYER_URL,
    WBD_MAX_ALLOWABLE_OFFSET_DEG,
)
from floodmap.errors import FetchError, GateError
from floodmap.fetch import GetJson, default_get_json
from floodmap.template import TemplateGrid


def huc10_query_url(*, huc8: str = HUC8) -> str:
    where = f"huc10 LIKE '{huc8}%'"
    return (
        f"{WBD_HUC10_LAYER_URL}/query"
        f"?where={quote(where)}"
        f"&outFields=huc10,name,areasqkm,states"
        f"&returnGeometry=true"
        f"&outSR={VECTOR_CRS}"
        f"&maxAllowableOffset={WBD_MAX_ALLOWABLE_OFFSET_DEG}"
        f"&geometryPrecision={WBD_GEOMETRY_PRECISION}"
        f"&f=geojson"
    )


def fetch_huc10_features(
    get_json: GetJson | None = None,
    *,
    huc8: str = HUC8,
) -> list[dict[str, Any]]:
    getter = get_json or default_get_json
    doc = getter(huc10_query_url(huc8=huc8))
    if doc.get("error"):
        raise FetchError(f"HUC-10 query error: {doc['error']}")
    feats = doc.get("features") or []
    if not feats:
        raise GateError(f"no HUC-10 polygons for {huc8}")
    return feats


def rasterize_huc10(
    features: list[dict[str, Any]],
    template: TemplateGrid,
    dest: Path,
) -> dict[str, Any]:
    require_live_template(template)
    legend: dict[str, str] = {}
    shapes = []
    codes: list[str] = []
    for feat in features:
        props = feat.get("properties") or {}
        code = str(props.get("huc10") or props.get("HUC10") or "").strip()
        geom_doc = feat.get("geometry")
        if not code or not geom_doc:
            continue
        geom = shape(geom_doc)
        if geom.is_empty:
            continue
        g5070 = shape(
            transform_geom(
                CRS.from_epsg(VECTOR_CRS),
                CRS.from_epsg(TEMPLATE_CRS),
                mapping(geom),
            )
        )
        codes.append(code)
        legend_key_pending = code
        dest_id = len(codes)
        legend[str(dest_id)] = legend_key_pending
        shapes.append((mapping(g5070), dest_id))
    if not shapes:
        raise GateError("HUC-10 features had no geometries")
    painted = rasterize(
        shapes,
        out_shape=(template.height, template.width),
        transform=template.transform,
        fill=0,
        dtype="uint16",
        all_touched=False,
    )
    write_aligned(dest, template, painted, dtype="uint16", nodata=0)
    return {
        "n_huc10": len(codes),
        "legend": legend,
        "huc10_codes": codes,
        "path": str(dest),
        "n_painted": int((painted > 0).sum()),
    }


def train_test_halo(
    huc10: np.ndarray,
    test_id: int,
    eligible: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Train excludes the test HUC-10 and a 1-pixel halo. Test is the HUC-10 itself."""
    if test_id <= 0:
        raise GateError("HUC-10 test id must be > 0")
    test = (huc10 == test_id) & eligible
    halo = binary_dilation(huc10 == test_id, iterations=1) & eligible
    train = eligible & (huc10 > 0) & (huc10 != test_id) & ~halo
    return train, test, halo


def save_huc10_geojson(features: list[dict[str, Any]], dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    doc = {
        "type": "FeatureCollection",
        "crs": {"type": "name", "properties": {"name": "EPSG:4269"}},
        "features": features,
    }
    dest.write_text(json.dumps(doc), encoding="utf-8")
    return dest
