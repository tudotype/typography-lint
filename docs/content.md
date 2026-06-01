# Typeproof -- Rule Reference: All User-Visible Text

---

## Cover

<!-- section.cover -->

**Logo:** [Tudotype SVG wordmark]
<!-- div.cover-logo > svg -->

**Eyebrow:** Typeproof
<!-- div.cover-eyebrow -->

**H1:** Typeproof.
<!-- h1 — "Lint." has amber-colored period via span.title-accent -->

**H2:** Language-aware typographic correction for the multilingual web
<!-- h2 -->

**Description (p.cover-desc):** Indexing the rules for everyone before they're forgotten by a flood of synthetic text. 46 deterministic rules across 13 language variants, encoded as executable infrastructure.
<!-- p.cover-desc -->

**Meta pills:**
- v1.0
- May 2026
- 46+ rules
- open-source
<!-- span elements inside div.cover-meta -->

**Meta text:** Typeproof. A type & AI endeavour by João Miranda
<!-- plain text in div.cover-meta -->

---

## Premise

<!-- section.premise -->

**Lead (p.premise-lead):** The growing volume of synthetic text is changing how we think, how we write but also degrading how good writing should look like on the page.

**Body paragraph 1 (p):** Every day, more machine-generated text enters circulation. Most of it is typographically illiterate: straight quotes where curly quotes belong, hyphens masquerading as dashes, no awareness of locale conventions. As adoption grows, and more synthetic text gets published, these errors compound due to the flattening of the references we rely on. The good points of reference get harder to find due to a combination of human written data scarcity getting swallowed by the volume of synthetic text being generated. Although partially, it includes this text too. 

**Body paragraph 2 (p):** It doesn't help that English hegemony, a language that already differs between english-speaking countries, is flattening our ability to write natively. French spacing rules vanish. Portuguese guillemets become American curly quotes. German low-high quotation marks are replaced by English ones. The typographic DNA of each language erodes silently, one API call at a time.

**Body paragraph 3 (p):** This project exists because someone has to write the rules down and share with the community before they're forgotten. Not as documentation that drifts from practice, but as executable infrastructure: a schema that generates training data, a linter that enforces conventions, a model that learns the judgement calls no lookup table can make.

---

## The Journey

<!-- section.journey -->

**Eyebrow:** The Journey
<!-- div.journey-eyebrow -->

### The Spark
<!-- details.journey-card > summary.accordion-trigger -->

**Accordion icon:** +
<!-- span.accordion-icon -->

**Paragraph 1:** It started with an internal conversation about the em dash. A colleague triggered a conversation about how it should be used, what the conventions are and whether Automattic should standardise. People from different teams, different countries, different editorial traditions weighed in. Everyone had an opinion about a single character.

**Paragraph 2:** Following that thread meant following the em dash across borders. American English uses it without spaces. British English prefers a spaced en dash. Portuguese uses travessao for dialogue. French uses tiret with non-breaking spaces. The same function – a parenthetical pause – expressed differently in every language WordPress serves.

**Paragraph 3:** No good system existed. Gutenberg did basic smart quotes, English-only. Grammarly and ProWritingAid barely touched typographic correctness. Translation tools carried source-language conventions into target languages. I decided to build the infrastructure as an experiment with ML. The global impact of Automattic products, including its core contributions to WordPress, made this experiment even more relevant, as there's a great opportunity to do _the good thing_ and promote our open-source ethos to share this widely. 

### The Architecture
<!-- details.journey-card > summary.accordion-trigger -->

**Accordion icon:** +

**Paragraph 1:** The key insight was the 80/20 split. Most typographic corrections are deterministic – replacing straight quotes with curly quotes is a lookup operation. But some require genuine judgment: is this dash a parenthetical or a range? Should the colon capitalise what follows? Does this abbreviation need a period in this locale?

**Paragraph 2:** So we built two layers. Layer 1 is a pure-Python lint library: 46+ rules, 13 language variants, zero ML dependencies. It handles the deterministic 80%. Layer 2 is a fine-tuned model trained from a YAML schema that serves as the single source of truth. The schema describes rules; the generator translates them into training examples. When the schema changes, regenerate. The YAML never knows about edge cases; the Python handles them.

**Paragraph 3:** Three layers total: **Lint → Model → Font Gate**. The font gate ensures the corrected output is actually renderable in the target typeface. No missing glyphs. No weird glyph replacements. No tofu.

### The Data Lesson
<!-- details.journey-card > summary.accordion-trigger -->

**Accordion icon:** +

**Stat 1 (div.journey-stat):** 1/83
**Stat 1 label (div.journey-stat-label):** v1 exact matches

**Stat 2 (div.journey-stat):** 22/83
**Stat 2 label (div.journey-stat-label):** v2 exact matches

**Paragraph 1:** v1 trained on 3,292 pairs including 815 detection and explanation pairs. Those pairs taught the model to *explain* typography instead of *correcting* it. The instruction said 'correct the text' but the model had learned that output means explanation.

**Paragraph 2:** v2 changed three things: added 'Output only the corrected text, no explanation' to every instruction, removed the explanation pairs, and increased from 3 to 12 epochs. The result: 1/83 → 22/83 exact matches. The largest single jump in the entire project. The lesson was clear: **data quality beats data quantity**. And it beats model size, architecture, and hyperparameter tuning.

### The Ceiling
<!-- details.journey-card > summary.accordion-trigger -->

**Accordion icon:** +

**Stat 1 (div.journey-stat):** 27.7%
**Stat 1 label (div.journey-stat-label):** 3B ceiling (v3--v4)

**Stat 2 (div.journey-stat):** 50.6%
**Stat 2 label (div.journey-stat-label):** 7B breakthrough (v5)

**Paragraph 1:** Three iterations on Llama 3.2 3B plateaued at 23/83 (27.7%). Rank tuning, epoch tuning, template expansion – nothing moved the needle. The remaining failures clustered around one root cause: invisible Unicode characters. NBSP (U+00A0), NNBSP (U+202F), ZWNJ (U+200C) – characters the tokenizer couldn't represent at 3B scale.

**Paragraph 2:** Switching to Mistral 7B jumped to 42/83 (50.6%). The failure mode wasn't 'the model can't learn' – it was 'the tokenizer can't represent'. The lessons from v1–v4 (data quality, instruction format, correction-only templates) all transferred. The 7B model inherited them at the dataset level and added the one thing 3B couldn't provide: stable codepoint representations for invisible characters.

---

## Overview

<!-- section.overview -->

**Intro (p.overview-intro):** Typeproof is a fast, pure-Python deterministic typographic correction library. It handles the 80% of corrections that are straightforward substitution rules: curly quotes, locale-correct dashes, non-breaking spaces, diacritic integrity, and more. No ML dependencies.

### Supported Languages
<!-- h3 -->

#### Language Table
<!-- table.lang-table -->

| Column headers (th) | Code | Language | Group | Notes |
|---|---|---|---|---|
| | `en-US` | English (US) | Core 13 | CMOS style: em dash, serial comma, period inside quotes |
| | `en-GB` | English (UK) | Core 13 | Oxford style: spaced en dash, single-quote primary |
| | `pt-PT` | Portuguese (Portugal) | Core 13 | Guillemets with thin space; ordinals with .o/.a |
| | `pt-BR` | Portuguese (Brazil) | Core 13 | Curly doubles; inherits from pt-PT |
| | `fr-FR` | French | Core 13 | NNBSP before high punctuation; oe/ae ligatures |
| | `de-DE` | German | Core 13 | "low-high" quotes; SS capitalisation; DIN 5008 |
| | `it-IT` | Italian | Core 13 | Guillemets; apostrophic acute correction |
| | `es-ES` | Spanish (Spain) | Core 13 | ?/! insertion; interrogative accents |
| | `es-MX` | Spanish (Mexico) | Core 13 | Curly doubles; inherits from es-ES |
| | `nl-NL` | Dutch (Netherlands) | Core 13 | Curly doubles; currency before with NBSP |
| | `nl-BE` | Dutch (Belgium) | Core 13 | Same as nl-NL |
| | `ro-RO` | Romanian | Core 13 | Comma-below s/t |
| | `sc` | Sardinian | Core 13 | Guillemets; spaced en dash |
| | `sv` | Swedish | Nordic | Curly doubles; spaced en dash |
| | `nb` | Norwegian Bokmal | Nordic | Guillemets; spaced en dash |
| | `da` | Danish | Nordic | Low-high quotes; spaced en dash |
| | `fi` | Finnish | Nordic | Curly doubles; spaced en dash |
| | `pl` | Polish | Central/Eastern EU | Low-high quotes; em dash; single-letter NBSP |
| | `cs` | Czech | Central/Eastern EU | Low-high quotes; spaced en dash; single-letter NBSP |
| | `ca` | Catalan | Iberian | Guillemets; em dash (IEC) |
| | `ru` | Russian | Slavic/Cyrillic | Guillemets; spaced em dash (GOST) |

### Usage
<!-- h3 -->

**Code snippet label (b):** Python
**Code (pre.code-snippet):**
```
from typeproof import TypographyLinter
result = TypographyLinter(language="fr-FR").lint(text)
print(result.text)
```

**Code snippet label (b):** CLI
**Code (pre.code-snippet):**
```
python3 typeproof.py "He said \"hello\" and left." --lang en-US --diff
```

---

## Live Demo

<!-- section.demo-section > div.demo-panel -->

**H3:** Try It Live
<!-- h3 -->

**Subtitle (p.demo-subtitle):** Paste your own text. Select your language. See what changes. **Changed glyphs are highlighted in green** – the corrections most people never notice, made visible.

**Input label (span.demo-area-label):** Your text

**Textarea placeholder:** Paste text in any language...

**Textarea default content:**
```
He said "hello" and left... She replied "goodbye" -- then walked away.

The room was 1920x1080. It cost (c) 2024. See p. 42 for 3/4 of the data.

Click -> next, or go <- back.
```

**Language select options (select.demo-select):**
en-US (selected), en-GB, fr-FR, de-DE, pt-PT, pt-BR, it-IT, es-ES, es-MX, nl-NL, nl-BE, ro-RO, sc, sv, nb, da, fi, pl, cs, ca, ru

**Button (button.demo-btn):** Lint

**Output label (span.demo-area-label):** Corrected

**Output area (div.demo-output):** [dynamically generated]

**Corrections list (ul.demo-corrections):** [dynamically generated]

**Note (p.demo-note):** Showing a subset of rules (ellipsis, quotes, dashes, legal symbols, arrows, multiplication, fractions, apostrophes, double spaces). The full Python linter handles all 46+ rules including NBSP, diacritics, and accessibility.

**No-corrections message (JS):** No corrections needed -- your text is already typographically clean.

---

## Filter Bar

<!-- div.filter-bar -->

**Language row label (span.filter-label):** Language
**Language filter pills (button.filter-pill):**
Show All (active), Universal, en-US, en-GB, fr-FR, de-DE, pt-PT, pt-BR, it-IT, es-ES, es-MX, nl-NL, ro-RO, pl, sv, da, ru

**Count (span.filter-count):** 46 rules

**Category row label (span.filter-label):** Category
**Category filter pills (button.filter-pill):**
Normalization, Diacritics, Homoglyphs, Symbols, Quotes, Dashes, Spacing, Arrows, Structural, Abbreviations, Lang-Specific, Punctuation, Accessibility, Cleanup, Code Exclusion

---

## Rules

### 1. Normalization
<!-- h2.category #cat-normalization -->

**Category description (p.category-desc):** Safety-first preprocessing: canonical Unicode form and invisible character cleanup.

#### nfc_normalization -- NFC Unicode Normalization
<!-- span.rule-name / span.rule-title -->
**Description (p.rule-desc):** Applies Unicode NFC (Canonical Decomposition + Canonical Composition) to combine decomposed character sequences into their precomposed equivalents. Runs first, before any other rule.
**Language pills:** all languages
**Example:**
- Raw: cafe (with combining accent) -> Correct: cafe (precomposed e) | Unicode note: U+0065 U+0301 -> U+00E9

#### zero_width_chars -- Zero-Width Character Cleanup
**Description:** Strips stray ZWSP (U+200B) from prose; replaces it with a regular space when between two letters. Removes mid-text BOM (U+FEFF). Preserves ZWNJ (ligature suppression) and ZWJ (emoji).
**Language pills:** all languages
**Example:**
- Raw: hello[ZWSP]world -> Correct: hello world | Unicode note: ZWSP between letters -> space

---

### 2. Diacritics & Accents
<!-- h2.category #cat-diacritics -->

**Category description:** Restoring correct diacritical marks across Romance, Germanic, and Slavic languages.

#### romanian_diacritics -- Romanian s/t (Comma-Below)
**Description:** Replaces cedilla forms (s-cedilla, t-cedilla) with the correct comma-below forms (s-comma-below, t-comma-below) per Romanian Academy standard. Legacy fonts and keyboards often produce the wrong codepoint.
**Language pills:** ro-RO
**Examples:**
- ro-RO: scoala (cedilla) -> scoala (comma-below) | U+015F -> U+0219
- ro-RO: tara (cedilla) -> tara (comma-below) | U+0163 -> U+021B

#### french_ligatures -- French Orthographic Ligatures oe/ae
**Description:** Replaces decomposed "oe" with the mandatory French ligature oe in words like coeur, oeuf, boeuf. These are not stylistic ligatures -- they are distinct letters in French orthography.
**Language pills:** fr-FR
**Examples:**
- fr-FR: coeur -> coeur (with oe ligature)
- fr-FR: oeuvre -> oeuvre (with oe ligature)
- fr-FR: boeuf -> boeuf (with oe ligature)

#### french_capital_accents -- French Capital Accent Restoration
**Description:** Adds missing accents on all-caps French words per Academie francaise mandate. Also handles contextual "A" -> "A-grave" when followed by an all-caps word.
**Language pills:** fr-FR
**Examples:**
- fr-FR: ETAT -> ETAT (with E-acute)
- fr-FR: HOTEL -> HOTEL (with O-circumflex)
- fr-FR: A PARIS -> A-grave PARIS

#### italian_apostrophic_acute -- Italian Apostrophic Acute Correction
**Description:** Converts trailing apostrophe-as-accent to the correct precomposed accented letter. Common on keyboards without dead keys. Covers the "-che" family (acute e) and common grave-accented words.
**Language pills:** it-IT
**Examples:**
- it-IT: perche' -> perche (with e-acute)
- it-IT: e' importante -> e-grave importante
- it-IT: caffe' -> caffe (with e-grave)

#### spanish_interrogative_accent -- Spanish Interrogative/Exclamative Accents
**Description:** Restores the tilde on interrogative pronouns (donde, que, como, cual) at sentence start when the sentence ends with ? or !.
**Language pills:** es-ES, es-MX
**Example:**
- es-ES: Donde vives? -> ?Donde (with accents) vives?

#### spanish_lexical_accents -- Spanish Lexical Accent Restoration
**Description:** Corrects unambiguously wrong unaccented forms of common Spanish words. Conservative closed list: increible, rapido, musica, facil, telefono, America, etc.
**Language pills:** es-ES, es-MX
**Examples:**
- es-ES: Es increible -> Es increible (with i-acute)
- es-ES: musica rapido -> musica rapido (with accents)

#### capital_accents -- Capital Accent Preservation
**Description:** Restores accents on all-caps proper nouns and place names. Word-boundary matching only -- never fires on substrings. Sources: RAE, Treccani, Priberam.
**Language pills:** es-ES, es-MX, it-IT, pt-PT, pt-BR
**Examples:**
- es-ES: MEXICO -> MEXICO (with E-acute)
- it-IT: CITTA -> CITTA (with A-grave)
- pt-PT: AGUA -> AGUA (with A-acute)

---

### 3. Homoglyphs
<!-- h2.category #cat-homoglyphs -->

**Category description:** Visually similar but semantically wrong characters.

#### homoglyph_detection -- Homoglyph Detection & Correction
**Description:** Masculine ordinal indicator (U+00BA) -> degree sign (U+00B0) in temperature/angle context, with proper NBSP spacing. In German, Greek beta -> eszett.
**Language pills:** ordinal->degree all languages | beta->eszett de-DE
**Examples:**
- (universal): 20[ordinal]C -> 20[NBSP][degree]C | U+00BA -> NBSP + U+00B0
- de-DE: Stra[beta]e -> Strasse (with eszett) | U+03B2 -> U+00DF

---

### 4. Symbols
<!-- h2.category #cat-symbols -->

**Category description:** ASCII approximations replaced with their proper Unicode equivalents.

#### ellipsis -- Ellipsis Character
**Description:** Three consecutive periods -> ellipsis character (U+2026). Prevents reflowing across line breaks.
**Language pills:** all languages
**Example:**
- Wait... -> Wait... (ellipsis char) | U+2026

#### copyright_sign / registered_sign / trademark_sign -- Legal Symbols (c) (r) (tm)
**Description:** Converts ASCII approximations to proper Unicode legal symbols. Case-insensitive.
**Language pills:** all languages
**Examples:**
- (c) -> (c) (copyright sign) | U+00A9
- (r) -> (r) (registered sign) | U+00AE
- (tm) -> (tm) (trademark sign) | U+2122

#### fractions -- Common Fractions
**Description:** Replaces ASCII fraction notation with Unicode fraction characters.
**Language pills:** all languages
**Examples:**
- 1/2 -> 1/2 (fraction char)
- 3/4 -> 3/4 (fraction char)

#### primes -- Prime & Double-Prime Marks
**Description:** Straight quotes after numbers -> prime and double-prime for measurements (feet/inches, degrees/minutes).
**Language pills:** all languages
**Examples:**
- 5'10" -> 5[prime]10[double-prime] | U+2032 U+2033
- 6' -> 6[prime]

---

### 5. Quotes & Apostrophes
<!-- h2.category #cat-quotes -->

**Category description:** Language-specific quotation mark conventions and apostrophe curling.

#### quotation_marks -- Quotation Mark Substitution
**Description:** Replaces straight quotes with language-appropriate typographic quotes. Uses adjacency-based stack parsing to handle nested quotes correctly. Inner spaces (NNBSP for fr-FR guillemets, thin space for pt-PT) are inserted automatically.

**Quotation marks matrix table (table.matrix):**

| Language | Primary | Nested | Inner Space | Example |
|---|---|---|---|---|
| `en-US` | \u201C \u201D | \u2018 \u2019 | none | \u201Chello\u201D |
| `en-GB` | \u2018 \u2019 | \u201C \u201D | none | \u2018hello\u2019 |
| `fr-FR` | \u00AB \u00BB | \u201C \u201D | NNBSP | \u00AB[NNBSP]bonjour[NNBSP]\u00BB |
| `de-DE` | \u201E \u201C | \u2039 \u203A | none | \u201Ehallo\u201C |
| `pt-PT` | \u00AB \u00BB | \u201C \u201D | thin | \u00AB[thin]ola[thin]\u00BB |
| `pt-BR` | \u201C \u201D | \u2018 \u2019 | none | \u201Cola\u201D |
| `it-IT` | \u00AB \u00BB | \u201C \u201D | none | \u00ABciao\u00BB |
| `es-ES` | \u00AB \u00BB | \u201C \u201D | none | \u00ABhola\u00BB |
| `es-MX` | \u201C \u201D | \u2018 \u2019 | none | \u201Chola\u201D |
| `nl-NL/BE` | \u201C \u201D | \u2018 \u2019 | none | \u201Challo\u201D |
| `ro-RO` | \u201E \u201D | \u00AB \u00BB | none | \u201Ebuna\u201D |
| `pl` | \u201E \u201D | \u00AB \u00BB | none | \u201Eczesc\u201D |
| `da` | \u201E \u201D | \u201A \u2018 | none | \u201Ehej\u201D |
| `nb` | \u00AB \u00BB | \u2039 \u203A | none | \u00ABhei\u00BB |
| `ru` | \u00AB \u00BB | \u201E \u201D | none | \u00AB[privet]\u00BB |

#### apostrophe -- Typographic Apostrophe
**Description:** Straight apostrophe between word characters -> typographic apostrophe (U+2019). Covers contractions, possessives, and elisions.
**Language pills:** all languages
**Example:**
- don't -> don't (curly apostrophe) | U+2019

---

### 6. Dashes
<!-- h2.category #cat-dashes -->

**Category description:** Locale-aware dash conventions for parenthetical, range, and mathematical contexts.

#### em_dash / en_dash -- Parenthetical Dash
**Description:** Converts " - " (space-hyphen-space) to the locale-appropriate dash. Only matches when surrounded by non-hyphen, non-digit characters.

**Dash styles matrix table (table.matrix):**

| Style | Languages | Result | Source |
|---|---|---|---|
| Em dash, no space | `en-US, pt-PT, pt-BR, pl, ca` | foo--bar (em dash) | CMOS, PWN, IEC |
| Spaced en dash | `en-GB, de-DE, it-IT, nl-NL/BE, ro-RO, sc, sv, nb, da, fi, cs` | foo -- bar (en dash) | Hart's, Duden |
| NNBSP + em dash + NNBSP | `fr-FR` | foo[NNBSP]--[NNBSP]bar | Imprimerie nationale |
| Spaced em dash | `es-ES, es-MX, ru` | foo -- bar (em dash) | RAE, GOST |

#### range_dash -- Range Dash (En Dash)
**Description:** Hyphen between numbers -> en dash (U+2013) for number ranges.
**Language pills:** all languages
**Examples:**
- 2020-2024 -> 2020--2024 (en dash)
- pp. 5-10 -> pp.[NBSP]5--10 (en dash)

#### minus_sign -- Minus Sign
**Description:** Hyphen in numeric context -> minus sign (U+2212). Handles negative numbers and subtraction.
**Language pills:** all languages
**Example:**
- a -5 b -> a [minus]5 b | U+2212

---

### 7. Spacing
<!-- h2.category #cat-spacing -->

**Category description:** Non-breaking spaces, unit spacing, and locale-aware whitespace conventions.

#### double_space -- Double Space Collapse
**Description:** Collapses 2+ consecutive ASCII spaces to a single space. Common in PDF pastes, AI outputs, and legacy CMS exports. Preserves line-start indentation.
**Language pills:** all languages
**Example:**
- Hello  world -> Hello world

#### number_unit_spacing -- Number + Unit Spacing
**Description:** Inserts NBSP between a number and its unit to prevent line break. Covers SI, digital, CSS, and time units. French uses NNBSP; all others use NBSP.
**Language pills:** all languages
**Examples:**
- 10km -> 10[NBSP]km
- fr-FR: 5kg -> 5[NNBSP]kg | NNBSP U+202F

#### percentage_spacing -- Percentage Sign Spacing
**Description:** Locale-aware spacing before the percent sign.
**Language pills:** fr-FR NNBSP | de-DE NBSP | others: no space
**Examples:**
- fr-FR: 25% -> 25[NNBSP]%
- de-DE: 25% -> 25[NBSP]%
- en-US: 25% -> 25% | (unchanged)

#### currency_spacing -- Currency Symbol Spacing
**Description:** Locale-aware positioning and spacing of currency symbols (EUR, GBP, JPY, $).

**Currency matrix table (table.matrix):**

| Style | Languages | Example |
|---|---|---|
| Before, no space | `en-US, en-GB, es-MX, pt-BR` | $10.50 |
| After, NBSP | `pt-PT, es-ES, fr-FR, de-DE, it-IT, ro-RO, sc, sv, nb, da, fi, pl, cs, ca, ru` | 10[NBSP]EUR |
| Before, NBSP | `nl-NL, nl-BE` | EUR[NBSP]10,00 |

#### multiplication_sign -- Multiplication Sign
**Description:** Letter "x" between numbers -> multiplication sign (U+00D7) with thin spaces.
**Language pills:** all languages
**Example:**
- 1920x1080 -> 1920[thin][multiplication][thin]1080 | thin x thin

---

### 8. Arrows
<!-- h2.category #cat-arrows -->

**Category description:** ASCII arrow approximations replaced with proper Unicode arrows.

#### right_arrow / left_arrow / left_right_arrow -- ASCII Arrow Substitution
**Description:** Whitespace-bounded ASCII arrows -> Unicode arrows. obj->method() and => (fat arrow) are left alone.
**Language pills:** all languages
**Examples:**
- click -> next -> click [right arrow] next | U+2192
- step <- back -> step [left arrow] back | U+2190
- foo <-> bar -> foo [left-right arrow] bar | U+2194

---

### 9. Structural
<!-- h2.category #cat-structural -->

**Category description:** Bracket nesting, initial binding, and structural whitespace rules.

#### nested_parentheticals -- Nested Parenthetical Brackets
**Description:** Converts inner parentheses to square brackets when nested.
**Language pills:** all languages
**Example:**
- (like (this)) -> (like [this])

#### nbsp_between_initials -- NBSP Between Initials
**Description:** Inserts NBSP between adjacent initials. English locale guard: two-letter abbreviations (U.S., U.K.) are left alone per AP/CMOS; 3+ initials get NBSP.
**Language pills:** all languages
**Examples:**
- en-US: J.R.R. Tolkien -> J.[NBSP]R.[NBSP]R. Tolkien
- en-US: U.S. government -> U.S. government | (unchanged -- 2-letter EN)
- de-DE: J.R. Ewing -> J.[NBSP]R. Ewing

---

### 10. Abbreviations
<!-- h2.category #cat-abbreviations -->

**Category description:** Locale-specific period conventions and non-breaking space insertion after titles.

#### abbreviation_periods -- Abbreviation Period Conventions
**Description:** Locale-specific rules for periods in title abbreviations.

**Abbreviation matrix table (table.matrix):**

| Language | Convention | Example |
|---|---|---|
| `en-US` | Always period | Mr. Smith, Dr. Jones |
| `en-GB` | Contractions: no period | Mr Smith, Dr Jones, Prof. Adams |
| `fr-FR` | M. / Mme / Mlle | M. Dupont, Mme Blanc |
| `pt-PT/BR` | Always period | Sr. Silva, Dra. Costa |

#### nbsp_after_title -- NBSP After Title Abbreviations
**Description:** Inserts NBSP between title abbreviations and the following capitalized name. Language-aware: includes locale-specific titles.
**Language pills:** all languages
**Examples:**
- Mr. Smith -> Mr.[NBSP]Smith
- de-DE: Fr. Muller -> Fr.[NBSP]Muller

#### nbsp_page_abbrev -- NBSP After Page/Section Abbreviations
**Description:** Inserts NBSP between page/section abbreviations (p., pp., section-sign, art., fig., tab.) and the following number.
**Language pills:** all languages
**Examples:**
- p. 42 -> p.[NBSP]42
- pp. 10-20 -> pp.[NBSP]10--20 (en dash)

---

### 11. Language-Specific Rules
<!-- h2.category #cat-language-specific -->

**Category description:** Rules that only fire for specific language codes.

#### german_eszett -- German Capital Eszett
**Description:** In all-caps German words, SS -> capital sharp s for known eszett words. Introduced 2017 by the Rat fur deutsche Rechtschreibung.
**Language pills:** de-DE
**Examples:**
- de-DE: STRASSE -> STRASSE (with capital eszett)
- de-DE: FUSSBALL -> FUSSBALL (with capital eszett)

#### german_din5008_spacing -- German DIN 5008 Abbreviation Spacing
**Description:** Inserts NNBSP between parts of multi-part abbreviations per DIN 5008.
**Language pills:** de-DE
**Examples:**
- de-DE: z.B. -> z.[NNBSP]B.
- de-DE: i.d.R. -> i.[NNBSP]d.[NNBSP]R.

#### ligature_suppression -- Ligature Suppression (ZWNJ)
**Description:** Inserts ZWNJ (U+200C) at morpheme boundaries in compound words where a ligature would incorrectly span the boundary.
**Language pills:** de-DE, en-US, en-GB
**Examples:**
- de-DE: Auflage -> Auf[ZWNJ]lage | ZWNJ at morpheme boundary
- de-DE: Schifffahrt -> Schiff[ZWNJ]fahrt
- en-US: shelfful -> shelf[ZWNJ]ful

#### ordinals -- Ordinal Typographic Forms
**Description:** Converts numeric ordinal approximations to proper typographic forms.
**Language pills:** pt-PT, pt-BR, es-ES, es-MX
**Examples:**
- pt-PT: 5o andar -> 5.o (masculine ordinal) andar
- es-ES: 3er lugar -> 3.o (masculine ordinal) lugar

#### single_letter_nbsp -- Single-Letter Word NBSP (Anti-Orphan)
**Description:** Replaces the space after single-letter prepositions and conjunctions with NBSP to prevent orphans. Skips all-caps display contexts.
**Language pills:** fr-FR, es-ES/MX, it-IT, pt-PT/BR, pl, cs
**Examples:**
- es-ES: pan y agua -> pan y[NBSP]agua
- pl: ide w kino -> ide w[NBSP]kino
- fr-FR: voyage a mon ami -> voyage a[NBSP]mon ami

#### french_high_punctuation -- French High Punctuation Spacing
**Description:** Inserts NNBSP (U+202F) before : ; ! ? in French text per Imprimerie nationale. Does not fire on URL schemes.
**Language pills:** fr-FR
**Examples:**
- fr-FR: Bonjour ! -> Bonjour[NNBSP]! | NNBSP U+202F
- fr-FR: question? -> question[NNBSP]?
- fr-FR: liste: un -> liste[NNBSP]: un

#### inverted_punctuation -- Spanish Inverted Punctuation
**Description:** Inserts inverted-? and inverted-! at the start of question/exclamation sentences. Required since RAE 1754.
**Language pills:** es-ES, es-MX
**Examples:**
- es-ES: Donde vives? -> inverted-? Donde (with accent) vives?
- es-ES: Que increible! -> inverted-! Que (with accent) increible (with accent)!

---

### 12. Punctuation Placement
<!-- h2.category #cat-punctuation -->

**Category description:** Locale conventions for quote-punctuation order, footnotes, serial comma, and colon capitalisation.

#### quote_punctuation_placement -- Quote-Punctuation Order
**Description:** Moves period and comma relative to the closing quote per locale style. Only periods and commas are affected.

**Quote-punctuation matrix (table.matrix):**

| Policy | Languages | Example |
|---|---|---|
| Inside (typesetters') | `en-US` | "magnificent." |
| Outside (logical) | `en-GB, de-DE, fr-FR, it-IT, es-ES/MX, pt-PT/BR, nl-NL/BE` | 'magnificent'. |

#### footnote_mark_placement -- Footnote Mark Placement
**Description:** Moves superscript footnote marks relative to terminal punctuation per locale.

**Footnote matrix (table.matrix):**

| Policy | Languages | Result |
|---|---|---|
| Mark after punctuation | `en-US, en-GB, de-DE, it-IT, es-ES, pt-PT, nl-NL, ro-RO, sv, nb, da, fi, pl, cs, ca, ru` | matters.[superscript 1] |
| Mark before punctuation | `fr-FR` | matters[superscript 1]. |

#### serial_comma -- Serial (Oxford) Comma
**Description:** Enforces or removes the serial comma before the final coordinator in lists. Requires at least one prior comma.

**Serial comma matrix (table.matrix):**

| Policy | Languages | Example |
|---|---|---|
| Enforce | `en-US, en-GB` | red, white, and blue |
| Remove | `fr-FR, de-DE, it-IT, es-ES/MX, pt-PT/BR, nl-NL/BE` | rouge, blanc et bleu |

#### colon_capitalisation -- Colon Capitalisation
**Description:** Capitalises or lowercases the first word after a colon per locale. French always lowercases. English and German use clause-aware heuristics. Proper nouns are never lowercased.

**Colon capitalisation matrix (table.matrix):**

| Policy | Languages | Example |
|---|---|---|
| Always lower | `fr-FR` | le verdict[NNBSP]: il est coupable. |
| Clause-aware | `en-US, en-GB` | The verdict: He was guilty. |
| Clause-aware | `de-DE` | Das Ergebnis: Er war schuldig. |

---

### 13. Accessibility
<!-- h2.category #cat-accessibility -->

**Category description:** WCAG-compliant text reflow and reference mark spacing.

#### breakable_containers -- WCAG Breakable Containers (SC 1.4.12)
**Description:** Reduces NBSP chains of 4+ elements by breaking middle connections to allow text reflow. Keeps first and last NBSP intact.
**Language pills:** all languages
**Example:**
- J.[NBSP]R.[NBSP]R.[NBSP]Tolkien -> J.[NBSP]R. R.[NBSP]Tolkien | middle NBSP -> space

#### reference_mark_nbsp -- Reference Mark NBSP
**Description:** Inserts NBSP between reference marks (section-sign, pilcrow) and adjacent numbers.
**Language pills:** all languages
**Example:**
- [section-sign] 5 -> [section-sign][NBSP]5

---

### 14. Final Cleanup
<!-- h2.category #cat-cleanup -->

**Category description:** Post-processing passes that run after all other rules.

#### abbreviation_haplology -- Abbreviation Haplology
**Description:** Collapses double periods at sentence end when an abbreviation's period coincides with the sentence-ending period.
**Language pills:** all languages
**Example:**
- etc.. -> etc.

#### widow_prevention -- Widow Prevention (Opt-In)
**Description:** Replaces the last inter-word space in 4+-word paragraphs with NBSP. Off by default; enabled via `prevent_widows=True`.
**Language pills:** all languages (opt-in)
**Example:**
- This is a short sentence. -> This is a short[NBSP]sentence.

---

### 15. Code Exclusion
<!-- h2.category #cat-code-exclusion -->

**Category description:** Cross-cutting safety layer: regions that must never be corrected.

#### code_exclusion -- Code & Identifier Masking
**Description:** Before any rule runs, the linter masks: fenced code blocks, inline backtick code, HTML code/pre/kbd elements, URLs, emails, file paths, version strings, @mentions, #hashtags, camelCase and snake_case identifiers, and regex patterns. Restored verbatim after all rules run.
**Language pills:** all languages
**Examples:**
- `x...` is code -> `x...` is code | (unchanged inside backticks)
- See https://example.com/foo--bar -> See https://example.com/foo--bar | (URL preserved)

---

## Call to Action

<!-- section.cta-section -->

**Eyebrow (div.cta-eyebrow):** Open Source

**Heading (h2.cta-heading):** This work needs native speakers.

**Body paragraph 1 (p):** I verified the sources the LLM pulled from. I cross-referenced grammars, style guides, and typographic authorities for every language variant. But there's nothing like a native to truly validate this kind of work. The rules for your language deserve to be reviewed by someone who grew up writing in it.

**Body paragraph 2 (p):** This is where Typeproof can – and should – scale. Extend the schema to new languages. Catch conventions I got wrong. Add the rules that only a native would know to look for. The YAML schema is designed for exactly this: auditable, extensible, open.

**CTA buttons (a.cta-btn):**
- View on GitHub (primary) -> https://github.com/tudotype/typeproof
- Report an Issue (secondary) -> https://github.com/tudotype/typeproof/issues
- Fork & Contribute (secondary) -> https://github.com/tudotype/typeproof/fork

### Install Card
<!-- div.install-card -->

**Heading (h4):** Install

**pip (pre, label b):**
```
pip install typeproof
```

**Standalone (pre, label b):**
```
curl -O https://raw.githubusercontent.com/tudotype/typeproof/main/typeproof.py
python3 typeproof.py "your text" --lang fr-FR
```

**Claude Code Skill (pre, label b):**
```
# Add to your .claude/skills/ directory:
curl -O https://raw.githubusercontent.com/tudotype/typeproof/main/skills/typeproof.md
```

---

## Author

<!-- div.author-section -->

**Section heading (h4):** About the Author

**Avatar (div.author-avatar):** J

**Name (div.author-name, a):** João Miranda
<!-- links to https://www.linkedin.com/in/walkingfearless/ -->

**Role (div.author-role):** Brand Designer at Automattic
<!-- "Automattic" links to https://automattic.design -->

**Bio (p.author-bio):** João is a Portuguese brand and type designer with over a decade of experience at consultancies including Pentagram, Wolff Olins and R/GA. At Automattic, he shapes the visual identity of WordPress – the platform that powers over 40% of the web. He also founded tudotype, an independent type foundry.
<!-- "Automattic" links to https://automattic.design, "tudotype" links to https://tudotype.com -->

---

## Footer

<!-- div.footer -->

**Footer left (div.footer-left):** [Tudotype SVG wordmark logo]
<!-- span.footer-logo > svg -->

**Footer right (div.footer-right):** **46+ rules** . 13 language variants . May 2026
Set in Google Sans
<!-- "46+ rules" is span.amber; "Google Sans" links to https://fonts.google.com/specimen/Google+Sans -->

---

## Page Metadata

**Title (title):** Typeproof -- Rule Reference
**Charset:** UTF-8
**Fonts loaded:** Google Sans (400, 500, 700), Google Sans Mono (400, 500), Google Sans Text (400, 500)
