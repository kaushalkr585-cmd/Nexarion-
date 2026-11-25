import React, { useEffect, useMemo, useRef, useState } from "react";
import { CheckIcon, CodeIcon, GithubIcon, PaperclipIcon } from "../icons/Icons";

export interface ComposerIntegrationItem {
  id: "github" | "attach_file" | "attach_diff";
  name: string;
  description: string;
  isSelected: boolean;
  badge?: string;
}

interface ComposerIntegrationsMenuProps {
  isOpen: boolean;
  onClose: () => void;
  githubEnabled: boolean;
  githubConnected: boolean;
  hasDiffAttached: boolean;
  attachmentsCount: number;
  onToggleGitHub: () => void;
  onTriggerAttachFile: () => void;
  onToggleAttachDiff: () => void;
}

export const ComposerIntegrationsMenu: React.FC<ComposerIntegrationsMenuProps> = ({
  isOpen,
  onClose,
  githubEnabled,
  githubConnected,
  hasDiffAttached,
  attachmentsCount,
  onToggleGitHub,
  onTriggerAttachFile,
  onToggleAttachDiff,
}) => {
  const [activeIndex, setActiveIndex] = useState(0);
  const menuRef = useRef<HTMLDivElement | null>(null);

  const items: ComposerIntegrationItem[] = useMemo(
    () => [
      {
        id: "github",
        name: "GitHub",
        description:
          "Inspect repositories, analyze code, explore pull requests, issues and commits.",
        isSelected: githubEnabled,
        badge: githubEnabled ? "Active" : githubConnected ? "Connected" : undefined,
      },
      {
        id: "attach_file",
        name: "Attach File",
        description: "Upload PDF, code, diff, or text documents into this conversation.",
        isSelected: attachmentsCount > 0,
        badge: attachmentsCount > 0 ? `${attachmentsCount} attached` : undefined,
      },
      {
        id: "attach_diff",
        name: "Attach Diff",
        description: "Paste a unified git diff for focused multi-agent code review.",
        isSelected: hasDiffAttached,
        badge: hasDiffAttached ? "Attached" : undefined,
      },
    ],
    [githubEnabled, githubConnected, attachmentsCount, hasDiffAttached]
  );

  useEffect(() => {
    if (isOpen) {
      setActiveIndex(0);
    }
  }, [isOpen]);

  useEffect(() => {
    if (!isOpen) return;

    const handlePointerDown = (event: MouseEvent | TouchEvent) => {
      const target = event.target as HTMLElement | null;
      if (target?.closest("[data-plus-menu-trigger='true']")) return;
      if (menuRef.current && !menuRef.current.contains(event.target as Node)) {
        onClose();
      }
    };

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        onClose();
      }
    };

    document.addEventListener("mousedown", handlePointerDown);
    document.addEventListener("touchstart", handlePointerDown);
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("mousedown", handlePointerDown);
      document.removeEventListener("touchstart", handlePointerDown);
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [isOpen, onClose]);

  const handleSelectItem = (item: ComposerIntegrationItem) => {
    if (item.id === "github") {
      onToggleGitHub();
    } else if (item.id === "attach_file") {
      onTriggerAttachFile();
    } else if (item.id === "attach_diff") {
      onToggleAttachDiff();
    }
    onClose();
  };

  const handleMenuKeyDown = (e: React.KeyboardEvent) => {
    if (items.length === 0) return;
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setActiveIndex((prev) => (prev + 1) % items.length);
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActiveIndex((prev) => (prev - 1 + items.length) % items.length);
    } else if (e.key === "Enter") {
      e.preventDefault();
      const target = items[activeIndex];
      if (target) handleSelectItem(target);
    }
  };

  if (!isOpen) return null;

  const renderIcon = (id: ComposerIntegrationItem["id"], selected: boolean) => {
    const cls = `w-4 h-4 flex-shrink-0 ${selected ? "text-white" : "text-neutral-300"}`;
    if (id === "github") return <GithubIcon className={cls} />;
    if (id === "attach_file") return <PaperclipIcon className={cls} />;
    return <CodeIcon className={cls} />;
  };

  return (
    <div
      ref={menuRef}
      role="menu"
      aria-label="Integrations and composer tools"
      onKeyDown={handleMenuKeyDown}
      className="absolute bottom-full left-0 mb-2.5 w-[310px] sm:w-[340px] max-w-[calc(100vw-2rem)] rounded-2xl bg-[#141414]/95 border border-white/15 shadow-2xl backdrop-blur-xl overflow-hidden z-50 animate-fade-in"
    >
      <div className="p-1.5 space-y-0.5">
        {items.map((item, index) => {
          const isHighlighted = index === activeIndex;
          return (
            <button
              key={item.id}
              type="button"
              role="menuitem"
              onClick={() => handleSelectItem(item)}
              onMouseEnter={() => setActiveIndex(index)}
              className={`w-full flex items-start gap-3 px-3 py-2.5 rounded-xl text-left transition-colors cursor-pointer ${
                item.isSelected
                  ? "bg-white/12 border border-white/15"
                  : isHighlighted
                  ? "bg-white/[0.08] border border-transparent"
                  : "hover:bg-white/[0.07] border border-transparent"
              }`}
            >
              <div
                className={`mt-0.5 w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0 border ${
                  item.isSelected
                    ? "bg-white/15 border-white/25"
                    : "bg-white/5 border-white/10"
                }`}
              >
                {renderIcon(item.id, item.isSelected)}
              </div>

              <div className="flex-1 min-w-0">
                <div className="flex items-center justify-between gap-2">
                  <span className="text-xs sm:text-[13px] font-semibold text-white truncate">
                    {item.name}
                  </span>
                  <div className="flex items-center gap-1.5 flex-shrink-0">
                    {item.badge && (
                      <span
                        className={`px-1.5 py-0.5 rounded-md text-[10px] font-mono ${
                          item.isSelected
                            ? "bg-white text-black font-semibold"
                            : "bg-white/10 text-neutral-300"
                        }`}
                      >
                        {item.badge}
                      </span>
                    )}
                    {item.isSelected && <CheckIcon className="w-3.5 h-3.5 text-white" />}
                  </div>
                </div>
                <p className="text-[11px] text-neutral-400 leading-snug mt-0.5 line-clamp-2">
                  {item.description}
                </p>
              </div>
            </button>
          );
        })}
      </div>
    </div>
  );
};
