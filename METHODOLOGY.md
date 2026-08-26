# Methodology (locked 2026-08-26)

This file is the working contract. If README and this file disagree, this file wins for what to build.

Sibling `indiana_hazmat_floodplain` stays parked. Its Stage 0 occupancy (facility unit, Indiana, 2026-08-25) is imported here as a freeze file. Do not recompute that occupancy. Do not unpark the sibling.

## Objects (keep separate)

| Object | Unit | Tree |
|--------|------|------|
| Occupancy | Facility inside current SFHA | Sibling, frozen |
| Hydrologic class | 30 m pixel `P(sfha \| hydro)` | This tree |
| Overlay tables D1, D2 | Facility inside HUC 05120201 | This tree, Stage D |

`P(sfha | hydro)` is the predicted probability that a 30 m cell is inside the current-effective Special Flood Hazard Area, given hydrologic covariates. It is not a 100-year exceedance probability.

## Geography lock

Upper White HUC-8 **05120201**. FIPS state 18. Expanding the HUC is a new stage.

Template raster: NLCD 2021 Percent Developed Impervious (`NLCD_2021_Impervious_L48`), 30 m, EPSG:5070, clipped to the HUC. Every later raster warps to that grid. Zero is a valid percent; MRLC WMS GeoTIFFs that tag nodata=0 are rewritten so 0 is kept and 255 is nodata. A fixture template is allowed for Stage 0 CI. Stage A refuses a fixture template.

HUC source: USGS WBD MapServer layer 4 (8-digit HU), `huc8='05120201'`, `outSR=4269`. Simplification `maxAllowableOffset=0.0001` degrees (~11 m). Area must fall in 6000 to 8000 km² when the WBD `areasqkm` field is present. States must include IN when that field is present.

Vector layers stay EPSG:4269 until an explicit, logged warp.

## Stages

| Stage | Job | Success |
|-------|-----|---------|
| **0** | Pin, claims, occupancy freeze, HUC clip, 30 m 5070 template | Freeze numbers match; claim scan clean; HUC non-empty; template CRS 5070 at 30 m |
| **A** | Ingest DEM, NHD, soils, FIRM (all zones), TRI points and pounds, 2008 OFR overlap mask | Shared template transform; SFHA has 0 and 1; 2008 mask file exists (fraction may be small); TRI error budget written |
| **B** | TWI, HAND, distance, stack | Finite TWI on interior; toy-watershed test green |
| **C** | Spatial block CV, XGBoost, `p_sfha.tif` | PR-AUC above SFHA-rate baseline; Brier; no test HUC-10 in train; report names `P(sfha\|hydro)` |
| **D** | Sample TRI in-HUC; tables D1 and D2; SHAP; Folium | Both tables written; pounds column `on_site_release_lb` with year; every row `huc=05120201` and `state=IN` |

Do not skip. Stage C does not start without A and B reports. Stage D does not start without C metrics and a 2008 overlap mask.

## Tables D1 and D2

| Table | Definition |
|-------|------------|
| D1 | Facility in 05120201, FEMA Zone X (or `sfha_tf=F`), `P(sfha \| hydro) ≥ t` |
| D2 | Facility in 05120201, FEMA Zone X, inside 2008 inundation (OFR 2008-1322) or HWM buffer |

Thresholds: 0.50, 0.75 (headline), 0.90, plus expected pounds `sum(P * on_site_release_lb)`. Publishing D1 as missing FEMA maps without D2, or without the overlap mask, fails the claim scan / graph.

TRI pounds are on-site releases from Form R for a tagged year. Storage is not the metric.

## Occupancy freeze (imported)

Locked numbers from sibling Stage 0, 2026-08-25:

- `n_tris_joinable`: 2897
- `n_in_sfha`: 120
- `share_in_sfha`: 0.041422
- `crs`: 4269
- `n_dropped_missing_xy`: 13

File: `data/frozen/sibling_stage0_occupancy.json`. Rewriting it requires an explicit unfreeze.

## Claim bans (software-scanned on every report)

- Casualty language: death, deaths, fatality, fatalities, casualty, casualties, killed, injuries as a count of people
- Climate attribution: CMIP, downscaled GCM, “climate made”
- Tornado counts
- Population-at-risk or “lives” tallies
- TRI storage as the pounds metric
- `P` as a 100-year exceedance
- Phrase “unmapped risk”
- Occupancy share presented as this tree’s measurement

Allowed: “SFHA-like hydrology outside Zone A/AE”, “June 2008 inundation (OFR 2008-1322) outside current SFHA on reach X”, on-site release pounds, Brier, PR-AUC.

## GraphForge

Pin: `whiteforge/`. Sibling engine at `~/graphforge`. Verify-before-done is the finish gate; the pin does not re-encode it.

Laws: `white.stage_gate`, `white.claim_bans`, `white.stage0_import_freeze`, `white.stale_map`.

## Hard gate (Stage 0)

Pass only if all of these hold:

1. Freeze file matches the locked numbers above.
2. Claim scan of the report artifacts returns clean.
3. HUC polygon is non-empty and coded 05120201.
4. Template CRS is EPSG:5070 and resolution is 30 m.
5. Product laws allow Stage 0.

## Revisions

- 2026-08-26: locked the five-stage table, occupancy freeze, D1/D2, Upper White 05120201, WhiteForge pin.
- 2026-08-26: live WBD HUC-8 fetch and NLCD 2021 impervious template (30 m, EPSG:5070, MRLC WMS, tiled).
