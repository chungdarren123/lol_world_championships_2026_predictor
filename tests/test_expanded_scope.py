"""Expanded selection, historical membership, and chronological fold leakage checks."""

from copy import deepcopy
import csv
import json
import hashlib
from pathlib import Path
import tempfile
import unittest

from test_audit import game, CONFIG, FIELDS
from worlds_predictor.data.expanded_audit import (
    at, audit_expanded, classify, resolve_membership, structural_issues, write_expanded,
    reconcile_previous_pool,
)
from worlds_predictor.evaluation.folds import build_folds


SCOPE = json.loads(Path("configs/expanded_scope.json").read_text())


class ScopeTests(unittest.TestCase):
    def test_historical_worlds_label_does_not_admit_regional_qualifiers(self):
        selection, reason = classify(2024, "WLDs", "q", at("2024-09-01T12:00:00Z"), SCOPE, set(), CONFIG)
        self.assertIsNone(selection)
        selection, _ = classify(2024, "WLDs", "w", at("2024-10-01T12:00:00Z"), SCOPE, set(), CONFIG)
        self.assertEqual(selection["event"], "Worlds")
        self.assertEqual(selection["stage"], "all_event_stages")

    def test_old_regional_results_never_become_training_candidates(self):
        selected, _ = classify(2024, "LCK", "g", at("2024-05-02T00:00:00Z"), SCOPE, set(), CONFIG)
        self.assertIsNone(selected)

    def test_only_approved_2026_play_in_window_is_admitted(self):
        selected, _ = classify(2026, "WLDs", "g", at("2026-10-18T18:00:00Z"), SCOPE, set(), CONFIG)
        self.assertEqual(selected["stage"], "play_in")
        for stamp in ("2026-10-19T00:00:00Z", "2026-10-23T17:00:00Z"):
            self.assertIsNone(classify(2026, "WLDs", "g", at(stamp), SCOPE, set(), CONFIG)[0])

    def test_qualifier_exception_requires_exact_reviewed_reference_and_date(self):
        selected, _ = classify(2026, "WLDs", "13506-13506_game_1", at("2026-09-17T09:00:00Z"), SCOPE, set(), CONFIG)
        self.assertEqual(selected["scope_review"], "pending_primary_event_confirmation")
        for gid, stamp in (("other", "2026-09-17T09:00:00Z"), ("13506-13506_game_1", "2026-10-17T09:00:00Z")):
            selected, _ = classify(2026, "WLDs", gid, at(stamp), SCOPE, set(), CONFIG)
            self.assertNotEqual(selected and selected["stage"], "regional_qualifier")

    def test_membership_never_uses_later_participation(self):
        observations = [(at("2024-06-01T00:00:00Z"), "Korea", "LCK", "g")]
        self.assertEqual(resolve_membership(observations, at("2024-05-01T00:00:00Z"))[0], "")
        observations.append((at("2024-01-01T00:00:00Z"), "China", "LPL", "h"))
        self.assertEqual(resolve_membership(observations, at("2024-05-01T00:00:00Z"))[0], "China")
        self.assertEqual(resolve_membership(observations, at("2024-07-01T00:00:00Z"))[2], "conflicting_evidence")

    def test_structural_validation_checks_lineups_and_results(self):
        rows = game(players=True)
        self.assertEqual(structural_issues(rows, 2026), [])
        rows[1]["result"] = "0"
        self.assertTrue(structural_issues(rows, 2026))
        rows = game(players=True)
        rows[1]["playerid"] = ""
        self.assertIn("incomplete_or_repeated_player_ids", structural_issues(rows, 2026))

    def test_small_audit_and_export_preserve_raw_file(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / "sample.csv"
            with source.open("w", encoding="utf-8", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=FIELDS)
                writer.writeheader()
                writer.writerows(game(players=True))
            original = source.read_bytes()
            scope = deepcopy(SCOPE)
            scope["sources"] = {"2026": str(source)}
            scope["historical_events"] = []
            scope["play_in"]["expected_series"] = 0
            identities = {"team_aliases": [], "series": {"maximum_continuation_gap_hours": 6, "overrides": []}}
            rows, groups, report = audit_expanded(scope, CONFIG, identities)
            self.assertEqual(report["candidate_games"], 1)
            self.assertEqual(report["errors"], [])
            self.assertEqual(rows[0]["blue_region"], "Korea")
            write_expanded(rows, groups, report, root / "output", root / "reports")
            self.assertEqual(source.read_bytes(), original)
            self.assertFalse((root / "output/manifest.json").exists())
            self.assertTrue((root / "output/audit_manifest.json").exists())

    def test_missing_sources_produce_a_blocked_audit(self):
        scope = deepcopy(SCOPE)
        scope["sources"] = {"2026": "no-such-source-file.csv"}
        _, _, report = audit_expanded(scope, CONFIG, {"team_aliases": [], "series": {"maximum_continuation_gap_hours": 6, "overrides": []}})
        self.assertEqual(report["status"], "blocked")
        self.assertTrue(any("Missing source" in e for e in report["errors"]))

    def test_post_draw_freeze_cannot_precede_announcement_evidence(self):
        scope = deepcopy(SCOPE)
        scope["forecast_freeze_utc"] = "2026-10-18T20:00:00Z"
        with self.assertRaisesRegex(ValueError, "announcement timestamp"):
            audit_expanded(scope, CONFIG, {"team_aliases": [], "series": {"maximum_continuation_gap_hours": 6, "overrides": []}})

    def test_snapshot_comparison_exposes_changed_outcomes(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            original = {"game_id": "g", "started_at_utc": "2026-05-01T00:00:00+00:00", "blue_team_id": "A",
                        "red_team_id": "B", "blue_won": "1", "source_season": "2026"}
            with (root / "games.csv").open("w", newline="", encoding="utf-8") as stream:
                writer = csv.DictWriter(stream, fieldnames=list(original))
                writer.writeheader()
                writer.writerow(original)
            manifest = {"source": {"sha256": "previous-raw"}, "output_sha256": {
                "games.csv": hashlib.sha256((root / "games.csv").read_bytes()).hexdigest()}}
            (root / "manifest.json").write_text(json.dumps(manifest))
            updated = dict(original, played_year=2026, scope_review="existing_approved_scope", blue_won=0)
            comparison = reconcile_previous_pool([updated], root)
            self.assertEqual(comparison["changed_inspected_game_fields"], [{"game_id": "g", "changed_fields": ["blue_won"]}])


def record(gid, sid, started, available, event="LCK", status="provisional_sequence"):
    return {"game_id": gid, "series_id": sid, "started_at_utc": started,
            "assumed_available_at_utc": available, "league": event, "stage": "main_event",
            "blue_region": "Korea", "red_region": "China", "series_status": status,
            "scope_review": "reviewed_window", "blue_won": 1}


def protocol():
    return {"freeze_model_for_entire_event": True, "purge_training_series_overlapping_fit_boundary": True,
            "folds": [{"id": "event", "fit_before_utc": "2026-06-01T00:00:00Z", "event": "MSI", "stage": "main_event",
                       "start_utc": "2026-06-01T00:00:00Z", "end_utc_exclusive": "2026-06-10T00:00:00Z"}]}


class FoldTests(unittest.TestCase):
    def test_later_labels_never_change_membership(self):
        rows = [record("a", "s1", "2026-05-01T00:00:00Z", "2026-05-01T01:00:00Z"),
                record("b", "s2", "2026-06-02T00:00:00Z", "2026-06-02T01:00:00Z", "MSI")]
        before = build_folds(rows, protocol())
        for row in rows:
            row["blue_won"] = 0
        self.assertEqual(before, build_folds(rows, protocol()))
        self.assertFalse(any("blue_won" in row for row in before[0]))

    def test_whole_series_is_purged_when_availability_crosses_boundary(self):
        rows = [record("a", "same", "2026-05-31T22:00:00Z", "2026-05-31T23:00:00Z"),
                record("b", "same", "2026-05-31T23:30:00Z", "2026-06-01T00:30:00Z"),
                record("c", "target", "2026-06-02T00:00:00Z", "2026-06-02T01:00:00Z", "MSI")]
        output, summary = build_folds(rows, protocol())
        self.assertEqual(summary[0]["candidate_training_games"], 0)
        self.assertEqual(summary[0]["boundary_purged_games"], 2)
        self.assertEqual({r["role"] for r in output}, {"evaluate", "purged_at_boundary"})

    def test_an_event_cannot_split_a_series(self):
        rows = [record("a", "same", "2026-06-02T00:00:00Z", "2026-06-02T01:00:00Z", "MSI"),
                record("b", "same", "2026-06-11T00:00:00Z", "2026-06-11T01:00:00Z", "MSI")]
        with self.assertRaisesRegex(ValueError, "splits a series"):
            build_folds(rows, protocol())

    def test_known_partial_target_is_not_scored(self):
        rows = [record("a", "partial", "2026-06-02T00:00:00Z", "2026-06-02T01:00:00Z", "MSI", "source_supported_partial")]
        _, summary = build_folds(rows, protocol())
        self.assertEqual(summary[0]["evaluation_games"], 0)
        self.assertEqual(summary[0]["known_partial_evaluation_games_excluded"], 1)

    def test_result_available_exactly_at_fit_boundary_is_not_training_data(self):
        rows = [record("a", "before", "2026-05-31T23:00:00Z", "2026-06-01T00:00:00Z"),
                record("b", "target", "2026-06-02T00:00:00Z", "2026-06-02T01:00:00Z", "MSI")]
        _, summary = build_folds(rows, protocol())
        self.assertEqual(summary[0]["candidate_training_games"], 0)


if __name__ == "__main__":
    unittest.main()
