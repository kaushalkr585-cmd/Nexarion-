import { useEffect } from "react";
import type { NavView, Conversation, Review } from "../types";

export interface DocumentTitleOptions {
  currentView: NavView;
  activeConversationId?: string;
  activeConversation: Conversation | null;
  conversations: Conversation[];
  isComposerOpen?: boolean;
  isDetailOpen?: boolean;
  selectedReview?: Review | null;
}

export function computeDocumentTitle(options: DocumentTitleOptions): string {
  const {
    currentView,
    activeConversationId,
    activeConversation,
    conversations,
    isComposerOpen,
    isDetailOpen,
  } = options;

  if (isComposerOpen) {
    return "New Review — Nexarion";
  }

  if (isDetailOpen) {
    return "Review Details — Nexarion";
  }

  switch (currentView) {
    case "history":
      return "Review History — Nexarion";
    case "overview":
      return "Overview — Nexarion";
    case "prs":
      return "Pull Requests — Nexarion";
    case "agents":
      return "Agents — Nexarion";
    case "settings":
      return "Settings — Nexarion";
    case "chat":
    default: {
      if (activeConversationId) {

        const convTitle =
          activeConversation?.id === activeConversationId
            ? activeConversation.title
            : conversations.find((c) => c.id === activeConversationId)?.title;

        if (convTitle && convTitle.trim()) {
          return `${convTitle.trim()} — Nexarion`;
        }
      }
      return "Nexarion";
    }
  }
}

export function useDocumentTitle(options: DocumentTitleOptions): void {
  useEffect(() => {
    const nextTitle = computeDocumentTitle(options);
    if (typeof document !== "undefined" && document.title !== nextTitle) {
      document.title = nextTitle;
    }
  }, [
    options.currentView,
    options.activeConversationId,
    options.activeConversation?.id,
    options.activeConversation?.title,
    options.conversations,
    options.isComposerOpen,
    options.isDetailOpen,
    options.selectedReview?.id,
  ]);
}
