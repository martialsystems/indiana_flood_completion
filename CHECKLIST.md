# Checklist

Status as of **2026-08-27:** D tables, Folium map, SHAP, interview note, README cartography, and five-site parcels on disk. gSSURGO C2 not run. B closed.

## Stage 0

- [x] Methodology lock (05120201, pixel unit, D1/D2, occupancy freeze, claim bans)
- [x] Stage A codebook lock (2008 mask 0/1/2, FIRM `zone_class`, D1=`unshaded_x`)
- [x] WhiteForge pin (stage order, claims, import freeze, stale map)
- [x] Occupancy freeze file (`2897` / `120` / `0.041422`)
- [x] Claim scanner (sibling bans plus this tree)
- [x] Fixture Stage 0 path (`tests/fixtures/huc.geojson` + 30 m 5070 template)
- [x] Live WBD clip for 05120201
- [x] Live NLCD 2021 impervious template (4826x4252, 30 m, EPSG:5070; 0% kept)
- [x] Private GitHub remote (`martialsystems/indiana_flood_completion`)

## Later work

- [x] Stage A: DEM, NHD, TRI pounds, 2008 three-state mask (OFR 2008-1322 Appendix 2 only)
- [x] Stage A FIRM recount: NFHL layer 28, no `FLD_ZONE` filter, gate samples `unshaded_x`, floodway in `sfha==1` (unshaded_x 6,986,426; unmapped 7,480)
- [ ] Stage A HSG: Indiana gSSURGO 10 m (tiled SDA is `hsg_incomplete`)
- [x] Stage B: TWI / HAND stack (flow-path HAND, slope floor, waterbody distance)
- [x] Stage C: HUC-10 CV + XGBoost + `p_sfha.tif` (no HSG; HAND-nodata excluded)
- [x] Stage C addendum: isotonic OOF `p_sfha_calibrated.tif`
- [x] Stage D: D1/D2 tables from calibrated P
- [x] Folium map (calibrated P, five office vs max cells)
- [x] SHAP global + five max cells
- [x] README cartography (disagreement, five zooms, two 2008 reaches)
- [x] Five-site parcels (`logs/parcels/`; D tables untouched)
- [x] Research note PDF (`docs/interview_note.pdf`)
- [ ] gSSURGO C2 (must not rewrite D)
