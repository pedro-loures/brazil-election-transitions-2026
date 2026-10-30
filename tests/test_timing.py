import csv
import json

import pandas as pd
import pytest

from elections.timing import audit_events, EVENT_COLUMNS, parse_timestamp


def write_events(path, timestamps, section=1):
    with path.open("w") as f:
        writer = csv.DictWriter(f, fieldnames=EVENT_COLUMNS)
        writer.writeheader()
        for i, timestamp in enumerate(timestamps):
            writer.writerow(dict(zip(EVENT_COLUMNS,
                ["AC", 1120, 1, section, 2, "machine1", str(i), "vote_computed", timestamp])))


def test_requires_timezone_and_converts_to_brasilia():
    assert parse_timestamp("2026-10-25T15:30:00-05:00").hour == 17
    with pytest.raises(ValueError, match="explicit UTC offset"):
        parse_timestamp("2026-10-25T15:30:00")


def test_missing_logs_are_coverage_failures_and_counts_must_reconcile(tmp_path):
    events = tmp_path / "events.csv"
    write_events(events, ["2026-10-25T08:00:00-05:00", "2026-10-25T15:30:00-05:00"])
    expected = pd.DataFrame([dict(uf="AC", municipality_code=1120, zone=1, section=s,
                                  round=2, turnout=2) for s in [1, 2]])
    summary = audit_events(events, expected, tmp_path / "out", {"2": "2026-10-25"})
    assert not summary["complete"]
    result = pd.read_csv(tmp_path / "out/timing_municipalities.csv").iloc[0]
    assert result.turnout_coverage == .5
    assert result.votes_at_or_after_17_brt_in_reconciled_sections == 1
    assert result.votes_before_11_brt_in_reconciled_sections == 1


def test_wrong_election_date_is_rejected(tmp_path):
    events = tmp_path / "events.csv"
    write_events(events, ["2026-10-24T08:00:00-03:00"])
    with pytest.raises(ValueError, match="outside"):
        audit_events(events, pd.DataFrame(), tmp_path / "out", {"2": "2026-10-25"})
