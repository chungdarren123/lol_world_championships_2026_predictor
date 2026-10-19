# Elo baseline diagnostic

Status: retrospective_diagnostic_with_unverified_timing

Input: 2772 games; scored predictions: 2771; rating updates: 2772; teams: 70.

Predictions share a frozen pre-series rating snapshot. This is an online historical replay, not a frozen tournament forecast. Warmup scores are descriptive.

| Period | Region pairing | Games | Series | Elo log loss | 50/50 log loss | Elo Brier | Accuracy* |
|---|---|---:|---:|---:|---:|---:|---:|
| warmup | all | 1822 | 733 | 0.6539 | 0.6931 | 0.2309 | 61.4% |
| warmup | same_region | 1765 | 716 | 0.6529 | 0.6931 | 0.2304 | 61.7% |
| warmup | cross_region | 57 | 17 | 0.6854 | 0.6931 | 0.2464 | 54.4% |
| validation | all | 711 | 281 | 0.6544 | 0.6931 | 0.2314 | 59.8% |
| validation | same_region | 612 | 241 | 0.6482 | 0.6931 | 0.2284 | 61.3% |
| validation | cross_region | 99 | 40 | 0.6926 | 0.6931 | 0.2497 | 50.5% |
| test | all | 238 | 64 | 0.6683 | 0.6931 | 0.2382 | 58.0% |
| test | same_region | 238 | 64 | 0.6683 | 0.6931 | 0.2382 | 58.0% |

Lower log loss/Brier is better. A 50/50 prediction has log loss 0.6931 and Brier 0.25. *Accuracy gives half credit to exact 50/50 ties; the 50/50 reference therefore scores 50%.

Test cross-region coverage: 0 games. A test without cross-region games cannot validate international matchup performance.

Calibration bins and reference Brier/accuracy are in the JSON report. Calibration compares predicted probabilities with observed win rates; small bins are noisy. No calibrator was fitted.

Exclusions: {'known_partial_series_games': 1}

## Settings

- initial_rating: 1500.0
- k_factor: 20.0
- rating_scale: 400.0
- validation_start_utc: 2026-07-01T00:00:00Z
- test_start_utc: 2026-09-01T00:00:00Z
- forecast_lead_minutes: 60
- result_delay_minutes: 60
- tuning: None. Teaching defaults fixed before inspecting baseline scores.

## Limits

- Timestamps assume UTC and durations assume seconds; neither source convention is verified.
- Forecast time is first observed game start minus the configured lead, not a verified pre-draft timestamp.
- Result availability is assumed series end plus configured delay, not a historical publication record.
- Most series groups remain provisional; unknown missing whole games/series cannot be ruled out.
- Known partial series are excluded from prediction scores; their observed games still update ratings after availability.
- Online evaluation updates only from earlier available series, including during validation/test; it is not a frozen whole-tournament backtest.
- No parameter tuning or calibration was performed. Future choices must not be guided by the reported test score.
- Equal regional starts, roster changes, no inactivity decay, and sparse cross-region links limit interpretation of global ratings.
- No draft, side advantage, roster-strength adjustment, or Gold/XP feature is used. Regions only stratify evaluation.
- Games within a series share a rating snapshot and are correlated. Scores are game-weighted; no independence-based confidence intervals are claimed.
- The later raw download may contain backfills or corrections. These diagnostics do not certify an authentic pre-Worlds snapshot.

The exported ratings are research artifacts, not a certified Worlds forecast. Check provenance hashes in the JSON report before reusing them.
