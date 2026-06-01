# Typeproof — Adoption Roadmap

_Reconciles the original improvement notes and solution roadmap with what is actually in the repo, then re-frames the work around the real goal: **make Typeproof easy to adopt, depending on who you are.**_

_Last reconciled against the codebase: 2026-06-01._

---

## 0. Why this document exists

The earlier roadmap was sequenced by **maintainer effort** — a sensible lens for deciding what to build next. But the stated goal is different: _people should be able to adopt this with ease, depending on their role._ That is a different axis. An effort-sequence tells the maintainer what to do next; a **role map** tells an arriving stranger “here is your five-minute path.”

Before either is useful, the project has to stop contradicting itself. An audit of the repo against the three planning documents (the notes, the roadmap, and `CLAUDE.md`) surfaced a set of gaps that are pure trust failures — the cheapest and highest-leverage work, and none of it appeared on the original roadmap because the roadmap assumed a project that does not quite exist.

### What the audit found

| Claim | Notes/Roadmap | `CLAUDE.md` | `README.md` | `wp-plugin/readme.txt` | Demo site | **Reality (schema + code)** |
|---|---|---|---|---|---|---|
| Language variants | “21 locales / 46×21” | 13 | **9** | “20+” | “21” | **13** (`SUPPORTED_LANGUAGES`) |
| Deterministic rules | — | ~40 | — | “50+” | “46+” | **34 methods** (36 dispatch sites) |
| Eval cases | “83-case” | — | — | — | — | **83** ✓ (the one figure that matched) |

Five documents quoted five different language counts. The README simultaneously **under-claims** (lists 9, ships 13 — Sardinian, both Dutch variants, and Romanian ship undocumented) and the plugin/demo **over-claim** (“20+”, “21”). The “21” is not arbitrary: it is baked into the test suite’s smoke test (`test_basic_lint_does_not_crash` asserts support for 21 languages; the linter cleanly rejects the 8 it does not implement, so the test fails). The inflated number leaked from aspiration into code.

### The three trust traps (fix before any feature)

1. **The README front door is broken.** It documents a `schema/` `pipeline/` `data/` layout that does not exist — everything lives at the repo root. Every quick-start command (`python pipeline/generate_dataset.py`) ends in `No such file`. A developer’s first 60 seconds fail.
2. **CI is green-washed.** `.github/workflows/ci.yml` runs the linter and schema-parity suites with `continue-on-error: true`. Current real state: **45 of 88 linter tests fail, 5 of 7 parity tests fail.** The badge says green; the repo is red. The moment an evaluator runs `pytest`, the project loses the room. (Most failures are unimplemented Batch 4/5 features — legitimately `xfail` — but they must be _declared_ as such, not hidden.)
3. **The WordPress plugin looks shippable and is not.** `wp-plugin/` shells out to `typeproof.py` via `proc_open` and `readme.txt` states “Requires Python 3.8+ available on the server.” No WordPress.org host and almost no managed host permits that. It will silently do nothing on real hosting — a one-bad-experience uninstall (premortem #1 + #7 fused).

### What is already built (and the roadmap undersold)

- **`typeproof.py`** — a real ~2,050-line deterministic linter: a code-exclusion **masker** (`_mask_exclusions`/`_unmask_exclusions`), 34 rules, `LintResult`/`Correction` with `to_dict()`, and `_highlight_diff()`. → Roadmap item #4 (“diff transparency in the API”) is **essentially already done**; it needs documenting, not building.
- **`correct.py`** — the model CLI (Layer 2).
- **`font_gate.py`** — a font-awareness gate (Layer 3) that already guarantees “never emit a glyph the font can’t render; a visible imperfect character beats tofu.” This is a genuine, **unmarketed safety asset** the positioning work should sell.
- **`wp-plugin/`** — a full Gutenberg integration (REST controller, settings, sidebar JS) — real, but with the unshippable runtime above.

So several Phase-2/3 items are partly done, in the wrong shape, or free. The roadmap’s spirit holds; its inventory was stale.

---

## 1. Pushback on the source documents

Kept here so the reasoning is not lost.

- **The roadmap’s most important item is missing: reconcile reality.** Every roadmap item is a feature; none addresses the self-contradiction above. The broken README + green-washed CI is the cheapest trust win in the whole plan and it was unlisted. → Added as **Phase 0.5** below.
- **“21 locales / 46×21 matrix” over-states the surface.** It is 13 variants and 34 rules. Right-sizing makes the native-validation program tractable and honest, and shrinks the perceived maintenance burden (premortem #6).
- **Item #4 (diff transparency) is already built** — budget it as documentation, not work.
- **Items #9/#10 (JS core + Gutenberg plugin) are mis-framed as greenfield.** A plugin exists; the work is replacing its runtime, and _loudly relabelling the current one_ so it stops looking done.
- **The notes underweight Layers 2 & 3.** “Flag-don’t-fix” (#2) is partly a _demotion-and-wiring_ job on existing code, and `font_gate.py` is a safety selling point the positioning section omits.
- **Agreements (unchanged):** distribution beats more rules; flag-don’t-fix as posture; the masker as the safety floor (confirmed: no idempotency / “never-corrupt” / strict mode exists yet — item #1 is genuinely unbuilt and correctly first); freeze rule-count scope.

---

## 2. The role map — adoption paths

The goal restated as five concrete on-ramps. Each names the persona, the promise, the artifacts that serve them, and the gap today.

### 2.1 The designer / curious visitor
- **Promise:** “See it work in 30 seconds.” Land on the demo, paste text, watch the green diff.
- **Serves them:** `docs/index.html` (live demo), an honest README.
- **Gap:** demo claims 21 languages / 46+ rules (over-claim). The experience itself is strong — the live diff is the best part of the project.
- **Action:** correct the language count to 13; let João decide the rules-count framing (see §4). No build.

### 2.2 The developer / integrator
- **Promise:** “Lint typography in my pipeline in one command.” `pip`/clone, run the CLI or import the library, wire it into CI.
- **Serves them:** `typeproof.py` (library + `--json` CLI), a working README, `.typeproofrc` config, a CI Action + pre-commit hook, documented diff API.
- **Gap:** README is broken; no config file; no published CI Action; no documented stable API surface.
- **Actions:** README rewrite (Phase 0.5); `.typeproofrc` (#6); CI Action + pre-commit (#8); document the already-built `to_dict()` diff API (#4).

### 2.3 The native-speaker validator
- **Promise:** “Tell us a rule is wrong without writing Python.” Submit a failing example (input → expected output); a maintainer turns it into a rule/test.
- **Serves them:** `CONTRIBUTING.md` with a no-code contribution path, an issue template, per-locale maturity badges, a golden corpus per locale.
- **Gap:** none of this exists. The people who can validate `pt-PT` or `ro-RO` mostly do not write Python — today they have no door. **This is the only on-ramp that must never require code**, and it is the one most directly tied to the breadth-credibility risk (premortem #3).
- **Actions:** `CONTRIBUTING.md` + issue template (Phase 0.5, started); maturity badges + golden corpus (#11).

### 2.4 The WordPress publisher
- **Promise:** “Install a plugin; my posts get correct typography.” Activate, pick locale, done.
- **Serves them:** the Gutenberg plugin.
- **Gap:** the plugin requires server-side Python — unshippable to normal hosting; currently advertised as if it were not.
- **Actions:** **now —** relabel the plugin “experimental / requires server-side Python” so no one is misled (planned, not yet actioned — see §3). **Later —** JS/WASM (or PHP) deterministic core (#9) → a real plugin (#10).

### 2.5 The enterprise evaluator
- **Promise:** “Prove it is safe and measurably better than doing nothing.” Read the benchmark, confirm strict-mode never corrupts, confirm the model never silently writes.
- **Serves them:** public benchmark, strict/“never-corrupt” mode + idempotency invariant, flag-don’t-fix posture, honest CI.
- **Gap:** CI lies; no strict mode / idempotency guarantee; benchmark is an internal 83-case eval, not a standing public suite.
- **Actions:** de-green-wash CI (Phase 0.5); harden the safety core (#1); flag-don’t-fix wiring (#2); public benchmark (#5).

---

## 3. The plugin plan (to action later — detailed per your call)

The plugin is left untouched this pass; this is the spec for when it is picked up.

**Problem.** `wp-plugin/includes/class-ti-linter.php` runs `proc_open("python3 typeproof.py --json", …)`, piping post content through stdin. This requires a Python 3 interpreter on the web server with the repo present and `proc_open` enabled — three conditions that fail on WordPress.org-listed shared hosting, most managed WP hosts, and any locked-down environment. The plugin therefore _looks_ complete (REST controller, settings UI, Gutenberg sidebar) but cannot be distributed.

**Step 0 — honesty (cheap, do first when picked up).**
- Add a prominent notice to `wp-plugin/readme.txt` and the plugin header: “Experimental. Requires server-side Python 3.8+. Not yet suitable for WordPress.org or standard managed hosting.”
- Fix the `readme.txt` counts: “20+ languages / 50+ rules” → **13 language variants / 34 rules**, with the maturity-badge caveat for unverified locales.
- Add a graceful-degradation path: if `proc_open`/python is unavailable, the plugin should detect it on activation and surface an admin notice rather than failing silently on save (premortem #7).

**Step 1 — the real fix (the “big rock”, roadmap #9).** Port the deterministic core so it runs without server-side Python. Two viable targets:
- **PHP port** — runs everywhere WordPress runs, no new runtime, no asset weight. The substitution rules (quotes, dashes, symbols, fractions, currency) are data-driven and can be **generated from the YAML schema** into PHP just as they are into Python — reusing the schema-as-source-of-truth architecture. The algorithmic rules (NFC, the nested-quote stack parser, the masker) need a genuine PHP re-implementation; the masker is the riskiest (premortem #7) and must be fuzzed against the Python reference.
- **JS/WASM port** — required anyway for the browser/as-you-type editor experience (roadmap #12) and for client-side Gutenberg. Heavier; Pyodide (~MBs) is a non-starter inside an editor, so a JS re-implementation of the algorithmic core + schema-generated substitution layer is the right call.
- **Recommendation:** PHP first (unblocks the plugin with the least new surface and lowest asset cost), JS second (unblocks as-you-type + LSP). Either way, budget **parity tests**: run the public benchmark against _both_ runtimes so Python, PHP, and JS never diverge silently. `test_schema_parity.py` is the seed of this harness.

**Step 2 — the plugin proper (roadmap #10).** With a no-Python core: format/filter on save or publish, locale read from post/site language, publish-time UX, and the sidebar diff already prototyped in `assets/js/ti-sidebar.js`. Meaningful work, but not research-grade once the core exists.

---

## 4. Sequenced plan

Scored as in the original roadmap: **R**elevance (1 minor → 5 load-bearing), **D**ifficulty (1 trivial → 5 major).

### Phase 0.5 — Make the front door honest _(days — the missing prerequisite)_

| Item | R | D | Status |
|---|:-:|:-:|---|
| Rewrite README to real layout + working quick-start | 5 | 1 | **in progress** |
| Standardise to 13 variants / 34 rules across all docs (+ maturity-badge concept) | 4 | 1 | **in progress** |
| De-green-wash CI: fix real regressions, `xfail` TODO-batch tests, report truthfully | 5 | 2 | **in progress** |
| `CONTRIBUTING.md` with Python-free native-validator path + issue template | 4 | 1 | **in progress** |
| Plugin: relabel experimental + fix counts (per §3 Step 0) | 4 | 1 | planned (not this pass) |
| Demo: correct “21 → 13 language variants”; flag rules-count to João | 3 | 1 | partial |

> Rationale: distribution built on an untrustworthy, self-contradicting core just distributes the contradiction. None of this adds a feature; all of it protects the asset already in hand.

### Phase 1 — Earn credibility _(1–2 months)_

| # | Item | R | D | Notes vs. reality |
|:-:|---|:-:|:-:|---|
| 1 | Harden the safety core (idempotency invariant, strict “never-corrupt” default, **fuzz the masker**) | 5 | 2 | Confirmed unbuilt. The masker exists; the guarantees around it do not. |
| 2 | Model: flag-don’t-fix posture | 5 | 2 | Partly demotion-and-wiring on `correct.py`/`font_gate.py`, not greenfield. |
| 3 | Positioning: “typographic linter for synthetic text”, local-first, **sell the font gate** | 3 | 1 | Copy only. Add `font_gate.py` as a safety selling point. |
| 4 | Document the diff API | 3 | 1 | **Already built** (`to_dict`, `_highlight_diff`) — document, don’t build. |
| 5 | Public benchmark (grow the 83-case eval into a standing suite) | 4 | 3 | Seed exists (`eval_typography.py`, 83 cases). |
| 6 | `.typeproofrc` config + per-rule/per-locale toggles | 4 | 2 | Prereq for #7. |
| 7 | Split editorial-style from typographic-correctness (objective on, contestable off) | 4 | 2 | Several failing tests _are_ the contestable Batch-4 rules — keep them off by default. |
| 8 | CI Action + pre-commit hook (`--check`, non-zero exit) | 4 | 2 | Runs existing Python; cheapest real distribution win. |

### Phase 2 — Reach the web _(multi-month — the big rock)_

| # | Item | R | D | Notes vs. reality |
|:-:|---|:-:|:-:|---|
| 9 | JS/WASM **(or PHP)** deterministic core | 5 | 5 | See §3 Step 1. PHP unblocks the plugin soonest. |
| 10 | Gutenberg plugin (shippable) | 5 | 4 | Scaffolding exists; needs the no-Python core + relabel of the current prototype. |

### Phase 3 — Trust at scale & ecosystem _(ongoing, parallel)_

| # | Item | R | D | Notes vs. reality |
|:-:|---|:-:|:-:|---|
| 11 | Native-validation program (maturity badges + golden corpus + failing-example contribution) | 4 | 3 | Serves §2.3. Badges trivial; corpus + flow are the work. |
| 12 | Editor / LSP extension (inline green-diff) | 3 | 4 | Benefits from #9’s JS core. |
| 13 | Schema as citable spec / interchange format | 3 | 3 | The durable asset; discipline of versioning, not code. |

---

## 5. If you only do the next three things

1. **Phase 0.5 — make the front door honest.** README, CI truth, counts, a contributor door. Days, not weeks. Nothing else is trustworthy until this lands.
2. **#1 + #2 — harden the core and make the model flag-don’t-fix.** Makes it _safe to recommend_.
3. **§3 Step 1 (PHP core) → #10 (plugin).** The one bet that makes “for the multilingual web” true.

Everything else is multiplier, not foundation. **Freeze rule-count scope until the plugin ships** — the rules are the part fonts can’t do and the part that is already sound; they are not where the project lives or dies.
