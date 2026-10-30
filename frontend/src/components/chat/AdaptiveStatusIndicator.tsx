import React, { useEffect, useRef, useState } from "react";
import type { GenerationState, GenerationType } from "../../types";

interface AdaptiveStatusIndicatorProps {
  state: GenerationState;
  type?: GenerationType;
  className?: string;
  showAvatar?: boolean;
}

const STATUS_MESSAGES: Record<
  GenerationState,
  {
    chat: string[];
    diff: string[];
    review: string[];
  }
> = {
  idle: {
    chat: ["Ready"],
    diff: ["Ready"],
    review: ["Ready"],
  },
  submitting: {
    chat: ["On it...", "Preparing your response..."],
    diff: ["On it...", "Preparing diff inspection..."],
    review: ["Coordinating review agents...", "Initializing agent workspace..."],
  },
  connecting: {
    chat: ["Connecting to model...", "Establishing inference stream..."],
    diff: ["Connecting to model...", "Loading diff context..."],
    review: ["Connecting to review pipeline...", "Allocating agent processes..."],
  },
  thinking: {
    chat: [
      "Thinking through your question...",
      "Working through the details...",
      "Considering the best approach...",
      "Formulating response...",
    ],
    diff: [
      "Inspecting the changes...",
      "Checking for potential issues...",
      "Reviewing code quality...",
      "Evaluating security and edge cases...",
    ],
    review: [
      "Coordinating review agents...",
      "Inspecting code diff with AST & security analyzers...",
      "Combining agent findings...",
      "Preparing the review summary...",
    ],
  },
  reviewing: {
    chat: [
      "Inspecting the changes...",
      "Checking for potential issues...",
      "Reviewing code quality...",
      "Evaluating security and edge cases...",
    ],
    diff: [
      "Inspecting the changes...",
      "Checking for potential issues...",
      "Reviewing code quality...",
      "Evaluating security and edge cases...",
    ],
    review: [
      "Coordinating review agents...",
      "Inspecting code diff with AST & security analyzers...",
      "Combining agent findings...",
      "Preparing the review summary...",
    ],
  },
  streaming: {
    chat: [
      "Writing the response...",
      "Putting the answer together...",
      "Working through the solution...",
    ],
    diff: [
      "Drafting review findings...",
      "Summarizing code inspection...",
      "Formulating recommendations...",
    ],
    review: [
      "Aggregating findings...",
      "Drafting review report...",
      "Finalizing agent output...",
    ],
  },
  finalizing: {
    chat: ["Finalizing response..."],
    diff: ["Finalizing review..."],
    review: ["Finalizing review summary..."],
  },
  completed: {
    chat: ["Response complete"],
    diff: ["Review complete"],
    review: ["Review complete"],
  },
  cancelled: {
    chat: ["Generation stopped"],
    diff: ["Review stopped"],
    review: ["Review stopped"],
  },
  error: {
    chat: ["Generation halted"],
    diff: ["Review halted"],
    review: ["Review halted"],
  },
};

export const AdaptiveStatusIndicator: React.FC<AdaptiveStatusIndicatorProps> = ({
  state,
  type = "chat",
  className = "",
  showAvatar = true,
}) => {
  const modeKey: "chat" | "diff" | "review" = type === "review" ? "review" : type === "diff" ? "diff" : "chat";
  const messages = STATUS_MESSAGES[state]?.[modeKey] || STATUS_MESSAGES.thinking.chat;

  const [messageIndex, setMessageIndex] = useState(0);
  const [isFading, setIsFading] = useState(false);
  const activeStateRef = useRef(state);
  activeStateRef.current = state;

  useEffect(() => {
    setMessageIndex(0);
    setIsFading(false);
  }, [state, type]);

  useEffect(() => {
    const isRotatingState =
      state === "submitting" ||
      state === "connecting" ||
      state === "thinking" ||
      state === "reviewing" ||
      state === "streaming";

    if (!isRotatingState || messages.length <= 1) {
      return;
    }

    const interval = setInterval(() => {

      setIsFading(true);
      setTimeout(() => {
        setMessageIndex((prev) => (prev + 1) % messages.length);
        setIsFading(false);
      }, 250);
    }, 3800);

    return () => clearInterval(interval);
  }, [state, type, messages.length]);

  const currentText = messages[messageIndex % messages.length];

  const isAnimated =
    state === "submitting" ||
    state === "connecting" ||
    state === "thinking" ||
    state === "reviewing" ||
    state === "streaming";

  return (
    <div className={`flex items-center gap-3.5 ${className}`}>
      {showAvatar && (
        <div className="w-7 h-7 rounded-lg bg-white/10 border border-white/20 flex items-center justify-center flex-shrink-0 select-none">
          <span className="text-[10px] font-bold text-white font-mono">NX</span>
        </div>
      )}

      <div className="px-4 py-3 rounded-2xl bg-black/60 border border-white/10 rounded-tl-sm text-xs text-neutral-400 flex items-center gap-2.5 backdrop-blur-md shadow-sm">
        {isAnimated ? (
          <span className="thinking-dots-container flex-shrink-0" aria-hidden="true">
            <span className="thinking-dot" />
            <span className="thinking-dot" />
            <span className="thinking-dot" />
          </span>
        ) : state === "cancelled" ? (
          <span className="w-2 h-2 rounded-full bg-neutral-500 flex-shrink-0" />
        ) : state === "error" ? (
          <span className="w-2 h-2 rounded-full bg-red-400 flex-shrink-0" />
        ) : (
          <span className="w-2 h-2 rounded-full bg-white/60 flex-shrink-0" />
        )}

        <span
          className={`font-mono text-[11px] text-neutral-400 transition-opacity duration-200 select-none ${
            isFading ? "opacity-0" : "opacity-100"
          }`}
        >
          {currentText}
        </span>
      </div>
    </div>
  );
};
