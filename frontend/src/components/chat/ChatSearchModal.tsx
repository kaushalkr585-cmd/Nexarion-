import React, { useEffect, useRef, useState, useCallback } from "react";
import type { ConversationSearchResult } from "../../types";
import { conversationApi } from "../../services/api";
import { CloseIcon, SearchIcon, ChatIcon } from "../icons/Icons";

interface ChatSearchModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSelectConversation: (id: string) => void;
}

/**
 * Renders text with search query occurrences highlighted with a subtle background.
 */
function HighlightMatches({ text, query }: { text: string; query: string }) {
  if (!query.trim() || !text) {
    return <span>{text}</span>;
  }

  const escaped = query.trim().replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const regex = new RegExp(`(${escaped})`, "gi");
  const parts = text.split(regex);

  return (
    <span>
      {parts.map((part, i) =>
        regex.test(part) ? (
          <mark
            key={i}
            className="bg-white/30 text-white font-medium rounded-xs px-0.5"
          >
            {part}
          </mark>
        ) : (
          <span key={i}>{part}</span>
        )
      )}
    </span>
  );
}

function formatRelativeTime(dateStr: string): string {
  try {
    const date = new Date(dateStr);
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffMins = Math.floor(diffMs / 60000);
    const diffHours = Math.floor(diffMins / 60);
    const diffDays = Math.floor(diffHours / 24);

    if (diffMins < 1) return "Just now";
    if (diffMins < 60) return `${diffMins}m ago`;
    if (diffHours < 24) return `${diffHours}h ago`;
    if (diffDays === 1) return "Yesterday";
    if (diffDays < 7) return `${diffDays}d ago`;

    return date.toLocaleDateString(undefined, {
      month: "short",
      day: "numeric",
      year: date.getFullYear() !== now.getFullYear() ? "numeric" : undefined,
    });
  } catch {
    return dateStr;
  }
}

export const ChatSearchModal: React.FC<ChatSearchModalProps> = ({
  isOpen,
  onClose,
  onSelectConversation,
}) => {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<ConversationSearchResult[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [selectedIndex, setSelectedIndex] = useState(0);
  const [hasSearched, setHasSearched] = useState(false);

  const inputRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLDivElement>(null);
  const debounceTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Focus input whenever modal opens
  useEffect(() => {
    if (isOpen) {
      setQuery("");
      setResults([]);
      setSelectedIndex(0);
      setHasSearched(false);
      setTimeout(() => {
        inputRef.current?.focus();
      }, 50);
    }
  }, [isOpen]);

  // Debounced search
  useEffect(() => {
    if (!isOpen) return;

    const trimmed = query.trim();
    if (!trimmed) {
      setResults([]);
      setIsLoading(false);
      setHasSearched(false);
      setSelectedIndex(0);
      return;
    }

    setIsLoading(true);
    if (debounceTimerRef.current) {
      clearTimeout(debounceTimerRef.current);
    }

    debounceTimerRef.current = setTimeout(async () => {
      try {
        const data = await conversationApi.search(trimmed, 25);
        setResults(data);
        setSelectedIndex(0);
        setHasSearched(true);
      } catch (err) {
        console.error("Conversation search failed:", err);
        setResults([]);
        setHasSearched(true);
      } finally {
        setIsLoading(false);
      }
    }, 200);

    return () => {
      if (debounceTimerRef.current) {
        clearTimeout(debounceTimerRef.current);
      }
    };
  }, [query, isOpen]);

  // Handle keyboard navigation
  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Escape") {
      e.preventDefault();
      onClose();
    } else if (e.key === "ArrowDown") {
      e.preventDefault();
      setSelectedIndex((prev) =>
        results.length > 0 ? (prev + 1) % results.length : 0
      );
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setSelectedIndex((prev) =>
        results.length > 0 ? (prev - 1 + results.length) % results.length : 0
      );
    } else if (e.key === "Enter") {
      e.preventDefault();
      if (results.length > 0 && results[selectedIndex]) {
        handleSelect(results[selectedIndex].id);
      }
    }
  };

  // Scroll active item into view
  useEffect(() => {
    if (listRef.current) {
      const activeEl = listRef.current.querySelector(
        `[data-index="${selectedIndex}"]`
      ) as HTMLElement | null;
      if (activeEl) {
        activeEl.scrollIntoView({ block: "nearest" });
      }
    }
  }, [selectedIndex]);

  const handleSelect = useCallback(
    (id: string) => {
      onSelectConversation(id);
      onClose();
    },
    [onSelectConversation, onClose]
  );

  if (!isOpen) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center p-3 sm:p-4 pt-12 sm:pt-20 bg-black/80 backdrop-blur-md animate-fade-in"
      onClick={onClose}
      aria-label="Search conversation history"
      role="dialog"
      aria-modal="true"
    >
      <div
        className="relative w-full max-w-2xl rounded-2xl bg-[#0E0E0E] border border-white/20 shadow-2xl flex flex-col overflow-hidden max-h-[80vh] sm:max-h-[75vh]"
        onClick={(e) => e.stopPropagation()}
        onKeyDown={handleKeyDown}
      >
        {/* Search Input Bar */}
        <div className="flex items-center gap-3 px-4 py-3.5 border-b border-white/10 bg-white/[0.02]">
          <SearchIcon className="w-5 h-5 text-neutral-400 flex-shrink-0" />
          <input
            ref={inputRef}
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search chats by title or message..."
            className="flex-1 bg-transparent text-white placeholder-neutral-500 text-sm sm:text-base focus:outline-none"
            aria-label="Search conversations"
          />

          {isLoading ? (
            <div className="w-5 h-5 flex items-center justify-center">
              <svg
                className="animate-spin h-4 w-4 text-neutral-400"
                viewBox="0 0 24 24"
                fill="none"
              >
                <circle
                  className="opacity-25"
                  cx="12"
                  cy="12"
                  r="10"
                  stroke="currentColor"
                  strokeWidth="3"
                />
                <path
                  className="opacity-75"
                  fill="currentColor"
                  d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z"
                />
              </svg>
            </div>
          ) : query.length > 0 ? (
            <button
              type="button"
              onClick={() => {
                setQuery("");
                inputRef.current?.focus();
              }}
              className="p-1 text-neutral-400 hover:text-white rounded-md hover:bg-white/10 transition-colors cursor-pointer"
              title="Clear search"
              aria-label="Clear search"
            >
              <CloseIcon className="w-4 h-4" />
            </button>
          ) : (
            <kbd className="hidden sm:inline-flex items-center px-1.5 py-0.5 text-[11px] font-mono text-neutral-500 bg-white/5 rounded border border-white/10">
              ESC
            </kbd>
          )}
        </div>

        {/* Results / Empty States */}
        <div
          ref={listRef}
          className="flex-1 overflow-y-auto overscroll-contain p-2 sm:p-2.5 divide-y divide-white/5 space-y-1"
        >
          {query.trim().length === 0 ? (
            <div className="py-12 px-4 text-center">
              <div className="w-10 h-10 rounded-full bg-white/5 border border-white/10 flex items-center justify-center mx-auto mb-3 text-neutral-400">
                <SearchIcon className="w-5 h-5" />
              </div>
              <h3 className="text-sm font-medium text-white mb-1">
                Search your conversations
              </h3>
              <p className="text-xs text-neutral-400 max-w-sm mx-auto leading-relaxed">
                Find past discussions, code reviews, prompts, and AI responses by typing keywords.
              </p>
              <div className="mt-4 flex items-center justify-center gap-3 text-[11px] text-neutral-500 font-mono">
                <span>↑↓ Navigate</span>
                <span>•</span>
                <span>Enter to select</span>
                <span>•</span>
                <span>Esc to close</span>
              </div>
            </div>
          ) : results.length === 0 && hasSearched && !isLoading ? (
            <div className="py-12 px-4 text-center">
              <div className="w-10 h-10 rounded-full bg-white/5 border border-white/10 flex items-center justify-center mx-auto mb-3 text-neutral-400">
                <ChatIcon className="w-5 h-5" />
              </div>
              <h3 className="text-sm font-medium text-white mb-1">
                No conversations found
              </h3>
              <p className="text-xs text-neutral-400 max-w-sm mx-auto leading-relaxed">
                No chats matched <span className="text-white font-mono">"{query.trim()}"</span>. Try searching for other terms or topics.
              </p>
            </div>
          ) : (
            results.map((item, idx) => {
              const isSelected = idx === selectedIndex;
              return (
                <div
                  key={item.id}
                  data-index={idx}
                  onClick={() => handleSelect(item.id)}
                  onMouseEnter={() => setSelectedIndex(idx)}
                  className={`w-full p-3 rounded-xl text-left transition-colors cursor-pointer group flex flex-col gap-1.5 ${
                    isSelected
                      ? "bg-white/10 border border-white/15"
                      : "hover:bg-white/5 border border-transparent"
                  }`}
                  role="button"
                  tabIndex={0}
                >
                  <div className="flex items-center justify-between gap-2">
                    <div className="flex items-center gap-2 min-w-0">
                      <ChatIcon
                        className={`w-4 h-4 flex-shrink-0 ${
                          isSelected ? "text-white" : "text-neutral-400"
                        }`}
                      />
                      <span className="text-sm font-medium text-white truncate">
                        <HighlightMatches text={item.title} query={query} />
                      </span>
                    </div>

                    <div className="flex items-center gap-2 flex-shrink-0 text-[11px] text-neutral-400 font-mono">
                      {item.role && (
                        <span
                          className={`px-1.5 py-0.5 rounded text-[10px] uppercase font-sans font-medium ${
                            item.role === "user"
                              ? "bg-blue-500/15 text-blue-300 border border-blue-500/20"
                              : "bg-emerald-500/15 text-emerald-300 border border-emerald-500/20"
                          }`}
                        >
                          {item.role === "user" ? "You" : "Nexarion"}
                        </span>
                      )}
                      <span>{formatRelativeTime(item.updated_at || item.created_at)}</span>
                    </div>
                  </div>

                  {item.snippet && item.snippet !== item.title && (
                    <div className="text-xs text-neutral-400 line-clamp-2 pl-6 font-mono leading-relaxed group-hover:text-neutral-300">
                      <HighlightMatches text={item.snippet} query={query} />
                    </div>
                  )}
                </div>
              );
            })
          )}
        </div>

        {/* Footer shortcuts hint */}
        {results.length > 0 && (
          <div className="px-4 py-2 bg-white/[0.02] border-t border-white/10 flex items-center justify-between text-[11px] text-neutral-500 font-mono">
            <span>
              {results.length} conversation{results.length === 1 ? "" : "s"} found
            </span>
            <div className="hidden sm:flex items-center gap-3">
              <span>↑↓ Navigate</span>
              <span>•</span>
              <span>Enter Open</span>
              <span>•</span>
              <span>Esc Close</span>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};
