# Copyright (c) 2026 Martial Systems LLC. All rights reserved.
"""Fail closed if a report emits banned claims."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Iterable

from floodmap.errors import ClaimBanError

# Keep patterns tight so ordinary FIRM words (hazard, zone AE) are not banned.
_BANS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "casualty_count",
        re.compile(
            r"\b(deaths?|fatalit(?:y|ies)|casualt(?:y|ies)|killed|injuries)\b",
            re.I,
        ),
    ),
    (
        "climate_attribution",
        re.compile(
            r"\b(cmip\d*|downscal(?:e|ed|ing)|gcm)\b|"
            r"climate(?:\s+change)?\s+(?:made|caused|attributed)",
            re.I,
        ),
    ),
    (
        "tornado_count",
        re.compile(r"\btornado(?:es)?\s+counts?\b", re.I),
    ),
    (
        "population_at_risk",
        re.compile(
            r"\b(lives\s+at\s+risk|people\s+at\s+risk|population\s+at\s+risk)\b",
            re.I,
        ),
    ),
    (
        "tri_storage",
        re.compile(
            r"\b(chemicals?\s+stored|stored\s+annually|on-site\s+storage|"
            r"tri\s+storage)\b",
            re.I,
        ),
    ),
    (
        "p_as_100yr",
        re.compile(
            r"\b100-year\s+exceedance\b|"
            r"\bprobability of (?:a )?100-year\b|"
            r"\bP\(flood\) is the 100-year\b",
            re.I,
        ),
    ),
    (
        "unmapped_risk",
        re.compile(r"\bunmapped risk\b", re.I),
    ),
    (
        "occupancy_as_this_tree",
        re.compile(
            r"\bthis tree(?:'s)? occupancy\b|"
            r"\brecomputed occupancy\b",
            re.I,
        ),
    ),
    (
        "d2_empty_without_split",
        re.compile(r"\bno 2008 overlap\b", re.I),
    ),
)


def scan_text(text: str) -> list[str]:
    hits: list[str] = []
    for name, pat in _BANS:
        if pat.search(text or ""):
            hits.append(name)
    return hits


def scan_obj(obj: object) -> list[str]:
    return scan_text(json.dumps(obj, default=str))


def require_clean(text: str, *, source: str) -> None:
    hits = scan_text(text)
    if hits:
        raise ClaimBanError(f"{source}: banned claims {hits}")


def require_paths_clean(paths: Iterable[Path]) -> None:
    for path in paths:
        if not path.is_file():
            continue
        require_clean(path.read_text(encoding="utf-8"), source=str(path))
