# Static hierarchical Bradley-Terry diagnostic

Status: diagnostic_fit_sampling_passed

**Not a forecast.** Static fit to the existing 2026 pre-Play-Ins pool. Expanded data and temporal modeling remain pending.

Games: 2772; series represented: 1079; team-region-season entities: 70; regions: 6; cross-region games: 156.

Region graph components: [['Asia Pacific', 'Brazil', 'China', 'EMEA', 'Korea', 'North America']]. Team graph component sizes: [70].

## Inference checks

Passed: True; max rank-normalized R-hat: 1.0041139649936623; min bulk/tail ESS: 762.3092741010109 / 1218.964300070724; divergences: 0.

BFMI by chain: [0.7192987651280113, 0.6610953661919914, 0.6552832137978154, 0.6100545683328202]

R-hat checks agreement between chains; ESS estimates independent information in correlated draws. Divergences and BFMI warn about exploration problems. Passing these checks does not validate the model's assumptions.

## Region effects

The reference is the mean of the modeled regional pool means, with within-region team deviations centred at zero. These are log-odds effects, not win percentages. Intervals are central 90% posterior credible intervals.

| Region | Mean | 5% | 95% |
|---|---:|---:|---:|
| Asia Pacific | -1.177 | -1.837 | -0.549 |
| Brazil | -0.880 | -1.676 | -0.156 |
| China | 0.860 | 0.417 | 1.300 |
| EMEA | -0.045 | -0.489 | 0.419 |
| Korea | 1.368 | 0.956 | 1.793 |
| North America | -0.126 | -0.660 | 0.369 |

## Predictive checks

The JSON report contains prior matchup probabilities, posterior predictive blue-win rates by event/stage and region pairing, and in-sample probability bins. These check plausibility and model fit; none is an out-of-sample forecast score.

| Pairing | Games | Observed blue wins | Replicated mean | Replicated 5% to 95% |
|---|---:|---:|---:|---:|
| all | 2772 | 55.6% | 52.2% | 50.7% to 53.6% |
| cross_region | 156 | 63.5% | 54.6% | 48.7% to 60.3% |
| same_region | 2616 | 55.1% | 52.0% | 50.5% to 53.6% |

Discrepancies (descriptive checks across multiple groups, not significance tests):

- all: observed blue win rate is outside the central 90% replicated range
- cross_region: observed blue win rate is outside the central 90% replicated range
- same_region: observed blue win rate is outside the central 90% replicated range
- CBLOL/regional_competition: observed blue win rate is outside the central 90% replicated range
- LCK/regional_competition: observed blue win rate is outside the central 90% replicated range
- LCS/promotion: observed blue win rate is outside the central 90% replicated range

Omitted map-side effects, selection mechanisms, changing strengths, or other misspecification could explain mismatches. A mismatch does not establish a causal blue-side advantage. Passing sampler checks does not remove model discrepancies.

## Limitations

- Static 2026 pre-Play-Ins diagnostic only: no time decay, historical international data, or completed Play-In games yet.
- Uses the original scheduled cutoff and unverified UTC/seconds source assumptions, with an explicit assumed result delay.
- Publication time and later source corrections are unknown; this is not a verified historical snapshot.
- Region means describe this modeled team pool; coverage and selection of international entrants affect interpretation.
- Disconnected comparisons depend on priors; graph connectivity alone does not guarantee precise regional strengths.
- Team-region-season effects are constant despite roster/patch changes; lineups remain preserved in canonical tables.
- Games are conditionally independent given fixed strengths. Within-series dependence and adaptation are omitted.
- Known partial series contributes observed games only; no missing results or official final scores are invented.
- Missing Gold/XP games are retained; those statistics and drafts are not features and no imputation is performed.
- Prior and posterior predictive checks use observed fixtures; in-sample checks do not demonstrate forecasting skill.
- Sampling checks assess numerical inference, not whether assumptions or predictions are correct.
- A single synthetic recovery exercise is a smoke test, not simulation-based calibration across many synthetic datasets.
- Region/team scale priors require sensitivity review; no test-outcome-driven parameter tuning is authorized.
