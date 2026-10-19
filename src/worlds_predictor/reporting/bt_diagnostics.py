"""Sampling checks and explicitly in-sample model checks, never forecast scores."""

import csv
import hashlib
import json
from pathlib import Path
import platform


def interval(values):
    import numpy as np
    return {"mean": float(np.mean(values)), "sd": float(np.std(values)),
            "q05": float(np.quantile(values, .05)), "q95": float(np.quantile(values, .95))}


def sampling_diagnostics(posterior, config):
    import arviz as az
    import numpy as np
    variables = [v for v in ("region_sd", "team_sd", "z_region", "z_team",
                             "region_effect", "team_effect", "strength") if v in posterior.posterior]
    summary = az.summary(posterior, var_names=variables, round_to="none")
    # Fixed zero effects, possible for singleton regions, have no mixing diagnostic.
    active = summary[summary["sd"] > 1e-12]
    limits = config["diagnostic_limits"]
    rhat = active["r_hat"].to_numpy()
    bulk, tail = (active[k].to_numpy() for k in ("ess_bulk", "ess_tail"))
    bfmi = np.asarray(az.bfmi(posterior))
    divergences = int(posterior.sample_stats["diverging"].sum())
    valid = all(np.all(np.isfinite(x)) for x in (rhat, bulk, tail, bfmi)) and len(active) > 0
    checks = {
        "finite_diagnostics": bool(valid),
        "rhat": bool(valid and np.max(rhat) <= limits["max_rhat"]),
        "bulk_ess": bool(valid and np.min(bulk) >= limits["min_bulk_ess"]),
        "tail_ess": bool(valid and np.min(tail) >= limits["min_tail_ess"]),
        "bfmi": bool(valid and np.min(bfmi) >= limits["min_bfmi"]),
        "divergences": divergences <= limits["max_divergences"],
    }
    if "reached_max_treedepth" in posterior.sample_stats:
        checks["tree_depth"] = not bool(posterior.sample_stats["reached_max_treedepth"].any())
    elif "tree_depth" in posterior.sample_stats:
        checks["tree_depth"] = int(posterior.sample_stats["tree_depth"].max()) < config["max_tree_depth"]
    return {"passed": all(checks.values()), "checks": checks,
            "max_rhat": float(np.max(rhat)) if valid else None,
            "min_bulk_ess": float(np.min(bulk)) if valid else None,
            "min_tail_ess": float(np.min(tail)) if valid else None,
            "bfmi_by_chain": [float(x) if np.isfinite(x) else None for x in bfmi], "divergences": divergences,
            "fixed_parameters_omitted": int(len(summary) - len(active)),
            "limits": limits}, summary


def probability_checks(strength, records, data, seed):
    import numpy as np
    from worlds_predictor.models.static_bt import matchup_draws
    index = {e: i for i, e in enumerate(data["entities"])}
    a, b = (np.array([index[r[k]] for r in records]) for k in ("a", "b"))
    flat = strength.reshape(-1, strength.shape[-1])
    # Bound memory while preserving draws of joint strengths.
    selected = flat[np.linspace(0, len(flat) - 1, min(1000, len(flat)), dtype=int)]
    delta = selected[:, a] - selected[:, b]
    probabilities = np.exp(-np.logaddexp(0, -delta))
    predictive = np.random.default_rng(seed).binomial(1, probabilities)
    groups = {"all": np.ones(len(records), dtype=bool),
              "cross_region": np.array([r["a"][2] != r["b"][2] for r in records]),
              "same_region": np.array([r["a"][2] == r["b"][2] for r in records])}
    for label in sorted({r["league"] + "/" + r["stage"] for r in records}):
        groups[label] = np.array([r["league"] + "/" + r["stage"] == label for r in records])
    y = np.array([r["y"] for r in records])
    mean_p = probabilities.mean(axis=0)
    bins = []
    for i in range(10):
        mask = np.minimum((mean_p * 10).astype(int), 9) == i
        if mask.any():
            bins.append({"lower": i / 10, "upper": (i + 1) / 10, "games": int(mask.sum()),
                         "mean_probability": float(mean_p[mask].mean()), "observed_rate": float(y[mask].mean())})
    checks = {}
    for name, mask in groups.items():
        if mask.any():
            replicated = predictive[:, mask].mean(axis=1)
            checks[name] = {"games": int(mask.sum()), "observed_blue_win_rate": float(y[mask].mean()),
                            "replicated_blue_win_rate": interval(replicated)}
            checks[name]["outside_central_90_predictive_interval"] = bool(
                y[mask].mean() < np.quantile(replicated, .05) or y[mask].mean() > np.quantile(replicated, .95))
    # Algebraic symmetry is checked on each draw, not on rounded means.
    p = matchup_draws(flat, 0, 1)
    reverse = matchup_draws(flat, 1, 0)
    return {"interpretation": "IN-SAMPLE checks only; not held-out performance or calibration validation. "
            "Multiple group intervals are descriptive discrepancy checks, not significance tests.",
            "posterior_predictive_groups": checks, "in_sample_calibration": bins,
            "in_sample_log_loss": float(-np.mean(y * np.log(np.clip(mean_p, 1e-15, 1)) +
                                                   (1-y) * np.log(np.clip(1-mean_p, 1e-15, 1)))),
            "in_sample_brier": float(np.mean((mean_p-y)**2)),
            "maximum_symmetry_error": float(np.max(np.abs(p + reverse - 1)))}


def export_fit(data, records, posterior, prior, config, provenance, output_dir, report_dir, label="static_bt"):
    import importlib.metadata
    import numpy as np
    from worlds_predictor.models.static_bt import matchup_draws
    output_dir, report_dir = Path(output_dir), Path(report_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    report_dir.mkdir(parents=True, exist_ok=True)
    diagnostic, summary = sampling_diagnostics(posterior, config)
    summary.to_csv(output_dir / "parameter_diagnostics.csv")
    arrays = {name: posterior.posterior[name].values for name in ("strength", "region_effect", "team_effect")}
    np.savez_compressed(output_dir / "posterior_draws.npz", **arrays)
    # Retain all sampled parameters and sampler statistics for later reinspection.
    np.savez_compressed(output_dir / "inference_trace.npz",
                        **{"posterior__" + k: v.values for k, v in posterior.posterior.data_vars.items()},
                        **{"stats__" + k: v.values for k, v in posterior.sample_stats.data_vars.items()},
                        **{"prior__" + k: v.values for k, v in prior.prior.data_vars.items()})
    region_rows = [{"region": region, **interval(arrays["region_effect"][..., i])}
                   for i, region in enumerate(data["regions"])]
    team_rows = [{"entity_index": i, "team_id": e[0], "played_season": e[1], "region": e[2],
                  "display_name": data["names"][i], "games": data["games_by_entity"][i],
                  **interval(arrays["strength"][..., i])} for i, e in enumerate(data["entities"])]
    for name, rows in (("regions", region_rows), ("teams", team_rows)):
        with (output_dir / (name + ".csv")).open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
    prior_strength = prior.prior["strength"].values
    prior_ps = np.concatenate([matchup_draws(prior_strength, p["a"], p["b"]).reshape(-1)
                               for p in data["pairs"]])
    prior_check = {"interpretation": "Equal weight per observed matchup pair; not per game.",
                   "matchup_probability": interval(prior_ps),
                   "fraction_below_01_or_above_99": float(np.mean((prior_ps < .01) | (prior_ps > .99)))}
    report = {"status": "diagnostic_fit_sampling_passed" if diagnostic["passed"] else "diagnostic_fit_sampling_failed",
              "forecast_ready": False, "config": config, "provenance": provenance,
              "coverage": data["coverage"], "sampling": diagnostic, "region_summaries": region_rows,
              "prior_predictive": prior_check,
              "model_checks": probability_checks(arrays["strength"], records, data, config["seed"] + 1),
              "versions": {name: importlib.metadata.version(name) for name in
                           ("pymc", "arviz", "numpy", "pytensor", "scipy", "pandas", "numpyro", "jax", "jaxlib")},
              "python_version": platform.python_version(),
              "limitations": [
                  "Static 2026 pre-Play-Ins diagnostic only: no time decay, historical international data, or completed Play-In games yet.",
                  "Uses the original scheduled cutoff and unverified UTC/seconds source assumptions, with an explicit assumed result delay.",
                  "Publication time and later source corrections are unknown; this is not a verified historical snapshot.",
                  "Region means describe this modeled team pool; coverage and selection of international entrants affect interpretation.",
                  "Disconnected comparisons depend on priors; graph connectivity alone does not guarantee precise regional strengths.",
                  "Team-region-season effects are constant despite roster/patch changes; lineups remain preserved in canonical tables.",
                  "Games are conditionally independent given fixed strengths. Within-series dependence and adaptation are omitted.",
                  "Known partial series contributes observed games only; no missing results or official final scores are invented.",
                  "Missing Gold/XP games are retained; those statistics and drafts are not features and no imputation is performed.",
                  "Prior and posterior predictive checks use observed fixtures; in-sample checks do not demonstrate forecasting skill.",
                  "Sampling checks assess numerical inference, not whether assumptions or predictions are correct.",
                  "A single synthetic recovery exercise is a smoke test, not simulation-based calibration across many synthetic datasets.",
                  "Region/team scale priors require sensitivity review; no test-outcome-driven parameter tuning is authorized.",
              ]}
    if provenance.get("synthetic"):
        report["limitations"] = [
            "Synthetic data with known fixed strengths only; no real-team conclusions or historical timing assumptions apply.",
            "One seeded recovery experiment is not simulation-based calibration across many simulated datasets.",
            "Synthetic games match the model's conditional-independence assumptions; real games may violate them.",
            "Sampling success and recovery here do not establish out-of-sample accuracy on real tournaments.",
        ]
    report["model_check_warnings"] = [
        name + ": observed blue win rate is outside the central 90% replicated range"
        for name, check in report["model_checks"]["posterior_predictive_groups"].items()
        if check["outside_central_90_predictive_interval"]]
    package = Path(__file__).resolve().parents[1]
    digest = hashlib.sha256()
    for module in sorted(package.rglob("*.py")):
        digest.update(module.relative_to(package).as_posix().encode() + b"\0" + module.read_bytes())
    report["package_source_sha256"] = digest.hexdigest()
    metadata = {"schema_version": 1, "array_axes": {"strength": ["chain", "draw", "entity"],
                "team_effect": ["chain", "draw", "entity"], "region_effect": ["chain", "draw", "region"]},
                "inference_trace_axes": {
                    **{"posterior__" + k: list(v.dims) for k, v in posterior.posterior.data_vars.items()},
                    **{"stats__" + k: list(v.dims) for k, v in posterior.sample_stats.data_vars.items()},
                    **{"prior__" + k: list(v.dims) for k, v in prior.prior.data_vars.items()}},
                "entities": [list(e) for e in data["entities"]], "regions": data["regions"],
                "region_index": data["region_index"], "config": config,
                "sampling_passed": diagnostic["passed"], "forecast_ready": False}
    (output_dir / "posterior_metadata.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    plot_regions(region_rows, output_dir / "region_intervals.png")
    plot_traces(posterior, output_dir / "scale_traces.png")
    report["artifact_sha256"] = {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                                 for p in sorted(output_dir.iterdir()) if p.is_file()}
    text = render_report(report)
    (report_dir / (label + ".json")).write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    (report_dir / (label + ".md")).write_text(text, encoding="utf-8")
    return report, text


def plot_regions(rows, path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    figure, axes = plt.subplots(figsize=(9, 5), layout="constrained")
    for i, row in enumerate(rows):
        axes.plot([row["q05"], row["q95"]], [i, i], color="#2563eb", linewidth=3)
        axes.plot(row["mean"], i, "o", color="#1e3a8a")
    axes.axvline(0, color="grey", linestyle="--", linewidth=1)
    axes.set_yticks(range(len(rows)), [r["region"] for r in rows])
    axes.set_xlabel("Regional effect on log-odds scale; mean and central 90% credible interval")
    axes.set_title("Static 2026 fit: regional uncertainty\nDiagnostic only; not a current-strength forecast")
    figure.savefig(path, dpi=160)
    plt.close(figure)


def plot_traces(posterior, path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    variables = [k for k in ("region_sd", "team_sd") if k in posterior.posterior]
    figure, axes = plt.subplots(len(variables), 1, figsize=(10, 3 * len(variables)), squeeze=False, layout="constrained")
    for ax, variable in zip(axes[:, 0], variables):
        values = posterior.posterior[variable].values
        for chain in range(values.shape[0]):
            ax.plot(values[chain], alpha=.6, linewidth=.5, label=f"Chain {chain + 1}")
        ax.set_title(variable + ": retained draws; warmup excluded")
        ax.set_ylabel("Log-odds scale")
        ax.legend(loc="upper right", ncol=4)
    axes[-1, 0].set_xlabel("Draw within chain")
    figure.savefig(path, dpi=140)
    plt.close(figure)


def render_report(report):
    c, d = report["coverage"], report["sampling"]
    scope = ("Synthetic recovery experiment with known strengths; not a real-data fit."
             if report["provenance"].get("synthetic") else
             "Static fit to the existing 2026 pre-Play-Ins pool. Expanded data and temporal modeling remain pending.")
    lines = ["# Static hierarchical Bradley-Terry diagnostic", "", f"Status: {report['status']}", "",
             "**Not a forecast.** " + scope, "",
             f"Games: {c['games']}; series represented: {c['series']}; team-region-season entities: {c['teams']}; "
             f"regions: {c['regions']}; cross-region games: {c['cross_region_games']}.", "",
             f"Region graph components: {c['region_components']}. Team graph component sizes: {c['team_component_sizes']}.", "",
             "## Inference checks", "",
             f"Passed: {d['passed']}; max rank-normalized R-hat: {d['max_rhat']}; "
             f"min bulk/tail ESS: {d['min_bulk_ess']} / {d['min_tail_ess']}; divergences: {d['divergences']}.", "",
             f"BFMI by chain: {d['bfmi_by_chain']}", "",
             "R-hat checks agreement between chains; ESS estimates independent information in correlated draws. "
             "Divergences and BFMI warn about exploration problems. Passing these checks does not validate the model's assumptions.", "",
             "## Region effects", "",
             "The reference is the mean of the modeled regional pool means, with within-region team deviations centred at zero. "
             "These are log-odds effects, not win percentages. Intervals are central 90% posterior credible intervals.", "",
             "| Region | Mean | 5% | 95% |", "|---|---:|---:|---:|"]
    lines += [f"| {r['region']} | {r['mean']:.3f} | {r['q05']:.3f} | {r['q95']:.3f} |" for r in report["region_summaries"]]
    lines += ["", "## Predictive checks", "",
              "The JSON report contains prior matchup probabilities, posterior predictive blue-win rates by event/stage and region pairing, "
              "and in-sample probability bins. These check plausibility and model fit; none is an out-of-sample forecast score.", "",
              "| Pairing | Games | Observed blue wins | Replicated mean | Replicated 5% to 95% |",
              "|---|---:|---:|---:|---:|"]
    for key in ("all", "cross_region", "same_region"):
        check = report["model_checks"]["posterior_predictive_groups"].get(key)
        if check:
            replicated = check["replicated_blue_win_rate"]
            lines.append(f"| {key} | {check['games']} | {check['observed_blue_win_rate']:.1%} | "
                         f"{replicated['mean']:.1%} | {replicated['q05']:.1%} to {replicated['q95']:.1%} |")
    lines += ["", "Discrepancies (descriptive checks across multiple groups, not significance tests):", ""]
    lines += ["- " + item for item in report["model_check_warnings"]] or ["- None flagged by this check."]
    lines += ["", "Omitted map-side effects, selection mechanisms, changing strengths, or other misspecification could explain mismatches. "
              "A mismatch does not establish a causal blue-side advantage. Passing sampler checks does not remove model discrepancies.", "",
              "## Limitations", ""]
    lines += ["- " + item for item in report["limitations"]]
    return "\n".join(lines) + "\n"
