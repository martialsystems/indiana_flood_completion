# Copyright (c) 2026 Martial Systems LLC. All rights reserved.
"""Download USGS WBD HUC-8 and MRLC NLCD 2021 impervious (injectable HTTP)."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Callable, Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

from floodmap.config import (
    HUC8,
    NLCD_LAYER,
    NLCD_TILE_PX,
    NLCD_WMS_URL,
    NLCD_WMS_VERSION,
    TEMPLATE_CRS,
    TEMPLATE_RES_M,
    USER_AGENT,
    VECTOR_CRS,
    WBD_GEOMETRY_PRECISION,
    WBD_LAYER_URL,
    WBD_MAX_ALLOWABLE_OFFSET_DEG,
)
from floodmap.errors import CrsMissingError, EmptyHucError, FetchError, GateError

GetJson = Callable[[str], dict[str, Any]]
GetBytes = Callable[[str], bytes]


def _request(url: str, *, timeout: int) -> bytes:
    req = Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urlopen(req, timeout=timeout) as resp:
            return resp.read()
    except (HTTPError, URLError, TimeoutError) as exc:
        raise FetchError(f"GET failed: {url}: {exc}") from exc


def default_get_json(url: str, *, timeout: int = 90) -> dict[str, Any]:
    raw = _request(url, timeout=timeout)
    try:
        doc = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise FetchError(f"not JSON: {url}") from exc
    if not isinstance(doc, dict):
        raise FetchError(f"JSON object required: {url}")
    return doc


def default_get_bytes(url: str, *, timeout: int = 120) -> bytes:
    return _request(url, timeout=timeout)


def default_post_json(url: str, fields: dict[str, str], *, timeout: int = 120) -> dict[str, Any]:
    body = urlencode(fields).encode("utf-8")
    req = Request(
        url,
        data=body,
        headers={"User-Agent": USER_AGENT, "Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    try:
        with urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
    except (HTTPError, URLError, TimeoutError) as exc:
        raise FetchError(f"POST failed: {url}: {exc}") from exc
    try:
        doc = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise FetchError(f"POST not JSON: {url}") from exc
    if not isinstance(doc, dict):
        raise FetchError(f"POST JSON object required: {url}")
    return doc


def _layer_wkid(meta: dict[str, Any]) -> int | None:
    extent = meta.get("extent") or {}
    sr = (
        extent.get("spatialReference")
        or meta.get("sourceSpatialReference")
        or meta.get("spatialReference")
        or {}
    )
    wkid = sr.get("latestWkid") or sr.get("wkid")
    try:
        return int(wkid) if wkid is not None else None
    except (TypeError, ValueError):
        return None


def wbd_query_url(
    *,
    huc8: str = HUC8,
    out_sr: int = VECTOR_CRS,
    max_allowable_offset: float = WBD_MAX_ALLOWABLE_OFFSET_DEG,
) -> str:
    where = f"huc8='{huc8}'"
    return (
        f"{WBD_LAYER_URL}/query"
        f"?where={quote(where)}"
        f"&outFields=huc8,name,states,areasqkm"
        f"&returnGeometry=true"
        f"&outSR={out_sr}"
        f"&maxAllowableOffset={max_allowable_offset}"
        f"&geometryPrecision={WBD_GEOMETRY_PRECISION}"
        f"&f=geojson"
    )


def fetch_wbd_doc(
    get_json: GetJson,
    *,
    huc8: str = HUC8,
) -> tuple[int, dict[str, Any]]:
    meta = get_json(f"{WBD_LAYER_URL}?f=pjson")
    if meta.get("error"):
        raise FetchError(f"WBD layer error: {meta['error']}")
    native = _layer_wkid(meta)
    if native is None:
        raise CrsMissingError("WBD MapServer/4 has no spatialReference")
    doc = get_json(wbd_query_url(huc8=huc8))
    if doc.get("error"):
        raise FetchError(f"WBD query error: {doc['error']}")
    features = doc.get("features") or []
    if not features:
        raise EmptyHucError(f"WBD query returned no features for {huc8}")
    props = features[0].get("properties") or {}
    got = str(props.get("huc8") or props.get("HUC8") or "")
    if got != huc8:
        raise EmptyHucError(f"WBD huc8={got!r} != {huc8!r}")
    crs_name = ((doc.get("crs") or {}).get("properties") or {}).get("name") or ""
    if "4269" not in str(crs_name) and "EPSG:4269" not in str(crs_name):
        doc.setdefault(
            "crs",
            {"type": "name", "properties": {"name": f"EPSG:{VECTOR_CRS}", "wkid": VECTOR_CRS}},
        )
    return VECTOR_CRS, doc


def write_wbd_geojson(dest: Path, *, wkid: int, doc: dict[str, Any]) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if "crs" not in doc:
        doc = {
            **doc,
            "crs": {
                "type": "name",
                "properties": {"name": f"EPSG:{wkid}", "wkid": wkid},
            },
        }
    dest.write_text(json.dumps(doc), encoding="utf-8")
    return dest


def fetch_wbd(
    raw_dir: Path,
    *,
    get_json: GetJson | None = None,
    huc8: str = HUC8,
) -> Path:
    getter = get_json or default_get_json
    wkid, doc = fetch_wbd_doc(getter, huc8=huc8)
    dest = raw_dir / f"huc{huc8}.geojson"
    return write_wbd_geojson(dest, wkid=wkid, doc=doc)


def snap_bounds(
    minx: float,
    miny: float,
    maxx: float,
    maxy: float,
    *,
    res: float = TEMPLATE_RES_M,
    pad_px: int = 1,
) -> tuple[float, float, float, float, int, int]:
    west = math.floor(minx / res) * res - pad_px * res
    south = math.floor(miny / res) * res - pad_px * res
    east = math.ceil(maxx / res) * res + pad_px * res
    north = math.ceil(maxy / res) * res + pad_px * res
    width = int(round((east - west) / res))
    height = int(round((north - south) / res))
    if width < 2 or height < 2:
        raise GateError(f"snapped NLCD window too small: {width}x{height}")
    return west, south, east, north, width, height


def iter_tiles(
    west: float,
    south: float,
    east: float,
    north: float,
    *,
    res: float = TEMPLATE_RES_M,
    tile_px: int = NLCD_TILE_PX,
) -> Iterable[tuple[float, float, float, float, int, int]]:
    width = int(round((east - west) / res))
    height = int(round((north - south) / res))
    for row0 in range(0, height, tile_px):
        h = min(tile_px, height - row0)
        for col0 in range(0, width, tile_px):
            w = min(tile_px, width - col0)
            tw = west + col0 * res
            tn = north - row0 * res
            te = tw + w * res
            ts = tn - h * res
            yield tw, ts, te, tn, w, h


def nlcd_wms_url(
    *,
    west: float,
    south: float,
    east: float,
    north: float,
    width: int,
    height: int,
    layer: str = NLCD_LAYER,
    crs: int = TEMPLATE_CRS,
) -> str:
    params = {
        "SERVICE": "WMS",
        "VERSION": NLCD_WMS_VERSION,
        "REQUEST": "GetMap",
        "LAYERS": layer,
        "CRS": f"EPSG:{crs}",
        "BBOX": f"{west},{south},{east},{north}",
        "WIDTH": str(width),
        "HEIGHT": str(height),
        "FORMAT": "image/geotiff",
        "STYLES": "",
    }
    return f"{NLCD_WMS_URL}?{urlencode(params)}"


def _require_geotiff(payload: bytes, *, url: str) -> bytes:
    if payload[:4] in (b"II*\x00", b"MM\x00*") or payload[:4] == b"\x49\x49\x2a\x00":
        return payload
    head = payload[:200].lstrip()
    if head.startswith(b"<") or b"ServiceException" in payload[:400]:
        raise FetchError(f"NLCD WMS exception: {url}: {payload[:300]!r}")
    raise FetchError(f"NLCD WMS did not return GeoTIFF: {url}")


def fetch_nlcd_tile_bytes(
    get_bytes: GetBytes,
    *,
    west: float,
    south: float,
    east: float,
    north: float,
    width: int,
    height: int,
) -> bytes:
    url = nlcd_wms_url(
        west=west, south=south, east=east, north=north, width=width, height=height
    )
    return _require_geotiff(get_bytes(url), url=url)
