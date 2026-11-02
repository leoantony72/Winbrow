import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach, beforeEach, vi } from "vitest";

class TestResizeObserver implements ResizeObserver {
  observe() {}
  unobserve() {}
  disconnect() {}
}

beforeEach(() => {
  // Node 25 may expose a nonfunctional native localStorage to jsdom 25.
  const values = new Map<string, string>();
  const storage: Storage = {
    get length() {
      return values.size;
    },
    clear: () => values.clear(),
    getItem: (key) => values.get(key) ?? null,
    key: (index) => [...values.keys()][index] ?? null,
    removeItem: (key) => {
      values.delete(key);
    },
    setItem: (key, value) => {
      values.set(key, String(value));
    },
  };
  vi.stubGlobal("localStorage", storage);
  window.history.replaceState(null, "", "/");
  vi.stubGlobal("ResizeObserver", TestResizeObserver);
  vi.stubGlobal(
    "matchMedia",
    vi.fn((query: string): MediaQueryList => ({
      matches: query.includes("prefers-reduced-motion"),
      media: query,
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(() => true),
    })),
  );
  // Fail closed: even an unexpected request cannot reach a real sidecar.
  vi.stubGlobal(
    "fetch",
    vi.fn<typeof fetch>(async (input) => {
      const url = input instanceof Request ? input.url : String(input);
      if (!url.endsWith("/api/voice") && !url.endsWith("/api/voice/toggle")) {
        throw new Error(`Unexpected test fetch: ${url}`);
      }
      return new Response(
        JSON.stringify({ running: false, mode: "", muted: false }),
        {
          status: 200,
          headers: { "content-type": "application/json" },
        },
      );
    }),
  );
});

afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.unstubAllGlobals();
  delete window.winbrow;
});
