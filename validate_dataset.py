#!/usr/bin/env python3
"""
Typography Intelligence — Dataset Validation Script
=====================================================
Validates that typography_training.jsonl conforms to the Alpaca
instruction format expected by train_typography.py.

Checks:
  - Every line is valid JSON
  - Required fields: instruction, input, output
  - No empty instruction or output fields
  - Metadata fields present and valid (type, rule/source_language+target_language, language)
  - Unicode properly encoded (no double-escaped sequences)
  - No duplicate entries
  - Instruction text varies (not all identical)
  - raw != correct in correction pairs (teaching signal exists)
  - Statistics: languages, rules, pair types

Usage:
  python validate_dataset.py [path_to_jsonl]
"""

import json
import sys
import re
from collections import Counter
from pathlib import Path


def validate_dataset(path: str) -> bool:
    """Run all validations and print a summary report. Returns True if clean."""

    filepath = Path(path)
    if not filepath.exists():
        print(f"ERROR: File not found: {path}")
        return False

    # ------------------------------------------------------------------
    # Pass 1: Parse all lines, collect records
    # ------------------------------------------------------------------
    records: list[dict] = []
    parse_errors: list[tuple[int, str]] = []

    with open(filepath, "r", encoding="utf-8") as f:
        for lineno, raw_line in enumerate(f, start=1):
            line = raw_line.strip()
            if not line:
                continue  # skip blank lines
            try:
                record = json.loads(line)
                record["_lineno"] = lineno
                records.append(record)
            except json.JSONDecodeError as e:
                parse_errors.append((lineno, str(e)))

    total = len(records)

    # ------------------------------------------------------------------
    # Pass 2: Field-level validation
    # ------------------------------------------------------------------
    REQUIRED_FIELDS = {"instruction", "input", "output"}
    missing_fields: list[tuple[int, set]] = []
    empty_instruction: list[int] = []
    empty_output: list[int] = []
    empty_input: list[int] = []  # informational only; some formats allow empty input

    missing_metadata: list[int] = []
    missing_meta_type: list[int] = []
    missing_meta_language: list[int] = []
    missing_meta_rule: list[int] = []  # rule required for non-cross_language types

    double_escaped: list[tuple[int, str]] = []
    raw_equals_correct: list[tuple[int, str, str]] = []

    instructions = Counter()
    languages = Counter()
    rules = Counter()
    pair_types = Counter()
    registers = Counter()

    seen_hashes: dict[str, int] = {}  # hash -> first lineno
    duplicates: list[tuple[int, int]] = []  # (dup_lineno, original_lineno)

    for rec in records:
        ln = rec["_lineno"]

        # --- Required fields ---
        present = set(rec.keys()) - {"_lineno"}
        missing = REQUIRED_FIELDS - present
        if missing:
            missing_fields.append((ln, missing))
            continue  # skip further checks if core fields missing

        # --- Empty values ---
        if not rec["instruction"] or not rec["instruction"].strip():
            empty_instruction.append(ln)
        if not rec["output"] or not rec["output"].strip():
            empty_output.append(ln)
        if not rec["input"] and rec["input"] is not None:
            empty_input.append(ln)

        # --- Instruction diversity ---
        instructions[rec["instruction"]] += 1

        # --- Duplicate detection (based on instruction+input+output) ---
        sig = json.dumps(
            [rec["instruction"], rec["input"], rec["output"]], ensure_ascii=False, sort_keys=True
        )
        if sig in seen_hashes:
            duplicates.append((ln, seen_hashes[sig]))
        else:
            seen_hashes[sig] = ln

        # --- Double-escaped Unicode ---
        for field in ("instruction", "input", "output"):
            val = rec.get(field, "")
            if val and re.search(r"\\u[0-9a-fA-F]{4}", val):
                double_escaped.append((ln, field))

        # --- Metadata validation ---
        meta = rec.get("metadata")
        if meta is None:
            missing_metadata.append(ln)
        else:
            ptype = meta.get("type")
            if not ptype:
                missing_meta_type.append(ln)
            else:
                pair_types[ptype] += 1

            # Language tracking
            if ptype == "cross_language":
                src = meta.get("source_language")
                tgt = meta.get("target_language")
                if src:
                    languages[src] += 1
                if tgt:
                    languages[tgt] += 1
                if not src or not tgt:
                    missing_meta_language.append(ln)
            else:
                lang = meta.get("language")
                if not lang:
                    missing_meta_language.append(ln)
                else:
                    languages[lang] += 1

            # Rule tracking (not required for cross_language)
            rule = meta.get("rule")
            if rule:
                rules[rule] += 1
            elif ptype not in ("cross_language",):
                missing_meta_rule.append(ln)

            # Register tracking (optional)
            reg = meta.get("register")
            if reg:
                registers[reg] += 1

        # --- raw == correct in correction pairs ---
        if meta and meta.get("type") == "correction":
            if rec["input"] and rec["output"] and rec["input"] == rec["output"]:
                raw_equals_correct.append((ln, rec["input"][:60], rec["output"][:60]))

    # ------------------------------------------------------------------
    # Report
    # ------------------------------------------------------------------
    issues_found = False

    def section(title: str):
        print(f"\n{'=' * 60}")
        print(f"  {title}")
        print(f"{'=' * 60}")

    def issue(msg: str, items: list, limit: int = 5):
        nonlocal issues_found
        if items:
            issues_found = True
            print(f"\n  ISSUE: {msg} ({len(items)} found)")
            for item in items[:limit]:
                print(f"    - {item}")
            if len(items) > limit:
                print(f"    ... and {len(items) - limit} more")
        else:
            print(f"\n  OK: {msg} -- none found")

    print("\n")
    section("TYPOGRAPHY TRAINING DATASET VALIDATION")
    print(f"\n  File: {filepath}")
    print(f"  Total records: {total}")

    # --- Parse errors ---
    section("1. JSON PARSING")
    issue("Malformed JSON lines", parse_errors)

    # --- Field presence ---
    section("2. REQUIRED FIELDS (instruction, input, output)")
    issue("Records missing required fields", missing_fields)
    issue("Empty instruction fields", empty_instruction)
    issue("Empty output fields", empty_output)
    print(f"\n  INFO: Records with empty input field: {len(empty_input)}")

    # --- Metadata ---
    section("3. METADATA VALIDATION")
    issue("Records missing metadata entirely", missing_metadata)
    issue("Records missing metadata.type", missing_meta_type)
    issue("Records missing metadata.language (or source/target for cross_language)", missing_meta_language)
    issue("Non-cross_language records missing metadata.rule", missing_meta_rule)

    # --- Duplicates ---
    section("4. DUPLICATE DETECTION")
    issue("Duplicate records (instruction+input+output)", duplicates)

    # --- Unicode encoding ---
    section("5. UNICODE ENCODING")
    issue("Fields with double-escaped Unicode (\\\\uXXXX in decoded string)", double_escaped)

    # --- Instruction diversity ---
    section("6. INSTRUCTION DIVERSITY")
    unique_instructions = len(instructions)
    print(f"\n  Unique instruction templates: {unique_instructions}")
    print(f"  Top 5 most frequent instructions:")
    for instr, count in instructions.most_common(5):
        truncated = instr[:80] + ("..." if len(instr) > 80 else "")
        print(f"    [{count:4d}x] {truncated}")

    if unique_instructions == 1:
        issues_found = True
        print("\n  ISSUE: All records share the same instruction -- no diversity!")
    else:
        print(f"\n  OK: Instructions are diverse ({unique_instructions} unique templates)")

    # --- raw == correct ---
    section("7. TEACHING SIGNAL (raw != correct in correction pairs)")
    issue("Correction pairs where input == output (no teaching signal)", raw_equals_correct)

    # --- Statistics ---
    section("8. DATASET STATISTICS")

    print(f"\n  Total records:        {total}")
    print(f"  Unique languages:     {len(languages)}")
    print(f"  Unique rules:         {len(rules)}")
    print(f"  Unique pair types:    {len(pair_types)}")
    print(f"  Unique registers:     {len(registers)}")

    print(f"\n  --- Languages ---")
    for lang, count in languages.most_common():
        print(f"    {lang:12s}  {count:4d}")

    print(f"\n  --- Pair types ---")
    for pt, count in pair_types.most_common():
        print(f"    {pt:20s}  {count:4d}")

    print(f"\n  --- Rules (top 15) ---")
    for rule, count in rules.most_common(15):
        print(f"    {rule:35s}  {count:4d}")
    if len(rules) > 15:
        print(f"    ... and {len(rules) - 15} more rules")

    print(f"\n  --- Registers ---")
    for reg, count in registers.most_common():
        print(f"    {reg:15s}  {count:4d}")

    # --- Alpaca format compatibility ---
    section("9. ALPACA FORMAT COMPATIBILITY")
    # Check that format_alpaca from train_typography.py would work
    format_ok = True
    for rec in records[:5]:
        test_rec = {k: v for k, v in rec.items() if k != "_lineno"}
        test_rec.pop("metadata", None)
        try:
            if test_rec.get("input"):
                _ = (
                    "Below is an instruction that describes a task, paired with an input "
                    "that provides further context. Write a response that appropriately "
                    "completes the request.\n\n"
                    f"### Instruction:\n{test_rec['instruction']}\n\n"
                    f"### Input:\n{test_rec['input']}\n\n"
                    f"### Response:\n{test_rec['output']}"
                )
            else:
                _ = (
                    "Below is an instruction that describes a task. Write a response "
                    "that appropriately completes the request.\n\n"
                    f"### Instruction:\n{test_rec['instruction']}\n\n"
                    f"### Response:\n{test_rec['output']}"
                )
        except (KeyError, TypeError) as e:
            format_ok = False
            print(f"\n  ISSUE: format_alpaca would fail on line {rec['_lineno']}: {e}")

    if format_ok:
        print(f"\n  OK: All sampled records are compatible with format_alpaca()")
    else:
        issues_found = True

    # --- Final verdict ---
    section("FINAL VERDICT")
    if not issues_found:
        print("\n  ALL CHECKS PASSED. Dataset is clean and Alpaca-compatible.\n")
    else:
        print("\n  ISSUES DETECTED. See details above.\n")

    return not issues_found


if __name__ == "__main__":
    dataset_path = sys.argv[1] if len(sys.argv) > 1 else "typography_training.jsonl"
    clean = validate_dataset(dataset_path)
    sys.exit(0 if clean else 1)
