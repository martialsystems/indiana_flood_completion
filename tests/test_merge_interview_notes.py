# Copyright (c) 2026 Martial Systems LLC

from pathlib import Path

import pytest

pytest.importorskip("pypdf", reason="pip install -r requirements.txt")

from pypdf import PdfReader

REPO = Path(__file__).resolve().parents[1]
MAP = REPO / "docs" / "interview_note_map_completion.pdf"
NORA = REPO / "docs" / "interview_note_nora.pdf"
COMBINED = REPO / "docs" / "interview_note.pdf"


def test_combined_interview_note_has_both_parts() -> None:
    assert MAP.is_file() and NORA.is_file() and COMBINED.is_file()
    n_map = len(PdfReader(str(MAP)).pages)
    n_nora = len(PdfReader(str(NORA)).pages)
    comb = PdfReader(str(COMBINED))
    assert len(comb.pages) == n_map + n_nora + 1
    text = "\n".join(page.extract_text() or "" for page in comb.pages)
    assert "Upper White interview notes" in text
    assert "THURSDAY POOLS" in text
    assert "leftover SFHA" in text
    assert "21.18" in text
    assert "03351000" in text
    assert "provisional" in text.lower()
    assert "https://github.com/martialsystems/white_river_stage_inundation" in text
    assert "https://github.com/martialsystems/indiana_flood_completion" in text
