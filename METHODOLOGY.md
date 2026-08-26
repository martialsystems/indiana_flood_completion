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
| **A** | Ingest DEM, NHD, soils, FIRM (all zones), TRI points and pounds, 2008 three-state mask | Shared template transform; `sfha` ∈ {0,1} **and** `zone_class` codebook written; 2008 mask unique values include code 1, and code 2 if any Appendix 2 raster intersects the HUC; TRI error budget fields listed below |
| **B** | TWI, HAND, distance, stack | Finite TWI on interior; toy-watershed test green |
| **C** | Spatial block CV, XGBoost, `p_sfha.tif` | Report title and colorbar say `P(sfha \| hydro)`; PR-AUC above the SFHA-rate baseline; Brier vs that same constant; no test HUC-10 in train, including a 1-pixel halo; HAND-thresholded SFHA logged on the held-out HUC-10s |
| **D** | Sample TRI in-HUC; tables D1 and D2; SHAP; Folium | Both tables written; D1 filter is `zone_class == unshaded_x`; D2 is mask code 2; coverage split (`ofr_reaches_intersecting_huc`, `d2_n_code1`, `d2_n_code2`) present even if D2 is empty; pounds column `on_site_release_lb` with year; occupancy is `n_tris_huc_year` only; freeze path cited; every row `huc=05120201` and `state=IN` |

Do not skip. Stage C does not start without A and B reports. Stage D does not start without C metrics and a 2008 three-state mask.

## FIRM zone codebook (Stage A)

`sfha == 0` is not D1. It mixes unmapped cells, Zone D, open water, area not included, and Zone X. Rasterize two bands on the template grid:

| Band | Values |
|------|--------|
| `sfha` | 1 if `SFHA_TF` is true, else 0 |
| `zone_class` | `unmapped`, `sfha`, `floodway`, `shaded_x`, `unshaded_x`, `D`, `other` |

Codes live in `floodmap.codes`. D1 filter is `zone_class == unshaded_x`. Shaded X (0.2% annual chance) is a mapped FEMA moderate-hazard zone: it is still Zone X in speech and is **not** eligible for D1. Count shaded X in a sensitivity column. D1 headers say “SFHA-like hydrology outside Zone A/AE” and name the filter `unshaded_x`, not `sfha==0`.

## 2008 three-state mask (Stage A)

OFR 2008-1322 is the June 7-9, 2008 White River Basin flood. Appendix 2 GIS is **reach-scale**, not a basin layer: surveyed high-water marks on about 50 miles of stream in nine communities (Columbus, Edinburgh, Franklin, Paragon, Seymour, Spencer, Martinsville, Newberry, Worthington). Most of those reaches are outside 05120201. Zeros on a naive boolean warp mean “never mapped,” not “dry in June 2008.”

Pin the artifact: Appendix 2 ERDAS `.img` depth / WSE grids from https://pubs.usgs.gov/of/2008/1322/, plus the HWM table if buffers are used. Do not substitute later SIM inundation libraries (Spencer SIM 3251, Newberry SIM 3231) unless this file grows a new row.

Mask codes (uint8, `floodmap.codes`):

| Code | Meaning |
|------|---------|
| 0 | outside HUC (template nodata) |
| 1 | inside HUC, no OFR inundation grid and no HWM buffer |
| 2 | inside an OFR inundation raster or HWM buffer |
| 3 | optional: HWM point buffer only, if points are kept separate from the `.img` grids |

Stage A unique values must include code 1. If any Appendix 2 raster intersects the HUC, they must also include code 2. Cite the product as “June 7-9, 2008 inundation (OFR 2008-1322)”. Do not paste the OFR abstract (it contains deaths and evacuations and will fail the claim scan).

## Tables D1 and D2

| Table | Definition |
|-------|------------|
| D1 | Facility in 05120201, `zone_class == unshaded_x`, `P(sfha \| hydro) ≥ t` |
| D2 | Facility in 05120201, `zone_class == unshaded_x`, 2008 mask code 2 |

Thresholds: 0.50, 0.75 (headline), 0.90, plus expected pounds `sum(P * on_site_release_lb)`.

If D2 has zero rows, that is a **coverage** result, not a flood-safety result. The D-report must list which named Appendix 2 reaches intersect the HUC and how many in-HUC TRI points fall in mask code 1 vs code 2. Publishing “no 2008 overlap” without that split fails `white.claim_bans` (`d2_without_coverage_split`). Publishing D1 as missing FEMA maps without D2, or using `sfha==0` as the D1 filter, fails the same graph.

TRI pounds are on-site releases from Form R for a tagged year. Storage is not the metric. Dioxin rows stay in grams and are counted, not mixed into pounds.

## TRI error budget (Stage A)

Required fields: `n_dropped_missing_xy`, `n_dropped_out_of_huc`, `n_dropped_non_in`, `n_dioxin_rows_held_grams`, `reporting_year`, `n_excluded_off_site`, `n_tris_huc_year`.

This tree’s only occupancy number is `n_tris_huc_year`: facilities with valid xy, `huc=05120201`, `state=IN`, tagged TRI year.

## Occupancy freeze (imported)

Locked numbers from sibling Stage 0, 2026-08-25:

- `n_tris_joinable`: 2897
- `n_in_sfha`: 120
- `share_in_sfha`: 0.041422
- `crs`: 4269
- `n_dropped_missing_xy`: 13

File: `data/frozen/sibling_stage0_occupancy.json`. Rewriting it requires an explicit unfreeze.

`n_tris_joinable: 2897` is larger than a single-year Indiana TRI facility count. That is expected if the sibling joined a broader FRS `TRIS` extract. Leave it frozen. Do not print `share_in_sfha: 0.041422` in Stage D. The D-report cites `imported_occupancy_path` so a reviewer does not reconcile 2897 with the in-HUC point file.

## Claim bans (software-scanned on every report)

- Casualty language: death, deaths, fatality, fatalities, casualty, casualties, killed, injuries as a count of people
- Climate attribution: CMIP, downscaled GCM, “climate made”
- Tornado counts
- Population-at-risk or “lives” tallies
- TRI storage as the pounds metric
- `P` as a 100-year exceedance
- Phrase “unmapped risk”
- Occupancy share presented as this tree’s measurement; `share_in_sfha` as a top-level Stage D field
- Phrase “no 2008 overlap” without the code-1 / code-2 split and named reaches

Allowed: “SFHA-like hydrology outside Zone A/AE”, “June 7-9, 2008 inundation (OFR 2008-1322)”, on-site release pounds, Brier, PR-AUC vs the SFHA-rate constant, HAND-thresholded SFHA on held-out HUC-10s.

Stage C may still pass if XGBoost does not beat a HAND threshold on held-out HUC-10s. The D-report then says the industrial overlay is mostly terrain, not the booster. Filename `p_sfha.tif` is allowed; the colorbar is `P(sfha | hydro)`.

Spatial CV: grouped by HUC-10. No test pixel from a train HUC-10, including a 1-pixel halo. Streams ignore HUC-10 lines.

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
- 2026-08-26: Stage A success table: FIRM zone codebook, 2008 three-state mask (OFR 2008-1322 Appendix 2 is reach-scale), D1=`unshaded_x`, D2=mask code 2, TRI error budget, occupancy is `n_tris_huc_year`.
- 2026-08-26: Stage A fetch: warp_to_template on live nlcd_2021; all 17 Appendix 2 zips downloaded; only intersecting reaches paint mask code 2; Martinsville/Paragon intersection measured.
