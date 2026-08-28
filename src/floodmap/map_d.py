# Copyright (c) 2026 Martial Systems LLC. All rights reserved.
"""Folium map for the D edge screen. Calibrated P only. No table rewrite."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

import numpy as np
import rasterio
from rasterio.features import shapes
from rasterio.warp import transform as rio_transform
from rasterio.warp import transform_bounds, transform_geom
from shapely.geometry import mapping, shape
from shapely.ops import unary_union

from floodmap.claims import require_clean
from floodmap.codes import MASK_OFR_OR_HWM, P_DEFINITION
from floodmap.config import (
    HUC8,
    P_SFHA_CALIBRATED_NAME,
    P_SFHA_NODATA,
)
from floodmap.errors import GateError

# Centroids of the two Appendix 2 reaches that paint mask code 2 in 05120201.
# Speckle cells within _OFR_CLUSTER_DEG merge into the nearer named reach.
_OFR_CLUSTER_DEG = 0.05
_OFR_REACH_ANCHORS = (
    ("White River at Martinsville", -86.443, 39.424),
    ("unnamed tributary of Fall Creek at Paragon", -86.566, 39.394),
)

_ZONE_RGB = {
    0: (180, 180, 180),
    1: (200, 40, 40),
    2: (120, 0, 0),
    3: (230, 150, 40),
    4: (230, 230, 210),
    5: (120, 80, 160),
    6: (100, 100, 100),
}


def _p_overlay(arr: np.ndarray, nodata: float, step: int) -> np.ndarray:
    sub = arr[::step, ::step]
    valid = np.isfinite(sub) & (sub != nodata)
    v = np.clip(np.where(valid, sub, 0.0), 0.0, 1.0)
    rgba = np.zeros((*sub.shape, 4), dtype=np.uint8)
    rgba[..., 0] = (40 + 215 * v).astype(np.uint8)
    rgba[..., 1] = (40 + 80 * (1.0 - v)).astype(np.uint8)
    rgba[..., 2] = (180 * (1.0 - v)).astype(np.uint8)
    rgba[..., 3] = np.where(valid, 150, 0).astype(np.uint8)
    return rgba


def _zone_overlay(arr: np.ndarray, step: int) -> np.ndarray:
    sub = arr[::step, ::step]
    rgba = np.zeros((*sub.shape, 4), dtype=np.uint8)
    for code, rgb in _ZONE_RGB.items():
        hit = sub == code
        for i, c in enumerate(rgb):
            rgba[..., i][hit] = c
        rgba[..., 3][hit] = 90 if code == 4 else 140
    return rgba


def _latlon(transform, crs, row: int, col: int) -> tuple[float, float]:
    x, y = rasterio.transform.xy(transform, row, col, offset="center")
    lon, lat = rio_transform(crs, "EPSG:4326", [x], [y])
    return float(lat[0]), float(lon[0])


def _name_ofr_reach(lon: float, lat: float) -> str:
    best_name = _OFR_REACH_ANCHORS[0][0]
    best_d = float("inf")
    for name, alon, alat in _OFR_REACH_ANCHORS:
        d = (lon - alon) ** 2 + (lat - alat) ** 2
        if d < best_d:
            best_d = d
            best_name = name
    return best_name


def cluster_ofr_features(geoms_geojson: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Merge code-2 speckles into the two named Appendix 2 reaches."""
    geoms = [shape(g) for g in geoms_geojson if g]
    geoms = [g for g in geoms if not g.is_empty]
    if not geoms:
        return []
    cents = [(g.centroid.x, g.centroid.y) for g in geoms]
    n = len(geoms)
    used = [False] * n
    clusters: list[list[int]] = []
    for i in range(n):
        if used[i]:
            continue
        stack = [i]
        used[i] = True
        group: list[int] = []
        while stack:
            j = stack.pop()
            group.append(j)
            jx, jy = cents[j]
            for k in range(n):
                if used[k]:
                    continue
                kx, ky = cents[k]
                if (jx - kx) ** 2 + (jy - ky) ** 2 <= _OFR_CLUSTER_DEG**2:
                    used[k] = True
                    stack.append(k)
        clusters.append(group)
    out: list[dict[str, Any]] = []
    for group in clusters:
        merged = unary_union([geoms[i] for i in group])
        if merged.is_empty:
            continue
        lon, lat = merged.centroid.x, merged.centroid.y
        out.append(
            {
                "type": "Feature",
                "geometry": mapping(merged),
                "properties": {"code": 2, "reach": _name_ofr_reach(lon, lat)},
            }
        )
    return out


def _ofr_polygons(mask: np.ndarray, transform, src_crs) -> list[dict[str, Any]]:
    code2 = (mask == MASK_OFR_OR_HWM).astype(np.uint8)
    if int(code2.sum()) == 0:
        return []
    raw: list[dict[str, Any]] = []
    for geom, val in shapes(code2, mask=code2.astype(bool), transform=transform):
        if int(val) != 1:
            continue
        g4326 = shape(transform_geom(src_crs, "EPSG:4326", geom))
        if g4326.is_empty:
            continue
        raw.append(mapping(g4326))
    return cluster_ofr_features(raw)


def _popup(name: str, p_max: float | None, p_mean: float | None, note: str) -> str:
    pm = "none" if p_mean is None else f"{p_mean:.3f}"
    px = "none" if p_max is None else f"{p_max:.3f}"
    return (
        f"<b>{name}</b><br>"
        f"P_max={px}<br>"
        f"p_mean={pm}<br>"
        f"{note}<br>"
        f"{P_DEFINITION} calibrated"
    )


def build_d_map(
    *,
    interim_dir: Path,
    facilities_csv: Path,
    headline_csv: Path,
    dest_html: Path,
    downsample: int = 8,
) -> dict[str, Any]:
    p_path = interim_dir / P_SFHA_CALIBRATED_NAME
    if not p_path.is_file():
        raise GateError(f"map needs {P_SFHA_CALIBRATED_NAME}")
    if (interim_dir / "p_sfha.tif").is_file() is False:
        raise GateError("raw p_sfha.tif must remain on disk; map still uses calibrated")
    with rasterio.open(p_path) as src:
        p = src.read(1)
        p_crs = src.crs
        p_tf = src.transform
        west, south, east, north = transform_bounds(src.crs, "EPSG:4326", *src.bounds)
    with rasterio.open(interim_dir / "zone_class.tif") as src:
        zone = src.read(1)
    with rasterio.open(interim_dir / "mask_2008.tif") as src:
        mask = src.read(1)
        mask_crs = src.crs
        mask_tf = src.transform

    import folium
    from folium.raster_layers import ImageOverlay

    fmap = folium.Map(
        location=[(south + north) / 2, (west + east) / 2],
        zoom_start=9,
        tiles="CartoDB positron",
    )
    ImageOverlay(
        image=_p_overlay(p, P_SFHA_NODATA, downsample),
        bounds=[[south, west], [north, east]],
        opacity=0.85,
        name=f"calibrated {P_DEFINITION}",
        mercator_project=True,
    ).add_to(fmap)
    ImageOverlay(
        image=_zone_overlay(zone, downsample),
        bounds=[[south, west], [north, east]],
        opacity=0.5,
        name="zone_class",
        mercator_project=True,
        show=False,
    ).add_to(fmap)
    ofr_gj = _ofr_polygons(mask, mask_tf, mask_crs)
    if ofr_gj:
        folium.GeoJson(
            {"type": "FeatureCollection", "features": ofr_gj},
            name="OFR 2008 code 2 (Martinsville, Paragon)",
            style_function=lambda _: {
                "color": "#0033aa",
                "weight": 2,
                "fillOpacity": 0.25,
                "fillColor": "#3366cc",
            },
            tooltip=folium.GeoJsonTooltip(fields=["reach"], aliases=["OFR 2008"]),
        ).add_to(fmap)

    fac_rows = list(csv.DictReader(facilities_csv.open(encoding="utf-8")))
    head_rows = {r["name"]: r for r in csv.DictReader(headline_csv.open(encoding="utf-8"))}
    n_pts = 0
    for rec in fac_rows:
        lat, lon = float(rec["lat"]), float(rec["lon"])
        name = rec["name"]
        p_max = float(rec["p_max"]) if rec.get("p_max") not in ("", None) else None
        p_mean = float(rec["p_mean"]) if rec.get("p_mean") not in ("", None) else None
        note = rec.get("p_max_note") or rec.get("zone_class") or ""
        eligible = rec.get("d1_eligible") == "True"
        headline = name in head_rows
        color = "#d62728" if headline else ("#1f77b4" if eligible else "#7f7f7f")
        folium.CircleMarker(
            location=[lat, lon],
            radius=5 if headline else 3,
            color=color,
            fill=True,
            fill_opacity=0.85,
            popup=_popup(name, p_max, p_mean, note),
            tooltip=f"{name} p_mean={p_mean if p_mean is not None else 'none'}",
        ).add_to(fmap)
        n_pts += 1
        if headline:
            hr = head_rows[name]
            dr = int(float(hr.get("p_max_dr") or 0))
            dc = int(float(hr.get("p_max_dc") or 0))
            xs, ys = rio_transform("EPSG:4326", p_crs, [lon], [lat])
            orow, ocol = rasterio.transform.rowcol(p_tf, xs[0], ys[0])
            mlat, mlon = _latlon(p_tf, p_crs, orow + dr, ocol + dc)
            folium.PolyLine(
                [[lat, lon], [mlat, mlon]],
                color="#111111",
                weight=2,
                tooltip=f"{name} p_mean={p_mean} office to P_max cell",
            ).add_to(fmap)
            folium.CircleMarker(
                location=[mlat, mlon],
                radius=6,
                color="#000000",
                fill=True,
                fill_color="#ffff00",
                popup=_popup(name, p_max, p_mean, f"P_max cell: {hr.get('p_max_note')}"),
            ).add_to(fmap)

    folium.LayerControl().add_to(fmap)
    dest_html.parent.mkdir(parents=True, exist_ok=True)
    html = fmap.get_root().render()
    require_clean(html, source=str(dest_html))
    dest_html.write_text(html, encoding="utf-8")
    return {
        "path": str(dest_html),
        "p_source": P_SFHA_CALIBRATED_NAME,
        "n_points": n_pts,
        "n_headline": len(head_rows),
        "n_ofr_polygons": len(ofr_gj),
        "huc8": HUC8,
        "colorbar": P_DEFINITION,
    }
