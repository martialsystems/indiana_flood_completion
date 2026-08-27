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

Report and colorbar: `P(sfha | hydro)`. Do not start D from C. The fixture path is the CI join.

## Claim bans

Reports state hydrologic class and, later, TRI overlay tables. The scanner in `floodmap.claims` fails the run if the report text includes casualty language, climate attribution, tornado counts, population-at-risk, TRI storage as pounds, `P` as a 100-year exceedance, or the phrase “unmapped risk”.

## GraphForge

Pin: `whiteforge/`. Verify-before-done is the finish gate.

## Legal

Copyright (c) 2026 Martial Systems LLC. All rights reserved.
