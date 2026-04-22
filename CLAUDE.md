# CLAUDE.md—Typography Intelligence

## Project identity

Typography Intelligence is a fine-tuning pipeline that trains language-aware typographic correction models. It uses a YAML-based rule system as both the source of truth for typographic conventions and the engine for generating training data.

This is João’s project. He is a brand designer at Automattic (Woo Design team) with deep expertise in Brand OS architecture, YAML schema design, and AI tooling. He communicates directly and thinks in systems. Don’t over-explain things he already knows.

## Architecture

```
schema/
  typography-system-schema.yaml    ← THE source of truth. All rules live here.

pipeline/
  generate_dataset.py              ← Schema → JSONL training pairs
  train_typography.py              ← Unsloth LoRA fine-tuning
  eval_typography.py               ← Ground-truth evaluation

data/
  typography_training.jsonl        ← Generated dataset (regenerate, don’t hand-edit)

docs/
  thinking.md                      ← Running thinking/findings log
  README.md                        ← Repo README
```

### Core design principles

1. **Primitives → Semantic Rules → Language Layers → Registers**—every typographic decision traces from semantic intent down to explicit Unicode codepoints. No magic.
2. **Inheritance, not duplication**—languages inherit from `universal`, regional variants inherit from parent language (PT-BR → PT-PT, EN-GB → EN-US, ES-MX → ES-ES).
3. **80/20 deterministic-to-AI split**—deterministic rules (quotation mark substitution, number formatting) stay in YAML. The fine-tuned model handles fuzzy, context-dependent cases (accent correction, dash choice in ambiguous contexts).
4. **The YAML is always right**—if the model disagrees with the schema, the schema wins. Training data is derived from the schema, never the reverse.

### Languages covered (13 variants)

PT-PT, PT-BR, EN-US, EN-GB, FR-FR, DE-DE, IT-IT, ES-ES, ES-MX, SC (Sardinian), NL-NL, NL-BE, RO-RO

### Rule architecture (6 batches)

The schema organises rules in implementation batches:
- **Batch 1** (IMPLEMENTED): Code exclusion, NFC normalization, zero-width character handling—the safety layer
- **Batch 2** (IMPLEMENTED): Diacritic integrity—French capital accents, German ẞ, French œ/æ, Romanian ș/ț, homoglyph detection
- **Batch 3** (IMPLEMENTED): NNBSP semantics, expanded NBSP obligations, single-letter line-ending rules
- **Batch 4** (TODO): Locale-branched punctuation—colon capitalisation, serial comma, footnote placement, abbreviation periods
- **Batch 5** (TODO): Micro-typography—ligature suppression, figure styles, small caps, tracking
- **Batch 6** (TODO): WCAG-safe emission—accessibility constraints on corrector output

## Working rules

### When editing the schema (`typography-system-schema.yaml`)

- Every rule MUST have a `description` and either `resolves_to` (pointing to a primitive) or a `rule` field explaining the convention.
- Every language-specific rule MUST include at least one `examples` entry with `raw` and `correct` fields.
- When adding a new language: inherit from the closest parent, override only what differs, add language-specific rules under `additions`.
- Spacing is declared via named patterns from `primitives.spacing_patterns`—never inline raw Unicode in rule definitions.
- When in doubt about a convention, add a `notes` field explaining the ambiguity rather than picking a side silently.
- If a rule is register-sensitive (behaves differently in editorial vs marketing vs UI), mark it `register_sensitive: true`.

### When editing the dataset generator (`generate_dataset.py`)

- Templates in `TEMPLATES` dict are grouped by rule name, then by language code.
- `_universal` is a special key for rules that apply identically across languages.
- Every template is a tuple: `(raw_text, correct_text)`. The raw text should contain the specific error the rule addresses.
- After editing templates, ALWAYS regenerate the JSONL: `python pipeline/generate_dataset.py`
- The JSONL in `data/` is a build artifact. Never hand-edit it.
- Cross-language pairs in `generate_cross_language_pairs()` use parallel sentences—same meaning, different typographic treatment. These are the highest-value training examples.

### When editing training or eval scripts

- `train_typography.py` uses Alpaca instruction format. Don’t change the prompt template without updating eval too.
- `eval_typography.py` has hardcoded ground-truth cases in `EVAL_CASES`. When adding new rules or languages to the schema, add corresponding eval cases.
- The Ollama Modelfile template in the training script must match the prompt format.

### When updating docs

- `docs/thinking.md` is a running log of design decisions, strategic thinking, and findings. Append, don’t reorganise. Date new entries.
- Keep README.md concise—it’s the quick-start, not the full story.

## Conventions

- Language codes follow BCP 47: `pt-PT`, `en-US`, `fr-FR`, etc.
- Unicode characters are referenced by primitive name in YAML, by escape sequence in Python (`\u201C`).
- File encoding is always UTF-8.
- Python follows standard conventions. No type: ignore comments without explanation.
- Commit messages: `schema: ...` for YAML changes, `pipeline: ...` for scripts, `docs: ...` for documentation, `data: ...` for regenerated datasets.

## Strategic context

This project has dual purpose:

1. **Technical**—build a working typography correction model via LoRA fine-tuning
2. **Strategic**—position Automattic as the platform that cares about typographic quality at infrastructure level, relevant to Newspack publishers and WordPress VIP enterprise clients

The YAML schema is designed to be open-sourced as a community contribution. The blog post on automattic.design will document the journey. Keep this context in mind when making architectural decisions—extensibility and auditability matter as much as correctness.

## Do NOT

- Invent typographic rules. If unsure, flag it with a `notes` field or ask.
- Hand-edit the JSONL dataset. Always regenerate from the schema.
- Change the prompt template format in one script without updating all three (generate, train, eval).
- Add languages without at least 3 example pairs per rule that applies to that language.
- Use straight quotes in any output or documentation. Practice what we preach.
