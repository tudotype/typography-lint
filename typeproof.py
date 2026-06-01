#!/usr/bin/env python3
"""
Typeproof -- Layer 1 of the Typeproof pipeline.
===================================================================
A fast, pure-Python deterministic typographic correction library.
No ML dependencies. Handles the 80% of corrections that are
straightforward substitution rules derived from the YAML schema.

Pipeline position:
    Raw text -> [Layer 1: typeproof] -> [Layer 2: Fine-tuned model] -> [Layer 3: Font Gate] -> Safe output

Standalone usage:
    python3 typeproof.py "text to correct" --lang fr-FR
    python3 typeproof.py --file input.txt --lang pt-PT --json
    python3 typeproof.py --file input.txt --lang en-US --diff

Library usage:
    from typeproof import TypographyLinter

    linter = TypographyLinter(language="fr-FR", register="editorial")
    result = linter.lint(text)
    print(result.text)
    print(result.corrections)
    print(result.stats)
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Correction record
# ---------------------------------------------------------------------------

@dataclass
class Correction:
    """A single typographic correction."""
    position: int
    original: str
    replacement: str
    rule: str
    description: str

    def to_dict(self) -> dict:
        return {
            "position": self.position,
            "original": self.original,
            "replacement": self.replacement,
            "rule": self.rule,
            "description": self.description,
        }


@dataclass
class LintResult:
    """Result of a lint pass."""
    text: str
    original: str
    language: str
    register: Optional[str] = None
    corrections: List[Correction] = field(default_factory=list)

    @property
    def stats(self) -> dict:
        by_rule: Dict[str, int] = {}
        for c in self.corrections:
            by_rule[c.rule] = by_rule.get(c.rule, 0) + 1
        return {
            "total_corrections": len(self.corrections),
            "by_rule": by_rule,
        }

    def to_dict(self) -> dict:
        return {
            "text": self.text,
            "original": self.original,
            "language": self.language,
            "register": self.register,
            "corrections": [c.to_dict() for c in self.corrections],
            "stats": self.stats,
        }


# ---------------------------------------------------------------------------
# Code exclusion -- mask regions that must never be corrected
# ---------------------------------------------------------------------------

# Each pattern captures regions to protect.  Order matters: more specific
# patterns should come first to avoid partial matches.
_EXCLUSION_PATTERNS: List[Tuple[str, re.Pattern]] = [
    # Fenced code blocks (``` ... ```)
    ("fenced_code", re.compile(r"```[\s\S]*?```", re.MULTILINE)),
    # HTML code/pre/kbd elements
    ("html_code", re.compile(r"<(?:code|pre|kbd|samp|var|tt)(?:\s[^>]*)?>[\s\S]*?</(?:code|pre|kbd|samp|var|tt)>", re.IGNORECASE)),
    # Any HTML/XML tag -- protects attribute quotes (href="...") from curling.
    # Requires a letter (or /) after "<", so "a < b" and "<3" are NOT matched.
    ("html_tag", re.compile(r"</?[a-zA-Z][^<>]*>")),
    # Inline backtick code (`...`)
    ("inline_code", re.compile(r"`[^`\n]+`")),
    # Email addresses
    ("email", re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")),
    # URLs -- quotes NOT excluded so query-param values like ?q="test" are masked
    ("url", re.compile(r"(?:https?|ftp)://[^\s<>)\]]+", re.ASCII)),
    # File paths (Unix)
    ("filepath_unix", re.compile(r"(?<!\w)(?:/[a-zA-Z0-9_.\-]+){2,}")),
    # File paths (Windows)
    ("filepath_win", re.compile(r"[A-Z]:\\(?:[a-zA-Z0-9_.\-]+\\?)+", re.ASCII)),
    # Version strings  v1.2.3, V2.0.0-beta
    ("version", re.compile(r"\bv\d+(?:\.\d+)+(?:-[a-zA-Z0-9.]+)?\b", re.IGNORECASE)),
    # @mentions
    ("mention", re.compile(r"@[a-zA-Z0-9_]+")),
    # #hashtags
    ("hashtag", re.compile(r"#[a-zA-Z][a-zA-Z0-9_]*")),
    # CamelCase identifiers (at least two uppercase transitions)
    ("camelcase", re.compile(r"\b[a-z]+(?:[A-Z][a-z]+){2,}\b|\b(?:[A-Z][a-z]+){2,}\b")),
    # snake_case identifiers (at least one underscore between word chars)
    ("snakecase", re.compile(r"\b[a-zA-Z][a-zA-Z0-9]*(?:_[a-zA-Z0-9]+){1,}\b")),
    # Regex-like patterns (between slashes with flags)
    ("regex", re.compile(r"(?<!\w)/(?:[^\\/\n]|\\.)+/[gimsuy]*(?!\w)")),
]


def _mask_exclusions(text: str) -> Tuple[str, List[Tuple[str, int, int, str]]]:
    """
    Replace code/URL/path regions with placeholder tokens.
    Returns (masked_text, list_of (placeholder, start, end, original)).
    """
    placeholders: List[Tuple[str, int, int, str]] = []
    masked = text

    # We iterate patterns and replace from right to left so positions stay stable.
    all_spans: List[Tuple[int, int, str, str]] = []
    for name, pat in _EXCLUSION_PATTERNS:
        for m in pat.finditer(text):
            all_spans.append((m.start(), m.end(), name, m.group()))

    # Sort by start position, longest first for overlaps
    all_spans.sort(key=lambda s: (s[0], -(s[1] - s[0])))

    # Remove overlapping spans -- keep the first (longest) one
    filtered: List[Tuple[int, int, str, str]] = []
    last_end = -1
    for start, end, name, orig in all_spans:
        if start >= last_end:
            filtered.append((start, end, name, orig))
            last_end = end

    # Replace from right to left
    for i, (start, end, name, orig) in enumerate(reversed(filtered)):
        idx = len(filtered) - 1 - i
        placeholder = f"\x00EXCL{idx:04d}\x00"
        placeholders.append((placeholder, start, end, orig))
        masked = masked[:start] + placeholder + masked[end:]

    # Reverse placeholders so they are in left-to-right order
    placeholders.reverse()
    return masked, placeholders


def _unmask_exclusions(text: str, placeholders: List[Tuple[str, int, int, str]]) -> str:
    """Restore placeholder tokens to their original content."""
    for placeholder, _start, _end, original in placeholders:
        text = text.replace(placeholder, original)
    return text


# ---------------------------------------------------------------------------
# Quotation mark configuration per language
# ---------------------------------------------------------------------------

# (primary_open, primary_close, nested_open, nested_close,
#  primary_inner_space, nested_inner_space)
# Inner space is the character inserted after open and before close.

NBSP = "\u00A0"
NNBSP = "\u202F"
THIN = "\u2009"

QUOTE_STYLES: Dict[str, Tuple[str, str, str, str, str, str]] = {
    # Language:     (prim_open, prim_close, nest_open, nest_close, prim_space, nest_space)
    "pt-PT":       ("\u00AB", "\u00BB", "\u201C", "\u201D", THIN, ""),
    "pt-BR":       ("\u201C", "\u201D", "\u2018", "\u2019", "", ""),
    "en-US":       ("\u201C", "\u201D", "\u2018", "\u2019", "", ""),
    "en-GB":       ("\u2018", "\u2019", "\u201C", "\u201D", "", ""),
    "fr-FR":       ("\u00AB", "\u00BB", "\u201C", "\u201D", NNBSP, ""),
    "de-DE":       ("\u201E", "\u201C", "\u2039", "\u203A", "", ""),
    "it-IT":       ("\u00AB", "\u00BB", "\u201C", "\u201D", "", ""),
    "es-ES":       ("\u00AB", "\u00BB", "\u201C", "\u201D", "", ""),
    "es-MX":       ("\u201C", "\u201D", "\u2018", "\u2019", "", ""),
    "nl-NL":       ("\u201C", "\u201D", "\u2018", "\u2019", "", ""),
    "nl-BE":       ("\u201C", "\u201D", "\u2018", "\u2019", "", ""),
    "ro-RO":       ("\u201E", "\u201D", "\u00AB", "\u00BB", "", ""),
    "sc":          ("\u00AB", "\u00BB", "\u201C", "\u201D", "", ""),
}

# Languages covered
SUPPORTED_LANGUAGES = set(QUOTE_STYLES.keys())


# ---------------------------------------------------------------------------
# Units for number-unit spacing
# ---------------------------------------------------------------------------

_UNITS = (
    # SI base and derived
    "km", "m", "cm", "mm", "nm", "pm",
    "kg", "g", "mg", "lb", "oz",
    "ml", "l", "L", "dl", "cl",
    "km/h", "m/s",
    "kHz", "MHz", "GHz", "THz", "Hz",
    "kB", "MB", "GB", "TB", "PB",
    "kW", "MW", "GW", "W",
    "kWh", "MWh",
    "V", "mV", "kV",
    "mA", "A",
    "Pa", "hPa", "kPa", "MPa",
    "px", "pt", "em", "rem",
    "fps", "dpi", "ppi",
    "min", "sec", "ms", "ns",
    "rpm",
)

# Build a regex that matches number immediately followed by a unit (no space)
_UNIT_PATTERN = re.compile(
    r"(\d)"
    r"("
    + "|".join(re.escape(u) for u in sorted(_UNITS, key=len, reverse=True))
    + r")"
    r"(?=[\s\.,;:!?\)\]\}]|$)",
)

# Languages that use NNBSP for number-unit spacing
_NNBSP_UNIT_LANGS = {"fr-FR"}

# Languages that use NBSP for number-unit spacing (most European)
_NBSP_UNIT_LANGS = SUPPORTED_LANGUAGES - {"en-US", "en-GB"} - _NNBSP_UNIT_LANGS


# ---------------------------------------------------------------------------
# Common fractions
# ---------------------------------------------------------------------------

_FRACTIONS: Dict[str, str] = {
    "1/2": "\u00BD",
    "1/4": "\u00BC",
    "3/4": "\u00BE",
    "1/3": "\u2153",
    "2/3": "\u2154",
}

_FRACTION_PATTERN = re.compile(
    r"(?<!\d)(" + "|".join(re.escape(k) for k in _FRACTIONS) + r")(?!\d|/)"
)


# ---------------------------------------------------------------------------
# French OE/AE ligatures -- mandatory orthographic letters
# ---------------------------------------------------------------------------

_FR_OE_WORDS = [
    # Lowercase oe -> oe ligature
    ("coeur", "c\u0153ur"),
    ("soeur", "s\u0153ur"),
    ("oeuf", "\u0153uf"),
    ("oeuvre", "\u0153uvre"),
    ("oeuvres", "\u0153uvres"),
    ("boeuf", "b\u0153uf"),
    ("boeufs", "b\u0153ufs"),
    ("voeu", "v\u0153u"),
    ("voeux", "v\u0153ux"),
    ("noeud", "n\u0153ud"),
    ("noeuds", "n\u0153uds"),
    ("moeurs", "m\u0153urs"),
    ("oeil", "\u0153il"),
    ("oeillade", "\u0153illade"),
    ("oeillet", "\u0153illet"),
    ("oeillets", "\u0153illets"),
    ("oesophage", "\u0153sophage"),
    ("oedeme", "\u0153d\u00E8me"),
    ("oenologie", "\u0153nologie"),
    ("oenologue", "\u0153nologue"),
    ("oecumenique", "\u0153cum\u00E9nique"),
    ("manoeuvre", "man\u0153uvre"),
    ("manoeuvres", "man\u0153uvres"),
    ("hors-d'oeuvre", "hors-d'\u0153uvre"),
]


# ---------------------------------------------------------------------------
# Romanian cedilla -> comma-below
# ---------------------------------------------------------------------------

_RO_CEDILLA_MAP = {
    "\u015F": "\u0219",  # s with cedilla -> s with comma below
    "\u0163": "\u021B",  # t with cedilla -> t with comma below
    "\u015E": "\u0218",  # S with cedilla -> S with comma below
    "\u0162": "\u021A",  # T with cedilla -> T with comma below
}


# ---------------------------------------------------------------------------
# German DIN 5008 abbreviation pairs
# ---------------------------------------------------------------------------

_DE_DIN5008_ABBREVS = [
    # (wrong_pattern, replacement) -- NNBSP between parts
    ("z.B.", "z.\u202FB."),
    ("d.h.", "d.\u202Fh."),
    ("u.a.", "u.\u202Fa."),
    ("e.V.", "e.\u202FV."),
    ("u.U.", "u.\u202FU."),
    ("o.g.", "o.\u202Fg."),
    ("s.o.", "s.\u202Fo."),
    ("s.u.", "s.\u202Fu."),
    ("u.v.m.", "u.\u202Fv.\u202Fm."),
    ("i.d.R.", "i.\u202Fd.\u202FR."),
    ("m.E.", "m.\u202FE."),
]


# ---------------------------------------------------------------------------
# Title abbreviations for NBSP insertion (language-aware)
# ---------------------------------------------------------------------------

_TITLE_ABBREVS_UNIVERSAL = ["Mr.", "Mrs.", "Ms.", "Dr.", "Prof."]
_TITLE_ABBREVS_BY_LANG = {
    "pt-PT": ["Sr.", "Sra.", "Dra.", "Eng."],
    "pt-BR": ["Sr.", "Sra.", "Dra.", "Eng."],
    "fr-FR": ["Mme", "Mlle", "M."],
    "de-DE": ["Fr.", "Hr."],
    "es-ES": ["Sr.", "Sra.", "Srta."],
    "es-MX": ["Sr.", "Sra.", "Srta."],
    "it-IT": ["Sig.", "Sig.ra", "Dott."],
}

# Page/section abbreviations: p. 42, pp. 10, s. 3 etc.
# These take NBSP before the number (not before a capitalized name).
_PAGE_ABBREVS = ["p.", "pp.", "s.", "no.", "No.", "§", "art.", "fig.", "tab."]
_PAGE_ABBREV_PAT = re.compile(
    r'(' + '|'.join(re.escape(a) for a in sorted(_PAGE_ABBREVS, key=len, reverse=True)) + r')'
    r' (\d)'
)


# ---------------------------------------------------------------------------
# Single-letter words for NBSP (anti-orphan) by language
# ---------------------------------------------------------------------------

_SINGLE_LETTER_WORDS = {
    # French: à (preposition), y (adverb) — exclude 'a' (verb "avoir") to avoid false positives
    "fr-FR": ["à", "y", "ô", "û"],
    "es-ES": ["y", "o", "e", "a", "u"],
    "es-MX": ["y", "o", "e", "a", "u"],
    "it-IT": ["e", "o", "a", "i"],
    "pt-PT": ["e", "é", "ó", "a", "o"],
    "pt-BR": ["e", "é", "ó", "a", "o"],
}


# ---------------------------------------------------------------------------
# Homoglyph mappings
# ---------------------------------------------------------------------------

# Greek beta -> German eszett word patterns
_BETA_TO_ESZETT_WORDS = [
    "Straβe", "Straße",
    "Groβ", "Groß",
    "groβ", "groß",
    "Fuβ", "Fuß",
    "Spaβ", "Spaß",
    "heiβ", "heiß",
    "weiβ", "weiß",
    "Maβ", "Maß",
    "Gruβ", "Gruß",
    "Schloβ", "Schloß",
    "Floβ", "Floß",
    "Soβe", "Soße",
    "drauβen", "draußen",
    "auβen", "außen",
    "muβ", "muß",
    "daβ", "daß",
]


# ---------------------------------------------------------------------------
# French capital accents -- mandatory per Académie française
# ---------------------------------------------------------------------------

# Word-level substitutions: all-caps form without accent -> with accent
# Applied as whole-word replacements only.  Conservative list -- no ambiguous
# single letters (A -> À requires context).
_FR_CAPITAL_ACCENTS: Dict[str, str] = {
    # É (E-acute)
    "ETAT": "\u00c9TAT",
    "ETAIT": "\u00c9TAIT",
    "ETE": "\u00c9T\u00c9",
    "ECOLE": "\u00c9COLE",
    "EPOQUE": "\u00c9POQUE",
    "EQUIPE": "\u00c9QUIPE",
    "ETUDE": "\u00c9TUDE",
    "ELEVE": "\u00c9L\u00c8VE",
    "ELECTION": "\u00c9LECTION",
    "ELECTRICITE": "\u00c9LECTRICIT\u00c9",
    "ELEMENT": "\u00c9L\u00c9MENT",
    "ELEMENTS": "\u00c9L\u00c9MENTS",
    "EMETTEUR": "\u00c9METTEUR",
    "ENERGIE": "\u00c9NERGIE",
    "EVIER": "\u00c9VIER",
    # Ê (E-circumflex)
    "ETRE": "\u00caTRE",
    "FETE": "F\u00caTE",
    "TETE": "T\u00caTE",
    "FORET": "FOR\u00caT",
    "MEME": "M\u00caM",  # intentionally left out to avoid false positives
    # Ô (O-circumflex)
    "HOTEL": "H\u00d4TEL",
    "COTE": "C\u00d4TE",
    "COTES": "C\u00d4TES",
    "HOTE": "H\u00d4TE",
    "HOPITAL": "H\u00d4PITAL",
    # Î (I-circumflex)
    "ILE": "\u00ceLE",
    "ILES": "\u00ceLES",
    # Â (A-circumflex)
    "AGE": "\u00c2GE",
    "AGES": "\u00c2GES",
    # Û (U-circumflex)
    "SUR": "S\u00dbR",  # risky -- only for sur with circumflex (mûr?)
    # Remove risky entries -- keep only unambiguous words
}

# Safe subset: remove any that could cause false positives
_FR_CAPITAL_ACCENTS_SAFE: Dict[str, str] = {
    k: v for k, v in {
        "ETAT": "\u00c9TAT",
        "ETAIT": "\u00c9TAIT",
        "ECOLE": "\u00c9COLE",
        "EPOQUE": "\u00c9POQUE",
        "EQUIPE": "\u00c9QUIPE",
        "ETUDE": "\u00c9TUDE",
        "ELECTION": "\u00c9LECTION",
        "ENERGIE": "\u00c9NERGIE",
        "ETRE": "\u00caTRE",
        "FETE": "F\u00caTE",
        "TETE": "T\u00caTE",
        "FORET": "FOR\u00caT",
        "HOTEL": "H\u00d4TEL",
        "HOPITAL": "H\u00d4PITAL",
        "HOTE": "H\u00d4TE",
        "ILE": "\u00ceLE",
        "ILES": "\u00ceLES",
    }.items()
}


# ---------------------------------------------------------------------------
# Ordinal patterns by language
# ---------------------------------------------------------------------------

# Portuguese: 5o -> 5.º, 5a -> 5.ª (period + superscript letter)
_PT_ORDINAL_PAT = re.compile(r'(\d+)([oa])\b')

# Spanish (RAE 2010): 3er -> 3.º, 3o -> 3.º, 3a -> 3.ª
_ES_ORDINAL_PAT = re.compile(r'(\d+)(?:er|r)?\b(?= *(?:piso|lugar|grado|cap[íi]tulo|art[íi]culo|secci[óo]n)|\b)')
# Simpler: just catch numeric+ordinal-suffix patterns
_ES_ORDINAL_SUFFIX_PAT = re.compile(r'(\d+)(er|o|a)\b')


# ---------------------------------------------------------------------------
# Ligature suppression -- known German compound words needing ZWNJ
# ---------------------------------------------------------------------------

_DE_LIGATURE_SUPPRESSIONS: List[Tuple[str, str]] = [
    ("Auflage", "Auf\u200clage"),
    ("Auflagen", "Auf\u200clagen"),
    ("Schifffahrt", "Schiff\u200cfahrt"),
    ("Schifffahrts", "Schiff\u200cfahrts"),
    ("Auflauf", "Auf\u200clauf"),
    ("auflagen", "auf\u200clagen"),
    ("Staffel", "Staf\u200cfel"),
    ("staffel", "staf\u200cfel"),
    ("Griffel", "Grif\u200cfel"),
    ("griffel", "grif\u200cfel"),
    ("Kraftfahrzeug", "Kraft\u200cfahrzeug"),
    ("Auffindung", "Auf\u200cfindung"),
    ("Aufführung", "Auf\u200cf\u00fchrung"),
]

_EN_LIGATURE_SUPPRESSIONS: List[Tuple[str, str]] = [
    ("shelfful", "shelf\u200cful"),
    ("shelffuls", "shelf\u200cfuls"),
    ("halflife", "half\u200clife"),
    ("leaflike", "leaf\u200clike"),
]


# ---------------------------------------------------------------------------
# Abbreviation conventions
# ---------------------------------------------------------------------------

# EN-US: all abbreviations take a period
_EN_US_ABBREVS = {
    "Mr": "Mr.", "Mrs": "Mrs.", "Ms": "Ms.", "Dr": "Dr.",
    "St": "St.", "Jr": "Jr.", "Sr": "Sr.", "Ave": "Ave.",
    "Prof": "Prof.", "Rev": "Rev.", "Gen": "Gen.",
}

# EN-GB: contractions (last letter of full word preserved) drop the period
_EN_GB_ABBREVS_NO_PERIOD = {"Mr.", "Mrs.", "Ms.", "Dr.", "St.", "Jr.", "Sr."}
_EN_GB_ABBREVS_NEED_PERIOD = {
    "Prof": "Prof.", "Rev": "Rev.", "Gen": "Gen.", "Vol": "Vol.",
}

# FR-FR: specific conventions
_FR_ABBREVS_ADD_PERIOD = {"M": "M."}  # Monsieur
_FR_ABBREVS_REMOVE_PERIOD = {"Mme.": "Mme", "Mlle.": "Mlle", "Dr.": "Dr"}

# PT-PT / PT-BR
_PT_ABBREVS = {
    "Sr": "Sr.", "Sra": "Sra.", "Dr": "Dr.", "Dra": "Dra.",
    "Prof": "Prof.", "Eng": "Eng.",
}


# ---------------------------------------------------------------------------
# The Linter
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Strict "never-corrupt" mode
# ---------------------------------------------------------------------------
# Rules whose correction is an *inference* from ambiguous context rather than an
# unambiguous substitution. In strict mode (recommended default for enterprise),
# these are skipped: when a change isn't provably safe, do nothing. The
# unambiguous substitutions (quotes, apostrophes, ellipsis, fractions, legal
# symbols, NFC, zero-width cleanup, diacritics, NBSP) still run.
#
# NOTE (for review): this classification is a typographic judgement call. Move a
# rule out of this set if you consider its inference safe enough to always apply.
_STRICT_SKIP_RULES = frozenset({
    "_rule_dashes",          # " - " -> em/en dash: the hyphen may be intentional
    "_rule_range_dash",      # 10-20 -> en dash: may be a part number, score, etc.
    "_rule_minus_sign",      # -5 -> U+2212: may be a list/bullet hyphen
    "_rule_multiplication",  # 3 x 4 -> 3 × 4: "x" may be a letter
    "_rule_ordinals",        # 1o -> 1º: may not be an ordinal
    "_rule_single_letter_nbsp",  # heuristic NBSP after single-letter words
})


class TypographyLinter:
    """
    Deterministic typographic correction engine.

    Each rule is a method returning (corrected_text, list_of_corrections).
    Rules run in priority order: exclusion masking -> NFC normalization ->
    substitution rules.

    Set ``strict=True`` for a "never-corrupt" posture: inference-based rules
    (see ``_STRICT_SKIP_RULES``) are skipped so output only changes where the
    correction is unambiguous. Recommended default for enterprise/automated use.
    """

    def __init__(
        self,
        language: str = "en-US",
        register: Optional[str] = None,
        strict: bool = False,
    ):
        if language not in SUPPORTED_LANGUAGES:
            raise ValueError(
                f"Unsupported language: {language!r}. "
                f"Supported: {', '.join(sorted(SUPPORTED_LANGUAGES))}"
            )
        self.language = language
        self.register = register
        self.strict = strict

        # Pre-compute quote style for this language
        qs = QUOTE_STYLES[language]
        self._prim_open = qs[0]
        self._prim_close = qs[1]
        self._nest_open = qs[2]
        self._nest_close = qs[3]
        self._prim_space = qs[4]
        self._nest_space = qs[5]

    # ----- Public API -----

    def lint(self, text: str) -> LintResult:
        """Run all deterministic corrections and return a LintResult."""
        original = text
        all_corrections: List[Correction] = []

        # Phase 1: Mask exclusion zones
        masked, placeholders = _mask_exclusions(text)

        # Phase 2: NFC normalization + zero-width character cleanup
        masked, nfc_corrs = self._rule_nfc_normalize(masked)
        all_corrections.extend(nfc_corrs)

        masked, corrs = self._rule_zero_width_chars(masked)
        all_corrections.extend(corrs)

        # Phase 3: Language-specific pre-processing rules
        # (must run before universal quote substitution)
        if self.language == "ro-RO":
            masked, corrs = self._rule_romanian_diacritics(masked)
            all_corrections.extend(corrs)

        if self.language == "fr-FR":
            masked, corrs = self._rule_french_ligatures(masked)
            all_corrections.extend(corrs)
            masked, corrs = self._rule_french_capital_accents(masked)
            all_corrections.extend(corrs)

        # Phase 3b: Homoglyph detection (before general substitution)
        masked, corrs = self._rule_homoglyph_detection(masked)
        all_corrections.extend(corrs)

        # Phase 4: Universal substitution rules (order matters)
        rule_methods = [
            self._rule_ellipsis,
            self._rule_legal_symbols,
            self._rule_fractions,
            self._rule_primes,
            self._rule_quotation_marks,
            self._rule_apostrophe,
            self._rule_dashes,
            self._rule_range_dash,
            self._rule_minus_sign,
            self._rule_multiplication,
            self._rule_double_space,
            self._rule_number_unit_spacing,
        ]

        for method in rule_methods:
            if self.strict and method.__name__ in _STRICT_SKIP_RULES:
                continue
            masked, corrs = method(masked)
            all_corrections.extend(corrs)

        # Phase 4b: Universal structural rules
        masked, corrs = self._rule_nested_parentheticals(masked)
        all_corrections.extend(corrs)

        masked, corrs = self._rule_nbsp_between_initials(masked)
        all_corrections.extend(corrs)

        # Phase 5: Language-specific post-processing rules
        if self.language == "fr-FR":
            masked, corrs = self._rule_french_high_punctuation(masked)
            all_corrections.extend(corrs)

        if self.language.startswith("pt-"):
            masked, corrs = self._rule_abbreviations_pt(masked)
            all_corrections.extend(corrs)
            if not self.strict:
                masked, corrs = self._rule_ordinals(masked)
                all_corrections.extend(corrs)

        if self.language == "en-US":
            masked, corrs = self._rule_abbreviations_en_us(masked)
            all_corrections.extend(corrs)

        if self.language == "en-GB":
            masked, corrs = self._rule_abbreviations_en_gb(masked)
            all_corrections.extend(corrs)

        if self.language == "fr-FR":
            masked, corrs = self._rule_abbreviations_fr(masked)
            all_corrections.extend(corrs)

        if self.language in ("es-ES", "es-MX") and not self.strict:
            masked, corrs = self._rule_ordinals(masked)
            all_corrections.extend(corrs)

        if self.language == "de-DE":
            masked, corrs = self._rule_german_eszett(masked)
            all_corrections.extend(corrs)
            masked, corrs = self._rule_german_din5008(masked)
            all_corrections.extend(corrs)
            masked, corrs = self._rule_ligature_suppression(masked)
            all_corrections.extend(corrs)

        if self.language in ("en-US", "en-GB"):
            masked, corrs = self._rule_ligature_suppression(masked)
            all_corrections.extend(corrs)

        # Phase 5b: NBSP rules (after abbreviation processing)
        masked, corrs = self._rule_nbsp_after_title(masked)
        all_corrections.extend(corrs)

        masked, corrs = self._rule_nbsp_page_abbrev(masked)
        all_corrections.extend(corrs)

        if self.language in _SINGLE_LETTER_WORDS and not self.strict:
            masked, corrs = self._rule_single_letter_nbsp(masked)
            all_corrections.extend(corrs)

        # Phase 5c: Breakable containers (WCAG post-pass on NBSP chains)
        masked, corrs = self._rule_breakable_containers(masked)
        all_corrections.extend(corrs)

        # Phase 6: Abbreviation haplology -- never double period at end
        masked, corrs = self._rule_abbreviation_haplology(masked)
        all_corrections.extend(corrs)

        # Phase 7: Unmask exclusion zones
        result_text = _unmask_exclusions(masked, placeholders)

        # Recalculate positions based on final text
        # (positions in corrections are relative to the masked text; after
        # unmasking they may shift -- but for practical purposes, the position
        # field gives a useful approximation of where in the text the change was)

        return LintResult(
            text=result_text,
            original=original,
            language=self.language,
            register=self.register,
            corrections=all_corrections,
        )

    # ----- NFC Normalization -----

    def _rule_nfc_normalize(self, text: str) -> Tuple[str, List[Correction]]:
        """Apply NFC normalization (Batch 1 requirement)."""
        normalized = unicodedata.normalize("NFC", text)
        corrections: List[Correction] = []
        if normalized != text:
            corrections.append(Correction(
                position=0,
                original="(composite characters)",
                replacement="(NFC-normalized)",
                rule="nfc_normalization",
                description="Applied Unicode NFC normalization",
            ))
        return normalized, corrections

    # ----- Ellipsis -----

    def _rule_ellipsis(self, text: str) -> Tuple[str, List[Correction]]:
        """Three periods -> ellipsis character (U+2026)."""
        corrections: List[Correction] = []
        pattern = re.compile(r"\.{3}")
        offset = 0
        result = []
        last_end = 0

        for m in pattern.finditer(text):
            result.append(text[last_end:m.start()])
            corrections.append(Correction(
                position=m.start() - offset,
                original="...",
                replacement="\u2026",
                rule="ellipsis",
                description="Three periods replaced with ellipsis character (U+2026)",
            ))
            result.append("\u2026")
            offset += 2  # 3 chars -> 1 char
            last_end = m.end()

        result.append(text[last_end:])
        return "".join(result), corrections

    # ----- Legal symbols -----

    def _rule_legal_symbols(self, text: str) -> Tuple[str, List[Correction]]:
        """(c) -> copyright, (r) -> registered, (tm) -> trademark."""
        corrections: List[Correction] = []
        replacements = [
            (re.compile(r"\(c\)", re.IGNORECASE), "\u00A9", "copyright_sign", "Replaced (c) with copyright sign \u00A9"),
            (re.compile(r"\(r\)", re.IGNORECASE), "\u00AE", "registered_sign", "Replaced (r) with registered sign \u00AE"),
            (re.compile(r"\(tm\)", re.IGNORECASE), "\u2122", "trademark_sign", "Replaced (tm) with trademark sign \u2122"),
        ]

        for pat, repl, rule, desc in replacements:
            new_text = ""
            last_end = 0
            for m in pat.finditer(text):
                new_text += text[last_end:m.start()]
                corrections.append(Correction(
                    position=m.start(),
                    original=m.group(),
                    replacement=repl,
                    rule=rule,
                    description=desc,
                ))
                new_text += repl
                last_end = m.end()
            new_text += text[last_end:]
            text = new_text

        return text, corrections

    # ----- Fractions -----

    def _rule_fractions(self, text: str) -> Tuple[str, List[Correction]]:
        """Common fractions -> Unicode fraction characters."""
        corrections: List[Correction] = []

        def _repl(m: re.Match) -> str:
            frac = m.group(1)
            replacement = _FRACTIONS[frac]
            corrections.append(Correction(
                position=m.start(),
                original=frac,
                replacement=replacement,
                rule="fractions",
                description=f"Replaced {frac} with Unicode fraction {replacement}",
            ))
            return replacement

        result = _FRACTION_PATTERN.sub(_repl, text)
        return result, corrections

    # ----- Primes (measurements) -----

    def _rule_primes(self, text: str) -> Tuple[str, List[Correction]]:
        """Straight quotes after numbers -> prime/double-prime for measurements.
        Handles patterns like: 5'10" (feet/inches), 45'30" (degrees/minutes).
        """
        corrections: List[Correction] = []

        # Pattern: number + ' + optional(number + ")
        # e.g., 5'10", 6', 45'30"
        prime_pat = re.compile(
            r"""(\d+)'(\d+)(?:"|'')?"""  # 5'10" or 5'10
            r"|"
            r"""(\d+)'(?=\s|$|[,;:.!?\)\]\}])"""  # 5' standalone
            r"|"
            r"""(\d+)"(?=\s|$|[,;:.!?\)\]\}])"""  # 10" standalone
        )

        result = []
        last_end = 0

        for m in prime_pat.finditer(text):
            result.append(text[last_end:m.start()])

            if m.group(1) is not None and m.group(2) is not None:
                # Full pattern: 5'10" -> 5 prime 10 double-prime
                orig = m.group(0)
                replacement = f"{m.group(1)}\u2032{m.group(2)}\u2033"
                corrections.append(Correction(
                    position=m.start(),
                    original=orig,
                    replacement=replacement,
                    rule="primes",
                    description=f"Straight quotes replaced with prime/double-prime marks",
                ))
                result.append(replacement)
            elif m.group(3) is not None:
                # Single prime: 5'
                orig = m.group(0)
                replacement = f"{m.group(3)}\u2032"
                corrections.append(Correction(
                    position=m.start(),
                    original=orig,
                    replacement=replacement,
                    rule="primes",
                    description="Straight apostrophe replaced with prime mark (\u2032)",
                ))
                result.append(replacement)
            elif m.group(4) is not None:
                # Double prime: 10"
                orig = m.group(0)
                replacement = f"{m.group(4)}\u2033"
                corrections.append(Correction(
                    position=m.start(),
                    original=orig,
                    replacement=replacement,
                    rule="primes",
                    description="Straight double quote replaced with double-prime mark (\u2033)",
                ))
                result.append(replacement)

            last_end = m.end()

        result.append(text[last_end:])
        return "".join(result), corrections

    # ----- Quotation marks -----

    def _rule_quotation_marks(self, text: str) -> Tuple[str, List[Correction]]:
        """Replace straight quotes with language-appropriate typographic quotes.

        Handles both double (U+0022) and single (U+0027) straight quotes.
        For languages with guillemet primaries (pt-PT, fr-FR, etc.) or curly-double
        primaries (en-US, de-DE etc.), processes double quotes.
        For languages with single-quote primaries (en-GB), processes single quotes.

        Strategy: alternating open/close toggle through the text.
        """
        corrections: List[Correction] = []
        result = list(text)
        ps = self._prim_space

        # Determine which straight quote character maps to the primary
        # en-GB uses single quotes as primary; all others use double quotes
        uses_single_primary = self.language in ("en-GB",)

        if not uses_single_primary:
            # Process double quotes -> primary quotes
            double_positions = [i for i, ch in enumerate(result) if ch == '"']
            is_open = True
            for pos in double_positions:
                if is_open:
                    repl = self._prim_open + ps
                    corrections.append(Correction(
                        position=pos,
                        original='"',
                        replacement=repl,
                        rule="quotation_marks",
                        description=f"Opening straight double quote replaced with {repr(repl)}",
                    ))
                    result[pos] = repl
                    is_open = False
                else:
                    repl = ps + self._prim_close
                    corrections.append(Correction(
                        position=pos,
                        original='"',
                        replacement=repl,
                        rule="quotation_marks",
                        description=f"Closing straight double quote replaced with {repr(repl)}",
                    ))
                    result[pos] = repl
                    is_open = True
        else:
            # Process single quotes -> primary quotes (en-GB pattern)
            # We must distinguish quotation singles from apostrophes.
            # Opening: straight ' preceded by space, punctuation, or start-of-string
            # Closing: straight ' followed by space, punctuation, or end-of-string
            # Apostrophe: straight ' between two word characters (handled by _rule_apostrophe)
            i = 0
            in_quote = False
            text_list = result  # alias for readability
            while i < len(text_list):
                ch = text_list[i]
                if ch == "'":
                    prev = text_list[i - 1] if i > 0 else None
                    nxt = text_list[i + 1] if i + 1 < len(text_list) else None
                    prev_is_word = prev is not None and (prev.isalpha() or prev.isdigit())
                    next_is_word = nxt is not None and (nxt.isalpha() or nxt.isdigit())

                    if prev_is_word and next_is_word:
                        # Apostrophe -- leave for _rule_apostrophe
                        i += 1
                        continue

                    if not in_quote and not prev_is_word:
                        # Opening quote
                        repl = self._prim_open + ps
                        corrections.append(Correction(
                            position=i,
                            original="'",
                            replacement=repl,
                            rule="quotation_marks",
                            description=f"Opening straight single quote replaced with {repr(repl)}",
                        ))
                        text_list[i] = repl
                        in_quote = True
                    elif in_quote and not next_is_word:
                        # Closing quote
                        repl = ps + self._prim_close
                        corrections.append(Correction(
                            position=i,
                            original="'",
                            replacement=repl,
                            rule="quotation_marks",
                            description=f"Closing straight single quote replaced with {repr(repl)}",
                        ))
                        text_list[i] = repl
                        in_quote = False
                i += 1

        return "".join(result), corrections

    # ----- Apostrophe -----

    def _rule_apostrophe(self, text: str) -> Tuple[str, List[Correction]]:
        """Straight apostrophe -> typographic apostrophe (U+2019).

        We target the common contraction/possessive patterns:
        word'word, word's, n't, 'tis, etc.
        """
        corrections: List[Correction] = []

        # Pattern: letter + ' + letter (contraction/possessive)
        # Also: 's at end, n't, 'd, 'll, 're, 've, 'm
        apo_pat = re.compile(r"(?<=\w)'(?=\w)|(?<=\w)'(?=s\b)|(?<=n)'(?=t\b)")

        def _repl(m: re.Match) -> str:
            corrections.append(Correction(
                position=m.start(),
                original="'",
                replacement="\u2019",
                rule="apostrophe",
                description="Straight apostrophe replaced with typographic apostrophe (\u2019)",
            ))
            return "\u2019"

        result = apo_pat.sub(_repl, text)
        return result, corrections

    # ----- Range dash -----

    def _rule_range_dash(self, text: str) -> Tuple[str, List[Correction]]:
        """Hyphen in number ranges -> en dash (U+2013).

        Patterns: 10-20, 2020-2025, pp. 10-20, pages 10-20

        Only a *tight* (space-free) hyphen between two numbers is treated as a
        range. A spaced hyphen ("10 - 3") is intentionally left alone: it is
        ambiguous with subtraction, and silently turning "10 - 3 = 7" into
        "10-3 = 7" is a corruption bug. Precision over recall — when in doubt,
        do nothing.
        """
        corrections: List[Correction] = []

        # number-hyphen-number, tight only (not preceded by another hyphen or letter)
        range_pat = re.compile(r"(?<![a-zA-Z\-])(\d+)-(\d+)(?![a-zA-Z\-])")

        def _repl(m: re.Match) -> str:
            orig = m.group(0)
            replacement = f"{m.group(1)}\u2013{m.group(2)}"
            corrections.append(Correction(
                position=m.start(),
                original=orig,
                replacement=replacement,
                rule="range_dash",
                description="Hyphen in number range replaced with en dash (\u2013)",
            ))
            return replacement

        result = range_pat.sub(_repl, text)
        return result, corrections

    # ----- Minus sign -----

    def _rule_minus_sign(self, text: str) -> Tuple[str, List[Correction]]:
        """Hyphen before number (negative) -> minus sign (U+2212).

        Pattern: space/start-of-string + hyphen + digit (negative number context).
        Also: digit + space + hyphen + space + digit (subtraction).
        """
        corrections: List[Correction] = []

        # Negative number: preceded by space, open paren, or start of string
        neg_pat = re.compile(r"(?<=[\s(=:,])-(?=\d)")

        def _repl_neg(m: re.Match) -> str:
            corrections.append(Correction(
                position=m.start(),
                original="-",
                replacement="\u2212",
                rule="minus_sign",
                description="Hyphen in negative number replaced with minus sign (\u2212)",
            ))
            return "\u2212"

        result = neg_pat.sub(_repl_neg, text)

        # Also handle start-of-string negative
        if result.startswith("-") and len(result) > 1 and result[1].isdigit():
            corrections.append(Correction(
                position=0,
                original="-",
                replacement="\u2212",
                rule="minus_sign",
                description="Hyphen in negative number replaced with minus sign (\u2212)",
            ))
            result = "\u2212" + result[1:]

        # Subtraction: digit space hyphen space digit
        sub_pat = re.compile(r"(\d) - (\d)")

        def _repl_sub(m: re.Match) -> str:
            corrections.append(Correction(
                position=m.start(),
                original=m.group(0),
                replacement=f"{m.group(1)} \u2212 {m.group(2)}",
                rule="minus_sign",
                description="Hyphen in subtraction replaced with minus sign (\u2212)",
            ))
            return f"{m.group(1)} \u2212 {m.group(2)}"

        result = sub_pat.sub(_repl_sub, result)
        return result, corrections

    # ----- Multiplication -----

    def _rule_multiplication(self, text: str) -> Tuple[str, List[Correction]]:
        """Letter x between numbers -> multiplication sign (U+00D7).

        Patterns: 3x4, 1920x1080, 3 x 4
        """
        corrections: List[Correction] = []

        # number + optional_space + x + optional_space + number
        mul_pat = re.compile(r"(\d)\s?[xX]\s?(\d)")

        def _repl(m: re.Match) -> str:
            orig = m.group(0)
            # Schema says thin_both spacing for dimensions
            replacement = f"{m.group(1)}\u2009\u00D7\u2009{m.group(2)}"
            corrections.append(Correction(
                position=m.start(),
                original=orig,
                replacement=replacement,
                rule="multiplication_sign",
                description="Letter x between numbers replaced with multiplication sign (\u00D7)",
            ))
            return replacement

        result = mul_pat.sub(_repl, text)
        return result, corrections

    # ----- Double space -----

    def _rule_double_space(self, text: str) -> Tuple[str, List[Correction]]:
        """Double space after punctuation -> single space."""
        corrections: List[Correction] = []
        pattern = re.compile(r"([.!?;:,])  +")

        def _repl(m: re.Match) -> str:
            corrections.append(Correction(
                position=m.start(),
                original=m.group(0),
                replacement=m.group(1) + " ",
                rule="double_space",
                description="Double space after punctuation reduced to single space",
            ))
            return m.group(1) + " "

        result = pattern.sub(_repl, text)
        return result, corrections

    # ----- Number-unit spacing -----

    def _rule_number_unit_spacing(self, text: str) -> Tuple[str, List[Correction]]:
        """Add NBSP between number and unit: 10kg -> 10 kg."""
        corrections: List[Correction] = []
        lang = self.language

        # Determine spacing character
        if lang in _NNBSP_UNIT_LANGS:
            space_char = NNBSP
        elif lang in _NBSP_UNIT_LANGS:
            space_char = NBSP
        else:
            space_char = NBSP  # English also uses NBSP to prevent line break

        def _repl(m: re.Match) -> str:
            orig = m.group(0)
            replacement = m.group(1) + space_char + m.group(2)
            corrections.append(Correction(
                position=m.start(),
                original=orig,
                replacement=replacement,
                rule="number_unit_spacing",
                description=f"Added non-breaking space between number and unit ({m.group(2)})",
            ))
            return replacement

        result = _UNIT_PATTERN.sub(_repl, text)
        return result, corrections

    # ----- French high punctuation spacing -----

    def _rule_french_high_punctuation(self, text: str) -> Tuple[str, List[Correction]]:
        """Insert NNBSP before : ; ! ? in French text.

        Rules:
        - If there is no space before the punctuation, insert NNBSP
        - If there is a regular space, replace with NNBSP
        - If there is already NNBSP, leave it
        """
        corrections: List[Correction] = []
        result = text
        new_corrections: List[Correction] = []

        for punct in [";", "!", "?"]:
            new_result = []
            i = 0
            while i < len(result):
                if result[i] == punct and i > 0:
                    # Check what precedes
                    prev = result[i - 1]
                    if prev == NNBSP:
                        new_result.append(result[i])
                        i += 1
                        continue
                    if prev in (" ", NBSP, THIN):
                        # Replace the space with NNBSP
                        new_result[-1] = NNBSP
                        new_corrections.append(Correction(
                            position=i - 1,
                            original=prev + punct,
                            replacement=NNBSP + punct,
                            rule="french_high_punctuation",
                            description=f"Replaced space with NNBSP before {punct!r}",
                        ))
                        new_result.append(result[i])
                    elif prev not in ("\n", "\r", "\t") and prev != NNBSP:
                        # Insert NNBSP
                        new_corrections.append(Correction(
                            position=i,
                            original=punct,
                            replacement=NNBSP + punct,
                            rule="french_high_punctuation",
                            description=f"Inserted NNBSP (U+202F) before {punct!r}",
                        ))
                        new_result.append(NNBSP)
                        new_result.append(result[i])
                    else:
                        new_result.append(result[i])
                else:
                    new_result.append(result[i])
                i += 1
            result = "".join(new_result)

        # Handle colon separately -- must not trigger on URL schemes
        colon_result = []
        i = 0
        while i < len(result):
            if result[i] == ":" and i > 0:
                # Check it is not part of a URL scheme (http:// etc.)
                # Check ahead for //
                after = result[i + 1:i + 3] if i + 2 < len(result) else ""
                if after.startswith("//") or after.startswith("\\"):
                    colon_result.append(result[i])
                    i += 1
                    continue

                prev = result[i - 1]
                if prev == NNBSP:
                    colon_result.append(result[i])
                    i += 1
                    continue
                if prev in (" ", NBSP, THIN):
                    colon_result[-1] = NNBSP
                    new_corrections.append(Correction(
                        position=i - 1,
                        original=prev + ":",
                        replacement=NNBSP + ":",
                        rule="french_high_punctuation",
                        description="Replaced space with NNBSP before colon",
                    ))
                    colon_result.append(result[i])
                elif prev not in ("\n", "\r", "\t") and prev != NNBSP:
                    new_corrections.append(Correction(
                        position=i,
                        original=":",
                        replacement=NNBSP + ":",
                        rule="french_high_punctuation",
                        description="Inserted NNBSP (U+202F) before colon",
                    ))
                    colon_result.append(NNBSP)
                    colon_result.append(result[i])
                else:
                    colon_result.append(result[i])
            else:
                colon_result.append(result[i])
            i += 1

        result = "".join(colon_result)
        return result, new_corrections

    # ----- French orthographic ligatures -----

    def _rule_french_ligatures(self, text: str) -> Tuple[str, List[Correction]]:
        """Replace decomposed oe/ae with proper French ligatures."""
        corrections: List[Correction] = []

        for wrong, right in _FR_OE_WORDS:
            # Case-insensitive word boundary search
            pat = re.compile(r"\b" + re.escape(wrong) + r"\b", re.IGNORECASE)
            for m in pat.finditer(text):
                matched = m.group()
                # Preserve original casing as much as possible
                if matched[0].isupper():
                    replacement = right[0].upper() + right[1:]
                else:
                    replacement = right
                if matched != replacement:
                    corrections.append(Correction(
                        position=m.start(),
                        original=matched,
                        replacement=replacement,
                        rule="french_ligatures",
                        description=f"Decomposed oe/ae replaced with French ligature: {matched} -> {replacement}",
                    ))
            text = pat.sub(lambda m: (right[0].upper() + right[1:]) if m.group()[0].isupper() else right, text)

        return text, corrections

    # ----- Romanian diacritics -----

    def _rule_romanian_diacritics(self, text: str) -> Tuple[str, List[Correction]]:
        """Replace cedilla forms with comma-below forms for Romanian."""
        corrections: List[Correction] = []
        result = list(text)

        for i, ch in enumerate(result):
            if ch in _RO_CEDILLA_MAP:
                replacement = _RO_CEDILLA_MAP[ch]
                corrections.append(Correction(
                    position=i,
                    original=ch,
                    replacement=replacement,
                    rule="romanian_diacritics",
                    description=f"Cedilla form {ch!r} (U+{ord(ch):04X}) replaced with comma-below {replacement!r} (U+{ord(replacement):04X})",
                ))
                result[i] = replacement

        return "".join(result), corrections

    # ----- German eszett capitalisation -----

    def _rule_german_eszett(self, text: str) -> Tuple[str, List[Correction]]:
        """STRASSE -> STRAẞE when in all-caps German words containing SS."""
        corrections: List[Correction] = []

        # Common German words where SS should become ẞ in all-caps
        # We look for all-caps words containing SS that are known eszett words
        _eszett_words = {
            "STRASSE": "STRA\u1E9EE",
            "GROSSE": "GRO\u1E9EE",
            "GROSSER": "GRO\u1E9EER",
            "GROSSES": "GRO\u1E9EES",
            "GROSSEN": "GRO\u1E9EEN",
            "SCHLIESSEN": "SCHLIE\u1E9EEN",
            "GIESSEN": "GIE\u1E9EEN",
            "FUSSBALL": "FU\u1E9EBALL",
            "SPASS": "SPA\u1E9E",
            "MASSE": "MA\u1E9EE",
            "MASSEN": "MA\u1E9EEN",
            "HEISS": "HEI\u1E9E",
            "HEISSE": "HEI\u1E9EE",
            "WEISS": "WEI\u1E9E",
            "WEISSE": "WEI\u1E9EE",
            "DRAUSSEN": "DRAU\u1E9EEN",
            "AUSSEN": "AU\u1E9EEN",
            "GRUSS": "GRU\u1E9E",
            "GRUSSE": "GR\u00DC\u1E9EE",
            "FLIESSEN": "FLIE\u1E9EEN",
            "REISSEN": "REI\u1E9EEN",
            "WISSEN": "WISSEN",  # this is NOT an eszett word -- double s
        }

        for wrong, right in _eszett_words.items():
            if wrong == right:
                continue
            pat = re.compile(r"\b" + re.escape(wrong) + r"\b")
            for m in pat.finditer(text):
                corrections.append(Correction(
                    position=m.start(),
                    original=wrong,
                    replacement=right,
                    rule="german_eszett",
                    description=f"SS in all-caps word replaced with capital sharp s (\u1E9E): {wrong} -> {right}",
                ))
            text = pat.sub(right, text)

        return text, corrections

    # ----- Homoglyph detection -----

    def _rule_homoglyph_detection(self, text: str) -> Tuple[str, List[Correction]]:
        """Detect and fix common homoglyph confusions.

        - Masculine ordinal indicator (U+00BA) -> degree sign (U+00B0) in temperature/angle context
        - Add space before degree+unit if missing (20ºC -> 20 °C)
        - Greek beta (U+03B2) -> eszett (U+00DF) in German text
        """
        corrections: List[Correction] = []

        # 1. Masculine ordinal º (U+00BA) -> degree sign ° (U+00B0) before C/F/K or angle context
        # Also handles adding a space between number and °C/°F
        temp_pat = re.compile(r"(\d)\u00BA([CFK])\b")
        def _repl_temp(m: re.Match) -> str:
            orig = m.group(0)
            replacement = f"{m.group(1)}\u00A0\u00B0{m.group(2)}"
            corrections.append(Correction(
                position=m.start(),
                original=orig,
                replacement=replacement,
                rule="homoglyph_detection",
                description=f"Masculine ordinal indicator (U+00BA) replaced with degree sign (U+00B0) and added space before °{m.group(2)}",
            ))
            return replacement
        text = temp_pat.sub(_repl_temp, text)

        # Also handle: number + degree sign but missing space (20°C -> 20 °C)
        deg_nospace_pat = re.compile(r"(\d)\u00B0([CFK])\b")
        def _repl_deg_nospace(m: re.Match) -> str:
            orig = m.group(0)
            replacement = f"{m.group(1)}\u00A0\u00B0{m.group(2)}"
            corrections.append(Correction(
                position=m.start(),
                original=orig,
                replacement=replacement,
                rule="homoglyph_detection",
                description=f"Added non-breaking space before °{m.group(2)}",
            ))
            return replacement
        text = deg_nospace_pat.sub(_repl_deg_nospace, text)

        # Standalone º -> ° when preceded by a digit (general angle/degree context)
        standalone_ord_pat = re.compile(r"(\d)\u00BA(?![a-zA-Z])")
        def _repl_standalone(m: re.Match) -> str:
            orig = m.group(0)
            replacement = f"{m.group(1)}\u00B0"
            corrections.append(Correction(
                position=m.start(),
                original=orig,
                replacement=replacement,
                rule="homoglyph_detection",
                description="Masculine ordinal indicator (U+00BA) replaced with degree sign (U+00B0)",
            ))
            return replacement
        text = standalone_ord_pat.sub(_repl_standalone, text)

        # 2. Greek beta -> eszett in German text
        if self.language == "de-DE":
            beta_pat = re.compile(r"\u03B2")
            def _repl_beta(m: re.Match) -> str:
                corrections.append(Correction(
                    position=m.start(),
                    original="\u03B2",
                    replacement="\u00DF",
                    rule="homoglyph_detection",
                    description="Greek beta (\u03B2) replaced with German eszett (\u00DF)",
                ))
                return "\u00DF"
            text = beta_pat.sub(_repl_beta, text)

        return text, corrections

    # ----- German DIN 5008 abbreviation spacing -----

    def _rule_german_din5008(self, text: str) -> Tuple[str, List[Correction]]:
        """Insert NNBSP between parts of German multi-part abbreviations per DIN 5008.

        z.B. -> z. B., d.h. -> d. h., i.d.R. -> i. d. R., etc.
        """
        corrections: List[Correction] = []

        for wrong, right in _DE_DIN5008_ABBREVS:
            pat = re.compile(re.escape(wrong))
            for m in pat.finditer(text):
                corrections.append(Correction(
                    position=m.start(),
                    original=wrong,
                    replacement=right,
                    rule="german_din5008_spacing",
                    description=f"DIN 5008 abbreviation spacing: {wrong} -> {right}",
                ))
            text = pat.sub(right, text)

        # General pattern: single lowercase letter + period + letter + period with no space
        # Catches remaining cases not in the explicit list
        general_pat = re.compile(r"\b([a-zäöü])\.([a-zA-ZäöüÄÖÜ])\.")
        def _repl_general(m: re.Match) -> str:
            orig = m.group(0)
            # Check we haven't already fixed this (NNBSP present)
            replacement = f"{m.group(1)}.\u202F{m.group(2)}."
            if orig != replacement:
                corrections.append(Correction(
                    position=m.start(),
                    original=orig,
                    replacement=replacement,
                    rule="german_din5008_spacing",
                    description=f"DIN 5008: inserted NNBSP in abbreviation {orig} -> {replacement}",
                ))
            return replacement
        text = general_pat.sub(_repl_general, text)

        return text, corrections

    # ----- NBSP between initials -----

    def _rule_nbsp_between_initials(self, text: str) -> Tuple[str, List[Correction]]:
        """Insert NBSP between initials: J.R.R. -> J.\u00A0R.\u00A0R.

        Pattern: uppercase letter + period immediately followed by uppercase letter + period.
        """
        corrections: List[Correction] = []

        # Match sequences of initials (A.B. or A.B.C. etc.)
        # We do iterative replacement since each pass may reveal new adjacency
        changed = True
        while changed:
            pat = re.compile(r"([A-Z]\.)([A-Z]\.)")
            m = pat.search(text)
            if m:
                orig = m.group(0)
                replacement = f"{m.group(1)}\u00A0{m.group(2)}"
                corrections.append(Correction(
                    position=m.start(),
                    original=orig,
                    replacement=replacement,
                    rule="nbsp_between_initials",
                    description=f"Inserted NBSP between initials: {orig} -> {replacement}",
                ))
                text = text[:m.start()] + replacement + text[m.end():]
            else:
                changed = False

        return text, corrections

    # ----- NBSP after title abbreviations -----

    def _rule_nbsp_after_title(self, text: str) -> Tuple[str, List[Correction]]:
        """Insert NBSP after title abbreviations before a capitalized name.

        Mr. Smith -> Mr.\u00A0Smith (prevents line break between title and name).
        """
        corrections: List[Correction] = []

        titles = list(_TITLE_ABBREVS_UNIVERSAL)
        lang_titles = _TITLE_ABBREVS_BY_LANG.get(self.language, [])
        titles.extend(lang_titles)

        # Sort by length descending to match longer abbreviations first
        titles.sort(key=len, reverse=True)

        for title in titles:
            # Match title + regular space + capitalized word
            escaped = re.escape(title)
            pat = re.compile(escaped + r" (?=[A-Z\u00C0-\u024F])")
            for m in pat.finditer(text):
                orig = m.group(0)
                replacement = title + NBSP
                corrections.append(Correction(
                    position=m.start(),
                    original=orig,
                    replacement=replacement,
                    rule="nbsp_after_title",
                    description=f"Replaced space with NBSP after title abbreviation {title!r}",
                ))
            text = pat.sub(title + NBSP, text)

        return text, corrections

    # ----- Single-letter word NBSP (anti-orphan) -----

    def _rule_single_letter_nbsp(self, text: str) -> Tuple[str, List[Correction]]:
        """Replace space after single-letter words with NBSP to prevent orphans.

        Language-specific: fr-FR, es-ES, es-MX, it-IT, pt-PT, pt-BR.
        """
        corrections: List[Correction] = []

        words = _SINGLE_LETTER_WORDS.get(self.language, [])
        if not words:
            return text, corrections

        for word in words:
            # Match the single letter as a standalone word followed by a regular space
            # Use lookbehind for start-of-string or space/punctuation
            escaped = re.escape(word)
            # Case-sensitive for lowercase, but also handle uppercase at sentence start
            pat = re.compile(
                r"(?:(?<=\s)|(?<=^)|(?<=[\u2014\u2013\u2012\(\[\{\"'\u00AB\u201C\u201E\u2018\u2039]))"
                + escaped
                + r" (?=\S)",
                re.MULTILINE,
            )
            for m in pat.finditer(text):
                orig = m.group(0)
                replacement = word + NBSP
                corrections.append(Correction(
                    position=m.start(),
                    original=orig,
                    replacement=replacement,
                    rule="single_letter_nbsp",
                    description=f"Replaced space after single-letter word {word!r} with NBSP to prevent orphan",
                ))
            text = pat.sub(word + NBSP, text)

            # Handle uppercase variant (sentence start)
            upper_word = word.upper()
            if upper_word != word:
                pat_upper = re.compile(
                    r"(?:(?<=\s)|(?<=^)|(?<=[\u2014\u2013\u2012\(\[\{\"'\u00AB\u201C\u201E\u2018\u2039]))"
                    + re.escape(upper_word)
                    + r" (?=\S)",
                    re.MULTILINE,
                )
                for m in pat_upper.finditer(text):
                    orig = m.group(0)
                    replacement = upper_word + NBSP
                    corrections.append(Correction(
                        position=m.start(),
                        original=orig,
                        replacement=replacement,
                        rule="single_letter_nbsp",
                        description=f"Replaced space after single-letter word {upper_word!r} with NBSP to prevent orphan",
                    ))
                text = pat_upper.sub(upper_word + NBSP, text)

        return text, corrections

    # ----- Nested parentheticals -----

    def _rule_nested_parentheticals(self, text: str) -> Tuple[str, List[Correction]]:
        """Convert inner parentheses to square brackets when nested.

        ((like (this))) -> ([like [this]])
        """
        corrections: List[Correction] = []
        result = list(text)
        depth = 0

        for i, ch in enumerate(result):
            if ch == "(":
                depth += 1
                if depth > 1:
                    corrections.append(Correction(
                        position=i,
                        original="(",
                        replacement="[",
                        rule="nested_parentheticals",
                        description="Inner opening parenthesis converted to square bracket",
                    ))
                    result[i] = "["
            elif ch == ")":
                if depth > 1:
                    corrections.append(Correction(
                        position=i,
                        original=")",
                        replacement="]",
                        rule="nested_parentheticals",
                        description="Inner closing parenthesis converted to square bracket",
                    ))
                    result[i] = "]"
                depth = max(0, depth - 1)

        return "".join(result), corrections

    # ----- Abbreviation rules -----

    def _rule_abbreviations_en_us(self, text: str) -> Tuple[str, List[Correction]]:
        """EN-US: all abbreviations take a period (Mr -> Mr.)."""
        corrections: List[Correction] = []

        for abbr, with_period in _EN_US_ABBREVS.items():
            # Match abbreviation without period, followed by space + capital letter
            pat = re.compile(r"\b" + re.escape(abbr) + r"(?!\.)(?=\s+[A-Z\u00C0-\u024F])")
            for m in pat.finditer(text):
                corrections.append(Correction(
                    position=m.start(),
                    original=abbr,
                    replacement=with_period,
                    rule="abbreviation_periods",
                    description=f"EN-US abbreviation: {abbr} -> {with_period}",
                ))
            text = pat.sub(with_period, text)

        return text, corrections

    def _rule_abbreviations_en_gb(self, text: str) -> Tuple[str, List[Correction]]:
        """EN-GB: contractions drop the period; true truncations keep it."""
        corrections: List[Correction] = []

        # Remove period from contractions (Mr. -> Mr, Dr. -> Dr, etc.)
        for with_period in _EN_GB_ABBREVS_NO_PERIOD:
            without = with_period.rstrip(".")
            pat = re.compile(r"\b" + re.escape(with_period) + r"(?=\s+[A-Z\u00C0-\u024F])")
            for m in pat.finditer(text):
                corrections.append(Correction(
                    position=m.start(),
                    original=with_period,
                    replacement=without,
                    rule="abbreviation_periods",
                    description=f"EN-GB contraction: {with_period} -> {without} (last letter preserved, no period)",
                ))
            text = pat.sub(without, text)

        # Add period to truncations (Prof -> Prof., Rev -> Rev.)
        for abbr, with_period in _EN_GB_ABBREVS_NEED_PERIOD.items():
            pat = re.compile(r"\b" + re.escape(abbr) + r"(?!\.)(?=\s+[A-Z\u00C0-\u024F])")
            for m in pat.finditer(text):
                corrections.append(Correction(
                    position=m.start(),
                    original=abbr,
                    replacement=with_period,
                    rule="abbreviation_periods",
                    description=f"EN-GB truncation: {abbr} -> {with_period}",
                ))
            text = pat.sub(with_period, text)

        return text, corrections

    def _rule_abbreviations_fr(self, text: str) -> Tuple[str, List[Correction]]:
        """FR-FR: M -> M., but Mme. -> Mme, Dr. -> Dr."""
        corrections: List[Correction] = []

        # Add period to M (Monsieur)
        for abbr, with_period in _FR_ABBREVS_ADD_PERIOD.items():
            pat = re.compile(r"\b" + re.escape(abbr) + r"(?!\.)(?=\s+[A-Z\u00C0-\u024F])")
            for m in pat.finditer(text):
                corrections.append(Correction(
                    position=m.start(),
                    original=abbr,
                    replacement=with_period,
                    rule="abbreviation_periods",
                    description=f"FR abbreviation: {abbr} -> {with_period}",
                ))
            text = pat.sub(with_period, text)

        # Remove period from contractions
        for with_period, without in _FR_ABBREVS_REMOVE_PERIOD.items():
            pat = re.compile(r"\b" + re.escape(with_period) + r"(?=\s)")
            for m in pat.finditer(text):
                corrections.append(Correction(
                    position=m.start(),
                    original=with_period,
                    replacement=without,
                    rule="abbreviation_periods",
                    description=f"FR contraction: {with_period} -> {without} (no period when last letter preserved)",
                ))
            text = pat.sub(without, text)

        return text, corrections

    def _rule_abbreviations_pt(self, text: str) -> Tuple[str, List[Correction]]:
        """PT-PT/PT-BR: abbreviations take a period (Sr -> Sr., Dr -> Dr.)."""
        corrections: List[Correction] = []

        for abbr, with_period in _PT_ABBREVS.items():
            pat = re.compile(r"\b" + re.escape(abbr) + r"(?!\.)(?=\s+[A-Z\u00C0-\u024F])")
            for m in pat.finditer(text):
                corrections.append(Correction(
                    position=m.start(),
                    original=abbr,
                    replacement=with_period,
                    rule="abbreviation_periods",
                    description=f"PT abbreviation: {abbr} -> {with_period}",
                ))
            text = pat.sub(with_period, text)

        return text, corrections

    # ----- Zero-width character handling -----

    def _rule_zero_width_chars(self, text: str) -> Tuple[str, List[Correction]]:
        """Strip ZWSP (U+200B) from prose; replace with space when between letters.

        Preserve ZWNJ (U+200C, ligature suppression) and ZWJ (U+200D, emoji).
        Also strip stray mid-text BOM (U+FEFF).
        """
        corrections: List[Correction] = []
        result = []
        i = 0
        while i < len(text):
            ch = text[i]
            if ch == "\u200B":  # ZWSP
                # Context-aware: if between two letter chars, insert a space
                prev_is_letter = i > 0 and text[i - 1].isalpha()
                next_is_letter = i + 1 < len(text) and text[i + 1].isalpha()
                if prev_is_letter and next_is_letter:
                    replacement = " "
                    desc = "ZWSP between letters replaced with space"
                else:
                    replacement = ""
                    desc = "Stray ZWSP stripped from text"
                corrections.append(Correction(
                    position=i,
                    original="\u200B",
                    replacement=replacement,
                    rule="zero_width_chars",
                    description=desc,
                ))
                result.append(replacement)
            elif ch == "\uFEFF" and i > 0:  # mid-text BOM (not at start)
                corrections.append(Correction(
                    position=i,
                    original="\uFEFF",
                    replacement="",
                    rule="zero_width_chars",
                    description="Stray BOM (U+FEFF) stripped from mid-text",
                ))
            else:
                result.append(ch)
            i += 1
        return "".join(result), corrections

    # ----- Dash rules (language-specific) -----

    def _rule_dashes(self, text: str) -> Tuple[str, List[Correction]]:
        """Convert space-hyphen-space to em dash (en-US) or spaced en dash (en-GB).

        This handles parenthetical dashes in prose, e.g.:
          en-US: "The project - a big one - succeeded." -> "...—a big one—..."
          en-GB: "The project - a big one - succeeded." -> "... – a big one – ..."
        """
        corrections: List[Correction] = []

        # Only apply for languages with a defined dash convention
        if self.language == "en-US":
            # Em dash, no spaces
            dash_pat = re.compile(r'(?<=[^\-\d]) - (?=[^\-\d])')
            replacement = "\u2014"
            def _repl(m: re.Match) -> str:
                corrections.append(Correction(
                    position=m.start(),
                    original=" - ",
                    replacement=replacement,
                    rule="em_dash",
                    description="Space-hyphen-space replaced with em dash (no spaces) for EN-US",
                ))
                return replacement

        elif self.language == "en-GB":
            # En dash with spaces
            dash_pat = re.compile(r'(?<=[^\-\d]) - (?=[^\-\d])')
            replacement = " \u2013 "
            def _repl(m: re.Match) -> str:
                corrections.append(Correction(
                    position=m.start(),
                    original=" - ",
                    replacement=" \u2013 ",
                    rule="en_dash",
                    description="Space-hyphen-space replaced with spaced en dash for EN-GB",
                ))
                return " \u2013 "

        else:
            return text, corrections

        result = dash_pat.sub(_repl, text)
        return result, corrections

    # ----- Ordinals -----

    def _rule_ordinals(self, text: str) -> Tuple[str, List[Correction]]:
        """Convert numeric ordinal approximations to proper typographic forms.

        PT: 5o -> 5.º, 3a -> 3.ª
        ES: 3er -> 3.º, 5o -> 5.º, 3a -> 3.ª
        """
        corrections: List[Correction] = []

        if self.language in ("pt-PT", "pt-BR"):
            def _repl_pt(m: re.Match) -> str:
                num = m.group(1)
                suffix = m.group(2)
                mark = ".\u00BA" if suffix == "o" else ".\u00AA"
                replacement = num + mark
                corrections.append(Correction(
                    position=m.start(),
                    original=m.group(0),
                    replacement=replacement,
                    rule="ordinals",
                    description=f"Ordinal approximation {m.group(0)!r} -> {replacement!r}",
                ))
                return replacement
            text = _PT_ORDINAL_PAT.sub(_repl_pt, text)

        elif self.language in ("es-ES", "es-MX"):
            def _repl_es(m: re.Match) -> str:
                num = m.group(1)
                suffix = m.group(2)
                mark = ".\u00BA" if suffix in ("er", "o") else ".\u00AA"
                replacement = num + mark
                corrections.append(Correction(
                    position=m.start(),
                    original=m.group(0),
                    replacement=replacement,
                    rule="ordinals",
                    description=f"Ordinal approximation {m.group(0)!r} -> {replacement!r}",
                ))
                return replacement
            text = _ES_ORDINAL_SUFFIX_PAT.sub(_repl_es, text)

        return text, corrections

    # ----- French capital accents -----

    def _rule_french_capital_accents(self, text: str) -> Tuple[str, List[Correction]]:
        """Add missing accents to French all-caps words per Académie française mandate."""
        corrections: List[Correction] = []

        for wrong, right in _FR_CAPITAL_ACCENTS_SAFE.items():
            pat = re.compile(r'\b' + re.escape(wrong) + r'\b')
            for m in pat.finditer(text):
                if m.group() == wrong:  # exact case match
                    corrections.append(Correction(
                        position=m.start(),
                        original=wrong,
                        replacement=right,
                        rule="french_capital_accents",
                        description=f"French capital accent: {wrong} -> {right}",
                    ))
            text = pat.sub(right, text)

        return text, corrections

    # ----- NBSP for page abbreviations -----

    def _rule_nbsp_page_abbrev(self, text: str) -> Tuple[str, List[Correction]]:
        """Insert NBSP between page/section abbreviations and following number.

        p. 42 -> p.\u00a042, pp. 10-20 -> pp.\u00a010-20
        """
        corrections: List[Correction] = []

        def _repl(m: re.Match) -> str:
            abbr = m.group(1)
            digit = m.group(2)
            replacement = abbr + NBSP + digit
            corrections.append(Correction(
                position=m.start(),
                original=m.group(0),
                replacement=replacement,
                rule="nbsp_page_abbrev",
                description=f"NBSP inserted between {abbr!r} and number",
            ))
            return replacement

        result = _PAGE_ABBREV_PAT.sub(_repl, text)
        return result, corrections

    # ----- Ligature suppression -----

    def _rule_ligature_suppression(self, text: str) -> Tuple[str, List[Correction]]:
        """Insert ZWNJ (U+200C) at morpheme boundaries to suppress unwanted ligatures.

        German: Auf|lage, Schiff|fahrt
        English: shelf|ful
        """
        corrections: List[Correction] = []

        if self.language == "de-DE":
            suppression_list = _DE_LIGATURE_SUPPRESSIONS
        elif self.language in ("en-US", "en-GB"):
            suppression_list = _EN_LIGATURE_SUPPRESSIONS
        else:
            return text, corrections

        for wrong, right in suppression_list:
            pat = re.compile(r'\b' + re.escape(wrong) + r'\b')
            for m in pat.finditer(text):
                corrections.append(Correction(
                    position=m.start(),
                    original=wrong,
                    replacement=right,
                    rule="ligature_suppression",
                    description=f"ZWNJ inserted at morpheme boundary: {wrong!r} -> {right!r}",
                ))
            text = pat.sub(right, text)

        return text, corrections

    # ----- Breakable containers (WCAG) -----

    def _rule_breakable_containers(self, text: str) -> Tuple[str, List[Correction]]:
        """Reduce NBSP chains of 4+ elements (3+ NBSP) to prevent unbreakable runs (WCAG).

        J.\u00a0R.\u00a0R.\u00a0Tolkien -> J.\u00a0R. R.\u00a0Tolkien
        Keeps the first NBSP and the last NBSP; breaks middle ones.
        Only fires on chains of 4+ elements (3+ NBSP) to leave 2-element
        initials pairs intact.
        """
        corrections: List[Correction] = []

        # Requires 2+ MIDDLE elements (= 4+ total, 3+ NBSP) to fire.
        # group1 = first element + NBSP (keep)
        # group2 = 2+ middle elements each ending with NBSP (break inner, keep last)
        # group3 = final word (pure letters)
        chain_pat = re.compile(
            r'([A-Z]\.' + NBSP + r')' +
            r'((?:[A-Z]\.' + NBSP + r'){2,})' +
            r'([A-Za-z\u00C0-\u024F]+)'
        )

        def _repl_chain(m: re.Match) -> str:
            first = m.group(1)    # "J.\u00a0"
            inner = m.group(2)    # "R.\u00a0R.\u00a0" (2+ elements each with NBSP)
            last_word = m.group(3)  # "Tolkien"

            # Split inner by NBSP, discard trailing empty
            inner_parts = [p for p in inner.split(NBSP) if p]
            # Rebuild: break all inner connections, keep NBSP before last_word
            if len(inner_parts) <= 1:
                # Nothing to break; reconstruct identically
                inner_rebuilt = inner
            else:
                # Join all inner elements with space, add NBSP at end
                # (the NBSP at the end connects the last inner element to last_word)
                inner_rebuilt = " ".join(inner_parts[:-1]) + " " + inner_parts[-1] + NBSP

            replacement = first + inner_rebuilt + last_word
            if replacement != m.group(0):
                corrections.append(Correction(
                    position=m.start(),
                    original=m.group(0),
                    replacement=replacement,
                    rule="breakable_containers",
                    description="NBSP chain of 4+ elements reduced to allow text reflow (WCAG SC 1.4.12)",
                ))
            return replacement

        result = chain_pat.sub(_repl_chain, text)
        return result, corrections

    # ----- Abbreviation haplology -----

    def _rule_abbreviation_haplology(self, text: str) -> Tuple[str, List[Correction]]:
        """Never double period: 'etc..' -> 'etc.' """
        corrections: List[Correction] = []

        # Pattern: word ending with period, followed by another period (sentence end)
        pattern = re.compile(r"(\w\.)\.(?=\s|$)")

        def _repl(m: re.Match) -> str:
            corrections.append(Correction(
                position=m.start(),
                original=m.group(0),
                replacement=m.group(1),
                rule="abbreviation_haplology",
                description="Removed double period (abbreviation haplology)",
            ))
            return m.group(1)

        result = pattern.sub(_repl, text)
        return result, corrections


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _highlight_diff(original: str, corrected: str) -> str:
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


def main():
    parser = argparse.ArgumentParser(
        description="Typeproof -- deterministic typographic corrections (Layer 1)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Examples:
  python3 typeproof.py "He said \\"hello\\" and left." --lang en-US
  python3 typeproof.py --file input.txt --lang fr-FR --json
  python3 typeproof.py --file input.txt --lang pt-PT --diff
  python3 typeproof.py "3x4 resolution, pages 10-20" --lang en-US
""",
    )
    parser.add_argument("text", nargs="?", help="Text to correct (or use --file or stdin)")
    parser.add_argument("--lang", default="en-US",
                        help=f"Language code: {', '.join(sorted(SUPPORTED_LANGUAGES))}")
    parser.add_argument("--register", choices=["editorial", "marketing", "ui", "literary"],
                        help="Register/context for register-sensitive rules")
    parser.add_argument("--file", help="Read text from file")
    parser.add_argument("--json", action="store_true", help="Output as JSON with metadata")
    parser.add_argument("--diff", action="store_true", help="Show before/after diff with highlights")
    parser.add_argument("--strict", action="store_true",
                        help="Never-corrupt mode: skip inference-based rules; only apply unambiguous corrections")
    parser.add_argument("--verbose", action="store_true", help="Show per-rule correction details")

    args = parser.parse_args()

    # Get input text
    if args.file:
        from pathlib import Path
        text = Path(args.file).read_text(encoding="utf-8")
    elif args.text:
        text = args.text
    elif not sys.stdin.isatty():
        text = sys.stdin.read()
    else:
        parser.error("Provide text as an argument, via --file, or pipe through stdin")

    # Validate language
    if args.lang not in SUPPORTED_LANGUAGES:
        print(
            f"Error: '{args.lang}' not in supported languages. "
            f"Supported: {', '.join(sorted(SUPPORTED_LANGUAGES))}",
            file=sys.stderr,
        )
        sys.exit(1)

    # Run lint
    linter = TypographyLinter(language=args.lang, register=args.register, strict=args.strict)
    result = linter.lint(text)

    # Output
    if args.json:
        print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
    elif args.diff:
        if result.corrections:
            print(_highlight_diff(result.original, result.text))
            print(
                f"\n({result.stats['total_corrections']} correction"
                f"{'s' if result.stats['total_corrections'] != 1 else ''})",
                file=sys.stderr,
            )
        else:
            print(result.text)
            print("\n(no changes)", file=sys.stderr)
    else:
        print(result.text)

    if args.verbose:
        stats = result.stats
        print(f"\nCorrections: {stats['total_corrections']}", file=sys.stderr)
        if stats["by_rule"]:
            for rule, count in sorted(stats["by_rule"].items()):
                print(f"  {rule}: {count}", file=sys.stderr)
        if result.corrections:
            print("\nDetails:", file=sys.stderr)
            for c in result.corrections:
                print(
                    f"  pos {c.position}: {c.original!r} -> {c.replacement!r}  [{c.rule}]",
                    file=sys.stderr,
                )


if __name__ == "__main__":
    main()
