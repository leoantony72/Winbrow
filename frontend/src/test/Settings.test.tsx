import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import Settings from "../Settings";

const ENV = {
  path: "D:\\Codee\\desktop_agent\\.env",
  groups: [
    {
      id: "brain",
      label: "AI brain",
      description: "Provider keys and model selection.",
      fields: [
        {
          key: "NEBIUS_API_KEY",
          label: "Nebius API key",
          description: "Token Factory key.",
          kind: "text",
          choices: [],
          restart: false,
          secret: true,
          value: "",
          default: "",
          source: "env",
          is_set: true,
          in_file: true,
        },
        {
          key: "WINBROW_STREAM",
          label: "Stream responses",
          description: "0 forces buffered calls.",
          kind: "boolean",
          choices: [],
          restart: false,
          secret: false,
          value: "1",
          default: "1",
          source: "default",
          is_set: true,
          in_file: false,
        },
      ],
    },
  ],
  custom: [],
  secrets_stored_plaintext: true,
};

function jsonResponse(body: unknown) {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { "content-type": "application/json" },
  });
}

describe("Settings tab", () => {
  it("loads grouped values, masks secrets, and saves only changed keys", async () => {
    const user = userEvent.setup();
    let posted: Record<string, unknown> | null = null;
    const fetchMock = vi.fn<typeof fetch>(async (input, init) => {
      const url = String(input);
      if (url.endsWith("/api/env") && init?.method === "POST") {
        posted = JSON.parse(String(init.body));
        return jsonResponse({
          status: "saved",
          saved: ["WINBROW_STREAM"],
          unset: [],
          requires_restart: false,
          restart_keys: [],
        });
      }
      if (url.endsWith("/api/env")) return jsonResponse(ENV);
      throw new Error(`Unexpected fetch: ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<Settings />);

    await screen.findByText("AI brain");
    expect(screen.getByText("NEBIUS_API_KEY")).toBeInTheDocument();
    expect(screen.getByText("set")).toBeInTheDocument();

    const row = screen.getByText("Stream responses").closest(".settings-field");
    expect(row).not.toBeNull();
    const toggle = within(row as HTMLElement).getByRole("switch");
    await user.click(toggle);

    await user.click(screen.getByRole("button", { name: /Save changes/ }));

    await waitFor(() => expect(posted).not.toBeNull());
    expect(posted).toEqual({
      updates: { WINBROW_STREAM: "0" },
      unset: [],
    });
  });
});
