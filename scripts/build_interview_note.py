#!/usr/bin/env python3
# Copyright (c) 2026 Martial Systems LLC. All rights reserved.
"""Interview note PDF for the Upper White map-completion product.

Lead is the five-sentence claim graph, the five-row table, and the map.
Does not reopen D, B, or raw P.
"""

from __future__ import annotations

import csv
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(REPO), str(REPO / "src")]

from whiteforge._bootstrap import ensure_paths  # noqa: E402

ensure_paths()

from floodmap.claims import require_clean  # noqa: E402
from floodmap.codes import P_DEFINITION  # noqa: E402
from floodmap.config import HUC8, P_SFHA_CALIBRATED_NAME, P_SFHA_NODATA  # noqa: E402
from floodmap.errors import GateError  # noqa: E402
from floodmap.map_d import _ofr_polygons  # noqa: E402

NOTE_DATE = "2026-08-27"
DEST_PDF = REPO / "docs" / "interview_note.pdf"
MAP_PNG = REPO / "logs" / "stage_d" / "map_figure.png"
SHAP_PNG = REPO / "logs" / "stage_d" / "shap_global.png"


def _git_sha() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short=12", "HEAD"],
            cwd=str(REPO),
            text=True,
        ).strip()
    except Exception:
        return "unknown"


def render_map_figure(
    *,
    interim_dir: Path,
    facilities_csv: Path,
    headline_csv: Path,
    dest_png: Path,
    downsample: int = 12,
) -> Path:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np
    import rasterio
    from rasterio.warp import transform as rio_transform
    from shapely.geometry import shape

    p_path = interim_dir / P_SFHA_CALIBRATED_NAME
    if not p_path.is_file():
        raise GateError(f"interview map needs {P_SFHA_CALIBRATED_NAME}")
    with rasterio.open(p_path) as src:
        p = src.read(1)
        p_crs = src.crs
        p_tf = src.transform
        west, south, east, north = src.bounds
        nod = src.nodata if src.nodata is not None else P_SFHA_NODATA
    with rasterio.open(interim_dir / "mask_2008.tif") as src:
        ofr = _ofr_polygons(src.read(1), src.transform, src.crs)

    sub = p[::downsample, ::downsample]
    valid = np.isfinite(sub) & (sub != nod)
    show = np.ma.masked_where(~valid, np.clip(sub, 0.0, 1.0))
    fig, ax = plt.subplots(figsize=(8.2, 7.0), dpi=140)
    im = ax.imshow(
        show,
        cmap="YlOrRd",
        vmin=0.0,
        vmax=1.0,
        extent=(west, east, south, north),
        interpolation="nearest",
        origin="upper",
    )
    def _draw_poly(geom) -> None:
        lon, lat = geom.exterior.xy
        x, y = rio_transform("EPSG:4326", p_crs, list(lon), list(lat))
        ax.plot(x, y, color="#0033aa", lw=2.0, zorder=3)

    for feat in ofr:
        g = shape(feat["geometry"])
        if g.geom_type == "Polygon":
            _draw_poly(g)
        elif g.geom_type == "MultiPolygon":
            for part in g.geoms:
                _draw_poly(part)
    head = {r["name"]: r for r in csv.DictReader(headline_csv.open(encoding="utf-8"))}
    fac = list(csv.DictReader(facilities_csv.open(encoding="utf-8")))
    for rec in fac:
        lon, lat = float(rec["lon"]), float(rec["lat"])
        x, y = rio_transform("EPSG:4326", p_crs, [lon], [lat])
        name = rec["name"]
        headline = name in head
        ax.plot(
            x[0],
            y[0],
            marker="o",
            ms=5 if headline else 2.4,
            color="#b2182b" if headline else "#2166ac",
            markeredgecolor="white",
            markeredgewidth=0.3,
            zorder=4 if headline else 3,
            linestyle="None",
        )
        if headline:
            hr = head[name]
            dr = int(float(hr.get("p_max_dr") or 0))
            dc = int(float(hr.get("p_max_dc") or 0))
            xs, ys = rio_transform("EPSG:4326", p_crs, [lon], [lat])
            orow, ocol = rasterio.transform.rowcol(p_tf, xs[0], ys[0])
            mx, my = rasterio.transform.xy(p_tf, orow + dr, ocol + dc, offset="center")
            ax.plot([x[0], mx], [y[0], my], color="#111111", lw=0.8, zorder=5)
            ax.plot(mx, my, marker="s", ms=5, color="#ffff33", markeredgecolor="black", zorder=6)
    cb = fig.colorbar(im, ax=ax, fraction=0.046, pad=0.03)
    cb.set_label(f"calibrated {P_DEFINITION}")
    ax.set_title(f"Upper White {HUC8}: calibrated {P_DEFINITION}")
    ax.set_xlabel("EPSG:5070 easting (m)")
    ax.set_ylabel("EPSG:5070 northing (m)")
    ax.ticklabel_format(useOffset=False, style="plain")
    ax.set_aspect("equal")
    fig.tight_layout()
    dest_png.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(dest_png, dpi=140)
    plt.close(fig)
    return dest_png


def _styles():
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet

    base = getSampleStyleSheet()
    ink = colors.HexColor("#1a2430")
    muted = colors.HexColor("#4a5563")
    styles = {
        "title": ParagraphStyle(
            "NoteTitle",
            parent=base["Title"],
            fontName="Times-Bold",
            fontSize=16,
            leading=19,
            textColor=ink,
            alignment=TA_LEFT,
            spaceAfter=6,
        ),
        "sub": ParagraphStyle(
            "NoteSub",
            parent=base["Normal"],
            fontName="Times-Italic",
            fontSize=10,
            leading=13,
            textColor=muted,
            spaceAfter=10,
        ),
        "h1": ParagraphStyle(
            "NoteH1",
            parent=base["Heading1"],
            fontName="Times-Bold",
            fontSize=12,
            leading=15,
            textColor=ink,
            spaceBefore=12,
            spaceAfter=6,
        ),
        "body": ParagraphStyle(
            "NoteBody",
            parent=base["Normal"],
            fontName="Times-Roman",
            fontSize=10,
            leading=13,
            textColor=ink,
            alignment=TA_JUSTIFY,
            spaceAfter=8,
        ),
        "talk": ParagraphStyle(
            "NoteTalk",
            parent=base["Normal"],
            fontName="Times-Italic",
            fontSize=10,
            leading=13,
            textColor=ink,
            alignment=TA_JUSTIFY,
            leftIndent=8,
            rightIndent=8,
            spaceAfter=8,
        ),
        "cap": ParagraphStyle(
            "NoteCap",
            parent=base["Normal"],
            fontName="Times-Italic",
            fontSize=8.5,
            leading=11,
            textColor=muted,
            spaceBefore=4,
            spaceAfter=10,
        ),
        "cell": ParagraphStyle(
            "NoteCell",
            parent=base["Normal"],
            fontName="Times-Roman",
            fontSize=8,
            leading=10,
            textColor=ink,
            alignment=TA_LEFT,
        ),
        "cellr": ParagraphStyle(
            "NoteCellR",
            parent=base["Normal"],
            fontName="Times-Roman",
            fontSize=8,
            leading=10,
            textColor=ink,
            alignment=TA_CENTER,
        ),
        "foot": ParagraphStyle(
            "NoteFoot",
            parent=base["Normal"],
            fontName="Times-Roman",
            fontSize=8,
            leading=10,
            textColor=muted,
            alignment=TA_CENTER,
        ),
        "rev": ParagraphStyle(
            "NoteRev",
            parent=base["Normal"],
            fontName="Times-Roman",
            fontSize=8,
            leading=10,
            textColor=muted,
            spaceAfter=10,
        ),
    }
    return styles


def _table(rows: list[list[str]], col_widths: list[float], *, numeric: bool = False):
    from reportlab.lib import colors
    from reportlab.platypus import Paragraph, Table, TableStyle

    styles = _styles()
    data = []
    for i, row in enumerate(rows):
        out = []
        for j, cell in enumerate(row):
            st = styles["cell"]
            if i == 0:
                st = styles["cell"]
                cell = f"<b>{cell}</b>"
            elif numeric and j > 0:
                st = styles["cellr"]
            out.append(Paragraph(cell, st))
        data.append(out)
    grid = Table(data, colWidths=col_widths, repeatRows=1)
    grid.setStyle(
        TableStyle(
            [
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#c5d0c8")),
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e4ebe7")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ]
        )
    )
    return grid


def _footer(canvas, doc) -> None:
    canvas.saveState()
    canvas.setFont("Times-Roman", 8)
    canvas.setFillColorRGB(0.29, 0.33, 0.39)
    canvas.drawString(72, 36, "Copyright (c) 2026 Martial Systems LLC. All rights reserved.")
    canvas.drawRightString(letter_w() - 72, 36, f"page {doc.page}")
    canvas.restoreState()


def letter_w():
    from reportlab.lib.pagesizes import letter

    return letter[0]


def build_pdf(*, dest: Path, map_png: Path, sha: str) -> Path:
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.units import inch
    from reportlab.platypus import Image, KeepTogether, Paragraph, SimpleDocTemplate

    styles = _styles()
    generated = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    story = []

    story.append(Paragraph("Upper White flood-map completion: interview note", styles["title"]))
    story.append(
        Paragraph(
            f"HUC-8 {HUC8}. Methods and claim discipline. {P_DEFINITION} on a 30 m EPSG:5070 grid.",
            styles["sub"],
        )
    )
    story.append(
        Paragraph(
            f"Revisions: {NOTE_DATE}: first interview note (abstract, Table 1, Figure 2, uses, Stage C metrics, limitations). "
            f"Generated {generated}. Git {sha}. Product artifacts at c0e9d5e.",
            styles["rev"],
        )
    )

    story.append(Paragraph("Abstract", styles["h1"]))
    story.append(
        Paragraph(
            f"<i>{P_DEFINITION}</i> is a map-completion score, not a 1%-annual-chance exceedance probability.",
            styles["body"],
        )
    )
    story.append(
        Paragraph(
            "Calibrated OOF PR-AUC (0.36) beats the SFHA-rate baseline (0.10) and a HAND score (0.24).",
            styles["body"],
        )
    )
    story.append(
        Paragraph(
            "Five Zone X plants have one wet cell in a 120 m window; site-mean P is 0.06 to 0.19; none clear 0.50 on the footprint.",
            styles["body"],
        )
    )
    story.append(
        Paragraph(
            "THURSDAY POOLS is the only large-inventory terrain hit, and it is neighboring land.",
            styles["body"],
        )
    )
    story.append(
        Paragraph(
            "June 2008 Appendix 2 does not cover the industrial core of 05120201.",
            styles["body"],
        )
    )
    story.append(
        Paragraph(
            "To three decimals: raw PR-AUC 0.369, calibrated 0.362, Brier 0.073 after isotonic calibration. "
            "Stage D samples p_sfha_calibrated.tif only. Do not treat 0.75 as a percent chance on the raw raster.",
            styles["body"],
        )
    )

    story.append(Paragraph("Table 1. Five Zone X plants ranked on window-max P", styles["h1"]))
    story.append(
        _table(
            [
                [
                    "Plant",
                    "2023 on-site release (lb)",
                    "Highest P in 120 m",
                    "Mean P in 120 m",
                    "What the high cell is",
                ],
                [
                    "THURSDAY POOLS",
                    "257590",
                    "0.769",
                    "p_mean 0.152",
                    "neighboring land, unshaded X",
                ],
                [
                    "FGF LLC",
                    "27335",
                    "0.780",
                    "p_mean 0.060",
                    "adjacent hydro (floodway)",
                ],
                [
                    "ROYAL SPA CORP",
                    "4950",
                    "0.774",
                    "p_mean 0.113",
                    "adjacent hydro (waterbody)",
                ],
                [
                    "LINDE GAS & EQUIPMENT",
                    "1048",
                    "0.763",
                    "p_mean 0.192",
                    "neighboring land, unshaded X",
                ],
                [
                    "MAGNA POWERTRAIN EAST",
                    "0",
                    "0.789",
                    "p_mean 0.098",
                    "neighboring land, unshaded X",
                ],
            ],
            [1.85 * inch, 1.15 * inch, 1.05 * inch, 1.05 * inch, 1.90 * inch],
        )
    )
    story.append(
        Paragraph(
            "Table 1 ranks on the wettest 30 m cell inside a 120 m window. Mean P is the footprint. "
            "At THURSDAY POOLS (p_mean 0.152) that cell is neighboring unshaded X, HAND = 0, 120 m from the office point: "
            "an edge screen, not a wet footprint. FGF LLC (p_mean 0.060) and ROYAL SPA CORP (p_mean 0.113) are adjacent-hydro "
            "footnotes (floodway corner; waterbody). MAGNA POWERTRAIN EAST (p_mean 0.098) is in the list because the rank is "
            "window-max P. Inventory pounds are the table column only.",
            styles["cap"],
        )
    )

    if not map_png.is_file():
        raise GateError(f"missing map figure {map_png}")
    img = Image(str(map_png), width=6.9 * inch, height=6.9 * inch * 7.0 / 8.2)
    img.hAlign = "CENTER"
    story.append(
        KeepTogether(
            [
                Paragraph("Figure 2. Calibrated map and TRI overlay", styles["h1"]),
                img,
                Paragraph(
                    "Figure 2. Calibrated P(sfha | hydro) for 05120201. Blue dots: 117 in-HUC TRI plants (2023). "
                    "Red dots: five headline plants. Black line: office point to the window-max cell (yellow square). "
                    "Blue outlines: June 7-9, 2008 inundation (OFR 2008-1322) code 2, dissolved to Martinsville and Paragon. "
                    "Interactive copy: logs/stage_d/map.html.",
                    styles["cap"],
                ),
            ]
        )
    )

    story.append(Paragraph("What you can do with it", styles["h1"]))
    story.append(Paragraph("<b>1. Portfolio (methods and claim discipline).</b>", styles["body"]))
    story.append(
        Paragraph(
            "This is the highest-value use. Geospatial, climate-risk, insurance, and civic-tech readers can see that the work "
            "locked a geography (Upper White 05120201), refused a bad label (IndianaMap dropped unshaded Zone X; NFHL layer 28 "
            "with where=1=1 restored it), calibrated probabilities instead of waving at 0.75, split window-max from site-mean "
            "so five factories were not called flooded, and wrote claim bans into CI. Lead with the five abstract sentences and "
            "Figure 2. Show map.html, Table 1, and the Stage C metrics below. Do not pitch this as hidden flood zones.",
            styles["body"],
        )
    )
    story.append(Paragraph("<b>2. Interview talk (about 90 seconds).</b>", styles["body"]))
    story.append(
        Paragraph(
            "I trained a model to complete FEMA floodplain maps in the Upper White basin. It beats a HAND baseline on ranking. "
            "When I overlay TRI plants, five Zone X sites have one wet cell in a 120 m window. Site-average probability stays low. "
            "The 2008 USGS inundation maps do not cover Indianapolis industry. So this is map completion plus an edge screen, "
            "not a plant-level hazard list.",
            styles["talk"],
        )
    )
    story.append(
        Paragraph(
            "If they push: calibration, spatial CV, and why Zone X extraction was the actual bug. Those notes are below. "
            "They are methods, not a second finding.",
            styles["body"],
        )
    )
    story.append(Paragraph("<b>3. This short note.</b>", styles["body"]))
    story.append(
        Paragraph(
            "Five sentences as abstract, Table 1, Figure 2, one limitations paragraph. That is the sendable object. "
            "The repo is martialsystems/indiana_flood_completion (private).",
            styles["body"],
        )
    )

    story.append(Paragraph("Stage C metrics", styles["h1"]))
    story.append(
        _table(
            [
                ["Metric", "Value"],
                ["PR-AUC, quoted", "0.36 (raw 0.369, calibrated 0.362)"],
                ["SFHA-rate baseline", "0.10 (0.097)"],
                ["HAND score PR-AUC", "0.24 (0.243)"],
                ["Brier after isotonic", "0.073"],
                ["Brier, raw scores", "0.177 (constant classifier 0.088)"],
                ["CV", "leave-one-HUC-10-out, 17 watersheds, 1-pixel halo"],
                ["Features", "slope, TWI, HAND, dist_flowline, dist_waterbody, NLCD impervious"],
                ["HSG in model", "no"],
                ["D sample raster", "p_sfha_calibrated.tif"],
                ["In-HUC TRI 2023", "117 (101 unshaded X; 16 already mapped hazard)"],
            ],
            [2.3 * inch, 4.7 * inch],
        )
    )
    story.append(
        Paragraph(
            "Raw booster scores ranked and were miscalibrated (Brier worse than the constant). Isotonic regression on out-of-fold "
            "scores, same HUC-10 cuts, wrote the calibrated raster. Rank held (0.369 to 0.362). D never samples raw p_sfha.tif.",
            styles["cap"],
        )
    )

    story.append(Paragraph("If they push", styles["h1"]))
    story.append(
        Paragraph(
            "Zone X extract: IndianaMap FIRM 2023 omitted AREA OF MINIMAL FLOOD HAZARD polygons. Monument Circle, a Carmel "
            "till-plain cell, and a Delaware field painted as unmapped. D1 is zone_class == unshaded_x, so that extract would have "
            "dropped Indianapolis mapped Zone X from the overlay. FEMA NFHL MapServer layer 28, where=1=1, is the live FIRM. "
            "Interior unshaded X is 6,986,426 cells (89.23%).",
            styles["body"],
        )
    )
    story.append(
        Paragraph(
            "Spatial CV: 17 HUC-10 blocks, leave-one-out, no test HUC-10 in train, including a 1-pixel halo. Labels are binary "
            "SFHA (floodway included). HAND-nodata cells are excluded and stay nodata on both P rasters.",
            styles["body"],
        )
    )
    story.append(
        Paragraph(
            "Max versus mean: buffer-max is one 30 m cell in a 120 m window. Buffer-mean is the footprint. Zero headline rows "
            "have mean P at or above 0.50. Adjacent hydro is NHD/FIRM paint: FGF LLC (p_mean 0.060) floodway corner, "
            "ROYAL SPA CORP (p_mean 0.113) waterbody.",
            styles["body"],
        )
    )
    story.append(
        Paragraph(
            "Claim scanner: floodmap.claims fails a report that uses banned tokens, treats P as a 1%-annual-chance exceedance, "
            "prints empty D2 without the code-1 / code-2 split, or names a D1 headline plant without p_mean in the same window. "
            "GraphForge pin: whiteforge/.",
            styles["body"],
        )
    )

    story.append(Paragraph("Close-out: SHAP", styles["h1"]))
    story.append(
        Paragraph(
            "Global SHAP on C features, no HSG: HAND first (mean |SHAP| 1.37), then distance to water, then slope. TWI is last "
            "because HAND already ate the wetness signal. At the THURSDAY POOLS max cell (p_mean 0.152), HAND = 0 is the local "
            "driver and the cell is still unshaded X. Write-up, not discovery.",
            styles["body"],
        )
    )
    if SHAP_PNG.is_file():
        shap = Image(str(SHAP_PNG), width=5.4 * inch, height=5.4 * inch * 3.2 / 6.0)
        shap.hAlign = "CENTER"
        story.append(shap)
        story.append(Paragraph("Figure 3. Global SHAP for C features. Close-out, not a new result.", styles["cap"]))

    story.append(Paragraph("Limitations", styles["h1"]))
    story.append(
        Paragraph(
            "No parcels: adjacent hydro is NHD/FIRM paint, not a cadastral clip; a parcel clip would change certainty on FGF LLC "
            "(p_mean 0.060) and ROYAL SPA CORP (p_mean 0.113), not the mean-versus-max finding. No soil: hydrologic soil group "
            "is not in this model; gSSURGO C2 was not required for the claim graph. Not a FIRM: P does not replace the effective "
            "flood map. 2008 is coverage: 117 plants in mask code 1, 0 in code 2; Appendix 2 reaches in the HUC are Martinsville "
            "and Paragon only. The map HTML was not opened in a browser for this note; Figure 2 is drawn from the calibrated "
            "raster and the D tables.",
            styles["body"],
        )
    )

    dest.parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(
        str(dest),
        pagesize=letter,
        leftMargin=0.75 * inch,
        rightMargin=0.75 * inch,
        topMargin=0.7 * inch,
        bottomMargin=0.65 * inch,
        title="Upper White flood-map completion: interview note",
        author="Martial Systems LLC",
    )
    doc.build(story, onFirstPage=_footer, onLaterPages=_footer)
    return dest


def main() -> int:
    sha = _git_sha()
    render_map_figure(
        interim_dir=REPO / "data" / "interim",
        facilities_csv=REPO / "logs" / "stage_d" / "facilities.csv",
        headline_csv=REPO / "logs" / "stage_d" / "d1_headline.csv",
        dest_png=MAP_PNG,
    )
    pdf = build_pdf(dest=DEST_PDF, map_png=MAP_PNG, sha=sha)
    from pypdf import PdfReader

    reader = PdfReader(str(pdf))
    text = "\n".join((page.extract_text() or "") for page in reader.pages)
    require_clean(text, source=str(pdf))
    print(f"wrote {pdf} pages={len(reader.pages)} bytes={pdf.stat().st_size} sha={sha}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
