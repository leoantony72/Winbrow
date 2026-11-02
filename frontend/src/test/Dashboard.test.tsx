import { act, fireEvent, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import Dashboard from "../Dashboard";
import {
  installBridge,
  makeAgent,
  makeConfirmation,
  makeConversation,
  makeSession,
  makeTask,
} from "./fixtures";

describe("Dashboard regression flows", () => {
  it("sends a trimmed message once and clears the accessible composer", async () => {
    const user = userEvent.setup();
    const agent = makeAgent();
    render(<Dashboard agent={agent} />);
    const input = screen.getByRole("textbox", { name: "Message WinBrow" });
    const send = screen.getByRole("button", { name: "Send" });
    expect(send).toBeDisabled();
    await user.type(input, "   ");
    expect(send).toBeDisabled();
    await user.type(input, "Find my report  ");
    await user.click(send);
    expect(agent.run).toHaveBeenCalledTimes(1);
    expect(agent.run).toHaveBeenCalledWith("Find my report", "");
    expect(input).toHaveValue("");
  });

  it("keeps Shift+Enter as a newline and sends with Enter", async () => {
    const user = userEvent.setup();
    const agent = makeAgent();
    render(<Dashboard agent={agent} />);
    const input = screen.getByRole("textbox", { name: "Message WinBrow" });
    await user.type(input, "First line");
    await user.keyboard("{Shift>}{Enter}{/Shift}");
    await user.type(input, "Second line");
    expect(input).toHaveValue("First line\nSecond line");
    expect(agent.run).not.toHaveBeenCalled();
    await user.keyboard("{Enter}");
    expect(agent.run).toHaveBeenCalledTimes(1);
    expect(agent.run).toHaveBeenCalledWith("First line\nSecond line", "");
    expect(input).toHaveValue("");
  });

  it.each(["offline", "connecting"] as const)(
    "blocks button and keyboard submissions while %s",
    async (connection) => {
      const user = userEvent.setup();
      const agent = makeAgent({ connection });
      render(<Dashboard agent={agent} />);
      await user.type(screen.getByRole("textbox"), "Do not run yet{Enter}");
      expect(screen.getByRole("button", { name: "Send" })).toBeDisabled();
      expect(agent.run).not.toHaveBeenCalled();
      expect(screen.getByRole("textbox")).toHaveValue("Do not run yet");
    },
  );

  it("does not submit a second task while the current task is running", async () => {
    const user = userEvent.setup();
    const agent = makeConversation(makeTask({ status: "running", live: true }));
    render(<Dashboard agent={agent} />);
    await user.type(screen.getByRole("textbox"), "Wait for the result{Enter}");
    expect(screen.getByRole("button", { name: "Follow up" })).toBeDisabled();
    expect(agent.run).not.toHaveBeenCalled();
  });

  it("does not treat an IME composition Enter as a submit", async () => {
    const user = userEvent.setup();
    const agent = makeAgent();
    render(<Dashboard agent={agent} />);
    const input = screen.getByRole("textbox");
    await user.type(input, "Draft");
    fireEvent.keyDown(input, {
      key: "Enter",
      code: "Enter",
      isComposing: true,
    });
    expect(agent.run).not.toHaveBeenCalled();
    expect(input).toHaveValue("Draft");
  });

  it("ignores whitespace-only Enter submissions", async () => {
    const user = userEvent.setup();
    const agent = makeAgent();
    render(<Dashboard agent={agent} />);
    await user.type(screen.getByRole("textbox"), "   {Enter}");
    expect(agent.run).not.toHaveBeenCalled();
  });

  it.each([
    "Research the web",
    "Work with files",
    "Create a document",
    "Compare & analyze",
  ])(
    "fills the composer from the %s example without executing it",
    async (name) => {
      const user = userEvent.setup();
      const agent = makeAgent();
      render(<Dashboard agent={agent} />);
      await user.click(
        screen.getByRole("button", {
          name: new RegExp(name, "i"),
        }),
      );
      const input = screen.getByRole("textbox", { name: "Message WinBrow" });
      expect(input).toHaveFocus();
      expect(input).not.toHaveValue("");
      expect(agent.run).not.toHaveBeenCalled();
      await user.click(screen.getByRole("button", { name: "Send" }));
      expect(agent.run).toHaveBeenCalledTimes(1);
      expect(agent.run).toHaveBeenCalledWith(expect.any(String), "");
    },
  );

  it("starts a new chat from its button and Ctrl+K while in Chats", async () => {
    const user = userEvent.setup();
    const agent = makeAgent();
    render(<Dashboard agent={agent} />);
    await user.click(screen.getByTitle("New chat (Ctrl+K)"));
    expect(agent.newChat).toHaveBeenCalledTimes(1);
    expect(screen.getByRole("textbox")).toHaveFocus();
    await user.keyboard("{Control>}k{/Control}");
    expect(agent.newChat).toHaveBeenCalledTimes(2);
    expect(screen.getByRole("textbox")).toHaveFocus();
  });

  it.each(["button", "shortcut"])(
    "returns from Server and focuses a new chat via %s",
    async (method) => {
      const user = userEvent.setup();
      const agent = makeAgent();
      render(<Dashboard agent={agent} />);
      await user.click(screen.getByRole("button", { name: "Server" }));
      expect(
        screen.getByRole("heading", { name: "Server activity" }),
      ).toBeInTheDocument();
      if (method === "button")
        await user.click(screen.getByTitle("New chat (Ctrl+K)"));
      else await user.keyboard("{Control>}k{/Control}");
      expect(agent.newChat).toHaveBeenCalledTimes(1);
      expect(
        screen.queryByRole("heading", { name: "Server activity" }),
      ).not.toBeInTheDocument();
      expect(screen.getByRole("textbox")).toHaveFocus();
    },
  );

  it("selects a session and deletes another without selecting it", async () => {
    const user = userEvent.setup();
    const first = makeSession();
    const second = makeSession({ id: "chat-2", title: "Invoice conversation" });
    const agent = makeAgent({
      sessions: { [first.id]: first, [second.id]: second },
      sessionOrder: [first.id, second.id],
    });
    render(<Dashboard agent={agent} />);
    await user.click(screen.getByText(first.title));
    expect(agent.selectSession).toHaveBeenCalledTimes(1);
    expect(agent.selectSession).toHaveBeenCalledWith(first.id);
    const secondItem = screen.getByText(second.title).closest(".rail-item");
    expect(secondItem).not.toBeNull();
    await user.click(
      within(secondItem as HTMLElement).getByTitle("Delete chat"),
    );
    expect(agent.deleteChat).toHaveBeenCalledTimes(1);
    expect(agent.deleteChat).toHaveBeenCalledWith(second.id);
    expect(agent.selectSession).toHaveBeenCalledTimes(1);
  });

  it.each([true, false])(
    "passes the explicit approval decision %s",
    async (approve) => {
      const user = userEvent.setup();
      const agent = makeAgent({ confirm: makeConfirmation() });
      render(<Dashboard agent={agent} />);
      expect(
        screen.getByText("Delete the draft report?", { exact: false }),
      ).toBeInTheDocument();
      await user.click(
        screen.getByRole("button", {
          name: approve ? "Allow" : "Deny",
        }),
      );
      expect(agent.respond).toHaveBeenCalledTimes(1);
      expect(agent.respond).toHaveBeenCalledWith(approve);
    },
  );

  it("stops a running task via Stop and Escape, but not after completion", async () => {
    const user = userEvent.setup();
    const agent = makeConversation(
      makeTask({ status: "running", live: true, answer: "" }),
    );
    const { rerender } = render(<Dashboard agent={agent} />);
    await user.click(screen.getAllByRole("button", { name: "Stop" })[0]);
    expect(agent.cancel).toHaveBeenCalledTimes(1);
    await user.keyboard("{Escape}");
    expect(agent.cancel).toHaveBeenCalledTimes(2);
    rerender(<Dashboard agent={makeConversation()} />);
    await user.keyboard("{Escape}");
    expect(agent.cancel).toHaveBeenCalledTimes(2);
  });

  it("toggles real Trace raw reasoning and persists the preference", async () => {
    const user = userEvent.setup();
    const agent = makeConversation(
      makeTask({
        thinking: [
          {
            id: "summary",
            kind: "summary",
            text: "Inspecting the report",
            ts: 1,
          },
          {
            id: "raw",
            kind: "raw",
            text: "Private provider reasoning fixture",
            ts: 1,
          },
        ],
      }),
    );
    const { unmount } = render(<Dashboard agent={agent} />);
    expect(
      screen.queryByText("reasoning", { exact: true }),
    ).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "raw reasoning off" }));
    expect(screen.getByText("reasoning", { exact: true })).toBeInTheDocument();
    expect(localStorage.getItem("winbrow.raw")).toBe("1");
    unmount();
    render(<Dashboard agent={agent} />);
    expect(
      screen.getByRole("button", { name: "raw reasoning on" }),
    ).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "raw reasoning on" }));
    expect(
      screen.queryByText("reasoning", { exact: true }),
    ).not.toBeInTheDocument();
    expect(localStorage.getItem("winbrow.raw")).toBe("0");
  });

  it("sends typed follow-ups with the completed task as parent", async () => {
    const user = userEvent.setup();
    const agent = makeConversation();
    render(<Dashboard agent={agent} />);
    await user.type(screen.getByRole("textbox"), "Explain the result");
    await user.click(screen.getByRole("button", { name: "Follow up" }));
    expect(agent.run).toHaveBeenCalledTimes(1);
    expect(agent.run).toHaveBeenCalledWith("Explain the result", "task-1");
  });

  it("routes both Trace and composer choices to their originating task", async () => {
    const user = userEvent.setup();
    const agent = makeConversation(
      makeTask({
        needsInput: true,
        question: "Which format?",
        options: ["PDF", "Text"],
        answer: "",
      }),
    );
    render(<Dashboard agent={agent} />);
    const choices = screen.getAllByRole("button", { name: /PDF/ });
    expect(choices).toHaveLength(2);
    await user.click(choices[0]);
    await user.click(choices[1]);
    expect(agent.run).toHaveBeenNthCalledWith(1, "PDF", "task-1");
    expect(agent.run).toHaveBeenNthCalledWith(2, "PDF", "task-1");
  });

  it("hides choices from a task that was already cancelled", () => {
    const agent = makeConversation(
      makeTask({
        status: "cancelled",
        needsInput: true,
        question: "Which format?",
        options: ["PDF", "Text"],
        answer: "",
      }),
    );
    render(<Dashboard agent={agent} />);
    expect(
      screen.queryByRole("button", { name: /PDF/ }),
    ).not.toBeInTheDocument();
    expect(screen.queryByText("needs your input")).not.toBeInTheDocument();
  });

  it("sends a suggested follow-up with its parent task", async () => {
    const user = userEvent.setup();
    const agent = makeConversation(
      makeTask({ goal: "Find the report file", answer: "Saved report.txt" }),
    );
    render(<Dashboard agent={agent} />);
    await user.click(
      screen.getByRole("button", { name: "Open the output file" }),
    );
    expect(agent.run).toHaveBeenCalledTimes(1);
    expect(agent.run).toHaveBeenCalledWith("Open the output file", "task-1");
  });

  it("switches Server and Chats, filters real activity, and invokes server controls", async () => {
    const user = userEvent.setup();
    const { bridge } = installBridge();
    const agent = makeAgent({
      activity: [
        {
          id: "brain",
          ts: 1,
          kind: "thinking",
          status: "info",
          title: "Planning the search",
        },
        {
          id: "step",
          ts: 2,
          kind: "step",
          status: "success",
          title: "Search finished",
        },
      ],
    });
    render(<Dashboard agent={agent} />);
    await user.click(screen.getByRole("button", { name: "Server" }));
    expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
    expect(screen.getByText("Planning the search")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Steps" }));
    expect(screen.queryByText("Planning the search")).not.toBeInTheDocument();
    expect(screen.getByText("Search finished")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "clear" }));
    expect(agent.clearActivity).toHaveBeenCalledTimes(1);
    expect(agent.clearConnectionLog).toHaveBeenCalledTimes(1);
    await user.click(screen.getByRole("button", { name: "Restart server" }));
    expect(bridge.restartSidecar).toHaveBeenCalledTimes(1);
    await user.click(screen.getByRole("button", { name: "Chats" }));
    expect(screen.getByRole("textbox")).toBeInTheDocument();
  });

  it("groups each prompt into an IST-stamped dropdown with oldest action first", async () => {
    const user = userEvent.setup();
    const base = Date.now() - 60_000;
    const older = makeTask({
      id: "task-old",
      goal: "Old prompt",
      status: "completed",
      createdAt: base,
      updatedAt: base + 4_000,
      startedAt: base,
      live: false,
      answer: "",
    });
    const newer = makeTask({
      id: "task-new",
      goal: "New prompt",
      status: "completed",
      createdAt: base + 10_000,
      updatedAt: base + 14_000,
      startedAt: base + 10_000,
      live: false,
      answer: "",
    });
    const agent = makeAgent({
      tasks: { [older.id]: older, [newer.id]: newer },
      activity: [
        {
          id: "old-1",
          ts: base + 1_000,
          taskId: older.id,
          kind: "step",
          status: "success",
          title: "first_action",
        },
        {
          id: "old-2",
          ts: base + 2_000,
          taskId: older.id,
          kind: "thinking",
          status: "info",
          title: "middle_plan",
        },
        {
          id: "old-3",
          ts: base + 3_000,
          taskId: older.id,
          kind: "step",
          status: "success",
          title: "last_action",
        },
        {
          id: "new-1",
          ts: base + 11_000,
          taskId: newer.id,
          kind: "step",
          status: "success",
          title: "second_action",
        },
      ],
    });

    render(<Dashboard agent={agent} />);
    await user.click(screen.getByRole("button", { name: "Server" }));

    const olderToggle = screen.getByRole("button", { name: /Old prompt/ });
    const newerToggle = screen.getByRole("button", { name: /New prompt/ });
    const olderGroup = olderToggle.closest(".prompt-group") as HTMLElement;
    const newerGroup = newerToggle.closest(".prompt-group") as HTMLElement;

    expect(within(olderToggle).getByText(/IST$/)).toBeInTheDocument();
    expect(within(olderGroup).queryByText("first_action")).not.toBeInTheDocument();
    expect(within(newerGroup).getByText("second_action")).toBeInTheDocument();

    await user.click(olderToggle);
    const first = within(olderGroup).getByText("first_action");
    const middle = within(olderGroup).getByText("middle_plan");
    const last = within(olderGroup).getByText("last_action");
    expect(
      first.compareDocumentPosition(middle) & Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
    expect(
      middle.compareDocumentPosition(last) & Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
  });

  it("dispatches window buttons to the mocked Electron bridge", async () => {
    const user = userEvent.setup();
    const { bridge } = installBridge();
    render(<Dashboard agent={makeAgent()} />);
    await user.click(screen.getByTitle("Minimize"));
    await user.click(screen.getByTitle("Maximize"));
    await user.click(screen.getByTitle("Close"));
    expect(bridge.minimize).toHaveBeenCalledTimes(1);
    expect(bridge.maximize).toHaveBeenCalledTimes(1);
    expect(bridge.closeDashboard).toHaveBeenCalledTimes(1);
  });

  it("handles the host Server event and unsubscribes on unmount", () => {
    const host = installBridge();
    const { unmount } = render(<Dashboard agent={makeAgent()} />);
    act(() => {
      host.emit("main:show-server");
    });
    expect(
      screen.getByRole("heading", { name: "Server activity" }),
    ).toBeInTheDocument();
    unmount();
    expect(host.listenerCount()).toBe(0);
  });

  it("uses only the stubbed voice endpoints for local voice toggling", async () => {
    const user = userEvent.setup();
    render(<Dashboard agent={makeAgent()} />);
    await user.click(screen.getByTitle("Start/stop local voice"));
    expect(vi.mocked(fetch)).toHaveBeenCalledWith(
      expect.stringMatching(/\/api\/voice\/toggle$/),
      { method: "POST" },
    );
  });
});
