"""Streaming timing audit for normalized, section-sorted voting-machine events.

Raw TSE log extraction is a separate, version-specific operation. This module
requires explicit timestamps with UTC offsets and never infers a ballot choice.
"""
import csv
from datetime import datetime
from itertools import groupby
import json
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

from .data import ROUND_KEY

EVENT_COLUMNS = ROUND_KEY + ["machine_id", "event_id", "event_type", "timestamp"]
BRT = ZoneInfo("America/Sao_Paulo")


def parse_timestamp(value):
    timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if timestamp.utcoffset() is None:
        raise ValueError("Log timestamps need an explicit UTC offset; machine local time cannot be assumed to be BRT")
    return timestamp.astimezone(BRT)


def audit_events(events, expected, output, election_dates=None):
    """Read a CSV sorted lexicographically by uf, municipality, zone, section, round.

    IDs identify machine events, not voters. Repeated copies of the same machine
    event are counted once; conflicting copies fail. Unreconciled sections are
    retained as coverage failures, never interpreted as zero after-hours votes.
    """
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    rows, previous = [], None
    with Path(events).open(newline="", encoding="utf-8") as stream:
        reader = csv.DictReader(stream)
        if not set(EVENT_COLUMNS).issubset(reader.fieldnames or []):
            raise ValueError(f"Event CSV requires {EVENT_COLUMNS}")

        def key(row):
            return (row["uf"], *(int(row[k]) for k in ROUND_KEY[1:]))

        for group_key, records in groupby(reader, key):
            if previous is not None and group_key <= previous:
                raise ValueError("Event CSV must be sorted by uf, municipality_code, zone, section, round")
            previous = group_key
            unique = {}
            for event in records:
                if event["event_type"] != "vote_computed":
                    continue
                if not event["machine_id"] or not event["event_id"]:
                    raise ValueError("Each vote event requires machine_id and event_id")
                identifier = event["machine_id"], event["event_id"]
                timestamp = parse_timestamp(event["timestamp"])
                if election_dates and timestamp.date().isoformat() != election_dates[str(group_key[-1])]:
                    raise ValueError("Vote event is outside the specified election date")
                if identifier in unique and unique[identifier] != timestamp:
                    raise ValueError("Conflicting duplicate machine event")
                unique[identifier] = timestamp
            times = list(unique.values())
            after = sum(t.hour >= 17 for t in times)
            before = sum(t.hour < 11 for t in times)
            rows.append({**dict(zip(ROUND_KEY, group_key)), "logged_votes": len(times),
                         "votes_at_or_after_17_brt": after, "votes_before_11_brt": before,
                         "machine_count": len({k[0] for k in unique}),
                         "first_vote_brt": min(times).isoformat() if times else None,
                         "last_vote_brt": max(times).isoformat() if times else None})
    expected = expected[expected.uf.ne("ZZ")][ROUND_KEY + ["turnout"]].copy()
    if expected.duplicated(ROUND_KEY).any():
        raise ValueError("Expected turnout must contain one record per section-round")
    columns = ROUND_KEY + ["logged_votes", "votes_at_or_after_17_brt", "votes_before_11_brt",
                           "machine_count", "first_vote_brt", "last_vote_brt"]
    observed = pd.DataFrame(rows, columns=columns)
    audit = expected.merge(observed, on=ROUND_KEY, how="outer", validate="one_to_one", indicator=True)
    audit["log_present"] = audit._merge.ne("left_only")
    audit["expected_present"] = audit._merge.ne("right_only")
    audit["count_reconciled"] = audit.logged_votes.eq(audit.turnout) & audit.log_present & audit.expected_present
    audit["vote_count_difference"] = audit.logged_votes-audit.turnout
    audit.drop(columns="_merge").to_csv(output / "timing_sections.csv.gz", index=False)
    municipal = []
    for (uf, code, turn), group in audit.groupby(["uf", "municipality_code", "round"]):
        valid = group[group.count_reconciled]
        total = group.loc[group.expected_present, "turnout"].sum()
        municipal.append({"uf": uf, "municipality_code": code, "round": turn,
            "expected_sections": int(group.expected_present.sum()),
            "sections_with_logs": int(group.log_present.sum()),
            "reconciled_sections": len(valid), "expected_turnout": int(total),
            "reconciled_logged_votes": int(valid.logged_votes.sum()),
            "turnout_coverage": float(valid.logged_votes.sum()/total) if total else None,
            "votes_at_or_after_17_brt_in_reconciled_sections": int(valid.votes_at_or_after_17_brt.sum()),
            "votes_before_11_brt_in_reconciled_sections": int(valid.votes_before_11_brt.sum()),
            "complete": bool(group.count_reconciled.all())})
    result = pd.DataFrame(municipal)
    result.to_csv(output / "timing_municipalities.csv", index=False)
    summary = {"timestamp_basis": "America/Sao_Paulo (UTC-03:00 for the specified elections)",
               "after_cutoff_definition": "timestamp >= 17:00:00 BRT",
               "event_source": str(Path(events).resolve()),
               "expected_section_rounds": len(expected), "log_section_rounds": len(observed),
               "reconciled_section_rounds": int(audit.count_reconciled.sum()),
               "complete": bool(audit.count_reconciled.all()),
               "raw_log_extraction": "Not performed by this command; normalized events are an input"}
    (output / "timing_summary.json").write_text(json.dumps(summary, indent=2))
    return summary
