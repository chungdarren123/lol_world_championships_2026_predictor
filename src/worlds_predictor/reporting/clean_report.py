"""Explain which structural identities were resolved and which remain inferred."""


def render_clean_report(report):
    lines = ["# Clean game tables", "", f"Status: {report['status']}", "",
             f"Source SHA-256: {report['source']['sha256']}",
             f"Forecast cutoff: {report['selection_config']['cutoff_utc']}", "",
             "| Table | Rows |", "|---|---:|"]
    for name, count in report["table_counts"].items():
        lines.append(f"| {name} | {count:,} |")
    lines += ["", "Relational checks: " + ", ".join(report["relational_validation"]) + ". All passed."]
    lines += ["", "## Identity resolution", "",
              f"Source team IDs: {report['source_team_ids']}",
              f"Canonical team IDs: {report['table_counts']['teams']}",
              f"Team-game rows using reviewed aliases: {report['reviewed_alias_team_games']}",
              "Region evidence is dated and queried at or before each game's start. Supplemental league records provide membership metadata only.",
              "", "## Series reconstruction", ""]
    lines += [f"- {name}: {count}" for name, count in sorted(report["series_status_counts"].items())]
    lines += ["", "Source-supported means a shared source match reference passed structural checks. It does not certify official best-of or completeness.",
              "Sequence groups are provisional: same opponents and competition context, consecutive game numbers, and bounded time gaps. A new game 1 starts a new group.",
              "", f"Series diagnostic entries: {len(report['series_issues'])}",
              f"Games retained with missing gold-at-15: {report['games_missing_gold_15']}", "",
              "## Quality warnings", ""]
    lines += [f"- {key}: {count}" for key, count in sorted(report["quality_warnings"].items())] or ["None observed."]
    if report["series_issues"]:
        lines += ["", "Series issue examples (full list in JSON):", ""]
        lines += ["- " + str(issue) for issue in report["series_issues"][:10]]
    lines += ["", "## Interpretation before modeling", ""]
    lines += [f"- {x}" for x in report["limitations"]]
    lines += ["", "Training readiness: not established. Canonical tables organize the evidence; they do not create pre-draft features.", ""]
    return "\n".join(lines)
