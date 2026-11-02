import { StrictMode, type PropsWithChildren } from "react";
import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  DynamicIslandProvider,
  useDynamicIslandSize,
  useScheduledAnimations,
  type AnimationStep,
} from "../components/ui/dynamic-island";

function Wrapper({ children }: PropsWithChildren) {
  return <DynamicIslandProvider>{children}</DynamicIslandProvider>;
}

function advance(ms: number) {
  act(() => { vi.advanceTimersByTime(ms); });
}

describe("DynamicIslandProvider queue lifecycle", () => {
  beforeEach(() => { vi.useFakeTimers(); });
  afterEach(() => { vi.clearAllTimers(); });

  it("completes steps using relative delays and clears the final queue", () => {
    const { result } = renderHook(useDynamicIslandSize, { wrapper: Wrapper });
    act(() => {
      result.current.scheduleAnimation([
        { size: "large", delay: 100 },
        { size: "compact", delay: 200 },
      ]);
    });
    expect(result.current.state.isAnimating).toBe(true);
    advance(99);
    expect(result.current.state.size).toBe("default");
    advance(1);
    expect(result.current.state).toMatchObject({
      size: "large", previousSize: "default", isAnimating: true,
      animationQueue: [{ size: "compact", delay: 200 }],
    });
    advance(199);
    expect(result.current.state.size).toBe("large");
    advance(1);
    expect(result.current.state).toEqual({
      size: "compact", previousSize: "large", isAnimating: false, animationQueue: [],
    });
    expect(vi.getTimerCount()).toBe(0);
  });

  it("replaces pending steps and ignores an older owner's cleanup", () => {
    const { result } = renderHook(useDynamicIslandSize, { wrapper: Wrapper });
    let cancelOld = () => {};
    let cancelNew = () => {};
    act(() => { cancelOld = result.current.scheduleAnimation([{ size: "massive", delay: 100 }]); });
    advance(50);
    act(() => { cancelNew = result.current.scheduleAnimation([{ size: "compact", delay: 200 }]); });
    act(() => { cancelOld(); });
    advance(100);
    expect(result.current.state.size).toBe("default");
    expect(result.current.state.isAnimating).toBe(true);
    advance(100);
    expect(result.current.state.size).toBe("compact");
    act(() => { cancelNew(); });
    expect(result.current.state.animationQueue).toEqual([]);
    expect(result.current.state.isAnimating).toBe(false);
  });

  it("owner cleanup cancels its pending queue without changing the size", () => {
    const { result } = renderHook(useDynamicIslandSize, { wrapper: Wrapper });
    let cancel = () => {};
    act(() => { cancel = result.current.scheduleAnimation([{ size: "large", delay: 100 }]); });
    act(() => { cancel(); });
    advance(1000);
    expect(result.current.state).toMatchObject({ size: "default", isAnimating: false, animationQueue: [] });
    expect(vi.getTimerCount()).toBe(0);
  });

  it("clears the pending timeout when the provider unmounts", () => {
    const { result, unmount } = renderHook(useDynamicIslandSize, { wrapper: Wrapper });
    act(() => { result.current.scheduleAnimation([{ size: "large", delay: 100 }]); });
    expect(vi.getTimerCount()).toBe(1);
    unmount();
    expect(vi.getTimerCount()).toBe(0);
    advance(1000);
  });

  it("manual transitions can return to the previous size and cancel scheduled work", () => {
    const { result } = renderHook(useDynamicIslandSize, { wrapper: Wrapper });
    act(() => { result.current.setSize("large"); });
    expect(result.current.state.previousSize).toBe("default");
    act(() => { result.current.scheduleAnimation([{ size: "massive", delay: 100 }]); });
    const previous = result.current.state.previousSize;
    expect(previous).toBe("default");
    act(() => { result.current.setSize(previous!); });
    advance(1000);
    expect(result.current.state).toEqual({
      size: "default", previousSize: "large", animationQueue: [], isAnimating: false,
    });
    act(() => { result.current.setSize(result.current.state.previousSize!); });
    expect(result.current.state).toMatchObject({ size: "large", previousSize: "default" });
  });

  it("setting the current size still cancels a queue without losing previousSize", () => {
    const { result } = renderHook(useDynamicIslandSize, { wrapper: Wrapper });
    act(() => { result.current.setSize("large"); });
    act(() => { result.current.scheduleAnimation([{ size: "compact", delay: 100 }]); });
    act(() => { result.current.setSize("large"); });
    advance(100);
    expect(result.current.state).toEqual({
      size: "large", previousSize: "default", animationQueue: [], isAnimating: false,
    });
  });

  it("an empty replacement cancels the previous queue", () => {
    const { result } = renderHook(useDynamicIslandSize, { wrapper: Wrapper });
    act(() => { result.current.scheduleAnimation([{ size: "large", delay: 100 }]); });
    act(() => { result.current.scheduleAnimation([]); });
    advance(100);
    expect(result.current.state).toMatchObject({ size: "default", isAnimating: false, animationQueue: [] });
  });

  it.each([-10, Number.NaN, Number.POSITIVE_INFINITY])("normalizes invalid delay %s to zero", (delay) => {
    const { result } = renderHook(useDynamicIslandSize, { wrapper: Wrapper });
    act(() => { result.current.scheduleAnimation([{ size: "large", delay }]); });
    advance(0);
    expect(result.current.state).toMatchObject({ size: "large", isAnimating: false });
  });

  it("supports legacy dispatch initialization, scheduling, and cancellation", () => {
    const { result } = renderHook(useDynamicIslandSize, { wrapper: Wrapper });
    act(() => { result.current.dispatch({ type: "INITIALIZE", firstState: "compact" }); });
    act(() => { result.current.dispatch({ type: "SET_SIZE", newSize: "large" }); });
    act(() => {
      result.current.dispatch({ type: "SCHEDULE_ANIMATION", animationSteps: [{ size: "tall", delay: 100 }] });
    });
    act(() => { result.current.dispatch({ type: "ANIMATION_END" }); });
    advance(100);
    expect(result.current.state).toEqual({
      size: "large", previousSize: "compact", animationQueue: [], isAnimating: false,
    });
  });

  it("initializes and completes its initial animation under StrictMode", () => {
    const steps: AnimationStep[] = [{ size: "large", delay: 100 }, { size: "compact", delay: 100 }];
    const { result } = renderHook(useDynamicIslandSize, {
      wrapper: ({ children }: PropsWithChildren) => (
        <StrictMode>
          <DynamicIslandProvider initialSize="minimalLeading" initialAnimation={steps}>
            {children}
          </DynamicIslandProvider>
        </StrictMode>
      ),
    });
    expect(result.current.state).toMatchObject({ size: "minimalLeading", isAnimating: true });
    advance(100);
    expect(result.current.state.size).toBe("large");
    advance(100);
    expect(result.current.state).toEqual({
      size: "compact", previousSize: "large", isAnimating: false, animationQueue: [],
    });
    expect(steps).toEqual([{ size: "large", delay: 100 }, { size: "compact", delay: 100 }]);
    expect(vi.getTimerCount()).toBe(0);
  });

  it("does not restart equal inline hook steps on rerender and cleans up on unmount", () => {
    const { result, rerender, unmount } = renderHook(() => {
      useScheduledAnimations([{ size: "large", delay: 100 }, { size: "compact", delay: 200 }]);
      return useDynamicIslandSize();
    }, { wrapper: Wrapper });
    advance(50);
    rerender();
    advance(50);
    expect(result.current.state.size).toBe("large");
    advance(100);
    rerender();
    advance(100);
    expect(result.current.state).toMatchObject({ size: "compact", isAnimating: false });
    unmount();
    expect(vi.getTimerCount()).toBe(0);
  });

  it("replaces changed hook steps and cancels them when the consumer unmounts", () => {
    const { result, rerender, unmount } = renderHook(({ steps }) => {
      useScheduledAnimations(steps);
      return useDynamicIslandSize();
    }, {
      wrapper: Wrapper,
      initialProps: { steps: [{ size: "large", delay: 100 }] as AnimationStep[] },
    });
    advance(50);
    rerender({ steps: [{ size: "compact", delay: 200 }] });
    advance(100);
    expect(result.current.state.size).toBe("default");
    unmount();
    expect(vi.getTimerCount()).toBe(0);
  });

  it("schedules hook animations exactly once through StrictMode effect replay", () => {
    const { result } = renderHook(() => {
      useScheduledAnimations([{ size: "large", delay: 100 }]);
      return useDynamicIslandSize();
    }, {
      wrapper: ({ children }: PropsWithChildren) => (
        <StrictMode><DynamicIslandProvider>{children}</DynamicIslandProvider></StrictMode>
      ),
    });
    expect(vi.getTimerCount()).toBe(1);
    advance(100);
    expect(result.current.state).toMatchObject({ size: "large", previousSize: "default", isAnimating: false });
    expect(vi.getTimerCount()).toBe(0);
  });
});
