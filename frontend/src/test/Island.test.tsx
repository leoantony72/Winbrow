import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import Island from "../Island";
import { DynamicIslandProvider } from "../components/ui/dynamic-island";
import type { AgentState } from "../lib/useAgent";
import {
  installBridge,
  makeAgent,
  makeConfirmation,
  makeConversation,
  makeTask,
} from "./fixtures";

function island(agent: AgentState) {
  return (
    <DynamicIslandProvider>
      <Island agent={agent} />
    </DynamicIslandProvider>
  );
}

describe("Island integration", () => {
  it("expands and collapses without running anything, and opens the dashboard", async () => {
    const user = userEvent.setup();
    const { bridge } = installBridge();
    const agent = makeAgent();
    render(island(agent));
    expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Expand island" }));
    expect(screen.getByRole("textbox")).toBeInTheDocument();
    expect(agent.refreshContext).toHaveBeenCalled();
    await user.click(screen.getByRole("button", { name: "Collapse island" }));
    await waitFor(() => {
      expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
    });
    expect(agent.run).not.toHaveBeenCalled();
    await user.click(screen.getByRole("button", { name: "Expand island" }));
    await user.click(screen.getByRole("button", { name: /Open dashboard/ }));
    expect(bridge.openDashboard).toHaveBeenCalledTimes(1);
    expect(
      screen.getByRole("button", { name: "Expand island" }),
    ).toBeInTheDocument();
    expect(bridge.resizeIsland).toHaveBeenCalled();
  });

  it("sends a typed task through the agent and collapses", async () => {
    const user = userEvent.setup();
    const { bridge } = installBridge();
    const agent = makeAgent();
    render(island(agent));
    await user.click(screen.getByRole("button", { name: "Expand island" }));
    const input = screen.getByRole("textbox");
    await user.type(input, "  Summarize this window  ");
    expect(bridge.focusIsland).toHaveBeenCalled();
    await user.keyboard("{Enter}");
    expect(agent.run).toHaveBeenCalledTimes(1);
    expect(agent.run).toHaveBeenCalledWith("Summarize this window");
    expect(
      screen.getByRole("button", { name: "Expand island" }),
    ).toBeInTheDocument();
  });

  it.each([true, false])(
    "automatically expands for a permission and sends decision %s",
    async (approve) => {
      const user = userEvent.setup();
      const agent = makeAgent({ confirm: makeConfirmation() });
      render(island(agent));
      expect(screen.getByText("Delete the draft report?")).toBeInTheDocument();
      expect(
        screen.getByRole("button", { name: "Collapse island" }),
      ).toBeInTheDocument();
      await user.click(
        screen.getByRole("button", { name: approve ? "Allow" : "Deny" }),
      );
      expect(agent.respond).toHaveBeenCalledTimes(1);
    expect(agent.respond).toHaveBeenCalledWith(approve);
    },
  );

  it("keeps the desktop control Stop reachable while collapsed and interrupts voice", async () => {
    const user = userEvent.setup();
    const task = makeTask({
      status: "running",
      live: true,
      answer: "",
      steps: [
        {
          id: "click",
          skill: "computer_click",
          args: { app: "Notepad" },
          status: "running",
          startedAt: Date.now(),
        },
      ],
    });
    const agent = makeConversation(task);
    render(island(agent));
    expect(
      screen.getByText("Agent is controlling your computer"),
    ).toBeInTheDocument();
    expect(screen.getByText("Notepad")).toBeInTheDocument();
    expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Stop" }));
    expect(agent.cancel).toHaveBeenCalledTimes(1);
    expect(agent.voiceAction).toHaveBeenCalledTimes(1);
    expect(agent.voiceAction).toHaveBeenCalledWith("interrupt");
  });

  it("stops a non-control task from the collapsed bar", async () => {
    const user = userEvent.setup();
    const agent = makeConversation(
      makeTask({ status: "running", live: true, answer: "" }),
    );
    render(island(agent));
    await user.click(
      screen.getByRole("button", { name: "Stop the current task" }),
    );
    expect(agent.cancel).toHaveBeenCalledTimes(1);
    expect(agent.voiceAction).toHaveBeenCalledTimes(1);
    expect(agent.voiceAction).toHaveBeenCalledWith("interrupt");
  });

  it.each([
    {
      running: false,
      muted: false,
      action: "start-wake",
      label: "Voice is off — click to start listening",
    },
    {
      running: true,
      muted: false,
      action: "mute",
      label: "Microphone on — click to mute",
    },
    {
      running: true,
      muted: true,
      action: "unmute",
      label: "Microphone muted — click to unmute",
    },
  ])(
    "maps microphone state to $action without expanding",
    async ({ running, muted, action, label }) => {
      const user = userEvent.setup();
      const agent = makeAgent();
      agent.voice = {
        ...agent.voice,
        running,
        muted,
        phase: running ? "idle" : "off",
      };
      render(island(agent));
      await user.click(screen.getByRole("button", { name: label }));
      expect(agent.voiceAction).toHaveBeenCalledTimes(1);
    expect(agent.voiceAction).toHaveBeenCalledWith(action);
      expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
    },
  );

  it("supports push-to-talk and voice lifecycle controls in the expanded card", async () => {
    const user = userEvent.setup();
    const agent = makeAgent();
    const { rerender } = render(island(agent));
    await user.click(screen.getByRole("button", { name: "Expand island" }));
    await user.click(
      screen.getByRole("button", { name: "Push to talk" }),
    );
    expect(agent.voiceAction).toHaveBeenLastCalledWith("ptt");
    await user.click(
      screen.getByRole("button", { name: "Voice on" }),
    );
    expect(agent.voiceAction).toHaveBeenLastCalledWith("start-wake");
    agent.voice = { ...agent.voice, running: true, muted: true, phase: "idle" };
    rerender(island(agent));
    expect(
      screen.getByRole("button", { name: "Push to talk" }),
    ).toBeDisabled();
    await user.click(
      screen.getByRole("button", { name: "Voice off" }),
    );
    expect(agent.voiceAction).toHaveBeenLastCalledWith("stop");
  });

  it("interrupts spoken output without cancelling the task", async () => {
    const user = userEvent.setup();
    const agent = makeAgent();
    agent.voice = {
      ...agent.voice,
      running: true,
      phase: "speaking",
      spoken: "Here is your report",
    };
    render(island(agent));
    await user.click(screen.getByRole("button", { name: "Expand island" }));
    await user.click(
      screen.getByRole("button", { name: "Stop speaking" }),
    );
    expect(agent.voiceAction).toHaveBeenCalledTimes(1);
    expect(agent.voiceAction).toHaveBeenCalledWith("interrupt");
    expect(agent.cancel).not.toHaveBeenCalled();
  });

  it("does not send commands or start voice while offline", async () => {
    const user = userEvent.setup();
    const { bridge } = installBridge();
    const agent = makeAgent({ connection: "offline" });
    render(island(agent));
    await user.click(screen.getByRole("button", { name: "Expand island" }));
    await user.type(screen.getByRole("textbox"), "Find a report{Enter}");
    expect(agent.run).not.toHaveBeenCalled();
    await user.click(
      screen.getByRole("button", {
        name: "Voice is off — click to start listening",
      }),
    );
    expect(agent.voiceAction).not.toHaveBeenCalled();
    await user.click(
      screen.getByRole("button", { name: "Start sidecar" }),
    );
    expect(bridge.startSidecar).toHaveBeenCalledTimes(1);
  });

  it("does not pin a failed task forever", () => {
    const agent = makeConversation(
      makeTask({
        status: "failed",
        error: "boom",
        updatedAt: Date.now() - 60_000,
      }),
    );
    render(island(agent));
    expect(screen.getByText("Ready")).toBeInTheDocument();
    expect(screen.queryByText("Failed")).not.toBeInTheDocument();
  });

  it("does not show choices from a cancelled task", () => {
    const agent = makeConversation(
      makeTask({
        status: "cancelled",
        needsInput: true,
        question: "Pick one",
        options: ["A", "B"],
        updatedAt: Date.now() - 60_000,
      }),
    );
    render(island(agent));
    expect(screen.queryByText("Needs input")).not.toBeInTheDocument();
    expect(screen.queryByText("Pick one")).not.toBeInTheDocument();
  });

  it("uses the latest agent for host kill events and removes subscriptions on unmount", () => {
    const host = installBridge();
    const oldAgent = makeAgent();
    const nextAgent = makeAgent();
    const { rerender, unmount } = render(island(oldAgent));
    rerender(island(nextAgent));
    act(() => {
      host.emit("main:kill");
    });
    expect(oldAgent.cancel).not.toHaveBeenCalled();
    expect(nextAgent.cancel).toHaveBeenCalledTimes(1);
    expect(nextAgent.voiceAction).toHaveBeenCalledTimes(1);
    expect(nextAgent.voiceAction).toHaveBeenCalledWith("interrupt");
    unmount();
    expect(host.listenerCount()).toBe(0);
    act(() => {
      host.emit("main:kill");
    });
    expect(nextAgent.cancel).toHaveBeenCalledTimes(1);
  });
});
