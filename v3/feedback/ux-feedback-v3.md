# UX Design Feedback — Eden AI V3 Documentation

**Reviewed by:** UX Designer (external review)
**Date:** March 12, 2026
**Scope:** Full V3 documentation (quickstart, overview, LLMs, expert models, general, data governance, integrations)

---

## Executive Summary

The V3 docs are technically thorough and cover a wide surface area. The underlying product is genuinely powerful, and that comes through. However, the documentation currently reads like it was written for people who already understand what Eden AI is. For a new developer landing here for the first time — especially one coming from a specific use case — the experience has significant friction. The main issues are: a split mental model introduced too early, inconsistent onboarding paths, and structural redundancy that creates confusion about where to look for information.

---

## 1. Information Architecture

### 1.1 The Two-Endpoint Problem Is Not Resolved Early Enough

**Issue:** Eden AI has two core endpoints — LLM and Universal AI — and this distinction is load-bearing for everything else in the docs. Yet a user landing on the homepage (`index.mdx`) is immediately met with cards for both without a clear signal of which one applies to them.

The `llms-vs-expert-models.mdx` page exists precisely to resolve this, but it sits as the *third* page inside the Overview section — not prominently surfaced at entry points. By the time a developer has clicked into Quickstart and started reading code, they may already be on the wrong path.

**Recommendation:**
- Make the homepage card layout more decisive. Instead of "LLM Endpoint" and "Universal AI Endpoint" as parallel choices, lead with user goals: *"I want to use ChatGPT / Claude / Gemini"* → LLM, *"I want to analyze text, process images, transcribe audio"* → Universal AI.
- Move or duplicate the comparison content (`llms-vs-expert-models`) to immediately after the homepage hero, or embed a condensed version directly on the homepage.

---

### 1.2 Navigation Depth vs. Discoverability

**Issue:** The Expert Models section contains 18+ feature pages nested under `features/text/`, `features/ocr/`, `features/image/`, etc. This is appropriate for reference, but there is no overview page that lets a user scan *all available features in one place* with a quick description of each. A developer evaluating whether Eden AI covers their use case must click into multiple sub-pages.

**Recommendation:**
- Add a single "What can Expert Models do?" overview page that lists all feature categories (OCR, Image, Audio, Text, Translation) with a one-liner per feature and a link to its page.
- This page could double as a discovery entry point from the homepage.

---

### 1.3 "General" Section Has a Mixed Identity

**Issue:** The General section groups together very different types of content:
- Operational features (caching, sandbox, monitoring, BYOK)
- Account management (credits, custom API keys, users & org)
- Reference content (support)

This creates a catch-all bucket that doesn't communicate a clear mental model. When looking for "how do I manage my API keys?", it's not obvious whether to look in General or somewhere else.

**Recommendation:**
- Split General into two sections: **Platform Features** (caching, sandbox, monitoring, BYOK) and **Account & Billing** (credits, API keys, users/org, support).
- Or at minimum, add a landing page for the General section that provides orientation.

---

### 1.4 Duplicate "Listing Models" Pages

**Issue:** There are two separate `listing-models.mdx` pages — one under LLMs and one under Expert Models. The content is largely the same (same `/v3/info` endpoints, same response formats), but split with slight differences. A developer searching for "how to list models" will land on one or the other and may not realize the other exists.

**Recommendation:**
- Consolidate into a single "API Discovery" page under a top-level section or General.
- Link to it from both LLMs and Expert Models sections with a short note about any feature-specific nuances.

---

### 1.5 Duplicate "Fallback" Pages

**Issue:** Same problem as above — `llms/fallback.mdx` and `expert-models/fallback.mdx` both cover fallback patterns with very similar conceptual framing. The LLM fallback page also introduces Smart Routing, which has its own dedicated page (`smart-routing.mdx`), creating yet another overlap.

**Recommendation:**
- Either consolidate fallback into one page with tabs/sections for each endpoint type, or clearly differentiate the scope of each page so users know which one applies to them without reading both.

---

## 2. Onboarding & First-Time User Experience

### 2.1 Quickstart Is Good but Incomplete

**Strengths:** `first-llm-call.mdx` is well-structured. It has a clear goal, a working code example in three languages, and a logical progression from "get key" → "make call" → "read response." The OpenAI-compatible angle is a smart hook for developers already familiar with that SDK.

**Issues:**
- After completing the quickstart, there is no clear "what's next?" guidance. The page ends without a call to action pointing toward the next logical step (streaming? tools? smart routing?).
- `first-expert-model-call.mdx` (the Universal AI quickstart) does not have the same polished feel. The model string format (`feature/subfeature/provider/model`) is introduced inline without enough scaffolding. A developer unfamiliar with this pattern will be confused.

**Recommendation:**
- Add a "Next steps" section at the bottom of each quickstart page with 3 curated links.
- Add a brief explanation box in the Universal AI quickstart that unpacks the model string format visually before showing code.

---

### 2.2 Authentication Is Scattered

**Issue:** Authentication (`Authorization: Bearer <api_key>`) is explained in the overview, the quickstart, and multiple individual pages — but there is no single canonical "Authentication" page. Developers who search for auth setup may land on any of these entry points and get slightly different information depending on where they land.

**Recommendation:**
- Create a dedicated Authentication page (likely under General or a new "Getting Started" group) that covers: getting an API key, using it in headers, sandbox tokens vs. production tokens, and token management. Then link to it from all pages that reference auth.

---

### 2.3 Sandbox Tokens Have Two Pages

**Issue:** There is `sandbox.mdx` and `sandbox_tokens.mdx` — two pages covering overlapping content about sandbox/testing tokens. One appears to be a tutorial and the other a reference, but this isn't clearly signaled by their names or placement in the navigation.

**Recommendation:**
- Merge into one page with clear sections: what sandbox tokens are, how to create them, how to use them. The lifecycle management content from `sandbox.mdx` can live at the bottom as an advanced section.

---

## 3. Content Clarity & Writing Quality

### 3.1 Inconsistent Page-Level Structure

**Issue:** Pages across the docs don't follow a consistent template. Some pages start with an introductory paragraph, some with a code block, some with a callout. Some have `<CardGroup>` links at the bottom, some don't. This creates a reading experience that feels slightly unpredictable — users don't know what to expect when they click into a new page.

**Recommendation:**
- Define and apply a consistent page template:
  1. One-sentence "what this page covers"
  2. Prerequisites (if any)
  3. Core content with progressive complexity
  4. Related pages / next steps

---

### 3.2 Feature Pages Under Expert Models Are Thin

**Issue:** The feature pages (e.g., OCR, text moderation, TTS, face detection) tend to follow the same structural pattern, which is good. But many of them feel like stubs — they show the API call but don't explain output fields, don't discuss provider differences or quirks, and don't give "when to use this" context.

**Example:** `image/background-removal.mdx` shows the request but doesn't explain the response format (what does the output look like? a URL? base64?), error cases, or which providers perform best.

**Recommendation:**
- Add a minimum content standard for feature pages: request example, response example with field descriptions, provider notes, and one real-world use case.

---

### 3.3 "Plans & Prices" Page Needs More Clarity

**Issue:** `plans-prices.mdx` describes the 5.5% platform fee and two tiers, but it doesn't answer the most common pricing question a developer has before signing up: *"How much will this cost me to run X requests per day?"* There are no example calculations, no cost estimator, no link to a pricing page.

**Recommendation:**
- Add 2-3 worked pricing examples: "If you run 1,000 GPT-4o calls/day at the provider's list price, your Eden AI cost is X."
- Link to the dashboard pricing page if one exists.

---

### 3.4 "Smart Routing" and "Fallback" Are Conceptually Blurry

**Issue:** The smart routing page and the fallback page both address reliability and model selection, but the relationship between them is not clearly explained. Does `@edenai` include automatic fallback? Is `router_candidates` a fallback mechanism? A reader would need to read both pages carefully to understand the difference.

**Recommendation:**
- Add a short intro at the top of each page that explicitly positions it relative to the other: "Smart Routing automatically selects the best model. For manual fallback control, see Fallback."

---

## 4. Code Examples

### 4.1 Strengths

- Using `<CodeGroup>` with Python, JavaScript, and cURL tabs is the right call — it covers the most common developer environments.
- Code examples are functional and realistic (not toy examples).
- Examples build on each other within a page (e.g., basic → with parameters → with streaming).

### 4.2 Issues

**Language inconsistency:** Not all pages include all three languages. Some pages only have Python + cURL, some have TypeScript labeled as JavaScript. Developers working in TypeScript will notice the inconsistency.

**No runnable playground:** There is no "try it" button or embedded API playground. For a product whose main value proposition is easy integration, the ability to run a request directly from the docs (like Stripe's API explorer or OpenAI's Playground) would meaningfully reduce time-to-first-success.

**Error handling in examples:** Most code examples don't show error handling. Developers copy-paste these snippets and then wonder why their app crashes when a provider is down. At minimum, quickstart examples should demonstrate try-catch or response status checking.

**Recommendation:**
- Standardize: all pages must have Python, TypeScript, and cURL. Flag which are missing and prioritize filling gaps.
- Add a "copy to run" annotation or direct Colab/CodeSandbox link for quickstart examples.
- Add error handling to at least the quickstart code blocks.

---

## 5. Visual Hierarchy & Scannability

### 5.1 Long Pages Without Anchored Navigation

**Issue:** Several pages (notably `chat-completions.mdx`, `tools.mdx`, `listing-models.mdx`) are long and dense. While Mintlify provides auto-generated anchor links in the right sidebar, the page-level headers (`##`) don't always reflect the logical sections a developer would search for.

**Recommendation:**
- Audit long pages for heading structure. Every distinct "thing a user wants to do" on a page should have its own `##` heading so it appears in the sidebar TOC.

### 5.2 Callouts Are Used Inconsistently

**Issue:** `<Note>`, `<Warning>`, and `<Tip>` callouts appear on some pages but not others. Pages with important caveats (e.g., file expiration after 7 days in `file-upload.mdx`, rate limits, provider-specific quirks) sometimes bury this information in body text rather than surfacing it in a callout.

**Recommendation:**
- Establish a clear policy for callout usage:
  - `<Warning>`: anything that will cause a runtime error if missed
  - `<Note>`: important context that changes behavior
  - `<Tip>`: non-essential best practices
- Apply consistently across all pages.

---

## 6. Integration Pages

### 6.1 Strengths

The integrations section is strong. The pattern of "just change the base URL" is a killer feature for developer adoption, and the docs communicate this clearly. The LangChain, Claude Code, and Continue.dev pages are well-scoped and actionable.

### 6.2 Issues

**No integration comparison:** The integrations index (`index.mdx`) lists the categories but doesn't help a developer choose. If I use VS Code, should I use Continue.dev or is there a better option? If I use a Python framework, is LangChain the right fit?

**LibreChat and Open WebUI pages are very long:** These two pages contain full Docker deployment guides, advanced configuration, and production setup. This is genuinely useful content, but it might be better hosted as standalone guides or linked from the integration page rather than embedded in the main docs flow.

**Recommendation:**
- Add a quick "Which integration should I use?" decision guide at the top of the integrations index.
- Consider splitting deployment-heavy integration pages into a separate "Deployment Guides" section or an external docs link.

---

## 7. Missing Content

| Gap | Priority | Notes |
|-----|----------|-------|
| Dedicated Authentication page | High | Currently scattered across multiple pages |
| "All Expert Model Features" overview page | High | No single scannable list exists |
| Error codes & troubleshooting guide | High | Referenced in responses.mdx but no dedicated page |
| Rate limits & quotas | High | Not documented anywhere |
| Changelog / what's new in V3 | Medium | Helps users migrating from V2 |
| V2 → V3 migration guide | Medium | V2 still accessible, migration path unclear |
| Glossary of terms | Low | "provider", "feature", "subfeature", "preset" — not obvious to new users |
| Webhook security (signature verification) | Medium | webhooks.mdx doesn't cover payload verification |

---

## 8. Tone & Voice

The writing is clear and professional. It avoids marketing fluff, which is appropriate for developer docs. A few observations:

- Some pages shift between second-person ("you can use...") and imperative ("use the endpoint...") inconsistently. Pick one and stick with it.
- The phrase "Eden AI" is sometimes written without the space and sometimes capitalized differently across pages. Standardize.
- Feature pages under Expert Models tend to be drier than LLM pages. The LLM pages feel more like someone is guiding you; the feature pages feel more like auto-generated reference. Closing this gap would improve the overall feel.

---

## Priority Action List

| Priority | Action |
|----------|--------|
| 🔴 P0 | Create dedicated Authentication page and link from all entry points |
| 🔴 P0 | Add "Next Steps" section to both quickstart pages |
| 🔴 P0 | Add error handling to quickstart code examples |
| 🟠 P1 | Consolidate the two Sandbox pages into one |
| 🟠 P1 | Consolidate the two Listing Models pages |
| 🟠 P1 | Add a "What can Expert Models do?" overview page |
| 🟠 P1 | Clarify relationship between Smart Routing and Fallback |
| 🟡 P2 | Standardize page template (intro → prerequisites → content → next steps) |
| 🟡 P2 | Fill missing code language tabs (TypeScript in particular) |
| 🟡 P2 | Enrich thin feature pages with response field docs and provider notes |
| 🟡 P2 | Add rate limits & error codes documentation |
| 🟢 P3 | Add V2 → V3 migration guide |
| 🟢 P3 | Add "Which integration?" decision guide |
| 🟢 P3 | Add a Glossary page |

---

*This review was conducted as a first-pass UX audit from the perspective of a developer encountering the Eden AI V3 docs for the first time. Recommendations are meant to be actionable and prioritized by user impact.*
