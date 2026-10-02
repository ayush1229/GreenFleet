# GreenFleet user guide

## Start locally on Windows

The project includes `.venv` with Python 3.11 and installed dependencies. From
`D:\project\SIH_Spare` run:

```powershell
.venv\Scripts\python -m streamlit run app.py
```

Open the localhost URL printed by Streamlit. To recreate the environment:

```powershell
py -3.11 -m venv .venv
.venv\Scripts\python -m pip install -r requirements.lock
.venv\Scripts\python -m pip install -e . --no-deps
.venv\Scripts\python -m pytest -q
```

## Walkthrough

1. Keep the default synthetic fixture, or upload a `bundle.json` following
   `docs/data-dictionary.md`. The included `data/demo/bundle.json` is an example.
   Digests, units, references and rows are validated before planning. Uploaded
   filenames are never used as filesystem paths.
2. Choose demand, shore power, adverse weather, prices, candidate cap, method,
   predictor, seed and search budget. The financial convention is initial fuel
   inventory sunk: purchases count once; consumed-fuel value is separately shown.
3. Run the greedy baseline, then a selected algorithm. A background worker keeps
   cancellation responsive. Cancelled or failed runs withhold all recommendations.
4. Inspect Pareto plans with explicit MJ, configured currency and kg CO2e axes.
   Balanced selection uses the recorded fixed weights/scales. Lowest-cost and
   lowest-emissions selections come only from independently verified plans.
5. Inspect nominal/adverse cases, service schedules, fuel, rule scope, support and
   exclusions. A cap means limited coverage; a heuristic failure is not a proof.
6. Download the ZIP with deployment/purchases/rules/inventory CSVs, full summary,
   provenance JSON and Markdown. Each click/run has a unique directory. The
   original scenario, factors, sources, versions, dates, hashes and seeds travel
   with the export. Local outputs are excluded from Git.

`completed` with `unknown` compliance means operationally feasible under configured
constraints with compliance unverified. Requiring verified configured-rule
compliance with missing coverage prevents a recommendation. A configured-rule pass
is not a regulatory certificate. The demo hard emissions limit intentionally fails.

## Reproduce from the CLI

```powershell
.venv\Scripts\python -m greenfleet.cli demo
.venv\Scripts\python -m greenfleet.cli demo --method qie --budget 128
.venv\Scripts\python -m greenfleet.cli demo --case impossible
.venv\Scripts\python -m greenfleet.cli demo --case missing-factor
.venv\Scripts\python -m greenfleet.cli demo --predictor qie_tuned
.venv\Scripts\python -m greenfleet.cli benchmark --config configs/demo.yaml
```

The benchmark defaults to 20 paired seeds and separate evaluator/wall-clock
ceilings. It writes `outputs/benchmarks/benchmark-<id>/manifest.json`, summary CSV,
convergence SVG and report Markdown. The UI reads saved benchmark evidence. Full
real-data empirical conclusions remain blocked on measured observations and
sourced factors; the included run is explicitly synthetic.

## Limits and handover

Fixed routes, capacities and a discrete candidate universe are prototype choices.
The checker reconstructs explicit reposition, bunker, changeover and shore actions;
it accounts for idle hotel load between selected actions. It does not schedule
ocean geometry, retrofits, fuel mixing or live vessel control. Route-zone segments
must be represented as separate explicit service legs; arbitrary route geometry
is deferred until reliable zone/segment data exists. Weather multipliers are
scenario assumptions, not forecasts. Engine efficiency is a documented constant
in this profile. Unknown physical inputs exclude options; no universal alternative
fuel ranking is inferred. Curves/maps must be supplied for engineering/residual
prediction; unsupported ML estimates are never used numerically.

The synthetic default can hit its 2,000-action cap. It remains useful for a local
demonstration, but any frontier is limited. Raise the cap or narrow the fleet,
horizon or departure grid for broader coverage. Exact enumeration accepts at most
20 bits and proves whole-scenario infeasibility only for a complete unpruned set;
the capacity witness is independent of the candidate cap.

This is a local research application, without production authentication or
operational certification. Domain decisions and sponsor acceptance are tracked in
`docs/decision-log.md`. No empirical accuracy or savings are established here.
