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
    python -m agenticmcdm.harness generate-cards
    # fill K3 to K10 in run/card_admissibility.csv by hand
    python -m agenticmcdm.harness freeze-cards --seed 20260806
    python -m agenticmcdm.harness collect --round 1 --dry-run
    python -m agenticmcdm.harness collect --round 1

Card generation and freezing are two commands rather than one on purpose. Generation writes
candidates and a checklist worksheet; freezing refuses to run until every item on that sheet
is a recorded pass or fail. The neutral within-role index is drawn at freeze time, so no card
can influence its own label.
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
import time

from agenticmcdm import providers, schema_check


class ConfigurationFault(RuntimeError):
    """A fault that every remaining slot in the round would hit in the same way.

    A wrong key, a model identifier the account cannot reach, a malformed request. The round
    stops rather than spending its remaining slots proving the same point 74 more times.
    Slots already recorded stay recorded; the round is resumed after the cause is fixed.
    """


ROOT = pathlib.Path(__file__).resolve().parents[2]
PROTOCOL = ROOT / "protocol"
PROMPTS = ROOT / "prompts"
MODELS = ROOT / "models"
RUN = ROOT / "run"
DATA = ROOT / "data"
CARDS = PROTOCOL / "cards"
CANDIDATES = RUN / "card_candidates"
WORKSHEET = RUN / "card_admissibility.csv"

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


def completed_run_ids() -> set[str]:
    """Slots that must not be called again, read back from the ledger.

    A slot is finished once it produced model output, and it is finished just as surely once
    its one permitted retry has been spent, whatever that retry returned. Calling either
    again would put a third physical request against a slot the protocol allows two.

    A slot whose only record is a failed first attempt is not finished. That is exactly what
    an aborted round leaves behind, and it is meant to be picked up once the cause is fixed.
    """
    path = DATA / "ledger.csv"
    if not path.exists():
        return set()
    done: set[str] = set()
    with path.open(newline="") as handle:
        for row in csv.DictReader(handle):
            if row.get("attempt_type") not in ("initial", "transport_retry"):
                continue
            if row.get("transport_status") == "success":
                done.add(row["run_id"])
            elif row.get("attempt_type") == "transport_retry":
                done.add(row["run_id"])
    return done


def store_raw(attempt_id: str, raw: bytes) -> str:
    path = DATA / "raw" / f"{attempt_id}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    return str(path.relative_to(ROOT))


# ------------------------------------------------------------------ calling


def call_with_one_retry(base: dict, system: str, user: str,
                        settings: dict) -> tuple[object | None, int]:
    """The initial attempt and the one transport retry the protocol allows, and no more.

    Returns the reply with the attempt count that produced it, or `(None, 2)` when both
    attempts failed a fault that might not have repeated. Every physical request writes its
    own ledger row before this returns, so a failure is recorded even when nothing came back.

    Raises `ConfigurationFault` when the provider rejected the request itself, since the
    retry would be spent proving that the same request is still unacceptable.
    """
    attempts, reply = 0, None
    while attempts < 2 and reply is None:
        attempts += 1
        attempt_type = "initial" if attempts == 1 else "transport_retry"
        try:
            reply = providers.call(base["adapter"], base["api_model_id"],
                                   system, user, settings)
        except providers.TransportError as exc:
            status = f"transport_error_{exc.status}" if exc.status else "transport_error"
            append_ledger({**base, "attempt_id": f"{base['run_id']}_{attempt_type}",
                           "attempt_type": attempt_type, "requested_at_utc": _now(),
                           "transport_status": status, "validation_status": "",
                           "schema_error_codes": str(exc)[:200]})
            if not providers.is_retryable(exc):
                raise ConfigurationFault(
                    f"{base['provider']} rejected the request with HTTP {exc.status}. "
                    f"Sending it again would not change that, and the remaining calls "
                    f"would fail the same way.\n{exc}"
                ) from exc
            if attempts == 2:
                return None, attempts
            delay = providers.retry_delay(exc)
            print(f"  {base['run_id']}: {status}, retrying once in {delay:.0f}s")
            time.sleep(delay)
    return reply, attempts


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
        "prompt_version": schema_check.PROMPT_VERSION,
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
    reply, attempts = call_with_one_retry(base, system, user, settings)
    if reply is None:
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


# ------------------------------------------------------------------ cards


def load_checklist() -> list[dict]:
    """The admissibility items, in the order the checklist file states them."""
    import yaml

    spec = yaml.safe_load((PROTOCOL / "card_admissibility_checklist.yaml").read_text())
    return spec["checks"]


def generate_card(model_row: dict, role: str, dry_run: bool) -> dict:
    """One card-generation call, under the same retry and repair rules a decision slot gets.

    The generator is asked for the six fields it writes and never for an identifier. The
    neutral within-role index is drawn later, once every card has passed, so that no card
    can influence its own label.
    """
    system = (PROMPTS / "card_system.txt").read_text().strip()
    user = (PROMPTS / "card_generation.txt").read_text().replace("{ROLE}", role)
    run_id = f"G_{model_row['provider']}_{role}"

    base = {
        "run_id": run_id, "collection_round": 0, "execution_position": 0,
        "phase": "card_generation",
        "provider": model_row["provider"],
        "adapter": model_row.get("adapter") or "openai_compatible",
        "api_model_id": model_row["api_model_id"],
        "snapshot": model_row.get("snapshot", ""),
        "card_id": "", "card_hash": "",
        "prompt_version": "card_v1_icaira",
        "request_hash": _hash(system + user), "system_prompt_hash": _hash(system),
        "matrix_hash": "", "pair_order_hash": "",
        "requested_temperature": model_row.get("requested_temperature", ""),
        "top_p": model_row.get("top_p", ""),
        "seed": model_row.get("seed", ""),
    }

    if dry_run:
        print(f"[dry-run] {run_id} -> {model_row['api_model_id']}, "
              f"request hash {base['request_hash']}, {len(user.split())} words")
        return {"status": "dry_run", **base}

    settings = dict(model_row)
    reply, attempts = call_with_one_retry(base, system, user, settings)
    if reply is None:
        return {"status": "transport_failed", **base}

    attempt_type = "initial" if attempts == 1 else "transport_retry"
    attempt_id = f"{run_id}_{attempt_type}"
    raw_path = store_raw(attempt_id, reply.raw)

    def record(attempt_id: str, attempt_type: str, reply, raw_path: str, result) -> None:
        append_ledger({**base, "attempt_id": attempt_id, "attempt_type": attempt_type,
                       "requested_at_utc": _now(), "reported_model": reply.reported_model,
                       "provider_request_id": reply.provider_request_id,
                       "latency_ms": reply.latency_ms, "input_tokens": reply.input_tokens,
                       "output_tokens": reply.output_tokens, "raw_response_path": raw_path,
                       "transport_status": "success",
                       "validation_status": "valid" if result.ok else "invalid",
                       "schema_error_codes": ";".join(result.codes)})

    def parse(text: str):
        try:
            card = extract_json(text)
        except json.JSONDecodeError as exc:
            return None, schema_check.Result(False, [f"E_JSON: {exc}"])
        return card, schema_check.check_card(card, role, expect_persona_id=False)

    card, result = parse(reply.text)
    record(attempt_id, attempt_type, reply, raw_path, result)
    if result.ok:
        return {"status": "valid", "card": card, **base}

    # The checklist allows one structural repair that preserves semantic content.
    repair_user = user + "\n\n" + REPAIR_MESSAGE.format(errors="\n".join(result.errors))
    attempt_id = f"{run_id}_schema_repair"
    try:
        repair, _ = call_with_one_retry({**base, "run_id": f"{run_id}_repair"},
                                        system, repair_user, settings)
    except ConfigurationFault:
        raise
    if repair is None:
        return {"status": "repair_failed", **base}

    raw_path = store_raw(attempt_id, repair.raw)
    card, repair_result = parse(repair.text)
    record(attempt_id, "schema_repair", repair, raw_path, repair_result)
    if repair_result.ok:
        return {"status": "repaired_valid", "card": card, **base}
    return {"status": "invalid", "errors": repair_result.errors, **base}


def cmd_generate_cards(args: argparse.Namespace) -> None:
    """Write card candidates and the admissibility worksheet. Freezing is a separate step."""
    if CARDS.exists() and any(CARDS.glob("P-*.json")):
        raise SystemExit(
            f"{CARDS} already holds frozen cards. Cards are frozen once. Record a deviation "
            "if a set genuinely has to be regenerated."
        )
    registry = load_registry()
    generators = [r for r in registry if r["role_in_study"] in ("generator", "both")]
    if not generators:
        raise SystemExit("model_registry.csv holds no generator rows")
    if args.generator:
        generators = [r for r in generators if r["provider"] == args.generator]
        if not generators:
            raise SystemExit(f"no generator row named {args.generator!r}")

    CANDIDATES.mkdir(parents=True, exist_ok=True)
    written, failed = [], []
    for model_row in generators:
        for role in ROLES:
            target = CANDIDATES / f"{model_row['provider']}_{role}.json"
            if target.exists() and not args.generator:
                print(f"  {target.name} already written, leaving it alone")
                continue
            outcome = generate_card(model_row, role, args.dry_run)
            if args.dry_run:
                continue
            if "card" not in outcome:
                failed.append((model_row["provider"], role, outcome["status"]))
                print(f"  [FAIL] {model_row['provider']} {role}: {outcome['status']}")
                continue
            target.write_text(json.dumps(outcome["card"], indent=2, ensure_ascii=False) + "\n")
            written.append(target)
            print(f"  [ok]   {target.name}  ({outcome['status']})")

    if args.dry_run:
        return
    print(f"\n{len(written)} candidate(s) written to {CANDIDATES}")
    if failed:
        raise SystemExit(
            f"{len(failed)} generation(s) did not produce a structurally valid card: "
            f"{failed}. Per the checklist failure rule a generator that cannot produce an "
            "admissible set is regenerated once with `--generator <provider>`, and a second "
            "failure removes it from the study with the cause reported."
        )
    write_worksheet()


def write_worksheet() -> None:
    """Write the admissibility worksheet, pre-filling only what a machine can decide.

    K1, K2 and K11 are structural: fields and limits, the requested role, and model
    self-reference. The harness fills those and leaves the rest blank, because items such as
    "no claim that every person in the occupation shares these preferences" need a reader.
    Freezing refuses to proceed while any cell is blank.
    """
    checks = load_checklist()
    ids = [c["id"] for c in checks]
    rows = []
    for path in sorted(CANDIDATES.glob("*.json")):
        generator, role = path.stem.rsplit("_", 1)
        card = json.loads(path.read_text())
        structural = schema_check.check_card(card, role, expect_persona_id=False)
        self_reference = schema_check.find_self_reference(card)
        row = {"candidate": path.name, "generator": generator, "role": role}
        for check_id in ids:
            if check_id == "K1":
                row[check_id] = "pass" if structural.ok else "fail"
            elif check_id == "K2":
                row[check_id] = "pass" if card.get("role") == role else "fail"
            elif check_id == "K11":
                row[check_id] = "fail" if self_reference else "pass"
            else:
                row[check_id] = ""
        rows.append(row)

    WORKSHEET.parent.mkdir(parents=True, exist_ok=True)
    with WORKSHEET.open("w", newline="") as handle:
        handle.write("# Admissibility worksheet. Every cell must read exactly `pass` before "
                     "cards can be frozen.\n")
        handle.write("# K1, K2 and K11 were filled by the harness. K3 to K10 need a reader; "
                     "see protocol/card_admissibility_checklist.yaml.\n")
        handle.write("# A `fail` on any item voids that generator's whole set of three.\n")
        writer = csv.DictWriter(handle, fieldnames=["candidate", "generator", "role"] + ids)
        writer.writeheader()
        writer.writerows(rows)
    print(f"wrote {WORKSHEET} with {len(rows)} row(s); fill K3 to K10 before freezing")


def read_worksheet() -> list[dict]:
    if not WORKSHEET.exists():
        raise SystemExit(f"no {WORKSHEET}; run generate-cards first")
    with WORKSHEET.open() as handle:
        return list(csv.DictReader(l for l in handle if not l.startswith("#")))


def cmd_freeze_cards(args: argparse.Namespace) -> None:
    """Assign the neutral indices and write the frozen cards. Refuses on an unfinished sheet."""
    if CARDS.exists() and any(CARDS.glob("P-*.json")):
        raise SystemExit(f"{CARDS} already holds frozen cards; cards are frozen once")

    registry = load_registry()
    generators = [r for r in registry if r["role_in_study"] in ("generator", "both")]
    expected = {f"{g['provider']}_{role}.json" for g in generators for role in ROLES}
    present = {p.name for p in CANDIDATES.glob("*.json")}
    if present != expected:
        raise SystemExit(
            f"candidate set is incomplete. missing: {sorted(expected - present)}; "
            f"unexpected: {sorted(present - expected)}"
        )

    ids = [c["id"] for c in load_checklist()]
    rows = read_worksheet()
    blank = [(r["candidate"], k) for r in rows for k in ids if not r[k].strip()]
    if blank:
        raise SystemExit(
            f"{len(blank)} checklist cell(s) are still blank, for example {blank[:5]}. "
            "Every item is a recorded pass or fail before any card is frozen."
        )
    failures = [(r["generator"], r["candidate"], k) for r in rows for k in ids
                if r[k].strip().lower() != "pass"]
    if failures:
        voided = sorted({g for g, _, _ in failures})
        raise SystemExit(
            f"{len(failures)} item(s) failed: {failures}. Per the failure rule this voids "
            f"the whole set of three for {voided}. Regenerate with "
            f"`generate-cards --generator <provider>`, once. A second failure removes the "
            "generator from the study and the exclusion is reported with its cause."
        )

    rng = random.Random(args.seed)
    CARDS.mkdir(parents=True, exist_ok=True)
    assignment = []
    for role in ROLES:
        order = [g["provider"] for g in generators]
        rng.shuffle(order)
        for index, provider in enumerate(order, start=1):
            persona_id = f"P-{role}-{index}"
            card = json.loads((CANDIDATES / f"{provider}_{role}.json").read_text())
            frozen = {"persona_id": persona_id, **card}
            result = schema_check.check_card(frozen, role)
            if not result.ok:
                raise SystemExit(f"{persona_id} failed structural validation: {result.errors}")
            text = json.dumps(frozen, indent=2, ensure_ascii=False) + "\n"
            (CARDS / f"{persona_id}.json").write_text(text)
            assignment.append({"persona_id": persona_id, "role": role,
                               "generator": provider, "card_hash": _hash(text)})

    with (CARDS / "_assignment.csv").open("w", newline="") as handle:
        handle.write("# Which generator wrote which card, needed for the self-authored "
                     "contrast and for scoring the blinding check.\n")
        handle.write("# This file is never placed in any prompt. Decision respondents see "
                     "the card JSON and nothing else.\n")
        handle.write(f"# Index assignment seed: {args.seed}\n")
        writer = csv.DictWriter(handle,
                                fieldnames=["persona_id", "role", "generator", "card_hash"])
        writer.writeheader()
        writer.writerows(assignment)

    print(f"froze {len(assignment)} card(s) in {CARDS}")
    print(f"assignment recorded in {CARDS / '_assignment.csv'} with seed {args.seed}")


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
    counts: dict[str, int] = {}
    ordered = sorted(slots, key=lambda r: int(r["execution_position"]))
    if args.role:
        # The pilot is the CFO slice of rounds 1 to 3. Restricting the role selects that
        # slice out of the frozen schedule rather than building a second schedule for it,
        # so the pilot slots keep the execution order and positions they were assigned.
        if args.role not in ROLES:
            raise SystemExit(f"unknown role {args.role!r}; known: {ROLES}")
        ordered = [r for r in ordered if r["card_id"].split("-")[1] == args.role]
    scheduled = len(ordered)
    if not args.dry_run:
        done = completed_run_ids()
        ordered = [r for r in ordered if r["run_id"] not in done]
    scope = f" for {args.role}" if args.role else ""
    print(f"round {args.round}{scope}: {len(ordered)} slot(s) to run "
          f"out of {scheduled} scheduled")
    try:
        for slot in ordered:
            card_path = cards_dir / f"{slot['card_id']}.json"
            if not card_path.exists():
                raise SystemExit(f"frozen card missing: {card_path}")
            outcome = run_slot(slot, registry[slot["provider"]], case,
                               card_path.read_text().strip(), args.dry_run)
            counts[outcome["status"]] = counts.get(outcome["status"], 0) + 1
    except ConfigurationFault as exc:
        done = sum(counts.values())
        print("outcomes so far:", json.dumps(counts, indent=2))
        raise SystemExit(
            f"round {args.round} stopped after {done} of {len(ordered)} slot(s).\n{exc}\n"
            f"Fix the cause and rerun this round; recorded slots are in the ledger."
        ) from exc
    print("outcomes:", json.dumps(counts, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    build = sub.add_parser("build-schedule", help="write the frozen 375-slot schedule once")
    build.add_argument("--seed", type=int, default=20260805)

    cards = sub.add_parser("generate-cards",
                           help="call each generator once per role and write candidates")
    cards.add_argument("--generator", help="regenerate one generator's set of three")
    cards.add_argument("--dry-run", action="store_true",
                       help="render every request and print its hash without calling")

    freeze = sub.add_parser("freeze-cards",
                            help="assign neutral indices and write the frozen cards")
    freeze.add_argument("--seed", type=int, default=20260806)

    collect = sub.add_parser("collect", help="run one collection round")
    collect.add_argument("--round", type=int, required=True)
    collect.add_argument("--role", help="restrict to one role; the pilot is CFO, rounds 1 to 3")
    collect.add_argument("--dry-run", action="store_true",
                         help="render every request and print its hash without calling")

    args = parser.parse_args()
    if args.command == "build-schedule":
        print("wrote", build_schedule(args.seed))
    elif args.command == "generate-cards":
        cmd_generate_cards(args)
    elif args.command == "freeze-cards":
        cmd_freeze_cards(args)
    else:
        cmd_collect(args)


if __name__ == "__main__":
    main()
