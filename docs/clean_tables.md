# Canonical games, identities, and series

This milestone organizes the approved data pool into related tables. It performs no model fitting and constructs no pre-draft features. The raw CSV remains unchanged.

## What the tables represent

| Table | One row represents | Current rows |
|---|---|---:|
| games.csv | One retained individual game, with source lineage and series link | 2,772 |
| team_games.csv | One team's participation and observed performance in one game | 5,544 |
| player_games.csv | One player's role, team, and observed performance in one game | 27,720 |
| series.csv | One source-supported or inferred series group | 1,079 |
| teams.csv | One canonical team identity, with descriptive observed-name history | 70 |
| players.csv | One provider player identity, with observed-name history | 441 |
| team_aliases.csv | One observed source ID/name/competition to canonical-team mapping | 137 |
| team_regions.csv | Earliest observed membership evidence for a team/region/league | 71 |

These files are in `data/processed/pre_worlds_2026/`. The directory is ignored by Git. Generated data has not been published or redistributed. A manifest records input hash, configuration snapshots/hashes, Python version, package-source fingerprint, table schemas, output checksums, counts, diagnostics, and limitations.

The `game_id` is a deterministic hash of source competition and source game ID. The source values remain in separate columns. This avoids collisions when different competitions reuse a provider game ID. Use `game_id` to join game, team, and player records. Use `(game_id, team_id)` to join player rows to their participating team; use `series_id` to group related games. An ID joins records, not an instruction to treat its spelling as a predictive feature.

Do not sum a team statistic once per player after a join. A game has two team rows and ten player rows; careless joins can multiply counts. The validator checks unique keys, valid links, opposite-side teams, consistent results, complete-lineup membership, region-evidence chronology, and reconciliation of observed series scores.

## Team identity correction

The provider gives `Team Secret` and `Team Secret Whales` different team IDs. The [EWC organizer](https://ewc-web.prod.esf-systems.com/en/competitions/2026/league-of-legends) identifies Team Secret as the LCP representative. The source records for both names contain Pun, Hizto, Dire, Eddie, and Bie with identical player IDs around the event.

The reviewed rule in `configs/identities_2026.json` maps the Team Secret EWC ID to the Team Secret Whales ID within the relevant date window. Eight team-game rows use it. All original IDs and names remain available. This retrospective correction establishes structural identity; it is not an automatically learned association based on future wins or future player performance.

Other provider IDs remain separate. Similar names, common sponsors, or shared players alone never cause an automatic merge. Team and player summary tables describe the full selected pool, so they are not historical feature snapshots.

## Region membership with time

Regions mean competitive ecosystems rather than the nationalities of players. For example, the CBLOL promotion pathway includes LATAM teams, but its modeling region is the CBLOL ecosystem called Brazil in this project.

For each game, region lookup uses only membership observations at or before that game's timestamp. A later domestic appearance must not fill an earlier international game's region silently. Conflicting or absent evidence leaves a visible unresolved status rather than using an opponent's region or a team's name to guess.

Galions and Solary participate in EWC qualifiers but have no appearances in the initial Tier 1 domestic pool. Their earlier 2026 LFL membership records identify EMEA; Solary's [own March 2026 LFL final broadcast](https://www.youtube.com/watch?v=Gdw3PAy4VZI) also names both teams. The supplemental read uses only team ID, name, competition, season, and date metadata. It imports no LFL results or player statistics into the modeling pool. Along with the Team Secret mapping, this resolves the source audit's 24 region-unknown games. Every current team-game row now has an as-of membership region without conflicting evidence.

Observation time is not a verified publication time. The provider's naive timestamps are still provisionally interpreted as UTC. These limitations carry into the manifest; this build does not certify that every metadata field was publicly available before champion select.

## Series reconstruction and evidence

The source `game` column is the number within a series, not a unique match ID. Tournament-server game IDs such as `LOLTMNT03_337058` identify individual games. Their shared server prefix must never be treated as a series ID.

1. Prefer a shared source match reference. LPL records expose a match number in IDs such as `13060-13060_game_1` and a matching `bmid` URL. Validate consistent teams, game numbers, and metadata. Current build: 246 source-supported groups.
2. Where there is no match reference, group games for the same unordered opponents and competition context with consecutive game numbers. Require a positive continuation gap of at most six hours. This accommodates a series crossing midnight. A new game 1 always creates a new group, even for the same opponents on the same day. Current build: 832 provisional sequence groups.
3. Record reviewed corrections separately, with evidence. Current build: one source-supported partial series, described below.

The six-hour rule is a reconstruction assumption, not an official tournament rule. Interrupted series, gaps in source coverage, or incorrect game numbers can break it. Any inference must remain distinguishable from explicit source evidence. A source-supported group still does not prove that all its games have been collected. Missing final games cannot always be detected from sequence continuity alone.

`observed_wins_a` and `observed_wins_b` count only records actually present. They are not certified final match scores. `best_of`, `source_observations_complete`, and `official_winner_team_id` remain blank unless separately established. The only populated `best_of` currently comes from a reviewed BO3 source; there is no guessed series winner. `first_observed_game_at_utc` is the first available game in a group, not a guaranteed true series start.

These groups help prevent games from the same match crossing evaluation folds. The provisional status must still be respected; using groups does not turn inferred match metadata into verified ground truth.

## One confirmed source gap

The file contains game 2, `LOLTMNT02_444730`, of Gen.G versus Dplus Kia on 1 August 2026, but has no game 1 for that matchup/date. Games of Legends has a [game-1 record](https://gol.gg/game/stats/80675/page-game/) and a [BO3 summary](https://gol.gg/game/stats/80675/page-summary/).

A reviewed series rule identifies the available game as belonging to that match, records best-of-three, and marks game 1 missing. It does not import an external outcome, fabricate absent player/statistic rows, or claim the observed one-game score is the final series score. The retained game remains usable as an observed game result, but pre-series evaluation must account for the unknown true first-game timestamp and incomplete observations. Backfilling from another source is a separate data acquisition decision.

This is a useful distinction: a dataset can have exactly twelve well-formed rows for every recorded game and still omit an entire game. A row-level audit cannot certify full schedule coverage.

## Missing values and observed outcomes

All 133 games missing Gold/XP-at-15 data remain included, as do the promotion exceptions, EWC qualifiers, and games across lineup changes. Numeric blanks export as empty CSV fields rather than zeros. Lineup IDs are deterministic from team identity and role/player assignments; they change when the actual lineup changes.

Statistics prefixed `observed_`, including champion choices, are observations of the current finished game. They are preserved evidence, not permitted inputs for predicting that same game before its draft. The next milestone must create historical aggregates from preceding games and fit any imputation only within the training period. The `won` columns are outcome labels.

## Run and inspect

From the repository root in PowerShell:

```powershell
$env:PYTHONPATH = 'src'
python -m worlds_predictor clean data/raw/2026_LoL_esports_match_data_from_OraclesElixir.csv
python -m unittest discover -s tests -v
```

Use `--config`, `--identities`, `--output-dir`, and `--report-dir` to select explicit inputs and destinations. Supply the actual acquisition URL and timestamp with `--source-url` and `--retrieved-at` only if known. A successful build reconciles tables and preserves the audited scope; it does not train or evaluate a model.
