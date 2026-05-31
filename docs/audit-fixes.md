# UX/UI Audit — Fix List

Each fix must be verified in isolation **and** against all previously completed fixes before moving to the next. This is a recursive review chain: after fixing item N, re-verify items 1 through N-1 still hold.

---

## 1. Filter bar: fix nested buttons (invalid HTML)

**Problem:** `<button class="filter-pill">` elements are nested inside `<button class="filter-toggle">`. This is invalid HTML — browsers handle it unpredictably, keyboard navigation breaks, screen readers announce it incorrectly.

**Fix:** Change `.filter-toggle` from `<button>` to `<div role="button" tabindex="0">`, or extract the `.filter-dropdown` out of the toggle button entirely and position it as a sibling. The dropdown should use `role="menu"` with `role="menuitem"` on each pill, or keep pills as standalone `<button>` elements inside a non-button container.

**Files:** `docs/index.html` — HTML at ~lines 1888-1932, JS at ~lines 3458-3553
**Verify:** Tab through the filter bar with keyboard. Each pill must be focusable and activatable with Enter/Space. Screen reader must announce toggle state.

---

## 2. Filter bar: add background

**Problem:** `.filter-bar` is `position: sticky; top: 0; z-index: 100` but has no `background` property. When sticky, page content scrolls behind it with no visual separation.

**Fix:** Add `background: var(--surface)` (or `rgba(242,241,237,0.92)` with `backdrop-filter: blur(12px)` for a frosted effect). Add a subtle `box-shadow: 0 1px 0 var(--border-light)` for grounding.

**Files:** `docs/index.html` — CSS `.filter-bar` at ~line 1076
**Verify:** Scroll the rules section. The filter bar must have a solid/frosted backing. No content bleeding through.

---

## 3. Filter bar: mobile touch targets

**Problem:** `.filter-toggle` is ~24px tall on mobile (8px font, 6px 10px padding). `.filter-pill` in dropdowns is ~22px tall. Both fail the 44px minimum touch target.

**Fix:** Mobile override should set `.filter-toggle { min-height: 44px; padding: 10px 14px; font-size: 10px; }` and `.filter-pill { min-height: 36px; padding: 8px 14px; }` (pills inside dropdown can be slightly smaller since they have spacing between them, but the toggle itself must be 44px).

**Files:** `docs/index.html` — CSS `@media (max-width: 700px)` block, ~line 780
**Verify:** Test on a 375px viewport. All tappable elements in the filter bar must be comfortable to hit with a thumb.

---

## 4. Filter bar: add ARIA attributes

**Problem:** Filter toggles have no `aria-expanded`, `aria-haspopup`, or `aria-controls`. No Escape key handler to close dropdowns.

**Fix:**
- Add `aria-haspopup="true"` and `aria-expanded="false"` to each toggle element
- Toggle `aria-expanded` in JS when opening/closing
- Add `aria-controls="lang-filters"` / `aria-controls="cat-filters"`
- Add keydown listener for Escape to close open dropdowns
- Add `role="group"` or `role="listbox"` to the dropdown containers

**Files:** `docs/index.html` — HTML ~lines 1888-1932, JS ~lines 3527-3541
**Verify:** Use VoiceOver or NVDA. Toggle must announce "expanded"/"collapsed". Escape must close.

---

## 5. Filter bar: add "All" reset pill to category dropdown

**Problem:** Language dropdown has "Show All" but category dropdown has no equivalent. Users must re-click the active pill to deselect — this is undiscoverable.

**Fix:** Add `<button class="filter-pill" data-cat="all">All</button>` as the first pill in `#cat-filters`. Update JS to handle `cat === 'all'` as a reset (set `activeCat = null`, remove active class from all cat pills, add active to the "All" pill).

**Files:** `docs/index.html` — HTML ~line 1917, JS ~line 3530
**Verify:** Click a category. Click "All". Rules must reset to show all categories. The "All" pill must show as active by default.

---

## 6. Contrast: white on amber

**Problem:** Multiple elements use white or near-white text on `#FFA000` amber background:
- Lint button: `white` on `#FFA000` = 1.8:1 (needs 4.5:1)
- Title accent dot: `white` on `#FFA000` = 1.8:1
- Cover subtitle: `#5C3600` on `#FFA000` = 3.1:1
- Cover eyebrow: `#5C3600` on `#FFA000` = 3.1:1
- Active filter pill: `white` on `#FFA000` = 1.8:1

**Fix:**
- Lint button: change to `background: var(--ink); color: #fff` (dark button, not amber)
- Title accent: change to `color: #3D1F00` (matches h1 color, still visible as accent via weight/size)
- Cover subtitle + eyebrow: darken to `color: #2D1500` or similar (target 4.5:1+)
- Active filter pill: change to `background: var(--ink); color: #fff` or `background: #CC8000; color: #fff` (darker amber)

**Files:** `docs/index.html` — CSS at lines 95 (title-accent), 81 (eyebrow), 101 (h2), 1009 (demo-btn), 1160 (filter-pill.active)
**Verify:** Run each combination through a contrast checker. All must pass WCAG AA (4.5:1 for normal text, 3:1 for large text ≥18pt).

---

## 7. Contrast: ink-muted on surface

**Problem:** `--ink-muted: #707070` on `--surface: #F2F1ED` = 3.9:1. Used for dozens of labels, descriptions, and secondary text at small sizes (9px, 10px). Fails AA at those sizes.

**Fix:** Darken `--ink-muted` from `#707070` to `#5F5F5F` (~5.0:1 on `#F2F1ED`). This is a single variable change that cascades everywhere.

**Files:** `docs/index.html` — CSS `:root` at ~line 22
**Verify:** Spot-check all muted text: filter count, demo labels, footer, category descriptions, table headers. All must remain readable and pass 4.5:1.

---

## 8. Contrast: rule-name pills

**Problem:** `#CC8000` (`--amber-dark`) on `#FFF3CC` (`--amber-soft`) = 3.2:1 at 9px font. Fails AA.

**Fix:** Darken `--amber-dark` from `#CC8000` to `#996000` (~5.3:1 on `#FFF3CC`). Or darken the soft background: change `--amber-soft` to `#FFE8A0` and keep `--amber-dark`.

**Files:** `docs/index.html` — CSS `:root` at ~line 25
**Verify:** Check rule-name pills across the rules section. Must pass 4.5:1.

---

## 9. Form labels

**Problem:** `<textarea id="demo-input">` and `<select id="demo-lang">` have no `<label>` or `aria-label`. The visual labels are `<span class="demo-area-label">` with no programmatic association.

**Fix:**
- Change `<span class="demo-area-label">Your text</span>` to `<label for="demo-input" class="demo-area-label">Your text</label>`
- Add `aria-label="Select language"` to `<select id="demo-lang">`
- Or add a `<label for="demo-lang">` if space allows

**Files:** `docs/index.html` — HTML ~lines 1841, 1848
**Verify:** Click the "Your text" label — textarea must receive focus. VoiceOver must announce "Your text, text area" when focusing the textarea.

---

## 10. Demo output: aria-live

**Problem:** `#demo-output` and `#demo-corrections` are dynamically updated by JS but have no `aria-live`. Screen readers won't announce changes.

**Fix:**
- Add `aria-live="polite"` and `role="status"` to `<div id="demo-output">`
- Add `aria-live="polite"` to `<ul id="demo-corrections">`

**Files:** `docs/index.html` — HTML ~lines 1876, 1879
**Verify:** With VoiceOver on, click "Lint". The corrected text must be announced.

---

## 11. Focus indicators

**Problem:** `outline: none` on `.demo-textarea:focus` (line 985) and `.demo-select` (line 1000) with no replacement. Filter pills and lang-pills also lack `:focus-visible` styles.

**Fix:**
- Remove `outline: none` from textarea and select, or replace with `outline: 2px solid var(--amber); outline-offset: 2px` on `:focus-visible`
- Add `:focus-visible` styles to `.filter-pill`, `.filter-toggle`, `.lang-pill`, `.pill-contribute`
- Use `:focus-visible` (not `:focus`) to avoid showing outlines on click

**Files:** `docs/index.html` — CSS at ~lines 985, 1000, 1141, 665, 628
**Verify:** Tab through the entire page. Every interactive element must show a visible focus ring.

---

## 12. Erosion illustration: respect prefers-reduced-motion

**Problem:** The erosion animation JS runs `setTimeout` loops for character-by-character erosion/restoration regardless of motion preference. CSS catches transitions but JS sequencing still causes visible movement.

**Fix:** In the erosion IIFE, check `window.matchMedia('(prefers-reduced-motion: reduce)').matches` at the top. If true, show the first specimen in its "correct" state statically — skip the erosion/restoration cycle entirely.

**Files:** `docs/index.html` — JS erosion IIFE, ~line 4033
**Verify:** Enable "Reduce motion" in system preferences. The erosion illustration must show a static specimen with no animation.

---

## 13. Demo panel: max-width alignment

**Problem:** `.demo-panel` was given `max-width: 800px` but needs to be verified against other sections (premise, journey, CTA) for consistent content width.

**Fix:** Already applied. Verify it matches the 800px used by `.premise-body`, `.journey-card`, `.cta-heading`, `.cta-body`, `.install-card`, `.author-section`.

**Files:** `docs/index.html` — CSS `.demo-panel` at ~line 939
**Verify:** Compare content width of demo panel to premise body and CTA section at full desktop width. Must align.

---

## 14. Cover h1 mobile sizing

**Problem:** Already partially fixed (28px with 24px/16px padding). Verify it works on 375px and 320px viewports.

**Fix:** Already applied. Verify no text overflow or awkward line breaks on smallest common viewport (320px iPhone SE).

**Files:** `docs/index.html` — CSS `@media (max-width: 700px)` ~line 739
**Verify:** Chrome DevTools → 320px width. "Typeproof." must not overflow or get clipped.

---

## 15. SVG alt text

**Problem:** Cover logo SVG and author section SVGs have no `<title>` element or `aria-hidden`.

**Fix:**
- Add `aria-hidden="true"` to decorative SVGs (the tudotype wordmark is decorative since "Typeproof" is in the h1)
- Or add `<title>Typeproof logo</title>` as first child of the SVG and `role="img"` on the SVG element

**Files:** `docs/index.html` — HTML ~line 1672
**Verify:** VoiceOver must either skip the SVG entirely (if `aria-hidden`) or announce "Typeproof logo" (if titled).

---

## 16. Section ARIA labels

**Problem:** Multiple `<section>` elements with no distinguishing `aria-label`. Landmark navigation is unhelpful.

**Fix:** Add `aria-label` to each major section:
- `<section class="cover" aria-label="Cover">`
- `<section class="premise" aria-label="Premise">`
- `<section class="journey" aria-label="The Journey">`
- `<section class="demo-section" aria-label="Live Demo">`
- `<section class="cta-section" aria-label="Contribute">`

**Files:** `docs/index.html` — HTML section elements
**Verify:** VoiceOver rotor → Landmarks. Each section must appear with its label.

---

## Review Protocol

After completing each fix:

1. **Verify the fix works** — test the specific behavior described in "Verify"
2. **Re-verify all previous fixes** — quickly check each completed item still holds
3. **Check for regressions** — ensure the fix didn't break layout, functionality, or accessibility elsewhere
4. **Only then move to the next fix**

This recursive review prevents cascading breakage. If a later fix undoes an earlier one, catch it immediately.
