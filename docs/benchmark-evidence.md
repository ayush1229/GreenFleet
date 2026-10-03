# Verified synthetic benchmark evidence

This is a software demonstration, not real-world accuracy or savings evidence.
The final experiment used **20 paired seeds**, **160 fleet runs** (four methods,
two comparison protocols), **200 separate prediction reports**, and **80 tiny
frontier comparisons**. All 160 fleet runs completed with verified feasible
plans; every tiny comparison reached the known exact frontier.

Held-out decisions were kept fixed. The realized case is explicitly
`independent_adverse`; the first replay changed energy from 8,604 MJ to 13,446 MJ.
Unknown compliance remained separate from successful operational planning.

The 2,000-candidate cap was reached. The 10/50/100-vessel generation attempts
also reached the cap and are recorded as **not benchmarked**, not successful
large-scale evidence. LNG, methanol, hydrogen and ammonia cases remain excluded
without valid vessel/pathway/port data. No optimizer superiority is established.

- Local detailed manifest: `outputs/benchmarks/benchmark-ad380cc886504c41811d89bd63d45c46/manifest.json`
- Frozen settings: same directory, `frozen-inputs.json`
- Reproducibility check: `outputs/verification/benchmark-evidence.json`
- Checked summary: [benchmark-summary.csv](benchmark-summary.csv)
- Convergence figure: [benchmark-convergence.svg](benchmark-convergence.svg)

Core source commit: `76a54f9`. Every method within a comparison has the same
dataset, split, candidate, factor and evaluator hash. The manifest includes
versions/hardware, actual calls, timeouts, failures, normalization, paired
intervals, exclusions, scales, ablations and scenario cases. Fixed reference
predictors use zero/one fit; QIE and random tuning share a four-fit budget.
Earlier development experiments are preserved under `outputs/archive` and are
not shown as current UI evidence.
