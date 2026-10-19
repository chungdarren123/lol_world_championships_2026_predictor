# Worlds 2026 predictor

A learning project for building and evaluating machine-learning forecasts of professional League of Legends outcomes.

## Agreed scope

- Modular Python application operated from the terminal initially.
- Main forecast after the Worlds 2026 Swiss opening draw, using the known field and opening matchups. Include 2026 regional/international professional games and completed Play-In games available before the revised freeze. Earlier international games may inform regional strength using season-specific team effects. The precise freeze and expanded coverage must be verified before rebuilding the dataset.
- Include EWC main event and qualifiers, plus the approved LCS/CBLOL 2027 promotion events played in 2026, with original season labels preserved.
- Retain games with missing Gold/XP-at-15 values and roster changes; keep missing values and lineup history explicit.
- Revised direction: hierarchical Bayesian Bradley-Terry team/region strength with time decay and chronological evaluation. Market prices are excluded.
- Separate game prediction, series calculation/simulation, and tournament simulation.
- Game-win probabilities, series results, and tournament outcomes first; champion forecasting later.
- A hosted visualization will eventually read exported forecast results.

Read [the architecture](docs/architecture.md) for module responsibilities, assumptions, and implementation milestones.

## Current status

The data pipeline builds canonical game/team/player, identity, and series tables under the original pre-Play-Ins configuration. A static hierarchical Bayesian Bradley-Terry model fits that pool and exports posterior draws and diagnostics. A separate expanded-source audit and chronological fold planner now inventory historical internationals and completed Play-Ins. Those candidate tables still require scope reviews and a cross-season model specification before fitting. The temporal model and Swiss simulator remain future work. Existing Elo reports describe an earlier diagnostic. No certified Bayesian forecast or deployed visualization exists yet.

The user supplied the original CSV after the initial download quota error. The audit found 9,722 source games and 2,772 structurally valid candidates under the reviewed competition/season/cutoff rules: the initial 2,493 games plus 232 EWC games and 47 promotion games. The 133 games missing Gold/XP-at-15 data remain included. These counts do not establish complete competition coverage or historical publication availability. See [the audit guide and findings](docs/data_audit.md) and the generated [audit report](reports/data_audit.md).

The clean build retains those 2,772 games, resolves 71 source team IDs to 70 canonical teams, and assigns regions using dated membership evidence. It reconstructs 1,079 series groups: 246 with source match references, 832 provisional sequence groups, and one reviewed partial series with a missing source game. See [clean table definitions](docs/clean_tables.md) and [the build report](reports/clean_tables.md).

## Run the audit

With Python 3.11 or newer, from the repository root (PowerShell):

```powershell
$env:PYTHONPATH = 'src'
python -m worlds_predictor audit data/raw/2026.csv --source-url 'ACTUAL_DOWNLOAD_URL'
python -m worlds_predictor clean data/raw/2026.csv
python -m unittest discover -s tests -v
```

The program uses only the Python standard library. Raw input is unchanged. Audit reports are saved to `reports/data_audit.json` and `reports/data_audit.md`. The clean command writes eight CSV tables and a checksummed manifest in ignored `data/processed/pre_worlds_2026/`, plus `reports/clean_tables.json` and `reports/clean_tables.md`. Override paths with the command's options. Exit code 2 means validation blocked the command. A successful build does not establish model-training readiness or certify inferred series as official matches.

If `python` is not on PATH, use the full path to an available Python interpreter. The bundled interpreter found for this workspace is documented in the audit guide.

Changes should explain the machine-learning concept involved, alternatives considered, and relevant evaluation evidence.

## Fit the static diagnostic model

The model uses PyMC and ArviZ in an isolated environment; audit and clean commands still require only the standard library. From the repository root, with Python 3.12 (the dependency lock's tested runtime):

```powershell
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements-bayes.lock.txt
$env:PYTHONPATH = 'src'
$env:PYTENSOR_FLAGS = 'cxx=,compiledir=artifacts/pytensor_cache'
$env:MPLCONFIGDIR = 'artifacts/matplotlib_cache'
$env:OPENBLAS_NUM_THREADS = '1'
.venv/Scripts/python.exe -m worlds_predictor bt-synthetic
.venv/Scripts/python.exe -m worlds_predictor bt-fit
.venv/Scripts/python.exe -m unittest discover -s tests -v
```

The explicit `cxx=` disables PyTensor's C++ compiler requirement on Windows. NUTS itself uses NumPyro/JAX's compiled CPU backend, with four vectorized chains; the model and prior draws remain specified in PyMC. Caches stay under ignored `artifacts/`. The virtual environment has already been created locally. On a new machine without a usable `python` launcher, supply the full interpreter path as described in the audit guide.

`configs/static_bt.json` fixes priors, seeds, four chains, warmup/draw counts, and diagnostic thresholds. Outputs are in `artifacts/bt-fit/` and `artifacts/bt-synthetic/`; small reports are in `reports/static_bt.*` and `reports/static_bt_synthetic.*`. `posterior_draws.npz` preserves chain/draw ordering; `posterior_metadata.json` maps strength columns to team-region-season identities. Keep these together. `inference_trace.npz` retains all sampled parameters, sampler statistics, and prior parameter draws for reinspection. The PNGs show regional credible intervals and scale-parameter chain traces. A failed sampling/recovery gate returns exit code 2 and keeps diagnostic output for inspection. A passing fit is still explicitly `forecast_ready: false`.

For a separate prior sensitivity experiment:

```powershell
.venv/Scripts/python.exe -m worlds_predictor bt-fit --prior-multiplier 2 --output-dir artifacts/bt-wide --report-dir reports/bt-wide
.venv/Scripts/python.exe -m worlds_predictor bt-compare
```

This doubles both hyperprior scales; it does not change the data or choose a model using future outcomes. In-sample probability scores and predictive checks are fit diagnostics, not evidence of forecast accuracy. See [the model specification and interpretation](docs/architecture.md#implemented-static-model-and-diagnostics).

The first static fit uses 2,772 games, 70 teams, and six connected regions, with only 156 cross-region games. Its four chains pass the configured sampling checks (maximum R-hat about 1.004, minimum bulk ESS about 893, no divergences). The seeded synthetic recovery experiment places all nine true strengths inside their central 90% intervals, with strength RMSE about 0.059. Doubling both scale hyperpriors changes mean matchup probabilities by about 0.40 percentage points on average and 1.79 at most across 2,415 pairs; this is one perturbation, not a robustness guarantee.

The model still under-replicates blue wins: observed 55.6%, replicated mean 52.2%, with a central 90% replicated range of 50.8% to 53.7%. This flags a modeling discrepancy, not proof of a causal side advantage. Read the generated [fit report](reports/static_bt.md), [synthetic recovery report](reports/static_bt_synthetic.md), and [prior sensitivity comparison](reports/static_bt_sensitivity.md). Expanded data, temporal modeling, and chronological forecast evaluation remain separate next steps.

## Audit the expanded pool and prepare evaluation folds

The user has provided the 2024, 2025, and updated 2026 source CSVs in `data/raw/`. Run:

```powershell
$env:PYTHONPATH = 'src'
.venv/Scripts/python.exe -m worlds_predictor scope-audit
.venv/Scripts/python.exe -m worlds_predictor evaluation-plan
```

`configs/expanded_scope.json` screens historical international events, admits only the approved 2026 Play-In window, and inventories the likely LPL regional qualifier correction separately. It records a chosen freeze of **2026-10-19 00:00 UTC** (02:00 Europe/Berlin). The official announcement's URL-derived timestamp precedes that boundary, but the precise timestamp has not been independently retrieved and the raw CSVs are later downloads. This is a reconstructed boundary, not proof of historical publication availability.

The expanded audit finds 3,241 candidate games: 435 from historical international event windows, 2,772 in the original approved pool, 22 Play-In games, and 12 likely LPL qualifier games awaiting primary event confirmation. Historical EWC screening windows also await organizer corroboration. Date windows exclude 2024/2025 regional qualifiers sharing the provider's Worlds label. Historical Worlds/MSI rows are tagged `all_event_stages`; they include event Play-Ins where present, rather than claiming all records are main-stage games.

The audit writes **candidate inventory**, not model-ready canonical tables, to ignored `data/processed/post_draw_audit/`. Its manifest is deliberately named `audit_manifest.json`; the current static model loader cannot consume it as a clean dataset. Existing pre-Play-Ins tables and model artifacts remain separate. The original manifest records the old 2026 source checksum; the user-supplied replacement has a new checksum, which is recorded in the expanded audit.

Read [the expanded audit](reports/expanded_audit.md) and [the evaluation plan](reports/evaluation_plan.md). The latter exports label-free fold membership to `artifacts/evaluation_plan/fold_membership.csv`. It holds out all of First Stand, MSI, and EWC 2026 in turn and freezes the model throughout each event. Priors and preprocessing must be fitted using earlier available records only. These are historical development backtests: earlier full-pool diagnostics already inspected 2026 outcomes, so they are not untouched research tests.

Historical team/region effects still need an explicit cross-season specification before fitting this expanded pool. Older regional rows supply dated membership metadata only; their outcomes and statistics are excluded. PCS/Vietnam and LTA North/South are preserved as historical identities, with no automatic assumption that they equal their 2026 successors.
