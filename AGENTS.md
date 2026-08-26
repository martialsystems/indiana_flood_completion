# Agent notes: indiana_flood_completion

Private research. Geography is Upper White HUC-8 05120201.

Sibling `~/indiana_hazmat_floodplain` is parked. Do not unpark it. Do not start its Stage A/B. Do not rewrite `data/frozen/sibling_stage0_occupancy.json`.

## Geography

Stay on 05120201. Expanding the HUC is a new stage and a methodology edit.

## Claim bans

Run `floodmap.claims.scan_text` on every written report (JSON, markdown, HTML, PDF text). Fail closed on casualties, climate attribution, tornado counts, population-at-risk, TRI storage as pounds, `P` as 100-year exceedance, the phrase “unmapped risk”, and “no 2008 overlap” without the coverage split.

Cite OFR 2008-1322 as “June 7-9, 2008 inundation (OFR 2008-1322)”. Do not paste the abstract.

`P` is `P(sfha | hydro)` in code, reports, SHAP titles, and map legends. D1 is `zone_class == unshaded_x`. D2 is 2008 mask code 2. Occupancy in this tree is `n_tris_huc_year`.

## Stages

Stage order is 0, A, B, C, D. `whiteforge.gate.require_stage` refuses skips. Stage A refuses a fixture template. Stage C refuses missing A/B reports. Stage D refuses missing C metrics or a missing 2008 three-state mask. Do not start Stage A fetch until the FIRM zone codebook and 2008 mask codes in METHODOLOGY.md / `floodmap.codes` are the success table (locked 2026-08-26).

## CRS

Vector native: EPSG:4269 until an explicit logged warp. Rasters: EPSG:5070, 30 m, NLCD 2021 template. Missing CRS: refuse. Live HUC is USGS WBD layer 4. Live template is MRLC WMS `NLCD_2021_Impervious_L48`, tiled, clipped to the HUC.

## Verify

`python3 ~/agent_laws_verify_before_done/vbd_gate.py check --app-root . --claim-done`

`vbd.runtime.json` runs pytest, the fixture `run_stage0.py` path, and `whiteforge/scripts/sanity_whiteforge.py`.

## GraphForge

Pin is `whiteforge/`. Engine checkout `~/graphforge`. Do not add catalog/`surfaces.json` wiring unless the operator asks.
