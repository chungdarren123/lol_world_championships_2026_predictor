# Chronological evaluation plan

Candidate fold membership only. Model fitting is not yet enabled.

Historical development backtests, not an untouched research test: 2026 outcomes already appeared in full-pool diagnostics.

| Event fold | Candidate training games | Pending scope review in train | Evaluation games | Cross-region evaluation games |
|---|---:|---:|---:|---:|
| fst_2026 | 1108 | 52 | 45 | 42 |
| msi_2026 | 2242 | 52 | 71 | 71 |
| ewc_2026 | 2313 | 52 | 51 | 43 |

Each fit uses only whole observed series whose assumed result availability precedes the fitting boundary. The target event is held out in full and the model remains frozen throughout it. A boundary-overlapping series is purged, including earlier games within that series. Known partial target series are not scored.

Unknown future sides cannot become deployable features through historical hindsight. A conditional-on-known-side experiment must be reported separately or marginalized using a justified pre-draft model.

## Remaining constraints

- Candidate training sets are for inspection; open event/identity/model-bridge reviews must be resolved before fitting.
- No probabilities were fitted or scored; this report contains sample counts and membership only.
- Historical 2026 outcomes were already inspected in diagnostics, so these are development backtests, not pristine research holdouts.
- Within each future fit, priors, decay, feature construction, and preprocessing must use training records only.
- Models stay frozen through each event; no within-event result updates are allowed by this protocol.
- Publication delay is assumed and series groups are provisional; those limitations persist in this plan.
