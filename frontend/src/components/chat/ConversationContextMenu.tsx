import React, { useEffect, useRef, useState } from "react";
import type { Conversation } from "../../types";

interface ConversationContextMenuProps {
  conversation: Conversation;
  triggerRect: DOMRect;
  onClose: () => void;
  onRename: (conversation: Conversation) => void;
  onTogglePin: (conversation: Conversation) => void;
  onSetSection: (conversation: Conversation, sectionName: string | null) => void;
  onShare: (conversation: Conversation) => void;
  onArchive: (conversation: Conversation) => void;
  onUnarchive?: (conversation: Conversation) => void;
  onDelete: (conversation: Conversation) => void;
  existingSections: string[];
}

export const ConversationContextMenu: React.FC<ConversationContextMenuProps> = ({
  conversation,
  triggerRect,
  onClose,
  onRename,
  onTogglePin,
  onSetSection,
  onShare,
  onArchive,
  onUnarchive,
  onDelete,
  existingSections,
}) => {
  const menuRef = useRef<HTMLDivElement>(null);
  const [showSectionSubmenu, setShowSectionSubmenu] = useState(false);
  const [isCreatingSection, setIsCreatingSection] = useState(false);
  const [newSectionName, setNewSectionName] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);

  const menuWidth = 210;
  const menuHeight = 260;
  let top = triggerRect.bottom + 4;
  let left = triggerRect.left;

  if (top + menuHeight > window.innerHeight - 10) {
    top = Math.max(10, triggerRect.top - menuHeight - 4);
  }

  if (left + menuWidth > window.innerWidth - 10) {
    left = Math.max(10, window.innerWidth - menuWidth - 10);
  }

  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        onClose();
      }
    };

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        onClose();
      }
    };

    const handleScroll = () => {
      onClose();
    };

    document.addEventListener("mousedown", handleClickOutside);
    document.addEventListener("keydown", handleKeyDown);
    window.addEventListener("scroll", handleScroll, true);

    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
      document.removeEventListener("keydown", handleKeyDown);
      window.removeEventListener("scroll", handleScroll, true);
    };
  }, [onClose]);

  useEffect(() => {
    if (isCreatingSection && inputRef.current) {
      inputRef.current.focus();
    }
  }, [isCreatingSection]);

  const handleCreateSectionSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const trimmed = newSectionName.trim();
    if (trimmed) {
      onSetSection(conversation, trimmed);
      onClose();
    }
  };

  return (
    <div
      ref={menuRef}
      style={{ top: `${top}px`, left: `${left}px` }}
      className="fixed z-[100] w-[210px] bg-[#171717] border border-white/12 rounded-xl shadow-2xl p-1 text-xs text-neutral-200 select-none animate-in fade-in zoom-in-95 duration-100"
      role="menu"
      aria-label="Conversation actions"
    >

      <button
        type="button"
        role="menuitem"
        onClick={() => {
          onRename(conversation);
          onClose();
        }}
        className="w-full flex items-center gap-2.5 px-2.5 py-1.5 rounded-lg text-left hover:bg-white/10 hover:text-white transition-colors cursor-pointer group"
      >
        <svg
          className="w-3.5 h-3.5 text-neutral-400 group-hover:text-white transition-colors"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          <path d="M17 3a2.828 2.828 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5L17 3z" />
        </svg>
        <span>Rename</span>
      </button>

      <button
        type="button"
        role="menuitem"
        onClick={() => {
          onTogglePin(conversation);
          onClose();
        }}
        className="w-full flex items-center gap-2.5 px-2.5 py-1.5 rounded-lg text-left hover:bg-white/10 hover:text-white transition-colors cursor-pointer group"
      >
        <svg
          className="w-3.5 h-3.5 text-neutral-400 group-hover:text-white transition-colors"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          <line x1="12" y1="17" x2="12" y2="22" />
          <path d="M5 17h14v-1.76a2 2 0 0 0-1.11-1.79l-1.78-.89A4 4 0 0 1 14 9V5a2 2 0 0 0-2-2h0a2 2 0 0 0-2 2v4a4 4 0 0 1-2.11 3.56l-1.78.89A2 2 0 0 0 5 15.24Z" />
        </svg>
        <span>{conversation.is_pinned ? "Unpin" : "Pin"}</span>
      </button>

      <div
        className="relative"
        onMouseEnter={() => setShowSectionSubmenu(true)}
        onMouseLeave={() => {
          if (!isCreatingSection) setShowSectionSubmenu(false);
        }}
      >
        <button
          type="button"
          role="menuitem"
          aria-haspopup="true"
          aria-expanded={showSectionSubmenu}
          onClick={() => setShowSectionSubmenu(!showSectionSubmenu)}
          className="w-full flex items-center justify-between px-2.5 py-1.5 rounded-lg text-left hover:bg-white/10 hover:text-white transition-colors cursor-pointer group"
        >
          <div className="flex items-center gap-2.5">
            <svg
              className="w-3.5 h-3.5 text-neutral-400 group-hover:text-white transition-colors"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z" />
            </svg>
            <span>Section</span>
          </div>
          <svg
            className="w-3.5 h-3.5 text-neutral-500 group-hover:text-neutral-300"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <polyline points="9 18 15 12 9 6" />
          </svg>
        </button>

        {showSectionSubmenu && (
          <div
            className="absolute left-full top-0 ml-1.5 w-[190px] bg-[#171717] border border-white/12 rounded-xl shadow-2xl p-1 text-xs text-neutral-200 z-[110] animate-in fade-in duration-75"
            role="menu"
            aria-label="Section options"
          >
            <div className="px-2 py-1 text-[10px] font-mono uppercase text-neutral-500 tracking-wider">
              {conversation.section_name ? `Current: ${conversation.section_name}` : "Assign to section"}
            </div>

            {existingSections.length > 0 && (
              <div className="max-h-36 overflow-y-auto space-y-0.5 py-0.5 border-b border-white/10 mb-1">
                {existingSections.map((sec) => (
                  <button
                    key={sec}
                    type="button"
                    onClick={() => {
                      onSetSection(conversation, sec);
                      onClose();
                    }}
                    className={`w-full flex items-center justify-between px-2 py-1.5 rounded-lg text-left transition-colors cursor-pointer ${
                      conversation.section_name === sec
                        ? "bg-white/15 text-white font-medium"
                        : "hover:bg-white/10 text-neutral-300 hover:text-white"
                    }`}
                  >
                    <span className="truncate">{sec}</span>
                    {conversation.section_name === sec && (
                      <span className="text-[10px] text-white">✓</span>
                    )}
                  </button>
                ))}
              </div>
            )}

            {isCreatingSection ? (
              <form onSubmit={handleCreateSectionSubmit} className="p-1">
                <input
                  ref={inputRef}
                  type="text"
                  value={newSectionName}
                  onChange={(e) => setNewSectionName(e.target.value)}
                  placeholder="Section name..."
                  maxLength={50}
                  className="w-full px-2 py-1 bg-black/60 border border-white/20 rounded text-xs text-white placeholder-neutral-500 focus:outline-none focus:border-white/40"
                  onKeyDown={(e) => {
                    if (e.key === "Escape") {
                      setIsCreatingSection(false);
                      setNewSectionName("");
                    }
                  }}
                />
                <div className="flex justify-end gap-1 mt-1.5">
                  <button
                    type="button"
                    onClick={() => {
                      setIsCreatingSection(false);
                      setNewSectionName("");
                    }}
                    className="px-1.5 py-0.5 text-[10px] text-neutral-400 hover:text-white"
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    disabled={!newSectionName.trim()}
                    className="px-2 py-0.5 bg-white/20 hover:bg-white/30 disabled:opacity-40 text-white rounded text-[10px] font-medium"
                  >
                    Save
                  </button>
                </div>
              </form>
            ) : (
              <button
                type="button"
                onClick={() => setIsCreatingSection(true)}
                className="w-full flex items-center gap-2 px-2 py-1.5 rounded-lg text-left text-neutral-300 hover:bg-white/10 hover:text-white transition-colors cursor-pointer"
              >
                <span className="text-sm font-bold leading-none">+</span>
                <span>New section</span>
              </button>
            )}

            {conversation.section_name && (
              <button
                type="button"
                onClick={() => {
                  onSetSection(conversation, null);
                  onClose();
                }}
                className="w-full flex items-center gap-2 px-2 py-1.5 rounded-lg text-left text-neutral-400 hover:bg-white/10 hover:text-red-300 transition-colors cursor-pointer border-t border-white/10 mt-1"
              >
                <span>Remove from section</span>
              </button>
            )}
          </div>
        )}
      </div>

      <div className="my-1 border-t border-white/10" />

      <button
        type="button"
        role="menuitem"
        onClick={() => {
          onShare(conversation);
          onClose();
        }}
        className="w-full flex items-center gap-2.5 px-2.5 py-1.5 rounded-lg text-left hover:bg-white/10 hover:text-white transition-colors cursor-pointer group"
      >
        <svg
          className="w-3.5 h-3.5 text-neutral-400 group-hover:text-white transition-colors"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          <path d="M4 12v8a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-8" />
          <polyline points="16 6 12 2 8 6" />
          <line x1="12" y1="2" x2="12" y2="15" />
        </svg>
        <span>Share</span>
      </button>

      <div className="my-1 border-t border-white/10" />

      {conversation.is_archived ? (
        <button
          type="button"
          role="menuitem"
          onClick={() => {
            if (onUnarchive) {
              onUnarchive(conversation);
            } else {
              onArchive(conversation);
            }
            onClose();
          }}
          className="w-full flex items-center gap-2.5 px-2.5 py-1.5 rounded-lg text-left hover:bg-white/10 hover:text-white transition-colors cursor-pointer group"
        >
          <svg
            className="w-3.5 h-3.5 text-neutral-400 group-hover:text-white transition-colors"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <polyline points="21 8 21 21 3 21 3 8" />
            <rect x="1" y="3" width="22" height="5" />
            <line x1="12" y1="17" x2="12" y2="11" />
            <polyline points="9 14 12 11 15 14" />
          </svg>
          <span>Unarchive</span>
        </button>
      ) : (
        <button
          type="button"
          role="menuitem"
          onClick={() => {
            onArchive(conversation);
            onClose();
          }}
          className="w-full flex items-center gap-2.5 px-2.5 py-1.5 rounded-lg text-left hover:bg-white/10 hover:text-white transition-colors cursor-pointer group"
        >
          <svg
            className="w-3.5 h-3.5 text-neutral-400 group-hover:text-white transition-colors"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <polyline points="21 8 21 21 3 21 3 8" />
            <rect x="1" y="3" width="22" height="5" />
            <line x1="10" y1="12" x2="14" y2="12" />
          </svg>
          <span>Archive</span>
        </button>
      )}

      <button
        type="button"
        role="menuitem"
        onClick={() => {
          onDelete(conversation);
          onClose();
        }}
        className="w-full flex items-center gap-2.5 px-2.5 py-1.5 rounded-lg text-left text-red-400/90 hover:text-red-400 hover:bg-red-500/10 transition-colors cursor-pointer group"
      >
        <svg
          className="w-3.5 h-3.5 text-red-400/80 group-hover:text-red-400 transition-colors"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          <polyline points="3 6 5 6 21 6" />
          <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
          <line x1="10" y1="11" x2="10" y2="17" />
          <line x1="14" y1="11" x2="14" y2="17" />
        </svg>
        <span>Delete</span>
      </button>
    </div>
  );
};
