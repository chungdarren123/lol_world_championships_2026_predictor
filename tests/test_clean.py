"""Exercise identity chronology, series boundaries, and table-level conservation."""

import copy
import csv
import json
import tempfile
import unittest
from pathlib import Path

from test_audit import CONFIG, FIELDS, game
from worlds_predictor.data.audit import parse_date
from worlds_predictor.data.clean import build_tables, export_tables
from worlds_predictor.data.identities import IdentityResolver
from worlds_predictor.data.series import resolve_series, stable_id
from worlds_predictor.data.validation import validate_tables


def identity_config():
    return {"team_aliases": [], "additional_region_metadata_leagues": {},
            "series": {"maximum_continuation_gap_hours": 6, "overrides": []}}


def series_game(key, date, n, league="LCK", blue="A", red="B", source_id=None, url="", split="Cup"):
    return {"game_id": key, "source_game_id": source_id or key, "league": league, "source_season": 2026,
            "stage": "regional_competition", "split": split, "season_exception": "",
            "started_at_utc": date, "game_number": n, "blue_team_id": blue, "red_team_id": red,
            "winner_team_id": blue, "source_url": url, "source_series_id": ""}


class IdentityTests(unittest.TestCase):
    def test_region_lookup_never_uses_future_membership(self):
        resolver = IdentityResolver(identity_config())
        early, _ = parse_date("2026-02-01T12:00:00Z", "UTC")
        later, _ = parse_date("2026-03-01T12:00:00Z", "UTC")
        resolver.observe_region("A", "Korea", later, "LCK", "later-game")
        self.assertEqual(resolver.region_at("A", early)[1], "unresolved")
        self.assertEqual(resolver.region_at("A", later)[0], "Korea")

    def test_region_conflicts_remain_unresolved(self):
        resolver = IdentityResolver(identity_config())
        date, _ = parse_date("2026-02-01T12:00:00Z", "UTC")
        resolver.observe_region("A", "Korea", date, "LCK", "a")
        resolver.observe_region("A", "China", date, "LPL", "b")
        self.assertEqual(resolver.region_at("A", date)[1], "conflicting_evidence")

    def test_alias_requires_matching_id_league_and_date(self):
        config = identity_config()
        config["team_aliases"] = [{"source_team_id": "alias", "canonical_team_id": "main", "canonical_name": "Main",
            "source_leagues": ["EWC"], "valid_from_utc": "2026-05-01T00:00:00Z", "valid_until_utc_exclusive": "2026-08-01T00:00:00Z",
            "evidence": "Reviewed fixture identity", "source_url": "https://example.com/identity"}]
        resolver = IdentityResolver(config)
        date, _ = parse_date("2026-05-02T00:00:00Z", "UTC")
        before, _ = parse_date("2026-04-01T00:00:00Z", "UTC")
        self.assertEqual(resolver.team("alias", "Alias", "EWC", date)[0], "main")
        self.assertEqual(resolver.team("alias", "Alias", "LCK", date)[0], "alias")
        self.assertEqual(resolver.team("alias", "Alias", "EWC", before)[0], "alias")
        self.assertEqual(resolver.team("other", "Main", "EWC", date)[0], "other")


class SeriesTests(unittest.TestCase):
    def resolve(self, games, policy=None):
        return resolve_series(games, policy or identity_config()["series"])

    def test_series_continues_across_midnight_and_side_swap(self):
        games = [series_game("a", "2026-05-01T23:40:00Z", 1),
                 series_game("b", "2026-05-02T00:40:00Z", 2, blue="B", red="A")]
        series, issues = self.resolve(games)
        self.assertEqual(len(series), 1)
        self.assertEqual(issues, [])
        self.assertEqual(games[0]["series_id"], games[1]["series_id"])
        self.assertIsNone(series[0]["best_of"])
        self.assertIsNone(series[0]["source_observations_complete"])
        self.assertIsNone(series[0]["official_winner_team_id"])

    def test_repeated_game_one_never_merges_same_opponents(self):
        series, _ = self.resolve([series_game("a", "2026-05-01T12:00:00Z", 1),
                                 series_game("b", "2026-05-01T13:00:00Z", 1)])
        self.assertEqual(len(series), 2)

    def test_long_gap_or_missing_first_game_is_flagged(self):
        series, issues = self.resolve([series_game("a", "2026-05-01T12:00:00Z", 1),
                                     series_game("b", "2026-05-02T12:00:00Z", 2)])
        self.assertEqual(len(series), 2)
        self.assertEqual(series[1]["resolution_status"], "needs_review")
        self.assertIn("missing_or_nonconsecutive_game_numbers", issues[0]["issue"])

    def test_changing_competition_context_separates_groups(self):
        series, _ = self.resolve([series_game("a", "2026-05-01T12:00:00Z", 1, split="Spring"),
                                 series_game("b", "2026-05-01T13:00:00Z", 2, split="Summer")])
        self.assertEqual(len(series), 2)

    def test_lpl_shared_source_reference(self):
        games = [series_game("a", "2026-05-01T12:00:00Z", 1, league="LPL", source_id="123-123_game_1", url="https://lpl.qq.com/es/stats.shtml?bmid=123"),
                 series_game("b", "2026-05-01T13:00:00Z", 2, league="LPL", source_id="123-123_game_2", url="https://lpl.qq.com/es/stats.shtml?bmid=123")]
        series, issues = self.resolve(games)
        self.assertEqual(len(series), 1)
        self.assertEqual(issues, [])
        self.assertEqual(series[0]["resolution_status"], "source_supported")

    def test_bad_lpl_reference_is_not_silently_trusted(self):
        games = [series_game("a", "2026-05-01T12:00:00Z", 1, league="LPL", source_id="123-123_game_2")]
        series, issues = self.resolve(games)
        self.assertEqual(series[0]["resolution_status"], "needs_review")
        self.assertTrue(any("inconsistent_lpl" in i["issue"] for i in issues))

    def test_shared_reference_with_different_opponents_is_flagged(self):
        a = series_game("a", "2026-05-01T12:00:00Z", 1)
        b = series_game("b", "2026-05-01T13:00:00Z", 2, red="C")
        a["source_series_id"] = b["source_series_id"] = "one-match"
        series, _ = self.resolve([a, b])
        self.assertEqual(series[0]["resolution_status"], "needs_review")
        self.assertIn("multiple_team_pairs", series[0]["issues"])

    def test_reviewed_partial_series_keeps_gap_and_no_final_winner(self):
        policy = identity_config()["series"]
        policy["overrides"] = [{"series_reference": "reviewed", "game_ids": ["b"],
            "evidence_url": "https://example.com/match", "best_of": 3, "known_missing_game_numbers": [1]}]
        series, _ = self.resolve([series_game("b", "2026-05-01T13:00:00Z", 2)], policy)
        self.assertEqual(series[0]["resolution_status"], "source_supported_partial")
        self.assertEqual(series[0]["observed_games"], 1)
        self.assertEqual(series[0]["best_of"], 3)
        self.assertFalse(series[0]["source_observations_complete"])
        self.assertIsNone(series[0]["official_winner_team_id"])


class CleanTableTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "source.csv"

    def write(self, rows):
        with self.path.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=FIELDS)
            writer.writeheader()
            writer.writerows(rows)

    def test_table_counts_scope_missingness_and_source_preservation(self):
        first = game("g1", players=True)
        for r in first:
            r["golddiffat15"] = ""
        rows = first + game("excluded", league="WLDs", players=True)
        self.write(rows)
        before = self.path.read_bytes()
        tables, summary = build_tables(self.path, copy.deepcopy(CONFIG), identity_config())
        self.assertEqual(summary["table_counts"]["games"], 1)
        self.assertEqual(summary["table_counts"]["team_games"], 2)
        self.assertEqual(summary["table_counts"]["player_games"], 10)
        self.assertEqual(summary["games_missing_gold_15"], 1)
        self.assertIsNone(tables["team_games"][0]["observed_gold_diff_15"])
        self.assertEqual(before, self.path.read_bytes())
        out = Path(self.temp.name) / "out"
        manifest = export_tables(tables, summary, out)
        self.assertEqual(len(manifest["output_sha256"]), 8)
        with (out / "team_games.csv").open(newline="") as stream:
            self.assertEqual(next(csv.DictReader(stream))["observed_gold_diff_15"], "")

    def test_supplemental_membership_does_not_import_outcomes(self):
        config = identity_config()
        config["additional_region_metadata_leagues"] = {"LFL": {"region": "EMEA", "source_url": "https://example.com/membership"}}
        self.write(game("member", league="LFL", players=True) + game("pool", league="EWC", date="2026-06-01T12:00:00Z", players=True))
        tables, summary = build_tables(self.path, copy.deepcopy(CONFIG), config)
        self.assertEqual(len(tables["games"]), 1)
        self.assertEqual({r["region"] for r in tables["team_games"]}, {"EMEA"})
        self.assertEqual({r["source_league"] for r in tables["team_regions"]}, {"LFL"})

    def test_later_membership_cannot_fill_earlier_region(self):
        self.write(game("early", league="EWC", date="2026-04-01T12:00:00Z", players=True)
                   + game("later", league="LCK", date="2026-06-01T12:00:00Z", players=True))
        tables, _ = build_tables(self.path, copy.deepcopy(CONFIG), identity_config())
        early_id = stable_id("game", "EWC", "early")
        self.assertTrue(all(r["region"] == "" for r in tables["team_games"] if r["game_id"] == early_id))

    def test_promotion_source_year_survives_cleaning(self):
        rows = game("promotion", league="LCS", date="2026-10-06T20:00:00Z", players=True)
        for row in rows:
            row["year"] = "2027"
        self.write(rows)
        tables, _ = build_tables(self.path, copy.deepcopy(CONFIG), identity_config())
        self.assertEqual(tables["games"][0]["source_season"], 2027)
        self.assertEqual(tables["games"][0]["stage"], "promotion")
        self.assertEqual(tables["games"][0]["played_year"], 2026)

    def test_no_fuzzy_merge_of_similar_team_names(self):
        rows = game(players=True)
        for r in rows:
            r["teamname"] = "Team Alpha" if r["side"] == "Blue" else "Team Alpha Academy"
        self.write(rows)
        tables, _ = build_tables(self.path, copy.deepcopy(CONFIG), identity_config())
        self.assertEqual(len(tables["teams"]), 2)

    def test_table_validator_rejects_future_region_evidence(self):
        self.write(game(players=True))
        tables, _ = build_tables(self.path, copy.deepcopy(CONFIG), identity_config())
        tables["team_games"][0]["region_evidence_observed_at_utc"] = "2026-12-01T00:00:00Z"
        with self.assertRaisesRegex(ValueError, "later observation"):
            validate_tables(tables, CONFIG)

    def test_table_validator_rejects_player_result_disagreement(self):
        self.write(game(players=True))
        tables, _ = build_tables(self.path, copy.deepcopy(CONFIG), identity_config())
        tables["player_games"][0]["won"] = 1 - tables["player_games"][0]["won"]
        with self.assertRaisesRegex(ValueError, "rows disagree"):
            validate_tables(tables, CONFIG)

    def test_table_validator_rejects_broken_game_series_reference(self):
        self.write(game(players=True))
        tables, _ = build_tables(self.path, copy.deepcopy(CONFIG), identity_config())
        tables["games"][0]["series_id"] = "unknown"
        with self.assertRaisesRegex(ValueError, "game-series"):
            validate_tables(tables, CONFIG)

    def test_repeated_build_has_identical_exported_table_checksums(self):
        self.write(game(players=True))
        tables_a, summary_a = build_tables(self.path, copy.deepcopy(CONFIG), identity_config())
        tables_b, summary_b = build_tables(self.path, copy.deepcopy(CONFIG), identity_config())
        a = export_tables(tables_a, summary_a, Path(self.temp.name) / "out_a")
        b = export_tables(tables_b, summary_b, Path(self.temp.name) / "out_b")
        self.assertEqual(a["output_sha256"], b["output_sha256"])
        self.assertEqual(a["package_source_sha256"], b["package_source_sha256"])


if __name__ == "__main__":
    unittest.main()
