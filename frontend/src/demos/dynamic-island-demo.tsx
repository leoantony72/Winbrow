"use client";

import { forwardRef } from "react";
import { motion, useReducedMotion, type HTMLMotionProps } from "framer-motion";
import {
  ArrowRight,
  Bell,
  Check,
  CloudUpload,
  Headphones,
  MessageCircle,
  Music2,
  Phone,
  PhoneOff,
  Play,
  RotateCcw,
  Timer,
  X,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  DynamicContainer,
  DynamicDescription,
  DynamicDiv,
  DynamicIsland,
  DynamicIslandProvider,
  DynamicTitle,
  useDynamicIslandSize,
  type AnimationStep,
  type SizePresets,
} from "@/components/ui/dynamic-island";
import { cn } from "@/lib/utils";

export const FadeIn = forwardRef<HTMLDivElement, HTMLMotionProps<"div">>(
  ({ className, ...props }, ref) => {
    const reduced = useReducedMotion();
    return (
      <motion.div
        ref={ref}
        className={className}
        variants={{
          hidden: { opacity: reduced ? 1 : 0, y: reduced ? 0 : 8 },
          visible: {
            opacity: 1,
            y: 0,
            transition: { duration: reduced ? 0 : 0.25 },
          },
        }}
        {...props}
      />
    );
  },
);
FadeIn.displayName = "FadeIn";

export const FadeInStagger = forwardRef<HTMLDivElement, HTMLMotionProps<"div">>(
  (props, ref) => {
    const reduced = useReducedMotion();
    return (
      <motion.div
        ref={ref}
        initial="hidden"
        animate="visible"
        variants={{
          hidden: {},
          visible: { transition: { staggerChildren: reduced ? 0 : 0.08 } },
        }}
        {...props}
      />
    );
  },
);
FadeInStagger.displayName = "FadeInStagger";

const CYCLE: readonly SizePresets[] = [
  "default",
  "compact",
  "large",
  "tall",
  "long",
  "medium",
  "compactLong",
  "compactMedium",
  "minimalLeading",
  "minimalTrailing",
  "ultra",
  "massive",
  "reset",
  "empty",
];
const INTRO: readonly AnimationStep[] = [
  { size: "compact", delay: 300 },
  { size: "large", delay: 1200 },
  { size: "tall", delay: 1500 },
  { size: "long", delay: 1800 },
  { size: "medium", delay: 1500 },
  { size: "default", delay: 2000 },
];

function Waveform() {
  const reduced = useReducedMotion();
  return (
    <div
      className="flex h-5 items-center gap-0.5 text-emerald-400"
      aria-hidden="true"
    >
      {[0.35, 0.7, 1, 0.55, 0.85].map((height, index) => (
        <motion.span
          key={index}
          className="block w-0.5 rounded-full bg-current"
          style={{ height: `${height * 100}%` }}
          animate={reduced ? { scaleY: 1 } : { scaleY: [1, 0.4, 1] }}
          transition={
            reduced
              ? { duration: 0 }
              : {
                  duration: 1,
                  repeat: Infinity,
                  delay: index * 0.12,
                }
          }
        />
      ))}
    </div>
  );
}

function IslandContents() {
  const { state, setSize } = useDynamicIslandSize();
  const row = "flex h-full w-full items-center justify-between gap-3 px-5";
  const title = "m-0 text-sm font-semibold text-white";
  const description = "m-0 text-xs text-neutral-400";

  switch (state.size) {
    case "empty":
      return null;
    case "reset":
      return (
        <DynamicContainer
          key={state.size}
          className="flex h-full flex-col items-center justify-center gap-3"
        >
          <Check className="size-7 text-emerald-400" aria-hidden="true" />
          <DynamicTitle className={title}>All caught up</DynamicTitle>
        </DynamicContainer>
      );
    case "minimalLeading":
    case "minimalTrailing":
      return (
        <DynamicContainer
          key={state.size}
          className="flex h-full items-center justify-center"
        >
          <span className="sr-only">
            {state.size === "minimalLeading"
              ? "Music playing"
              : "New notification"}
          </span>
          {state.size === "minimalLeading" ? (
            <Music2 className="size-5 text-emerald-400" aria-hidden="true" />
          ) : (
            <Bell className="size-5 text-amber-300" aria-hidden="true" />
          )}
        </DynamicContainer>
      );
    case "default":
      return (
        <DynamicContainer
          key={state.size}
          className={cn(row, "justify-center px-3")}
        >
          <span
            className="size-2 shrink-0 rounded-full bg-emerald-400"
            aria-hidden="true"
          />
          <DynamicTitle className={title}>Ready</DynamicTitle>
        </DynamicContainer>
      );
    case "compact":
    case "compactLong":
      return (
        <DynamicContainer key={state.size} className={row}>
          <Music2
            className="size-5 shrink-0 text-emerald-400"
            aria-hidden="true"
          />
          <DynamicTitle className={title}>Cult FM</DynamicTitle>
          {state.size === "compactLong" && (
            <DynamicDescription className={description}>
              Now playing
            </DynamicDescription>
          )}
          <Waveform />
        </DynamicContainer>
      );
    case "large":
      return (
        <DynamicContainer key={state.size} className={row}>
          <CloudUpload
            className="size-7 shrink-0 text-blue-400"
            aria-hidden="true"
          />
          <DynamicDiv className="min-w-0 flex-1 text-left">
            <DynamicTitle className={title}>Syncing your files</DynamicTitle>
            <DynamicDescription className={description}>
              3 of 5 files uploaded
            </DynamicDescription>
          </DynamicDiv>
          <Badge variant="outline" className="border-blue-400/30 text-blue-300">
            60%
          </Badge>
        </DynamicContainer>
      );
    case "long":
    case "compactMedium":
      return (
        <DynamicContainer key={state.size} className={row}>
          <Timer
            className="size-6 shrink-0 text-amber-300"
            aria-hidden="true"
          />
          <DynamicTitle className={title}>Focus timer</DynamicTitle>
          <DynamicDescription className="m-0 font-mono text-xl tabular-nums text-amber-300">
            12:48
          </DynamicDescription>
          <Button
            variant="ghost"
            size="icon"
            className="shrink-0 text-white hover:bg-white/10"
            aria-label="Dismiss timer"
            onClick={() => setSize("default")}
          >
            <X />
          </Button>
        </DynamicContainer>
      );
    case "medium":
      return (
        <DynamicContainer
          key={state.size}
          className="flex h-full flex-col justify-between p-6"
        >
          <div className="flex items-center gap-3">
            <div className="flex size-12 shrink-0 items-center justify-center rounded-full bg-violet-500/20">
              <Phone className="size-6 text-violet-300" aria-hidden="true" />
            </div>
            <div>
              <DynamicTitle className="m-0 text-lg font-semibold">
                Alex Morgan
              </DynamicTitle>
              <DynamicDescription className={description}>
                Incoming audio call
              </DynamicDescription>
            </div>
          </div>
          <div className="flex justify-between gap-3">
            <Button
              className="bg-red-600 text-white hover:bg-red-700"
              onClick={() => setSize("default")}
            >
              <PhoneOff /> Decline
            </Button>
            <Button
              className="bg-emerald-600 text-white hover:bg-emerald-700"
              onClick={() => setSize("compactLong")}
            >
              <Phone /> Accept
            </Button>
          </div>
        </DynamicContainer>
      );
    case "tall":
      return (
        <DynamicContainer
          key={state.size}
          className="flex h-full flex-col gap-3 p-6 text-left"
        >
          <div className="flex items-center gap-2 text-violet-300">
            <MessageCircle className="size-4" aria-hidden="true" />
            <span className="text-xs">Messages · just now</span>
          </div>
          <DynamicTitle className="m-0 text-lg font-semibold">
            A little update from Alex
          </DynamicTitle>
          <DynamicDescription className="m-0 text-sm text-neutral-300">
            The new release is ready. Want to take a look together?
          </DynamicDescription>
          <Button
            size="sm"
            variant="ghost"
            className="mt-auto self-start text-violet-300 hover:bg-white/10"
            onClick={() => setSize("medium")}
          >
            Call Alex <ArrowRight />
          </Button>
        </DynamicContainer>
      );
    case "ultra":
    case "massive":
      return (
        <DynamicContainer
          key={state.size}
          className="h-full overflow-y-auto p-7 text-left"
        >
          <FadeInStagger className="flex flex-col gap-6">
            <FadeIn className="flex items-center justify-between gap-3">
              <Badge className="bg-emerald-400/15 text-emerald-300">
                Now playing
              </Badge>
              <Headphones
                className="size-5 text-neutral-400"
                aria-hidden="true"
              />
            </FadeIn>
            <FadeIn className="flex aspect-square max-h-64 w-full items-center justify-center rounded-3xl bg-gradient-to-br from-violet-600 via-fuchsia-600 to-orange-400">
              <Music2 className="size-20 text-white/80" aria-hidden="true" />
            </FadeIn>
            <FadeIn>
              <DynamicTitle className="m-0 text-2xl font-bold">
                Late night, early morning
              </DynamicTitle>
              <DynamicDescription className="mt-2 text-sm text-neutral-400">
                Cult FM · Focus sessions
              </DynamicDescription>
            </FadeIn>
            <FadeIn className="flex items-center justify-between gap-4">
              <Waveform />
              <Button variant="secondary" onClick={() => setSize("compact")}>
                <Music2 /> Minimize player
              </Button>
            </FadeIn>
            {state.size === "massive" && (
              <FadeIn className="rounded-2xl border border-white/10 p-5">
                <h4 className="mb-2 mt-0 font-semibold">Up next</h4>
                <p className="m-0 text-sm text-neutral-400">
                  Ambient textures, quiet rhythms, and room to think.
                </p>
              </FadeIn>
            )}
          </FadeInStagger>
        </DynamicContainer>
      );
  }
}

function DemoControls() {
  const { state, setSize, scheduleAnimation, cancelAnimation } =
    useDynamicIslandSize();
  const cycle = () =>
    setSize(CYCLE[(CYCLE.indexOf(state.size) + 1) % CYCLE.length]);
  return (
    <div className="flex w-full max-w-3xl flex-col items-center gap-6">
      <div
        className="flex flex-wrap items-center justify-center gap-2"
        aria-live="polite"
      >
        <Badge variant="outline">prev · {state.previousSize ?? "none"}</Badge>
        <Badge variant="secondary">cur · {state.size}</Badge>
        {state.isAnimating && <Badge variant="outline">Sequence running</Badge>}
      </div>
      <div className="flex flex-wrap justify-center gap-2">
        <Button variant="outline" onClick={cycle}>
          Cycle states <ArrowRight />
        </Button>
        <Button variant="outline" onClick={() => scheduleAnimation(INTRO)}>
          <Play /> Play sequence
        </Button>
        <Button
          variant="ghost"
          onClick={cancelAnimation}
          disabled={!state.isAnimating}
        >
          <X /> Stop
        </Button>
        <Button variant="ghost" onClick={() => setSize("default")}>
          <RotateCcw /> Reset
        </Button>
      </div>
      <p className="m-0 max-w-md text-center text-sm text-neutral-500">
        Music, uploads, messages, calls, and timers share one surface. Cycle or
        reset at any time to interrupt the sequence.
      </p>
      <div className="flex min-h-64 w-full items-start justify-center py-4">
        <DynamicIsland id="dynamic-island-demo" className="shadow-xl">
          <DynamicContainer key={state.size} className="h-full w-full">
            <IslandContents />
          </DynamicContainer>
        </DynamicIsland>
      </div>
    </div>
  );
}

export function DynamicIslandDemo() {
  return (
    <DynamicIslandProvider initialSize="default">
      <section
        aria-label="Dynamic island interactive demo"
        className="flex w-full justify-center p-4 sm:p-8"
      >
        <DemoControls />
      </section>
    </DynamicIslandProvider>
  );
}

export default DynamicIslandDemo;
