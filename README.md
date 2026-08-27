# Upper White flood-map completion

Private research tree. Upper White HUC-8 **05120201**. Pixel unit: `P(sfha | hydro)` on a 30 m EPSG:5070 grid. Facility overlay (TRI on-site releases) is Stage D.

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
```

D samples `p_sfha_calibrated.tif` only. 101 of 117 in-HUC plants are on mapped unshaded X (D1 universe). The other 16 are already floodway (2), SFHA (4), shaded X (8), or unmapped (2).

Buffer-max ≥ 0.75 is a 30 m edge of the 120 m window. Buffer-mean is the footprint. Site-mean P at the five edge-screen rows is 0.06 to 0.19.

| Plant | on_site_release_lb | P_max | p_mean | P_max cell |
|---|---:|---:|---:|---|
| THURSDAY POOLS | 257590 | 0.769 | p_mean 0.152 | neighboring land, unshaded X |
| FGF LLC | 27335 | 0.780 | p_mean 0.060 | adjacent hydro (floodway) |
| ROYAL SPA CORP | 4950 | 0.774 | p_mean 0.113 | adjacent hydro (waterbody) |
| LINDE GAS & EQUIPMENT | 1048 | 0.763 | p_mean 0.192 | neighboring land, unshaded X |
| MAGNA POWERTRAIN EAST | 0 | 0.789 | p_mean 0.098 | neighboring land, unshaded X |

Sum of P_max × lb on those five rows: 224k, mostly THURSDAY POOLS inventory. Zero rows have P_mean ≥ 0.50. D2 is empty: 117 TRI in 2008 mask code 1, 0 in code 2; Appendix 2 reaches are Martinsville and Paragon only. The fixture path is the CI join.

## Claim bans

Reports state hydrologic class and, later, TRI overlay tables. The scanner in `floodmap.claims` fails the run if the report text includes casualty language, climate attribution, tornado counts, population-at-risk, TRI storage as pounds, `P` as a 100-year exceedance, or the phrase “unmapped risk”.

## GraphForge

Pin: `whiteforge/`. Verify-before-done is the finish gate.

## Legal

Copyright (c) 2026 Martial Systems LLC. All rights reserved.
