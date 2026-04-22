#!/usr/bin/env python3
"""
Build an interactive HTML review page for typography training pairs.

Samples a representative subset from the JSONL dataset, stratified by
language, rule, and pair type, then generates a self-contained HTML file
for human spot-checking.
"""

import json
import random
import html
import os
from collections import defaultdict
from pathlib import Path

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

JSONL_PATH = Path(__file__).parent / "typography_training.jsonl"
OUTPUT_PATH = Path(__file__).parent / "training-pair-review.html"

TIER_1 = ["pt-PT", "pt-BR", "en-US", "en-GB", "fr-FR", "de-DE", "it-IT", "es-ES", "es-MX"]
TIER_2 = ["nl-NL", "nl-BE", "ro-RO", "sc"]
ALL_LANGUAGES = TIER_1 + TIER_2 + ["_universal"]

TIER_1_PER_RULE = 5
TIER_2_PER_RULE = 3
UNIVERSAL_PER_RULE = 3
MAX_TOTAL = 200

PAIR_TYPES = ["correction", "detection", "cross_language", "explanation"]

SEED = 42

# Map of invisible/special Unicode characters to display labels
INVISIBLE_CHARS = {
    "\u00A0": ("NBSP", "#e74c3c"),
    "\u202F": ("NNBSP", "#e67e22"),
    "\u200B": ("ZWSP", "#9b59b6"),
    "\u200C": ("ZWNJ", "#8e44ad"),
    "\u200D": ("ZWJ", "#2980b9"),
    "\u2009": ("THIN SP", "#16a085"),
    "\u200A": ("HAIR SP", "#1abc9c"),
    "\uFEFF": ("BOM", "#c0392b"),
    "\u2060": ("WJ", "#d35400"),
    "\u034F": ("CGJ", "#7f8c8d"),
    "\u061C": ("ALM", "#7f8c8d"),
    "\u200E": ("LRM", "#95a5a6"),
    "\u200F": ("RLM", "#95a5a6"),
    "\u2028": ("LSEP", "#bdc3c7"),
    "\u2029": ("PSEP", "#bdc3c7"),
    "\u2007": ("FIG SP", "#27ae60"),
    "\u2008": ("PUNC SP", "#2ecc71"),
    "\u205F": ("MMSP", "#3498db"),
}


# ---------------------------------------------------------------------------
# Load & sample
# ---------------------------------------------------------------------------

def load_pairs():
    pairs = []
    with open(JSONL_PATH, "r", encoding="utf-8") as f:
        for i, line in enumerate(f):
            obj = json.loads(line)
            obj["_id"] = i
            pairs.append(obj)
    return pairs


def get_lang(pair):
    m = pair["metadata"]
    if m["type"] == "cross_language":
        return m.get("target_language", "_universal")
    return m.get("language", "_universal")


def get_rule(pair):
    m = pair["metadata"]
    if m["type"] == "cross_language":
        return "cross_language"
    return m.get("rule", "unknown")


def sample_pairs(all_pairs):
    random.seed(SEED)

    # Bucket by (language, rule, type)
    buckets = defaultdict(list)
    for p in all_pairs:
        lang = get_lang(p)
        rule = get_rule(p)
        ptype = p["metadata"]["type"]
        buckets[(lang, rule, ptype)].append(p)

    selected = []
    # Process each language
    for lang in ALL_LANGUAGES:
        if lang in TIER_1:
            per_rule = TIER_1_PER_RULE
        elif lang in TIER_2:
            per_rule = TIER_2_PER_RULE
        else:
            per_rule = UNIVERSAL_PER_RULE

        # Find all rules for this language
        rules_for_lang = set()
        for (l, r, t) in buckets:
            if l == lang:
                rules_for_lang.add(r)

        for rule in sorted(rules_for_lang):
            # Gather all types for this lang-rule combo
            type_buckets = {}
            for ptype in PAIR_TYPES:
                key = (lang, rule, ptype)
                if key in buckets and buckets[key]:
                    type_buckets[ptype] = list(buckets[key])

            if not type_buckets:
                continue

            # Distribute per_rule across available types
            total_available = sum(len(v) for v in type_buckets.values())
            budget = min(per_rule, total_available)

            # Try to get at least 1 from each type, then fill remaining
            picked = []
            remaining_budget = budget
            for ptype in PAIR_TYPES:
                if ptype in type_buckets and remaining_budget > 0:
                    sample_n = max(1, budget // len(type_buckets))
                    sample_n = min(sample_n, len(type_buckets[ptype]), remaining_budget)
                    chosen = random.sample(type_buckets[ptype], sample_n)
                    picked.extend(chosen)
                    remaining_budget -= len(chosen)

            selected.extend(picked)

    # Cap at MAX_TOTAL with stratified downsampling (preserve language representation)
    if len(selected) > MAX_TOTAL:
        # Group by language, then proportionally downsample each group
        by_lang = defaultdict(list)
        for p in selected:
            by_lang[get_lang(p)].append(p)

        # Ensure every language gets at least 2 pairs, distribute rest proportionally
        total_before = len(selected)
        reserved = min(2, MAX_TOTAL // len(by_lang))
        remaining_budget = MAX_TOTAL

        final = []
        for lang in ALL_LANGUAGES:
            if lang not in by_lang:
                continue
            pool = by_lang[lang]
            # Proportional share, but at least `reserved`
            share = max(reserved, round(len(pool) / total_before * MAX_TOTAL))
            share = min(share, len(pool), remaining_budget)
            if share <= 0:
                continue
            chosen = random.sample(pool, share)
            final.extend(chosen)
            remaining_budget -= len(chosen)

        selected = final

    # Sort for display: by language order, then rule, then type
    lang_order = {l: i for i, l in enumerate(ALL_LANGUAGES)}
    selected.sort(key=lambda p: (
        lang_order.get(get_lang(p), 99),
        get_rule(p),
        p["metadata"]["type"]
    ))

    return selected


# ---------------------------------------------------------------------------
# HTML generation helpers
# ---------------------------------------------------------------------------

def esc(text):
    """HTML-escape text."""
    return html.escape(text, quote=True)


def render_invisible_chars(text):
    """Replace invisible Unicode characters with visible indicator spans."""
    result = []
    for ch in text:
        if ch in INVISIBLE_CHARS:
            label, color = INVISIBLE_CHARS[ch]
            result.append(
                f'<span class="invis-char" style="border-color:{color};color:{color}" '
                f'title="{label} (U+{ord(ch):04X})">{label}</span>'
            )
        else:
            result.append(esc(ch))
    return "".join(result)


def char_diff(old_text, new_text):
    """
    Produce character-level diff HTML for old and new text.
    Returns (old_html, new_html) with changed characters highlighted.
    Uses a simple LCS-based diff.
    """
    # Build LCS table
    m, n = len(old_text), len(new_text)

    # For very long strings, fall back to simple display
    if m * n > 500000:
        return render_invisible_chars(old_text), render_invisible_chars(new_text)

    dp = [[0] * (n + 1) for _ in range(m + 1)]
    for i in range(1, m + 1):
        for j in range(1, n + 1):
            if old_text[i - 1] == new_text[j - 1]:
                dp[i][j] = dp[i - 1][j - 1] + 1
            else:
                dp[i][j] = max(dp[i - 1][j], dp[i][j - 1])

    # Backtrack to build diff ops
    ops = []
    i, j = m, n
    while i > 0 or j > 0:
        if i > 0 and j > 0 and old_text[i - 1] == new_text[j - 1]:
            ops.append(("equal", old_text[i - 1], new_text[j - 1]))
            i -= 1
            j -= 1
        elif j > 0 and (i == 0 or dp[i][j - 1] >= dp[i - 1][j]):
            ops.append(("insert", None, new_text[j - 1]))
            j -= 1
        else:
            ops.append(("delete", old_text[i - 1], None))
            i -= 1
    ops.reverse()

    old_parts = []
    new_parts = []

    def render_char(ch, cls=None):
        if ch in INVISIBLE_CHARS:
            label, color = INVISIBLE_CHARS[ch]
            extra_cls = f" {cls}" if cls else ""
            return (
                f'<span class="invis-char{extra_cls}" style="border-color:{color};color:{color}" '
                f'title="{label} (U+{ord(ch):04X})">{label}</span>'
            )
        else:
            if cls:
                return f'<span class="{cls}">{esc(ch)}</span>'
            return esc(ch)

    for op, old_ch, new_ch in ops:
        if op == "equal":
            old_parts.append(render_char(old_ch))
            new_parts.append(render_char(new_ch))
        elif op == "delete":
            old_parts.append(render_char(old_ch, "diff-del"))
        elif op == "insert":
            new_parts.append(render_char(new_ch, "diff-ins"))

    return "".join(old_parts), "".join(new_parts)


def render_card(pair, index):
    """Render a single pair as an HTML card."""
    m = pair["metadata"]
    ptype = m["type"]
    lang = get_lang(pair)
    rule = get_rule(pair)

    lang_display = lang.upper() if lang != "_universal" else "UNIVERSAL"

    type_colors = {
        "correction": "#3498db",
        "detection": "#e67e22",
        "cross_language": "#9b59b6",
        "explanation": "#27ae60",
    }
    type_color = type_colors.get(ptype, "#95a5a6")

    # Build card content based on type
    content_html = ""

    if ptype == "correction":
        input_text = pair.get("input", "")
        output_text = pair.get("output", "")
        old_html, new_html = char_diff(input_text, output_text)
        content_html = f'''
        <div class="diff-container">
            <div class="diff-panel diff-old">
                <div class="diff-label">Raw (input)</div>
                <div class="diff-text">{old_html}</div>
            </div>
            <div class="diff-arrow">&#x2192;</div>
            <div class="diff-panel diff-new">
                <div class="diff-label">Corrected (output)</div>
                <div class="diff-text">{new_html}</div>
            </div>
        </div>'''

    elif ptype == "detection":
        input_text = pair.get("input", "")
        output_text = pair.get("output", "")
        content_html = f'''
        <div class="detect-container">
            <div class="detect-input">
                <div class="diff-label">Input text</div>
                <div class="diff-text">{render_invisible_chars(input_text)}</div>
            </div>
            <div class="detect-output">
                <div class="diff-label">Detection output</div>
                <div class="diff-text explanation-text">{render_invisible_chars(output_text)}</div>
            </div>
        </div>'''

    elif ptype == "explanation":
        input_text = pair.get("input", "")
        output_text = pair.get("output", "")
        content_html = f'''
        <div class="explain-container">
            <div class="explain-input">
                <div class="diff-label">Input</div>
                <div class="diff-text">{render_invisible_chars(input_text)}</div>
            </div>
            <div class="explain-output">
                <div class="diff-label">Explanation</div>
                <div class="diff-text explanation-text">{render_invisible_chars(output_text)}</div>
            </div>
        </div>'''

    elif ptype == "cross_language":
        src_lang = m.get("source_language", "?")
        tgt_lang = m.get("target_language", "?")
        input_text = pair.get("input", "")
        output_text = pair.get("output", "")
        content_html = f'''
        <div class="cross-container">
            <div class="cross-panel">
                <div class="diff-label">Source ({esc(src_lang)})</div>
                <div class="diff-text">{render_invisible_chars(input_text)}</div>
            </div>
            <div class="diff-arrow">&#x2192;</div>
            <div class="cross-panel">
                <div class="diff-label">Target ({esc(tgt_lang)})</div>
                <div class="diff-text">{render_invisible_chars(output_text)}</div>
            </div>
        </div>'''

    instruction_html = esc(pair.get("instruction", ""))

    return f'''
    <div class="card" data-lang="{esc(lang)}" data-rule="{esc(rule)}" data-type="{esc(ptype)}" data-status="" data-index="{index}">
        <div class="card-header">
            <div class="badges">
                <span class="badge badge-lang">{esc(lang_display)}</span>
                <span class="badge badge-rule">{esc(rule)}</span>
                <span class="badge badge-type" style="background:{type_color}">{esc(ptype)}</span>
            </div>
            <div class="card-id">#{index + 1}</div>
        </div>
        <div class="instruction">{instruction_html}</div>
        {content_html}
        <div class="review-controls">
            <button class="review-btn btn-correct" onclick="setStatus(this, 'correct')" title="Correct">&#x2713; Correct</button>
            <button class="review-btn btn-uncertain" onclick="setStatus(this, 'uncertain')" title="Uncertain">? Uncertain</button>
            <button class="review-btn btn-wrong" onclick="setStatus(this, 'wrong')" title="Wrong">&#x2717; Wrong</button>
            <input type="text" class="note-input" placeholder="Notes..." oninput="updateNote(this)">
        </div>
    </div>'''


def build_html(sampled_pairs):
    """Build the full self-contained HTML page."""

    # Gather unique languages and rules for filters
    languages = []
    seen_langs = set()
    rules = set()
    type_counts = defaultdict(int)
    lang_counts = defaultdict(int)
    rule_counts = defaultdict(int)

    for p in sampled_pairs:
        lang = get_lang(p)
        rule = get_rule(p)
        ptype = p["metadata"]["type"]
        if lang not in seen_langs:
            languages.append(lang)
            seen_langs.add(lang)
        rules.add(rule)
        type_counts[ptype] += 1
        lang_counts[lang] += 1
        rule_counts[rule] += 1

    # Render all cards
    cards_html = "\n".join(render_card(p, i) for i, p in enumerate(sampled_pairs))

    # Language tabs
    lang_tabs = '<button class="tab active" data-filter-lang="all" onclick="filterLang(this)">All</button>\n'
    for lang in languages:
        display = lang.upper() if lang != "_universal" else "UNIV"
        count = lang_counts[lang]
        lang_tabs += f'<button class="tab" data-filter-lang="{esc(lang)}" onclick="filterLang(this)">{esc(display)} ({count})</button>\n'

    # Type filter buttons
    type_filters = '<button class="tab active" data-filter-type="all" onclick="filterType(this)">All</button>\n'
    for t in PAIR_TYPES:
        count = type_counts.get(t, 0)
        type_filters += f'<button class="tab" data-filter-type="{esc(t)}" onclick="filterType(this)">{esc(t)} ({count})</button>\n'

    # Build pairs data JSON for export
    pairs_meta = []
    for i, p in enumerate(sampled_pairs):
        pairs_meta.append({
            "index": i,
            "id": p["_id"],
            "language": get_lang(p),
            "rule": get_rule(p),
            "type": p["metadata"]["type"],
            "input": p.get("input", ""),
            "output": p.get("output", ""),
        })
    pairs_json = json.dumps(pairs_meta, ensure_ascii=False)

    total = len(sampled_pairs)

    html_doc = f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Typography Training Pair Review</title>
<style>
:root {{
    --bg: #f5f5f7;
    --card-bg: #ffffff;
    --border: #e0e0e0;
    --text: #1d1d1f;
    --text-secondary: #6e6e73;
    --accent: #0071e3;
    --correct-bg: #e8f5e9;
    --correct-border: #4caf50;
    --uncertain-bg: #fff8e1;
    --uncertain-border: #ff9800;
    --wrong-bg: #ffebee;
    --wrong-border: #f44336;
    --diff-del-bg: #fecdd2;
    --diff-ins-bg: #c8e6c9;
}}

* {{ margin: 0; padding: 0; box-sizing: border-box; }}

body {{
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    background: var(--bg);
    color: var(--text);
    line-height: 1.5;
    padding: 0;
}}

.header {{
    background: #1d1d1f;
    color: #f5f5f7;
    padding: 24px 32px;
    position: sticky;
    top: 0;
    z-index: 100;
}}

.header h1 {{
    font-size: 20px;
    font-weight: 600;
    letter-spacing: -0.02em;
}}

.header .subtitle {{
    font-size: 13px;
    color: #a1a1a6;
    margin-top: 4px;
}}

.stats-bar {{
    display: flex;
    gap: 24px;
    padding: 16px 32px;
    background: #fff;
    border-bottom: 1px solid var(--border);
    font-size: 13px;
    flex-wrap: wrap;
    align-items: center;
}}

.stat {{
    display: flex;
    align-items: center;
    gap: 6px;
}}

.stat-value {{
    font-weight: 700;
    font-size: 18px;
}}

.stat-label {{
    color: var(--text-secondary);
}}

.controls {{
    padding: 16px 32px;
    background: #fff;
    border-bottom: 1px solid var(--border);
}}

.control-row {{
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    align-items: center;
    margin-bottom: 8px;
}}

.control-row:last-child {{ margin-bottom: 0; }}

.control-label {{
    font-size: 12px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: var(--text-secondary);
    min-width: 80px;
}}

.tab {{
    padding: 6px 12px;
    border: 1px solid var(--border);
    background: #fff;
    border-radius: 6px;
    font-size: 12px;
    cursor: pointer;
    transition: all 0.15s;
    font-family: inherit;
    white-space: nowrap;
}}

.tab:hover {{ background: #f0f0f0; }}
.tab.active {{ background: var(--accent); color: #fff; border-color: var(--accent); }}

.action-row {{
    display: flex;
    gap: 8px;
    padding: 12px 32px;
    background: #fff;
    border-bottom: 1px solid var(--border);
}}

.action-btn {{
    padding: 8px 16px;
    border: 1px solid var(--border);
    background: #fff;
    border-radius: 6px;
    font-size: 13px;
    cursor: pointer;
    font-family: inherit;
    transition: all 0.15s;
}}

.action-btn:hover {{ background: #f0f0f0; }}
.action-btn.primary {{ background: var(--accent); color: #fff; border-color: var(--accent); }}
.action-btn.primary:hover {{ background: #005bb5; }}

.container {{
    max-width: 1100px;
    margin: 0 auto;
    padding: 24px 32px;
}}

.card {{
    background: var(--card-bg);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 20px;
    margin-bottom: 16px;
    transition: border-color 0.2s, box-shadow 0.2s;
}}

.card[data-status="correct"] {{ border-color: var(--correct-border); background: var(--correct-bg); }}
.card[data-status="uncertain"] {{ border-color: var(--uncertain-border); background: var(--uncertain-bg); }}
.card[data-status="wrong"] {{ border-color: var(--wrong-border); background: var(--wrong-bg); }}

.card.hidden {{ display: none; }}

.card-header {{
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 12px;
}}

.badges {{ display: flex; gap: 6px; flex-wrap: wrap; }}

.badge {{
    padding: 3px 8px;
    border-radius: 4px;
    font-size: 11px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.03em;
}}

.badge-lang {{ background: #e8e8ed; color: #1d1d1f; }}
.badge-rule {{ background: #f0f0f5; color: #48484a; }}
.badge-type {{ color: #fff; }}

.card-id {{ font-size: 12px; color: var(--text-secondary); }}

.instruction {{
    font-size: 12px;
    color: var(--text-secondary);
    margin-bottom: 12px;
    font-style: italic;
}}

.diff-container, .cross-container {{
    display: flex;
    gap: 12px;
    align-items: stretch;
}}

.diff-panel, .cross-panel {{
    flex: 1;
    background: #fafafa;
    border: 1px solid #eee;
    border-radius: 8px;
    padding: 12px;
    min-width: 0;
}}

.diff-arrow {{
    display: flex;
    align-items: center;
    font-size: 20px;
    color: var(--text-secondary);
    padding: 0 4px;
    flex-shrink: 0;
}}

.diff-label {{
    font-size: 11px;
    font-weight: 600;
    text-transform: uppercase;
    color: var(--text-secondary);
    margin-bottom: 6px;
    letter-spacing: 0.04em;
}}

.diff-text {{
    font-size: 15px;
    line-height: 1.7;
    word-break: break-word;
    white-space: pre-wrap;
}}

.diff-del {{
    background: var(--diff-del-bg);
    border-radius: 2px;
    padding: 0 1px;
    text-decoration: line-through;
    text-decoration-color: rgba(244,67,54,0.5);
}}

.diff-ins {{
    background: var(--diff-ins-bg);
    border-radius: 2px;
    padding: 0 1px;
}}

.invis-char {{
    display: inline-block;
    border: 1.5px dotted;
    border-radius: 3px;
    padding: 0 3px;
    font-size: 9px;
    font-weight: 700;
    letter-spacing: 0.02em;
    vertical-align: baseline;
    line-height: 1.6;
    margin: 0 1px;
}}

.detect-container, .explain-container {{
    display: flex;
    flex-direction: column;
    gap: 12px;
}}

.detect-input, .detect-output, .explain-input, .explain-output {{
    background: #fafafa;
    border: 1px solid #eee;
    border-radius: 8px;
    padding: 12px;
}}

.explanation-text {{
    font-size: 13px;
    color: var(--text-secondary);
}}

.review-controls {{
    display: flex;
    gap: 8px;
    margin-top: 14px;
    align-items: center;
    flex-wrap: wrap;
}}

.review-btn {{
    padding: 6px 14px;
    border: 1px solid var(--border);
    background: #fff;
    border-radius: 6px;
    font-size: 12px;
    cursor: pointer;
    font-family: inherit;
    transition: all 0.15s;
}}

.review-btn:hover {{ opacity: 0.8; }}
.review-btn.active-correct {{ background: var(--correct-border); color: #fff; border-color: var(--correct-border); }}
.review-btn.active-uncertain {{ background: var(--uncertain-border); color: #fff; border-color: var(--uncertain-border); }}
.review-btn.active-wrong {{ background: var(--wrong-border); color: #fff; border-color: var(--wrong-border); }}

.note-input {{
    flex: 1;
    min-width: 150px;
    padding: 6px 10px;
    border: 1px solid var(--border);
    border-radius: 6px;
    font-size: 12px;
    font-family: inherit;
}}

.note-input:focus {{ outline: none; border-color: var(--accent); }}

.empty-state {{
    text-align: center;
    padding: 60px 20px;
    color: var(--text-secondary);
    font-size: 15px;
}}

@media (max-width: 700px) {{
    .diff-container, .cross-container {{
        flex-direction: column;
    }}
    .diff-arrow {{
        transform: rotate(90deg);
        justify-content: center;
    }}
    .header, .stats-bar, .controls, .action-row, .container {{
        padding-left: 16px;
        padding-right: 16px;
    }}
}}
</style>
</head>
<body>

<div class="header">
    <h1>Typography Training Pair Review</h1>
    <div class="subtitle">Sampled {total} pairs from 3,292 total &middot; Generated for human spot-checking</div>
</div>

<div class="stats-bar" id="stats-bar">
    <div class="stat"><span class="stat-value" id="stat-total">{total}</span><span class="stat-label">Total</span></div>
    <div class="stat"><span class="stat-value" id="stat-visible">{total}</span><span class="stat-label">Visible</span></div>
    <div class="stat"><span class="stat-value" id="stat-reviewed">0</span><span class="stat-label">Reviewed</span></div>
    <div class="stat"><span class="stat-value" id="stat-correct">0</span><span class="stat-label" style="color:var(--correct-border)">Correct</span></div>
    <div class="stat"><span class="stat-value" id="stat-uncertain">0</span><span class="stat-label" style="color:var(--uncertain-border)">Uncertain</span></div>
    <div class="stat"><span class="stat-value" id="stat-wrong">0</span><span class="stat-label" style="color:var(--wrong-border)">Wrong</span></div>
</div>

<div class="controls">
    <div class="control-row">
        <span class="control-label">Language</span>
        {lang_tabs}
    </div>
    <div class="control-row">
        <span class="control-label">Type</span>
        {type_filters}
    </div>
    <div class="control-row">
        <span class="control-label">Status</span>
        <button class="tab active" data-filter-status="all" onclick="filterStatus(this)">All</button>
        <button class="tab" data-filter-status="unreviewed" onclick="filterStatus(this)">Unreviewed</button>
        <button class="tab" data-filter-status="flagged" onclick="filterStatus(this)">Flagged</button>
        <button class="tab" data-filter-status="correct" onclick="filterStatus(this)">Correct</button>
        <button class="tab" data-filter-status="uncertain" onclick="filterStatus(this)">Uncertain</button>
        <button class="tab" data-filter-status="wrong" onclick="filterStatus(this)">Wrong</button>
    </div>
</div>

<div class="action-row">
    <button class="action-btn primary" onclick="exportFeedback()">Export Feedback (JSON)</button>
    <button class="action-btn" onclick="clearAll()">Clear All Reviews</button>
</div>

<div class="container" id="cards-container">
{cards_html}
<div class="empty-state hidden" id="empty-state">No pairs match the current filters.</div>
</div>

<script>
// Pairs metadata for export
const pairsMeta = {pairs_json};

// State
let currentLang = "all";
let currentType = "all";
let currentStatus = "all";
const reviews = {{}};  // index -> {{ status, note }}

function setStatus(btn, status) {{
    const card = btn.closest(".card");
    const idx = parseInt(card.dataset.index);
    const current = card.dataset.status;

    // Toggle off if clicking same status
    if (current === status) {{
        card.dataset.status = "";
        delete reviews[idx];
        btn.closest(".review-controls").querySelectorAll(".review-btn").forEach(b => {{
            b.className = "review-btn " + b.className.split(" ").find(c => c.startsWith("btn-"));
        }});
    }} else {{
        card.dataset.status = status;
        if (!reviews[idx]) reviews[idx] = {{}};
        reviews[idx].status = status;

        // Update button states
        btn.closest(".review-controls").querySelectorAll(".review-btn").forEach(b => {{
            const baseClass = b.className.split(" ").find(c => c.startsWith("btn-"));
            b.className = "review-btn " + baseClass;
        }});
        btn.classList.add("active-" + status);
    }}

    updateStats();
    applyFilters();
}}

function updateNote(input) {{
    const card = input.closest(".card");
    const idx = parseInt(card.dataset.index);
    if (!reviews[idx]) reviews[idx] = {{}};
    reviews[idx].note = input.value;
    if (!reviews[idx].status && !input.value) {{
        delete reviews[idx];
    }}
}}

function filterLang(btn) {{
    currentLang = btn.dataset.filterLang;
    btn.parentElement.querySelectorAll(".tab").forEach(t => t.classList.remove("active"));
    btn.classList.add("active");
    applyFilters();
}}

function filterType(btn) {{
    currentType = btn.dataset.filterType;
    btn.parentElement.querySelectorAll(".tab").forEach(t => t.classList.remove("active"));
    btn.classList.add("active");
    applyFilters();
}}

function filterStatus(btn) {{
    currentStatus = btn.dataset.filterStatus;
    btn.parentElement.querySelectorAll(".tab").forEach(t => t.classList.remove("active"));
    btn.classList.add("active");
    applyFilters();
}}

function applyFilters() {{
    const cards = document.querySelectorAll(".card");
    let visible = 0;

    cards.forEach(card => {{
        const lang = card.dataset.lang;
        const type = card.dataset.type;
        const status = card.dataset.status || "";
        const idx = parseInt(card.dataset.index);

        let show = true;
        if (currentLang !== "all" && lang !== currentLang) show = false;
        if (currentType !== "all" && type !== currentType) show = false;

        if (currentStatus === "unreviewed" && status !== "") show = false;
        else if (currentStatus === "flagged" && status !== "uncertain" && status !== "wrong") show = false;
        else if (currentStatus === "correct" && status !== "correct") show = false;
        else if (currentStatus === "uncertain" && status !== "uncertain") show = false;
        else if (currentStatus === "wrong" && status !== "wrong") show = false;

        card.classList.toggle("hidden", !show);
        if (show) visible++;
    }});

    document.getElementById("stat-visible").textContent = visible;
    document.getElementById("empty-state").classList.toggle("hidden", visible > 0);
}}

function updateStats() {{
    let reviewed = 0, correct = 0, uncertain = 0, wrong = 0;
    for (const idx in reviews) {{
        if (reviews[idx].status) {{
            reviewed++;
            if (reviews[idx].status === "correct") correct++;
            if (reviews[idx].status === "uncertain") uncertain++;
            if (reviews[idx].status === "wrong") wrong++;
        }}
    }}
    document.getElementById("stat-reviewed").textContent = reviewed;
    document.getElementById("stat-correct").textContent = correct;
    document.getElementById("stat-uncertain").textContent = uncertain;
    document.getElementById("stat-wrong").textContent = wrong;
}}

function exportFeedback() {{
    const feedback = {{
        exported_at: new Date().toISOString(),
        total_pairs: {total},
        reviews: []
    }};

    for (const idx in reviews) {{
        const r = reviews[idx];
        if (r.status || r.note) {{
            const meta = pairsMeta[parseInt(idx)];
            feedback.reviews.push({{
                pair_index: parseInt(idx),
                original_id: meta.id,
                language: meta.language,
                rule: meta.rule,
                type: meta.type,
                input: meta.input,
                output: meta.output,
                status: r.status || null,
                note: r.note || null
            }});
        }}
    }}

    const blob = new Blob([JSON.stringify(feedback, null, 2)], {{ type: "application/json" }});
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "typography-review-feedback.json";
    a.click();
    URL.revokeObjectURL(url);
}}

function clearAll() {{
    if (!confirm("Clear all review statuses and notes?")) return;
    for (const idx in reviews) delete reviews[idx];
    document.querySelectorAll(".card").forEach(card => {{
        card.dataset.status = "";
        card.querySelectorAll(".review-btn").forEach(b => {{
            const baseClass = b.className.split(" ").find(c => c.startsWith("btn-"));
            b.className = "review-btn " + baseClass;
        }});
        card.querySelector(".note-input").value = "";
    }});
    updateStats();
    applyFilters();
}}
</script>

</body>
</html>'''

    return html_doc


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("Loading JSONL...")
    all_pairs = load_pairs()
    print(f"  Loaded {len(all_pairs)} pairs")

    print("Sampling representative subset...")
    sampled = sample_pairs(all_pairs)
    print(f"  Sampled {len(sampled)} pairs")

    # Print breakdown
    from collections import Counter
    lang_c = Counter(get_lang(p) for p in sampled)
    type_c = Counter(p["metadata"]["type"] for p in sampled)
    rule_c = Counter(get_rule(p) for p in sampled)

    print("\n  By language:")
    for lang in ALL_LANGUAGES:
        if lang in lang_c:
            print(f"    {lang}: {lang_c[lang]}")

    print(f"\n  By type:")
    for t in PAIR_TYPES:
        print(f"    {t}: {type_c.get(t, 0)}")

    print(f"\n  Unique rules: {len(rule_c)}")

    print("\nGenerating HTML...")
    html_content = build_html(sampled)

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        f.write(html_content)

    size_kb = os.path.getsize(OUTPUT_PATH) / 1024
    print(f"  Written to {OUTPUT_PATH} ({size_kb:.0f} KB)")
    print("Done.")


if __name__ == "__main__":
    main()
