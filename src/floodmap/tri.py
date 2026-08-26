# Copyright (c) 2026 Martial Systems LLC. All rights reserved.
"""TRI Form R on-site releases for a tagged year, clipped to the HUC."""

from __future__ import annotations

import csv
import io
import json
import zipfile
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from shapely.geometry import Point

from floodmap.config import (
    FRS_CSV_NAME,
    FRS_URL,
    HUC8,
    STATE_CODE,
    TRI_PROGRAM,
    TRI_YEAR_CANDIDATES,
)
from floodmap.errors import FetchError, GateError
from floodmap.fetch import GetBytes, default_get_bytes
from floodmap.huc import HucLayer
from floodmap.template import huc_geom_5070
from rasterio.warp import transform as warp_xy
from rasterio.crs import CRS

from floodmap.config import TEMPLATE_CRS, VECTOR_CRS


def _col(row: dict, *needles: str) -> str:
    upper = {str(k).upper().strip(): k for k in row}
    for needle in needles:
        n = needle.upper().strip()
        if n in upper:
            val = row.get(upper[n])
            return "" if val is None else str(val).strip()
    for needle in needles:
        n = needle.upper().strip()
        if len(n) < 4:
            continue
        for uk, orig in upper.items():
            if n in uk.replace(".", " "):
                val = row.get(orig)
                return "" if val is None else str(val).strip()
    return ""


def _float(text) -> float | None:
    if isinstance(text, (int, float)) and not isinstance(text, bool):
        return float(text)
    t = str(text or "").replace(",", "").strip()
    if not t or t.upper() in {"NA", "NONE", "NULL"}:
        return None
    try:
        return float(t)
    except ValueError:
        return None


def parse_tri_1a(
    text: str,
    *,
    year: int,
) -> tuple[dict[str, dict], dict[str, int]]:
    """Aggregate on-site release lb by facility key (frs or trifd)."""
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise GateError("TRI 1a csv has no header")
    by_fac: dict[str, dict] = {}
    n_rows = 0
    n_in = 0
    n_dioxin = 0
    n_off = 0
    n_missing_xy = 0
    n_non_in = 0
    for row in reader:
        n_rows += 1
        st = _col(row, "5. ST", "ST", "STATE").upper()
        if st and st != STATE_CODE:
            n_non_in += 1
            continue
        n_in += 1
        unit = _col(row, "UNIT OF MEASURE", "UNIT").upper()
        chem = _col(row, "CHEMICAL", "CHEMICAL NAME").upper()
        onsite = _float(_col(row, "ON-SITE RELEASE TOTAL", "ONSITE RELEASE TOTAL"))
        offsite = _float(_col(row, "OFF-SITE RELEASE TOTAL", "OFFSITE RELEASE TOTAL"))
        if offsite and offsite != 0.0:
            n_off += 1
        dioxin = "DIOXIN" in chem or unit in {"GRAMS", "G"}
        if dioxin:
            n_dioxin += 1
            lb = 0.0
        else:
            lb = onsite or 0.0
        lat = _float(_col(row, "LATITUDE", "LATITUDE83"))
        lon = _float(_col(row, "LONGITUDE", "LONGITUDE83"))
        if lat is None or lon is None:
            n_missing_xy += 1
            continue
        frs = _col(row, "FRS ID", "FRS_ID", "REGISTRY")
        trifd = _col(row, "TRIFD", "TRIFID", "TRI FACILITY ID")
        key = frs or trifd or f"{lat:.5f},{lon:.5f}"
        name = _col(row, "FACILITY NAME", "PRIMARY_NAME")
        rec = by_fac.setdefault(
            key,
            {
                "key": key,
                "frs": frs,
                "trifd": trifd,
                "name": name,
                "lat": lat,
                "lon": lon,
                "state": st or STATE_CODE,
                "on_site_release_lb": 0.0,
                "n_chem": 0,
                "year": year,
            },
        )
        rec["on_site_release_lb"] += lb
        rec["n_chem"] += 1
    budget = {
        "n_1a_rows": n_rows,
        "n_1a_in": n_in,
        "n_dropped_missing_xy": n_missing_xy,
        "n_dropped_non_in": n_non_in,
        "n_dioxin_rows_held_grams": n_dioxin,
        "n_excluded_off_site": n_off,
        "reporting_year": year,
    }
    return by_fac, budget


def clip_to_huc(facilities: Iterable[dict], huc: HucLayer) -> tuple[list[dict], int]:
    kept: list[dict] = []
    n_out = 0
    for rec in facilities:
        pt = Point(rec["lon"], rec["lat"])
        if huc.geom.covers(pt) or huc.geom.intersects(pt):
            rec = dict(rec)
            rec["huc"] = huc.huc8
            rec["state"] = rec.get("state") or STATE_CODE
            kept.append(rec)
        else:
            n_out += 1
    return kept, n_out


def write_facilities_csv(path: Path, rows: list[dict]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "key",
        "frs",
        "trifd",
        "name",
        "lat",
        "lon",
        "state",
        "huc",
        "year",
        "on_site_release_lb",
        "n_chem",
    ]
    with path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for row in rows:
            w.writerow(row)
    return path


def fetch_tri_envirofacts(
    *,
    year: int,
    get_bytes: GetBytes | None = None,
    page: int = 10000,
) -> list[dict]:
    """IN-only TRI basic rows for a reporting year via Envirofacts."""
    getter = get_bytes or default_get_bytes
    rows: list[dict] = []
    start = 1
    for _ in range(20):
        url = (
            "https://data.epa.gov/efservice/MV_TRI_BASIC_DOWNLOAD/"
            f"YEAR/{year}/ST/IN/ROWS/{start}:{start + page - 1}/JSON"
        )
        payload = getter(url)
        doc = json.loads(payload.decode("utf-8"))
        if not isinstance(doc, list) or not doc:
            break
        rows.extend(doc)
        if len(doc) < page:
            break
        start += page
    if not rows:
        raise GateError(f"TRI Envirofacts empty for {year}")
    return rows


def parse_tri_json(rows: list[dict], *, year: int) -> tuple[dict[str, dict], dict[str, int]]:
    # Reuse CSV parser via a synthetic header+rows path is messy; map to the same loop
    # by building a list of dicts with string values.
    as_str = [{str(k): v for k, v in rec.items()} for rec in rows]
    # Fake a CSV so parse_tri_1a stays the single aggregator.
    if not as_str:
        raise GateError("TRI json empty")
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=list(as_str[0].keys()))
    writer.writeheader()
    for rec in as_str:
        writer.writerow({k: "" if rec.get(k) is None else rec.get(k) for k in writer.fieldnames})
    return parse_tri_1a(buf.getvalue(), year=year)


def unzip_csv(payload: bytes) -> str:
    if payload[:2] == b"PK":
        with zipfile.ZipFile(io.BytesIO(payload)) as zf:
            names = [n for n in zf.namelist() if n.lower().endswith(".csv")]
            if not names:
                raise GateError(f"no csv in TRI zip: {zf.namelist()[:8]}")
            return zf.read(names[0]).decode("utf-8", errors="replace")
    return payload.decode("utf-8", errors="replace")
