# Implementation and handover

Implemented in `D:\project\SIH_Spare` on the local `feat/greenfleet` branch.
Python 3.11 virtual environment: `.venv`. Dependencies are installed and pinned
in `pyproject.toml` and `requirements.lock`. No remote repository was configured.

## Delivery map

| Plan task | Implemented artifacts | Acceptance evidence |
|---|---|---|
| 1: contracts and ingestion | Frozen records, unit-aware JSON bundle loader, deterministic fixture, manifest hashing, validation UI | Unit conversion, invalid rows, digest changes and status-domain tests |
| 2: prediction | Temporal/unseen split manifests, engineering/direct/residual models, train-only preprocessing and interval calibration | Leakage, unsupported speed, interval/report and unobserved-vessel tests |
| 3: accounting | Engine/pathway compatibility, separate sea/auxiliary/shore energy, nominal/adverse totals, inventory cost convention | Hand-calculated MJ/kg CO2e, no double-counting, missing-factor and purchase tests |
| 4: candidates and checker | Explicit service/reposition/bunkering/changeover choices; independent paths, inventory, weather, berth, pump and shore checks | Two-trip fuel, port contention, location/time, deadlines, cap and speed-grid tests |
| 5: conventional planner | Greedy insertion, exact tiny enumeration, structural capacity witness, separate failure/proof statuses | Hand frontier, independently checked plans and incomplete-search tests |
| 6: research methods | QIE sampling/rotation/reset; bounded classical predictor tuning; ALNS and NSGA-II using the shared evaluator | Seeds/budgets, leakage, feasible archive, refuelling and exact-frontier comparisons |
| 7: experiments | Paired seed runner, evaluation/time ceilings, predictive reports, ablations, case matrix, scale caps, held-out fixed-decision replay | Paired manifest, undefined metrics and explicit realized-case tests; saved synthetic experiment |
| 8: platform and handover | Streamlit controls/Pareto/plans/provenance, cancellation, unique run storage, atomic CSV/JSON/Markdown exports and CLI | Export recomputation, concurrent runs, cancellation audit, UI walkthrough and server health |

## Verification

`python -m pytest -q`: **51 passed**. `pip check`: no broken requirements.
Python compilation and `git diff --check` passed. The Streamlit testing harness
walked through feasible, impossible-demand, missing-factor and hard-rule cases
without UI exceptions, and generated report ZIPs. CSV, JSON and Markdown exports
were opened and parsed. The local server's health endpoint returned `ok`.
A connected browser was unavailable; browser screenshot inspection was not performed.

A fresh independent code reviewer identified four Important issues. Regression
tests reproduced and fixed each: optional-weather physical-check bypass, hard-rule
effective dates, held-out case selection, and reports for vessels without history.
Additional final checks preserved cancellation logs and corrected the tiny test
fixture and repositioning speed grid. No review findings were deferred as minor.

## Decisions and limits

- The folder initially contained only the plan. A new local repository and
  development branch were created in place; no existing code or branch was moved.
- The original referenced briefs were absent. The supplied detailed plan governs
  this implementation; domain decisions remain provisional if those briefs differ.
- No measured data, authoritative pathway factors or regulatory scope were
  supplied. The plan's synthetic demonstrator path was used. Accuracy, savings,
  optimizer superiority and operational certification remain unestablished.
- Windows PowerShell progress records were maintained directly instead of the
  skill's POSIX helper scripts. Tests and commits provide the execution evidence.
- This is the only branch of a newly created local repository, with no upstream or
  base branch to merge into. It is preserved in the requested workspace.
- JSON equivalent-table bundles are the supported upload format. CSV is used for
  reports; separate CSV/Parquet input directories require conversion to that bundle.
- The demo candidate cap is explicit. Limited candidate frontiers never prove
  whole-scenario infeasibility. 10/50/100-vessel comparisons are withheld when
  generation reaches the declared cap, rather than reported as successful scaling.
- Alternative fuels without complete source data are explicitly excluded. A
  constant sourced efficiency is supported; engine maps, geometry/zone segmentation,
  certification, real ship/load coverage and deployment authentication need domain
  data and further operational work. The week-1 sponsor/data gate and operational
  domain review remain open.

Run commands and interpretation are in `docs/user-guide.md`; the complete domain
decision register is `docs/decision-log.md`. Local evidence and outputs are under
`outputs/`, intentionally ignored by Git.
