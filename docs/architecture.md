# Architecture and learning plan

## Decisions

The project uses modular Python rather than notebooks. The user has revised the primary model to hierarchical Bayesian Bradley-Terry strength estimation with regional and team effects and time decay. A separate Monte Carlo simulator converts game probabilities into Swiss outcomes. The main forecast is conditional on the known Swiss field and Round 1 draw, after that draw; completed Play-In games available before the new freeze may inform strengths. Kalshi/Polymarket prices are excluded. Actual future drafts remain unavailable inputs. Terminal output comes first; a hosted visualization and champion forecasts remain later work.

## Data boundary

Use the 2026 competitive season, including regional and international professional tournaments, and completed Worlds 2026 Play-In games available before the revised freeze. Earlier seasons' international games are now authorized to inform regional strength. Their teams require separate season-specific effects and dated region mappings; an older team's results must not be attributed directly to its current roster. The exact historical window and coverage remain to be reviewed. The user approved EWC main-event and qualifier games, plus 47 LCS/CBLOL promotion games held in September/October 2026 for 2027 league places. Preserve source seasons and event stages. Every exception must satisfy its configured event boundaries.

Retain games with missing Gold/XP-at-15 statistics and games across lineup changes. Preserve missingness, track midseason substitutions and roster versions, and do not silently fill unknown values with zero. Any imputation must be selected during model development and fitted inside training folds. Retaining an old lineup's games does not mean assuming its strength is identical to the current lineup's strength.

Explicitly identify eligible competitions and report which are covered, missing, or incomplete. Do not silently assume every source covers every league. A season boundary does not ensure a fixed lineup. EWC qualifiers remain distinguishable from main-event games, including when reporting region connections.

Verify and store the exact post-draw forecast freeze in UTC. The original scheduled pre-Play-Ins cutoff, configs, clean tables, and diagnostic reports remain separate historical artifacts; do not silently relabel them as post-draw data. For the revised dataset, explicitly permit eligible completed Play-In games and exclude all Swiss/knockout results. Do not guess historical publication times or treat a start timestamp as result availability.

Preserve raw downloads and record checksums, retrieval time, source, schema, competition coverage, and limitations. A retrospective download may contain corrections unavailable at the forecast date; disclose this rather than claiming an authentic historical snapshot.

Keep outcomes after the revised forecast freeze outside fitting, feature selection, tuning, and calibration. Completed Play-In outcomes are the explicit approved exception to the previous all-Worlds-results exclusion. Evaluate the Swiss forecast only after freezing it; those outcomes cannot influence its design or parameters.

## Module boundaries

```text
src/worlds_predictor/
  cli.py             Terminal entry point; delegates to modules
  ingestion/         Read/download source records; preserve provenance
  data/              Canonical schemas, identity mapping, validation
  features/          Features constructed from preceding games only
  models/            Hierarchical Bradley-Terry model and posterior export
  evaluation/        Chronological folds, metrics, calibration
  simulation/        Series outcomes, legal draws, tournament progression
  reporting/         CSV/JSON outputs and forecast metadata
configs/             Season, cutoff, competition scope, model/rule settings
tests/               Leakage checks and model/simulator invariants
docs/                Concepts, design decisions, and interpretation
```

Create modules as milestones require them; the structure above is a design, not implemented code. Local raw/processed data and model artifacts are separate from source code. Git tracks code, configuration, documentation, and appropriate small results; raw provider data is not published without checking redistribution rights.

The future presentation layer reads exported results. Training must not run merely because a user loads a page. Keeping forecasts independent of the UI permits a static hosted dashboard or a later Python web application; no host or framework is selected yet.

## Prediction contract

A game model accepts two teams and context actually known at the forecast time, and returns a probability in [0, 1]. The reversed matchup must have complementary probabilities under consistently reversed context. Unseen teams or insufficient histories must be handled explicitly and flagged.

For the post-draw Swiss forecast, condition on the known field and Round 1 pairings. Later opponents, drafts, and selection choices remain unknown and must be omitted, integrated over, or simulated. Freeze the fitted strength distribution at the revised forecast timestamp.

Historical training features must be constructed using each historical forecast time, not full-pool aggregates. A forecast made before a series cannot use later games in that series. A game-start forecast may use earlier completed games only if that is the documented evaluation task. Never update the frozen strength distribution with simulated results as if they were real observations.

## Models and the concepts they teach

### Revised Bayesian strength model: specification under discussion

Model a game's binary outcome with `P(A wins) = logistic(strength_A - strength_B)`, where strength is a dated region effect plus a season-specific team deviation. Regional priors and team priors partially pool estimates; thin histories should lead to greater uncertainty. Domestic games primarily identify within-region differences; international games connect regions. Partial pooling cannot manufacture missing international evidence.

Constrain regional locations and within-region team deviations so regional effects cannot be arbitrarily exchanged with team effects. If earlier seasons are included, use evolving region-season effects and separate team-season effects. Regional estimates describe the modeled competitive pool; international entrants are selected top teams rather than random regional representatives.

Temporal alternatives require discussion before implementation: (1) exponentially downweight old game log-likelihood terms, which is simple but produces a generalized/power posterior rather than an explicit generative evolution model; or (2) let strengths evolve through a time-indexed stochastic process, which is more coherent for temporal uncertainty but adds parameters and computation. Start with an inspectable static hierarchical fit to validate the decomposition, then add the selected temporal method before producing the intended forecast. Choose decay settings or evolution scales using historical validation, not Swiss outcomes.

PyMC now specifies the implemented static diagnostic model, using NumPyro/JAX for CPU posterior sampling. Sampling requires convergence checks, effective sample sizes, divergence review, prior sensitivity, and posterior predictive checks. Export joint posterior draws rather than only average strengths. The Bradley-Terry model is itself a constrained logistic regression, so the project still teaches logistic probabilities, coefficients, regularization through priors, and probability evaluation. A separate feature-rich logistic model is deferred; Elo is no longer the required primary benchmark. Preserve earlier diagnostics without treating them as proof of international predictive ability.

### Series and tournament simulation

Start with constant per-game matchup probability and conditional independence within a series. Calculate best-of series probabilities exactly using that assumption; use simulation to cross-check them and to sample tournament paths. This simplifies learning but omits adaptation and draft effects.

Implement the actual official Play-In, Swiss, and knockout rules, including series lengths, draw constraints, rematch restrictions, and bracket seeding. Verify legal draw procedures rather than assuming arbitrary rejection sampling reproduces their probabilities. Never invent a complete Swiss ranking where only record buckets exist.

The revised immediate scope is Swiss simulation, conditional on the user-supplied opening pairs: GEN-IG, TLAW-CFO, AL-KC, G2-DK, HLE-TES, LOS-T1, TSW-LYON, BLG-MKOI. These pairs have not yet been independently verified against an official draw record. Riot's [2026 event rules](https://cdn.sanity.io/files/dsfx7636/news_live/faa5ce974e58615911fbee931c6123e2785a8b46.pdf), sections 4.1.2 and 4.3.3, specify Bo3 advancement/elimination matches, same-record draws, next-available-slot handling of prohibited rematches, and an official waiver if no eligible draw exists. Do not silently replace that procedure with uniform legal matching; document any unresolved operational ambiguity or approximation. The [official primer](https://lolesports.com/en-GB/news/worlds-2026-primer) places the opening Swiss draw after Play-Ins on October 18.

Target about 100,000 simulations after small-scale validation. For each simulated tournament, draw one joint set of strengths from the frozen posterior and use it consistently through that tournament. Then sample legal pairings and outcomes. With a constant conditional game probability p and independent games, Bo3 win probability is `3*p*p - 2*p*p*p`; average this over posterior draws rather than applying it to an already averaged probability. This preserves shared strength uncertainty; do not independently resample every team's strength for every match.

Export P(3-0), P(3-1), P(3-2), P(0-3), P(1-3), P(2-3), and P(advance). Check that each team's six terminal probabilities sum to one and all advancement probabilities sum to eight. Each simulation must contain two 3-0, three 3-1, three 3-2, two 0-3, three 1-3, and three 2-3 finishes. The top eight by marginal advancement probability are a selection summary, not a complete predicted joint tournament outcome. A later knockout simulation must use each run's actual eight qualifiers.

Use a fixed random seed for reproducibility. Distinguish outcome randomness, Monte Carlo estimation error, and uncertainty about team strength. More simulations reduce only Monte Carlo error. A first fixed-parameter model does not quantify all model uncertainty.

## Evaluation

Use chronological historical periods, with series grouped for pre-series forecasts. All historical fitting must respect each fold's own availability cutoff, including selection of earlier international records. Compare a 50% reference, a non-hierarchical Bradley-Terry model, and the hierarchical model on common eligible games. Regional partial pooling and temporal components should earn their complexity through validation. The earlier Elo diagnostic's September test has already been inspected and must not be described as untouched for repeated model selection. Design the revised evaluation before fitting or inspecting new model scores, emphasizing international holdouts where feasible.

Report log loss, Brier score, calibration, accuracy, sample counts, and domestic versus international breakdowns. Fit any calibrator using disjoint earlier data; calibration on the test set invalidates the test. Preserve prediction timestamps and availability assumptions. Do not promise an accuracy level in advance.

Important tests include no post-cutoff data, no current-game outcome in features, duplicate-game detection, complementary matchup probabilities, legal pairings, series probabilities summing to one, and correct advancement/elimination.

## Reproducibility and GitHub workflow

Each forecast should identify the Git commit, data checksum, cutoff, feature definitions, model settings, evaluation results, rules source/version, seed, and simulation count. Dependency versions should be locked once the runtime is selected.

Use focused commits and branches with clear explanations. Once executable code exists, add GitHub Actions for meaningful tests and formatting checks. Keep provider credentials in environment variables or GitHub secrets; never commit them. Dataset publication and deployment configuration are separate later decisions.

## Milestones

1. Verify Python runtime and repository setup. Establish packaging and the terminal entry point.
2. Audit 2026 source coverage and verify the cutoff. Produce a data-quality report, then a canonical dataset.
3. Finalize the Bayesian specification, earlier-season window, and revised post-draw freeze; audit the expanded data pool without overwriting the old snapshot.
4. Implement a static hierarchical Bradley-Terry fit, verify identifiability and inference, then add the agreed temporal method and chronological evaluation.
5. Implement and verify series calculations and the official Swiss simulation, propagating posterior uncertainty.
6. Freeze and export the post-draw Swiss forecast and terminal-record probabilities with provenance; extend to knockouts separately.
7. Build and deploy a visualization of the exported results, showing assumptions and uncertainty.

The program should be runnable after each executable milestone; do not implement the entire system before discussing intermediate results.

## Implemented static model and diagnostics

The first Bayesian implementation is a static diagnostic on the existing audited 2026 pre-Play-Ins tables, not a rebuilt post-draw forecast. Data loading verifies canonical checksums, dated regional evidence, unique game/team keys, and the original cutoff. It assumes durations are seconds and results become available one hour after game end. Source timing conventions and publication availability remain unverified. Earlier international games and completed Play-In games still need their approved coverage/identity audit before inclusion. Source season labels remain in the canonical tables; the model entity uses the year played plus team and dated region, so the approved promotion exception stays in the 2026 played-year pool.

The model is `s_i = region_effect[r(i)] + team_effect[i]` and `P(A wins) = logistic(s_A - s_B)`. It treats the regional effects as summing to zero and team deviations as summing to zero within each region. The region mean is the average strength of the modeled teams in that region, rather than a claim about every professional team in its ecosystem. Zero-sum orthonormal contrasts remove redundant directions exactly. Contrasts are rescaled so each marginal effect has the stated conditional standard deviation. A singleton region has a zero team deviation.

The hierarchical priors are `region_sd ~ HalfNormal(1)` and `team_sd ~ HalfNormal(1)`, with independent unit-normal contrast coefficients multiplied by these learned scales. Half-normal means a positive distribution favouring moderate scale values; its scale 1 is a disclosed modeling choice, not a measured League constant. Non-centred parameterization separates unit-normal coefficients from their scales and can improve sampling when evidence is weak. It can be less efficient for strongly measured effects. A broad hyperprior is not automatically neutral, particularly with only six regional effects.

This model learns through `posterior proportional to likelihood times prior`. The likelihood rewards strengths that make observed winners more probable; priors regularize extreme differences and share information. Only fixed team identities, dated regions, and game outcomes enter this version. No draft, Gold/XP, roster, patch, or map-side coefficient is included. Existing lineups and missing statistics remain preserved outside the model. Repeated unordered matchups are aggregated to binomial win counts: for fixed strengths and independent games, the parameter-dependent likelihood is exactly the same as individual Bernoulli outcomes. This aggregation must be revisited when strengths change over time or context varies.

PyMC specifies the model and NumPyro/JAX runs four vectorized CPU NUTS chains with 1,000 warmup steps and 1,000 retained draws per chain, seed 20261018, target acceptance 0.95, and maximum tree depth 10. The compiled CPU backend avoids the very slow compiler-free PyTensor NUTS path on this Windows runtime. Warmup adapts the sampler and is discarded. Retained draws are correlated; 4,000 draws are not necessarily 4,000 independent observations. The model command returns a failed diagnostic status if rank-normalized R-hat exceeds 1.01, bulk/tail effective sample sizes fall below 400, chain BFMI falls below 0.3, a divergence occurs, or a checked tree-depth limit is reached. These are screening thresholds, not a proof of convergence or prediction accuracy. [ArviZ R-hat](https://python.arviz.org/en/v0.22.0/api/generated/arviz.rhat.html), [ESS](https://python.arviz.org/en/v0.22.0/api/generated/arviz.ess.html), and [BFMI](https://python.arviz.org/en/v0.22.0/api/generated/arviz.bfmi.html) document the checks.

The diagnostic workflow has separate questions:

1. Structural tests verify zero sums, full-rank parameterization, complementary probabilities, exact static aggregation, and no later membership evidence.
2. Synthetic recovery fits 2,880 generated games among nine teams with known strengths. Predeclared smoke-test thresholds are strength RMSE below 0.25 and at least two-thirds of true strengths inside central 90% intervals. One successful dataset is not a calibration study; repeated simulation-based calibration would be stronger and more expensive.
3. Connectivity checks enumerate actual region links and disconnected team components. Priors can yield finite estimates even without identifying evidence; report such estimates as prior-dependent.
4. Prior predictive draws check whether the chosen scales imply implausibly extreme probabilities before seeing outcomes. The exported summary weights observed matchup pairs equally.
5. Posterior predictive draws check blue-win rates by region pairing and event stage, and inspect in-sample probability bins. These can reveal mismatch but cannot validate future accuracy. Match/game correlation and constant season-wide strength remain assumptions.
6. Prior sensitivity fits use separate output directories and changed hyperprior scales. Compare intervals and probabilities as well as mean rankings. Do not choose priors to produce preferred teams or Swiss outcomes.

Posterior exports preserve joint region/team strengths by chain and draw; the simulator must take a joint draw for each simulated tournament. Intervals are central 90% posterior credible intervals for parameters under this model, not a 90% guarantee about an individual game. The regional plot shows log-odds effects, not win percentages. For example, a one-unit total strength advantage gives a game win probability of about 73.1%. To compare two regions, inspect their difference within each joint posterior draw; marginal interval overlap alone does not answer that question. Predictive checks use up to 1,000 evenly spaced joint draws to bound memory; all 4,000 retained draws remain exported.

The diagnostic report remains separate from chronological held-out evaluation and the eventual post-draw forecast. Time decay should be added only after interpreting the static fit and its sensitivity; sampling success alone is not a reason to skip that evaluation.

## Expanded-source audit and evaluation protocol

The updated sources are inventoried separately by `scope-audit`, using `configs/expanded_scope.json`. The chosen post-draw reporting boundary is 2026-10-19 00:00 UTC, equivalent to 02:00 Europe/Berlin. The opening pairs match the [official Swiss bracket](https://lolesports.com/en-AU/tournament/115660540725177488/stage/115660540725570706). The announcement URL's ID decodes to a timestamp before that boundary; direct retrieval did not independently confirm its exact timestamp, and historical data publication timing remains unknown. The boundary is a documented reconstruction, not an authenticated archived snapshot or exact draw-completion time.

The audit inventories 3,241 candidate games, including 435 historical international games, 22 2026 Play-In games, and 12 likely regional qualifier corrections still under scope review. Historical EWC date windows also require organizer corroboration. Audit inventories retain raw seasons and ten-player lineups, preserve source team IDs alongside the existing dated alias correction, and expose dated regional membership evidence. Regional source rows supply membership metadata only. Historical Worlds and MSI include all actual event stages within their windows, not the domestic qualification games sharing a source league label. Candidate output uses a separate audit manifest and is not accepted by the existing static model loader.

`configs/evaluation_protocol.json` defines historical event backtests before fitting new variants: fit before March 16 for First Stand, June 28 for MSI, and July 15 for EWC, all at 00:00 UTC. Freeze the model through each held-out event. Whole observed series are included in training only if every observed game's assumed result availability precedes that boundary. Purge a series straddling the boundary, and do not score known partial target series. The existing 2026 MSI `main_event` label covers the whole MSI pool, including its Play-Ins; the evaluation fold therefore holds out that whole event. Historical audit rows label this broader coverage `all_event_stages` explicitly.

These folds create out-of-sample predictions within each eventual fit, but not an untouched research experiment: 2026 outcomes already appeared in prior full-pool diagnostics. Model choices use development backtests, while the initial 2026 Swiss forecast must remain frozen and prospectively evaluated. A historical conditional-on-realized-side experiment must not be presented as a pre-tournament forecast unless unknown sides are marginalized under a justified selection model.

The next modeling decision is how to connect region-season effects across years. Independent seasons avoid imposing continuity but cannot transfer much regional information. Weak seasonal links transfer information with uncertainty; reorganizations such as PCS/Vietnam into LCP and LTA conferences into LCS/CBLOL need explicit, reviewed bridges rather than equality constraints. Preserve season-specific team effects in either approach. The fold planner records historical region labels without choosing these bridges or fitting priors from future data.
