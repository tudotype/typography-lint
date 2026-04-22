# Typography Intelligence

Language-aware typographic correction, powered by a YAML rule system and LoRA fine-tuning.

Covers 9 language variants (PT-PT, PT-BR, EN-US, EN-GB, FR-FR, DE-DE, IT-IT, ES-ES, ES-MX) with full Unicode-level traceability from semantic intent to character output.

## Structure

```
CLAUDE.md                          ← Agent instructions (Claude Code)
schema/
  typography-system-schema.yaml    ← Source of truth for all typographic rules
pipeline/
  generate_dataset.py              ← Schema → training pairs (JSONL)
  train_typography.py              ← LoRA fine-tuning (Unsloth)
  eval_typography.py               ← Ground-truth evaluation
data/
  typography_training.jsonl        ← Generated dataset (build artifact)
docs/
  thinking.md                      ← Design decisions and findings
```

## Quick start

```bash
# 1. Generate dataset from schema
python pipeline/generate_dataset.py

# 2. Train (requires GPU—see docs/thinking.md for hardware options)
pip install unsloth transformers trl datasets peft
python pipeline/train_typography.py --base_model gemma2

# 3. Export to Ollama
python pipeline/train_typography.py --export_ollama

# 4. Evaluate
python pipeline/eval_typography.py --mode ollama --model typography-intel
```

## Adding a language

1. Add a language section under `languages:` in `schema/typography-system-schema.yaml`
2. Add corresponding templates in `pipeline/generate_dataset.py`
3. Add eval cases in `pipeline/eval_typography.py`
4. Regenerate: `python pipeline/generate_dataset.py`

See `CLAUDE.md` for full conventions.

## License

TBD
