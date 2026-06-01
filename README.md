# Typeproof

Language-aware typographic correction, powered by a YAML rule system and LoRA fine-tuning.

Typeproof fixes the typography that fonts can’t reach — straight quotes, wrong dashes, missing diacritics, broken spacing — at the **codepoint** level, with rules that change by language. It covers **13 language variants** across a three-layer pipeline, with full traceability from semantic intent to character output.

> **Status:** the deterministic core (Layer 1) is usable today. The fine-tuned model (Layer 2) is research-stage — see [`thinking.md`](thinking.md). Per-locale rules carry a maturity status (see [Language coverage](#language-coverage)); breadth without verification is marked as such on purpose.

## How it works — three layers

```
Raw text → [Layer 1: deterministic YAML rules] → [Layer 2: fine-tuned model] → [Layer 3: font gate] → safe output
```

1. **Layer 1 — deterministic linter** (`typeproof.py`): 34 rules covering quotes, dashes, spacing, diacritics, symbols, fractions, NBSP. Pure Python, no ML. Handles the deterministic ~80%. Includes a code-exclusion masker so URLs, code fences, and paths are never touched.
2. **Layer 2 — fine-tuned model** (`correct.py`): handles the genuinely fuzzy cases the rules can’t (ambiguous dash choice, context-dependent accents). Research-stage.
3. **Layer 3 — font gate** (`font_gate.py`): guarantees the output is renderable in the target font. A visible imperfect glyph beats a missing one — it never emits tofu.

The **YAML schema is the source of truth.** Rules are authored once in [`typography-system-schema.yaml`](typography-system-schema.yaml) and generate both the training data and the eval ground truth.

## Repository layout

Everything lives at the repository root (no `src/`/`pipeline/` nesting):

```
typography-system-schema.yaml   ← source of truth for all typographic rules
typeproof.py                    ← Layer 1: deterministic linter (library + CLI)
correct.py                      ← full pipeline CLI (lint → model → font gate)
font_gate.py                    ← Layer 3: font-awareness gate
generate_dataset.py             ← schema → training pairs (typography_training.jsonl)
train_typography.py             ← LoRA fine-tuning (MLX / Apple Silicon)
eval_typography.py              ← ground-truth evaluation (83 cases)
test_typeproof.py               ← linter unit tests
test_schema_parity.py           ← schema ↔ linter parity tests
conftest.py                     ← ledger of not-yet-implemented behaviour (xfail)
docs/                           ← live demo (index.html), adoption-roadmap.md, thinking.md
wp-plugin/                      ← Gutenberg plugin (EXPERIMENTAL — requires server-side Python; see below)
```

## Pick your path

Typeproof serves different people differently.

### I just want to see it work
Open the live demo: **[docs/index.html](docs/index.html)** (or the deployed GitHub Pages site). Paste text, watch the green diff.

### I’m a developer — lint typography in my code or CI
```bash
pip install -r requirements.txt          # the core needs only pyyaml; fonttools is optional

# Lint a string (deterministic core, no ML needed):
echo 'She said "hello"...' | python3 typeproof.py --lang en-US
#   → She said “hello”…

# Machine-readable output (the integration contract — corrected text + per-correction diff):
python3 typeproof.py --file article.md --lang fr-FR --json

# As a library:
python3 - <<'PY'
from typeproof import TypographyLinter
result = TypographyLinter(language="de-DE").lint('Er sagte "danke".')
print(result.text)            # → Er sagte „danke“.
print(result.to_dict())       # full diff: every correction with position + rule
PY
```
Supported `--lang` values: `pt-PT pt-BR en-US en-GB fr-FR de-DE it-IT es-ES es-MX nl-NL nl-BE ro-RO sc`.

**Strict / never-corrupt mode** — for automated or enterprise use, pass `--strict` (or `TypographyLinter(language=…, strict=True)`). It skips inference-based rules (dash/range/multiplication inference, ordinals, heuristic NBSP) and applies only unambiguous substitutions — when a change isn’t provably safe, it does nothing. Safety is enforced by tests in [`test_safety.py`](test_safety.py): idempotency (run-twice = run-once) across all locales, and a fuzzed code-exclusion masker that guarantees URLs, code, paths, and HTML tags are never altered.

### I’m a native speaker — a rule is wrong for my language
You do **not** need to write Python or YAML. Open an issue with a failing example — the text as it is, and the text as it should be — and a maintainer turns it into a rule and a test. See [CONTRIBUTING.md](CONTRIBUTING.md).

### I run WordPress
The [`wp-plugin/`](wp-plugin/) is a working Gutenberg integration **but is experimental**: it shells out to `typeproof.py` and therefore needs Python 3.8+ on the web server, which most hosting does not allow. A no-Python (PHP/JS) core is on the roadmap — see [docs/adoption-roadmap.md](docs/adoption-roadmap.md) §3.

### I want the full pipeline (with the model)
```bash
# Requires a fused model in typography-lora/ (see Training below)
python3 correct.py "some text with bad typography" --lang pt-PT --diff
```

## Training (optional, advanced)

Training targets **Apple Silicon via MLX** (not Unsloth). Most users never need this — the deterministic core runs without it.

```bash
python3 generate_dataset.py                         # schema → typography_training.jsonl (~3.9k pairs)
python3 train_typography.py --base_model mistral    # LoRA fine-tune (mistral | llama3.2 | gemma2)
python3 train_typography.py --export_ollama         # export to Ollama
python3 eval_typography.py                           # evaluate against the 83 ground-truth cases
```

See [`thinking.md`](thinking.md) for the model-iteration history — what the model learned, and what it couldn’t.

## Language coverage

13 variants. Each carries a maturity status — breadth is only a strength if it is honest about verification (the rules for an unverified locale may be subtly wrong).

| Status | Locales |
|---|---|
| Native-verified | `pt-PT`, `pt-BR` (author-native), `it-IT` |
| Cross-checked against style authorities (not yet native-verified) | `es-ES`, `es-MX`, `de-DE`, `fr-FR` |
| LLM-sourced, pending review | `en-US`, `en-GB`, `nl-NL`, `nl-BE`, `ro-RO`, `sc` |

If a locale above is yours, [we’d love your eyes on it](CONTRIBUTING.md).

## Status of the rule set

34 deterministic rules are implemented and tested (Batches 1–3: code exclusion, NFC, zero-width handling, diacritic integrity, NBSP semantics, single-letter line-ending). Further batches (locale-branched punctuation, micro-typography, accessibility emission) are specified in the schema but not yet implemented; their tests are marked `xfail` in [`conftest.py`](conftest.py) so the suite reports the truth. See [docs/adoption-roadmap.md](docs/adoption-roadmap.md).

## Adding a language

1. Add a section under `languages:` in [`typography-system-schema.yaml`](typography-system-schema.yaml) — inherit from the closest parent, override only what differs.
2. Add templates in [`generate_dataset.py`](generate_dataset.py) (≥ 3 example pairs per applicable rule).
3. Add eval cases in [`eval_typography.py`](eval_typography.py).
4. Regenerate: `python3 generate_dataset.py`.

See [`CLAUDE.md`](CLAUDE.md) for full conventions.

## Roadmap

See [docs/adoption-roadmap.md](docs/adoption-roadmap.md) for the sequenced plan, organized by adoption role.

## Prior art & acknowledgements

Typeproof stands on the shoulders of a long line of typography tooling. If you
want battle-tested correction in PHP **today**, reach for these first — they are
excellent, and Typeproof is not trying to replace them:

- **[JoliTypo](https://github.com/jolicode/JoliTypo)** — a PHP microtypography
  fixer. DOM-based (parses with `\DOMDocument` rather than regex), composes
  small named “fixers” into a pipeline, and maps locales to rule presets. A
  clean reference for safe, composable, HTML-aware correction.
- **[php-typography](https://github.com/mundschenk-at/php-typography)** and its
  WordPress plugin **[wp-Typography](https://github.com/Melindrea/wp-typography)** —
  a mature PHP library (50+ languages, hyphenation, widow protection) that ships
  to ordinary WordPress hosting with no server-side runtime. Proof that a
  typography corrector can be a plain plugin.
- **[PHP SmartyPants](https://github.com/michelf/php-smartypants)** — the
  canonical minimal smart-quotes/dashes prettifier, derived from John Gruber’s
  original [SmartyPants](https://daringfireball.net/projects/smartypants/).
- **[`wptexturize()`](https://developer.wordpress.org/reference/functions/wptexturize/)** —
  WordPress core’s built-in baseline; the floor Typeproof aims to raise.

**Where Typeproof differs.** Its bet is a **YAML schema as the single source of
truth** that generates the implementation, the training data, *and* the eval;
explicit **per-locale maturity**; broad **multilingual codepoint** coverage; and
a **fine-tuned model** for the genuinely fuzzy cases rules can’t reach. For pure
deterministic smart-quote/dash correction in one runtime today, the projects
above may serve you better — that honesty is the point.

_This list is a starting point, not a survey. Typographic conventions live in
national orthography bodies and style guides (CMOS, Duden, the Acordo
Ortográfico, etc.); contributions that trace a rule back to such an authority are
the most valuable — see [CONTRIBUTING.md](CONTRIBUTING.md)._

## License

TBD.
