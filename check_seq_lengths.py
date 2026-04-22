#!/usr/bin/env python3
"""
Sequence length analysis for Typography Intelligence training data.

Reads the JSONL dataset, formats each record using the Alpaca template
(matching train_typography.py), and estimates token counts.

Reports: max, mean, median, p95, p99, and recommends a max_seq_length.
"""

import json
import statistics

JSONL_PATH = "typography_training.jsonl"


def format_alpaca(example: dict) -> str:
    """Format a training example in Alpaca instruction format (mirrors train_typography.py)."""
    if example.get("input"):
        return (
            "Below is an instruction that describes a task, paired with an input "
            "that provides further context. Write a response that appropriately "
            "completes the request.\n\n"
            f"### Instruction:\n{example['instruction']}\n\n"
            f"### Input:\n{example['input']}\n\n"
            f"### Response:\n{example['output']}"
        )
    else:
        return (
            "Below is an instruction that describes a task. Write a response "
            "that appropriately completes the request.\n\n"
            f"### Instruction:\n{example['instruction']}\n\n"
            f"### Response:\n{example['output']}"
        )


def estimate_tokens(text: str) -> int:
    """Estimate token count using chars/4 heuristic (better than whitespace split for multilingual text)."""
    return max(1, len(text) // 4)


def next_power_of_2(n: int) -> int:
    """Return the smallest power of 2 >= n."""
    p = 1
    while p < n:
        p *= 2
    return p


def main():
    records = []
    with open(JSONL_PATH, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            rec.pop("metadata", None)
            records.append(rec)

    print(f"Total records: {len(records)}\n")

    token_counts = []
    char_counts = []
    for rec in records:
        text = format_alpaca(rec)
        char_counts.append(len(text))
        token_counts.append(estimate_tokens(text))

    token_counts.sort()
    char_counts.sort()

    n = len(token_counts)
    p95_idx = int(n * 0.95)
    p99_idx = int(n * 0.99)

    mean_tok = statistics.mean(token_counts)
    median_tok = statistics.median(token_counts)
    max_tok = max(token_counts)
    min_tok = min(token_counts)
    p95_tok = token_counts[p95_idx]
    p99_tok = token_counts[p99_idx]

    print("=== Token estimates (chars / 4) ===")
    print(f"  Min:    {min_tok}")
    print(f"  Mean:   {mean_tok:.1f}")
    print(f"  Median: {median_tok}")
    print(f"  P95:    {p95_tok}")
    print(f"  P99:    {p99_tok}")
    print(f"  Max:    {max_tok}")

    print(f"\n=== Character counts ===")
    print(f"  Min:    {min(char_counts)}")
    print(f"  Mean:   {statistics.mean(char_counts):.1f}")
    print(f"  Median: {statistics.median(char_counts)}")
    print(f"  P95:    {char_counts[p95_idx]}")
    print(f"  P99:    {char_counts[p99_idx]}")
    print(f"  Max:    {max(char_counts)}")

    # Recommendation: smallest power-of-2 that covers p99 with ~10% headroom
    target = int(p99_tok * 1.1)
    recommended = next_power_of_2(target)

    print(f"\n=== Recommendation ===")
    print(f"  P99 with 10% headroom: {target} tokens")
    print(f"  Recommended max_seq_length (next power of 2): {recommended}")
    print(f"  Current default in train_typography.py: 512")

    if recommended < 512:
        print(f"  -> Current value (512) is HIGHER than needed. Can reduce to {recommended}.")
    elif recommended > 512:
        print(f"  -> Current value (512) is TOO LOW. Should increase to {recommended}.")
    else:
        print(f"  -> Current value (512) is appropriate.")

    # Distribution buckets
    print(f"\n=== Distribution (token estimate buckets) ===")
    buckets = [32, 64, 128, 256, 512, 1024, 2048]
    for b in buckets:
        count = sum(1 for t in token_counts if t <= b)
        pct = count / n * 100
        print(f"  <= {b:5d}: {count:5d} ({pct:5.1f}%)")


if __name__ == "__main__":
    main()
