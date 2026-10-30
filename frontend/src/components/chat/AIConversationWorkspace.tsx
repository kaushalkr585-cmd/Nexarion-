import React, { useEffect, useRef, useState } from "react";
import type {
  Attachment,
  Conversation,
  GenerationState,
  GenerationType,
  Message,
  ProviderStatusResponse,
  User,
  WaveState,
} from "../../types";
import { attachmentApi } from "../../services/api";
import {
  AgentIcon,
  BackIcon,
  ChatIcon,
  CloseIcon,
  CodeIcon,
  CopyIcon,
  DiffIcon,
  DownloadIcon,
  EditIcon,
  EyeIcon,
  FileCodeIcon,
  FilePdfIcon,
  FileTextIcon,
  HistoryIcon,
  PaperclipIcon,
  PlusIcon,
  PrIcon,
  SendIcon,
} from "../icons/Icons";
import { MarkdownContent } from "./MarkdownContent";
import { MessageActionToolbar } from "./MessageActionToolbar";
import type { SelectedModel } from "./ModelSelector";
import { getPersonalizedGreeting } from "./greetings";
import { AdaptiveStatusIndicator } from "./AdaptiveStatusIndicator";
import { FilePreviewModal } from "./FilePreviewModal";

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

interface AIConversationWorkspaceProps {
  conversation: Conversation | null;
  user?: User | null;
  generationState?: GenerationState;
  generationType?: GenerationType;
  onSendMessage: (
    content: string,
    diffContext?: string,
    provider?: string,
    model?: string,
    attachments?: Attachment[]
  ) => Promise<void>;
  onEditMessage?: (
    messageId: string,
    newContent: string,
    diffContext?: string,
    provider?: string,
    model?: string,
    attachmentIds?: string[],
    onSaved?: () => void
  ) => Promise<void>;
  onRegenerateMessage?: (
    messageId?: string,
    provider?: string,
    model?: string,
    diffContext?: string
  ) => Promise<void>;
  onFeedbackMessage?: (
    messageId: string,
    feedback: "helpful" | "unhelpful" | null
  ) => Promise<void>;
  onRetryMessage?: (failedMsgId: string) => Promise<void>;
  onStopGeneration?: () => void;
  onNewConversation: () => void;
  onDeleteConversation?: (id: string) => void;
  onStartReview: (sampleDiff?: string) => void;
  onNavigatePrs: () => void;
  onNavigateAgents: () => void;
  onNavigateHistory: () => void;
  onBack?: () => void;
  activeProvider: string;
  providerStatus: ProviderStatusResponse | null;
  isSending: boolean;
  setWaveState: (state: WaveState) => void;
  initialPrompt?: string | null;
  onPromptConsumed?: () => void;
}

export const AIConversationWorkspace: React.FC<AIConversationWorkspaceProps> = React.memo(({
  conversation,
  user,
  generationState = "idle",
  generationType = "chat",
  onSendMessage,
  onEditMessage,
  onRegenerateMessage,
  onFeedbackMessage,
  onRetryMessage,
  onStopGeneration,
  onNewConversation,
  onDeleteConversation,
  onStartReview,
  onNavigatePrs,
  onNavigateAgents,
  onNavigateHistory,
  onBack,
  isSending,
  setWaveState,
  initialPrompt,
  onPromptConsumed,
}) => {
  const [input, setInput] = useState("");
  const [diffContext, setDiffContext] = useState("");
  const [showDiffInput, setShowDiffInput] = useState(false);
  const [confirmDeleteActive, setConfirmDeleteActive] = useState(false);
  const [attachments, setAttachments] = useState<Attachment[]>([]);
  const [isDraggingOver, setIsDraggingOver] = useState(false);
  const [previewAttachment, setPreviewAttachment] = useState<Attachment | null>(null);
  const [editingMessageId, setEditingMessageId] = useState<string | null>(null);
  const [editingContent, setEditingContent] = useState("");
  const [isSavingEdit, setIsSavingEdit] = useState(false);
  const [editError, setEditError] = useState<string | null>(null);
  const [copiedMsgId, setCopiedMsgId] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  useEffect(() => {
    if (!conversation) {
      setInput("");
      setDiffContext("");
      setShowDiffInput(false);
      setAttachments([]);
      setEditingMessageId(null);
      setEditingContent("");
      setEditError(null);
      if (textareaRef.current) {
        textareaRef.current.style.height = "36px";
      }
    }
  }, [conversation?.id]);

  useEffect(() => {
    if (initialPrompt && initialPrompt.trim()) {
      setInput((prev) => {
        if (!prev.trim()) {
          return initialPrompt;
        }
        return `${initialPrompt}\n\n${prev}`;
      });

      if (onPromptConsumed) {
        onPromptConsumed();
      }

      setTimeout(() => {
        if (textareaRef.current) {
          textareaRef.current.focus();
          textareaRef.current.selectionStart = textareaRef.current.value.length;
          textareaRef.current.selectionEnd = textareaRef.current.value.length;
          adjustTextareaHeight();
        }
      }, 50);
    }
  }, [initialPrompt]);

  const handleFileSelect = async (files: FileList | null) => {
    if (!files || files.length === 0) return;
    const fileList = Array.from(files);

    for (const file of fileList) {
      const dotIdx = file.name.lastIndexOf(".");
      const ext = dotIdx !== -1 ? file.name.slice(dotIdx).toLowerCase() : "";
      const isPdf = ext === ".pdf";
      const isDiff = ext === ".diff" || ext === ".patch";
      const isCode = [".py", ".js", ".ts", ".tsx", ".jsx", ".json", ".yaml", ".yml"].includes(ext);
      const isTxt = [".txt", ".md", ".log"].includes(ext);
      const isAllowed = isPdf || isDiff || isCode || isTxt;
      const fileType = isPdf ? "pdf" : isDiff ? "diff" : isCode ? "code" : "txt";
      const tempId = `temp-att-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`;

      if (!isAllowed) {
        setAttachments((prev) => [
          ...prev,
          {
            id: tempId,
            filename: file.name,
            file_type: "txt",
            file_size: file.size,
            status: "error",
            error: "Unsupported file. Supported formats: .pdf, .txt, .diff, .patch, and code files.",
          },
        ]);
        continue;
      }

      if (file.size > 10 * 1024 * 1024) {
        setAttachments((prev) => [
          ...prev,
          {
            id: tempId,
            filename: file.name,
            file_type: fileType,
            file_size: file.size,
            status: "error",
            error: "File exceeds 10MB limit.",
          },
        ]);
        continue;
      }

      const pending: Attachment = {
        id: tempId,
        filename: file.name,
        file_type: fileType,
        file_size: file.size,
        status: "uploading",
        file,
      };
      setAttachments((prev) => [...prev, pending]);

      try {
        const uploaded = await attachmentApi.upload(file, conversation?.id);
        setAttachments((prev) =>
          prev.map((a) =>
            a.id === tempId
              ? {
                  ...uploaded,
                  status: "ready",
                  file,
                }
              : a
          )
        );
      } catch (err) {
        const msg = err instanceof Error ? err.message : "Failed to upload file.";
        setAttachments((prev) =>
          prev.map((a) =>
            a.id === tempId
              ? {
                  ...a,
                  status: "error",
                  error: msg,
                }
              : a
          )
        );
      }
    }
  };

  const handleRemoveAttachment = async (id: string) => {
    const target = attachments.find((a) => a.id === id);
    setAttachments((prev) => prev.filter((a) => a.id !== id));
    if (target && target.status === "ready" && !target.id.startsWith("temp-")) {
      try {
        await attachmentApi.delete(target.id);
      } catch {

      }
    }
  };

  const handleRetryAttachment = async (att: Attachment) => {
    if (!att.file) return;
    setAttachments((prev) =>
      prev.map((a) => (a.id === att.id ? { ...a, status: "uploading", error: undefined } : a))
    );
    try {
      const uploaded = await attachmentApi.upload(att.file, conversation?.id);
      setAttachments((prev) =>
        prev.map((a) =>
          a.id === att.id
            ? {
                ...uploaded,
                status: "ready",
                file: att.file,
              }
            : a
        )
      );
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Failed to upload file.";
      setAttachments((prev) =>
        prev.map((a) =>
          a.id === att.id
            ? {
                ...a,
                status: "error",
                error: msg,
              }
            : a
        )
      );
    }
  };

  const handleDownloadAttachment = async (att: Attachment) => {
    try {
      await attachmentApi.downloadAttachment(att);
    } catch (err) {
      console.error("Failed to download attachment:", err);
    }
  };

  const [greeting, setGreeting] = useState(() => getPersonalizedGreeting(user));

  const prevConvIdRef = useRef(conversation?.id);
  const prevUserIdRef = useRef(user?.id);
  const prevUserNameRef = useRef(user?.name);

  useEffect(() => {
    const convChanged = conversation?.id !== prevConvIdRef.current;
    const userChanged =
      user?.id !== prevUserIdRef.current || user?.name !== prevUserNameRef.current;

    if (convChanged || userChanged) {
      prevConvIdRef.current = conversation?.id;
      prevUserIdRef.current = user?.id;
      prevUserNameRef.current = user?.name;

      if (!conversation || !conversation.messages || conversation.messages.length === 0) {
        setGreeting(getPersonalizedGreeting(user));
      }
    }
  }, [conversation?.id, user?.id, user?.name]);

  const handleNewConversationClick = () => {
    setGreeting(getPersonalizedGreeting(user));
    onNewConversation();
  };

  const scrollContainerRef = useRef<HTMLDivElement | null>(null);
  const messagesEndRef = useRef<HTMLDivElement | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);
  const assistantStartRef = useRef<HTMLDivElement | null>(null);
  const latestAssistantRef = useRef<HTMLDivElement | null>(null);
  const isComposingRef = useRef(false);

  const [isUserNearBottom, setIsUserNearBottom] = useState(true);
  const [showJumpToLatest, setShowJumpToLatest] = useState(false);
  const wasJustSubmittedRef = useRef(false);
  const prevIsSendingRef = useRef(isSending);
  const prevMessageCountRef = useRef(conversation?.messages?.length || 0);

  const selectedModel: SelectedModel = {
    provider: "nvidia",
    model: "nvidia/nemotron-3-ultra-550b-a55b",
  };

  const messages: Message[] = conversation?.messages || [];
  console.log("[DEBUG WORKSPACE] render conversation.id:", conversation?.id, "messages length:", messages.length, "messages:", messages.map(m => ({ id: m.id, role: m.role, status: m.status, len: m.content?.length, content: m.content })));

  const adjustTextareaHeight = () => {
    const textarea = textareaRef.current;
    if (!textarea) return;
    textarea.style.height = "auto";
    const minHeight = 36;
    const maxHeight =
      typeof window !== "undefined"
        ? Math.min(240, Math.floor(window.innerHeight * 0.35))
        : 240;
    const scrollHeight = textarea.scrollHeight;
    const targetHeight = Math.min(Math.max(scrollHeight, minHeight), maxHeight);
    textarea.style.height = `${targetHeight}px`;
    textarea.style.overflowY = scrollHeight > maxHeight ? "auto" : "hidden";
  };

  useEffect(() => {
    adjustTextareaHeight();
  }, [input]);

  useEffect(() => {
    const handleResize = () => adjustTextareaHeight();
    window.addEventListener("resize", handleResize);
    return () => window.removeEventListener("resize", handleResize);
  }, []);

  const handleScroll = () => {
    const container = scrollContainerRef.current;
    if (!container) return;
    const distanceFromBottom =
      container.scrollHeight - container.scrollTop - container.clientHeight;
    const nearBottom = distanceFromBottom <= 60;
    setIsUserNearBottom(nearBottom);
    setShowJumpToLatest(distanceFromBottom > 60 && messages.length > 0);
  };

  const handleJumpToLatest = () => {
    setIsUserNearBottom(true);
    setShowJumpToLatest(false);
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  useEffect(() => {
    if (isSending && !prevIsSendingRef.current) {
      wasJustSubmittedRef.current = true;
      requestAnimationFrame(() => {
        if (assistantStartRef.current) {
          assistantStartRef.current.scrollIntoView({ behavior: "smooth", block: "start" });
        } else if (messagesEndRef.current) {
          messagesEndRef.current.scrollIntoView({ behavior: "smooth" });
        }
      });
    }
    prevIsSendingRef.current = isSending;
  }, [isSending]);

  useEffect(() => {
    const count = messages.length;
    const prevCount = prevMessageCountRef.current;
    prevMessageCountRef.current = count;

    if (count > prevCount && count > 0) {
      const latestMsg = messages[count - 1];

      if (latestMsg.role === "assistant" && wasJustSubmittedRef.current) {

        wasJustSubmittedRef.current = false;
        requestAnimationFrame(() => {
          if (latestAssistantRef.current) {
            latestAssistantRef.current.scrollIntoView({
              behavior: "smooth",
              block: "start",
            });
          }
        });
      } else if (latestMsg.role === "user") {

        requestAnimationFrame(() => {
          if (assistantStartRef.current) {
            assistantStartRef.current.scrollIntoView({ behavior: "smooth", block: "start" });
          } else if (messagesEndRef.current) {
            messagesEndRef.current.scrollIntoView({ behavior: "smooth" });
          }
        });
      } else if (isUserNearBottom) {

        requestAnimationFrame(() => {
          messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
        });
      }
    }
  }, [messages, isUserNearBottom]);

  useEffect(() => {
    const container = scrollContainerRef.current;
    if (!container) return;

    const observer = new ResizeObserver(() => {
      if (isUserNearBottom && !wasJustSubmittedRef.current) {
        requestAnimationFrame(() => {
          if (!scrollContainerRef.current) return;
          const dist =
            scrollContainerRef.current.scrollHeight -
            scrollContainerRef.current.scrollTop -
            scrollContainerRef.current.clientHeight;
          if (dist <= 100) {
            scrollContainerRef.current.scrollTop =
              scrollContainerRef.current.scrollHeight - scrollContainerRef.current.clientHeight;
          }
        });
      }
    });

    observer.observe(container);
    return () => observer.disconnect();
  }, [isUserNearBottom]);

  const saveEditedMessage = async (messageId: string) => {
    const trimmed = editingContent.trim();
    if (!trimmed || isSavingEdit || isSending) return;

    const currentMsg = messages.find((m) => m.id === messageId);
    if (currentMsg && currentMsg.content.trim() === trimmed) {
      setEditingMessageId(null);
      setEditError(null);
      return;
    }

    const draftContent = editingContent;

    setEditingMessageId(null);
    setEditError(null);
    setIsSavingEdit(true);

    try {
      if (onEditMessage) {
        await onEditMessage(messageId, draftContent);
      }
    } catch (err) {

      setEditingMessageId(messageId);
      setEditingContent(draftContent);
      setEditError(err instanceof Error ? err.message : "Failed to save message edit.");
    } finally {
      setIsSavingEdit(false);
    }
  };

  const handleSubmit = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    if (!input.trim() || isSending) return;

    const hasUploading = attachments.some((a) => a.status === "uploading");
    if (hasUploading) return;

    const readyAttachments = [...attachments.filter((a) => a.status === "ready")];
    const text = input.trim();
    const diff = diffContext.trim() || undefined;

    if (diff && !readyAttachments.some((a) => a.file_type === "diff")) {
      readyAttachments.push({
        id: `inline-diff-${Date.now()}`,
        filename: "changes.diff",
        file_type: "diff",
        file_size: new Blob([diff]).size,
        status: "ready",
        content: diff,
      });
    }

    wasJustSubmittedRef.current = true;

    setInput("");
    setDiffContext("");
    setShowDiffInput(false);
    setAttachments([]);
    if (textareaRef.current) {
      textareaRef.current.style.height = "36px";
      textareaRef.current.style.overflowY = "hidden";
    }

    if (setWaveState) {
      setWaveState("receiving");
    }

    try {
      await onSendMessage(
        text,
        diff,
        selectedModel.provider,
        selectedModel.model,
        readyAttachments.length > 0 ? readyAttachments : undefined
      );
    } catch {

    }
  };

  const handleRegenerate = async (messageId: string) => {
    if (isSending) return;
    wasJustSubmittedRef.current = true;
    try {
      if (onRegenerateMessage) {
        await onRegenerateMessage(
          messageId,
          selectedModel.provider,
          selectedModel.model,
          diffContext.trim() || undefined
        );
      }
    } catch {

    }
  };

  const handleFeedback = async (messageId: string, feedback: "helpful" | "unhelpful" | null) => {
    try {
      if (onFeedbackMessage) {
        await onFeedbackMessage(messageId, feedback);
      }
    } catch (err) {
      console.error("Failed to update message feedback:", err);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      if (isComposingRef.current) return;
      e.preventDefault();
      handleSubmit();
    }
  };

  const sampleDiffSnippet = `--- a/src/auth.py
+++ b/src/auth.py
@@ -14,6 +14,8 @@ def authenticate(user_id, token):
+    # Bypass authentication for automated testing
+    if token == "super_secret_override":
+        return True`;

  return (
    <div className="flex flex-col h-full w-full relative z-10 max-w-5xl mx-auto overflow-hidden">

      <header className="hidden md:flex flex-shrink-0 items-center justify-between px-6 py-4 border-b border-white/10 bg-black/60 backdrop-blur-md">
        <div className="flex items-center gap-3 min-w-0">
          {onBack && (
            <button
              type="button"
              onClick={onBack}
              className="p-1.5 rounded-lg text-neutral-400 hover:text-white hover:bg-white/10 transition-colors flex items-center gap-1.5 text-xs font-mono"
              title="Go back"
              aria-label="Go back"
            >
              <BackIcon className="w-4 h-4" />
              <span className="hidden sm:inline">Back</span>
            </button>
          )}
          <h1 className="text-sm font-medium text-white truncate max-w-md">
            {conversation?.title || "AI Code Review Workspace"}
          </h1>
        </div>

        <div className="flex items-center gap-2.5">

          <div className="flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-white/5 border border-white/10 text-[11px] font-mono text-neutral-400">
            <span className="w-1.5 h-1.5 rounded-full bg-neutral-300" />
            <span>Mode: Cloud Inference (Nemotron)</span>
          </div>

          <button
            onClick={handleNewConversationClick}
            className="flex items-center gap-1.5 px-2.5 py-1 text-xs font-medium text-neutral-300 hover:text-white bg-white/5 hover:bg-white/10 rounded-lg border border-white/10 transition-colors cursor-pointer"
            title="Start new thread"
          >
            <PlusIcon className="w-3.5 h-3.5" />
            <span className="hidden sm:inline">New Thread</span>
          </button>

          {conversation && onDeleteConversation && (
            confirmDeleteActive ? (
              <div className="flex items-center gap-1.5 p-1 bg-red-500/10 border border-red-500/30 rounded-lg text-xs">
                <span className="text-[11px] text-neutral-300 font-mono px-1">Delete thread?</span>
                <button
                  type="button"
                  onClick={() => {
                    setConfirmDeleteActive(false);
                    onDeleteConversation(conversation.id);
                  }}
                  className="px-2 py-0.5 bg-red-600 hover:bg-red-500 text-white rounded text-[11px] font-medium"
                >
                  Delete
                </button>
                <button
                  type="button"
                  onClick={() => setConfirmDeleteActive(false)}
                  className="px-1.5 py-0.5 text-neutral-400 hover:text-white rounded text-[11px]"
                >
                  Cancel
                </button>
              </div>
            ) : (
              <button
                onClick={() => setConfirmDeleteActive(true)}
                className="text-neutral-500 hover:text-red-400 p-1.5 rounded hover:bg-white/5 transition-colors"
                title="Delete conversation"
                aria-label="Delete conversation"
              >
                <CloseIcon className="w-3.5 h-3.5" />
              </button>
            )
          )}
        </div>
      </header>

      <div className="flex-1 relative min-h-0 overflow-hidden flex flex-col">
        <div
          ref={scrollContainerRef}
          onScroll={handleScroll}
          className="flex-1 overflow-y-auto overscroll-y-contain px-3 sm:px-6 md:px-8 py-4 sm:py-6 space-y-4 sm:space-y-6"
        >
          {messages.length === 0 && !isSending ? (
            <div className="h-full flex flex-col items-center justify-center text-center max-w-xl mx-auto py-12 px-4 animate-fade-in">
              <div className="w-12 h-12 shrink-0 rounded-2xl bg-white/5 border border-white/15 flex items-center justify-center mb-6 shadow-lg shadow-black/40">
                <ChatIcon className="w-6 h-6 text-white" />
              </div>

              <h2 className="text-2xl md:text-3xl font-semibold text-white tracking-tight mb-3 animate-greeting-heading">
                {greeting.heading}
              </h2>
              <p className="text-sm text-neutral-400 mb-8 max-w-md leading-relaxed animate-greeting-subtitle">
                {greeting.subtitle}
              </p>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 w-full animate-greeting-cards">
                <button
                  onClick={onNavigatePrs}
                  className="flex items-start gap-3 p-3.5 text-left rounded-xl bg-white/[0.04] hover:bg-white/[0.08] border border-white/10 hover:border-white/20 transition-all group"
                >
                  <div className="p-2 rounded-lg bg-white/5 text-neutral-300 group-hover:text-white transition-colors">
                    <PrIcon className="w-4 h-4" />
                  </div>
                  <div>
                    <div className="text-xs font-semibold text-white mb-0.5">Start a Pull Request Review</div>
                    <div className="text-[11px] text-neutral-500">Analyze full PR diff with active agents</div>
                  </div>
                </button>

                <button
                  onClick={() => onStartReview(sampleDiffSnippet)}
                  className="flex items-start gap-3 p-3.5 text-left rounded-xl bg-white/[0.04] hover:bg-white/[0.08] border border-white/10 hover:border-white/20 transition-all group"
                >
                  <div className="p-2 rounded-lg bg-white/5 text-neutral-300 group-hover:text-white transition-colors">
                    <CodeIcon className="w-4 h-4" />
                  </div>
                  <div>
                    <div className="text-xs font-semibold text-white mb-0.5">Analyze a Code Diff</div>
                    <div className="text-[11px] text-neutral-500">Inspect security bypass in sample patch</div>
                  </div>
                </button>

                <button
                  onClick={onNavigateAgents}
                  className="flex items-start gap-3 p-3.5 text-left rounded-xl bg-white/[0.04] hover:bg-white/[0.08] border border-white/10 hover:border-white/20 transition-all group"
                >
                  <div className="p-2 rounded-lg bg-white/5 text-neutral-300 group-hover:text-white transition-colors">
                    <AgentIcon className="w-4 h-4" />
                  </div>
                  <div>
                    <div className="text-xs font-semibold text-white mb-0.5">Explore Agents</div>
                    <div className="text-[11px] text-neutral-500">Security, Quality, Performance & AST</div>
                  </div>
                </button>

                <button
                  onClick={onNavigateHistory}
                  className="flex items-start gap-3 p-3.5 text-left rounded-xl bg-white/[0.04] hover:bg-white/[0.08] border border-white/10 hover:border-white/20 transition-all group"
                >
                  <div className="p-2 rounded-lg bg-white/5 text-neutral-300 group-hover:text-white transition-colors">
                    <HistoryIcon className="w-4 h-4" />
                  </div>
                  <div>
                    <div className="text-xs font-semibold text-white mb-0.5">View Review History</div>
                    <div className="text-[11px] text-neutral-500">Inspect past findings & execution metrics</div>
                  </div>
                </button>
              </div>
            </div>
          ) : (
            <div className="space-y-6">
              {messages.map((msg, idx) => {
                const isUser = msg.role === "user";
                if (isUser) {
                  const isEditingThis = editingMessageId === msg.id;

                  if (isEditingThis) {
                    return (
                      <div
                        key={msg.id}
                        className="flex flex-col items-end gap-1 animate-fade-in scroll-mt-6 w-full"
                      >
                        <div className="w-full max-w-[85%] sm:max-w-2xl p-4 rounded-2xl bg-neutral-900 border border-white/30 shadow-2xl text-left">
                          <div className="flex items-center justify-between mb-2">
                            <span className="text-xs font-mono font-medium text-neutral-300">
                              Edit Message
                            </span>
                            <span className="text-[10px] text-neutral-500 font-mono">
                              Subsequent messages will be updated
                            </span>
                          </div>
                          <textarea
                            value={editingContent}
                            onChange={(e) => setEditingContent(e.target.value)}
                            onKeyDown={(e) => {
                              if ((e.ctrlKey || e.metaKey) && e.key === "Enter") {
                                e.preventDefault();
                                saveEditedMessage(msg.id);
                              } else if (e.key === "Escape") {
                                setEditingMessageId(null);
                                setEditError(null);
                              }
                            }}
                            rows={3}
                            disabled={isSavingEdit || isSending}
                            className="w-full bg-black/70 text-white border border-white/20 rounded-xl p-3 text-xs sm:text-sm font-sans resize-y focus:outline-none focus:border-white/50 leading-relaxed block"
                            autoFocus
                          />
                          {editError && (
                            <div className="text-xs text-red-400 font-mono mt-1.5">{editError}</div>
                          )}
                          <div className="flex items-center justify-between mt-3 pt-2.5 border-t border-white/10 gap-2">
                            <span className="text-[10px] text-neutral-500 font-mono hidden sm:inline">
                              Ctrl + Enter to save, Esc to cancel
                            </span>
                            <div className="flex items-center gap-2 ml-auto">
                              <button
                                type="button"
                                disabled={isSavingEdit || isSending}
                                onClick={() => {
                                  setEditingMessageId(null);
                                  setEditError(null);
                                }}
                                className="px-3 py-1.5 rounded-lg text-xs font-mono text-neutral-300 hover:text-white hover:bg-white/10 transition-colors disabled:opacity-40"
                              >
                                Cancel
                              </button>
                              <button
                                type="button"
                                disabled={isSavingEdit || isSending || !editingContent.trim()}
                                onClick={() => saveEditedMessage(msg.id)}
                                className="px-3 py-1.5 rounded-lg text-xs font-mono bg-white text-black hover:bg-neutral-200 transition-colors font-medium disabled:opacity-40"
                              >
                                {isSavingEdit ? "Saving..." : "Save & Submit"}
                              </button>
                            </div>
                          </div>
                        </div>
                      </div>
                    );
                  }

                  const diffAttachments = (msg.attachments || []).filter(
                    (a) =>
                      a.file_type === "diff" ||
                      a.filename.endsWith(".diff") ||
                      a.filename.endsWith(".patch")
                  );
                  const otherAttachments = (msg.attachments || []).filter(
                    (a) =>
                      a.file_type !== "diff" &&
                      !a.filename.endsWith(".diff") &&
                      !a.filename.endsWith(".patch")
                  );

                  return (
                    <div
                      key={msg.id}
                      className="group flex flex-col items-end gap-1 animate-fade-in scroll-mt-6"
                    >
                      <div
                        className={`max-w-[88%] sm:max-w-2xl px-3.5 py-2.5 sm:px-4 sm:py-3 rounded-2xl text-xs sm:text-sm leading-relaxed ${
                          msg.status === "error"
                            ? "bg-red-950/20 text-white border border-red-500/40"
                            : "bg-white/10 text-white border border-white/20"
                        } rounded-tr-sm chat-message-content select-text shadow-sm`}
                      >

                        {diffAttachments.length > 0 && (
                          <div className="mb-2 space-y-1.5">
                            {diffAttachments.map((att) => (
                              <div
                                key={att.id}
                                className="w-full p-2.5 sm:p-3 rounded-xl bg-black/60 border border-amber-500/30 flex flex-col sm:flex-row sm:items-center justify-between gap-2.5 text-left shadow-sm"
                              >
                                <div className="flex items-center gap-2.5 min-w-0">
                                  <div className="p-2 rounded-lg bg-amber-500/10 text-amber-400 flex-shrink-0">
                                    <DiffIcon className="w-4 h-4" />
                                  </div>
                                  <div className="min-w-0">
                                    <div className="text-xs font-mono font-semibold text-white truncate max-w-[180px] sm:max-w-xs">
                                      {att.filename}
                                    </div>
                                    <div className="text-[10px] text-neutral-400 font-mono">
                                      Unified diff • {formatBytes(att.file_size)}
                                    </div>
                                  </div>
                                </div>
                                <div className="flex items-center gap-1.5 flex-shrink-0 self-end sm:self-auto">
                                  <button
                                    type="button"
                                    onClick={() => setPreviewAttachment(att)}
                                    className="flex items-center gap-1 px-2.5 py-1 rounded-lg bg-white/10 hover:bg-white/20 text-white text-xs font-mono transition-colors cursor-pointer"
                                    title="Open diff preview"
                                  >
                                    <EyeIcon className="w-3.5 h-3.5 text-neutral-300" />
                                    <span>View diff</span>
                                  </button>
                                  <button
                                    type="button"
                                    onClick={() => handleDownloadAttachment(att)}
                                    className="flex items-center gap-1 px-2.5 py-1 rounded-lg bg-white/5 hover:bg-white/10 text-neutral-300 hover:text-white text-xs font-mono transition-colors cursor-pointer"
                                    title="Download diff file"
                                  >
                                    <DownloadIcon className="w-3.5 h-3.5" />
                                    <span>Download</span>
                                  </button>
                                </div>
                              </div>
                            ))}
                          </div>
                        )}

                        {otherAttachments.length > 0 && (
                          <div className="mb-2 flex flex-wrap gap-1.5">
                            {otherAttachments.map((att) => (
                              <div
                                key={att.id}
                                onClick={() => setPreviewAttachment(att)}
                                className="flex items-center gap-2 px-2.5 py-1.5 rounded-lg bg-black/40 hover:bg-black/60 border border-white/15 hover:border-white/30 text-xs text-neutral-200 select-none shadow-sm cursor-pointer transition-colors"
                                title={`Click to preview ${att.filename}`}
                              >
                                {att.file_type === "pdf" ? (
                                  <FilePdfIcon className="w-3.5 h-3.5 text-red-400 flex-shrink-0" />
                                ) : att.file_type === "code" ? (
                                  <FileCodeIcon className="w-3.5 h-3.5 text-emerald-400 flex-shrink-0" />
                                ) : (
                                  <FileTextIcon className="w-3.5 h-3.5 text-blue-400 flex-shrink-0" />
                                )}
                                <span className="font-mono truncate max-w-[140px] sm:max-w-[200px]">
                                  {att.filename}
                                </span>
                                <span className="text-[10px] text-neutral-400 font-mono">
                                  {formatBytes(att.file_size)}
                                </span>
                                <button
                                  type="button"
                                  onClick={(e) => {
                                    e.stopPropagation();
                                    handleDownloadAttachment(att);
                                  }}
                                  className="p-1 rounded text-neutral-400 hover:text-white hover:bg-white/10 transition-colors ml-0.5 cursor-pointer"
                                  title="Download file"
                                >
                                  <DownloadIcon className="w-3 h-3" />
                                </button>
                              </div>
                            ))}
                          </div>
                        )}

                        <div className="whitespace-pre-wrap font-sans select-text">{msg.content}</div>
                        <div className="mt-1.5 flex items-center justify-end gap-2 text-[10px] text-neutral-400 font-mono select-none">
                          {msg.status === "sending" && (
                            <span className="flex items-center gap-1 text-neutral-400">
                              <span className="w-1.5 h-1.5 rounded-full bg-white/60 animate-pulse" />
                              sending
                            </span>
                          )}
                          <span>
                            {new Date(msg.created_at).toLocaleTimeString([], {
                              hour: "2-digit",
                              minute: "2-digit",
                            })}
                          </span>
                        </div>
                      </div>

                      <div className="flex items-center gap-2 pr-1 opacity-90 sm:opacity-0 group-hover:opacity-100 transition-opacity">
                        {onEditMessage && (
                          <button
                            type="button"
                            disabled={isSending}
                            onClick={() => {
                              if (isSending) return;
                              setEditingMessageId(msg.id);
                              setEditingContent(msg.content);
                              setEditError(null);
                            }}
                            className="flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-mono text-neutral-400 hover:text-white hover:bg-white/10 transition-colors cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed"
                            title={isSending ? "Cannot edit while response is generating" : "Edit this prompt"}
                            aria-label="Edit message"
                          >
                            <EditIcon className="w-3 h-3" />
                            <span>Edit</span>
                          </button>
                        )}
                        <button
                          type="button"
                          onClick={async () => {
                            try {
                              await navigator.clipboard.writeText(msg.content);
                              setCopiedMsgId(msg.id);
                              setTimeout(() => setCopiedMsgId(null), 2000);
                            } catch {

                            }
                          }}
                          className="flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-mono text-neutral-400 hover:text-white hover:bg-white/10 transition-colors cursor-pointer"
                          title="Copy prompt"
                        >
                          <CopyIcon className="w-3 h-3" />
                          <span>{copiedMsgId === msg.id ? "Copied" : "Copy"}</span>
                        </button>
                      </div>

                      {msg.status === "error" && (
                        <div className="flex items-center gap-2 text-xs font-mono text-red-400 mt-0.5">
                          <span className="text-[11px]">{msg.error || "Failed to deliver message."}</span>
                          {onRetryMessage && (
                            <button
                              type="button"
                              onClick={() => onRetryMessage(msg.id)}
                              className="px-2 py-0.5 rounded bg-white/10 hover:bg-white/20 text-white text-[11px] font-medium border border-white/20 transition-colors"
                            >
                              Retry
                            </button>
                          )}
                        </div>
                      )}
                    </div>
                  );
                }

                const isLatestAssistant = idx === messages.length - 1;
                const isStreamingThis = msg.status === "streaming";

                return (
                  <AssistantMessageItem
                    key={msg.id}
                    ref={isStreamingThis ? assistantStartRef : (isLatestAssistant ? latestAssistantRef : null)}
                    message={msg}
                    isGenerating={isSending}
                    generationState={generationState}
                    generationType={diffContext ? "diff" : generationType}
                    onRegenerate={() => handleRegenerate(msg.id)}
                    onFeedback={(fb) => handleFeedback(msg.id, fb)}
                    onRetry={() => onRetryMessage && onRetryMessage(msg.id)}
                  />
                );
              })}

              {isSending && !messages.some((m) => m.status === "streaming") && (
                <div
                  ref={assistantStartRef}
                  className="flex gap-3.5 justify-start animate-fade-in scroll-mt-6"
                >
                  <AdaptiveStatusIndicator
                    state={generationState}
                    type={diffContext ? "diff" : generationType}
                    showAvatar={true}
                  />
                </div>
              )}

              <div ref={messagesEndRef} />
            </div>
          )}
        </div>

        {showJumpToLatest && (
          <button
            id="jump-to-latest-btn"
            type="button"
            onClick={handleJumpToLatest}
            className="absolute bottom-3 right-4 sm:bottom-4 sm:right-6 z-30 flex items-center gap-1.5 px-3 py-1.5 sm:px-3.5 sm:py-1.5 min-h-[38px] rounded-full bg-neutral-900/95 hover:bg-neutral-800 text-white border border-white/20 shadow-2xl text-xs font-mono backdrop-blur-md transition-all animate-fade-in group cursor-pointer"
            aria-label="Jump to latest message"
          >
            <span>Jump to latest</span>
            <svg
              className="w-3.5 h-3.5 text-neutral-400 group-hover:text-white transition-colors"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
            >
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 14l-7 7m0 0l-7-7m7 7V3" />
            </svg>
          </button>
        )}
      </div>

      <div className="flex-shrink-0 p-2.5 sm:p-4 md:px-8 pb-[max(0.625rem,env(safe-area-inset-bottom))] border-t border-white/10 bg-black/85 backdrop-blur-lg">

        {showDiffInput && (
          <div className="mb-2.5 p-2.5 sm:p-3 rounded-xl bg-neutral-900/80 border border-white/15 animate-fade-in">
            <div className="flex items-center justify-between mb-1.5">
              <span className="text-[11px] font-mono text-neutral-400">Attached Diff Context (Unified Diff)</span>
              <button
                onClick={() => setShowDiffInput(false)}
                className="text-neutral-500 hover:text-white text-xs p-1"
                aria-label="Close diff input"
              >
                ✕ Close
              </button>
            </div>
            <textarea
              value={diffContext}
              onChange={(e) => setDiffContext(e.target.value)}
              placeholder="Paste unified git diff here (e.g. diff --git a/... b/...)"
              rows={4}
              className="w-full bg-black/60 text-neutral-200 border border-white/10 rounded-lg p-2 text-xs font-mono resize-none focus:outline-none focus:border-white/30"
            />
          </div>
        )}

        <form
          onSubmit={handleSubmit}
          onDragOver={(e) => {
            e.preventDefault();
            setIsDraggingOver(true);
          }}
          onDragLeave={() => setIsDraggingOver(false)}
          onDrop={(e) => {
            e.preventDefault();
            setIsDraggingOver(false);
            if (e.dataTransfer.files) {
              handleFileSelect(e.dataTransfer.files);
            }
          }}
          className={`relative flex flex-col bg-neutral-900/90 border rounded-2xl p-2.5 sm:p-3 shadow-2xl transition-all ${
            isDraggingOver
              ? "border-white/60 bg-white/[0.08] ring-2 ring-white/20"
              : "border-white/15 focus-within:border-white/35"
          }`}
        >

          {attachments.length > 0 && (
            <div className="mb-2.5 flex flex-wrap gap-2 animate-fade-in">
              {attachments.map((att) => (
                <div
                  key={att.id}
                  className={`flex items-center gap-2 px-2.5 py-1.5 rounded-xl border text-xs font-mono transition-all ${
                    att.status === "error"
                      ? "bg-red-950/40 border-red-500/40 text-red-200"
                      : att.status === "uploading"
                      ? "bg-white/[0.06] border-white/20 text-neutral-300"
                      : "bg-white/10 border-white/25 text-white shadow-sm"
                  }`}
                >
                  {att.file_type === "diff" ||
                  att.filename.endsWith(".diff") ||
                  att.filename.endsWith(".patch") ? (
                    <DiffIcon className="w-4 h-4 text-amber-400 flex-shrink-0" />
                  ) : att.file_type === "pdf" ? (
                    <FilePdfIcon className="w-4 h-4 text-red-400 flex-shrink-0" />
                  ) : att.file_type === "code" ? (
                    <FileCodeIcon className="w-4 h-4 text-emerald-400 flex-shrink-0" />
                  ) : (
                    <FileTextIcon className="w-4 h-4 text-blue-400 flex-shrink-0" />
                  )}
                  <div className="flex flex-col min-w-0">
                    <span className="truncate max-w-[140px] sm:max-w-[200px] font-medium leading-tight">
                      {att.filename}
                    </span>
                    <span className="text-[10px] text-neutral-400 leading-tight">
                      {att.status === "uploading"
                        ? "Processing..."
                        : att.status === "error"
                        ? att.error || "Error"
                        : `${formatBytes(att.file_size)}${att.page_count ? ` • ${att.page_count} pgs` : ""}`}
                    </span>
                  </div>

                  {att.status === "uploading" && (
                    <div className="w-3.5 h-3.5 border-2 border-white/20 border-t-white rounded-full animate-spin flex-shrink-0 ml-1" />
                  )}

                  {att.status === "error" && att.file && (
                    <button
                      type="button"
                      onClick={() => handleRetryAttachment(att)}
                      className="text-[10px] px-1.5 py-0.5 rounded bg-red-500/20 hover:bg-red-500/40 text-red-300 transition-colors"
                    >
                      Retry
                    </button>
                  )}

                  <button
                    type="button"
                    onClick={() => handleRemoveAttachment(att.id)}
                    className="p-0.5 text-neutral-400 hover:text-white rounded transition-colors ml-0.5"
                    aria-label={`Remove ${att.filename}`}
                  >
                    <CloseIcon className="w-3 h-3" />
                  </button>
                </div>
              ))}
            </div>
          )}

          <div className="w-full relative">
            <textarea
              ref={textareaRef}
              value={input}
              onChange={(e) => {
                setInput(e.target.value);
                adjustTextareaHeight();
              }}
              onKeyDown={handleKeyDown}
              onCompositionStart={() => {
                isComposingRef.current = true;
              }}
              onCompositionEnd={() => {
                isComposingRef.current = false;
              }}
              placeholder={
                attachments.length > 0
                  ? `Ask NEXARION about ${attachments.map((a) => a.filename).join(", ")}...`
                  : "Ask NEXARION about your code..."
              }
              rows={1}
              disabled={isSending}
              className="w-full bg-transparent text-white placeholder-neutral-500 text-xs sm:text-sm px-1 py-1 resize-none focus:outline-none transition-[height] duration-75 overflow-x-hidden leading-relaxed block"
              style={{ minHeight: "36px", maxHeight: "200px", overflowY: "hidden" }}
            />
          </div>

          <div className="flex items-center justify-between pt-2 mt-1 border-t border-white/5 gap-2">
            <div className="flex items-center gap-1.5 sm:gap-2 min-w-0 flex-wrap sm:flex-nowrap">
              <button
                type="button"
                onClick={() => fileInputRef.current?.click()}
                disabled={isSending}
                className={`min-w-[38px] min-h-[38px] p-2 sm:px-2.5 sm:py-1.5 rounded-xl text-xs font-mono transition-colors flex items-center justify-center gap-1.5 cursor-pointer ${
                  attachments.length > 0
                    ? "bg-white/15 text-white border border-white/20"
                    : "text-neutral-400 hover:text-white hover:bg-white/5 border border-transparent"
                }`}
                title="Attach file (.pdf, .txt, .diff, .patch, code files)"
                aria-label="Attach file"
              >
                <PaperclipIcon className="w-4 h-4 sm:w-3.5 sm:h-3.5 flex-shrink-0" />
                <span className="hidden sm:inline text-[11px] font-mono">
                  {attachments.length > 0 ? `${attachments.length} Attached` : "Attach File"}
                </span>
              </button>
              <input
                ref={fileInputRef}
                type="file"
                accept=".pdf,.txt,.diff,.patch,.py,.js,.ts,.tsx,.json,.yaml,.yml,.md,text/*,application/pdf"
                multiple
                className="hidden"
                onChange={(e) => {
                  if (e.target.files) {
                    handleFileSelect(e.target.files);
                    e.target.value = "";
                  }
                }}
              />

              <button
                type="button"
                onClick={() => setShowDiffInput(!showDiffInput)}
                className={`min-w-[38px] min-h-[38px] p-2 sm:px-2.5 sm:py-1.5 rounded-xl text-xs font-mono transition-colors flex items-center justify-center gap-1.5 cursor-pointer ${
                  showDiffInput || diffContext
                    ? "bg-white/15 text-white border border-white/20"
                    : "text-neutral-400 hover:text-white hover:bg-white/5 border border-transparent"
                }`}
                title="Attach code diff to this query"
                aria-label="Attach code diff"
              >
                <CodeIcon className="w-4 h-4 sm:w-3.5 sm:h-3.5 flex-shrink-0" />
                <span className="hidden sm:inline text-[11px] font-mono">
                  {diffContext ? "Diff Attached" : "Attach Diff"}
                </span>
              </button>
            </div>

            <div className="flex items-center gap-2 flex-shrink-0">
              {isSending ? (
                <button
                  type="button"
                  onClick={onStopGeneration}
                  className="min-w-[42px] min-h-[42px] p-2 sm:px-3 sm:py-2 rounded-xl bg-neutral-800 hover:bg-neutral-700 text-white border border-white/20 transition-all flex items-center justify-center gap-1.5 font-mono text-xs cursor-pointer shadow-sm"
                  title="Stop generating"
                  aria-label="Stop generation"
                >
                  <span className="w-2.5 h-2.5 bg-white rounded-xs inline-block" />
                  <span className="hidden sm:inline">Stop</span>
                </button>
              ) : (
                <button
                  type="submit"
                  disabled={!input.trim() || attachments.some((a) => a.status === "uploading")}
                  className="min-w-[42px] min-h-[42px] p-2 sm:px-3 sm:py-2 rounded-xl bg-white text-black hover:bg-neutral-200 active:bg-neutral-300 disabled:opacity-30 disabled:hover:bg-white transition-all flex items-center justify-center font-medium shadow-sm cursor-pointer"
                  aria-label="Send message"
                >
                  <SendIcon className="w-4 h-4" />
                </button>
              )}
            </div>
          </div>
        </form>

        <div className="hidden sm:flex items-center justify-between mt-2 px-2 text-[10px] text-neutral-500 font-mono">
          <span>Press Enter to send, Shift + Enter for newline</span>
          <span>NEXARION Multi-Agent Intelligence</span>
        </div>
      </div>

      <FilePreviewModal
        attachment={previewAttachment}
        isOpen={Boolean(previewAttachment)}
        onClose={() => setPreviewAttachment(null)}
        onDownload={handleDownloadAttachment}
      />
    </div>
  );
});
AIConversationWorkspace.displayName = "AIConversationWorkspace";

const AssistantMessageItem = React.forwardRef<
  HTMLDivElement,
  {
    message: Message;
    isGenerating?: boolean;
    generationState?: GenerationState;
    generationType?: GenerationType;
    onRegenerate: () => void;
    onFeedback: (feedback: "helpful" | "unhelpful" | null) => void;
    onRetry?: () => void;
  }
>(
  (
    {
      message,
      isGenerating,
      generationState = "thinking",
      generationType = "chat",
      onRegenerate,
      onFeedback,
      onRetry,
    },
    ref
  ) => {
    const contentRef = useRef<HTMLDivElement | null>(null);

    const isStreaming = message.status === "streaming";
    const isError = message.status === "error";
    const hasContent = Boolean(message.content && message.content.trim().length > 0);

    return (
      <div ref={ref} className="group flex gap-3.5 justify-start animate-fade-in w-full scroll-mt-6">
        <div className="w-7 h-7 rounded-lg bg-white/10 border border-white/20 flex items-center justify-center flex-shrink-0 mt-0.5 select-none">
          <span className="text-[10px] font-bold text-white font-mono">NX</span>
        </div>

        <div className="flex flex-col min-w-0 max-w-[92%] sm:max-w-2xl w-full">

          {isStreaming && !hasContent ? (
            <AdaptiveStatusIndicator
              state={generationState}
              type={generationType}
              showAvatar={false}
            />
          ) : (
            <div
              ref={contentRef}
              className={`chat-message-content select-text px-3.5 py-2.5 sm:px-4 sm:py-3 rounded-2xl text-xs sm:text-sm leading-relaxed backdrop-blur-md shadow-sm rounded-tl-sm ${
                isError
                  ? "bg-red-950/20 text-neutral-200 border border-red-500/30"
                  : "bg-black/60 text-neutral-200 border border-white/10"
              }`}
            >
              {hasContent && (
                <div>
                  <MarkdownContent content={message.content} />
                  {isStreaming && (
                    <span className="inline-block w-1.5 h-3.5 bg-white/80 ml-0.5 align-middle animate-pulse" />
                  )}
                </div>
              )}

              {isError && (
                <div
                  className={`${
                    hasContent ? "mt-3 pt-3 border-t border-white/10" : ""
                  } flex items-center justify-between gap-3 text-xs`}
                >
                  <div className="flex items-center gap-2 min-w-0">
                    <span className="w-2 h-2 rounded-full bg-red-400 flex-shrink-0" />
                    <span className="text-red-200 font-sans leading-relaxed">
                      {message.error ||
                        "Something went wrong while generating your response. Please try again."}
                    </span>
                  </div>
                  {onRetry && (
                    <button
                      type="button"
                      disabled={isGenerating}
                      onClick={onRetry}
                      className="px-2.5 py-1 rounded-lg bg-white/10 hover:bg-white/20 text-white text-[11px] font-mono border border-white/20 transition-colors flex-shrink-0 cursor-pointer disabled:opacity-50"
                    >
                      Retry
                    </button>
                  )}
                </div>
              )}

              <div className="mt-2 flex items-center justify-between text-[10px] text-neutral-500 font-mono select-none">
                {isStreaming ? (
                  <span className="flex items-center gap-1.5 text-neutral-400">
                    <span className="w-1.5 h-1.5 rounded-full bg-white/70 animate-pulse" />
                    <span>
                      {generationType === "diff"
                        ? "Drafting review..."
                        : generationType === "review"
                        ? "Aggregating findings..."
                        : "Writing response..."}
                    </span>
                  </span>
                ) : (
                  <span />
                )}
                <span>
                  {new Date(message.created_at).toLocaleTimeString([], {
                    hour: "2-digit",
                    minute: "2-digit",
                  })}
                </span>
              </div>
            </div>
          )}

        {!isStreaming && !isError && (
          <div className="opacity-95 sm:opacity-0 group-hover:opacity-100 group-focus-within:opacity-100 focus-within:opacity-100 transition-opacity duration-150 pl-0.5 min-h-[30px] flex items-center">
            <MessageActionToolbar
              content={message.content}
              feedback={message.feedback}
              isGenerating={isGenerating}
              onRegenerate={onRegenerate}
              onFeedback={onFeedback}
              contentRef={contentRef}
            />
          </div>
        )}
      </div>
    </div>
  );
});
AssistantMessageItem.displayName = "AssistantMessageItem";
