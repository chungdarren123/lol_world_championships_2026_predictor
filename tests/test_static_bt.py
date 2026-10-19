"""Data boundaries, identifiability, and model contract checks without sampling."""

import copy
import importlib.util
import unittest

from worlds_predictor.models.bt_data import encode_records, prepare_records

HAS_NUMPY = importlib.util.find_spec("numpy") is not None
HAS_PYMC = importlib.util.find_spec("pymc") is not None


def tiny_records():
    entities = [("A", 2026, "East"), ("B", 2026, "East"),
                ("C", 2026, "West"), ("D", 2026, "West")]
    return [{"game_id": str(i), "series_id": str(i), "a": entities[a], "b": entities[b],
             "name_a": entities[a][0], "name_b": entities[b][0], "y": y,
             "league": "TEST", "stage": "regional"}
            for i, (a, b, y) in enumerate(((0, 1, 1), (1, 0, 0), (2, 3, 0), (0, 2, 1)))]


def tiny_tables():
    return {"games": [{"game_id": "g", "series_id": "s", "started_at_utc": "2026-05-01T12:00:00Z",
                       "played_year": "2026", "league": "TEST", "blue_team_id": "A", "red_team_id": "B",
                       "blue_won": "1", "stage": "regional"}],
            "team_games": [{"game_id": "g", "team_id": team, "region": "East",
                             "region_evidence_observed_at_utc": "2026-04-01T00:00:00Z",
                             "observed_duration_source_units": "1800"} for team in ("A", "B")],
            "teams": [{"team_id": team, "display_name": team} for team in ("A", "B")]}


class InputTests(unittest.TestCase):
    def test_reverse_orientation_aggregates_same_likelihood(self):
        data = encode_records(tiny_records())
        ab = next(p for p in data["pairs"] if (p["a"], p["b"]) == (0, 1))
        self.assertEqual(ab, {"a": 0, "b": 1, "wins_a": 2, "games": 2})
        self.assertEqual(data["coverage"]["cross_region_games"], 1)
        self.assertEqual(data["coverage"]["region_components"], [["East", "West"]])

    def test_disconnected_regions_are_visible(self):
        data = encode_records(tiny_records()[:-1])
        self.assertEqual(data["coverage"]["region_components"], [["East"], ["West"]])
        self.assertEqual(data["coverage"]["team_component_sizes"], [2, 2])

    def test_membership_is_not_reconstructed_from_future(self):
        tables = tiny_tables()
        tables["team_games"][0]["region_evidence_observed_at_utc"] = "2026-06-01T00:00:00Z"
        with self.assertRaisesRegex(ValueError, "Future region"):
            prepare_records(tables, "2026-10-15T18:00:00Z")

    def test_missing_stats_are_not_features_or_drop_conditions(self):
        tables = tiny_tables()
        tables["team_games"][0]["observed_gold_diff_15"] = ""
        records, excluded = prepare_records(tables, "2026-10-15T18:00:00Z")
        self.assertEqual(len(records), 1)
        self.assertEqual(excluded, {})
        self.assertNotIn("observed_gold_diff_15", records[0])

    def test_reject_duplicates_post_cutoff_and_unknown_regions(self):
        for problem in ("duplicate", "cutoff", "region", "duration", "worlds", "outcome"):
            tables = tiny_tables()
            if problem == "duplicate":
                tables["games"].append(copy.deepcopy(tables["games"][0]))
            elif problem == "cutoff":
                tables["games"][0]["started_at_utc"] = "2026-10-16T00:00:00Z"
            elif problem == "region":
                tables["team_games"][0]["region"] = ""
            elif problem == "duration":
                tables["team_games"][0]["observed_duration_source_units"] = "nan"
            elif problem == "worlds":
                tables["games"][0]["league"] = "WLDs"
            else:
                tables["games"][0]["blue_won"] = "2"
            with self.assertRaises(ValueError, msg=problem):
                prepare_records(tables, "2026-10-15T18:00:00Z")

    def test_end_and_delay_must_precede_freeze(self):
        tables = tiny_tables()
        # All games unavailable is a blocking input, not an empty fitted model.
        with self.assertRaisesRegex(ValueError, "No eligible"):
            prepare_records(tables, "2026-05-01T13:30:00Z")
        records, _ = prepare_records(tables, "2026-05-01T13:30:01Z")
        self.assertEqual(len(records), 1)


@unittest.skipUnless(HAS_NUMPY, "Install the bayes extra for numeric model tests")
class ConstraintTests(unittest.TestCase):
    def test_contrasts_have_expected_rank_and_zero_sum(self):
        import numpy as np
        from worlds_predictor.models.static_bt import zero_sum_basis, design_matrices
        for size in (1, 2, 6, 12):
            basis = zero_sum_basis(size)
            np.testing.assert_allclose(basis.sum(axis=0), 0, atol=1e-12)
            np.testing.assert_allclose(basis.T @ basis, np.eye(size - 1), atol=1e-12)
        data = encode_records(tiny_records())
        rb, tb = design_matrices(data)
        region_per_entity = rb[np.array(data["region_index"])]
        full = np.column_stack((region_per_entity, tb))
        self.assertEqual(np.linalg.matrix_rank(full), len(data["entities"]) - 1)
        for region in range(len(data["regions"])):
            np.testing.assert_allclose(tb[np.array(data["region_index"]) == region].sum(axis=0), 0, atol=1e-12)

    def test_complementarity_on_each_posterior_draw(self):
        import numpy as np
        from worlds_predictor.models.static_bt import matchup_draws
        draws = np.array([[[-1000, 1000], [0, 0], [1.0, -1.0]]])
        forward, reverse = matchup_draws(draws, 0, 1), matchup_draws(draws, 1, 0)
        np.testing.assert_allclose(forward + reverse, 1)
        self.assertTrue(np.isfinite(forward).all())
        with self.assertRaises(ValueError):
            matchup_draws(draws, 0, 0)

    def test_aggregation_retains_parameter_dependent_log_likelihood(self):
        import numpy as np
        records = tiny_records()
        data = encode_records(records)
        strengths = np.array([.8, -.2, .3, -.9])
        index = {e: i for i, e in enumerate(data["entities"])}
        individual = 0
        for row in records:
            x = strengths[index[row["a"]]] - strengths[index[row["b"]]]
            individual += -np.logaddexp(0, -x) if row["y"] else -np.logaddexp(0, x)
        aggregated = sum(-p["wins_a"] * np.logaddexp(0, -(strengths[p["a"]]-strengths[p["b"]]))
                         - (p["games"]-p["wins_a"]) * np.logaddexp(0, strengths[p["a"]]-strengths[p["b"]])
                         for p in data["pairs"])
        self.assertAlmostEqual(individual, aggregated)


@unittest.skipUnless(HAS_PYMC, "Install the bayes extra for PyMC construction tests")
class GraphTests(unittest.TestCase):
    def test_model_has_finite_initial_density_and_constrained_draws(self):
        import numpy as np
        import pymc as pm
        from worlds_predictor.models.static_bt import build_model
        data = encode_records(tiny_records())
        model = build_model(data, {"region_scale_prior": 1., "team_scale_prior": 1.})
        self.assertTrue(np.isfinite(model.compile_logp()(model.initial_point())))
        with model:
            strengths, regions, teams = pm.draw([model["strength"], model["region_effect"], model["team_effect"]],
                                                draws=5, random_seed=82)
        np.testing.assert_allclose(regions.sum(axis=-1), 0, atol=1e-12)
        for r in range(2):
            np.testing.assert_allclose(teams[:, np.array(data["region_index"]) == r].sum(axis=-1), 0, atol=1e-12)
        np.testing.assert_allclose(strengths, regions[:, data["region_index"]] + teams)

    def test_sampling_gate_rejects_disagreeing_chains_and_divergences(self):
        import arviz as az
        import json
        import numpy as np
        from pathlib import Path
        from worlds_predictor.reporting.bt_diagnostics import sampling_diagnostics
        config = json.loads(Path("configs/static_bt.json").read_text())
        rng = np.random.default_rng(99)
        values = rng.normal(size=(4, 1000, 2))
        stats = {"energy": rng.normal(size=(4, 1000)), "diverging": np.zeros((4, 1000), dtype=bool),
                 "tree_depth": np.ones((4, 1000), dtype=int)}
        good = az.from_dict(posterior={"strength": values}, sample_stats=stats)
        self.assertTrue(sampling_diagnostics(good, config)[0]["passed"])
        shifted = values.copy()
        shifted[0] += 10
        bad = az.from_dict(posterior={"strength": shifted}, sample_stats=stats)
        self.assertFalse(sampling_diagnostics(bad, config)[0]["checks"]["rhat"])
        stats["diverging"][0, 0] = True
        bad = az.from_dict(posterior={"strength": values}, sample_stats=stats)
        self.assertFalse(sampling_diagnostics(bad, config)[0]["checks"]["divergences"])


if __name__ == "__main__":
    unittest.main()
