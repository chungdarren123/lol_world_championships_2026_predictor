# Clean game tables

Status: built_with_documented_assumptions

Source SHA-256: 68bb4fd24bc7bfd643f0aba476ed6ad98e17a4812135cbf405295ba0f64c79d0
Forecast cutoff: 2026-10-15T18:00:00Z

| Table | Rows |
|---|---:|
| games | 2,772 |
| team_games | 5,544 |
| player_games | 27,720 |
| series | 1,079 |
| teams | 70 |
| players | 441 |
| team_aliases | 137 |
| team_regions | 71 |

Relational checks: game_team_player_links, cutoff_and_season_provenance, region_evidence_chronology, series_counts_and_observed_scores. All passed.

## Identity resolution

Source team IDs: 71
Canonical team IDs: 70
Team-game rows using reviewed aliases: 8
Region evidence is dated and queried at or before each game's start. Supplemental league records provide membership metadata only.

## Series reconstruction

- provisional_sequence: 832
- source_supported: 246
- source_supported_partial: 1

Source-supported means a shared source match reference passed structural checks. It does not certify official best-of or completeness.
Sequence groups are provisional: same opponents and competition context, consecutive game numbers, and bounded time gaps. A new game 1 starts a new group.

Series diagnostic entries: 1
Games retained with missing gold-at-15: 133

## Quality warnings

None observed.

Series issue examples (full list in JSON):

- {'series_id': 'series:0f1a237c20f4dffc157d31f6', 'issue': 'known_missing_game_numbers:1'}

## Interpretation before modeling

- Naive source timestamps and duration units retain the unverified assumptions in the selection config.
- Observed membership time is not a verified publication timestamp; region evidence is never taken from later games.
- Team/player summaries are descriptive across the full pool, not historical model features.
- Sequence-inferred series are provisional. Best-of, official winner, and completeness are not guessed.
- Observed statistics and champion choices belong to the finished game; pre-draft features must use preceding games only.
- No models were fitted. Missing values and lineup changes are retained.

Training readiness: not established. Canonical tables organize the evidence; they do not create pre-draft features.
