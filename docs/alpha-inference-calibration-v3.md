# Alpha inference calibration v3 — self-normalized fixed-b interval

This is a synthetic-only methods revision after two separately frozen block-bootstrap calibration contracts failed their own null-coverage criteria. It is not an Alpha experiment and does not read historical returns, labels, scores, predictions, or `signal-history` outcomes.

## Why v3 exists

V1 used a non-circular moving-block bootstrap and materially undercovered. V2 removed endpoint inclusion asymmetry with circular blocks and used a centered/basic interval, yet all 16 primary cells still failed at least one frozen tolerance and every registered block-length sensitivity had zero fully passing cells. The failure included IID null cells, so simply choosing another block length would not be a defensible repair.

The v3 response is therefore not to promote a favorable sensitivity or relax the 95% material-coverage floor. It removes the block-length tuning parameter from the primary evaluation interval.

## Method

For each registered date-level statistic series `x_1,...,x_n`, the estimand is its arithmetic mean. Define prefix sums `S_t` and

`W_n = n^-2 * sum_{t=1}^n (S_t - (t/n) S_n)^2`.

The confidence interval is

`x_bar +/- sqrt(c * W_n / n)`,

where `c = 66.57` is the frozen 97.5% upper critical value of the scalar pivotal distribution

`U_1 = B(1)^2 / integral_0^1 (B(r) - r B(1))^2 dr`.

Shao (2010, JRSS B 72(3), 343–366, DOI 10.1111/j.1467-9868.2009.00737.x; corrigendum DOI 10.1111/j.1467-9868.2010.00754.x) gives the recursive-estimate self-normalized confidence-region construction and relates it to fixed-b inference with the Bartlett kernel at `b=1`. Lobato (2001, JASA 96, 1066–1076) tabulates the pivotal critical values; an independently reproduced table gives 66.57 for `q=1` at 97.5%.

This construction is deliberately less power-oriented than a finely tuned HAC/bootstrap rule. Its purpose here is size/coverage discipline before any historical outcome access.

## Frozen synthetic contract

V3 retains the v2 synthetic null DGPs, horizons, calendar depths, statistics, 300 Monte Carlo replications, 97.5% claim-level confidence, 95% material-coverage floor, 5% directional false-positive ceiling, 5% undefined ceiling, and 4pp Monte Carlo half-width ceiling. It uses a new seed `20260930` frozen before implementation results.

The block candidate grid is not carried into v3 because block length is no longer an inferential tuning parameter. V1/v2 block sensitivities may not be used to tune v3.

## Stopping rule

After this protocol is merged, run `Synthetic alpha inference calibration v3` exactly once on `main`.

- Complete `PASS`: the synthetic null calibration requirement is closed for this interval mechanic. This says nothing about historical Alpha or deployability.
- Complete `FAIL`: v3 is closed. Do not change the pivotal critical value, seed, DGPs, calendar depths, or tolerances to rescue it.
- Runtime/transport failure before a complete artifact exists: an identical rerun is allowed after an infrastructure-only repair.

No historical Alpha outcome may be accessed as part of this calibration step.
