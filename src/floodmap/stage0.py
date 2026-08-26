# Copyright (c) 2026 Martial Systems LLC. All rights reserved.
"""Production Stage 0 path: freeze, HUC, template, laws, report."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from floodmap.config import (
    FIXTURE_COLS,
    FIXTURE_ROWS,
    TEMPLATE_KIND_FIXTURE,
    TEMPLATE_KIND_NLCD,
)
from floodmap.errors import GateError
from floodmap.freeze import verify_freeze
from floodmap.huc import load_huc
from floodmap.report import build_stage0_report, write_report
from floodmap.template import inspect_template, sha256_file, write_fixture_template
from whiteforge.gate import require_claims, require_freeze, require_stage, require_stale_map


def run_stage0(
    *,
    huc_path: Path,
    out_dir: Path,
    template_path: Path | None = None,
    huc_wkid: int | None = None,
    template_kind: str = TEMPLATE_KIND_FIXTURE,
    extra: dict[str, Any] | None = None,
) -> dict:
    freeze = verify_freeze()
    require_freeze(rewrite_stage0_packet=False)
    require_claims()
    require_stale_map(request_site_publish=False)
    huc = load_huc(huc_path, wkid=huc_wkid)
    if template_kind not in {TEMPLATE_KIND_FIXTURE, TEMPLATE_KIND_NLCD}:
        template_kind = TEMPLATE_KIND_FIXTURE
    if template_path is None:
        if template_kind == TEMPLATE_KIND_NLCD:
            raise GateError("nlcd_2021 template path is required")
        template_path = out_dir / "template.tif"
        template = write_fixture_template(template_path)
        kind = TEMPLATE_KIND_FIXTURE
    else:
        kind = template_kind
        template = inspect_template(template_path, kind=kind)
        if kind == TEMPLATE_KIND_NLCD and (
            template.width <= FIXTURE_COLS and template.height <= FIXTURE_ROWS
        ):
            raise GateError("nlcd_2021 template looks like the fixture grid")
    require_stage(
        current_stage="0",
        target_stage="0",
        freeze_verified=True,
        claim_stage0_complete=True,
        template_kind=kind,
        thread_id="stage0",
    )
    extra_out = dict(extra or {})
    extra_out.setdefault("template_sha256", sha256_file(template.path))
    report = build_stage0_report(
        huc,
        template,
        huc_source=huc_path.name,
        template_source=template.path.name,
        freeze=freeze,
        extra=extra_out,
    )
    write_report(out_dir, report)
    return report
