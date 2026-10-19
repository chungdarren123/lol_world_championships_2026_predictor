"""Terminal data preparation and inspectable model diagnostics."""

import argparse
import csv
import json
from pathlib import Path

from worlds_predictor.data.audit import audit_csv, parse_date
from worlds_predictor.data.clean import TABLE_FIELDS, build_tables, export_tables
from worlds_predictor.reporting.audit_report import render_report
from worlds_predictor.reporting.clean_report import render_clean_report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    audit = commands.add_parser("audit", help="Audit an existing CSV without changing it")
    audit.add_argument("csv", type=Path)
    audit.add_argument("--config", type=Path, default=Path("configs/audit_2026.json"))
    audit.add_argument("--source-url", help="Actual download URL, not an assumed original source")
    audit.add_argument("--retrieved-at", help="Known acquisition timestamp with a timezone; omit if unknown")
    audit.add_argument("--output-dir", type=Path, default=Path("reports"))
    clean = commands.add_parser("clean", help="Build canonical game/team/player tables from the audited pool")
    clean.add_argument("csv", type=Path)
    clean.add_argument("--config", type=Path, default=Path("configs/audit_2026.json"))
    clean.add_argument("--identities", type=Path, default=Path("configs/identities_2026.json"))
    clean.add_argument("--source-url")
    clean.add_argument("--retrieved-at")
    clean.add_argument("--output-dir", type=Path, default=Path("data/processed/pre_worlds_2026"))
    clean.add_argument("--report-dir", type=Path, default=Path("reports"))
    for name in ("bt-fit", "bt-synthetic"):
        bt = commands.add_parser(name, help="Static hierarchical Bradley-Terry diagnostic")
        bt.add_argument("--config", type=Path, default=Path("configs/static_bt.json"))
        bt.add_argument("--output-dir", type=Path, default=Path("artifacts/" + name))
        bt.add_argument("--report-dir", type=Path, default=Path("reports"))
        if name == "bt-fit":
            bt.add_argument("--dataset", type=Path, default=Path("data/processed/pre_worlds_2026"))
            bt.add_argument("--prior-multiplier", type=float, default=1.0,
                            help="Multiply both scale hyperprior SDs for a sensitivity fit; use separate output/report directories")
    compare = commands.add_parser("bt-compare", help="Compare baseline and changed-prior diagnostic fits")
    compare.add_argument("--baseline-artifacts", type=Path, default=Path("artifacts/bt-fit"))
    compare.add_argument("--alternate-artifacts", type=Path, default=Path("artifacts/bt-wide"))
    compare.add_argument("--baseline-report", type=Path, default=Path("reports/static_bt.json"))
    compare.add_argument("--alternate-report", type=Path, default=Path("reports/bt-wide/static_bt.json"))
    compare.add_argument("--report-dir", type=Path, default=Path("reports"))
    scope = commands.add_parser("scope-audit", help="Audit expanded historical/current pool without replacing clean tables")
    scope.add_argument("--config", type=Path, default=Path("configs/expanded_scope.json"))
    scope.add_argument("--base-config", type=Path, default=Path("configs/audit_2026.json"))
    scope.add_argument("--identities", type=Path, default=Path("configs/identities_2026.json"))
    scope.add_argument("--output-dir", type=Path, default=Path("data/processed/post_draw_audit"))
    scope.add_argument("--report-dir", type=Path, default=Path("reports"))
    plan = commands.add_parser("evaluation-plan", help="Export chronological candidate folds without fitting models")
    plan.add_argument("--config", type=Path, default=Path("configs/evaluation_protocol.json"))
    plan.add_argument("--dataset", type=Path, default=Path("data/processed/post_draw_audit"))
    plan.add_argument("--output-dir", type=Path, default=Path("artifacts/evaluation_plan"))
    plan.add_argument("--report-dir", type=Path, default=Path("reports"))
    args = parser.parse_args(argv)
    try:
        if args.command == "bt-compare":
            from worlds_predictor.reporting.bt_sensitivity import compare_fits
            result, text = compare_fits(args.baseline_artifacts, args.alternate_artifacts,
                                       args.baseline_report, args.alternate_report, args.report_dir)
            print(text)
            return 0 if result["both_sampling_passed"] else 2
        config = json.loads(args.config.read_text(encoding="utf-8"))
        if args.command == "evaluation-plan":
            from worlds_predictor.evaluation.folds import export_plan
            print(export_plan(args.dataset, config, args.output_dir, args.report_dir))
            return 0
        if args.command == "scope-audit":
            from worlds_predictor.data.expanded_audit import audit_expanded, write_expanded, reconcile_previous_pool
            base = json.loads(args.base_config.read_text(encoding="utf-8"))
            identities = json.loads(args.identities.read_text(encoding="utf-8"))
            candidates, groups, result = audit_expanded(config, base, identities)
            original = Path("data/processed/pre_worlds_2026/manifest.json")
            if original.exists():
                previous = json.loads(original.read_text(encoding="utf-8"))["source"]["sha256"]
                result["previous_2026_source_sha256"] = previous
                result["current_2026_source_changed"] = result.get("sources", {}).get("2026", {}).get("source", {}).get("sha256") != previous
                result["previous_pool_reconciliation"] = reconcile_previous_pool(candidates, original.parent)
            print(write_expanded(candidates, groups, result, args.output_dir, args.report_dir))
            return 2 if result["status"] == "blocked" else 0
        if args.command.startswith("bt-"):
            from worlds_predictor.models.bt_workflow import run_fit, run_synthetic
            if args.command == "bt-fit":
                config["region_scale_prior"] *= args.prior_multiplier
                config["team_scale_prior"] *= args.prior_multiplier
                config["prior_multiplier"] = args.prior_multiplier
                result, text = run_fit(args.dataset, config, args.output_dir, args.report_dir)
            else:
                result, text = run_synthetic(config, args.output_dir, args.report_dir)
            print(text)
            passed = result["sampling"]["passed"] and result.get("recovery", {}).get("passed", True)
            return 0 if passed else 2
        if args.retrieved_at:
            timestamp, naive = parse_date(args.retrieved_at, "UTC")
            if timestamp is None or naive:
                raise ValueError("--retrieved-at must be an ISO timestamp with timezone.")
        if args.command == "clean":
            identities = json.loads(args.identities.read_text(encoding="utf-8"))
            targets = [args.output_dir / (name + ".csv") for name in TABLE_FIELDS]
            targets += [args.output_dir / "manifest.json", args.report_dir / "clean_tables.json", args.report_dir / "clean_tables.md"]
            if args.csv.resolve() in {p.resolve() for p in targets}:
                raise ValueError("Generated output must not overwrite the source file.")
            tables, summary = build_tables(args.csv, config, identities, args.source_url, args.retrieved_at)
            manifest = export_tables(tables, summary, args.output_dir)
            args.report_dir.mkdir(parents=True, exist_ok=True)
            (args.report_dir / "clean_tables.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            text = render_clean_report(manifest)
            (args.report_dir / "clean_tables.md").write_text(text, encoding="utf-8")
            print(text)
            print(f"Saved canonical tables in {args.output_dir}")
            return 0
        targets = [args.output_dir / "data_audit.json", args.output_dir / "data_audit.md"]
        if args.csv.resolve() in {p.resolve() for p in targets}:
            raise ValueError("An output report must not overwrite the source file.")
        report = audit_csv(args.csv, config, args.source_url, args.retrieved_at)
    except (OSError, ValueError, KeyError, csv.Error, ImportError) as error:
        parser.exit(2, f"Command could not run: {error}\n")
    report["config_source"] = str(args.config)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    targets[0].write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    text = render_report(report)
    targets[1].write_text(text, encoding="utf-8")
    print(text)
    print(f"Saved {targets[0]} and {targets[1]}")
    return 2 if report["status"] == "blocked" else 0
