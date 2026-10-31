import React, { useEffect, useMemo, useState } from "react";
import type { Conversation, NavView, Review, User } from "../../types";
import { ConversationContextMenu } from "../chat/ConversationContextMenu";
import { DeleteConfirmModal, ShareModal } from "../chat/ConversationModals";
import {
  AgentIcon,
  ChatIcon,
  HistoryIcon,
  LogoIcon,
  LogoutIcon,
  OverviewIcon,
  PlusIcon,
  PrIcon,
  SettingsIcon,
} from "../icons/Icons";

interface SidebarProps {
  currentView: NavView;
  onSelectView: (view: NavView) => void;
  conversations: Conversation[];
  activeConversationId?: string;
  onSelectConversation: (id: string) => void;
  onNewChat: () => void;
  onNewReview: () => void;
  onRenameConversation?: (id: string, title: string) => Promise<void>;
  onTogglePinConversation?: (id: string, isPinned: boolean) => Promise<void>;
  onSetConversationSection?: (id: string, sectionName: string | null) => Promise<void>;
  onArchiveConversation?: (id: string) => Promise<void>;
  onUnarchiveConversation?: (id: string) => Promise<void>;
  onDeleteConversation?: (id: string) => Promise<void>;
  onDeleteReview?: (id: string) => void;
  onOpenGitHub?: () => void;
  reviews: Review[];
  user: User | null;
  onOpenSettings: () => void;
  onLogout: () => void;
  onOpenAuth: () => void;
  isLoadingConversations?: boolean;
  isMobileOpen?: boolean;
  onCloseMobile?: () => void;
  isCollapsed?: boolean;
  onToggleCollapse?: () => void;
}

export const Sidebar: React.FC<SidebarProps> = React.memo(({
  currentView,
  onSelectView,
  conversations,
  activeConversationId,
  onSelectConversation,
  onNewChat,
  onNewReview,
  onRenameConversation,
  onTogglePinConversation,
  onSetConversationSection,
  onArchiveConversation,
  onUnarchiveConversation,
  onDeleteConversation,
  onDeleteReview,
  onOpenGitHub,
  reviews,
  user,
  onOpenSettings,
  onLogout,
  onOpenAuth,
  isLoadingConversations = false,
  isMobileOpen = false,
  onCloseMobile,
  isCollapsed = false,
  onToggleCollapse,
}) => {
  const [confirmDeleteReviewId, setConfirmDeleteReviewId] = useState<string | null>(null);
  const [isDeletingReviewId, setIsDeletingReviewId] = useState<string | null>(null);

  const [menuState, setMenuState] = useState<{
    conversation: Conversation;
    rect: DOMRect;
  } | null>(null);

  const [shareTargetConv, setShareTargetConv] = useState<Conversation | null>(null);
  const [deleteTargetConv, setDeleteTargetConv] = useState<Conversation | null>(null);
  const [isDeletingConv, setIsDeletingConv] = useState(false);

  const [renamingConvId, setRenamingConvId] = useState<string | null>(null);
  const [renameInputVal, setRenameInputVal] = useState("");

  const [showArchived, setShowArchived] = useState<boolean>(false);

  const [collapsedSections, setCollapsedSections] = useState<Record<string, boolean>>({});

  useEffect(() => {
    if (!isMobileOpen) return;

    const originalOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        if (onCloseMobile) onCloseMobile();
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => {
      document.body.style.overflow = originalOverflow;
      window.removeEventListener("keydown", handleKeyDown);
    };
  }, [isMobileOpen, onCloseMobile]);

  const navItems = [
    { id: "chat" as NavView, label: "AI Assistant", icon: ChatIcon },
    { id: "overview" as NavView, label: "Overview", icon: OverviewIcon },
    { id: "prs" as NavView, label: "Pull Requests", icon: PrIcon },
    { id: "agents" as NavView, label: "Agents", icon: AgentIcon },
    { id: "history" as NavView, label: "Review History", icon: HistoryIcon },
  ];

  const activeConversations = useMemo(
    () => conversations.filter((c) => !c.is_archived),
    [conversations]
  );

  const archivedConversations = useMemo(
    () => conversations.filter((c) => !!c.is_archived),
    [conversations]
  );

  const pinnedConversations = useMemo(
    () => activeConversations.filter((c) => c.is_pinned),
    [activeConversations]
  );

  const sectionConversations = useMemo(
    () => activeConversations.filter((c) => !c.is_pinned && c.section_name),
    [activeConversations]
  );

  const recentConversations = useMemo(
    () => activeConversations.filter((c) => !c.is_pinned && !c.section_name),
    [activeConversations]
  );

  const groupedSections = useMemo(() => {
    const groups: Record<string, Conversation[]> = {};
    for (const conv of sectionConversations) {
      const sec = conv.section_name || "Uncategorized";
      if (!groups[sec]) groups[sec] = [];
      groups[sec].push(conv);
    }
    return groups;
  }, [sectionConversations]);

  const existingSections = useMemo(() => {
    const set = new Set<string>();
    for (const c of conversations) {
      if (c.section_name && c.section_name.trim()) {
        set.add(c.section_name.trim());
      }
    }
    return Array.from(set);
  }, [conversations]);

  const handleStartRename = (conv: Conversation) => {
    setRenamingConvId(conv.id);
    setRenameInputVal(conv.title || "");
  };

  const handleSaveRename = async (convId: string) => {
    const trimmed = renameInputVal.trim();
    setRenamingConvId(null);
    if (trimmed && onRenameConversation) {
      try {
        await onRenameConversation(convId, trimmed);
      } catch (err) {
        console.error("Failed to rename conversation:", err);
      }
    }
  };

  const handleTogglePin = async (conv: Conversation) => {
    if (onTogglePinConversation) {
      try {
        await onTogglePinConversation(conv.id, !conv.is_pinned);
      } catch (err) {
        console.error("Failed to toggle pin:", err);
      }
    }
  };

  const handleSetSection = async (conv: Conversation, sectionName: string | null) => {
    if (onSetConversationSection) {
      try {
        await onSetConversationSection(conv.id, sectionName);
      } catch (err) {
        console.error("Failed to update section:", err);
      }
    }
  };

  const handleArchive = async (conv: Conversation) => {
    if (onArchiveConversation) {
      try {
        await onArchiveConversation(conv.id);
      } catch (err) {
        console.error("Failed to archive conversation:", err);
      }
    }
  };

  const handleUnarchive = async (conv: Conversation) => {
    if (onUnarchiveConversation) {
      try {
        await onUnarchiveConversation(conv.id);
      } catch (err) {
        console.error("Failed to unarchive conversation:", err);
      }
    }
  };

  const handleConfirmDelete = async (conv: Conversation) => {
    if (!onDeleteConversation) return;
    setIsDeletingConv(true);
    try {
      await onDeleteConversation(conv.id);
      setDeleteTargetConv(null);
    } catch (err) {
      console.error("Failed to delete conversation:", err);
    } finally {
      setIsDeletingConv(false);
    }
  };

  const toggleSectionCollapse = (sec: string) => {
    setCollapsedSections((prev) => ({ ...prev, [sec]: !prev[sec] }));
  };

  const renderConversationRow = (conv: Conversation) => {
    const isActive = currentView === "chat" && activeConversationId === conv.id;
    const isEditing = renamingConvId === conv.id;
    const isMenuOpen = menuState?.conversation.id === conv.id;

    if (isEditing) {
      return (
        <div key={conv.id} className="px-2 py-1">
          <form
            onSubmit={(e) => {
              e.preventDefault();
              handleSaveRename(conv.id);
            }}
            className="flex items-center gap-1"
          >
            <input
              type="text"
              autoFocus
              value={renameInputVal}
              onChange={(e) => setRenameInputVal(e.target.value)}
              onBlur={() => handleSaveRename(conv.id)}
              onKeyDown={(e) => {
                if (e.key === "Escape") setRenamingConvId(null);
              }}
              className="w-full px-2 py-1 text-xs bg-black/80 border border-white/30 rounded text-white focus:outline-none focus:border-white"
            />
          </form>
        </div>
      );
    }

    return (
      <div
        key={conv.id}
        className={`group relative flex items-center justify-between px-3 py-2 rounded-xl text-[13px] transition-colors ${
          isActive
            ? "bg-white/12 text-white font-medium shadow-sm"
            : "text-neutral-400 hover:text-neutral-200 hover:bg-white/5"
        }`}
      >
        <button
          type="button"
          onClick={() => {
            onSelectConversation(conv.id);
            if (onCloseMobile) onCloseMobile();
          }}
          className="flex-1 flex items-center gap-2 text-left truncate min-w-0 pr-1 cursor-pointer"
          title={conv.title}
        >
          {conv.is_pinned ? (
            <svg
              className="w-3 h-3 text-neutral-400 flex-shrink-0"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
            >
              <line x1="12" y1="17" x2="12" y2="22" />
              <path d="M5 17h14v-1.76a2 2 0 0 0-1.11-1.79l-1.78-.89A4 4 0 0 1 14 9V5a2 2 0 0 0-2-2h0a2 2 0 0 0-2 2v4a4 4 0 0 1-2.11 3.56l-1.78.89A2 2 0 0 0 5 15.24Z" />
            </svg>
          ) : (
            <span className="text-[10px] text-neutral-600 font-mono">•</span>
          )}
          <span className="truncate">{conv.title || "Untitled Discussion"}</span>
        </button>

        <button
          type="button"
          onClick={(e) => {
            e.stopPropagation();
            const rect = e.currentTarget.getBoundingClientRect();
            setMenuState({ conversation: conv, rect });
          }}
          className={`p-1 rounded text-neutral-400 hover:text-white hover:bg-white/15 transition-all cursor-pointer flex-shrink-0 ${
            isMenuOpen
              ? "opacity-100 bg-white/15 text-white"
              : "opacity-0 group-hover:opacity-100 focus:opacity-100"
          }`}
          title="Conversation options"
          aria-label={`Options for ${conv.title}`}
        >
          <svg className="w-4 h-4" viewBox="0 0 24 24" fill="currentColor">
            <circle cx="5" cy="12" r="2" />
            <circle cx="12" cy="12" r="2" />
            <circle cx="19" cy="12" r="2" />
          </svg>
        </button>
      </div>
    );
  };

  return (
    <>

      {/* Mobile Backdrop */}
      {isMobileOpen && (
        <div
          className="fixed inset-0 bg-black/80 backdrop-blur-sm z-40 md:hidden"
          onClick={onCloseMobile}
          aria-hidden="true"
        />
      )}

      <aside
        className={`fixed top-0 bottom-0 left-0 z-50 w-[85vw] max-w-[320px] md:w-[260px] md:max-w-none h-full h-[100dvh] bg-black/95 md:bg-[#070707]/90 border-r border-white/10 flex flex-col justify-between transition-all duration-300 ${
          isMobileOpen
            ? "translate-x-0"
            : "-translate-x-full md:translate-x-0"
        } ${
          isCollapsed
            ? "md:-translate-x-full md:pointer-events-none md:w-0 md:opacity-0"
            : "md:translate-x-0 md:w-[260px] md:opacity-100"
        }`}
        aria-label="Application Navigation"
      >

        <div className="p-3.5 sm:p-4 pt-[max(0.875rem,env(safe-area-inset-top))] border-b border-white/10 flex-shrink-0">
          <div className="flex items-center justify-between mb-3.5">
            <div
              className="cursor-pointer group flex-1 min-w-0"
              onClick={() => {
                onSelectView("chat");
                if (onCloseMobile) onCloseMobile();
              }}
            >
              <div className="flex items-center gap-2.5">
                <LogoIcon size={25} />
                <span className="font-semibold text-[15px] tracking-wider text-white group-hover:text-neutral-200 transition-colors">
                  NEXARION
                </span>
              </div>
              <span className="block text-[11px] text-neutral-400 uppercase tracking-widest font-mono pl-[35px] mt-0.5 truncate">
                Code Intelligence
              </span>
            </div>

            {onToggleCollapse && (
              <button
                type="button"
                onClick={onToggleCollapse}
                className="hidden md:flex p-1.5 rounded-lg text-neutral-400 hover:text-white hover:bg-white/10 transition-colors cursor-pointer"
                title="Collapse sidebar"
                aria-label="Collapse sidebar"
              >
                <svg
                  className="w-[18px] h-[18px]"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                >
                  <rect x="3" y="3" width="18" height="18" rx="2" ry="2" />
                  <line x1="9" y1="3" x2="9" y2="21" />
                </svg>
              </button>
            )}

            {onCloseMobile && (
              <button
                type="button"
                onClick={onCloseMobile}
                className="md:hidden w-11 h-11 flex items-center justify-center rounded-xl text-neutral-400 hover:text-white hover:bg-white/10 active:bg-white/20 transition-colors cursor-pointer"
                aria-label="Close sidebar"
                title="Close sidebar"
              >
                <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            )}
          </div>

          <div className="flex gap-2">
            <button
              onClick={() => {
                onNewChat();
                if (onCloseMobile) onCloseMobile();
              }}
              className="flex-1 flex items-center justify-center gap-1.5 min-h-[44px] py-2 px-3 text-xs font-medium rounded-xl bg-white/10 hover:bg-white/15 active:bg-white/20 text-white border border-white/15 transition-all shadow-sm cursor-pointer"
              title="Start a new conversation thread"
            >
              <PlusIcon className="w-4 h-4" />
              <span className="text-[13px] sm:text-sm font-medium">New Chat</span>
            </button>
            <button
              onClick={() => {
                onNewReview();
                if (onCloseMobile) onCloseMobile();
              }}
              className="flex items-center justify-center gap-1 min-h-[44px] py-2 px-3 text-[13px] sm:text-sm font-medium rounded-xl bg-white/5 hover:bg-white/10 active:bg-white/20 text-neutral-300 hover:text-white border border-white/10 transition-all cursor-pointer"
              title="Review a new code diff"
            >
              <span>+ Review</span>
            </button>
          </div>
        </div>

        <div className="flex-1 overflow-y-auto overscroll-y-contain px-3 py-3 space-y-5">
          <nav className="space-y-1" aria-label="Main navigation">
            {navItems.map((item) => {
              const Icon = item.icon;
              const isActive = currentView === item.id;
              return (
                <button
                  key={item.id}
                  onClick={() => {
                    onSelectView(item.id);
                    if (onCloseMobile) onCloseMobile();
                  }}
                  className={`w-full min-h-[44px] flex items-center gap-3.5 px-3.5 py-2.5 text-[13px] sm:text-sm font-medium rounded-xl transition-colors text-left cursor-pointer ${
                    isActive
                      ? "bg-white/12 text-white border border-white/20 shadow-sm"
                      : "text-neutral-400 hover:text-neutral-200 hover:bg-white/5"
                  }`}
                >
                  <Icon className={`w-[18px] h-[18px] flex-shrink-0 ${isActive ? "text-white" : "text-neutral-400"}`} />
                  <span>{item.label}</span>
                </button>
              );
            })}
          </nav>

          <div className="flex items-center p-0.5 mb-3 bg-white/[0.04] rounded-lg border border-white/10 text-xs sm:text-[13px]">
            <button
              type="button"
              onClick={() => setShowArchived(false)}
              className={`flex-1 py-1 px-2 rounded-md transition-all text-center font-medium cursor-pointer ${
                !showArchived
                  ? "bg-white/15 text-white shadow-sm"
                  : "text-neutral-400 hover:text-white"
              }`}
            >
              Active ({activeConversations.length})
            </button>
            <button
              type="button"
              onClick={() => setShowArchived(true)}
              className={`flex-1 py-1 px-2 rounded-md transition-all text-center font-medium flex items-center justify-center gap-1.5 cursor-pointer ${
                showArchived
                  ? "bg-white/15 text-white shadow-sm"
                  : "text-neutral-400 hover:text-white"
              }`}
            >
              <svg
                className="w-3.5 h-3.5"
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
              <span>Archived</span>
              {archivedConversations.length > 0 && (
                <span className="text-[10px] px-1.5 py-0.2 bg-white/20 rounded-full font-mono">
                  {archivedConversations.length}
                </span>
              )}
            </button>
          </div>

          {showArchived ? (
            <div className="space-y-2">
              <div className="flex items-center justify-between px-2.5 mb-1.5">
                <span className="text-[10px] font-semibold text-neutral-400 uppercase tracking-wider font-mono">
                  Archived Chats
                </span>
                <span className="text-[10px] text-neutral-500 font-mono">
                  {archivedConversations.length} total
                </span>
              </div>

              {archivedConversations.length === 0 ? (
                <div className="px-3 py-6 text-center rounded-lg border border-dashed border-white/10 bg-white/[0.02]">
                  <p className="text-xs text-neutral-400">No archived chats</p>
                  <p className="text-[10px] text-neutral-500 mt-1">
                    Conversations you archive will appear here.
                  </p>
                </div>
              ) : (
                <div className="space-y-0.5">
                  {archivedConversations.map(renderConversationRow)}
                </div>
              )}
            </div>
          ) : (
            <div className="space-y-4">

              {pinnedConversations.length > 0 && (
                <div>
                  <div className="flex items-center gap-1.5 px-2.5 mb-1.5 text-[10px] font-semibold text-neutral-400 uppercase tracking-wider font-mono">
                    <svg
                      className="w-3 h-3 text-neutral-400"
                      viewBox="0 0 24 24"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth="2"
                    >
                      <line x1="12" y1="17" x2="12" y2="22" />
                      <path d="M5 17h14v-1.76a2 2 0 0 0-1.11-1.79l-1.78-.89A4 4 0 0 1 14 9V5a2 2 0 0 0-2-2h0a2 2 0 0 0-2 2v4a4 4 0 0 1-2.11 3.56l-1.78.89A2 2 0 0 0 5 15.24Z" />
                    </svg>
                    <span>Pinned</span>
                    <span className="ml-auto text-[10px] text-neutral-600 font-mono">
                      {pinnedConversations.length}
                    </span>
                  </div>
                  <div className="space-y-0.5">
                    {pinnedConversations.map(renderConversationRow)}
                  </div>
                </div>
              )}

              {Object.keys(groupedSections).length > 0 && (
                <div className="space-y-3">
                  {Object.entries(groupedSections).map(([secName, secConvs]) => {
                    const isSecCollapsed = !!collapsedSections[secName];
                    return (
                      <div key={secName} className="space-y-1">
                        <button
                          type="button"
                          onClick={() => toggleSectionCollapse(secName)}
                          className="w-full flex items-center justify-between px-2.5 py-1 text-[10px] font-semibold text-neutral-400 uppercase tracking-wider font-mono hover:text-neutral-200 transition-colors"
                        >
                          <div className="flex items-center gap-1.5 truncate">
                            <svg
                              className={`w-3 h-3 text-neutral-500 transition-transform ${
                                isSecCollapsed ? "-rotate-90" : "rotate-0"
                              }`}
                              viewBox="0 0 24 24"
                              fill="none"
                              stroke="currentColor"
                              strokeWidth="2"
                            >
                              <polyline points="6 9 12 15 18 9" />
                            </svg>
                            <span className="truncate">{secName}</span>
                          </div>
                          <span className="text-[10px] text-neutral-600 font-mono">
                            {secConvs.length}
                          </span>
                        </button>
                        {!isSecCollapsed && (
                          <div className="space-y-0.5 pl-1.5 border-l border-white/5 ml-2.5">
                            {secConvs.map(renderConversationRow)}
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              )}

              <div>
                <div className="flex items-center justify-between px-2.5 mb-1.5">
                  <span className="text-[10px] font-semibold text-neutral-500 uppercase tracking-wider font-mono">
                    Recent Conversations
                  </span>
                  <span className="text-[10px] text-neutral-600 font-mono">
                    {recentConversations.length}
                  </span>
                </div>

                <div className="space-y-0.5">
                  {recentConversations.length === 0 && pinnedConversations.length === 0 && Object.keys(groupedSections).length === 0 ? (
                    isLoadingConversations ? (
                      <div className="space-y-2 px-2 py-2" data-testid="conversations-loading-skeleton">
                        <div className="h-7 rounded-lg bg-white/[0.04] animate-pulse" />
                        <div className="h-7 rounded-lg bg-white/[0.03] animate-pulse" />
                        <div className="h-7 rounded-lg bg-white/[0.02] animate-pulse" />
                      </div>
                    ) : (
                      <div className="px-3 py-2 text-[11px] text-neutral-600 italic">
                        No previous conversations
                      </div>
                    )
                  ) : (
                    recentConversations.map(renderConversationRow)
                  )}
                </div>
              </div>
            </div>
          )}

          {reviews.length > 0 && (
            <div>
              <div className="flex items-center justify-between px-3 mb-2">
                <span className="text-[10px] font-semibold text-neutral-500 uppercase tracking-wider font-mono">
                  Recent Reviews
                </span>
                <span className="text-[10px] text-neutral-600 font-mono">{reviews.length}</span>
              </div>
              <div className="space-y-1">
                {reviews.slice(0, 5).map((rev) => {
                  const isConfirming = confirmDeleteReviewId === rev.id;
                  return (
                    <div
                      key={rev.id}
                      className="group flex items-center justify-between px-2.5 py-1.5 text-xs text-neutral-400 hover:text-neutral-200 hover:bg-white/5 rounded-md transition-colors"
                    >
                      {isConfirming ? (
                        <div className="flex items-center justify-between w-full py-0.5 text-xs animate-fade-in">
                          <span className="text-[10px] text-neutral-300 font-mono">Delete?</span>
                          <div className="flex items-center gap-1.5">
                            <button
                              type="button"
                              disabled={isDeletingReviewId === rev.id}
                              onClick={async (e) => {
                                e.stopPropagation();
                                setIsDeletingReviewId(rev.id);
                                try {
                                  if (onDeleteReview) await onDeleteReview(rev.id);
                                  setConfirmDeleteReviewId(null);
                                } catch {

                                } finally {
                                  setIsDeletingReviewId(null);
                                }
                              }}
                              className="px-2 py-0.5 bg-red-600 hover:bg-red-500 disabled:opacity-50 text-white rounded text-[10px] font-medium transition-colors"
                            >
                              {isDeletingReviewId === rev.id ? "..." : "Delete"}
                            </button>
                            <button
                              type="button"
                              disabled={isDeletingReviewId === rev.id}
                              onClick={(e) => {
                                e.stopPropagation();
                                setConfirmDeleteReviewId(null);
                              }}
                              className="px-1.5 py-0.5 text-neutral-400 hover:text-white rounded text-[10px]"
                            >
                              Cancel
                            </button>
                          </div>
                        </div>
                      ) : (
                        <>
                          <button
                            type="button"
                            onClick={() => {
                              onSelectView("history");
                              if (onCloseMobile) onCloseMobile();
                            }}
                            className="flex-1 text-left truncate max-w-[130px] cursor-pointer"
                            title={rev.title}
                          >
                            <span className="truncate">{rev.title}</span>
                          </button>
                          <div className="flex items-center gap-1.5">
                            <span
                              className={`text-[9px] px-1.5 py-0.5 rounded font-mono ${
                                rev.has_critical
                                  ? "bg-neutral-800 text-neutral-200 border border-neutral-700"
                                  : "bg-neutral-900 text-neutral-400"
                              }`}
                            >
                              {rev.finding_count} f
                            </span>
                            {onDeleteReview && (
                              <button
                                type="button"
                                onClick={(e) => {
                                  e.stopPropagation();
                                  setConfirmDeleteReviewId(rev.id);
                                }}
                                className="opacity-0 group-hover:opacity-100 p-0.5 text-neutral-500 hover:text-red-400 rounded transition-opacity"
                                title="Delete review"
                                aria-label="Delete review"
                              >
                                <svg className="w-3 h-3" viewBox="0 0 16 16" fill="currentColor">
                                  <path d="M5.5 5.5A.5.5 0 0 1 6 6v6a.5.5 0 0 1-1 0V6a.5.5 0 0 1 .5-.5zm2.5 0a.5.5 0 0 1 .5.5v6a.5.5 0 0 1-1 0V6a.5.5 0 0 1 .5-.5zm3 .5a.5.5 0 0 0-1 0v6a.5.5 0 0 0 1 0V6z" />
                                  <path
                                    fillRule="evenodd"
                                    d="M14.5 3a1 1 0 0 1-1 1H13v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V4h-.5a1 1 0 0 1-1-1V2a1 1 0 0 1 1-1H6a1 1 0 0 1 1-1h2a1 1 0 0 1 1 1h3.5a1 1 0 0 1 1 1v1zM4.118 4 4 4.059V13a1 1 0 0 0 1 1h6a1 1 0 0 0 1-1V4.059L11.882 4H4.118zM2.5 3V2h11v1h-11z"
                                  />
                                </svg>
                              </button>
                            )}
                          </div>
                        </>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {onOpenGitHub && (
            <div className="pt-2 border-t border-white/5">
              <button
                type="button"
                onClick={() => {
                  onOpenGitHub();
                  if (onCloseMobile) onCloseMobile();
                }}
                className="w-full flex items-center justify-between px-3 py-2 rounded-lg bg-white/[0.02] hover:bg-white/[0.06] border border-white/10 text-xs text-neutral-300 hover:text-white transition-colors cursor-pointer"
              >
                <div className="flex items-center gap-2">
                  <svg className="w-4 h-4 text-neutral-400" viewBox="0 0 16 16" fill="currentColor">
                    <path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.012 8.012 0 0 0 16 8c0-4.42-3.58-8-8-8z" />
                  </svg>
                  <span>GitHub PRs</span>
                </div>
                <span className="text-[10px] text-neutral-500 font-mono">Review →</span>
              </button>
            </div>
          )}
        </div>

        <div className="p-3 pb-[max(0.75rem,env(safe-area-inset-bottom))] border-t border-white/10 bg-black/40 space-y-2 flex-shrink-0">
          <button
            onClick={() => {
              onOpenSettings();
              if (onCloseMobile) onCloseMobile();
            }}
            className={`w-full min-h-[44px] flex items-center gap-3 px-3.5 py-2.5 text-[13px] sm:text-sm font-medium rounded-xl transition-all text-left cursor-pointer ${
              currentView === "settings"
                ? "bg-white/12 text-white border border-white/20"
                : "text-neutral-400 hover:text-neutral-200 hover:bg-white/5 active:bg-white/10"
            }`}
          >
            <SettingsIcon className="w-[18px] h-[18px] text-neutral-400" />
            <span>Settings</span>
          </button>

          {user ? (
            <div className="flex items-center justify-between p-2 rounded-lg bg-white/5 border border-white/10">
              <div className="flex items-center gap-2.5 min-w-0">
                {user.avatar_url ? (
                  <img
                    src={user.avatar_url}
                    alt={user.name}
                    className="w-8 h-8 rounded-full object-cover border border-white/20 flex-shrink-0"
                    onError={(e) => {
                      (e.currentTarget as HTMLElement).style.display = "none";
                      const fallback = e.currentTarget.parentElement?.querySelector(".avatar-fallback");
                      if (fallback) (fallback as HTMLElement).classList.remove("hidden");
                    }}
                  />
                ) : null}
                <div
                  className={`avatar-fallback w-8 h-8 rounded-full bg-neutral-800 border border-white/20 items-center justify-center text-xs font-semibold text-white flex-shrink-0 ${
                    user.avatar_url ? "hidden" : "flex"
                  }`}
                >
                  {user.name ? user.name.charAt(0).toUpperCase() : "U"}
                </div>
                <div className="min-w-0">
                  <div className="text-sm font-semibold text-white truncate">{user.name}</div>
                  <div className="text-xs text-neutral-400 font-mono truncate">{user.email}</div>
                </div>
              </div>
              <button
                onClick={onLogout}
                className="text-neutral-400 hover:text-white p-1 rounded hover:bg-white/10 transition-colors flex-shrink-0 ml-1 cursor-pointer"
                title="Log out"
                aria-label="Log out"
              >
                <LogoutIcon className="w-4 h-4" />
              </button>
            </div>
          ) : (
            <button
              onClick={onOpenAuth}
              className="w-full py-2 px-3 text-xs font-medium text-center rounded-lg bg-white/10 hover:bg-white/15 text-white border border-white/15 transition-all cursor-pointer"
            >
              Sign In / Register
            </button>
          )}
        </div>
      </aside>

      {menuState && (
        <ConversationContextMenu
          conversation={menuState.conversation}
          triggerRect={menuState.rect}
          onClose={() => setMenuState(null)}
          onRename={handleStartRename}
          onTogglePin={handleTogglePin}
          onSetSection={handleSetSection}
          onShare={(conv) => setShareTargetConv(conv)}
          onArchive={handleArchive}
          onUnarchive={handleUnarchive}
          onDelete={(conv) => setDeleteTargetConv(conv)}
          existingSections={existingSections}
        />
      )}

      {shareTargetConv && (
        <ShareModal
          conversation={shareTargetConv}
          onClose={() => setShareTargetConv(null)}
        />
      )}

      {deleteTargetConv && (
        <DeleteConfirmModal
          conversation={deleteTargetConv}
          isOpen={!!deleteTargetConv}
          isDeleting={isDeletingConv}
          onClose={() => setDeleteTargetConv(null)}
          onConfirm={handleConfirmDelete}
        />
      )}
    </>
  );
});
Sidebar.displayName = "Sidebar";
