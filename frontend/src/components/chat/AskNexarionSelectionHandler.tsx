import React, { useEffect, useRef, useState, useCallback } from "react";
import { LogoIcon } from "../icons/Icons";
import { formatSelectionPrompt, isTargetExcluded } from "../../utils/selectionPrompt";

export { formatSelectionPrompt, isTargetExcluded };

export interface SelectionPosition {
  top: number;
  left: number;
  text: string;
  isBelow: boolean;
}

interface AskNexarionSelectionHandlerProps {
  onAskNexarion: (selectedText: string) => void;
  maxSelectionLength?: number;
  minSelectionLength?: number;
}

export const AskNexarionSelectionHandler: React.FC<AskNexarionSelectionHandlerProps> = ({
  onAskNexarion,
  maxSelectionLength = 10000,
  minSelectionLength = 3,
}) => {
  const [position, setPosition] = useState<SelectionPosition | null>(null);
  const buttonRef = useRef<HTMLDivElement | null>(null);
  const isInteractingRef = useRef<boolean>(false);

  const hideButton = useCallback(() => {
    if (!isInteractingRef.current) {
      setPosition(null);
    }
  }, []);

  const calculatePosition = useCallback(() => {
    const selection = window.getSelection();
    if (!selection || selection.isCollapsed || selection.rangeCount === 0) {
      hideButton();
      return;
    }

    const rawText = selection.toString();
    const text = rawText.trim();

    if (!text || text.length < minSelectionLength || text.length > maxSelectionLength) {
      hideButton();
      return;
    }

    const range = selection.getRangeAt(0);
    const container = range.commonAncestorContainer;

    if (isTargetExcluded(container)) {
      hideButton();
      return;
    }

    const rect = range.getBoundingClientRect();
    if (rect.width === 0 && rect.height === 0) {
      hideButton();
      return;
    }

    const buttonWidth = 148;
    const buttonHeight = 36;
    const spacing = 8;

    let left = rect.left + rect.width / 2 - buttonWidth / 2;

    left = Math.max(12, Math.min(left, window.innerWidth - buttonWidth - 12));

    let top = rect.top - buttonHeight - spacing;
    let isBelow = false;
    if (top < 10) {
      top = rect.bottom + spacing;
      isBelow = true;
    }

    top = Math.max(8, Math.min(top, window.innerHeight - buttonHeight - 8));

    setPosition({ top, left, text, isBelow });
  }, [minSelectionLength, maxSelectionLength, hideButton]);

  useEffect(() => {
    const handleMouseUp = () => {

      setTimeout(calculatePosition, 20);
    };

    const handleKeyUp = (e: KeyboardEvent) => {
      if (e.key === "Shift" || e.key.startsWith("Arrow")) {
        setTimeout(calculatePosition, 20);
      }
    };

    const handleSelectionChange = () => {
      const selection = window.getSelection();
      if (!selection || selection.isCollapsed) {
        hideButton();
      }
    };

    document.addEventListener("mouseup", handleMouseUp);
    document.addEventListener("keyup", handleKeyUp);
    document.addEventListener("touchend", handleMouseUp);
    document.addEventListener("selectionchange", handleSelectionChange);

    return () => {
      document.removeEventListener("mouseup", handleMouseUp);
      document.removeEventListener("keyup", handleKeyUp);
      document.removeEventListener("touchend", handleMouseUp);
      document.removeEventListener("selectionchange", handleSelectionChange);
    };
  }, [calculatePosition, hideButton]);

  useEffect(() => {
    const handleScrollOrResize = () => {
      if (!position) return;
      const selection = window.getSelection();
      if (!selection || selection.isCollapsed || selection.rangeCount === 0) {
        hideButton();
        return;
      }
      const range = selection.getRangeAt(0);
      const rect = range.getBoundingClientRect();

      if (
        rect.bottom < 0 ||
        rect.top > window.innerHeight ||
        rect.right < 0 ||
        rect.left > window.innerWidth
      ) {
        hideButton();
        return;
      }

      calculatePosition();
    };

    window.addEventListener("scroll", handleScrollOrResize, { capture: true, passive: true });
    window.addEventListener("resize", handleScrollOrResize, { passive: true });

    return () => {
      window.removeEventListener("scroll", handleScrollOrResize, { capture: true });
      window.removeEventListener("resize", handleScrollOrResize);
    };
  }, [position, calculatePosition, hideButton]);

  useEffect(() => {
    const handleMouseDown = (e: MouseEvent) => {
      const target = e.target as HTMLElement | null;
      if (target && target.closest(".ask-nexarion-floating-btn")) {

        return;
      }
      hideButton();
    };

    document.addEventListener("mousedown", handleMouseDown);
    return () => {
      document.removeEventListener("mousedown", handleMouseDown);
    };
  }, [hideButton]);

  if (!position) return null;

  const handleAction = () => {
    isInteractingRef.current = true;
    onAskNexarion(position.text);
    setPosition(null);
    try {
      window.getSelection()?.removeAllRanges();
    } catch {

    }
    setTimeout(() => {
      isInteractingRef.current = false;
    }, 100);
  };

  return (
    <div
      ref={buttonRef}
      role="button"
      tabIndex={0}
      aria-label="Ask Nexarion about selected text"

      onMouseDown={(e) => {
        e.preventDefault();
        e.stopPropagation();
      }}
      onClick={(e) => {
        e.preventDefault();
        e.stopPropagation();
        handleAction();
      }}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          handleAction();
        } else if (e.key === "Escape") {
          e.preventDefault();
          setPosition(null);
        }
      }}
      style={{
        top: `${position.top}px`,
        left: `${position.left}px`,
      }}
      className="ask-nexarion-floating-btn fixed z-50 inline-flex items-center gap-2 px-3 py-1.5 rounded-full bg-[#111113]/95 text-white text-xs font-medium border border-white/20 hover:border-white/40 hover:bg-[#1f1f23] shadow-2xl backdrop-blur-md cursor-pointer transition-all duration-150 transform hover:scale-105 active:scale-95 animate-fade-in select-none"
    >
      <LogoIcon className="w-3.5 h-3.5 flex-shrink-0" />
      <span className="whitespace-nowrap font-sans font-medium text-xs tracking-tight">
        Ask Nexarion
      </span>
      <span className="text-[10px] text-neutral-400 font-mono ml-0.5" aria-hidden="true">
        ↵
      </span>
    </div>
  );
};
