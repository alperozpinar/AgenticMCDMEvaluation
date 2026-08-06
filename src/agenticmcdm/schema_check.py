"""Response validation, written as the protocol states it rather than as generic JSON Schema.

The respondent returns three keys and no more. `persona_id` and `repetition` are attached by
the harness from the scheduled slot, not requested from the model: the repetition index is a
collection-round label, and putting it in the prompt would make the request differ between
the repetitions of a cell, which the protocol forbids.

The schema files under `schemas/` are the published contract. This module is the executable
form of the same rules, so a failure reports which protocol rule broke instead of a generic
path error. Validation is strict: a response either satisfies every rule or it is a
first-attempt invalid outcome, and there is no partial credit.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from itertools import combinations

CODES = ["C1", "C2", "C3", "C4", "C5", "C6"]
INTENSITIES = {"equal", "moderate", "strong", "very_strong", "extreme"}
ROLES = {"CFO", "CIO", "COO"}
SCHEMA_VERSION = "structured_v1_icaira"
MAX_REASON_WORDS = 25


@dataclass
class Result:
    """Outcome of validating one response. `errors` is empty exactly when `ok` is true."""

    ok: bool
    errors: list[str] = field(default_factory=list)

    @property
    def codes(self) -> list[str]:
        """Short machine-readable error codes for the ledger."""
        return [e.split(":", 1)[0] for e in self.errors]


def _words(text: str) -> int:
    return len([w for w in re.split(r"\s+", text.strip()) if w])


def check_decision(payload: object, expected_pairs: list[str]) -> Result:
    """Validate one structured decision response against the elicitation contract."""
    errors: list[str] = []

    if not isinstance(payload, dict):
        return Result(False, ["E_TYPE: response is not a JSON object"])

    allowed = {"schema_version", "criterion_comparisons", "declared_priority_order"}
    extra = set(payload) - allowed
    if extra:
        errors.append(f"E_EXTRA_FIELD: unexpected field(s) {sorted(extra)}")
    missing = allowed - set(payload)
    if missing:
        errors.append(f"E_MISSING_FIELD: missing field(s) {sorted(missing)}")
        return Result(False, errors)

    if payload["schema_version"] != SCHEMA_VERSION:
        errors.append(f"E_VERSION: schema_version is {payload['schema_version']!r}")

    comparisons = payload["criterion_comparisons"]
    if not isinstance(comparisons, list):
        errors.append("E_COMPARISONS_TYPE: criterion_comparisons is not a list")
        return Result(False, errors)
    if len(comparisons) != 15:
        errors.append(f"E_COUNT: {len(comparisons)} comparison(s) instead of 15")

    seen: set[frozenset[str]] = set()
    for i, item in enumerate(comparisons):
        tag = f"pair index {i}"
        if not isinstance(item, dict):
            errors.append(f"E_PAIR_TYPE: {tag} is not an object")
            continue
        need = {"pair_id", "criterion_a", "criterion_b", "preferred", "intensity", "reason"}
        if set(item) != need:
            errors.append(f"E_PAIR_FIELDS: {tag} has fields {sorted(item)}")
            continue

        a, b = item["criterion_a"], item["criterion_b"]
        if a not in CODES or b not in CODES or a == b:
            errors.append(f"E_PAIR_CODES: {tag} has codes {a!r}, {b!r}")
            continue
        key = frozenset((a, b))
        if key in seen:
            errors.append(f"E_PAIR_DUPLICATE: {tag} repeats {a}_{b}")
        seen.add(key)

        if item["pair_id"] not in (f"{a}_{b}", f"{b}_{a}"):
            errors.append(f"E_PAIR_ID: {tag} pair_id {item['pair_id']!r} disagrees with codes")

        intensity = item["intensity"]
        if intensity not in INTENSITIES:
            errors.append(f"E_INTENSITY: {tag} intensity {intensity!r} is off scale")
        elif intensity == "equal":
            if item["preferred"] != "NEUTRAL":
                errors.append(f"E_NEUTRAL: {tag} is equal but preferred is "
                              f"{item['preferred']!r}")
        elif item["preferred"] not in (a, b):
            errors.append(f"E_PREFERRED: {tag} preferred {item['preferred']!r} is not "
                          f"{a} or {b}")

        reason = item["reason"]
        if not isinstance(reason, str):
            errors.append(f"E_REASON_TYPE: {tag} reason is not a string")
        elif _words(reason) > MAX_REASON_WORDS:
            errors.append(f"E_REASON_LENGTH: {tag} reason has {_words(reason)} words")

    expected = {frozenset(p.split("_")) for p in expected_pairs}
    absent = expected - seen
    if absent:
        errors.append(f"E_PAIR_MISSING: {len(absent)} registered pair(s) absent")

    order = payload["declared_priority_order"]
    if not isinstance(order, list) or len(order) != 3:
        errors.append("E_PRIORITY_COUNT: declared_priority_order is not three items")
    elif len(set(order)) != 3 or any(c not in CODES for c in order):
        errors.append(f"E_PRIORITY_CODES: declared_priority_order is {order!r}")

    return Result(not errors, errors)


def check_card(payload: object, role: str) -> Result:
    """Validate one generated persona card against the card schema.

    Structural rules only. The domain admissibility checklist in
    `protocol/card_admissibility_checklist.yaml` is a human pass or fail and is recorded
    separately; it is not automated here, because items such as "no claim that every person
    in the occupation shares these preferences" need a reader.
    """
    errors: list[str] = []
    if not isinstance(payload, dict):
        return Result(False, ["E_TYPE: card is not a JSON object"])

    allowed = {"persona_id", "role", "professional_background", "decision_priorities",
               "risk_attitude", "time_horizon", "organizational_constraints"}
    if set(payload) != allowed:
        errors.append(f"E_CARD_FIELDS: card has fields {sorted(payload)}")
        return Result(False, errors)

    if payload["role"] != role:
        errors.append(f"E_CARD_ROLE: role {payload['role']!r} is not the requested {role!r}")
    if payload["role"] not in ROLES:
        errors.append(f"E_CARD_ROLE_UNKNOWN: role {payload['role']!r}")

    if _words(payload["professional_background"]) > 80:
        errors.append("E_CARD_BACKGROUND_LENGTH: professional_background exceeds 80 words")

    priorities = payload["decision_priorities"]
    if not isinstance(priorities, list) or not 3 <= len(priorities) <= 5:
        errors.append("E_CARD_PRIORITIES: decision_priorities is not 3 to 5 items")

    constraints = payload["organizational_constraints"]
    if not isinstance(constraints, list) or not 2 <= len(constraints) <= 4:
        errors.append("E_CARD_CONSTRAINTS: organizational_constraints is not 2 to 4 items")

    for field_name in ("risk_attitude", "time_horizon"):
        if not isinstance(payload[field_name], str) or not payload[field_name].strip():
            errors.append(f"E_CARD_EMPTY: {field_name} is empty")

    return Result(not errors, errors)


SELF_REFERENCE = re.compile(
    r"\b(gpt|chatgpt|openai|claude|anthropic|gemini|bard|google\s+deepmind|grok|xai|"
    r"kimi|moonshot|llama|mistral|deepseek|qwen|as an ai|language model)\b",
    re.IGNORECASE,
)


def find_self_reference(card: dict) -> list[str]:
    """Locate model self-reference in card text, which voids the card before freezing.

    A decision respondent that can tell which service wrote a card breaks the blinding, so
    this runs on every card before it is frozen.
    """
    hits = []
    for key, value in card.items():
        texts = value if isinstance(value, list) else [value]
        for text in texts:
            if isinstance(text, str):
                for match in SELF_REFERENCE.finditer(text):
                    hits.append(f"{key}: {match.group(0)}")
    return hits
