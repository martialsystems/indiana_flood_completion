# Copyright (c) 2026 Martial Systems LLC. All rights reserved.

import pytest

from floodmap.crs import require_epsg
from floodmap.errors import CrsMismatchError, CrsMissingError


def test_require_epsg_ok() -> None:
    assert require_epsg(5070, expected=5070) == 5070


def test_require_epsg_missing() -> None:
    with pytest.raises(CrsMissingError):
        require_epsg(None)


def test_require_epsg_mismatch() -> None:
    with pytest.raises(CrsMismatchError):
        require_epsg(4269, expected=5070)
