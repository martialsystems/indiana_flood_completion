# Copyright (c) 2026 Martial Systems LLC. All rights reserved.

import json
from pathlib import Path

import pytest

from floodmap.config import (
    FROZEN_N_IN_SFHA,
    FROZEN_N_TRIS_JOINABLE,
    FROZEN_OCCUPANCY_PATH,
    FROZEN_SHARE_IN_SFHA,
)
from floodmap.errors import FreezeError
from floodmap.freeze import load_freeze, verify_freeze


def test_committed_freeze_matches_lock() -> None:
    packet = verify_freeze()
    assert packet["n_tris_joinable"] == FROZEN_N_TRIS_JOINABLE
    assert packet["n_in_sfha"] == FROZEN_N_IN_SFHA
    assert round(float(packet["share_in_sfha"]), 6) == FROZEN_SHARE_IN_SFHA
    assert FROZEN_OCCUPANCY_PATH.is_file()


def test_freeze_rejects_rewritten_count(tmp_path: Path) -> None:
    src = json.loads(FROZEN_OCCUPANCY_PATH.read_text(encoding="utf-8"))
    src["n_in_sfha"] = 999
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps(src), encoding="utf-8")
    with pytest.raises(FreezeError, match="n_in_sfha"):
        verify_freeze(path=bad)


def test_load_freeze_missing(tmp_path: Path) -> None:
    with pytest.raises(FreezeError, match="missing"):
        load_freeze(tmp_path / "nope.json")
