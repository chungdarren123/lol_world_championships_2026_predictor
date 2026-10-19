# Expanded data scope audit

Status: audited_with_open_reviews

**Not training-ready.** Candidate inventory only; earlier canonical tables are preserved.

Forecast freeze: 2026-10-19T00:00:00Z. Chosen post-draw reporting boundary, not an asserted exact draw-completion time. The official announcement URL's X snowflake decodes to 2026-10-18T20:31:22.645Z; direct timestamp/content retrieval was unavailable. Historical publication availability remains unverified.

Candidates: 3241 games / 1260 series groups. Play-Ins: 22 games / 6 groups.

| Year / event / stage | Candidate games |
|---|---:|
| 2024/EWC/main_event | 19 |
| 2024/MSI/all_event_stages | 78 |
| 2024/Worlds/all_event_stages | 106 |
| 2025/EWC/main_event | 33 |
| 2025/First Stand/main_event | 35 |
| 2025/MSI/all_event_stages | 80 |
| 2025/Worlds/all_event_stages | 84 |
| 2026/CBLOL/promotion | 24 |
| 2026/CBLOL/regional_competition | 275 |
| 2026/EWC/main_event | 51 |
| 2026/EWC/qualifiers | 181 |
| 2026/First Stand/main_event | 45 |
| 2026/LCK/regional_competition | 502 |
| 2026/LCP/regional_competition | 283 |
| 2026/LCS/promotion | 23 |
| 2026/LCS/regional_competition | 260 |
| 2026/LEC/regional_competition | 383 |
| 2026/LPL/regional_competition | 674 |
| 2026/LPL/regional_qualifier | 12 |
| 2026/MSI/main_event | 71 |
| 2026/Worlds/play_in | 22 |

## Blocking findings

- None in implemented structural checks.

## Open reviews

- Event-scope reviews remain: {'window_corroboration_pending': 52, 'pending_primary_event_confirmation': 12}
- Cross-season region transitions and historical team priors are not yet specified or fitted.
- Forecast boundary is chosen; announcement timestamp is decoded from its URL, not independently retrieved.
- Publication timing and source UTC/seconds conventions are not verified.

## Limitations

- Candidate inventory is not a canonical training export; existing model loaders must not consume it as one.
- Source paths, bytes, and checksums are observed; download URLs and retrieval timestamps remain unknown.
- Source league WLDs contains regional qualifiers as well as Worlds; explicit date/ID rules are required.
- All eligible games retain their actual ten player IDs; no missing performance statistics are imputed or used.
- Historical regional rows supply membership metadata only; their outcomes and performance are not imported.
- Historical region labels are not silently mapped to 2026 successors. A model bridge is a separate choice.
- Six inferred Play-In groups and structurally complete rows do not independently prove full official event coverage.
- Complete event coverage requires reconciliation against official fixtures, beyond file-level counts.
