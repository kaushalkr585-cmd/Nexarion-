import React, { useState } from "react";
import type { PullRequest } from "../types";
import { CodeIcon, GithubIcon, PrIcon } from "../components/icons/Icons";

interface PullRequestsPageProps {
  pullRequests: PullRequest[];
  isLoading?: boolean;
  error?: string | null;
  isGitHubConnected: boolean;
  isReviewingId?: string | null;
  onRetry: () => void;
  onConnectGitHub: () => void;
  onReviewPr: (pr: PullRequest) => void;
}

export const PullRequestsPage: React.FC<PullRequestsPageProps> = React.memo(({
  pullRequests,
  isLoading = false,
  error = null,
  isGitHubConnected,
  isReviewingId = null,
  onRetry,
  onConnectGitHub,
  onReviewPr,
}) => {
  const [filter, setFilter] = useState<string>("all");

  const filtered = pullRequests.filter((pr) => {
    if (filter === "all") return true;
    return pr.status?.toLowerCase() === filter;
  });

  const getStatusBadge = (status: string) => {
    const s = status.toLowerCase();
    if (s === "open") {
      return (
        <span className="text-[10px] px-2 py-0.5 rounded-full font-mono bg-emerald-500/10 text-emerald-300 border border-emerald-500/30 uppercase">
          Open
        </span>
      );
    }
    if (s === "merged") {
      return (
        <span className="text-[10px] px-2 py-0.5 rounded-full font-mono bg-purple-500/10 text-purple-300 border border-purple-500/30 uppercase">
          Merged
        </span>
      );
    }
    return (
      <span className="text-[10px] px-2 py-0.5 rounded-full font-mono bg-neutral-800 text-neutral-400 border border-neutral-700 uppercase">
        Closed
      </span>
    );
  };

  return (
    <div className="max-w-6xl mx-auto px-6 py-8 space-y-6 relative z-10 text-left">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-6 border-b border-white/10">
        <div>
          <h1 className="text-2xl sm:text-3xl font-semibold text-white tracking-tight">
            Pull Requests
          </h1>
          <p className="text-xs sm:text-sm text-neutral-400 mt-1">
            Real pull requests retrieved from your connected GitHub repositories
          </p>
        </div>

        {isGitHubConnected && !error && (
          <div className="flex items-center gap-1.5 p-1 rounded-xl bg-white/5 border border-white/10 text-xs font-mono">
            {["all", "open", "merged", "closed"].map((f) => (
              <button
                key={f}
                onClick={() => setFilter(f)}
                className={`px-3 py-1.5 rounded-lg capitalize transition-colors ${
                  filter === f
                    ? "bg-white/20 text-white font-semibold"
                    : "text-neutral-400 hover:text-white"
                }`}
              >
                {f}
              </button>
            ))}
          </div>
        )}
      </div>

      {!isGitHubConnected && !isLoading && (
        <div className="glass-panel p-12 text-center rounded-2xl max-w-lg mx-auto space-y-4 my-8">
          <div className="w-12 h-12 rounded-2xl bg-white/5 border border-white/10 flex items-center justify-center mx-auto text-neutral-300">
            <GithubIcon className="w-6 h-6" />
          </div>
          <div>
            <h2 className="text-base font-semibold text-white">GitHub Not Connected</h2>
            <p className="text-xs text-neutral-400 mt-1.5 leading-relaxed">
              Connect your GitHub account to access pull requests from your authorized repositories and run automated multi-agent code reviews.
            </p>
          </div>
          <button
            onClick={onConnectGitHub}
            className="btn-silver text-xs py-2 px-5 inline-flex items-center gap-2 mx-auto"
          >
            <GithubIcon className="w-4 h-4" />
            <span>Connect GitHub</span>
          </button>
        </div>
      )}

      {error && isGitHubConnected && (
        <div className="glass-panel p-8 text-center rounded-2xl max-w-md mx-auto space-y-3 border-red-500/20">
          <div className="text-xs text-red-400 font-mono">GitHub Request Failed</div>
          <p className="text-xs text-neutral-400">{error}</p>
          <button
            onClick={onRetry}
            className="px-3.5 py-1.5 rounded-xl bg-white/10 hover:bg-white/20 text-white text-xs font-mono transition-colors"
          >
            Retry Request
          </button>
        </div>
      )}

      {isLoading && pullRequests.length === 0 && (
        <div className="space-y-3">
          {[1, 2, 3].map((i) => (
            <div
              key={i}
              className="glass-card p-5 rounded-2xl flex flex-col sm:flex-row justify-between gap-4 animate-pulse"
            >
              <div className="space-y-2 flex-1">
                <div className="h-3.5 bg-white/10 rounded w-1/4" />
                <div className="h-4.5 bg-white/15 rounded w-3/4" />
                <div className="h-3 bg-white/5 rounded w-1/2" />
              </div>
              <div className="h-8 bg-white/10 rounded-xl w-32 self-start sm:self-center" />
            </div>
          ))}
        </div>
      )}

      {!error && isGitHubConnected && (pullRequests.length > 0 || !isLoading) && (
        <div className="space-y-3">
          {filtered.length === 0 ? (
            <div className="glass-panel p-12 text-center rounded-2xl text-xs text-neutral-500 font-mono">
              {pullRequests.length === 0
                ? "No pull requests found in your connected repositories."
                : `No pull requests found matching "${filter}".`}
            </div>
          ) : (
            filtered.map((pr) => {
              const isReviewing = isReviewingId === pr.id;
              return (
                <div
                  key={pr.id}
                  className="glass-card p-5 rounded-2xl flex flex-col sm:flex-row sm:items-center justify-between gap-4 hover:border-white/20 transition-all"
                >
                  <div className="flex items-start gap-4 min-w-0">
                    <div className="p-2.5 rounded-xl bg-white/5 text-neutral-300 mt-0.5 flex-shrink-0">
                      <PrIcon className="w-5 h-5" />
                    </div>
                    <div className="min-w-0">
                      <div className="flex items-center gap-2 mb-1 flex-wrap">
                        <span className="text-xs font-mono text-neutral-400 truncate max-w-xs">
                          {pr.repository_name}
                        </span>
                        <span className="text-xs text-neutral-600 font-mono">•</span>
                        {getStatusBadge(pr.status)}
                      </div>
                      <h3 className="text-sm sm:text-base font-semibold text-white break-words">
                        #{pr.pr_number}: {pr.title}
                      </h3>
                      <div className="flex flex-wrap items-center gap-2 sm:gap-3 text-xs text-neutral-400 font-mono mt-1.5">
                        <span>by {pr.author}</span>
                        <span>•</span>
                        <span className="text-white/80">{pr.source_branch}</span>
                        <span>→</span>
                        <span className="text-neutral-500">{pr.target_branch}</span>
                        {pr.created_at && (
                          <>
                            <span>•</span>
                            <span className="text-neutral-500">
                              {new Date(pr.created_at).toLocaleDateString()}
                            </span>
                          </>
                        )}
                      </div>
                    </div>
                  </div>

                  <button
                    onClick={() => onReviewPr(pr)}
                    disabled={isReviewing}
                    className="btn-silver self-start sm:self-auto text-xs py-2 px-4 flex-shrink-0"
                  >
                    <CodeIcon className="w-3.5 h-3.5" />
                    <span>{isReviewing ? "Analyzing..." : "Run Agent Review"}</span>
                  </button>
                </div>
              );
            })
          )}
        </div>
      )}
    </div>
  );
});
