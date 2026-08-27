# Copyright (c) 2026 Martial Systems LLC. All rights reserved.
"""Stage B hydrology on arrays: slope, D8, TWI, flow-path HAND.

HAND follows D8 flow paths to a drained stream cell. It is not Euclidean
height to the nearest painted stream pixel.
"""

from __future__ import annotations

from collections import deque
from heapq import heappop, heappush

import numpy as np
from scipy.ndimage import binary_erosion, distance_transform_edt

from floodmap.config import HYDRO_FILL_EPSILON_M, SLOPE_FLOOR_RAD
from floodmap.errors import GateError

# D8: N, NE, E, SE, S, SW, W, NW
D8_OFFSETS: tuple[tuple[int, int], ...] = (
    (-1, 0),
    (-1, 1),
    (0, 1),
    (1, 1),
    (1, 0),
    (1, -1),
    (0, -1),
    (-1, -1),
)
_SQRT2 = float(np.sqrt(2.0))
D8_WEIGHTS: tuple[float, ...] = (1.0, _SQRT2, 1.0, _SQRT2, 1.0, _SQRT2, 1.0, _SQRT2)

FLOWDIR_NODATA = np.int8(-1)
FLOWDIR_OUTLET = np.int8(-2)


def slope_radians(dem: np.ndarray, valid: np.ndarray, cellsize: float) -> np.ndarray:
    """Slope angle in radians from the display DEM (Horn-style via numpy gradient)."""
    if cellsize <= 0:
        raise GateError("cellsize must be > 0")
    fill = float(np.nanmedian(dem[valid])) if valid.any() else 0.0
    z = np.where(valid, dem.astype(np.float64, copy=False), fill)
    dz_dy, dz_dx = np.gradient(z, cellsize, cellsize)
    slope = np.arctan(np.hypot(dz_dx, dz_dy))
    slope = np.where(valid, slope, np.nan)
    return slope


def count_slope_floor(slope_rad: np.ndarray, valid: np.ndarray, floor_rad: float) -> int:
    hit = valid & np.isfinite(slope_rad) & (slope_rad < floor_rad)
    return int(hit.sum())


def burn_dem(
    dem: np.ndarray,
    burn_mask: np.ndarray,
    *,
    depth_m: float,
    valid: np.ndarray,
) -> np.ndarray:
    out = dem.astype(np.float64, copy=True)
    out[burn_mask & valid] = out[burn_mask & valid] - float(depth_m)
    return out


def priority_flood_fill(
    dem: np.ndarray,
    valid: np.ndarray,
    *,
    seed_mask: np.ndarray | None = None,
    epsilon: float = HYDRO_FILL_EPSILON_M,
) -> np.ndarray:
    """Fill depressions. Stream/waterbody seeds stay at burned elevation."""
    h, w = dem.shape
    filled = dem.astype(np.float64, copy=True)
    visited = np.zeros((h, w), dtype=bool)
    visited[~valid] = True
    interior = binary_erosion(valid, structure=np.ones((3, 3), dtype=bool))
    seeds = valid & ~interior
    if seed_mask is not None:
        seeds = seeds | (seed_mask & valid)
    heap: list[tuple[float, int, int]] = []
    ctr = 0
    ys, xs = np.where(seeds)
    for i, j in zip(ys.tolist(), xs.tolist()):
        heappush(heap, (float(filled[i, j]), ctr, i * w + j))
        ctr += 1
        visited[i, j] = True
    while heap:
        z, _, idx = heappop(heap)
        i, j = divmod(idx, w)
        for di, dj in D8_OFFSETS:
            ni = i + di
            nj = j + dj
            if ni < 0 or nj < 0 or ni >= h or nj >= w or visited[ni, nj]:
                continue
            visited[ni, nj] = True
            nz = float(filled[ni, nj])
            if nz < z + epsilon:
                filled[ni, nj] = z + epsilon
            heappush(heap, (float(filled[ni, nj]), ctr, ni * w + nj))
            ctr += 1
    return filled


def d8_flowdir(filled: np.ndarray, valid: np.ndarray, cellsize: float) -> np.ndarray:
    """Steepest-descent D8. Outlets (no downhill neighbor) are FLOWDIR_OUTLET."""
    h, w = filled.shape
    best_drop = np.full((h, w), -np.inf, dtype=np.float64)
    best_dir = np.full((h, w), int(FLOWDIR_OUTLET), dtype=np.int8)
    for k, ((di, dj), weight) in enumerate(zip(D8_OFFSETS, D8_WEIGHTS)):
        dist = weight * cellsize
        ti = slice(max(0, -di), h - max(0, di))
        tj = slice(max(0, -dj), w - max(0, dj))
        si = slice(max(0, di), h + min(0, di))
        sj = slice(max(0, dj), w + min(0, dj))
        drop = (filled[ti, tj] - filled[si, sj]) / dist
        ok = valid[ti, tj] & valid[si, sj] & (drop > best_drop[ti, tj])
        best_drop[ti, tj] = np.where(ok, drop, best_drop[ti, tj])
        best_dir[ti, tj] = np.where(ok, np.int8(k), best_dir[ti, tj])
    best_dir = np.where(best_drop > 0, best_dir, FLOWDIR_OUTLET)
    best_dir = np.where(valid, best_dir, FLOWDIR_NODATA)
    return best_dir.astype(np.int8, copy=False)


def _downstream_index(flowdir: np.ndarray, valid: np.ndarray) -> np.ndarray:
    h, w = flowdir.shape
    down = np.full(h * w, -1, dtype=np.int32)
    for k, (di, dj) in enumerate(D8_OFFSETS):
        sel = (flowdir == k) & valid
        ys, xs = np.where(sel)
        if ys.size == 0:
            continue
        ni = ys + di
        nj = xs + dj
        ok = (ni >= 0) & (nj >= 0) & (ni < h) & (nj < w) & valid[ni, nj]
        down[ys[ok] * w + xs[ok]] = ni[ok] * w + nj[ok]
    return down


def _reverse_csr(down: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    n = int(down.size)
    valid_down = down >= 0
    counts = np.zeros(n, dtype=np.int32)
    np.add.at(counts, down[valid_down], 1)
    ptr = np.zeros(n + 1, dtype=np.int32)
    np.cumsum(counts, out=ptr[1:])
    adj = np.empty(int(ptr[-1]), dtype=np.int32)
    cursor = ptr[:-1].copy()
    for i in np.flatnonzero(valid_down):
        d = int(down[i])
        adj[cursor[d]] = i
        cursor[d] += 1
    return ptr, adj


def flow_accumulation(flowdir: np.ndarray, valid: np.ndarray) -> np.ndarray:
    """D8 contributing cell count (not including the cell itself)."""
    h, w = flowdir.shape
    n = h * w
    down = _downstream_index(flowdir, valid)
    ptr, adj = _reverse_csr(down)
    incoming = np.zeros(n, dtype=np.int32)
    np.add.at(incoming, down[down >= 0], 1)
    acc = np.zeros(n, dtype=np.float64)
    q: deque[int] = deque(int(i) for i in np.flatnonzero((incoming == 0) & valid.ravel()))
    remaining = incoming.copy()
    seen = np.zeros(n, dtype=bool)
    while q:
        i = q.popleft()
        if seen[i]:
            continue
        seen[i] = True
        d = int(down[i])
        if d >= 0:
            acc[d] += acc[i] + 1.0
            remaining[d] -= 1
            if remaining[d] == 0:
                q.append(d)
    return acc.reshape(h, w)


def specific_catchment_area(acc: np.ndarray, cellsize: float) -> np.ndarray:
    """α = A / w with A = (acc+1) cellarea and w = cellsize, so α = (acc+1)*cellsize."""
    return (acc + 1.0) * float(cellsize)


def topographic_wetness(
    acc: np.ndarray,
    slope_rad: np.ndarray,
    cellsize: float,
    *,
    floor_rad: float = SLOPE_FLOOR_RAD,
    valid: np.ndarray | None = None,
) -> tuple[np.ndarray, int]:
    """TWI = ln(α / tan β). Floor β at floor_rad. No inf on valid cells."""
    n_floor = count_slope_floor(
        slope_rad, valid if valid is not None else np.isfinite(slope_rad), floor_rad
    )
    beta = np.maximum(slope_rad, floor_rad)
    tanb = np.tan(beta)
    sca = specific_catchment_area(acc, cellsize)
    with np.errstate(divide="ignore", invalid="ignore"):
        twi = np.log(sca / tanb)
    if valid is not None:
        twi = np.where(valid, twi, np.nan)
    return twi, n_floor


def hand_along_flow(
    z_surface: np.ndarray,
    flowdir: np.ndarray,
    stream: np.ndarray,
    valid: np.ndarray,
) -> np.ndarray:
    """Height above the drained stream cell along D8, using z_surface (raw DEM)."""
    h, w = z_surface.shape
    n = h * w
    down = _downstream_index(flowdir, valid)
    ptr, adj = _reverse_csr(down)
    flat_z = z_surface.astype(np.float64, copy=False).ravel()
    stream_z = np.full(n, np.nan, dtype=np.float64)
    flat_stream = np.asarray(stream, dtype=bool).ravel()
    flat_valid = np.asarray(valid, dtype=bool).ravel()
    seeds = np.flatnonzero(flat_stream & flat_valid)
    stream_z[seeds] = flat_z[seeds]
    seen = np.zeros(n, dtype=bool)
    seen[seeds] = True
    q: deque[int] = deque(int(i) for i in seeds)
    while q:
        i = q.popleft()
        for up in adj[ptr[i] : ptr[i + 1]]:
            if seen[up] or not flat_valid[up]:
                continue
            stream_z[up] = stream_z[i]
            seen[up] = True
            q.append(int(up))
    delta = flat_z - stream_z
    # Height above the drained stream. Burned D8 can route slightly uphill on the raw DEM.
    hand = np.where(np.isfinite(delta), np.maximum(delta, 0.0), np.nan).reshape(h, w)
    return hand


def euclidean_distance_m(mask: np.ndarray, cellsize: float) -> np.ndarray:
    """Euclidean distance in metres to True cells."""
    if not np.asarray(mask, dtype=bool).any():
        raise GateError("distance mask is empty")
    dist = distance_transform_edt(~np.asarray(mask, dtype=bool)) * float(cellsize)
    return dist.astype(np.float64, copy=False)


def require_finite_twi(twi: np.ndarray, valid: np.ndarray) -> None:
    subset = twi[valid]
    if subset.size == 0:
        raise GateError("TWI has no valid interior cells")
    if not np.isfinite(subset).all():
        n_bad = int((~np.isfinite(subset)).sum())
        raise GateError(f"TWI has {n_bad} non-finite interior cells")
