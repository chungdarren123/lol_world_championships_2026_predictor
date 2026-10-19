"""Terminal fitting and a deterministic synthetic recovery experiment."""

import json
from pathlib import Path

from worlds_predictor.models.bt_data import encode_records, read_dataset


def validate_config(config):
    import math
    for key in ("region_scale_prior", "team_scale_prior", "result_delay_minutes"):
        if not math.isfinite(config[key]) or config[key] <= 0:
            raise ValueError(f"{key} must be finite and positive.")
    for key in ("draws", "tune", "chains", "prior_draws"):
        if not isinstance(config[key], int) or config[key] < 1:
            raise ValueError(f"{key} must be a positive integer.")
    if config["chains"] < 2 or not .5 < config["target_accept"] < 1:
        raise ValueError("Need multiple chains and target_accept between 0.5 and 1.")
    if config["sampler"] != "numpyro" or not 1 <= config["max_tree_depth"] <= 15:
        raise ValueError("Expected numpyro and a tree-depth limit between 1 and 15.")


def run_fit(dataset, config, output_dir, report_dir):
    from worlds_predictor.models.static_bt import fit_model
    from worlds_predictor.reporting.bt_diagnostics import export_fit
    validate_config(config)
    source, output_dir, report_dir = map(Path, (dataset, output_dir, report_dir))
    if source.resolve() == output_dir.resolve() or source.resolve() == report_dir.resolve():
        raise ValueError("Fit outputs must be separate from canonical inputs.")
    records, provenance = read_dataset(source, config["result_delay_minutes"])
    data = encode_records(records)
    posterior, prior = fit_model(data, config)
    return export_fit(data, records, posterior, prior, config, provenance, output_dir, report_dir)


def synthetic_records(seed=410):
    import numpy as np
    rng = np.random.default_rng(seed)
    regions = ["Synthetic_A", "Synthetic_B", "Synthetic_C"]
    entities = [(f"team_{r}_{t}", 2026, region) for r, region in enumerate(regions) for t in range(3)]
    truth = np.array([r + t for r in (-.7, 0., .7) for t in (-.5, 0., .5)])
    records = []
    for i in range(len(entities)):
        for j in range(i + 1, len(entities)):
            p = 1 / (1 + np.exp(-(truth[i] - truth[j])))
            for k, y in enumerate(rng.binomial(1, p, size=80)):
                records.append({"game_id": f"s{i}_{j}_{k}", "series_id": f"s{i}_{j}_{k}",
                                "a": entities[i], "b": entities[j], "y": int(y),
                                "name_a": entities[i][0], "name_b": entities[j][0],
                                "league": "SYNTHETIC", "stage": "synthetic_recovery"})
    return records, truth


def run_synthetic(config, output_dir, report_dir):
    import numpy as np
    from worlds_predictor.models.static_bt import fit_model
    from worlds_predictor.reporting.bt_diagnostics import export_fit, render_report
    validate_config(config)
    records, truth = synthetic_records()
    data = encode_records(records)
    posterior, prior = fit_model(data, config)
    draws = posterior.posterior["strength"].values
    means = draws.mean(axis=(0, 1))
    low, high = np.quantile(draws.reshape(-1, len(truth)), [.05, .95], axis=0)
    recovery = {"strength_rmse": float(np.sqrt(np.mean((means-truth)**2))),
                "central_90_interval_coverage": float(np.mean((truth >= low) & (truth <= high))),
                "truth": truth.tolist(), "posterior_means": means.tolist(),
                "passed": bool(np.sqrt(np.mean((means-truth)**2)) < .25 and np.mean((truth >= low) & (truth <= high)) >= 2/3),
                "interpretation": "One seeded recovery smoke test, not simulation-based calibration."}
    report, text = export_fit(data, records, posterior, prior, config, {"synthetic": True},
                              output_dir, report_dir, label="static_bt_synthetic")
    report["recovery"] = recovery
    if not recovery["passed"]:
        report["status"] = "diagnostic_fit_recovery_failed"
    text = render_report(report) + "\n## Synthetic recovery\n\n" + json.dumps(recovery, indent=2) + "\n"
    (Path(report_dir) / "static_bt_synthetic.json").write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    (Path(report_dir) / "static_bt_synthetic.md").write_text(text, encoding="utf-8")
    return report, text
