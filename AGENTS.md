# Agent notes: indiana_flood_completion

Public snapshot of Upper White HUC-8 05120201. MIT on this tree. Later HUCs or a parcel product stay out of this repo. Nora reach stage inundation is the private sibling `white_river_stage_inundation`. Combined interview PDF is packaging only: do not reopen D, B, or HAND.

Sibling `~/indiana_hazmat_floodplain` is parked. Do not unpark it. Do not start its Stage A/B. Do not rewrite `data/frozen/sibling_stage0_occupancy.json`.

## Geography

Stay on 05120201. Expanding the HUC is a new stage and a methodology edit.

## Claim bans

Run `floodmap.claims.scan_text` on every written report (JSON, markdown, HTML, PDF text). Fail closed on casualties, climate attribution, tornado counts, population-at-risk, TRI storage as pounds, `P` as 100-year exceedance, the phrase “unmapped risk”, “no 2008 overlap” without the coverage split, and D1 headline plant names without `p_mean` in the same window.

Cite OFR 2008-1322 as “June 7-9, 2008 inundation (OFR 2008-1322)”. Do not paste the abstract.

`P` is `P(sfha | hydro)` in code, reports, SHAP titles, and map legends. D1 is `zone_class == unshaded_x`. D2 is 2008 mask code 2. Occupancy in this tree is `n_tris_huc_year`.

## Stages

Stage order is 0, A, B, C, D. `whiteforge.gate.require_stage` refuses skips. Stage A refuses a fixture template. Stage B refuses `firm_unshaded_x_ok=False`. Stage C refuses missing A/B reports. Stage D refuses missing C metrics or a missing 2008 three-state mask. Stage D samples `p_sfha_calibrated.tif` only. Do not ship `sum(P*lb)` from raw `p_sfha.tif`. Do not reopen B. HSG omitted is accepted. OFR 3082 and TRI 117 stay frozen as inputs; D reads them. HAND-nodata stays nodata on both P rasters.

## CRS

Vector native: EPSG:4269 until an explicit logged warp. Rasters: EPSG:5070, 30 m, NLCD 2021 template. Missing CRS: refuse. Live HUC is USGS WBD layer 4. Live template is MRLC WMS `NLCD_2021_Impervious_L48`, tiled, clipped to the HUC.

## Verify

`python3 ~/agent_laws_verify_before_done/vbd_gate.py check --app-root . --claim-done`

`vbd.runtime.json` runs pytest, the fixture `run_stage0.py` path, and `whiteforge/scripts/sanity_whiteforge.py`.

## GraphForge

Pin is `whiteforge/`. Engine checkout `~/graphforge`. Do not add catalog/`surfaces.json` wiring unless the operator asks.
