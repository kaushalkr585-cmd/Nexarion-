import React, { useCallback, useEffect, useRef, useState } from "react";
import { ArrowUpIcon, CloseIcon, SparkleIcon } from "../icons/Icons";

export interface SelectionCoordinates {
  top: number;
  left: number;
  placement: "above" | "below";
}

export interface ValidChatSelection {
  text: string;
  messageId?: string;
  rect: {
    top: number;
    bottom: number;
    left: number;
    width: number;
    height: number;
  };
}

const IGNORED_SELECTOR = [
  "pre",
  "[data-code-block='true']",
  "[data-ask-nexarion-ignore='true']",
  "input",
  "textarea",
  "[contenteditable='true']",
  "button",
  "[role='toolbar']",
].join(", ");

const SELECTABLE_BUBBLE_SELECTOR = "[data-ask-nexarion-selectable='true']";

function getClosestElement(node: Node | null): HTMLElement | null {
  if (!node) return null;
  if (node.nodeType === 1) return node as HTMLElement;
  return (node as { parentElement?: HTMLElement | null }).parentElement || null;
}

export function isNodeIgnoredForAskNexarion(node: Node | null): boolean {
  const el = getClosestElement(node);
  if (!el || typeof el.closest !== "function") return true;
  return Boolean(el.closest(IGNORED_SELECTOR));
}

export function extractValidChatSelection(
  selection: Selection | null,
  container: HTMLElement | null
): ValidChatSelection | null {
  if (!container || !selection || selection.isCollapsed || selection.rangeCount === 0) {
    return null;
  }

  const activeEl = typeof document !== "undefined" ? (document.activeElement as HTMLElement | null) : null;
  if (
    activeEl &&
    (activeEl.tagName === "INPUT" ||
      activeEl.tagName === "TEXTAREA" ||
      activeEl.isContentEditable)
  ) {
    return null;
  }

  const text = selection.toString().trim();
  if (text.length < 2 || text.length > 4000) {
    return null;
  }

  const range = selection.getRangeAt(0);
  const startNode = range.startContainer;
  const endNode = range.endContainer;
  const ancestorNode = range.commonAncestorContainer;

  if (
    !container.contains(startNode) ||
    !container.contains(endNode) ||
    !container.contains(ancestorNode)
  ) {
    return null;
  }

  const startEl = getClosestElement(startNode);
  const endEl = getClosestElement(endNode);
  if (!startEl || !endEl) return null;

  const startBubble = startEl.closest(SELECTABLE_BUBBLE_SELECTOR) as HTMLElement | null;
  const endBubble = endEl.closest(SELECTABLE_BUBBLE_SELECTOR) as HTMLElement | null;
  if (!startBubble || !endBubble || startBubble !== endBubble) {
    return null;
  }

  if (isNodeIgnoredForAskNexarion(startNode) || isNodeIgnoredForAskNexarion(endNode)) {
    return null;
  }

  if (typeof range.intersectsNode === "function") {
    const ignoredDescendants = startBubble.querySelectorAll(
      "[data-code-block='true'], pre, [data-ask-nexarion-ignore='true']"
    );
    for (const ignored of Array.from(ignoredDescendants)) {
      if (range.intersectsNode(ignored)) {
        // Reject when selection is inside or spans across a code block or ignored UI
        return null;
      }
    }
  }

  const rawRect = range.getBoundingClientRect();
  if (!rawRect || (rawRect.width === 0 && rawRect.height === 0)) {
    return null;
  }

  return {
    text,
    messageId: startBubble.getAttribute("data-message-id") || undefined,
    rect: {
      top: rawRect.top,
      bottom: rawRect.bottom,
      left: rawRect.left,
      width: rawRect.width,
      height: rawRect.height,
    },
  };
}

export function computeFloatingCoordinates(
  rect: { top: number; bottom: number; left: number; width: number; height: number },
  viewport: { width: number; height: number },
  overlay: { width: number; height: number }
): SelectionCoordinates {
  const safeMargin = 12;
  const headerClearance = 70;
  const gap = 10;

  let placement: "above" | "below" = "above";
  let top = rect.top - overlay.height - gap;

  if (top < headerClearance) {
    const belowTop = rect.bottom + gap;
    if (belowTop + overlay.height <= viewport.height - safeMargin || belowTop > top) {
      placement = "below";
      top = belowTop;
    }
  }

  const maxTop = Math.max(headerClearance, viewport.height - overlay.height - safeMargin);
  top = Math.max(headerClearance, Math.min(top, maxTop));

  const centeredLeft = rect.left + rect.width / 2 - overlay.width / 2;
  const maxLeft = Math.max(safeMargin, viewport.width - overlay.width - safeMargin);
  const left = Math.max(safeMargin, Math.min(centeredLeft, maxLeft));

  return { top, left, placement };
}

interface AskNexarionSelectionHandlerProps {
  containerRef: React.RefObject<HTMLDivElement | null>;
  conversationId?: string;
  disabled?: boolean;
  onSubmitQuestion: (payload: {
    question: string;
    selectedText: string;
    messageId?: string;
  }) => void;
}

export const AskNexarionSelectionHandler: React.FC<AskNexarionSelectionHandlerProps> = ({
  containerRef,
  conversationId,
  disabled = false,
  onSubmitQuestion,
}) => {
  const [phase, setPhase] = useState<"closed" | "button" | "prompt">("closed");
  const [selectedText, setSelectedText] = useState("");
  const [selectedMessageId, setSelectedMessageId] = useState<string | undefined>(undefined);
  const [coords, setCoords] = useState<SelectionCoordinates>({
    top: 100,
    left: 100,
    placement: "above",
  });
  const [question, setQuestion] = useState("");

  const overlayRef = useRef<HTMLDivElement | null>(null);
  const inputRef = useRef<HTMLTextAreaElement | null>(null);
  const touchActiveRef = useRef(false);
  const debounceTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const clearTimer = () => {
    if (debounceTimerRef.current) {
      clearTimeout(debounceTimerRef.current);
      debounceTimerRef.current = null;
    }
  };

  const resetOverlay = useCallback(() => {
    clearTimer();
    setPhase("closed");
    setSelectedText("");
    setSelectedMessageId(undefined);
    setQuestion("");
  }, []);

  useEffect(() => {
    resetOverlay();
  }, [conversationId, disabled, resetOverlay]);

  const evaluateSelectionNow = useCallback(() => {
    if (disabled) {
      resetOverlay();
      return;
    }

    const container = containerRef.current;
    if (!container) return;

    const sel = typeof window !== "undefined" ? window.getSelection() : null;
    const valid = extractValidChatSelection(sel, container);

    if (!valid) {
      setPhase((current) => (current === "prompt" ? current : "closed"));
      return;
    }

    const vw = typeof window !== "undefined" ? window.innerWidth : 1024;
    const vh = typeof window !== "undefined" ? window.innerHeight : 768;
    const nextCoords = computeFloatingCoordinates(
      valid.rect,
      { width: vw, height: vh },
      { width: 136, height: 36 }
    );

    setSelectedText(valid.text);
    setSelectedMessageId(valid.messageId);
    setCoords(nextCoords);
    setPhase("button");
  }, [containerRef, disabled, resetOverlay]);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const scheduleEval = (delayMs: number) => {
      clearTimer();
      debounceTimerRef.current = setTimeout(() => {
        evaluateSelectionNow();
      }, delayMs);
    };

    const handleMouseUp = () => {
      touchActiveRef.current = false;
      scheduleEval(20);
    };

    const handleTouchStart = () => {
      touchActiveRef.current = true;
    };

    const handleTouchEnd = () => {
      touchActiveRef.current = true;
      scheduleEval(180);
    };

    const handleKeyUp = (e: KeyboardEvent) => {
      if (e.shiftKey || e.key === "Shift") {
        scheduleEval(20);
      }
    };

    const handleScroll = () => {
      setPhase((current) => (current === "button" ? "closed" : current));
    };

    container.addEventListener("mouseup", handleMouseUp);
    container.addEventListener("touchstart", handleTouchStart, { passive: true });
    container.addEventListener("touchend", handleTouchEnd, { passive: true });
    container.addEventListener("keyup", handleKeyUp);
    container.addEventListener("scroll", handleScroll, { passive: true });

    const handleSelectionChange = () => {
      if (!touchActiveRef.current) return;
      scheduleEval(180);
    };
    document.addEventListener("selectionchange", handleSelectionChange);

    return () => {
      clearTimer();
      container.removeEventListener("mouseup", handleMouseUp);
      container.removeEventListener("touchstart", handleTouchStart);
      container.removeEventListener("touchend", handleTouchEnd);
      container.removeEventListener("keyup", handleKeyUp);
      container.removeEventListener("scroll", handleScroll);
      document.removeEventListener("selectionchange", handleSelectionChange);
    };
  }, [containerRef, evaluateSelectionNow]);

  useEffect(() => {
    if (phase === "closed") return;

    const handleOutsidePointer = (e: MouseEvent | TouchEvent) => {
      const target = e.target as Node | null;
      if (overlayRef.current && target && overlayRef.current.contains(target)) {
        return;
      }
      if (phase === "button") {
        const container = containerRef.current;
        if (container && target && container.contains(target)) {
          return;
        }
      }
      resetOverlay();
    };

    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        resetOverlay();
      }
    };

    document.addEventListener("mousedown", handleOutsidePointer);
    document.addEventListener("touchstart", handleOutsidePointer, { passive: true });
    window.addEventListener("keydown", handleEscape);

    return () => {
      document.removeEventListener("mousedown", handleOutsidePointer);
      document.removeEventListener("touchstart", handleOutsidePointer);
      window.removeEventListener("keydown", handleEscape);
    };
  }, [phase, containerRef, resetOverlay]);

  useEffect(() => {
    if (phase === "prompt" && inputRef.current) {
      inputRef.current.focus();
    }
  }, [phase]);

  if (phase === "closed" || !selectedText) {
    return null;
  }

  const handleOpenPrompt = (e: React.MouseEvent | React.TouchEvent) => {
    e.preventDefault();
    e.stopPropagation();

    const vw = typeof window !== "undefined" ? window.innerWidth : 1024;
    const vh = typeof window !== "undefined" ? window.innerHeight : 768;
    const promptWidth = Math.min(360, vw - 24);
    const promptHeight = 230;
    const sel = typeof window !== "undefined" ? window.getSelection() : null;
    const liveRect =
      sel && sel.rangeCount > 0 && !sel.isCollapsed
        ? sel.getRangeAt(0).getBoundingClientRect()
        : { top: coords.top, bottom: coords.top + 36, left: coords.left, width: 120, height: 24 };

    const promptCoords = computeFloatingCoordinates(
      liveRect,
      { width: vw, height: vh },
      { width: promptWidth, height: promptHeight }
    );
    setCoords(promptCoords);
    setPhase("prompt");
  };

  const submitContextual = (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    const cleanQuestion = question.trim();
    if (!cleanQuestion || !selectedText.trim() || disabled) return;

    onSubmitQuestion({
      question: cleanQuestion,
      selectedText: selectedText.trim(),
      messageId: selectedMessageId,
    });
    if (typeof window !== "undefined") {
      window.getSelection()?.removeAllRanges();
    }
    resetOverlay();
  };

  if (phase === "button") {
    return (
      <div
        ref={overlayRef}
        data-ask-nexarion-overlay="button"
        style={{ top: `${coords.top}px`, left: `${coords.left}px` }}
        className="fixed z-40 animate-fade-in select-none"
      >
        <button
          type="button"
          onMouseDown={(e) => e.preventDefault()}
          onClick={handleOpenPrompt}
          onTouchEnd={handleOpenPrompt}
          data-testid="ask-nexarion-floating-btn"
          className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-[#121212]/95 hover:bg-[#1E1E1E] text-white border border-white/25 hover:border-white/45 shadow-2xl backdrop-blur-md text-xs font-medium tracking-tight transition-all cursor-pointer"
        >
          <SparkleIcon className="w-3.5 h-3.5 text-amber-300 shrink-0" />
          <span>Ask Nexarion</span>
        </button>
      </div>
    );
  }

  return (
    <div
      ref={overlayRef}
      data-ask-nexarion-overlay="prompt"
      style={{ top: `${coords.top}px`, left: `${coords.left}px`, width: "min(360px, calc(100vw - 24px))" }}
      className="fixed z-40 rounded-2xl bg-[#101010]/98 border border-white/20 shadow-2xl backdrop-blur-xl p-3.5 space-y-3 animate-fade-in text-left"
      role="dialog"
      aria-label="Ask Nexarion about selected text"
    >
      <div className="flex items-center justify-between gap-2 pb-2 border-b border-white/10">
        <div className="flex items-center gap-1.5 text-xs font-semibold text-white">
          <SparkleIcon className="w-3.5 h-3.5 text-amber-300 shrink-0" />
          <span>Ask Nexarion</span>
        </div>
        <button
          type="button"
          onClick={resetOverlay}
          aria-label="Close contextual prompt"
          className="p-1 rounded-md text-neutral-400 hover:text-white hover:bg-white/10 transition-colors cursor-pointer"
        >
          <CloseIcon className="w-3.5 h-3.5" />
        </button>
      </div>

      <div className="max-h-24 overflow-y-auto pl-2.5 border-l-2 border-white/35 text-[11px] text-neutral-300 leading-relaxed italic">
        &ldquo;{selectedText}&rdquo;
      </div>

      <form onSubmit={submitContextual} className="space-y-2.5">
        <textarea
          ref={inputRef}
          rows={2}
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              submitContextual();
            }
          }}
          placeholder="Ask about this selected text..."
          className="w-full bg-black/75 border border-white/15 rounded-xl px-3 py-2 text-xs text-white placeholder-neutral-500 resize-none focus:outline-none focus:border-white/40"
        />

        <div className="flex items-center justify-between gap-2">
          <button
            type="button"
            onClick={resetOverlay}
            className="px-2.5 py-1.5 rounded-lg text-[11px] font-mono text-neutral-400 hover:text-white hover:bg-white/10 transition-colors cursor-pointer"
          >
            Cancel
          </button>
          <button
            type="submit"
            disabled={!question.trim() || disabled}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-white text-black hover:bg-neutral-200 text-xs font-semibold transition-colors disabled:opacity-35 disabled:cursor-not-allowed cursor-pointer"
          >
            <span>Ask</span>
            <ArrowUpIcon className="w-3.5 h-3.5" />
          </button>
        </div>
      </form>
    </div>
  );
};
