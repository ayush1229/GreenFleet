# Case-study protocol

The committed bundle and test fixture freeze the conventional instance before
comparisons. `configs/demo.yaml` declares 20 paired seeds, fixed weights/scales,
and a reference point before any outcomes. The runner creates a unique experiment
directory containing frozen inputs, per-seed JSON, CSV, Markdown and convergence
SVG. Both evaluation-ceiling and wall-clock-ceiling comparisons record actual
evaluator/repair calls, generation time, fit costs, failure reasons and sampled RSS.

The conventional, shore-off, increased-demand, adverse-weather, price, grid and
pathway-intensity cases use explicit synthetic scenario changes. LNG, methanol,
hydrogen and ammonia are excluded unless complete vessel/pathway/port data exists.
10/50/100-vessel generation attempts publish cap limits; capped scale comparisons
are withheld. Prediction-only, fleet-only and combined ablations are explicit.

Known/unseen prediction reports stay separate. QIE and random predictor tuning
use equal fit budgets; fixed references transparently use fewer fits. Fleet
methods share one candidate universe/evaluator. Bootstrap intervals resample paired
seeds. Infeasible hypervolume and zero-denominator WAPE remain null. Pareto results
from capped candidates are approximate and cannot prove infeasibility.

Held-out decision replay keeps selected actions fixed and changes independently
simulated weather; it reports realized totals and schedule/fuel failures. No
counterfactual empirical regret or universal green-fuel ranking is claimed. All
software evidence in this repository remains a **synthetic demonstration** until
measured data, sourced factors, agreed operational selection weights and domain
review permit a real comparative experiment.
