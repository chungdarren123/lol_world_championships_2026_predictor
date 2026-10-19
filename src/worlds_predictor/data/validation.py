"""Check relational integrity independently of source parsing and series inference."""

from collections import defaultdict

from .audit import ROLES, parse_date


def unique(rows, fields, label):
    keys = [tuple(row[field] for field in fields) for row in rows]
    if len(keys) != len(set(keys)):
        raise ValueError(f"Duplicate key in {label}: {fields}")


def validate_tables(tables, config):
    unique(tables["games"], ["game_id"], "games")
    unique(tables["games"], ["source_league", "source_game_id"], "source game keys")
    unique(tables["team_games"], ["game_id", "team_id"], "team_games")
    unique(tables["player_games"], ["game_id", "player_id"], "player_games")
    unique(tables["teams"], ["team_id"], "teams")
    unique(tables["players"], ["player_id"], "players")
    unique(tables["series"], ["series_id"], "series")
    games = {g["game_id"]: g for g in tables["games"]}
    teams = {t["team_id"] for t in tables["teams"]}
    players = {p["player_id"] for p in tables["players"]}
    series = {s["series_id"]: s for s in tables["series"]}
    cutoff, _ = parse_date(config["cutoff_utc"], "UTC")
    team_rows, player_rows, series_games = defaultdict(list), defaultdict(list), defaultdict(list)
    team_game_keys = {(r["game_id"], r["team_id"]) for r in tables["team_games"]}
    for row in tables["team_games"]:
        if row["game_id"] not in games or row["team_id"] not in teams or row["opponent_team_id"] not in teams:
            raise ValueError("Broken team-game foreign key.")
        team_rows[row["game_id"]].append(row)
    for row in tables["player_games"]:
        if ((row["game_id"], row["team_id"]) not in team_game_keys or row["player_id"] not in players):
            raise ValueError("Broken player-game foreign key.")
        player_rows[(row["game_id"], row["team_id"])].append(row)
    for game in games.values():
        at, _ = parse_date(game["started_at_utc"], "UTC")
        if at is None or at >= cutoff or at.year != config["season"]:
            raise ValueError("Out-of-cutoff game in canonical table.")
        if game["source_season"] != config["season"] and not game["season_exception"]:
            raise ValueError("Source-season exception provenance was lost.")
        if game["series_id"] not in series:
            raise ValueError("Broken game-series foreign key.")
        series_games[game["series_id"]].append(game)
        rows = team_rows[game["game_id"]]
        expected = {"blue": game["blue_team_id"], "red": game["red_team_id"]}
        if len(rows) != 2 or {r["side"] for r in rows} != {"blue", "red"} or sum(r["won"] for r in rows) != 1:
            raise ValueError("A game must have two opposite-side team rows and one winner.")
        for row in rows:
            if row["team_id"] != expected[row["side"]] or row["opponent_team_id"] != expected["red" if row["side"] == "blue" else "blue"]:
                raise ValueError("Team/opponent references disagree with game sides.")
            if bool(row["won"]) != (row["team_id"] == game["winner_team_id"]):
                raise ValueError("Team and game results disagree.")
            members = player_rows[(game["game_id"], row["team_id"])]
            for member in members:
                if member["won"] != row["won"] or member["side"] != row["side"] or member["lineup_id"] != row["lineup_id"]:
                    raise ValueError("Player, lineup, and team rows disagree.")
            if row["lineup_complete"] and (len(members) != 5 or {p["role"] for p in members} != ROLES):
                raise ValueError("A complete lineup must contain exactly five roles.")
            if row["region"]:
                evidence, _ = parse_date(row["region_evidence_observed_at_utc"], "UTC")
                if evidence is None or evidence > at:
                    raise ValueError("Region evidence comes from a later observation.")
    for key, row in series.items():
        records = series_games[key]
        if len(records) != row["observed_games"]:
            raise ValueError("Series game count does not reconcile.")
        score_a = sum(g["winner_team_id"] == row["team_a_id"] for g in records)
        score_b = sum(g["winner_team_id"] == row["team_b_id"] for g in records)
        if (score_a, score_b) != (row["observed_wins_a"], row["observed_wins_b"]):
            raise ValueError("Observed series score does not reconcile.")
        if row["resolution_status"] != "needs_review" and score_a + score_b != len(records):
            raise ValueError("A resolved series includes unrelated opponents.")
    return {"game_team_player_links": "passed", "cutoff_and_season_provenance": "passed",
            "region_evidence_chronology": "passed", "series_counts_and_observed_scores": "passed"}
