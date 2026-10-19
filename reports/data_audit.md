# 2026 data audit

Status: audited

Source file: 2026_LoL_esports_match_data_from_OraclesElixir.csv
Source URL: not recorded
Retrieved at (UTC): not recorded
SHA-256: 68bb4fd24bc7bfd643f0aba476ed6ad98e17a4812135cbf405295ba0f64c79d0

Cutoff: 2026-10-15T18:00:00Z
Scheduled first Play-In start; conservative forecast freeze, not a verified actual game-server start.

Training readiness: not established. This audit does not produce model inputs.

Source records: 116,664
Source game keys: 9,722
In-scope candidates: 2,772
Structurally valid candidates: 2,772
Quarantined candidates: 0

## Competition coverage

Observed presence does not prove complete coverage. Dates are candidate game starts.

| Competition | Observed games | Candidates | Valid candidates | First date | Last date |
|---|---:|---:|---:|---|---|
| LCK | 502 | 502 | 502 | 2026-01-14T08:13:43+00:00 | 2026-09-13T08:19:05+00:00 |
| LPL | 674 | 674 | 674 | 2026-01-14T09:13:04+00:00 | 2026-09-13T12:03:56+00:00 |
| LEC | 383 | 383 | 383 | 2026-01-17T16:08:02+00:00 | 2026-09-20T17:13:10+00:00 |
| LCS | 283 | 283 | 283 | 2026-01-24T21:24:34+00:00 | 2026-10-13T00:26:18+00:00 |
| LCP | 283 | 283 | 283 | 2026-01-16T06:23:26+00:00 | 2026-08-30T10:26:53+00:00 |
| CBLOL | 299 | 299 | 299 | 2026-01-17T16:19:20+00:00 | 2026-10-12T23:41:27+00:00 |
| First Stand | 45 | 45 | 45 | 2026-03-16T13:10:29+00:00 | 2026-03-22T16:04:39+00:00 |
| MSI | 71 | 71 | 71 | 2026-06-28T03:10:49+00:00 | 2026-07-12T11:11:20+00:00 |
| EWC | 232 | 232 | 232 | 2026-04-14T18:07:58+00:00 | 2026-07-19T15:15:31+00:00 |

## Retention and event context

Games with missing timed statistics and lineup changes are retained. Missing values remain missing.
Approved promotion exceptions retain their original source season; nothing in the raw CSV is relabeled.

| Competition | Stage | Source season | Valid candidate games |
|---|---|---:|---:|
| CBLOL | promotion | 2027 | 24 |
| CBLOL | regional_competition | 2026 | 275 |
| EWC | main_event | 2026 | 51 |
| EWC | qualifiers | 2026 | 181 |
| First Stand | main_event | 2026 | 45 |
| LCK | regional_competition | 2026 | 502 |
| LCP | regional_competition | 2026 | 283 |
| LCS | promotion | 2027 | 23 |
| LCS | regional_competition | 2026 | 260 |
| LEC | regional_competition | 2026 | 383 |
| LPL | regional_competition | 2026 | 674 |
| MSI | main_event | 2026 | 71 |

## Feature coverage

Counts refer to team rows in structurally valid candidates. A valid zero is numeric, not missing.

| Field | Numeric | Missing | Invalid |
|---|---:|---:|---:|
| gold_diff_15 | 5278 | 266 | 0 |
| xp_diff_15 | 5278 | 266 | 0 |
| kills | 5544 | 0 | 0 |
| duration | 5544 | 0 | 0 |

Games missing usable gold-at-15 values for either team: 133

| League | Source completeness | Duration band (source units) | Games missing gold at 15 |
|---|---|---|---:|
| LEC | complete | 900_or_more_source_units_or_unknown | 1 |
| LPL | complete | 900_or_more_source_units_or_unknown | 12 |
| LPL | partial | 900_or_more_source_units_or_unknown | 120 |

## Excluded games

- unreviewed_competition: 6923
- worlds: 27

## Row issues

None observed.

## Candidate validation failures

None observed.

## Quality warnings

- games_with_assumed_timestamp_timezone: 2772
- games_without_explicit_series_id: 2772

## Observed competition labels

- AC: 19
- AL: 350
- AM: 63
- CBLOL: 299
- CCWS: 40
- CD: 258
- DCGI: 71
- DCup: 3
- EBL: 213
- EM: 519
- EWC: 232
- FST: 45
- HC: 201
- HLL: 235
- HM: 174
- HW: 103
- KeSPA Cup: 61
- LAS: 486
- LCK: 502
- LCKC: 491
- LCP: 283
- LCS: 283
- LEC: 383
- LES: 208
- LFL: 275
- LIT: 280
- LJL: 363
- LPL: 674
- LPLOL: 162
- LRN: 176
- LRS: 187
- MSI: 71
- NACL: 281
- NL: 149
- NLC: 210
- PCS: 86
- PRM: 322
- RL: 211
- ROL: 261
- TCL: 219
- VCS: 155
- WLDs: 27
- WLRQ: 6
- WSCI: 85

## Cross-region game counts

- Asia Pacific / China: 4
- Asia Pacific / EMEA: 9
- Asia Pacific / Korea: 9
- Asia Pacific / North America: 6
- Brazil / China: 5
- Brazil / EMEA: 1
- Brazil / Korea: 6
- Brazil / North America: 10
- China / EMEA: 16
- China / Korea: 30
- China / North America: 8
- EMEA / Korea: 25
- EMEA / North America: 8
- Korea / North America: 15

Observed lineup changes: 176
Distinct team identity keys: 71
Team IDs with name aliases: 0
Team names with multiple IDs: 0
International games with unresolved regions: 24
Same-region games in multi-region competition families (including qualifiers): 172

Detailed examples, source competition/season inventory, lineup transitions, splits, patches, and per-league feature coverage are in the JSON report.

## Review before modeling

- Coverage must be reconciled with an independent competition schedule.
- Publication times and pre-cutoff availability have not been verified.
- Series identifiers and historical prediction timing require review.
- Source timestamp timezone has not been verified.
- Game-duration units have not been verified; completion before the cutoff is unconfirmed.
- Candidate and structurally valid counts are audit findings, not permission to train.
- Observed lineup changes may reflect substitutions, aliases, or source errors. Incomplete lineups are not interpolated.
- International region mapping is retrospective for this audit only; it must not be copied into historical features.

Match timestamps do not prove data was published before the cutoff. A later download may contain backfills or corrections.
