"""Matrix screening by stochastic weight-space acceptability analysis.

The performance matrix is a designed stimulus. Before any model is called it has to be shown
that the matrix can express a difference between the two ranking procedures, and that no
single alternative wins almost everywhere. Otherwise the whole experiment is measuring a
matrix that was never able to move.

The method is SMAA (Lahdelma, Hokkanen and Salminen, EJOR 106(1):137-143, 1998): sample the
weight simplex, rank under each procedure, and report the acceptability of each alternative.

Acceptance rules, fixed before collection:

1. at least three alternatives win somewhere;
2. no alternative wins more than 80 percent of the sampled weight space;
3. EDAS and TOPSIS select different winners in at least 5 percent of it.

A matrix that fails is revised before collection and never after.
"""

from __future__ import annotations

import argparse
import csv
import json
import pathlib

import numpy as np

from agenticmcdm.mcdm import edas, topsis, winner_set

ACCEPT_MIN_DISTINCT_WINNERS = 3
ACCEPT_MAX_WINNER_SHARE = 0.80
ACCEPT_MIN_PROCEDURE_DISAGREEMENT = 0.05

PROTOCOL = pathlib.Path(__file__).resolve().parents[2] / "protocol"


def load_case() -> tuple[list[str], np.ndarray, list[str], list[str]]:
    """Read the criteria, their directions and the main performance matrix."""
    import yaml

    spec = yaml.safe_load((PROTOCOL / "criteria.yaml").read_text())
    codes = [c["code"] for c in spec["criteria"]]
    directions = [c["direction"] for c in spec["criteria"]]

    rows, alternatives = [], []
    with (PROTOCOL / "decision_matrix_main.csv").open() as handle:
        for row in csv.DictReader(handle):
            alternatives.append(row["alternative"])
            rows.append([float(row[code]) for code in codes])
    return alternatives, np.asarray(rows, dtype=float), directions, codes


def dominance_report(x: np.ndarray, directions: list[str]) -> list[tuple[int, int]]:
    """Pairs (i, j) where i dominates j on every criterion. Should be empty for A to D."""
    benefit = np.array([d == "benefit" for d in directions])
    better = lambda a, b: np.where(benefit, a >= b, a <= b)  # noqa: E731
    strict = lambda a, b: np.where(benefit, a > b, a < b)  # noqa: E731
    out = []
    for i in range(x.shape[0]):
        for j in range(x.shape[0]):
            if i != j and better(x[i], x[j]).all() and strict(x[i], x[j]).any():
                out.append((i, j))
    return out


def screen(draws: int, seed: int) -> dict:
    """Sample the weight simplex and summarize acceptability under both procedures."""
    alternatives, x, directions, codes = load_case()
    n_alt, n_crit = x.shape
    rng = np.random.default_rng(seed)
    weights = rng.dirichlet(np.ones(n_crit), size=draws)

    wins_edas = np.zeros(n_alt, dtype=int)
    wins_topsis = np.zeros(n_alt, dtype=int)
    disagreements = 0
    leader = np.zeros(n_alt, dtype=int)  # first-place counts pooled over both procedures

    for w in weights:
        se, st = edas(x, w, directions), topsis(x, w, directions)
        we, wt = winner_set(se), winner_set(st)
        for i in we:
            wins_edas[i] += 1
            leader[i] += 1
        for i in wt:
            wins_topsis[i] += 1
            leader[i] += 1
        if we != wt:
            disagreements += 1

    share_edas = wins_edas / draws
    share_topsis = wins_topsis / draws
    disagreement_share = disagreements / draws
    distinct = int(sum(1 for i in range(n_alt) if leader[i] > 0))
    max_share = float(max(share_edas.max(), share_topsis.max()))

    checks = {
        "at_least_three_alternatives_win": distinct >= ACCEPT_MIN_DISTINCT_WINNERS,
        "no_alternative_above_80_percent": max_share <= ACCEPT_MAX_WINNER_SHARE,
        "procedure_disagreement_at_least_5_percent": (
            disagreement_share >= ACCEPT_MIN_PROCEDURE_DISAGREEMENT
        ),
        "no_dominance_among_alternatives": dominance_report(x, directions) == [],
    }

    return {
        "draws": draws,
        "seed": seed,
        "alternatives": alternatives,
        "criteria": codes,
        "winner_share_edas": dict(zip(alternatives, share_edas.round(6).tolist())),
        "winner_share_topsis": dict(zip(alternatives, share_topsis.round(6).tolist())),
        "procedure_disagreement_share": round(disagreement_share, 6),
        "distinct_winners": distinct,
        "dominance_pairs": [
            (alternatives[i], alternatives[j]) for i, j in dominance_report(x, directions)
        ],
        "acceptance_rules": {
            "min_distinct_winners": ACCEPT_MIN_DISTINCT_WINNERS,
            "max_winner_share": ACCEPT_MAX_WINNER_SHARE,
            "min_procedure_disagreement": ACCEPT_MIN_PROCEDURE_DISAGREEMENT,
        },
        "checks": checks,
        "accepted": all(checks.values()),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--draws", type=int, default=500_000)
    parser.add_argument("--seed", type=int, default=20260805)
    parser.add_argument("--out", type=pathlib.Path, default=None)
    args = parser.parse_args()

    report = screen(args.draws, args.seed)
    text = json.dumps(report, indent=2)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text + "\n")
    print(text)
    if not report["accepted"]:
        raise SystemExit("matrix screening FAILED; revise the matrix before collection")


if __name__ == "__main__":
    main()
