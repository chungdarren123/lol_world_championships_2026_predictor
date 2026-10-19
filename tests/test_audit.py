"""Synthetic fixtures test rules, never stand in for real 2026 findings."""

import copy
import csv
import json
import tempfile
import unittest
from pathlib import Path

from worlds_predictor.cli import main
from worlds_predictor.data.audit import audit_csv


ROOT = Path(__file__).resolve().parents[1]
CONFIG = json.loads((ROOT / "configs/audit_2026.json").read_text())
FIELDS = ["gameid", "league", "year", "date", "position", "side", "result", "teamname", "teamid",
          "playerid", "playername", "golddiffat15", "gamelength", "game", "patch", "split", "playoffs"]


def game(game_id="g1", league="LCK", date="2026-05-01 12:00:00", players=False):
    records = []
    for side, won, name in (("Blue", "1", "A"), ("Red", "0", "B")):
        team = dict.fromkeys(FIELDS, "")
        team.update(gameid=game_id, league=league, year="2026", date=date, position="team", side=side,
                    result=won, teamname=name, teamid=name, golddiffat15="0", gamelength="1800", game="1", patch="16.9", playoffs="0")
        records.append(team)
        if players:
            for role in ("top", "jng", "mid", "bot", "sup"):
                player = dict(team, position=role, playerid=name + role, playername=name + role)
                records.append(player)
    return records


class AuditTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "sample.csv"

    def run_audit(self, rows, config=None):
        with self.path.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=FIELDS)
            writer.writeheader()
            writer.writerows(rows)
        return audit_csv(self.path, config or copy.deepcopy(CONFIG))

    def test_counts_games_not_player_rows(self):
        result = self.run_audit(game(players=True))
        self.assertEqual(result["rows"]["total"], 12)
        self.assertEqual(result["structurally_valid_games"], 1)
        self.assertNotIn("team_games_without_complete_lineup", result["quality_warnings"])
        self.assertEqual(result["training_readiness"], "not_established")

    def test_worlds_unknown_year_and_cutoff_are_excluded(self):
        rows = game("good") + game("worlds", "WCS") + game("worlds_label", "WLDs") + game("academy", "LCK CL")
        rows += game("at", date="2026-10-15T18:00:00Z")
        rows += game("offset", date="2026-10-15T20:00:00+02:00")
        old = game("old")
        for row in old:
            row["year"] = "2025"
        result = self.run_audit(rows + old)
        self.assertEqual(result["structurally_valid_games"], 1)
        self.assertEqual(result["exclusions"]["worlds"], 2)
        self.assertEqual(result["exclusions"]["unreviewed_competition"], 1)
        self.assertEqual(result["exclusions"]["wrong_or_inconsistent_season"], 1)
        self.assertEqual(result["exclusions"]["at_or_after_cutoff"], 2)

    def test_same_game_id_in_distinct_leagues_not_merged(self):
        result = self.run_audit(game() + game(league="LPL"))
        self.assertEqual(result["structurally_valid_games"], 2)
        self.assertEqual(result["game_ids_reused_across_leagues"], 1)

    def test_duplicate_is_flagged_not_silently_removed(self):
        rows = game()
        result = self.run_audit(rows + [rows[0]])
        self.assertEqual(result["row_issues"]["exact_duplicate_rows"], 1)
        self.assertEqual(result["quarantined_candidate_games"], 1)

    def test_two_winners_and_same_side_are_quarantined(self):
        winners, sides = game("w"), game("s")
        winners[1]["result"] = "1"
        sides[1]["side"] = "Blue"
        result = self.run_audit(winners + sides)
        self.assertEqual(result["structurally_valid_games"], 0)
        self.assertEqual(result["validation_failures"]["invalid_or_noncomplementary_results"], 1)
        self.assertEqual(result["validation_failures"]["invalid_sides"], 1)

    def test_zero_missing_and_invalid_features_are_distinct(self):
        rows = game("a") + game("b")
        rows[1]["golddiffat15"] = ""
        rows[2]["golddiffat15"] = "broken"
        rows[3]["golddiffat15"] = "inf"
        result = self.run_audit(rows)
        self.assertEqual(result["team_row_feature_coverage"]["gold_diff_15"], {"numeric": 1, "missing": 1, "invalid": 2})
        self.assertEqual(result["games_without_both_numeric_team_values"]["gold_diff_15"], 2)

    def test_invalid_and_inconsistent_dates_cannot_enter_candidates(self):
        bad = game("bad", date="not a date")
        mixed = game("mixed")
        mixed[1]["date"] = "2026-05-02T12:00:00Z"
        result = self.run_audit(bad + mixed)
        self.assertEqual(result["candidate_games"], 0)
        self.assertEqual(result["exclusions"]["invalid_or_inconsistent_date"], 2)

    def test_html_response_is_blocked_even_with_csv_extension(self):
        self.path.write_text("<!doctype html><html><title>Google Drive - Quota exceeded</title></html>")
        result = audit_csv(self.path, CONFIG)
        self.assertEqual(result["status"], "blocked")
        self.assertIn("quota", result["errors"][0])
        self.assertNotIn("candidate_games", result)

    def test_missing_header_field_does_not_get_inferred(self):
        self.path.write_text("gameid,league\ng1,LCK\n")
        result = audit_csv(self.path, CONFIG)
        self.assertEqual(result["status"], "blocked")
        self.assertIn("Missing required columns", result["errors"][0])

    def test_unclosed_csv_quote_returns_blocked_report(self):
        self.path.write_text(",".join(FIELDS) + '\n"unterminated field')
        result = audit_csv(self.path, CONFIG)
        self.assertEqual(result["status"], "blocked")
        self.assertNotIn("candidate_games", result)

    def test_unobserved_expected_competition_is_reported_as_missing(self):
        result = self.run_audit(game())
        self.assertEqual(result["coverage"]["MSI"]["observed_games"], 0)
        self.assertEqual(result["coverage"]["MSI"]["candidate_games"], 0)

    def test_region_connections_require_unambiguous_domestic_evidence(self):
        korea = game("kr")
        china = game("cn", league="LPL")
        for row in china:
            row["teamid"] = "C" if row["side"] == "Blue" else "D"
            row["teamname"] = row["teamid"]
        international = game("intl", league="MSI")
        international[1].update(teamid="C", teamname="C")
        result = self.run_audit(korea + china + international)
        self.assertEqual(result["cross_region_game_counts"], {"China / Korea": 1})
        result = self.run_audit(international)
        self.assertEqual(result["international_games_with_unresolved_regions"], 1)
        self.assertEqual(result["cross_region_game_counts"], {})

    def test_roster_transition_and_incomplete_roster(self):
        first, second = game("a", players=True), game("b", date="2026-05-02T12:00:00Z", players=True)
        second[1]["playerid"] = "new_top"
        result = self.run_audit(first + second)
        self.assertEqual(len(result["observed_lineup_changes"]), 1)
        self.assertEqual(result["observed_lineup_changes"][0]["players_retained"], 4)
        result = self.run_audit(first[:-1])
        self.assertEqual(result["quality_warnings"]["team_games_without_complete_lineup"], 1)

    def test_duration_completion_is_not_silently_assumed(self):
        config = copy.deepcopy(CONFIG)
        config["duration_unit_verified"] = True
        result = self.run_audit(game(date="2026-10-15T17:45:00Z"), config)
        self.assertEqual(result["quality_warnings"]["team_rows_not_finished_by_cutoff"], 2)
        self.assertEqual(result["training_readiness"], "not_established")

    def test_missing_player_identity_cannot_form_complete_lineup(self):
        rows = game(players=True)
        rows[1].update(playerid="", playername="N/A")
        result = self.run_audit(rows)
        self.assertEqual(result["quality_warnings"]["team_games_without_complete_lineup"], 1)

    def test_same_region_international_game_is_not_cross_region_evidence(self):
        result = self.run_audit(game("domestic") + game("international", league="MSI"))
        self.assertEqual(result["cross_region_game_counts"], {})
        self.assertEqual(result["same_region_international_game_counts"], {"Korea": 1})

    def test_calendar_year_does_not_override_competitive_season(self):
        rows = game()
        for row in rows:
            row["year"] = "2027"
        result = self.run_audit(rows)
        self.assertEqual(result["candidate_games"], 0)
        self.assertEqual(result["source_competition_inventory"][0]["year"], "2027")

    def test_approved_promotion_exception_retains_source_season(self):
        rows = game("promo", league="LCS", date="2026-10-06T20:00:00Z")
        for row in rows:
            row["year"] = "2027"
        result = self.run_audit(rows)
        self.assertEqual(result["structurally_valid_games"], 1)
        self.assertEqual(result["season_exceptions_included"], {"LCS_2027_promotion_played_2026": 1})
        self.assertEqual(result["event_stage_game_counts"], [
            {"league": "LCS", "stage": "promotion", "source_season": 2027, "games": 1}])
        with self.path.open(newline="") as stream:
            self.assertEqual(next(csv.DictReader(stream))["year"], "2027")

    def test_promotion_exception_requires_reviewed_dates_and_metadata(self):
        rows = game("early", league="LCS", date="2026-10-04T20:00:00Z")
        rows += game("after_window", league="LCS", date="2026-10-14T00:00:00Z")
        wrong_metadata = game("wrong", league="LCS", date="2026-10-06T20:00:00Z")
        for row in wrong_metadata:
            row["split"] = "Regular season"
        rows += wrong_metadata
        for row in rows:
            row["year"] = "2027"
        result = self.run_audit(rows)
        self.assertEqual(result["candidate_games"], 0)
        self.assertEqual(result["exclusions"]["wrong_or_inconsistent_season"], 3)

    def test_promotion_exception_never_bypasses_forecast_cutoff(self):
        config = copy.deepcopy(CONFIG)
        config["season_exceptions"][0]["end_utc_exclusive"] = "2026-10-30T00:00:00Z"
        rows = game("too_late", league="LCS", date=CONFIG["cutoff_utc"])
        for row in rows:
            row["year"] = "2027"
        result = self.run_audit(rows, config)
        self.assertEqual(result["candidate_games"], 0)
        self.assertEqual(result["exclusions"]["at_or_after_cutoff"], 1)

    def test_ewc_qualifiers_and_main_event_retained_with_distinct_stages(self):
        rows = game("qualifier", league="EWC", date="2026-05-01T12:00:00Z")
        rows += game("main", league="EWC", date="2026-07-15T12:00:00Z")
        result = self.run_audit(rows)
        self.assertEqual(result["structurally_valid_games"], 2)
        stages = {r["stage"]: r["games"] for r in result["event_stage_game_counts"]}
        self.assertEqual(stages, {"main_event": 1, "qualifiers": 1})

    def test_missing_statistics_and_roster_changes_never_drop_valid_results(self):
        first = game("a", players=True)
        second = game("b", date="2026-05-02T12:00:00Z", players=True)
        second[1]["playerid"] = "replacement"
        for row in first + second:
            row["golddiffat15"] = ""
        result = self.run_audit(first + second)
        self.assertEqual(result["structurally_valid_games"], 2)
        self.assertEqual(result["games_without_both_numeric_team_values"]["gold_diff_15"], 2)
        self.assertEqual(len(result["observed_lineup_changes"]), 1)

    def test_source_bytes_are_not_changed_by_audit(self):
        self.run_audit(game())
        before = self.path.read_bytes()
        audit_csv(self.path, CONFIG)
        self.assertEqual(self.path.read_bytes(), before)

    def test_cli_writes_blocked_report_and_nonzero_exit(self):
        self.path.write_text("<!doctype html><html>quota exceeded</html>")
        output = Path(self.temp.name) / "reports"
        import contextlib
        import io
        with contextlib.redirect_stdout(io.StringIO()):
            code = main(["audit", str(self.path), "--config", str(ROOT / "configs/audit_2026.json"), "--output-dir", str(output)])
        self.assertEqual(code, 2)
        self.assertEqual(json.loads((output / "data_audit.json").read_text())["status"], "blocked")
        self.assertIn("No real-game coverage", (output / "data_audit.md").read_text())


if __name__ == "__main__":
    unittest.main()
