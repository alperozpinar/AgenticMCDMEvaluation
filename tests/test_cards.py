"""Card generation, the admissibility gate, and the neutral index assignment.

No network. What is tested is which card shape is valid at which moment, the refusal to
freeze an unfinished checklist, and the labelling invariants that blinding rests on.
"""

from __future__ import annotations

import argparse
import csv
import json

import pytest

from agenticmcdm import harness, schema_check

GENERATORS = ["alpha", "beta", "gamma", "delta", "epsilon"]


def written_card(role="CFO", **overrides):
    """The six fields a generator writes, with no identifier of its own."""
    card = {
        "role": role,
        "professional_background": "Two decades in corporate finance across manufacturing.",
        "decision_priorities": ["capital discipline", "payback horizon", "risk exposure"],
        "risk_attitude": "cautious, treats risk as a graded cost",
        "time_horizon": "three to five years",
        "organizational_constraints": ["fixed annual budget", "board reporting cycle"],
    }
    card.update(overrides)
    return card


# ------------------------------------------------------------------ the two shapes


def test_a_written_card_needs_no_identifier():
    assert schema_check.check_card(written_card(), "CFO", expect_persona_id=False).ok


def test_a_generator_that_labels_its_own_card_is_rejected():
    """The index is drawn after every card passes, so a self-chosen label is a contract break."""
    card = written_card(persona_id="P-CFO-1")
    assert "E_CARD_FIELDS" in schema_check.check_card(
        card, "CFO", expect_persona_id=False).codes


def test_a_frozen_card_without_its_assigned_identifier_is_rejected():
    assert "E_CARD_FIELDS" in schema_check.check_card(written_card(), "CFO").codes


def test_a_frozen_card_with_its_assigned_identifier_passes():
    frozen = {"persona_id": "P-CFO-1", **written_card()}
    assert schema_check.check_card(frozen, "CFO").ok


# ------------------------------------------------------------------ fixtures


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    """A throwaway repository layout holding five generators and fifteen candidates."""
    models = tmp_path / "models"
    models.mkdir()
    header = ("provider,adapter,api_model_id,snapshot,base_url,key_env,role_in_study,"
              "access_date_utc,requested_temperature,top_p,seed,max_output_tokens,"
              "native_json_constraint,tools_enabled,web_enabled,memory_enabled,notes\n")
    rows = "".join(
        f"{g},openai_compatible,model-{g},,,KEY,both,2026-08-06,,,,,false,false,false,false,\n"
        for g in GENERATORS
    )
    (models / "model_registry.csv").write_text(header + rows)

    candidates = tmp_path / "run" / "card_candidates"
    candidates.mkdir(parents=True)
    for generator in GENERATORS:
        for role in harness.ROLES:
            (candidates / f"{generator}_{role}.json").write_text(
                json.dumps(written_card(role)))

    monkeypatch.setattr(harness, "MODELS", models)
    monkeypatch.setattr(harness, "CANDIDATES", candidates)
    monkeypatch.setattr(harness, "WORKSHEET", tmp_path / "run" / "card_admissibility.csv")
    monkeypatch.setattr(harness, "CARDS", tmp_path / "protocol" / "cards")
    return tmp_path


def fill_worksheet(verdict="pass", override=None):
    """Write every checklist cell, optionally failing one (candidate, item) pair."""
    harness.write_worksheet()
    ids = [c["id"] for c in harness.load_checklist()]
    with harness.WORKSHEET.open() as handle:
        rows = list(csv.DictReader(l for l in handle if not l.startswith("#")))
    for row in rows:
        for check_id in ids:
            row[check_id] = verdict
    if override:
        candidate, check_id, value = override
        for row in rows:
            if row["candidate"] == candidate:
                row[check_id] = value
    with harness.WORKSHEET.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["candidate", "generator", "role"] + ids)
        writer.writeheader()
        writer.writerows(rows)


# ------------------------------------------------------------------ the worksheet


def test_the_harness_fills_only_what_it_can_decide(workspace):
    harness.write_worksheet()
    with harness.WORKSHEET.open() as handle:
        rows = list(csv.DictReader(l for l in handle if not l.startswith("#")))
    assert len(rows) == 15
    for row in rows:
        assert row["K1"] == "pass" and row["K2"] == "pass" and row["K11"] == "pass"
        assert all(row[f"K{i}"] == "" for i in range(3, 11))


def test_self_reference_fails_the_blinding_item(workspace):
    (harness.CANDIDATES / "alpha_CFO.json").write_text(json.dumps(
        written_card(risk_attitude="As an AI, I would weigh risk cautiously")))
    harness.write_worksheet()
    with harness.WORKSHEET.open() as handle:
        rows = {r["candidate"]: r for r in csv.DictReader(
            l for l in handle if not l.startswith("#"))}
    assert rows["alpha_CFO.json"]["K11"] == "fail"
    assert rows["beta_CFO.json"]["K11"] == "pass"


# ------------------------------------------------------------------ the freeze gate


def test_freezing_refuses_while_any_item_is_unrecorded(workspace):
    harness.write_worksheet()
    with pytest.raises(SystemExit, match="blank"):
        harness.cmd_freeze_cards(argparse.Namespace(seed=1))


def test_a_failed_item_voids_the_whole_set_of_three(workspace):
    fill_worksheet(override=("gamma_CIO.json", "K7", "fail"))
    with pytest.raises(SystemExit, match="gamma"):
        harness.cmd_freeze_cards(argparse.Namespace(seed=1))
    assert not harness.CARDS.exists() or not list(harness.CARDS.glob("P-*.json"))


def test_freezing_refuses_an_incomplete_candidate_set(workspace):
    fill_worksheet()
    (harness.CANDIDATES / "delta_COO.json").unlink()
    with pytest.raises(SystemExit, match="incomplete"):
        harness.cmd_freeze_cards(argparse.Namespace(seed=1))


# ------------------------------------------------------------------ the assignment


def test_freezing_writes_one_card_per_cell(workspace):
    fill_worksheet()
    harness.cmd_freeze_cards(argparse.Namespace(seed=20260806))
    frozen = sorted(p.name for p in harness.CARDS.glob("P-*.json"))
    assert frozen == sorted(f"P-{role}-{i}.json"
                            for role in harness.ROLES for i in range(1, 6))


def test_every_index_is_used_once_within_each_role(workspace):
    """An index that appeared twice would make two card conditions indistinguishable."""
    fill_worksheet()
    harness.cmd_freeze_cards(argparse.Namespace(seed=20260806))
    with (harness.CARDS / "_assignment.csv").open() as handle:
        rows = list(csv.DictReader(l for l in handle if not l.startswith("#")))
    for role in harness.ROLES:
        in_role = [r for r in rows if r["role"] == role]
        assert sorted(r["persona_id"] for r in in_role) == [
            f"P-{role}-{i}" for i in range(1, 6)]
        assert sorted(r["generator"] for r in in_role) == sorted(GENERATORS)


def test_a_generator_is_not_given_the_same_index_in_every_role(workspace):
    """A generator pinned to one index across roles would be readable straight off the label."""
    fill_worksheet()
    harness.cmd_freeze_cards(argparse.Namespace(seed=20260806))
    with (harness.CARDS / "_assignment.csv").open() as handle:
        rows = list(csv.DictReader(l for l in handle if not l.startswith("#")))
    by_generator: dict[str, set[str]] = {}
    for row in rows:
        by_generator.setdefault(row["generator"], set()).add(row["persona_id"].split("-")[-1])
    assert any(len(indices) > 1 for indices in by_generator.values())


def test_the_frozen_card_carries_its_identifier_and_nothing_else_new(workspace):
    fill_worksheet()
    harness.cmd_freeze_cards(argparse.Namespace(seed=20260806))
    frozen = json.loads((harness.CARDS / "P-CFO-1.json").read_text())
    assert frozen["persona_id"] == "P-CFO-1"
    assert schema_check.check_card(frozen, "CFO").ok
    assert schema_check.find_self_reference(frozen) == []


def test_freezing_twice_is_refused(workspace):
    fill_worksheet()
    harness.cmd_freeze_cards(argparse.Namespace(seed=20260806))
    with pytest.raises(SystemExit, match="frozen once"):
        harness.cmd_freeze_cards(argparse.Namespace(seed=20260806))
