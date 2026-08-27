# Copyright (c) 2026 Martial Systems LLC. All rights reserved.
"""gSSURGO hydrologic soil group on the template. Dual groups stay distinct."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import numpy as np
import rasterio
from rasterio.crs import CRS
from rasterio.features import rasterize
from rasterio.warp import transform_geom
from shapely.geometry import mapping, shape

from floodmap.align import interior_mask, require_live_template, write_aligned
from floodmap.config import (
    HSG_CODE,
    HSG_NODATA,
    SDA_URL,
    TEMPLATE_CRS,
    USER_AGENT,
    VECTOR_CRS,
)
from floodmap.errors import FetchError, GateError
from floodmap.huc import HucLayer
from floodmap.template import TemplateGrid

SdaPost = Callable[[str], dict[str, Any]]


def _wkt_wgs84(huc: HucLayer) -> str:
    # 4269 lon/lat is close enough to WGS84 for SDA intersection.
    return huc.geom.wkt


def default_sda_post(sql: str) -> dict[str, Any]:
    body = urlencode({"format": "JSON", "query": sql}).encode("utf-8")
    req = Request(
        SDA_URL,
        data=body,
        headers={
            "User-Agent": USER_AGENT,
            "Content-Type": "application/x-www-form-urlencoded",
        },
        method="POST",
    )
    try:
        with urlopen(req, timeout=45) as resp:
            raw = resp.read()
    except Exception as exc:  # noqa: BLE001
        raise FetchError(f"SDA POST failed: {exc}") from exc
    try:
        return json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise FetchError("SDA returned non-JSON") from exc


def _table(doc: dict[str, Any]) -> list[list[Any]]:
    table = doc.get("Table") or doc.get("table")
    if not table:
        raise FetchError(f"SDA response missing Table: {list(doc)[:8]}")
    return table


def _bbox_wkts(huc: HucLayer, step: float = 0.2) -> list[str]:
    minx, miny, maxx, maxy = huc.geom.bounds
    wkts: list[str] = []
    x = minx
    while x < maxx:
        y = miny
        x2 = min(x + step, maxx)
        while y < maxy:
            y2 = min(y + step, maxy)
            wkts.append(
                f"POLYGON(({x} {y},{x2} {y},{x2} {y2},{x} {y2},{x} {y}))"
            )
            y = y2
        x = x2
    return wkts


def fetch_hsg_polygons(huc: HucLayer, sda_post: SdaPost) -> list[tuple[dict, int]]:
    """Return (geojson-mapping in 5070, hsg_code) from tiled SDA mupolygongeo."""
    wkt = _wkt_wgs84(huc).replace("'", "''")
    sql_hsg = (
        "SELECT muaggatt.mukey, muaggatt.hydgrpdcd "
        "FROM muaggatt "
        "INNER JOIN ("
        f"SELECT * FROM SDA_Get_Mukey_from_intersection_with_WktWgs84('{wkt}')"
        ") AS mu ON muaggatt.mukey = mu.mukey"
    )
    hsg_map = {k: v for k, v in fetch_hsg_rows_from_sql(sda_post, sql_hsg)}
    out: list[tuple[dict, int]] = []
    for tile_wkt in _bbox_wkts(huc):
        tw = tile_wkt.replace("'", "''")
        sql_poly = (
            "SELECT mukey, mupolygongeo FROM mupolygon WHERE mukey IN ("
            f"SELECT * FROM SDA_Get_Mukey_from_intersection_with_WktWgs84('{tw}')"
            ")"
        )
        try:
            doc = sda_post(sql_poly)
        except FetchError:
            continue
        table = _table(doc)
        if not table:
            continue
        header = [str(c).lower() for c in table[0]]
        if "mukey" in header:
            i_key = header.index("mukey")
            i_geo = 1 if len(header) > 1 else 0
            body = table[1:]
        else:
            i_key, i_geo = 0, 1
            body = table
        for row in body:
            if len(row) <= max(i_key, i_geo):
                continue
            mukey = str(row[i_key] or "").strip()
            geom = _parse_sda_geom(row[i_geo])
            if geom is None or geom.is_empty:
                continue
            g5070 = shape(
                transform_geom(
                    CRS.from_epsg(VECTOR_CRS),
                    CRS.from_epsg(TEMPLATE_CRS),
                    mapping(geom),
                )
            )
            code = hsg_code(hsg_map.get(mukey, ""))
            out.append((mapping(g5070), code))
    if not out:
        raise GateError("SDA polygons empty after parse")
    return out


def fetch_hsg_rows_from_sql(sda_post: SdaPost, sql: str) -> list[tuple[str, str]]:
    doc = sda_post(sql)
    rows = _table(doc)
    if not rows:
        raise GateError("SDA returned no hydgrp rows")
    header = [str(c).lower() for c in rows[0]]
    has_header = "mukey" in header or any("hydgrp" in h for h in header)
    if has_header:
        body = rows[1:]
        try:
            i_key = next(i for i, h in enumerate(header) if "mukey" in h)
            i_hsg = next(i for i, h in enumerate(header) if "hydgrp" in h)
        except StopIteration as exc:
            raise GateError(f"SDA hydgrp columns missing: {header}") from exc
    else:
        body = rows
        i_key, i_hsg = 0, 1
    out: list[tuple[str, str]] = []
    for row in body:
        if len(row) <= max(i_key, i_hsg):
            continue
        mukey = str(row[i_key] or "").strip()
        hsg = str(row[i_hsg] or "").strip().upper().replace(" ", "")
        if mukey:
            out.append((mukey, hsg))
    if not out:
        raise GateError("SDA hydgrp rows empty after parse")
    return out


def _parse_sda_geom(raw: object):
    if raw is None:
        return None
    if isinstance(raw, dict) and raw.get("type"):
        return shape(raw)
    text = str(raw).strip()
    if not text:
        return None
    if text.startswith("{") or text.startswith("["):
        try:
            return shape(json.loads(text))
        except Exception:
            return None
    try:
        from shapely import wkt as shapely_wkt

        return shapely_wkt.loads(text)
    except Exception:
        return None


def fetch_hsg_rows(huc: HucLayer, sda_post: SdaPost) -> list[tuple[str, str]]:
    wkt = _wkt_wgs84(huc).replace("'", "''")
    sql = (
        "SELECT mu.mukey, muaggatt.hydgrpdcd "
        "FROM muaggatt "
        "INNER JOIN ("
        f"SELECT * FROM SDA_Get_Mukey_from_intersection_with_WktWgs84('{wkt}')"
        ") AS mu ON muaggatt.mukey = mu.mukey"
    )
    return fetch_hsg_rows_from_sql(sda_post, sql)


def hsg_code(token: str) -> int:
    if token in HSG_CODE:
        return HSG_CODE[token]
    if token and "/" in token:
        return 10
    return HSG_NODATA


def write_hsg_from_sda(
    huc: HucLayer,
    template: TemplateGrid,
    dest: Path,
    sda_post: SdaPost,
) -> dict:
    """Tile the HUC, fetch mupolygongeo, paint HSG onto the template as we go."""
    require_live_template(template)
    painted = np.full((template.height, template.width), HSG_NODATA, dtype=np.uint8)
    n_poly = 0
    n_tiles_ok = 0
    wkt = _wkt_wgs84(huc).replace("'", "''")
    sql_hsg = (
        "SELECT muaggatt.mukey, muaggatt.hydgrpdcd "
        "FROM muaggatt "
        "INNER JOIN ("
        f"SELECT * FROM SDA_Get_Mukey_from_intersection_with_WktWgs84('{wkt}')"
        ") AS mu ON muaggatt.mukey = mu.mukey"
    )
    hsg_map = {k: v for k, v in fetch_hsg_rows_from_sql(sda_post, sql_hsg)}
    for tile_wkt in _bbox_wkts(huc, step=0.25):
        tw = tile_wkt.replace("'", "''")
        sql_poly = (
            "SELECT TOP 4000 mukey, mupolygongeo FROM mupolygon WHERE mukey IN ("
            f"SELECT * FROM SDA_Get_Mukey_from_intersection_with_WktWgs84('{tw}')"
            ")"
        )
        try:
            doc = sda_post(sql_poly)
        except FetchError:
            continue
        table = _table(doc)
        if not table:
            continue
        header = [str(c).lower() for c in table[0]]
        if "mukey" in header:
            i_key, i_geo = header.index("mukey"), 1
            body = table[1:]
        else:
            i_key, i_geo = 0, 1
            body = table
        batch: list[tuple[dict, int]] = []
        for row in body:
            if len(row) <= max(i_key, i_geo):
                continue
            mukey = str(row[i_key] or "").strip()
            geom = _parse_sda_geom(row[i_geo])
            if geom is None or geom.is_empty:
                continue
            g5070 = shape(
                transform_geom(
                    CRS.from_epsg(VECTOR_CRS),
                    CRS.from_epsg(TEMPLATE_CRS),
                    mapping(geom),
                )
            )
            batch.append((mapping(g5070), hsg_code(hsg_map.get(mukey, ""))))
        if not batch:
            continue
        layer = rasterize(
            batch,
            out_shape=(template.height, template.width),
            transform=template.transform,
            fill=0,
            dtype="uint8",
            all_touched=False,
        )
        painted = np.where((layer > 0) & (layer < HSG_NODATA), layer, painted).astype(
            np.uint8
        )
        n_poly += len(batch)
        n_tiles_ok += 1
    inside = interior_mask(template)
    painted = np.where(inside, painted, HSG_NODATA).astype(np.uint8)
    if int((painted[inside] != HSG_NODATA).sum()) == 0:
        raise GateError("HSG raster has no valid cells inside the HUC")
    write_aligned(dest, template, painted, dtype="uint8", nodata=HSG_NODATA)
    interior = painted[inside]
    counts = {str(int(k)): int((interior == k).sum()) for k in sorted(np.unique(interior))}
    return hsg_coverage_fields(
        counts,
        n_polygons=n_poly,
        n_tiles_ok=n_tiles_ok,
        path=dest,
        from_existing=False,
    )


def rasterize_hsg(
    polygons: list[tuple[Any, int]],
    template: TemplateGrid,
    dest: Path,
) -> dict:
    require_live_template(template)
    if not polygons:
        raise GateError("no HSG polygons")
    painted = rasterize(
        polygons,
        out_shape=(template.height, template.width),
        transform=template.transform,
        fill=HSG_NODATA,
        dtype="uint8",
        all_touched=False,
    )
    inside = interior_mask(template)
    painted = np.where(inside, painted, HSG_NODATA).astype(np.uint8)
    write_aligned(dest, template, painted, dtype="uint8", nodata=HSG_NODATA)
    interior = painted[inside]
    counts = {str(int(k)): int((interior == k).sum()) for k in sorted(np.unique(interior))}
    return hsg_coverage_fields(
        counts,
        n_polygons=len(polygons),
        path=dest,
        from_existing=False,
    )


def hsg_coverage_fields(
    counts: dict[str, int],
    *,
    n_polygons: int | None = None,
    n_tiles_ok: int | None = None,
    path: Path | None = None,
    from_existing: bool = False,
) -> dict[str, Any]:
    n_missing = int(counts.get(str(HSG_NODATA), 0))
    n_coded = sum(int(v) for k, v in counts.items() if str(k) != str(HSG_NODATA))
    n_interior = n_coded + n_missing
    incomplete = n_interior == 0 or (n_coded / n_interior) < 0.5
    out: dict[str, Any] = {
        "hsg_counts": counts,
        "n_coded": n_coded,
        "n_missing": n_missing,
        "n_interior": n_interior,
        "hsg_incomplete": incomplete,
        "hsg_source": "tiled_sda_top4000",
        "from_existing_rasters": from_existing,
    }
    if n_polygons is not None:
        out["n_polygons"] = n_polygons
    if n_tiles_ok is not None:
        out["n_tiles_ok"] = n_tiles_ok
    if path is not None:
        out["path"] = str(path)
    return out


def summarize_hsg_raster(template: TemplateGrid, path: Path) -> dict[str, Any]:
    require_live_template(template)
    with rasterio.open(path) as src:
        painted = src.read(1)
    inside = interior_mask(template)
    interior = painted[inside]
    counts = {str(int(k)): int((interior == k).sum()) for k in sorted(np.unique(interior))}
    return hsg_coverage_fields(counts, path=path, from_existing=True)
