#!/usr/bin/env python3
# Copyright (c) 2026 Martial Systems LLC
"""Merge HUC map-completion note and Nora stage note into one interview PDF.

Does not reopen D, B, or HAND. No third Delta. No second HUC.
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(REPO), str(REPO / "src")]

from floodmap.claims import require_clean  # noqa: E402
from floodmap.errors import GateError  # noqa: E402

NOTE_DATE = "2026-08-28"
MAP_PDF = REPO / "docs" / "interview_note_map_completion.pdf"
NORA_PDF = REPO / "docs" / "interview_note_nora.pdf"
DEST_PDF = REPO / "docs" / "interview_note.pdf"


def _spine_text() -> list[str]:
    return [
        "Upper White interview notes",
        "HUC-8 05120201. Two git trees, one 30 m HAND grid.",
        (
            f"Revisions: {NOTE_DATE}: merge the map-completion note and the Nora "
            "stage-inundation note. Does not reopen D, B, or HAND. No third Delta."
        ),
        (
            "Part 1 is map completion on the Upper White: P(sfha | hydro) as a "
            "map-completion layer, TRI overlay, five-site edge screen."
        ),
        (
            "Part 2 is USGS 03351000 / NWS NORI3 (White River near Nora). "
            "Flood stage 11.00 ft (Delta = 1.09 m) and the 21.18 ft crest on "
            "2026-08-15 (NWS provisional, Delta = 4.19 m) on the same 5 km "
            "drain-to-reach window. Extra 679 wet cells filled leftover SFHA "
            "(dry 369 to 50); unshaded X wet 38 to 338."
        ),
        (
            "P(sfha | hydro) is a map-completion layer, not water at 11 ft and "
            "not water at 21.18 ft. Paint on the Nora reach uses stage and WSE, "
            "not discharge."
        ),
        "Trees: https://github.com/martialsystems/indiana_flood_completion "
        "and https://github.com/martialsystems/white_river_stage_inundation.",
    ]


def write_spine(dest: Path) -> Path:
    from reportlab.lib.colors import HexColor
    from reportlab.lib.enums import TA_JUSTIFY, TA_LEFT
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.platypus import Paragraph, SimpleDocTemplate

    base = getSampleStyleSheet()
    ink = HexColor("#1a2430")
    muted = HexColor("#4a5563")
    title = ParagraphStyle(
        "SpineTitle",
        parent=base["Title"],
        fontName="Times-Bold",
        fontSize=16,
        leading=20,
        textColor=ink,
        alignment=TA_LEFT,
        spaceAfter=10,
    )
    body = ParagraphStyle(
        "SpineBody",
        parent=base["Normal"],
        fontName="Times-Roman",
        fontSize=11,
        leading=15,
        textColor=ink,
        alignment=TA_JUSTIFY,
        spaceAfter=10,
    )
    rev = ParagraphStyle(
        "SpineRev",
        parent=base["Normal"],
        fontName="Times-Italic",
        fontSize=9,
        leading=12,
        textColor=muted,
        spaceAfter=12,
    )
    story = []
    texts = _spine_text()
    for t in texts:
        require_clean(t, source="combined_spine")
    generated = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    story.append(Paragraph(texts[0], title))
    story.append(Paragraph(texts[1], rev))
    left = ParagraphStyle(
        "SpineLeft",
        parent=body,
        alignment=TA_LEFT,
    )
    story.append(Paragraph(texts[2] + f" Generated {generated}.", rev))
    for t in texts[3:-1]:
        story.append(Paragraph(t, body))
    story.append(Paragraph(texts[-1], left))
    dest.parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(
        str(dest),
        pagesize=letter,
        title="Upper White interview notes",
        author="Martial Systems LLC",
        leftMargin=72,
        rightMargin=72,
        topMargin=72,
        bottomMargin=64,
    )
    doc.build(story)
    return dest


def merge(*, dest: Path = DEST_PDF, map_pdf: Path = MAP_PDF, nora_pdf: Path = NORA_PDF) -> Path:
    from pypdf import PdfReader, PdfWriter

    if not map_pdf.is_file():
        raise GateError(f"missing map-completion note {map_pdf}")
    if not nora_pdf.is_file():
        raise GateError(f"missing Nora note {nora_pdf}")
    spine = dest.parent / "_spine_interview.pdf"
    write_spine(spine)
    writer = PdfWriter()
    for path in (spine, map_pdf, nora_pdf):
        writer.append(str(path))
    dest.parent.mkdir(parents=True, exist_ok=True)
    with dest.open("wb") as fh:
        writer.write(fh)
    spine.unlink(missing_ok=True)
    return dest


def main() -> int:
    dest = Path(sys.argv[1]) if len(sys.argv) > 1 else DEST_PDF
    out = merge(dest=dest)
    from pypdf import PdfReader

    n = len(PdfReader(str(out)).pages)
    print(f"combined interview note {out} pages={n}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
