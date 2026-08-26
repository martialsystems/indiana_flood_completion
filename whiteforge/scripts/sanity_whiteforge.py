#!/usr/bin/env python3
# Copyright (c) 2026 Martial Systems LLC. All rights reserved.
"""Import GraphForge, run allow-state product laws, run WhiteForge tests."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
WHITE = REPO / "whiteforge"
sys.path[:0] = [str(REPO), str(WHITE)]

from whiteforge._bootstrap import ensure_paths  # noqa: E402


def main() -> int:
    gf = ensure_paths()
    import graphforge

    print(f"graphforge {getattr(graphforge, '__version__', '?')} @ {gf}")

    try:
        from graphforge.consumer_gate import discover_product_laws
        from graphforge.product_law import require_law

        for law in discover_product_laws(WHITE):
            build = law.get("build") or law.get("builder")
            if not callable(build):
                continue
            require_law(
                build(),
                dict(law.get("state") or {}),
                allow_decisions=law.get("allow_decisions"),
                law_id=str(law.get("id") or "white_law"),
                thread_id=f"sanity_{law.get('id')}",
                raise_error=True,
            )
        print("product_laws: OK")
    except Exception as exc:  # noqa: BLE001 - sanity surface
        print(f"product_laws: FAIL ({exc})", file=sys.stderr)
        return 1

    tr = subprocess.run(
        [sys.executable, "-m", "pytest", str(REPO / "tests" / "test_whiteforge_laws.py"), "-q"],
        cwd=str(REPO),
        check=False,
    )
    return tr.returncode


if __name__ == "__main__":
    raise SystemExit(main())
