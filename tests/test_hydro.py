# Copyright (c) 2026 Martial Systems LLC. All rights reserved.

import numpy as np

from floodmap.config import SLOPE_FLOOR_RAD
from floodmap.hydro import (
    D8_OFFSETS,
    FLOWDIR_OUTLET,
    burn_dem,
    count_slope_floor,
    d8_flowdir,
    euclidean_distance_m,
    flow_accumulation,
    hand_along_flow,
    priority_flood_fill,
    require_finite_twi,
    slope_radians,
    topographic_wetness,
)


def test_hand_clamps_below_stream_to_zero() -> None:
    z = np.array([[0.0, 5.0], [3.0, 5.0]], dtype=np.float64)
    valid = np.ones_like(z, dtype=bool)
    east = next(i for i, off in enumerate(D8_OFFSETS) if off == (0, 1))
    flow = np.full(z.shape, east, dtype=np.int8)
    flow[:, 1] = FLOWDIR_OUTLET
    stream = np.zeros_like(z, dtype=bool)
    stream[:, 1] = True
    hand = hand_along_flow(z, flow, stream, valid)
    assert hand[0, 0] == 0.0
    assert hand[1, 0] == 0.0
    assert hand[0, 1] == 0.0


def test_slope_floor_counts_till_plain() -> None:
    dem = np.full((8, 8), 200.0)
    valid = np.ones((8, 8), dtype=bool)
    slp = slope_radians(dem, valid, 30.0)
    n_floor = count_slope_floor(slp, valid, SLOPE_FLOOR_RAD)
    assert n_floor == 64
    twi, logged = topographic_wetness(np.zeros((8, 8)), slp, 30.0, valid=valid)
    assert logged == 64
    assert np.isfinite(twi).all()


def test_hand_follows_flow_not_euclidean() -> None:
    """Ridge: Euclidean nearest stream is the left channel; D8 drains south."""
    z = np.array(
        [
            [1.0, 8.0, 20.0, 8.0, 10.0, 10.0, 10.0],
            [1.0, 8.0, 20.0, 8.0, 9.0, 9.0, 9.0],
            [1.0, 8.0, 20.0, 8.0, 8.0, 8.0, 8.0],
            [1.0, 8.0, 20.0, 8.0, 7.0, 7.0, 7.0],
            [1.0, 8.0, 20.0, 8.0, 6.0, 6.0, 6.0],
            [1.0, 8.0, 20.0, 8.0, 5.0, 5.0, 5.0],
            [1.0, 8.0, 20.0, 8.0, 4.0, 4.0, 4.0],
        ],
        dtype=np.float64,
    )
    valid = np.ones_like(z, dtype=bool)
    south = next(i for i, off in enumerate(D8_OFFSETS) if off == (1, 0))
    west = next(i for i, off in enumerate(D8_OFFSETS) if off == (0, -1))
    flow = np.full(z.shape, south, dtype=np.int8)
    flow[:, 0] = FLOWDIR_OUTLET
    flow[6, :] = FLOWDIR_OUTLET
    flow[0:6, 1] = west
    stream = np.zeros_like(z, dtype=bool)
    stream[:, 0] = True
    stream[6, 4:] = True
    hand = hand_along_flow(z, flow, stream, valid)
    # (0,5) flows south to stream z=4, not west to stream z=1.
    assert hand[0, 5] == 6.0
    euc_nearest_left = z[0, 5] - z[0, 0]
    assert euc_nearest_left == 9.0
    assert hand[0, 5] != euc_nearest_left
    assert hand[0, 0] == 0.0
    assert hand[6, 5] == 0.0
    assert np.nanmin(hand) >= 0.0


def test_toy_watershed_twi_finite_hand_zero_on_stream() -> None:
    h, w = 16, 16
    dem = np.zeros((h, w), dtype=np.float64)
    for r in range(h):
        dem[r, :] = 30.0 - r
    valid = np.ones((h, w), dtype=bool)
    stream = np.zeros((h, w), dtype=bool)
    stream[-1, :] = True
    slp = slope_radians(dem, valid, 30.0)
    burned = burn_dem(dem, stream, depth_m=5.0, valid=valid)
    filled = priority_flood_fill(burned, valid, seed_mask=stream)
    flow = d8_flowdir(filled, valid, 30.0)
    acc = flow_accumulation(flow, valid)
    twi, n_floor = topographic_wetness(acc, slp, 30.0, valid=valid)
    require_finite_twi(twi, valid)
    hand = hand_along_flow(dem, flow, stream, valid)
    dist = euclidean_distance_m(stream, 30.0)
    assert np.isfinite(twi[valid]).all()
    assert np.all(hand[stream] == 0.0)
    assert hand[0, 8] > hand[8, 8] > 0
    assert dist[-1, 5] == 0.0
    assert dist[-2, 5] == 30.0
    assert n_floor >= 0
    # South-draining interior cells, not the stream row.
    assert np.all(flow[:-1, 1:-1] == next(i for i, o in enumerate(D8_OFFSETS) if o == (1, 0)))
