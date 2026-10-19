"""Prepare inspectable candidate folds; do not fit models or export forecasts."""

from collections import defaultdict
import csv
import hashlib
import io
import json
from pathlib import Path

from worlds_predictor.data.expanded_audit import at


def build_folds(records, protocol):
    if not protocol.get("freeze_model_for_entire_event") or not protocol.get("purge_training_series_overlapping_fit_boundary"):
        raise ValueError("This planner implements frozen events and whole-series boundary purging only.")
    if len({r["game_id"] for r in records}) != len(records):
        raise ValueError("Duplicate candidate game IDs in evaluation input.")
    groups = defaultdict(list)
    for row in records:
        if not row.get("series_id"):
            raise ValueError("Every evaluation record needs an explicit series group.")
        if at(row["assumed_available_at_utc"]) <= at(row["started_at_utc"]):
            raise ValueError("Result availability must follow game start.")
        groups[row["series_id"]].append(row)
    output, summaries = [], []
    for fold in protocol["folds"]:
        boundary, start, end = (at(fold[k]) for k in ("fit_before_utc", "start_utc", "end_utc_exclusive"))
        if boundary > start or start >= end:
            raise ValueError("Require fitting boundary <= evaluation start < evaluation end.")
        target = [r for r in records if r["league"] == fold["event"] and r["stage"] == fold["stage"]
                  and start <= at(r["started_at_utc"]) < end]
        if not target:
            raise ValueError("No evaluation games in " + fold["id"])
        target_ids = {r["game_id"] for r in target}
        target_series = {r["series_id"] for r in target}
        if any(any(r["game_id"] not in target_ids for r in groups[sid]) for sid in target_series):
            raise ValueError("Evaluation window splits a series group.")
        train, purged = [], []
        for sid, members in sorted(groups.items()):
            if sid in target_series:
                continue
            if max(at(r["assumed_available_at_utc"]) for r in members) < boundary:
                train.extend(members)
            elif min(at(r["started_at_utc"]) for r in members) < boundary:
                purged.extend(members)
        if set(r["game_id"] for r in train) & target_ids:
            raise ValueError("Training/evaluation overlap.")
        scored = [r for r in target if "partial" not in r.get("series_status", "")]
        summary = {"id": fold["id"], "fit_before_utc": boundary.isoformat(),
                   "candidate_training_games": len(train), "candidate_training_series": len({r["series_id"] for r in train}),
                   "training_games_with_pending_scope_review": sum(r["scope_review"] not in {
                       "reviewed_window", "existing_approved_scope", "approved_play_in_only"} for r in train),
                   "training_region_labels": sorted({r[s + "_region"] for r in train for s in ("blue", "red")}),
                   "evaluation_games": len(scored), "evaluation_series": len({r["series_id"] for r in scored}),
                   "evaluation_cross_region_games": sum(r["blue_region"] != r["red_region"] for r in scored),
                   "known_partial_evaluation_games_excluded": len(target) - len(scored),
                   "boundary_purged_games": len(purged),
                   "latest_training_availability": max((r["assumed_available_at_utc"] for r in train), default=None)}
        summaries.append(summary)
        for role, rows in (("candidate_train", train), ("evaluate", scored), ("purged_at_boundary", purged)):
            for row in sorted(rows, key=lambda r: (r["started_at_utc"], r["game_id"])):
                # No outcomes enter fold construction or the exported membership file.
                output.append({"fold_id": fold["id"], "role": role, "game_id": row["game_id"],
                               "series_id": row["series_id"], "started_at_utc": row["started_at_utc"],
                               "assumed_available_at_utc": row["assumed_available_at_utc"],
                               "scope_review": row["scope_review"]})
    return output, summaries


def export_plan(dataset, protocol, output_dir, report_dir):
    dataset, output_dir, report_dir = map(Path, (dataset, output_dir, report_dir))
    if dataset.resolve() == output_dir.resolve():
        raise ValueError("Evaluation output must be separate from the audit inventory.")
    manifest_bytes = (dataset / "audit_manifest.json").read_bytes()
    manifest = json.loads(manifest_bytes)
    raw = (dataset / "candidate_games.csv").read_bytes()
    if hashlib.sha256(raw).hexdigest() != manifest["output_sha256"]["candidate_games.csv"]:
        raise ValueError("Candidate inventory checksum mismatch.")
    if manifest["errors"]:
        raise ValueError("Resolve blocking source audit findings before preparing folds.")
    records = list(csv.DictReader(io.StringIO(raw.decode("utf-8-sig"))))
    output, summaries = build_folds(records, protocol)
    report = {"status": "candidate_fold_membership_prepared", "execution_ready": False,
              "audit_manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
              "protocol": protocol, "folds": summaries,
              "pending_audit_reviews": manifest["open_reviews"],
              "limitations": [
                  "Candidate training sets are for inspection; open event/identity/model-bridge reviews must be resolved before fitting.",
                  "No probabilities were fitted or scored; this report contains sample counts and membership only.",
                  "Historical 2026 outcomes were already inspected in diagnostics, so these are development backtests, not pristine research holdouts.",
                  "Within each future fit, priors, decay, feature construction, and preprocessing must use training records only.",
                  "Models stay frozen through each event; no within-event result updates are allowed by this protocol.",
                  "Publication delay is assumed and series groups are provisional; those limitations persist in this plan.",
              ]}
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "fold_membership.csv"
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(output[0]))
        writer.writeheader()
        writer.writerows(output)
    report["fold_membership_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    text = render_plan(report)
    report_dir.mkdir(parents=True, exist_ok=True)
    (report_dir / "evaluation_plan.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    (report_dir / "evaluation_plan.md").write_text(text, encoding="utf-8")
    return text


def render_plan(report):
    lines = ["# Chronological evaluation plan", "", "Candidate fold membership only. Model fitting is not yet enabled.", "",
             report["protocol"]["purpose"], "",
             "| Event fold | Candidate training games | Pending scope review in train | Evaluation games | Cross-region evaluation games |",
             "|---|---:|---:|---:|---:|"]
    lines += [f"| {r['id']} | {r['candidate_training_games']} | {r['training_games_with_pending_scope_review']} | "
              f"{r['evaluation_games']} | {r['evaluation_cross_region_games']} |" for r in report["folds"]]
    lines += ["", "Each fit uses only whole observed series whose assumed result availability precedes the fitting boundary. "
              "The target event is held out in full and the model remains frozen throughout it. A boundary-overlapping series is purged, "
              "including earlier games within that series. Known partial target series are not scored.", "",
              "Unknown future sides cannot become deployable features through historical hindsight. A conditional-on-known-side experiment "
              "must be reported separately or marginalized using a justified pre-draft model.", "",
              "## Remaining constraints", ""]
    lines += ["- " + item for item in report["limitations"]]
    return "\n".join(lines) + "\n"
