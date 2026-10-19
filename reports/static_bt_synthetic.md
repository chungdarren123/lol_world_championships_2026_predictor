# Static hierarchical Bradley-Terry diagnostic

Status: diagnostic_fit_sampling_passed

**Not a forecast.** Synthetic recovery experiment with known strengths; not a real-data fit.

Games: 2880; series represented: 2880; team-region-season entities: 9; regions: 3; cross-region games: 2160.

Region graph components: [['Synthetic_A', 'Synthetic_B', 'Synthetic_C']]. Team graph component sizes: [9].

## Inference checks

Passed: True; max rank-normalized R-hat: 1.004196325052804; min bulk/tail ESS: 442.0541531545986 / 609.4106619132859; divergences: 0.

BFMI by chain: [0.7015909802365773, 0.7472732997570548, 0.8077513850554477, 0.715962694763568]

R-hat checks agreement between chains; ESS estimates independent information in correlated draws. Divergences and BFMI warn about exploration problems. Passing these checks does not validate the model's assumptions.

## Region effects

The reference is the mean of the modeled regional pool means, with within-region team deviations centred at zero. These are log-odds effects, not win percentages. Intervals are central 90% posterior credible intervals.

| Region | Mean | 5% | 95% |
|---|---:|---:|---:|
| Synthetic_A | -0.713 | -0.780 | -0.646 |
| Synthetic_B | 0.056 | -0.007 | 0.121 |
| Synthetic_C | 0.657 | 0.593 | 0.724 |

## Predictive checks

The JSON report contains prior matchup probabilities, posterior predictive blue-win rates by event/stage and region pairing, and in-sample probability bins. These check plausibility and model fit; none is an out-of-sample forecast score.

| Pairing | Games | Observed blue wins | Replicated mean | Replicated 5% to 95% |
|---|---:|---:|---:|---:|
| all | 2880 | 30.7% | 31.5% | 29.7% to 33.3% |
| cross_region | 2160 | 29.6% | 30.3% | 28.2% to 32.5% |
| same_region | 720 | 33.9% | 35.2% | 31.9% to 38.5% |

Discrepancies (descriptive checks across multiple groups, not significance tests):

- None flagged by this check.

Omitted map-side effects, selection mechanisms, changing strengths, or other misspecification could explain mismatches. A mismatch does not establish a causal blue-side advantage. Passing sampler checks does not remove model discrepancies.

## Limitations

- Synthetic data with known fixed strengths only; no real-team conclusions or historical timing assumptions apply.
- One seeded recovery experiment is not simulation-based calibration across many simulated datasets.
- Synthetic games match the model's conditional-independence assumptions; real games may violate them.
- Sampling success and recovery here do not establish out-of-sample accuracy on real tournaments.

## Synthetic recovery

{
  "strength_rmse": 0.05915736645521686,
  "central_90_interval_coverage": 1.0,
  "truth": [
    -1.2,
    -0.7,
    -0.19999999999999996,
    -0.5,
    0.0,
    0.5,
    0.19999999999999996,
    0.7,
    1.2
  ],
  "posterior_means": [
    -1.1412793216626302,
    -0.7904529683753864,
    -0.2062389566559753,
    -0.42273194438220213,
    0.045053211424931586,
    0.5444780627071896,
    0.20281311294704765,
    0.658433326762747,
    1.1099254772342815
  ],
  "passed": true,
  "interpretation": "One seeded recovery smoke test, not simulation-based calibration."
}
