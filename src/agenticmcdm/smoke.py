"""Smoke test: one real call per configured provider, before spending the collection budget.

Two modes:

    ping      minimal request per provider. Checks credentials, endpoint path, response
              shape and the text-extraction path. Cheap.
    decision  the actual elicitation prompt against a placeholder card, validated with
              schema_check. Checks that a provider can produce the structured output the
              study needs at all, and reports what breaks when it cannot.

Smoke output never enters the study. It exists so that a provider that cannot satisfy the
output contract is discovered now rather than 300 calls in.

    python -m agenticmcdm.smoke ping
    python -m agenticmcdm.smoke decision
"""

from __future__ import annotations

import argparse
import json
import time

from agenticmcdm import harness, providers, schema_check

PLACEHOLDER_CARD = {
    "persona_id": "P-CFO-1",
    "role": "CFO",
    "professional_background": (
        "Two decades in corporate finance across manufacturing and services, most recently "
        "responsible for capital allocation and the annual technology budget."
    ),
    "decision_priorities": [
        "protect the annual operating budget",
        "prefer investments with a defensible payback period",
        "keep downside exposure bounded and quantified",
    ],
    "risk_attitude": "cautious; treats risk as a graded cost rather than a veto",
    "time_horizon": "three to five years, with annual budget checkpoints",
    "organizational_constraints": [
        "fixed annual technology budget",
        "quarterly board reporting cycle",
    ],
}


def _providers() -> list[dict]:
    rows = harness.load_registry()
    if not rows:
        raise SystemExit(
            "model_registry.csv has no row with an api_model_id. Fill it before smoke testing."
        )
    return rows


def ping(row: dict) -> dict:
    """Minimal request. Verifies credentials, endpoint, response shape and text extraction."""
    started = time.monotonic()
    try:
        reply = providers.call(
            row.get("adapter") or "openai_compatible",
            row["api_model_id"],
            "You are a test harness probe. Answer in exactly one word.",
            "Reply with the single word OK and nothing else.",
            row,
        )
    except providers.TransportError as exc:
        return {"provider": row["provider"], "ok": False, "stage": "transport",
                "error": str(exc)[:300]}

    text = reply.text.strip()
    return {
        "provider": row["provider"],
        "ok": bool(text),
        "stage": "ok" if text else "empty_text",
        "model_id": row["api_model_id"],
        "reported_model": reply.reported_model,
        "text": text[:80],
        "latency_ms": reply.latency_ms,
        "wall_s": round(time.monotonic() - started, 1),
        "input_tokens": reply.input_tokens,
        "output_tokens": reply.output_tokens,
    }


def decision(row: dict) -> dict:
    """The real elicitation prompt, validated with the study's own schema check."""
    case = harness.load_case()
    system = (harness.PROMPTS / "decision_system.txt").read_text().strip()
    user = (
        (harness.PROMPTS / "decision_user.txt").read_text()
        .replace("{CARD_JSON}", json.dumps(PLACEHOLDER_CARD, indent=2))
        .replace("{CRITERIA_BLOCK}", case["criteria_block"])
        .replace("{MATRIX_BLOCK}", case["matrix_block"])
        .replace("{PAIR_BLOCK}", case["pair_block"])
    )

    started = time.monotonic()
    try:
        reply = providers.call(row.get("adapter") or "openai_compatible",
                               row["api_model_id"], system, user, row)
    except providers.TransportError as exc:
        return {"provider": row["provider"], "ok": False, "stage": "transport",
                "error": str(exc)[:300]}

    out = {
        "provider": row["provider"],
        "model_id": row["api_model_id"],
        "wall_s": round(time.monotonic() - started, 1),
        "input_tokens": reply.input_tokens,
        "output_tokens": reply.output_tokens,
        "chars": len(reply.text),
    }

    try:
        payload = harness.extract_json(reply.text)
    except json.JSONDecodeError as exc:
        return {**out, "ok": False, "stage": "json",
                "error": f"{exc}", "head": reply.text[:200]}

    result = schema_check.check_decision(payload, case["pair_order"])
    if not result.ok:
        return {**out, "ok": False, "stage": "schema",
                "error_codes": result.codes[:8], "errors": result.errors[:4]}

    return {**out, "ok": True, "stage": "ok",
            "declared": payload["declared_priority_order"]}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=["ping", "decision"])
    parser.add_argument("--provider", help="run one provider only")
    args = parser.parse_args()

    rows = [r for r in _providers()
            if not args.provider or r["provider"] == args.provider]
    run = ping if args.mode == "ping" else decision

    results = []
    for row in rows:
        outcome = run(row)
        results.append(outcome)
        mark = "PASS" if outcome.get("ok") else "FAIL"
        print(f"[{mark}] {outcome['provider']:<10} {json.dumps(outcome)[:420]}", flush=True)

    failed = [r["provider"] for r in results if not r.get("ok")]
    print(f"\n{len(results) - len(failed)}/{len(results)} passed")
    if failed:
        print("failing:", ", ".join(failed))
        raise SystemExit(1)


if __name__ == "__main__":
    main()
