# Contributing to Typeproof

There are several ways to help, depending on who you are. Find your path — you do **not** need to be able to do everything below to contribute something valuable.

---

## I’m a native speaker — a rule is wrong (or missing) for my language

**This is the most valuable contribution, and it needs no code.**

Typeproof covers 13 language variants. Many of their rules were sourced from grammars and style guides and cross-referenced, but **not yet verified by a native speaker** (see the maturity table in the [README](README.md#language-coverage)). If a correction looks wrong for your language — or a correction that *should* happen doesn’t — you are exactly the person we need.

You don’t have to touch Python or YAML. Just open an issue with a **failing example**:

> **Locale:** `pt-PT`
> **Input (as it is):** `Ele disse "ola".`
> **Expected (as it should be):** `Ele disse «olá».`
> **Why:** Portuguese uses guillemets, and “olá” needs the acute accent.

That’s it. A maintainer turns it into a schema rule, a generated training example, and a regression test. Use the **“Locale correction report”** issue template if available.

The golden rule of this project: **we never invent a typographic convention.** If you can point to a style authority (a national orthography body, a major style guide), include it — it goes straight into the rule’s `notes`.

---

## I’m a developer — I want to fix or add a rule

The deterministic linter lives in [`typeproof.py`](typeproof.py); the source of truth is [`typography-system-schema.yaml`](typography-system-schema.yaml).

1. **Read [`CLAUDE.md`](CLAUDE.md)** — it documents the schema conventions and the 80/20 deterministic-vs-model split. Follow them.
2. **Add the rule to the schema first.** Every rule needs a `description` and either a `resolves_to` primitive or a `rule` field. Language-specific rules need ≥ 1 `examples` entry with `raw` and `correct`. If a convention is contestable (house style, not typographic fact), mark it and default it **off**.
3. **Implement it** as a `_rule_*` method on `TypographyLinter` and wire it into `lint()`. Bias to **under-correction** near anything code-shaped — the masker is the most safety-critical component; when in doubt, do nothing.
4. **Add a test** in [`test_typeproof.py`](test_typeproof.py). If you’re implementing a feature that currently has an `xfail` entry in [`conftest.py`](conftest.py), **delete that entry** so the test starts gating for real.
5. **Run the suite:** `python3 -m pytest test_typeproof.py test_schema_parity.py`. It must be green (passing + xfailed, zero failed) before you open a PR.
6. **If you changed the schema,** regenerate the dataset: `python3 generate_dataset.py` (do not hand-edit the JSONL — it’s a build artifact).

### What “green” means here
CI gates honestly. Tests for not-yet-built rules are declared `xfail` in `conftest.py` with a reason, **not** hidden behind `continue-on-error`. A new genuine failure fails CI. Don’t paper over a real failure with an `xfail` — `xfail` is for *not-yet-implemented*, not *broken*.

---

## I want to add a whole language

See [README → Adding a language](README.md#adding-a-language). In short: inherit from the closest parent locale, override only what differs, add ≥ 3 example pairs per applicable rule, regenerate. New locales ship as **“LLM-sourced, unverified”** until a native validates them — don’t market an unverified locale as production-ready (that’s a credibility liability, not breadth).

---

## Commit conventions

Prefix by area (from `CLAUDE.md`):

- `schema:` — YAML changes
- `pipeline:` — generator / training / eval scripts
- `data:` — regenerated datasets
- `docs:` — documentation, README, the demo site

And: **use real typography in everything you write here** — curly quotes, proper dashes. We practice what we preach.

---

## Roadmap & scope

Before proposing something large, check [docs/adoption-roadmap.md](docs/adoption-roadmap.md). Rule-count scope is intentionally **frozen** until the project is installable where people work — the rules are already the sound part; distribution and trust are where help is most needed.
