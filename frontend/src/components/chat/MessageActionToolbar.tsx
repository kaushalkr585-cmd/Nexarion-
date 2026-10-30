import React, { useEffect, useRef, useState } from "react";
import {
  CheckIcon,
  CopyIcon,
  DotsHorizontalIcon,
  FlagIcon,
  MarkdownIcon,
  RegenerateIcon,
  SelectTextIcon,
  ThumbsDownIcon,
  ThumbsUpIcon,
} from "../icons/Icons";

interface MessageActionToolbarProps {
  content: string;
  feedback?: "helpful" | "unhelpful" | null;
  isGenerating?: boolean;
  onRegenerate: () => void;
  onFeedback: (feedback: "helpful" | "unhelpful" | null) => void;
  contentRef?: React.RefObject<HTMLDivElement | null>;
}

export const MessageActionToolbar: React.FC<MessageActionToolbarProps> = ({
  content,
  feedback,
  isGenerating = false,
  onRegenerate,
  onFeedback,
  contentRef,
}) => {
  const [copied, setCopied] = useState(false);
  const [copiedMarkdown, setCopiedMarkdown] = useState(false);
  const [isMenuOpen, setIsMenuOpen] = useState(false);
  const [reported, setReported] = useState(false);
  const menuRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setIsMenuOpen(false);
      }
    };
    if (isMenuOpen) {
      document.addEventListener("mousedown", handleClickOutside);
    }
    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
    };
  }, [isMenuOpen]);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Escape") {
      setIsMenuOpen(false);
    }
  };

  const copyToClipboard = async (text: string): Promise<boolean> => {
    try {
      if (navigator.clipboard && window.isSecureContext) {
        await navigator.clipboard.writeText(text);
        return true;
      }
      const textarea = document.createElement("textarea");
      textarea.value = text;
      textarea.style.position = "fixed";
      textarea.style.opacity = "0";
      document.body.appendChild(textarea);
      textarea.select();
      const success = document.execCommand("copy");
      document.body.removeChild(textarea);
      return success;
    } catch (err) {
      console.error("Clipboard copy error:", err);
      return false;
    }
  };

  const handleCopyResponse = async () => {
    const success = await copyToClipboard(content);
    if (success) {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
      setIsMenuOpen(false);
    }
  };

  const handleCopyMarkdown = async () => {
    const success = await copyToClipboard(content);
    if (success) {
      setCopiedMarkdown(true);
      setTimeout(() => setCopiedMarkdown(false), 2000);
      setIsMenuOpen(false);
    }
  };

  const handleSelectText = () => {
    setIsMenuOpen(false);
    if (contentRef?.current) {
      const selection = window.getSelection();
      const range = document.createRange();
      range.selectNodeContents(contentRef.current);
      selection?.removeAllRanges();
      selection?.addRange(range);
    }
  };

  const handleGoodFeedback = () => {
    onFeedback(feedback === "helpful" ? null : "helpful");
  };

  const handleBadFeedback = () => {
    onFeedback(feedback === "unhelpful" ? null : "unhelpful");
  };

  const handleReport = () => {
    setReported(true);
    setIsMenuOpen(false);
    setTimeout(() => setReported(false), 3000);
  };

  return (
    <div
      className="flex items-center gap-1 mt-2 text-neutral-400 select-none relative"
      onKeyDown={handleKeyDown}
      role="toolbar"
      aria-label="Assistant message actions"
    >

      <button
        type="button"
        onClick={handleCopyResponse}
        aria-label={copied ? "Response copied" : "Copy response"}
        title={copied ? "Copied to clipboard" : "Copy response"}
        className={`flex items-center gap-1 px-1.5 py-1 rounded-md text-[11px] font-mono transition-colors ${
          copied
            ? "text-emerald-400 bg-emerald-500/10"
            : "hover:text-white hover:bg-white/10"
        }`}
      >
        {copied ? (
          <>
            <CheckIcon className="w-3.5 h-3.5 text-emerald-400" />
            <span className="text-[10px] font-medium text-emerald-400">Copied</span>
          </>
        ) : (
          <CopyIcon className="w-3.5 h-3.5" />
        )}
      </button>

      <button
        type="button"
        onClick={handleSelectText}
        aria-label="Select text"
        title="Select response text"
        className="p-1 rounded-md text-neutral-400 hover:text-white hover:bg-white/10 transition-colors"
      >
        <SelectTextIcon className="w-3.5 h-3.5" />
      </button>

      {!isGenerating && (
        <button
          type="button"
          onClick={onRegenerate}
          aria-label="Regenerate response"
          title="Regenerate response"
          className="p-1 rounded-md text-neutral-400 hover:text-white hover:bg-white/10 transition-colors"
        >
          <RegenerateIcon className="w-3.5 h-3.5" />
        </button>
      )}

      <button
        type="button"
        onClick={handleGoodFeedback}
        aria-label="Mark helpful"
        title="Good response"
        className={`p-1 rounded-md transition-colors ${
          feedback === "helpful"
            ? "text-white bg-white/20 border border-white/30"
            : "text-neutral-400 hover:text-white hover:bg-white/10"
        }`}
      >
        <ThumbsUpIcon className="w-3.5 h-3.5" filled={feedback === "helpful"} />
      </button>

      <button
        type="button"
        onClick={handleBadFeedback}
        aria-label="Mark unhelpful"
        title="Bad response"
        className={`p-1 rounded-md transition-colors ${
          feedback === "unhelpful"
            ? "text-white bg-white/20 border border-white/30"
            : "text-neutral-400 hover:text-white hover:bg-white/10"
        }`}
      >
        <ThumbsDownIcon className="w-3.5 h-3.5" filled={feedback === "unhelpful"} />
      </button>

      <div className="relative" ref={menuRef}>
        <button
          type="button"
          onClick={() => setIsMenuOpen(!isMenuOpen)}
          aria-label="More actions"
          aria-haspopup="menu"
          aria-expanded={isMenuOpen}
          title="More actions"
          className={`p-1 rounded-md transition-colors ${
            isMenuOpen
              ? "text-white bg-white/20"
              : "text-neutral-400 hover:text-white hover:bg-white/10"
          }`}
        >
          <DotsHorizontalIcon className="w-3.5 h-3.5" />
        </button>

        {isMenuOpen && (
          <div
            role="menu"
            className="absolute left-0 bottom-full mb-1.5 w-44 rounded-xl bg-[#0D0D0D] border border-white/20 shadow-2xl backdrop-blur-xl p-1 z-50 animate-fade-in text-xs font-mono"
          >
            <button
              type="button"
              role="menuitem"
              onClick={handleCopyResponse}
              className="w-full flex items-center gap-2 px-2.5 py-1.5 rounded-lg text-neutral-300 hover:text-white hover:bg-white/10 transition-colors text-left"
            >
              <CopyIcon className="w-3 h-3 text-neutral-400" />
              <span>Copy response</span>
            </button>

            <button
              type="button"
              role="menuitem"
              onClick={handleCopyMarkdown}
              className="w-full flex items-center gap-2 px-2.5 py-1.5 rounded-lg text-neutral-300 hover:text-white hover:bg-white/10 transition-colors text-left"
            >
              <MarkdownIcon className="w-3 h-3 text-neutral-400" />
              <span>{copiedMarkdown ? "Copied Markdown!" : "Copy as Markdown"}</span>
            </button>

            <button
              type="button"
              role="menuitem"
              onClick={handleSelectText}
              className="w-full flex items-center gap-2 px-2.5 py-1.5 rounded-lg text-neutral-300 hover:text-white hover:bg-white/10 transition-colors text-left"
            >
              <SelectTextIcon className="w-3 h-3 text-neutral-400" />
              <span>Select text</span>
            </button>

            {!isGenerating && (
              <button
                type="button"
                role="menuitem"
                onClick={() => {
                  setIsMenuOpen(false);
                  onRegenerate();
                }}
                className="w-full flex items-center gap-2 px-2.5 py-1.5 rounded-lg text-neutral-300 hover:text-white hover:bg-white/10 transition-colors text-left"
              >
                <RegenerateIcon className="w-3 h-3 text-neutral-400" />
                <span>Regenerate response</span>
              </button>
            )}

            <div className="my-1 border-t border-white/10" />

            <button
              type="button"
              role="menuitem"
              onClick={handleReport}
              className="w-full flex items-center gap-2 px-2.5 py-1.5 rounded-lg text-neutral-400 hover:text-red-300 hover:bg-red-500/10 transition-colors text-left"
            >
              <FlagIcon className="w-3 h-3 text-neutral-400" />
              <span>Report response</span>
            </button>
          </div>
        )}
      </div>

      {reported && (
        <span className="text-[10px] text-neutral-400 font-mono animate-fade-in pl-1">
          Response flagged for review
        </span>
      )}
    </div>
  );
};
