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
    <div className="w-full max-w-6xl mx-auto px-3.5 sm:px-6 py-4 sm:py-8 space-y-4 sm:space-y-6 relative z-10 text-left min-w-0 box-border">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 sm:gap-4 pb-4 sm:pb-6 border-b border-white/10 min-w-0 w-full">
        <div className="min-w-0 max-w-full">
          <div className="flex items-center gap-2 flex-wrap">
            <h1 className="text-xl sm:text-2xl md:text-3xl font-semibold text-white tracking-tight truncate">
              Pull Requests
            </h1>
            {isLoading && pullRequests.length > 0 && (
              <span className="flex items-center gap-1.5 px-2 py-0.5 rounded-full text-[11px] font-mono bg-white/10 text-neutral-300 border border-white/10 animate-pulse shrink-0">
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-ping" />
                <span>Syncing...</span>
              </span>
            )}
          </div>
          <p className="text-xs sm:text-sm text-neutral-400 mt-1 break-words">
            Real pull requests retrieved from your connected GitHub repositories
          </p>
        </div>

        {isGitHubConnected && !error && (
          <div className="flex items-center justify-between sm:justify-start gap-1 p-1 rounded-xl bg-white/5 border border-white/10 text-xs font-mono w-full sm:w-auto shrink-0 max-w-full">
            {["all", "open", "merged", "closed"].map((f) => (
              <button
                key={f}
                type="button"
                onClick={() => setFilter(f)}
                className={`flex-1 sm:flex-initial text-center px-2.5 sm:px-3 py-1.5 rounded-lg capitalize transition-colors whitespace-nowrap min-w-0 cursor-pointer ${
                  filter === f
                    ? "bg-white/20 text-white font-semibold shadow-sm"
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
        <div className="glass-panel p-6 sm:p-12 text-center rounded-2xl max-w-lg mx-auto space-y-4 my-4 sm:my-8 w-full min-w-0 box-border">
          <div className="w-12 h-12 rounded-2xl bg-white/5 border border-white/10 flex items-center justify-center mx-auto text-neutral-300">
            <GithubIcon className="w-6 h-6" />
          </div>
          <div>
            <h2 className="text-base font-semibold text-white">GitHub Not Connected</h2>
            <p className="text-xs text-neutral-400 mt-1.5 leading-relaxed break-words">
              Connect your GitHub account to access pull requests from your authorized repositories and run automated multi-agent code reviews.
            </p>
          </div>
          <button
            type="button"
            onClick={onConnectGitHub}
            className="btn-silver text-xs py-2 px-5 inline-flex items-center gap-2 mx-auto cursor-pointer"
          >
            <GithubIcon className="w-4 h-4" />
            <span>Connect GitHub</span>
          </button>
        </div>
      )}

      {error && isGitHubConnected && (
        <div className="glass-panel p-6 sm:p-8 text-center rounded-2xl max-w-md mx-auto space-y-3 border-red-500/20 w-full min-w-0 box-border">
          <div className="text-xs text-red-400 font-mono">GitHub Request Failed</div>
          <p className="text-xs text-neutral-400 break-words">{error}</p>
          <button
            type="button"
            onClick={onRetry}
            className="px-3.5 py-1.5 rounded-xl bg-white/10 hover:bg-white/20 text-white text-xs font-mono transition-colors cursor-pointer"
          >
            Retry Request
          </button>
        </div>
      )}

      {isLoading && pullRequests.length === 0 && (
        <div className="space-y-3 w-full min-w-0">
          {[1, 2, 3].map((i) => (
            <div
              key={i}
              className="glass-card p-4 sm:p-5 rounded-2xl flex flex-col sm:flex-row justify-between gap-4 animate-pulse w-full min-w-0 box-border"
            >
              <div className="space-y-2.5 flex-1 min-w-0">
                <div className="h-3.5 bg-white/10 rounded w-1/3 sm:w-1/4" />
                <div className="h-4.5 bg-white/15 rounded w-5/6 sm:w-3/4" />
                <div className="h-3 bg-white/5 rounded w-1/2 sm:w-1/3" />
              </div>
              <div className="h-8 bg-white/10 rounded-xl w-full sm:w-32 self-start sm:self-center shrink-0" />
            </div>
          ))}
        </div>
      )}

      {!error && isGitHubConnected && (pullRequests.length > 0 || !isLoading) && (
        <div className="space-y-3 w-full min-w-0">
          {filtered.length === 0 ? (
            <div className="glass-panel p-8 sm:p-12 text-center rounded-2xl text-xs text-neutral-500 font-mono w-full min-w-0 box-border">
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
                  className="glass-card p-3.5 sm:p-5 rounded-2xl flex flex-col sm:flex-row sm:items-center justify-between gap-3.5 sm:gap-4 hover:border-white/20 transition-all w-full min-w-0 box-border"
                >
                  <div className="flex items-start gap-3 sm:gap-4 min-w-0 flex-1 w-full">
                    <div className="p-2 sm:p-2.5 rounded-xl bg-white/5 text-neutral-300 mt-0.5 shrink-0">
                      <PrIcon className="w-4 h-4 sm:w-5 sm:h-5" />
                    </div>
                    <div className="min-w-0 flex-1 max-w-full">
                      <div className="flex items-center gap-1.5 sm:gap-2 mb-1 flex-wrap min-w-0">
                        <span
                          className="text-xs font-mono text-neutral-400 truncate max-w-[180px] xs:max-w-[240px] sm:max-w-xs block min-w-0"
                          title={pr.repository_name}
                        >
                          {pr.repository_name}
                        </span>
                        <span className="text-xs text-neutral-600 font-mono shrink-0">•</span>
                        <div className="shrink-0">{getStatusBadge(pr.status)}</div>
                      </div>
                      <h3 className="text-sm sm:text-base font-semibold text-white break-words [overflow-wrap:anywhere] min-w-0 leading-snug">
                        <span className="text-neutral-400 font-mono font-normal">#{pr.pr_number}</span>{" "}
                        {pr.title}
                      </h3>
                      <div className="flex flex-wrap items-center gap-x-2 gap-y-1 sm:gap-x-3 text-xs text-neutral-400 font-mono mt-1.5 min-w-0 max-w-full">
                        <span className="truncate max-w-[120px] sm:max-w-[180px]" title={`Author: ${pr.author}`}>
                          by {pr.author}
                        </span>
                        <span className="shrink-0">•</span>
                        <div className="inline-flex items-center gap-1 min-w-0 max-w-full overflow-hidden">
                          <span
                            className="text-white/80 max-w-[100px] xs:max-w-[140px] sm:max-w-[200px] truncate inline-block align-bottom"
                            title={`Source: ${pr.source_branch}`}
                          >
                            {pr.source_branch}
                          </span>
                          <span className="text-neutral-600 shrink-0">→</span>
                          <span
                            className="text-neutral-500 max-w-[100px] xs:max-w-[140px] sm:max-w-[200px] truncate inline-block align-bottom"
                            title={`Target: ${pr.target_branch}`}
                          >
                            {pr.target_branch}
                          </span>
                        </div>
                        {pr.created_at && (
                          <>
                            <span className="hidden xs:inline shrink-0">•</span>
                            <span className="text-neutral-500 whitespace-nowrap shrink-0">
                              {new Date(pr.created_at).toLocaleDateString()}
                            </span>
                          </>
                        )}
                      </div>
                    </div>
                  </div>

                  <button
                    type="button"
                    onClick={() => onReviewPr(pr)}
                    disabled={isReviewing}
                    className="btn-silver w-full sm:w-auto justify-center text-xs py-2 px-3.5 sm:px-4 shrink-0 transition-all cursor-pointer"
                    aria-label={`Run Agent Review for pull request #${pr.pr_number}`}
                  >
                    <CodeIcon className="w-3.5 h-3.5 shrink-0" />
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
