"""Compare prior perturbations without selecting a model on future outcomes."""

import json
from pathlib import Path


def compare_fits(baseline_artifacts, alternate_artifacts, baseline_report, alternate_report, report_dir):
    import numpy as np
    from worlds_predictor.models.static_bt import matchup_draws
    base, alt = [json.loads(Path(p).read_text(encoding="utf-8")) for p in (baseline_report, alternate_report)]
    if base["provenance"]["input_sha256"] != alt["provenance"]["input_sha256"]:
        raise ValueError("Sensitivity fits must use identical input tables.")
    excluded_settings = {"region_scale_prior", "team_scale_prior", "prior_multiplier"}
    if {k: v for k, v in base["config"].items() if k not in excluded_settings} != {
            k: v for k, v in alt["config"].items() if k not in excluded_settings}:
        raise ValueError("A prior-only comparison requires other model/sampler settings to match.")
    paths = [Path(p) for p in (baseline_artifacts, alternate_artifacts)]
    metadata = [json.loads((p / "posterior_metadata.json").read_text(encoding="utf-8")) for p in paths]
    if metadata[0]["entities"] != metadata[1]["entities"]:
        raise ValueError("Sensitivity entity order differs.")
    strengths = []
    for folder, report in zip(paths, (base, alt)):
        import hashlib
        meta = folder / "posterior_metadata.json"
        if hashlib.sha256(meta.read_bytes()).hexdigest() != report["artifact_sha256"][meta.name]:
            raise ValueError("Sensitivity metadata checksum mismatch.")
        path = folder / "posterior_draws.npz"
        if hashlib.sha256(path.read_bytes()).hexdigest() != report["artifact_sha256"][path.name]:
            raise ValueError("Sensitivity posterior artifact checksum mismatch.")
        with np.load(path, allow_pickle=False) as archive:
            strengths.append(archive["strength"].reshape(-1, len(metadata[0]["entities"])))
    regions = [{"region": a["region"], "baseline_mean": a["mean"], "alternate_mean": b["mean"],
                "mean_shift": b["mean"] - a["mean"],
                "baseline_q05_q95": [a["q05"], a["q95"]], "alternate_q05_q95": [b["q05"], b["q95"]]}
               for a, b in zip(base["region_summaries"], alt["region_summaries"])]
    differences, largest = [], None
    for a in range(len(metadata[0]["entities"])):
        for b in range(a + 1, len(metadata[0]["entities"])):
            p, q = [float(matchup_draws(draws, a, b).mean()) for draws in strengths]
            delta = abs(q - p)
            differences.append(delta)
            if largest is None or delta > largest["absolute_shift"]:
                largest = {"team_a": metadata[0]["entities"][a], "team_b": metadata[0]["entities"][b],
                           "baseline_probability": p, "alternate_probability": q, "absolute_shift": delta}
    report = {"both_sampling_passed": base["sampling"]["passed"] and alt["sampling"]["passed"],
              "baseline_config": base["config"], "alternate_config": alt["config"],
              "region_comparison": regions, "matchup_pairs_compared": len(differences),
              "mean_absolute_probability_shift": float(np.mean(differences)), "largest_shift": largest,
              "interpretation": "One prior perturbation, with Monte Carlo noise in each fit. "
              "This is not a forecast-accuracy comparison, exhaustive robustness test, or model selection rule."}
    text = "# Static model prior sensitivity\n\n" + report["interpretation"] + "\n\n"
    text += f"Both fits passed sampling checks: {report['both_sampling_passed']}.\n\n"
    text += f"Across {len(differences)} team pairs, mean absolute probability shift: {100*np.mean(differences):.2f} percentage points; maximum: {100*max(differences):.2f} percentage points.\n\n"
    text += "| Region | Baseline mean | Alternate mean | Shift |\n|---|---:|---:|---:|\n"
    text += "\n".join(f"| {r['region']} | {r['baseline_mean']:.3f} | {r['alternate_mean']:.3f} | {r['mean_shift']:.3f} |" for r in regions) + "\n"
    target = Path(report_dir)
    target.mkdir(parents=True, exist_ok=True)
    (target / "static_bt_sensitivity.json").write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    (target / "static_bt_sensitivity.md").write_text(text, encoding="utf-8")
    return report, text
