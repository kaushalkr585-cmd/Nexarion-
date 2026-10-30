import type {
  AgentConfig,
  Attachment,
  Conversation,
  GitHubPullRequest,
  GitHubRepo,
  GitHubStatus,
  Message,
  OverviewMetrics,
  PullRequest,
  ProviderStatusResponse,
  ProviderTestResponse,
  Review,
  ReviewJobStatus,
  User,
} from "../types";

const TOKEN_KEY = "nexarion_auth_token";

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string): void {
  localStorage.setItem(TOKEN_KEY, token);
}

export function clearToken(): void {
  localStorage.removeItem(TOKEN_KEY);
}

export interface StreamError {
  error_code: string;
  user_message: string;
  retryable: boolean;
}

export function sanitizeErrorMessage(raw: string): string {
  if (!raw) return "Something went wrong while generating your response. Please try again.";
  const lower = raw.toLowerCase();

  if (lower.includes("timeout") || lower.includes("timed out")) {
    return "NEXARION couldn't get a response in time. Please try again.";
  }
  if (lower.includes("rate limit") || lower.includes("429") || lower.includes("too many requests")) {
    return "Too many requests right now. Please wait a moment and try again.";
  }
  if (
    lower.includes("context length") ||
    lower.includes("too large") ||
    lower.includes("maximum context") ||
    lower.includes("413")
  ) {
    return "This request is too large to process. Try shortening it or splitting it into smaller parts.";
  }
  if (
    lower.includes("authentication required") ||
    lower.includes("please sign in") ||
    lower.includes("sign in required") ||
    lower.includes("login required") ||
    lower.includes("session expired")
  ) {
    return "Authentication required. Please sign in or register to proceed.";
  }
  if (
    lower.includes("unauthorized") ||
    lower.includes("401") ||
    lower.includes("403") ||
    lower.includes("forbidden") ||
    lower.includes("api_key") ||
    lower.includes("invalid api key") ||
    lower.includes("couldn't be accessed")
  ) {
    return "The selected model couldn't be accessed. Check your AI configuration.";
  }
  if (
    lower.includes("connection refused") ||
    lower.includes("cannot connect") ||
    lower.includes("failed to connect") ||
    lower.includes("network") ||
    lower.includes("failed to fetch")
  ) {
    return "Couldn't connect to the AI service. Check your connection and retry.";
  }
  if (
    lower.includes("503") ||
    lower.includes("502") ||
    lower.includes("unavailable") ||
    lower.includes("service unavailable") ||
    lower.includes("bad gateway")
  ) {
    return "The AI service is temporarily unavailable. Please try again shortly.";
  }

  if (
    (lower.includes("attachment") || lower.includes("file")) &&
    (lower.includes("not found") || lower.includes("access is denied") || lower.includes("unauthorized"))
  ) {
    return "The attached file could not be found or accessed. Please re-attach the file and try again.";
  }

  if (
    lower.includes("unsupported file") ||
    lower.includes("unsupported attachment") ||
    lower.includes("supported formats include")
  ) {
    return "The attached file type is not supported. Please upload a .pdf, .txt, .diff, .patch, or code file.";
  }

  if (
    lower.includes("could not decode") ||
    lower.includes("binary data detected") ||
    lower.includes("contains no readable text") ||
    lower.includes("scanned or image-only")
  ) {
    return "Could not read the attached file. Ensure it is a valid text or diff file with supported encoding.";
  }

  if (
    lower.includes("model not found") ||
    lower.includes("model isn't configured") ||
    lower.includes("model is not configured") ||
    lower.includes("unknown model") ||
    lower.includes("unsupported ai model") ||
    lower.includes("model does not exist")
  ) {
    return "This model isn't configured correctly. Please check AI Settings.";
  }

  const clean = raw
    .replace(/ai model error with provider ['"][^'"]+['"]:\s*/gi, "")
    .replace(/request to nvidia nim timed out after [0-9\.]+s/gi, "NEXARION couldn't get a response in time. Please try again.")
    .replace(/nvidia\s*nim/gi, "AI Service")
    .replace(/nvidia/gi, "AI Service")
    .replace(/nemotron/gi, "AI Model")
    .replace(/ollama/gi, "Local AI Service");

  return clean.trim() || "Something went wrong while generating your response. Please try again.";
}

async function request<T>(endpoint: string, options: RequestInit = {}): Promise<T> {
  const token = getToken();
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(options.headers as Record<string, string>),
  };

  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }

  const response = await fetch(endpoint, {
    credentials: "include",
    ...options,
    headers,
  });

  if (!response.ok) {
    let errorDetail = `Request failed: ${response.status} ${response.statusText}`;
    try {
      const errJson = await response.json();
      if (errJson) {
        if (typeof errJson.detail === "object" && errJson.detail?.user_message) {
          errorDetail = errJson.detail.user_message;
        } else if (errJson.detail) {
          errorDetail =
            typeof errJson.detail === "string" ? errJson.detail : JSON.stringify(errJson.detail);
        }
      }
    } catch {

    }
    throw new Error(sanitizeErrorMessage(errorDetail));
  }

  if (response.status === 204) {
    return {} as T;
  }

  return response.json();
}

async function readSSEStream(
  response: Response,
  callbacks: {
    onInit?: (metadata: { id: string; title: string }) => void;
    onToken?: (token: string) => void;
    onDone?: (data: {
      conversation_id: string;
      message_id: string;
      content: string;
      created_at: string;
      metrics?: { ttft_ms?: number; total_ms?: number; chunks?: number };
    }) => void;
    onError?: (err: StreamError) => void;
  }
): Promise<void> {
  if (!response.body) {
    throw new Error("Response body is not readable.");
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder("utf-8");
  let buffer = "";

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      const lines = buffer.split("\n\n");
      buffer = lines.pop() || "";

      for (const block of lines) {
        if (!block.trim()) continue;
        let eventType = "message";
        let dataStr = "";

        for (const line of block.split("\n")) {
          if (line.startsWith("event: ")) {
            eventType = line.slice(7).trim();
          } else if (line.startsWith("data: ")) {
            dataStr = line.slice(6).trim();
          }
        }

        if (!dataStr) continue;

        try {
          const parsed = JSON.parse(dataStr);
          if (eventType === "init" && callbacks.onInit) {
            callbacks.onInit(parsed);
          } else if (eventType === "token" && callbacks.onToken) {
            callbacks.onToken(parsed.chunk);
          } else if (eventType === "done" && callbacks.onDone) {
            callbacks.onDone(parsed);
          } else if (eventType === "error") {
            const friendly: StreamError = {
              error_code: parsed.error_code || "ERROR",
              user_message: sanitizeErrorMessage(parsed.user_message || parsed.detail || ""),
              retryable: parsed.retryable !== false,
            };
            if (callbacks.onError) callbacks.onError(friendly);
            return;
          }
        } catch (e) {
          console.warn("Error parsing SSE data block:", e, dataStr);
        }
      }
    }
  } catch (err: unknown) {
    const errorObj = err as { name?: string };
    if (errorObj?.name === "AbortError") {
      return;
    }
    throw err;
  }
}

export const authApi = {
  async login(email: string, password: string): Promise<{ token: string; user: User }> {
    const res = await request<{ token: string; user: User }>("/api/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    });
    if (res.token) setToken(res.token);
    return res;
  },

  async signup(
    name: string,
    email: string,
    password: string
  ): Promise<{ token: string; user: User }> {
    const res = await request<{ token: string; user: User }>("/api/auth/signup", {
      method: "POST",
      body: JSON.stringify({ name, email, password }),
    });
    if (res.token) setToken(res.token);
    return res;
  },

  async getGoogleAuthUrl(origin?: string): Promise<{ url: string }> {
    const originParam = encodeURIComponent(origin || window.location.origin);
    return request<{ url: string }>(`/api/auth/google/url?origin=${originParam}`);
  },

  async getMe(): Promise<User> {
    return request<User>("/api/users/me");
  },

  async logout(): Promise<void> {
    try {
      await request<void>("/api/auth/logout", { method: "POST" });
    } catch {

    } finally {
      clearToken();
    }
  },
};

export const overviewApi = {
  async getMetrics(): Promise<OverviewMetrics> {
    return request<OverviewMetrics>("/api/overview/metrics");
  },
};

export const conversationApi = {
  async list(includeArchived: boolean = true): Promise<Conversation[]> {
    const query = includeArchived ? "?include_archived=true" : "";
    return request<Conversation[]>(`/api/conversations${query}`);
  },

  async create(
    title?: string,
    initial_message?: string,
    diff_context?: string,
    provider?: string,
    model?: string,
    attachment_ids?: string[]
  ): Promise<Conversation> {
    return request<Conversation>("/api/conversations", {
      method: "POST",
      body: JSON.stringify({
        title,
        initial_message,
        diff_context,
        provider,
        model,
        attachment_ids: attachment_ids || [],
      }),
    });
  },

  async get(id: string): Promise<Conversation> {
    return request<Conversation>(`/api/conversations/${id}`);
  },

  async sendMessage(
    conversationId: string,
    content: string,
    diffContext?: string,
    provider?: string,
    model?: string,
    attachmentIds?: string[]
  ): Promise<Conversation> {
    return request<Conversation>(`/api/conversations/${conversationId}/messages`, {
      method: "POST",
      body: JSON.stringify({
        content,
        diff_context: diffContext,
        provider,
        model,
        attachment_ids: attachmentIds || [],
      }),
    });
  },

  async regenerate(
    conversationId: string,
    messageId?: string,
    provider?: string,
    model?: string,
    diffContext?: string
  ): Promise<Conversation> {
    return request<Conversation>(`/api/conversations/${conversationId}/regenerate`, {
      method: "POST",
      body: JSON.stringify({ message_id: messageId, provider, model, diff_context: diffContext }),
    });
  },

  async streamMessage(
    conversationId: string | null,
    payload: {
      content: string;
      diffContext?: string;
      provider?: string;
      model?: string;
      attachmentIds?: string[];
    },
    callbacks: {
      onInit?: (metadata: { id: string; title: string }) => void;
      onToken?: (token: string) => void;
      onDone?: (data: {
        conversation_id: string;
        message_id: string;
        content: string;
        created_at: string;
        metrics?: { ttft_ms?: number; total_ms?: number; chunks?: number };
      }) => void;
      onError?: (err: StreamError) => void;
      signal?: AbortSignal;
    }
  ): Promise<void> {
    const token = getToken();
    const headers: Record<string, string> = {
      "Content-Type": "application/json",
    };
    if (token) {
      headers["Authorization"] = `Bearer ${token}`;
    }

    const endpoint = conversationId
      ? `/api/conversations/${conversationId}/messages/stream`
      : `/api/conversations/stream`;

    const body = conversationId
      ? JSON.stringify({
          content: payload.content,
          diff_context: payload.diffContext,
          provider: payload.provider,
          model: payload.model,
          attachment_ids: payload.attachmentIds || [],
        })
      : JSON.stringify({
          initial_message: payload.content,
          diff_context: payload.diffContext,
          provider: payload.provider,
          model: payload.model,
          attachment_ids: payload.attachmentIds || [],
        });

    const response = await fetch(endpoint, {
      method: "POST",
      headers,
      body,
      signal: callbacks.signal,
    });

    if (!response.ok) {
      let rawError = `Request failed: ${response.status}`;
      try {
        const errJson = await response.json();
        if (errJson) {
          rawError = errJson.detail?.user_message || errJson.detail || errJson.message || rawError;
        }
      } catch {

      }
      const safeError = sanitizeErrorMessage(typeof rawError === "string" ? rawError : JSON.stringify(rawError));
      if (callbacks.onError) {
        callbacks.onError({
          error_code: "HTTP_ERROR",
          user_message: safeError,
          retryable: response.status >= 500,
        });
      }
      return;
    }

    await readSSEStream(response, callbacks);
  },

  async streamRegenerate(
    conversationId: string,
    payload: {
      messageId?: string;
      provider?: string;
      model?: string;
      diffContext?: string;
    },
    callbacks: {
      onToken?: (token: string) => void;
      onDone?: (data: {
        conversation_id: string;
        message_id: string;
        content: string;
        created_at: string;
        metrics?: { ttft_ms?: number; total_ms?: number; chunks?: number };
      }) => void;
      onError?: (err: StreamError) => void;
      signal?: AbortSignal;
    }
  ): Promise<void> {
    const token = getToken();
    const headers: Record<string, string> = {
      "Content-Type": "application/json",
    };
    if (token) {
      headers["Authorization"] = `Bearer ${token}`;
    }

    const response = await fetch(`/api/conversations/${conversationId}/regenerate/stream`, {
      method: "POST",
      headers,
      body: JSON.stringify({
        message_id: payload.messageId,
        provider: payload.provider,
        model: payload.model,
        diff_context: payload.diffContext,
      }),
      signal: callbacks.signal,
    });

    if (!response.ok) {
      let rawError = `Regenerate failed: ${response.status}`;
      try {
        const errJson = await response.json();
        if (errJson) {
          rawError = errJson.detail?.user_message || errJson.detail || errJson.message || rawError;
        }
      } catch {

      }
      const safeError = sanitizeErrorMessage(typeof rawError === "string" ? rawError : JSON.stringify(rawError));
      if (callbacks.onError) {
        callbacks.onError({
          error_code: "HTTP_ERROR",
          user_message: safeError,
          retryable: response.status >= 500,
        });
      }
      return;
    }

    await readSSEStream(response, callbacks);
  },

  async editMessage(
    conversationId: string,
    messageId: string,
    payload: {
      content: string;
      diffContext?: string;
      provider?: string;
      model?: string;
      attachmentIds?: string[];
    }
  ): Promise<Conversation> {
    return request<Conversation>(
      `/api/conversations/${conversationId}/messages/${messageId}/edit`,
      {
        method: "POST",
        body: JSON.stringify({
          content: payload.content,
          diff_context: payload.diffContext,
          provider: payload.provider,
          model: payload.model,
          attachment_ids: payload.attachmentIds || [],
        }),
      }
    );
  },

  async streamEditMessage(
    conversationId: string,
    messageId: string,
    payload: {
      content: string;
      diffContext?: string;
      provider?: string;
      model?: string;
      attachmentIds?: string[];
    },
    callbacks: {
      onToken?: (token: string) => void;
      onDone?: (data: {
        conversation_id: string;
        message_id: string;
        content: string;
        created_at: string;
        metrics?: { ttft_ms?: number; total_ms?: number; chunks?: number };
      }) => void;
      onError?: (err: StreamError) => void;
      onSaved?: () => void;
      signal?: AbortSignal;
    }
  ): Promise<void> {
    const token = getToken();
    const headers: Record<string, string> = {
      "Content-Type": "application/json",
    };
    if (token) {
      headers["Authorization"] = `Bearer ${token}`;
    }

    const response = await fetch(
      `/api/conversations/${conversationId}/messages/${messageId}/edit/stream`,
      {
        method: "POST",
        headers,
        body: JSON.stringify({
          content: payload.content,
          diff_context: payload.diffContext,
          provider: payload.provider,
          model: payload.model,
          attachment_ids: payload.attachmentIds || [],
        }),
        signal: callbacks.signal,
      }
    );

    if (!response.ok) {
      let rawError = `Edit request failed: ${response.status}`;
      try {
        const errJson = await response.json();
        if (errJson) {
          rawError =
            errJson.detail?.user_message ||
            errJson.detail ||
            errJson.message ||
            rawError;
        }
      } catch {

      }
      const safeError = sanitizeErrorMessage(
        typeof rawError === "string" ? rawError : JSON.stringify(rawError)
      );
      if (callbacks.onError) {
        callbacks.onError({
          error_code: "HTTP_ERROR",
          user_message: safeError,
          retryable: response.status >= 500,
        });
      }
      throw new Error(safeError);
    }

    if (callbacks.onSaved) {
      callbacks.onSaved();
    }

    await readSSEStream(response, callbacks);
  },

  async setFeedback(
    conversationId: string,
    messageId: string,
    feedback: "helpful" | "unhelpful" | null
  ): Promise<Message> {
    return request<Message>(`/api/conversations/${conversationId}/messages/${messageId}/feedback`, {
      method: "POST",
      body: JSON.stringify({ feedback }),
    });
  },

  async update(
    id: string,
    payload: {
      title?: string;
      is_pinned?: boolean;
      is_archived?: boolean;
      section_name?: string | null;
    }
  ): Promise<Conversation> {
    return request<Conversation>(`/api/conversations/${id}`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    });
  },

  async delete(id: string): Promise<void> {
    await request<void>(`/api/conversations/${id}`, { method: "DELETE" });
  },

  async clearAll(): Promise<void> {
    await request<void>("/api/conversations", { method: "DELETE" });
  },
};

export function triggerBlobDownload(blobOrFile: Blob | File, filename: string): void {
  const url = window.URL.createObjectURL(blobOrFile);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  setTimeout(() => {
    window.URL.revokeObjectURL(url);
  }, 1000);
}

export const attachmentApi = {
  async upload(file: File, conversationId?: string): Promise<Attachment> {
    const token = getToken();
    const formData = new FormData();
    formData.append("file", file);
    if (conversationId) {
      formData.append("conversation_id", conversationId);
    }

    const headers: Record<string, string> = {};
    if (token) {
      headers["Authorization"] = `Bearer ${token}`;
    }

    const endpoint = conversationId
      ? `/api/conversations/${conversationId}/attachments/upload`
      : `/api/conversations/attachments/upload`;

    const response = await fetch(endpoint, {
      method: "POST",
      headers,
      body: formData,
      credentials: "include",
    });

    if (!response.ok) {
      let rawError = `Upload failed: ${response.statusText}`;
      try {
        const errJson = await response.json();
        if (errJson?.detail) {
          rawError = typeof errJson.detail === "string" ? errJson.detail : JSON.stringify(errJson.detail);
        }
      } catch {

      }
      throw new Error(rawError);
    }

    return response.json();
  },

  async delete(attachmentId: string): Promise<void> {
    await request<void>(`/api/conversations/attachments/${attachmentId}`, {
      method: "DELETE",
    });
  },

  async download(attachmentId: string, filename?: string): Promise<void> {
    const token = getToken();
    const headers: Record<string, string> = {};
    if (token) {
      headers["Authorization"] = `Bearer ${token}`;
    }

    const response = await fetch(
      `/api/conversations/attachments/${attachmentId}/download`,
      {
        headers,
        credentials: "include",
      }
    );

    if (!response.ok) {
      throw new Error(`Download failed: ${response.status}`);
    }

    const blob = await response.blob();
    const cd = response.headers.get("content-disposition");
    let resolvedFilename = filename;
    if (!resolvedFilename && cd) {
      const match = /filename\*?=['"]?(?:UTF-8'')?([^"';]+)['"]?/i.exec(cd);
      if (match && match[1]) {
        resolvedFilename = decodeURIComponent(match[1]);
      }
    }

    triggerBlobDownload(blob, resolvedFilename || "attachment");
  },

  async downloadAttachment(att: Attachment): Promise<void> {
    const filename = att.filename || "attachment";

    // 1. If it's a client-side synthetic ID (inline-diff-* or temp-att-*)
    const isSynthetic = !att.id || att.id.startsWith("inline-") || att.id.startsWith("temp-");

    if (isSynthetic) {
      if (att.file) {
        triggerBlobDownload(att.file, filename);
        return;
      }
      if (att.content !== undefined && att.content !== null) {
        const mime =
          att.mime_type ||
          (att.file_type === "diff"
            ? "text/x-diff;charset=utf-8"
            : "text/plain;charset=utf-8");
        const blob = new Blob([att.content], { type: mime });
        triggerBlobDownload(blob, filename);
        return;
      }
    }

    if (att.id && !att.id.startsWith("inline-") && !att.id.startsWith("temp-")) {
      try {
        await this.download(att.id, filename);
        return;
      } catch (err) {
        console.warn("Backend attachment download failed, attempting fallback:", err);
      }
    }

    if (att.file) {
      triggerBlobDownload(att.file, filename);
      return;
    }

    if (att.content !== undefined && att.content !== null) {
      const mime =
        att.mime_type ||
        (att.file_type === "diff"
          ? "text/x-diff;charset=utf-8"
          : "text/plain;charset=utf-8");
      const blob = new Blob([att.content], { type: mime });
      triggerBlobDownload(blob, filename);
      return;
    }

    if (att.id && !att.id.startsWith("inline-") && !att.id.startsWith("temp-")) {
      const res = await this.getContent(att.id);
      if (res && res.content !== undefined && res.content !== null) {
        const mime =
          res.mime_type ||
          (att.file_type === "diff"
            ? "text/x-diff;charset=utf-8"
            : "text/plain;charset=utf-8");
        const blob = new Blob([res.content], { type: mime });
        triggerBlobDownload(blob, filename);
        return;
      }
    }

    throw new Error("Unable to download attachment: file data is unavailable.");
  },

  async getContent(attachmentId: string): Promise<{
    id: string;
    filename: string;
    file_type: string;
    mime_type: string;
    file_size: number;
    content: string;
    page_count: number;
  }> {
    return request(`/api/conversations/attachments/${attachmentId}/content`);
  },
};

export const reviewApi = {
  async list(): Promise<Review[]> {
    return request<Review[]>("/api/reviews");
  },

  async get(id: string): Promise<Review> {
    return request<Review>(`/api/reviews/${id}`);
  },

  async createReview(payload: {
    diff_text: string;
    title?: string;
    repository_name?: string;
    pr_identifier?: string;
    provider?: string;
    include_llm?: boolean;
    agents?: string[];
  }): Promise<Review> {
    return request<Review>("/api/reviews", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },

  async update(
    id: string,
    payload: {
      title?: string;
      is_pinned?: boolean;
      is_archived?: boolean;
      section_name?: string | null;
    }
  ): Promise<Conversation> {
    return request<Conversation>(`/api/conversations/${id}`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    });
  },

  async delete(id: string): Promise<void> {
    await request<void>(`/api/reviews/${id}`, { method: "DELETE" });
  },

  async clearAll(): Promise<void> {
    await request<void>("/api/reviews", { method: "DELETE" });
  },
};

export const prApi = {
  async list(status?: string): Promise<PullRequest[]> {
    const url = status ? `/api/pull-requests?status=${status}` : "/api/pull-requests";
    return request<PullRequest[]>(url);
  },

  async get(id: string): Promise<PullRequest> {
    return request<PullRequest>(`/api/pull-requests/${id}`);
  },
};

export const agentApi = {
  async list(): Promise<AgentConfig[]> {
    return request<AgentConfig[]>("/api/agents");
  },

  async toggleAgent(agentId: string, isEnabled: boolean): Promise<AgentConfig> {
    return request<AgentConfig>(`/api/agents/${agentId}`, {
      method: "PUT",
      body: JSON.stringify({ is_enabled: isEnabled }),
    });
  },
};

export const providerApi = {
  async getStatus(): Promise<ProviderStatusResponse> {
    return request<ProviderStatusResponse>("/api/providers/status");
  },

  async testProvider(
    provider: string,
    model?: string,
    apiKey?: string
  ): Promise<ProviderTestResponse> {
    return request<ProviderTestResponse>("/api/providers/test", {
      method: "POST",
      body: JSON.stringify({ provider, model, api_key: apiKey }),
    });
  },
};

export const userApi = {
  async updateProfile(updates: Partial<User>): Promise<User> {
    return request<User>("/api/users/me", {
      method: "PUT",
      body: JSON.stringify(updates),
    });
  },

  async uploadAvatar(file: File): Promise<User> {
    const validTypes = ["image/png", "image/jpeg", "image/webp"];
    if (!validTypes.includes(file.type)) {
      throw new Error("Please select a valid PNG, JPEG, or WebP image.");
    }
    if (file.size > 5 * 1024 * 1024) {
      throw new Error("File size must not exceed 5MB.");
    }

    const token = getToken();
    const formData = new FormData();
    formData.append("file", file);

    const headers: Record<string, string> = {};
    if (token) headers["Authorization"] = `Bearer ${token}`;

    const res = await fetch("/api/users/me/avatar", {
      method: "POST",
      headers,
      body: formData,
    });

    if (!res.ok) {
      let msg = `Avatar upload failed (${res.status})`;
      try {
        const data = await res.json();
        if (data && data.detail) {
          msg = typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail);
        }
      } catch {

      }
      throw new Error(msg);
    }
    return res.json();
  },
};

export const githubApi = {
  async getStatus(): Promise<GitHubStatus> {
    return request<GitHubStatus>("/api/github/status");
  },

  async getAuthUrl(): Promise<{ url: string }> {
    return request<{ url: string }>("/api/github/auth-url");
  },

  async connect(token: string): Promise<GitHubStatus> {
    return request<GitHubStatus>("/api/github/connect", {
      method: "POST",
      body: JSON.stringify({ token }),
    });
  },

  async disconnect(): Promise<GitHubStatus> {
    return request<GitHubStatus>("/api/github/disconnect", {
      method: "POST",
    });
  },

  async listRepos(): Promise<GitHubRepo[]> {
    return request<GitHubRepo[]>("/api/github/repos");
  },

  async listPulls(owner: string, repo: string): Promise<GitHubPullRequest[]> {
    return request<GitHubPullRequest[]>(`/api/github/repos/${owner}/${repo}/pulls`);
  },

  async getDiff(
    owner: string,
    repo: string,
    number: number
  ): Promise<{ diff: string; title: string; number: number; additions: number; deletions: number }> {
    return request<{
      diff: string;
      title: string;
      number: number;
      additions: number;
      deletions: number;
    }>(`/api/github/repos/${owner}/${repo}/pulls/${number}/diff`);
  },

  async reviewPullRequest(
    owner: string,
    repo: string,
    number: number,
    postToGithub: boolean = false
  ): Promise<{ job_id: string; diff: string; title: string }> {
    const query = postToGithub ? "?post_to_github=true" : "";
    return request<{ job_id: string; diff: string; title: string }>(
      `/api/github/repos/${owner}/${repo}/pulls/${number}/review${query}`,
      { method: "POST" }
    );
  },

  async getReviewJob(jobId: string): Promise<ReviewJobStatus> {
    return request<ReviewJobStatus>(`/api/github/review-jobs/${jobId}`);
  },

  async postReview(
    owner: string,
    repo: string,
    number: number,
    payload: { review_id?: string; commit_sha?: string; event?: string } = {}
  ): Promise<{
    status: string;
    github_review_id?: number;
    review_url?: string;
    total_findings: number;
    inline_comments_posted: number;
    verdict: string;
  }> {
    return request(`/api/github/repos/${owner}/${repo}/pulls/${number}/post-review`, {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },
};
