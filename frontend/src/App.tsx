import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type {
  AgentConfig,
  Attachment,
  Conversation,
  GenerationState,
  GenerationType,
  Message,
  NavView,
  OverviewMetrics,
  PullRequest,
  ProviderStatusResponse,
  Review,
  User,
  WaveState,
} from "./types";
import {
  agentApi,
  authApi,
  conversationApi,
  githubApi,
  overviewApi,
  prApi,
  providerApi,
  reviewApi,
  sanitizeErrorMessage,
  setToken,
} from "./services/api";

import { Sidebar } from "./components/layout/Sidebar";
import { AIConversationWorkspace } from "./components/chat/AIConversationWorkspace";
import { OverviewPage } from "./pages/OverviewPage";
import { PullRequestsPage } from "./pages/PullRequestsPage";
import { AgentsPage } from "./pages/AgentsPage";
import { HistoryPage } from "./pages/HistoryPage";
import { SettingsPage } from "./pages/SettingsPage";
import { ReviewComposerModal } from "./components/reviews/ReviewComposerModal";
import { ReviewDetailModal } from "./components/reviews/ReviewDetailModal";
import { AuthModal } from "./components/modals/AuthModal";
import { ResourceModal, type ResourceType } from "./components/modals/ResourceModal";
import { GitHubPrPickerModal } from "./components/github/GitHubPrPickerModal";
import { BackIcon, CloseIcon, CodeIcon, MenuIcon, PlusIcon, SettingsIcon } from "./components/icons/Icons";
import { useDocumentTitle } from "./hooks/useDocumentTitle";
import { getViewFromPath, getPathFromView } from "./utils/router";
import {
  AskNexarionSelectionHandler,
  formatSelectionPrompt,
} from "./components/chat/AskNexarionSelectionHandler";

export const App: React.FC = () => {

  const initialRoute = useMemo(() => {
    if (typeof window === "undefined") return { view: "chat" as NavView };
    return getViewFromPath(window.location.pathname);
  }, []);

  const [currentView, setCurrentView] = useState<NavView>(initialRoute.view);
  const [navHistory, setNavHistory] = useState<Array<{ view: NavView; conversationId?: string }>>([]);
  const setWaveState = useCallback(
    (_nextState: WaveState | ((current: WaveState) => WaveState)) => {
      void _nextState;
    },
    []
  );
  const [generationState, setGenerationState] = useState<GenerationState>("idle");
  const [generationType, setGenerationType] = useState<GenerationType>("chat");
  const [isMobileNavOpen, setIsMobileNavOpen] = useState(false);
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);
  const [isSidebarCollapsed, setIsSidebarCollapsed] = useState<boolean>(() => {
    try {
      return localStorage.getItem("nexarion_sidebar_collapsed") === "true";
    } catch {
      return false;
    }
  });

  const handleToggleSidebarCollapse = () => {
    setIsSidebarCollapsed((prev) => {
      const next = !prev;
      try {
        localStorage.setItem("nexarion_sidebar_collapsed", String(next));
      } catch {

      }
      return next;
    });
  };
  const [isAuthChecking, setIsAuthChecking] = useState<boolean>(true);

  const [user, setUser] = useState<User | null>(() => {
    try {
      const cached = sessionStorage.getItem("nexarion_user_cache");
      return cached ? JSON.parse(cached) : null;
    } catch {
      return null;
    }
  });
  const [conversations, setConversations] = useState<Conversation[]>(() => {
    try {
      const cached = sessionStorage.getItem("nexarion_conversations_cache");
      return cached ? JSON.parse(cached) : [];
    } catch {
      return [];
    }
  });
  const [isLoadingConversations, setIsLoadingConversations] = useState<boolean>(false);
  const [activeConversationId, setActiveConversationId] = useState<string | undefined>(
    initialRoute.conversationId
  );
  const activeConvIdRef = useRef<string | undefined>(initialRoute.conversationId);
  const activeSelectionVersionRef = useRef(0);

  useEffect(() => {
    activeConvIdRef.current = activeConversationId;
  }, [activeConversationId]);

  const [activeConversation, setActiveConversation] = useState<Conversation | null>(null);
  const [isLoadingActiveConversation, setIsLoadingActiveConversation] = useState(false);
  const [reviews, setReviews] = useState<Review[]>(() => {
    try {
      const cached = sessionStorage.getItem("nexarion_reviews_cache");
      return cached ? JSON.parse(cached) : [];
    } catch {
      return [];
    }
  });
  const [pullRequests, setPullRequests] = useState<PullRequest[]>([]);
  const [overviewMetrics, setOverviewMetrics] = useState<OverviewMetrics | null>(null);
  const [isOverviewLoading, setIsOverviewLoading] = useState<boolean>(false);
  const [overviewError, setOverviewError] = useState<string | null>(null);
  const [isPrsLoading, setIsPrsLoading] = useState<boolean>(false);
  const [prsError, setPrsError] = useState<string | null>(null);
  const [reviewingPrNumber, setReviewingPrNumber] = useState<string | null>(null);
  const [agents, setAgents] = useState<AgentConfig[]>([]);
  const [agentToast, setAgentToast] = useState<{ message: string; type: "error" | "success" } | null>(null);
  const agentToggleSeqRef = useRef<Map<string, number>>(new Map());
  const agentToastTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [providerStatus, setProviderStatus] = useState<ProviderStatusResponse | null>(null);

  const [isComposerOpen, setIsComposerOpen] = useState(false);
  const [composerInitialDiff, setComposerInitialDiff] = useState<string>("");
  const [composerTitle, setComposerTitle] = useState<string>("");
  const [composerRepo, setComposerRepo] = useState<string>("");
  const [isComposerLoadingDiff, setIsComposerLoadingDiff] = useState<boolean>(false);
  const [composerDiffError, setComposerDiffError] = useState<string | null>(null);
  const prDiffFetchRef = useRef<(() => void) | null>(null);
  const [selectedReview, setSelectedReview] = useState<Review | null>(null);
  const [isDetailOpen, setIsDetailOpen] = useState(false);
  const [isReviewDetailLoading, setIsReviewDetailLoading] = useState(false);
  const reviewDetailRequestRef = useRef(0);
  const [isAuthOpen, setIsAuthOpen] = useState(false);
  const [activeResource, setActiveResource] = useState<ResourceType | null>(null);
  const [isGitHubModalOpen, setIsGitHubModalOpen] = useState(false);

  useDocumentTitle({
    currentView,
    activeConversationId,
    activeConversation,
    conversations,
    isComposerOpen,
    isDetailOpen,
    selectedReview,
  });

  const [isSendingMessage, setIsSendingMessage] = useState(false);
  const [pendingComposerPrompt, setPendingComposerPrompt] = useState<string | null>(null);
  const abortControllerRef = useRef<AbortController | null>(null);
  const activeStreamControllersRef = useRef<Map<string, AbortController>>(new Map());
  const streamedContentRef = useRef<Map<string, string>>(new Map());
  const streamingMessageIdsRef = useRef<Map<string, string>>(new Map());
  const skipFetchConversationIdRef = useRef<string | null>(null);
  const mobileMenuRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!isMobileMenuOpen) return;

    const handlePointerDown = (event: MouseEvent | TouchEvent) => {
      if (
        mobileMenuRef.current &&
        !mobileMenuRef.current.contains(event.target as Node)
      ) {
        setIsMobileMenuOpen(false);
      }
    };

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setIsMobileMenuOpen(false);
      }
    };

    document.addEventListener("mousedown", handlePointerDown);
    document.addEventListener("touchstart", handlePointerDown, { passive: true });
    window.addEventListener("keydown", handleKeyDown);

    return () => {
      document.removeEventListener("mousedown", handlePointerDown);
      document.removeEventListener("touchstart", handlePointerDown);
      window.removeEventListener("keydown", handleKeyDown);
    };
  }, [isMobileMenuOpen]);

  const handleAskNexarion = (selectedText: string) => {
    const formattedPrompt = formatSelectionPrompt(selectedText);
    if (!formattedPrompt) return;

    setIsDetailOpen(false);
    setIsComposerOpen(false);

    if (currentView !== "chat") {
      navigateTo("chat");
    }

    setPendingComposerPrompt(formattedPrompt);
  };

  const navigateTo = useCallback(
    (view: NavView, conversationId?: string, replace: boolean = false) => {

      const nextConversationId =
        view === "chat" ? conversationId : (conversationId ?? activeConvIdRef.current);
      const targetPath = getPathFromView(view, view === "chat" ? conversationId : undefined);

      if (!replace && (currentView !== view || activeConversationId !== nextConversationId)) {
        activeSelectionVersionRef.current += 1;
        setNavHistory((prev) => [...prev, { view: currentView, conversationId: activeConversationId }]);
        try {
          window.history.pushState({ view, conversationId: nextConversationId }, "", targetPath);
        } catch {

        }
      } else if (replace) {
        try {
          window.history.replaceState({ view, conversationId: nextConversationId }, "", targetPath);
        } catch {

        }
      }
      setCurrentView(view);
      setActiveConversationId(nextConversationId);
      activeConvIdRef.current = nextConversationId;
      setIsMobileMenuOpen(false);
      if (view !== "chat") {
        setIsMobileNavOpen(false);
      }
    },
    [currentView, activeConversationId]
  );

  const handleSelectView = useCallback(
    (view: NavView) => {
      if (view === currentView) return;
      if (view === "chat") {
        navigateTo("chat", activeConvIdRef.current);
      } else {
        navigateTo(view, activeConvIdRef.current);
      }
    },
    [currentView, navigateTo]
  );

  const canGoBack = navHistory.length > 0 || currentView !== "chat" || Boolean(activeConversationId);

  const handleGoBack = useCallback(() => {
    setIsMobileMenuOpen(false);
    if (isSendingMessage && abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
      setIsSendingMessage(false);
    }

    if (navHistory.length > 0) {
      const prev = navHistory[navHistory.length - 1];
      activeSelectionVersionRef.current += 1;
      setNavHistory((hist) => hist.slice(0, -1));
      setCurrentView(prev.view);
      setActiveConversationId(prev.conversationId);
      activeConvIdRef.current = prev.conversationId;
      setIsSendingMessage(
        prev.conversationId
          ? activeStreamControllersRef.current.has(prev.conversationId)
          : false
      );
      try {
        const targetPath = getPathFromView(prev.view, prev.conversationId);
        window.history.replaceState(
          { view: prev.view, conversationId: prev.conversationId },
          "",
          targetPath
        );
      } catch {

      }
      return;
    }

    if (currentView !== "chat") {
      navigateTo("chat", activeConvIdRef.current);
      const selectedId = activeConvIdRef.current;
      const isGeneratingSelectedConversation = Boolean(
        selectedId && activeStreamControllersRef.current.has(selectedId)
      );
      setIsSendingMessage(isGeneratingSelectedConversation);
      setGenerationState(isGeneratingSelectedConversation ? "streaming" : "idle");
      setWaveState(isGeneratingSelectedConversation ? "responding" : "idle");
      return;
    }

    if (activeConversationId) {
      navigateTo("chat", undefined);
      setIsSendingMessage(false);
      setGenerationState("idle");
      setWaveState("idle");
    }
  }, [navHistory, currentView, activeConversationId, isSendingMessage, navigateTo]);

  useEffect(() => {
    const handlePopState = (e: PopStateEvent) => {
      activeSelectionVersionRef.current += 1;
      if (e.state && e.state.view) {
        setCurrentView(e.state.view);
        setActiveConversationId(e.state.conversationId);
        activeConvIdRef.current = e.state.conversationId;
      } else {
        const route = getViewFromPath(window.location.pathname);
        setCurrentView(route.view);
        setActiveConversationId(route.conversationId);
        activeConvIdRef.current = route.conversationId;
      }
      const selectedId = e.state?.conversationId ?? getViewFromPath(window.location.pathname).conversationId;
      setIsSendingMessage(Boolean(selectedId && activeStreamControllersRef.current.has(selectedId)));
    };
    window.addEventListener("popstate", handlePopState);
    return () => window.removeEventListener("popstate", handlePopState);
  }, []);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.altKey && e.key === "ArrowLeft") {
        e.preventDefault();
        handleGoBack();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [navHistory, currentView, activeConversationId]);

  const clearUserData = () => {
    setUser(null);
    setConversations([]);
    setActiveConversationId(undefined);
    setActiveConversation(null);
    setReviews([]);
    setSelectedReview(null);
    setIsDetailOpen(false);
    setPullRequests([]);
    setOverviewMetrics(null);
    setOverviewError(null);
    setPrsError(null);
    setGenerationState("idle");
    setGenerationType("chat");
    try {
      if (typeof window !== "undefined" && window.sessionStorage) {
        window.sessionStorage.removeItem("nexarion_last_greeting_heading");
        window.sessionStorage.removeItem("nexarion_user_cache");
        window.sessionStorage.removeItem("nexarion_conversations_cache");
        window.sessionStorage.removeItem("nexarion_reviews_cache");
      }
    } catch {

    }
  };

  const fetchOverviewMetrics = async () => {
    setIsOverviewLoading(true);
    setOverviewError(null);
    try {
      const m = await overviewApi.getMetrics();
      setOverviewMetrics(m);
    } catch (err) {
      setOverviewError(
        sanitizeErrorMessage(err instanceof Error ? err.message : "Failed to load overview data")
      );
    } finally {
      setIsOverviewLoading(false);
    }
  };

  const fetchPullRequests = async () => {
    setIsPrsLoading(true);
    setPrsError(null);
    try {
      const prs = await prApi.list();
      setPullRequests(prs);
    } catch (err) {
      setPrsError(
        sanitizeErrorMessage(err instanceof Error ? err.message : "Failed to load pull requests")
      );
    } finally {
      setIsPrsLoading(false);
    }
  };

  const loadUserData = async (currentUser: User) => {
    setIsLoadingConversations(true);
    try {

      const [convList, reviewList] = await Promise.all([
        conversationApi.list().catch(() => [] as Conversation[]),
        reviewApi.list().catch(() => [] as Review[]),
      ]);

      setConversations(convList);
      try {
        sessionStorage.setItem("nexarion_conversations_cache", JSON.stringify(convList));
      } catch {

      }

      setReviews(reviewList);
      try {
        sessionStorage.setItem("nexarion_reviews_cache", JSON.stringify(reviewList));
      } catch {

      }
    } catch (err) {
      console.error("Failed to load user data:", err);
    } finally {
      setIsLoadingConversations(false);
    }

    void fetchOverviewMetrics();

    if (currentUser.github_connected) {
      void fetchPullRequests();
    } else {
      setPullRequests([]);
      setPrsError(null);
    }
  };

  const checkAuthAndInitialize = async () => {
    setIsAuthChecking(true);

    agentApi.list().then(setAgents).catch(() => {});
    providerApi.getStatus().then(setProviderStatus).catch(() => {});

    try {

      const me = await authApi.getMe();
      setUser(me);
      try {
        sessionStorage.setItem("nexarion_user_cache", JSON.stringify(me));
      } catch {

      }
      await loadUserData(me);
    } catch {
      clearUserData();
    } finally {
      setIsAuthChecking(false);
    }
  };

  useEffect(() => {

    const params = new URLSearchParams(window.location.search);
    const urlToken = params.get("token");
    const authError = params.get("auth_error") || params.get("error");

    if (urlToken) {
      setToken(urlToken);
      const cleanPath =
        window.location.pathname === "/auth/google/callback" ? "/" : window.location.pathname;
      window.history.replaceState({}, document.title, cleanPath);
    }

    if (authError) {
      console.warn("OAuth authentication notice:", authError);
      window.history.replaceState({}, document.title, "/");
    }

    checkAuthAndInitialize();
  }, []);

  useEffect(() => {
    if (!activeConversationId) {
      setActiveConversation(null);
      setIsLoadingActiveConversation(false);
      return;
    }

    if (skipFetchConversationIdRef.current === activeConversationId) {

      skipFetchConversationIdRef.current = null;
      setIsLoadingActiveConversation(false);
      return;
    }

    const requestedId = activeConversationId;
    let isCurrent = true;
    setIsLoadingActiveConversation(true);
    conversationApi
      .get(requestedId)
      .then((conv) => {

        if (isCurrent && activeConvIdRef.current === requestedId) {
          const streamedContent = streamedContentRef.current.get(requestedId);
          if (streamedContent && activeStreamControllersRef.current.has(requestedId)) {
            const assistantMessage: Message = {
              id: streamingMessageIdsRef.current.get(requestedId) || `streaming-${requestedId}`,
              conversation_id: requestedId,
              role: "assistant",
              content: streamedContent,
              status: "streaming",
              created_at: new Date().toISOString(),
            };
            setActiveConversation({
              ...conv,
              messages: [...(conv.messages || []), assistantMessage],
            });
          } else {
            setActiveConversation(conv);
          }
        }
      })
      .catch((err) => {
        console.error("Failed to fetch conversation details:", err);
      })
      .finally(() => {
        if (isCurrent && activeConvIdRef.current === requestedId) {
          setIsLoadingActiveConversation(false);
        }
      });

    return () => {
      isCurrent = false;
    };
  }, [activeConversationId]);

  const handleStopGeneration = () => {
    const activeController = activeConversationId
      ? activeStreamControllersRef.current.get(activeConversationId) || abortControllerRef.current
      : [...activeStreamControllersRef.current.entries()].find(([key]) => key.startsWith("pending-"))?.[1]
        || abortControllerRef.current;
    activeController?.abort();
    if (activeConversationId) activeStreamControllersRef.current.delete(activeConversationId);
    if (abortControllerRef.current === activeController) abortControllerRef.current = null;
    setIsSendingMessage(false);
    setGenerationState("cancelled");
    setWaveState("idle");
    setTimeout(() => {
      setGenerationState((current) => (current === "cancelled" ? "idle" : current));
    }, 600);
    setActiveConversation((prev) => {
      if (!prev) return prev;
      return {
        ...prev,
        messages: (prev.messages || []).map((m) =>
          m.status === "streaming" ? { ...m, status: "sent" } : m
        ),
      };
    });
  };

  const handleSendMessage = async (
    content: string,
    diffContext?: string,
    provider?: string,
    model?: string,
    attachments?: Attachment[],
    startNewConversation = false
  ) => {
    if (isSendingMessage && !startNewConversation) return;

    const targetConvId = startNewConversation ? undefined : activeConversationId;
    const streamKey = targetConvId || `pending-${Date.now()}`;
    let streamConversationId = targetConvId;
    const selectionVersionAtStart = activeSelectionVersionRef.current;

    const isDiffReview = Boolean(diffContext && diffContext.trim().length > 0);
    setGenerationType(isDiffReview ? "diff" : "chat");
    setGenerationState("submitting");

    const userTempId = `temp-user-${Date.now()}`;
    const asstTempId = `temp-asst-${Date.now()}`;
    streamingMessageIdsRef.current.set(streamKey, asstTempId);
    if (targetConvId) streamingMessageIdsRef.current.set(targetConvId, asstTempId);

    const optimisticUserMsg: Message = {
      id: userTempId,
      conversation_id: targetConvId || streamKey,
      role: "user",
      content,
      status: "sent",
      attachments: attachments && attachments.length > 0 ? attachments : undefined,
      created_at: new Date().toISOString(),
    };

    const optimisticAsstMsg: Message = {
      id: asstTempId,
      conversation_id: targetConvId || streamKey,
      role: "assistant",
      content: "",
      status: "streaming",
      created_at: new Date().toISOString(),
    };

    if (!targetConvId) {
      const now = new Date().toISOString();
      const title = content.trim().slice(0, 60);
      setConversations((prev) => [
        {
          id: streamKey,
          title: title || "New Conversation",
          created_at: now,
          updated_at: now,
          message_count: 1,
        },
        ...prev,
      ]);
    }

    setActiveConversation((prev) => {
      if (prev) {
        return {
          ...prev,
          messages: [...(prev.messages || []), optimisticUserMsg, optimisticAsstMsg],
          attachments: [
            ...(prev.attachments || []),
            ...(attachments || []).filter(
              (a) => !(prev.attachments || []).some((ea) => ea.id === a.id)
            ),
          ],
        };
      }
      return {
        id: streamKey,
        title: content.slice(0, 50),
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
        messages: [optimisticUserMsg, optimisticAsstMsg],
        attachments: attachments || [],
      };
    });

    setIsSendingMessage(true);
    setWaveState("receiving");

    setTimeout(() => {
      setGenerationState((curr) =>
        curr === "submitting" ? (isDiffReview ? "reviewing" : "thinking") : curr
      );
      setWaveState((curr) =>
        curr === "receiving" ? (isDiffReview ? "reviewing" : "thinking") : curr
      );
    }, 180);

    const abortController = new AbortController();
    activeStreamControllersRef.current.set(streamKey, abortController);
    const targetProvider = provider || providerStatus?.active_provider;
    const attachmentIds = attachments
      ?.map((a) => a.id)
      .filter((id) => Boolean(id) && !id.startsWith("inline-") && !id.startsWith("temp-"));

    try {
      await conversationApi.streamMessage(
        targetConvId || null,
        {
          content,
          diffContext,
          provider: targetProvider,
          model,
          attachmentIds,
        },
        {
          signal: abortController.signal,
          onInit: (metadata) => {
            streamConversationId = metadata.id;
            activeStreamControllersRef.current.delete(streamKey);
            activeStreamControllersRef.current.set(metadata.id, abortController);
            const pendingContent = streamedContentRef.current.get(streamKey);
            const pendingMessageId = streamingMessageIdsRef.current.get(streamKey);
            if (pendingMessageId) {
              streamingMessageIdsRef.current.delete(streamKey);
              streamingMessageIdsRef.current.set(metadata.id, pendingMessageId);
            }
            if (pendingContent) {
              streamedContentRef.current.delete(streamKey);
              streamedContentRef.current.set(metadata.id, pendingContent);
            }
            const shouldFocus = targetConvId
              ? activeConvIdRef.current === targetConvId &&
                activeSelectionVersionRef.current === selectionVersionAtStart
              : activeConvIdRef.current === undefined &&
                activeSelectionVersionRef.current === selectionVersionAtStart;
            if (shouldFocus) {
              activeConvIdRef.current = metadata.id;
              setGenerationState(isDiffReview ? "reviewing" : "thinking");
              setWaveState(isDiffReview ? "reviewing" : "thinking");
              setActiveConversationId(metadata.id);
            }
            if (!targetConvId) {
              if (shouldFocus) {
                skipFetchConversationIdRef.current = metadata.id;
                setActiveConversation((prev) => {
                  if (!prev) {
                    return {
                      id: metadata.id,
                      title: metadata.title,
                      created_at: new Date().toISOString(),
                      updated_at: new Date().toISOString(),
                      messages: [
                        { ...optimisticUserMsg, conversation_id: metadata.id },
                        { ...optimisticAsstMsg, conversation_id: metadata.id },
                      ],
                    };
                  }
                  return {
                    ...prev,
                    id: metadata.id,
                    title: metadata.title,
                    messages: (prev.messages || []).map((m) => ({
                      ...m,
                      conversation_id: metadata.id,
                    })),
                  };
                });
              }
              setConversations((prev) => {
                const pendingConversation = prev.find((conversation) => conversation.id === streamKey);
                const resolvedConversation = {
                  id: metadata.id,
                  title: metadata.title,
                  created_at: pendingConversation?.created_at || new Date().toISOString(),
                  updated_at: new Date().toISOString(),
                  message_count: pendingConversation?.message_count || 1,
                };
                return [
                  resolvedConversation,
                  ...prev.filter(
                    (conversation) =>
                      conversation.id !== metadata.id && conversation.id !== streamKey
                  ),
                ];
              });
            }
          },
          onToken: (chunk) => {
            const contentKey = streamConversationId || targetConvId || streamKey;
            streamedContentRef.current.set(
              contentKey,
              (streamedContentRef.current.get(contentKey) || "") + chunk
            );
            if (activeConvIdRef.current !== (streamConversationId || targetConvId || undefined)) return;
            setGenerationState("streaming");
            setWaveState("responding");
            setActiveConversation((prev) => {
              if (!prev) return prev;
              if (streamConversationId && prev.id !== streamConversationId) return prev;
              const hasAsst = (prev.messages || []).some((m) => m.id === asstTempId);
              if (hasAsst) {
                return {
                  ...prev,
                  messages: (prev.messages || []).map((m) =>
                    m.id === asstTempId ? { ...m, content: m.content + chunk } : m
                  ),
                };
              }
              return {
                ...prev,
                messages: [
                  ...(prev.messages || []),
                  {
                    id: asstTempId,
                    conversation_id: prev.id,
                    role: "assistant",
                    content: chunk,
                    status: "streaming",
                    created_at: new Date().toISOString(),
                  },
                ],
              };
            });
          },
          onDone: (data) => {
            streamedContentRef.current.delete(streamConversationId || targetConvId || streamKey);
            streamingMessageIdsRef.current.delete(streamConversationId || targetConvId || streamKey);
            if (data.conversation_id) {
              setConversations((prev) =>
                prev.map((c) =>
                  c.id === data.conversation_id
                    ? { ...c, updated_at: new Date().toISOString() }
                    : c
                )
              );
            }
            if (activeConvIdRef.current !== (streamConversationId || targetConvId || undefined)) return;
            setGenerationState("completed");
            setWaveState("idle");
            setTimeout(() => {
              setGenerationState((curr) => (curr === "completed" ? "idle" : curr));
            }, 600);
            setActiveConversation((prev) => {
              if (!prev) return prev;
              const hasAsst = (prev.messages || []).some((m) => m.id === asstTempId);
              if (hasAsst) {
                return {
                  ...prev,
                  messages: (prev.messages || []).map((m) =>
                    m.id === asstTempId
                      ? {
                          ...m,
                          id: data.message_id || m.id,
                          conversation_id: data.conversation_id || m.conversation_id,
                          content: data.content || m.content,
                          status: "sent",
                          created_at: data.created_at || m.created_at,
                        }
                      : m
                  ),
                };
              }
              return {
                ...prev,
                messages: [
                  ...(prev.messages || []),
                  {
                    id: data.message_id || asstTempId,
                    conversation_id: data.conversation_id || prev.id,
                    role: "assistant",
                    content: data.content || "",
                    status: "sent",
                    created_at: data.created_at || new Date().toISOString(),
                  },
                ],
              };
            });
          },
          onError: (err) => {
            streamedContentRef.current.delete(streamConversationId || targetConvId || streamKey);
            streamingMessageIdsRef.current.delete(streamConversationId || targetConvId || streamKey);
            if (activeConvIdRef.current !== (streamConversationId || targetConvId || undefined)) return;
            setGenerationState("error");
            setWaveState("error");
            setTimeout(() => {
              setGenerationState((curr) => (curr === "error" ? "idle" : curr));
              setWaveState("idle");
            }, 2500);
            setActiveConversation((prev) => {
              if (!prev) return prev;
              const hasAsst = (prev.messages || []).some((m) => m.id === asstTempId);
              if (hasAsst) {
                return {
                  ...prev,
                  messages: (prev.messages || []).map((m) =>
                    m.id === asstTempId
                      ? {
                          ...m,
                          status: "error",
                          error:
                            err.user_message ||
                            "Something went wrong while generating your response. Please try again.",
                        }
                      : m
                  ),
                };
              }
              return {
                ...prev,
                messages: [
                  ...(prev.messages || []),
                  {
                    id: asstTempId,
                    conversation_id: prev.id,
                    role: "assistant",
                    content: "",
                    status: "error",
                    error:
                      err.user_message ||
                      "Something went wrong while generating your response. Please try again.",
                    created_at: new Date().toISOString(),
                  },
                ],
              };
            });
          },
        }
      );
    } catch (err: unknown) {
      if ((err as { name?: string })?.name === "AbortError") {
        if (activeConvIdRef.current === (streamConversationId || targetConvId || undefined)) {
          setGenerationState("cancelled");
          setWaveState("idle");
          setTimeout(() => {
            setGenerationState((curr) => (curr === "cancelled" ? "idle" : curr));
          }, 600);
        }
      } else {
        if (activeConvIdRef.current === (streamConversationId || targetConvId || undefined)) {
          setGenerationState("error");
          setWaveState("error");
          setTimeout(() => {
            setGenerationState((curr) => (curr === "error" ? "idle" : curr));
            setWaveState("idle");
          }, 2500);
        }
        const safeError = sanitizeErrorMessage(err instanceof Error ? err.message : "");
        setActiveConversation((prev) => {
          if (
            !prev ||
            activeSelectionVersionRef.current !== selectionVersionAtStart ||
            (streamConversationId && prev.id !== streamConversationId)
          ) return prev;
          const hasAsst = (prev.messages || []).some((m) => m.id === asstTempId);
          if (hasAsst) {
            return {
              ...prev,
              messages: (prev.messages || []).map((m) =>
                m.id === asstTempId
                  ? {
                      ...m,
                      status: "error",
                      error:
                        safeError ||
                        "Something went wrong while generating your response. Please try again.",
                    }
                  : m
              ),
            };
          }
          return {
            ...prev,
            messages: [
              ...(prev.messages || []),
              {
                id: asstTempId,
                conversation_id: prev.id,
                role: "assistant",
                content: "",
                status: "error",
                error:
                  safeError ||
                  "Something went wrong while generating your response. Please try again.",
                created_at: new Date().toISOString(),
              },
            ],
          };
        });
      }
    } finally {
      activeStreamControllersRef.current.delete(streamKey);
      if (streamConversationId) activeStreamControllersRef.current.delete(streamConversationId);
      streamedContentRef.current.delete(streamKey);
      if (streamConversationId) streamedContentRef.current.delete(streamConversationId);
      streamingMessageIdsRef.current.delete(streamKey);
      if (streamConversationId) streamingMessageIdsRef.current.delete(streamConversationId);
      if (activeConvIdRef.current === (streamConversationId || targetConvId || undefined)) {
        setIsSendingMessage(false);
      }
    }
  };

  const handleRetryMessage = async (failedMsgId: string) => {
    if (isSendingMessage || !activeConversation) return;

    const msgIndex = (activeConversation.messages || []).findIndex((m) => m.id === failedMsgId);
    if (msgIndex === -1) return;

    const targetMsg = activeConversation.messages![msgIndex];

    if (targetMsg.role === "assistant") {
      // Regenerate the assistant reply for the conversation context without duplicating user messages
      await handleRegenerateMessage(targetMsg.id);
    } else {

      const userPrompt = targetMsg.content;
      const targetAtts = targetMsg.attachments;
      setActiveConversation((prev) => {
        if (!prev) return prev;
        return {
          ...prev,
          messages: (prev.messages || []).filter((m) => m.id !== failedMsgId),
        };
      });
      await handleSendMessage(userPrompt, undefined, undefined, undefined, targetAtts);
    }
  };

  const handleRegenerateMessage = async (
    messageId?: string,
    provider?: string,
    model?: string,
    diffContext?: string
  ) => {
    if (!activeConversationId || isSendingMessage) return;

    const targetMsgId =
      messageId ||
      activeConversation?.messages?.filter((m) => m.role === "assistant").pop()?.id;
    if (!targetMsgId) return;

    const isDiffReview = Boolean(diffContext && diffContext.trim().length > 0);
    setGenerationType(isDiffReview ? "diff" : "chat");
    setGenerationState("submitting");

    setActiveConversation((prev) => {
      if (!prev) return prev;
      return {
        ...prev,
        messages: (prev.messages || []).map((m) =>
          m.id === targetMsgId ? { ...m, content: "", status: "streaming", error: undefined } : m
        ),
      };
    });

    setIsSendingMessage(true);
    setWaveState(isDiffReview ? "reviewing" : "thinking");
    setTimeout(() => {
      setGenerationState((curr) =>
        curr === "submitting" ? (isDiffReview ? "reviewing" : "thinking") : curr
      );
    }, 180);

    const abortController = new AbortController();
    abortControllerRef.current = abortController;

    const targetProvider = provider || providerStatus?.active_provider;

    try {
      await conversationApi.streamRegenerate(
        activeConversationId,
        {
          messageId: targetMsgId,
          provider: targetProvider,
          model,
          diffContext,
        },
        {
          signal: abortController.signal,
          onToken: (chunk) => {
            setGenerationState("streaming");
            setWaveState("responding");
            setActiveConversation((prev) => {
              if (!prev) return prev;
              return {
                ...prev,
                messages: (prev.messages || []).map((m) =>
                  m.id === targetMsgId ? { ...m, content: m.content + chunk } : m
                ),
              };
            });
          },
          onDone: (data) => {
            setGenerationState("completed");
            setWaveState("idle");
            setTimeout(() => {
              setGenerationState((curr) => (curr === "completed" ? "idle" : curr));
            }, 600);
            setActiveConversation((prev) => {
              if (!prev) return prev;
              return {
                ...prev,
                messages: (prev.messages || []).map((m) =>
                  m.id === targetMsgId
                    ? {
                        ...m,
                        id: data.message_id || m.id,
                        content: data.content || m.content,
                        status: "sent",
                        created_at: data.created_at || m.created_at,
                      }
                    : m
                ),
              };
            });
          },
          onError: (err) => {
            setGenerationState("error");
            setWaveState("error");
            setTimeout(() => {
              setGenerationState((curr) => (curr === "error" ? "idle" : curr));
              setWaveState("idle");
            }, 2500);
            setActiveConversation((prev) => {
              if (!prev) return prev;
              return {
                ...prev,
                messages: (prev.messages || []).map((m) =>
                  m.id === targetMsgId
                    ? {
                        ...m,
                        status: "error",
                        error: err.user_message || "Something went wrong while generating your response. Please try again.",
                      }
                    : m
                ),
              };
            });
          },
        }
      );
    } catch (err: unknown) {
      if ((err as { name?: string })?.name === "AbortError") {
        setGenerationState("cancelled");
        setWaveState("idle");
        setTimeout(() => {
          setGenerationState((curr) => (curr === "cancelled" ? "idle" : curr));
        }, 600);
      } else {
        setGenerationState("error");
        setWaveState("error");
        setTimeout(() => {
          setGenerationState((curr) => (curr === "error" ? "idle" : curr));
          setWaveState("idle");
        }, 2500);
        const safeError = sanitizeErrorMessage(err instanceof Error ? err.message : "");
        setActiveConversation((prev) => {
          if (!prev) return prev;
          return {
            ...prev,
            messages: (prev.messages || []).map((m) =>
              m.id === targetMsgId
                ? {
                    ...m,
                    status: "error",
                    error: safeError || "Something went wrong while generating your response. Please try again.",
                  }
                : m
            ),
          };
        });
      }
    } finally {
      setIsSendingMessage(false);
      abortControllerRef.current = null;
    }
  };

  const handleEditMessage = async (
    messageId: string,
    newContent: string,
    diffContext?: string,
    provider?: string,
    model?: string,
    attachmentIds?: string[],
    onSaved?: () => void
  ) => {
    if (!activeConversationId || isSendingMessage) return;

    const conv = activeConversation;
    if (!conv || !conv.messages) return;

    const targetIdx = conv.messages.findIndex((m) => m.id === messageId);
    if (targetIdx === -1) return;

    const targetConvId = activeConversationId;
    const previousConv = conv;

    const existingAttachmentIds =
      conv.messages[targetIdx].attachments?.map((a) => a.id) || [];
    const effectiveAttachmentIds = (
      attachmentIds ?? (existingAttachmentIds.length > 0 ? existingAttachmentIds : undefined)
    )?.filter((id) => Boolean(id) && !id.startsWith("inline-") && !id.startsWith("temp-"));

    const updatedUserMsg: Message = {
      ...conv.messages[targetIdx],
      content: newContent,
      status: "sent",
    };

    const asstTempId = `temp-asst-${Date.now()}`;
    const optimisticAsstMsg: Message = {
      id: asstTempId,
      conversation_id: targetConvId,
      role: "assistant",
      content: "",
      status: "streaming",
      created_at: new Date().toISOString(),
    };

    const newMessages = [
      ...conv.messages.slice(0, targetIdx),
      updatedUserMsg,
      optimisticAsstMsg,
    ];

    setActiveConversation({
      ...conv,
      messages: newMessages,
    });

    setIsSendingMessage(true);
    setWaveState("receiving");
    setGenerationType(diffContext ? "diff" : "chat");
    setGenerationState("submitting");

    setTimeout(() => {
      setGenerationState(diffContext ? "reviewing" : "thinking");
      setWaveState(diffContext ? "reviewing" : "thinking");
    }, 180);

    const abortController = new AbortController();
    abortControllerRef.current = abortController;

    const targetProvider = provider || providerStatus?.active_provider;

    try {
      await conversationApi.streamEditMessage(
        targetConvId,
        messageId,
        {
          content: newContent,
          diffContext,
          provider: targetProvider,
          model,
          attachmentIds: effectiveAttachmentIds,
        },
        {
          signal: abortController.signal,
          onSaved: () => {
            if (onSaved) onSaved();
          },
          onToken: (chunk) => {
            setGenerationState("streaming");
            setWaveState("responding");
            setActiveConversation((prev) => {
              if (!prev || prev.id !== targetConvId) return prev;
              return {
                ...prev,
                messages: (prev.messages || []).map((m) =>
                  m.id === asstTempId ? { ...m, content: m.content + chunk } : m
                ),
              };
            });
          },
          onDone: (data) => {
            setGenerationState("completed");
            setWaveState("idle");
            setTimeout(() => {
              setGenerationState((curr) => (curr === "completed" ? "idle" : curr));
            }, 600);
            setActiveConversation((prev) => {
              if (!prev || prev.id !== targetConvId) return prev;
              return {
                ...prev,
                messages: (prev.messages || []).map((m) =>
                  m.id === asstTempId
                    ? {
                        ...m,
                        id: data.message_id || m.id,
                        content: data.content || m.content,
                        status: "sent",
                        created_at: data.created_at || m.created_at,
                      }
                    : m
                ),
              };
            });
          },
          onError: (err) => {
            setGenerationState("error");
            setWaveState("error");
            setTimeout(() => {
              setGenerationState((curr) => (curr === "error" ? "idle" : curr));
              setWaveState("idle");
            }, 2500);
            setActiveConversation((prev) => {
              if (!prev || prev.id !== targetConvId) return prev;
              return {
                ...prev,
                messages: (prev.messages || []).map((m) =>
                  m.id === asstTempId
                    ? {
                        ...m,
                        status: "error",
                        error:
                          err.user_message ||
                          "Something went wrong while generating your response. Please try again.",
                      }
                    : m
                ),
              };
            });
          },
        }
      );
    } catch (err: unknown) {
      if ((err as { name?: string })?.name === "AbortError") {
        setGenerationState("cancelled");
        setWaveState("idle");
        setTimeout(() => {
          setGenerationState((curr) => (curr === "cancelled" ? "idle" : curr));
        }, 600);
      } else {

        setActiveConversation(previousConv);
        setGenerationState("error");
        setWaveState("error");
        setTimeout(() => {
          setGenerationState((curr) => (curr === "error" ? "idle" : curr));
          setWaveState("idle");
        }, 2500);
        throw err;
      }
    } finally {
      setIsSendingMessage(false);
      abortControllerRef.current = null;
    }
  };

  const handleFeedbackMessage = async (
    messageId: string,
    feedback: "helpful" | "unhelpful" | null
  ) => {
    if (!activeConversationId) return;
    try {
      const updatedMsg = await conversationApi.setFeedback(
        activeConversationId,
        messageId,
        feedback
      );
      setActiveConversation((prev) => {
        if (!prev || !prev.messages) return prev;
        return {
          ...prev,
          messages: prev.messages.map((m) =>
            m.id === messageId ? { ...m, feedback: updatedMsg.feedback } : m
          ),
        };
      });
    } catch (err) {
      console.error("Failed to submit feedback:", err);
    }
  };

  const handleNewChat = useCallback(() => {
    activeSelectionVersionRef.current += 1;
    setIsMobileMenuOpen(false);
    if (isSendingMessage && abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
      setIsSendingMessage(false);
      setGenerationState("idle");
      setWaveState("idle");
    }
    setIsSendingMessage(false);
    setGenerationState("idle");
    setWaveState("idle");
    setIsMobileNavOpen(false);
    setActiveConversation(null);
    setIsLoadingActiveConversation(false);
    navigateTo("chat", undefined);
  }, [isSendingMessage, navigateTo]);

  const handleSelectConversation = useCallback(
    (id: string) => {
      setIsMobileNavOpen(false);
      if (id === activeConversationId) {
        navigateTo("chat", id, true);
        return;
      }
      if (isSendingMessage && abortControllerRef.current) {
        abortControllerRef.current.abort();
        abortControllerRef.current = null;
        setIsSendingMessage(false);
        setGenerationState("idle");
        setWaveState("idle");
      }
      setIsLoadingActiveConversation(true);
      setActiveConversation(null);
      navigateTo("chat", id);
      const isGeneratingSelectedConversation = activeStreamControllersRef.current.has(id);
      setIsSendingMessage(isGeneratingSelectedConversation);
      setGenerationState(isGeneratingSelectedConversation ? "streaming" : "idle");
      setWaveState(isGeneratingSelectedConversation ? "responding" : "idle");
    },
    [activeConversationId, isSendingMessage, navigateTo]
  );

  const handleDeleteConversation = async (id: string) => {
    try {
      await conversationApi.delete(id);
      const remaining = conversations.filter((c) => c.id !== id);
      setConversations(remaining);
      if (activeConversationId === id) {
        if (remaining.length > 0) {
          setActiveConversationId(remaining[0].id);
        } else {
          handleNewChat();
        }
      }
    } catch (err) {
      console.error("Failed to delete conversation:", err);
    }
  };

  const handleRenameConversation = async (id: string, title: string) => {
    try {
      setConversations((prev) =>
        prev.map((c) => (c.id === id ? { ...c, title } : c))
      );
      if (activeConversation?.id === id) {
        setActiveConversation((prev) => (prev ? { ...prev, title } : prev));
      }
      await conversationApi.update(id, { title });
    } catch (err) {
      console.error("Failed to rename conversation:", err);
      conversationApi.list().then(setConversations).catch(() => {});
    }
  };

  const handleTogglePinConversation = async (id: string, isPinned: boolean) => {
    try {
      setConversations((prev) =>
        prev.map((c) => (c.id === id ? { ...c, is_pinned: isPinned } : c))
      );
      if (activeConversation?.id === id) {
        setActiveConversation((prev) => (prev ? { ...prev, is_pinned: isPinned } : prev));
      }
      await conversationApi.update(id, { is_pinned: isPinned });
    } catch (err) {
      console.error("Failed to toggle pin:", err);
      conversationApi.list().then(setConversations).catch(() => {});
    }
  };

  const handleSetConversationSection = async (id: string, sectionName: string | null) => {
    try {
      setConversations((prev) =>
        prev.map((c) => (c.id === id ? { ...c, section_name: sectionName } : c))
      );
      if (activeConversation?.id === id) {
        setActiveConversation((prev) => (prev ? { ...prev, section_name: sectionName } : prev));
      }
      await conversationApi.update(id, { section_name: sectionName });
    } catch (err) {
      console.error("Failed to set section:", err);
      conversationApi.list().then(setConversations).catch(() => {});
    }
  };

  const handleArchiveConversation = async (id: string) => {
    try {
      setConversations((prev) =>
        prev.map((c) => (c.id === id ? { ...c, is_archived: true } : c))
      );
      if (activeConversationId === id) {
        const remainingActive = conversations.filter(
          (c) => c.id !== id && !c.is_archived
        );
        if (remainingActive.length > 0) {
          setActiveConversationId(remainingActive[0].id);
        } else {
          handleNewChat();
        }
      }
      await conversationApi.update(id, { is_archived: true });
    } catch (err) {
      console.error("Failed to archive conversation:", err);
      conversationApi.list(true).then(setConversations).catch(() => {});
    }
  };

  const handleUnarchiveConversation = async (id: string) => {
    try {
      setConversations((prev) =>
        prev.map((c) => (c.id === id ? { ...c, is_archived: false } : c))
      );
      await conversationApi.update(id, { is_archived: false });
    } catch (err) {
      console.error("Failed to unarchive conversation:", err);
      conversationApi.list(true).then(setConversations).catch(() => {});
    }
  };

  const handleDeleteReview = async (id: string) => {
    try {
      await reviewApi.delete(id);
      setReviews((prev) => prev.filter((r) => r.id !== id));
      if (selectedReview?.id === id) {
        setIsDetailOpen(false);
        setSelectedReview(null);
      }
      fetchOverviewMetrics().catch(() => {});
    } catch (err) {
      console.error("Failed to delete review:", err);
      throw err;
    }
  };

  const handleClearReviews = async () => {
    try {
      await reviewApi.clearAll();
      setReviews([]);
      setSelectedReview(null);
      setIsDetailOpen(false);
      fetchOverviewMetrics().catch(() => {});
    } catch (err) {
      console.error("Failed to clear reviews:", err);
      throw err;
    }
  };

  const handleOpenReviewDetail = async (review: Review) => {
    const requestId = ++reviewDetailRequestRef.current;
    setSelectedReview(review);
    setIsDetailOpen(true);
    const hasDetails = review.diff_content !== undefined && review.findings !== undefined;
    setIsReviewDetailLoading(!hasDetails);
    if (hasDetails) return;
    try {
      const full = await reviewApi.get(review.id);
      if (reviewDetailRequestRef.current === requestId) setSelectedReview(full);
    } catch {
      // Keep the summary visible if the detail request fails.
    } finally {
      if (reviewDetailRequestRef.current === requestId) setIsReviewDetailLoading(false);
    }
  };

  const handleReviewCreated = (review: Review) => {
    reviewDetailRequestRef.current += 1;
    setReviews((prev) => [review, ...prev]);
    setSelectedReview(review);
    setIsDetailOpen(true);
    setIsReviewDetailLoading(false);
    fetchOverviewMetrics().catch(() => {});
  };

  const handleStartReview = (sampleDiff?: string) => {
    setComposerInitialDiff(sampleDiff || "");
    setComposerTitle("");
    setComposerRepo("");
    setIsComposerLoadingDiff(false);
    setComposerDiffError(null);
    prDiffFetchRef.current = null;
    setIsComposerOpen(true);
  };

  const handleReviewPr = (pr: PullRequest) => {
    const title = pr.title || `Review PR #${pr.pr_number}`;
    const repo = pr.repository_name || "";
    setReviewingPrNumber(String(pr.pr_number));
    setComposerTitle(title);
    setComposerRepo(repo);
    setComposerInitialDiff("");
    setComposerDiffError(null);
    setIsComposerLoadingDiff(true);

    setIsComposerOpen(true);

    const fetchDiff = async () => {
      setIsComposerLoadingDiff(true);
      setComposerDiffError(null);
      try {
        let diffContent = "";
        if (repo && repo.includes("/")) {
          const [owner, repoName] = repo.split("/");
          const diffData = await githubApi.getDiff(owner, repoName, pr.pr_number);
          diffContent = diffData.diff;
        }
        setComposerInitialDiff(diffContent);
      } catch (err) {
        console.warn("Could not fetch remote diff for PR:", err);
        setComposerDiffError(err instanceof Error ? err.message : "Failed to load PR changes.");
      } finally {
        setIsComposerLoadingDiff(false);
        setReviewingPrNumber(null);
      }
    };

    prDiffFetchRef.current = fetchDiff;
    fetchDiff();
  };

  const handleToggleAgent = useCallback(
    async (agentId: string, isEnabled: boolean) => {
      // 1. Avoid duplicate requests if agent is already in the target state
      const currentAgent = agents.find((a) => a.agent_id === agentId);
      if (currentAgent && currentAgent.is_enabled === isEnabled) {
        return;
      }

      const previousConfirmedState = currentAgent ? currentAgent.is_enabled : !isEnabled;

      // 2. Increment per-agent sequence to prevent race conditions on rapid clicking
      const nextSeq = (agentToggleSeqRef.current.get(agentId) || 0) + 1;
      agentToggleSeqRef.current.set(agentId, nextSeq);

      // 3. Optimistic UI update: immediate transition (< 100ms)
      setAgents((prev) =>
        prev.map((a) => (a.agent_id === agentId ? { ...a, is_enabled: isEnabled } : a))
      );

      // 4. Send configuration update to backend asynchronously
      try {
        const updated = await agentApi.toggleAgent(agentId, isEnabled);
        // Only reconcile if this is still the latest user action
        if (agentToggleSeqRef.current.get(agentId) === nextSeq) {
          setAgents((prev) =>
            prev.map((a) => (a.agent_id === agentId ? { ...a, ...updated, is_enabled: updated.is_enabled } : a))
          );
        }
      } catch (err) {
        // Rollback if this request failed and no newer action was taken
        if (agentToggleSeqRef.current.get(agentId) === nextSeq) {
          setAgents((prev) =>
            prev.map((a) => (a.agent_id === agentId ? { ...a, is_enabled: previousConfirmedState } : a))
          );
          const rawMessage = err instanceof Error ? err.message : `Failed to update agent '${agentId}'.`;
          const safeMessage = sanitizeErrorMessage(rawMessage);
          setAgentToast({
            message: `Could not toggle agent: ${safeMessage}`,
            type: "error",
          });
          if (agentToastTimerRef.current) {
            clearTimeout(agentToastTimerRef.current);
          }
          agentToastTimerRef.current = setTimeout(() => {
            setAgentToast(null);
          }, 4500);
        }
      }
    },
    [agents]
  );

  const handleLogout = async () => {
    try {
      await authApi.logout();
    } catch {

    } finally {
      clearUserData();
      navigateTo("chat", undefined);
      setIsAuthOpen(true);
    }
  };

  return (
    <div className="relative h-[100dvh] w-screen max-w-full bg-black text-white flex flex-col font-sans overflow-hidden">

      {isAuthChecking && (
        <div className="absolute top-0 left-0 right-0 h-0.5 bg-gradient-to-r from-transparent via-white/80 to-transparent animate-pulse z-50 pointer-events-none" />
      )}

      {/* Tap-anywhere backdrop to auto-close 3-dots mobile menu */}
      {isMobileMenuOpen && (
        <div
          className="fixed inset-0 z-20 bg-black/25 backdrop-blur-[1px] md:hidden cursor-pointer"
          onClick={() => setIsMobileMenuOpen(false)}
          onTouchStart={() => setIsMobileMenuOpen(false)}
          aria-hidden="true"
        />
      )}

      {/* Mobile Header Bar */}
      <header className="md:hidden flex-shrink-0 flex items-center justify-between px-2.5 sm:px-4 py-2 pt-[max(0.625rem,env(safe-area-inset-top))] bg-black/90 backdrop-blur-md border-b border-white/10 z-30">
        <div className="flex items-center gap-1 min-w-0">
          <button
            type="button"
            onClick={() => setIsMobileNavOpen(true)}
            className="w-11 h-11 flex items-center justify-center rounded-xl text-neutral-300 hover:text-white hover:bg-white/10 active:bg-white/20 transition-colors cursor-pointer flex-shrink-0"
            aria-label={isMobileNavOpen ? "Close sidebar" : "Open sidebar"}
            title="Open sidebar"
          >
            <MenuIcon className="w-5 h-5" />
          </button>

          {canGoBack && (
            <button
              type="button"
              onClick={handleGoBack}
              className="w-11 h-11 flex items-center justify-center rounded-xl text-neutral-300 hover:text-white hover:bg-white/10 active:bg-white/20 transition-colors flex-shrink-0 cursor-pointer"
              aria-label="Go back"
              title="Go back"
            >
              <BackIcon className="w-5 h-5" />
            </button>
          )}

          <div className="min-w-0 px-1.5 flex flex-col justify-center">
            {currentView === "chat" ? (
              <>
                <h1 className="text-sm sm:text-base font-semibold text-white tracking-tight truncate max-w-[160px] xs:max-w-[220px] sm:max-w-xs">
                  {activeConversation?.title || "NEXARION"}
                </h1>
                <span className="text-[11px] text-neutral-400 font-mono truncate block">
                  {activeConversation
                    ? `${activeConversation.messages?.length || 0} messages`
                    : "Coding Assistant"}
                </span>
              </>
            ) : (
              <>
                <h1 className="text-xs sm:text-sm font-semibold text-white tracking-tight truncate max-w-[180px] sm:max-w-xs capitalize">
                  {currentView === "prs"
                    ? "Pull Requests"
                    : currentView === "history"
                    ? "Review History"
                    : currentView}
                </h1>
                <span className="text-[11px] text-neutral-400 font-mono truncate block">
                  NEXARION Code Review
                </span>
              </>
            )}
          </div>
        </div>

        <div className="flex items-center gap-1 flex-shrink-0">
          <button
            type="button"
            onClick={handleNewChat}
            className="h-9 px-2.5 rounded-xl bg-white/10 hover:bg-white/20 active:bg-white/30 text-white font-mono text-xs flex items-center gap-1.5 transition-colors cursor-pointer shadow-sm border border-white/10"
            title="Start new conversation"
            aria-label="New chat"
          >
            <PlusIcon className="w-4 h-4" />
            <span className="hidden xs:inline">Chat</span>
          </button>

          <div className="relative" ref={mobileMenuRef}>
            <button
              type="button"
              onClick={() => setIsMobileMenuOpen((prev) => !prev)}
              className={`w-11 h-11 flex items-center justify-center rounded-xl text-neutral-400 hover:text-white hover:bg-white/10 active:bg-white/20 transition-colors cursor-pointer ${
                isMobileMenuOpen ? "text-white bg-white/10 ring-1 ring-white/25" : ""
              }`}
              aria-label="More actions"
              aria-expanded={isMobileMenuOpen}
              aria-haspopup="true"
              title="More actions"
            >
              <svg className="w-5 h-5" viewBox="0 0 24 24" fill="currentColor">
                <circle cx="12" cy="5" r="1.75" />
                <circle cx="12" cy="12" r="1.75" />
                <circle cx="12" cy="19" r="1.75" />
              </svg>
            </button>

            {isMobileMenuOpen && (
              <div
                role="menu"
                aria-orientation="vertical"
                className="absolute right-0 top-full mt-1.5 w-48 py-1.5 rounded-xl bg-neutral-900 border border-white/15 shadow-2xl z-50 animate-fade-in text-xs font-mono"
              >
                <button
                  type="button"
                  onClick={() => {
                    setIsMobileMenuOpen(false);
                    handleStartReview();
                  }}
                  className="w-full flex items-center gap-2.5 px-3.5 py-2.5 text-left text-neutral-200 hover:text-white hover:bg-white/10 transition-colors cursor-pointer"
                >
                  <CodeIcon className="w-4 h-4 text-neutral-400" />
                  <span>+ New Review</span>
                </button>

                {currentView === "chat" && activeConversation && (
                  <button
                    type="button"
                    onClick={() => {
                      setIsMobileMenuOpen(false);
                      handleDeleteConversation(activeConversation.id);
                    }}
                    className="w-full flex items-center gap-2.5 px-3.5 py-2.5 text-left text-red-400 hover:text-red-300 hover:bg-red-500/10 transition-colors cursor-pointer"
                  >
                    <CloseIcon className="w-4 h-4" />
                    <span>Delete Thread</span>
                  </button>
                )}

                <div className="my-1 border-t border-white/10" />

                <button
                  type="button"
                  onClick={() => {
                    setIsMobileMenuOpen(false);
                    navigateTo("settings");
                  }}
                  className="w-full flex items-center gap-2.5 px-3.5 py-2.5 text-left text-neutral-300 hover:text-white hover:bg-white/10 transition-colors cursor-pointer"
                >
                  <SettingsIcon className="w-4 h-4 text-neutral-400" />
                  <span>Settings</span>
                </button>
              </div>
            )}
          </div>
        </div>
      </header>

      <div className="flex-1 flex w-full min-h-0 overflow-hidden relative">

        <Sidebar
          currentView={currentView}
          onSelectView={handleSelectView}
          conversations={conversations}
          activeConversationId={activeConversationId}
          onSelectConversation={handleSelectConversation}
          onNewChat={handleNewChat}
          onNewReview={() => handleStartReview()}
          onRenameConversation={handleRenameConversation}
          onTogglePinConversation={handleTogglePinConversation}
          onSetConversationSection={handleSetConversationSection}
          onArchiveConversation={handleArchiveConversation}
          onUnarchiveConversation={handleUnarchiveConversation}
          onDeleteConversation={handleDeleteConversation}
          onDeleteReview={handleDeleteReview}
          onOpenGitHub={() => setIsGitHubModalOpen(true)}
          reviews={reviews}
          user={user}
          isLoadingConversations={isLoadingConversations}
          onOpenSettings={() => handleSelectView("settings")}
          onLogout={handleLogout}
          onOpenAuth={() => setIsAuthOpen(true)}
          isMobileOpen={isMobileNavOpen}
          onCloseMobile={() => setIsMobileNavOpen(false)}
          isCollapsed={isSidebarCollapsed}
          onToggleCollapse={handleToggleSidebarCollapse}
        />

        <main
          className={`flex-1 flex flex-col ${
            isSidebarCollapsed ? "md:pl-0" : "md:pl-[260px]"
          } transition-[padding] duration-300 w-full min-h-0 relative z-10 overflow-hidden`}
        >

          {isSidebarCollapsed && (
            <button
              type="button"
              onClick={() => {
                setIsSidebarCollapsed(false);
                try {
                  localStorage.setItem("nexarion_sidebar_collapsed", "false");
                } catch {

                }
              }}
              className="hidden md:flex items-center gap-2 px-2.5 py-1.5 rounded-lg bg-[#141414]/90 hover:bg-[#202020] text-neutral-300 hover:text-white border border-white/10 text-xs font-mono shadow-xl transition-all fixed top-3 left-4 z-40 cursor-pointer backdrop-blur"
              title="Open sidebar"
              aria-label="Open sidebar"
            >
              <svg
                className="w-4 h-4 text-neutral-400"
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
              <span>Sidebar</span>
            </button>
          )}

          {currentView !== "chat" && (
            <div className="hidden md:flex flex-shrink-0 items-center justify-between px-6 py-4 min-h-[61px] border-b border-white/10 bg-black/60 backdrop-blur-md">
              <button
                type="button"
                onClick={handleGoBack}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-white/5 hover:bg-white/10 text-neutral-300 hover:text-white border border-white/10 text-xs font-mono transition-colors cursor-pointer"
                aria-label="Back"
                title="Back (Alt + Left Arrow)"
              >
                <BackIcon className="w-[18px] h-[18px]" />
                <span>Back</span>
              </button>
              <span className="text-xs font-mono text-neutral-400 capitalize">
                {currentView === "prs" ? "Pull Requests" : currentView}
              </span>
            </div>
          )}

          <div className="flex-1 flex flex-col w-full min-h-0 relative">
            <div
              className={
                currentView === "chat"
                  ? "flex-1 flex flex-col w-full h-full min-h-0 overflow-hidden"
                  : "hidden"
              }
            >
              <AIConversationWorkspace
                conversation={activeConversation}
                isLoadingConversation={isLoadingActiveConversation}
                loadingConversationTitle={
                  conversations.find((item) => item.id === activeConversationId)?.title
                }
                user={user}
                generationState={generationState}
                generationType={generationType}
                onSendMessage={handleSendMessage}
                onEditMessage={handleEditMessage}
                onNewConversation={handleNewChat}
                onDeleteConversation={handleDeleteConversation}
                onStartReview={handleStartReview}
                onNavigatePrs={() => handleSelectView("prs")}
                onNavigateAgents={() => handleSelectView("agents")}
                onNavigateHistory={() => handleSelectView("history")}
                onBack={canGoBack ? handleGoBack : undefined}
                activeProvider={providerStatus?.active_provider || "nvidia"}
                providerStatus={providerStatus}
                isSending={isSendingMessage}
                setWaveState={setWaveState}
                onRegenerateMessage={handleRegenerateMessage}
                onFeedbackMessage={handleFeedbackMessage}
                onRetryMessage={handleRetryMessage}
                onStopGeneration={handleStopGeneration}
                initialPrompt={pendingComposerPrompt}
                onPromptConsumed={() => setPendingComposerPrompt(null)}
              />
            </div>

            {currentView === "overview" && (
              <div className="flex-1 flex flex-col w-full h-full min-h-0 overflow-y-auto overscroll-y-contain">
                <OverviewPage
                  metrics={overviewMetrics}
                  isLoading={isOverviewLoading}
                  error={overviewError}
                  onRetry={fetchOverviewMetrics}
                  onStartReview={() => handleStartReview()}
                  onOpenReviewDetail={handleOpenReviewDetail}
                  onNavigatePrs={() => handleSelectView("prs")}
                  onNavigateAgents={() => handleSelectView("agents")}
                  onNavigateHistory={() => handleSelectView("history")}
                  onConnectGitHub={() => setIsGitHubModalOpen(true)}
                />
              </div>
            )}

            {currentView === "prs" && (
              <div className="flex-1 flex flex-col w-full h-full min-h-0 overflow-y-auto overscroll-y-contain">
                <PullRequestsPage
                  pullRequests={pullRequests}
                  isLoading={isPrsLoading}
                  error={prsError}
                  isGitHubConnected={Boolean(user?.github_connected)}
                  isReviewingId={reviewingPrNumber}
                  onRetry={fetchPullRequests}
                  onConnectGitHub={() => setIsGitHubModalOpen(true)}
                  onReviewPr={handleReviewPr}
                />
              </div>
            )}

            {currentView === "agents" && (
              <div className="flex-1 flex flex-col w-full h-full min-h-0 overflow-y-auto overscroll-y-contain">
                <AgentsPage agents={agents} onToggleAgent={handleToggleAgent} />
              </div>
            )}

            {currentView === "history" && (
              <div className="flex-1 flex flex-col w-full h-full min-h-0 overflow-y-auto overscroll-y-contain">
                <HistoryPage
                  reviews={reviews}
                  onOpenReviewDetail={handleOpenReviewDetail}
                  onStartReview={() => handleStartReview()}
                  onDeleteReview={handleDeleteReview}
                  onClearReviews={handleClearReviews}
                />
              </div>
            )}

            {currentView === "settings" && (
              <div className="flex-1 flex flex-col w-full h-full min-h-0 overflow-y-auto overscroll-y-contain">
                <SettingsPage
                  user={user}
                  onUserUpdated={(updatedUser) => {
                    setUser(updatedUser);
                    if (updatedUser.github_connected) {
                      fetchPullRequests();
                      fetchOverviewMetrics();
                    }
                  }}
                />
              </div>
            )}
          </div>
        </main>
      </div>

      <ReviewComposerModal
        isOpen={isComposerOpen}
        onClose={() => {
          setIsComposerOpen(false);
          setIsComposerLoadingDiff(false);
          setComposerDiffError(null);
        }}
        onReviewCreated={handleReviewCreated}
        setWaveState={setWaveState}
        initialDiff={composerInitialDiff}
        initialTitle={composerTitle}
        initialRepo={composerRepo}
        isLoadingDiff={isComposerLoadingDiff}
        diffError={composerDiffError}
        onRetryFetchDiff={() => {
          if (prDiffFetchRef.current) {
            prDiffFetchRef.current();
          }
        }}
      />

      <ReviewDetailModal
        review={selectedReview}
        isOpen={isDetailOpen}
        isLoadingDetails={isReviewDetailLoading}
        onClose={() => setIsDetailOpen(false)}
      />

      <AuthModal
        isOpen={isAuthOpen}
        onClose={() => setIsAuthOpen(false)}
        onSuccess={(newUser) => {
          setUser(newUser);
          loadUserData(newUser);
        }}
      />

      <ResourceModal
        resource={activeResource}
        onClose={() => setActiveResource(null)}
      />

      <GitHubPrPickerModal
        isOpen={isGitHubModalOpen}
        onClose={() => setIsGitHubModalOpen(false)}
        onAttachDiff={(diffText, title) => {
          navigateTo("chat", undefined);
          setActiveConversation(null);
          const attachmentName =
            title.replace(/[^a-z0-9_-]+/gi, "-").replace(/^-|-$/g, "").slice(0, 100) ||
            "pull-request";
          const diffAttachment: Attachment = {
            id: `inline-diff-${Date.now()}`,
            filename: `${attachmentName}.diff`,
            file_type: "diff",
            mime_type: "text/x-diff",
            file_size: new Blob([diffText]).size,
            content: diffText,
            status: "ready",
            created_at: new Date().toISOString(),
          };
          void handleSendMessage(
            `Analyze this pull request: ${title}`,
            diffText,
            undefined,
            undefined,
            [diffAttachment],
            true
          );
        }}
        onReviewCreated={(review) => {
          handleReviewCreated(review);
        }}
        onOpenSettings={() => navigateTo("settings")}
      />

      <AskNexarionSelectionHandler onAskNexarion={handleAskNexarion} />

      {agentToast && (
        <div
          role="alert"
          className="fixed bottom-6 right-6 z-50 flex items-center gap-3 px-4 py-3 rounded-xl bg-neutral-900/95 border border-red-500/40 text-red-200 text-xs sm:text-sm shadow-2xl backdrop-blur-md animate-in fade-in slide-in-from-bottom-2 duration-200"
        >
          <span className="w-2 h-2 rounded-full bg-red-400 shrink-0" />
          <span className="font-sans">{agentToast.message}</span>
          <button
            type="button"
            onClick={() => setAgentToast(null)}
            className="ml-2 text-neutral-400 hover:text-white transition-colors text-base leading-none p-1"
            aria-label="Dismiss error notification"
          >
            &times;
          </button>
        </div>
      )}
    </div>
  );
};
