"""Explicit identity corrections and region evidence that can be queried as of a game."""

from collections import defaultdict

from .audit import missing, parse_date


class IdentityResolver:
    def __init__(self, config):
        self.config = config
        self.rules = config.get("team_aliases", [])
        self.evidence = defaultdict(list)
        for rule in self.rules:
            start, _ = parse_date(rule["valid_from_utc"], "UTC")
            end, _ = parse_date(rule["valid_until_utc_exclusive"], "UTC")
            if start is None or end is None or start >= end or not rule.get("evidence") or not rule.get("source_url"):
                raise ValueError("Identity aliases need a valid date window and recorded evidence.")
            if rule["source_team_id"] == rule["canonical_team_id"]:
                raise ValueError("An alias cannot map a team ID to itself.")
        targets = {r["canonical_team_id"] for r in self.rules}
        if targets & {r["source_team_id"] for r in self.rules}:
            raise ValueError("Alias chains and cycles are not permitted; map directly to the canonical team.")

    def team(self, source_id, source_name, league, date):
        if missing(source_id):
            # A name key is explicit and distinct from provider IDs, never fuzzy matched.
            return "name:" + source_name, source_name, "name_fallback"
        matches = []
        for rule in self.rules:
            start, _ = parse_date(rule["valid_from_utc"], "UTC")
            end, _ = parse_date(rule["valid_until_utc_exclusive"], "UTC")
            if (source_id == rule["source_team_id"] and league in rule["source_leagues"]
                    and start <= date < end):
                matches.append(rule)
        if len(matches) > 1:
            raise ValueError("Overlapping aliases match one source team record.")
        if matches:
            return matches[0]["canonical_team_id"], matches[0]["canonical_name"], "reviewed_alias"
        return source_id, source_name, "provider_id"

    def observe_region(self, team_id, region, date, source_league, source_game_id, source_url=""):
        self.evidence[team_id].append({
            "team_id": team_id, "region": region, "observed_at_utc": date.isoformat(),
            "source_league": source_league, "source_game_id": source_game_id,
            "source_url": source_url,
        })

    def region_at(self, team_id, date):
        records = [r for r in self.evidence[team_id]
                   if parse_date(r["observed_at_utc"], "UTC")[0] <= date]
        regions = {r["region"] for r in records}
        if not regions:
            return "", "unresolved", "", "", ""
        if len(regions) > 1:
            return "", "conflicting_evidence", "", "", ""
        first = min(records, key=lambda r: (r["observed_at_utc"], r["source_game_id"]))
        return first["region"], "membership_at_or_before_game", first["observed_at_utc"], first["source_league"], first["source_game_id"]

    def region_table(self, team_ids):
        """One earliest observation per team/region/league; no match results retained."""
        rows = []
        for team in sorted(team_ids):
            grouped = {}
            for record in self.evidence[team]:
                key = (record["region"], record["source_league"])
                if key not in grouped or record["observed_at_utc"] < grouped[key]["observed_at_utc"]:
                    grouped[key] = record
            rows.extend(grouped[k] for k in sorted(grouped))
        return rows
