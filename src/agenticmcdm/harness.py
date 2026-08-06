"""Collection harness: schedule, render, call, validate, record.

The harness never decides anything. It executes a schedule that was built and frozen before
the first call, and it writes down what happened. Three rules from the protocol are enforced
here rather than left to whoever runs it:

1. **The schedule is built once.** `build-schedule` writes `run/run_schedule.csv` and refuses
   to overwrite it. Cells are never topped up on the basis of what earlier calls returned.
2. **One transport retry, one repair, and no more.** A transport failure with no model output
   is retried once in the same slot. A schema failure is not a transport failure; it gets one
   fixed repair request whose output goes to a separate population, never to the primary one.
3. **Raw bytes are preserved before parsing.** Every physical request writes a ledger row and
   a raw response file, so a parsing decision can always be revisited.

Nothing here computes weights or rankings. That is `mcdm.py`, and it runs after collection
from the stored responses.

Usage:

    python -m agenticmcdm.harness build-schedule --seed 20260805
    python -m agenticmcdm.harness generate-cards --dry-run
    python -m agenticmcdm.harness collect --round 1 --dry-run
    python -m agenticmcdm.harness collect --round 1
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import json
import pathlib
import random
import re

from agenticmcdm import providers, schema_check

ROOT = pathlib.Path(__file__).resolve().parents[2]
PROTOCOL = ROOT / "protocol"
PROMPTS = ROOT / "prompts"
MODELS = ROOT / "models"
RUN = ROOT / "run"
DATA = ROOT / "data"

ROLES = ["CFO", "CIO", "COO"]
ROUNDS = 5
REPAIR_MESSAGE = (
    "The previous response did not satisfy the required output contract. "
    "The problems were:\n{errors}\n"
    "Return the corrected JSON only. Do not add commentary and do not change any judgment "
    "you intended to make."
)

LEDGER_FIELDS = [
    "run_id", "attempt_id", "attempt_type", "collection_round", "execution_position",
    "phase", "provider", "adapter", "api_model_id", "snapshot", "reported_model",
    "provider_request_id", "requested_at_utc", "card_id", "card_hash", "prompt_version",
    "request_hash", "system_prompt_hash", "matrix_hash", "pair_order_hash",
    "requested_temperature", "top_p", "seed", "latency_ms", "input_tokens", "output_tokens",
    "raw_response_path", "transport_status", "validation_status", "schema_error_codes",
]


# ------------------------------------------------------------------ helpers


def _hash(text: str | bytes) -> str:
    data = text.encode() if isinstance(text, str) else text
    return hashlib.sha256(data).hexdigest()[:16]


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def load_registry() -> list[dict]:
    """Read the run registry, skipping comment lines and rows without a model id."""
    rows = []
    with (MODELS / "model_registry.csv").open() as handle:
        for row in csv.DictReader(l for l in handle if not l.startswith("#")):
            if (row.get("api_model_id") or "").strip():
                rows.append(row)
    return rows


def load_case() -> dict:
    """Criteria, pair order and the two matrices, with hashes."""
    import yaml

    spec = yaml.safe_load((PROTOCOL / "criteria.yaml").read_text())
    codes = [c["code"] for c in spec["criteria"]]
    main = (PROTOCOL / "decision_matrix_main.csv").read_text()

    criteria_block = "\n".join(
        f"{c['code']}: {c['name']} ({c['direction']}, {c['unit']}). {c['definition'].strip()}"
        for c in spec["criteria"]
    )
    rows = list(csv.DictReader(main.splitlines()))
    header = "Alternative | " + " | ".join(codes)
    matrix_block = "\n".join(
        [header, "-" * len(header)]
        + [f"{r['alternative']} | " + " | ".join(r[c] for c in codes) for r in rows]
    )
    pair_block = "\n".join(f"{i + 1}. {p}" for i, p in enumerate(spec["pair_order"]))

    return {
        "codes": codes,
        "pair_order": spec["pair_order"],
        "criteria_block": criteria_block,
        "matrix_block": matrix_block,
        "pair_block": pair_block,
        "matrix_hash": _hash(main),
        "pair_order_hash": _hash(",".join(spec["pair_order"])),
    }


def extract_json(text: str) -> object:
    """Parse the model's reply as JSON, tolerating a fenced code block around it.

    Tolerating the fence is a parsing decision, not a repair: the bytes are stored unchanged
    and the fence is a formatting habit rather than a judgment. Anything beyond that is a
    schema failure.
    """
    stripped = text.strip()
    fenced = re.match(r"^```(?:json)?\s*(.*?)\s*```$", stripped, re.DOTALL)
    if fenced:
        stripped = fenced.group(1)
    return json.loads(stripped)


# ------------------------------------------------------------------ schedule


def build_schedule(seed: int) -> pathlib.Path:
    """Write the frozen 375-slot schedule. Refuses to overwrite an existing one."""
    target = RUN / "run_schedule.csv"
    if target.exists():
        raise SystemExit(
            f"{target} already exists. The schedule is built once, before collection, and "
            "is never rebuilt. Record a deviation if it genuinely has to change."
        )
    registry = load_registry()
    if not registry:
        raise SystemExit("model_registry.csv holds no rows with an api_model_id yet")

    decision = [r for r in registry if r["role_in_study"] in ("decision", "both")]
    generators = [r for r in registry if r["role_in_study"] in ("generator", "both")]
    cards = [f"P-{role}-{i}" for role in ROLES for i in range(1, len(generators) + 1)]

    rng = random.Random(seed)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["run_id", "collection_round", "execution_position", "card_id",
                         "provider", "api_model_id", "repetition"])
        for rnd in range(1, ROUNDS + 1):
            slots = [(c, m) for c in cards for m in decision]
            rng.shuffle(slots)
            for position, (card, model) in enumerate(slots, start=1):
                run_id = f"S_{card}_{model['provider']}_{rnd:02d}"
                writer.writerow([run_id, rnd, position, card, model["provider"],
                                 model["api_model_id"], rnd])
    return target


# ------------------------------------------------------------------ ledger


def append_ledger(row: dict) -> None:
    path = DATA / "ledger.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    new = not path.exists()
    with path.open("a", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=LEDGER_FIELDS, extrasaction="ignore")
        if new:
            writer.writeheader()
        writer.writerow(row)


def store_raw(attempt_id: str, raw: bytes) -> str:
    path = DATA / "raw" / f"{attempt_id}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    return str(path.relative_to(ROOT))


# ------------------------------------------------------------------ one slot


def run_slot(slot: dict, model_row: dict, case: dict, card_json: str, dry_run: bool) -> dict:
    """Execute one scheduled slot: initial attempt, one transport retry, one repair.

    Returns the validated payload under `payload` when the slot produced a first-attempt
    valid response, and records everything either way.
    """
    system = (PROMPTS / "decision_system.txt").read_text().strip()
    user = (
        (PROMPTS / "decision_user.txt").read_text()
        .replace("{CARD_JSON}", card_json)
        .replace("{CRITERIA_BLOCK}", case["criteria_block"])
        .replace("{MATRIX_BLOCK}", case["matrix_block"])
        .replace("{PAIR_BLOCK}", case["pair_block"])
    )

    base = {
        "run_id": slot["run_id"],
        "collection_round": slot["collection_round"],
        "execution_position": slot["execution_position"],
        "phase": "decision",
        "provider": model_row["provider"],
        "adapter": model_row.get("adapter") or "openai_compatible",
        "api_model_id": model_row["api_model_id"],
        "snapshot": model_row.get("snapshot", ""),
        "card_id": slot["card_id"],
        "card_hash": _hash(card_json),
        "prompt_version": "structured_v1_icaira",
        "request_hash": _hash(system + user),
        "system_prompt_hash": _hash(system),
        "matrix_hash": case["matrix_hash"],
        "pair_order_hash": case["pair_order_hash"],
        "requested_temperature": model_row.get("requested_temperature", ""),
        "top_p": model_row.get("top_p", ""),
        "seed": model_row.get("seed", ""),
    }

    if dry_run:
        print(f"[dry-run] {slot['run_id']} -> {model_row['provider']} "
              f"{model_row['api_model_id']}, request hash {base['request_hash']}, "
              f"{len(user.split())} words")
        return {"status": "dry_run", **base}

    settings = dict(model_row)
    attempts, reply = 0, None
    while attempts < 2 and reply is None:
        attempts += 1
        attempt_type = "initial" if attempts == 1 else "transport_retry"
        attempt_id = f"{slot['run_id']}_{attempt_type}"
        try:
            reply = providers.call(base["adapter"], model_row["api_model_id"],
                                   system, user, settings)
        except providers.TransportError as exc:
            append_ledger({**base, "attempt_id": attempt_id, "attempt_type": attempt_type,
                           "requested_at_utc": _now(), "transport_status": "transport_error",
                           "validation_status": "", "schema_error_codes": str(exc)[:200]})
            if attempts == 2:
                return {"status": "transport_failed", **base}

    attempt_type = "initial" if attempts == 1 else "transport_retry"
    attempt_id = f"{slot['run_id']}_{attempt_type}"
    raw_path = store_raw(attempt_id, reply.raw)

    try:
        payload = extract_json(reply.text)
        result = schema_check.check_decision(payload, case["pair_order"])
    except json.JSONDecodeError as exc:
        payload, result = None, schema_check.Result(False, [f"E_JSON: {exc}"])

    append_ledger({**base, "attempt_id": attempt_id, "attempt_type": attempt_type,
                   "requested_at_utc": _now(), "reported_model": reply.reported_model,
                   "provider_request_id": reply.provider_request_id,
                   "latency_ms": reply.latency_ms, "input_tokens": reply.input_tokens,
                   "output_tokens": reply.output_tokens, "raw_response_path": raw_path,
                   "transport_status": "success",
                   "validation_status": "valid" if result.ok else "invalid",
                   "schema_error_codes": ";".join(result.codes)})

    if result.ok:
        return {"status": "first_attempt_valid", "payload": payload, **base}

    # One fixed repair request. Its output never enters the primary population.
    repair_user = user + "\n\n" + REPAIR_MESSAGE.format(errors="\n".join(result.errors))
    attempt_id = f"{slot['run_id']}_schema_repair"
    try:
        repair = providers.call(base["adapter"], model_row["api_model_id"],
                                system, repair_user, settings)
    except providers.TransportError as exc:
        append_ledger({**base, "attempt_id": attempt_id, "attempt_type": "schema_repair",
                       "requested_at_utc": _now(), "transport_status": "transport_error",
                       "schema_error_codes": str(exc)[:200]})
        return {"status": "invalid_repair_failed", **base}

    raw_path = store_raw(attempt_id, repair.raw)
    try:
        repaired = extract_json(repair.text)
        repair_result = schema_check.check_decision(repaired, case["pair_order"])
    except json.JSONDecodeError as exc:
        repaired, repair_result = None, schema_check.Result(False, [f"E_JSON: {exc}"])

    append_ledger({**base, "attempt_id": attempt_id, "attempt_type": "schema_repair",
                   "requested_at_utc": _now(), "reported_model": repair.reported_model,
                   "provider_request_id": repair.provider_request_id,
                   "latency_ms": repair.latency_ms, "input_tokens": repair.input_tokens,
                   "output_tokens": repair.output_tokens, "raw_response_path": raw_path,
                   "transport_status": "success",
                   "validation_status": "repaired_valid" if repair_result.ok else "invalid",
                   "schema_error_codes": ";".join(repair_result.codes)})

    return {"status": "repair_only" if repair_result.ok else "invalid",
            "payload": repaired if repair_result.ok else None, **base}


# ------------------------------------------------------------------ cli


def cmd_collect(args: argparse.Namespace) -> None:
    schedule = RUN / "run_schedule.csv"
    if not schedule.exists():
        raise SystemExit("no run_schedule.csv; run build-schedule first")
    case = load_case()
    registry = {r["provider"]: r for r in load_registry()}
    cards_dir = PROTOCOL / "cards"

    slots = [
        r for r in csv.DictReader(schedule.open())
        if int(r["collection_round"]) == args.round
    ]
    print(f"round {args.round}: {len(slots)} slot(s)")
    counts: dict[str, int] = {}
    for slot in sorted(slots, key=lambda r: int(r["execution_position"])):
        card_path = cards_dir / f"{slot['card_id']}.json"
        if not card_path.exists():
            raise SystemExit(f"frozen card missing: {card_path}")
        outcome = run_slot(slot, registry[slot["provider"]], case,
                           card_path.read_text().strip(), args.dry_run)
        counts[outcome["status"]] = counts.get(outcome["status"], 0) + 1
    print("outcomes:", json.dumps(counts, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    build = sub.add_parser("build-schedule", help="write the frozen 375-slot schedule once")
    build.add_argument("--seed", type=int, default=20260805)

    collect = sub.add_parser("collect", help="run one collection round")
    collect.add_argument("--round", type=int, required=True)
    collect.add_argument("--dry-run", action="store_true",
                         help="render every request and print its hash without calling")

    args = parser.parse_args()
    if args.command == "build-schedule":
        print("wrote", build_schedule(args.seed))
    else:
        cmd_collect(args)


if __name__ == "__main__":
    main()
