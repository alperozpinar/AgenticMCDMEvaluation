"""Lexical overlap between the frozen persona cards.

This is a descriptive and it gates nothing. It exists because the persona-card condition can
only produce a difference between rankings if the cards themselves differ, and a reader who
sees a small E2 deserves to know whether the cards were nearly alike to begin with.

What is measured is the Jaccard overlap of content-word sets. Because each generator writes
exactly one card per role, every pair of cards falls into one of three cells, and the whole
design is visible in their comparison:

- same role, different generator: what the persona-card factor has to work with;
- different role, same generator: how much of a card's wording is its writer's habit;
- different role, different generator: the floor, sharing neither.

The measure is lexical, not semantic. High overlap is direct evidence that two cards say
similar things in similar words. Low overlap is weaker evidence of the opposite, since two
cards can express the same priorities in different vocabulary.
"""

from __future__ import annotations

import argparse
import csv
import itertools
import json
import pathlib
import re
from statistics import mean

ROOT = pathlib.Path(__file__).resolve().parents[2]
CARDS = ROOT / "protocol" / "cards"
RESULTS = ROOT / "results"

# Function words carry no content here, and every card shares them by construction.
STOPWORDS = {
    "the", "and", "for", "with", "that", "this", "from", "into", "over", "under", "while",
    "where", "when", "which", "their", "there", "than", "then", "them", "they", "have",
    "has", "had", "was", "were", "been", "being", "are", "its", "it", "of", "in", "on",
    "to", "a", "an", "as", "at", "by", "or", "not", "no", "but", "also", "across", "after",
    "before", "during", "through", "within", "without", "between", "both", "each", "one",
    "two", "three", "four", "five", "other", "such", "same", "more", "most", "less",
}


def content_words(card: dict) -> set[str]:
    """Lowercased alphabetic words of three letters or more, minus function words.

    `persona_id` and `role` are excluded. Both are assigned labels rather than written text,
    and every card of a role carries the same role string, which would inflate every
    within-role comparison by a constant.
    """
    parts: list[str] = []
    for key, value in card.items():
        if key in ("persona_id", "role"):
            continue
        parts.extend([value] if isinstance(value, str) else value)
    words = re.findall(r"[a-z]{3,}", " ".join(parts).lower())
    return {w for w in words if w not in STOPWORDS}


def jaccard(left: set[str], right: set[str]) -> float:
    """Shared words over total distinct words. Two empty cards count as identical."""
    union = left | right
    if not union:
        return 1.0
    return len(left & right) / len(union)


def load_cards() -> dict[str, dict]:
    return {p.stem: json.loads(p.read_text()) for p in sorted(CARDS.glob("P-*.json"))}


def load_generators() -> dict[str, str]:
    """Which generator wrote each frozen card, read from the freeze-time assignment."""
    path = CARDS / "_assignment.csv"
    if not path.exists():
        raise SystemExit(f"no {path}; run freeze-cards first")
    with path.open() as handle:
        return {r["persona_id"]: r["generator"]
                for r in csv.DictReader(l for l in handle if not l.startswith("#"))}


def _stats(values: list[float]) -> dict:
    """Summary of one cell. A cell can be empty when fewer than three roles are in play."""
    if not values:
        return {"pairs": 0, "mean": None, "min": None, "max": None}
    return {"pairs": len(values), "mean": round(mean(values), 4),
            "min": round(min(values), 4), "max": round(max(values), 4)}


def _lift(values: list[float], floor: float | None) -> float | None:
    """How far a cell sits above the floor. Undefined when either side has nothing to divide.

    A floor of zero means no pair sharing neither role nor writer had a single word in
    common, so there is no baseline to be a multiple of, and reporting nothing is honest.
    """
    if not values or not floor:
        return None
    return round(mean(values) / floor, 3)


def summarize(cards: dict[str, dict], generators: dict[str, str]) -> dict:
    """Overlap decomposed into the three cells a one-card-per-generator-per-role design has."""
    words = {pid: content_words(card) for pid, card in cards.items()}

    cells: dict[str, list[float]] = {
        "same_role_different_generator": [],
        "different_role_same_generator": [],
        "different_role_different_generator": [],
    }
    by_role: dict[str, list[float]] = {}
    ranked: list[tuple[float, str, str]] = []

    for a, b in itertools.combinations(sorted(cards), 2):
        value = jaccard(words[a], words[b])
        ranked.append((value, a, b))
        same_role = cards[a]["role"] == cards[b]["role"]
        same_generator = generators[a] == generators[b]
        if same_role and same_generator:
            # Impossible by construction: one card per generator per role.
            raise AssertionError(f"{a} and {b} share both role and generator")
        if same_role:
            cells["same_role_different_generator"].append(value)
            by_role.setdefault(cards[a]["role"], []).append(value)
        elif same_generator:
            cells["different_role_same_generator"].append(value)
        else:
            cells["different_role_different_generator"].append(value)

    ranked.sort(reverse=True)
    baseline = cells["different_role_different_generator"]
    floor = mean(baseline) if baseline else None

    return {
        "cards": len(cards),
        "cells": {name: _stats(values) for name, values in cells.items()},
        "same_role_by_role": {r: round(mean(v), 4) for r, v in sorted(by_role.items())},
        "lift_over_floor": {
            "role": _lift(cells["same_role_different_generator"], floor),
            "generator": _lift(cells["different_role_same_generator"], floor),
        },
        "most_similar_pairs": [
            {"overlap": round(v, 4), "a": a, "b": b,
             "generator_a": generators[a], "generator_b": generators[b],
             "same_role": cards[a]["role"] == cards[b]["role"]}
            for v, a, b in ranked[:5]
        ],
        "words_shared_by_every_card": sorted(set.intersection(*words.values())),
        "measure": "Jaccard overlap of content-word sets; lexical, not semantic",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true",
                        help="also write the summary under results/")
    args = parser.parse_args()

    cards = load_cards()
    if not cards:
        raise SystemExit(f"no frozen cards in {CARDS}; run freeze-cards first")
    summary = summarize(cards, load_generators())
    print(json.dumps(summary, indent=2))

    if args.write:
        RESULTS.mkdir(exist_ok=True)
        target = RESULTS / "card_similarity.json"
        target.write_text(json.dumps(summary, indent=2) + "\n")
        print(f"\nwrote {target}")


if __name__ == "__main__":
    main()
