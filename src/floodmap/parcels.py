# Copyright (c) 2026 Martial Systems LLC. All rights reserved.
"""Cadastral clip for the five Table 1 sites only. Does not rewrite D."""

from __future__ import annotations

import csv
import json
import math
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlencode

import numpy as np
import rasterio
from rasterio.warp import transform as rio_transform
from rasterio.warp import transform_geom
from shapely.geometry import Point, shape
from shapely.ops import nearest_points

from floodmap.cartography import HEADLINE_ORDER, ZOOM_HALF_CELLS, _extent, _lonlat_xy, _xy_to_rowcol
from floodmap.claims import require_clean, scan_obj
from floodmap.codes import P_DEFINITION, ZONE_FLOODWAY, ZONE_SFHA
from floodmap.config import (
    D_BUFFER_RADIUS_CELLS,
    PARCEL_LAYER_URL,
    PARCEL_SNAP_M,
    PARCEL_SOURCE,
    PARCEL_WINDOW_M,
    P_SFHA_CALIBRATED_NAME,
    P_SFHA_NODATA,
    USER_AGENT,
)
from floodmap.errors import FetchError, GateError
from floodmap.fetch import default_get_json

GetJson = Callable[[str], dict[str, Any]]

_DEG_M = 111_320.0
_OUT_FIELDS = "state_parcel_id,parcel_id,county_fips,SHAPE__Area"


def _deg_m(lat: float) -> tuple[float, float]:
    return _DEG_M, _DEG_M * math.cos(math.radians(lat))


def _distance_m(geom, lon: float, lat: float) -> float:
    dlat_m, dlon_m = _deg_m(lat)
    pt = Point(lon, lat)
    near = nearest_points(geom, pt)[0]
    return float(math.hypot((near.y - lat) * dlat_m, (near.x - lon) * dlon_m))


def _parcel_id(props: dict[str, Any] | None) -> str | None:
    if not props:
        return None
    pid = props.get("parcel_id") or props.get("state_parcel_id")
    if pid in (None, ""):
        return None
    return str(pid)


def _is_row(props: dict[str, Any] | None) -> bool:
    pid = _parcel_id(props)
    return pid == "ROW" if pid else False


def nearest_parcel(
    lon: float,
    lat: float,
    features: list[dict[str, Any]],
    *,
    snap_m: float = PARCEL_SNAP_M,
    allow_row: bool = True,
) -> tuple[dict[str, Any] | None, float | None]:
    best: dict[str, Any] | None = None
    best_d = float("inf")
    for feat in features:
        geom = feat.get("geometry")
        if not geom:
            continue
        props = feat.get("properties") or {}
        if not allow_row and _is_row(props):
            continue
        g = shape(geom)
        if g.is_empty:
            continue
        d = _distance_m(g, lon, lat)
        if d < best_d:
            best_d = d
            best = feat
    if best is None or best_d > snap_m:
        return None, None
    return best, best_d


def reading_for(*, office_id: str | None, max_id: str | None) -> str:
    if office_id is None:
        return "office not near a parcel"
    if max_id is None:
        return "max cell in unparceled area"
    if office_id == max_id:
        return "max cell on office parcel"
    return "max cell off office parcel"


def query_parcels_envelope(
    lon: float,
    lat: float,
    *,
    window_m: float = PARCEL_WINDOW_M,
    get_json: GetJson | None = None,
    layer_url: str = PARCEL_LAYER_URL,
) -> list[dict[str, Any]]:
    getter = get_json or default_get_json
    dlat_m, dlon_m = _deg_m(lat)
    dlat = window_m / dlat_m
    dlon = window_m / dlon_m
    envelope = f"{lon - dlon},{lat - dlat},{lon + dlon},{lat + dlat}"
    fields = {
        "where": "1=1",
        "geometry": envelope,
        "geometryType": "esriGeometryEnvelope",
        "inSR": "4326",
        "spatialRel": "esriSpatialRelIntersects",
        "outFields": _OUT_FIELDS,
        "returnGeometry": "true",
        "outSR": "4326",
        "f": "geojson",
    }
    url = f"{layer_url}/query?{urlencode(fields)}"
    doc = getter(url)
    if doc.get("error"):
        raise FetchError(f"parcel query error: {doc['error']}")
    feats = doc.get("features")
    if not isinstance(feats, list):
        raise FetchError("parcel query did not return a FeatureCollection")
    return [f for f in feats if isinstance(f, dict) and f.get("geometry")]


def _max_cell_lonlat(
    *,
    transform,
    crs,
    lon: float,
    lat: float,
    dr: int,
    dc: int,
) -> tuple[float, float]:
    x, y = _lonlat_xy(crs, lon, lat)
    orow, ocol = _xy_to_rowcol(transform, x, y)
    mx, my = rasterio.transform.xy(transform, orow + dr, ocol + dc, offset="center")
    mlon, mlat = rio_transform(crs, "EPSG:4326", [mx], [my])
    return float(mlon[0]), float(mlat[0])


def classify_site(
    *,
    name: str,
    lon: float,
    lat: float,
    headline: dict[str, str],
    features: list[dict[str, Any]],
    transform,
    crs,
    snap_m: float = PARCEL_SNAP_M,
) -> dict[str, Any]:
    p_mean = float(headline["p_mean"])
    dr = int(float(headline.get("p_max_dr") or 0))
    dc = int(float(headline.get("p_max_dc") or 0))
    mlon, mlat = _max_cell_lonlat(transform=transform, crs=crs, lon=lon, lat=lat, dr=dr, dc=dc)
    office_feat, office_d = nearest_parcel(lon, lat, features, snap_m=snap_m, allow_row=False)
    if office_feat is None:
        office_feat, office_d = nearest_parcel(lon, lat, features, snap_m=snap_m, allow_row=True)
    max_feat, max_d = nearest_parcel(mlon, mlat, features, snap_m=snap_m, allow_row=True)
    office_id = _parcel_id((office_feat or {}).get("properties"))
    max_id = _parcel_id((max_feat or {}).get("properties"))
    office_props = (office_feat or {}).get("properties") or {}
    row = {
        "name": name,
        "p_mean": p_mean,
        "p_max": float(headline.get("p_max") or 0),
        "p_max_note": headline.get("p_max_note"),
        "p_max_zone_class": headline.get("p_max_zone_class"),
        "office_lon": lon,
        "office_lat": lat,
        "max_lon": mlon,
        "max_lat": mlat,
        "office_parcel_id": office_id,
        "max_parcel_id": max_id,
        "max_on_office_parcel": bool(office_id and max_id and office_id == max_id),
        "office_snap_m": None if office_d is None else round(office_d, 1),
        "max_snap_m": None if max_d is None else round(max_d, 1),
        "n_parcels_in_window": len(features),
        "county_fips": office_props.get("county_fips") or (max_feat or {}).get("properties", {}).get("county_fips"),
        "reading": reading_for(office_id=office_id, max_id=max_id),
    }
    return row


def write_parcel_zooms(
    *,
    p: np.ndarray,
    zone: np.ndarray,
    transform,
    crs,
    facilities: list[dict[str, str]],
    headline: list[dict[str, str]],
    site_features: dict[str, list[dict[str, Any]]],
    site_rows: list[dict[str, Any]],
    dest: Path,
    p_nodata: float = P_SFHA_NODATA,
    half: int = ZOOM_HALF_CELLS,
) -> list[str]:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Polygon as MplPoly
    from matplotlib.patches import Rectangle

    fac = {r["name"]: r for r in facilities}
    by_name = {r["name"]: r for r in headline}
    rows = {r["name"]: r for r in site_rows}
    names = [n for n in HEADLINE_ORDER if n in by_name]
    titles: list[str] = []
    fig, axes = plt.subplots(2, 3, figsize=(11.0, 7.4), dpi=130)
    radius = D_BUFFER_RADIUS_CELLS
    for i, ax in enumerate(axes.ravel()):
        if i >= len(names):
            ax.axis("off")
            ax.set_title("Legend")
            ax.text(
                0.05,
                0.7,
                "Wash: calibrated P\nGreen: parcels\nBold green: office parcel\n"
                "Black line: office to max cell\nBox: 9x9 / 120 m window",
                transform=ax.transAxes,
                fontsize=8,
                va="top",
            )
            continue
        name = names[i]
        rec = fac[name]
        hr = by_name[name]
        site = rows[name]
        p_mean = float(hr["p_mean"])
        title = f"{name} p_mean {p_mean:.3f}"
        titles.append(title)
        lon, lat = float(rec["lon"]), float(rec["lat"])
        x, y = _lonlat_xy(crs, lon, lat)
        orow, ocol = _xy_to_rowcol(transform, x, y)
        dr = int(float(hr.get("p_max_dr") or 0))
        dc = int(float(hr.get("p_max_dc") or 0))
        r0 = max(0, orow - half)
        r1 = min(p.shape[0], orow + half + 1)
        c0 = max(0, ocol - half)
        c1 = min(p.shape[1], ocol + half + 1)
        pwin = p[r0:r1, c0:c1]
        zw = zone[r0:r1, c0:c1]
        show = np.ma.masked_where(~np.isfinite(pwin) | (pwin == p_nodata), np.clip(pwin, 0, 1))
        win_tf = rasterio.Affine(
            transform.a,
            transform.b,
            transform.c + c0 * transform.a,
            transform.d,
            transform.e,
            transform.f + r0 * transform.e,
        )
        west, east, south, north = _extent(win_tf, pwin.shape[0], pwin.shape[1])
        ax.imshow(
            show,
            cmap="YlOrRd",
            vmin=0.0,
            vmax=1.0,
            extent=(west, east, south, north),
            interpolation="nearest",
            origin="upper",
        )
        office_id = site.get("office_parcel_id")
        for feat in site_features.get(name, []):
            geom = feat.get("geometry")
            if not geom:
                continue
            g5070 = shape(transform_geom("EPSG:4326", crs, geom))
            parts = [g5070] if g5070.geom_type == "Polygon" else list(getattr(g5070, "geoms", []))
            bold = _parcel_id(feat.get("properties")) == office_id
            for part in parts:
                if part.is_empty or part.geom_type != "Polygon":
                    continue
                xs, ys = part.exterior.xy
                ax.add_patch(
                    MplPoly(
                        list(zip(xs, ys, strict=False)),
                        fill=False,
                        edgecolor="#1b7f3a" if bold else "#6aa87a",
                        lw=1.6 if bold else 0.6,
                        zorder=4,
                    )
                )
        yy, xx = np.mgrid[r0:r1, c0:c1]
        mapped = (zw == ZONE_SFHA) | (zw == ZONE_FLOODWAY)
        if mapped.any():
            xs = transform.c + (xx[mapped] + 0.5) * transform.a
            ys = transform.f + (yy[mapped] + 0.5) * transform.e
            ax.plot(xs, ys, ",", color="#7a1010", alpha=0.4, zorder=3)
        ox = transform.c + (ocol + 0.5) * transform.a
        oy = transform.f + (orow + 0.5) * transform.e
        mx = transform.c + (ocol + dc + 0.5) * transform.a
        my = transform.f + (orow + dr + 0.5) * transform.e
        ax.plot([ox, mx], [oy, my], color="#111111", lw=1.0, zorder=5)
        ax.plot(ox, oy, marker="o", color="#2166ac", ms=7, markeredgecolor="white", zorder=6)
        ax.plot(mx, my, marker="s", color="#ffff33", ms=7, markeredgecolor="black", zorder=6)
        cell = abs(transform.a)
        ax.add_patch(
            Rectangle(
                (ox - (radius + 0.5) * cell, oy - (radius + 0.5) * abs(transform.e)),
                (2 * radius + 1) * cell,
                (2 * radius + 1) * abs(transform.e),
                fill=False,
                edgecolor="#111111",
                lw=0.8,
                zorder=4,
            )
        )
        ax.set_title(f"{title}\n{site['reading']}", fontsize=8)
        ax.tick_params(labelsize=6)
        ax.ticklabel_format(useOffset=False, style="plain")
        ax.set_aspect("equal")
    fig.suptitle(f"Five-site parcels on calibrated {P_DEFINITION}", fontsize=11)
    fig.tight_layout()
    dest.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(dest, dpi=130)
    plt.close(fig)
    return titles


def run_five_site_parcels(
    *,
    interim_dir: Path,
    facilities_csv: Path,
    headline_csv: Path,
    out_dir: Path,
    get_json: GetJson | None = None,
    layer_url: str = PARCEL_LAYER_URL,
) -> dict[str, Any]:
    p_path = interim_dir / P_SFHA_CALIBRATED_NAME
    if not p_path.is_file():
        raise GateError(f"parcels need {P_SFHA_CALIBRATED_NAME}")
    with rasterio.open(p_path) as src:
        p = src.read(1)
        p_crs = src.crs
        p_tf = src.transform
        p_nod = src.nodata if src.nodata is not None else P_SFHA_NODATA
    with rasterio.open(interim_dir / "zone_class.tif") as src:
        zone = src.read(1)
    facilities = list(csv.DictReader(facilities_csv.open(encoding="utf-8")))
    headline = list(csv.DictReader(headline_csv.open(encoding="utf-8")))
    fac = {r["name"]: r for r in facilities}
    head = {r["name"]: r for r in headline}
    names = [n for n in HEADLINE_ORDER if n in head]
    if len(names) != 5:
        raise GateError("parcels run is the five Table 1 sites only")
    site_features: dict[str, list[dict[str, Any]]] = {}
    rows: list[dict[str, Any]] = []
    collection: list[dict[str, Any]] = []
    for name in names:
        rec = fac[name]
        lon, lat = float(rec["lon"]), float(rec["lat"])
        feats = query_parcels_envelope(lon, lat, get_json=get_json, layer_url=layer_url)
        site_features[name] = feats
        row = classify_site(
            name=name,
            lon=lon,
            lat=lat,
            headline=head[name],
            features=feats,
            transform=p_tf,
            crs=p_crs,
        )
        rows.append(row)
        for feat in feats:
            props = dict(feat.get("properties") or {})
            props["site"] = name
            props["p_mean"] = row["p_mean"]
            collection.append({"type": "Feature", "geometry": feat["geometry"], "properties": props})
    out_dir.mkdir(parents=True, exist_ok=True)
    png = out_dir / "zooms_parcels.png"
    titles = write_parcel_zooms(
        p=p,
        zone=zone,
        transform=p_tf,
        crs=p_crs,
        facilities=facilities,
        headline=headline,
        site_features=site_features,
        site_rows=rows,
        dest=png,
        p_nodata=p_nod,
    )
    geojson = {
        "type": "FeatureCollection",
        "features": collection,
        "properties": {"source": PARCEL_SOURCE, "n_sites": 5},
    }
    gj_path = out_dir / "five_sites.geojson"
    gj_path.write_text(json.dumps(geojson) + "\n", encoding="utf-8")
    require_clean(gj_path.read_text(encoding="utf-8"), source=str(gj_path))
    caption = (
        "Five-site Indiana 2025 parcels (GIS Data Harvest). Snap 30 m (one cell). "
        "Does not rewrite D tables. Adjacent hydro is tighter when the window-max cell "
        "is off the office parcel. "
        + " ".join(f"{r['name']} p_mean {r['p_mean']:.3f}: {r['reading']}." for r in rows)
    )
    report = {
        "source": PARCEL_SOURCE,
        "layer_url": layer_url,
        "snap_m": PARCEL_SNAP_M,
        "window_m": PARCEL_WINDOW_M,
        "n_sites": 5,
        "d_tables_rewritten": False,
        "raw_p_sampled": False,
        "p_source": P_SFHA_CALIBRATED_NAME,
        "sites": rows,
        "zoom_titles": titles,
        "zooms_png": png.name,
        "geojson": "five_sites.geojson",
        "caption": caption,
        "user_agent": USER_AGENT,
    }
    require_clean(caption, source="parcels caption")
    hits = scan_obj(report)
    if hits:
        raise GateError(f"parcels claim scan {hits}")
    sidecar = out_dir / "parcels.json"
    sidecar.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    require_clean(sidecar.read_text(encoding="utf-8"), source=str(sidecar))
    return report
