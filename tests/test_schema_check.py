"""Validation tests. Every rule the protocol states should reject something."""

from __future__ import annotations

import itertools

import pytest

from agenticmcdm.schema_check import (
    check_card,
    check_decision,
    find_self_reference,
)

CODES = ["C1", "C2", "C3", "C4", "C5", "C6"]
PAIRS = [f"{a}_{b}" for a, b in itertools.combinations(CODES, 2)]


def good_response(**overrides):
    comparisons = [
        {"pair_id": f"{a}_{b}", "criterion_a": a, "criterion_b": b,
         "preferred": a, "intensity": "moderate", "reason": "cost dominates this trade-off"}
        for a, b in itertools.combinations(CODES, 2)
    ]
    payload = {
        "criterion_comparisons": comparisons,
        "declared_priority_order": ["C1", "C4", "C2"],
    }
    payload.update(overrides)
    return payload


def test_well_formed_response_passes():
    assert check_decision(good_response(), PAIRS).ok


def test_fourteen_pairs_is_rejected():
    r = good_response()
    r["criterion_comparisons"] = r["criterion_comparisons"][:-1]
    result = check_decision(r, PAIRS)
    assert not result.ok
    assert "E_COUNT" in result.codes and "E_PAIR_MISSING" in result.codes


def test_duplicated_pair_is_rejected():
    r = good_response()
    r["criterion_comparisons"][1] = dict(r["criterion_comparisons"][0])
    assert "E_PAIR_DUPLICATE" in check_decision(r, PAIRS).codes


def test_equal_with_a_direction_is_rejected():
    r = good_response()
    r["criterion_comparisons"][0]["intensity"] = "equal"
    assert "E_NEUTRAL" in check_decision(r, PAIRS).codes


def test_equal_with_neutral_is_accepted():
    r = good_response()
    r["criterion_comparisons"][0].update(intensity="equal", preferred="NEUTRAL")
    assert check_decision(r, PAIRS).ok


def test_preferred_outside_the_pair_is_rejected():
    r = good_response()
    r["criterion_comparisons"][0]["preferred"] = "C6"
    assert "E_PREFERRED" in check_decision(r, PAIRS).codes


def test_off_scale_intensity_is_rejected():
    r = good_response()
    r["criterion_comparisons"][0]["intensity"] = "quite_strong"
    assert "E_INTENSITY" in check_decision(r, PAIRS).codes


def test_overlong_reason_is_rejected():
    r = good_response()
    r["criterion_comparisons"][0]["reason"] = " ".join(["word"] * 26)
    assert "E_REASON_LENGTH" in check_decision(r, PAIRS).codes


def test_reason_at_the_limit_is_accepted():
    r = good_response()
    r["criterion_comparisons"][0]["reason"] = " ".join(["word"] * 25)
    assert check_decision(r, PAIRS).ok


@pytest.mark.parametrize("order,code", [
    (["C1", "C2"], "E_PRIORITY_COUNT"),
    (["C1", "C1", "C2"], "E_PRIORITY_CODES"),
    (["C1", "C2", "C9"], "E_PRIORITY_CODES"),
])
def test_declared_priority_rules(order, code):
    assert code in check_decision(good_response(declared_priority_order=order), PAIRS).codes


def test_extra_field_is_rejected():
    r = good_response()
    r["criterion_weights"] = [0.2] * 6
    assert "E_EXTRA_FIELD" in check_decision(r, PAIRS).codes


def test_ranking_of_alternatives_is_rejected_as_an_extra_field():
    r = good_response()
    r["ranking"] = ["A", "D", "C", "B"]
    assert "E_EXTRA_FIELD" in check_decision(r, PAIRS).codes


def test_persona_id_from_the_model_is_rejected_as_an_extra_field():
    """The harness attaches persona_id; a model that volunteers it broke the contract."""
    assert "E_EXTRA_FIELD" in check_decision(good_response(persona_id="P-CFO-3"), PAIRS).codes


def test_an_echoed_prompt_version_is_rejected_as_an_extra_field():
    """Echoing a constant tested copying rather than judgment, so it left the contract."""
    assert "E_EXTRA_FIELD" in check_decision(
        good_response(schema_version="structured_v2_icaira"), PAIRS).codes


# ------------------------------------------------------------------ cards


def good_card(**overrides):
    card = {
        "persona_id": "P-CFO-1",
        "role": "CFO",
        "professional_background": "Two decades in corporate finance across manufacturing.",
        "decision_priorities": ["capital discipline", "payback horizon", "risk exposure"],
        "risk_attitude": "cautious, treats risk as a graded cost",
        "time_horizon": "three to five years",
        "organizational_constraints": ["fixed annual budget", "board reporting cycle"],
    }
    card.update(overrides)
    return card


def test_well_formed_card_passes():
    assert check_card(good_card(), "CFO").ok


def test_card_role_mismatch_is_rejected():
    assert "E_CARD_ROLE" in check_card(good_card(), "CIO").codes


def test_card_with_too_few_priorities_is_rejected():
    assert "E_CARD_PRIORITIES" in check_card(good_card(decision_priorities=["a", "b"]),
                                             "CFO").codes


def test_card_with_an_extra_field_is_rejected():
    card = good_card()
    card["age"] = 52
    assert "E_CARD_FIELDS" in check_card(card, "CFO").codes


def test_self_reference_is_found_and_voids_the_card():
    card = good_card(risk_attitude="As an AI, I would weigh risk cautiously")
    hits = find_self_reference(card)
    assert hits and "risk_attitude" in hits[0]


def test_clean_card_has_no_self_reference():
    assert find_self_reference(good_card()) == []
