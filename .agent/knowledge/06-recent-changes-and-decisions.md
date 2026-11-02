---
knowledge: 06-recent-changes-and-decisions
last_verified: 2026-11-01
source_files:
  - .git
  - winbrow/brain/skill_writer.py
  - winbrow/brain/agent_loop.py
  - winbrow/brain/batching.py
  - winbrow/brain/prompt.py
  - winbrow/execution.py
  - winbrow/permissions.py
  - winbrow/brain/skill_registry.py
  - winbrow/brain/model_gateway.py
  - winbrow/skill_scripts.py
  - winbrow/integrations.py
  - winbrow/browser_credentials.py
  - winbrow/everything.py
  - winbrow/shell.py
  - winbrow/subagents.py
  - winbrow/agent.py
  - server.py
  - templates/index.html
  - winbrow/tests/test_skill_writer.py
  - winbrow/tests/test_find_files_tool.py
  - tools/seed.json
  - winbrow/skills/find-files/SKILL.md
  - tools/skills.json
  - winbrow/browser_task.py
  - winbrow/router.py
---

# 06 — Recent Changes and Decisions

Verified 2026-10-25. This file records **why** the code looks the way it does and which surfaces are
most likely to drift. It is the first file to update after a refactor.

## 1. Git state at verification time

- HEAD: `b82cfb2` — `fix: file picker window` (2026-10-22 23:37:50 +0530).
- Previous: `348b213` — `fix: upload file issue, browser click issue`.
- Previous: `58c7e8a` — `fixed: browser tab issue, app opening mismatch, toggle play/pause issue`.

Uncommitted working tree:

```
 M tools/seed.json
 M tools/skills.json
 M winbrow/agent.py
 M winbrow/brain/agent_loop.py
 M winbrow/brain/skill_registry.py
 M winbrow/browser_task.py
 M winbrow/browser_tools.py
?? .agent/
?? test_browser_fixes.py
?? winbrow/brain/skill_writer.py
?? winbrow/tests/
```

The uncommitted work is the **post-session skill writer**:

- New `winbrow/brain/skill_writer.py` (721 lines): analysis prompt, JSON schema, specificity guards,
  atomic `SKILL.md` write, hot reload.
- `brain/agent_loop.py`: `_fire_skill_writer()` and `_maybe_save_skill()`; fired on completed
  actions/done.
- `brain/skill_registry.py`: live metadata rebuild / hot-reload support.
- `winbrow/tests/test_skill_writer.py` (221 lines): guard/write tests.
- `tools/skills.json`: replay records touched by the same work.

Do not assume this work is committed or deployed. If you change the writer, update
`03-skill-system.md` and this file.

## 1a. Browser task regression fixes (2026-10-25)

Trace: `"open chrome and go to x.com and search for onepiece"` opened Notepad,
used Brave after launching Chrome, and then every read of the x.com search page
returned `Title: (untitled)` / `PAGE TEXT: (empty)`.

Causes and fixes:

1. **Poisoned page cache** — `browser_navigate` snapshotted x.com while the SPA
   was still committing (URL set, title/body empty) and `get_page_state` cached
   it by URL. Later reads replayed the blank snapshot forever.
   Fix: `_fetch_page_state` polls up to 3 s for a non-blank snapshot;
   `_state_is_blank` snapshots are flagged `_blank` and never cached/served.
2. **Repeat guard blocked re-reads** — `browser_wait({seconds:3})` was treated as
   an already-completed step and the planner was handed the *old* Home/X result.
   Fix: `REPEATABLE_SKILLS` (reads/waits/time) bypass the completed-step guard.
3. **Notepad default** — `app_focus_or_launch` defaulted `app_name` to
   `"notepad"` in both `agent.py` and `tools/seed.json`, so an omitted argument
   opened Notepad. Fix: empty default; missing name fails with a clear message.
4. **`open_common_app` unknown: chrome** — browsers were not in the enum/map.
   Fix: enum + script entries, and `agent.run_skill` routes browser names to
   `_open_requested_browser`.
5. **Chrome launched, Brave used** — the browser layer attached to whichever
   Chromium had CDP. Fix: `set_preferred_browser()` remembers the requested
   browser (`_browser_order` puts it first, `_devtools_ws_endpoint` refuses to
   attach to a different browser when the requested one is not running), and
   browser app-open steps call `launch_with_cdp(guide=False)`. `reset_session()`
   clears the preference; navigate output now reports the browser used.

Regression tests: `test_browser_fixes.py` (13 tests).
Known pre-existing unrelated failures at HEAD: router tests
`test_multistep_browser_routes_to_brain`, `test_download_with_url_routes_to_tool`,
`TestEditorSequence` (save variants).

## 2. Recency map

| Surface | Last meaningful change | Risk |
|---|---|---|
| Batch planner/executor + contracts | 2026-11-01 (section 20) | High; new execution path with test coverage |
| Permission continuation / action keys | 2026-11-01 (section 20) | High; old `v2:` grants intentionally invalidated |
| Browser batch guard (`batch_state`) | 2026-11-01 (section 20) | Medium; mocked CDP tests only |
| Browser page-state cache / readiness | 2026-10-25 (this session) | Medium; see "Browser task regression fixes" below |
| Browser app preference (`set_preferred_browser`) | 2026-10-25 (this session) | Medium; Chrome/Edge/Brave routing |
| Browser upload/tab/click | 2026-10-22 (`b82cfb2`, `348b213`) | **Highest**; actively churning |
| Router / ultrafast | 2026-10-22 (`58c7e8a`) | High; routing regressions common |
| `windows.py` / `apps.py` | 2026-10-22 | High; app launch fixes |
| Skill writer | Uncommitted, 2026-10-25 | High; new and not fully exercised |
| `browser_tools.py` / `browser_task.py` | 2026-10-22 | High; see `05` B-01…B-20 |
| `generator.py` | 2026-10-17 | Medium |
| `llm.py` / `model_manager.py` | 2026-10-19 | Medium; known broken `_request` |
| `router.py` / `resolvers.py` / `small_llm.py` | 2026-10-04 (resolvers/small_llm) | Stale; orphaned option architecture |
| `accessibility.py` | 2026-10-05 | Dead code |
| `vision.py` | Older, unreferenced | Dead/broken |

## 3. Documented decisions (13)

D1. **Raw CDP over a browser framework.** Avoid Playwright/pydoll/Selenium; keep the user's real
browser and logins. Accept hand-rolled transport complexity.

D2. **Two browser transports.** HTTP `/json/*` for a separate/legacy profile; one persistent
consent-mode WebSocket for the user's normal browser. Never open a browser-level socket per page in
consent mode.

D3. **Agent tab isolation.** The agent gets its own tab per task; `_pick_tab()` returns `None`
rather than touching a user tab if that tab disappeared. `end_task()` leaves the tab open for
inspection.

D4. **URL-keyed page cache.** Cheap repeated reads; correctness depends on callers forcing a refresh
after mutations. No TTL.

D5. **Precedence ladder, not a single router.** Replay → MCP shortcuts → browser fast path → router →
brain → generator. Each tier can return early; failures fall through.

D6. **Browser tasks always use the brain loop when available.** Replay is deliberately skipped for
browser intents because live web state invalidates recorded assumptions.

D7. **One permission gate at `run_skill()`.** No tool may bypass it. T3 is never remembered; T2 can
be remembered by exact action key.

D8. **Progressive-disclosure markdown skills.** Metadata only in the system prompt; full body
injected after selection. Skills are instructions, not executable plugins.

D9. **Two independent skill memories.** Brain markdown skills (writer) and procedural replay JSON
(captured plans) are not merged. Browser workflows are excluded from replay.

D10. **Post-session skill writer is asynchronous and conservative.** Minimum 3 successful steps,
specificity guards, no overwrite, hot reload, all exceptions swallowed.

D11. **Cloud-first brain with optional local fallback.** Nebius Token Factory
(`NEBIUS_API_KEY`, OpenAI-compatible `https://api.tokenfactory.nebius.com/v1`)
is first in auto; OpenRouter/DeepSeek remains a fallback. llama.cpp/Qwen only
when explicitly enabled. Reasoning budgets are capped because hidden reasoning
consumes `max_tokens`; Nebius maps the shared policy to `reasoning_effort`.

D12. **Windows-native execution.** PowerShell + COM + UIA + ctypes, with app adapters rather than a
generic GUI framework. `policy.py` is a safety net, not a sandbox.

D13. **Backend-owned batch contracts, sequential by default.** The planner may emit a bounded
`steps[]`, but a reviewed `BatchPolicy` (not a model flag, name prefix, permission tier or
external description) decides ordered/parallel eligibility and barriers. Mutations stay
ordered; only reviewed independent reads may run concurrently via the separate
`WINBROW_PARALLEL_READS` flag. Every member still goes through `run_skill()`. Exact approval
continuation resumes the unexecuted suffix under a shared execution lease; it never restarts
the goal or re-spends an approval. Unknown capabilities fall back to singletons/observation
barriers until reviewed. See `BRAIN_BATCHING_PLAN.md` and section 20.

## 4. What changed most recently and why it matters

### 4.1 Skill writer (uncommitted)

The writer was added to turn repeated successful workflows into reusable brain skills. It is
**not** the same as replay memory:

- Writer output: `winbrow/skills/<name>/SKILL.md`, chosen by the planner later.
- Replay output: `tools/skills.json`, executed without the planner.

Consequences:

- A generated skill can change planner behavior immediately (hot reload).
- A bad generated skill is persistent; the writer refuses to overwrite it.
- The writer costs one model call per eligible task; disable with `WINBROW_SKILL_WRITER=0`.

### 4.2 Browser upload/click fixes

Recent commits targeted the Google Drive upload flow: intercept the native chooser during the click,
then set the file input via CDP. The load-bearing details are the 0.2 s connection hold
(`browser_task.py:1338-1340`) and the private `_tabs`/`_pick_tab`/`_page_conn` path in
`browser_upload_file`. Refactors that "clean up" either one tend to break upload.

### 4.3 Tab lifecycle fixes

Recent commits also fixed tab hijacking: the agent tab is exclusive, and a missing agent tab is not
silently replaced by a user tab. Keep that behavior even when reads return empty; surface the
failure instead.

### 4.4 App launch fixes

`windows.focus_or_launch_app()` and `apps.resolve_app()` were touched for app-opening mismatches.
The remaining sub-threshold launch bug (D-02) is a known risk in that area.

## 5. Stale-risk checklist

Mark a knowledge file stale when any of these change:

| Knowledge file | Watch these sources |
|---|---|
| `01-system-architecture.md` | `server.py`, `agent.py` init, `requirements.txt`, `.env.example` |
| `02-browser-automation.md` | `browser_task.py`, `browser_tools.py`, `ultrafast.py`, browser `SKILL.md` |
| `03-skill-system.md` | `brain/skill_registry.py`, `brain/skill_writer.py`, `memory/skills.py`, `skills/` |
| `04-request-data-flow.md` | `agent.py` `execute()`/`run_skill()`, `router.py`, `brain/agent_loop.py`, `permissions.py` |
| `05-known-issues.md` | Any file cited in a row; remove fixed rows |
| `06-recent-changes-and-decisions.md` | Git history, uncommitted files, architectural decisions |

The `Stop` hook compares each file's `last_verified` date with the mtimes of its `source_files`.
A source edited after `last_verified` marks the knowledge file stale.

## 6. Refresh procedure

1. Read `.agent/memory/stale.md`; pick the highest-risk file.
2. Read only the changed source files (use `git diff -- <paths>` first).
3. Update the knowledge file's facts and line numbers.
4. Bump `last_verified` to today.
5. If the change affects a decision, add a new `D<n>` entry here; do not silently rewrite history.
6. Remove the file from `stale.md` (or let the next hook run rebuild the list).
7. Add a session-log entry describing what changed and what was verified.

## 7. Verification honesty

The knowledge base was built by reading source, not by running the product. No live CDP session,
UIA tree, COM automation, voice loop, or end-to-end task was executed for these documents. Treat
runtime claims as "what the code says", not "what was observed". When you run something, record the
exact command and result in the session log.

## 8. Converted skill library (2026-10-25)

Added 43 playbooks from the six requested awesome-claude-skills sections:

- `winbrow/skills/library/<section>/<name>/SKILL.md` plus 21 helpers,
  references, and templates.
- `kind: playbook` in the frontmatter; unique `playbook_*` keys; grouped
  metadata; budget raised from 4,000 to 12,000 chars.
- `agent_loop._run_step` acknowledges a playbook without a tool lookup and
  injects the body as SKILL DETAIL on the next turn.
- `winbrow/skill_scripts.py` adds `run_skill_script` (T2, allowlisted).
- `winbrow/integrations.py` adds provider storage, probes, and the T0
  `integration_status` tool.
- `server.py` + `templates/index.html` add the Integrations panel and endpoints.

Verified in this session: 24 focused tests (`test_playbooks`,
`test_converted_skills`, `test_integrations`, `test_integrations_api`,
`test_skill_writer`) passed; 69 skill definitions load; metadata is ~9,626 chars.
The document/media helpers were smoke-tested for PDF, PPTX, XLSX, EPUB, CSV,
PNG, and GIF. DOCX and the credential-gated integrations were not exercised
end-to-end because their optional packages/accounts are not installed here.

## 9. Scoped subagents (2026-10-26)

Added `winbrow/subagents.py` + `winbrow/skills/delegate-task/SKILL.md`:

- `delegate_task` is a real registry tool (`impl="subagent"`, T1). The main
  planner sees its SKILL.md body; child actions go through the parent
  `run_skill` gate. Delegation is automatic by default; `WINBROW_SUBAGENTS=0`
  disables it and `WINBROW_SUBAGENTS_EXPLICIT=1` requires an explicit request.
  Explicit and independent-research candidates bypass the browser fast path so
  they reach the brain.
- Six profiles (`researcher`, `file-analyst`, `writer`, `code-reviewer`,
  `verifier`, `general`) each get a filtered skill registry + scoped tool
  registry, a short system prompt, no subagents, no skill writer, and a step cap.
- `AgentBrain` gained `allowed_skills`, `system_prompt`, and
  `enable_skill_writer`; `_run_step` rejects disallowed keys before every meta,
  playbook, and tool branch.
- `file-analyst` is the only parallel-safe profile. Browser/write profiles are
  forced sequential; max 4 tasks per call, max 3 concurrent.
- Runs persist to `data/subagents.json` (last 50) and appear in the Subagents
  UI panel + `GET /api/subagents`.
- Tests: `winbrow/tests/test_subagents.py` covers profile filtering, scoped
  registry, blocked children, parallel fallback, real child-brain execution, and
  the API/UI surface. No live model call was made.

## 10. Web access hierarchy (2026-10-26)

The browser was opening for research because the old `web_search` seed tool ran
`laya_ultrafast_browser`, the router preferred `laya_ultrafast_browser` for
searches, and the agent browser fast path treated `search` as a browser
keyword.

Fixed:

- `winbrow/web_tools.py` adds native `web_search` (DuckDuckGo HTML API) and
  `web_fetch` (HTTP GET + BeautifulSoup/pdfminer), both T0 and browser-free. The
  old seed `web_search` was removed.
- `SYSTEM_PROMPT_STATIC` ends with the verbatim WEB ACCESS HIERARCHY + WORKED
  EXAMPLES, so it sits immediately before the AVAILABLE SKILLS system block.
- The router sends search/price/comparison/documentation to
  `web_search`/`web_fetch`; only booking/checkout/form/login/media/explicit-open
  routes to the browser.
- `_is_browser_intent` no longer matches bare research/search/site words; site
  names require an explicit open/go/visit verb.
- `web_search` and `web_fetch` have SKILL.md descriptions ending in
  "No browser opened"; `browser_navigate` is interaction-only.
- `.claude/knowledge/session-patterns.md` records the web-access pattern table.

Verification: `test_web_tools.py` (9 tests) covers DDG parsing, browser-free
descriptions, prompt ordering, browser-intent negatives, router
search-vs-booking, and session-patterns. No live network test was run.

## 11. Brain-first routing (2026-10-26)

`WinBrowAgent.execute()` now attempts the brain before replay, MCP shortcuts,
the browser fast path, or the router whenever a provider is available.

- `_execute_brain_goal()` uses `handle_browser_task()` for browser-intent
  utterances and `AgentBrain.handle()` for everything else.
- Route tier is `brain_first`; a planner exception is `brain_first_error`. A
  normal brain result (including `needs_input`) is returned immediately.
- Replay is skipped when brain-first is active. MCP shortcuts, browser fast
  path, and router remain fallbacks only when the provider is unavailable or
  fails (`GatewayUnavailable`/`GatewayError`).
- `WINBROW_BRAIN_FIRST` defaults to `1`; set `0` only to debug legacy routing.
- Tests: `test_brain_first.py` proves an MCP shortcut is not used when the brain
  is available and that a planner exception does not fall through to MCP.

## 12. Web search transport: curl_cffi TLS impersonation (2026-10-26)

DuckDuckGo started serving plain `requests` clients an HTTP 202 "Select all
squares containing a duck" challenge, so `web_search` returned zero results on
both `html.duckduckgo.com` and `lite.duckduckgo.com`. The CSS selectors and the
existing parsers were still correct.

Fixed:

- `winbrow/web_tools.py` keeps the DDG HTML/Lite parsers and replaces the
  `requests` transport with `curl_cffi` (browser TLS/HTTP2 impersonation).
  Measured before/after: `requests` → 202 challenge; `curl_cffi` chrome124 →
  200 with 10 parsed results in ~0.8s.
- Challenges are detected by status (202/403/429) and body markers, then
  retried up to 3 times alternating `chrome124` → `safari17_0` with 0.6s/1.2s
  backoff. A challenged identity happens intermittently under rapid queries.
- One budget (`WINBROW_SEARCH_TIMEOUT`, default 20s) is shared by both DDG
  endpoints; each gets half. Fingerprint order is `WINBROW_TLS_IMPERSONATE`.
- `web_fetch` uses the same transport (falls back to `requests` only when
  `curl_cffi` is missing) because impersonation also clears site 403s.
- `web_search` now also returns `provider` and `transport`
  (e.g. `curl_cffi:chrome124`). The failure text, including "Do not open the
  browser for research", is unchanged.
- `curl_cffi` is in `requirements.txt` and in `integrations.DEPENDENCIES` so the
  Integrations UI install command includes it.

Non-goals: no SearXNG/Docker (not installed on the target machine), no Brave or
other keyed API, no Google scraping (Google serves a JS-only interstitial even
to curl_cffi), no extra providers or ports.

Verification: `test_web_tools.py` adds challenge detection, retry, lite-endpoint
fallback, missing-dependency, and failure-message tests; the live DuckDuckGo
test is opt-in via `WINBROW_LIVE_TESTS=1`. A live query returned 10 results.

## 13. Research loop fix: web history budget + URL repeat guard (2026-10-26)

A 12-step Kimi K3.1 Pro research run re-ran `web_search` four times and fetched
the same two URLs repeatedly. The cause was history compression, not the
planner: `format_history` capped every non-document step at
`RECENT_OUTPUT_LIMIT` (400 chars). `web_search` therefore showed ~2 of 5
results, and `web_fetch` showed only the first 400 chars of a 12k-char page.
Refetching with a larger `max_chars` produced the same 400-char prefix, so the
model could never see more and kept trying.

Fixed:

- `winbrow/utils/history.py` gives web output its own newest-first budgets:
  `web_search` 3k per step / 6k total; `web_fetch` 20k per step / 30k total.
  Documents keep 30k/60k; every other tool stays terse at 400 chars.
- `_step_signature` identifies `web_fetch` by URL only, so a different
  `max_chars` no longer bypasses the completed-step guard.
  `_is_fetch_escalation` still allows ONE larger re-fetch of a truncated page
  (hard cap: two successful fetches per URL), then guards again.
- Prompt rule 22 and the web-search/web-fetch SKILL.md step patterns state the
  budget: one search, 2-3 fetches, never the same URL twice, answer once two
  sources agree.
- Tests: `winbrow/tests/test_research_loop.py` covers web text surviving
  compression, newest-first budgets, terse non-web output, URL-only signatures,
  and the one-time escalation rule.

## 14. Web fetch: main-content extraction + focus selection (2026-10-26)

`web_fetch` returned raw BeautifulSoup text (nav, cookie banners, footers) up to
12k chars. The planner only needs the part that answers the question.

Added:

- `trafilatura` (Apache-2.0, ~1 MB, no model) extracts main content as Markdown
  with headings, tables, and code preserved. Fallback: the old
  `_html_to_text()` when extraction is empty/short, `trafilatura` is missing, or
  the page is not HTML. Measured: MDN 153k HTML → 2.6k text; Wikipedia 383k →
  16.7k; kimi.ai blog 20.9k → 5.5k after focus selection.
- `web_fetch(url, max_chars, focus="")`: with `focus`, a dependency-free BM25
  ranks Markdown sections and keeps the intro plus the best sections up to
  `WINBROW_FETCH_FOCUS_CHARS` (default 6000). A 15% quota preserves numeric /
  price / date lines from otherwise-dropped sections under
  "Additional relevant facts".
- Login/JavaScript walls (`You signed in with another tab…`, Cloudflare
  interstitials) now return `success=False` with a `browser_navigate` hint
  instead of page chrome.
- Output header adds `EXTRACTOR`, `RAW-CHARS`, and (when focused) `FOCUS` and
  `SELECTED: k/n sections`; the result dict adds matching fields.
- Prompt rule 22, the Layer 3 block, and the web-fetch/web-search SKILL.md files
  instruct the planner to pass `focus` with the facts it needs.

Deliberately not added: local LLM summarization (measured 7.4 prompt tok/s for
the bundled Qwen 0.5B on this CPU — a 12k page takes minutes), LLMLingua-2
(100M-600M model, deletes exact numbers), Dripper/ReaderLM (model inference),
and Docker/SearXNG.

Tests: `winbrow/tests/test_web_extract.py` covers extraction, fallback, BM25,
section selection, fact retention, focus plumbing, and wall detection.

## 15. Native input: UIA CLSID init, fail-safe corners, word-level OCR (2026-10-27)

A WhatsApp run failed on `computer_click_text`: UIA never initialized
(CO_E_CLASSSTRING), OCR line boxes were all `[0,0,0,0]`, and PyAutoGUI aborted
with its fail-safe.

Fixed:

- `winbrow/computer/uia.py`: create IUIAutomation by CLSID
  (`comtypes.client.GetModule("UIAutomationCore.dll")` + `CoCreateInstance`)
  instead of the unregistered `"UIAutomationClient.CUIAutomation"` ProgID.
  COM-init the thread before creating the engine and keep one engine per worker
  thread (computer tools run via `asyncio.to_thread`). `accessibility.py` uses
  the same CLSID path.
- `winbrow/computer/screen.py`: Windows OCR's `OcrLine.BoundingRect` is null in
  PowerShell 5.1, so every line rect was `0,0,0,0` — a click at the "line
  center" became `(0,0)` and tripped the corner fail-safe. Line rects are now
  derived from word rects; the script emits explicit x/y/w/h for lines and
  words, and `_rect4()` accepts dict, list, or `"x y w h"` strings.
- `winbrow/computer/ladder.py`: match the target phrase against OCR *words* and
  click the union of their rects, so merged OCR lines (WhatsApp sidebar, chat
  rows) no longer land between controls. Line matching remains as fallback.
- `winbrow/computer/driver.py`: FAILSAFE stays enabled, but a cursor resting
  exactly on a corner is nudged 2 px inward via `SetCursorPos` before the
  action. Clicks outside the desktop or exactly on a corner are refused, and
  fail-safe failures report the target/cursor/screen. Coordinates are scaled to
  PyAutoGUI's space if DPI awareness made the sizes differ.
- `winbrow/computer/tools.py`: `computer_key` accepts `combo`, `key`, `keys`,
  or `hotkey`; click failures include the grounding source and coordinates.
- Prompt rule 23: focus the named app first, prefer the keyboard for search
  boxes and result lists, and never retry a fail-safe/refused click.
- Tests: `winbrow/tests/test_computer_input.py` covers corner validation, the
  cursor nudge, key aliases, CLSID engine init, word-level phrase grounding,
  and rect normalization.

## 16. Anthropic skills integrated (2026-10-27)

Added/upgraded five skills from `anthropics/skills`, adapted to WinBrow's
playbook format and Python toolchain (no Node, LibreOffice, pandoc, or Poppler
dependency):

- `docx` (document-processing): upgraded workflow (TOC, page numbers, headers/
  footers, comments, images, run merging, inspection) and extended
  `docx_tool.py` with `comment`, `toc`, `page_numbers`, `header_footer`,
  `image`, `merge_runs`, and `inspect`. Uses `python-docx 1.2` comments.
- `pdf` (document-processing): added `metadata`, `tables` (pdfplumber),
  `fields`, `fill_form` (pypdf, optional flatten), and `images`; upgraded the
  playbook for forms/tables/verification and vendored upstream `forms.md` and
  `reference.md` under `references/`.
- `pptx` (document-processing): upgraded design guidance (palette, motif, one
  idea per slide) and added `add_table`, `add_image`, `set_notes`,
  `delete_slide`; `read` now includes tables and speaker notes.
- `algorithmic-art` (creative-media): new two-phase skill (philosophy →
  p5.js), a custom responsive viewer, `scaffold_art.py`, and the upstream
  generator template as reference.
- `skill-creator` (productivity-organization): new authoring playbook plus
  `scaffold_skill.py` and `validate_skill.py` for WinBrow frontmatter, script
  contract, trigger descriptions, and category rules.

Registry: 54 playbooks + 27 tool skills. `validate_skill.py --spec-json
'{"all": true}'` reports 0 errors across 81 skills. Tests:
`winbrow/tests/test_anthropic_skills.py` covers registry wiring, validation,
and live helper calls for docx/pdf/pptx/art/skill scaffolding.

## 17. HTML PPT Studio integrated (2026-10-27)

Added `html-ppt` (document-processing), the complete
[lewislulu/html-ppt-skill](https://github.com/lewislulu/html-ppt-skill) design
system: 36 themes, 36 layout pages, 15 full-deck templates, 27 CSS animations,
20 canvas FX, keyboard runtime, presenter mode with notes, and print/PDF rules.
Vendored under `winbrow/skills/library/document-processing/html-ppt/` (MIT).

Windows-native helpers replace the upstream shell scripts:

- `scripts/new_deck.py` copies a template, copies `assets/` into the deck so it
  is portable across drives, rewrites every asset reference, and verifies all
  local HTML/CSS references before reporting success.
- `scripts/render_deck.py` exports PDF (default 16:9) or per-slide PNG through
  installed Chrome/Edge. `winbrow/html_to_pdf.py` discovers the browser, injects
  `@page` size, and renders with `--print-to-pdf`.
- `pdf_tool.py` adds `operation="from_html"` for the same export path, and the
  PDF playbook documents it.
- The `pptx` playbook now routes designed/animated/presenter decks to
  `html-ppt` and keeps `python-pptx` for genuinely editable `.pptx` work.

Verified live: pitch-deck template → 10-page PDF at 13.33×7.5 in; starter deck
→ 6-page PDF; page renders checked visually. Tests:
`winbrow/tests/test_html_ppt_skill.py` covers registry wiring, asset copying,
reference verification, PDF page count/size, and the PDF skill's `from_html`.

## 19. Measured PDF/PPTX layout + image search + visual QA (2026-10-27)

Replaced the fixed-coordinate PDF writer and the basic pptx builder with
measured layout engines under `winbrow/layout/`:

- `measure.py` — font metrics, wrapping (including long URLs/words), font-size
  fitting, and proportional image fitting.
- `pdf.py` — `PdfReport` paginates from actual page geometry. Paragraphs, code,
  and quotes split across pages instead of leaving a stranded heading/blank
  block; table rows split with repeated headers; images are proportional,
  captioned, credited, and bordered; headers/footers/page numbers reserve their
  own space. Themes: corporate, academic, minimal, editorial. Page sizes A4,
  Letter, Legal; portrait/landscape.
- `pptx.py` — `PptxBuilder` with 16:9/4:3 sizes, five themes, auto-fit bullets
  that split into continuation slides, measured tables with centered layout,
  proportional image/gallery placement, native editable charts, diagrams,
  quotes, sections, notes, footers, and slide numbers.
- `validate.py` + `preview.py` — PDF validation renders every page with
  pypdfium2, checks text outside page/margins, page size, blank pages, and
  horizontal whitespace. PPTX validation checks shape bounds, text fit, image
  aspect ratio, overlap, and renders every slide with a PIL preview because
  PowerPoint/LibreOffice is absent (disclosed in the result); charts are
  simplified in that preview.
- `winbrow/image_search.py` — Wikimedia Commons search with public-domain/CC
  filtering, HTML-cleaned credits, download + PIL validation, proportional
  resizing, no placeholders. PDF `images`/`image_query` and PPTX slide `images`
  accept `query`; `find_image` is available in both skills. Openverse was
  attempted but times out on this network, so Commons is the provider.

Skill docs (`pdf`, `pptx`) now include the measured spec, themes, image rules,
mandatory validation workflow, and acceptance criteria.

Samples generated and inspected:
`data/samples/document-generation/sample-report.pdf`,
`sample-deck.pptx`, plus `sample-report_validation/` and
`sample-deck_slides/`. The deck includes a Wikimedia image with credit; the
report has a table, wrapped long URL, Unicode, image, caption, and credit.

Tests: `test_pdf_layout.py`, `test_pptx_layout.py`, and
`test_image_search.py` cover dense pages, 70-row tables, landscape Letter,
long URLs, images, 16:9/4:3, continuation slides, native charts, geometry
validation, and local/live image search.

## 20. General-purpose guarded batching (2026-11-01)

Implemented the Phases 0–2 first slice from `BRAIN_BATCHING_PLAN.md`. The planner can
now emit one bounded heterogeneous `steps[]` group; the backend decides eligibility and
the executor verifies or stops between members.

- `winbrow/brain/batching.py` adds immutable, reviewed `BatchPolicy` records keyed by
  exact tool name plus dispatcher impl, a live `WINBROW_MAX_ACTIONS_PER_TURN` cap
  (default 5, clamp 1–10), and all-or-nothing `validate_steps()` preflight. Names,
  categories, tiers, learned/MCP descriptions and model `parallel` flags grant no
  eligibility.
- `winbrow/brain/prompt.py` makes `steps[]` first-class, bounds it in the schema,
  states the mixed known-input/read-after-write rules, and replaces the contradictory
  one-action/read-only prompt text. Every ordered tool's contract/full guidance is in
  the BATCH TOOL CONTRACTS system block, not first-member-only detail.
- `winbrow/brain/agent_loop.py` executes validated members sequentially through
  `run_skill()`, keeps per-member budget/history/events, records `BrainResult.batches`
  with planned/attempted/unexecuted/stop_reason, stops at policy/verification barriers,
  and saves an exact continuation cursor on permission-required. `resume_pending()`
  revalidates and runs only the unexecuted suffix.
- `winbrow/execution.py` adds a re-entrant ContextVar lease that serialises top-level
  goals while letting awaited children/subagents inherit ownership. `execute()`,
  `confirm_pending()` and direct `/api/browser` actions hold it; a pending
  approval releases it while waiting.
- `winbrow/browser_task.py` adds `batch_state()`: remembered agent tab + per-document
  token + selector signatures without mutable values. `WinBrowAgent._guard_batch()`
  revalidates document identity and one connected/visible/enabled target before the
  batch and after each successful member. Desktop has no reviewed window guard yet, so
  desktop batches replan as single actions.
- `winbrow/permissions.py` adds request scoping, full case-sensitive `v2:` action keys,
  atomic consume-before-dispatch, exact ID/session/args matching, TTL pruning on lookup,
  and one-shot T3. `POST /api/confirm`, WebSocket confirm and chat yes/no all use the
  same continuation path.
- Browser checkboxes, desired-state primitives, reviewed desktop window guards, result
  bindings, MCP/API contracts and live performance measurement remain Phase 3+ barriers,
  not hidden batch eligibility.

Verification: `python -m pytest winbrow/tests -q` → 598 passed, 2 skipped;
`test_brain_m0.py` → 50 passed; focused batch/policy/guard/permission tests → 309
passed. No live model, CDP or UIA run. Unrelated root suites still have
environment-dependent failures at HEAD when `.env` supplies a live provider.

## 21. Consent-based browser password import (2026-11-01)

`winbrow/browser_credentials.py` adds a local vault for logins the user exports
from a Chromium browser’s own password manager. It deliberately does **not** read
`Login Data`, decrypt a browser profile, or accept a browser database path.

- `preview_browser_csv()` accepts only the user-selected CSV, validates
  `http(s)` origins, deduplicates by origin + username, and returns metadata
  (`origin`, `username`, `name`, `source`) without passwords. Pending plaintext
  lives only in process memory for 10 minutes.
- `commit_browser_import()` stores only the explicitly selected row IDs. Each
  password is encrypted with Windows DPAPI before `data/browser_credentials.json`
  is written; the file is gitignored and gets a best-effort private ACL.
- `GET /api/browser-credentials` and the import responses never serialize a
  password. Delete/clear endpoints remove vault entries. The UI is the
  **Passwords** modal in `templates/index.html`; the file picker is the only
  browser-password input path.
- `get_credential_for_origin()` is an internal broker helper for a future
  login/fill action. It is intentionally not exposed through REST or a model
  tool; no agent-facing credential-returning tool exists.
- Tests: `winbrow/tests/test_browser_credentials.py` covers metadata-only
  previews, DPAPI-at-rest, selected-row commits, re-import updates, invalid/
  unsupported URLs, API masking, and the UI consent markers.

This is **not** a cross-browser harvester. The user must export from the
browser UI and choose the CSV; there is no silent profile read.

## 22. PDF export performance guard (2026-11-02)

Recent slow PDF runs were dominated by orchestration, not the PDF engine:

- `run_command` was used for ad-hoc headless Edge/Chrome `--print-to-pdf`.
  The first attempt failed after 33.5s; the retry needed another 26.3s. The
  existing helpers (`html-ppt/render_deck.py`, `pdf/pdf_tool.py` `from_html`)
  already use `--headless=new`, a temporary profile, `file://` URIs, repair,
  timing, and validation.
- `run_command` now rejects `--print-to-pdf` with an actionable message naming
  both helper calls. The static planner prompt also forbids ad-hoc headless PDF
  export and points at the helpers.
- Measured on this machine: a 5-page PDF with 5 images plus validation took
  **6.0s** through `pdf_tool.py create`; a five-slide HTML deck took **2.8s**
  to render and **1.6s** to validate. The PDF writer is not the bottleneck.
- Remaining slow paths are serial image downloads and one LLM planning turn per
  step; these are not changed by this guard.

Tests: `test_shell_caps.py` and `test_prompt_order.py` cover the guard and
prompt routing; the PDF/deck suites pass.

## 23. Fast indexed file search (2026-11-02)

`find_files` uses the Everything index as its only search backend:

1. **Everything CLI** (`es.exe`): case-insensitive filename search through the
   portable WinBrow instance (or a standard Everything install). It returns
   folders first (`/ad`), then files (`/a-d`), and marks folders as
   `[folder] path`. The tool starts the portable instance itself if it is not
   running.
2. **No Windows Search and no scoped folder fallback.** The old
   Desktop/Documents/Downloads/Pictures `Get-ChildItem` walk and the
   `SYSTEMINDEX` query were both removed. If Everything is missing or still
   building its first index, the tool reports that instead of returning partial
   user-folder results.
3. **No `-i` flag.** In ES 1.1.0.38 `-i` means *match case*; passing it made
   `kaithi` miss `KAITHI_2019_...mp4`. Case-insensitive is the default.
4. **Folders are included.** The old `Test-Path -PathType Leaf` filter dropped
   directory hits, so "find the pcc folder" missed `D:\Codee\pcc` and the
   planner fell back to `run_command`/`list_directory`.
5. **UTF-8 JSON export.** ES stdout is decoded with the console code page inside
   the persistent PowerShell host; paths with non-ASCII characters (the NBSP in
   `KAITHI_2019_Tamil Proper...`) became `\ufffd` and failed `Test-Path`. The
   tool now runs `-export-json <tmp> -utf8-bom`, reads the file with UTF-8, and
   parses it with `ConvertFrom-Json`.

The persistent PowerShell host does not honor a top-level `return` as “stop
the rest of this input”, so each later backend is guarded with
`if ($results.Count -eq 0)` rather than early returns; the final result is one
mutually exclusive `if/elseif/else`. The search term uses a single-quoted
PowerShell string so `$()` is treated literally. The final output names the
source that produced the hit. The skill and README describe the indexed search
order and the unindexed-drive limitation.

`app_search` remains the winget package search. It is not a local installed-app
finder; `app_focus_or_launch` resolves from the cached local app catalog.

## 24. Portable Everything auto-install (2026-11-02)

`winbrow/everything.py` makes the `find_files` Everything fallback available
without a manual install:

- Checks `%LOCALAPPDATA%\WinBrow\Everything` for `es.exe` + `Everything.exe`.
- If missing, downloads the official voidtools x64 archives pinned to
  Everything 1.5.0.1424b and ES 1.1.0.38, verifies the published/observed
  SHA-256 digests and both Authenticode signatures (`CN=voidtools PTY LTD`),
  and extracts only `Everything.exe`, `Everything.lng`, and `es.exe`.
- Starts a **private** Everything instance named `WinBrow` with `-startup` and
  `-config` in the app folder. First start uses `-no-auto-index -folders`
  for fixed drives (folder indexing works as a standard user; no service or
  admin). Later starts reuse the saved config; `folders.txt` changes trigger a
  folder-list update.
- `server.py` runs this in a background task after PowerShell warm-up, so boot
  is not blocked. Under pytest the side effect is skipped.
- `find_files` prefers the app-local `es.exe` with `-instance WinBrow` and
  `-timeout 5000`, then standard Everything installations, then the scoped
  folder fallback.
- Disable with `WINBROW_EVERYTHING_AUTOINSTALL=0`; override paths with
  `WINBROW_EVERYTHING_DIR` / `WINBROW_EVERYTHING_FOLDERS`.

Live smoke: a temporary install found a unique file through the app-local ES
instance after Windows Search missed it. The production install also completed
in `%LOCALAPPDATA%\WinBrow\Everything` and `find_files` found a `D:\` repo file
through Everything after Windows Search missed it. The initial full-drive folder
index can take minutes; ES returns partial results until it completes. After
stop/restart the persisted `Everything-WinBrow.db` (~49.7 MB) loaded and the
query still worked. `ensure_everything()` reports `ready` only when an ES query
succeeds, otherwise `indexing`. Final verification: full `winbrow/tests` suite
671 passed, 2 skipped; installer/finder-focused tests 7 passed.

## 24. In-app env settings, chat tombstones, island/cancel fixes (2026-11-02)

- **Settings tab / .env editor.** `winbrow/env_settings.py` owns a curated,
  grouped catalog of environment fields (provider keys, agent budget, voice,
  search, local model, advanced). `GET /api/env` returns effective values with
  secrets masked (`is_set` only); `POST /api/env` merges `updates`/`unset` into
  `.env` atomically, applies them to `os.environ`, and reports
  `requires_restart`. Saving provider/model keys calls `reset_gateway()` +
  `agent.rebuild_gateway()`. The React `Settings` tab (Dashboard ? Settings)
  edits the same file, supports custom keys, and offers a sidecar restart for
  startup-only fields.
- **Values, defaults and source labels.** `/api/env` returns each field's
  effective `value`, `default` and `source` (`env`, `process`, `default`).
  Values from the real `.env` win; unset fields show the code default (computed
  for Everything/wallpaper/image paths and thread count). The UI badges
  `env` / `default` / `optional` and adds a `default: X` hint when a value
  overrides it. The catalog covers all 60 keys in `.env.example`; only the four
  genuinely optional keys (image user agent, extra artifact dirs, external
  local endpoint/model) stay empty. `_SECRET_HINT` now requires a whole key
  segment, so `WINBROW_CONTEXT_TOKENS` / `REASONING_MAX_TOKENS` /
  `PLANNER_MAX_TOKENS` are no longer masked as secrets. Tests:
  `test_env_settings.py` 9 passed.
- **Deleted chats stay deleted.** `frontend/src/lib/useAgent.ts` tombstones
  deleted session IDs in `localStorage` (`winbrow.deletedSessions`). `refresh()`
  filters them from `/api/sessions` and retries the DELETE until the server
  confirms it. This prevents a chat deleted while the sidecar was offline from
  reappearing after an app restart.
- **Dynamic island failure notice is transient.** `deriveIsland()` no longer
  pins `phase=error` for a failed task until the next task. Failed, completed
  and cancelled tasks all use the same 6-second hold before the pill returns to
  Ready.
- **Cancelled tasks drop their questions/options.** `cancel()`, the live
  `task.cancelled` / `task.failed` reducers, the replay reducer, and
  `finalizeFromExecution()` clear `needsInput`, `question` and `options`.
  `Trace` and the Dashboard composer also refuse to render choices for
  cancelled/failed tasks.
- **Frontend build required.** `desktop.bat` only builds when `dist/index.html`
  is missing, so run `cmd /c "npm run build"` in `frontend/` after source
  changes. Tests: `npm test` 61 passed; `test_env_settings.py` 6 passed.
