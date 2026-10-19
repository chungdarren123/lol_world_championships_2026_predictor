"""Load an integrity-checked, explicitly limited 2026 diagnostic dataset."""

from collections import Counter, defaultdict
import csv
from datetime import datetime, timedelta
import hashlib
import io
import json
from pathlib import Path


def instant(value):
    at = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if at.tzinfo is None:
        raise ValueError("Expected timezone-aware timestamp.")
    return at


def read_dataset(folder, delay_minutes=60):
    folder = Path(folder)
    raw_manifest = (folder / "manifest.json").read_bytes()
    manifest = json.loads(raw_manifest)
    tables, hashes = {}, {}
    for name in ("games", "team_games", "teams"):
        raw = (folder / (name + ".csv")).read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        if digest != manifest["output_sha256"][name + ".csv"]:
            raise ValueError(f"Checksum mismatch: {name}.csv")
        hashes[name + ".csv"] = digest
        tables[name] = list(csv.DictReader(io.StringIO(raw.decode("utf-8-sig"))))
    selection = manifest["selection_config"]
    if selection["season"] != 2026 or selection["duration_unit"] != "seconds":
        raise ValueError("This diagnostic loader supports the audited 2026/seconds snapshot only.")
    records, excluded = prepare_records(tables, selection["cutoff_utc"], delay_minutes)
    return records, {"dataset_manifest_sha256": hashlib.sha256(raw_manifest).hexdigest(),
                     "input_sha256": hashes, "raw_source": manifest["source"],
                     "selection_config": selection, "excluded": excluded,
                     "input_games": len(tables["games"])}


def prepare_records(tables, cutoff, delay_minutes=60):
    """No silent missing-region imputation or membership lookup from later games."""
    if delay_minutes < 0:
        raise ValueError("Result delay must be nonnegative.")
    cutoff = instant(cutoff)
    names = {r["team_id"]: r["display_name"] for r in tables["teams"]}
    sides = {}
    for row in tables["team_games"]:
        key = (row["game_id"], row["team_id"])
        if key in sides:
            raise ValueError("Duplicate team-game key.")
        sides[key] = row
    seen, records, excluded = set(), [], Counter()
    for game in sorted(tables["games"], key=lambda r: (r["started_at_utc"], r["game_id"])):
        gid = game["game_id"]
        if gid in seen:
            raise ValueError("Duplicate game key.")
        seen.add(gid)
        start = instant(game["started_at_utc"])
        if start >= cutoff or start.year != 2026 or int(game["played_year"]) != 2026:
            raise ValueError("Game outside the diagnostic season/cutoff.")
        if game["league"].casefold() in {"worlds", "wlds", "wcs"}:
            raise ValueError("Existing pre-Play-Ins snapshot must not contain Worlds games.")
        blue, red = game["blue_team_id"], game["red_team_id"]
        if blue == red or game["blue_won"] not in ("0", "1", 0, 1):
            raise ValueError("Invalid game teams/outcome.")
        br, rr = (sides[(gid, team)] for team in (blue, red))
        durations = []
        for team_row in (br, rr):
            if not team_row["region"]:
                raise ValueError("Region unresolved; review identity evidence before fitting.")
            if instant(team_row["region_evidence_observed_at_utc"]) > start:
                raise ValueError("Future region evidence.")
            duration = float(team_row["observed_duration_source_units"])
            if not 0 < duration < 86400:
                raise ValueError("Invalid/missing duration for assumed availability.")
            durations.append(duration)
        if durations[0] != durations[1]:
            raise ValueError("Inconsistent game durations.")
        if start + timedelta(seconds=durations[0], minutes=delay_minutes) >= cutoff:
            excluded["assumed_result_not_available_before_cutoff"] += 1
            continue
        # A region change creates a separate within-region entity rather than
        # retroactively assigning earlier matches to the latest membership.
        entities = [(team, 2026, row["region"]) for team, row in ((blue, br), (red, rr))]
        records.append({"game_id": gid, "series_id": game["series_id"],
                        "a": entities[0], "b": entities[1], "y": int(game["blue_won"]),
                        "name_a": names[blue], "name_b": names[red],
                        "league": game["league"], "stage": game["stage"]})
    if len(sides) != 2 * len(seen):
        raise ValueError("Expected precisely two team rows per game.")
    if not records:
        raise ValueError("No eligible games.")
    return records, dict(excluded)


def connected_components(nodes, edges):
    neighbours = {node: set() for node in nodes}
    for a, b in edges:
        neighbours[a].add(b)
        neighbours[b].add(a)
    groups, remaining = [], set(nodes)
    while remaining:
        frontier, group = [min(remaining)], set()
        while frontier:
            node = frontier.pop()
            if node not in group:
                group.add(node)
                frontier.extend(neighbours[node] - group)
        remaining -= group
        groups.append(sorted(group))
    return groups


def encode_records(records):
    """Aggregate exchangeable games exactly, not as a time/series approximation."""
    entities = sorted({r[k] for r in records for k in ("a", "b")})
    regions = sorted({e[2] for e in entities})
    index = {e: i for i, e in enumerate(entities)}
    names, counts, links, pair_counts = {}, Counter(), Counter(), defaultdict(lambda: [0, 0])
    for row in records:
        for k in ("a", "b"):
            names[row[k]] = row["name_" + k]
            counts[row[k]] += 1
        a, b = index[row["a"]], index[row["b"]]
        low, high = sorted((a, b))
        pair_counts[(low, high)][0] += row["y"] if a == low else 1 - row["y"]
        pair_counts[(low, high)][1] += 1
        ra, rb = row["a"][2], row["b"][2]
        if ra != rb:
            links[tuple(sorted((ra, rb)))] += 1
    pairs = [{"a": a, "b": b, "wins_a": wins, "games": n}
             for (a, b), (wins, n) in sorted(pair_counts.items())]
    region_components = connected_components(regions, links)
    team_components = connected_components(range(len(entities)), pair_counts)
    return {"entities": entities, "regions": regions, "pairs": pairs,
            "names": [names[e] for e in entities], "games_by_entity": [counts[e] for e in entities],
            "region_index": [regions.index(e[2]) for e in entities],
            "coverage": {"games": len(records), "series": len({r["series_id"] for r in records}),
                         "teams": len(entities), "regions": len(regions), "matchup_pairs": len(pairs),
                         "cross_region_games": sum(links.values()),
                         "cross_region_links": [{"region_a": a, "region_b": b, "games": n}
                                                for (a, b), n in sorted(links.items())],
                         "region_components": region_components,
                         "team_component_sizes": sorted(map(len, team_components), reverse=True)}}
