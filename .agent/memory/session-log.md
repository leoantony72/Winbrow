# Session Log

Append-only. The `Stop` hook (`.agent/hooks/post-session.py`) adds one entry per session.
Permanent findings belong in `.agent/knowledge/`; this file is chronological context.

## 2026-10-25 — Knowledge base bootstrap

- **Scope:** Read the `winbrow/` codebase, then build `AGENT.md`, six knowledge files, task memory,
  and the post-session hook.
- **Key findings:**
  - Browser control is raw CDP (HTTP `/json/*` or one consent-mode WebSocket via
    `DevToolsActivePort`), not Playwright/pydoll/Selenium.
  - There are two independent skill systems: brain markdown skills (`winbrow/skills/*/SKILL.md`,
    progressive disclosure, writer-generated) and procedural replay (`tools/skills.json`, approved
    records only, Jaccard ≥ 0.66).
  - Uncommitted work adds the post-session skill writer and its hot-reload path.
  - `WinBrowAgent.run_skill()` is the single permission + dispatch funnel.
  - The current tree is Windows-first: PowerShell/COM/UIA + ctypes, with a cloud-first planner.
- **Verified issue count:** 58 (`05-known-issues.md`; browser 20, desktop 14, routing/generation 14,
  IO/memory/voice 10).
- **Documented decisions:** 12 (`06-recent-changes-and-decisions.md`).
- **Verification:** Source inspection only. No live CDP, UIA, COM, voice, or end-to-end task was run.
  No test suite was executed for this bootstrap; do not claim otherwise.
- **Stale knowledge:** none at bootstrap. `stale.md` is created only by the hook when a source file
  is newer than a knowledge file's `last_verified` date.

## 2026-10-25 10:52 - session

- **Summary:** Bootstrap verification: knowledge files, hook, and settings validated; no stale knowledge.
- **Changed files:** `M tools/skills.json`, `M winbrow/agent.py`, `M winbrow/brain/agent_loop.py`, `M winbrow/brain/skill_registry.py`, `?? .agent/`, `?? AGENT.md`, `?? winbrow/brain/skill_writer.py`, `?? winbrow/tests/`
- **Knowledge:** 6 file(s) present; 0 stale
- **Auto-refresh:** not needed: no stale knowledge

## 2026-10-25 - converted skill library

- **Summary:** Added 43 playbook skills from the six requested sections, 21 bundled helpers, playbook dispatch, the script runner, and the Integrations panel/backend.
- **Changed files:** winbrow/skills/library/**, winbrow/skill_scripts.py, winbrow/skill_script_utils.py, winbrow/integrations.py, winbrow/brain/skill_registry.py, winbrow/brain/agent_loop.py, winbrow/brain/prompt.py, winbrow/agent.py, winbrow/permissions.py, server.py, templates/index.html, winbrow/tests/*
- **Verification:** pytest winbrow/tests -q -> 27 passed; pytest test_agent.py test_brain_m0.py test_syntax.py -q -> 48 passed, 1 pre-existing fixture error; smoke PDF/PPTX/XLSX/EPUB/DOCX/CSV/PNG/GIF; 65 skills, 43 playbooks, metadata ~9,060 chars.
- **Knowledge:** 03 and 06 updated; no stale knowledge.

## 2026-10-26 - scoped subagents

- **Summary:** Added delegate_task, six scoped subagent profiles, automatic delegation by default, filtered skill/tool registries, child-brain execution through the parent permission gate, parallel-safe file analysis, run history, and a Subagents UI panel. Independent research/review candidates are forced into the brain before the browser fast path.
- **Changed files:** winbrow/subagents.py, winbrow/skills/delegate-task/SKILL.md, winbrow/agent.py, winbrow/brain/agent_loop.py, winbrow/brain/prompt.py, winbrow/brain/skill_registry.py, winbrow/permissions.py, server.py, templates/index.html, winbrow/tests/test_subagents.py, docs.
- **Verification:** pytest winbrow/tests -> 37 passed; pytest test_brain_m0.py test_syntax.py -> 48 passed; scripted-gateway child brain test; node UI syntax 0 errors.
- **Limitations:** no live model-provider run; browser subagents are intentionally serialized. Set WINBROW_SUBAGENTS=0 to disable or WINBROW_SUBAGENTS_EXPLICIT=1 to require an explicit request.

## 2026-10-26 - web access hierarchy

- **Summary:** Replaced the browser-backed web_search with native HTTP web_search/web_fetch, added the verbatim WEB ACCESS HIERARCHY + WORKED EXAMPLES to the planner prompt, narrowed browser intent, and routed research/search/price/doc reads away from the browser.
- **Changed files:** winbrow/web_tools.py, winbrow/skills/web-search/SKILL.md, winbrow/skills/web-fetch/SKILL.md, winbrow/skills/browser-navigate/SKILL.md, winbrow/agent.py, winbrow/router.py, winbrow/browser_tools.py, winbrow/brain/prompt.py, winbrow/brain/skill_registry.py, winbrow/permissions.py, tools/seed.json, requirements.txt, .claude/knowledge/session-patterns.md, tests.
- **Verification:** pytest winbrow/tests -> 49 passed; test_scenarios/test_winbrow_all/test_brain_m0/test_syntax -> 104 passed. No live network search or browser run was performed.
- **Limitations:** DuckDuckGo HTML can be rate-limited; the tool reports that honestly and never falls back to the browser for research.

## 2026-10-26 - brain-first routing

- **Summary:** Every user request now attempts the brain before replay, MCP shortcuts, the browser fast path, or the router. Legacy paths remain fallbacks only when the provider is unavailable or fails.
- **Changed files:** winbrow/agent.py, winbrow/tests/test_brain_first.py, AGENT.md, .env.example, docs.
- **Verification:** pytest winbrow/tests -> 52 passed; test_m6_mcp/test_scenarios/test_winbrow_all/test_brain_m0/test_syntax -> all passed with provider-failure fallback.
- **Limitation:** with a configured provider that returns 402/429, the request still tries the brain first, then falls back to legacy routing.

## 2026-10-26 - Nebius Token Factory

- **Summary:** Added Nebius Token Factory as an OpenAI-compatible brain provider. NEBIUS_API_KEY puts it first in auto; WINBROW_BRAIN_PROVIDER=nebius forces it. OpenRouter/OpenAI remain fallbacks.
- **Changed files:** winbrow/brain/model_gateway.py, server.py, templates/index.html, .env.example, .env comments, tests/test_nebius_gateway.py, docs.
- **Verification:** pytest winbrow/tests -> 56 passed; test_brain_m0/test_syntax -> 48 passed; test_scenarios -> 3 passed. No live Nebius request was made (no key).
- **Limitations:** default model deepseek-ai/DeepSeek-V4-Flash-0731 can be overridden with WINBROW_NEBIUS_MODEL.

## 2026-11-01 - Electron workspace and dynamic island

- **Summary:** Refreshed the responsive dashboard; installed Tailwind/shadcn structure and reusable dynamic-island, Button, Badge primitives. Integrated the island into real state rendering while preserving backend/permission/voice/kill-switch paths. Added accessible history controls, focus repair, offline/busy/IME composer guards, and an isolated showcase.
- **Changed files:** frontend renderer/components/styles/config/dependencies, regression tests and Electron smoke script, frontend/README.md, architecture section 9, task checkpoint and ledger.
- **Verification:** `npm test -- --reporter=dot` -> 54 passed; `npm exec tsc -- --noEmit` passed; `npm run build` passed; `npm run test:electron` passed (dashboard/results/Server, 16 island layouts, narrow layout, showcase, no renderer errors); `git diff --check` passed. Screenshots reviewed at `logs/ui-smoke/`. `npm audit --omit=dev --audit-level=moderate` -> zero production vulnerabilities.
- **Limitations:** No live sidecar/CDP/UIA/voice actions were run. Development-toolchain audit advisories remain; no unrelated major upgrades applied. CSS editor warnings are Tailwind directives plus existing line-clamp compatibility hints.

## 2026-11-01 - Guarded action batching research

- **Summary:** Researched multi-action planning, bounded browser sequences, programmatic orchestration and dependency-aware execution. Created `BRAIN_BATCHING_PLAN.md` with a phased native-checkbox MVP, observation optimization and later approved workflow reuse. Existing `steps[]` execution already supports multiple ordered commands; planner policy restricts mutation batching.
- **Safety review:** Added fail-closed protection against whole-goal approval replay after partial guarded execution, shared ownership covering existing foreground writers, and backend-enforced reviewed-form eligibility. No arbitrary-code executor, provider migration or parallel UI mutations recommended.
- **Changed files:** `BRAIN_BATCHING_PLAN.md`, `.agent/knowledge/04-request-data-flow.md`, checkpoint, ledger and this log. Preserved existing UI/source changes.
- **Verification:** `python -m pytest winbrow/tests/test_parallel_reads.py winbrow/tests/test_loop_recovery.py -q` → 9 passed in 25.66s; local plan JSON/reference/fence/whitespace validation passed; targeted `git diff --check` passed with LF/CRLF warnings.
- **Limitations:** Research/plan only; no runtime implementation, provider call, live CDP/UIA or speed benchmark. Initial repository-wide status timed out after partial output; subsequent validation was path-scoped.

## 2026-11-01 - General-purpose multi-step scope clarification

- **Summary:** User clarified that checkbox selection was only an example. Revised `BRAIN_BATCHING_PLAN.md` into a general planner/executor feature for any eligible task, with heterogeneous tools, ordered known-input dependencies, independent read parallelism and explicit reasoning/approval barriers. Checkbox state-setting is now an adapter example, not the first-release boundary.
- **Decisions:** Generic tool execution contracts and multi-domain fixtures come first; exact scoped T2/T3 pause/resume is part of shared executor work rather than deferred workflow reuse. Unknown tool capabilities remain conservative until reviewed. No broad task-category or mixed-tool ban.
- **Changed files:** Plan, request-data-flow proposal summary, checkpoint, ledger and this log only; no application source or settings changed.
- **Verification scope:** Targeted registry and document-tool source review; revised plan JSON/reference/fence/whitespace and scope checks plus targeted diff check recorded in checkpoint. Application tests were not rerun for documentation-only edits; prior nine passing tests belong to the original research turn.

## 2026-11-01 - Guarded multi-action batching implementation (Phases 0-2)

- **Summary:** Implemented backend-owned batch contracts, bounded heterogeneous `steps[]`, a sequential guarded executor, shared browser/desktop ownership and exact permission continuation. Unknown/learned/script/MCP tools remain singleton barriers; desktop batches replan as single actions until a window guard exists.
- **Changed files:** `winbrow/brain/batching.py`, `winbrow/brain/agent_loop.py`, `winbrow/brain/prompt.py`, `winbrow/execution.py`, `winbrow/agent.py`, `winbrow/permissions.py`, `winbrow/browser_task.py`, `winbrow/subagents.py`, `server.py`, `test_brain_m0.py`, `winbrow/tests/test_batch_policy.py`, `test_batch_execution.py`, `test_browser_batch_guard.py`, `test_permission_scopes.py`, `.env.example`, `README.md`, `AGENT.md`, plan/knowledge/memory.
- **Verification:** `python -m pytest winbrow/tests -q` -> 598 passed, 2 skipped; `test_brain_m0.py` -> 50 passed; focused batch/policy/guard/permission files -> 309 passed. No live provider, CDP/UIA, form submission or benchmark.
- **Limitations:** A few unrelated root suites fail at HEAD in this workspace when `.env` supplies a live provider (route-tier assertions expect legacy tiers); reproduced without the batching code. Checkbox state, reviewed desktop window guards, result bindings and MCP/API contracts remain Phase 3+ barriers.

## 2026-11-01 - Fix tool preflight defaults and argument aliases

- **Summary:** Fixed false `brain_batch_rejected` errors. Optional enum defaults (`web_search.freshness=""`) were rejected by the new validator; installer app tools also demanded `package` when the planner used `app`/`app_name`/`name`/`query`. Enum matching is now case-insensitive, a declared empty optional default is valid, common recency words are canonicalized (`today` -> `day`, `recent` -> `week`), and installer package aliases are normalized both before preflight and at execution. Unknown enum values still fail closed.
- **Changed files:** `winbrow/brain/batching.py`, `winbrow/web_tools.py`, `winbrow/installer.py`, `winbrow/tests/test_batch_policy.py`, `winbrow/tests/test_web_tools.py`, `.agent/knowledge/04-request-data-flow.md`.
- **Verification:** `test_batch_policy.py` + `test_web_tools.py` -> 169 passed, 1 skipped; `test_batch_execution.py` + `test_parallel_reads.py` + `test_permission_scopes.py` -> 118 passed. No full-suite rerun.

## 2026-11-01 - Server activity grouped by prompt (IST)

- **Summary:** Reworked the dashboard **Server activity** page so every prompt is a collapsible dropdown stamped with its start time in IST. Each dropdown lists the prompt's brain plans/reasoning, actions, answers, approvals and completion oldest-to-newest. Live/running prompts and the newest prompt open by default; older prompts stay collapsed. Live activity is merged with persisted task steps without duplicate thinking/answer rows, and server/connection lines are collected in a final **Server & connection** dropdown.
- **Changed files:** `frontend/src/Server.tsx`, `frontend/src/styles.css`, `frontend/src/test/Dashboard.test.tsx`, `frontend/README.md`.
- **Scroll fix:** The Server root only had `.activity` (a plain block), so `.connection-scroll` never received a bounded flex height and long open dropdowns were clipped. `.activity` now shares the same flex column/min-height:0 rules as `.connection`; the Electron smoke injects 2400px of content and verifies the scroller can move.
- **Verification:** `npm.cmd exec tsc -- --noEmit` passed; `npm.cmd run build` passed; `npm.cmd test` -> 55 passed across 3 files, including a new test for IST-stamped prompt dropdowns and oldest-first action order. Electron UI smoke passed, including computed Server flex/overflow checks and a real scroll-height check. Existing Server filter/clear/restart tests still pass.

## 2026-11-01 - Skill/tool architecture compatibility audit

- **Summary:** Audited all 81 SKILL.md files and all 218 live tools against the guarded-batching executor. Fixed four classes of incompatibility: (1) nine advertised tool skills had no executor (eight were skill-writer output); they are now library playbooks, and the writer always emits `kind: playbook` with a `playbook_` key; (2) 29/126 MCP tools were rejected preflight because optional inputSchema args without defaults were treated as required, so `ArgSpec` now carries explicit `required`; (3) `browser_interact` was unusable selector-only because `instruction` was required despite the skill documenting the selector fast path; (4) `create_text_file`/`open_file` now enforce the required arguments their SKILL.md documents. Playbook-in-batch rejection now explains how to load guidance. Playbooks remain intentional singletons.
- **Changed files:** `winbrow/registry.py`, `winbrow/mcp.py`, `winbrow/browser_tools.py`, `winbrow/brain/batching.py`, `winbrow/brain/skill_registry.py`, `winbrow/brain/skill_writer.py`, `tools/seed.json`, eight SKILL.md conversions under `winbrow/skills/library/`, `winbrow/tests/test_batch_policy.py`, `test_mcp_args.py` (new), `test_skill_writer.py`, `test_converted_skills.py`, README/knowledge.
- **Verification:** `python -m pytest winbrow/tests -q` -> 618 passed, 2 skipped; skill validator (spec `{"all": true}`) -> 81 skills, 0 errors; all 27 helper scripts compile and emit one JSON object; all 126 MCP tools preflight with only their schema-required args. No live provider/CDP/UIA run.

## 2026-11-01 - Persistent playbook guidance + copyable UI

- **Summary:** Fixed SKILL DETAIL eviction. A playbook body was injected for one planning turn, then replaced by the next tool's schema, so the planner lost the workflow mid-task (seen with `playbook_html_ppt` -> `run_command`). The latest playbook body now persists as `ACTIVE PLAYBOOK GUIDANCE` for the rest of the run and is combined with the current tool schema; permission continuations carry it. Also fixed MCP array/object arguments (`excludePatterns`, `paths`) being rejected as non-scalar by adding a `json` ArgSpec kind. UI: text selection is enabled app-wide for content; copy buttons added to chat user turns, reasoning, step details, the answer, and Server activity (prompt group + individual entries); row toggles ignore an active text selection.
- **Changed files:** `winbrow/brain/agent_loop.py`, `winbrow/brain/prompt.py`, `winbrow/brain/batching.py`, `winbrow/mcp.py`, `winbrow/tests/test_playbooks.py`, `test_batch_policy.py`, `test_mcp_args.py`, `frontend/src/components/CopyButton.tsx` (new), `Trace.tsx`, `Dashboard.tsx`, `Server.tsx`, `styles.css`, `frontend/src/test/CopyButton.test.tsx` (new).
- **Verification:** `python -m pytest winbrow/tests -q` -> 621 passed, 2 skipped; `npm.cmd test` -> 57 passed; `npm.cmd exec tsc -- --noEmit` and `npm.cmd run build` pass. No live provider/browser run.

## 2026-11-01 - Any-folder writes (system paths refused)

- **Summary:** Removed the friendly-folder enums that blocked real paths. `download_images.folder`, `create_text_file.folder` and `download_file.folder` now accept Desktop/Downloads/Documents/Pictures/Videos, a relative subfolder under the user profile, or any absolute path (another drive, project folder, UNC share). A new `winbrow/safe_paths.py` refuses Windows, Program Files, ProgramData, Recovery, Boot and similar OS-owned trees; `files.write_named_text_file`, `image_tools.resolve_folder/download_image`, and the `download_file`/`take_screenshot` PowerShell guards enforce it. `create_text_file` also accepts a full path in `filename`. Prompt rules and both skill docs now describe the wider contract.
- **Changed files:** `winbrow/safe_paths.py` (new), `winbrow/files.py`, `winbrow/image_tools.py`, `tools/seed.json`, `winbrow/brain/prompt.py`, `winbrow/skills/create-text-file/SKILL.md`, `winbrow/skills/download-images/SKILL.md`, `winbrow/tests/test_safe_paths.py` (new), `test_image_tools.py`, `test_m2_adapters.py`, knowledge.
- **Verification:** `python -m pytest winbrow/tests -q` -> 629 passed, 2 skipped; `TestFileWrites` -> 2 passed; both rendered PowerShell scripts parse with 0 errors; skill validator 81 skills/0 errors. No live download/write to another drive was run.
