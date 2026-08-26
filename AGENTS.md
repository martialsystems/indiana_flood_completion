# Agent notes: indiana_flood_completion

Private research. Geography is Upper White HUC-8 05120201.

Sibling `~/indiana_hazmat_floodplain` is parked. Do not unpark it. Do not start its Stage A/B. Do not rewrite `data/frozen/sibling_stage0_occupancy.json`.

## Geography

Stay on 05120201. Expanding the HUC is a new stage and a methodology edit.

## Claim bans

Run `floodmap.claims.scan_text` on every written report (JSON, markdown, HTML, PDF text). Fail closed on casualties, climate attribution, tornado counts, population-at-risk, TRI storage as pounds, `P` as 100-year exceedance, and the phrase “unmapped risk”.

`P` is `P(sfha | hydro)` in code, reports, SHAP titles, and map legends.

## Stages

Stage order is 0, A, B, C, D. `whiteforge.gate.require_stage` refuses skips. Stage A refuses a fixture template. Stage C refuses missing A/B reports. Stage D refuses missing C metrics or a missing 2008 overlap mask.

## CRS

Vector native: EPSG:4269 until an explicit logged warp. Rasters: EPSG:5070, 30 m, NLCD 2021 template. Missing CRS: refuse. Live HUC is USGS WBD layer 4. Live template is MRLC WMS `NLCD_2021_Impervious_L48`, tiled, clipped to the HUC.

## Verify

`python3 ~/agent_laws_verify_before_done/vbd_gate.py check --app-root . --claim-done`

`vbd.runtime.json` runs pytest, the fixture `run_stage0.py` path, and `whiteforge/scripts/sanity_whiteforge.py`.

## GraphForge

Pin is `whiteforge/`. Engine checkout `~/graphforge`. Do not add catalog/`surfaces.json` wiring unless the operator asks.
