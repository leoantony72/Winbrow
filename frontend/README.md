# WinBrow Desktop (Electron)

A second UI for the existing agent. The classic web UI (`http://127.0.0.1:8765/`)
is untouched; this app adds:

- **Island** — a frameless, click-through pill at the top of the screen that
  shows the live status ("Thinking…", "Searching the web…", "Editing file…"),
  the current step, and Allow/Deny cards for risky actions.
- **Dashboard** — a Claude-Code/Codex-style trace view: tasks rail, collapsible
  thinking, every tool call with input/output, streamed answer, replayable
  history from SQLite.

The Python sidecar (`server.py`) stays the single source of truth. The app only
renders typed events; it never executes tools itself.

## Run (one click)

Double-click **`desktop.bat`** in the repo root (or run `npm start` in this
folder). The app starts the Python sidecar itself if it is not already running,
so there is no second terminal to keep open.

```powershell
cd frontend
npm install          # first time only
npm start            # production build; sidecar auto-starts
```

For UI development, `npm run dev:electron` keeps Vite hot-reload on 5173 while
the app still owns the sidecar.

The sidecar health check is `http://127.0.0.1:8765/api/system`. If it cannot be
started, the island shows the error and a **Start sidecar** button, and details
go to `logs/desktop-sidecar.log`.

## UI structure and styling

The renderer already had React 18 and strict TypeScript. Tailwind CSS 3 and
shadcn-compatible configuration are now installed; no project re-scaffold is
needed. Paths resolve consistently in TypeScript, Vite, and Vitest:

- `src/components/ui/` (`@/components/ui`) — reusable shadcn primitives and
  `dynamic-island.tsx`. This is the renderer's equivalent of `/components/ui`,
  not a second folder at repository root. Keeping primitives here lets the
  shadcn CLI and copied components use the same imports.
- `src/lib/utils.ts` — `cn()` using `clsx` + `tailwind-merge`.
- `src/styles.css` — Tailwind entry, shared tokens, existing trace/island CSS.
- `src/workspace.css` — dashboard presentation and responsive layouts.
- `components.json`, `tailwind.config.cjs`, `postcss.config.cjs` — CLI and CSS
  configuration. Tailwind Preflight is disabled deliberately so its reset
  cannot break existing Electron controls and Markdown rendering.

For future shadcn components, run `npx shadcn@latest add <component>` from
`frontend/`; do not run `init` over the configured app. To restore dependencies,
use `npm ci`. Icons use `lucide-react`; no remote images or fonts are required,
so the desktop UI does not depend on an image CDN or send requests to Unsplash.

The supplied dynamic-island provider now renders the real overlay, using
explicit widths (196/404/460px) and content-driven height so permission and
control cards are not clipped by demo preset heights. Animation queues are
cancellable and support returning to a previous size. Reduced motion is honored.

The independent component showcase is available with `?win=component-demo`.
It does not connect to the automation sidecar. The other `?demo=` previews below
continue to use the existing task-state fixtures.

## UI verification

```powershell
npm test                # renderer regression tests; no live tools run
npm run build           # strict TypeScript + production Vite bundle
npm run test:electron   # built renderer smoke check; run after build
```

The Electron smoke check never starts the sidecar. It checks desktop and narrow
layouts, result rendering, Server navigation, expanded/collapsed island states,
and the component showcase. Screenshots go to `logs/ui-smoke/` at repository
root. UI tests cover send/newline, example prompts, chat selection/deletion,
follow-ups, approval/denial, cancellation, voice actions, window actions, and
animation lifecycle. These are not evidence of live CDP/UIA/voice execution.

Dependency check on 2026-11-01: `npm audit --omit=dev` reported zero production
vulnerabilities. The full audit still reports development/toolchain advisories;
no breaking Electron/build-tool upgrades were applied as part of this UI change.

## Build / package

```powershell
cd frontend
npm run build        # tsc + vite → frontend/dist
npm start            # Electron against the built bundle
npm run package      # electron-builder → frontend/release (NSIS)
```

Packaging the Python sidecar is Phase 6: put a PyInstaller build at
`resources/backend/winbrow-agent.exe`; the main process prefers it when present.

## Event protocol (v2)

Every message on `/ws`:

```json
{
  "v": 2,
  "type": "tool.started",
  "task_id": "task_…",
  "step_id": "…",
  "seq": 12,
  "ts": 1712.0,
  "payload": {}
}
```

| Event                                                                | Rendered as                   |
| -------------------------------------------------------------------- | ----------------------------- |
| `task.started` / `task.completed` / `task.failed` / `task.cancelled` | task row + island state       |
| `thinking.delta` / `thinking.summary`                                | collapsible thinking block    |
| `tool.started` / `tool.result`                                       | tool card with input/output   |
| `answer.delta` / `answer.final`                                      | streamed answer               |
| `confirm.required`                                                   | island + dashboard Allow/Deny |
| `transcript.*`, `agent.speaking`, `state.changed`                    | voice / island status         |

`seq` is monotonic per task, so both windows can dedupe and the dashboard can
replay from `GET /api/tasks/{id}`. Legacy `{type: routing|result}` messages are
still accepted for older sidecars.

## Controls

| Shortcut                | Action                                               |
| ----------------------- | ---------------------------------------------------- |
| `Ctrl+Alt+Space`        | show/hide dashboard                                  |
| `Ctrl+Alt+I`            | expand/collapse island                               |
| `Ctrl+Alt+Esc`          | cancel the running task / stop control (kill switch) |
| `Ctrl+Alt+T`            | push-to-talk (one-shot capture)                      |
| `Ctrl+Alt+M`            | mute/unmute the microphone                           |
| `Ctrl+Alt+X`            | stop speaking (barge-in)                             |
| `Esc` (dashboard)       | stop the running task                                |
| `Ctrl+K`                | focus the composer                                   |
| `Enter` / `Shift+Enter` | run / newline                                        |

Island states: `idle`, `listening`, `speaking`, `thinking`, `working`,
`done`, `error`, `confirm`, `control` — one primary state at a time, chosen by
priority. Sizes: small idle pill, medium working/voice, large card. See
[`ISLAND.md`](./ISLAND.md) for the full state machine, transition table,
event contract, and non-interference guarantees.

## Results, follow-ups and choices

The task view is built to show the actual result, not just a status line:

- **Markdown results** — headings, bold, lists, tables, fenced code and links
  render properly. Long answers are selectable and have a **copy** button;
  source URLs are repeated as clickable chips.
- **Clarifying questions** — when the brain pauses with `needs_input`, the task
  switches to **needs input** and shows the question plus up to six clickable
  options (for example, three matching invoice files). Clicking an option
  continues the original goal; you can also type a custom answer.
- **Follow-ups** — after a task finishes, the composer becomes _“Ask a follow-up
  about this result…”_. Follow-ups run in the same `desktop` session, so the
  brain keeps the previous turn, artifacts and pending choice in context. The
  child task is indented with **↳** in the rail and links back to its parent.
- **Multiple cases/options** — comparisons are rendered as tables with a
  recommendation; ambiguous choices become option buttons instead of being
  collapsed into one answer.

The planner prompt also requires the final answer itself (findings, trade-offs,
recommendation, sources) for research/comparison tasks instead of a one-line
“Compared X and Y” status report.

## Server activity page

The dashboard has **Tasks** and **Server** tabs. The Server page is a live view
of what the Python sidecar is doing — the same brain stream the sidecar sends to
the UI, not connection chatter. Each prompt is its own collapsible dropdown,
stamped with its start time in **IST** and ordered oldest → newest inside:

- task start / completion / failure, with the goal
- **brain** plans (`thinking.summary`) and raw reasoning (`thinking.delta`)
- **steps**: skill, arguments, why, status, duration and output
- answers and confirmation prompts
- Python server startup/shutdown lines and sidecar errors in a final
  **Server & connection** dropdown

Live and newest prompts open automatically; older prompts stay collapsed until
clicked, and the open/closed state is preserved while new events arrive. Host-level
noise (desktop start, heartbeat pings, UI socket state, WebSocket
connect/disconnect, `/api/*` request lines) is deliberately not shown. The page
supports **All / Brain / Steps / Tasks** filters, **clear** (view only), and
**Restart server** for the app-managed process. Recent runs are replayed from
`/api/tasks` on launch so each prompt still has its full step list before the
next task; live activity is merged with the persisted steps without duplicates.
The raw sidecar log remains `logs/desktop-sidecar.log` for deep debugging, and
the tray has a **Server activity** shortcut.

The desktop app starts the sidecar itself: it probes `/api/system`, then spawns
the packaged `winbrow-agent.exe` when present or `python -m uvicorn server:app`
in development.

## Voice

Voice is the existing local pipeline (`VoiceLoop`: VAD/wake word/push-to-talk,
Whisper, SAPI). Start it from the tray ("Voice: start / stop") or the dashboard
rail; nothing leaves the machine. `WINBROW_VOICE=1` starts it with the sidecar.

The island's **Voice on** starts the wake-word loop (`mode=vad`), shows a live
waveform from the real microphone peak, and streams partial transcripts by
re-transcribing the buffered utterance roughly once a second. Set
`WINBROW_PARTIAL_STT=0` to turn partial transcription off on slow machines.
**Push to talk** is a separate one-shot capture and works even when the
continuous loop is off. Voice errors surface in the expanded card.

## Notes

- Click-through is decided in the main process by hit-testing the real cursor
  against the island bounds (`setIgnoreMouseEvents`), so the pill never steals
  focus from the app you are typing in. The window is only focusable while the
  text input is in use.
- The idle pill is 196×36 at 84% opacity, and the window does not show over
  fullscreen workspaces.
- The window is re-anchored to the primary display on DPI/monitor changes.
- `?demo=1` renders a seeded working task for design review. Use
  `?win=island&demo=idle|listening|working|confirm|control|done|error` to pin a
  specific state, and add `&open=1` for the expanded card. `?win=dashboard`
  selects the dashboard.
