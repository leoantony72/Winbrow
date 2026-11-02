# Task Checkpoint — Guarded multi-action batching implementation (2026-11-01)

## Current goal and milestone

Implement the Phases 0–2 first slice from `BRAIN_BATCHING_PLAN.md`: backend-owned
tool execution contracts, bounded heterogeneous `steps[]`, a guarded sequential
executor, shared UI ownership and exact permission continuation. DONE — runtime
implementation, focused tests and documentation are complete. Phase 3+ items
(checked-state primitive, reviewed desktop window guard, result bindings,
reviewed MCP/API contracts, measured live benchmark) remain deliberate barriers.

## Shipped surface

- `winbrow/brain/batching.py`: immutable `BatchPolicy` records (exact name +
  dispatcher impl), `WINBROW_MAX_ACTIONS_PER_TURN` default 5 / clamp 1–10,
  all-or-nothing `validate_steps()` preflight, duplicate-mutation and
  result-reference rejection, unknown/learned/script/MCP tools as singletons.
- `winbrow/brain/prompt.py`: `steps[]` first-class and bounded, mixed known-input
  and read-after-write rules, contradictory one-action/read-only text removed,
  per-turn cap in both planner builders, all-member tool contracts injected.
- `winbrow/brain/agent_loop.py`: sequential member execution through `run_skill()`,
  cancellation boundaries, batch/plan telemetry, not-executed reporting,
  barrier stops, exact continuation save/resume; desktop batches replan as
  singletons; permission/denial/expiry never replays the completed prefix.
- `winbrow/execution.py` + `winbrow/agent.py`: re-entrant ContextVar lease held by
  `execute()` and `confirm_pending()`; approval waits while another goal owns
  shared browser/desktop state.
- `winbrow/browser_task.py` + `_guard_batch()`: pinned agent tab/document token,
  selector uniqueness/visibility/enabled checks, same-URL reload/navigation and
  changed-target stops; subagent brains reuse the guard with scoped registries.
  Per-member events now carry batch ID/ordinal/size. No checkbox state claim.
- `winbrow/permissions.py` + `server.py`: request scopes, full canonical `v2:`
  action keys, atomic consume-before-dispatch, exact pending/session/args checks,
  TTL pruning on lookup, one-shot T3, and REST/WebSocket/chat continuation.
- `test_brain_m0.py` adapted to real `Tool` records for batch preflight.

## Verification history (this implementation session)

- `python -m pytest winbrow/tests -q` → 598 passed, 2 skipped.
- `python -m pytest test_brain_m0.py -q` → 50 passed.
- `python -m pytest winbrow/tests/test_batch_policy.py test_batch_execution.py test_browser_batch_guard.py test_permission_scopes.py -q`
  → 309 passed.
- No live provider model call, real CDP/UIA session, form submission or
  performance benchmark was run.
- Root legacy suites still have environment-dependent failures at HEAD when the
  local `.env` supplies a provider (route-tier assertions and a few shared-state
  fixtures). The batching-specific tests pass in a clean environment.

## Next actions

- Phase 3: reviewed desktop window guard, checked-state/desired-state browser
  primitive, audited result bindings, reviewed MCP/API contracts, file/account
  scope metadata, consolidated observation.
- Run a live provider + CDP/UIA smoke and a paired latency benchmark before
  enabling new paths by default. Do not weaken singleton barriers without a
  reviewed contract.

## 2026-11-01 — Planner argument preflight hardening

- `brain/batching.py`: optional `null` now means "omitted" (default is applied),
  a one-item array is unwrapped for scalar text/enum args, enum variants
  (quotes, case, `the … folder`, an absolute path ending in a choice) resolve
  to the exact choice, and rejected args report the skill plus a bounded value
  preview. Absolute subfolders and unknown enum values still fail closed.
- `brain/agent_loop.py`: a rejected proposal injects the failing tool's schema
  for the retry, argument mistakes get a third preflight attempt while
  structural mistakes still stop after two, and `brain_batch_rejected` logs a
  redacted step preview.
- `installer.py`: package aliases extended (`app_id`, `package_name`,
  `application`, `software`, `program`, …) and one-item arrays are accepted.
- `skill_scripts.py`: `run_skill_script.spec` is now `kind="json"`, matching
  `_normalize_spec()`; object specs are no longer rejected preflight.
- Note: the running backend must be restarted after these edits. The trace's
  `folder` enum rejection came from the pre-any-folder `download_images`
  schema at HEAD, not the current working tree.
- Verification: `test_batch_policy.py` 175 passed (includes real `run_command`
  `cwd`, `download_images` absolute-folder and dict-object `run_skill_script`
  regressions); affected loop/batch/MCP/skill suites 88 passed; full
  `winbrow/tests` run passed (see the ledger for the final count).

## 2026-11-01 — Generated deliverables default to the user profile

- Root cause of "PDF saved in the project folder": the html-ppt scaffold
  received a relative `Desktop` parent while `run_skill_script` executed with
  `cwd=<repo>`, producing `D:\Codee\desktop_agent\Desktop\...`. The prompt also
  never supplied the machine's real user-folder paths.
- `skill_scripts.py`: subprocess cwd is now `Path.home()`, never the source
  tree; `PYTHONPATH` still points at the repo for imports.
- `skill_script_utils.resolve_path`: relative `Desktop`/`Documents`/
  `Downloads`/`Pictures`/`Music`/`Videos` paths resolve under the user profile.
- `safe_paths.remap_project_user_folder`: accidental project-local
  `<repo>\Desktop\...` (and the other known folder names) map to the real
  profile; ordinary project paths are untouched. Applied in
  `files.resolve_user_folder`, absolute `create_text_file` filenames and
  `image_tools.resolve_folder`.
- `brain/agent_loop._ctx_block`: every planner turn now lists the exact
  Desktop, Documents, Downloads, Pictures and Videos paths and defaults new
  deliverables to Desktop.
- `brain/prompt.py`: new OUTPUT LOCATION rule (27) and clarified rules 8–9:
  deliverables are user files, never app/project files.
- Document creators (`pdf`, `pptx`, `docx`, `xlsx`, `html-ppt`, EPUB) resolve
  bare output names under Desktop; PDF/PPTX image helpers default to
  `Pictures\WinBrow Images` instead of `Path.cwd()/images`.
- `create-text-file/SKILL.md`: document the relative-profile and app-folder
  rules.
- Verification: path/prompt/skill/batch suites 193 passed; pdf/anthropic/
  converted suites 16 passed; html-ppt 6 passed; broader document/tool suite
  52 passed. Direct smoke with a temporary user profile created PDF, DOCX,
  PPTX, XLSX and EPUB from bare names under `<home>\\Desktop`, and html-ppt
  with relative `Desktop` plus a project-absolute `Desktop` path both landed
  under the profile Desktop, never the source tree. Full suite rerun pending.

---

# Previous checkpoint — Electron UI refresh (2026-11-01)

## Current goal and milestone

Improve the existing Electron UI and integrate the supplied dynamic island
without replacing chat, voice, confirmation, cancellation, or Server wiring.
DONE — implementation, documentation, regression tests and Electron renderer
smoke verification complete.

## Decisions and files

- React/TypeScript already existed. Added Tailwind 3 (no Preflight reset),
  shadcn `components.json`, and `@/` aliases for Vite/TS/Vitest.
- Reusable primitives are `frontend/src/components/ui/{dynamic-island,button,badge}.tsx`;
  `cn()` lives in `frontend/src/lib/utils.ts`.
- `Dashboard.tsx` has a calmer responsive workspace, accessible history controls,
  useful prompt cards, composer guards and correct focus after leaving Server.
- `Island.tsx` uses the provider/shell but retains derivation, priority, expiry,
  kill switch, voice actions, focus/click-through IPC and existing dimensions.
- Showcase route: `?win=component-demo`. No remote images/fonts are needed.
- `frontend/src/test/*` and `scripts/ui-smoke.cjs` exercise UI without real tools.

## Verification so far (this session)

- `npm test -- --reporter=dot`: 54 passed, 3 files (final run).
- `npm exec tsc -- --noEmit`: passed after final test additions.
- `npm run build`: strict TypeScript and Vite production build passed.
- `npm run test:electron`: dashboard/results/Server, 16 island layouts, narrow
  dashboard, component demo passed; no renderer errors. Screenshots inspected
  under `logs/ui-smoke/`.
- `npm audit --omit=dev --audit-level=moderate`: zero production vulnerabilities.
  Full development audit has advisories; no unrelated major upgrades attempted.
- No live CDP/UIA/voice/backend automation was executed.

## Next actions

No pending implementation steps. Build and Electron smoke were repeated after
final short-height CSS/theme refinements; both passed. `git diff --check` passed.
Editor diagnostics: no errors; three expected unknown-`@tailwind` CSS warnings
and three pre-existing line-clamp compatibility warnings. Full development
package audit still has advisories; only the production audit is clean.
A live sidecar/CDP/UIA/voice smoke is a separate follow-up, not covered here.

---

# Previous checkpoint — Converted Skill Library + Integrations

## Goal

Convert the 43 entries from the six requested sections of
`ComposioHQ/awesome-claude-skills` into WinBrow-compatible skills, and add a UI
for the optional services those skills need.

## Status

DONE — all six phases implemented; focused tests passing.

## Scope

- 43 playbooks under `winbrow/skills/library/<section>/<name>/SKILL.md`.
- 21 bundled Python helpers, references, and templates.
- `kind: playbook` support, category-grouped metadata, 12k budget.
- `run_skill_script` (T2, allowlisted) and `integration_status` (T0).
- Integrations panel and backend for 8 providers + dependency status.
- 56 focused tests pass; 69 skill definitions load; metadata ~9,626 chars.

## Key decisions

- Playbooks are guidance-only; a playbook step is acknowledged and the body is
  injected as SKILL DETAIL on the next turn.
- Metadata budget raised from 4,000 to 12,000 chars because 43 entries no longer
  fit. Core descriptions stay longest; playbooks use 95 chars.
- Bundled scripts are invoked through one native runner, not shell-string
  interpolation. Specs travel as JSON; the runner is T2.
- Credentials live in `data/integrations.json`, DPAPI-encrypted on Windows,
  masked on read, env vars win. Gated skills must call `integration_status`
  first.
- Upstream proprietary skills (`docx`, `pdf`, `pptx`, `xlsx`) were rewritten,
  not copied. See `winbrow/skills/library/PROVENANCE.md`.

## Verification run in this session

- `python -m pytest winbrow/tests -q` → 27 passed.
- `python -m pytest test_agent.py test_brain_m0.py test_syntax.py -q` →
  48 passed, 1 pre-existing fixture error (`test_agent.py::test_api` has no
  `cmd` fixture).
- Smoke: PDF, PPTX, XLSX, EPUB, DOCX, CSV, PNG, GIF, and a playbook dispatch.
- `node` compile of both inline scripts → 2 scripts, 0 syntax errors.
- `load_skill_registry` → 69 total, 43 playbooks, including native web_search/web_fetch.

## Subagents (2026-10-26)

- Added `winbrow/subagents.py` and `winbrow/skills/delegate-task/SKILL.md`.
- `delegate_task` (T1) spawns scoped `AgentBrain` children with filtered skill
  and tool registries; child actions still use the parent permission gate.
- Delegation is automatic by default; `WINBROW_SUBAGENTS=0` disables it and
  `WINBROW_SUBAGENTS_EXPLICIT=1` requires an explicit request. Independent
  research/review candidates are forced into the brain before the browser fast
  path.
- Profiles: researcher, file-analyst, writer, code-reviewer, verifier, general.
- Only `file-analyst` is parallel-safe; browser/write profiles are serialized.
- Runs persist to `data/subagents.json` and surface in the **Subagents** panel
  plus `GET /api/subagents`.
- Tests: 37 in `winbrow/tests` pass; 48 core tests (`test_brain_m0`,
  `test_syntax`) pass. Real-model subagent execution was not run (no provider
  key); a scripted gateway covers the child-brain path.

## Web access hierarchy (2026-10-26)

- Root cause: old `web_search` was a seed tool that ran `laya_ultrafast_browser`;
  the router preferred the browser for searches; `_is_browser_intent` treated
  `search` as a browser keyword.
- Added `winbrow/web_tools.py`: native `web_search` (DuckDuckGo HTML API) and
  `web_fetch` (HTTP GET, BeautifulSoup/pdfminer), both T0/no-browser.
- Removed the seed `web_search`; registered web tools in `WinBrowAgent`.
- Added `web-search`/`web-fetch` SKILL.md files; rewrote `browser-navigate` to
  interaction-only.
- Appended the verbatim WEB ACCESS HIERARCHY + WORKED EXAMPLES to the end of
  `SYSTEM_PROMPT_STATIC`, immediately before the AVAILABLE SKILLS block.
- Router now sends search/price/comparison to `web_search` and read/fetch to
  `web_fetch`; booking/checkout/form/login/media/explicit-open still use the
  browser.
- `_is_browser_intent` no longer matches bare research/search/site words.
- Added `.claude/knowledge/session-patterns.md`.
- Tests: `winbrow/tests` 49 pass; core brain/syntax 48 pass. No live network
  search was run.

## Brain-first routing (2026-10-26)

- `WinBrowAgent.execute()` now attempts the brain before replay, MCP shortcuts,
  browser fast path, and router whenever a provider is available.
- `_execute_brain_goal()` uses `handle_browser_task()` for browser-intent
  utterances and `AgentBrain.handle()` for everything else. Tier is
  `brain_first`; planner exceptions are `brain_first_error`.
- Replay is skipped while brain-first is active. Legacy paths are fallbacks
  only for `GatewayUnavailable`/`GatewayError`; a normal brain failure never
  falls through to MCP.
- `WINBROW_BRAIN_FIRST=1` default; `0` restores legacy routing for debugging.
- Tests: `test_brain_first.py` proves MCP shortcuts are bypassed when the brain
  is available and that a planner exception does not fall through to MCP.

## Nebius Token Factory (2026-10-26)

- `winbrow/brain/model_gateway.py` now builds Nebius first in `auto` when
  `NEBIUS_API_KEY` is present; `WINBROW_BRAIN_PROVIDER=nebius` forces it.
- Base URL `https://api.tokenfactory.nebius.com/v1`, default model
  `deepseek-ai/DeepSeek-V4-Flash-0731`; both overridable with
  `WINBROW_NEBIUS_BASE` / `WINBROW_NEBIUS_MODEL`.
- Nebius is OpenAI-compatible; the shared reasoning policy maps to
  `reasoning_effort` (medium structured / none chat / low capped retry).
- Settings UI has a Nebius option; `POST /api/settings` stores the key in
  `NEBIUS_API_KEY` and sets `WINBROW_BRAIN_PROVIDER=nebius`.
- Tests: `test_nebius_gateway.py` (4) covers auto order, env model/base,
  provider preference, and reasoning payload translation.

## Session context + artifacts (2026-10-29)

- `SessionMemory.Turn` now stores `artifacts` (absolute paths created/opened)
  and persists them; older turns are backfilled from stored snippets.
- `reference_hint()` binds follow-ups ("where is the pdf?", "open it") to the
  most recent artifact, flags format mismatches (asked PDF, produced HTML), and
  is injected into the brain prompt. `context_block()` shows artifact paths.
- Fixed `test_brain_m0` wiping the real `default` session via
  `agent.session.reset()`; restored the 12-turn default history.
- Tests: `test_session_context.py` + session/loop/brain suites (27 pass).

## Presentation/PDF pipeline (2026-10-29)

- Root cause of broken deck PDFs: the planner replaced `index.html` and linked
  a non-existent `assets/index.css`, dropping `base.css`, the theme, `.deck`,
  and `runtime.js`. Chrome then printed unstyled HTML (3 pages, light text on
  white).
- Added `winbrow/deck_repair.py`: restores required CSS/theme/runtime, wraps
  stray slides in `.deck`, adds the `tpl-*` body class, normalises h1/h2, and
  injects token-based fallback CSS. Idempotent; never changes slide text.
- Added `winbrow/deck_layout.py`: headless Chrome measures each slide's
  overflow; export fails with the exact slide instead of clipping text.
- `html_to_pdf.py`: `auto` page resolves decks to 16:9 (13.333x7.5in) and
  documents/resumes to A4; print CSS forces one slide per page and
  `print-color-adjust: exact`; added legal/a5 sizes.
- `render_deck.py` repairs + layout-checks + validates page count/size before
  reporting success. `pdf_tool.from_html` defaults to `auto` and repairs decks.
- `layout/pdf.py` adds a `resume` theme; `pdf_tool.create` supports
  `document_kind=resume|cover_letter|official`, A4/Letter portrait, no page
  numbers. Optional `latex` operation compiles via pdflatex/xelatex/lualatex/
  latexmk when installed (not installed on this machine).
- Prompt/SKILL rules now forbid replacing scaffolded HTML, require preserving
  asset links, default decks to 16:9, and send resumes/official docs to
  A4/Letter.
- Verification: 24 PDF/deck tests pass; the real
  `remote-execution-vulnerability` deck exported 12 pages at 960x540 with no
  overflow; a sample resume exported A4 595.28x841.89 with no warnings.

## Next actions

- Install optional packages as needed: `pip install -r
winbrow/skills/library/requirements-skills.txt`.
- Configure credentials in the Integrations panel before using gated skills.
- Live-smoke the Google OAuth flow and the NotebookLM browser flow.
- Run the full repo suite when time allows; `test_agent.py::test_api` needs a
  fixture and is unrelated.

## 2026-11-01 - Skill/tool architecture audit

- Audited 81 SKILL.md files against 218 live tools (42 batch-eligible, 176
  reviewed-or-unknown singletons). No advertised skill lacks an executor now.
- Fixed: skill-writer output is always a `kind: playbook` with a `playbook_` key
  (eight orphan tool skills were converted and moved into `skills/library/`);
  MCP `ArgSpec.required` preserves inputSchema optionality (29/126 tools were
  unusable); selector-only `browser_interact`; required `create_text_file` /
  `open_file` args; playbook batch rejection now explains the singleton rule.
- Remaining conditional dependency: `mcp_filesystem_move_file` exists only when
  the filesystem MCP server is enabled. It is enabled and cached in this repo.
- Verification: `pytest winbrow/tests -q` -> 618 passed, 2 skipped; skill
  validator -> 0 errors; helper-script JSON smoke; MCP preflight sweep.

## 2026-11-01 - Playbook detail persistence + copyable UI

- SKILL DETAIL for a playbook now persists as `ACTIVE PLAYBOOK GUIDANCE` for
  the whole run and is combined with each turn's tool schema; permission
  resumes restore it. The one-turn injection previously let a `run_command`
  call evict the `html-ppt` workflow.
- MCP array/object schema args use `ArgSpec(kind="json")`; preflight accepts
  lists for `excludePatterns`/`paths` instead of failing as non-scalar.
- UI: content text is selectable (chrome stays `user-select: none`) and copy
  buttons cover chat turns, reasoning, step details, answers, Server prompt
  groups and Server entries.
- Verification: winbrow tests 621 passed / 2 skipped; vitest 57 passed; tsc and
  Vite build pass.

## 2026-11-01 - Any-folder writes

- Write tools no longer restrict `folder` to a short enum. `download_images`,
  `create_text_file`, `download_file` and `take_screenshot` accept an alias, a
  relative subfolder under the user profile, or any absolute/UNC path.
- `winbrow/safe_paths.py` is the single policy: Windows, Program Files,
  ProgramData, Recovery, Boot, EFI, PerfLogs, Config.Msi and similar OS-owned
  trees are refused; everything else is writable.
- Verification: winbrow tests 629 passed / 2 skipped; rendered PowerShell
  scripts parse clean; skill validator 0 errors.

## 2026-11-01 - Consent-based browser password import

- Added `winbrow/browser_credentials.py` and the **Passwords** modal in
  `templates/index.html`. The only input is a CSV the user exports from the
  browser's own password manager; no `Login Data`/DPAPI browser decryptor was
  added.
- Preview returns metadata only. Commit stores just the checked row IDs, with
  passwords encrypted by Windows DPAPI in `data/browser_credentials.json`
  (gitignored, best-effort ACL). REST responses never include secrets.
- `get_credential_for_origin()` exists only as an internal broker helper; there
  is no model-facing tool that returns a password.
- Verification: full `winbrow/tests` suite 661 passed, 2 skipped;
  `test_browser_credentials.py` 10 passed; integration tests 8 passed;
  `test_browser_batch_guard.py` 53 passed; py_compile clean; both inline UI
  scripts pass `node --check`; no live browser or model run.

## 2026-11-02 - PDF generation latency audit

- Recent PDF tasks were slow because of orchestration, not the layout engine.
  Thrissur Pooram run: 18 planner calls = 185.1s, tools = 96.7s; 6-image
  download = 63.1s; final PDF script = 13.3s. Indian-art run: 13 steps =
  144.0s tools, 5 image downloads = 53.9s, failed Edge export = 33.5s,
  successful Chrome export = 26.3s.
- Benchmarks: 5-page PDF + 5 images + validation = 6.0s; five-slide HTML render
  = 2.8s + 1.6s validation.
- Fixed the avoidable export failure: `run_command` rejects `--print-to-pdf`
  and the static prompt routes deck/page export to `render_deck.py` /
  `pdf_tool.py from_html`.
- Remaining opportunities: parallel/multi-query `download_images`, fewer
  planner turns, MCP `path`/`file_path` normalization, image downscaling.
- Verification: shell/prompt/PDF/deck suites 35 passed; py_compile clean.
- The full suite initially hit one unrelated brittle assertion: the converted
  library lint compared *all* playbooks against the 54 library entries, so the
  new top-level `retrieve-internal-marks` skill made it fail. Scoped the lint to
  `winbrow/skills/library/`; `test_converted_skills.py` 5 passed.
- Final full-suite rerun: 664 passed, 2 skipped.

## 2026-11-02 - Indexed find_files

- `find_files` now checks the Windows Search index first (`SYSTEMINDEX` via
  OleDb/Search.CollatorDSO), then Everything `es.exe` when installed, then the
  existing Desktop/Documents/Downloads/Pictures depth-4 fallback.
- Measured index hit: 0.72–0.91s (previous scoped no-match probe: 3.76s).
  Index search is C:\Users-oriented; unindexed drives still require Everything
  or a full path.
- The persistent PowerShell host does not treat top-level `return` as “stop
  this input”, so each backend is guarded by `$results.Count -eq 0` and the
  final result is one mutually exclusive `if/elseif/else`.
- The search term is interpolated into a single-quoted PowerShell string so
  `$()` is literal, not executable.
- Live smoke: `indian_art_styles` found via Windows Search index in 0.72s;
  a temporary Downloads probe was found by the fallback in 8.54s (new file not
  indexed). `es.exe` is not installed on this machine, so that branch was
  reviewed but not live-exercised.
- Verification: `test_find_files_tool.py` 2 passed after the final quoting/guard
  changes; full `winbrow/tests` suite 666 passed, 2 skipped. Targeted
  adapter/installer suites remain 292 passed, 3 skipped, with 4 known
  environment-dependent failures in `test_m2_adapters.py`
  (brain-first/replay route assertions).

## 2026-11-02 - Portable Everything auto-install

- Added `winbrow/everything.py`: checks `%LOCALAPPDATA%\WinBrow\Everything`,
  downloads official voidtools x64 Everything 1.5.0.1424b + ES 1.1.0.38 zips
  when missing, verifies SHA-256 and Authenticode (`voidtools PTY LTD`), and
  extracts only the three required files.
- Starts a private `WinBrow` Everything instance with `-startup`, app-local
  config, and folder indexing for fixed drives; no service/admin required.
  `server.py` runs it in a background task after PowerShell warm-up and skips
  it under pytest. `find_files` prefers the app-local `es.exe` with
  `-instance WinBrow -timeout 5000`.
- Live smoke: temp install + Desktop folder index found a unique file via ES
  after Windows Search missed it. End-to-end `find_files` test also found a
  temp file through the app-local ES instance.
- Production install completed in `%LOCALAPPDATA%\WinBrow\Everything`; the
  private `WinBrow` instance is running and `find_files` found
  `D:\Codee\desktop_agent\BRAIN_BATCHING_PLAN.md` via Everything after Windows
  Search missed it. The full C:\ + D:\ folder index completed to a ~49.7 MB
  `Everything-WinBrow.db`; after stop/restart, `ensure_everything()` reported
  `ready` and the D: query still worked.
- `ensure_everything()` reports `ready` only when an ES query succeeds,
  otherwise `indexing`; startup logs the distinction.
- Tests: `test_everything_setup.py` + `test_find_files_tool.py` 7 passed after
  the final stale-lock/architecture tweaks; full `winbrow/tests` suite 671
  passed, 2 skipped; py_compile clean; pytest startup side effect is skipped.

## 2026-11-02 - find_files is Everything-only

- `tools/seed.json` `find_files` uses the Everything CLI (`es.exe`) as its
  **only** backend. Both the old Desktop/Documents/Downloads/Pictures
  `Get-ChildItem` walk and the `SYSTEMINDEX` Windows Search query were deleted.
- The script starts the portable `WinBrow` Everything instance itself when
  `es.exe -get-everything-version` reports it is not running, so searches work
  even if the server's startup task has not run.
- Tool description, `winbrow/skills/find-files/SKILL.md`, README, catalogue,
  `.env.example`, `server.py` log text, and knowledge/06 now describe Everything
  as the only search backend.
- Root cause of the "still searching Downloads/Pictures" report: the running
  uvicorn process started at 10:32 and had the old `seed.json` in memory. The
  registry only loads seed tools at construction, so the server must be
  restarted after a seed/skill change.
- Tests: `test_find_files_tool.py` rewritten (3 passed) to assert `es.exe` is
  present and `SYSTEMINDEX`/`Get-ChildItem` are absent; rendered script parsed
  by the PowerShell AST and live-tested with Everything stopped (auto-started
  and found `BRAIN_BATCHING_PLAN.md`).
- Live API verification after restarting uvicorn: `/api/tools` reports the new
  Everything-only description (`uses_folders=False`, `uses_systemindex=False`),
  and `POST /api/execute` for "find the file BRAIN_BATCHING_PLAN" returned
  `Found 1 file(s) matching 'BRAIN_BATCHING_PLAN' in Everything:
  D:\Codee\desktop_agent\BRAIN_BATCHING_PLAN.md (37.2 KB)`.


## 2026-11-02 - find_files case-insensitive + folder results

- ES 1.1.0.38 defines `-i` as **match case**. The tool was passing `-i`, so a
  lowercase query (`kaithi`) never matched `KAITHI_2019_...mp4`. The flag is
  removed; ES default case-insensitive is used.
- The tool filtered hits with `Test-Path -PathType Leaf`, which dropped every
  directory from Everything results. It now queries `/ad` (folders) first and
  `/a-d` (files) second, dedupes, and renders folders as `[folder] path`.
- ES stdout decoding in the persistent host mangles non-ASCII paths, so the
  tool now uses `-export-json <tmp> -utf8-bom` and reads the export with UTF-8
  + `ConvertFrom-Json`. This fixes the NBSP in
  `KAITHI_2019_Tamil Proper...mp4` and any other Unicode filename.
- Live pshost checks: `kaithi` returned `D:\movie\KAITHI_2019_Tamil...mp4`;
  `pcc` returned `[folder] D:\Codee\pcc\`; `*.mkv` returned the D:\movie files
  with their Unicode names intact.
- Tool description, catalogue, README, knowledge/06, and the find-files
  SKILL.md now say files AND folders and forbid `run_command` /
  `mcp_filesystem_list_directory` name lookups.

## 2026-11-02 - Settings tab, chat tombstones, island fixes

- Added `winbrow/env_settings.py` + `GET/POST /api/env`: grouped .env editor,
  secret masking, atomic merge, live `os.environ` updates, restart flags, and
  gateway rebuild for provider/model keys.
- Added `frontend/src/Settings.tsx` and a Dashboard Settings tab. It supports
  curated fields, custom variables, clear/undo, filtering, and a restart
  banner wired to `window.winbrow.restartSidecar()`.
- Deleted chats are tombstoned in localStorage (`winbrow.deletedSessions`).
  `refresh()` hides tombstoned sessions and retries the DELETE until the
  server confirms; this fixes chats reappearing after an app restart.
- `deriveIsland()` no longer pins a failed task forever: failed/completed/
  cancelled tasks all expire after the 6s hold and return to Ready.
- `cancel()`, `task.failed`, `task.cancelled`, `finalizeFromExecution`, Trace
  and the Dashboard composer now clear or suppress `needsInput`/`options` for
  cancelled/failed tasks.
- Verification: `npm run build` clean; `npm test` 61 passed;
  `test_env_settings.py` 6 passed; live API round-trip for a custom key;
  `winbrow/tests/test_find_files_tool.py` still green.
- Live UI check in the Vite dashboard: the Settings tab rendered 47 fields
  with masked secrets and restart badges. A temporary chat was created,
  deleted from the rail (X), confirmed gone from `/api/sessions`, and
  stayed gone after a full page reload.
- Settings now shows the real .env value or the code/computed default for every field, with env/default/optional badges and a default hint when overridden. The catalog covers all 60 .env.example keys. Fixed the TOKENS-named fields being masked as secrets.
