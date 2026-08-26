# Copyright (c) 2026 Martial Systems LLC. All rights reserved.
"""Stage 0 report. Pixel-grid bootstrap. Claim-scanned."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from floodmap.claims import require_clean, scan_obj
from floodmap.config import HUC8, HUC_NAME, STATE_CODE, TEMPLATE_CRS, TEMPLATE_RES_M
from floodmap.errors import GateError
from floodmap.freeze import verify_freeze
from floodmap.huc import HucLayer
from floodmap.template import TemplateGrid


def build_stage0_report(
    huc: HucLayer,
    template: TemplateGrid,
    *,
    huc_source: str,
    template_source: str,
    freeze: dict[str, Any],
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    packet = verify_freeze(freeze)
    if huc.huc8 != HUC8:
        raise GateError(f"HUC {huc.huc8!r} != {HUC8!r}")
    if template.crs != TEMPLATE_CRS:
        raise GateError(f"template CRS {template.crs} != {TEMPLATE_CRS}")
    report: dict[str, Any] = {
        "stage": "0",
        "state": STATE_CODE,
        "huc8": HUC8,
        "huc_name": huc.name or HUC_NAME,
        "unit": "pixel",
        "p_definition": "P(sfha | hydro)",
        "vector_crs": huc.crs,
        "template_crs": template.crs,
        "template_res_m": TEMPLATE_RES_M,
        "template_kind": template.kind,
        "template_shape": [template.height, template.width],
        "huc_source": huc_source,
        "template_source": template_source,
        "n_huc_features": huc.n_features,
        "huc_states": huc.states,
        "huc_areasqkm": huc.areasqkm,
        "imported_occupancy": {
            "source_repo": packet.get("source_repo"),
            "frozen_date": packet.get("frozen_date"),
            "n_tris_joinable": packet["n_tris_joinable"],
            "n_in_sfha": packet["n_in_sfha"],
            "share_in_sfha": packet["share_in_sfha"],
            "unit": packet["unit"],
        },
        "claim_bans": [
            "casualty_count",
            "climate_attribution",
            "tornado_count",
            "population_at_risk",
            "tri_storage",
            "p_as_100yr",
            "unmapped_risk",
            "occupancy_as_this_tree",
            "d2_empty_without_split",
        ],
        "gate": "pass",
    }
    if extra:
        report.update(extra)
    require_clean(json.dumps(report, default=str), source="stage0_report")
    hits = scan_obj(report)
    if hits:
        raise GateError(f"report claim scan {hits}")
    return report


def write_report(out_dir: Path, report: dict[str, Any]) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "stage0_report.json"
    text = json.dumps(report, indent=2, sort_keys=True) + "\n"
    require_clean(text, source=str(path))
    path.write_text(text, encoding="utf-8")
    return path
