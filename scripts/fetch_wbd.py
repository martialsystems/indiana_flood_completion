#!/usr/bin/env python3
# Copyright (c) 2026 Martial Systems LLC. All rights reserved.

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(REPO), str(REPO / "src")]

from floodmap.fetch import fetch_wbd  # noqa: E402


def main() -> int:
    dest = fetch_wbd(REPO / "data" / "raw")
    print(dest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
