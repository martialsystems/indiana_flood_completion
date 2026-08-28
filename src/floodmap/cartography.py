# Copyright (c) 2026 Martial Systems LLC. All rights reserved.
"""README cartography. Calibrated P only. Does not rewrite D tables."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

import numpy as np
import rasterio
from rasterio.warp import transform as rio_transform
from shapely.geometry import shape

from floodmap.claims import require_clean, scan_obj
from floodmap.codes import (
    P_DEFINITION,
    ZONE_FLOODWAY,
    ZONE_SFHA,
    ZONE_UNSHADED_X,
)
from floodmap.config import (
    D_BUFFER_RADIUS_CELLS,
    D_HEADLINE_T,
    HUC8,
    P_SFHA_CALIBRATED_NAME,
    P_SFHA_NODATA,
)
from floodmap.errors import GateError
from floodmap.map_d import _ofr_polygons

# Classified disagreement (uint8). Max-pool downsample keeps cyan threads.
CLS_OUTSIDE = 0
CLS_OTHER = 1
CLS_MAPPED_SFHA = 2
CLS_HYDRO_OUTSIDE_AE = 3

_CLS_RGB = {
    CLS_OUTSIDE: (255, 255, 255),
    CLS_OTHER: (236, 230, 214),
    CLS_MAPPED_SFHA: (139, 26, 26),
    CLS_HYDRO_OUTSIDE_AE: (0, 163, 184),
}

ZOOM_HALF_CELLS = 25
HEADLINE_ORDER = (
    "THURSDAY POOLS",
    "FGF LLC",
    "ROYAL SPA CORP",
    "LINDE GAS & EQUIPMENT",
    "MAGNA POWERTRAIN EAST",
)

CAPTION_DISAGREEMENT = (
    "Figure 1. Basin disagreement on calibrated P(sfha | hydro). "
    "Dark red: mapped SFHA and floodway. Cyan: unshaded X with calibrated P "
    f">= {D_HEADLINE_T:.2f} (same t as Table 1 window-max, pixel not plant). "
    "Pale: other interior. Cyan is map-completion on the FIRM, not a plant-level "
    "hazard list and not a 1%-annual-chance layer."
)
CAPTION_ZOOMS = (
    "Figure 2. Office point to window-max cell for the five Table 1 plants. "
    "Wash is calibrated P. Box is the 9x9 (120 m) window. Black line is office "
    "to the max cell. Adjacent-hydro notes stay footnotes; mean P is the footprint."
)
CAPTION_OFR = (
    "Figure 3. June 7-9, 2008 inundation (OFR 2008-1322) code 2 on the same HUC. "
    "Blue polygons: White River at Martinsville and unnamed tributary of Fall "
    "Creek at Paragon. Grey dots: 117 TRI office points (no names). D2 stays "
    "117 / 0. Appendix 2 is reach-scale; the industrial core is code 1."
)


def disagreement_classes(
    zone: np.ndarray,
    p: np.ndarray,
    *,
    p_nodata: float = P_SFHA_NODATA,
    t: float = D_HEADLINE_T,
) -> np.ndarray:
    """Return classified disagreement. Cyan only on unshaded_x with P >= t."""
    p_ok = np.isfinite(p) & (p != p_nodata)
    interior = zone != 255
    out = np.zeros(zone.shape, dtype=np.uint8)
    out[interior] = CLS_OTHER
    mapped = (zone == ZONE_SFHA) | (zone == ZONE_FLOODWAY)
    out[mapped] = CLS_MAPPED_SFHA
    hydro = (zone == ZONE_UNSHADED_X) & p_ok & (p >= t)
    out[hydro] = CLS_HYDRO_OUTSIDE_AE
    return out


def _maxpool(cls: np.ndarray, step: int) -> np.ndarray:
    if step <= 1:
        return cls
    h, w = cls.shape
    hs, ws = h // step, w // step
    if hs == 0 or ws == 0:
        return cls[::step, ::step]
    blocks = cls[: hs * step, : ws * step].reshape(hs, step, ws, step)
    return blocks.max(axis=(1, 3))


def _require_calibrated(interim_dir: Path) -> Path:
    p_path = interim_dir / P_SFHA_CALIBRATED_NAME
    if not p_path.is_file():
        raise GateError(f"cartography needs {P_SFHA_CALIBRATED_NAME}")
    return p_path


def _extent(transform, height: int, width: int) -> tuple[float, float, float, float]:
    west = float(transform.c)
    north = float(transform.f)
    east = west + width * float(transform.a)
    south = north + height * float(transform.e)
    return west, east, south, north


def _xy_to_rowcol(transform, x: float, y: float) -> tuple[int, int]:
    r, c = rasterio.transform.rowcol(transform, x, y)
    return int(r), int(c)


def _lonlat_xy(crs, lon: float, lat: float) -> tuple[float, float]:
    xs, ys = rio_transform("EPSG:4326", crs, [lon], [lat])
    return float(xs[0]), float(ys[0])


def _draw_ofr(ax, ofr: list[dict[str, Any]], crs) -> None:
    for feat in ofr:
        g = shape(feat["geometry"])
        parts = [g] if g.geom_type == "Polygon" else list(getattr(g, "geoms", []))
        for part in parts:
            if part.is_empty or part.geom_type != "Polygon":
                continue
            lon, lat = part.exterior.xy
            x, y = rio_transform("EPSG:4326", crs, list(lon), list(lat))
            ax.plot(x, y, color="#0033aa", lw=1.8, zorder=4)


def write_disagreement_png(
    *,
    zone: np.ndarray,
    p: np.ndarray,
    transform,
    dest: Path,
    downsample: int = 12,
    p_nodata: float = P_SFHA_NODATA,
) -> Path:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.colors import ListedColormap
    from matplotlib.patches import Patch

    cls = disagreement_classes(zone, p, p_nodata=p_nodata)
    sub = _maxpool(cls, downsample)
    west, east, south, north = _extent(transform, zone.shape[0], zone.shape[1])
    cmap = ListedColormap(
        [
            np.array(_CLS_RGB[i]) / 255.0
            for i in (CLS_OUTSIDE, CLS_OTHER, CLS_MAPPED_SFHA, CLS_HYDRO_OUTSIDE_AE)
        ]
    )
    fig, ax = plt.subplots(figsize=(8.2, 7.0), dpi=140)
    ax.imshow(
        sub,
        cmap=cmap,
        vmin=0,
        vmax=3,
        extent=(west, east, south, north),
        interpolation="nearest",
        origin="upper",
    )
    ax.set_title(f"Upper White {HUC8}: disagreement on calibrated {P_DEFINITION}")
    ax.set_xlabel("EPSG:5070 easting (m)")
    ax.set_ylabel("EPSG:5070 northing (m)")
    ax.ticklabel_format(useOffset=False, style="plain")
    ax.set_aspect("equal")
    ax.legend(
        handles=[
            Patch(facecolor=np.array(_CLS_RGB[CLS_MAPPED_SFHA]) / 255.0, label="mapped SFHA / floodway"),
            Patch(
                facecolor=np.array(_CLS_RGB[CLS_HYDRO_OUTSIDE_AE]) / 255.0,
                label=f"unshaded X, P >= {D_HEADLINE_T:.2f}",
            ),
            Patch(facecolor=np.array(_CLS_RGB[CLS_OTHER]) / 255.0, label="other interior"),
        ],
        loc="lower left",
        framealpha=0.92,
        fontsize=8,
    )
    fig.tight_layout()
    dest.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(dest, dpi=140)
    plt.close(fig)
    return dest


def write_zooms_png(
    *,
    p: np.ndarray,
    zone: np.ndarray,
    transform,
    crs,
    facilities: list[dict[str, str]],
    headline: list[dict[str, str]],
    dest: Path,
    p_nodata: float = P_SFHA_NODATA,
    half: int = ZOOM_HALF_CELLS,
) -> list[str]:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Rectangle

    fac = {r["name"]: r for r in facilities}
    by_name = {r["name"]: r for r in headline}
    names = [n for n in HEADLINE_ORDER if n in by_name] or [r["name"] for r in headline]
    if not names:
        raise GateError("zooms need headline rows")
    titles: list[str] = []
    fig, axes = plt.subplots(2, 3, figsize=(11.0, 7.4), dpi=130)
    axes_flat = list(axes.ravel())
    radius = D_BUFFER_RADIUS_CELLS
    for i, ax in enumerate(axes_flat):
        if i >= len(names):
            ax.axis("off")
            ax.set_title("Legend")
            ax.text(
                0.05,
                0.75,
                "Wash: calibrated P\nRed outline: floodway / SFHA\n"
                "Black line: office to max cell\nBox: 9x9 / 120 m window",
                transform=ax.transAxes,
                fontsize=8,
                va="top",
            )
            continue
        name = names[i]
        rec = fac.get(name) or {}
        hr = by_name[name]
        p_mean = float(hr["p_mean"])
        title = f"{name} p_mean {p_mean:.3f}"
        titles.append(title)
        note = hr.get("p_max_note") or ""
        zc = hr.get("p_max_zone_class") or ""
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
        yy, xx = np.mgrid[r0:r1, c0:c1]
        mapped = (zw == ZONE_SFHA) | (zw == ZONE_FLOODWAY)
        if mapped.any():
            xs = transform.c + (xx[mapped] + 0.5) * transform.a
            ys = transform.f + (yy[mapped] + 0.5) * transform.e
            ax.plot(xs, ys, ",", color="#7a1010", alpha=0.45, zorder=3)
        ox = transform.c + (ocol + 0.5) * transform.a
        oy = transform.f + (orow + 0.5) * transform.e
        mx = transform.c + (ocol + dc + 0.5) * transform.a
        my = transform.f + (orow + dr + 0.5) * transform.e
        ax.plot([ox, mx], [oy, my], color="#111111", lw=1.0, zorder=5)
        ax.plot(ox, oy, marker="o", color="#2166ac", ms=7, markeredgecolor="white", zorder=6)
        ax.plot(mx, my, marker="s", color="#ffff33", ms=7, markeredgecolor="black", zorder=6)
        cell = abs(transform.a)
        box_w = (2 * radius + 1) * cell
        ax.add_patch(
            Rectangle(
                (ox - (radius + 0.5) * cell, oy - (radius + 0.5) * abs(transform.e)),
                box_w,
                (2 * radius + 1) * abs(transform.e),
                fill=False,
                edgecolor="#111111",
                lw=0.8,
                zorder=4,
            )
        )
        ax.set_title(f"{title}\n{note}, {zc}", fontsize=8)
        ax.tick_params(labelsize=6)
        ax.ticklabel_format(useOffset=False, style="plain")
        ax.set_aspect("equal")
    fig.suptitle(f"Office to window-max cell ({P_DEFINITION}, calibrated)", fontsize=11)
    fig.tight_layout()
    dest.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(dest, dpi=130)
    plt.close(fig)
    return titles


def write_ofr_reaches_png(
    *,
    p: np.ndarray,
    transform,
    crs,
    mask: np.ndarray,
    mask_transform,
    mask_crs,
    facilities: list[dict[str, str]],
    dest: Path,
    downsample: int = 12,
    p_nodata: float = P_SFHA_NODATA,
) -> dict[str, Any]:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    ofr = _ofr_polygons(mask, mask_transform, mask_crs)
    step = max(1, downsample)
    sub = p[::step, ::step]
    valid = np.isfinite(sub) & (sub != p_nodata)
    show = np.ma.masked_where(~valid, np.clip(sub, 0.0, 1.0))
    west, east, south, north = _extent(transform, p.shape[0], p.shape[1])
    fig, ax = plt.subplots(figsize=(8.2, 7.0), dpi=140)
    ax.imshow(
        show,
        cmap="Greys",
        vmin=0.0,
        vmax=1.0,
        extent=(west, east, south, north),
        interpolation="nearest",
        origin="upper",
        alpha=0.85,
    )
    _draw_ofr(ax, ofr, crs)
    for rec in facilities:
        lon, lat = float(rec["lon"]), float(rec["lat"])
        x, y = _lonlat_xy(crs, lon, lat)
        ax.plot(x, y, marker="o", ms=2.0, color="#888888", linestyle="None", zorder=3)
    # Indianapolis industrial core sits in mask code 1.
    ix, iy = _lonlat_xy(crs, -86.1581, 39.7684)
    ax.annotate(
        "industrial core (code 1)",
        xy=(ix, iy),
        xytext=(ix + 18000, iy + 12000),
        fontsize=8,
        color="#333333",
        arrowprops={"arrowstyle": "->", "color": "#333333", "lw": 0.8},
    )
    ax.set_title(f"Upper White {HUC8}: OFR 2008 code 2 (Martinsville, Paragon)")
    ax.set_xlabel("EPSG:5070 easting (m)")
    ax.set_ylabel("EPSG:5070 northing (m)")
    ax.ticklabel_format(useOffset=False, style="plain")
    ax.set_aspect("equal")
    fig.tight_layout()
    dest.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(dest, dpi=140)
    plt.close(fig)
    return {
        "n_ofr_polygons": len(ofr),
        "ofr_reaches": [f.get("properties", {}).get("reach") for f in ofr],
    }


def write_cartography(
    *,
    interim_dir: Path,
    facilities_csv: Path,
    headline_csv: Path,
    out_dir: Path,
    downsample: int = 12,
) -> dict[str, Any]:
    p_path = _require_calibrated(interim_dir)
    if (interim_dir / "p_sfha.tif").is_file() is False:
        # Fixture path may omit raw P. Live keeps it; this module still does not read it.
        pass
    with rasterio.open(p_path) as src:
        p = src.read(1)
        p_crs = src.crs
        p_tf = src.transform
        p_nod = src.nodata if src.nodata is not None else P_SFHA_NODATA
    with rasterio.open(interim_dir / "zone_class.tif") as src:
        zone = src.read(1)
    with rasterio.open(interim_dir / "mask_2008.tif") as src:
        mask = src.read(1)
        mask_crs = src.crs
        mask_tf = src.transform
    facilities = list(csv.DictReader(facilities_csv.open(encoding="utf-8")))
    headline = list(csv.DictReader(headline_csv.open(encoding="utf-8")))
    out_dir.mkdir(parents=True, exist_ok=True)
    disagreement = out_dir / "disagreement.png"
    zooms = out_dir / "zooms.png"
    ofr_png = out_dir / "ofr_reaches.png"
    write_disagreement_png(
        zone=zone, p=p, transform=p_tf, dest=disagreement, downsample=downsample, p_nodata=p_nod
    )
    titles = write_zooms_png(
        p=p,
        zone=zone,
        transform=p_tf,
        crs=p_crs,
        facilities=facilities,
        headline=headline,
        dest=zooms,
        p_nodata=p_nod,
    )
    ofr_info = write_ofr_reaches_png(
        p=p,
        transform=p_tf,
        crs=p_crs,
        mask=mask,
        mask_transform=mask_tf,
        mask_crs=mask_crs,
        facilities=facilities,
        dest=ofr_png,
        downsample=downsample,
        p_nodata=p_nod,
    )
    report = {
        "huc8": HUC8,
        "p_source": P_SFHA_CALIBRATED_NAME,
        "raw_p_sampled": False,
        "headline_t": D_HEADLINE_T,
        "disagreement_png": disagreement.name,
        "zooms_png": zooms.name,
        "ofr_reaches_png": ofr_png.name,
        "zoom_titles": titles,
        "caption_disagreement": CAPTION_DISAGREEMENT,
        "caption_zooms": CAPTION_ZOOMS,
        "caption_ofr": CAPTION_OFR,
        **ofr_info,
    }
    for cap in (CAPTION_DISAGREEMENT, CAPTION_ZOOMS, CAPTION_OFR, "\n".join(titles)):
        require_clean(cap, source="cartography caption")
    hits = scan_obj(report)
    if hits:
        raise GateError(f"cartography claim scan {hits}")
    sidecar = out_dir / "cartography.json"
    sidecar.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    require_clean(sidecar.read_text(encoding="utf-8"), source=str(sidecar))
    return report
