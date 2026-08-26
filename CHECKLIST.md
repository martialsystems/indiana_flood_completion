# Checklist

Status as of **2026-08-26:** Stage 0 live WBD + NLCD 2021 template on disk. Fixture path remains the CI join. Stage A may start.

## Stage 0

- [x] Methodology lock (05120201, pixel unit, D1/D2, occupancy freeze, claim bans)
- [x] WhiteForge pin (stage order, claims, import freeze, stale map)
- [x] Occupancy freeze file (`2897` / `120` / `0.041422`)
- [x] Claim scanner (sibling bans plus this tree)
- [x] Fixture Stage 0 path (`tests/fixtures/huc.geojson` + 30 m 5070 template)
- [x] Live WBD clip for 05120201
- [x] Live NLCD 2021 impervious template (4826x4252, 30 m, EPSG:5070; 0% kept)
- [x] Private GitHub remote (`martialsystems/indiana_flood_completion`)

## Later work

- [ ] Stage A: DEM, NHD, soils, FIRM all zones, TRI pounds, 2008 overlap mask
- [ ] Stage B: TWI / HAND stack
- [ ] Stage C: HUC-10 CV + XGBoost + `p_sfha.tif`
- [ ] Stage D: D1/D2 tables, SHAP, Folium
- [ ] Research note PDF
