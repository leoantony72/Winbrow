import { useEffect, useMemo, useRef, useState } from "react";
import type { AgentState } from "./lib/useAgent";
import Server from "./Server";
import Settings from "./Settings";
import Trace from "./Trace";
import CopyButton from "./components/CopyButton";
import { SERVER_HTTP } from "./lib/agent";
import { elapsed, relativeTime, shortTime, argHint } from "./lib/format";
import {
  ArrowUp,
  ArrowUpRight,
  AudioLines,
  Files,
  Globe2,
  MessageSquare,
  Minus,
  Plus,
  ScanText,
  Settings as SettingsIcon,
  Sparkles,
  Square,
  TerminalSquare,
  X,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";

const EXAMPLES = [
  {
    title: "Research the web",
    detail: "Find answers, not more tabs",
    prompt:
      "Research the latest developments in renewable energy and summarize with sources",
    icon: Globe2,
  },
  {
    title: "Work with files",
    detail: "Find the details that matter",
    prompt: "Find the latest invoice on my Desktop and summarize it",
    icon: Files,
  },
  {
    title: "Create a document",
    detail: "Turn a thought into a first draft",
    prompt: "Create a short document explaining practical uses of AI",
    icon: ScanText,
  },
  {
    title: "Compare & analyze",
    detail: "Make sense of the differences",
    prompt: "Help me find and compare two PDFs, then list the differences",
    icon: Sparkles,
  },
];

function StatusText({ status }: { status: string }) {
  const label =
    status === "completed"
      ? "done"
      : status === "cancelled"
        ? "stopped"
        : status === "needs_input"
          ? "needs input"
          : status;
  return <span className={`status-text status-${status}`}>{label}</span>;
}

function getSuggestedFollowups(task?: any): string[] {
  if (!task || task.status !== "completed") return [];
  const suggestions: string[] = [];
  const goalLower = (task.goal || "").toLowerCase();
  const answerLower = (task.answer || "").toLowerCase();

  if (
    goalLower.includes("file") ||
    goalLower.includes("pdf") ||
    goalLower.includes("doc") ||
    answerLower.includes(".pdf") ||
    answerLower.includes(".rtf") ||
    answerLower.includes(".txt") ||
    answerLower.includes(".html")
  ) {
    suggestions.push("Open the output file");
    suggestions.push("Where was it saved?");
  }
  if (
    goalLower.includes("search") ||
    goalLower.includes("find") ||
    goalLower.includes("summarize") ||
    goalLower.includes("weather")
  ) {
    suggestions.push("Tell me more details");
    suggestions.push("Summarize in 3 bullet points");
  }
  if (suggestions.length < 2) {
    suggestions.push("Explain what you did step by step");
    suggestions.push("What else can you do?");
  }
  return suggestions.slice(0, 4);
}

export default function Dashboard({ agent }: { agent: AgentState }) {
  const [draft, setDraft] = useState("");
  const [rawReasoning, setRawReasoning] = useState(
    () => localStorage.getItem("winbrow.raw") === "1",
  );
  const [sidecar, setSidecar] = useState("online");
  const [voice, setVoice] = useState({
    running: false,
    mode: "",
    muted: false,
  });
  const [view, setView] = useState<"tasks" | "server" | "settings">(() =>
    window.location.hash === "#server" || window.location.hash === "#connection"
      ? "server"
      : window.location.hash === "#settings"
        ? "settings"
        : "tasks",
  );
  const scrollRef = useRef<HTMLDivElement>(null);
  const composerRef = useRef<HTMLTextAreaElement>(null);
  const api = window.winbrow;

  const currentSession = agent.activeSession;
  const turns = agent.activeTasks;
  const latestTurn = turns.length > 0 ? turns[turns.length - 1] : agent.active;
  const running = latestTurn?.status === "running";

  const parentTask = useMemo(() => {
    const parentId = latestTurn?.parentId;
    if (!parentId) return null;
    const local = agent.tasks[parentId];
    if (local) return { id: parentId, goal: local.goal || "(untitled task)" };
    const remote = agent.remote.find((task) => task.id === parentId);
    return { id: parentId, goal: remote?.goal || parentId };
  }, [latestTurn?.parentId, agent.tasks, agent.remote]);

  useEffect(() => {
    if (!api?.onMainEvent) return;
    return api.onMainEvent("sidecar:status", (state) =>
      setSidecar(String(state)),
    );
  }, [api]);

  useEffect(() => {
    if (!api?.onMainEvent) return;
    return api.onMainEvent("main:show-server", () => setView("server"));
  }, [api]);

  useEffect(() => {
    if (agent.demo) return;
    let alive = true;
    const load = () => {
      fetch(`${SERVER_HTTP}/api/voice`)
        .then((response) => (response.ok ? response.json() : null))
        .then((data) => {
          if (alive && data) setVoice(data);
        })
        .catch(() => {});
    };
    load();
    const timer = window.setInterval(load, 4000);
    return () => {
      alive = false;
      window.clearInterval(timer);
    };
  }, [agent.demo]);

  const toggleVoice = () => {
    fetch(`${SERVER_HTTP}/api/voice/toggle`, { method: "POST" })
      .then((response) => (response.ok ? response.json() : null))
      .then((data) => data && setVoice(data))
      .catch(() => {});
  };

  useEffect(() => {
    if (view === "tasks") composerRef.current?.focus();
  }, [view, agent.activeSessionId]);

  useEffect(() => {
    const node = scrollRef.current;
    if (!node || turns.length === 0) return;
    node.scrollTop = node.scrollHeight;
  }, [
    agent.activeSessionId,
    turns.length,
    latestTurn?.updatedAt,
    latestTurn?.answer?.length,
  ]);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape" && running) {
        event.preventDefault();
        agent.cancel();
      }
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setView("tasks");
        agent.newChat();
        composerRef.current?.focus();
      }
      if ((event.ctrlKey || event.metaKey) && event.key === "Enter") {
        event.preventDefault();
        setView("tasks");
        submit();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

  const chatItems = useMemo(() => {
    return (
      agent.sessionOrder
        .map((id) => agent.sessions[id])
        .filter((s): s is NonNullable<typeof s> => Boolean(s))
        // A freshly created chat is a local placeholder until its first message
        // creates a task; keep it while active, but don't leave it in the rail
        // after the user moves back to an existing conversation.
        .filter(
          (s) =>
            s.id === agent.activeSessionId ||
            (s.taskCount ?? 0) > 0 ||
            s.status === "running",
        )
    );
  }, [agent.sessionOrder, agent.sessions, agent.activeSessionId]);

  function submit(overrideText?: string): void {
    const text = (overrideText ?? draft).trim();
    if (!text || running || agent.connection !== "online") return;
    const parent = latestTurn && !latestTurn.live ? latestTurn.id : "";
    agent.run(text, parent);
    setDraft("");
  }

  function handleOption(option: string, taskId?: string): void {
    agent.run(option, taskId || latestTurn?.id || "");
  }

  function toggleRaw(): void {
    setRawReasoning((value) => {
      localStorage.setItem("winbrow.raw", value ? "0" : "1");
      return !value;
    });
  }

  const liveLabel =
    agent.connection === "online" ? "connected" : agent.connection;

  return (
    <div className="app">
      <header className="titlebar">
        <div className="brand">
          <span className="brand-mark">
            <AudioLines size={19} aria-hidden />
          </span>
          <span className="brand-name">WinBrow</span>
          <span className="brand-sub">Your desktop, in flow</span>
        </div>
        <div className="view-tabs">
          <button
            className={`view-tab ${view === "tasks" ? "active" : ""}`}
            onClick={() => setView("tasks")}
          >
            <MessageSquare size={14} aria-hidden /> Chats
          </button>
          <button
            className={`view-tab ${view === "server" ? "active" : ""}`}
            onClick={() => setView("server")}
            title={`Python server activity (${liveLabel})`}
          >
            <span
              className={`dot dot-${
                agent.connection === "online"
                  ? "success"
                  : agent.connection === "offline"
                    ? "failed"
                    : "running"
              }`}
            />
            Server
          </button>
          <button
            className={`view-tab ${view === "settings" ? "active" : ""}`}
            onClick={() => setView("settings")}
            title="Environment settings"
          >
            <SettingsIcon size={14} aria-hidden /> Settings
          </button>
        </div>
        <div className="titlebar-spacer" />
        <button
          className="chip"
          onClick={toggleRaw}
          title="Show raw provider reasoning when available"
        >
          raw reasoning {rawReasoning ? "on" : "off"}
        </button>
        <div className="window-buttons">
          <button
            onClick={() => api?.minimize()}
            title="Minimize"
            aria-label="Minimize"
          >
            <Minus size={15} />
          </button>
          <button
            onClick={() => api?.maximize()}
            title="Maximize"
            aria-label="Maximize"
          >
            <Square size={12} />
          </button>
          <button
            className="close"
            onClick={() => api?.closeDashboard()}
            title="Close"
            aria-label="Close"
          >
            <X size={16} />
          </button>
        </div>
      </header>

      <div className="layout">
        <aside className="rail">
          <div className="rail-intro">
            <span className="workspace-icon">
              <TerminalSquare size={18} aria-hidden />
            </span>
            <div>
              <strong>Personal workspace</strong>
              <span>Make room for what matters</span>
            </div>
          </div>
          <div className="rail-head">
            <span>Recent chats</span>
            <button
              className="rail-new"
              onClick={() => {
                setView("tasks");
                agent.newChat();
                composerRef.current?.focus();
              }}
              title="New chat (Ctrl+K)"
              aria-label="New chat (Ctrl+K)"
            >
              <Plus size={16} aria-hidden />
            </button>
          </div>
          <div className="rail-list">
            {chatItems.length === 0 ? (
              <div className="rail-empty">No chats yet.</div>
            ) : (
              chatItems.map((item) => (
                <div
                  key={item.id}
                  className={`rail-item ${item.id === agent.activeSessionId ? "active" : ""}`}
                >
                  <button
                    className="rail-select"
                    aria-current={
                      item.id === agent.activeSessionId ? "page" : undefined
                    }
                    onClick={() => {
                      setView("tasks");
                      agent.selectSession(item.id);
                    }}
                  >
                    <span
                      className={`dot dot-${
                        item.status === "running"
                          ? "running"
                          : item.status === "needs_input"
                            ? "needs_input"
                            : item.status
                      }`}
                    />
                    <span className="rail-goal">{item.title}</span>
                    <span className="rail-meta">
                      {relativeTime(item.updatedAt || item.createdAt)}
                    </span>
                  </button>
                  <button
                    className="rail-del"
                    title="Delete chat"
                    onClick={(e) => {
                      e.stopPropagation();
                      void agent.deleteChat(item.id);
                    }}
                  >
                    <X size={13} aria-hidden />
                  </button>
                </div>
              ))
            )}
          </div>
          <div className="rail-foot">
            <div className="rail-stat">
              <span>sidecar</span>
              <button
                className="rail-link"
                onClick={() =>
                  sidecar === "online" ? agent.refresh() : api?.startSidecar()
                }
                title={sidecar === "online" ? "Refresh" : "Start the sidecar"}
              >
                {sidecar}
              </button>
            </div>
            <div className="rail-stat">
              <span>voice</span>
              <button
                className="rail-link"
                onClick={toggleVoice}
                title="Start/stop local voice"
              >
                {voice.running
                  ? voice.muted
                    ? "muted"
                    : voice.mode || "on"
                  : "off"}
              </button>
            </div>
            <div className="rail-stat">
              <span>stop</span>
              <span>Esc</span>
            </div>
          </div>
        </aside>

        <main className="main">
          {view === "settings" ? (
            <Settings />
          ) : view === "server" ? (
            <Server agent={agent} />
          ) : currentSession && turns.length > 0 ? (
            <>
              <div className="task-head">
                <div className="task-title">
                  <StatusText
                    status={
                      latestTurn?.needsInput
                        ? "needs_input"
                        : latestTurn?.status || currentSession.status
                    }
                  />
                  <h1>{currentSession.title || "(untitled chat)"}</h1>
                  {parentTask ? (
                    <button
                      className="task-parent"
                      onClick={() => agent.select(parentTask.id)}
                      title="Open parent task"
                    >
                      ↳ follow-up to {parentTask.goal}
                    </button>
                  ) : null}
                </div>
                <div className="task-meta">
                  <span>
                    {turns.length} message{turns.length === 1 ? "" : "s"}
                  </span>
                  <span>{elapsed(latestTurn || turns[0])}</span>
                  {running ? (
                    <button className="btn btn-stop" onClick={agent.cancel}>
                      Stop
                    </button>
                  ) : null}
                </div>
              </div>
              <div className="trace-scroll" ref={scrollRef}>
                {turns.map((turn) => (
                  <div key={turn.id} className="chat-turn">
                    <div className="turn-user-msg">
                      <span className="turn-user-badge">You</span>
                      <div className="turn-user-text">{turn.goal}</div>
                      <CopyButton
                        text={turn.goal}
                        title="Copy your message"
                        className="answer-copy turn-copy"
                      />
                      <span className="turn-user-meta">
                        {shortTime(turn.createdAt)}
                      </span>
                    </div>
                    <div className="turn-agent-msg">
                      <Trace
                        task={turn}
                        rawReasoning={rawReasoning}
                        onOption={(option) => handleOption(option, turn.id)}
                      />
                    </div>
                  </div>
                ))}
              </div>
            </>
          ) : (
            <div className="empty">
              <div className="welcome-emblem">
                <AudioLines size={32} strokeWidth={1.5} aria-hidden />
              </div>
              <Badge variant="outline" className="welcome-badge">
                <span
                  className={`dot dot-${agent.connection === "online" ? "success" : "running"}`}
                />{" "}
                YOUR DESKTOP COPILOT
              </Badge>
              <h1>
                Less busywork.
                <br />
                <span>More possibility.</span>
              </h1>
              <div className="empty-sub">
                A little help for your everyday. Research, create, and get
                things done
                <br className="welcome-break" /> across your desktop—with you in
                control.
              </div>
              <div className="empty-examples">
                {EXAMPLES.map((example) => (
                  <button
                    key={example.title}
                    className="example"
                    onClick={() => {
                      setDraft(example.prompt);
                      composerRef.current?.focus();
                    }}
                  >
                    <span className="example-icon">
                      <example.icon size={19} strokeWidth={1.6} aria-hidden />
                    </span>
                    <span className="example-copy">
                      <strong>{example.title}</strong>
                      <span>{example.detail}</span>
                    </span>
                    <ArrowUpRight
                      className="example-arrow"
                      size={15}
                      aria-hidden
                    />
                  </button>
                ))}
              </div>
            </div>
          )}

          {agent.confirm ? (
            <div className="confirm-bar">
              <div className="confirm-text">
                <strong>{agent.confirm.tier?.toUpperCase()}</strong>{" "}
                {agent.confirm.message || `Allow “${agent.confirm.tool}”?`}
                <span className="confirm-args">
                  {argHint(agent.confirm.args)}
                </span>
              </div>
              <button
                className="btn btn-primary"
                onClick={() => agent.respond(true)}
              >
                Allow
              </button>
              <button className="btn" onClick={() => agent.respond(false)}>
                Deny
              </button>
            </div>
          ) : null}

          {view === "tasks" ? (
            <div className={`composer ${running ? "composer-busy" : ""}`}>
              {/* Options & Follow-up ribbon */}
              {latestTurn?.needsInput &&
              latestTurn.status !== "cancelled" &&
              latestTurn.status !== "failed" &&
              latestTurn.options &&
              latestTurn.options.length > 0 ? (
                <div className="followup-options-bar">
                  <span className="followup-options-label">Choices:</span>
                  <div className="followup-options-list">
                    {latestTurn.options.map((opt, idx) => (
                      <button
                        key={`${idx}-${opt}`}
                        className="followup-option-chip"
                        onClick={() => handleOption(opt, latestTurn.id)}
                        title={opt}
                      >
                        <span className="chip-idx">{idx + 1}</span>
                        <span className="chip-text">{opt}</span>
                      </button>
                    ))}
                  </div>
                </div>
              ) : currentSession &&
                turns.length > 0 &&
                latestTurn?.status === "completed" &&
                !running ? (
                <div className="followup-options-bar">
                  <span className="followup-options-label">
                    Suggested follow-ups:
                  </span>
                  <div className="followup-options-list">
                    {getSuggestedFollowups(latestTurn).map((opt, idx) => (
                      <button
                        key={`${idx}-${opt}`}
                        className="followup-option-chip followup-suggestion"
                        onClick={() => handleOption(opt, latestTurn.id)}
                        title={opt}
                      >
                        <span className="chip-text">{opt}</span>
                      </button>
                    ))}
                  </div>
                </div>
              ) : null}

              <textarea
                aria-label="Message WinBrow"
                ref={composerRef}
                value={draft}
                rows={1}
                placeholder={
                  running
                    ? "Agent is working… press Esc to stop"
                    : latestTurn?.needsInput
                      ? "Answer the question or select an option above…"
                      : currentSession && turns.length > 0
                        ? "Ask a follow-up or give the next instruction…"
                        : "Ask WinBrow to do something…"
                }
                onChange={(event) => setDraft(event.target.value)}
                onKeyDown={(event) => {
                  if (
                    event.key === "Enter" &&
                    !event.shiftKey &&
                    !event.nativeEvent.isComposing
                  ) {
                    event.preventDefault();
                    submit();
                  }
                }}
                onInput={(event) => {
                  const target = event.currentTarget;
                  target.style.height = "auto";
                  target.style.height = `${Math.min(target.scrollHeight, 200)}px`;
                }}
              />
              <div className="composer-actions">
                <span className="composer-hint">
                  <span className="composer-mode">
                    <Sparkles size={12} aria-hidden /> Agent
                  </span>
                  <span>Enter to send · Shift+Enter for a new line</span>
                </span>
                {running ? (
                  <button
                    className="btn btn-stop"
                    onClick={agent.cancel}
                    style={{ marginRight: 8 }}
                  >
                    Stop
                  </button>
                ) : null}
                <Button
                  className="send-button"
                  onClick={() => submit()}
                  disabled={
                    !draft.trim() || running || agent.connection !== "online"
                  }
                >
                  {currentSession && turns.length > 0 ? "Follow up" : "Send"}
                  <ArrowUp size={15} aria-hidden />
                </Button>
              </div>
            </div>
          ) : null}
          {view === "tasks" ? (
            <div className="workspace-note">
              <span
                className={`dot dot-${agent.connection === "online" ? "success" : "failed"}`}
              />
              {agent.connection === "online"
                ? "Connected to your desktop"
                : "Waiting for your desktop connection"}
              <span>Risky actions always ask for permission</span>
            </div>
          ) : null}
        </main>
      </div>
    </div>
  );
}
