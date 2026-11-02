# General-purpose multi-action planning for WinBrow

**Date:** 2026-11-01

**Status:** Implemented (Phases 0–2 first slice) on 2026-11-01. Sections 1–3
remain the research record that motivated the change; §7 records the shipped
surface, verification and remaining barriers.

## Recommendation

Make multi-step emission a **general capability of the brain**, applicable to
any supported task that can safely execute several commands without another
model decision. Checkboxes are one example, not the feature boundary or a
prerequisite for other task types. Commands need not be identical, use the same
tool, or belong to the same domain.

The governing rule is: **plan through predictable execution, stop at unresolved
reasoning or authorization boundaries**. Let deterministic code execute and
verify known work; return to the brain when a new result requires judgment.

Examples include reading several documents, gathering known web sources,
creating and populating known file paths, applying browser form edits, performing
reviewed desktop sequences, document processing, and eligible MCP/API workflows.
Applicability depends on each operation's contract, permissions and resources,
not on a task-name whitelist.

**Multiple commands per response is not the same as parallel execution.**
Sequential execution is the general default, including dependent known-input
steps. Parallelize only independently safe calls. One browser tab and the Windows
foreground desktop are shared mutable resources; their mutations remain ordered.

For repeated tasks across separate requests, add approved, parameterized workflow
reuse later. Reuse validated action structure, not hidden model reasoning,
old approval grants or stale DOM selectors.

## 1. What the current source actually does

The bottleneck is not simply a missing loop over commands: part of the required
infrastructure already exists.

| Verified source                                   | Current behavior                                                                                                                           | Consequence                                                                                  |
| ------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------ | -------------------------------------------------------------------------------------------- |
| `winbrow/brain/prompt.py:15–58`                   | Schema accepts both `step` and legacy `steps[]`; no array-size bound.                                                                      | No provider migration is needed to emit several commands.                                    |
| `winbrow/brain/prompt.py:62–100,179–184`          | Emit one action, except 2–3 independent read-only calls; observe after successful mutations.                                               | The model is instructed not to batch mutations in any task domain.                           |
| `winbrow/brain/agent_loop.py:1125–1155,1319–1323` | Iterates over supplied steps, clipped to the remaining action budget.                                                                      | Ordered multi-step execution already works; extend it rather than replacing the brain.       |
| `winbrow/brain/agent_loop.py:229–238`             | `WINBROW_PARALLEL_READS` defaults off; an explicit read-only allowlist can run concurrently.                                               | This flag does not enable safe UI batching.                                                  |
| `winbrow/brain/agent_loop.py:1416–1423,1561–1562` | Permission/policy stops return immediately; an ordinary failure ends the current sequence and replans.                                     | Reuse these behaviors, but add explicit unexecuted-member reporting and state-change guards. |
| `winbrow/brain/agent_loop.py:2154–2189`           | Skill-detail injection selects only the first member; details reach the next model turn.                                                   | General mixed-skill batches need an instruction/schema-availability policy.                  |
| `winbrow/browser_tools.py:46–96`                  | DOM snapshot supplies selector, label, type and disabled state, but no checked/indeterminate state; native inputs default to textbox role. | The brain cannot reliably distinguish checked from unchecked controls.                       |
| `winbrow/browser_tools.py:756–769,850–860`        | Generic interaction chooses type for nonempty `value`, otherwise click; sleeps 0.6 seconds and refreshes page state.                       | `value="true"` does not check a checkbox. Repeated clicks can undo work.                     |
| `winbrow/browser_task.py:2074–2083`               | `fill_and_submit_form()` exists, but always reports success and does not stop on failed fields. No callers found.                          | Do not expose this helper unchanged as the solution.                                         |
| `winbrow/agent.py:443–479`                        | `run_skill()` is the registry/permission funnel for dispatched tools.                                                                      | Every executable batch member must retain this gate.                                         |
| `server.py:781–807`; `winbrow/agent.py:888–897`   | REST approval reruns the original utterance; browser tasks reset tab scope.                                                                | Approval is not exact continuation and may repeat prior side effects.                        |

The single-action docstrings and older knowledge snapshot understate existing
batch support. This session corrects the relevant knowledge, not runtime code.

Existing `brain_plan` telemetry already records token counts, cache reads,
parse status and elapsed time (`agent_loop.py:1677–1708`). Extend it rather than
building a second measurement system. The gateway uses planner JSON output with
`strict=False` (`model_gateway.py:898–902`), so local validation is essential;
adding schema constraints alone is not enforcement.

## 2. Research findings

All links below were reviewed on 2026-11-01. Published results describe their
own workloads, **not a measured WinBrow speedup**.

### A. Browser agents already use bounded multi-action turns

[Browser Use's parameter reference][1] documents `max_actions_per_step=5`,
explicitly gives multi-field form filling as an example, and executes queued
actions until the page changes. Its [multi-action guard tests][2] cover static
sequence-ending actions, URL/focus changes and safe input chains.

**Apply:** short batches with automatic interruption. **Improve for WinBrow:**
URL equality is insufficient; same-URL navigation, rerendered forms, dialogs and
replaced targets must also invalidate the remaining assumptions. Do not add
Browser Use or replace raw CDP to adopt this pattern.

### B. Multiple calls per response and parallel execution are separate choices

[OpenAI's function-calling guide][3] supports multiple calls in a model response
and application-side handling of each result. It also recommends combining
functions that are always called in sequence and moving deterministic work out
of the model.

**Apply:** retain the existing provider-neutral `steps[]` representation. The
executor, not a model-supplied claim of independence, decides whether execution
is sequential or concurrent. Native provider tool calling is optional, not a
prerequisite for this project.

### C. Code can orchestrate repetitive work without another inference

[Anthropic's programmatic tool-calling documentation][4] describes loops,
conditionals, filtering and multiple calls without sampling the model between
operations. It also notes that small or reasoning-dependent sequences may not
benefit, and that its managed computer/browser toolsets are not programmatic
call targets.

**Apply the architectural idea, not the hosted product:** use a constrained,
local action list now; consider bounded declarative loops later. Do not give
arbitrary generated Python/JavaScript/PowerShell direct access to browser atoms
or bypass `run_skill()`. No new provider, remote code container or data-sharing
arrangement is required.

### D. Plan independent work together; honor actual dependencies

[LLMCompiler, ICML 2024][5], separates planning, dependency-aware dispatch and
execution; it reports up to 3.7× latency improvement on its evaluated function-
calling tasks. [ReWOO][6] similarly separates reasoning from tool observation
and reports token-efficiency gains on NLP benchmarks.

**Apply:** identify already-known inputs and decision boundaries. Do not plan
“search, then click an unknown result” as a blind batch. A general dependency
DAG is unnecessary for the first general-purpose sequential executor. A data
dependency does not automatically require another model turn: known paths and
explicit deterministic bindings can be handled locally.

### E. State-setting actions are safer than blind toggles

[Playwright's input guide][7] uses `setChecked`/`check` semantics, while its
[actionability guide][8] checks uniqueness, visibility, stability, event
reception and enabled state before interaction.

**Apply these semantics through existing CDP**, without adding Playwright.
Observe checkbox state, click only if needed, and verify the requested state.
A DOM property assignment alone is not proof that a framework accepted a change.

## 3. Target execution model

```text
Observe task context, known inputs and relevant resource identities
    ↓
Brain proposes a bounded steps[] group, possibly using different tools
    ↓
Validate tool contracts, arguments, dependencies and authorization scope
    ↓
Execute the next eligible segment:
  sequential by default; bounded parallelism only for safe independent calls
  acquire and revalidate the resources required by that segment
  dispatch every executable member through run_skill()
  verify its outcome using the tool's deterministic contract
  record results, progress and the next execution index
    ↓
At a reasoning boundary: return fresh evidence to the brain
At an approval boundary: pause and resume the exact authorized member
At failure/uncertainty: discard unsafe queued work and replan
    ↓
Finish only when task-specific evidence confirms the goal
```

An expected state change does not itself require a model turn. Creating a known
folder, focusing a known window, or changing a form field can be verified
locally, allowing the next already-specified command to proceed. Unexpected
navigation, a replaced target, an ambiguous file match or an unplanned dialog
invalidates the assumptions behind affected commands.

### Eligibility, not task-specific exceptions

A sequence is batchable when each command has a known or safely resolvable
input, the preceding outcomes can be checked deterministically, permissions are
preserved, and no intermediate choice requires the model. Similarity is neither
necessary nor sufficient: three different tools can form a safe batch, whereas
three identical clicks may be unsafe.

| Execution policy              | When to use it                                                                 | Examples                                                                                                                                |
| ----------------------------- | ------------------------------------------------------------------------------ | --------------------------------------------------------------------------------------------------------------------------------------- |
| Ordered batch                 | Commands are fully specified; effects/dependencies are locally checkable.      | Create a known directory → write known content → verify; fill observed fields; reviewed desktop focus → type → verify.                  |
| Independent parallel group    | Inputs are known, contracts permit concurrency, and resources do not conflict. | Fetch several known URLs; read independent documents.                                                                                   |
| Observation/reasoning barrier | A new observation must be interpreted or an input/target is unresolved.        | Search → let brain choose the result; navigate → inspect unseen controls; open an unknown file dialog.                                  |
| Approval barrier              | A member needs authorization.                                                  | Pause before a gated file write, message, upload or destructive action; resume only that exact authorized operation after revalidation. |

A model may describe a longer goal, but executable commands must not guess
unseen selectors, undiscovered paths or future user choices. In the first
release, restrict emitted executable steps to known arguments. Add explicit,
validated result bindings later, without treating arbitrary tool text as code.

### Trusted tool execution contracts

The current `Tool` dataclass (`winbrow/registry.py:36–46`) has no batching,
resource, retry or verification metadata. Add a small backend-owned policy
record associated with each registered tool; do not infer safety from a name or
a model-supplied `parallel=true`. Proposed fields, not current runtime APIs:

- **Effect/scope:** read, reversible mutation, external write, destructive;
  retain content-sensitive tiering and target/user scope, not just a static tier.
- **Resources:** browser session/document, foreground desktop/clipboard,
  canonical file paths, or API account/record; lock conflicts appropriately.
- **Inputs/dependencies:** required arguments, expected prior outcomes, and
  whether unresolved input requires replanning.
- **Verification:** what proves the result, whether an integrated check suffices,
  and when an observation or model review is required.
- **Retry behavior:** idempotent/no-op, reconcile-before-retry, or never replay
  automatically. Dispatch acknowledgement is not completion evidence.
- **Batch behavior:** ordered-safe, parallel-read-safe, or a barrier until the
  tool has a reviewed contract. Unknown/learned/MCP tools start conservative,
  but can become eligible through reviewed metadata rather than a new scheduler.

Keep batch eligibility separate from permission tier. Generic browser clicks
and uploads are currently T1 even when their semantic effects are consequential;
a T1 label is not sufficient evidence of safe batching. User authorization and
trusted operation policy must cover the actual effect. Page labels, external
tool descriptions and model intent are not authorization.

This framework supports all task categories, but does not promise that every
existing opaque tool can safely batch on day one. Missing capabilities receive
an explicit barrier/fallback and can be added incrementally.

## 4. Revised implementation plan — generic engine first

The earlier checkbox-first rollout is superseded by the user's scope
clarification. Build the common mechanism first and validate it across multiple
task families. Domain-specific improvements must plug into it, not define it.

### Phase 0 — Cross-domain baselines

**Files:** existing brain telemetry, tests under `winbrow/tests/`, temporary file
fixtures and local HTML under the existing `fixtures/` directory.

- Measure model requests/tokens, action/observation time and verified completion.
- Build representative cases for web/document reads, known-path file workflows,
  browser form changes, reviewed desktop sequences and mocked MCP/API calls.
- Include different-tool ordered sequences and read-after-write verification,
  not just repeated calls to the same tool.
- Include failure, unresolved input, approval after partial progress, resource
  contention and non-idempotent side effects. Use temporary data and scripted
  gateways; do not mutate the user's real files or settings.
- Preserve single-action behavior as the comparison and rollback path.

**Exit:** reproducible multi-domain fixtures, including which segments can run
without another model decision.

### Phase 1 — General planner and tool contracts

**Files:** `winbrow/registry.py`, `winbrow/brain/prompt.py`,
`winbrow/brain/agent_loop.py`, relevant tool definitions and tests.

- Define backend-owned execution policy records for representative tools from
  multiple domains. Start with a small record, not a general effect-inference
  framework. A policy registry can avoid modifying unrelated dispatchers.
- Make `steps[]` a first-class output, retaining single `step` compatibility.
  Start with a configurable three-command rollout cap and evaluate five. A
  rollout setting is proposed here, not an existing environment variable.
- Validate the complete array, required args, tool availability, contracts and
  budget before side effects. Reject ambiguous simultaneous `step`/`steps` and
  oversized or malformed proposals rather than silently dropping commands.
- Replace all contradictory one-action prompt rules. Teach: batch the longest
  useful eligible prefix, allow different tools and ordered dependencies, never
  guess unknown inputs, and keep single-step mode when a real decision is next.
- Make usage instructions available for every chosen tool before the model
  plans its executable segment. Current first-member-only, next-turn disclosure
  is insufficient for mixed-tool batches. Keep pure playbook/meta loaders as
  planning barriers; do not execute undisclosed follow-on instructions blindly.
- Preserve scope filtering, subagent restrictions and local argument validation;
  JSON schema in non-strict gateway mode is not the enforcement boundary.

**Exit:** the planner can propose bounded, heterogeneous batches and the backend
can explain which operations are eligible, sequential, parallel or barriers.

### Phase 2 — Generic guarded executor and exact permission continuation

**Files:** `winbrow/brain/agent_loop.py`, `winbrow/agent.py`,
`winbrow/permissions.py`, `server.py`, resource ownership/lifecycle code and tests.

- Extend the current loop over `steps[]`; do not create an arbitrary-code or
  nested batch wrapper that dispatches atoms outside `run_skill()`.
- Execute heterogeneous commands sequentially by default, including mixed reads
  and writes when their contracts/dependencies permit. A read after a write is
  often verification, not a reason to forbid the batch. Keep the existing
  independent-read concurrency flag separate from general batch eligibility.
- Acquire resources for each execution segment in a consistent order and
  revalidate assumptions after any wait. Use file/account scope for non-UI
  tools, not a single unnecessary global lock. Browser lifecycle changes and
  all foreground writers (computer tools, adapters, shortcuts and OS fallbacks)
  must honor shared UI ownership or defer conflicting work.
- Bind browser targets to the observed tab/document/frame and control identity;
  bind desktop work to the intended window. File workflows validate path and
  overwrite assumptions. API workflows validate account/record scope. Expected
  transitions can continue; unexpected transitions invalidate queued work.
- Before each executable member, check cancellation and call the normal
  permission gate through `_run_step()` → `run_skill()`. A batch is never a
  blanket approval. T2/T3 members can be supported through exact pauses, not
  excluded forever because they belong to a write-capable task family.
- Implement a scoped execution cursor: run/session/batch ID, immutable proposed
  commands, completed outcomes, next index, exact pending member, expiry and
  relevant resource identity. Bind approval to full canonical arguments and
  target/session scope, not existing lowercased/truncated action keys.
- Unify REST/chat/WebSocket confirmation around that cursor. On approval,
  reacquire resources, revalidate the pending member, use its gate approval and
  continue only the unexecuted suffix. Never restart the utterance. Every T3
  operation still requires a fresh one-shot approval. Denial, expiry or changed
  args/targets must not execute the suffix. If safe continuation is unavailable,
  return recovery-required rather than replaying completed work.
- Release resources during human approval. Include **batch → later singleton
  approval** in the same continuation policy, not only pauses inside arrays.
- Keep per-member tool events, history, error handling and action-budget charges.
  Add batch/turn IDs, ordinal progress and explicit not-executed outcomes.
  Stop affected queued work on failure, uncertain outcome, timeout, denial,
  cancellation or an unresolved model decision. Preserve evidence; no rollback
  or exactly-once-across-crashes claim.
- Require verification appropriate to each tool. Integrated native checks can
  suffice; registered read/verification tools still use the dispatch gate.
  Keep full observations initially where lightweight evidence is not ready.
  Extend `_completion_gap()` to reject unverified requested effects across
  domains, not merely count successful dispatches.

**Exit:** one planner response drives verified multi-tool sequences across
multiple task families; approvals resume safely and resource conflicts cannot
interleave shared-state mutations.

### Phase 3 — Domain adapters, observation efficiency and deterministic bindings

**Files:** existing browser/computer/file/document/MCP handlers as applicable,
`winbrow/utils/history.py`, loop result models, telemetry and tests.

- Add reviewed policy records and verifiers for more tools without modifying the
  scheduling algorithm. Audit unknown/learned/MCP tools before enabling their
  ordered or parallel capabilities; external descriptions are not trusted policy.
- Prefer desired-state operations where useful: replace text, ensure checked,
  ensure a directory exists. For the checkbox example, add checked-state
  observation and a verified state-setting primitive through the normal registry,
  permission and skill-definition path. This is an adapter improvement, not the
  foundation or limit of multi-action emission.
- Resolve browser text input's OS-paste-plus-Enter fallback before marking it
  safe for unattended batches (`browser_task.py:1999–2020`). Apply equivalent
  focus, overwrite and uncertain-side-effect checks in other domains.
- Allow audited navigation, uploads and external writes according to their
  contracts and authorization, not blanket task bans. Navigation to unknown
  controls remains a reasoning barrier; known transitions with deterministic
  evidence can continue. Sending/purchasing/deleting never gains authorization
  just because it is listed after safe steps.
- Add explicit result references only for trusted structured output fields:
  validate provenance/type and resolve before the next member's gate. No eval,
  implicit shell interpolation or model-guessed output values. A semantic choice
  among results still returns to the brain. A full DAG engine is optional later.
- Once correct, use targeted local checks and consolidated observations rather
  than repeated full snapshots/sleeps. Preserve domain-specific evidence in
  compact batch history, full diagnostics outside the prompt and every failure.
- Distinguish model-turn, action, concurrency and wall-clock budgets; neither
  a batch nor a compound tool may bypass execution limits. Adapt batch size to
  observed interruptions and verification confidence, within a fixed hard cap.

**Exit:** broader tools use the same batching infrastructure, with measured
latency savings and no loss of completion evidence or authorization.

### Phase 4 — Reuse repeated workflows across requests

**Files:** existing `winbrow/memory/skills.py`, brain skill registry/writer and
brain-first orchestration, with approval and continuation tests.

- Keep reusable skill guidance and procedural replay distinct. Brain-first
  currently skips legacy replay; offer approved parameterized workflow candidates
  within that path instead of introducing an unconditional pre-brain shortcut.
- Bind new values once, verify current preconditions, then use the same generic
  executor, resources, verifiers and permission continuation from Phase 2.
- Store semantic targets/expected states rather than stale browser IDs,
  coordinates, file assumptions or approval grants. A successful trace is not
  automatically trusted for future autonomous execution.
- Add bounded declarative repetition when measured demand warrants it. Every
  expanded action still consumes budget and passes the gate. Reconcile unknown
  effects before retry; expire unrecoverable cursors safely.
- Defer arbitrary code execution and a general DAG scheduler unless they offer
  a measured advantage over bounded ordered sequences and explicit bindings.

**Exit:** similar browser, desktop, file, document and API workflows reuse
validated execution structure without stale-state replay or weakened approvals.

## 5. Examples across task types

| Task      | Work that can share one planner response                                            | Where another decision is needed                                                    |
| --------- | ----------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------- |
| Research  | Fetch several already-known source URLs and read a known local document.            | Choose new sources or synthesize findings after reading results.                    |
| Files     | Create a known output directory, write supplied content to a known path, verify it. | Ambiguous destination, overwrite conflict or unexpected existing content.           |
| Browser   | Fill several observed fields, select known options, set checkbox states.            | Unseen page/controls, conditional fields requiring interpretation, changed targets. |
| Desktop   | Focus a known window, enter known text, invoke a reviewed shortcut, verify.         | Unexpected foreground window or dialog; save destination is unresolved.             |
| Documents | Execute specified operations on known input/output paths; verify artifacts.         | Decide a layout from new content, repair an unexpected export failure.              |
| MCP/API   | Run known read queries or explicitly authorized operations on known records.        | Select among ambiguous records, approve a write, interpret a conflict response.     |

Illustrative heterogeneous batch using existing tool names and known inputs;
the local document path is an example, not an instruction to access a real file:

```json
{
  "kind": "action",
  "steps": [
    {
      "skill": "web_fetch",
      "args": { "url": "https://proceedings.mlr.press/v235/kim24y.html" }
    },
    {
      "skill": "read_document",
      "args": { "path": "D:\\Reports\\requirements.txt" }
    },
    {
      "skill": "web_fetch",
      "args": {
        "url": "https://docs.browser-use.com/open-source/customize/agent/all-parameters"
      }
    }
  ]
}
```

These reads may run concurrently under reviewed contracts. In contrast, writing
and then reading the same file is an ordered dependency that can still share a
planner turn when both arguments and verification expectations are known.
Browser/desktop mutations also remain ordered even when emitted together.

For ten eligible commands, a five-command cap can reduce action-planning turns
from ten to two, plus common setup and finalization. If a dependency requires
new reasoning, return to the brain sooner. “All in one go” means no unnecessary
intervening model inference, not atomic execution or permission bypass.

## 6. Measurement and release gates

Let `N` be actions, `K` batch size, `Q=ceil(N/K)`, `L` model latency, `A` action
cost, `O` full-observation cost and `G` local guard/postcondition cost:

```text
One action per turn:       approximately N × (L + A + O)
MVP, full reads retained:  approximately Q × L + N × (A + O + G)
Optimized observation:     approximately Q × (L + O) + N × (A + G)
```

Model latency/output size changes with batch size, and retries reduce savings;
these are planning approximations, excluding common setup/finalization costs.
For illustration only, with ten actions, `K=5`, `L=3s`, `A=0.2s`, `O=0.8s` and
`G=0.05s`, estimates are 40s single-step, 16.5s MVP and 10.1s optimized. These
numbers are **not measurements or performance promises**.

Record p50/p95 wall-clock time, model requests/tokens, completed actions per
request, observation time, batch interruption reasons, wrong-target changes,
retries, cancellation behavior and independently verified task completion.
Use paired runs on identical fixtures/models and include dynamic/negative
cases; report sample sizes and uncertainty rather than only successful demos.

Proposed release gates:

- Ten fully specified commands: at least 60% fewer action-planning requests
  at cap three (four instead of ten), excluding common setup/finalization;
  measure this across read-heavy and ordered-mutation task families, not only
  checkbox fixtures.
- Zero permission bypasses, executed unapproved members, unintended submits or
  stale-target continuation in deterministic safety fixtures.
- No task-completion regression on paired cross-domain fixture suites; include
  heterogeneous/read-after-write sequences and expected transitions. Expand
  measured live evaluation before general rollout.
- Cancellation stops before the next member. An in-flight side effect is
  reported honestly, not described as rolled back; bound local polling time.
- Flag-off single-step behavior and existing parallel-read behavior stay intact.
- Real CDP/UIA and domain-specific integration smoke are required before
  enabling their paths by default. Mocked `pytest` alone is not proof of
  browser, desktop, filesystem or remote-service runtime reliability.

### Required regression cases

1. Heterogeneous batches, same-tool repetition and known-input dependencies:
   ordered write → read, directory → file, browser and reviewed desktop actions.
2. Resource conflicts: same file/account/browser/foreground versus independent
   paths/reads; competing sessions and subagents; no concurrent UI mutations.
3. Expected transitions continue without a model call; ambiguous results,
   unknown selectors and unexpected dialogs trigger a real reasoning barrier.
4. Failure/timeout/cancellation after partial progress preserves evidence and
   prevents unsafe suffix execution. Post-mutation read failure is uncertain,
   not permission to replay an irreversible effect.
5. Invalid/oversized proposals, conflicting same-target states, exhausted action
   budget, unknown tool contracts and malformed JSON. Valid mixed tools and
   read/write arrays must not be rejected merely for being heterogeneous.
6. Exact T2/T3 pause/resume, denial, expiry, argument/target/session isolation,
   fresh one-shot T3 approval, no whole-goal replay and **batch → later singleton
   approval**, through every confirmation channel. Safe recovery if state is lost.
7. Browser target replacement/same-URL reload, checkbox toggle state, desktop
   focus, file overwrite conflict and API record-version mismatch.
8. All members' usage instructions are available; allow/scope filtering remains
   enforced; tool output cannot change the execution policy or authorize effects.
9. Verification evidence survives history compression; `done` is rejected when
   effects are unverified. Existing read concurrency and repeat recovery remain.
10. Later result bindings: type/provenance checks, no missing-field substitution,
    no code evaluation, and resolved arguments gated before execution.

## 7. Implementation record (2026-11-01)

**Shipped first slice — Phases 0–2.** Runtime code now implements shared
backend-owned contracts, bounded heterogeneous `steps[]`, a guarded sequential
executor and exact approval continuation.

| Surface | Implementation |
| --- | --- |
| Tool/execution contracts | `winbrow/brain/batching.py`: immutable `BatchPolicy` records keyed by exact tool name + dispatcher impl; `ordered`/`parallel`/`barrier_after`/`resource`/`reason`. Unknown, learned, script, MCP and shell tools default to singleton barriers. `WINBROW_MAX_ACTIONS_PER_TURN` default 5, clamp 1–10. |
| Planner schema/prompt | `winbrow/brain/prompt.py`: `step` + bounded `steps[]`, live per-turn cap, no truncation, mixed known-input dependencies and read-after-write documented. Contradictory one-action/read-only rules removed. BATCH TOOL CONTRACTS are injected for every ordered tool, so mixed-tool batches do not wait for first-member-only disclosure. |
| Preflight | `validate_steps()` validates the complete array (shape, args/defaults/enums, availability, subagent scope, result-reference rejection, duplicate mutations, budget) before any side effect; `step`/`steps` conflicts and oversized arrays are rejected, never clipped. |
| Execution | `winbrow/brain/agent_loop.py`: per-member `run_skill()` gate, `asyncio.sleep(0)` cancellation boundary, sequential default, existing `WINBROW_PARALLEL_READS` concurrency still limited to reviewed independent reads, batch IDs/ordinals/unexecuted members in `batches`. Failures, timeouts, denial and uncertain outcomes stop the suffix. |
| Shared UI ownership | `winbrow/execution.py`: a `ContextVar` lease serialises top-level goals while awaited children/subagents inherit it. `execute()`, `confirm_pending()` and direct `/api/browser` actions acquire it; approval releases it while waiting. Child subagent brains receive the same browser guard but keep their scoped registries. |
| Browser guard | `BrowserController.batch_state()` (`winbrow/browser_task.py`) pins the remembered agent tab and a per-document token, and returns selector signatures without mutable values/checked state. `WinBrowAgent._guard_batch()` requires one connected, visible, enabled target before the batch and revalidates identity/targets after each member. Same-URL reload, navigation, replaced targets and dialogs stop queued work. |
| Desktop guard | No reviewed window-state guard yet, so desktop batches return a replan boundary and execute one action at a time. Reviewed desktop `BatchPolicy` records still make them eligible for ordered single-action planning. |
| Permission continuation | `winbrow/permissions.py`: scoped `permission_scope`, canonical full-argument `v2:` action keys, atomic approved-record consumption before dispatch, exact pending lookup by session/ID/args, TTL pruning and one-shot T3. `WinBrowAgent.confirm_pending()` resumes only the saved unexecuted suffix; REST, WebSocket and chat "yes" share it. Denial/expiry/session mismatch discards the cursor; lost state returns recovery-required instead of replaying the goal. Legacy non-brain pendings keep single-action replay. |
| Telemetry/history | Per-member `brain_step` events, `brain_plan` token/cache/parse metrics retained, `brain_batch_rejected`, and `BrainResult.batches` with planned/attempted/unexecuted/stop_reason. |

**Verification (this implementation session):**

- `python -m pytest winbrow/tests -q` → **598 passed, 2 skipped**
  (scripted/mocked planner, browser-state and permission paths).
- `python -m pytest test_brain_m0.py -q` → **50 passed** (including oversized
  batch rejection and multi-step loop mechanics).
- `python -m pytest winbrow/tests/test_batch_policy.py test_batch_execution.py test_browser_batch_guard.py test_permission_scopes.py -q`
  → **309 passed** (contracts, preflight, guard, negotiation, continuation).
- No live provider model call, real CDP/UIA session, website form submission or
  performance benchmark was run. The `__init__` browser guard tests use a
  mocked controller; the JS fragment has Node-based tests only.
- Unrelated pre-existing failures remain in legacy root suites when the local
  `.env` supplies a live provider (for example route-tier assertions expecting
  `mcp_shortcut`/`browser_brain`). They are not caused by this change and were
  reproduced at HEAD without the batching code.

**Known remaining barriers (Phase 3+):** no reviewed desktop window-guard,
file/account-scope lock metadata, result bindings, checkbox desired-state
primitive, custom MCP contracts, or measured live latency benchmark. These are
explicit singleton/observation boundaries in the current executor, not silent
gaps. Unknown tools remain executable as singletons but cannot join a batch
until a reviewed `BatchPolicy` is added.

## 8. Research validation history

- Source review of planner/schema, execution, browser state/actions, permission
  gate/confirmation and history; independent read-only review of UI constraints.
- Original research turn: `python -m pytest winbrow/tests/test_parallel_reads.py winbrow/tests/test_loop_recovery.py -q`
  → **9 passed in 25.66s**, using scripted/mocked execution.
- Scope-clarification revision checked the registry contract and revised this
  plan, knowledge summary and task memory; no runtime code existed then.
- No live provider, CDP, UIA, website form or performance benchmark was run for
  the research phase.

**Scope note:** the recommended first slice (Phases 0–2) is the implemented
scope. Checkbox state is one Phase 3 adapter and was not used to define batch
eligibility. A measured live evaluation is still required before broad rollout.

## Sources

[1]: https://docs.browser-use.com/open-source/customize/agent/all-parameters
[2]: https://github.com/browser-use/browser-use/blob/d19ec6ef/tests/ci/test_multi_act_guards.py
[3]: https://developers.openai.com/api/docs/guides/function-calling
[4]: https://platform.claude.com/docs/en/agents-and-tools/tool-use/programmatic-tool-calling
[5]: https://proceedings.mlr.press/v235/kim24y.html
[6]: https://arxiv.org/html/2305.18323v1
[7]: https://playwright.dev/docs/input
[8]: https://playwright.dev/docs/actionability
