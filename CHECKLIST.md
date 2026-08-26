# Checklist

Status as of **2026-08-26:** Stage A report on disk. Martinsville and Paragon Appendix 2 rasters intersect 05120201 (measured). Stage B has not started.

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

- [x] Stage A: DEM, NHD, soils, FIRM zone codebook, TRI pounds, 2008 three-state mask (OFR 2008-1322 Appendix 2 only)
- [ ] Stage B: TWI / HAND stack
- [ ] Stage C: HUC-10 CV + XGBoost + `p_sfha.tif`
- [ ] Stage D: D1/D2 tables, SHAP, Folium
- [ ] Research note PDF
