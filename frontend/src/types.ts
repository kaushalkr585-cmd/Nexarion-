export type WaveState = "idle" | "receiving" | "thinking" | "reviewing" | "responding" | "error";

export type GenerationState =
  | "idle"
  | "submitting"
  | "connecting"
  | "thinking"
  | "streaming"
  | "reviewing"
  | "finalizing"
  | "completed"
  | "error"
  | "cancelled";

export type GenerationType = "chat" | "diff" | "review";

export type NavView = "chat" | "overview" | "prs" | "agents" | "history" | "settings" | "feedback";

export interface User {
  id: string;
  name: string;
  email: string;
  avatar_url?: string | null;
  plan?: string;
  theme: string;
  role?: "user" | "admin" | string;
  github_connected: boolean;
  github_username?: string | null;
  auth_provider?: string;
  google_email?: string | null;
  google_linked?: boolean;
  has_password?: boolean;
  email_verified?: boolean;
  pending_email?: string | null;
  created_at: string;
}

export interface Attachment {
  id: string;
  filename: string;
  file_type: "pdf" | "txt" | "diff" | "code" | string;
  mime_type?: string;
  file_size: number;
  page_count?: number;
  chunk_count?: number;
  status?: "uploading" | "ready" | "error";
  error?: string;
  file?: File;
  content?: string;
  created_at?: string;
}

export interface FeedbackItem {
  id: string;
  user_id: string;
  user?: {
    id: string;
    name: string;
    email: string;
    avatar_url?: string | null;
    role: string;
  } | null;
  conversation_id?: string | null;
  message_id?: string | null;
  conversation_ref?: string | null;
  message_ref?: string | null;
  conversation_title?: string | null;
  category: string;
  details?: string | null;
  reported_response: string;
  status: "new" | "reviewing" | "resolved" | string;
  email_notification_status: "pending" | "sent" | "failed" | string;
  email_error?: string | null;
  email_message_id?: string | null;
  email_sent_at?: string | null;
  created_at: string;
  updated_at: string;
}

export interface FeedbackListResponse {
  items: FeedbackItem[];
  total: number;
  page: number;
  limit: number;
  pages: number;
}

export interface FeedbackStats {
  total: number;
  new_count: number;
  reviewing_count: number;
  resolved_count: number;
  failed_emails: number;
}


export interface Message {
  id: string;
  conversation_id: string;
  role: "user" | "assistant" | "system";
  content: string;
  feedback?: "helpful" | "unhelpful" | null;
  status?: "sending" | "streaming" | "sent" | "error";
  error?: string;
  attachments?: Attachment[];
  repoCandidates?: GitHubRepo[];
  repoMeta?: {
    repository: string;
    branch: string;
    commit_sha?: string | null;
  };
  created_at: string;
}

export interface Conversation {
  id: string;
  title: string;
  is_pinned?: boolean;
  is_archived?: boolean;
  is_shared?: boolean;
  section_name?: string | null;
  created_at: string;
  updated_at: string;
  message_count?: number;
  messages?: Message[];
  attachments?: Attachment[];
}

export interface ConversationSearchResult {
  id: string;
  title: string;
  match_type: "title" | "message" | "both";
  snippet: string;
  role?: "user" | "assistant" | null;
  created_at: string;
  updated_at: string;
  message_count: number;
}

export interface Finding {
  id: string;
  agent: string;
  title: string;
  description: string;
  severity: "CRITICAL" | "ERROR" | "WARNING" | "INFO";
  category: "SECURITY" | "QUALITY" | "PERFORMANCE" | "DOCUMENTATION" | "STYLE";
  file_path: string;
  line_start: number;
  line_end?: number | null;
  suggested_fix?: string | null;
  rule_id?: string | null;
  evidence?: string | null;
}

export interface Review {
  id: string;
  repository_name: string;
  pr_identifier: string;
  title: string;
  provider: string;
  model_name: string;
  agents_used: string[];
  finding_count: number;
  has_critical: boolean;
  duration_seconds: number;
  created_at: string;
  diff_content?: string;
  findings?: Finding[];
}

export interface ReviewJobStatus {
  status: "queued" | "running" | "completed" | "failed";
  agents: Record<string, "queued" | "running" | "completed" | "failed">;
  completed_agents: number;
  total_agents: number;
  review?: Review;
  error?: string;
}

export interface PullRequest {
  id: string;
  repository_name: string;
  pr_number: number;
  title: string;
  source_branch: string;
  target_branch: string;
  author: string;
  status: "open" | "closed" | "merged" | "draft";
  additions: number;
  deletions: number;
  changed_files: number;
  created_at: string;
}

export interface AgentConfig {
  id: string;
  agent_id: string;
  name: string;
  description: string;
  is_enabled: boolean;
  provider: string;
  model_name: string;
  capabilities: string[];
  options?: Record<string, unknown>;
}

export interface ProviderStatus {
  provider: string;
  name: string;
  is_available: boolean;
  current_model: string;
  endpoint: string;
  type: "local" | "cloud";
  note?: string | null;
  available_models?: string[];
}

export interface ProviderStatusResponse {
  active_provider: string;
  providers: ProviderStatus[];
}

export interface ProviderTestResponse {
  provider: string;
  success: boolean;
  message: string;
  latency_ms?: number | null;
  models?: string[];
}

export interface GitHubStatus {
  connected: boolean;
  username?: string | null;
  configured: boolean;
  auth_type: string;
  auth_method?: string;
  connection_status?: "connected" | "expired" | "revoked" | "disconnected" | "not_connected" | string;
  app_configured?: boolean;
  installation_id?: string | null;
}

export interface ConversationRepoContext {
  conversation_id: string;
  repository_full_name: string;
  repository_id?: string | null;
  default_branch: string;
  selected_branch: string;
  last_inspected_commit?: string | null;
}

export interface GitHubRepo {
  id: number;
  name: string;
  full_name: string;
  owner: string;
  private: boolean;
  html_url: string;
  default_branch: string;
  description?: string;
  language?: string;
  visibility?: string;
  updated_at?: string;
}

export interface GitHubPullRequest {
  number: number;
  title: string;
  state: string;
  author: string;
  html_url: string;
  created_at?: string;
  updated_at?: string;
  head_branch: string;
  base_branch: string;
  body?: string;
}

export interface OverviewMetrics {
  total_reviews: number;
  total_findings: number;
  critical_findings: number;
  pull_requests_count: number | null;
  open_pull_requests_count: number | null;
  active_agents_count: number;
  total_agents_count: number;
  github_connected: boolean;
  recent_reviews: Review[];
}
