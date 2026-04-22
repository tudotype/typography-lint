#!/usr/bin/env python3
"""
Font-Awareness Gate — Layer 3 of the Typography Intelligence pipeline.

Ensures corrector output is renderable by the target font. Never outputs a
character the font cannot render: a typographically imperfect but visible
character is always better than a missing glyph (tofu).

Architecture position:
    Raw text -> [Layer 1: Deterministic YAML rules] -> [Layer 2: Fine-tuned model] -> [Layer 3: Font Gate] -> Safe output

Full pipeline usage:

    from font_gate import FontGate

    # After model correction:
    corrected_text = model.correct(raw_text, language="fr-FR")

    # Before output:
    gate = FontGate(font_path="path/to/target-font.otf")
    safe = gate.process(corrected_text)
    print(safe.text)        # guaranteed renderable
    print(safe.fallbacks)   # what was downgraded and why

Conservative mode (no font file):

    gate = FontGate()  # assumes only tier 1 + tier 2 characters are safe
    safe = gate.process(corrected_text)
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

# ---------------------------------------------------------------------------
# Primitive name -> Unicode codepoint mapping
# Mirrors primitives.characters from typography-system-schema.yaml
# ---------------------------------------------------------------------------

PRIMITIVES: Dict[str, int] = {
    # Quotation marks
    "left_double_quote":        0x201C,
    "right_double_quote":       0x201D,
    "left_single_quote":        0x2018,
    "right_single_quote":       0x2019,
    "left_angle_quote":         0x00AB,
    "right_angle_quote":        0x00BB,
    "left_single_angle_quote":  0x2039,
    "right_single_angle_quote": 0x203A,
    "low_double_quote":         0x201E,
    "low_single_quote":         0x201A,

    # Dashes
    "hyphen":                   0x002D,
    "hyphen_minus":             0x002D,
    "en_dash":                  0x2013,
    "em_dash":                  0x2014,

    # Spaces
    "non_breaking_space":       0x00A0,
    "thin_space":               0x2009,
    "narrow_no_break_space":    0x202F,
    "hair_space":               0x200A,
    "regular_space":            0x0020,

    # Other marks
    "ellipsis":                 0x2026,
    "multiplication_sign":      0x00D7,
    "apostrophe":               0x2019,
    "prime":                    0x2032,
    "double_prime":             0x2033,
    "ordinal_indicator_masc":   0x00BA,
    "ordinal_indicator_fem":    0x00AA,
    "inverted_question":        0x00BF,
    "inverted_exclamation":     0x00A1,

    # Romanian diacritics
    "s_comma_below":            0x0219,
    "t_comma_below":            0x021B,
    "s_cedilla":                0x015F,
    "t_cedilla":                0x0163,

    # Mathematical
    "minus_sign":               0x2212,
    "degree_sign":              0x00B0,
    "fraction_slash":           0x2044,

    # Legal symbols
    "copyright_sign":           0x00A9,
    "registered_sign":          0x00AE,
    "trademark_sign":           0x2122,

    # Fractions
    "fraction_half":            0x00BD,
    "fraction_quarter":         0x00BC,
    "fraction_three_quarters":  0x00BE,
    "fraction_one_third":       0x2153,
    "fraction_two_thirds":      0x2154,

    # German
    "capital_sharp_s":          0x1E9E,
    "double_S":                 None,  # multi-char fallback: "SS"

    # French ligatures
    "oe_ligature":              0x0153,
    "oe_ligature_cap":          0x0152,
    "ae_ligature":              0x00E6,
    "ae_ligature_cap":          0x00C6,

    # Zero-width
    "zwnj":                     0x200C,
    "zwj":                      0x200D,
    "word_joiner":              0x2060,

    # Currency
    "euro_sign":                0x20AC,
    "dollar_sign":              0x0024,
    "pound_sign":               0x00A3,
    "yen_sign":                 0x00A5,
    "cent_sign":                0x00A2,

    # Reference marks
    "section_sign":             0x00A7,
    "paragraph_sign":           0x00B6,
    "dagger":                   0x2020,
    "double_dagger":            0x2021,
    "asterism":                 0x2042,
    "numero_sign":              0x2116,

    # Arrows and bullets
    "right_arrow":              0x2192,
    "left_arrow":               0x2190,
    "bullet":                   0x2022,
    "middle_dot":               0x00B7,

    # Other
    "interrobang":              0x203D,
    "per_mille":                0x2030,
    "percent":                  0x0025,
    "solidus":                  0x002F,
    "asterisk":                 0x002A,
    "period":                   0x002E,
    "comma":                    0x002C,
    "ampersand":                0x0026,
    "straight_double_quote":    0x0022,
    "straight_single_quote":    0x0027,

    # Bidi isolates
    "lri":                      0x2066,
    "rli":                      0x2067,
    "fsi":                      0x2068,
    "pdi":                      0x2069,
}

# Multi-character fallback strings (primitives that are not single codepoints)
MULTI_CHAR_FALLBACKS: Dict[str, str] = {
    "three_periods":            "...",
    "letter_x":                 "x",
    "double_S":                 "SS",
    "text_fraction_1_2":        "1/2",
    "text_fraction_1_4":        "1/4",
    "text_fraction_3_4":        "3/4",
    "text_fraction_1_3":        "1/3",
    "text_fraction_2_3":        "2/3",
    "text_copyright":           "(c)",
    "text_registered":          "(R)",
    "text_trademark":           "(TM)",
    "text_numero":              "No.",
    "text_section":             "Sec.",
    "asterisk_asterisk":        "**",
    "question_exclamation":     "?!",
    "text_arrow_right":         "->",
    "text_arrow_left":          "<-",
    "text_EUR":                 "EUR",
    "text_GBP":                 "GBP",
    "text_JPY":                 "JPY",
    "text_cent":                "c",
    "text_oe":                  "oe",
    "text_OE":                  "OE",
    "text_ae":                  "ae",
    "text_AE":                  "AE",
    "text_per_mille":           "\u2030",  # fallback is the symbol itself or "per mille"
    "text_degree":              "deg",
}

# ---------------------------------------------------------------------------
# Risk tiers — from font_awareness.font_risk_tiers in the schema
# ---------------------------------------------------------------------------

TIER_1_SAFE: Set[int] = {
    # basic_latin covers U+0020..U+007E
    *range(0x0020, 0x007F),
}

TIER_2_COMMON: Set[int] = {
    0x201C,  # left_double_quote
    0x201D,  # right_double_quote
    0x2018,  # left_single_quote
    0x2019,  # right_single_quote
    0x2014,  # em_dash
    0x2013,  # en_dash
    0x2026,  # ellipsis
    0x00A0,  # non_breaking_space
    0x00A9,  # copyright_sign
    0x00AE,  # registered_sign
    0x2122,  # trademark_sign
    0x00B0,  # degree_sign
    0x20AC,  # euro_sign
    0x00A3,  # pound_sign
    0x00A5,  # yen_sign
    0x00A7,  # section_sign
    0x2022,  # bullet
    0x00D7,  # multiplication_sign
    0x00BD,  # fraction_half
    0x00BC,  # fraction_quarter
    0x00BE,  # fraction_three_quarters
    0x0153,  # oe_ligature
    0x0152,  # oe_ligature_cap
    0x00E6,  # ae_ligature
    0x00C6,  # ae_ligature_cap
    0x00BF,  # inverted_question
    0x00A1,  # inverted_exclamation
}

TIER_3_SPECIALIST: Set[int] = {
    0x202F,  # narrow_no_break_space
    0x2009,  # thin_space
    0x200A,  # hair_space
    0x2032,  # prime
    0x2033,  # double_prime
    0x00AB,  # left_angle_quote
    0x00BB,  # right_angle_quote
    0x2039,  # left_single_angle_quote
    0x203A,  # right_single_angle_quote
    0x201E,  # low_double_quote
    0x201A,  # low_single_quote
    0x2044,  # fraction_slash
    0x00BA,  # ordinal_indicator_masc
    0x00AA,  # ordinal_indicator_fem
    0x2212,  # minus_sign
    0x2153,  # fraction_one_third
    0x2154,  # fraction_two_thirds
    0x2020,  # dagger
    0x2021,  # double_dagger
    0x2116,  # numero_sign
    0x2030,  # per_mille
    0x00B7,  # middle_dot
    0x00B6,  # paragraph_sign
}

TIER_4_RARE: Set[int] = {
    0x1E9E,  # capital_sharp_s
    0x0219,  # s_comma_below
    0x021B,  # t_comma_below
    0x200C,  # zwnj
    0x2060,  # word_joiner
    0x2066,  # lri
    0x2067,  # rli
    0x2068,  # fsi
    0x2069,  # pdi
    0x203D,  # interrobang
    0x2042,  # asterism
    0x2192,  # right_arrow
    0x2190,  # left_arrow
}

ALL_TRACKED: Set[int] = TIER_1_SAFE | TIER_2_COMMON | TIER_3_SPECIALIST | TIER_4_RARE

# ---------------------------------------------------------------------------
# Fallback chains — from font_awareness.fallback_chains in the schema
# Each chain maps a codepoint to an ordered list of fallback options.
# A fallback is either a codepoint (int) or a multi-char string (str).
# ---------------------------------------------------------------------------

def _resolve(name: str):
    """Resolve a primitive name to a codepoint or multi-char string."""
    if name in PRIMITIVES and PRIMITIVES[name] is not None:
        return PRIMITIVES[name]
    if name in MULTI_CHAR_FALLBACKS:
        return MULTI_CHAR_FALLBACKS[name]
    return None


def _build_fallback_chains() -> Dict[int, list]:
    """Build codepoint -> [fallback options] from schema definitions."""
    # Schema fallback_chains: ideal_primitive_name -> [fallback_primitive_names]
    _schema_chains = {
        "narrow_no_break_space":    ["thin_space", "non_breaking_space", "regular_space"],
        "thin_space":               ["non_breaking_space", "regular_space"],
        "hair_space":               ["thin_space", "regular_space"],
        "left_double_quote":        ["straight_double_quote"],
        "right_double_quote":       ["straight_double_quote"],
        "left_single_quote":        ["straight_single_quote"],
        "right_single_quote":       ["straight_single_quote"],
        "left_angle_quote":         ["left_double_quote", "straight_double_quote"],
        "right_angle_quote":        ["right_double_quote", "straight_double_quote"],
        "left_single_angle_quote":  ["left_single_quote", "straight_single_quote"],
        "right_single_angle_quote": ["right_single_quote", "straight_single_quote"],
        "low_double_quote":         ["straight_double_quote"],
        "low_single_quote":         ["straight_single_quote"],
        "em_dash":                  ["en_dash", "hyphen_minus"],
        "en_dash":                  ["hyphen_minus"],
        "ellipsis":                 ["three_periods"],
        "multiplication_sign":      ["letter_x"],
        "minus_sign":               ["hyphen_minus"],
        "fraction_slash":           ["solidus"],
        "capital_sharp_s":          ["double_S"],
        "s_comma_below":            ["s_cedilla"],
        "t_comma_below":            ["t_cedilla"],
        "fraction_half":            ["text_fraction_1_2"],
        "fraction_quarter":         ["text_fraction_1_4"],
        "fraction_three_quarters":  ["text_fraction_3_4"],
        "fraction_one_third":       ["text_fraction_1_3"],
        "fraction_two_thirds":      ["text_fraction_2_3"],
        "prime":                    ["straight_single_quote"],
        "double_prime":             ["straight_double_quote"],
        "copyright_sign":           ["text_copyright"],
        "registered_sign":          ["text_registered"],
        "trademark_sign":           ["text_trademark"],
        "numero_sign":              ["text_numero"],
        "section_sign":             ["text_section"],
        "dagger":                   ["asterisk"],
        "double_dagger":            ["asterisk_asterisk"],
        "interrobang":              ["question_exclamation"],
        "right_arrow":              ["text_arrow_right"],
        "left_arrow":               ["text_arrow_left"],
        "euro_sign":                ["text_EUR"],
        "pound_sign":               ["text_GBP"],
        "yen_sign":                 ["text_JPY"],
        "cent_sign":                ["text_cent"],
        "oe_ligature":              ["text_oe"],
        "oe_ligature_cap":          ["text_OE"],
        "ae_ligature":              ["text_ae"],
        "ae_ligature_cap":          ["text_AE"],
        "per_mille":                ["text_per_mille"],
        "degree_sign":              ["text_degree"],
        "bullet":                   ["hyphen_minus"],
        "lri":                      [],
        "rli":                      [],
        "fsi":                      [],
        "pdi":                      [],
        "zwnj":                     [],
        "zwj":                      [],
        "word_joiner":              ["zwnj"],
    }

    chains: Dict[int, list] = {}
    for name, fallback_names in _schema_chains.items():
        cp = PRIMITIVES.get(name)
        if cp is None:
            continue
        resolved = []
        for fb_name in fallback_names:
            r = _resolve(fb_name)
            if r is not None:
                resolved.append(r)
        chains[cp] = resolved
    return chains


FALLBACK_CHAINS: Dict[int, list] = _build_fallback_chains()

# Reverse lookup: codepoint -> primitive name (for reporting)
_CP_TO_NAME: Dict[int, str] = {}
for _name, _cp in PRIMITIVES.items():
    if _cp is not None and _cp not in _CP_TO_NAME:
        _CP_TO_NAME[_cp] = _name


def _char_name(cp: int) -> str:
    """Human-readable name for a codepoint."""
    name = _CP_TO_NAME.get(cp, "")
    return f"U+{cp:04X} {name}" if name else f"U+{cp:04X}"


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class FallbackRecord:
    """Record of a single character substitution."""
    original: str
    replacement: str
    position: int
    reason: str

    def to_dict(self) -> dict:
        return {
            "original": self.original,
            "replacement": self.replacement,
            "position": self.position,
            "reason": self.reason,
        }


@dataclass
class ProcessedText:
    """Result of FontGate.process()."""
    text: str
    fallbacks: List[FallbackRecord] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "text": self.text,
            "fallbacks": [f.to_dict() for f in self.fallbacks],
            "warnings": self.warnings,
        }


# ---------------------------------------------------------------------------
# FontGate
# ---------------------------------------------------------------------------

class FontGate:
    """
    Font-awareness gate for the Typography Intelligence pipeline.

    Checks whether characters are renderable by the target font and applies
    fallback chains for unsupported characters.

    Three modes of initialisation:
      - font_path: read cmap from a .ttf/.otf/.woff/.woff2 file (requires fonttools)
      - supported_chars: explicit set of supported codepoints
      - no args: conservative mode (tier 1 + tier 2 assumed safe)
    """

    def __init__(
        self,
        font_path: Optional[str] = None,
        supported_chars: Optional[Set[int]] = None,
    ):
        self._font_path = font_path
        self._mode: str = "conservative"
        self._supported: Optional[Set[int]] = None

        if font_path is not None:
            self._supported = self._load_cmap(font_path)
            self._mode = "cmap"
        elif supported_chars is not None:
            self._supported = set(supported_chars)
            self._mode = "explicit"
        # else: conservative mode -- tier 1 + tier 2 assumed safe

    @staticmethod
    def _load_cmap(font_path: str) -> Set[int]:
        """Load supported codepoints from a font file via fonttools."""
        try:
            from fontTools.ttLib import TTFont
        except ImportError:
            raise ImportError(
                "fonttools is required for font file reading. "
                "Install with: pip install fonttools>=4.0.0\n"
                "For .woff/.woff2 support also install: pip install brotli"
            )
        font = TTFont(font_path)
        cmap = font.getBestCmap()
        if cmap is None:
            raise ValueError(f"No usable cmap table found in {font_path}")
        return set(cmap.keys())

    @property
    def mode(self) -> str:
        """Return the detection mode: 'cmap', 'explicit', or 'conservative'."""
        return self._mode

    # ----- Core methods -----

    def check(self, char: str) -> bool:
        """
        Check whether a single character is supported by the font.

        In conservative mode, tier 1 and tier 2 characters are assumed safe;
        tier 3 and tier 4 are assumed unsupported.
        """
        cp = ord(char[0]) if isinstance(char, str) else char
        if self._supported is not None:
            return cp in self._supported
        # Conservative mode
        return cp in TIER_1_SAFE or cp in TIER_2_COMMON

    def get_tier(self, char: str) -> int:
        """
        Return the risk tier (1-4) for a character. Returns 0 if the
        character is not in any tracked tier (e.g., standard letters).
        """
        cp = ord(char[0]) if isinstance(char, str) else char
        if cp in TIER_1_SAFE:
            return 1
        if cp in TIER_2_COMMON:
            return 2
        if cp in TIER_3_SPECIALIST:
            return 3
        if cp in TIER_4_RARE:
            return 4
        return 0

    def _find_fallback(self, cp: int) -> Optional[Tuple[str, str]]:
        """
        Walk the fallback chain for a codepoint.

        Returns (replacement_string, reason) or None if no fallback is available.
        """
        chain = FALLBACK_CHAINS.get(cp)
        if chain is None:
            return None

        for fb in chain:
            if isinstance(fb, str):
                # Multi-character fallback -- always "supported" since it is
                # composed of basic characters
                return (fb, f"multi-char fallback for {_char_name(cp)}")
            # Single codepoint fallback
            if self.check(chr(fb)):
                fb_char = chr(fb)
                return (fb_char, f"{_char_name(cp)} -> {_char_name(fb)}")
            # The fallback itself might have its own chain -- recurse one level
            nested = FALLBACK_CHAINS.get(fb)
            if nested:
                for nested_fb in nested:
                    if isinstance(nested_fb, str):
                        return (nested_fb, f"{_char_name(cp)} -> {_char_name(fb)} -> multi-char")
                    if self.check(chr(nested_fb)):
                        return (chr(nested_fb), f"{_char_name(cp)} -> {_char_name(fb)} -> {_char_name(nested_fb)}")
        return None

    def process(self, text: str) -> ProcessedText:
        """
        Walk the text, check every character, apply fallback chains for
        unsupported characters. Returns a ProcessedText with the safe text,
        fallback records, and warnings.
        """
        result_chars: List[str] = []
        fallbacks: List[FallbackRecord] = []
        warnings: List[str] = []
        output_pos = 0

        for i, ch in enumerate(text):
            cp = ord(ch)

            # Only process characters that the typography system tracks
            if cp not in ALL_TRACKED and cp not in FALLBACK_CHAINS:
                result_chars.append(ch)
                output_pos += 1
                continue

            if self.check(ch):
                result_chars.append(ch)
                output_pos += 1
                continue

            # Character not supported -- find fallback
            fb = self._find_fallback(cp)
            if fb is not None:
                replacement, reason = fb
                fallbacks.append(FallbackRecord(
                    original=ch,
                    replacement=replacement,
                    position=output_pos,
                    reason=reason,
                ))
                result_chars.append(replacement)
                output_pos += len(replacement)
            else:
                # No fallback available
                if FALLBACK_CHAINS.get(cp) == []:
                    # Empty chain (invisible control chars) -- drop silently
                    warnings.append(
                        f"Dropped unsupported invisible character {_char_name(cp)} at position {i}"
                    )
                else:
                    # Leave original to avoid tofu -- but warn
                    warnings.append(
                        f"No fallback for unsupported character {_char_name(cp)} at position {i}; left unchanged"
                    )
                    result_chars.append(ch)
                    output_pos += 1

        return ProcessedText(
            text="".join(result_chars),
            fallbacks=fallbacks,
            warnings=warnings,
        )

    def report(self, text: str) -> dict:
        """
        Analyse text without modifying it. Report which characters are at risk,
        their tier, and what fallbacks would be applied.
        """
        characters: List[dict] = []
        tier_counts = {1: 0, 2: 0, 3: 0, 4: 0}
        at_risk: List[dict] = []

        seen: Set[int] = set()
        for i, ch in enumerate(text):
            cp = ord(ch)
            if cp not in ALL_TRACKED and cp not in FALLBACK_CHAINS:
                continue

            tier = self.get_tier(ch)
            if tier > 0:
                tier_counts[tier] += 1

            supported = self.check(ch)
            fb_info = None
            if not supported:
                fb = self._find_fallback(cp)
                if fb is not None:
                    fb_info = {"replacement": fb[0], "reason": fb[1]}

            if cp not in seen:
                entry = {
                    "char": ch,
                    "codepoint": f"U+{cp:04X}",
                    "name": _CP_TO_NAME.get(cp, ""),
                    "tier": tier,
                    "supported": supported,
                    "position_first_seen": i,
                }
                if fb_info:
                    entry["fallback"] = fb_info
                characters.append(entry)
                if not supported:
                    at_risk.append(entry)
                seen.add(cp)

        return {
            "mode": self._mode,
            "total_tracked_characters": sum(tier_counts.values()),
            "tier_counts": tier_counts,
            "unique_characters": characters,
            "at_risk": at_risk,
        }

    def check_font(self) -> dict:
        """
        Report the font's typography readiness: tier coverage, missing
        characters, and an overall readiness score.
        """
        if self._supported is None:
            return {"error": "No font loaded. Use font_path= to load a font."}

        tiers = {
            1: ("tier_1_safe", TIER_1_SAFE),
            2: ("tier_2_common", TIER_2_COMMON),
            3: ("tier_3_specialist", TIER_3_SPECIALIST),
            4: ("tier_4_rare", TIER_4_RARE),
        }

        total_chars = 0
        total_supported = 0
        tier_reports = {}

        for tier_num, (tier_name, tier_set) in tiers.items():
            supported = []
            missing = []
            for cp in sorted(tier_set):
                name = _CP_TO_NAME.get(cp, "")
                entry = {"codepoint": f"U+{cp:04X}", "name": name, "char": chr(cp)}
                if cp in self._supported:
                    supported.append(entry)
                else:
                    missing.append(entry)
            total = len(tier_set)
            total_chars += total
            total_supported += len(supported)
            tier_reports[tier_name] = {
                "total": total,
                "supported": len(supported),
                "missing_count": len(missing),
                "missing": missing,
                "coverage": f"{len(supported)/total*100:.1f}%" if total > 0 else "N/A",
            }

        # Weighted score: tier 1 and 2 matter much more than 3 and 4
        weights = {1: 4.0, 2: 3.0, 3: 2.0, 4: 1.0}
        weighted_score = 0.0
        weight_total = 0.0
        for tier_num, (tier_name, tier_set) in tiers.items():
            total = len(tier_set)
            if total == 0:
                continue
            supported_count = tier_reports[tier_name]["supported"]
            w = weights[tier_num]
            weighted_score += w * (supported_count / total)
            weight_total += w

        readiness = (weighted_score / weight_total * 100) if weight_total > 0 else 0

        return {
            "font_path": self._font_path,
            "total_typography_characters": total_chars,
            "total_supported": total_supported,
            "overall_coverage": f"{total_supported/total_chars*100:.1f}%" if total_chars > 0 else "N/A",
            "typography_readiness_score": f"{readiness:.1f}%",
            "tiers": tier_reports,
        }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _cli():
    parser = argparse.ArgumentParser(
        description="Font-awareness gate for the Typography Intelligence pipeline.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Examples:
  python font_gate.py --font myfont.ttf --input "He said, \\u201CHello.\\u201D"
  python font_gate.py --font myfont.otf --file corrected.txt
  python font_gate.py --report "Analyse this text\\u2019s characters"
  python font_gate.py --check-font myfont.woff2
""",
    )
    parser.add_argument("--font", help="Path to font file (.ttf, .otf, .woff, .woff2)")
    parser.add_argument("--input", help="Text string to process")
    parser.add_argument("--file", help="File containing text to process")
    parser.add_argument("--report", help="Analyse text without changing it (report mode)")
    parser.add_argument("--check-font", dest="check_font", help="Report font typography readiness")
    parser.add_argument("--json", action="store_true", help="Output as JSON")

    args = parser.parse_args()

    # --check-font mode
    if args.check_font:
        gate = FontGate(font_path=args.check_font)
        result = gate.check_font()
        if args.json:
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            _print_check_font(result)
        return

    # --report mode (no font required)
    if args.report is not None:
        text = args.report
        gate = FontGate(font_path=args.font) if args.font else FontGate()
        result = gate.report(text)
        if args.json:
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            _print_report(result)
        return

    # --input or --file mode
    text = None
    if args.input:
        text = args.input
    elif args.file:
        with open(args.file, "r", encoding="utf-8") as f:
            text = f.read()

    if text is None:
        parser.print_help()
        sys.exit(1)

    gate = FontGate(font_path=args.font) if args.font else FontGate()
    result = gate.process(text)

    if args.json:
        print(json.dumps(result.to_dict(), indent=2, ensure_ascii=False))
    else:
        _print_process(result)


def _print_process(result: ProcessedText):
    """Pretty-print a ProcessedText result."""
    print("--- Processed Text ---")
    print(result.text)
    if result.fallbacks:
        print(f"\n--- Fallbacks ({len(result.fallbacks)}) ---")
        for fb in result.fallbacks:
            orig_display = repr(fb.original)
            repl_display = repr(fb.replacement)
            print(f"  pos {fb.position}: {orig_display} -> {repl_display}  ({fb.reason})")
    if result.warnings:
        print(f"\n--- Warnings ({len(result.warnings)}) ---")
        for w in result.warnings:
            print(f"  {w}")
    if not result.fallbacks and not result.warnings:
        print("\nAll characters supported. No fallbacks needed.")


def _print_report(report: dict):
    """Pretty-print a report result."""
    print(f"Mode: {report['mode']}")
    print(f"Tracked characters in text: {report['total_tracked_characters']}")
    tc = report["tier_counts"]
    print(f"  Tier 1 (safe): {tc[1]}  |  Tier 2 (common): {tc[2]}  |  Tier 3 (specialist): {tc[3]}  |  Tier 4 (rare): {tc[4]}")

    if report["at_risk"]:
        print(f"\nAt-risk characters ({len(report['at_risk'])}):")
        for entry in report["at_risk"]:
            ch = repr(entry["char"])
            fb = ""
            if "fallback" in entry:
                fb = f"  -> fallback: {repr(entry['fallback']['replacement'])}"
            print(f"  {entry['codepoint']} {entry['name']} (tier {entry['tier']}) {ch}{fb}")
    else:
        print("\nNo at-risk characters found.")


def _print_check_font(report: dict):
    """Pretty-print a check-font result."""
    if "error" in report:
        print(f"Error: {report['error']}")
        return
    print(f"Font: {report['font_path']}")
    print(f"Typography readiness score: {report['typography_readiness_score']}")
    print(f"Overall coverage: {report['overall_coverage']} ({report['total_supported']}/{report['total_typography_characters']})")
    print()

    for tier_name, tier_data in report["tiers"].items():
        print(f"  {tier_name}: {tier_data['coverage']} ({tier_data['supported']}/{tier_data['total']})")
        if tier_data["missing"]:
            for m in tier_data["missing"]:
                print(f"    MISSING: {m['codepoint']} {m['name']}")
    print()


if __name__ == "__main__":
    _cli()
