# Upper White flood-map completion

This tree scores every 30 meter cell in the Upper White River basin (HUC-8 **05120201**) for how much it looks like FEMA's current Special Flood Hazard Area, given terrain and distance-to-water. The score is `P(sfha | hydro)`. TRI on-site releases for 2023 are an overlay, not the training target.

`P(sfha | hydro)` is a map-completion score, not a 100-year exceedance.

Calibrated OOF PR-AUC (0.36) beats the SFHA-rate baseline (0.10) and a HAND score (0.24). To three decimals: raw PR-AUC 0.369, calibrated 0.362, Brier 0.073 after isotonic calibration. Stage D samples `p_sfha_calibrated.tif` only.

Five Zone X plants have one wet cell in a 120 m window; site-mean P is 0.06 to 0.19; none clear 0.50 on the footprint.

THURSDAY POOLS is the only large-inventory terrain hit, and it is neighboring land.

June 2008 Appendix 2 does not cover the industrial core of 05120201.

| Plant | 2023 on-site release (lb) | Highest P in 120 m | Mean P in 120 m | What the high cell is |
|---|---:|---:|---:|---|
| THURSDAY POOLS | 257590 | 0.769 | p_mean 0.152 | neighboring land, unshaded X |
| FGF LLC | 27335 | 0.780 | p_mean 0.060 | adjacent hydro (floodway) |
| ROYAL SPA CORP | 4950 | 0.774 | p_mean 0.113 | adjacent hydro (waterbody) |
| LINDE GAS & EQUIPMENT | 1048 | 0.763 | p_mean 0.192 | neighboring land, unshaded X |
| MAGNA POWERTRAIN EAST | 0 | 0.789 | p_mean 0.098 | neighboring land, unshaded X |

The table ranks on window-max P. Buffer-max is one 30 m cell; buffer-mean is the 120 m footprint. At THURSDAY POOLS (p_mean 0.152) the wet cell is neighboring unshaded X, HAND = 0, 120 m from the office point: an edge screen, not a wet footprint. FGF LLC (p_mean 0.060) and ROYAL SPA CORP (p_mean 0.113) are adjacent-hydro footnotes (floodway corner; waterbody). MAGNA POWERTRAIN EAST (p_mean 0.098) is in the list because the rank is P_max.

Map: [logs/stage_d/map.html](logs/stage_d/map.html). Calibrated P, zone class, two named 2008 polygons (Martinsville, Paragon), 117 office points, five office-to-max cells. Interview note: [docs/interview_note.pdf](docs/interview_note.pdf).

101 of 117 in-HUC plants sit on mapped unshaded X. The other 16 are already floodway (2), SFHA (4), shaded X (8), or unmapped (2).

Limitations:

- No parcels: adjacent hydro is NHD/FIRM paint, not a cadastral clip.
- No soil: hydrologic soil group is not in this model.
- Not a FIRM: P does not replace the effective flood map.
- 2008 is coverage: 117 plants in mask code 1, 0 in code 2. Appendix 2 reaches in the HUC are Martinsville and Paragon only.

Sibling occupancy study: `indiana_hazmat_floodplain` (parked, Stage 0 frozen 2026-08-25). This tree imports that occupancy as a freeze file. It does not recompute it.

| File | Role |
|------|------|
| [METHODOLOGY.md](METHODOLOGY.md) | Locked contract |
| [AGENTS.md](AGENTS.md) | Agent rules |
| [CHECKLIST.md](CHECKLIST.md) | Operator list |
| `src/floodmap/` | Claims, freeze, HUC, template, Stage 0 |
| `whiteforge/` | GraphForge pin |

## Stage 0

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
PYTHONPATH=src:. python3 scripts/run_stage0.py \
  --huc tests/fixtures/huc.geojson \
  --out logs/stage0_fixture
PYTHONPATH=src:. python3 -m pytest tests -q
```

Hard gate: freeze numbers match, claim scan clean, HUC non-empty, template EPSG:5070 at 30 m, product laws allow Stage 0. See METHODOLOGY.md.

Live WBD + NLCD 2021 (network; writes `data/raw/` and `data/interim/`, gitignored):

```bash
PYTHONPATH=src:. python3 scripts/run_stage0_live.py
```

Stage A (network; live `nlcd_2021` template required):

```bash
PYTHONPATH=src:. python3 scripts/run_stage_a.py
```

Stage B (network for NHD waterbodies; live template + DEM required):

```bash
PYTHONPATH=src:. python3 scripts/run_stage_b.py
```

Finite TWI on interior, toy-watershed tests in `tests/test_hydro.py`, bands on transform sha256 `479ac37628bfd7e5`. D1 is `unshaded_x`. OFR 2008-1322 Appendix 2 is a reach-scale three-state mask. HSG stays out of the B stack and out of this C model.

Stage C (HUC-10 fetch; live bands required):

```bash
PYTHONPATH=src:. python3 scripts/run_stage_c.py
```

Report and colorbar: `P(sfha | hydro)`. Calibrate OOF scores before D:

```bash
PYTHONPATH=src:. python3 scripts/run_c_calibrate.py
PYTHONPATH=src:. python3 scripts/run_stage_d.py
PYTHONPATH=src:. python3 scripts/run_d_map.py
PYTHONPATH=src:. python3 scripts/run_d_shap.py
```

The fixture path is the CI join. gSSURGO C2 is not run. Do not reopen D, B, or raw `p_sfha.tif`.

## Claim bans

Reports state hydrologic class and, later, TRI overlay tables. The scanner in `floodmap.claims` fails the run if the report text includes casualty language, climate attribution, tornado counts, population-at-risk, TRI storage as pounds, `P` as a 100-year exceedance, or the phrase “unmapped risk”.

## GraphForge

Pin: `whiteforge/`. Verify-before-done is the finish gate.

## Legal

Copyright (c) 2026 Martial Systems LLC. All rights reserved.
