# Typography Intelligence: Thinking & Findings

## Origin

Exploration started from a simple question: if I wanted to fine-tune an LLM, where would I start? The answer led to an unexpected intersection—my existing Brand OS architecture (YAML-as-source-of-truth, 80/20 deterministic-to-AI split) is already a form of model tuning. The natural next step was finding a use case where actual fine-tuning adds value that structured prompting can’t.

Typography turned out to be that use case.

## The Insight

I’ve been developing a global typography YAML covering principles from Butterick’s Practical Typography and ortotipografia conventions. The key realisation: typographic correctness is **culturally embedded, language-sensitive, and pattern-based**—exactly the kind of knowledge that’s hard to express fully in a system prompt but learnable from structured examples.

A fine-tuned model could internalise rules like:
- The difference between a hyphen, en dash, and em dash *in context*
- That Portuguese uses « » with thin inner spaces, French uses « » with narrow no-break spaces, and Italian uses « » with no spaces—same glyphs, different rules
- That `perche'` is keyboard laziness for `perché` (acute, not grave)
- That German closes quotes with „ “ where the opening left double quote serves as the closer

These aren’t lookup problems. They’re pattern recognition problems that benefit from model-level learning.

## Architecture: Primitives → Semantic Rules → Language Layers → Registers

### Design philosophy
- **Semantic intent at the working level**—rules describe *what* typographic function is being served (dialogue attribution, parenthetical aside, numeric range)
- **Full traceability to primitives**—every semantic rule resolves to explicit Unicode codepoints with named references
- **Inheritance, not duplication**—language layers inherit from universal, regional variants inherit from parent language (PT-BR inherits from PT-PT, EN-GB from EN-US)
- **Register sensitivity**—editorial, marketing, UI, and literary contexts can override defaults within a language
- **No magic, everything auditable**—mirrors Brand OS principles

### Schema structure (implemented in YAML)

1. **Primitives**—Unicode characters (quotation marks, dashes, spaces, primes, ordinal indicators) and spacing patterns (space_before, nbsp_both, thin_both, etc.)
2. **Semantic rules (universal)**—rules that hold across all Latin-script languages: typographic quotes over straight quotes, proper apostrophes, ellipsis character, prime marks for measurements, single sentence spacing, multiplication sign for dimensions
3. **Language layers**—each inherits from universal, overrides where needed, adds language-specific rules
4. **Registers**—context-dependent overrides (editorial, marketing, UI, literary) that apply within any language
5. **Resolution logic**—declarative algorithm: register → language → universal → primitive → spacing → output
6. **Training pair generation spec**—how to derive fine-tuning examples (correction, detection, cross-language, explanation pairs)

### Languages covered

| Language | Inherits from | Key distinguishing features |
|----------|--------------|---------------------------|
| PT-PT | universal | « » with thin inner spaces, travessão for dialogue, ordinals with period (1.º, 2.ª) |
| PT-BR | PT-PT | " " as primary quotes, inherits travessão convention |
| EN-US | universal | " " quotes, em dash no spaces, serial comma (register-dependent), punctuation inside quotes |
| EN-GB | EN-US | ' ' as primary quotes, en dash with spaces, punctuation outside quotes |
| FR-FR | universal | « » with narrow no-break inner spaces, NNBSP before high punctuation (: ; ! ?), tiret for dialogue |
| DE-DE | universal | „ " quotes (low-9 open, left double as close), ‹ › nested, en dash with spaces |
| IT-IT | universal | « » no inner spaces (key divergence from PT/FR), lineetta for dialogue, è/é accent distinction, d-euphonic rules, troncamento/abbreviazione system, alternate " " style for modern editorial |

### Inheritance model validation

PT-BR inheriting from PT-PT (not from universal) proved the model works—shared travessão convention propagates, only quotation preference needs overriding. German’s quotation system (opening quote reused as closer) stress-tests the primitives layer. Italian’s « » with no inner spacing validates that the same glyphs need different semantic rules per language.

## Fine-tuning approach

### Why fine-tune (vs. prompt-only)

The 80/20 split applies here too:
- **Deterministic (YAML-driven):** quotation mark substitution, number formatting, known abbreviation patterns—these are lookup/replacement operations
- **AI-mediated (fine-tuned model):** context-dependent dash choices, accent correction from keyboard shortcuts, detecting errors in mixed-language passages, handling edge cases like nested quotes 3+ levels deep

The model needs to *internalise a style of reasoning* about typography, not just follow a rule list.

### Technical path

- **Base model:** Mistral 7B or Llama 3.2 via Ollama (already exploring locally)
- **Method:** LoRA/QLoRA—adapter-only training, ~10–50 MB added to base model regardless of language count
- **Dataset size:** 300–500 training pairs per language × 7 languages = ~2,100–3,500 pairs. Well within LoRA sweet spot (1,000–10,000 examples)
- **Training pair types:** correction (raw → fixed), detection (find errors), cross-language (same text, different typographic treatment), explanation (which rule and why)
- **Tooling:** Unsloth for efficient LoRA training, Hugging Face ecosystem
- **Evaluation:** mirrors Brand OS test system as permanent institutional memory—define correct brand outputs, measure improvement over base model

### Scaling—how many languages?

The model doesn’t get heavier with more languages. LoRA adapter size scales with rank, not dataset volume. Could train on 50 languages with the same adapter size.

The real constraint is **quality, not quantity**—each language needs verified conventions from authoritative sources.

**Tier system:**
- **Tier 1 (launch):** Languages I can personally validate—PT, EN, IT, FR, ES. ~5 languages.
- **Tier 2 (expansion):** Major European with documented conventions—DE (already done), NL, PL, SV. Need a reviewer per language.
- **Tier 3 (future):** Non-Latin systems—CJK, Arabic, Hebrew, Devanagari. Each is a sub-project with fundamentally different rule categories (text direction, character composition, line-breaking).

**Recommendation:** Ship with 8–12 Latin-script languages. Proves the architecture, keeps rules verifiable, model is no heavier than 3 languages.

## Application contexts

### AI post-processing layer
Every LLM produces typographically sloppy output. This model sits as the last agent in any content generation chain—inside Brand OS or any other pipeline. Clean everything before it reaches the user.

### CMS and editor integration (WordPress / Gutenberg)
WordPress handles billions of words. Gutenberg already does basic smart quote replacement, but it’s English-centric and shallow. A typography-aware system respecting the post’s language setting and applying the full rule set would be a genuine differentiator. Spell-check’s sophisticated cousin: **type-check**.

### Translation and localisation
Highest-value application. Translation tools routinely get typography wrong across language boundaries—they translate words but carry source-language typographic conventions. A post-translation typography pass is genuinely hard to find in existing tooling.

### Design-to-production pipelines
Figma to Gutenberg, design comp to published output. Typography errors introduced during content handoff are constant. A validation layer catches “the designer used the right dash but the CMS ate it.”

### Email and messaging composition
Keyboard laziness fixes in real time—`perche'` → `perché`, straight quotes → curly quotes. Needs the model to be small and fast enough for real-time input.

### Publishing and editorial workflows
Book production, journalism, documentation. ProWritingAid and Grammarly barely touch typographic correctness, and when they do, it’s English-only.

### Accessibility
Screen readers interpret proper Unicode characters differently from ASCII approximations. En dash reads differently from hyphen. Proper ellipsis announced correctly. Typographic correctness = accessibility improvement.

## Strategic positioning for Automattic

### The opportunity

This positions Automattic as the platform that **cares about typographic quality at the infrastructure level**. Not cosmetic—structural. The kind of quality signal that publishers, brands, and enterprise clients recognise as a trust marker.

### Newspack and VIP angle

- **Newspack publishers** need credibility in every detail. Typographic correctness is a quality signal readers perceive even when they can’t name it. A newspaper with consistent em dashes and proper quotation marks reads as more authoritative than one with straight quotes and hyphens.
- **WordPress VIP enterprise clients** operate in regulated, high-stakes content environments. Typographic consistency across multilingual content is a real pain point at scale. This solves it at the platform level rather than relying on editorial style guides that nobody follows consistently.
- **Brand partners** get a quality differentiator they can point to—“our CMS handles typography correctly across 12 languages” is a statement competitors can’t match.

### Open-source the schema, productise the tooling

The YAML schema is the community contribution—freely available, auditable, extensible. Anyone can add languages, propose rule corrections, adapt for their editorial conventions. The WordPress plugin / Gutenberg extension is the product layer. Open-source rules, integrated tooling, powered by a fine-tuned model for the fuzzy cases.

This is the Brand OS philosophy applied to typography: ground layer that other projects plug into, not a top-down mandate.

### Blog post opportunity (automattic.design)

A post documenting this thinking—from the architecture to the multilingual challenges to the strategic positioning—serves multiple purposes:
- Establishes thought leadership on typography in digital publishing
- Signals to Newspack/VIP partners that Automattic invests in content quality infrastructure
- Invites community contribution to the YAML schema
- Positions the design team as technically ambitious, not just aesthetic

## Open questions

- How to handle mixed-language passages (Portuguese text quoting English source)?
- Should the Gutenberg integration be a plugin or core proposal?
- What’s the right interface for the “Typography Quality” panel in the editor?
- Is there a path to contributing the YAML schema to an existing standards body or typography community?
- Sardinian orthographic conventions: separate layer or regional notes under IT-IT?
- How does this relate to existing WordPress i18n/l10n infrastructure?
- Dutch (NL-NL) as next language to add?

## Blog post—origin story and structure

### The trigger

Pablo Honey posted on P2 about the em dash—how it should be used, what the conventions are, whether Automattic’s communications should standardise on one approach. That post sparked a cross-company conversation. People from different teams, different countries, different editorial traditions weighed in. It turns out everyone had an opinion about a single character.

That thread is the origin story. It revealed something important: typography isn’t a cosmetic concern—it’s a signal of care. And the people at Automattic care enough to argue about dashes.

### The narrative arc for the post

1. **The spark**—a P2 conversation about the em dash. Reference the thread. Show that this started as a real debate among real people, not a top-down initiative.

2. **The rabbit hole**—following that conversation, realising the em dash question can’t be answered in isolation. American English uses em dashes without spaces. British English uses en dashes with spaces. Portuguese uses travessão for dialogue. Spanish uses raya with asymmetric spacing. French uses tiret with non-breaking spaces. The same character, used differently in every language WordPress serves.

3. **The absence**—there’s no good system for this. Gutenberg does basic smart quote replacement, English-centric. Grammarly and ProWritingAid barely touch typographic correctness. Translation tools carry source-language conventions into target languages. Publishers are on their own.

4. **The build**—we built a typographic rule system. YAML schema covering 9 language variants, from Unicode primitives up through semantic rules. Inheritance model so Portuguese and Brazilian Portuguese share what they share and differ where they differ. Registers for editorial, marketing, UI, literary contexts. Open, auditable, extensible.

5. **The AI layer**—on top of the deterministic rules, we fine-tuned a model to handle the fuzzy cases: accent correction from keyboard shortcuts (`perche'` → `perché`), context-dependent dash choices, mixed-language passages. The 80/20 split: most corrections are pure rule application, the model handles what rules can’t express.

6. **The offer**—this is infrastructure for everyone who publishes on WordPress. Newspack publishers get typographic credibility their readers perceive even when they can’t name it. VIP enterprise clients get multilingual consistency at scale. The YAML schema is open-source—anyone can contribute languages, propose corrections, adapt for their editorial conventions.

7. **The philosophy**—this is what it looks like when a design team follows a conversation about a dash all the way to building infrastructure. It’s an almost invisible layer, and that’s the point. The care shows in what people don’t notice—text that just *feels* right.

### Tone

Direct, technical enough to be credible, not so technical it alienates non-designers. Show the actual Unicode characters, the actual YAML, the actual before/after examples. Let the craft speak.

### Key line

Something like: “It started with a conversation about a dash. It ended with infrastructure for typographic quality across 9 languages. This is the kind of invisible work that separates a platform that publishes text from a platform that cares about text.”

## Resolved questions

- Spanish (ES-ES, ES-MX) added—completes the Romance cluster
- Model size concern: LoRA adapter stays ~10–50 MB regardless of language count. 8–12 languages recommended for launch, purely a quality/verification constraint.
- Adoption path: deterministic YAML-based library for 80% of rules (no model needed), fine-tuned model API for fuzzy 20%, Gutenberg plugin wrapping both.

## Files

- `schema/typography-system-schema.yaml`—full schema with 13 language variants, 4 registers, resolution logic, and training pair generation spec
- `pipeline/generate_dataset.py`—dataset generator (864 pairs across 4 types)
- `pipeline/train_typography.py`—Unsloth LoRA training script with Ollama export
- `pipeline/eval_typography.py`—evaluation with 20 ground-truth test cases
- `data/typography_training.jsonl`—pre-generated training dataset
- `CLAUDE.md`—Claude Code agent instructions

---

## Session log—2025–04-18

### What was built in this session

1. **Typography system schema** (YAML) covering 13 language variants: PT-PT, PT-BR, EN-US, EN-GB, FR-FR, DE-DE, IT-IT, ES-ES, ES-MX, SC (Sardinian), NL-NL, NL-BE, RO-RO. Architecture: primitives → semantic rules → language layers → registers → resolution logic.

2. **Dataset generation pipeline** producing 864 training pairs across 4 types (correction, detection, cross-language, explanation) from templates embedded in the Python generator.

3. **Training script** (Unsloth LoRA) with Ollama GGUF export, supporting Llama 3.2 3B, Mistral 7B, Gemma 2 9B, Phi-4 14B base models.

4. **Evaluation script** with 20 ground-truth test cases across all covered languages and rule categories.

5. **CLAUDE.md** for Claude Code agent instructions.

6. **Repo structure** ready for `git init`: schema/, pipeline/, data/, docs/, with .gitignore and requirements.txt.

### Key design decisions made

- **Inheritance model**: PT-BR → PT-PT, EN-GB → EN-US, ES-MX → ES-ES, NL-BE → NL-NL, SC → IT-IT. Regional variants inherit and override.
- **80/20 split**: deterministic rules (quotation marks, number formatting) stay in YAML for a lightweight lint library; fine-tuned model handles fuzzy cases (accent correction, context-dependent dashes, mixed-language).
- **Semantic over character-level**: rules express intent (dialogue attribution, parenthetical aside, numeric range), primitives express the Unicode atoms.
- **Registers**: editorial, marketing, UI, literary—context-dependent overrides within any language.

### Universal rules added during session

- Quotation marks, apostrophes, dashes (hyphen/en/em), ellipsis, prime marks, dimensions/multiplication, sentence spacing, number-unit spacing, percent spacing, degree symbol, minus sign, legal symbols (©®™), fractions.

### Language-specific rules added

- PT: travessão, ordinals with period, number formatting
- EN: parenthetical dash divergence (US em no space / GB en with space), serial comma, punctuation placement inside/outside quotes
- FR: NNBSP before high punctuation, tiret dialogue
- DE: „ " quotation system, ‹ › nested, en dash with spaces
- IT: « » no inner space, è/é accent distinction, d-euphonic, troncamento/abbreviazione, alternate " " style
- ES: ¿¡ inverted punctuation (clause-start not sentence-start), raya asymmetric spacing, RAE 2010 ordinals, tilde diacrítica
- SC: elision apostrophe rules, Campidanese/Logudorese dialect notes
- NL: IJ digraph capitalisation, abbreviation spacing (a.u.b. vs J. P. Coen), NL-BE currency position divergence
- RO: comma-below vs cedilla (highest-priority correction), „ " quotation with « » nested, â/î distribution, linie de dialog

### Blog post origin story captured

Pablo Honey’s P2 post about the em dash → cross-company conversation → realisation that every language handles it differently → building infrastructure. Seven-section narrative arc documented.

### Research findings (2025–04-18)

Thorough research identified ~60 discrete rule families across 7 categories that the system was missing or underspecifying. The research report is saved as context in the conversation. Key findings organised by implementation priority:

**Batch 1—Code-exclusion + normalization (SAFETY LAYER)**
- Code-context detection: suppress all corrections inside `<code>`, `<pre>`, `<kbd>`, fenced code blocks, inline backticks, file paths, URLs, email addresses, @mentions, #hashtags, regex patterns, CamelCase/snake_case identifiers, version strings
- NFC normalization for storage; never NFKC (destroys ﬁ→fi, Ĳ→IJ, collapses U+202F→U+0020)
- Zero-width character handling: preserve ZWNJ (ligature suppression), ZWJ (emoji composition), WORD JOINER (U+2060); strip stray ZWSP (U+200B) and mid-text BOM (U+FEFF)

**Batch 2—Highest-signal diacritic corrections**
- Romanian ș/ț comma-below migration (aggressive, no valid use of cedilla in RO)
- French accents on capitals mandatory (ÉTAT not ETAT, À PARIS not A PARIS)
- German ẞ (capital ß, U+1E9E)—valid since 2017, preferred since 2024
- Italian acute/grave precision (already partially covered, needs expansion)
- Portuguese AO1990 corrections (trema removal, silent c/p drop)
- Homoglyph confusable detection (° vs º vs ⁰, ß vs β, · vs • vs . etc.)

**Batch 3—NNBSP semantics + expanded NBSP obligations**
- French NNBSP (U+202F) is canonical for espace fine insécable, not NBSP
- German DIN 5008 abbreviations with NNBSP (z. B., u. a., d. h., i. d. R.)
- NBSP between initials (J. R. R. Tolkien), after titles (Mr./Dr./Mme), before §/№/#/p., in dates, currency amounts per locale
- Single-letter line-ending prohibition: hard rule for PL/CS/SK only; stylistic recommendation for FR/IT/PT/ES

**Batch 4—Locale-branched punctuation (FUTURE)**
- Colon capitalisation rules per language (EN-US capitalises, FR never, DE conditionally)
- Serial/Oxford comma: prohibited in ES/DE/FR/IT/PT/NL/RO
- Comma/period placement relative to closing quote: US inside (typesetters), all others logical
- Abbreviation periods: UK contractions drop period (Mr, Dr, St), US keeps all
- Abbreviation haplology: never double period at sentence end (etc. not etc..)
- Footnote mark placement: EN/DE after punctuation, FR/ES before punctuation with NNBSP
- Nested parentheticals: inner layer → square brackets

**Batch 5—Micro-typography (FUTURE)**
- Ligature suppression at morpheme boundaries via ZWNJ (German compounds: Auf|lage, Schiff|fahrt)
- French œ/æ as orthographic letters (cœur, sœur, ex æquo—never decompose)
- Small caps for 3+ letter acronyms, era markers, Roman-numeral centuries
- Figure styles: oldstyle proportional for prose, lining tabular for tables
- Letter-spacing: 5–12% tracking for all-caps/small-caps runs
- Hanging punctuation / optical margin alignment

**Batch 6—WCAG-safe emission (FUTURE)**
- SC 1.4.12 text spacing compliance
- No fixed-width containers or !important on typographic properties
- Preserved bidi isolates (U+2066 LRI, U+2067 RLI, U+2068 FSI, U+2069 PDI)
- Breakable containers—no unbreakable NBSP chains that prevent reflow

### Implementation status

Starting implementation of Batches 1–3 now. Batches 4–6 deferred to Claude Code sessions.

---

## Session log—2026-04-21

### What was built in this session

1. **Batch 4 (locale-branched punctuation) added to schema**—7 universal rules: colon capitalisation, serial comma, quote-punctuation placement, abbreviation periods, abbreviation haplology, footnote mark placement, nested parentheticals. Language-specific overrides for all 9 base languages. Schema grew from ~1,650 to ~2,180 lines.

2. **Batches 5–6 added to schema**—Batch 5 (micro-typography): ligature suppression, orthographic ligature preservation, small caps, figure styles, tracking, hanging punctuation. Batch 6 (WCAG-safe emission): text spacing compliance, bidi isolate preservation, breakable containers, language tagging, screen reader considerations. New type fields: `rendering_hint` and `output_requirement` to distinguish from character-level rules.

3. **Training data massively expanded**—from 864 to 3,292 pairs. Backfilled Batches 1–3 gaps, added all Batch 4–6 templates. 51 unique rules, 13 languages, 4 pair types (correction, detection, cross_language, explanation).

4. **Eval cases expanded**—from 19 to 83 ground-truth cases covering all 6 batches.

5. **Training script rewritten for MLX**—Apple Silicon native (M2 Max). Replaced Unsloth/CUDA with mlx-lm for LoRA fine-tuning. Supports Llama 3.2 3B, Mistral 7B, Gemma 2 9B (all 4-bit quantised). Export pipeline: LoRA → fuse → GGUF → Ollama.

6. **Interactive review tools built**—Two HTML review pages for the project owner (a designer) to audit the schema and training data visually. Each rule card shows the convention claim prominently, before/after examples with actual Unicode characters, invisible character visualisation, and review buttons with JSON export.

7. **Font-awareness fallback system added to schema**—New top-level section with 57 fallback chains, 4 risk tiers, font capability detection methods, and decision logic. Every rule that introduces a tier 3+ character now has `font_risk` and `fallback_note` fields. Key insight from reviewer: "the text looking worse than previously (tofu) is never acceptable."

8. **Schema accuracy review completed**—All 152 rules reviewed by project owner. 143 correct, 9 uncertain, 0 wrong. Uncertain rules addressed with notes and register-sensitivity flags. ES-ES quotation split into register-dependent behaviour (RAE angle quotes for editorial, curly doubles for marketing/UI).

9. **JSONL dataset validated**—Custom validation script confirms all 3,292 records are properly formatted Alpaca instruction pairs. 6 minor duplicates found. 173 unique instruction templates. All correction pairs have teaching signal.

### Key architectural decisions

- **MLX over cloud GPU**—M2 Max with 32 GB unified memory handles Llama 3.2 3B comfortably. Fast local iteration beats cloud upload/download cycles for a 3,292-pair dataset.

- **Font-awareness as post-processing, not in-model**—Follows the project's 80/20 principle. Font fallback is deterministic lookup (check cmap → walk fallback chain). Keeping it outside the model means zero token overhead at inference, no retraining when fonts change, and the model stays focused on fuzzy typographic correction. The schema's fallback_chains serve as the lookup table.

- **Sequence length optimisation**—Checking token distribution to use the shortest max_seq_length that covers the data, reducing memory and training time.

- **Stratified train/val split**—Split by language AND rule to ensure every language and rule family appears in both sets. Critical for evaluating low-resource languages like Sardinian.

- **Review-driven development**—Built HTML review tools so the designer/project owner can audit rules and training pairs visually. Feedback loop: review page → JSON export → apply corrections. This keeps the project owner in control despite not working in YAML/Python directly.

### Open decisions

- Baseline eval against raw Llama 3.2 3B still needed (pre-fine-tuning benchmark)
- Blog post for automattic.design not yet started (narrative arc documented in previous session)
- Consider adding real-world text examples to training data (current pairs are all template-generated)
- Mixed-language detection (per-segment language identification for multilingual texts)

### Additional builds (late session)

10. **Layer 1 deterministic lint library** (`typography_lint.py`)—pure-Python, no ML dependencies. Implements 11 universal substitution rules (quotes, dashes, ellipsis, primes, fractions, legal symbols, spacing) plus language-specific rules for all 13 variants (French NNBSP, Romanian comma-below, German ẞ, abbreviation conventions). Code exclusion layer masks code blocks, URLs, file paths, @mentions, CamelCase, etc. before any corrections run. CLI interface with `--diff` and `--json` output.

11. **Font-awareness gate module** (`font_gate.py`)—Layer 3 of the pipeline. Reads font cmap tables via fonttools, walks fallback chains, reports font typography readiness scores. Works standalone without the schema file (all 57 fallback chains embedded). Conservative mode when no font is specified (assume only tier 1+2 characters are safe).

12. **Explainability in correction output**—`correct.py` now has `--explain` flag. Each change is annotated with the rule name and human-readable reason. Rule matching maps character substitutions to schema rules with language-aware filtering. JSON output includes rule attribution per change. Summary stats at the end.

13. **Eval script upgraded** (`eval_typography.py`)—now supports `--baseline` (raw model), `--lint-only` (Layer 1 only), `--compare` (delta between two saved results), and `--output` (save to JSON). Scoring: exact match, character-level similarity, regression detection. Report by language, rule family, and batch.

14. **User-friendly correction CLI** (`correct.py`)—wraps the Alpaca prompt template internally so users type `python3 correct.py "text" --lang pt-PT` instead of pasting prompt templates. Supports `--diff`, `--json`, `--explain`, `--verbose`, `--font`, `--file`, and stdin piping.

15. **Model trained successfully**—Llama 3.2 3B LoRA fine-tuning completed on M2 Max via MLX. 3 epochs, 2,235 iterations, ~10 minutes. Fused model at `typography-lora/fused-model`. GGUF export pending (needs `brew install llama.cpp`).

### Three-layer pipeline architecture (finalised)

```
Layer 1: typography_lint.py     (deterministic, fast, 80% of corrections)
Layer 2: correct.py + model     (fine-tuned LLM, fuzzy 20%)
Layer 3: font_gate.py           (font-awareness, ensures output is renderable)
```

Font-awareness stays outside the model by design—follows the 80/20 principle. Font fallback is deterministic lookup, not a learned behaviour. Zero token overhead at inference, no retraining when fonts change.

### File inventory (end of session)

| File | Purpose | Lines |
|------|---------|-------|
| `typography-system-schema.yaml` | Source of truth: all rules, 6 batches, 13 languages, font awareness | ~2,700 |
| `generate_dataset.py` | Schema → JSONL training pairs | ~1,100 |
| `typography_training.jsonl` | 3,292 training pairs (build artifact) | 3,292 |
| `train_typography.py` | MLX LoRA fine-tuning + Ollama export | ~600 |
| `eval_typography.py` | 83 ground-truth eval cases + scoring | ~500 |
| `typography_lint.py` | Layer 1: deterministic lint library | ~800 |
| `correct.py` | User-facing CLI with explainability | ~350 |
| `font_gate.py` | Layer 3: font-awareness gate | ~500 |
| `validate_dataset.py` | JSONL structural validation | ~200 |
| `check_seq_lengths.py` | Token distribution analysis | ~80 |
| `build_review.py` | Schema → interactive HTML review page | ~1,100 |
| `build_pair_review.py` | JSONL → visual pair review page | ~500 |
| `schema-review.html` | Interactive schema review (generated) | — |
| `training-pair-review.html` | Visual pair spot-check (generated) | — |
| `typography-review-feedback.json` | Reviewer feedback (exported from HTML) | — |
| `thinking.md` | This file | — |
| `CLAUDE.md` | Agent instructions | — |
| `requirements.txt` | Python dependencies | — |

### Token consumption and cost estimate

**Session 1 (2025-04-18)—original build:**
Based on the scope of work (schema design, dataset generator, training script, eval script, thinking log, CLAUDE.md), and typical Claude conversation patterns for this kind of iterative design session:
- Estimated input tokens: ~80,000–100,000 (long YAML iterations, schema reviews, research)
- Estimated output tokens: ~60,000–80,000 (full schema, all Python scripts, thinking log)
- **Estimated total: ~150,000–180,000 tokens**
- Estimated cost (Claude Opus at $15/$75 per M input/output tokens): **~$6–9**

**Session 2 (2026-04-21)—Cowork session (this session):**
Main conversation plus 15+ parallel subagents, each with full file reads and writes:
- Main conversation input: ~120,000 tokens (schema reads, file reads, long context)
- Main conversation output: ~30,000 tokens
- Subagent tokens (15 agents, avg ~50,000 total tokens each): ~750,000 tokens
- **Estimated total: ~900,000–1,000,000 tokens**
- Estimated cost (Claude Opus at $15/$75 per M input/output tokens): **~$40–55**

**Combined project total: ~1,100,000–1,180,000 tokens, estimated cost ~$46–64**

Note: These are rough estimates. Actual token counts depend on context window management, caching, and the specific model tier used. The subagent architecture in Cowork means each agent starts with a fresh context including full file reads, which multiplies the token count compared to a single linear conversation. The tradeoff is wall-clock speed—parallel agents completed work in minutes that would have taken an hour sequentially.

