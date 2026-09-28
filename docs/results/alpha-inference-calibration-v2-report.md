# Alpha inference calibration v2 — closed substantive failure

Status: `FAIL`

Workflow run: `36476033206`

Main commit: `fb08ab3debd4890c3ce12aa36d0e1800f094230f`

Frozen spec SHA-256: `df82d685d62b0c55a789e79076d97a99b1fd37c344f8615b7312d280302e3973`

Artifact ZIP SHA-256: `e63f2cde44d5debd0766ae2453f8de1a994dfa1b221b41a2cc634d3c9c996d02`

## What happened

The v2 workflow executed normally, completed all 40 registered synthetic cells, wrote a complete JSON result artifact, and then exited with code 2 because the frozen contract returned `primaryStatus: FAIL`. This is not an infrastructure failure and must not be rerun with another seed or promoted sensitivity.

All 16 primary DGP × horizon × calendar-depth cells failed at least one registered tolerance. `dateMean` materially undercovered in 16/16 primary cells. The failure was not confined to highly persistent DGPs: IID null cells also materially undercovered. At H126 / 312 weeks / 52-week primary blocks, `dateMean` coverage was 0.8733 under IID and 0.8767 under WEAK_SERIAL; `selectedMean` coverage was 0.8733 and 0.8567 respectively. Directional false-positive excess also appeared in several primary cells.

Across all registered v2 block lengths, no sensitivity cell fully passed every registered statistic/tolerance. Therefore the result does not support replacing the failed primary block with a favorable sensitivity block.

## Interpretation

V2 repaired the non-circular endpoint-inclusion asymmetry from v1 and changed the interval to a centered/basic bootstrap interval, but material undercoverage persisted. With the frozen calendars, the primary H126 rule has only six effective 52-week blocks at 312 weeks and twelve at 624 weeks. The observed failure therefore points away from another small block-length adjustment and toward a different finite-sample inferential construction.

V2 is closed. Historical Alpha outcomes remain unopened by this calibration program.
