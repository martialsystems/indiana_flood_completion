# Copyright (c) 2026 Martial Systems LLC. All rights reserved.

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
README = (ROOT / "README.md").read_text(encoding="utf-8")
LICENSE = (ROOT / "LICENSE").read_text(encoding="utf-8")


def test_license_is_mit() -> None:
    assert LICENSE.lstrip().startswith("MIT License")
    assert "Permission is hereby granted" in LICENSE
    assert "All rights reserved" not in LICENSE


def test_readme_keeps_lead_table_and_caveat() -> None:
    assert "P(sfha | hydro)" in README
    assert "map-completion score, not a 100-year exceedance" in README
    assert "THURSDAY POOLS" in README
    assert "Highest P in 120 m" in README
    assert "Mean P (p_mean)" in README
    assert "Not a FIRM or site-level flood risk" in README
    assert "TRI names are an overlay" in README
    assert "All rights reserved" not in README
    lead, _sep, table = README.partition("| Plant |")
    assert "Not a FIRM or site-level flood risk" in lead
    assert "https://github.com/martialsystems/white_river_stage_inundation" in README
    assert "https://gist.github.com/martialsystems/16584e78d079666f7e8994b4cc6158be" in README
    assert (
        "[![Open the research console]"
        "(https://img.shields.io/badge/Open_the_research_console-2e7d32"
        "?style=for-the-badge)]"
        "(https://martialsystems.github.io/indiana_wx_pages/)"
    ) in README
    assert "labelColor" not in README
    assert "6e1f1c" not in README
    assert "66b896b0" not in README
    assert "Research index:" not in README
    assert "## Summary" in README
    assert "white_river_fim_compare" in README
    assert "FGF LLC" in table


def test_gitignore_keeps_raw_and_interim() -> None:
    gi = (ROOT / ".gitignore").read_text(encoding="utf-8")
    assert "data/raw/*" in gi
    assert "data/interim/*" in gi
