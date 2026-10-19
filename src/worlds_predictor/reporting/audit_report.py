"""Render findings without presenting candidate records as a training dataset."""


def render_report(report: dict) -> str:
    source = report.get("source", {})
    lines = ["# 2026 data audit", "", f"Status: {report['status']}", "",
             f"Source file: {source.get('file_name', 'unavailable')}",
             f"Source URL: {source.get('source_url') or 'not recorded'}",
             f"Retrieved at (UTC): {source.get('retrieved_at_utc') or 'not recorded'}",
             f"SHA-256: {source.get('sha256', 'unavailable')}", "",
             f"Cutoff: {report['config']['cutoff_utc']}",
             report['config']['cutoff_basis'], "",
             "Training readiness: not established. This audit does not produce model inputs.", ""]
    if report.get("errors"):
        lines += ["## Acquisition or schema errors", ""]
        lines += [f"- {message}" for message in report["errors"]]
        lines += ["", "No real-game coverage or feature-availability findings can be drawn from this source.", ""]
    else:
        lines += [f"Source records: {report['rows'].get('total', 0):,}",
                  f"Source game keys: {report['source_games']:,}",
                  f"In-scope candidates: {report['candidate_games']:,}",
                  f"Structurally valid candidates: {report['structurally_valid_games']:,}",
                  f"Quarantined candidates: {report['quarantined_candidate_games']:,}", "",
                  "## Competition coverage", "",
                  "Observed presence does not prove complete coverage. Dates are candidate game starts.", "",
                  "| Competition | Observed games | Candidates | Valid candidates | First date | Last date |",
                  "|---|---:|---:|---:|---|---|"]
        for name, row in report["coverage"].items():
            lines.append(f"| {name} | {row['observed_games']} | {row['candidate_games']} | {row['structurally_valid_games']} | {row['first_candidate_date'] or 'missing'} | {row['last_candidate_date'] or 'missing'} |")
        lines += ["", "## Retention and event context", "",
                  "Games with missing timed statistics and lineup changes are retained. Missing values remain missing.",
                  "Approved promotion exceptions retain their original source season; nothing in the raw CSV is relabeled.", "",
                  "| Competition | Stage | Source season | Valid candidate games |", "|---|---|---:|---:|"]
        for row in report["event_stage_game_counts"]:
            lines.append(f"| {row['league']} | {row['stage']} | {row['source_season']} | {row['games']} |")
        lines += ["", "## Feature coverage", "",
                  "Counts refer to team rows in structurally valid candidates. A valid zero is numeric, not missing.", "",
                  "| Field | Numeric | Missing | Invalid |", "|---|---:|---:|---:|"]
        for feature, counts in report["team_row_feature_coverage"].items():
            lines.append(f"| {feature} | {counts.get('numeric', 0)} | {counts.get('missing', 0)} | {counts.get('invalid', 0)} |")
        lines += ["", "Games missing usable gold-at-15 values for either team: "
                  + str(report["games_without_both_numeric_team_values"].get("gold_diff_15", 0)), "",
                  "| League | Source completeness | Duration band (source units) | Games missing gold at 15 |",
                  "|---|---|---|---:|"]
        for row in report["missing_gold_15_game_breakdown"]:
            lines.append(f"| {row['league']} | {row['completeness']} | {row['duration_band']} | {row['games']} |")
        for title, key in (("Excluded games", "exclusions"), ("Row issues", "row_issues"),
                           ("Candidate validation failures", "validation_failures"),
                           ("Quality warnings", "quality_warnings"),
                           ("Observed competition labels", "observed_league_labels"),
                           ("Cross-region game counts", "cross_region_game_counts")):
            lines += ["", f"## {title}", ""]
            values = report.get(key, {})
            lines += [f"- {name}: {count}" for name, count in sorted(values.items())] or ["None observed."]
        lines += ["", f"Observed lineup changes: {len(report['observed_lineup_changes'])}",
                  f"Distinct team identity keys: {report['distinct_team_ids_or_name_keys']}",
                  f"Team IDs with name aliases: {len(report['team_aliases'])}",
                  f"Team names with multiple IDs: {len(report['ambiguous_team_names'])}",
                  f"International games with unresolved regions: {report['international_games_with_unresolved_regions']}",
                  f"Same-region games in multi-region competition families (including qualifiers): {sum(report['same_region_international_game_counts'].values())}",
                  "", "Detailed examples, source competition/season inventory, lineup transitions, splits, patches, and per-league feature coverage are in the JSON report."]
    lines += ["", "## Review before modeling", ""]
    lines += [f"- {x}" for x in report.get("review_required", [])]
    lines += [f"- {x}" for x in report.get("warnings", [])]
    lines += ["", source.get("availability_caveat", "Source acquisition is incomplete."), ""]
    return "\n".join(lines)
