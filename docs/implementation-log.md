# SDD ledger — plan: 2026-10-02-greenfleet-detailed-implementation (1).md
Execution: inline, Tasks 1–8, test-first, whole-branch fresh review at end.
Ruling: New empty folder, no repository or baseline tests — initialize dedicated feat/greenfleet branch in place; no existing checkout to isolate. Cost: none to existing code.
Ruling: Referenced original specs and operational data are absent — use detailed plan plus labelled synthetic profile; defer domain/empirical gates. Cost: no operational or accuracy claims possible.
Ruling: Windows PowerShell cannot directly run the POSIX skill helper scripts — maintain equivalent per-task briefs, test logs and commit ledger locally. Cost: bookkeeping is manual.
Pre-flight 1→2: Dataset observations need four disjoint partitions (train/validation/calibration/test), UTC intervals and vessel/voyage IDs.
Pre-flight 1→3→4: Frozen scenario and versioned factors shared by estimates and independent checker; recompute physical quantities instead of trusting cached candidate scores.
Pre-flight 4→5→6: Candidate completeness explicitly distinct from cap/pruning; structural witnesses derive from full scenario. Shared evaluator and archive across algorithms.
Pre-flight 2→6→7: Tuning uses only development IDs; calibration/test never tune; model fit budgets logged.
Pre-flight 5→7→8: Run and compliance statuses separate; no partial archive exported as final after cancel/fail; one unique output directory per run.
Tasks pending: 1,2,3,4,5,6,7,8.
Task 1: complete; tests/test_ingest.py tests/test_app_smoke.py 4 passed. Virtualenv Python 3.11; resolved dependencies locked. Synthetic/domain gate documented. UI exercised via Streamlit AppTest; server/browser validation at final handover.
Task 2: complete; focused and implemented suite 11 passed; RED missing split/predict modules then GREEN. Engineering, direct and residual GBM; UI baseline reports. Future: 128/40/40/48; unseen: 128/32/32/64 (train/validation/calibration/test).
Task 3: complete; accounting RED missing module then 5 focused / 16 implemented suite passed. Hand checks: 1080 MJ = 86.4 kg CO2e; shore replacement gives 1026 MJ and 24.75 kg fuel; purchases and consumed value separate.
Task 4: complete; RED missing modules then 7 focused / 23 implemented tests passed. Candidate hashes stable, explicit cap/exclusion metadata, independent path/weather/inventory/port/rule checker. Safe exclusions conservatively make complete=false, so no exact whole-scenario proof from a pruned set.
Task 5: complete; RED missing solver module then full suite 27 passed. Exact two-bit hand frontier (900 MJ, 0 purchase cost, 72 kg CO2e), four evaluations. Feasible and structural-impossibility engine demos exercised. Frozen instance: data/demo/bundle.json committed at Task 1 plus tests/test_solvers.py tiny.
Task 6: complete; 8 intended RED failures then 18 focused / 35 full suite passed. QIE bounded probability/reset/seed tests, same fit budgets and final-test isolation, all methods exact tiny agreement, ALNS refuelling preservation, independently feasible nondominated archive.
Task 6 test-count correction: 36 full suite tests, not 35.
Task 7: complete; RED missing module then 3 focused / 39 full suite passed. Paired equal evaluation/wall-time ceilings, fixed decision replay, null metrics, exact tiny gaps, prediction comparisons, ablations, scales and scenario matrix. Full 20-seed synthetic evidence run at handover; empirical claims deferred per plan.
Task 8: complete; 6 intended RED failures then 6 focused / 45 full suite passed. Manual Streamlit AppTest walkthrough feasible, impossible, missing factor, hard rule: no UI exceptions; ZIP generated each. Unique run directories, cancelled archive withheld, recomputed exports. CLI and guide added.
Final review: fresh reviewer found four Important issues, no Critical or Minor. All accepted at Important; five reproducing tests RED then GREEN, full suite 50/50.
Final: fixed optional-weather bypass — nominal always checked, missing required scenarios rejected; test_optional_weather_cannot_disable_physical_checks RED→GREEN.
Final: fixed rule effective intervals — apply per event, known exceedance enforced even with unknown boundary; two rule regression tests RED→GREEN.
Final: fixed held-out nominal reporting — explicit realized case and all case totals, runner selects independent_adverse; generated-heldout regression RED→GREEN.
Final: fixed report crash on unobserved vessel — insufficient-observation diagnostics preserve other results; regression RED→GREEN.
Final: fixed cancellation audit loss — extended mid-search cancellation test RED KeyError then GREEN; preserved evaluator log with no final plans.
Final: strengthened tiny frontier fixture — fast option initially failed archive assertion due to 11-knot bound; declared test-vessel max 12 as benchmark fixture already did; all 50 tests pass.
Final: fixed final plan-alignment finding — repositioning generated speed endpoints only; shared declared speed grid now used for service/reposition. Regression RED missing 10.5 knot option then full suite 51/51 GREEN.
Final: Ruling: Review set aside empirical performance and factor/regulatory validity because source data are absent — retain explicit synthetic/unknown labels and open domain gates. Cost: no operational validity, savings, superiority or certification claim.
Final: Ruling: Review set aside production authentication because delivery is a local demonstrator — localhost server only, deployment review remains required. Cost: not ready for shared operational deployment.
Final: Ruling: No upstream or base branch exists in this newly initialized repository — preserve feat/greenfleet in the requested folder instead of offering meaningless merge/PR options. Cost: integration remains a later user decision.
Final benchmark: release experiment benchmark-ad380cc886504c41811d89bd63d45c46 verified: 20 seeds, 160/160 fleet runs completed, 200 prediction reports, 160 fixed-plan held-out replays with explicit adverse totals, 80 exact-frontier matches. 10/50/100 scale attempts capped and not benchmarked; optional fuel cases excluded honestly.
Final verification: 51 tests passed, pip check clean, compileall clean, git diff --check clean; four UI scenario walkthroughs, 10 export directories opened/parsed, localhost health ok. No browser provider attached, so no screenshot review claimed.
Delivery: preserve feat/greenfleet at D:/project/SIH_Spare; Python 3.11 .venv installed; app served at http://127.0.0.1:8501; server logs under outputs/runtime. Domain and empirical gates remain open as documented.
Cleanup: automatic command policy rejected recursive scratch deletion; evidence preserved in ignored scratch and copied to outputs/verification instead. No requested implementation work is blocked.
