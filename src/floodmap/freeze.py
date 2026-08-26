# Copyright (c) 2026 Martial Systems LLC. All rights reserved.
"""Load and verify the imported sibling occupancy freeze."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from floodmap.config import (
    FROZEN_CRS,
    FROZEN_DATE,
    FROZEN_N_DROPPED_MISSING_XY,
    FROZEN_N_IN_SFHA,
    FROZEN_N_TRIS_JOINABLE,
    FROZEN_OCCUPANCY_PATH,
    FROZEN_SHARE_IN_SFHA,
)
from floodmap.errors import FreezeError

_REQUIRED = {
    "n_tris_joinable": FROZEN_N_TRIS_JOINABLE,
    "n_in_sfha": FROZEN_N_IN_SFHA,
    "n_dropped_missing_xy": FROZEN_N_DROPPED_MISSING_XY,
    "crs": FROZEN_CRS,
    "frozen_date": FROZEN_DATE,
}


def load_freeze(path: Path | None = None) -> dict[str, Any]:
    target = path or FROZEN_OCCUPANCY_PATH
    if not target.is_file():
        raise FreezeError(f"missing occupancy freeze: {target}")
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise FreezeError(f"corrupt occupancy freeze: {target}") from exc
    if not isinstance(data, dict):
        raise FreezeError(f"occupancy freeze is not an object: {target}")
    return data


def verify_freeze(data: dict[str, Any] | None = None, *, path: Path | None = None) -> dict[str, Any]:
    packet = data if data is not None else load_freeze(path)
    for key, expected in _REQUIRED.items():
        got = packet.get(key)
        if got != expected:
            raise FreezeError(f"freeze {key}={got!r} != {expected!r}")
    share = packet.get("share_in_sfha")
    try:
        share_f = float(share)
    except (TypeError, ValueError) as exc:
        raise FreezeError(f"freeze share_in_sfha not a number: {share!r}") from exc
    if round(share_f, 6) != FROZEN_SHARE_IN_SFHA:
        raise FreezeError(
            f"freeze share_in_sfha={share_f} != {FROZEN_SHARE_IN_SFHA}"
        )
    if packet.get("unit") != "facility":
        raise FreezeError(f"freeze unit={packet.get('unit')!r} != 'facility'")
    if packet.get("state") != "IN":
        raise FreezeError(f"freeze state={packet.get('state')!r} != 'IN'")
    return packet
