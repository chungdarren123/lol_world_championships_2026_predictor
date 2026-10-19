# First lesson: audit the evidence before fitting a model

The data audit measures what the source contains and whether its records can be interpreted consistently. It produces no canonical training dataset and trains no model.

## Current acquisition result

Oracle's Elixir's [downloads page](https://oracleselixir.com/tools/downloads) links to a public [Google Drive folder](https://drive.google.com/drive/u/1/folders/1gLSw0RLjBbtaNy0dgnGQDAZOHIgCe-HH). That folder contains `2026_LoL_esports_match_data_from_OraclesElixir.csv`, file ID `1hnpbrUpBMS1TZI7IovfpKeZfWJH1Aptm`.

The initial download returned an HTML page titled `Google Drive - Quota exceeded`, despite a successful HTTP response. The auditor rejected it. The user subsequently replaced that file with the actual dataset, which has now been audited. No mirror was used.

The supplied CSV is 78,007,452 bytes with SHA-256 `68bb4fd24bc7bfd643f0aba476ed6ad98e17a4812135cbf405295ba0f64c79d0`. Its exact download URL and retrieval timestamp were not supplied, so the new report leaves them unknown. The file's modification time is not treated as proof of acquisition time. The raw file remains unchanged and ignored by Git.

## Findings from the supplied CSV

The source contains 165 columns, 116,664 rows, and 9,722 `(league, gameid)` keys. Under the reviewed scope, 2,772 games are candidates and pass the implemented structural checks: the initial 2,493, plus 232 EWC games and 47 approved promotion-event exceptions. There are no observed exact duplicate rows, malformed rows, or candidate team/result inconsistencies. This is evidence about those checks, not proof the source has no errors.

| Competition | Candidate games |
|---|---:|
| LCK | 502 |
| LPL | 674 |
| LEC | 383 |
| LCS (including 23 promotion games) | 283 |
| LCP | 283 |
| CBLOL (including 24 promotion games) | 299 |
| First Stand | 45 |
| MSI | 71 |
| EWC (51 main-event games and 181 qualifier games) | 232 |
| Total | 2,772 |

The source label for Worlds is `WLDs`; all 27 such games are explicitly excluded. The 47 records labeled source season 2027 are promotion tournaments played in 2026 for league places in 2027, not demonstrated labeling errors. Riot's [LCS announcement](https://lolesports.com/en-US/news/lcs-promotion-tournament-wsci) schedules the tournament for October 5-12 and explicitly says the winner earns the 2027 guest slot. Riot's [CBLOL announcement](https://lolesports.com/pt-BR/lolesports/news/torneio-de-promoo-ao-cblol-wsci) schedules September 28-October 12 with the same 2027 qualification purpose. October 13 source timestamps are consistent with later games in October 12 local sessions, assuming the source timezone is UTC.

The user approved inclusion of all 47 as explicit exceptions. Rules require the relevant league, source season 2027, reviewed event date window, blank source split and source playoffs flag 0, while still enforcing calendar year 2026 and the forecast cutoff. The source season remains 2027 in the inventory and stage breakdown. The raw CSV is never relabeled.

Gold/XP difference at 15 minutes is missing in 133 games: 132 LPL and one LEC. Both team values are numeric for the other 2,639 games. Kills and duration are numeric on all 5,544 candidate team rows. Dropping the 133 games would remove approximately 19.6% of the LPL sample, so missingness is not evenly distributed across regions. The user explicitly chose to retain these games, with missing values preserved. Elo can use their results. Logistic regression will need an explicit policy for missing historical feature aggregates, fitted using training data only. Availability counts/indicators can help distinguish well-supported averages from sparse ones. No missing value is converted to zero in this audit.

The provider's `complete` flag does not guarantee every desired feature is present: 13 of the 133 games missing gold at 15 are labeled complete. Conversely, some partial games have usable gold-at-15 data. Audit each needed field rather than filtering only on the label. None of the missing-gold games have duration values below 900 source units, so a game ending before 15 minutes does not explain these gaps under the provisional seconds interpretation.

Complete lineups are available for the current candidates, and 176 changes are observed between successive complete lineups. These are lineup transitions, not necessarily 176 permanent transfers. The user explicitly chose to retain games across those changes. Roster continuity or recency features can express their relevance without deleting historical results. All candidate games lack an explicit series ID column, so evaluation that groups games by series still requires a reviewed series mapping.

The user approved EWC inclusion. All 232 EWC games are retained: 181 qualifier-period games from April-June and 51 main-event games from July 15-19. The main-event window matches the [organizer's tournament page](https://ewc-web.prod.esf-systems.com/en/competitions/2026/league-of-legends), which also identifies the regional qualifiers. Reviewed date windows classify this source; the source playoffs flag alone is not treated as a universal stage definition. EWC records outside those windows would be retained but explicitly marked unclassified for review.

Not every EWC game is a cross-region match. The raw-ID region audit finds 172 same-region games in the multi-region competition families, and 24 games with unresolved region identities. These records remain retained. The subsequent [canonical-table build](clean_tables.md) resolves these region gaps using the reviewed Team Secret identity correction and earlier LFL membership metadata for Galions/Solary. The source audit intentionally remains a report on uncorrected provider identities. `KeSPA Cup`, `DCGI`, and `WLRQ` still require competition/participant scope review and remain outside the current pool.

The LCP source marks every Split 3 game `playoffs=0`, although the dates extend to August 30. This flag alone is insufficient evidence that playoff matches are missing. Coverage must be reconciled against a schedule using actual match identities.

## Cutoff and scope

Riot's [Worlds 2026 primer](https://lolesports.com/en-GB/news/worlds-2026-primer), published 5 October, schedules the first Play-In day for 15 October at 11 AM PDT / 8 PM CEST. We use `2026-10-15T18:00:00Z` as a conservative forecast freeze. This is a scheduled start, not evidence of the actual first game-server timestamp. Earlier availability of each game's results still needs review.

The competition allowlist in `configs/audit_2026.json` covers LCK, LPL, LEC, LCS, LCP, CBLOL, First Stand, MSI, and EWC. Every observed competition label is reported. Unknown labels are held out for review, so additional qualifiers or official cross-regional events are not silently discarded as irrelevant. All Worlds labels are explicitly excluded, independently of the date filter. Games need consistent 2026 season/date fields or an approved promotion-event season exception; all must be played in 2026 before the cutoff.

Coverage remains provisional until reconciled against competition schedules. The user requested regional and international professional data; this allowlist is an explicit reviewed pool, not a claim that these nine labels exhaust that scope.

## Three useful distinctions

1. **Source rows versus games:** a common source layout has ten player rows plus two team rows per game. We group by league and game ID and validate the actual structure. We do not divide row counts by twelve.
2. **Candidate versus structurally valid:** a candidate passes scope/date filters. A structurally valid candidate additionally has two distinct teams, Blue and Red sides, complementary results, and consistent metadata without duplicate rows. These counts do not establish historical publication availability.
3. **Missing versus zero:** a gold difference of zero means tied gold. A blank means unavailable. Invalid numbers such as infinity are reported separately. Nothing is imputed during the audit.

The provider's [legacy data dictionary](https://lol.timsevenhuysen.com/matchdata/match-data-dictionary/) documents the general field meanings and warns of schema changes. It is not sufficient to verify the exact 2026 schema. The auditor lists every source column and the selected alias for each semantic field. Missing required fields block the audit, rather than triggering guessed conversions.

## Checks and outputs

- Record the source filename, URL, bytes, SHA-256 checksum, actual retrieval time if known, and audit time.
- Inventory competitions and their observed counts, candidate date ranges, and structurally valid candidates. Complete schedules must still be reconciled independently.
- Report excluded games by reason: Worlds, unreviewed competition, wrong season, invalid date, or cutoff.
- Detect malformed rows, exact duplicates, missing game keys, inconsistent metadata, and invalid team/result structure. Never repair or deduplicate silently.
- Report numeric/missing/invalid feature counts overall and by league for historical gold/XP difference at 15 minutes, kills, and duration.
- List source completeness labels, patch counts, split/playoff counts, team-name aliases, and ambiguous names.
- Compare only complete five-role lineups in chronological order. Flag substitutions and identity uncertainty. A change is an observation, not proof of a permanent roster replacement.
- Count international region connections only where stable identities have unambiguous domestic evidence. This retrospective audit mapping is not a historical model feature.
- Flag absent explicit series IDs. The source `game` field is a game number, not a unique series identifier. No heuristic series grouping is asserted yet.

The JSON contains detailed diagnostics. The Markdown report provides a readable summary. Both name unresolved prerequisites before modeling. Detailed excluded-game outcomes are not included in feature summaries.

## Timing assumptions remain explicit

`timestamp_timezone_verified` and `duration_unit_verified` start false. Naive timestamps are provisionally interpreted as UTC, and duration units are configured as seconds, but neither assumption is treated as verified provider evidence. Once the actual schema/documentation is inspected, update these settings with evidence. If duration units are verified, the audit flags games whose estimated end reaches or exceeds the cutoff. Estimated game ends still do not prove when statistics were published.

Even when a source passes structural checks, the report leaves training readiness unestablished. This milestone is intended for review, not as an automatic admission gate. The later cleaning pipeline will enforce the reviewed availability rules, scope, and quarantine decisions.

## Running locally

The audit has no third-party runtime dependencies. In PowerShell from the repository root:

```powershell
$env:PYTHONPATH = 'src'
python -m worlds_predictor audit data/raw/2026.csv --source-url 'ACTUAL_DOWNLOAD_URL' --retrieved-at 'KNOWN_ISO_TIMESTAMP_WITH_TIMEZONE'
python -m unittest discover -s tests -v
```

Omit `--retrieved-at` when unknown; do not invent it from the match date or audit time. The reports record it as unavailable.

For this workspace, an available bundled Python executable is:

```text
C:/Users/chung/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe
```

Invoke it with PowerShell's `&` operator in place of `python`. This avoids installing a runtime for the audit. Other users can use any Python 3.11+ interpreter. Installing the package later exposes the `worlds-predictor` command.

## What comes after a real-data audit

Review competition coverage, timestamp/duration definitions, identity mappings, series identifiers, and feature missingness. Then build canonical game/team/player tables, followed by historical features. A team's past gold difference can be a pre-draft feature; the current game's gold difference cannot. All rolling features must use only records available before the historical prediction time.

The tests use small synthetic records to verify audit behavior. They do not demonstrate real-world data coverage or model performance.

## Follow-up audit of the expanded scope

The counts and blanket Worlds exclusion above describe the original source snapshot and rules. After the user supplied 2024, 2025, and an updated 2026 file, `scope-audit` inventories a separate expanded pool. It does not overwrite the original reports or canonical tables. The original 2026 checksum remains recorded in that snapshot; the replacement raw file has a different checksum.

The provider uses `WLDs` for some domestic qualification games as well as Worlds itself. Date windows therefore exclude 26 such pre-event records in 2024 and 12 in 2025 from the historical international pool. Twelve September 2026 LPL-reference records are separately flagged as likely regional finals; they need primary event confirmation before a training build restores them. The old blanket exclusion must not be reused as a final event-classification rule.

The updated 2026 file contains 22 observed Play-In games grouped into six series. Each observed game-number/win sequence is consistent with the official Bo5 format; this is distinct from independently reconciling every official final score or proving complete coverage. No missing games are fabricated. The expanded audit checks whole-game rows and actual lineups and records dated membership evidence without importing historical domestic outcomes.

The [expanded audit report](../reports/expanded_audit.md) distinguishes candidates, structural errors, and open reviews. The [chronological evaluation plan](../reports/evaluation_plan.md) freezes pre-event training sets before First Stand, MSI, and EWC 2026, using assumed result availability rather than game-start time alone. No new model is fitted by either command.
