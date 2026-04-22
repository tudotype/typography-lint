#!/usr/bin/env python3
"""
Typography Intelligence — Correction CLI
==========================================
User-friendly interface to the fine-tuned typography model.

Usage:
  python3 correct.py "some text with bad typography" --lang pt-PT
  python3 correct.py --file input.txt --lang fr-FR
  python3 correct.py --file input.txt --lang en-US --register editorial
  echo "text" | python3 correct.py --lang de-DE

Options:
  --lang        Language code (pt-PT, pt-BR, en-US, en-GB, fr-FR, de-DE,
                it-IT, es-ES, es-MX, nl-NL, nl-BE, ro-RO, sc)
  --register    Optional: editorial, marketing, ui, literary
  --model       Path to fused model (default: typography-lora/fused-model)
  --font        Optional: path to target font (.ttf/.otf) for font-aware fallback
  --json        Output as JSON with metadata (includes rule attribution)
  --diff        Show what changed (before/after with highlights)
  --explain     Show what changed and WHY (rule name + description per change)
  --verbose     Show full model prompt and timing

Pipeline integration:
  from correct import TypographyCorrector
  corrector = TypographyCorrector(model_path="typography-lora/fused-model")
  result = corrector.correct("some text", lang="pt-PT")
  print(result.text)
"""

import argparse
import json
import re
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path


# ---------------------------------------------------------------------------
# Language code → human-readable name (must match training data)
# ---------------------------------------------------------------------------
LANG_NAMES = {
    "pt-PT": "European Portuguese",
    "pt-BR": "Brazilian Portuguese",
    "en-US": "American English",
    "en-GB": "British English",
    "fr-FR": "French",
    "de-DE": "German",
    "it-IT": "Italian",
    "es-ES": "European Spanish",
    "es-MX": "Latin American Spanish",
    "nl-NL": "Dutch",
    "nl-BE": "Belgian Dutch",
    "ro-RO": "Romanian",
    "sc":    "Sardinian",
}


# ---------------------------------------------------------------------------
# Rule matching — maps character-level substitution patterns to schema rules
# ---------------------------------------------------------------------------

# Each entry: (compiled regex on original, compiled regex on corrected, rule_name, description, language_hint)
# language_hint is None for universal rules, or a callable (lang) -> bool for language-specific ones.

RULE_PATTERNS: list[dict] = [
    # --- Quotation marks ---
    {
        "id": "quotation",
        "description": "Typographic quotation marks \u2014 never straight quotes",
        "match": lambda orig, corr, _lang: (
            orig in ('"', "'", "\"", "\u0027")
            and corr in ("\u201C", "\u201D", "\u2018", "\u2019",  # EN curly
                         "\u00AB", "\u00BB",                       # angle quotes (FR, PT, etc.)
                         "\u2039", "\u203A",                       # single angle
                         "\u201E", "\u201A")                       # low quotes (DE, RO)
        ),
        "language": None,
    },
    # --- Apostrophe ---
    {
        "id": "apostrophe",
        "description": "Typographic apostrophe for contractions and possessives",
        "match": lambda orig, corr, _lang: orig == "'" and corr == "\u2019",
        "language": None,
    },
    # --- Dialogue attribution (em dash for dialogue) ---
    {
        "id": "dialogue_attribution",
        "description": {
            "pt-PT": "Portuguese uses travess\u00e3o (em dash) for dialogue, not hyphens",
            "pt-BR": "Brazilian Portuguese uses travess\u00e3o (em dash) for dialogue",
            "fr-FR": "French uses tiret (em dash) for dialogue",
            "it-IT": "Italian uses lineetta (em dash) for dialogue",
            "es-ES": "Spanish uses raya (em dash) for dialogue",
            "es-MX": "Latin American Spanish uses raya (em dash) for dialogue",
            "ro-RO": "Romanian uses linie de dialog (em dash) for dialogue",
            "_default": "Em dash used for dialogue attribution",
        },
        "match": lambda orig, corr, _lang: (
            orig in ("--", "-", "\u002D\u002D")
            and corr in ("\u2014",  # em dash
                         "\u2014 ", " \u2014", " \u2014 ",
                         "\u2014\u00A0", "\u00A0\u2014")
        ),
        "language": lambda lang: lang in (
            "pt-PT", "pt-BR", "fr-FR", "it-IT", "es-ES", "es-MX", "ro-RO",
        ),
    },
    # --- Range dash (en dash) ---
    {
        "id": "range_dash",
        "description": "En dash for numeric and temporal ranges",
        "match": lambda orig, corr, _lang: (
            orig in ("-", "--")
            and "\u2013" in corr  # en dash
        ),
        "language": None,
    },
    # --- Em dash for parenthetical aside (EN) ---
    {
        "id": "parenthetical_dash",
        "description": "Em dash for parenthetical asides",
        "match": lambda orig, corr, _lang: (
            orig in ("--", " -- ", " - ")
            and "\u2014" in corr
        ),
        "language": lambda lang: lang.startswith("en"),
    },
    # --- Ellipsis ---
    {
        "id": "ellipsis",
        "description": "Single ellipsis character, never three periods",
        "match": lambda orig, corr, _lang: orig == "..." and corr == "\u2026",
        "language": None,
    },
    # --- NBSP / NNBSP spacing rules ---
    {
        "id": "number_unit_spacing",
        "description": "Non-breaking space between number and unit prevents line break",
        "match": lambda orig, corr, _lang: (
            (orig in ("", " ") and corr in ("\u00A0", "\u202F"))
            or (orig == " " and corr == "\u00A0")
        ),
        "language": None,
    },
    # --- French punctuation spacing (NNBSP before : ; ! ?) ---
    {
        "id": "french_punctuation_spacing",
        "description": "Narrow no-break space before high punctuation in French typesetting",
        "match": lambda orig, corr, lang: (
            lang == "fr-FR"
            and (orig == "" or orig == " ")
            and corr in ("\u202F", "\u00A0")
        ),
        "language": lambda lang: lang == "fr-FR",
    },
    # --- Diacritic correctness (Romanian comma-below) ---
    {
        "id": "diacritic_correctness",
        "description": "Comma-below diacritics instead of cedilla for Romanian",
        "match": lambda orig, corr, _lang: (
            (orig == "\u015F" and corr == "\u0219")    # ş → ș
            or (orig == "\u0163" and corr == "\u021B")  # ţ → ț
        ),
        "language": lambda lang: lang == "ro-RO",
    },
    # --- French ligatures (oe, ae) ---
    {
        "id": "french_ligatures",
        "description": "French orthographic ligatures (\u0153, \u00e6) are mandatory, not decorative",
        "match": lambda orig, corr, _lang: (
            (orig in ("oe", "OE") and corr in ("\u0153", "\u0152"))
            or (orig in ("ae", "AE") and corr in ("\u00E6", "\u00C6"))
        ),
        "language": lambda lang: lang == "fr-FR",
    },
    # --- German capital sharp s ---
    {
        "id": "capital_sharp_s",
        "description": "Capital sharp s (\u1e9e) for all-caps German text",
        "match": lambda orig, corr, _lang: (
            orig == "SS" and corr == "\u1E9E"
        ),
        "language": lambda lang: lang == "de-DE",
    },
    # --- Sentence spacing ---
    {
        "id": "sentence_spacing",
        "description": "Single space between sentences \u2014 never double space",
        "match": lambda orig, corr, _lang: (
            orig == "  " and corr == " "
        ),
        "language": None,
    },
    # --- Measurements (primes) ---
    {
        "id": "measurements",
        "description": "Prime marks for feet/inches and minutes/seconds, not straight quotes",
        "match": lambda orig, corr, _lang: (
            (orig in ("'", '"') and corr in ("\u2032", "\u2033"))
        ),
        "language": None,
    },
    # --- Legal symbols ---
    {
        "id": "legal_symbols",
        "description": "Proper Unicode symbols for copyright, trademark, and registered marks",
        "match": lambda orig, corr, _lang: (
            (orig.lower() in ("(c)", "(r)", "(tm)")
             and corr in ("\u00A9", "\u00AE", "\u2122"))
        ),
        "language": None,
    },
    # --- Dimensions (multiplication sign) ---
    {
        "id": "dimensions",
        "description": "Multiplication sign for dimensions, not letter x",
        "match": lambda orig, corr, _lang: (
            orig.lower() == "x" and corr == "\u00D7"
        ),
        "language": None,
    },
    # --- Minus sign ---
    {
        "id": "minus_sign",
        "description": "Mathematical minus sign, not hyphen-minus",
        "match": lambda orig, corr, _lang: (
            orig == "-" and corr == "\u2212"
        ),
        "language": None,
    },
    # --- Degree symbol ---
    {
        "id": "degree_symbol",
        "description": "Proper degree sign, not superscript o or ordinal indicator",
        "match": lambda orig, corr, _lang: (
            orig in ("\u00BA", "o") and corr == "\u00B0"
        ),
        "language": None,
    },
    # --- Whitespace normalisation ---
    {
        "id": "whitespace",
        "description": "Normalise whitespace characters and patterns",
        "match": lambda orig, corr, _lang: (
            len(orig) > 0
            and orig.isspace() and len(orig) > 1
            and (corr == " " or corr == "")
        ),
        "language": None,
    },
    # --- Arrow symbols ---
    {
        "id": "arrow_symbols",
        "description": "Proper arrow characters instead of ASCII approximations",
        "match": lambda orig, corr, _lang: (
            (orig == "->" and corr == "\u2192")
            or (orig == "<-" and corr == "\u2190")
        ),
        "language": None,
    },
    # --- Fractions ---
    {
        "id": "fractions",
        "description": "Proper fraction characters for common fractions",
        "match": lambda orig, corr, _lang: (
            orig in ("1/2", "1/4", "3/4", "1/3", "2/3")
            and corr in ("\u00BD", "\u00BC", "\u00BE", "\u2153", "\u2154")
        ),
        "language": None,
    },
]


def identify_rule(change: dict, lang: str) -> dict | None:
    """Try to match a change to a typographic rule from the schema.

    Returns a dict with rule, rule_description, and language keys,
    or None if no rule matched.
    """
    orig = change.get("original", "")
    corr = change.get("corrected", "")

    for pattern in RULE_PATTERNS:
        try:
            if pattern["match"](orig, corr, lang):
                # Check language applicability
                lang_check = pattern.get("language")
                if lang_check is not None and not lang_check(lang):
                    continue

                # Resolve description
                desc = pattern["description"]
                if isinstance(desc, dict):
                    desc = desc.get(lang, desc.get("_default", ""))

                return {
                    "rule": pattern["id"],
                    "rule_description": desc,
                    "language": lang,
                }
        except Exception:
            continue

    return None


def annotate_changes(changes: list[dict], lang: str) -> list[dict]:
    """Annotate each change with rule attribution when possible."""
    annotated = []
    for change in changes:
        enriched = dict(change)
        match = identify_rule(change, lang)
        if match:
            enriched["rule"] = match["rule"]
            enriched["rule_description"] = match["rule_description"]
            enriched["language"] = match["language"]
        else:
            enriched["rule"] = None
            enriched["rule_description"] = None
            enriched["language"] = lang
        annotated.append(enriched)
    return annotated


def format_explain_output(corrected_text: str, changes: list[dict]) -> str:
    """Format the --explain terminal output."""
    lines = [corrected_text, ""]

    if not changes:
        lines.append("No changes.")
        return "\n".join(lines)

    lines.append("Changes:")
    for i, change in enumerate(changes, 1):
        orig_display = change["original"] if change["original"] else "[no space]"
        corr_display = change["corrected"] if change["corrected"] else "[removed]"
        # Make invisible characters visible in the display
        for char, label in [
            ("\u00A0", "[NBSP]"), ("\u202F", "[NNBSP]"), ("\u2009", "[thin space]"),
            ("\u200A", "[hair space]"), ("\u200B", "[ZWSP]"), ("\u200C", "[ZWNJ]"),
            ("\u200D", "[ZWJ]"), ("\u2060", "[WJ]"),
        ]:
            orig_display = orig_display.replace(char, label)
            corr_display = corr_display.replace(char, label)

        lines.append(f"  {i}. \u201C{orig_display}\u201D \u2192 \u201C{corr_display}\u201D")

        rule = change.get("rule")
        if rule:
            lang_tag = change.get("language", "")
            lines.append(f"     Rule: {rule} ({lang_tag})")
            desc = change.get("rule_description")
            if desc:
                lines.append(f"     Reason: {desc}")
        else:
            lines.append("     Rule: (unmatched)")
        lines.append("")

    # Summary stats
    rule_counts: dict[str, int] = {}
    for change in changes:
        rule_name = change.get("rule") or "unmatched"
        rule_counts[rule_name] = rule_counts.get(rule_name, 0) + 1

    unique_rules = len([r for r in rule_counts if r != "unmatched"])
    total_changes = len(changes)
    lines.append(
        f"Summary: {total_changes} change{'s' if total_changes != 1 else ''} "
        f"across {unique_rules} rule{'s' if unique_rules != 1 else ''}"
    )
    for rule_name, count in sorted(rule_counts.items(), key=lambda x: -x[1]):
        lines.append(f"  {rule_name}: {count} change{'s' if count != 1 else ''}")

    return "\n".join(lines)


@dataclass
class CorrectionResult:
    """Result of a typography correction."""
    text: str
    original: str
    language: str
    register: str | None = None
    changes: list = field(default_factory=list)
    font_fallbacks: list = field(default_factory=list)
    tokens_per_sec: float = 0.0
    peak_memory_gb: float = 0.0


def build_instruction(lang: str, register: str | None = None) -> str:
    """Build the instruction string matching the training data format."""
    lang_name = LANG_NAMES.get(lang)
    if not lang_name:
        # Fallback for unknown codes
        lang_name = lang

    instruction = f"Correct the typography in the following {lang_name} text"
    if register:
        instruction += f" for {register} use"
    instruction += "."
    return instruction


def build_alpaca_prompt(instruction: str, input_text: str) -> str:
    """Build the full Alpaca-format prompt the model expects."""
    return (
        "Below is an instruction that describes a task, paired with an input "
        "that provides further context. Write a response that appropriately "
        "completes the request.\n\n"
        f"### Instruction:\n{instruction}\n\n"
        f"### Input:\n{input_text}\n\n"
        "### Response:\n"
    )


def find_changes(original: str, corrected: str) -> list[dict]:
    """Find character-level differences between original and corrected text."""
    changes = []
    # Simple character-by-character comparison for short texts
    if original == corrected:
        return changes

    # Use difflib for a readable diff
    import difflib
    matcher = difflib.SequenceMatcher(None, original, corrected)
    for op, i1, i2, j1, j2 in matcher.get_opcodes():
        if op == "equal":
            continue
        change = {
            "type": op,
            "position": i1,
            "original": original[i1:i2],
            "corrected": corrected[j1:j2],
        }
        # Add Unicode details for non-ASCII characters
        if change["corrected"]:
            change["corrected_codepoints"] = [
                f"U+{ord(c):04X}" for c in change["corrected"]
            ]
        changes.append(change)
    return changes


def highlight_diff(original: str, corrected: str) -> str:
    """Show a coloured diff of changes (terminal ANSI codes)."""
    import difflib

    RED = "\033[91m\033[9m"      # red strikethrough
    GREEN = "\033[92m\033[1m"    # green bold
    RESET = "\033[0m"

    matcher = difflib.SequenceMatcher(None, original, corrected)
    parts = []
    for op, i1, i2, j1, j2 in matcher.get_opcodes():
        if op == "equal":
            parts.append(original[i1:i2])
        elif op == "replace":
            parts.append(f"{RED}{original[i1:i2]}{RESET}{GREEN}{corrected[j1:j2]}{RESET}")
        elif op == "insert":
            parts.append(f"{GREEN}{corrected[j1:j2]}{RESET}")
        elif op == "delete":
            parts.append(f"{RED}{original[i1:i2]}{RESET}")
    return "".join(parts)


class TypographyCorrector:
    """Typography correction using the fine-tuned MLX model."""

    def __init__(self, model_path: str = "typography-lora/fused-model", font_path: str | None = None):
        self.model_path = model_path
        self.model = None
        self.tokenizer = None
        self.font_gate = None

        if font_path:
            try:
                from font_gate import FontGate
                self.font_gate = FontGate(font_path=font_path)
            except ImportError:
                print("Warning: font_gate module not found. Font-aware fallback disabled.", file=sys.stderr)

    def _load_model(self):
        """Lazy-load the model on first use."""
        if self.model is not None:
            return

        from mlx_lm import load
        self.model, self.tokenizer = load(self.model_path)

    def correct(self, text: str, lang: str = "en-US", register: str | None = None) -> CorrectionResult:
        """Correct typography in the given text."""
        self._load_model()

        from mlx_lm import generate

        instruction = build_instruction(lang, register)
        prompt = build_alpaca_prompt(instruction, text)

        start = time.time()
        corrected = generate(
            self.model,
            self.tokenizer,
            prompt=prompt,
            max_tokens=len(text) * 3,  # generous but bounded
            temp=0.1,
            top_p=0.9,
            verbose=False,
        )
        elapsed = time.time() - start

        # Clean up: the model might include trailing whitespace or repeat the prompt
        corrected = corrected.strip()

        # If the model generated nothing useful, return original
        if not corrected:
            corrected = text

        result = CorrectionResult(
            text=corrected,
            original=text,
            language=lang,
            register=register,
            changes=find_changes(text, corrected),
        )

        # Apply font-awareness gate if available
        if self.font_gate:
            processed = self.font_gate.process(corrected)
            result.text = processed.text
            result.font_fallbacks = [
                {"original": fb.original, "replacement": fb.replacement, "reason": fb.reason}
                for fb in processed.fallbacks
            ] if hasattr(processed, 'fallbacks') else []

        return result


def main():
    parser = argparse.ArgumentParser(
        description="Typography Intelligence — correct typographic errors in text"
    )
    parser.add_argument("text", nargs="?", help="Text to correct (or use --file or stdin)")
    parser.add_argument("--lang", default="en-US", help=f"Language code: {', '.join(LANG_NAMES.keys())}")
    parser.add_argument("--register", choices=["editorial", "marketing", "ui", "literary"],
                        help="Register/context for register-sensitive rules")
    parser.add_argument("--model", default="typography-lora/fused-model", help="Path to fused model")
    parser.add_argument("--font", help="Path to target font for font-aware fallback")
    parser.add_argument("--file", help="Read text from file")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--diff", action="store_true", help="Show before/after diff")
    parser.add_argument("--explain", action="store_true",
                        help="Show what changed and why (rule name + description for each change)")
    parser.add_argument("--verbose", action="store_true", help="Show model details and timing")

    args = parser.parse_args()

    # Get input text
    if args.file:
        text = Path(args.file).read_text(encoding="utf-8")
    elif args.text:
        text = args.text
    elif not sys.stdin.isatty():
        text = sys.stdin.read()
    else:
        parser.error("Provide text as an argument, via --file, or pipe through stdin")

    # Validate language
    if args.lang not in LANG_NAMES:
        print(f"Warning: '{args.lang}' not in known languages. Known: {', '.join(LANG_NAMES.keys())}", file=sys.stderr)

    if args.verbose:
        print(f"Language: {args.lang} ({LANG_NAMES.get(args.lang, 'unknown')})", file=sys.stderr)
        if args.register:
            print(f"Register: {args.register}", file=sys.stderr)
        print(f"Model:    {args.model}", file=sys.stderr)
        if args.font:
            print(f"Font:     {args.font}", file=sys.stderr)
        print(file=sys.stderr)

    # Run correction
    corrector = TypographyCorrector(model_path=args.model, font_path=args.font)
    start = time.time()
    result = corrector.correct(text, lang=args.lang, register=args.register)
    elapsed = time.time() - start

    # Annotate changes with rule attribution when --explain or --json is used
    if args.explain or args.json:
        result.changes = annotate_changes(result.changes, args.lang)

    # Output
    if args.json:
        output = {
            "corrected": result.text,
            "original": result.original,
            "language": result.language,
            "register": result.register,
            "changes": result.changes,
            "font_fallbacks": result.font_fallbacks,
            "elapsed_seconds": round(elapsed, 2),
        }
        print(json.dumps(output, ensure_ascii=False, indent=2))
    elif args.explain:
        print(format_explain_output(result.text, result.changes))
    elif args.diff:
        if result.changes:
            print(highlight_diff(result.original, result.text))
            print(f"\n({len(result.changes)} change{'s' if len(result.changes) != 1 else ''})", file=sys.stderr)
        else:
            print(result.text)
            print("\n(no changes)", file=sys.stderr)
        if result.font_fallbacks:
            print(f"({len(result.font_fallbacks)} font fallback{'s' if len(result.font_fallbacks) != 1 else ''})", file=sys.stderr)
    else:
        print(result.text)

    if args.verbose:
        print(f"\nElapsed: {elapsed:.1f}s", file=sys.stderr)
        if result.changes:
            print(f"Changes: {len(result.changes)}", file=sys.stderr)
            for c in result.changes:
                cps = " ".join(c.get("corrected_codepoints", []))
                print(f"  '{c['original']}' → '{c['corrected']}' {cps}", file=sys.stderr)


if __name__ == "__main__":
    main()
