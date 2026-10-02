# Prediction model card

All fixture results are synthetic pipeline checks. Separate `future` and
`unseen_vessel` manifests retain row/voyage/vessel IDs, counts and time ranges.
Temporal splitting holds entire voyages together and embargoes aggregates whose
end overlaps the next partition. Four development/test partitions are disjoint.

Engineering: sourced cubic shaft-power coefficient plus separate auxiliary load,
converted through a pathway-specific efficiency and LHV. Missing curves/maps
exclude engineering/residual use. Demo sources are explicitly synthetic.
Direct: histogram gradient boosting. Residual: the same GBM learns correction to
engineering fuel rate. Imputation, missing indicators and categorical encoding
fit training rows only. Early stopping is disabled to avoid hidden partitions.
Calibration uses a disjoint absolute-residual 90% conformal quantile; negative
estimates and lower interval endpoints are clamped to zero. Intervals are not
robustness guarantees. Inference rejects unvalidated speeds, loads, categories
and sea-state ranges; an unsupported ML option never supplies a numeric estimate.

Reports include MAE, RMSE, WAPE (null for zero denominator), interval coverage/
width, sample counts, class metrics, fit/inference time and speed-grid diagnostics.
Known/unseen results are never averaged into a single accuracy claim.
No inference-time lag features or universal efficiency assumptions are used.
