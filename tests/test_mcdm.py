"""Invariant tests for the computation layer.

These check the properties the protocol depends on. They are not a substitute for
reproducing a published numerical example, which is listed as an open task in the README
and needs a cited source rather than a value asserted from memory.
"""

from __future__ import annotations

import itertools

import numpy as np
import pytest

from agenticmcdm.mcdm import (
    ProtocolError,
    build_matrix,
    edas,
    generalized_kendall,
    rgm_weights,
    topsis,
    winner_set,
    wsm,
)
from agenticmcdm.screening import dominance_report, load_case

CODES = ["C1", "C2", "C3", "C4", "C5", "C6"]


def complete_judgments(intensity="equal", preferred="NEUTRAL"):
    return [
        {"criterion_a": a, "criterion_b": b, "preferred": preferred, "intensity": intensity}
        for a, b in itertools.combinations(CODES, 2)
    ]


# ----------------------------------------------------------------- matrix assembly


def test_all_equal_gives_uniform_weights_and_perfect_consistency():
    m = build_matrix(complete_judgments(), CODES)
    out = rgm_weights(m)
    assert np.allclose(out.w, 1 / 6)
    assert out.cr == pytest.approx(0.0, abs=1e-9)
    assert out.gci == pytest.approx(0.0, abs=1e-12)


def test_matrix_is_reciprocal_and_unit_diagonal():
    js = complete_judgments()
    js[0] = {**js[0], "preferred": "C1", "intensity": "strong"}
    m = build_matrix(js, CODES)
    assert m[0, 1] == 5
    assert m[1, 0] == pytest.approx(1 / 5)
    assert np.allclose(np.diag(m), 1.0)


def test_missing_pair_is_rejected():
    with pytest.raises(ProtocolError, match="missing"):
        build_matrix(complete_judgments()[:-1], CODES)


def test_duplicate_pair_is_rejected():
    js = complete_judgments()
    with pytest.raises(ProtocolError, match="more than once"):
        build_matrix(js + [js[0]], CODES)


def test_equal_with_a_direction_is_rejected():
    js = complete_judgments()
    js[0] = {**js[0], "preferred": "C1"}
    with pytest.raises(ProtocolError, match="NEUTRAL"):
        build_matrix(js, CODES)


def test_unregistered_intensity_is_rejected():
    js = complete_judgments()
    js[0] = {**js[0], "intensity": "quite_strong", "preferred": "C1"}
    with pytest.raises(ProtocolError, match="registered scale"):
        build_matrix(js, CODES)


# ----------------------------------------------------------------- weights


def test_consistent_matrix_has_near_zero_indices():
    # A perfectly consistent matrix built from a known priority vector.
    v = np.array([0.30, 0.25, 0.20, 0.12, 0.08, 0.05])
    m = np.outer(v, 1 / v)
    out = rgm_weights(m)
    assert np.allclose(out.w, v / v.sum())
    assert out.cr == pytest.approx(0.0, abs=1e-9)
    assert out.gci == pytest.approx(0.0, abs=1e-9)


def test_inconsistent_matrix_raises_both_indices_together():
    v = np.array([0.30, 0.25, 0.20, 0.12, 0.08, 0.05])
    m = np.outer(v, 1 / v)
    m[0, 5], m[5, 0] = 9.0, 1 / 9.0  # push one judgment away from consistency
    out = rgm_weights(m)
    assert out.cr > 0
    assert out.gci > 0


def test_non_reciprocal_matrix_is_rejected():
    m = np.ones((6, 6))
    m[0, 1] = 3.0  # reciprocal left at 1
    with pytest.raises(ProtocolError, match="reciprocal"):
        rgm_weights(m)


# ----------------------------------------------------------------- ranking


def case():
    alternatives, x, directions, _ = load_case()
    return alternatives, x, directions


def test_case_matrix_has_no_dominance_among_alternatives():
    _, x, directions = case()
    assert dominance_report(x, directions) == []


def test_every_alternative_leads_on_some_criterion():
    alternatives, x, directions = case()
    leaders = set()
    for j, d in enumerate(directions):
        leaders.add(int(np.argmin(x[:, j]) if d == "cost" else np.argmax(x[:, j])))
    assert leaders == set(range(len(alternatives)))


@pytest.mark.parametrize("procedure", [edas, topsis, wsm])
def test_dominated_alternative_never_wins(procedure):
    """Both procedures preserve dominance under positive weights.

    This is why an E-over-D event in the reference-set recalculation is a software fault
    rather than a finding.
    """
    _, x, directions = case()
    e = np.array([310.0, 66.0, 150.0, 250.0, 3.2, 9.0])  # strictly dominated by D
    xe = np.vstack([x, e])
    rng = np.random.default_rng(7)
    for w in rng.dirichlet(np.ones(6), size=300):
        scores = procedure(xe, w, directions)
        assert scores[4] <= scores[3] + 1e-12


def test_scores_are_finite_across_the_simplex():
    _, x, directions = case()
    rng = np.random.default_rng(11)
    for w in rng.dirichlet(np.ones(6), size=200):
        assert np.all(np.isfinite(edas(x, w, directions)))
        assert np.all(np.isfinite(topsis(x, w, directions)))


def test_negative_or_zero_performance_is_rejected():
    _, x, directions = case()
    bad = x.copy()
    bad[0, 0] = 0.0
    with pytest.raises(ProtocolError, match="positive"):
        edas(bad, np.full(6, 1 / 6), directions)


# ----------------------------------------------------------------- distance


def test_identical_rankings_have_zero_distance():
    a = np.array([0.9, 0.7, 0.5, 0.3])
    assert generalized_kendall(a, a) == 0.0


def test_fully_reversed_ranking_has_distance_one():
    a = np.array([0.9, 0.7, 0.5, 0.3])
    assert generalized_kendall(a, -a) == 1.0


def test_tie_against_strict_order_costs_half_a_pair():
    a = np.array([0.5, 0.5, 0.2, 0.1])
    b = np.array([0.6, 0.5, 0.2, 0.1])
    assert generalized_kendall(a, b) == pytest.approx(0.5 / 6)


def test_winner_set_keeps_every_alternative_inside_tolerance():
    scores = np.array([0.80, 0.80 - 1e-12, 0.5, 0.4])
    assert winner_set(scores) == frozenset({0, 1})
