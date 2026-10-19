"""Read-only audit: candidate counts are not a cleaned training dataset."""

import csv
import hashlib
import math
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from worlds_predictor.ingestion.csv_source import SourceError, file_metadata, read_csv


ALIASES = {
    "game_id": ("gameid",), "league": ("league",), "year": ("year",),
    "date": ("date",), "position": ("position",), "side": ("side",),
    "result": ("result",), "team_name": ("teamname", "team"),
    "team_id": ("teamid",), "player_id": ("playerid",),
    "player_name": ("playername", "player"), "patch": ("patch", "patchno"),
    "split": ("split",), "playoffs": ("playoffs",), "game_number": ("game",),
    "series_id": ("seriesid", "series_id", "matchid"),
    "completeness": ("datacompleteness",),
    "gold_diff_15": ("golddiffat15", "gdat15"),
    "xp_diff_15": ("xpdiffat15", "xpdat15"),
    "kills": ("kills", "k"), "duration": ("gamelength",),
    "champion": ("champion",),
}
REQUIRED = ("game_id", "league", "year", "date", "position", "side", "result", "team_name")
MISSING = {"", "na", "n/a", "nan", "null", "none"}
ROLES = {"top", "jng", "mid", "bot", "sup"}
ROLE_ALIASES = {"jungle": "jng", "adc": "bot", "support": "sup"}


def missing(value):
    return value is None or str(value).strip().casefold() in MISSING


def number(value):
    if missing(value):
        return None
    try:
        value = float(value)
        return value if math.isfinite(value) else None
    except (TypeError, ValueError):
        return None


def parse_date(value, assumed_timezone):
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        naive = parsed.tzinfo is None
        if naive:
            tz = timezone.utc if assumed_timezone == "UTC" else ZoneInfo(assumed_timezone)
            parsed = parsed.replace(tzinfo=tz)
        return parsed.astimezone(timezone.utc), naive
    except (ValueError, TypeError, AttributeError):
        return None, False


def matching_season_exception(rows, canonical, date, config):
    """Reviewed exceptions preserve source year and never bypass date/cutoff rules."""
    matches = []
    for rule in config.get("season_exceptions", []):
        start, _ = parse_date(rule["start_utc"], "UTC")
        end, _ = parse_date(rule["end_utc_exclusive"], "UTC")
        if start is None or end is None or start >= end:
            raise ValueError(f"Invalid season-exception dates: {rule['id']}")
        if (canonical == rule["league"] and start <= date < end
                and all(number(r["year"]) == rule["source_season"]
                        and r["split"] == rule["split"] and r["playoffs"] == rule["playoffs"] for r in rows)):
            matches.append(rule["id"])
    if len(matches) > 1:
        raise ValueError("Overlapping season exceptions match the same game.")
    return matches[0] if matches else None


def event_stage(canonical, date, exception, config):
    if exception:
        return "promotion"
    info = config["leagues"][canonical]
    windows = info.get("stage_windows")
    if windows is None:
        return "regional_competition" if info["region"] else "main_event"
    stages = []
    for rule in windows:
        start, _ = parse_date(rule["start_utc"], "UTC")
        end, _ = parse_date(rule["end_utc_exclusive"], "UTC")
        if start is None or end is None or start >= end:
            raise ValueError(f"Invalid stage dates for {canonical}")
        if start <= date < end:
            stages.append(rule["stage"])
    if len(stages) > 1:
        raise ValueError(f"Overlapping stage windows for {canonical}")
    return stages[0] if stages else "unclassified"


def audit_csv(path: Path, config: dict, source_url=None, retrieved_at=None, *, include_game_keys=False) -> dict:
    report = {
        "status": "blocked", "source": file_metadata(path, source_url, retrieved_at),
        "config": config, "errors": [], "warnings": [],
        "training_readiness": "not_established",
    }
    cutoff, _ = parse_date(config["cutoff_utc"], "UTC")
    if cutoff is None or cutoff.year != config["season"]:
        raise ValueError("Cutoff must be a valid date in the configured season.")
    if config["duration_unit"] not in {"seconds", "minutes"}:
        raise ValueError("duration_unit must be seconds or minutes.")
    league_map = {}
    for canonical, info in config["leagues"].items():
        for alias in info["aliases"]:
            previous = league_map.setdefault(alias.casefold(), canonical)
            if previous != canonical:
                raise ValueError(f"Ambiguous league alias: {alias}")
    worlds = {x.casefold() for x in config["worlds_aliases"]}
    groups = defaultdict(list)
    row_counts, issues = Counter(), Counter()
    duplicates = Counter()
    seen = set()
    malformed_lines = []
    try:
        with read_csv(path) as (fields, reader):
            mapped = {key: next((a for a in options if a in fields), None) for key, options in ALIASES.items()}
            report["schema"] = {"columns": fields, "mapping": mapped}
            absent = [key for key in REQUIRED if not mapped[key]]
            if absent:
                raise SourceError(f"Missing required columns: {', '.join(absent)}. No schema is inferred silently.")
            for line, raw in enumerate(reader, 2):
                row_counts["total"] += 1
                if None in raw or any(value is None for value in raw.values()):
                    issues["malformed_rows"] += 1
                    if len(malformed_lines) < 10:
                        malformed_lines.append(line)
                    # Count a malformed row against its game when its key is readable.
                    key = (raw.get(mapped["league"], ""), raw.get(mapped["game_id"], ""))
                    if all(key):
                        duplicates[key] += 1
                    continue
                row = {key: raw.get(column, "").strip() if column else "" for key, column in mapped.items()}
                row["line"] = line
                digest = hashlib.sha256(repr(tuple(raw.values())).encode()).digest()
                key = (row["league"], row["game_id"])
                if digest in seen:
                    issues["exact_duplicate_rows"] += 1
                    duplicates[key] += 1
                seen.add(digest)
                if missing(row["league"]) or missing(row["game_id"]):
                    issues["rows_missing_game_key"] += 1
                    continue
                groups[key].append(row)
    except (SourceError, UnicodeError, csv.Error) as error:
        report["errors"].append(str(error))
        return report

    report["rows"] = dict(row_counts)
    report["row_issues"] = dict(issues)
    report["malformed_line_examples"] = malformed_lines
    report["game_key"] = ["league", "gameid"]
    report["source_games"] = len(groups)
    excluded, failures, warnings = Counter(), Counter(), Counter()
    coverage = {name: {"observed_games": 0, "candidate_games": 0, "structurally_valid_games": 0,
                       "first_candidate_date": None, "last_candidate_date": None}
                for name in config["leagues"]}
    labels, completeness, patches, splits = Counter(), Counter(), Counter(), Counter()
    feature_counts = {f: Counter() for f in ("gold_diff_15", "xp_diff_15", "kills", "duration")}
    feature_leagues = defaultdict(lambda: defaultdict(Counter))
    id_names, name_ids = defaultdict(set), defaultdict(set)
    game_id_leagues = defaultdict(set)
    team_regions = defaultdict(set)
    lineups = defaultdict(list)
    valid_games = []
    problem_examples = []
    inventory = {}
    missing_feature_games = Counter()
    missing_gold_details = Counter()
    short_game_examples = []
    season_exceptions_included = Counter()
    stage_counts = Counter()
    for (league, game_id), rows in groups.items():
        game_id_leagues[game_id].add(league)
        labels[league] += 1
        first = rows[0]
        inventory_key = (league, first["year"], first["split"], first["playoffs"])
        item = inventory.setdefault(inventory_key, {"games": 0, "first_date": None, "last_date": None})
        item["games"] += 1
        source_date, _ = parse_date(first["date"], config["naive_timestamp_timezone"])
        if source_date:
            stamp = source_date.isoformat()
            item["first_date"] = min(item["first_date"] or stamp, stamp)
            item["last_date"] = max(item["last_date"] or stamp, stamp)
        canonical = league_map.get(league.casefold())
        if canonical:
            coverage[canonical]["observed_games"] += 1
        # Excluded outcomes and game statistics are not used for feature summaries.
        if league.casefold() in worlds or "world" in league.casefold():
            excluded["worlds"] += 1
            continue
        if canonical is None:
            excluded["unreviewed_competition"] += 1
            continue
        seasons = {number(r["year"]) for r in rows}
        dates = [parse_date(r["date"], config["naive_timestamp_timezone"])[0] for r in rows]
        if len(seasons) != 1 or None in seasons:
            excluded["wrong_or_inconsistent_season"] += 1
            continue
        if None in dates or len(set(dates)) != 1:
            excluded["invalid_or_inconsistent_date"] += 1
            continue
        date = dates[0]
        if date.year != config["season"]:
            excluded["date_outside_season"] += 1
            continue
        if date >= cutoff:
            excluded["at_or_after_cutoff"] += 1
            continue
        exception = None
        if seasons != {config["season"]}:
            exception = matching_season_exception(rows, canonical, date, config)
            if exception is None:
                excluded["wrong_or_inconsistent_season"] += 1
                continue
        entry = coverage[canonical]
        entry["candidate_games"] += 1
        stamp = date.isoformat()
        entry["first_candidate_date"] = min(entry["first_candidate_date"] or stamp, stamp)
        entry["last_candidate_date"] = max(entry["last_candidate_date"] or stamp, stamp)
        reasons = []
        if duplicates[(league, game_id)]:
            reasons.append("duplicate_or_malformed_rows")
        teams = [r for r in rows if r["position"].casefold() == "team"]
        if len(teams) != 2:
            reasons.append("team_row_count_not_two")
        elif {r["side"].casefold() for r in teams} != {"blue", "red"}:
            reasons.append("invalid_sides")
        else:
            if sorted(number(r["result"]) if number(r["result"]) is not None else -1 for r in teams) != [0, 1]:
                reasons.append("invalid_or_noncomplementary_results")
            identities = [r["team_id"] if not missing(r["team_id"]) else r["team_name"] for r in teams]
            if any(missing(x) for x in identities) or identities[0] == identities[1]:
                reasons.append("missing_or_identical_teams")
            if any(missing(r["team_name"]) for r in teams):
                reasons.append("missing_team_names")
        if len({r["patch"] for r in rows if not missing(r["patch"])}) > 1:
            reasons.append("inconsistent_patch")
        if len({r["split"] for r in rows}) > 1 or len({r["game_number"] for r in rows}) > 1:
            reasons.append("inconsistent_game_metadata")
        if reasons:
            failures.update(reasons)
            if len(problem_examples) < 20:
                problem_examples.append({"league": league, "game_id": game_id, "issues": reasons})
            continue
        entry["structurally_valid_games"] += 1
        valid_games.append((canonical, date, teams))
        stage = event_stage(canonical, date, exception, config)
        stage_counts[(canonical, stage, int(next(iter(seasons))))] += 1
        if exception:
            season_exceptions_included[exception] += 1
        if stage == "unclassified":
            warnings["games_without_reviewed_event_stage"] += 1
        for feature in feature_counts:
            if any(number(r[feature]) is None for r in teams):
                missing_feature_games[feature] += 1
        if any(number(r["gold_diff_15"]) is None for r in teams):
            duration = number(teams[0]["duration"])
            missing_gold_details[(canonical, teams[0]["completeness"] or "missing",
                                  "under_900_source_units" if duration is not None and duration < 900
                                  else "900_or_more_source_units_or_unknown")] += 1
            if duration is not None and duration < 900 and len(short_game_examples) < 10:
                short_game_examples.append({"league": canonical, "game_id": game_id, "duration_source_units": duration})
        patches.update({r["patch"] or "missing" for r in teams})
        splits[(canonical, teams[0]["split"], teams[0]["playoffs"])] += 1
        if any(parse_date(r["date"], config["naive_timestamp_timezone"])[1] for r in teams):
            warnings["games_with_assumed_timestamp_timezone"] += 1
        if not all(r["series_id"] for r in teams):
            warnings["games_without_explicit_series_id"] += 1
        for r in teams:
            completeness[r["completeness"] or "missing"] += 1
            team = r["team_id"] if not missing(r["team_id"]) else "name:" + r["team_name"]
            if missing(r["team_id"]):
                warnings["team_rows_without_stable_id"] += 1
            id_names[team].add(r["team_name"])
            name_ids[r["team_name"].casefold()].add(team)
            region = config["leagues"][canonical]["region"]
            if region:
                team_regions[team].add(region)
            duration = number(r["duration"])
            if duration is None or duration <= 0:
                warnings["team_rows_without_positive_duration"] += 1
            elif config["duration_unit_verified"]:
                multiplier = 1 if config["duration_unit"] == "seconds" else 60
                if date + timedelta(seconds=duration * multiplier) >= cutoff:
                    warnings["team_rows_not_finished_by_cutoff"] += 1
            for feature in feature_counts:
                state = "missing" if missing(r[feature]) else "numeric" if number(r[feature]) is not None else "invalid"
                feature_counts[feature][state] += 1
                feature_leagues[canonical][feature][state] += 1
            players = [p for p in rows if p["side"].casefold() == r["side"].casefold() and p["position"].casefold() != "team"]
            roles = [ROLE_ALIASES.get(p["position"].casefold(), p["position"].casefold()) for p in players]
            player_keys = [p["player_id"] if not missing(p["player_id"]) else
                           "name:" + p["player_name"] if not missing(p["player_name"]) else ""
                           for p in players]
            valid_lineup = (len(players) == 5 and set(roles) == ROLES and len(set(player_keys)) == 5
                            and all(player_keys)
                            and all(p["team_name"] == r["team_name"] for p in players))
            if not valid_lineup:
                warnings["team_games_without_complete_lineup"] += 1
            else:
                if any(missing(p["player_id"]) for p in players):
                    warnings["lineups_using_player_name_fallback"] += 1
                lineups[team].append((date, game_id, frozenset(player_keys)))

    transitions = []
    for team, records in sorted(lineups.items()):
        previous = None
        for date, game_id, players in sorted(records, key=lambda x: (x[0], x[1])):
            if previous and date == previous[0]:
                warnings["lineup_records_with_ambiguous_time_order"] += 1
            elif previous and previous[2] != players:
                transitions.append({"team_id": team, "date": date.isoformat(), "game_id": game_id,
                                    "players_retained": len(players & previous[2])})
            previous = (date, game_id, players)
    connections = Counter()
    same_region_international = Counter()
    unresolved = 0
    for canonical, _, teams in valid_games:
        if config["leagues"][canonical]["region"] is not None:
            continue
        regions = []
        for r in teams:
            key = r["team_id"] if not missing(r["team_id"]) else "name:" + r["team_name"]
            region_set = team_regions[key]
            regions.append(next(iter(region_set)) if len(region_set) == 1 else None)
        if None in regions:
            unresolved += 1
        elif regions[0] == regions[1]:
            same_region_international[regions[0]] += 1
        else:
            connections[" / ".join(sorted(regions))] += 1

    candidates = sum(c["candidate_games"] for c in coverage.values())
    valid = len(valid_games)
    report.update({
        "status": "audited", "exclusions": dict(excluded),
        "observed_league_labels": dict(sorted(labels.items())), "coverage": coverage,
        "candidate_games": candidates, "structurally_valid_games": valid,
        "season_exceptions_included": dict(season_exceptions_included),
        "event_stage_game_counts": [{"league": k[0], "stage": k[1], "source_season": k[2], "games": v}
                                    for k, v in sorted(stage_counts.items())],
        "source_competition_inventory": [dict(league=k[0], year=k[1], split=k[2], playoffs=k[3], **v)
                                         for k, v in sorted(inventory.items())],
        "games_without_both_numeric_team_values": dict(missing_feature_games),
        "missing_gold_15_game_breakdown": [{"league": k[0], "completeness": k[1], "duration_band": k[2], "games": v}
                                           for k, v in sorted(missing_gold_details.items())],
        "short_games_missing_gold_15_examples": short_game_examples,
        "quarantined_candidate_games": candidates - valid,
        "validation_failures": dict(failures), "problem_examples": problem_examples,
        "quality_warnings": dict(warnings),
        "team_row_feature_coverage": {k: dict(v) for k, v in feature_counts.items()},
        "feature_coverage_by_league": {k: {f: dict(v) for f, v in values.items()} for k, values in feature_leagues.items()},
        "team_row_completeness_labels": dict(completeness), "patch_team_row_counts": dict(patches),
        "split_game_counts": [{"league": k[0], "split": k[1], "playoffs": k[2], "games": v} for k, v in sorted(splits.items())],
        "team_aliases": {k: sorted(v) for k, v in id_names.items() if len(v) > 1},
        "distinct_team_ids_or_name_keys": len(id_names),
        "team_names_by_id": {k: sorted(v) for k, v in sorted(id_names.items())},
        "ambiguous_team_names": {k: sorted(v) for k, v in name_ids.items() if len(v) > 1},
        "observed_lineup_changes": transitions,
        "cross_region_game_counts": dict(connections), "international_games_with_unresolved_regions": unresolved,
        "same_region_international_game_counts": dict(same_region_international),
        "game_ids_reused_across_leagues": sum(len(v) > 1 for v in game_id_leagues.values()),
    })
    if include_game_keys:
        report["accepted_game_keys"] = [
            {"league": teams[0]["league"], "source_game_id": teams[0]["game_id"]}
            for _, _, teams in valid_games
        ]
    blockers = ["Coverage must be reconciled with an independent competition schedule.",
                "Publication times and pre-cutoff availability have not been verified.",
                "Series identifiers and historical prediction timing require review."]
    if not config["timestamp_timezone_verified"]:
        blockers.append("Source timestamp timezone has not been verified.")
    if not config["duration_unit_verified"]:
        blockers.append("Game-duration units have not been verified; completion before the cutoff is unconfirmed.")
    if not valid:
        blockers.append("No structurally valid in-scope games found.")
    if issues:
        blockers.append("Source row issues need review; no rows were silently deduplicated or repaired.")
    report["review_required"] = blockers
    report["warnings"] = [
        "Candidate and structurally valid counts are audit findings, not permission to train.",
        "Observed lineup changes may reflect substitutions, aliases, or source errors. Incomplete lineups are not interpolated.",
        "International region mapping is retrospective for this audit only; it must not be copied into historical features.",
    ]
    return report
