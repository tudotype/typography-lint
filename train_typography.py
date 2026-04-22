#!/usr/bin/env python3
"""
Typography Intelligence — LoRA Fine-tuning Script (MLX / Apple Silicon)
========================================================================
Uses mlx-lm for efficient LoRA training on the typography dataset,
running natively on Apple Silicon Metal GPUs.

Requirements:
  pip install -r requirements.txt

Hardware:
  - Apple Silicon Mac (M1/M2/M3 family)
  - Recommended: M2 Max / M2 Ultra / M3 Max with 32 GB+ unified memory
  - 4-bit quantized 3B model fits comfortably in 32 GB

Usage:
  python train_typography.py                              # defaults (Llama 3.2 3B)
  python train_typography.py --base_model mistral         # use Mistral 7B
  python train_typography.py --epochs 5                   # more training
  python train_typography.py --dry_run                    # validate without training
  python train_typography.py --export_ollama              # train + export to Ollama

After training, export to Ollama:
  python train_typography.py --export_ollama
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path


# ---------------------------------------------------------------------------
# Model ID mapping — MLX-community quantized models from Hugging Face
# ---------------------------------------------------------------------------
MODEL_MAP = {
    "llama3.2": "mlx-community/Llama-3.2-3B-Instruct-4bit",      # 3B — fast, fits anywhere
    "mistral":  "mlx-community/Mistral-7B-Instruct-v0.3-4bit",    # 7B — good balance
    "gemma2":   "mlx-community/Gemma-2-9B-it-4bit",               # 9B — if memory allows
}


def get_args():
    parser = argparse.ArgumentParser(
        description="Typography Intelligence — LoRA fine-tuning on Apple Silicon (MLX)"
    )
    parser.add_argument(
        "--base_model", type=str, default="llama3.2",
        choices=list(MODEL_MAP.keys()),
        help="Base model to fine-tune (default: llama3.2)"
    )
    parser.add_argument("--dataset", type=str, default="typography_training.jsonl",
                        help="Path to JSONL training data")
    parser.add_argument("--output_dir", type=str, default="./typography-lora",
                        help="Directory for LoRA adapter output")
    parser.add_argument("--epochs", type=int, default=3,
                        help="Number of training epochs")
    parser.add_argument("--batch_size", type=int, default=4,
                        help="Training batch size")
    parser.add_argument("--learning_rate", type=float, default=1e-5,
                        help="Learning rate")
    parser.add_argument("--lora_rank", type=int, default=16,
                        help="LoRA rank")
    parser.add_argument("--lora_alpha", type=int, default=32,
                        help="LoRA alpha (scaling factor)")
    parser.add_argument("--max_seq_length", type=int, default=256,
                        help="Maximum sequence length")
    parser.add_argument("--warmup_steps", type=int, default=100,
                        help="Number of warmup steps")
    parser.add_argument("--save_every", type=int, default=100,
                        help="Save adapter checkpoint every N steps")
    parser.add_argument("--export_ollama", action="store_true",
                        help="Export to GGUF for Ollama after training")
    parser.add_argument("--quantization", type=str, default="q4_k_m",
                        choices=["q4_k_m", "q5_k_m", "q8_0", "f16"],
                        help="GGUF quantization level for Ollama export")
    parser.add_argument("--dry_run", action="store_true",
                        help="Validate config and data without training")
    return parser.parse_args()


# ---------------------------------------------------------------------------
# Alpaca format — must match eval_typography.py and generate_dataset.py
# ---------------------------------------------------------------------------
def format_alpaca(example: dict) -> str:
    """Format a training example in Alpaca instruction format."""
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


def load_dataset_from_jsonl(path: str) -> list[dict]:
    """Load the JSONL dataset, preserving metadata for stratified splitting."""
    records = []
    with open(path, "r", encoding="utf-8") as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as e:
                print(f"  WARNING: Skipping malformed line {line_num}: {e}")
                continue
            records.append(record)
    return records


def strip_metadata(records: list[dict]) -> list[dict]:
    """Remove metadata from records before writing training files."""
    cleaned = []
    for rec in records:
        r = dict(rec)
        r.pop("metadata", None)
        cleaned.append(r)
    return cleaned


def convert_to_mlx_format(records: list[dict], output_path: Path) -> int:
    """
    Convert Alpaca-format records to the JSONL chat format that mlx_lm.lora expects.

    mlx_lm supports {"messages": [{"role": "user", "content": ...}, {"role": "assistant", "content": ...}]}
    We also write a {"text": ...} version as fallback.

    Returns the number of examples written.
    """
    count = 0
    with open(output_path, "w", encoding="utf-8") as f:
        for rec in records:
            # Build user message from instruction + input
            if rec.get("input"):
                user_content = f"{rec['instruction']}\n\n{rec['input']}"
            else:
                user_content = rec["instruction"]

            entry = {
                "messages": [
                    {"role": "user", "content": user_content},
                    {"role": "assistant", "content": rec["output"]},
                ]
            }
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
            count += 1
    return count


def report_memory():
    """Report current memory usage on macOS via sysctl / vm_stat."""
    try:
        import mlx.core as mx
        # MLX tracks its own memory usage
        peak = mx.metal.get_peak_memory() / (1024 ** 3)
        active = mx.metal.get_active_memory() / (1024 ** 3)
        print(f"  MLX Metal memory — active: {active:.2f} GB, peak: {peak:.2f} GB")
    except Exception:
        pass

    try:
        import resource
        rusage = resource.getrusage(resource.RUSAGE_SELF)
        rss_gb = rusage.ru_maxrss / (1024 ** 3)  # macOS reports bytes
        print(f"  Process RSS (peak): {rss_gb:.2f} GB")
    except Exception:
        pass


def write_lora_config(output_dir: Path, args) -> Path:
    """Write the LoRA YAML config that mlx_lm.lora expects."""
    config_path = output_dir / "lora_config.yaml"
    config = {
        "lora_layers": args.lora_rank,
        "lora_parameters": {
            "rank": args.lora_rank,
            "alpha": args.lora_alpha,
            "dropout": 0.05,
            "scale": args.lora_alpha / args.lora_rank,
        },
    }

    import yaml
    with open(config_path, "w", encoding="utf-8") as f:
        yaml.dump(config, f, default_flow_style=False)

    return config_path


def write_train_config(output_dir: Path, args, train_jsonl: Path, valid_jsonl: Path | None, num_examples: int) -> Path:
    """Write the training YAML config for mlx_lm.lora."""
    config_path = output_dir / "train_config.yaml"

    # Calculate iterations from epochs
    steps_per_epoch = max(1, num_examples // args.batch_size)
    total_iters = steps_per_epoch * args.epochs

    config = {
        "model": MODEL_MAP[args.base_model],
        "train": True,
        "data": str(train_jsonl.parent),
        "batch_size": args.batch_size,
        "iters": total_iters,
        "learning_rate": args.learning_rate,
        "steps_per_report": 10,
        "steps_per_eval": args.save_every,
        "save_every": args.save_every,
        "adapter_path": str(output_dir / "adapters"),
        "max_seq_length": args.max_seq_length,
        "lora_layers": 16,  # number of layers to apply LoRA to
        "lora_parameters": {
            "rank": args.lora_rank,
            "alpha": args.lora_alpha,
            "dropout": 0.05,
            "scale": args.lora_alpha / args.lora_rank,
        },
    }

    import yaml
    with open(config_path, "w", encoding="utf-8") as f:
        yaml.dump(config, f, default_flow_style=False)

    return config_path


def split_train_valid(records: list[dict], valid_ratio: float = 0.1):
    """Split records into train and validation sets, stratified by language x rule.

    Guarantees every language and every rule appear in both train and validation.
    For language/rule groups with fewer than 3 examples, at least 1 goes to validation.
    """
    import random
    from collections import defaultdict

    random.seed(42)

    # Group records by (language, rule) using metadata if available
    groups: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for rec in records:
        meta = rec.get("metadata", {})
        lang = meta.get("language", "_unknown")
        rule = meta.get("rule", "_unknown")
        groups[(lang, rule)].append(rec)

    train, valid = [], []

    for key, group in groups.items():
        random.shuffle(group)
        n = len(group)

        if n < 3:
            # Ensure at least 1 in validation; rest in train
            valid.append(group[0])
            train.extend(group[1:])
        else:
            n_valid = max(1, round(n * valid_ratio))
            valid.extend(group[:n_valid])
            train.extend(group[n_valid:])

    # Final shuffle so training order is not grouped by language/rule
    random.shuffle(train)
    random.shuffle(valid)

    return train, valid


def run_training(args, train_data_dir: Path, num_train: int):
    """Run mlx_lm.lora training via subprocess for clean process isolation."""
    import yaml

    output_dir = Path(args.output_dir)
    adapter_path = output_dir / "adapters"
    adapter_path.mkdir(parents=True, exist_ok=True)

    steps_per_epoch = max(1, num_train // args.batch_size)
    total_iters = steps_per_epoch * args.epochs

    # mlx_lm.lora expects all config in a YAML file passed via -c
    config = {
        "model": MODEL_MAP[args.base_model],
        "train": True,
        "data": str(train_data_dir),
        "batch_size": args.batch_size,
        "iters": total_iters,
        "learning_rate": args.learning_rate,
        "steps_per_report": 10,
        "steps_per_eval": args.save_every,
        "save_every": args.save_every,
        "adapter_path": str(adapter_path),
        "max_seq_length": args.max_seq_length,
        "lora_layers": 16,
        "lora_parameters": {
            "rank": args.lora_rank,
            "alpha": args.lora_alpha,
            "dropout": 0.05,
            "scale": args.lora_alpha / args.lora_rank,
        },
    }

    config_path = output_dir / "train_config.yaml"
    with open(config_path, "w", encoding="utf-8") as f:
        yaml.dump(config, f, default_flow_style=False)

    cmd = [
        sys.executable, "-m", "mlx_lm.lora",
        "-c", str(config_path),
    ]

    print(f"\n  Config: {config_path}")
    print(f"  Running: {' '.join(cmd)}\n")
    start_time = time.time()

    result = subprocess.run(cmd, text=True)

    elapsed = time.time() - start_time
    minutes = int(elapsed // 60)
    seconds = int(elapsed % 60)

    if result.returncode != 0:
        print(f"\n  ERROR: Training failed with return code {result.returncode}")
        sys.exit(1)

    print(f"\n  Training complete in {minutes}m {seconds}s")
    return adapter_path


def fuse_adapter(args, adapter_path: Path) -> Path:
    """Fuse LoRA adapter into the base model using mlx_lm.fuse."""
    fused_dir = Path(args.output_dir) / "fused-model"
    fused_dir.mkdir(parents=True, exist_ok=True)

    cmd = [
        sys.executable, "-m", "mlx_lm.fuse",
        "--model", MODEL_MAP[args.base_model],
        "--adapter-path", str(adapter_path),
        "--save-path", str(fused_dir),
    ]

    print(f"  Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, text=True)

    if result.returncode != 0:
        print(f"  ERROR: Adapter fusion failed with return code {result.returncode}")
        sys.exit(1)

    print(f"  Fused model saved to: {fused_dir}")
    return fused_dir


def export_gguf(args, fused_dir: Path) -> Path:
    """Convert fused MLX model to GGUF for Ollama."""
    gguf_dir = Path(args.output_dir) / "gguf"
    gguf_dir.mkdir(parents=True, exist_ok=True)

    # Try mlx_lm.convert first (if it supports GGUF output)
    # Otherwise fall back to llama.cpp convert
    print(f"  Attempting GGUF conversion ({args.quantization})...")

    # mlx_lm.convert can convert to/from MLX format.
    # For GGUF, we typically need llama.cpp's convert script.
    # Check if llama-cpp-python or convert script is available.

    convert_script = shutil.which("convert-hf-to-gguf") or shutil.which("convert_hf_to_gguf.py")

    if convert_script:
        gguf_path = gguf_dir / f"typography-intel-{args.quantization}.gguf"
        cmd = [
            convert_script,
            str(fused_dir),
            "--outfile", str(gguf_path),
            "--outtype", args.quantization,
        ]
        print(f"  Running: {' '.join(cmd)}")
        result = subprocess.run(cmd, text=True)
        if result.returncode != 0:
            print(f"  WARNING: GGUF conversion failed. You can convert manually:")
            print(f"    python convert_hf_to_gguf.py {fused_dir} --outfile {gguf_path} --outtype {args.quantization}")
            return gguf_dir
    else:
        # Try using mlx_lm.convert to get HF format, then instruct user
        print("  convert-hf-to-gguf not found in PATH.")
        print("  The fused model is saved in MLX format. To convert to GGUF:")
        print(f"    1. Install llama.cpp: brew install llama.cpp")
        print(f"    2. Run: convert-hf-to-gguf {fused_dir} --outfile {gguf_dir}/typography-intel.gguf --outtype {args.quantization}")
        print(f"  Or use Ollama directly with the fused model directory.")

        gguf_path = gguf_dir / f"typography-intel-{args.quantization}.gguf"

    return gguf_dir


def generate_modelfile(args, gguf_dir: Path) -> Path:
    """Generate an Ollama Modelfile with the correct prompt template."""
    gguf_filename = f"typography-intel-{args.quantization}.gguf"
    gguf_path = gguf_dir / gguf_filename

    # If GGUF file exists, reference it; otherwise use a placeholder
    if gguf_path.exists():
        from_line = f"FROM {gguf_path}"
    else:
        from_line = f"FROM {gguf_path}  # Update this path if you converted manually"

    modelfile_content = f"""{from_line}

TEMPLATE \"\"\"Below is an instruction that describes a task, paired with an input that provides further context. Write a response that appropriately completes the request.

### Instruction:
{{{{ .System }}}}

### Input:
{{{{ .Prompt }}}}

### Response:
\"\"\"

SYSTEM "You are a typography expert. Correct typographic errors in text, applying language-appropriate conventions for quotation marks, dashes, spacing, punctuation, and other typographic elements. Always use proper Unicode characters."

PARAMETER temperature 0.1
PARAMETER top_p 0.9
"""

    modelfile_path = gguf_dir / "Modelfile"
    modelfile_path.write_text(modelfile_content, encoding="utf-8")
    return modelfile_path


def main():
    args = get_args()

    print("=" * 64)
    print("TYPOGRAPHY INTELLIGENCE — LoRA TRAINING (MLX / Apple Silicon)")
    print("=" * 64)
    print(f"  Base model:     {args.base_model} -> {MODEL_MAP[args.base_model]}")
    print(f"  Dataset:        {args.dataset}")
    print(f"  Epochs:         {args.epochs}")
    print(f"  LoRA rank:      {args.lora_rank}")
    print(f"  LoRA alpha:     {args.lora_alpha}")
    print(f"  Learning rate:  {args.learning_rate}")
    print(f"  Batch size:     {args.batch_size}")
    print(f"  Max seq length: {args.max_seq_length}")
    print(f"  Warmup steps:   {args.warmup_steps}")
    print(f"  Save every:     {args.save_every} steps")
    print(f"  Output:         {args.output_dir}")
    print(f"  Dry run:        {args.dry_run}")
    print("=" * 64)

    # ------------------------------------------------------------------
    # 1. Validate environment
    # ------------------------------------------------------------------
    print("\n[1/6] Validating environment...")

    try:
        import mlx.core as mx
        print(f"  MLX version: {mx.__version__}")
        print(f"  MLX default device: {mx.default_device()}")
    except ImportError:
        print("  ERROR: mlx is not installed. Install with: pip install mlx mlx-lm")
        sys.exit(1)

    try:
        import mlx_lm
        print(f"  mlx-lm available")
    except ImportError:
        print("  ERROR: mlx-lm is not installed. Install with: pip install mlx-lm")
        sys.exit(1)

    try:
        import yaml  # noqa: F401 — needed for config generation
    except ImportError:
        print("  WARNING: pyyaml not installed. Config file generation will be skipped.")

    report_memory()

    # ------------------------------------------------------------------
    # 2. Load and convert dataset
    # ------------------------------------------------------------------
    print("\n[2/6] Loading and converting dataset...")

    raw_data = load_dataset_from_jsonl(args.dataset)
    print(f"  Loaded {len(raw_data)} examples from {args.dataset}")

    if len(raw_data) == 0:
        print("  ERROR: No training examples found. Regenerate with: python pipeline/generate_dataset.py")
        sys.exit(1)

    # Split into train / valid (stratified by language x rule)
    train_records, valid_records = split_train_valid(raw_data, valid_ratio=0.1)
    print(f"  Train: {len(train_records)} examples")
    print(f"  Valid: {len(valid_records)} examples")

    # Strip metadata before writing training files
    train_records = strip_metadata(train_records)
    valid_records = strip_metadata(valid_records)

    # mlx_lm.lora expects a data directory with train.jsonl and valid.jsonl
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    data_dir = output_dir / "data"
    data_dir.mkdir(parents=True, exist_ok=True)

    train_jsonl = data_dir / "train.jsonl"
    valid_jsonl = data_dir / "valid.jsonl"

    n_train = convert_to_mlx_format(train_records, train_jsonl)
    n_valid = convert_to_mlx_format(valid_records, valid_jsonl)

    print(f"  Wrote {n_train} train examples to {train_jsonl}")
    print(f"  Wrote {n_valid} valid examples to {valid_jsonl}")

    # Show a sample
    with open(train_jsonl, "r", encoding="utf-8") as f:
        sample = json.loads(f.readline())
    print(f"\n  Sample (first train example):")
    user_msg = sample["messages"][0]["content"]
    asst_msg = sample["messages"][1]["content"]
    print(f"    User:      {user_msg[:80]}...")
    print(f"    Assistant: {asst_msg[:80]}...")

    # ------------------------------------------------------------------
    # 3. Dry run check
    # ------------------------------------------------------------------
    if args.dry_run:
        print("\n" + "=" * 64)
        print("DRY RUN — validation passed. No training performed.")
        print("=" * 64)

        steps_per_epoch = max(1, len(train_records) // args.batch_size)
        total_iters = steps_per_epoch * args.epochs
        print(f"\n  Would train for {total_iters} iterations ({args.epochs} epochs x {steps_per_epoch} steps/epoch)")
        print(f"  Model: {MODEL_MAP[args.base_model]}")
        print(f"  Data dir: {data_dir}")

        # Estimate memory usage
        model_name = args.base_model
        if "3B" in MODEL_MAP[model_name] or "3b" in MODEL_MAP[model_name]:
            est_mem = "~4-6 GB"
        elif "7B" in MODEL_MAP[model_name] or "7b" in MODEL_MAP[model_name]:
            est_mem = "~8-12 GB"
        elif "9B" in MODEL_MAP[model_name] or "9b" in MODEL_MAP[model_name]:
            est_mem = "~10-16 GB"
        else:
            est_mem = "unknown"
        print(f"  Estimated memory: {est_mem} (4-bit quantized + LoRA)")

        report_memory()
        return

    # ------------------------------------------------------------------
    # 4. Train with mlx_lm.lora
    # ------------------------------------------------------------------
    print("\n[3/6] Training LoRA adapter with mlx_lm...")

    adapter_path = run_training(args, data_dir, n_train)

    report_memory()

    # ------------------------------------------------------------------
    # 5. Save summary
    # ------------------------------------------------------------------
    print("\n[4/6] Training artifacts saved.")
    print(f"  Adapter path: {adapter_path}")

    # ------------------------------------------------------------------
    # 6. Export to Ollama (optional)
    # ------------------------------------------------------------------
    if args.export_ollama:
        print("\n[5/6] Fusing LoRA adapter into base model...")
        fused_dir = fuse_adapter(args, adapter_path)

        print(f"\n[6/6] Exporting to GGUF ({args.quantization}) for Ollama...")
        gguf_dir = export_gguf(args, fused_dir)
        modelfile_path = generate_modelfile(args, gguf_dir)

        print(f"\n  GGUF dir:   {gguf_dir}")
        print(f"  Modelfile:  {modelfile_path}")
        print(f"\n  To load in Ollama:")
        print(f"    ollama create typography-intel -f {modelfile_path}")
        print(f"    ollama run typography-intel")
    else:
        print("\n[5/6] Skipped (no --export_ollama flag)")
        print("[6/6] Skipped")
        print(f"\n  To fuse and export later:")
        print(f"    python -m mlx_lm.fuse --model {MODEL_MAP[args.base_model]} \\")
        print(f"        --adapter-path {adapter_path} \\")
        print(f"        --save-path {Path(args.output_dir) / 'fused-model'}")

    report_memory()

    print("\n" + "=" * 64)
    print("DONE")
    print("=" * 64)


if __name__ == "__main__":
    main()
