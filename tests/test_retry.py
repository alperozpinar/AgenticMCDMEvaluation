"""Retry classification, wait computation and resume behaviour.

None of these touch the network. What is tested is the decision to retry, the wait chosen
before it, and the rule that decides which scheduled slots may be called again.
"""

from __future__ import annotations

import csv
import datetime as dt
import email.utils

import pytest

from agenticmcdm import harness, providers
from agenticmcdm.providers import TransportError


# ------------------------------------------------------------------ classification


@pytest.mark.parametrize("status", [408, 409, 425, 429, 500, 502, 503, 504])
def test_moment_describing_statuses_are_retried(status):
    assert providers.is_retryable(TransportError("x", status=status))


@pytest.mark.parametrize("status", [400, 401, 403, 404, 405, 413, 422])
def test_request_describing_statuses_are_not_retried(status):
    """Repeating a rejected request changes nothing except the bill."""
    assert not providers.is_retryable(TransportError("x", status=status))


def test_failure_below_http_is_retried():
    """A timeout or a dropped connection carries no status and deserves the one retry."""
    assert providers.is_retryable(TransportError("connection reset"))


# ------------------------------------------------------------------ wait


def test_provider_retry_after_wins_over_the_default():
    assert providers.retry_delay(TransportError("x", status=429, retry_after=43.0)) == 43.0


def test_retry_after_is_capped():
    error = TransportError("x", status=429, retry_after=9999.0)
    assert providers.retry_delay(error) == providers.RETRY_CAP_SECONDS


def test_default_wait_applies_when_the_provider_sent_none():
    assert providers.retry_delay(TransportError("x", status=503)) == providers.RETRY_BASE_SECONDS


def test_negative_retry_after_does_not_produce_a_negative_wait():
    assert providers.retry_delay(TransportError("x", status=429, retry_after=-5.0)) == 0.0


# ------------------------------------------------------------------ Retry-After parsing


def test_retry_after_in_seconds_is_read():
    assert providers._retry_after_seconds({"Retry-After": "30"}) == 30.0


def test_retry_after_as_an_http_date_is_read():
    """The header may carry a date instead of a count, and providers do send both."""
    when = dt.datetime.now(dt.timezone.utc) + dt.timedelta(seconds=60)
    header = email.utils.format_datetime(when)
    seconds = providers._retry_after_seconds({"Retry-After": header})
    assert seconds is not None and 50 <= seconds <= 61


def test_absent_and_unparseable_retry_after_both_yield_none():
    assert providers._retry_after_seconds({}) is None
    assert providers._retry_after_seconds({"Retry-After": "soon"}) is None


def test_a_past_date_yields_zero_rather_than_a_negative_wait():
    past = email.utils.format_datetime(
        dt.datetime.now(dt.timezone.utc) - dt.timedelta(seconds=120))
    assert providers._retry_after_seconds({"Retry-After": past}) == 0.0


# ------------------------------------------------------------------ resume


def write_ledger(tmp_path, rows):
    """Point the harness at a throwaway data directory holding the given ledger rows."""
    data = tmp_path / "data"
    data.mkdir()
    with (data / "ledger.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=harness.LEDGER_FIELDS,
                                extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
    return data


def test_no_ledger_means_nothing_is_complete(tmp_path, monkeypatch):
    monkeypatch.setattr(harness, "DATA", tmp_path / "absent")
    assert harness.completed_run_ids() == set()


def test_a_slot_that_produced_output_is_not_called_again(tmp_path, monkeypatch):
    data = write_ledger(tmp_path, [
        {"run_id": "R1", "attempt_type": "initial", "transport_status": "success"},
    ])
    monkeypatch.setattr(harness, "DATA", data)
    assert harness.completed_run_ids() == {"R1"}


def test_a_slot_whose_retry_was_spent_is_not_called_again(tmp_path, monkeypatch):
    """Two failed attempts exhaust the slot. A third request is not the protocol's to make."""
    data = write_ledger(tmp_path, [
        {"run_id": "R2", "attempt_type": "initial", "transport_status": "transport_error_503"},
        {"run_id": "R2", "attempt_type": "transport_retry",
         "transport_status": "transport_error_503"},
    ])
    monkeypatch.setattr(harness, "DATA", data)
    assert harness.completed_run_ids() == {"R2"}


def test_a_single_failed_first_attempt_is_resumable(tmp_path, monkeypatch):
    """This is what an aborted round leaves behind, and it must be picked up on the rerun."""
    data = write_ledger(tmp_path, [
        {"run_id": "R3", "attempt_type": "initial", "transport_status": "transport_error_401"},
    ])
    monkeypatch.setattr(harness, "DATA", data)
    assert harness.completed_run_ids() == set()


def test_a_repair_row_alone_does_not_mark_a_slot_complete(tmp_path, monkeypatch):
    """Repair output lives in a separate population and never stands in for a primary call."""
    data = write_ledger(tmp_path, [
        {"run_id": "R4", "attempt_type": "schema_repair", "transport_status": "success"},
    ])
    monkeypatch.setattr(harness, "DATA", data)
    assert harness.completed_run_ids() == set()
