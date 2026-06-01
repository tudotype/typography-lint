"""Pytest configuration — the honest ledger of not-yet-implemented behaviour.

The test suites describe where Typeproof is *going*, not only where it is. Tests
for rules that have no backing implementation yet are marked ``xfail`` here —
centralised, with a reason, so the suite reports the truth (rather than being
hidden behind ``continue-on-error`` in CI). When a feature lands, delete its
entry and the test starts gating for real.

Each entry maps a test id (the part after ``<file>.py::``) to the reason it is
expected to fail. Grouped by cause. See docs/adoption-roadmap.md §4.
"""

import pytest

# Batch 4 — locale-branched punctuation (colon caps, serial comma, footnotes,
# in/out-of-quote punctuation, currency spacing, Spanish inverted marks,
# locale-branched percent spacing). No backing rule exists yet.
_BATCH4 = "Batch 4 (locale-branched punctuation) not yet implemented — see docs/adoption-roadmap.md §4"

# Extended diacritic correction beyond the French set already shipped.
_DIACRITIC = "Extended diacritic correction (non-FR capital accents, IT apostrophic acute, A→À) not yet implemented — see docs/adoption-roadmap.md §4"

# Rules that are simply not built yet.
_NOTIMPL = "Rule not yet implemented (planned) — see docs/adoption-roadmap.md §4"

# A locale outside the 13 supported variants.
_UNSUPPORTED = "Locale not among the 13 supported variants — see docs/adoption-roadmap.md §2"

# A convention the schema does not (yet) encode; implementing it would mean
# inventing a rule, which CLAUDE.md forbids without a schema entry.
_SCHEMA_AMBIG = "Exemption not encoded in the schema (would require inventing a convention) — see docs/adoption-roadmap.md"

# Parity tests that assert a schema metadata/dispatch layer the YAML does not
# yet define (name/version/license/dispatch_tables/lint_method annotations).
_PARITY_META = "Schema does not yet define the metadata/dispatch annotation layer this test asserts — see docs/adoption-roadmap.md §4"

XFAILS = {
    # --- Batch 4 -------------------------------------------------------------
    "TestSerialComma::test_en_us_enforce": _BATCH4,
    "TestSerialComma::test_fr_fr_remove": _BATCH4,
    "TestSerialComma::test_de_de_remove": _BATCH4,
    "TestColonCapitalisation::test_en_us_capitalise_clause": _BATCH4,
    "TestColonCapitalisation::test_en_us_lowercase_phrase": _BATCH4,
    "TestColonCapitalisation::test_fr_always_lower": _BATCH4,
    "TestColonCapitalisation::test_de_capitalise_clause": _BATCH4,
    "TestFootnotePlacement::test_en_us_after_period": _BATCH4,
    "TestFootnotePlacement::test_de_de_after_period": _BATCH4,
    "TestFootnotePlacement::test_fr_fr_before_period": _BATCH4,
    "TestQuotePunctuationPlacement::test_en_us_period_inside": _BATCH4,
    "TestQuotePunctuationPlacement::test_en_gb_period_outside": _BATCH4,
    "TestQuotePunctuationPlacement::test_de_de_period_outside": _BATCH4,
    "TestCurrency::test_en_us_strip_space": _BATCH4,
    "TestCurrency::test_pt_pt_after_with_nbsp": _BATCH4,
    "TestCurrency::test_fr_fr_after_with_nbsp": _BATCH4,
    "TestCurrency::test_nl_nl_before_with_nbsp": _BATCH4,
    "TestSpanishInverted::test_question_mark": _BATCH4,
    "TestSpanishInverted::test_exclamation": _BATCH4,
    "TestSpanishInverted::test_mid_paragraph_question": _BATCH4,
    "TestSpanishInverted::test_lexical_accent_increible": _BATCH4,
    "TestPercent::test_fr_nnbsp": _BATCH4,
    "TestPercent::test_de_nbsp": _BATCH4,
    # --- Extended diacritics --------------------------------------------------
    "TestItalianApostrophic::test_perche": _DIACRITIC,
    "TestItalianApostrophic::test_capital_perche": _DIACRITIC,
    "TestItalianApostrophic::test_e_verb": _DIACRITIC,
    "TestItalianApostrophic::test_caffe": _DIACRITIC,
    "TestCapitalAccents::test_es_mexico": _DIACRITIC,
    "TestCapitalAccents::test_es_bogota": _DIACRITIC,
    "TestCapitalAccents::test_it_citta": _DIACRITIC,
    "TestCapitalAccents::test_pt_agua": _DIACRITIC,
    "TestSingleLetterNBSPAllCaps::test_fr_a_paris_no_nbsp": _DIACRITIC,
    # --- Not implemented yet --------------------------------------------------
    "TestArrows::test_right_arrow_in_prose": _NOTIMPL,
    "TestArrows::test_left_arrow_in_prose": _NOTIMPL,
    "TestArrows::test_left_right_arrow": _NOTIMPL,
    "TestWidowPrevention::test_opt_in_joins_last_pair": _NOTIMPL,
    "TestWidowPrevention::test_short_paragraph_skipped": _NOTIMPL,
    "TestQuotes::test_pt_pt_nested_quotes": _NOTIMPL,
    "TestQuotes::test_en_us_nested_quotes": _NOTIMPL,
    "TestDashes::test_fr_em_with_nnbsp": _NOTIMPL,
    "TestDashes::test_de_spaced_en_dash": _NOTIMPL,
    # --- Unsupported locale ---------------------------------------------------
    "TestSingleLetterNBSP::test_pl_w": _UNSUPPORTED,
    # --- Schema-ambiguous -----------------------------------------------------
    "TestNBSPBetweenInitials::test_en_us_two_letter_country_code_unchanged": _SCHEMA_AMBIG,
    "TestNBSPBetweenInitials::test_en_us_uk_unchanged": _SCHEMA_AMBIG,
    # --- Schema parity (metadata/dispatch layer not yet defined) --------------
    "test_every_lint_method_is_referenced": _PARITY_META,
    "test_dispatch_table_locales_are_declared": _PARITY_META,
    "test_schema_has_required_top_level_keys": _PARITY_META,
    "test_metadata_values": _PARITY_META,
    "test_examples_round_trip_soft": (
        "Round-trip soft floor not yet met: dominated by unimplemented Batch 4/5 "
        "example rules (currency, degree, inverted punctuation). See docs/adoption-roadmap.md §4"
    ),
}


def pytest_collection_modifyitems(config, items):
    for item in items:
        # nodeid looks like "test_typeproof.py::TestArrows::test_x" — drop the file part
        key = item.nodeid.split("::", 1)[-1]
        reason = XFAILS.get(key)
        if reason is not None:
            item.add_marker(pytest.mark.xfail(reason=reason, strict=False))
