"""Deterministic computation layer.

No language model touches any number here. A model supplies fifteen semantic labels; this
module turns them into a reciprocal matrix, a weight vector, two consistency indices and two
rankings. Every function is pure and every tolerance is explicit.

Weights come from the row geometric mean, which is the logarithmic least-squares solution.
Consistency is reported twice. The classical consistency ratio uses the principal eigenvalue,
which belongs to the eigenvector derivation rather than to this one, and is kept because its
0.10 convention is what a reader of an AHP table expects. The geometric consistency index of
Aguaron and Moreno-Jimenez (EJOR 147(1):137-145, 2003) is the index matched to the row
geometric mean and is reported beside it.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations

import numpy as np

TIE_TOLERANCE = 1e-10
WEIGHT_SUM_TOLERANCE = 1e-12
RECIPROCAL_TOLERANCE = 1e-12

#: Saaty random index for a six-criterion matrix. Used only for the consistency ratio.
#: The numerical value must be taken from the random-matrix source cited in PROTOCOL.md and
#: is not an invention of this code.
RANDOM_INDEX_6 = 1.24

SCALE = {"equal": 1, "moderate": 3, "strong": 5, "very_strong": 7, "extreme": 9}


class ProtocolError(ValueError):
    """Raised when an input violates a rule the protocol fixed in advance."""


# --------------------------------------------------------------------------- matrix


def build_matrix(judgments: list[dict], codes: list[str]) -> np.ndarray:
    """Assemble the reciprocal comparison matrix from the model's semantic labels.

    ``judgments`` carries one record per unordered pair with keys ``criterion_a``,
    ``criterion_b``, ``preferred`` and ``intensity``. ``preferred`` is one of the two codes,
    or ``NEUTRAL`` when the intensity is ``equal``. Reciprocals and the unit diagonal are set
    here and are never requested from the model.
    """
    n = len(codes)
    index = {code: i for i, code in enumerate(codes)}
    matrix = np.ones((n, n), dtype=float)
    expected = set(combinations(codes, 2))
    seen: set[tuple[str, str]] = set()

    for record in judgments:
        a, b = record["criterion_a"], record["criterion_b"]
        if a not in index or b not in index:
            raise ProtocolError(f"unknown criterion code in pair {a}_{b}")
        pair = (a, b) if (a, b) in expected else (b, a)
        if pair not in expected:
            raise ProtocolError(f"pair {a}_{b} is not in the registered pair universe")
        if pair in seen:
            raise ProtocolError(f"pair {a}_{b} occurs more than once")
        seen.add(pair)

        intensity = record["intensity"]
        if intensity not in SCALE:
            raise ProtocolError(f"intensity {intensity!r} is not on the registered scale")
        value = float(SCALE[intensity])
        preferred = record["preferred"]

        if intensity == "equal":
            if preferred != "NEUTRAL":
                raise ProtocolError("an equal judgment must carry preferred = NEUTRAL")
            continue
        if preferred not in (a, b):
            raise ProtocolError(f"preferred {preferred!r} is not one of {a}, {b}")

        loser = b if preferred == a else a
        matrix[index[preferred], index[loser]] = value
        matrix[index[loser], index[preferred]] = 1.0 / value

    missing = expected - seen
    if missing:
        raise ProtocolError(f"{len(missing)} registered pair(s) missing: {sorted(missing)}")
    return matrix


def check_matrix(matrix: np.ndarray) -> None:
    """Structural invariants a comparison matrix must satisfy before it is used."""
    n, m = matrix.shape
    if n != m:
        raise ProtocolError("comparison matrix is not square")
    if not np.all(np.isfinite(matrix)) or np.any(matrix <= 0):
        raise ProtocolError("comparison matrix must be positive and finite")
    if not np.allclose(np.diag(matrix), 1.0, atol=RECIPROCAL_TOLERANCE):
        raise ProtocolError("comparison matrix diagonal is not one")
    if not np.allclose(matrix * matrix.T, 1.0, atol=RECIPROCAL_TOLERANCE):
        raise ProtocolError("comparison matrix is not reciprocal within tolerance")


# --------------------------------------------------------------------- weights


@dataclass(frozen=True)
class Weights:
    """Priority vector plus the two consistency diagnostics."""

    w: np.ndarray
    lambda_max: float
    ci: float
    cr: float
    gci: float


def rgm_weights(matrix: np.ndarray, random_index: float = RANDOM_INDEX_6) -> Weights:
    """Row geometric mean priorities, with CR and GCI as diagnostics.

    Neither index filters anything. A matrix above the 0.10 convention stays in the primary
    population; the distribution of both indices is itself an outcome.
    """
    check_matrix(matrix)
    n = matrix.shape[0]

    g = np.exp(np.log(matrix).mean(axis=1))
    w = g / g.sum()
    if abs(w.sum() - 1.0) > WEIGHT_SUM_TOLERANCE:
        raise ProtocolError("weights do not sum to one within tolerance")

    eigenvalues = np.linalg.eigvals(matrix)
    lambda_max = float(np.max(eigenvalues.real))
    ci = (lambda_max - n) / (n - 1)
    cr = ci / random_index if random_index else float("nan")

    # Aguaron and Moreno-Jimenez: mean squared log error of the reciprocal matrix against
    # the ratios implied by the row-geometric-mean priorities.
    log_w = np.log(w)
    residuals = [
        (np.log(matrix[i, j]) - log_w[i] + log_w[j]) ** 2
        for i, j in combinations(range(n), 2)
    ]
    gci = float(2.0 / ((n - 1) * (n - 2)) * sum(residuals))

    return Weights(w=w, lambda_max=lambda_max, ci=float(ci), cr=float(cr), gci=gci)


# --------------------------------------------------------------------- ranking


def _validate_ranking_inputs(x: np.ndarray, w: np.ndarray, directions: list[str]) -> None:
    if x.ndim != 2:
        raise ProtocolError("performance matrix must be two dimensional")
    if x.shape[1] != len(w) or x.shape[1] != len(directions):
        raise ProtocolError("performance matrix, weights and directions disagree in width")
    if not np.all(np.isfinite(x)) or np.any(x <= 0):
        raise ProtocolError("performance values must be positive and finite")
    if np.any(w <= 0):
        raise ProtocolError("weights must be positive")
    if set(directions) - {"cost", "benefit"}:
        raise ProtocolError("directions must be 'cost' or 'benefit'")


def edas(x: np.ndarray, w: np.ndarray, directions: list[str]) -> np.ndarray:
    """Appraisal scores by distance from the average solution.

    The average is taken over the alternatives actually present, so adding an alternative
    changes every term. A recalculation over a different reference set is not comparable
    with the original.
    """
    _validate_ranking_inputs(x, w, directions)
    av = x.mean(axis=0)
    if np.any(av <= 0):
        raise ProtocolError("EDAS requires a positive criterion average")

    benefit = np.array([d == "benefit" for d in directions])
    diff = x - av
    signed = np.where(benefit, diff, -diff)
    pda = np.maximum(0.0, signed) / av
    nda = np.maximum(0.0, -signed) / av

    sp = pda @ w
    sn = nda @ w
    max_sp, max_sn = sp.max(), sn.max()
    nsp = sp / max_sp if max_sp > TIE_TOLERANCE else np.zeros_like(sp)
    nsn = 1.0 - sn / max_sn if max_sn > TIE_TOLERANCE else np.ones_like(sn)
    return 0.5 * (nsp + nsn)


def topsis(x: np.ndarray, w: np.ndarray, directions: list[str]) -> np.ndarray:
    """Relative closeness to the ideal point under vector normalization.

    The ideal and anti-ideal points are taken from the alternatives present, so this
    procedure is reference-set dependent in the same way EDAS is.
    """
    _validate_ranking_inputs(x, w, directions)
    norm = np.sqrt((x**2).sum(axis=0))
    if np.any(norm <= 0):
        raise ProtocolError("TOPSIS normalization denominator is zero")
    v = (x / norm) * w

    benefit = np.array([d == "benefit" for d in directions])
    ideal = np.where(benefit, v.max(axis=0), v.min(axis=0))
    anti = np.where(benefit, v.min(axis=0), v.max(axis=0))

    d_plus = np.sqrt(((v - ideal) ** 2).sum(axis=1))
    d_minus = np.sqrt(((v - anti) ** 2).sum(axis=1))
    total = d_plus + d_minus
    if np.any(total <= TIE_TOLERANCE):
        raise ProtocolError("TOPSIS closeness denominator is zero")
    return d_minus / total


def wsm(x: np.ndarray, w: np.ndarray, directions: list[str]) -> np.ndarray:
    """Linear weighted sum on min-max normalized values. Internal cross-check only."""
    _validate_ranking_inputs(x, w, directions)
    lo, hi = x.min(axis=0), x.max(axis=0)
    span = np.where(hi - lo > TIE_TOLERANCE, hi - lo, 1.0)
    benefit = np.array([d == "benefit" for d in directions])
    normalized = np.where(benefit, (x - lo) / span, (hi - x) / span)
    return normalized @ w


# --------------------------------------------------------------------- ranks


def winner_set(scores: np.ndarray, tol: float = TIE_TOLERANCE) -> frozenset[int]:
    """Every alternative within tolerance of the best score. Ties are never broken."""
    best = scores.max()
    return frozenset(int(i) for i in np.flatnonzero(scores >= best - tol))


def generalized_kendall(a: np.ndarray, b: np.ndarray, tol: float = TIE_TOLERANCE) -> float:
    """Normalized pair-loss distance between two score vectors.

    A pair contributes 0 when both rankings agree on a strict order or both tie it, 0.5 when
    one ties and the other orders, and 1 when the strict orders are opposite. The sum is
    divided by the number of pairs, so the result lies in [0, 1]. The tolerance is what makes
    the half-credit branch reachable at all: both ranking procedures return continuous
    scores, so exact equality would otherwise never occur.
    """
    if a.shape != b.shape:
        raise ProtocolError("score vectors differ in length")
    n = a.shape[0]
    pairs = list(combinations(range(n), 2))

    def relation(scores: np.ndarray, i: int, j: int) -> int:
        d = scores[i] - scores[j]
        if abs(d) <= tol:
            return 0
        return 1 if d > 0 else -1

    loss = 0.0
    for i, j in pairs:
        ra, rb = relation(a, i, j), relation(b, i, j)
        if ra == rb:
            continue
        loss += 0.5 if 0 in (ra, rb) else 1.0
    return loss / len(pairs)
