import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import CopyButton from "../components/CopyButton";

afterEach(() => {
  delete (navigator as unknown as { clipboard?: unknown }).clipboard;
});

test("copies the text and shows confirmation", async () => {
  const writeText = vi.fn(async () => {});
  Object.defineProperty(navigator, "clipboard", {
    configurable: true,
    value: { writeText },
  });

  render(<CopyButton text="hello world" title="Copy hello" />);
  fireEvent.click(screen.getByRole("button", { name: "Copy hello" }));

  await waitFor(() => expect(writeText).toHaveBeenCalledWith("hello world"));
  expect(await screen.findByText("copied")).toBeInTheDocument();
});

test("does not toggle an enclosing control when asked to stop propagation", async () => {
  const writeText = vi.fn(async () => {});
  Object.defineProperty(navigator, "clipboard", {
    configurable: true,
    value: { writeText },
  });
  const onParent = vi.fn();

  render(
    <div onClick={onParent}>
      <CopyButton text="x" title="Copy x" stopPropagation />
    </div>,
  );
  fireEvent.click(screen.getByRole("button", { name: "Copy x" }));

  await waitFor(() => expect(writeText).toHaveBeenCalledWith("x"));
  expect(onParent).not.toHaveBeenCalled();
});
