"use client";

import {
  Children,
  createContext,
  forwardRef,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type Dispatch,
  type ReactNode,
} from "react";
import {
  AnimatePresence,
  motion,
  useReducedMotion,
  type HTMLMotionProps,
  type Transition,
} from "framer-motion";
import { cn } from "@/lib/utils";

export const stiffness = 400;
export const damping = 30;
export const SIZE_PRESETS = {
  RESET: "reset",
  EMPTY: "empty",
  DEFAULT: "default",
  COMPACT: "compact",
  COMPACT_LONG: "compactLong",
  LARGE: "large",
  LONG: "long",
  MINIMAL_LEADING: "minimalLeading",
  MINIMAL_TRAILING: "minimalTrailing",
  COMPACT_MEDIUM: "compactMedium",
  MEDIUM: "medium",
  TALL: "tall",
  ULTRA: "ultra",
  MASSIVE: "massive",
} as const;

export type SizePresets = (typeof SIZE_PRESETS)[keyof typeof SIZE_PRESETS];
export interface Preset {
  width: number;
  height?: number;
  /** The supplied presets express height / width, not CSS aspect-ratio. */
  aspectRatio: number;
  borderRadius: number;
}

export const DynamicIslandSizePresets: Record<SizePresets, Preset> = {
  reset: { width: 150, aspectRatio: 1, borderRadius: 20 },
  empty: { width: 0, aspectRatio: 0, borderRadius: 0 },
  default: { width: 150, aspectRatio: 44 / 150, borderRadius: 46 },
  compact: { width: 235, aspectRatio: 44 / 235, borderRadius: 46 },
  compactLong: { width: 300, aspectRatio: 44 / 235, borderRadius: 46 },
  large: { width: 371, aspectRatio: 84 / 371, borderRadius: 42 },
  long: { width: 371, aspectRatio: 84 / 371, borderRadius: 42 },
  minimalLeading: { width: 52.33, aspectRatio: 44 / 52.33, borderRadius: 22 },
  minimalTrailing: { width: 52.33, aspectRatio: 44 / 52.33, borderRadius: 22 },
  compactMedium: { width: 351, aspectRatio: 64 / 371, borderRadius: 44 },
  medium: { width: 371, aspectRatio: 210 / 371, borderRadius: 22 },
  tall: { width: 371, aspectRatio: 210 / 371, borderRadius: 42 },
  ultra: { width: 630, aspectRatio: 630 / 800, borderRadius: 42 },
  massive: { width: 891, height: 1900, aspectRatio: 1, borderRadius: 42 },
};

export interface AnimationStep {
  size: SizePresets;
  /** Wait before this step, in milliseconds (relative to the preceding step). */
  delay: number;
}
export interface BlobStateType {
  size: SizePresets;
  previousSize: SizePresets | undefined;
  animationQueue: AnimationStep[];
  /** True while scheduled steps remain; independent of individual motion springs. */
  isAnimating: boolean;
}
export type BlobAction =
  | { type: "SET_SIZE"; newSize: SizePresets }
  | { type: "INITIALIZE"; firstState: SizePresets }
  | { type: "SCHEDULE_ANIMATION"; animationSteps: readonly AnimationStep[] }
  | { type: "ANIMATION_END" };
export interface BlobContextType {
  state: BlobStateType;
  dispatch: Dispatch<BlobAction>;
  setSize: (size: SizePresets) => void;
  /** Replaces the current queue; returns an owner-scoped cancellation function. */
  scheduleAnimation: (steps: readonly AnimationStep[]) => () => void;
  cancelAnimation: () => void;
  presets: Record<SizePresets, Preset>;
}
export const BlobContext = createContext<BlobContextType | undefined>(
  undefined,
);

export interface DynamicIslandProviderProps {
  children: ReactNode;
  initialSize?: SizePresets;
  initialAnimation?: readonly AnimationStep[];
}

export function DynamicIslandProvider({
  children,
  initialSize = "default",
  initialAnimation = [],
}: DynamicIslandProviderProps) {
  const [state, updateState] = useState<BlobStateType>(() => ({
    size: initialSize,
    previousSize: "empty",
    animationQueue: initialAnimation.map((step) => ({ ...step })),
    isAnimating: initialAnimation.length > 0,
  }));
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const generation = useRef(0);
  const invalidate = useCallback(() => {
    generation.current += 1;
    clearTimeout(timer.current);
    timer.current = undefined;
  }, []);

  const cancelAnimation = useCallback(() => {
    invalidate();
    updateState((current) => ({
      ...current,
      animationQueue: [],
      isAnimating: false,
    }));
  }, [invalidate]);

  const setSize = useCallback(
    (size: SizePresets) => {
      // Even setting the current size is a manual override of a pending sequence.
      invalidate();
      updateState((current) => ({
        size,
        previousSize:
          size === current.size ? current.previousSize : current.size,
        animationQueue: [],
        isAnimating: false,
      }));
    },
    [invalidate],
  );

  const scheduleAnimation = useCallback(
    (steps: readonly AnimationStep[]) => {
      invalidate();
      const owner = generation.current;
      const queue = steps.map((step) => ({ ...step }));
      updateState((current) => ({
        ...current,
        animationQueue: queue,
        isAnimating: queue.length > 0,
      }));
      return () => {
        // A stale hook cleanup must never cancel a newer caller's sequence.
        if (generation.current === owner) cancelAnimation();
      };
    },
    [invalidate, cancelAnimation],
  );

  useEffect(() => {
    const [step] = state.animationQueue;
    if (!step) return;
    const owner = generation.current;
    const delay = Number.isFinite(step.delay) ? Math.max(0, step.delay) : 0;
    timer.current = setTimeout(() => {
      if (generation.current !== owner) return;
      updateState((current) => {
        if (current.animationQueue !== state.animationQueue) return current;
        const remaining = current.animationQueue.slice(1);
        return {
          size: step.size,
          previousSize:
            step.size === current.size ? current.previousSize : current.size,
          animationQueue: remaining,
          isAnimating: remaining.length > 0,
        };
      });
    }, delay);
    return () => clearTimeout(timer.current);
  }, [state.animationQueue]);

  useEffect(() => invalidate, [invalidate]);

  const dispatch = useCallback<Dispatch<BlobAction>>(
    (action) => {
      switch (action.type) {
        case "SET_SIZE":
          setSize(action.newSize);
          break;
        case "INITIALIZE":
          setSize(action.firstState);
          break;
        case "SCHEDULE_ANIMATION":
          scheduleAnimation(action.animationSteps);
          break;
        case "ANIMATION_END":
          cancelAnimation();
          break;
      }
    },
    [setSize, scheduleAnimation, cancelAnimation],
  );

  const value = useMemo<BlobContextType>(
    () => ({
      state,
      dispatch,
      setSize,
      scheduleAnimation,
      cancelAnimation,
      presets: DynamicIslandSizePresets,
    }),
    [state, dispatch, setSize, scheduleAnimation, cancelAnimation],
  );
  return <BlobContext.Provider value={value}>{children}</BlobContext.Provider>;
}

export function useDynamicIslandSize() {
  const context = useContext(BlobContext);
  if (!context) {
    throw new Error(
      "useDynamicIslandSize must be used within a DynamicIslandProvider",
    );
  }
  return context;
}

export function useScheduledAnimations(animations: readonly AnimationStep[]) {
  const { scheduleAnimation } = useDynamicIslandSize();
  // Value equality supports inline arrays without restarting on every size change.
  const signature = JSON.stringify(animations);
  useEffect(() => {
    const steps: AnimationStep[] = JSON.parse(signature);
    return scheduleAnimation(steps);
  }, [signature, scheduleAnimation]);
}

function useBounds(displayBounds: boolean) {
  const [bounds, setBounds] = useState<{ width: number; height: number }>();
  useEffect(() => {
    const update = () =>
      setBounds({
        width: displayBounds ? window.screen.availWidth : window.innerWidth,
        height: displayBounds ? window.screen.availHeight : window.innerHeight,
      });
    update();
    window.addEventListener("resize", update);
    return () => window.removeEventListener("resize", update);
  }, [displayBounds]);
  return bounds;
}

export interface DynamicIslandProps extends Omit<
  HTMLMotionProps<"div">,
  "children"
> {
  children?: ReactNode;
  /** Pixel dimensions override the preset. Use height="auto" for overlay content. */
  width?: number;
  height?: number | "auto";
}

export const Component = forwardRef<HTMLDivElement, DynamicIslandProps>(
  (
    { children, className, width, height, style, transition, ...props },
    ref,
  ) => {
    const { state, presets } = useDynamicIslandSize();
    const reduced = useReducedMotion();
    // Electron resizes its window to this node: clamping explicit dimensions to
    // that window would prevent it from ever growing from 196px to 404/460px.
    const bounds = useBounds(width !== undefined);
    const preset = presets[state.size];
    const mobile = bounds !== undefined && bounds.width <= 640;
    const mobileLarge =
      mobile && (state.size === "ultra" || state.size === "massive");
    const presetWidth = mobileLarge ? 350 : Math.min(preset.width, 691);
    const targetWidth = Math.max(
      0,
      Math.min(width ?? presetWidth, bounds?.width ?? Infinity),
    );
    const presetHeight = mobileLarge
      ? state.size === "ultra"
        ? 400
        : 700
      : presetWidth * preset.aspectRatio;
    const targetHeight =
      height === "auto"
        ? "auto"
        : Math.max(
            0,
            Math.min(height ?? presetHeight, bounds?.height ?? Infinity),
          );
    const spring: Transition = reduced
      ? { duration: 0 }
      : { type: "spring", stiffness, damping };

    return (
      <motion.div
        {...props}
        ref={ref}
        className={cn(
          "relative mx-auto shrink-0 overflow-hidden bg-black text-white",
          className,
        )}
        initial={false}
        animate={{
          width: targetWidth,
          height: targetHeight,
          borderRadius: preset.borderRadius,
        }}
        transition={reduced ? { duration: 0 } : (transition ?? spring)}
        style={{
          ...style,
          boxSizing: "border-box",
          maxWidth: width === undefined ? "100%" : bounds?.width,
          maxHeight: bounds?.height,
          overflowY: "auto",
        }}
        data-size={state.size}
      >
        <AnimatePresence initial={false}>
          {Children.toArray(children)}
        </AnimatePresence>
      </motion.div>
    );
  },
);
Component.displayName = "DynamicIsland";
export { Component as DynamicIsland };

function useContentMotion(): HTMLMotionProps<"div"> {
  const reduced = useReducedMotion();
  return {
    initial: reduced ? false : { opacity: 0, scale: 0.95, y: 5 },
    animate: { opacity: 1, scale: 1, y: 0 },
    exit: reduced
      ? { opacity: 0 }
      : { opacity: 0, scale: 0.95, y: 8, filter: "blur(4px)" },
    transition: reduced
      ? { duration: 0 }
      : { type: "spring", stiffness, damping },
  };
}

export const DynamicContainer = forwardRef<
  HTMLDivElement,
  HTMLMotionProps<"div">
>((props, ref) => <motion.div {...useContentMotion()} {...props} ref={ref} />);
DynamicContainer.displayName = "DynamicContainer";

export const DynamicDiv = forwardRef<HTMLDivElement, HTMLMotionProps<"div">>(
  (props, ref) => <motion.div {...useContentMotion()} {...props} ref={ref} />,
);
DynamicDiv.displayName = "DynamicDiv";

export const DynamicTitle = forwardRef<
  HTMLHeadingElement,
  HTMLMotionProps<"h3">
>((props, ref) => {
  const { initial, animate, exit, transition } = useContentMotion();
  return (
    <motion.h3
      initial={initial}
      animate={animate}
      exit={exit}
      transition={transition}
      {...props}
      ref={ref}
    />
  );
});
DynamicTitle.displayName = "DynamicTitle";

export const DynamicDescription = forwardRef<
  HTMLParagraphElement,
  HTMLMotionProps<"p">
>((props, ref) => {
  const { initial, animate, exit, transition } = useContentMotion();
  return (
    <motion.p
      initial={initial}
      animate={animate}
      exit={exit}
      transition={transition}
      {...props}
      ref={ref}
    />
  );
});
DynamicDescription.displayName = "DynamicDescription";
