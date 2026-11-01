import React from "react";
import type { OverviewMetrics, Review } from "../types";
import { AgentIcon, CodeIcon, GithubIcon, HistoryIcon, PrIcon, SecurityIcon } from "../components/icons/Icons";

interface OverviewPageProps {
  metrics: OverviewMetrics | null;
  isLoading?: boolean;
  error?: string | null;
  onRetry: () => void;
  onStartReview: () => void;
  onOpenReviewDetail: (review: Review) => void;
  onNavigatePrs: () => void;
  onNavigateAgents: () => void;
  onNavigateHistory: () => void;
  onConnectGitHub: () => void;
}

export const OverviewPage: React.FC<OverviewPageProps> = React.memo(({
  metrics,
  isLoading = false,
  error = null,
  onRetry,
  onStartReview,
  onOpenReviewDetail,
  onNavigatePrs,
  onNavigateAgents,
  onNavigateHistory,
  onConnectGitHub,
}) => {
  return (
    <div className="max-w-6xl mx-auto px-6 py-8 space-y-8 relative z-10 text-left">

      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-6 border-b border-white/10">
        <div>
          <div className="flex items-center gap-2.5">
            <h1 className="text-2xl sm:text-3xl font-semibold text-white tracking-tight">
              System Overview
            </h1>
            {isLoading && metrics && (
              <span className="text-[10px] font-mono px-2 py-0.5 rounded-full bg-white/10 text-neutral-400">
                Updating...
              </span>
            )}
          </div>
          <p className="text-xs sm:text-sm text-neutral-400 mt-1">
            Real-time metrics derived from your stored reviews and GitHub integration
          </p>
        </div>
        <button onClick={onStartReview} className="btn-silver self-start sm:self-auto">
          <CodeIcon className="w-4 h-4" />
          <span>New Review</span>
        </button>
      </div>

      {error && (
        <div className="glass-panel p-6 rounded-2xl flex flex-col sm:flex-row items-center justify-between gap-4 border-red-500/20 text-xs">
          <div className="space-y-1">
            <div className="text-red-400 font-semibold font-mono">Failed to load overview data</div>
            <div className="text-neutral-400">{error}</div>
          </div>
          <button
            onClick={onRetry}
            className="px-4 py-2 rounded-xl bg-white/10 hover:bg-white/20 text-white font-mono transition-colors"
          >
            Retry Request
          </button>
        </div>
      )}

      {isLoading && !metrics && !error && (
        <div className="space-y-8 animate-pulse">
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            {[1, 2, 3, 4].map((i) => (
              <div key={i} className="glass-card p-5 rounded-2xl space-y-3">
                <div className="h-3 bg-white/10 rounded w-1/2" />
                <div className="h-8 bg-white/20 rounded w-1/3" />
                <div className="h-2.5 bg-white/5 rounded w-3/4" />
              </div>
            ))}
          </div>
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <div className="glass-panel p-6 rounded-2xl h-64 bg-white/[0.02]" />
            <div className="glass-panel p-6 rounded-2xl h-64 bg-white/[0.02]" />
          </div>
        </div>
      )}

      {metrics && (
        <>

          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">

            <div
              className="glass-card p-5 rounded-2xl cursor-pointer hover:border-white/20 transition-all"
              onClick={onNavigateHistory}
            >
              <div className="flex items-center justify-between text-neutral-400 text-xs font-mono mb-2">
                <span>TOTAL REVIEWS</span>
                <HistoryIcon className="w-4 h-4 text-neutral-400" />
              </div>
              <div className="text-3xl font-semibold text-white tracking-tight">
                {metrics.total_reviews}
              </div>
              <div className="text-[11px] text-neutral-500 mt-1 font-mono">
                {metrics.total_findings} findings identified
              </div>
            </div>

            <div
              className="glass-card p-5 rounded-2xl cursor-pointer hover:border-white/20 transition-all"
              onClick={metrics.github_connected ? onNavigatePrs : onConnectGitHub}
            >
              <div className="flex items-center justify-between text-neutral-400 text-xs font-mono mb-2">
                <span>PULL REQUESTS</span>
                <PrIcon className="w-4 h-4 text-neutral-400" />
              </div>
              <div className="text-3xl font-semibold text-white tracking-tight">
                {metrics.github_connected ? (metrics.pull_requests_count ?? "—") : "—"}
              </div>
              <div className="text-[11px] text-neutral-500 mt-1 font-mono">
                {!metrics.github_connected
                  ? "GitHub disconnected • Connect"
                  : metrics.pull_requests_count !== null
                  ? `${metrics.open_pull_requests_count ?? 0} open for review`
                  : "Unavailable"}
              </div>
            </div>

            <div
              className="glass-card p-5 rounded-2xl cursor-pointer hover:border-white/20 transition-all"
              onClick={onNavigateAgents}
            >
              <div className="flex items-center justify-between text-neutral-400 text-xs font-mono mb-2">
                <span>ACTIVE AGENTS</span>
                <AgentIcon className="w-4 h-4 text-neutral-400" />
              </div>
              <div className="text-3xl font-semibold text-white tracking-tight">
                {metrics.active_agents_count} / {metrics.total_agents_count}
              </div>
              <div className="text-[11px] text-neutral-500 mt-1 font-mono">
                Specialized review agents
              </div>
            </div>

            <div className="glass-card p-5 rounded-2xl">
              <div className="flex items-center justify-between text-neutral-400 text-xs font-mono mb-2">
                <span>SECURITY AUDIT</span>
                <SecurityIcon className="w-4 h-4 text-neutral-400" />
              </div>
              <div className="text-3xl font-semibold text-white tracking-tight">
                {metrics.critical_findings}
              </div>
              <div className="text-[11px] text-neutral-500 mt-1 font-mono">
                {metrics.critical_findings === 0
                  ? "Zero critical breaches"
                  : `${metrics.critical_findings} critical risk ${
                      metrics.critical_findings === 1 ? "review" : "reviews"
                    }`}
              </div>
            </div>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">

            <div className="glass-panel p-6 rounded-2xl space-y-4">
              <div className="flex items-center justify-between">
                <h2 className="text-sm font-semibold text-white uppercase tracking-wider font-mono">
                  Recent Multi-Agent Reviews
                </h2>
                <button
                  onClick={onNavigateHistory}
                  className="text-xs text-neutral-400 hover:text-white transition-colors"
                >
                  View All →
                </button>
              </div>

              <div className="space-y-3">
                {metrics.recent_reviews.length === 0 ? (
                  <div className="py-12 text-center text-xs text-neutral-500 font-mono">
                    No review history found. Click &quot;New Review&quot; to execute your first review.
                  </div>
                ) : (
                  metrics.recent_reviews.map((r) => (
                    <div
                      key={r.id}
                      onClick={() => onOpenReviewDetail(r)}
                      className="flex items-center justify-between p-3.5 rounded-xl bg-white/[0.03] hover:bg-white/[0.08] border border-white/10 transition-all cursor-pointer"
                    >
                      <div className="min-w-0 pr-4">
                        <div className="text-xs font-medium text-white truncate">{r.title}</div>
                        <div className="text-[11px] text-neutral-500 font-mono mt-0.5 truncate">
                          {r.repository_name} • {r.duration_seconds}s
                        </div>
                      </div>
                      <div className="flex items-center gap-2 flex-shrink-0">
                        <span
                          className={`px-2 py-0.5 rounded text-[10px] font-mono ${
                            r.has_critical
                              ? "bg-red-500/10 text-red-300 border border-red-500/30"
                              : "bg-white/10 text-white"
                          }`}
                        >
                          {r.finding_count} {r.finding_count === 1 ? "finding" : "findings"}
                        </span>
                      </div>
                    </div>
                  ))
                )}
              </div>
            </div>

            <div className="glass-panel p-6 rounded-2xl space-y-4">
              <div className="flex items-center justify-between">
                <h2 className="text-sm font-semibold text-white uppercase tracking-wider font-mono">
                  Pull Request Queue
                </h2>
                <button
                  onClick={onNavigatePrs}
                  className="text-xs text-neutral-400 hover:text-white transition-colors"
                >
                  Inspect Queue →
                </button>
              </div>

              <div className="space-y-3">
                {!metrics.github_connected ? (
                  <div className="py-10 text-center space-y-3">
                    <div className="text-xs text-neutral-400 font-mono">
                      GitHub account is not connected.
                    </div>
                    <button
                      onClick={onConnectGitHub}
                      className="btn-silver text-xs py-1.5 px-3.5 inline-flex items-center gap-2 mx-auto"
                    >
                      <GithubIcon className="w-3.5 h-3.5" />
                      <span>Connect GitHub</span>
                    </button>
                  </div>
                ) : metrics.pull_requests_count === 0 ? (
                  <div className="py-12 text-center text-xs text-neutral-500 font-mono">
                    No pull requests found in your connected repositories.
                  </div>
                ) : (
                  <div className="py-8 text-center space-y-3">
                    <div className="text-sm font-semibold text-white font-mono">
                      {metrics.open_pull_requests_count ?? 0} Pull Requests Open
                    </div>
                    <p className="text-xs text-neutral-400 max-w-xs mx-auto">
                      Real pull requests are synchronized with your GitHub repositories.
                    </p>
                    <button
                      onClick={onNavigatePrs}
                      className="px-3.5 py-1.5 rounded-xl bg-white/10 hover:bg-white/20 text-white text-xs font-mono transition-colors"
                    >
                      Inspect Queue ({metrics.pull_requests_count} Total) →
                    </button>
                  </div>
                )}
              </div>
            </div>
          </div>
        </>
      )}
    </div>
  );
});

OverviewPage.displayName = "OverviewPage";
