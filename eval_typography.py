#!/usr/bin/env python3
"""
Typography Intelligence -- Evaluation Script
=============================================
Tests a trained typography model against known-correct outputs.
Supports MLX fused models, baseline comparison, and deterministic lint.

Usage:
  python3 eval_typography.py --model typography-lora/fused-model
  python3 eval_typography.py --baseline
  python3 eval_typography.py --lint-only
  python3 eval_typography.py --model typography-lora/fused-model --output results.json
  python3 eval_typography.py --compare results-baseline.json results-finetuned.json
"""

import argparse
import difflib
import json
import sys
import time
from dataclasses import dataclass, asdict
from pathlib import Path


# ---------------------------------------------------------------------------
# Optional imports -- ML deps only needed for model eval, not --lint-only
# ---------------------------------------------------------------------------

def _load_mlx():
    """Lazy-import mlx_lm; returns (load, generate) or raises ImportError."""
    from mlx_lm import load, generate
    return load, generate


# ---------------------------------------------------------------------------
# Language names (shared with correct.py -- canonical source)
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

# Rule family -> batch mapping for aggregate reporting
RULE_TO_BATCH = {
    "quotation": 0,
    "dashes": 0,
    "range": 0,
    "french_spacing": 0,
    "inverted_punctuation": 0,
    "accents": 0,
    "ellipsis": 0,
    "measurements": 0,
    "ordinals": 0,
    # Batch 1
    "code_exclusion": 1,
    "normalization": 1,
    "zero_width_characters": 1,
    # Batch 2
    "diacritic_correctness": 2,
    "capital_accents": 2,
    "eszett_capitalisation": 2,
    "orthographic_ligatures": 2,
    "homoglyph_detection": 2,
    # Batch 3
    "high_punctuation_spacing": 3,
    "din5008_abbreviations": 3,
    "nbsp_obligations": 3,
    "single_letter_line_end": 3,
    # Batch 4
    "colon_capitalisation": 4,
    "serial_comma": 4,
    "quote_punctuation_placement": 4,
    "abbreviation_periods": 4,
    "abbreviation_haplology": 4,
    "footnote_mark_placement": 4,
    "nested_parentheticals": 4,
    # Batch 5
    "ligature_suppression": 5,
    "orthographic_ligature_preservation": 5,
    # Batch 6
    "breakable_containers": 6,
    "bidi_isolate_preservation": 6,
    "screen_reader_typography": 6,
}


# ---------------------------------------------------------------------------
# Prompt building -- mirrors correct.py exactly
# ---------------------------------------------------------------------------

def build_instruction(lang: str, register: str | None = None) -> str:
    """Build the instruction string matching the training data format."""
    lang_name = LANG_NAMES.get(lang, lang)
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


# ---------------------------------------------------------------------------
# Result data
# ---------------------------------------------------------------------------

@dataclass
class EvalResult:
    language: str
    rule: str
    batch: int
    input_text: str
    expected: str
    predicted: str
    exact_match: bool
    similarity_score: float
    regression: bool
    description: str = ""


# ---------------------------------------------------------------------------
# Scoring helpers
# ---------------------------------------------------------------------------

def similarity_score(expected: str, predicted: str) -> float:
    """Character-level similarity between expected and predicted (0-1)."""
    if expected == predicted:
        return 1.0
    if not expected:
        return 1.0 if not predicted else 0.0
    return difflib.SequenceMatcher(None, expected, predicted).ratio()


def detect_regression(input_text: str, expected: str, predicted: str) -> bool:
    """
    Regression = the model made the text WORSE.
    We check whether the predicted text is further from the expected than the
    original input was.  If the model moved away from the target, that is a
    regression.
    """
    if predicted.strip() == expected.strip():
        return False  # exact match is never a regression
    input_sim = difflib.SequenceMatcher(None, expected, input_text).ratio()
    pred_sim = difflib.SequenceMatcher(None, expected, predicted).ratio()
    return pred_sim < input_sim


# ---------------------------------------------------------------------------
# Test cases -- ground truth for evaluation (83 cases)
# ---------------------------------------------------------------------------

EVAL_CASES = [
    # Quotation marks
    {"lang": "pt-PT", "rule": "quotation",
     "input": 'Ele disse "obrigado" e saiu.',
     "expected": 'Ele disse \u00ab\u2009obrigado\u2009\u00bb e\u00a0saiu.'},

    {"lang": "en-US", "rule": "quotation",
     "input": 'She whispered "be careful" to him.',
     "expected": 'She whispered \u201cbe careful\u201d to him.'},

    {"lang": "en-GB", "rule": "quotation",
     "input": "She whispered 'be careful' to him.",
     "expected": 'She whispered \u2018be careful\u2019 to him.'},

    {"lang": "fr-FR", "rule": "quotation",
     "input": 'Il a dit "merci" et est parti.',
     "expected": 'Il a dit \u00ab\u202fmerci\u202f\u00bb et est parti.'},

    {"lang": "de-DE", "rule": "quotation",
     "input": 'Er sagte "danke" und ging.',
     "expected": 'Er sagte \u201edanke\u201c und ging.'},

    {"lang": "it-IT", "rule": "quotation",
     "input": 'Ha detto "grazie" ed \u00e8 andato via.',
     "expected": 'Ha detto \u00abgrazie\u00bb ed \u00e8 andato via.'},

    {"lang": "es-ES", "rule": "quotation",
     "input": 'Ella dijo "gracias" y se fue.',
     "expected": 'Ella dijo \u00abgracias\u00bb y\u00a0se fue.'},

    {"lang": "es-MX", "rule": "quotation",
     "input": 'Ella dijo "gracias" y se fue.',
     "expected": 'Ella dijo \u201cgracias\u201d y\u00a0se fue.'},

    # Dashes
    {"lang": "en-US", "rule": "dashes",
     "input": "The project - a massive undertaking - succeeded.",
     "expected": "The project\u2014a massive undertaking\u2014succeeded."},

    {"lang": "en-GB", "rule": "dashes",
     "input": "The project - a massive undertaking - succeeded.",
     "expected": "The project \u2013 a massive undertaking \u2013 succeeded."},

    {"lang": "en-US", "rule": "range",
     "input": "See chapters 3-7.",
     "expected": "See chapters 3\u20137."},

    # French spacing
    {"lang": "fr-FR", "rule": "french_spacing",
     "input": "Vraiment? Oui!",
     "expected": "Vraiment\u202f? Oui\u202f!"},

    # Inverted punctuation
    {"lang": "es-ES", "rule": "inverted_punctuation",
     "input": "Donde vives?",
     "expected": "\u00bfD\u00f3nde vives?"},

    {"lang": "es-ES", "rule": "inverted_punctuation",
     "input": "Que increible!",
     "expected": "\u00a1Qu\u00e9 incre\u00edble!"},

    # Italian accents
    {"lang": "it-IT", "rule": "accents",
     "input": "Perche' non vieni con noi?",
     "expected": "Perch\u00e9 non vieni con noi?"},

    # Ellipsis
    {"lang": "en-US", "rule": "ellipsis",
     "input": "And then...",
     "expected": "And then\u2026"},

    # Measurements
    {"lang": "en-US", "rule": "measurements",
     "input": "Display: 2560x1440 resolution.",
     "expected": "Display: 2560\u2009\u00d7\u20091440 resolution."},

    # Ordinals
    {"lang": "pt-PT", "rule": "ordinals",
     "input": "O 5o andar do edif\u00edcio.",
     "expected": "O\u00a05.\u00ba andar do edif\u00edcio.",
     "description": "Ordinal 5o -> 5.º; NBSP after article O"},

    {"lang": "es-ES", "rule": "ordinals",
     "input": "El 3er piso.",
     "expected": "El 3.\u00ba piso."},

    # ===================================================================
    # BATCH 1 -- Code exclusion, NFC normalization, zero-width characters
    # ===================================================================

    {"lang": "en-US", "rule": "code_exclusion",
     "input": 'Use `"hello"` in your code, but "hello" in prose.',
     "expected": 'Use `"hello"` in your code, but \u201chello\u201d in prose.',
     "description": "Straight quotes inside inline backticks preserved; prose quotes corrected"},

    {"lang": "en-US", "rule": "code_exclusion",
     "input": 'The URL https://example.com/path?q="test" should stay.',
     "expected": 'The URL https://example.com/path?q="test" should stay.',
     "description": "URL with query parameters must not be modified"},

    {"lang": "fr-FR", "rule": "code_exclusion",
     "input": 'La variable `nom_d\'utilisateur` contient "Jean".',
     "expected": 'La variable `nom_d\'utilisateur` contient \u00ab\u202fJean\u202f\u00bb.',
     "description": "Code in backticks preserved; prose quotes get French guillemets with NNBSP"},

    # NFC normalization
    {"lang": "en-US", "rule": "normalization",
     "input": "re\u0301sume\u0301",
     "expected": "r\u00e9sum\u00e9",
     "description": "NFD decomposed e + combining acute composed to NFC precomposed \u00e9"},

    {"lang": "fr-FR", "rule": "normalization",
     "input": "E\u0301TAT",
     "expected": "\u00c9TAT",
     "description": "NFD decomposed E + combining acute composed to NFC precomposed \u00c9"},

    # Zero-width character handling
    {"lang": "en-US", "rule": "zero_width_characters",
     "input": "Hello\u200b world",
     "expected": "Hello world",
     "description": "Zero-width space (U+200B) stripped from running prose"},

    {"lang": "en-US", "rule": "zero_width_characters",
     "input": "Copy\u200bpaste\u200bartifact",
     "expected": "Copy paste artifact",
     "description": "ZWSP between letters replaced with space -- common copy-paste corruption"},

    {"lang": "de-DE", "rule": "zero_width_characters",
     "input": "Auf\u200clage",
     "expected": "Auf\u200clage",
     "description": "ZWNJ preserved -- legitimate German ligature suppression at morpheme boundary"},

    # ===================================================================
    # BATCH 2 -- Diacritic integrity and homoglyph detection
    # ===================================================================

    {"lang": "ro-RO", "rule": "diacritic_correctness",
     "input": "\u015fcoa\u0163l\u0103",
     "expected": "\u0219coa\u021bl\u0103",
     "description": "Romanian cedilla forms corrected to comma-below"},

    {"lang": "ro-RO", "rule": "diacritic_correctness",
     "input": "Bucure\u015fti",
     "expected": "Bucure\u0219ti",
     "description": "Cedilla S in Bucure\u015fti corrected to comma-below S"},

    {"lang": "ro-RO", "rule": "diacritic_correctness",
     "input": "cuno\u015ftin\u0163e",
     "expected": "cuno\u0219tin\u021be",
     "description": "Multiple cedilla characters corrected in a single word"},

    # French capital accents
    {"lang": "fr-FR", "rule": "capital_accents",
     "input": "L'ETAT",
     "expected": "L\u2019\u00c9TAT",
     "description": "Missing accent on capital E in ETAT; apostrophe also curled"},

    {"lang": "fr-FR", "rule": "capital_accents",
     "input": "A PARIS",
     "expected": "\u00c0 PARIS",
     "description": "Missing accent on capital A"},

    {"lang": "fr-FR", "rule": "capital_accents",
     "input": "HOTEL DE VILLE",
     "expected": "H\u00d4TEL DE VILLE",
     "description": "Missing circumflex on capital O in HOTEL"},

    # German capital sharp S
    {"lang": "de-DE", "rule": "eszett_capitalisation",
     "input": "STRASSE",
     "expected": "STRA\u1e9eE",
     "description": "STRASSE corrected to STRA\u1e9eE with capital sharp S"},

    {"lang": "de-DE", "rule": "eszett_capitalisation",
     "input": "GROSSE",
     "expected": "GRO\u1e9eE",
     "description": "GROSSE corrected to GRO\u1e9eE with capital sharp S"},

    # French orthographic ligatures
    {"lang": "fr-FR", "rule": "orthographic_ligatures",
     "input": "Il a du coeur.",
     "expected": "Il a du c\u0153ur.",
     "description": "Decomposed oe in coeur corrected to \u0153 ligature"},

    {"lang": "fr-FR", "rule": "orthographic_ligatures",
     "input": "C'est une oeuvre magistrale.",
     "expected": "C\u2019est une \u0153uvre magistrale.",
     "description": "Decomposed oe in oeuvre corrected to \u0153 ligature"},

    {"lang": "fr-FR", "rule": "orthographic_ligatures",
     "input": "Ma soeur est partie.",
     "expected": "Ma s\u0153ur est partie.",
     "description": "Decomposed oe in soeur corrected to \u0153 ligature"},

    # Homoglyph detection -- degree vs ordinal indicator
    {"lang": "en-US", "rule": "homoglyph_detection",
     "input": "The temperature is 20\u00baC.",
     "expected": "The temperature is 20\u00a0\u00b0C.",
     "description": "Masculine ordinal indicator corrected to degree sign in temperature context"},

    {"lang": "de-DE", "rule": "homoglyph_detection",
     "input": "Es sind 5\u00baC drau\u00dfen.",
     "expected": "Es sind 5\u00a0\u00b0C drau\u00dfen.",
     "description": "Ordinal indicator corrected to degree sign in German temperature"},

    # Homoglyph detection -- Greek beta vs German eszett
    {"lang": "de-DE", "rule": "homoglyph_detection",
     "input": "Die Stra\u03b2e ist lang.",
     "expected": "Die Stra\u00dfe ist lang.",
     "description": "Greek beta corrected to German eszett in Stra\u00dfe"},

    # ===================================================================
    # BATCH 3 -- NNBSP semantics, NBSP obligations, single-letter rules
    # ===================================================================

    {"lang": "fr-FR", "rule": "high_punctuation_spacing",
     "input": "Pourquoi? Parce que: c'est ainsi.",
     "expected": "Pourquoi\u202f? Parce que\u202f: c\u2019est ainsi.",
     "description": "NNBSP inserted before ? and : in French"},

    {"lang": "fr-FR", "rule": "high_punctuation_spacing",
     "input": "Attention; ceci est important!",
     "expected": "Attention\u202f; ceci est important\u202f!",
     "description": "NNBSP inserted before ; and ! in French"},

    {"lang": "fr-FR", "rule": "high_punctuation_spacing",
     "input": "Il a dit: \"Oui!\"",
     "expected": "Il a dit\u202f: \u00ab\u202fOui\u202f!\u202f\u00bb",
     "description": "NNBSP before colon, inside guillemets, and before exclamation mark"},

    # German DIN 5008 abbreviation spacing
    {"lang": "de-DE", "rule": "din5008_abbreviations",
     "input": "z.B. ist das interessant.",
     "expected": "z.\u202fB. ist das interessant.",
     "description": "NNBSP inserted between parts of z.B. per DIN 5008"},

    {"lang": "de-DE", "rule": "din5008_abbreviations",
     "input": "d.h. wir kommen morgen.",
     "expected": "d.\u202fh. wir kommen morgen.",
     "description": "NNBSP inserted between parts of d.h. per DIN 5008"},

    {"lang": "de-DE", "rule": "din5008_abbreviations",
     "input": "Der e.V. tagt morgen u.a. zum Thema.",
     "expected": "Der e.\u202fV. tagt morgen u.\u202fa. zum Thema.",
     "description": "Multiple DIN 5008 abbreviations corrected in one sentence"},

    # NBSP between initials
    {"lang": "en-US", "rule": "nbsp_obligations",
     "input": "J.R.R. Tolkien wrote The Hobbit.",
     "expected": "J.\u00a0R.\u00a0R. Tolkien wrote The Hobbit.",
     "description": "NBSP inserted between author initials to prevent line breaks"},

    {"lang": "fr-FR", "rule": "nbsp_obligations",
     "input": "Mme Curie a decouvert le radium.",
     "expected": "Mme\u00a0Curie a decouvert le radium.",
     "description": "NBSP after title abbreviation Mme to prevent line break (accent correction is model-only)"},

    {"lang": "pt-PT", "rule": "nbsp_obligations",
     "input": "O Sr. Silva chegou.",
     "expected": "O\u00a0Sr.\u00a0Silva chegou.",
     "description": "NBSP after single-letter article O and after title Sr."},

    {"lang": "en-US", "rule": "nbsp_obligations",
     "input": "See p. 42 for details.",
     "expected": "See p.\u00a042 for details.",
     "description": "NBSP between page abbreviation and number"},

    # Single-letter line-ending rules
    {"lang": "fr-FR", "rule": "single_letter_line_end",
     "input": "Il va \u00e0 la gare.",
     "expected": "Il va \u00e0\u00a0la gare.",
     "description": "NBSP after single-letter word \u00e0 in French to prevent orphan at line end"},

    {"lang": "es-ES", "rule": "single_letter_line_end",
     "input": "Pan y agua.",
     "expected": "Pan y\u00a0agua.",
     "description": "NBSP after single-letter conjunction y in Spanish to prevent orphan"},

    {"lang": "it-IT", "rule": "single_letter_line_end",
     "input": "Pane e acqua.",
     "expected": "Pane e\u00a0acqua.",
     "description": "NBSP after single-letter conjunction e in Italian to prevent orphan"},

    {"lang": "pt-PT", "rule": "single_letter_line_end",
     "input": "P\u00e3o e \u00e1gua.",
     "expected": "P\u00e3o e\u00a0\u00e1gua.",
     "description": "NBSP after single-letter conjunction e in Portuguese to prevent orphan"},

    # ===================================================================
    # BATCH 4 -- Locale-branched punctuation
    # ===================================================================

    {"lang": "en-US", "rule": "colon_capitalisation",
     "input": "The verdict was clear: he was guilty.",
     "expected": "The verdict was clear: He was guilty.",
     "description": "EN-US capitalises after colon when independent clause follows"},

    {"lang": "en-US", "rule": "colon_capitalisation",
     "input": "She had one goal: To win.",
     "expected": "She had one goal: to win.",
     "description": "EN-US lowercase after colon for infinitive phrase"},

    {"lang": "fr-FR", "rule": "colon_capitalisation",
     "input": "Le verdict est clair\u202f: Il est coupable.",
     "expected": "Le verdict est clair\u202f: il est coupable.",
     "description": "FR never capitalises after a colon"},

    {"lang": "de-DE", "rule": "colon_capitalisation",
     "input": "Das Ergebnis war klar: er war schuldig.",
     "expected": "Das Ergebnis war klar: Er war schuldig.",
     "description": "DE capitalises after colon when a full sentence follows"},

    # Serial comma
    {"lang": "en-US", "rule": "serial_comma",
     "input": "red, white and blue",
     "expected": "red, white, and blue",
     "description": "EN-US editorial register enforces serial (Oxford) comma"},

    {"lang": "fr-FR", "rule": "serial_comma",
     "input": "rouge, blanc, et bleu",
     "expected": "rouge, blanc et bleu",
     "description": "FR prohibits serial comma"},

    {"lang": "de-DE", "rule": "serial_comma",
     "input": "rot, wei\u00df, und blau",
     "expected": "rot, wei\u00df und blau",
     "description": "DE prohibits serial comma before und"},

    # Quote punctuation placement
    {"lang": "en-US", "rule": "quote_punctuation_placement",
     "input": "He called it \"magnificent\".",
     "expected": "He called it \u201cmagnificent.\u201d",
     "description": "EN-US typesetters\u2019 convention -- period moves inside closing quote"},

    {"lang": "en-GB", "rule": "quote_punctuation_placement",
     "input": "He called it \u2018magnificent.\u2019",
     "expected": "He called it \u2018magnificent\u2019.",
     "description": "EN-GB logical convention -- period outside closing quote"},

    {"lang": "de-DE", "rule": "quote_punctuation_placement",
     "input": "Er nannte es \u201egro\u00dfartig.\u201c",
     "expected": "Er nannte es \u201egro\u00dfartig\u201c.",
     "description": "DE logical placement -- period outside closing quote"},

    # Abbreviation periods
    {"lang": "en-US", "rule": "abbreviation_periods",
     "input": "Mr Smith and Dr Jones arrived.",
     "expected": "Mr.\u00a0Smith and Dr.\u00a0Jones arrived.",
     "description": "EN-US requires period after all abbreviations"},

    {"lang": "en-GB", "rule": "abbreviation_periods",
     "input": "Mr. Smith and Dr. Jones arrived.",
     "expected": "Mr Smith and Dr Jones arrived.",
     "description": "EN-GB drops period from contractions where last letter matches full word"},

    {"lang": "fr-FR", "rule": "abbreviation_periods",
     "input": "M Dupont et Mme. Curie sont arriv\u00e9s.",
     "expected": "M.\u00a0Dupont et Mme\u00a0Curie sont arriv\u00e9s.",
     "description": "FR: M. takes period (truncation), Mme drops it (contraction); NBSP after both"},

    # Abbreviation haplology
    {"lang": "en-US", "rule": "abbreviation_haplology",
     "input": "They sell fruit, vegetables, etc..",
     "expected": "They sell fruit, vegetables, etc.",
     "description": "Double period collapsed at sentence end"},

    {"lang": "en-US", "rule": "abbreviation_haplology",
     "input": "He works for Acme Corp..",
     "expected": "He works for Acme Corp.",
     "description": "Double period after Corp. collapsed"},

    # Footnote mark placement
    {"lang": "en-US", "rule": "footnote_mark_placement",
     "input": "Typography matters\u00b9.",
     "expected": "Typography matters.\u00b9",
     "description": "EN-US: footnote mark placed AFTER punctuation"},

    {"lang": "fr-FR", "rule": "footnote_mark_placement",
     "input": "La typographie est importante.\u00b9",
     "expected": "La typographie est importante\u00b9.",
     "description": "FR: footnote mark placed BEFORE punctuation"},

    {"lang": "de-DE", "rule": "footnote_mark_placement",
     "input": "Typografie ist wichtig\u00b9.",
     "expected": "Typografie ist wichtig.\u00b9",
     "description": "DE: footnote mark placed AFTER punctuation"},

    # Nested parentheticals
    {"lang": "en-US", "rule": "nested_parentheticals",
     "input": "The result (as noted by Smith (2020)) was significant.",
     "expected": "The result (as noted by Smith [2020]) was significant.",
     "description": "Inner parentheses converted to square brackets"},

    # ===================================================================
    # BATCH 5 -- Micro-typography (character-level rules)
    # ===================================================================

    {"lang": "de-DE", "rule": "ligature_suppression",
     "input": "Auflage",
     "expected": "Auf\u200clage",
     "description": "DE: ZWNJ inserted at morpheme boundary to suppress f-l ligature"},

    {"lang": "de-DE", "rule": "ligature_suppression",
     "input": "Schifffahrt",
     "expected": "Schiff\u200cfahrt",
     "description": "DE: ZWNJ at morpheme boundary in Schiff+fahrt"},

    {"lang": "en-US", "rule": "ligature_suppression",
     "input": "shelfful",
     "expected": "shelf\u200cful",
     "description": "EN-US: ZWNJ at morpheme boundary in shelf+ful"},

    # Orthographic ligature preservation
    {"lang": "fr-FR", "rule": "orthographic_ligature_preservation",
     "input": "Il a du coeur et sa soeur aussi.",
     "expected": "Il a du c\u0153ur et sa s\u0153ur aussi.",
     "description": "FR: decomposed oe corrected to \u0153 ligature"},

    {"lang": "fr-FR", "rule": "orthographic_ligature_preservation",
     "input": "C\u2019est une oeuvre de boeuf.",
     "expected": "C\u2019est une \u0153uvre de b\u0153uf.",
     "description": "FR: oe->oe ligature in oeuvre and boeuf"},

    # ===================================================================
    # BATCH 6 -- WCAG-safe emission
    # ===================================================================

    {"lang": "en-US", "rule": "breakable_containers",
     "input": "J.\u00a0R.\u00a0R.\u00a0Tolkien",
     "expected": "J.\u00a0R. R.\u00a0Tolkien",
     "description": "4-word NBSP chain reduced for reflow"},

    {"lang": "en-US", "rule": "bidi_isolate_preservation",
     "input": "The name is \u2066\u05e9\u05dc\u05d5\u05dd\u2069 in Hebrew.",
     "expected": "The name is \u2066\u05e9\u05dc\u05d5\u05dd\u2069 in Hebrew.",
     "description": "Bidi isolate characters preserved"},

    {"lang": "en-US", "rule": "screen_reader_typography",
     "input": "See pages 10-20 for details.",
     "expected": "See pages 10\u201320 for details.",
     "description": "Hyphen-minus in range replaced with en dash"},

    {"lang": "en-US", "rule": "screen_reader_typography",
     "input": "Mix 1/4 cup of flour...",
     "expected": "Mix \u00bc cup of flour\u2026",
     "description": "ASCII fraction replaced with vulgar fraction and three dots with ellipsis"},
]


# ---------------------------------------------------------------------------
# Inference backends
# ---------------------------------------------------------------------------

class MLXBackend:
    """Inference via mlx_lm (local MLX model)."""

    def __init__(self, model_path: str):
        load, _ = _load_mlx()
        print(f"  Loading model: {model_path}")
        self.model, self.tokenizer = load(model_path)
        _, self.generate_fn = _load_mlx()

    def predict(self, lang: str, input_text: str) -> str:
        instruction = build_instruction(lang)
        prompt = build_alpaca_prompt(instruction, input_text)
        # mlx_lm API changed: temp -> sampler kwarg; use temperature= if supported
        try:
            result = self.generate_fn(
                self.model,
                self.tokenizer,
                prompt=prompt,
                max_tokens=max(len(input_text) * 3, 128),
                temperature=0.1,
                top_p=0.9,
                verbose=False,
            )
        except TypeError:
            # Fallback: drop sampling args if API doesn't accept them
            result = self.generate_fn(
                self.model,
                self.tokenizer,
                prompt=prompt,
                max_tokens=max(len(input_text) * 3, 128),
                verbose=False,
            )
        return result.strip() if result else ""


class LintBackend:
    """Inference via the deterministic typography_lint library."""

    def __init__(self):
        try:
            import typography_lint
            self.lint = typography_lint
        except ImportError:
            print("ERROR: typography_lint module not found.", file=sys.stderr)
            print("  --lint-only requires typography_lint.py in the project.", file=sys.stderr)
            sys.exit(1)

    def predict(self, lang: str, input_text: str) -> str:
        from typography_lint import TypographyLinter
        linter = TypographyLinter(language=lang)
        result = linter.lint(input_text)
        return result.text


# ---------------------------------------------------------------------------
# Evaluation engine
# ---------------------------------------------------------------------------

def evaluate(backend, cases: list[dict], label: str = "model") -> list[EvalResult]:
    """Run all cases through a backend and return scored results."""
    results: list[EvalResult] = []
    total = len(cases)

    for i, case in enumerate(cases, 1):
        try:
            predicted = backend.predict(case["lang"], case["input"])
        except Exception as e:
            predicted = f"[ERROR: {e}]"

        expected = case["expected"]
        stripped_pred = predicted.strip()
        stripped_exp = expected.strip()

        exact = stripped_pred == stripped_exp
        sim = similarity_score(stripped_exp, stripped_pred)
        reg = detect_regression(case["input"], stripped_exp, stripped_pred)
        batch = RULE_TO_BATCH.get(case["rule"], -1)

        result = EvalResult(
            language=case["lang"],
            rule=case["rule"],
            batch=batch,
            input_text=case["input"],
            expected=expected,
            predicted=predicted,
            exact_match=exact,
            similarity_score=round(sim, 4),
            regression=reg,
            description=case.get("description", ""),
        )
        results.append(result)

        status = "\u2713" if exact else ("\u26a0" if reg else "\u2717")
        sys.stdout.write(f"\r  [{i:3d}/{total}] {status} {case['lang']} / {case['rule']:<35s}")
        sys.stdout.flush()

    # Clear progress line
    sys.stdout.write("\r" + " " * 80 + "\r")
    sys.stdout.flush()

    return results


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

def print_report(results: list[EvalResult], label: str = "Model"):
    """Print a detailed evaluation report to stdout."""
    total = len(results)
    exact_count = sum(1 for r in results if r.exact_match)
    regression_count = sum(1 for r in results if r.regression)
    avg_sim = sum(r.similarity_score for r in results) / total if total else 0

    print()
    print("=" * 70)
    print(f"  TYPOGRAPHY INTELLIGENCE -- EVALUATION REPORT")
    print(f"  Source: {label}")
    print(f"  Cases:  {total}")
    print("=" * 70)

    # Overall
    print(f"\n  OVERALL")
    print(f"    Exact matches:   {exact_count:3d}/{total} ({100 * exact_count / total:.1f}%)")
    print(f"    Avg similarity:  {avg_sim:.1%}")
    print(f"    Regressions:     {regression_count:3d}/{total} ({100 * regression_count / total:.1f}%)")

    # By language
    print(f"\n  BY LANGUAGE")
    print(f"    {'Language':<10s}  {'Exact':>8s}  {'Sim':>7s}  {'Regr':>6s}")
    print(f"    {'-' * 10}  {'-' * 8}  {'-' * 7}  {'-' * 6}")
    langs = sorted(set(r.language for r in results))
    for lang in langs:
        lr = [r for r in results if r.language == lang]
        le = sum(1 for r in lr if r.exact_match)
        ls = sum(r.similarity_score for r in lr) / len(lr)
        lreg = sum(1 for r in lr if r.regression)
        print(f"    {lang:<10s}  {le:>3d}/{len(lr):<3d}  {ls:>6.1%}  {lreg:>3d}")

    # By rule family
    print(f"\n  BY RULE FAMILY")
    print(f"    {'Rule':<38s}  {'Exact':>8s}  {'Sim':>7s}")
    print(f"    {'-' * 38}  {'-' * 8}  {'-' * 7}")
    rules = sorted(set(r.rule for r in results))
    for rule in rules:
        rr = [r for r in results if r.rule == rule]
        re_ = sum(1 for r in rr if r.exact_match)
        rs = sum(r.similarity_score for r in rr) / len(rr)
        print(f"    {rule:<38s}  {re_:>3d}/{len(rr):<3d}  {rs:>6.1%}")

    # By batch
    print(f"\n  BY BATCH")
    print(f"    {'Batch':<12s}  {'Exact':>8s}  {'Sim':>7s}  {'Regr':>6s}")
    print(f"    {'-' * 12}  {'-' * 8}  {'-' * 7}  {'-' * 6}")
    batches = sorted(set(r.batch for r in results))
    batch_labels = {
        0: "Pre-batch",
        1: "Batch 1",
        2: "Batch 2",
        3: "Batch 3",
        4: "Batch 4",
        5: "Batch 5",
        6: "Batch 6",
        -1: "Unknown",
    }
    for b in batches:
        br = [r for r in results if r.batch == b]
        be = sum(1 for r in br if r.exact_match)
        bs = sum(r.similarity_score for r in br) / len(br)
        breg = sum(1 for r in br if r.regression)
        bl = batch_labels.get(b, f"Batch {b}")
        print(f"    {bl:<12s}  {be:>3d}/{len(br):<3d}  {bs:>6.1%}  {breg:>3d}")

    # Failures detail
    failures = [r for r in results if not r.exact_match]
    if failures:
        print(f"\n  FAILURES ({len(failures)})")
        print(f"  {'-' * 66}")
        for r in failures:
            reg_flag = " [REGRESSION]" if r.regression else ""
            print(f"\n    {r.language} / {r.rule}{reg_flag}  (sim: {r.similarity_score:.1%})")
            if r.description:
                print(f"    Desc:     {r.description}")
            print(f"    Input:    {r.input_text}")
            print(f"    Expected: {r.expected}")
            print(f"    Got:      {r.predicted}")

    print()
    print("=" * 70)


def print_comparison(results_a: list[dict], results_b: list[dict],
                     label_a: str, label_b: str):
    """Print a side-by-side comparison of two result sets."""
    print()
    print("=" * 70)
    print(f"  COMPARISON: {label_a} vs {label_b}")
    print("=" * 70)

    total = len(results_a)
    ea = sum(1 for r in results_a if r["exact_match"])
    eb = sum(1 for r in results_b if r["exact_match"])
    sa = sum(r["similarity_score"] for r in results_a) / total if total else 0
    sb = sum(r["similarity_score"] for r in results_b) / total if total else 0
    ra = sum(1 for r in results_a if r.get("regression", False))
    rb = sum(1 for r in results_b if r.get("regression", False))

    def _delta(a, b, fmt=".1f"):
        d = b - a
        sign = "+" if d > 0 else ""
        return f"{sign}{d:{fmt}}"

    print(f"\n  {'Metric':<20s}  {label_a:>15s}  {label_b:>15s}  {'Delta':>10s}")
    print(f"  {'-' * 20}  {'-' * 15}  {'-' * 15}  {'-' * 10}")
    print(f"  {'Exact match':<20s}  {ea:>11d}/{total}  {eb:>11d}/{total}  {_delta(ea, eb, 'd'):>10s}")
    print(f"  {'Exact match %':<20s}  {100 * ea / total:>14.1f}%  {100 * eb / total:>14.1f}%  {_delta(100 * ea / total, 100 * eb / total):>9s}%")
    print(f"  {'Avg similarity':<20s}  {sa:>14.1%}  {sb:>14.1%}  {_delta(100 * sa, 100 * sb):>9s}%")
    print(f"  {'Regressions':<20s}  {ra:>11d}/{total}  {rb:>11d}/{total}  {_delta(ra, rb, 'd'):>10s}")

    # Per-language comparison
    langs_a = {}
    langs_b = {}
    for r in results_a:
        langs_a.setdefault(r["language"], []).append(r)
    for r in results_b:
        langs_b.setdefault(r["language"], []).append(r)

    print(f"\n  BY LANGUAGE")
    print(f"  {'Language':<10s}  {label_a + ' exact':>15s}  {label_b + ' exact':>15s}  {'Delta':>10s}")
    print(f"  {'-' * 10}  {'-' * 15}  {'-' * 15}  {'-' * 10}")
    for lang in sorted(set(list(langs_a.keys()) + list(langs_b.keys()))):
        la = langs_a.get(lang, [])
        lb = langs_b.get(lang, [])
        ea_l = sum(1 for r in la if r["exact_match"])
        eb_l = sum(1 for r in lb if r["exact_match"])
        n = max(len(la), len(lb))
        print(f"  {lang:<10s}  {ea_l:>11d}/{n}  {eb_l:>11d}/{n}  {_delta(ea_l, eb_l, 'd'):>10s}")

    # Cases where one model got it right and the other did not
    if len(results_a) == len(results_b):
        gained = []
        lost = []
        for ra_case, rb_case in zip(results_a, results_b):
            if not ra_case["exact_match"] and rb_case["exact_match"]:
                gained.append(rb_case)
            elif ra_case["exact_match"] and not rb_case["exact_match"]:
                lost.append(rb_case)

        if gained:
            print(f"\n  GAINED ({len(gained)} cases {label_b} got right that {label_a} missed)")
            for r in gained[:10]:  # cap display
                print(f"    {r['language']} / {r['rule']}: {r['input_text'][:60]}")

        if lost:
            print(f"\n  LOST ({len(lost)} cases {label_a} got right that {label_b} missed)")
            for r in lost[:10]:
                print(f"    {r['language']} / {r['rule']}: {r['input_text'][:60]}")

    print()
    print("=" * 70)


# ---------------------------------------------------------------------------
# JSON persistence
# ---------------------------------------------------------------------------

def save_results(results: list[EvalResult], path: str, label: str):
    """Save results to a JSON file for tracking over time."""
    import datetime
    data = {
        "label": label,
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "total": len(results),
        "exact_matches": sum(1 for r in results if r.exact_match),
        "regressions": sum(1 for r in results if r.regression),
        "avg_similarity": round(
            sum(r.similarity_score for r in results) / len(results) if results else 0, 4
        ),
        "cases": [asdict(r) for r in results],
    }
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  Results saved to: {path}")


def load_results(path: str) -> tuple[str, list[dict]]:
    """Load results from a JSON file. Returns (label, cases)."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return data.get("label", path), data["cases"]


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Typography Intelligence -- evaluate model accuracy against ground truth"
    )

    group = parser.add_mutually_exclusive_group()
    group.add_argument("--model", type=str,
                       help="Path to MLX fused model (e.g. typography-lora/fused-model)")
    group.add_argument("--baseline", action="store_true",
                       help="Evaluate the raw base model without fine-tuning")
    group.add_argument("--lint-only", action="store_true",
                       help="Evaluate the deterministic lint library (no ML deps needed)")
    group.add_argument("--compare", nargs=2, metavar=("FILE_A", "FILE_B"),
                       help="Compare two saved result JSON files")

    parser.add_argument("--base-model", type=str,
                        default="mlx-community/Llama-3.2-3B-Instruct-4bit",
                        help="Base model ID for --baseline mode")
    parser.add_argument("--output", type=str,
                        help="Save results to JSON file for tracking")

    args = parser.parse_args()

    # --compare mode: load two files and print comparison, then exit
    if args.compare:
        label_a, cases_a = load_results(args.compare[0])
        label_b, cases_b = load_results(args.compare[1])
        print_comparison(cases_a, cases_b, label_a, label_b)
        return

    # Determine backend and label
    if args.lint_only:
        label = "deterministic-lint"
        backend = LintBackend()
    elif args.baseline:
        label = f"baseline ({args.base_model})"
        backend = MLXBackend(args.base_model)
    elif args.model:
        label = f"fine-tuned ({args.model})"
        backend = MLXBackend(args.model)
    else:
        # Default to fused model
        default_path = "typography-lora/fused-model"
        label = f"fine-tuned ({default_path})"
        backend = MLXBackend(default_path)

    print("=" * 70)
    print("  TYPOGRAPHY INTELLIGENCE -- EVALUATION")
    print(f"  Source: {label}")
    print(f"  Cases:  {len(EVAL_CASES)}")
    print("=" * 70)

    start = time.time()
    results = evaluate(backend, EVAL_CASES, label=label)
    elapsed = time.time() - start

    print_report(results, label=label)
    print(f"  Elapsed: {elapsed:.1f}s ({elapsed / len(EVAL_CASES):.2f}s/case)")

    if args.output:
        save_results(results, args.output, label=label)


if __name__ == "__main__":
    main()
