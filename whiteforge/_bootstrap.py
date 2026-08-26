# Copyright (c) 2026 Martial Systems LLC. All rights reserved.
"""Put GraphForge + this repo on sys.path. Sibling clone, no pip required."""

from __future__ import annotations

import sys
from pathlib import Path

WHITEFORGE_ROOT = Path(__file__).resolve().parent
REPO = WHITEFORGE_ROOT.parent
GRAPHFORGE_CANDIDATES = [
    Path.home() / "graphforge",
    REPO.parent / "graphforge",
]


def ensure_paths() -> Path:
    """Return GraphForge root. Raise if the engine checkout is missing."""
    for p in (WHITEFORGE_ROOT, REPO, REPO / "src"):
        s = str(p)
        if s not in sys.path:
            sys.path.insert(0, s)

    for gf in GRAPHFORGE_CANDIDATES:
        src = gf / "src"
        if src.is_dir():
            if str(src) not in sys.path:
                sys.path.insert(0, str(src))
            return gf

    try:
        import graphforge  # noqa: F401

        return Path(graphforge.__file__).resolve().parents[1]
    except ImportError as exc:
        raise FileNotFoundError(
            "GraphForge not found. Clone martialsystems/graphforge to ~/graphforge."
        ) from exc
