"""The card overlap descriptive: the measure itself and the three-cell decomposition."""

from __future__ import annotations

import pytest

from agenticmcdm.card_descriptives import content_words, jaccard, summarize


def card(role, text, priorities=("alpha", "beta", "gamma")):
    return {
        "persona_id": f"P-{role}-1",
        "role": role,
        "professional_background": text,
        "decision_priorities": list(priorities),
        "risk_attitude": "",
        "time_horizon": "",
        "organizational_constraints": [],
    }


# ------------------------------------------------------------------ the measure


def test_identical_sets_overlap_completely():
    assert jaccard({"a", "b"}, {"a", "b"}) == 1.0


def test_disjoint_sets_do_not_overlap():
    assert jaccard({"a"}, {"b"}) == 0.0


def test_overlap_is_symmetric():
    left, right = {"a", "b", "c"}, {"b", "c", "d"}
    assert jaccard(left, right) == jaccard(right, left) == 0.5


def test_two_empty_cards_count_as_identical():
    """Avoids a division by zero, and an empty card is caught by validation long before."""
    assert jaccard(set(), set()) == 1.0


def test_the_assigned_label_and_role_are_excluded_from_the_words():
    """Both are assigned, not written, and the role string is constant within a role."""
    words = content_words(card("CFO", "capital discipline"))
    assert "cfo" not in words and "p-cfo-1" not in words
    assert {"capital", "discipline"} <= words


def test_function_words_are_dropped():
    assert content_words(card("CFO", "the plan and the budget")) >= {"plan", "budget"}
    assert "the" not in content_words(card("CFO", "the plan and the budget"))


def test_short_words_are_dropped():
    assert "an" not in content_words(card("CFO", "an audit"))


# ------------------------------------------------------------------ decomposition


@pytest.fixture
def four_cards():
    """Two generators writing two roles, so all three cells are populated."""
    alpha = ("cost", "discipline", "treasury")
    beta = ("throughput", "reliability", "sites")
    cards = {
        "P-CFO-1": card("CFO", " ".join(alpha), alpha),
        "P-CFO-2": card("CFO", " ".join(beta), beta),
        "P-CIO-1": card("CIO", " ".join(alpha), alpha),
        "P-CIO-2": card("CIO", " ".join(beta), beta),
    }
    generators = {"P-CFO-1": "alpha", "P-CFO-2": "beta",
                  "P-CIO-1": "alpha", "P-CIO-2": "beta"}
    return cards, generators


def test_every_pair_lands_in_exactly_one_cell(four_cards):
    result = summarize(*four_cards)
    counted = sum(c["pairs"] for c in result["cells"].values())
    assert counted == 6  # C(4, 2)


def test_a_generator_writing_the_same_words_twice_shows_up_as_generator_lift(four_cards):
    """Here wording tracks the writer and not the role, and the cells should say so."""
    result = summarize(*four_cards)
    assert result["cells"]["different_role_same_generator"]["mean"] == 1.0
    assert result["cells"]["same_role_different_generator"]["mean"] == 0.0


def test_sharing_both_role_and_generator_is_rejected_as_impossible():
    """One card per generator per role is what makes the decomposition well defined."""
    cards = {"P-CFO-1": card("CFO", "one"), "P-CFO-2": card("CFO", "two")}
    with pytest.raises(AssertionError, match="share both"):
        summarize(cards, {"P-CFO-1": "alpha", "P-CFO-2": "alpha"})


def test_an_empty_baseline_yields_no_lift_rather_than_a_crash(four_cards):
    """Nothing shared across both differences means there is no baseline to be a multiple of."""
    result = summarize(*four_cards)
    assert result["cells"]["different_role_different_generator"]["mean"] == 0.0
    assert result["lift_over_floor"] == {"role": None, "generator": None}


def test_the_most_similar_pairs_are_reported_in_descending_order(four_cards):
    result = summarize(*four_cards)
    overlaps = [p["overlap"] for p in result["most_similar_pairs"]]
    assert overlaps == sorted(overlaps, reverse=True)
