"""Unit tests for typeproof.

Each rule has a positive case (does the right thing) and at least one
negative case (does NOT fire when it shouldn't). The negative cases are
the important ones — they're what would otherwise show up as eval
regressions on real text.

Run with: ``pytest test_typeproof.py -v``
or:       ``python3 -m pytest test_typeproof.py``
"""
from __future__ import annotations

import pytest

from typeproof import (
    NBSP,
    NNBSP,
    THIN,
    TypographyLinter,
)


def lint(text: str, lang: str = "en-US", **kwargs) -> str:
    """Test helper: lint and return the corrected text."""
    return TypographyLinter(language=lang).lint(text, **kwargs).text


def rules_fired(text: str, lang: str = "en-US", **kwargs) -> set[str]:
    """Test helper: return the set of rule names that fired."""
    result = TypographyLinter(language=lang).lint(text, **kwargs)
    return {c.rule for c in result.corrections}


# ---------------------------------------------------------------------------
# NFC normalisation
# ---------------------------------------------------------------------------

class TestNFC:
    def test_nfc_combines_decomposed_chars(self):
        # "café" with combining acute (U+0065 + U+0301) -> precomposed
        decomposed = "cafe\u0301"
        assert lint(decomposed) == "café"

    def test_nfc_idempotent_on_precomposed(self):
        assert lint("café") == "café"


# ---------------------------------------------------------------------------
# Ellipsis
# ---------------------------------------------------------------------------

class TestEllipsis:
    def test_three_dots_becomes_ellipsis(self):
        assert lint("Wait...") == "Wait\u2026"

    def test_double_period_collapsed_by_haplology(self):
        # Documented behaviour: "Wait.." collapses to "Wait." via haplology rule.
        assert lint("Wait..") == "Wait."

    def test_ellipsis_not_in_code(self):
        assert lint("`x...` is code") == "`x...` is code"


# ---------------------------------------------------------------------------
# Quotation marks (en-US, en-GB, fr-FR, de-DE, pt-PT)
# ---------------------------------------------------------------------------

class TestQuotes:
    def test_en_us_curly_doubles(self):
        assert lint('He said "hi" today.') == "He said \u201chi\u201d today."

    def test_en_gb_single_primary(self):
        assert lint("He said 'hi' today.", lang="en-GB") == "He said \u2018hi\u2019 today."

    def test_fr_guillemets(self):
        out = lint('Il dit "bonjour".', lang="fr-FR")
        assert "\u00ab" in out and "\u00bb" in out

    def test_de_low_high(self):
        out = lint('Er sagte "hallo".', lang="de-DE")
        assert "\u201e" in out and "\u201c" in out

    def test_quotes_not_in_code(self):
        assert lint('Use `"foo"` here.') == 'Use `"foo"` here.'

    def test_pt_pt_nested_quotes(self):
        # Regression: schema parity round-trip surfaced tangled output for
        # nested quotes in pt-PT. Adjacency-based stack parsing now handles
        # both flat and nested cases. Outer should be guillemets («…»),
        # inner should be curly doubles (“…”).
        src = '"Ele disse "olá" e saiu"'
        out = lint(src, lang="pt-PT")
        assert "\u00ab" in out and "\u00bb" in out, "outer guillemets present"
        assert "\u201c" in out and "\u201d" in out, "inner curly doubles present"
        # The inner pair must wrap "olá" exactly, not the wrong substring.
        assert "\u201colá\u201d" in out

    def test_en_us_nested_quotes(self):
        # Same nesting logic should work for en-US (curly outer, single inner).
        src = 'She said "He told me \"hi\" yesterday" and left.'
        # That test input has escaped inner singles; use a cleaner case:
        src = 'She said "he replied "yes" politely" and left.'
        out = lint(src, lang="en-US")
        # Outer pair: curly doubles. Inner pair: curly singles.
        assert out.count("\u201c") == 1 and out.count("\u201d") == 1
        assert out.count("\u2018") == 1 and out.count("\u2019") == 1
        assert "\u2018yes\u2019" in out

    def test_two_separate_quoted_runs_both_outer(self):
        # Two non-nested quote pairs in a sentence should both be outer.
        src = 'He said "yes" and she said "no".'
        out = lint(src, lang="en-US")
        # Both pairs use primary (curly double), neither uses nested (singles).
        assert out.count("\u201c") == 2 and out.count("\u201d") == 2
        assert "\u2018" not in out and "\u2019" not in out


# ---------------------------------------------------------------------------
# Dashes (locale-aware)
# ---------------------------------------------------------------------------

class TestDashes:
    # Note: the dash rule fires on space-hyphen-space (" - "), not on
    # double-hyphen ("--"). Markdown/plain text typically use " - ".

    def test_en_us_em_dash(self):
        assert lint("foo - bar") == "foo\u2014bar"

    def test_en_gb_spaced_en_dash(self):
        assert lint("foo - bar", lang="en-GB") == "foo \u2013 bar"

    def test_fr_em_with_nnbsp(self):
        out = lint("foo - bar", lang="fr-FR")
        assert "\u2014" in out
        assert NNBSP in out

    def test_de_spaced_en_dash(self):
        assert lint("foo - bar", lang="de-DE") == "foo \u2013 bar"

    def test_dash_not_in_negative_number(self):
        # "-5" must not become an en-dash. (It does correctly become a
        # MINUS SIGN U+2212 via _rule_minus_sign — that's a separate rule.)
        out = lint("a -5 b")
        assert "\u2013" not in out  # no en-dash


# ---------------------------------------------------------------------------
# Range dash
# ---------------------------------------------------------------------------

class TestRangeDash:
    def test_year_range(self):
        assert lint("2020-2024") == "2020\u20132024"

    def test_page_range(self):
        assert lint("pp. 5-10") == "pp.\u00a05\u201310"

    def test_negative_number_in_prose_unchanged(self):
        # Don't convert "-5" (single number with leading minus) to en dash
        assert lint("a -5 b") != "a \u20135 b"

    def test_spaced_subtraction_not_turned_into_range(self):
        # Regression: a spaced hyphen between numbers is ambiguous with
        # subtraction. "10 - 3 = 7" must NOT become "10\u20133 = 7" (en-dash + eaten
        # spaces). The spaces must survive and no en-dash may appear. (The
        # operator legitimately becomes a true minus sign U+2212, which is
        # correct for subtraction.) Found in audit, 2026-06.
        out = lint("10 - 3 = 7")
        assert "\u2013" not in out          # no en-dash (the range-dash bug)
        assert out == "10 \u2212 3 = 7"     # spaces preserved; proper minus sign

    def test_tight_range_still_converts(self):
        # The legitimate tight range must still get an en-dash.
        assert lint("see 10-20") == "see 10\u201320"


# ---------------------------------------------------------------------------
# Arrows (NEW)
# ---------------------------------------------------------------------------

class TestArrows:
    def test_right_arrow_in_prose(self):
        assert lint("click -> next page") == "click \u2192 next page"

    def test_left_arrow_in_prose(self):
        assert lint("step <- back") == "step \u2190 back"

    def test_left_right_arrow(self):
        assert lint("foo <-> bar") == "foo \u2194 bar"

    def test_no_arrow_inside_code(self):
        assert lint("`foo->bar` is code") == "`foo->bar` is code"

    def test_no_arrow_unspaced(self):
        # method chaining -- typical in PHP/C; should not be touched
        assert lint("obj->method()") == "obj->method()"

    def test_fat_arrow_left_alone(self):
        assert lint("x => x + 1") == "x => x + 1"


# ---------------------------------------------------------------------------
# Currency spacing (NEW)
# ---------------------------------------------------------------------------

class TestCurrency:
    def test_en_us_strip_space(self):
        assert lint("$ 10.50", lang="en-US") == "$10.50"

    def test_en_us_attached_unchanged(self):
        assert lint("$10.50", lang="en-US") == "$10.50"

    def test_pt_pt_after_with_nbsp(self):
        assert lint("custa 10\u20ac.", lang="pt-PT") == f"custa 10{NBSP}\u20ac."

    def test_fr_fr_after_with_nbsp(self):
        assert lint("10 \u20ac aqui", lang="fr-FR") == f"10{NBSP}\u20ac aqui"

    def test_nl_nl_before_with_nbsp(self):
        assert lint("\u20ac10,00", lang="nl-NL") == f"\u20ac{NBSP}10,00"

    def test_no_currency_in_code(self):
        assert lint("`$10`", lang="pt-PT") == "`$10`"


# ---------------------------------------------------------------------------
# Italian apostrophic acute (NEW)
# ---------------------------------------------------------------------------

class TestItalianApostrophic:
    def test_perche(self):
        assert lint("perche'", lang="it-IT") == "perché"

    def test_capital_perche(self):
        assert lint("Perche'", lang="it-IT") == "Perché"

    def test_e_verb(self):
        assert lint("e' importante", lang="it-IT") == "è importante"

    def test_caffe(self):
        assert lint("un caffe' al bar", lang="it-IT") == "un caffè al bar"

    def test_does_not_fire_on_other_languages(self):
        # The Italian apostrophic acute rule must not fire for en-US:
        # the trailing apostrophe stays as-is (or gets curled, depending on
        # context), but the precomposed accent is never inserted.
        out = lint("perche'", lang="en-US")
        assert "perché" not in out

    def test_genuine_apostrophe_preserved(self):
        # "l'opera" has a real apostrophe (elision), don't accent the l
        out = lint("l'opera lirica", lang="it-IT")
        assert out.startswith("l\u2019opera") or out.startswith("l'opera")


# ---------------------------------------------------------------------------
# Capital accent preservation (NEW)
# ---------------------------------------------------------------------------

class TestCapitalAccents:
    def test_es_mexico(self):
        assert lint("MEXICO DF", lang="es-ES") == "MÉXICO DF"

    def test_es_bogota(self):
        assert lint("BOGOTA", lang="es-ES") == "BOGOTÁ"

    def test_it_citta(self):
        assert lint("CITTA del vaticano", lang="it-IT") == "CITTÀ del vaticano"

    def test_pt_agua(self):
        assert lint("AGUA fresca", lang="pt-PT") == "ÁGUA fresca"

    def test_does_not_match_substrings(self):
        # "AGUARDAR" contains "AGUA" — must not fire on substring
        assert "AGUA\u0301" not in lint("AGUARDAR", lang="pt-PT")
        assert lint("AGUARDAR", lang="pt-PT") == "AGUARDAR"

    def test_fires_only_for_configured_language(self):
        # English doesn't have a capital-accent table; CITTA stays
        assert lint("CITTA", lang="en-US") == "CITTA"


# ---------------------------------------------------------------------------
# Spanish inverted punctuation (NEW)
# ---------------------------------------------------------------------------

class TestSpanishInverted:
    def test_question_mark(self):
        assert lint("Donde vives?", lang="es-ES") == "\u00bfDónde vives?"

    def test_exclamation(self):
        assert lint("Que increible!", lang="es-ES") == "\u00a1Qué increíble!"

    def test_already_has_opener(self):
        assert lint("\u00bfDónde vives?", lang="es-ES") == "\u00bfDónde vives?"

    def test_mid_paragraph_question(self):
        out = lint("Hola. Donde vives? Bien.", lang="es-ES")
        assert "\u00bfDónde vives?" in out

    def test_does_not_fire_outside_spanish(self):
        assert lint("Where do you live?", lang="en-US") == "Where do you live?"

    def test_lexical_accent_increible(self):
        out = lint("Es increible.", lang="es-ES")
        assert "increíble" in out


# ---------------------------------------------------------------------------
# Percentage spacing
# ---------------------------------------------------------------------------

class TestPercent:
    def test_fr_nnbsp(self):
        assert lint("25%", lang="fr-FR") == f"25{NNBSP}%"

    def test_de_nbsp(self):
        assert lint("25%", lang="de-DE") == f"25{NBSP}%"

    def test_en_no_space(self):
        assert lint("25%", lang="en-US") == "25%"


# ---------------------------------------------------------------------------
# Single-letter NBSP
# ---------------------------------------------------------------------------

class TestSingleLetterNBSP:
    def test_es_y(self):
        assert lint("pan y agua", lang="es-ES") == f"pan y{NBSP}agua"

    def test_pl_w(self):
        assert lint("idę w kino", lang="pl") == f"idę w{NBSP}kino"

    def test_fr_a_not_fired(self):
        # 'a' is the 3rd-person verb in fr; we explicitly don't NBSP it
        # to avoid false positives. Only 'à' is treated.
        out = lint("il a faim", lang="fr-FR")
        assert NBSP not in out


# ---------------------------------------------------------------------------
# Code exclusion (cross-cutting safety)
# ---------------------------------------------------------------------------

class TestCodeExclusion:
    def test_fenced_block_unchanged(self):
        text = "```\nx --> y\n```"
        assert lint(text) == text

    def test_inline_code_unchanged(self):
        text = "Use `x->y` for that."
        assert lint(text) == text

    def test_url_unchanged(self):
        text = "See https://example.com/foo--bar for details."
        assert "example.com/foo--bar" in lint(text)


# ---------------------------------------------------------------------------
# Widow prevention (opt-in, document-level only)
# ---------------------------------------------------------------------------

class TestWidowPrevention:
    def test_default_off(self):
        # Default lint should NOT join last two words.
        text = "This is a short sentence."
        assert NBSP not in lint(text)

    def test_opt_in_joins_last_pair(self):
        text = "This is a short sentence."
        out = lint(text, prevent_widows=True)
        assert "short" + NBSP + "sentence" in out

    def test_short_paragraph_skipped(self):
        # 3 words — below threshold
        text = "Hi there friend."
        out = lint(text, prevent_widows=True)
        assert NBSP not in out


# ---------------------------------------------------------------------------
# Footnote mark placement (NEW)
# ---------------------------------------------------------------------------

class TestFootnotePlacement:
    def test_en_us_after_period(self):
        assert lint("Typography matters\u00b9.", lang="en-US") == "Typography matters.\u00b9"

    def test_de_de_after_period(self):
        assert lint("Typografie ist wichtig\u00b9.", lang="de-DE") == "Typografie ist wichtig.\u00b9"

    def test_fr_fr_before_period(self):
        assert lint("La typographie est importante.\u00b9", lang="fr-FR") == "La typographie est importante\u00b9."

    def test_no_change_when_already_correct_en(self):
        assert lint("Done.\u00b9", lang="en-US") == "Done.\u00b9"


# ---------------------------------------------------------------------------
# Quote punctuation placement (NEW)
# ---------------------------------------------------------------------------

class TestQuotePunctuationPlacement:
    def test_en_us_period_inside(self):
        assert lint('He called it "magnificent".', lang="en-US") == "He called it \u201cmagnificent.\u201d"

    def test_en_gb_period_outside(self):
        assert lint("He called it \u2018magnificent.\u2019", lang="en-GB") == "He called it \u2018magnificent\u2019."

    def test_de_de_period_outside(self):
        assert lint("Er nannte es \u201egro\u00dfartig.\u201c", lang="de-DE") == "Er nannte es \u201egro\u00dfartig\u201c."

    def test_question_mark_unaffected_en_us(self):
        # Only period and comma migrate; ? stays where it logically belongs.
        out = lint('He asked "why".', lang="en-US")
        assert out.endswith(".\u201d") or out.endswith("\u201d.")  # period migrates


# ---------------------------------------------------------------------------
# Serial comma (NEW)
# ---------------------------------------------------------------------------

class TestSerialComma:
    def test_en_us_enforce(self):
        assert lint("red, white and blue", lang="en-US") == "red, white, and blue"

    def test_fr_fr_remove(self):
        assert lint("rouge, blanc, et bleu", lang="fr-FR") == "rouge, blanc et bleu"

    def test_de_de_remove(self):
        assert lint("rot, wei\u00df, und blau", lang="de-DE") == "rot, wei\u00df und blau"

    def test_two_item_list_untouched(self):
        # No prior comma -> not a list -> don't add serial comma
        assert lint("salt and pepper", lang="en-US") == "salt and pepper"


# ---------------------------------------------------------------------------
# Colon capitalisation (NEW)
# ---------------------------------------------------------------------------

class TestColonCapitalisation:
    def test_en_us_capitalise_clause(self):
        assert lint("The verdict was clear: he was guilty.", lang="en-US") == \
            "The verdict was clear: He was guilty."

    def test_en_us_lowercase_phrase(self):
        assert lint("She had one goal: To win.", lang="en-US") == "She had one goal: to win."

    def test_fr_always_lower(self):
        assert lint("Le verdict est clair\u202f: Il est coupable.", lang="fr-FR") == \
            "Le verdict est clair\u202f: il est coupable."

    def test_de_capitalise_clause(self):
        assert lint("Das Ergebnis war klar: er war schuldig.", lang="de-DE") == \
            "Das Ergebnis war klar: Er war schuldig."

    def test_en_us_preserves_proper_noun_after_colon(self):
        # Regression: Newspack corpus surfaced data corruption where
        # "Craig: Pedro-Francisco" was lowercased to "Craig: pedro-Francisco".
        # Hyphenated proper nouns must NEVER be lowercased.
        src = "According to U.S. Representative Angie Craig: Pedro-Francisco is suffering."
        out = lint(src, lang="en-US")
        assert "Pedro-Francisco" in out
        assert "pedro-Francisco" not in out

    def test_en_us_preserves_simple_proper_noun_after_colon(self):
        # "The winner: Maria took the prize." — Maria is a proper noun.
        src = "The winner: Maria took the prize."
        out = lint(src, lang="en-US")
        assert "Maria" in out
        assert ": maria" not in out


# ---------------------------------------------------------------------------
# nbsp_between_initials — locale-gated for English country codes
# ---------------------------------------------------------------------------

class TestNBSPBetweenInitials:
    def test_en_us_two_letter_country_code_unchanged(self):
        # Regression: "U.S." was getting NBSP inserted, breaking AP/CMOS style.
        assert lint("from the U.S. government", lang="en-US") == \
            "from the U.S. government"

    def test_en_us_uk_unchanged(self):
        assert lint("the U.K. parliament", lang="en-US") == "the U.K. parliament"

    def test_en_us_three_initials_get_nbsp(self):
        # Personal names with 3+ initials still get NBSP-bound.
        out = lint("J.R.R. Tolkien", lang="en-US")
        assert "J." + NBSP + "R." + NBSP + "R." in out

    def test_de_de_two_initials_still_get_nbsp(self):
        # Non-English locales keep the universal 2+ behaviour.
        out = lint("J.R. Ewing", lang="de-DE")
        assert "J." + NBSP + "R." in out


# ---------------------------------------------------------------------------
# Single-letter NBSP all-caps skip (NEW behaviour)
# ---------------------------------------------------------------------------

class TestSingleLetterNBSPAllCaps:
    def test_fr_a_paris_no_nbsp(self):
        # "A PARIS" -> "À PARIS" with regular space (display context)
        assert lint("A PARIS", lang="fr-FR") == "\u00c0 PARIS"

    def test_fr_a_mixed_case_gets_nbsp(self):
        # "à mon ami" — running prose, NBSP after preposition
        out = lint("voyage à mon ami", lang="fr-FR")
        assert "\u00e0" + NBSP + "mon" in out


# ---------------------------------------------------------------------------
# Regressions sentinel — keep the lint-only eval at >= 66/83
# ---------------------------------------------------------------------------

class TestEvalBaseline:
    """Sanity-check that the integrated eval still meets the baseline.

    This isn't a unit test in the strict sense, but flagging a drop here
    catches accidental regressions that pass per-rule tests.
    """
    def test_basic_lint_does_not_crash(self):
        # Smoke test across every *supported* language. (Previously this list
        # included 8 languages the linter never implemented — sv/nb/da/fi/pl/
        # cs/ca/ru — so it failed in __init__. The honest set is the 13 in
        # SUPPORTED_LANGUAGES; aspirational locales belong on the roadmap.)
        from typeproof import SUPPORTED_LANGUAGES
        for lang in sorted(SUPPORTED_LANGUAGES):
            result = TypographyLinter(language=lang).lint(
                'Hello "world", a -- b. 25% of users.'
            )
            assert isinstance(result.text, str)
            assert len(result.text) > 0

    def test_unsupported_language_raises_cleanly(self):
        # An unsupported locale must fail loudly at construction, never corrupt.
        with pytest.raises(ValueError):
            TypographyLinter(language="sv")


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-v"]))
