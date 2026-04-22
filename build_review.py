#!/usr/bin/env python3
"""
Build an interactive HTML review page for the typography system schema.
Parses the YAML schema and generates a self-contained HTML file for human review.
"""

import json
import yaml
import html as html_mod
from pathlib import Path

SCHEMA_PATH = Path(__file__).parent / "typography-system-schema.yaml"
OUTPUT_PATH = Path(__file__).parent / "schema-review.html"

TIER_1_LANGS = ["pt-PT", "pt-BR", "en-US", "en-GB", "fr-FR", "de-DE", "it-IT", "es-ES", "es-MX"]
TIER_2_LANGS = ["nl-NL", "nl-BE", "ro-RO", "sc"]

# Invisible characters that need visible indicators
INVISIBLE_CHARS = {
    "\u00A0": ("NBSP", "#6366f1"),        # indigo
    "\u202F": ("NNBSP", "#8b5cf6"),       # violet
    "\u200C": ("ZWNJ", "#f59e0b"),        # amber
    "\u200D": ("ZWJ", "#f59e0b"),         # amber
    "\u200B": ("ZWSP", "#ef4444"),        # red
    "\u2009": ("THIN", "#06b6d4"),        # cyan
    "\u200A": ("HAIR", "#14b8a6"),        # teal
    "\u2060": ("WJ", "#f59e0b"),          # amber
    "\uFEFF": ("BOM", "#ef4444"),         # red
}

# Batch assignment map: rule_name -> batch number
# We detect batch from comments in the YAML structure
BATCH_ASSIGNMENTS = {}


def detect_batch(rule_name, rule_data):
    """Heuristic batch detection based on rule names and content."""
    batch1 = ["code_exclusion", "normalization", "zero_width_characters"]
    batch2 = ["capital_accent_preservation", "eszett_capitalisation", "french_ligatures",
              "homoglyph_detection", "diacritic_correctness", "accent_conventions",
              "capital_accents", "orthographic_ligatures"]
    batch3 = ["nnbsp_semantics", "nbsp_obligations", "single_letter_line_end",
              "high_punctuation_spacing", "din5008_abbreviations"]
    batch4 = ["colon_capitalisation", "serial_comma", "quote_punctuation_placement",
              "abbreviation_periods", "abbreviation_haplology", "footnote_mark_placement",
              "nested_parentheticals", "inverted_punctuation", "abbreviation_conventions",
              "abbreviation_periods"]
    batch5 = ["ligature_suppression", "orthographic_ligature_preservation",
              "small_caps_acronyms", "figure_styles", "caps_letter_spacing",
              "hanging_punctuation", "small_caps_centuries", "orthographic_ligature_priority"]
    batch6 = ["wcag_text_spacing", "no_fixed_width_containers", "bidi_isolate_preservation",
              "breakable_containers", "language_tagging", "screen_reader_typography"]

    rtype = rule_data.get("type", "") if isinstance(rule_data, dict) else ""
    if rtype == "output_requirement":
        return 6
    if rtype == "rendering_hint":
        return 5

    if rule_name in batch1: return 1
    if rule_name in batch2: return 2
    if rule_name in batch3: return 3
    if rule_name in batch4: return 4
    if rule_name in batch5: return 5
    if rule_name in batch6: return 6
    return 0  # pre-batch / general


def make_visible(text):
    """Replace invisible Unicode characters with visible HTML indicators."""
    if not isinstance(text, str):
        return str(text)
    result = ""
    for ch in text:
        if ch in INVISIBLE_CHARS:
            name, color = INVISIBLE_CHARS[ch]
            result += f'<span class="invis-char" style="border-bottom: 2px dotted {color}; color: {color};" title="{name} (U+{ord(ch):04X})">\u2423<sub class="invis-label">{name}</sub></span>'
        else:
            result += html_mod.escape(ch)
    return result


def diff_highlight(raw, correct):
    """Simple character-level diff highlighting between raw and correct."""
    raw_vis = make_visible(raw)
    correct_vis = make_visible(correct)
    return raw_vis, correct_vis


def extract_rules_from_section(section, source_label, lang_code=None):
    """Extract rule cards from a dict of rules."""
    cards = []
    if not isinstance(section, dict):
        return cards
    for rule_name, rule_data in section.items():
        if not isinstance(rule_data, dict):
            # Could be a scalar like number_formatting fields
            continue
        # Skip pure number_formatting blocks that are just config
        if rule_name == "number_formatting" and "description" not in rule_data:
            # Still interesting -- make a card for it
            card = {
                "name": rule_name,
                "source": source_label,
                "lang": lang_code or "universal",
                "batch": 0,
                "description": "Number formatting conventions",
                "rule": "",
                "examples": [],
                "notes": rule_data.get("notes", ""),
                "register_sensitive": False,
                "type": "config",
                "raw_data": rule_data,
            }
            # Build a readable rule from the config
            parts = []
            for k, v in rule_data.items():
                if k != "notes" and k != "examples":
                    parts.append(f"{k}: {v}")
            card["rule"] = "\n".join(parts)
            if rule_data.get("examples"):
                card["examples"] = rule_data["examples"]
            cards.append(card)
            continue

        batch = detect_batch(rule_name, rule_data)
        rtype = rule_data.get("type", "character_rule")

        card = {
            "name": rule_name,
            "source": source_label,
            "lang": lang_code or "universal",
            "batch": batch,
            "description": rule_data.get("description", ""),
            "rule": rule_data.get("rule", ""),
            "examples": rule_data.get("examples", []),
            "notes": rule_data.get("notes", ""),
            "register_sensitive": rule_data.get("register_sensitive", False),
            "type": rtype,
            "raw_data": rule_data,
        }
        cards.append(card)
    return cards


def parse_schema(schema):
    """Parse the full schema and return a list of rule cards."""
    cards = []

    # Universal rules
    universal = schema.get("semantic_rules", {}).get("universal", {})
    cards.extend(extract_rules_from_section(universal, "Universal"))

    # Language layers
    languages = schema.get("languages", {})
    for lang_code, lang_data in languages.items():
        if not isinstance(lang_data, dict):
            continue
        label = lang_data.get("label", lang_code)
        inherits = lang_data.get("inherits", "universal")

        # Overrides
        overrides = lang_data.get("overrides", {})
        for rule_name, rule_data in (overrides or {}).items():
            if not isinstance(rule_data, dict):
                continue
            batch = detect_batch(rule_name, rule_data)
            rtype = rule_data.get("type", "character_rule")
            card = {
                "name": rule_name,
                "source": f"{label} (override)",
                "lang": lang_code,
                "batch": batch,
                "description": rule_data.get("description", f"Override of {rule_name}"),
                "rule": rule_data.get("rule", ""),
                "examples": rule_data.get("examples", []),
                "notes": rule_data.get("notes", ""),
                "register_sensitive": rule_data.get("register_sensitive", False),
                "type": rtype,
                "inherits": inherits,
                "raw_data": rule_data,
            }
            cards.append(card)

        # Additions
        additions = lang_data.get("additions", {})
        cards.extend(extract_rules_from_section(
            additions, f"{label} (addition)", lang_code=lang_code
        ))

    return cards


def build_html(cards):
    """Generate the full HTML review page."""
    # Collect unique languages and batches
    all_langs = set()
    all_batches = set()
    for c in cards:
        all_langs.add(c["lang"])
        all_batches.add(c["batch"])

    all_batches_sorted = sorted(all_batches)

    # Build cards JSON for JS
    cards_json = []
    for i, c in enumerate(cards):
        examples_html = []
        for ex in (c["examples"] or []):
            if isinstance(ex, dict):
                raw = ex.get("raw", "")
                correct = ex.get("correct", "")
                ex_notes = ex.get("notes", "")
                examples_html.append({
                    "raw": raw,
                    "correct": correct,
                    "notes": ex_notes,
                })
            elif isinstance(ex, str):
                examples_html.append({"raw": "", "correct": ex, "notes": ""})

        cards_json.append({
            "id": i,
            "name": c["name"],
            "source": c["source"],
            "lang": c["lang"],
            "batch": c["batch"],
            "description": c["description"],
            "rule": c["rule"],
            "examples": examples_html,
            "notes": c["notes"],
            "register_sensitive": c["register_sensitive"],
            "type": c["type"],
        })

    tier1_order = TIER_1_LANGS
    tier2_order = TIER_2_LANGS

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Typography System Schema Review</title>
<style>
  :root {{
    --bg: #f8f7f4;
    --surface: #ffffff;
    --surface-hover: #fafaf8;
    --border: #e5e2db;
    --border-light: #f0ede6;
    --text: #1a1a1a;
    --text-secondary: #6b6560;
    --text-tertiary: #9b958e;
    --accent: #3b5998;
    --accent-light: #e8edf5;
    --green: #16a34a;
    --green-bg: #f0fdf4;
    --green-border: #bbf7d0;
    --amber: #d97706;
    --amber-bg: #fffbeb;
    --amber-border: #fde68a;
    --red: #dc2626;
    --red-bg: #fef2f2;
    --red-border: #fecaca;
    --badge-blue: #dbeafe;
    --badge-blue-text: #1e40af;
    --badge-purple: #ede9fe;
    --badge-purple-text: #6d28d9;
    --badge-gray: #f3f4f6;
    --badge-gray-text: #4b5563;
    --badge-orange: #ffedd5;
    --badge-orange-text: #c2410c;
  }}

  * {{ margin: 0; padding: 0; box-sizing: border-box; }}

  body {{
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
    background: var(--bg);
    color: var(--text);
    line-height: 1.6;
    font-size: 15px;
  }}

  .header {{
    background: var(--surface);
    border-bottom: 1px solid var(--border);
    padding: 24px 32px;
    position: sticky;
    top: 0;
    z-index: 100;
  }}

  .header h1 {{
    font-size: 22px;
    font-weight: 600;
    letter-spacing: -0.02em;
    margin-bottom: 4px;
  }}

  .header .subtitle {{
    font-size: 13px;
    color: var(--text-secondary);
  }}

  .stats-bar {{
    display: flex;
    gap: 24px;
    margin-top: 12px;
    flex-wrap: wrap;
  }}

  .stat {{
    font-size: 13px;
    color: var(--text-secondary);
  }}

  .stat strong {{
    font-weight: 600;
    color: var(--text);
    font-size: 18px;
    margin-right: 4px;
  }}

  .filters {{
    background: var(--surface);
    border-bottom: 1px solid var(--border);
    padding: 16px 32px;
    display: flex;
    gap: 16px;
    flex-wrap: wrap;
    align-items: center;
  }}

  .filter-group {{
    display: flex;
    flex-direction: column;
    gap: 6px;
  }}

  .filter-group label {{
    font-size: 11px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: var(--text-tertiary);
  }}

  .filter-group select,
  .filter-group input[type="text"] {{
    padding: 6px 10px;
    border: 1px solid var(--border);
    border-radius: 6px;
    font-size: 13px;
    background: var(--surface);
    color: var(--text);
    min-width: 140px;
  }}

  .filter-group select:focus,
  .filter-group input[type="text"]:focus {{
    outline: none;
    border-color: var(--accent);
    box-shadow: 0 0 0 2px var(--accent-light);
  }}

  .filter-pills {{
    display: flex;
    gap: 4px;
    flex-wrap: wrap;
  }}

  .pill {{
    padding: 4px 10px;
    border-radius: 20px;
    font-size: 12px;
    cursor: pointer;
    border: 1px solid var(--border);
    background: var(--surface);
    color: var(--text-secondary);
    transition: all 0.15s;
    white-space: nowrap;
  }}

  .pill:hover {{
    border-color: var(--accent);
    color: var(--accent);
  }}

  .pill.active {{
    background: var(--accent);
    color: white;
    border-color: var(--accent);
  }}

  .main {{
    max-width: 960px;
    margin: 0 auto;
    padding: 24px 32px;
  }}

  .section-label {{
    font-size: 11px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: var(--text-tertiary);
    margin: 32px 0 12px;
    padding-bottom: 8px;
    border-bottom: 1px solid var(--border-light);
  }}

  .card {{
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 20px 24px;
    margin-bottom: 16px;
    transition: border-color 0.15s;
  }}

  .card:hover {{
    border-color: #ccc;
  }}

  .card-header {{
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    gap: 12px;
    margin-bottom: 12px;
  }}

  .card-title {{
    font-size: 16px;
    font-weight: 600;
    letter-spacing: -0.01em;
  }}

  .card-badges {{
    display: flex;
    gap: 6px;
    flex-wrap: wrap;
    flex-shrink: 0;
  }}

  .badge {{
    padding: 2px 8px;
    border-radius: 4px;
    font-size: 11px;
    font-weight: 500;
    white-space: nowrap;
  }}

  .badge-batch {{
    background: var(--badge-blue);
    color: var(--badge-blue-text);
  }}

  .badge-lang {{
    background: var(--badge-gray);
    color: var(--badge-gray-text);
  }}

  .badge-register {{
    background: var(--badge-orange);
    color: var(--badge-orange-text);
  }}

  .badge-type {{
    background: var(--badge-purple);
    color: var(--badge-purple-text);
  }}

  .card-description {{
    font-size: 13px;
    color: var(--text-tertiary);
    margin-bottom: 8px;
  }}

  .card-rule {{
    font-size: 15px;
    line-height: 1.7;
    color: var(--text);
    background: #f5f3ee;
    border-left: 3px solid var(--accent);
    border-radius: 2px 6px 6px 2px;
    padding: 14px 18px;
    margin-bottom: 16px;
    white-space: pre-wrap;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    font-weight: 450;
  }}

  .card-rule::before {{
    content: "Convention";
    display: block;
    font-size: 10px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: var(--accent);
    margin-bottom: 6px;
  }}

  .examples-section {{
    margin-bottom: 12px;
  }}

  .examples-label {{
    font-size: 11px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: var(--text-tertiary);
    margin-bottom: 8px;
  }}

  .example-pair {{
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 8px;
    margin-bottom: 8px;
  }}

  .example-box {{
    border: 1px solid var(--border-light);
    border-radius: 6px;
    padding: 8px 12px;
    font-size: 14px;
    line-height: 1.6;
  }}

  .example-box.raw {{
    background: var(--red-bg);
    border-color: var(--red-border);
  }}

  .example-box.correct {{
    background: var(--green-bg);
    border-color: var(--green-border);
  }}

  .example-box .box-label {{
    font-size: 10px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    color: var(--text-tertiary);
    margin-bottom: 4px;
  }}

  .example-box.raw .box-label {{ color: var(--red); }}
  .example-box.correct .box-label {{ color: var(--green); }}

  .example-notes {{
    font-size: 12px;
    color: var(--text-tertiary);
    font-style: italic;
    margin-top: 2px;
  }}

  .invis-char {{
    font-size: 12px;
    padding: 0 1px;
    cursor: help;
    position: relative;
  }}

  .invis-label {{
    font-size: 8px;
    vertical-align: baseline;
    font-weight: 600;
  }}

  .card-notes {{
    font-size: 13px;
    color: var(--text-secondary);
    background: var(--amber-bg);
    border: 1px solid var(--amber-border);
    border-radius: 6px;
    padding: 10px 14px;
    margin-bottom: 12px;
    line-height: 1.6;
  }}

  .card-notes::before {{
    content: "Note: ";
    font-weight: 600;
    color: var(--amber);
  }}

  .review-controls {{
    display: flex;
    gap: 8px;
    align-items: center;
    flex-wrap: wrap;
    padding-top: 12px;
    border-top: 1px solid var(--border-light);
  }}

  .review-btn {{
    padding: 6px 14px;
    border-radius: 6px;
    font-size: 13px;
    cursor: pointer;
    border: 1px solid var(--border);
    background: var(--surface);
    color: var(--text-secondary);
    transition: all 0.15s;
    font-weight: 500;
  }}

  .review-btn:hover {{ border-color: #aaa; }}

  .review-btn.active-correct {{
    background: var(--green-bg);
    border-color: var(--green);
    color: var(--green);
  }}

  .review-btn.active-uncertain {{
    background: var(--amber-bg);
    border-color: var(--amber);
    color: var(--amber);
  }}

  .review-btn.active-wrong {{
    background: var(--red-bg);
    border-color: var(--red);
    color: var(--red);
  }}

  .review-note {{
    flex: 1;
    min-width: 200px;
    padding: 6px 10px;
    border: 1px solid var(--border);
    border-radius: 6px;
    font-size: 13px;
    background: var(--surface);
    color: var(--text);
  }}

  .review-note:focus {{
    outline: none;
    border-color: var(--accent);
    box-shadow: 0 0 0 2px var(--accent-light);
  }}

  .export-bar {{
    position: fixed;
    bottom: 0;
    left: 0;
    right: 0;
    background: var(--surface);
    border-top: 1px solid var(--border);
    padding: 12px 32px;
    display: flex;
    justify-content: flex-end;
    gap: 12px;
    z-index: 100;
  }}

  .export-btn {{
    padding: 8px 20px;
    border-radius: 6px;
    font-size: 13px;
    font-weight: 600;
    cursor: pointer;
    border: none;
    background: var(--accent);
    color: white;
    transition: opacity 0.15s;
  }}

  .export-btn:hover {{ opacity: 0.9; }}

  .no-results {{
    text-align: center;
    padding: 48px;
    color: var(--text-tertiary);
    font-size: 14px;
  }}

  .source-label {{
    font-size: 12px;
    color: var(--text-tertiary);
    margin-bottom: 4px;
  }}

  .hidden {{ display: none !important; }}

  .tier-divider {{
    font-size: 10px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.1em;
    color: var(--text-tertiary);
    padding: 4px 0;
    margin-top: 4px;
  }}

  @media (max-width: 700px) {{
    .example-pair {{ grid-template-columns: 1fr; }}
    .header, .filters, .main, .export-bar {{ padding-left: 16px; padding-right: 16px; }}
  }}

  /* Bottom padding for export bar */
  body {{ padding-bottom: 64px; }}
</style>
</head>
<body>

<div class="header">
  <h1>Typography System Schema Review</h1>
  <div class="subtitle">13 language variants, 6 rule batches. Review each rule for correctness.</div>
  <div class="stats-bar">
    <div class="stat"><strong id="stat-total">0</strong> total rules</div>
    <div class="stat"><strong id="stat-visible">0</strong> visible</div>
    <div class="stat"><strong id="stat-reviewed">0</strong> reviewed</div>
    <div class="stat" style="color: var(--amber);"><strong id="stat-uncertain">0</strong> uncertain</div>
    <div class="stat" style="color: var(--red);"><strong id="stat-wrong">0</strong> flagged wrong</div>
  </div>
</div>

<div class="filters">
  <div class="filter-group">
    <label>Language</label>
    <select id="filter-lang">
      <option value="all">All languages</option>
      <option value="universal">Universal</option>
      <optgroup label="Tier 1">
        {"".join(f'<option value="{l}">{l}</option>' for l in TIER_1_LANGS)}
      </optgroup>
      <optgroup label="Tier 2">
        {"".join(f'<option value="{l}">{l}</option>' for l in TIER_2_LANGS)}
      </optgroup>
    </select>
  </div>

  <div class="filter-group">
    <label>Batch</label>
    <select id="filter-batch">
      <option value="all">All batches</option>
      <option value="0">Pre-batch / General</option>
      <option value="1">Batch 1: Safety layer</option>
      <option value="2">Batch 2: Diacritics</option>
      <option value="3">Batch 3: Spacing</option>
      <option value="4">Batch 4: Punctuation</option>
      <option value="5">Batch 5: Micro-typo</option>
      <option value="6">Batch 6: WCAG</option>
    </select>
  </div>

  <div class="filter-group">
    <label>Type</label>
    <select id="filter-type">
      <option value="all">All types</option>
      <option value="character_rule">Character rules</option>
      <option value="rendering_hint">Rendering hints</option>
      <option value="output_requirement">Output requirements</option>
      <option value="config">Config</option>
    </select>
  </div>

  <div class="filter-group">
    <label>Review status</label>
    <select id="filter-status">
      <option value="all">All</option>
      <option value="unreviewed">Unreviewed</option>
      <option value="correct">Marked correct</option>
      <option value="uncertain">Uncertain</option>
      <option value="wrong">Wrong</option>
      <option value="flagged">Flagged (uncertain + wrong)</option>
    </select>
  </div>

  <div class="filter-group">
    <label>Search</label>
    <input type="text" id="filter-search" placeholder="Search rules..." />
  </div>
</div>

<div class="main" id="cards-container">
</div>

<div class="export-bar">
  <button class="export-btn" onclick="exportFeedback()" style="background: var(--green);">Export Feedback (JSON)</button>
  <button class="export-btn" onclick="resetAll()" style="background: var(--text-tertiary);">Reset All</button>
</div>

<script>
// Invisible character map for rendering
const INVIS = {json.dumps({hex(ord(k)): v for k, v in INVISIBLE_CHARS.items()})};

const CARDS = {json.dumps(cards_json, ensure_ascii=False)};

// Review state: id -> {{ status: "correct"|"uncertain"|"wrong"|null, note: "" }}
let reviewState = {{}};

// Load saved state
try {{
  const saved = localStorage.getItem("typo-review-state");
  if (saved) reviewState = JSON.parse(saved);
}} catch(e) {{}}

function saveState() {{
  try {{ localStorage.setItem("typo-review-state", JSON.stringify(reviewState)); }} catch(e) {{}}
}}

function makeVisible(text) {{
  if (!text) return "";
  let result = "";
  for (const ch of text) {{
    const cp = "0x" + ch.codePointAt(0).toString(16);
    const info = INVIS[cp];
    if (info) {{
      const [name, color] = info;
      result += '<span class="invis-char" style="border-bottom: 2px dotted ' + color + '; color: ' + color + ';" title="' + name + ' (U+' + ch.codePointAt(0).toString(16).toUpperCase().padStart(4, "0") + ')">\\u2423<sub class="invis-label">' + name + '</sub></span>';
    }} else {{
      result += escapeHtml(ch);
    }}
  }}
  return result;
}}

function escapeHtml(text) {{
  const div = document.createElement("div");
  div.textContent = text;
  return div.innerHTML;
}}

function batchLabel(b) {{
  const labels = {{
    0: "General",
    1: "Batch 1",
    2: "Batch 2",
    3: "Batch 3",
    4: "Batch 4",
    5: "Batch 5",
    6: "Batch 6"
  }};
  return labels[b] || "Batch " + b;
}}

function typeLabel(t) {{
  const labels = {{
    "character_rule": "Character rule",
    "rendering_hint": "Rendering hint",
    "output_requirement": "Output req.",
    "config": "Config"
  }};
  return labels[t] || t;
}}

function renderCard(card) {{
  const state = reviewState[card.id] || {{ status: null, note: "" }};

  let examplesHtml = "";
  if (card.examples && card.examples.length > 0) {{
    let pairs = "";
    for (const ex of card.examples) {{
      if (ex.raw || ex.correct) {{
        pairs += '<div class="example-pair">';
        if (ex.raw) {{
          pairs += '<div class="example-box raw"><div class="box-label">Before (raw)</div>' + makeVisible(ex.raw) + '</div>';
        }}
        if (ex.correct) {{
          pairs += '<div class="example-box correct"><div class="box-label">After (correct)</div>' + makeVisible(ex.correct) + '</div>';
        }}
        pairs += '</div>';
        if (ex.notes) {{
          pairs += '<div class="example-notes">' + escapeHtml(ex.notes) + '</div>';
        }}
      }}
    }}
    if (pairs) {{
      examplesHtml = '<div class="examples-section"><div class="examples-label">Examples</div>' + pairs + '</div>';
    }}
  }}

  let notesHtml = "";
  if (card.notes) {{
    notesHtml = '<div class="card-notes">' + escapeHtml(String(card.notes)) + '</div>';
  }}

  let ruleHtml = "";
  if (card.rule) {{
    ruleHtml = '<div class="card-rule">' + makeVisible(String(card.rule)) + '</div>';
  }}

  const correctClass = state.status === "correct" ? " active-correct" : "";
  const uncertainClass = state.status === "uncertain" ? " active-uncertain" : "";
  const wrongClass = state.status === "wrong" ? " active-wrong" : "";

  return `
    <div class="card" id="card-${{card.id}}" data-lang="${{card.lang}}" data-batch="${{card.batch}}" data-type="${{card.type}}" data-status="${{state.status || 'unreviewed'}}">
      <div class="source-label">${{escapeHtml(card.source)}}</div>
      <div class="card-header">
        <div class="card-title">${{escapeHtml(card.name)}}</div>
        <div class="card-badges">
          <span class="badge badge-batch">${{batchLabel(card.batch)}}</span>
          <span class="badge badge-lang">${{card.lang}}</span>
          ${{card.type !== "character_rule" ? '<span class="badge badge-type">' + typeLabel(card.type) + '</span>' : ''}}
          ${{card.register_sensitive ? '<span class="badge badge-register">Register-sensitive</span>' : ''}}
        </div>
      </div>
      ${{ruleHtml}}
      <div class="card-description">${{escapeHtml(card.description)}}</div>
      ${{examplesHtml}}
      ${{notesHtml}}
      <div class="review-controls">
        <button class="review-btn${{correctClass}}" onclick="setReview(${{card.id}}, 'correct')">&#10003; Correct</button>
        <button class="review-btn${{uncertainClass}}" onclick="setReview(${{card.id}}, 'uncertain')">? Uncertain</button>
        <button class="review-btn${{wrongClass}}" onclick="setReview(${{card.id}}, 'wrong')">&#10007; Wrong</button>
        <input type="text" class="review-note" placeholder="Add a note..."
               value="${{escapeHtml(state.note || '')}}"
               onchange="setNote(${{card.id}}, this.value)" />
      </div>
    </div>
  `;
}}

function setReview(id, status) {{
  if (!reviewState[id]) reviewState[id] = {{ status: null, note: "" }};
  // Toggle off if same status clicked
  if (reviewState[id].status === status) {{
    reviewState[id].status = null;
  }} else {{
    reviewState[id].status = status;
  }}
  saveState();
  renderCards();
}}

function setNote(id, note) {{
  if (!reviewState[id]) reviewState[id] = {{ status: null, note: "" }};
  reviewState[id].note = note;
  saveState();
  updateStats();
}}

function getFilters() {{
  return {{
    lang: document.getElementById("filter-lang").value,
    batch: document.getElementById("filter-batch").value,
    type: document.getElementById("filter-type").value,
    status: document.getElementById("filter-status").value,
    search: document.getElementById("filter-search").value.toLowerCase(),
  }};
}}

function cardMatchesFilters(card, filters) {{
  // Language filter
  if (filters.lang !== "all") {{
    if (filters.lang === "universal" && card.lang !== "universal") return false;
    if (filters.lang !== "universal" && card.lang !== filters.lang && card.lang !== "universal") return false;
    // Show universal when a specific language is selected
    if (filters.lang !== "universal" && filters.lang !== "all") {{
      if (card.lang !== filters.lang && card.lang !== "universal") return false;
    }}
  }}

  // Batch filter
  if (filters.batch !== "all" && String(card.batch) !== filters.batch) return false;

  // Type filter
  if (filters.type !== "all" && card.type !== filters.type) return false;

  // Status filter
  const state = reviewState[card.id] || {{ status: null }};
  if (filters.status === "unreviewed" && state.status !== null) return false;
  if (filters.status === "correct" && state.status !== "correct") return false;
  if (filters.status === "uncertain" && state.status !== "uncertain") return false;
  if (filters.status === "wrong" && state.status !== "wrong") return false;
  if (filters.status === "flagged" && state.status !== "uncertain" && state.status !== "wrong") return false;

  // Search filter
  if (filters.search) {{
    const text = (card.name + " " + card.description + " " + card.rule + " " + card.source + " " + (card.notes || "")).toLowerCase();
    if (!text.includes(filters.search)) return false;
  }}

  return true;
}}

function renderCards() {{
  const container = document.getElementById("cards-container");
  const filters = getFilters();

  // Sort: universal first, then by language order, then by batch
  const langOrder = ["universal", ...{json.dumps(TIER_1_LANGS)}, ...{json.dumps(TIER_2_LANGS)}];

  const visible = CARDS.filter(c => cardMatchesFilters(c, filters));

  // Group by language
  const grouped = {{}};
  for (const c of visible) {{
    const key = c.lang;
    if (!grouped[key]) grouped[key] = [];
    grouped[key].push(c);
  }}

  let html = "";
  let visibleCount = 0;

  for (const lang of langOrder) {{
    if (!grouped[lang]) continue;
    const langLabel = lang === "universal" ? "Universal Rules" : lang;
    html += '<div class="section-label">' + escapeHtml(langLabel) + ' (' + grouped[lang].length + ' rules)</div>';
    for (const card of grouped[lang]) {{
      html += renderCard(card);
      visibleCount++;
    }}
  }}

  // Any remaining languages not in the order
  for (const lang of Object.keys(grouped)) {{
    if (langOrder.includes(lang)) continue;
    html += '<div class="section-label">' + escapeHtml(lang) + '</div>';
    for (const card of grouped[lang]) {{
      html += renderCard(card);
      visibleCount++;
    }}
  }}

  if (visibleCount === 0) {{
    html = '<div class="no-results">No rules match the current filters.</div>';
  }}

  container.innerHTML = html;
  updateStats(visibleCount);
}}

function updateStats(visibleCount) {{
  if (visibleCount === undefined) {{
    visibleCount = document.querySelectorAll(".card").length;
  }}
  document.getElementById("stat-total").textContent = CARDS.length;
  document.getElementById("stat-visible").textContent = visibleCount;

  let reviewed = 0, uncertain = 0, wrong = 0;
  for (const id of Object.keys(reviewState)) {{
    const s = reviewState[id].status;
    if (s) reviewed++;
    if (s === "uncertain") uncertain++;
    if (s === "wrong") wrong++;
  }}
  document.getElementById("stat-reviewed").textContent = reviewed;
  document.getElementById("stat-uncertain").textContent = uncertain;
  document.getElementById("stat-wrong").textContent = wrong;
}}

function exportFeedback() {{
  const feedback = {{
    exported_at: new Date().toISOString(),
    total_rules: CARDS.length,
    reviews: {{}}
  }};

  for (const card of CARDS) {{
    const state = reviewState[card.id];
    if (state && (state.status || state.note)) {{
      feedback.reviews[card.name + " (" + card.lang + ")"] = {{
        rule_name: card.name,
        language: card.lang,
        source: card.source,
        batch: card.batch,
        status: state.status || "unreviewed",
        note: state.note || "",
      }};
    }}
  }}

  const reviewed = Object.values(feedback.reviews);
  feedback.summary = {{
    reviewed: reviewed.length,
    correct: reviewed.filter(r => r.status === "correct").length,
    uncertain: reviewed.filter(r => r.status === "uncertain").length,
    wrong: reviewed.filter(r => r.status === "wrong").length,
  }};

  const blob = new Blob([JSON.stringify(feedback, null, 2)], {{ type: "application/json" }});
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = "typography-review-feedback.json";
  a.click();
  URL.revokeObjectURL(url);
}}

function resetAll() {{
  if (confirm("Reset all review marks and notes? This cannot be undone.")) {{
    reviewState = {{}};
    saveState();
    renderCards();
  }}
}}

// Event listeners
document.getElementById("filter-lang").addEventListener("change", renderCards);
document.getElementById("filter-batch").addEventListener("change", renderCards);
document.getElementById("filter-type").addEventListener("change", renderCards);
document.getElementById("filter-status").addEventListener("change", renderCards);
document.getElementById("filter-search").addEventListener("input", renderCards);

// Initial render
renderCards();
</script>

</body>
</html>"""

    return html


def main():
    print("Reading schema...")
    with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
        schema = yaml.safe_load(f)

    print("Extracting rules...")
    cards = parse_schema(schema)
    print(f"  Found {len(cards)} rule cards")

    print("Building HTML...")
    html = build_html(cards)

    print(f"Writing {OUTPUT_PATH}...")
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"Done. {len(cards)} rules rendered to {OUTPUT_PATH.name}")


if __name__ == "__main__":
    main()
