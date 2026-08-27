# Copyright (c) 2026 Martial Systems LLC. All rights reserved.
"""NHD large-scale flowlines rasterized as distance-to-stream on the template."""

from __future__ import annotations

import json
import time
from pathlib import Path
from urllib.parse import quote

import numpy as np
from rasterio.crs import CRS
from rasterio.features import rasterize
from rasterio.warp import transform_geom
from scipy.ndimage import distance_transform_edt
from shapely.geometry import mapping, shape

from floodmap.align import interior_mask, require_live_template, write_aligned
from floodmap.config import (
    DIST_NODATA,
    NHD_AREA_URL,
    NHD_FLOWLINE_URL,
    NHD_PAGE_SIZE,
    NHD_WATERBODY_URL,
    TEMPLATE_CRS,
    TEMPLATE_RES_M,
    VECTOR_CRS,
)
from floodmap.errors import FetchError, GateError
from floodmap.fetch import GetJson, default_get_json, default_post_json
from floodmap.huc import HucLayer
from floodmap.template import TemplateGrid


def _esri_polygon(geom) -> dict:
    simple = geom.simplify(0.005, preserve_topology=True)
    if simple.geom_type == "MultiPolygon":
        rings = [list(p.exterior.coords) for p in simple.geoms]
    else:
        rings = [list(simple.exterior.coords)]
    return {"rings": rings, "spatialReference": {"wkid": VECTOR_CRS}}


def nhd_query_url(*, xmin: float, ymin: float, xmax: float, ymax: float, offset: int) -> str:
    geom = f"{xmin},{ymin},{xmax},{ymax}"
    return (
        f"{NHD_FLOWLINE_URL}/query"
        f"?where={quote('ftype=460')}"
        f"&geometry={quote(geom)}"
        f"&geometryType=esriGeometryEnvelope"
        f"&inSR={VECTOR_CRS}&outSR={VECTOR_CRS}"
        f"&spatialRel=esriSpatialRelIntersects"
        f"&returnGeometry=true&outFields=objectid"
        f"&resultOffset={offset}&resultRecordCount={NHD_PAGE_SIZE}"
        f"&f=geojson"
    )


def fetch_flowlines(
    huc: HucLayer,
    get_json: GetJson | None = None,
    *,
    post_json=None,
    pause_s: float = 0.05,
) -> list:
    """StreamRiver (ftype=460) intersecting the HUC. Live uses POST polygon; tests may GET."""
    if get_json is not None:
        minx, miny, maxx, maxy = huc.geom.bounds
        page = get_json(
            nhd_query_url(xmin=minx, ymin=miny, xmax=maxx, ymax=maxy, offset=0)
        )
        batch = page.get("features") or []
        if not batch:
            raise GateError("NHD query returned no flowlines")
        return batch
    poster = post_json or default_post_json
    features: list = []
    offset = 0
    geom = json.dumps(_esri_polygon(huc.geom))
    for _ in range(80):
        page = poster(
            f"{NHD_FLOWLINE_URL}/query",
            {
                "where": "ftype=460",
                "geometry": geom,
                "geometryType": "esriGeometryPolygon",
                "inSR": str(VECTOR_CRS),
                "outSR": str(VECTOR_CRS),
                "spatialRel": "esriSpatialRelIntersects",
                "returnGeometry": "true",
                "outFields": "objectid,ftype,fcode",
                "resultOffset": str(offset),
                "resultRecordCount": str(NHD_PAGE_SIZE),
                "f": "geojson",
            },
        )
        if page.get("error"):
            raise FetchError(f"NHD query error: {page['error']}")
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
        raise GateError("NHD pagination exceeded 80 pages")
    if not features:
        raise GateError("NHD query returned no flowlines")
    return features


def fetch_nhd_polygons(
    huc: HucLayer,
    layer_url: str,
    *,
    where: str,
    get_json: GetJson | None = None,
    post_json=None,
    pause_s: float = 0.05,
    out_fields: str = "objectid,ftype,fcode,gnis_name",
    empty_ok: bool = False,
) -> list:
    """POST HUC polygon against an NHD polygon layer. Tests may GET."""
    if get_json is not None:
        minx, miny, maxx, maxy = huc.geom.bounds
        geom = f"{minx},{miny},{maxx},{maxy}"
        page = get_json(
            f"{layer_url}/query"
            f"?where={quote(where)}"
            f"&geometry={quote(geom)}"
            f"&geometryType=esriGeometryEnvelope"
            f"&inSR={VECTOR_CRS}&outSR={VECTOR_CRS}"
            f"&spatialRel=esriSpatialRelIntersects"
            f"&returnGeometry=true&outFields=objectid"
            f"&resultOffset=0&resultRecordCount={NHD_PAGE_SIZE}"
            f"&f=geojson"
        )
        batch = page.get("features") or []
        if not batch and not empty_ok:
            raise GateError(f"NHD polygon query returned no features: {where}")
        return batch
    poster = post_json or default_post_json
    features: list = []
    offset = 0
    geom = json.dumps(_esri_polygon(huc.geom))
    for _ in range(80):
        page = poster(
            f"{layer_url}/query",
            {
                "where": where,
                "geometry": geom,
                "geometryType": "esriGeometryPolygon",
                "inSR": str(VECTOR_CRS),
                "outSR": str(VECTOR_CRS),
                "spatialRel": "esriSpatialRelIntersects",
                "returnGeometry": "true",
                "outFields": out_fields,
                "resultOffset": str(offset),
                "resultRecordCount": str(NHD_PAGE_SIZE),
                "f": "geojson",
            },
        )
        if page.get("error"):
            raise FetchError(f"NHD polygon query error: {page['error']}")
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
        raise GateError("NHD polygon pagination exceeded 80 pages")
    if not features and not empty_ok:
        raise GateError(f"NHD polygon query returned no features: {where}")
    return features


def fetch_waterbodies(huc: HucLayer, get_json: GetJson | None = None, **kwargs) -> list:
    return fetch_nhd_polygons(
        huc, NHD_WATERBODY_URL, where="1=1", get_json=get_json, **kwargs
    )


def fetch_area_streamriver(huc: HucLayer, get_json: GetJson | None = None, **kwargs) -> list:
    return fetch_nhd_polygons(
        huc, NHD_AREA_URL, where="ftype=460", get_json=get_json, empty_ok=True, **kwargs
    )


def features_to_mask(features: list, template: TemplateGrid) -> np.ndarray:
    """Rasterize GeoJSON features (any geometry) onto the template as uint8 0/1."""
    require_live_template(template)
    shapes = []
    for feat in features:
        geom_doc = feat.get("geometry")
        if not geom_doc:
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
        shapes.append((mapping(g5070), 1))
    mask = np.zeros((template.height, template.width), dtype=np.uint8)
    if not shapes:
        return mask
    painted = rasterize(
        shapes,
        out_shape=(template.height, template.width),
        transform=template.transform,
        fill=0,
        dtype="uint8",
        all_touched=True,
    )
    return painted


def rasterize_distance(
    features: list,
    template: TemplateGrid,
    dest: Path,
) -> dict:
    require_live_template(template)
    shapes = []
    for feat in features:
        geom_doc = feat.get("geometry")
        if not geom_doc:
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
        shapes.append((mapping(g5070), 1))
    if not shapes:
        raise GateError("no NHD geometries to rasterize")
    streams = rasterize(
        shapes,
        out_shape=(template.height, template.width),
        transform=template.transform,
        fill=0,
        dtype="uint8",
        all_touched=True,
    )
    dist = distance_transform_edt(streams == 0).astype(np.float32) * np.float32(TEMPLATE_RES_M)
    inside = interior_mask(template)
    dist[~inside] = DIST_NODATA
    write_aligned(dest, template, dist, dtype="float32", nodata=DIST_NODATA)
    return {
        "n_flowlines": len(features),
        "n_stream_cells": int((streams[inside] == 1).sum()),
        "dist_max_m": float(dist[inside].max()) if inside.any() else None,
        "path": str(dest),
    }
