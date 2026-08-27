# WhiteForge

GraphForge pin for this tree. **Not a second verify-before-done.**

Verify-before-done already runs as the home finish gate. This pin encodes
only the laws a graph can refuse here: stage order, claim bans, the
imported occupancy freeze, and a stale-public-map block when a dashboard
is published.

Engine checkout: `~/graphforge` (sibling clone, no pip). Mandatory engine
templates still run if you invoke `graphforge-gate`. They are not
re-implemented in `product_laws.py`.

## Laws

| ID | Blocks |
|----|--------|
| `white.stage_gate` | Unknown stage; skipping a stage; Stage A on a fixture template; Stage B without `firm_unshaded_x_ok`; Stage C without A/B reports; Stage D without C metrics or a 2008 overlap mask; Stage 0 complete without freeze verified |
| `white.claim_bans` | Casualties; climate attribution; tornado counts; population-at-risk; TRI storage as pounds; `P` as 100-year exceedance; D1 as missing maps without D2; D2 without the 2008 coverage split; D1 filtered on `sfha==0`; scoring facilities outside 05120201 |
| `white.stage0_import_freeze` | Rewriting `data/frozen/sibling_stage0_occupancy.json` without an explicit unfreeze; treating this tree as a replacement occupancy count |
| `white.stale_map` | Public dashboard publish that would regress a newer live payload, or publish without a live compare |

## Commands

```bash
export PYTHONPATH=~/graphforge/src:src:.
python3 whiteforge/scripts/sanity_whiteforge.py
python3 -m pytest tests/test_whiteforge_laws.py tests -q
```

Call sites: `scripts/run_stage0.py` refuses to print Stage 0 complete unless
`require_stage` allows it.
