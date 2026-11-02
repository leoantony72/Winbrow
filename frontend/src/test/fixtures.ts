import { vi } from "vitest";
import type { AgentState } from "../lib/useAgent";
import type { ChatSession, ConfirmRequest, TaskView } from "../types";

export function makeTask(overrides: Partial<TaskView> = {}): TaskView {
  return {
    id: "task-1",
    sessionId: "chat-1",
    goal: "Summarize the report",
    status: "completed",
    createdAt: Date.now() - 2000,
    updatedAt: Date.now(),
    thinking: [],
    steps: [],
    answer: "The report is ready.",
    live: false,
    ...overrides,
  };
}

export function makeSession(overrides: Partial<ChatSession> = {}): ChatSession {
  return {
    id: "chat-1",
    title: "Report conversation",
    createdAt: Date.now() - 2000,
    updatedAt: Date.now(),
    status: "completed",
    taskIds: ["task-1"],
    taskCount: 1,
    ...overrides,
  };
}

export function makeConfirmation(overrides: Partial<ConfirmRequest> = {}): ConfirmRequest {
  return {
    confirmationId: "confirm-1",
    tier: "t2",
    tool: "delete_file",
    args: { path: "C:\\Reports\\draft.txt" },
    message: "Delete the draft report?",
    taskId: "task-1",
    ...overrides,
  };
}

export function makeAgent(overrides: Partial<AgentState> = {}) {
  return {
    connection: "online",
    tasks: {},
    remote: [],
    sessions: {},
    sessionOrder: [],
    activeSessionId: "",
    activeSession: undefined,
    activeTasks: [],
    active: undefined,
    confirm: null,
    context: undefined,
    voice: {
      running: false, mode: "", muted: false, error: "", phase: "off",
      level: 0, partial: "", transcript: "", spoken: "", busy: false,
    },
    activity: [],
    connectionLog: [],
    ...overrides,
    run: vi.fn<AgentState["run"]>(),
    cancel: vi.fn<AgentState["cancel"]>(),
    newChat: vi.fn<AgentState["newChat"]>(),
    selectSession: vi.fn<AgentState["selectSession"]>(),
    deleteChat: vi.fn<AgentState["deleteChat"]>().mockResolvedValue(undefined),
    refresh: vi.fn<AgentState["refresh"]>().mockResolvedValue(undefined),
    select: vi.fn<AgentState["select"]>(),
    respond: vi.fn<AgentState["respond"]>().mockResolvedValue(undefined),
    refreshContext: vi.fn<AgentState["refreshContext"]>(),
    dismissConfirm: vi.fn<AgentState["dismissConfirm"]>(),
    voiceAction: vi.fn<AgentState["voiceAction"]>().mockResolvedValue(undefined),
    clearActivity: vi.fn<AgentState["clearActivity"]>(),
    clearConnectionLog: vi.fn<AgentState["clearConnectionLog"]>(),
  } satisfies AgentState;
}

export function makeConversation(task = makeTask()) {
  const session = makeSession({ taskIds: [task.id], status: task.status });
  return makeAgent({
    tasks: { [task.id]: task },
    sessions: { [session.id]: session },
    sessionOrder: [session.id],
    activeSessionId: session.id,
    activeSession: session,
    activeTasks: [task],
    active: task,
  });
}

export function installBridge() {
  type Bridge = NonNullable<Window["winbrow"]>;
  const listeners = new Map<string, Set<Parameters<Bridge["onMainEvent"]>[1]>>();
  const bridge = {
    serverUrl: "http://127.0.0.1:8765",
    resizeIsland: vi.fn<Bridge["resizeIsland"]>(),
    focusIsland: vi.fn<Bridge["focusIsland"]>(),
    blurIsland: vi.fn<Bridge["blurIsland"]>(),
    openDashboard: vi.fn<Bridge["openDashboard"]>(),
    closeDashboard: vi.fn<Bridge["closeDashboard"]>(),
    minimize: vi.fn<Bridge["minimize"]>(),
    maximize: vi.fn<Bridge["maximize"]>(),
    startSidecar: vi.fn<Bridge["startSidecar"]>(),
    restartSidecar: vi.fn<Bridge["restartSidecar"]>(),
    getSidecarLog: vi.fn<Bridge["getSidecarLog"]>().mockResolvedValue({ entries: [], path: "" }),
    quit: vi.fn<Bridge["quit"]>(),
    onMainEvent: vi.fn<Bridge["onMainEvent"]>((channel, handler) => {
      const handlers = listeners.get(channel) ?? new Set();
      handlers.add(handler);
      listeners.set(channel, handlers);
      return () => { handlers.delete(handler); };
    }),
  } satisfies Bridge;
  window.winbrow = bridge;
  return {
    bridge,
    emit(channel: string, payload?: unknown) {
      listeners.get(channel)?.forEach((handler) => handler(payload));
    },
    listenerCount() {
      return [...listeners.values()].reduce((count, handlers) => count + handlers.size, 0);
    },
  };
}
