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
| **A** | Ingest DEM, NHD, soils, FIRM (all zones), TRI points and pounds, 2008 three-state mask | Shared template transform; `sfha` ∈ {0,1} **and** `zone_class` codebook written; FIRM from NFHL S_FLD_HAZ_AR with `where=1=1`; gate samples at Monument Circle, Carmel till-plain, and a Delaware field are `unshaded_x`; `unshaded_x` > `sfha`; floodway cells have `sfha==1`; 2008 mask unique values include code 1, and code 2 if any Appendix 2 raster intersects the HUC; TRI error budget fields listed below. HSG may be marked `hsg_incomplete` |
| **B** | TWI, HAND, distance, stack | Finite TWI on interior cells where DEM is finite; toy-watershed test green; every band on transform sha256 `479ac37628bfd7e5`; `firm_unshaded_x_ok` required to start |
| **C** | Spatial block CV, XGBoost, `p_sfha.tif` | Report title and colorbar say `P(sfha \| hydro)`; PR-AUC above the SFHA-rate baseline; Brier vs that same constant; no test HUC-10 in train, including a 1-pixel halo; HAND-thresholded SFHA logged on the held-out HUC-10s |
| **D** | Sample TRI in-HUC; tables D1 and D2; SHAP; Folium | Both tables written; D1 filter is `zone_class == unshaded_x`; D2 is mask code 2; coverage split (`ofr_reaches_intersecting_huc`, `d2_n_code1`, `d2_n_code2`) present even if D2 is empty; pounds column `on_site_release_lb` with year; occupancy is `n_tris_huc_year` only; freeze path cited; every row `huc=05120201` and `state=IN` |

Do not skip. Stage C does not start without A and B reports. Stage D does not start without C metrics and a 2008 three-state mask.

## FIRM zone codebook (Stage A)

`sfha == 0` is not D1. It mixes unmapped cells, Zone D, open water, area not included, and Zone X. Rasterize two bands on the template grid:

| Band | Values |
|------|--------|
| `sfha` | 1 if the cell is SFHA, including floodway (`ZONE_SFHA` or `ZONE_FLOODWAY`); 0 otherwise |
| `zone_class` | `unmapped`, `sfha`, `floodway`, `shaded_x`, `unshaded_x`, `D`, `other` |

Source is FEMA NFHL MapServer layer 28 (`S_FLD_HAZ_AR`), `where=1=1`, clipped to the HUC polygon. Do not filter `FLD_ZONE` to A/AE/floodway/0.2%. IndianaMap FIRM 2023 omitted `AREA OF MINIMAL FLOOD HAZARD` polygons: those cells painted as `unmapped` and would have excluded Indianapolis mapped Zone X from D1.

Classification: `FLD_ZONE` X with empty `ZONE_SUBTY` or `AREA OF MINIMAL FLOOD HAZARD` is `unshaded_x`. `0.2 PCT ANNUAL CHANCE FLOOD HAZARD` is `shaded_x`. Floodway is SFHA: every floodway cell must have `sfha==1`.

Live gate samples (must be `unshaded_x` if the FIRM is whole):

| Name | Lon, lat | Place |
|------|----------|-------|
| `monument_circle` | -86.1581, 39.7684 | Downtown Indianapolis, off the floodway |
| `carmel_tillplain` | -86.118, 39.978 | Hamilton County till-plain suburb |
| `delaware_field` | -85.40, 40.20 | Rural Delaware County field |

On the live HUC template, `unshaded_x` must exceed `sfha`. Unmapped cells should be limited to communities that have no modern FIRM.

Live interior 2026-08-27 (NFHL layer 28, `where=1=1`, 7,830,039 cells):

| `zone_class` | cells | km² | share of interior |
|--------------|------:|----:|------------------:|
| unshaded_x | 6,986,426 | 6287.8 | 89.23% |
| sfha | 449,907 | 404.9 | 5.75% |
| floodway | 308,139 | 277.3 | 3.94% |
| shaded_x | 78,087 | 70.3 | 1.00% |
| unmapped | 7,480 | 6.7 | 0.10% |

Binary `sfha==1` is 758,046 cells, equal to floodway + sfha. Gate samples (Monument Circle, Carmel, Delaware field) are `unshaded_x`.

Codes live in `floodmap.codes`. D1 filter is `zone_class == unshaded_x`. Shaded X (0.2% annual chance) is a mapped FEMA moderate-hazard zone: it is still Zone X in speech and is **not** eligible for D1. Count shaded X in a sensitivity column. D1 headers say “SFHA-like hydrology outside Zone A/AE” and name the filter `unshaded_x`, not `sfha==0`.

HSG from tiled SDA `TOP 4000` per 0.25° tile is incomplete (~15% of the interior on 2026-08-26). Stage A may record `hsg_incomplete` and keep code 255 as `hsg_missing`. Stage C may start without HSG. Do not train C on the 15% SDA scrape. When the Indiana gSSURGO 10 m band exists and `hsg_missing` is not the majority interior class, that is a C addendum or a second model, not a silent column drop-in.

## Stage B hydrology

Inputs: live template DEM, NHD Flowline `ftype=460`, NHD Waterbody, NHD Area `ftype=460`. Order:

1. Slope (radians) from the display DEM. Till-plain cells have tan β near 0. Floor β at 0.001 rad (~0.057°) when computing TWI. Log `n_slope_floor`.
2. Hydroconditioned copy: burn NHD flowlines, waterbody polygons, and Area StreamRiver 50 m, then priority-flood fill with those cells as seeds. D8 and accumulation run on that copy.
3. HAND: raw DEM elevation minus elevation of the drained stream cell along D8. Not Euclidean height to the nearest painted stream pixel. Stream mask is the burned network (flowline ∪ waterbody ∪ area 460).
4. Distance: Euclidean metres to flowlines (`dist_flowline`) and separately to waterbodies (`dist_waterbody`). Geist, Morse, and Eagle Creek are waterbodies, not flowlines.
5. TWI = ln(α / tan β) with α = (acc+1) × 30 m from the conditioned accumulation. Interior nodata only where DEM is nodata. No inf.

Write `slope`, `twi`, `hand`, `dist_flowline`, `dist_waterbody` as separate COGs plus `stack_manifest.json`. Do not materialize 7.83M × k as a dense float64 matrix. Do not put HSG in the stack.

HAND nodata (cells that never reach NHD along D8): exclude from train/test; write nodata in `p_sfha.tif`. Do not fill with 0. Stream cells are native NHD paint (`all_touched=True`), not an extra buffer: log flowline-only vs waterbody-only vs overlap vs Area 460 remainder on the B report before C samples.

## Stage C

Train on binary `sfha` (floodway included). Do not train on `zone_class`. D still filters `unshaded_x`.

Features: `slope`, `twi`, `hand`, `dist_flowline`, `dist_waterbody`, `nlcd_impervious`. No HSG in this commit.

Sampling: do not load 7.83M rows as a dense matrix. Take all eligible SFHA ones plus 3× non-SFHA, with extra weight on `unshaded_x` within 300 m of a flowline or waterbody. Drop HAND-nodata.

Blocks: WBD 10-digit HU (17 watersheds in 05120201). Leave-one-HUC-10-out. No test HUC-10 in train, including a 1-pixel halo. Metrics on all eligible held-out cells, not the stratified train sample.

Pass: PR-AUC above the SFHA-rate constant; Brier vs that constant logged; report and colorbar say `P(sfha | hydro)`; file `p_sfha.tif`. If the booster barely beats a HAND score, still pass C and say so. Stratified sampling plus class weight can rank well while Brier is worse than the constant: log `probabilities_calibrated` as false on the raw raster. Fit isotonic on OOF scores with the same HUC-10 cuts (no test-fold labels). Write `p_sfha_calibrated.tif` with the HAND-nodata mask unchanged. Keep `p_sfha.tif`. Do not treat 0.75 as a cutoff in C. Do not write D1/D2 in C. Do not touch OFR or TRI.

Stage D samples `p_sfha_calibrated.tif` only. `p_source=p_sfha_calibrated.tif`. Thresholds 0.50 / 0.75 / 0.90. Headline D1 is `zone_class == unshaded_x` and buffer-max P ≥ 0.75. Report n_not_d1 (plants already in floodway / SFHA / shaded X / unmapped) as the denominator next to the 101. Expected pounds is `sum(P_max * on_site_release_lb)` on the headline rows after the five-row table, not as a lead figure. Naming those plants without `p_mean` fails the claim scan. Buffer-max is a 30 m edge of the 120 m window; buffer-mean is the footprint. If P_max is off the office cell on NHD water or floodway, the note is `adjacent_hydro_cell`. D2 is unshaded X and 2008 mask code 2 at the facility cell. Empty D2 is coverage: list Martinsville and Paragon, print in-HUC TRI counts in mask code 1 vs 2. HSG omitted is an accepted C state. Do not start D from raw P.

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
- 2026-08-27: FIRM source switched to FEMA NFHL layer 28, `where=1=1`. IndianaMap 2023 left Monument Circle, Carmel, and a Delaware field as `unmapped`. Gate samples must be `unshaded_x`. Binary `sfha==1` includes floodway. HSG tiled SDA marked `hsg_incomplete`. Stage B blocked until `firm_unshaded_x_ok`.
- 2026-08-27: Stage B hydrology: slope floor 0.001 rad, NHD burn + waterbodies, flow-path HAND, TWI, separate COGs. HSG stays out of the stack. Stage C not started.
- 2026-08-27: Stage C: binary sfha labels, HUC-10 leave-one-out with 1-pixel halo, HAND-nodata excluded, no HSG, `P(sfha | hydro)`. Stage D not started.
- 2026-08-27: C addendum: isotonic OOF calibration, `p_sfha_calibrated.tif`. Stage D tables from calibrated P, buffer max/mean, D2 coverage split. Raw `sum(P*lb)` not shipped.
- 2026-08-27: D finding narrowed: 16 not-D1 as denominator; five-row edge screen with P_mean; P_max cell GIS note (adjacent hydro vs neighboring land). Claim scan fails D1 names without p_mean.
- 2026-08-27: Folium map of calibrated P, zone_class, OFR code 2 as two named polygons (Martinsville, Paragon), 117 points, five office-to-max cells. SHAP global (HAND first) plus the five max cells. gSSURGO C2 not run.
- 2026-08-27: README lead is the five-sentence claim graph: map-completion P, OOF PR-AUC, five Zone X wet cells, THURSDAY POOLS (p_mean 0.152) neighboring land, 2008 not the industrial core. Map and SHAP are close-outs. Do not reopen D, B, or raw P.
- 2026-08-27: Interview note PDF (`docs/interview_note.pdf`): abstract, Table 1, Figure 2, portfolio/talk/uses, Stage C metrics, limitations. Does not reopen D, B, or raw P.
- 2026-08-27: README cartography: basin disagreement (unshaded X and P >= 0.75 vs mapped SFHA), five office-to-max zooms, two OFR 2008 reaches on the same HUC. Calibrated P only. Does not reopen D.
- 2026-08-27: Five-site Indiana 2025 parcels in `logs/parcels/` (snap 30 m). Tightens adjacent hydro. Does not rewrite D tables.
- 2026-08-27: Interview note PDF updated with Figures 1 to 4 (disagreement, zooms, 2008 reaches, five-site parcels). D tables unchanged.
