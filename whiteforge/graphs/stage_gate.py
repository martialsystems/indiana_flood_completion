# Copyright (c) 2026 Martial Systems LLC. All rights reserved.
"""Refuse stage skips and advance without the required reports."""

from __future__ import annotations

from typing import Any

from whiteforge._bootstrap import ensure_paths

ensure_paths()

from graphforge import END, START, StateGraph, last_value, operator_add
from graphforge.state import ChannelSpec, StateSchema

_ORDER = ("0", "A", "B", "C", "D")
_LIVE = "nlcd_2021"


def _rank(stage: Any) -> int:
    key = str(stage or "0")
    try:
        return _ORDER.index(key)
    except ValueError:
        return -1


def _schema() -> StateSchema:
    return StateSchema.from_specs(
        [
            ChannelSpec("current_stage", last_value, default="0"),
            ChannelSpec("target_stage", last_value, default="0"),
            ChannelSpec("freeze_verified", last_value, default=False),
            ChannelSpec("claim_stage0_complete", last_value, default=False),
            ChannelSpec("template_kind", last_value, default=""),
            ChannelSpec("stage_a_report", last_value, default=False),
            ChannelSpec("stage_b_report", last_value, default=False),
            ChannelSpec("stage_c_metrics", last_value, default=False),
            ChannelSpec("inundation_2008_mask", last_value, default=False),
            ChannelSpec("violations", last_value, default=[]),
            ChannelSpec("decision", last_value, default=None),
            ChannelSpec("events", operator_add, default=[]),
        ]
    )


def _evaluate(state: dict[str, Any]) -> dict[str, Any]:
    violations: list[str] = []
    current = str(state.get("current_stage") or "0")
    target = str(state.get("target_stage") or "0")
    cr, tr = _rank(current), _rank(target)
    if cr < 0 or tr < 0:
        violations.append("unknown_stage")
    if tr > cr + 1:
        violations.append("stage_skip")
    freeze_ok = bool(state.get("freeze_verified"))
    if bool(state.get("claim_stage0_complete")) and not freeze_ok:
        violations.append("stage0_complete_without_freeze")
    if tr >= _rank("A") and not freeze_ok:
        violations.append("advance_without_freeze")
    kind = str(state.get("template_kind") or "")
    if tr >= _rank("A") and kind != _LIVE:
        violations.append("advance_on_fixture_template")
    if tr >= _rank("C"):
        if not bool(state.get("stage_a_report")):
            violations.append("stage_c_without_a")
        if not bool(state.get("stage_b_report")):
            violations.append("stage_c_without_b")
    if tr >= _rank("D"):
        if not bool(state.get("stage_c_metrics")):
            violations.append("stage_d_without_c_metrics")
        if not bool(state.get("inundation_2008_mask")):
            violations.append("stage_d_without_2008_mask")
    ok = len(violations) == 0
    return {
        "violations": violations,
        "events": [{"node": "evaluate", "ok": ok, "violations": list(violations)}],
    }


def build_graph() -> StateGraph:
    g = StateGraph(_schema(), name="white.stage_gate")

    def allow(state: dict[str, Any]) -> dict[str, Any]:
        del state
        return {"decision": "allow", "events": [{"node": "allow"}]}

    def block(state: dict[str, Any]) -> dict[str, Any]:
        return {
            "decision": "block",
            "events": [{"node": "block", "violations": state.get("violations") or []}],
        }

    def route(state: dict[str, Any]) -> str:
        return "ok" if not (state.get("violations") or []) else "bad"

    g.add_node("evaluate", _evaluate)
    g.add_node("allow", allow)
    g.add_node("block", block)
    g.add_edge(START, "evaluate")
    g.add_conditional_edges("evaluate", route, {"ok": "allow", "bad": "block"})
    g.add_edge("allow", END)
    g.add_edge("block", END)
    return g
