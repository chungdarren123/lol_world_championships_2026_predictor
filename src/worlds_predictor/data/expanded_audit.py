"""Audit the proposed expanded pool without overwriting canonical snapshots."""

from collections import Counter, defaultdict
from copy import deepcopy
import csv
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path

from .audit import audit_csv, event_stage, matching_season_exception, number, parse_date, ROLE_ALIASES, ROLES
from .clean import source_text
from .identities import IdentityResolver
from .series import resolve_series, stable_id
from worlds_predictor.ingestion.csv_source import read_csv, file_metadata


PROJECT_FIELDS = ("gameid", "league", "year", "date", "position", "side", "result", "teamid", "teamname",
                  "team", "playerid", "game", "split", "playoffs", "gamelength", "url", "seriesid", "series_id", "matchid")


def at(value):
    result, naive = parse_date(value, "UTC")
    if result is None or naive:
        raise ValueError("Configuration timestamps must be timezone-aware.")
    return result


def classify(year, league, gid, started, scope, base_keys, base_config):
    """Explicit event windows prevent regional qualifiers masquerading as Worlds."""
    if started is None or started.year != year:
        return None, "invalid_played_year_or_date"
    if started >= at(scope["forecast_freeze_utc"]):
        return None, "at_or_after_forecast_freeze"
    if year < 2026:
        matches = [rule for rule in scope["historical_events"] if rule["year"] == year
                   and rule["league"] == league and at(rule["start"]) <= started < at(rule["end"])]
        if len(matches) > 1:
            raise ValueError("Historical event windows overlap.")
        if matches:
            return {"event": matches[0]["event"],
                    "stage": "all_event_stages" if matches[0]["event"] in {"Worlds", "MSI"} else "main_event",
                    "scope_review": "window_corroboration_pending" if matches[0]["source"] is None else "reviewed_window"}, None
        return None, "outside_historical_international_windows"
    if (league, gid) in base_keys:
        mapping = {alias.casefold(): name for name, info in base_config["leagues"].items() for alias in info["aliases"]}
        event = mapping[league.casefold()]
        return {"event": event, "stage": None, "scope_review": "existing_approved_scope"}, None
    play_in = scope["play_in"]
    if league == "WLDs" and at(play_in["start"]) <= started < at(play_in["end"]):
        return {"event": "Worlds", "stage": "play_in", "scope_review": "approved_play_in_only"}, None
    review = scope["regional_qualifier_review"]
    if (league == review["source_league"] and at(review["start"]) <= started < at(review["end"])
            and any(gid.startswith(ref + "-" + ref + "_game_") for ref in review["source_match_ids"])):
        return {"event": review["candidate_event"], "stage": review["candidate_stage"],
                "scope_review": review["review_status"]}, None
    return None, "not_in_approved_current_pool"


def structural_issues(rows, year):
    problems = []
    if len(rows) != 12:
        problems.append("expected_twelve_rows")
    for field in ("date", "year", "game", "split", "playoffs"):
        if len({r[field] for r in rows}) != 1:
            problems.append("inconsistent_" + field)
    if year < 2026 and any(number(r["year"]) != year for r in rows):
        problems.append("historical_source_season_mismatch")
    teams = [r for r in rows if r["position"].casefold() == "team"]
    if len(teams) != 2 or {r["side"].casefold() for r in teams} != {"blue", "red"}:
        problems.append("invalid_team_sides")
        return problems
    if len({r["teamid"] for r in teams}) != 2 or any(not r["teamid"] for r in teams):
        problems.append("invalid_team_ids")
    if sorted(number(r["result"]) for r in teams if number(r["result"]) is not None) != [0, 1]:
        problems.append("noncomplementary_outcomes")
    players = [r for r in rows if r["position"].casefold() != "team"]
    if len({r["playerid"] for r in players}) != 10 or any(not r["playerid"] for r in players):
        problems.append("incomplete_or_repeated_player_ids")
    for team in teams:
        side = team["side"].casefold()
        members = [r for r in players if r["side"].casefold() == side]
        roles = [ROLE_ALIASES.get(r["position"].casefold(), r["position"].casefold()) for r in members]
        if len(members) != 5 or set(roles) != ROLES:
            problems.append("incomplete_lineup_roles_" + side)
        if any(r["teamid"] != team["teamid"] or r["result"] != team["result"] for r in members):
            problems.append("player_team_or_outcome_disagreement_" + side)
    return sorted(set(problems))


def resolve_membership(observations, when):
    """Observations contain metadata only. Conflicting earlier labels need review."""
    prior = [r for r in observations if r[0] <= when]
    labels = {r[1] for r in prior}
    if len(labels) != 1:
        return "", "", "conflicting_evidence" if labels else "no_prior_membership"
    latest = max(prior)
    return latest[1], latest[0].isoformat(), "dated_participation"


def audit_expanded(scope, base_config, identities):
    cutoff = at(scope["forecast_freeze_utc"])
    announcement = datetime.fromtimestamp(((int(scope["announcement_id"]) >> 22) + 1288834974657) / 1000, timezone.utc)
    if cutoff <= announcement:
        raise ValueError("Post-draw freeze must follow the derived announcement timestamp.")
    if cutoff >= at(scope["swiss_first_scheduled_start_utc"]):
        raise ValueError("The Swiss forecast freeze must precede its first scheduled game.")
    revised_base = deepcopy(base_config)
    revised_base["cutoff_utc"] = scope["forecast_freeze_utc"]
    reports, candidates, exclusions, errors, pending = {}, [], Counter(), [], []
    base_path = Path(scope["sources"]["2026"])
    base_keys = set()
    if base_path.exists():
        base_report = audit_csv(base_path, revised_base, include_game_keys=True)
        if base_report["status"] != "audited":
            raise ValueError("Current-year baseline audit is blocked.")
        base_keys = {(r["league"], r["source_game_id"]) for r in base_report["accepted_game_keys"]}
    resolver = IdentityResolver(identities)
    for year_text, name in sorted(scope["sources"].items()):
        year, path = int(year_text), Path(name)
        if not path.exists():
            errors.append("Missing source: " + str(path))
            continue
        metadata = file_metadata(path, None, None)
        memberships, grouped, inventory = defaultdict(list), defaultdict(list), {}
        malformed = 0
        with read_csv(path) as (_, reader):
            for raw in reader:
                if None in raw or None in raw.values():
                    malformed += 1
                    continue
                row = {key: source_text(raw, key) for key in PROJECT_FIELDS}
                league, gid = row["league"], row["gameid"]
                stamp, _ = parse_date(row["date"], scope["source_timezone"])
                if row["position"].casefold() == "team":
                    key = (league, gid)
                    inventory.setdefault(key, {"source_league": league, "date": row["date"]})
                    label = scope["membership_leagues"].get(year_text, {}).get(league)
                    if label and stamp is not None and stamp.year == year and stamp < cutoff:
                        source_year = number(row["year"])
                        if source_year == year or (year == 2026 and key in base_keys):
                            team = resolver.team(row["teamid"], row["teamname"] or row["team"], league, stamp)[0] if year == 2026 else row["teamid"]
                            memberships[team].append((stamp, label, league, gid))
                selected, reason = classify(year, league, gid, stamp, scope, base_keys, revised_base)
                if selected:
                    grouped[(league, gid)].append(row)
        source_excluded = Counter()
        worlds_label_outside_event = 0
        for (league, gid), item in inventory.items():
            stamp, _ = parse_date(item["date"], scope["source_timezone"])
            selected, reason = classify(year, league, gid, stamp, scope, base_keys, revised_base)
            if not selected:
                source_excluded[reason] += 1
                if year < 2026 and league == "WLDs":
                    worlds_label_outside_event += 1
        reports[year_text] = {"source": metadata, "source_games_with_team_rows": len(inventory),
                              "malformed_rows": malformed, "selected_game_keys": len(grouped),
                              "historical_worlds_label_outside_event_window": worlds_label_outside_event,
                              "excluded": dict(source_excluded)}
        if malformed:
            errors.append(f"{year}: malformed source rows require review ({malformed}).")
        for (league, gid), rows in sorted(grouped.items()):
            issues = structural_issues(rows, year)
            if issues:
                errors.append(f"{year}/{league}/{gid}: " + ", ".join(issues))
                continue
            sides = {r["side"].casefold(): r for r in rows if r["position"].casefold() == "team"}
            first = sides["blue"]
            started, _ = parse_date(first["date"], scope["source_timezone"])
            selection, _ = classify(year, league, gid, started, scope, base_keys, revised_base)
            stage = selection["stage"]
            exception = None
            if stage is None:
                exception = matching_season_exception(rows, selection["event"], started, revised_base) if number(first["year"]) != 2026 else None
                stage = event_stage(selection["event"], started, exception, revised_base)
            durations = [number(r["gamelength"]) for r in sides.values()]
            if any(d is None or not 0 < d < 86400 for d in durations) or durations[0] != durations[1]:
                errors.append(f"{year}/{gid}: invalid duration; cannot audit assumed availability.")
                continue
            available = started + timedelta(seconds=durations[0], minutes=scope["assumed_result_delay_minutes"])
            if available >= cutoff:
                exclusions["assumed_result_available_after_freeze"] += 1
                continue
            if stage == "play_in" and any((r["teamname"] or r["team"]) not in scope["play_in"]["team_names"] for r in sides.values()):
                errors.append(f"Unexpected Play-In participant: {gid}")
                continue
            record = {"game_id": stable_id("game", league, gid) if year == 2026 else stable_id("game", year, league, gid),
                      "source_game_id": gid, "source_league": league, "league": selection["event"],
                      "source_season": int(number(first["year"])), "played_year": year, "stage": stage,
                      "split": first["split"], "season_exception": exception or "",
                      "started_at_utc": started.isoformat(), "assumed_available_at_utc": available.isoformat(),
                      "game_number": int(number(first["game"])) if number(first["game"]) is not None else "",
                      "source_url": first["url"], "source_series_id": first["seriesid"] or first["series_id"] or first["matchid"],
                      "blue_won": int(number(first["result"])), "scope_review": selection["scope_review"]}
            for side, row in sides.items():
                source_id = row["teamid"]
                name = row["teamname"] or row["team"]
                team = resolver.team(source_id, name, league, started)[0] if year == 2026 else source_id
                region, evidence, status = resolve_membership(memberships.get(team, []), started)
                record.update({side + "_team_id": team, side + "_source_team_id": source_id,
                               side + "_team_name": name, side + "_region": region,
                               side + "_membership_at_utc": evidence, side + "_region_status": status,
                               side + "_lineup_ids": json.dumps(sorted(r["playerid"] for r in rows
                                  if r["side"].casefold() == side and r["position"].casefold() != "team"))})
                eligible_evidence = [r for r in memberships.get(team, []) if r[0] <= started and r[1] == region]
                latest = max(eligible_evidence) if eligible_evidence else None
                record[side + "_membership_source_league"] = latest[2] if latest else ""
                record[side + "_membership_source_game_id"] = latest[3] if latest else ""
            record["winner_team_id"] = record["blue_team_id"] if record["blue_won"] else record["red_team_id"]
            candidates.append(record)
        if file_metadata(path, None, None)["sha256"] != metadata["sha256"]:
            raise ValueError("Source changed during expanded audit: " + str(path))
    candidates.sort(key=lambda r: (r["started_at_utc"], r["game_id"]))
    if len({r["game_id"] for r in candidates}) != len(candidates):
        raise ValueError("Cross-season game identity collision.")
    series_policy = deepcopy(identities["series"])
    observed_ids = {r["game_id"] for r in candidates}
    present_overrides = []
    for rule in series_policy.get("overrides", []):
        if set(rule["game_ids"]) <= observed_ids:
            present_overrides.append(rule)
        elif base_path.exists():
            errors.append("Reviewed partial-series override is missing from the candidate inventory: " + rule["series_reference"])
    series_policy["overrides"] = present_overrides
    series, series_issues = resolve_series(candidates, series_policy)
    play_series = [r for r in series if r["stage"] == "play_in"]
    play_checks = []
    for group in play_series:
        members = [r for r in candidates if r["series_id"] == group["series_id"]]
        numbers = sorted(r["game_number"] for r in members)
        wins = Counter(r["winner_team_id"] for r in members)
        consistent = numbers == list(range(1, len(members) + 1)) and max(wins.values()) == 3 and 3 <= len(members) <= 5
        play_checks.append({"series_id": group["series_id"], "observed_game_numbers": numbers,
                            "observed_wins": dict(wins), "consistent_with_bo5": consistent,
                            "official_final_score_verified": False})
        if not consistent:
            errors.append("Play-In group has missing/invalid observed BO5 sequence: " + group["series_id"])
    if len(play_series) != scope["play_in"]["expected_series"]:
        errors.append(f"Play-In coverage: observed {len(play_series)} series groups; expected {scope['play_in']['expected_series']}.")
    unresolved = [r["game_id"] for r in candidates if not r["blue_region"] or not r["red_region"]]
    if unresolved:
        errors.append(f"Unresolved or conflicting historical membership in {len(unresolved)} games.")
    review_counts = Counter(r["scope_review"] for r in candidates if r["scope_review"] not in
                            {"reviewed_window", "existing_approved_scope", "approved_play_in_only"})
    if review_counts:
        pending.append("Event-scope reviews remain: " + str(dict(review_counts)))
    pending += ["Cross-season region transitions and historical team priors are not yet specified or fitted.",
                "Forecast boundary is chosen; announcement timestamp is decoded from its URL, not independently retrieved.",
                "Publication timing and source UTC/seconds conventions are not verified."]
    for rule in scope["historical_events"]:
        if not any(r["played_year"] == rule["year"] and r["league"] == rule["event"] for r in candidates):
            errors.append(f"Missing expected historical event: {rule['year']} {rule['event']}")
    report = {"status": "blocked" if errors else "audited_with_open_reviews", "training_ready": False,
              "forecast_scope": scope, "base_selection_config": revised_base, "identity_config": identities,
              "announcement_time_derived_from_id_utc": announcement.isoformat(),
              "sources": reports, "errors": errors, "open_reviews": pending,
              "candidate_games": len(candidates), "candidate_series": len(series),
              "counts_by_event": dict(Counter(f"{r['played_year']}/{r['league']}/{r['stage']}" for r in candidates)),
              "candidate_region_labels": sorted({r[side + "_region"] for r in candidates for side in ("blue", "red")}),
              "play_in_games": sum(r["stage"] == "play_in" for r in candidates), "play_in_series_groups": len(play_series),
              "play_in_observed_sequence_checks": play_checks,
              "unresolved_region_games": unresolved, "scope_review_counts": dict(review_counts),
              "exclusions_after_selection": dict(exclusions), "series_issues": series_issues,
              "limitations": [
                  "Candidate inventory is not a canonical training export; existing model loaders must not consume it as one.",
                  "Source paths, bytes, and checksums are observed; download URLs and retrieval timestamps remain unknown.",
                  "Source league WLDs contains regional qualifiers as well as Worlds; explicit date/ID rules are required.",
                  "All eligible games retain their actual ten player IDs; no missing performance statistics are imputed or used.",
                  "Historical regional rows supply membership metadata only; their outcomes and performance are not imported.",
                  "Historical region labels are not silently mapped to 2026 successors. A model bridge is a separate choice.",
                  "Six inferred Play-In groups and structurally complete rows do not independently prove full official event coverage.",
                  "Complete event coverage requires reconciliation against official fixtures, beyond file-level counts.",
              ]}
    package = Path(__file__).resolve().parents[1]
    digest = hashlib.sha256()
    for module in sorted(package.rglob("*.py")):
        digest.update(module.relative_to(package).as_posix().encode() + b"\0" + module.read_bytes())
    report["package_source_sha256"] = digest.hexdigest()
    return candidates, series, report


def write_expanded(candidates, series, report, output_dir, report_dir):
    output_dir, report_dir = Path(output_dir), Path(report_dir)
    targets = [output_dir / "candidate_games.csv", output_dir / "candidate_series.csv", output_dir / "audit_manifest.json",
               report_dir / "expanded_audit.json", report_dir / "expanded_audit.md"]
    if {Path(p).resolve() for p in report["forecast_scope"]["sources"].values()} & {p.resolve() for p in targets}:
        raise ValueError("Audit outputs must not overwrite raw sources.")
    output_dir.mkdir(parents=True, exist_ok=True)
    hashes = {}
    for name, rows in (("candidate_games", candidates), ("candidate_series", series)):
        if not rows:
            continue
        fields = sorted({key for row in rows for key in row})
        target = output_dir / (name + ".csv")
        with target.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)
        hashes[target.name] = hashlib.sha256(target.read_bytes()).hexdigest()
    report["output_sha256"] = hashes
    text = render_expanded(report)
    report_dir.mkdir(parents=True, exist_ok=True)
    for target in (output_dir / "audit_manifest.json", report_dir / "expanded_audit.json"):
        target.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (report_dir / "expanded_audit.md").write_text(text, encoding="utf-8")
    return text


def reconcile_previous_pool(candidates, previous_dir):
    """Compare inspected model fields against the checksummed old clean snapshot."""
    previous_dir = Path(previous_dir)
    manifest = json.loads((previous_dir / "manifest.json").read_text(encoding="utf-8"))
    target = previous_dir / "games.csv"
    raw = target.read_bytes()
    if hashlib.sha256(raw).hexdigest() != manifest["output_sha256"]["games.csv"]:
        raise ValueError("Original canonical game checksum mismatch; preserve and inspect the snapshot.")
    import io
    before = {r["game_id"]: r for r in csv.DictReader(io.StringIO(raw.decode("utf-8-sig")))}
    after = {r["game_id"]: r for r in candidates if r["played_year"] == 2026 and r["scope_review"] == "existing_approved_scope"}
    fields = ("started_at_utc", "blue_team_id", "red_team_id", "blue_won", "source_season")
    differences = []
    for key in sorted(before.keys() & after.keys()):
        changed = [field for field in fields if str(before[key][field]) != str(after[key][field])]
        if changed:
            differences.append({"game_id": key, "changed_fields": changed})
    return {"old_source_sha256": manifest["source"]["sha256"], "old_games": len(before),
            "current_existing_scope_games": len(after), "shared_game_ids": len(before.keys() & after.keys()),
            "missing_old_game_ids": sorted(before.keys() - after.keys()),
            "new_existing_scope_game_ids": sorted(after.keys() - before.keys()),
            "changed_inspected_game_fields": differences, "fields_compared": list(fields),
            "limitation": "Comparison covers these canonical game fields only, not full raw rows or all statistics. "
                          "The previous raw bytes were replaced by the user and cannot be reconstructed from a checksum."}


def render_expanded(report):
    lines = ["# Expanded data scope audit", "", "Status: " + report["status"], "", "**Not training-ready.** Candidate inventory only; earlier canonical tables are preserved.", "",
             f"Forecast freeze: {report['forecast_scope']['forecast_freeze_utc']}. " + report["forecast_scope"]["freeze_basis"], "",
             f"Candidates: {report['candidate_games']} games / {report['candidate_series']} series groups. "
             f"Play-Ins: {report['play_in_games']} games / {report['play_in_series_groups']} groups.", "",
             "| Year / event / stage | Candidate games |", "|---|---:|"]
    lines += [f"| {key} | {value} |" for key, value in sorted(report["counts_by_event"].items())]
    lines += ["", "## Blocking findings", ""] + ["- " + e for e in report["errors"] or ["None in implemented structural checks."]]
    lines += ["", "## Open reviews", ""] + ["- " + e for e in report["open_reviews"]]
    lines += ["", "## Limitations", ""] + ["- " + e for e in report["limitations"]]
    return "\n".join(lines) + "\n"
