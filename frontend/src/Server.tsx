import { useEffect, useMemo, useRef, useState } from "react";
import { ChevronDown } from "lucide-react";
import type { AgentState } from "./lib/useAgent";
import CopyButton from "./components/CopyButton";
import type {
  ActivityEntry,
  ActivityKind,
  ActivityStatus,
  TaskView,
} from "./types";

const IST_TIME_ZONE = "Asia/Kolkata";
const IST_TIME = new Intl.DateTimeFormat("en-IN", {
  timeZone: IST_TIME_ZONE,
  hour12: false,
  hour: "2-digit",
  minute: "2-digit",
  second: "2-digit",
});
const IST_STAMP = new Intl.DateTimeFormat("en-IN", {
  timeZone: IST_TIME_ZONE,
  day: "2-digit",
  month: "short",
  year: "numeric",
  hour12: false,
  hour: "2-digit",
  minute: "2-digit",
  second: "2-digit",
});

function istTime(ts: number): string {
  return `${IST_TIME.format(new Date(ts))} IST`;
}

function istStamp(ts: number): string {
  return `${IST_STAMP.format(new Date(ts))} IST`;
}

function elapsedLabel(ms: number): string {
  if (!Number.isFinite(ms) || ms <= 0) return "";
  if (ms < 1000) return `${Math.round(ms)} ms`;
  if (ms < 60_000) {
    return `${(ms / 1000).toFixed(ms < 10_000 ? 1 : 0)} s`;
  }
  const minutes = Math.floor(ms / 60_000);
  const seconds = Math.round((ms % 60_000) / 1000);
  return `${minutes}m ${seconds}s`;
}

const KIND_LABEL: Record<ActivityKind, string> = {
  task: "task",
  thinking: "brain",
  step: "step",
  answer: "answer",
  confirm: "confirm",
  server: "server",
};

type Filter = "all" | "thinking" | "step" | "task";

const FILTERS: Array<{ id: Filter; label: string }> = [
  { id: "all", label: "All" },
  { id: "thinking", label: "Brain" },
  { id: "step", label: "Steps" },
  { id: "task", label: "Tasks" },
];

interface PromptGroup {
  id: string;
  taskId?: string;
  title: string;
  startedAt: number;
  updatedAt: number;
  headerTs: number;
  status: ActivityStatus;
  statusLabel: string;
  live: boolean;
  isServer: boolean;
  entries: ActivityEntry[];
}

function taskStatusActivity(status: TaskView["status"]): ActivityStatus {
  if (status === "running" || status === "queued") return "running";
  if (status === "failed") return "failed";
  if (status === "cancelled") return "info";
  return "success";
}

function stepStatusActivity(status: TaskView["steps"][number]["status"]): ActivityStatus {
  if (status === "success") return "success";
  if (status === "failed" || status === "cancelled") return "failed";
  if (status === "running") return "running";
  return "info";
}

function entryFromTask(task: TaskView, entry: ActivityEntry): ActivityEntry {
  return { ...entry, taskId: task.id };
}

/** Rebuild a prompt's log from the persisted task when live activity is absent. */
function taskEntries(task: TaskView): ActivityEntry[] {
  const startedAt = task.startedAt || task.createdAt;
  const entries: ActivityEntry[] = [
    entryFromTask(task, {
      id: `task-${task.id}-start`,
      ts: startedAt,
      kind: "task",
      status: "running",
      title: task.goal || "Task started",
      detail: "started",
    }),
  ];

  for (const block of task.thinking) {
    if (!block.text) continue;
    entries.push(
      entryFromTask(task, {
        id: `plan-${block.id}`,
        ts: block.ts ? block.ts * 1000 : startedAt,
        kind: "thinking",
        status: "info",
        title: block.kind === "raw" ? "Reasoning" : "Brain plan",
        detail: block.kind === "raw" ? "raw provider reasoning" : undefined,
        body: block.text,
      }),
    );
  }

  for (const step of task.steps) {
    const args =
      step.args && Object.keys(step.args).length
        ? JSON.stringify(step.args, null, 2)
        : "";
    entries.push(
      entryFromTask(task, {
        id: `step-${step.id}`,
        ts: step.startedAt || startedAt,
        kind: "step",
        status: stepStatusActivity(step.status),
        title: step.skill,
        detail: step.why || step.status,
        body: [args, step.output || "", step.warning ? `⚠ ${step.warning}` : ""]
          .filter(Boolean)
          .join("\n\n")
          .slice(0, 4000),
        elapsedMs: step.elapsedMs,
      }),
    );
  }

  if (task.answer) {
    entries.push(
      entryFromTask(task, {
        id: `answer-${task.id}`,
        ts: task.updatedAt,
        kind: "answer",
        status: "success",
        title: "Answer",
        body: task.answer.slice(0, 8000),
      }),
    );
  }

  if (task.status !== "running" && task.status !== "queued") {
    const status: ActivityStatus =
      task.status === "failed"
        ? "failed"
        : task.status === "cancelled"
          ? "info"
          : "success";
    const title =
      task.status === "failed"
        ? "Task failed"
        : task.status === "cancelled"
          ? "Task cancelled"
          : task.needsInput
            ? "Waiting for your answer"
            : "Task completed";
    const detail = task.error || task.summary || (task.needsInput ? task.question : "");
    entries.push(
      entryFromTask(task, {
        id: `task-${task.id}-done`,
        ts: task.updatedAt,
        kind: "task",
        status,
        title,
        detail: detail ? detail.slice(0, 160) : undefined,
        body: detail ? detail.slice(0, 8000) : undefined,
      }),
    );
  }

  return entries.sort((a, b) => a.ts - b.ts);
}

/** Keep live activity first but fill any persisted steps it did not replay. */
function mergeTaskEntries(
  liveEntries: ActivityEntry[],
  task: TaskView,
): ActivityEntry[] {
  const result = liveEntries.slice();
  const seenIds = new Set(result.map((entry) => entry.id));
  const seenBodies = new Map<ActivityKind, Set<string>>();
  for (const entry of result) {
    const set = seenBodies.get(entry.kind) || new Set<string>();
    set.add((entry.body || entry.title).trim());
    seenBodies.set(entry.kind, set);
  }

  for (const entry of taskEntries(task)) {
    if (seenIds.has(entry.id)) continue;
    // Thinking/answer events use different IDs in the live stream and the
    // persisted task, so compare their text. Steps keep ID identity only:
    // two real steps may legitimately share the same output.
    if (entry.kind === "thinking" || entry.kind === "answer") {
      const key = (entry.body || entry.title).trim();
      const bodies = seenBodies.get(entry.kind);
      if (bodies?.has(key)) continue;
      bodies?.add(key);
    }
    result.push(entry);
    seenIds.add(entry.id);
  }

  return result.sort((a, b) => a.ts - b.ts);
}

function entryCopyText(entry: ActivityEntry): string {
  return [entry.title, entry.detail, entry.body]
    .filter((part) => part && part.trim())
    .join("\n\n");
}

function promptCopyText(group: PromptGroup): string {
  const lines = [`${group.title} — ${istStamp(group.headerTs)}`];
  for (const entry of group.entries) {
    lines.push(
      `[${istTime(entry.ts)}] ${KIND_LABEL[entry.kind]}: ${entryCopyText(entry)}`,
    );
  }
  return lines.join("\n\n");
}

export default function Server({ agent }: { agent: AgentState }) {
  const [filter, setFilter] = useState<Filter>("all");
  const [openGroups, setOpenGroups] = useState<Set<string>>(() => new Set());
  const [expandedEntries, setExpandedEntries] = useState<Set<string>>(
    () => new Set(),
  );
  const initializedGroups = useRef<Set<string>>(new Set());
  const scrollRef = useRef<HTMLDivElement>(null);
  const api = window.winbrow;

  // Merge the Python side's typed brain/task events with main-process server
  // lifecycle entries, then group them under the prompt that produced them.
  const groups = useMemo<PromptGroup[]>(() => {
    const byTask = new Map<string, ActivityEntry[]>();
    const ungrouped: ActivityEntry[] = [];

    for (const entry of agent.activity) {
      if (entry.taskId) {
        const list = byTask.get(entry.taskId) || [];
        list.push(entry);
        byTask.set(entry.taskId, list);
      } else {
        ungrouped.push(entry);
      }
    }

    const connectionEntries: ActivityEntry[] = agent.connectionLog
      .filter((entry) => entry.kind !== "ping" && entry.source !== "ui")
      .filter(
        (entry) => !/^Sidecar: (WebSocket|connection)/i.test(entry.message),
      )
      .map((entry) => {
        const failed = entry.level === "error";
        return {
          id: `log-${entry.id}`,
          ts: entry.ts,
          kind: "server" as const,
          status: failed
            ? ("failed" as const)
            : entry.level === "warn"
              ? ("running" as const)
              : ("info" as const),
          title: entry.message,
          body: failed ? entry.detail : undefined,
          detail: failed ? undefined : entry.detail,
        };
      });

    const serverEntries = new Map<string, ActivityEntry>();
    for (const entry of [...ungrouped, ...connectionEntries]) {
      serverEntries.set(entry.id, entry);
    }

    const taskIds = new Set<string>([
      ...Object.keys(agent.tasks),
      ...byTask.keys(),
    ]);
    const promptGroups: PromptGroup[] = [];

    for (const taskId of taskIds) {
      const task = agent.tasks[taskId];
      const liveEntries = (byTask.get(taskId) || [])
        .slice()
        .sort((a, b) => a.ts - b.ts);
      const entries = task
        ? liveEntries.length
          ? mergeTaskEntries(liveEntries, task)
          : taskEntries(task)
        : liveEntries;
      if (!entries.length) continue;

      const startedAt =
        task?.startedAt ??
        task?.createdAt ??
        entries.find((entry) => entry.kind === "task")?.ts ??
        entries[0]?.ts ??
        Date.now();
      const updatedAt =
        task?.updatedAt ?? entries[entries.length - 1]?.ts ?? startedAt;
      const title =
        task?.goal ||
        entries.find((entry) => entry.kind === "task")?.title ||
        taskId;
      let status: ActivityStatus = task
        ? task.needsInput
          ? "running"
          : taskStatusActivity(task.status)
        : "info";
      if (!task) {
        if (entries.some((entry) => entry.status === "running")) {
          status = "running";
        } else if (entries.some((entry) => entry.status === "failed")) {
          status = "failed";
        } else if (entries.some((entry) => entry.status === "success")) {
          status = "success";
        }
      }

      promptGroups.push({
        id: `prompt-${taskId}`,
        taskId,
        title,
        startedAt,
        updatedAt,
        headerTs: startedAt,
        status,
        statusLabel: task?.needsInput ? "waiting" : task?.status || "log",
        live: task?.live ?? status === "running",
        isServer: false,
        entries,
      });
    }

    promptGroups.sort((a, b) => a.startedAt - b.startedAt);

    const serverList = [...serverEntries.values()].sort((a, b) => a.ts - b.ts);
    if (serverList.length) {
      const last = serverList[serverList.length - 1];
      const status: ActivityStatus =
        agent.connection === "offline"
          ? "failed"
          : agent.connection === "connecting"
            ? "running"
            : serverList.some((entry) => entry.status === "failed")
              ? "failed"
              : "info";
      promptGroups.push({
        id: "server-events",
        title: "Server & connection",
        startedAt: serverList[0].ts,
        updatedAt: last.ts,
        headerTs: last.ts,
        status,
        statusLabel:
          agent.connection === "online" ? "server online" : agent.connection,
        live: false,
        isServer: true,
        entries: serverList,
      });
    }

    return promptGroups;
  }, [agent.activity, agent.connection, agent.connectionLog, agent.tasks]);

  // Open a prompt the first time it appears when it is live or is the newest
  // prompt. Later user toggles are preserved.
  useEffect(() => {
    const newestPrompt = [...groups]
      .reverse()
      .find((group) => !group.isServer);
    setOpenGroups((prev) => {
      const next = new Set(prev);
      let changed = false;
      groups.forEach((group) => {
        if (initializedGroups.current.has(group.id)) return;
        initializedGroups.current.add(group.id);
        if (
          group.live ||
          group.id === newestPrompt?.id ||
          (!newestPrompt && group.isServer)
        ) {
          next.add(group.id);
          changed = true;
        }
      });
      return changed ? next : prev;
    });
  }, [groups]);

  useEffect(() => {
    const node = scrollRef.current;
    if (!node) return;
    const nearBottom =
      node.scrollHeight - node.scrollTop - node.clientHeight < 160;
    if (nearBottom) node.scrollTop = node.scrollHeight;
  }, [groups, openGroups]);

  const toggleGroup = (id: string) => {
    setOpenGroups((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const toggleEntry = (id: string) => {
    setExpandedEntries((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const visibleEntries = (group: PromptGroup) =>
    filter === "all"
      ? group.entries
      : group.entries.filter((entry) =>
          filter === "step" ? entry.kind === "step" : entry.kind === filter,
        );

  const statusClass =
    agent.connection === "online"
      ? "status-completed"
      : agent.connection === "offline"
        ? "status-failed"
        : "status-running";
  const promptCount = groups.filter((group) => !group.isServer).length;
  const stepCount = useMemo(
    () => groups.reduce(
      (count, group) =>
        count + group.entries.filter((entry) => entry.kind === "step").length,
      0,
    ),
    [groups],
  );

  return (
    <div className="activity">
      <div className="task-head connection-head">
        <div className="task-title">
          <span className={`status-text ${statusClass}`}>server</span>
          <h1>Server activity</h1>
          <div className="connection-sub">
            grouped by prompt · timestamps in IST · {promptCount} prompt
            {promptCount === 1 ? "" : "s"} · {stepCount} action
            {stepCount === 1 ? "" : "s"}
          </div>
        </div>
        <div className="connection-actions">
          <div className="activity-filters">
            {FILTERS.map((item) => (
              <button
                key={item.id}
                className={`chip ${filter === item.id ? "chip-active" : ""}`}
                onClick={() => setFilter(item.id)}
              >
                {item.label}
              </button>
            ))}
          </div>
          <button
            className="chip"
            onClick={() => {
              agent.clearActivity();
              agent.clearConnectionLog();
            }}
            title="Clear this view (the log files are kept)"
          >
            clear
          </button>
          <button
            className="btn btn-primary"
            onClick={() => api?.restartSidecar()}
            title="Stop the managed Python server and start it again"
          >
            Restart server
          </button>
        </div>
      </div>

      <div className="connection-scroll" ref={scrollRef}>
        <div className="connection-list prompt-stack">
          {groups.length === 0 ? (
            <div className="connection-empty">
              <span className="pulse" />
              No server activity yet. Start a task and each prompt will appear
              here with its brain plans and actions in order.
            </div>
          ) : (
            groups.map((group) => {
              const open = openGroups.has(group.id);
              const entries = visibleEntries(group);
              const actions = group.entries.filter(
                (entry) => entry.kind === "step",
              ).length;
              const duration = elapsedLabel(group.updatedAt - group.startedAt);
              return (
                <section
                  className={`prompt-group ${open ? "prompt-group-open" : ""}`}
                  key={group.id}
                >
                  <div className="prompt-head">
                    <button
                      type="button"
                      className="prompt-toggle"
                      onClick={() => {
                        if (window.getSelection()?.toString()) return;
                        toggleGroup(group.id);
                      }}
                      aria-expanded={open}
                    >
                      <span
                        className={`activity-dot activity-${group.status}`}
                      />
                      <span className="prompt-head-main">
                        <span className="prompt-goal">{group.title}</span>
                        <span className="prompt-meta">
                          <span className="prompt-time">
                            {istStamp(group.headerTs)}
                          </span>
                          <span>
                            {group.entries.length} event
                            {group.entries.length === 1 ? "" : "s"}
                          </span>
                          <span>
                            {actions} action{actions === 1 ? "" : "s"}
                          </span>
                          {duration ? <span>{duration}</span> : null}
                          <span className="prompt-status">
                            {group.statusLabel}
                          </span>
                        </span>
                      </span>
                      <ChevronDown
                        size={15}
                        className="prompt-caret"
                        aria-hidden
                      />
                    </button>
                    <CopyButton
                      text={promptCopyText(group)}
                      title="Copy this prompt's activity"
                      className="answer-copy prompt-copy"
                    />
                  </div>

                  {open ? (
                    <div className="prompt-log">
                      {entries.length === 0 ? (
                        <div className="prompt-empty">
                          No {filter} events for this prompt.
                        </div>
                      ) : (
                        entries.map((entry) => {
                          const long =
                            (entry.body || "").length > 180 ||
                            (entry.detail || "").length > 180;
                          const entryOpen = expandedEntries.has(entry.id);
                          return (
                            <div
                              className={`activity-row activity-kind-${entry.kind} ${
                                long ? "activity-clickable" : ""
                              } ${entryOpen ? "activity-open" : ""}`}
                              key={entry.id}
                              onClick={() => {
                                if (window.getSelection()?.toString()) return;
                                if (long) toggleEntry(entry.id);
                              }}
                              title={long ? "Click to expand" : undefined}
                            >
                              <span className="activity-time">
                                {istTime(entry.ts)}
                              </span>
                              <span
                                className={`activity-kind activity-kind-${entry.kind}`}
                              >
                                {KIND_LABEL[entry.kind]}
                              </span>
                              <span
                                className={`activity-dot activity-${entry.status}`}
                              />
                              <span className="activity-main">
                                <span className="activity-headline">
                                  <span className="activity-title">
                                    {entry.title}
                                  </span>
                                  {entry.detail ? (
                                    <span className="activity-detail">
                                      {entry.detail}
                                    </span>
                                  ) : null}
                                </span>
                                {entry.body ? (
                                  <span
                                    className={`activity-body ${
                                      entryOpen ? "activity-body-open" : ""
                                    }`}
                                  >
                                    {entry.body}
                                  </span>
                                ) : null}
                              </span>
                              <span className="activity-actions">
                                {entry.elapsedMs ? (
                                  <span className="activity-ms">
                                    {Math.round(entry.elapsedMs)} ms
                                  </span>
                                ) : null}
                                <CopyButton
                                  text={entryCopyText(entry)}
                                  title="Copy this entry"
                                  className="answer-copy activity-copy"
                                  stopPropagation
                                />
                              </span>
                            </div>
                          );
                        })
                      )}
                    </div>
                  ) : null}
                </section>
              );
            })
          )}
        </div>
      </div>
    </div>
  );
}
