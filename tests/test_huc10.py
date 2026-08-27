# Copyright (c) 2026 Martial Systems LLC. All rights reserved.

import numpy as np

from floodmap.huc10 import train_test_halo
from floodmap.errors import GateError
import pytest


def test_halo_excludes_neighbor_pixel_from_train() -> None:
    huc10 = np.zeros((5, 5), dtype=np.uint16)
    huc10[:, :3] = 1
    huc10[:, 3:] = 2
    eligible = np.ones((5, 5), dtype=bool)
    train, test, halo = train_test_halo(huc10, 2, eligible)
    assert test[0, 4]
    assert not train[0, 4]
    # Column 2 is in HUC 1 but adjacent to HUC 2: halo, not train.
    assert halo[2, 2]
    assert not train[2, 2]
    assert not test[2, 2]
    # Far into HUC 1 stays train.
    assert train[2, 0]


def test_halo_rejects_id_zero() -> None:
    with pytest.raises(GateError):
        train_test_halo(np.ones((3, 3), dtype=np.uint16), 0, np.ones((3, 3), dtype=bool))
