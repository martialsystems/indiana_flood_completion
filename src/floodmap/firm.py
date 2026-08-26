# Copyright (c) 2026 Martial Systems LLC. All rights reserved.
"""IndianaMap FIRM 2023: sfha band and zone_class codebook on the template."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any
from urllib.parse import quote

import numpy as np
from rasterio.crs import CRS
from rasterio.features import rasterize
from rasterio.warp import transform_geom
from shapely.geometry import mapping, shape

from floodmap.align import interior_mask, require_live_template, write_aligned
import rasterio
from floodmap.codes import (
    ZONE_CLASS_NAME,
    ZONE_D,
    ZONE_FLOODWAY,
    ZONE_OTHER,
    ZONE_SFHA,
    ZONE_SHADED_X,
    ZONE_UNMAPPED,
    ZONE_UNSHADED_X,
    classify_firm_zone,
)
from floodmap.config import (
    FIRM_EXPECTED_CRS,
    FIRM_GEOMETRY_PRECISION,
    FIRM_LAYER_URL,
    FIRM_MAX_ALLOWABLE_OFFSET_DEG,
    FIRM_PAGE_SIZE,
    TEMPLATE_CRS,
    VECTOR_CRS,
)
from floodmap.errors import CrsMissingError, FetchError, GateError
from floodmap.fetch import GetJson, _layer_wkid, default_get_json
from floodmap.template import TemplateGrid

_PAINT_ORDER = (
    ZONE_UNMAPPED,
    ZONE_OTHER,
    ZONE_D,
    ZONE_UNSHADED_X,
    ZONE_SHADED_X,
    ZONE_SFHA,
    ZONE_FLOODWAY,
)


def firm_query_url(*, offset: int, page_size: int = FIRM_PAGE_SIZE) -> str:
    return (
        f"{FIRM_LAYER_URL}/query"
        f"?where={quote('1=1')}"
        f"&outFields=objectid,fld_zone,sfha_tf,zone_subty,dfirm_id"
        f"&orderByFields=objectid"
        f"&resultOffset={offset}"
        f"&resultRecordCount={page_size}"
        f"&maxAllowableOffset={FIRM_MAX_ALLOWABLE_OFFSET_DEG}"
        f"&geometryPrecision={FIRM_GEOMETRY_PRECISION}"
        f"&returnGeometry=true"
        f"&outSR={VECTOR_CRS}"
        f"&f=geojson"
    )


def fetch_firm_pages(
    get_json: GetJson,
    *,
    page_size: int = FIRM_PAGE_SIZE,
    pause_s: float = 0.1,
) -> tuple[int, list[dict[str, Any]]]:
    meta = get_json(f"{FIRM_LAYER_URL}?f=pjson")
    wkid = _layer_wkid(meta)
    if wkid is None:
        raise CrsMissingError("FIRM FeatureServer has no spatialReference")
    if int(wkid) != FIRM_EXPECTED_CRS:
        raise GateError(f"FIRM wkid {wkid} != {FIRM_EXPECTED_CRS}")
    features: list[dict[str, Any]] = []
    offset = 0
    for _ in range(200):
        page = get_json(firm_query_url(offset=offset, page_size=page_size))
        if page.get("error"):
            raise FetchError(f"FIRM query error: {page['error']}")
        batch = page.get("features") or []
        if not batch:
            break
        features.extend(batch)
        exceeded = bool(
            (page.get("properties") or {}).get("exceededTransferLimit")
            or page.get("exceededTransferLimit")
        )
        if not exceeded:
            break
        offset += len(batch)
        if pause_s:
            time.sleep(pause_s)
    else:
        raise GateError("FIRM pagination exceeded 200 pages")
    if not features:
        raise GateError("FIRM query returned no features")
    return wkid, features


def summarize_firm_rasters(template: TemplateGrid, sfha_path: Path, zone_path: Path) -> dict:
    require_live_template(template)
    inside = interior_mask(template)
    with rasterio.open(sfha_path) as src:
        sfha = src.read(1)
    with rasterio.open(zone_path) as src:
        zone = src.read(1)
    interior_sfha = sfha[inside]
    interior_zone = zone[inside]
    counts = {
        ZONE_CLASS_NAME[int(k)]: int((interior_zone == k).sum())
        for k in sorted(np.unique(interior_zone))
        if int(k) in ZONE_CLASS_NAME
    }
    return {
        "sfha_counts": {
            "0": int((interior_sfha == 0).sum()),
            "1": int((interior_sfha == 1).sum()),
        },
        "zone_class_counts": counts,
        "sfha_has_0_and_1": bool(0 in interior_sfha and 1 in interior_sfha),
        "from_existing_rasters": True,
    }


def rasterize_firm(
    features: list[dict[str, Any]],
    template: TemplateGrid,
    *,
    sfha_dest: Path,
    zone_dest: Path,
) -> dict:
    require_live_template(template)
    buckets: dict[int, list] = {code: [] for code in _PAINT_ORDER}
    n_empty = 0
    for feat in features:
        props = feat.get("properties") or {}
        geom_doc = feat.get("geometry")
        if not geom_doc:
            n_empty += 1
            continue
        geom = shape(geom_doc)
        if geom.is_empty:
            n_empty += 1
            continue
        geom5070 = shape(
            transform_geom(
                CRS.from_epsg(VECTOR_CRS),
                CRS.from_epsg(TEMPLATE_CRS),
                mapping(geom),
            )
        )
        code, _name = classify_firm_zone(
            props.get("fld_zone"),
            props.get("zone_subty"),
            props.get("sfha_tf"),
        )
        buckets[code].append((mapping(geom5070), code))
    zone = np.full((template.height, template.width), ZONE_UNMAPPED, dtype=np.uint8)
    for code in _PAINT_ORDER:
        shapes = buckets[code]
        if not shapes:
            continue
        painted = rasterize(
            shapes,
            out_shape=(template.height, template.width),
            transform=template.transform,
            fill=0,
            dtype="uint8",
            all_touched=False,
        )
        zone = np.where(painted == code, painted, zone).astype(np.uint8)
    inside = interior_mask(template)
    sfha = np.where(
        np.isin(zone, (ZONE_SFHA, ZONE_FLOODWAY)),
        1,
        0,
    ).astype(np.uint8)
    zone = np.where(inside, zone, 255).astype(np.uint8)
    sfha = np.where(inside, sfha, 255).astype(np.uint8)
    interior_sfha = sfha[inside]
    if not (0 in interior_sfha and 1 in interior_sfha):
        raise GateError("sfha band missing 0 or 1 inside the HUC")
    write_aligned(sfha_dest, template, sfha, dtype="uint8", nodata=255)
    write_aligned(zone_dest, template, zone, dtype="uint8", nodata=255)
    interior_zone = zone[inside]
    counts = {
        ZONE_CLASS_NAME[int(k)]: int((interior_zone == k).sum())
        for k in sorted(np.unique(interior_zone))
        if int(k) in ZONE_CLASS_NAME
    }
    return {
        "n_firm_features": len(features),
        "n_empty_geom": n_empty,
        "sfha_counts": {
            "0": int((interior_sfha == 0).sum()),
            "1": int((interior_sfha == 1).sum()),
        },
        "zone_class_counts": counts,
        "sfha_has_0_and_1": True,
    }
