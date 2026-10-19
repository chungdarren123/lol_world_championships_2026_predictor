"""Reconstruct series without promoting sequence inference to official format evidence."""

import hashlib
import re
from collections import defaultdict
from urllib.parse import parse_qs, urlparse

from .audit import parse_date


def stable_id(prefix, *values):
    import json
    payload = json.dumps(values, ensure_ascii=False, separators=(",", ":"))
    return prefix + ":" + hashlib.sha256(payload.encode()).hexdigest()[:24]


def source_reference(game):
    if game.get("source_series_id"):
        return "explicit:" + game["source_series_id"], "explicit_source_field", ""
    url = urlparse(game.get("source_url", ""))
    if game["league"] == "LPL":
        encoded = re.fullmatch(r"(\d+)-(\d+)_game_(\d+)", game["source_game_id"])
        bmid = parse_qs(url.query).get("bmid", []) if url.hostname == "lpl.qq.com" else []
        if encoded:
            a, b, n = encoded.groups()
            if a != b or int(n) != game["game_number"] or (bmid and bmid != [a]):
                return "", "", "inconsistent_lpl_match_reference"
            return "lpl:" + a, "encoded_source_match_reference", ""
        if len(bmid) == 1 and bmid[0].isdigit():
            return "lpl:" + bmid[0], "shared_source_match_url", ""
    return "", "", ""


def resolve_series(games, policy):
    gap = policy["maximum_continuation_gap_hours"]
    if not isinstance(gap, (int, float)) or gap <= 0:
        raise ValueError("Series continuation gap must be positive.")
    overrides = {}
    for rule in policy.get("overrides", []):
        if not rule.get("evidence_url") or not rule.get("series_reference"):
            raise ValueError("A series override requires a reference and evidence URL.")
        if rule.get("best_of") is not None and (not isinstance(rule["best_of"], int) or rule["best_of"] <= 0 or rule["best_of"] % 2 != 1):
            raise ValueError("A reviewed best-of must be a positive odd integer.")
        for key in rule["game_ids"]:
            if key in overrides:
                raise ValueError("Duplicate game ID in series overrides.")
            overrides[key] = rule
    unknown = set(overrides) - {g["game_id"] for g in games}
    if unknown:
        raise ValueError(f"Series overrides reference absent games: {sorted(unknown)}")
    explicit, sequences = defaultdict(list), defaultdict(list)
    issues = []
    for game in games:
        pair = tuple(sorted((game["blue_team_id"], game["red_team_id"])))
        context = (game["league"], game["source_season"], game["stage"], game["split"], game["season_exception"])
        reference, method, issue = source_reference(game)
        evidence = ""
        if game["game_id"] in overrides:
            override = overrides[game["game_id"]]
            reference, method, evidence = override["series_reference"], "reviewed_override", override["evidence_url"]
            issue = ""
        if issue:
            issues.append({"game_id": game["game_id"], "issue": issue})
        if reference:
            # Do not split a reused match reference by team pair: expose it as a conflict.
            explicit[(context, reference)].append((game, method, evidence))
        else:
            sequences[(context, pair)].append((game, issue))
    groups = []
    for (context, ref), records in sorted(explicit.items()):
        groups.append((records, "source_reference", ref, []))
    for (context, pair), records in sorted(sequences.items()):
        current = []
        inherited = []
        previous = None
        for game, source_issue in sorted(records, key=lambda r: (r[0]["started_at_utc"], r[0]["game_id"])):
            at, _ = parse_date(game["started_at_utc"], "UTC")
            continuation = (previous is not None and game["game_number"] is not None
                            and previous["game_number"] is not None
                            and game["game_number"] == previous["game_number"] + 1
                            and 0 < (at - parse_date(previous["started_at_utc"], "UTC")[0]).total_seconds() <= gap * 3600)
            if not continuation:
                if current:
                    groups.append((current, "sequence_inferred", "", inherited))
                current, inherited = [], []
            current.append((game, "consecutive_game_numbers", ""))
            if source_issue:
                inherited.append(source_issue)
            previous = game
        if current:
            groups.append((current, "sequence_inferred", "", inherited))
    series = []
    for records, method, ref, inherited in groups:
        records.sort(key=lambda r: (r[0]["started_at_utc"], r[0]["game_id"]))
        ordered = [r[0] for r in records]
        first = ordered[0]
        numbers = [g["game_number"] for g in ordered]
        pairs = {tuple(sorted((g["blue_team_id"], g["red_team_id"]))) for g in ordered}
        problems = list(dict.fromkeys(inherited))
        if numbers != list(range(1, len(numbers) + 1)):
            problems.append("missing_or_nonconsecutive_game_numbers")
        if len(pairs) != 1:
            problems.append("source_reference_has_multiple_team_pairs")
        if len({g["started_at_utc"] for g in ordered}) != len(ordered):
            problems.append("ambiguous_game_order")
        if numbers and all(n is not None for n in numbers) and max(numbers) > 5:
            problems.append("more_than_five_games_requires_review")
        series_id = stable_id("series", first["league"], ref or first["game_id"], first["source_season"], first["stage"], first["split"])
        a, b = sorted((first["blue_team_id"], first["red_team_id"]))
        status = "needs_review" if problems else "source_supported" if method == "source_reference" else "provisional_sequence"
        for game in ordered:
            game.update(series_id=series_id, series_method=method, series_status=status)
        score_a = sum(g["winner_team_id"] == a for g in ordered)
        score_b = sum(g["winner_team_id"] == b for g in ordered)
        reviewed = [overrides[g["game_id"]] for g in ordered if g["game_id"] in overrides]
        best_of = reviewed[0].get("best_of") if reviewed else None
        known_missing = reviewed[0].get("known_missing_game_numbers", []) if reviewed else []
        if known_missing:
            if set(known_missing) & set(numbers):
                raise ValueError("A reviewed missing game now exists; update the stale override.")
            if (len(pairs) == 1 and problems == ["missing_or_nonconsecutive_game_numbers"]
                    and sorted(numbers + known_missing) == list(range(1, max(numbers + known_missing) + 1))):
                status = "source_supported_partial"
                problems = ["known_missing_game_numbers:" + ",".join(map(str, known_missing))]
                for game in ordered:
                    game["series_status"] = status
        series.append({
            "series_id": series_id, "league": first["league"], "source_season": first["source_season"],
            "stage": first["stage"], "split": first["split"], "team_a_id": a, "team_b_id": b,
            "first_observed_game_at_utc": first["started_at_utc"], "last_observed_game_at_utc": ordered[-1]["started_at_utc"],
            "observed_games": len(ordered), "observed_wins_a": score_a, "observed_wins_b": score_b,
            "best_of": best_of, "source_observations_complete": False if known_missing else None, "official_winner_team_id": None,
            "resolution_method": method, "resolution_status": status,
            "source_reference": ref, "source_reference_method": records[0][1] if ref else "",
            "evidence_url": records[0][2], "issues": ";".join(problems),
        })
        for issue in problems:
            issues.append({"series_id": series_id, "issue": issue})
    return sorted(series, key=lambda r: (r["first_observed_game_at_utc"], r["series_id"])), issues
