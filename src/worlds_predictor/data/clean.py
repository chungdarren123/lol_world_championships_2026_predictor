"""Build canonical tables from exactly the audited pool, with lineage and uncertainty."""

import csv
import hashlib
import json
import platform
from collections import Counter, defaultdict
from pathlib import Path

from worlds_predictor.ingestion.csv_source import file_metadata, read_csv
from .audit import (ROLE_ALIASES, ROLES, audit_csv, event_stage,
                    matching_season_exception, missing, number, parse_date)
from .identities import IdentityResolver
from .series import resolve_series, stable_id
from .validation import validate_tables


METRICS = {
    "kills": ("kills", "k"), "deaths": ("deaths", "d"), "assists": ("assists", "a"),
    "gold_diff_15": ("golddiffat15", "gdat15"), "xp_diff_15": ("xpdiffat15", "xpdat15"),
    "gold_at_15": ("goldat15",), "xp_at_15": ("xpat15",),
    "dragons": ("dragons", "teamdragkills"), "barons": ("barons", "teambaronkills"),
    "towers": ("towers", "teamtowerkills"), "duration_source_units": ("gamelength",),
}
GAME_FIELDS = ["game_id", "source_game_id", "source_league", "league", "source_season", "played_year",
               "season_exception", "stage", "split", "source_playoffs", "started_at_utc", "source_date",
               "timestamp_timezone_assumed", "patch", "source_url", "source_series_id", "game_number",
               "blue_team_id", "red_team_id", "blue_won", "winner_team_id", "series_id", "series_method", "series_status"]
TEAM_GAME_FIELDS = ["game_id", "team_id", "source_team_id", "source_team_name", "identity_method",
                    "opponent_team_id", "side", "won", "region", "region_status", "region_evidence_observed_at_utc",
                    "region_evidence_league", "region_evidence_source_game_id", "lineup_id", "lineup_complete",
                    "lineup_player_ids", "source_completeness", "observed_first_pick"] + ["observed_" + k for k in METRICS]
PLAYER_FIELDS = ["game_id", "team_id", "source_team_id", "player_id", "source_player_id", "player_name", "role", "side",
                 "won", "lineup_id", "observed_champion"] + ["observed_" + k for k in METRICS]
SERIES_FIELDS = ["series_id", "league", "source_season", "stage", "split", "team_a_id", "team_b_id",
                 "first_observed_game_at_utc", "last_observed_game_at_utc", "observed_games", "observed_wins_a", "observed_wins_b",
                 "best_of", "source_observations_complete", "official_winner_team_id", "resolution_method", "resolution_status",
                 "source_reference", "source_reference_method", "evidence_url", "issues"]
TABLE_FIELDS = {
    "games": GAME_FIELDS, "team_games": TEAM_GAME_FIELDS, "player_games": PLAYER_FIELDS,
    "series": SERIES_FIELDS,
    "teams": ["team_id", "display_name", "observed_names", "first_game_at_utc", "last_game_at_utc", "games"],
    "team_aliases": ["source_team_id", "source_name", "source_league", "canonical_team_id", "identity_method",
                     "first_observed_at_utc", "last_observed_at_utc"],
    "team_regions": ["team_id", "region", "observed_at_utc", "source_league", "source_game_id", "source_url"],
    "players": ["player_id", "observed_names", "first_game_at_utc", "last_game_at_utc", "games"],
}


def source_text(row, *fields):
    for field in fields:
        if field in row:
            return "" if missing(row[field]) else row[field].strip()
    return ""


def observed_stats(row):
    return {"observed_" + key: number(source_text(row, *aliases)) for key, aliases in METRICS.items()}


def read_metadata_regions(path, accepted_keys, config, resolver):
    """Read only team membership metadata from supplemental leagues, never performance."""
    region_leagues = {alias.casefold(): (info["region"], "") for info in config["leagues"].values()
                      if info["region"] for alias in info["aliases"]}
    for league, info in resolver.config.get("additional_region_metadata_leagues", {}).items():
        region_leagues[league.casefold()] = (info["region"], info["source_url"])
    cutoff, _ = parse_date(config["cutoff_utc"], "UTC")
    with read_csv(path) as (_, reader):
        for raw in reader:
            if None in raw or source_text(raw, "position").casefold() != "team":
                continue
            league = source_text(raw, "league")
            if league.casefold() not in region_leagues:
                continue
            key = (league, source_text(raw, "gameid"))
            source_year = number(source_text(raw, "year"))
            if source_year != config["season"] and key not in accepted_keys:
                continue
            date, _ = parse_date(source_text(raw, "date"), config["naive_timestamp_timezone"])
            if date is None or date.year != config["season"] or date >= cutoff:
                continue
            team, _, _ = resolver.team(source_text(raw, "teamid"), source_text(raw, "teamname", "team"), league, date)
            region, evidence_url = region_leagues[league.casefold()]
            resolver.observe_region(team, region, date, league, key[1], evidence_url)


def build_tables(path: Path, config: dict, identity_config: dict, source_url=None, retrieved_at=None):
    audit = audit_csv(path, config, source_url, retrieved_at, include_game_keys=True)
    if audit["status"] != "audited":
        raise ValueError("Source audit is blocked: " + "; ".join(audit["errors"]))
    keys = {(r["league"], r["source_game_id"]) for r in audit.pop("accepted_game_keys")}
    if not keys:
        raise ValueError("No structurally valid games in the audited pool.")
    resolver = IdentityResolver(identity_config)
    read_metadata_regions(path, keys, config, resolver)
    grouped = defaultdict(list)
    with read_csv(path) as (_, reader):
        for row in reader:
            key = (source_text(row, "league"), source_text(row, "gameid"))
            if key in keys:
                grouped[key].append(row)
    if set(grouped) != keys:
        raise ValueError("Source records changed between audit and cleaning.")
    league_map = {alias.casefold(): name for name, info in config["leagues"].items() for alias in info["aliases"]}
    games, team_games, player_games = [], [], []
    aliases, teams, players = {}, {}, {}
    warnings = Counter()
    for (source_league, source_game_id), rows in sorted(grouped.items()):
        team_rows = {source_text(r, "side").casefold(): r for r in rows if source_text(r, "position").casefold() == "team"}
        if set(team_rows) != {"blue", "red"}:
            raise ValueError(f"Source team rows changed after audit: {source_game_id}")
        first = team_rows["blue"]
        date, naive = parse_date(source_text(first, "date"), config["naive_timestamp_timezone"])
        league = league_map[source_league.casefold()]
        season = int(number(first["year"]))
        # Reuse exactly the approved exception conditions from the auditor.
        projected = [{"year": source_text(r, "year"), "split": source_text(r, "split"), "playoffs": source_text(r, "playoffs")} for r in rows]
        exception = matching_season_exception(projected, league, date, config) if season != config["season"] else None
        stage = event_stage(league, date, exception, config)
        game_id = stable_id("game", source_league, source_game_id)
        identities = {side: resolver.team(source_text(r, "teamid"), source_text(r, "teamname", "team"), source_league, date)
                      for side, r in team_rows.items()}
        if identities["blue"][0] == identities["red"][0]:
            raise ValueError("Alias resolution collapsed opponents into the same team.")
        urls = {source_text(r, "url") for r in rows if source_text(r, "url")}
        series_refs = {source_text(r, "seriesid", "series_id", "matchid") for r in rows
                       if source_text(r, "seriesid", "series_id", "matchid")}
        if len(urls) > 1 or len(series_refs) > 1:
            raise ValueError(f"Inconsistent source URLs or series IDs: {source_game_id}")
        game_number = number(source_text(first, "game"))
        game_number = int(game_number) if game_number is not None and game_number.is_integer() and game_number >= 1 else None
        blue_won = int(number(first["result"]))
        game = {
            "game_id": game_id, "source_game_id": source_game_id, "source_league": source_league, "league": league,
            "source_season": season, "played_year": date.year, "season_exception": exception or "", "stage": stage,
            "split": source_text(first, "split"), "source_playoffs": source_text(first, "playoffs"),
            "started_at_utc": date.isoformat(), "source_date": first["date"],
            "timestamp_timezone_assumed": naive and not config["timestamp_timezone_verified"],
            "patch": source_text(first, "patch", "patchno"), "source_url": next(iter(urls), ""),
            "source_series_id": next(iter(series_refs), ""), "game_number": game_number,
            "blue_team_id": identities["blue"][0], "red_team_id": identities["red"][0],
            "blue_won": blue_won, "winner_team_id": identities["blue" if blue_won else "red"][0],
        }
        games.append(game)
        game_player_keys = []
        for side in ("blue", "red"):
            raw = team_rows[side]
            team_id, display_name, identity_method = identities[side]
            raw_team_id = source_text(raw, "teamid")
            raw_name = source_text(raw, "teamname", "team")
            observed_at = date.isoformat()
            info = teams.setdefault(team_id, {"team_id": team_id, "display_name": display_name, "observed_names": set(),
                                              "first_game_at_utc": observed_at, "last_game_at_utc": observed_at, "games": 0})
            info["observed_names"].add(raw_name)
            info["first_game_at_utc"] = min(info["first_game_at_utc"], observed_at)
            info["last_game_at_utc"] = max(info["last_game_at_utc"], observed_at)
            info["games"] += 1
            alias_key = (raw_team_id, raw_name, source_league, team_id)
            alias = aliases.setdefault(alias_key, {"source_team_id": raw_team_id, "source_name": raw_name,
                "source_league": source_league, "canonical_team_id": team_id, "identity_method": identity_method,
                "first_observed_at_utc": observed_at, "last_observed_at_utc": observed_at})
            alias["first_observed_at_utc"] = min(alias["first_observed_at_utc"], observed_at)
            alias["last_observed_at_utc"] = max(alias["last_observed_at_utc"], observed_at)
            members = [r for r in rows if source_text(r, "position").casefold() != "team"
                       and source_text(r, "side").casefold() == side]
            role_members = []
            for member in members:
                role = source_text(member, "position").casefold()
                role = ROLE_ALIASES.get(role, role)
                source_player = source_text(member, "playerid")
                player_id = source_player or "name:" + source_text(member, "playername", "player")
                member_team, _, _ = resolver.team(source_text(member, "teamid"), source_text(member, "teamname", "team"), source_league, date)
                if member_team != team_id or player_id == "name:":
                    raise ValueError(f"Unresolved player/team identity: {source_game_id}")
                role_members.append((role, player_id, source_player, member))
                game_player_keys.append(player_id)
            complete = (len(role_members) == 5 and {r[0] for r in role_members} == ROLES
                        and len({r[1] for r in role_members}) == 5)
            if len({r[1] for r in role_members}) != len(role_members):
                raise ValueError(f"Duplicate player in one team/game: {source_game_id}")
            if not complete:
                warnings["incomplete_lineups"] += 1
            lineup_id = stable_id("lineup", team_id, sorted((r[0], r[1]) for r in role_members)) if complete else ""
            region, region_status, evidence_at, evidence_league, evidence_game = resolver.region_at(team_id, date)
            if not region:
                warnings["team_games_" + region_status + "_region"] += 1
            team_games.append({
                "game_id": game_id, "team_id": team_id, "source_team_id": raw_team_id, "source_team_name": raw_name,
                "identity_method": identity_method, "opponent_team_id": identities["red" if side == "blue" else "blue"][0],
                "side": side, "won": int(number(raw["result"])), "region": region, "region_status": region_status,
                "region_evidence_observed_at_utc": evidence_at, "region_evidence_league": evidence_league,
                "region_evidence_source_game_id": evidence_game, "lineup_id": lineup_id, "lineup_complete": complete,
                "lineup_player_ids": json.dumps([r[1] for r in sorted(role_members)], separators=(",", ":")),
                "source_completeness": source_text(raw, "datacompleteness"),
                "observed_first_pick": number(source_text(raw, "firstPick")), **observed_stats(raw),
            })
            for role, player_id, source_player, member in role_members:
                name = source_text(member, "playername", "player")
                player_info = players.setdefault(player_id, {"player_id": player_id, "observed_names": set(),
                    "first_game_at_utc": observed_at, "last_game_at_utc": observed_at, "games": 0})
                player_info["observed_names"].add(name)
                player_info["first_game_at_utc"] = min(player_info["first_game_at_utc"], observed_at)
                player_info["last_game_at_utc"] = max(player_info["last_game_at_utc"], observed_at)
                player_info["games"] += 1
                player_games.append({"game_id": game_id, "team_id": team_id, "source_team_id": source_text(member, "teamid"),
                    "player_id": player_id, "source_player_id": source_player, "player_name": name, "role": role,
                    "side": side, "won": int(number(member["result"])), "lineup_id": lineup_id,
                    "observed_champion": source_text(member, "champion"), **observed_stats(member)})
        if len(game_player_keys) != len(set(game_player_keys)):
            raise ValueError(f"A player appears more than once in the same game: {source_game_id}")
    games.sort(key=lambda g: (g["started_at_utc"], g["game_id"]))
    series, series_issues = resolve_series(games, identity_config["series"])
    for info in list(teams.values()) + list(players.values()):
        info["observed_names"] = json.dumps(sorted(info["observed_names"]), ensure_ascii=False)
    tables = {
        "games": games, "team_games": sorted(team_games, key=lambda r: (r["game_id"], r["side"])),
        "player_games": sorted(player_games, key=lambda r: (r["game_id"], r["side"], r["role"])),
        "series": series, "teams": [teams[k] for k in sorted(teams)],
        "players": [players[k] for k in sorted(players)],
        "team_aliases": [aliases[k] for k in sorted(aliases)], "team_regions": resolver.region_table(teams),
    }
    if len(games) != audit["structurally_valid_games"] or len({g["game_id"] for g in games}) != len(games):
        raise ValueError("Game count/key reconciliation failed.")
    if file_metadata(path, source_url, retrieved_at)["sha256"] != audit["source"]["sha256"]:
        raise ValueError("Raw source changed during the build; no output was exported.")
    validation = validate_tables(tables, config)
    summary = {
        "status": "built_with_documented_assumptions", "training_readiness": "not_established",
        "source": audit["source"], "selection_config": config, "identity_config": identity_config,
        "table_counts": {name: len(records) for name, records in tables.items()},
        "series_status_counts": dict(Counter(r["resolution_status"] for r in series)),
        "series_method_counts": dict(Counter(r["resolution_method"] for r in series)),
        "series_issues": series_issues, "quality_warnings": dict(warnings),
        "reviewed_alias_team_games": sum(r["identity_method"] == "reviewed_alias" for r in team_games),
        "games_missing_gold_15": audit["games_without_both_numeric_team_values"].get("gold_diff_15", 0),
        "source_team_ids": len({r["source_team_id"] for r in team_games}),
        "relational_validation": validation,
        "runtime_python_version": platform.python_version(),
        "selection_config_sha256": hashlib.sha256(json.dumps(config, sort_keys=True).encode()).hexdigest(),
        "identity_config_sha256": hashlib.sha256(json.dumps(identity_config, sort_keys=True).encode()).hexdigest(),
        "limitations": [
            "Naive source timestamps and duration units retain the unverified assumptions in the selection config.",
            "Observed membership time is not a verified publication timestamp; region evidence is never taken from later games.",
            "Team/player summaries are descriptive across the full pool, not historical model features.",
            "Sequence-inferred series are provisional. Best-of, official winner, and completeness are not guessed.",
            "Observed statistics and champion choices belong to the finished game; pre-draft features must use preceding games only.",
            "No models were fitted. Missing values and lineup changes are retained.",
        ],
    }
    package = Path(__file__).resolve().parents[1]
    digest = hashlib.sha256()
    for module in sorted(package.rglob("*.py")):
        digest.update(module.relative_to(package).as_posix().encode())
        digest.update(b"\0")
        digest.update(module.read_bytes())
    summary["package_source_sha256"] = digest.hexdigest()
    return tables, summary


def export_tables(tables, summary, output_dir: Path):
    """Only fixed, generated table filenames are written; raw input is never an output."""
    output_dir.mkdir(parents=True, exist_ok=True)
    checksums = {}
    for name, records in tables.items():
        target = output_dir / (name + ".csv")
        with target.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=TABLE_FIELDS[name], extrasaction="raise")
            writer.writeheader()
            writer.writerows(records)
        checksums[target.name] = hashlib.sha256(target.read_bytes()).hexdigest()
    manifest = dict(summary, output_sha256=checksums, schemas=TABLE_FIELDS)
    (output_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return manifest
