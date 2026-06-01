"""Safety invariants — the floor everything else stands on.

These tests encode the premortem's hardest requirements as executable guarantees:
idempotency, never corrupting code-shaped content (the masker), and a strict
"never-corrupt" mode. An auto-corrector dies on a single bad output; these are
the tests that catch that class of failure before it ships.
"""

import random
import string

import pytest

from typeproof import TypographyLinter, SUPPORTED_LANGUAGES

# A spread of realistic prose with the constructs that tend to break correctors:
# quotes, dashes, math, percentages, ranges, URLs, code, paths, version strings.
CORPUS = [
    'She said "hello" -- it\'s a test... 25% off, see pp. 10-20.',
    "The result: 10 - 3 = 7, and 3 x 4 = 12.",
    "Il a dit « merci » et 1+2. C'est l'évidence.",
    'Er sagte "danke" und ging. Strasse -> Straße?',
    "O preço é 10€, a página 5-10, e o 1o lugar.",
    "Visit https://example.com/a-b?x=1 and run `npm run build -- --watch`.",
    "Edit /usr/local/bin and set VERSION=1.2-rc3 in config.",
    "A list: a, b, and c. Then -5 degrees. Quote: 'single'.",
    "Email a@b.com, ratio 16:9, time 10:30-11:00.",
    "No changes needed here.",
    "",
    "   ",
    "Multiple   spaces    collapse.",
]


@pytest.mark.parametrize("lang", sorted(SUPPORTED_LANGUAGES))
def test_idempotent(lang):
    """Run twice == run once. lint(lint(x)) must equal lint(x)."""
    lt = TypographyLinter(language=lang)
    for s in CORPUS:
        once = lt.lint(s).text
        twice = lt.lint(once).text
        assert once == twice, f"[{lang}] not idempotent on {s!r}: {once!r} -> {twice!r}"


@pytest.mark.parametrize("lang", sorted(SUPPORTED_LANGUAGES))
def test_idempotent_strict(lang):
    """Idempotency must also hold in strict mode."""
    lt = TypographyLinter(language=lang, strict=True)
    for s in CORPUS:
        once = lt.lint(s).text
        assert once == lt.lint(once).text, f"[{lang}] strict not idempotent on {s!r}"


# --- Masker: code-shaped content must survive byte-for-byte ------------------

CODE_FRAGMENTS = [
    "https://example.com/path-to/page?a=1&b=2",
    "`inline code with \"quotes\" and -- dashes`",
    "```\nblock code 10-20 and 3 x 4\n```",
    "/usr/local/bin/python3.12",
    "VERSION=1.2-rc3",
    "obj->method()",
    "<a href=\"https://x.io\">link</a>",
]


@pytest.mark.parametrize("frag", CODE_FRAGMENTS)
def test_masked_fragments_unchanged(frag):
    """A code-shaped fragment embedded in prose must come back unchanged."""
    for lang in ("en-US", "fr-FR", "de-DE", "pt-PT"):
        text = f'Here is something: {frag} -- and "more" prose...'
        out = TypographyLinter(language=lang).lint(text).text
        assert frag in out, f"[{lang}] masker corrupted {frag!r}: {out!r}"


def test_masker_fuzz():
    """Fuzz: random code-shaped tokens embedded in random prose must survive.

    Deterministic seed (no Math.random/Date in scripts; explicit seed here) so
    failures are reproducible.
    """
    rnd = random.Random(20260601)
    alnum = string.ascii_letters + string.digits
    def tok(n):
        return "".join(rnd.choice(alnum) for _ in range(n))

    for _ in range(400):
        # Build a code-shaped token the masker should protect.
        kind = rnd.choice(["url", "inline", "path", "version"])
        if kind == "url":
            frag = f"https://{tok(5)}.com/{tok(3)}-{tok(3)}?q={tok(2)}"
        elif kind == "inline":
            frag = f"`{tok(3)} - {tok(2)}...{tok(2)}`"
        elif kind == "path":
            frag = f"/{tok(3)}/{tok(4)}-{tok(2)}/{tok(3)}.py"
        else:
            frag = f"v{rnd.randint(0,9)}.{rnd.randint(0,9)}-rc{rnd.randint(0,9)}"

        prose = f'The {tok(4)} said "{tok(3)}" -- {frag} -- and {tok(2)}... done.'
        lang = rnd.choice(sorted(SUPPORTED_LANGUAGES))
        out = TypographyLinter(language=lang).lint(prose).text
        assert frag in out, f"[{lang}] masker fuzz corrupted {frag!r} in {prose!r} -> {out!r}"


# --- Strict mode: skip inference, keep unambiguous --------------------------

def test_strict_skips_inferred_dash():
    """Strict mode must not infer a dash from a spaced hyphen."""
    out = TypographyLinter(language="en-US", strict=True).lint("foo - bar").text
    assert "—" not in out and "–" not in out


def test_strict_skips_range_and_multiplication():
    out = TypographyLinter(language="en-US", strict=True).lint("10-20 and 3 x 4").text
    assert "–" not in out          # no inferred range dash
    assert "×" not in out          # no inferred multiplication sign


def test_strict_still_fixes_unambiguous():
    """Strict mode still applies the safe substitutions (quotes, ellipsis)."""
    out = TypographyLinter(language="en-US", strict=True).lint('She said "hi"...').text
    assert "“hi”" in out
    assert "…" in out


def test_strict_is_a_subset_of_normal():
    """Anything strict changes, normal must also change (strict ⊆ normal)."""
    for lang in sorted(SUPPORTED_LANGUAGES):
        strict = TypographyLinter(language=lang, strict=True)
        normal = TypographyLinter(language=lang)
        for s in CORPUS:
            s_out = strict.lint(s).text
            n_out = normal.lint(s).text
            # Re-linting the strict output with the full linter should reach the
            # same place as linting the original: strict makes a subset of edits.
            assert normal.lint(s_out).text == n_out, (
                f"[{lang}] strict diverged from normal on {s!r}"
            )
