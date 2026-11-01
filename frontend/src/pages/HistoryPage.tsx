import React, { useState } from "react";
import type { Review } from "../types";
import { CodeIcon, HistoryIcon } from "../components/icons/Icons";

interface HistoryPageProps {
  reviews: Review[];
  onOpenReviewDetail: (review: Review) => void;
  onStartReview: () => void;
  onDeleteReview?: (id: string) => Promise<void>;
  onClearReviews?: () => Promise<void>;
}

export const HistoryPage: React.FC<HistoryPageProps> = React.memo(({
  reviews,
  onOpenReviewDetail,
  onStartReview,
  onDeleteReview,
  onClearReviews,
}) => {
  const [confirmDeleteId, setConfirmDeleteId] = useState<string | null>(null);
  const [isDeletingId, setIsDeletingId] = useState<string | null>(null);
  const [showClearConfirm, setShowClearConfirm] = useState(false);
  const [isClearing, setIsClearing] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  const handleDelete = async (e: React.MouseEvent, id: string) => {
    e.stopPropagation();
    if (!onDeleteReview) return;
    setIsDeletingId(id);
    setActionError(null);
    try {
      await onDeleteReview(id);
      setConfirmDeleteId(null);
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Failed to delete review.");
    } finally {
      setIsDeletingId(null);
    }
  };

  const handleClearAll = async () => {
    if (!onClearReviews) return;
    setIsClearing(true);
    setActionError(null);
    try {
      await onClearReviews();
      setShowClearConfirm(false);
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Failed to clear reviews.");
    } finally {
      setIsClearing(false);
    }
  };

  return (
    <div className="max-w-6xl mx-auto px-4 sm:px-6 py-6 sm:py-8 space-y-6 relative z-10 text-left">

      <div className="flex flex-col sm:flex-row sm:items-start lg:items-center justify-between gap-4 pb-6 border-b border-white/10 flex-wrap">
        <div className="min-w-0 flex-1 max-w-2xl">
          <h1 className="text-2xl sm:text-3xl font-semibold text-white tracking-tight">
            Review History
          </h1>
          <p className="text-xs sm:text-sm text-neutral-400 mt-1 leading-relaxed">
            Persisted execution audits and findings across all repositories ({reviews.length}{" "}
            {reviews.length === 1 ? "record" : "records"})
          </p>
        </div>
        <div className="flex items-center flex-wrap gap-2.5 self-start sm:self-auto flex-shrink-0 w-full sm:w-auto justify-start sm:justify-end">
          {onClearReviews && (
            <button
              type="button"
              disabled={reviews.length === 0 || isClearing}
              onClick={() => setShowClearConfirm(true)}
              className="inline-flex items-center justify-center gap-1.5 py-2 px-3.5 text-xs font-medium rounded-xl bg-white/5 hover:bg-red-500/10 text-neutral-400 hover:text-red-400 border border-white/10 hover:border-red-500/30 transition-all whitespace-nowrap flex-shrink-0 cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed disabled:hover:bg-white/5 disabled:hover:text-neutral-400 disabled:hover:border-white/10"
              title={reviews.length === 0 ? "No audit records to clear" : "Clear all review audits"}
            >
              Clear Audit
            </button>
          )}
          <button
            type="button"
            onClick={onStartReview}
            className="btn-silver text-xs py-2 px-4 inline-flex items-center gap-1.5 whitespace-nowrap flex-shrink-0 cursor-pointer"
            title="Start a new multi-agent code review"
          >
            <CodeIcon className="w-3.5 h-3.5 flex-shrink-0" />
            <span className="whitespace-nowrap">New Review</span>
          </button>
        </div>
      </div>

      {actionError && (
        <div className="p-3.5 rounded-xl bg-red-500/10 border border-red-500/20 text-xs text-red-200">
          {actionError}
        </div>
      )}

      {showClearConfirm && (
        <div className="p-4 rounded-2xl bg-neutral-900 border border-red-500/30 space-y-3 animate-fade-in">
          <div className="flex items-center justify-between">
            <div className="text-sm font-semibold text-white">Clear All Review Audits?</div>
            <button
              type="button"
              onClick={() => setShowClearConfirm(false)}
              className="text-neutral-400 hover:text-white text-xs p-1 cursor-pointer"
              aria-label="Close"
            >
              ✕
            </button>
          </div>
          <p className="text-xs text-neutral-400 leading-relaxed">
            This will permanently delete all {reviews.length} past reviews and their associated agent
            findings from the database. This action cannot be undone.
          </p>
          <div className="flex items-center gap-2 pt-1">
            <button
              type="button"
              onClick={handleClearAll}
              disabled={isClearing}
              className="px-3.5 py-1.5 rounded-lg bg-red-600 hover:bg-red-500 text-white text-xs font-medium transition-colors cursor-pointer disabled:opacity-50"
            >
              {isClearing ? "Clearing..." : "Yes, Clear All Audits"}
            </button>
            <button
              type="button"
              onClick={() => setShowClearConfirm(false)}
              disabled={isClearing}
              className="px-3.5 py-1.5 rounded-lg bg-white/5 hover:bg-white/10 text-neutral-300 text-xs transition-colors cursor-pointer"
            >
              Cancel
            </button>
          </div>
        </div>
      )}

      <div className="space-y-3">
        {reviews.length === 0 ? (
          <div className="glass-panel p-16 text-center rounded-2xl space-y-4">
            <HistoryIcon className="w-8 h-8 text-neutral-500 mx-auto" />
            <div className="text-sm font-semibold text-white">No review records found</div>
            <p className="text-xs text-neutral-400 max-w-sm mx-auto">
              You haven&apos;t executed any multi-agent reviews yet. Click &quot;New Review&quot; to inspect code.
            </p>
            <button
              type="button"
              onClick={onStartReview}
              className="btn-silver text-xs py-2 px-4 inline-flex items-center gap-1.5 whitespace-nowrap mx-auto cursor-pointer"
            >
              <CodeIcon className="w-3.5 h-3.5" />
              <span>New Review</span>
            </button>
          </div>
        ) : (
          reviews.map((r) => {
            const isConfirming = confirmDeleteId === r.id;
            return (
              <div
                key={r.id}
                onClick={() => onOpenReviewDetail(r)}
                className="glass-card p-4 sm:p-5 rounded-2xl flex flex-col sm:flex-row sm:items-center justify-between gap-4 cursor-pointer hover:border-white/30 transition-all"
              >
                <div className="space-y-1 min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="text-xs font-mono text-neutral-400 truncate max-w-full">
                      {r.repository_name} • {r.pr_identifier}
                    </span>
                    <span
                      className={`inline-flex items-center gap-1.5 text-[10px] px-2.5 py-0.5 rounded-full font-mono font-medium tracking-wide whitespace-nowrap shrink-0 ${
                        r.has_critical
                          ? "bg-red-500/10 text-red-300 border border-red-500/30"
                          : "bg-emerald-500/10 text-emerald-300 border border-emerald-500/30"
                      }`}
                    >
                      <span
                        className={`w-1.5 h-1.5 rounded-full ${
                          r.has_critical ? "bg-red-400" : "bg-emerald-400"
                        }`}
                      />
                      {r.has_critical ? "CRITICAL RISK" : "CLEAN AUDIT"}
                    </span>
                  </div>
                  <h3 className="text-sm sm:text-base font-semibold text-white break-words">
                    {r.title}
                  </h3>
                  <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-neutral-400 font-mono">
                    <span>{new Date(r.created_at).toLocaleString()}</span>
                    <span>•</span>
                    <span>Duration: {r.duration_seconds}s</span>
                    <span>•</span>
                    <span>
                      Mode:{" "}
                      {!r.provider ||
                      r.provider.toLowerCase() === "nvidia" ||
                      r.provider.toLowerCase() === "llm"
                        ? "llm"
                        : r.provider}
                    </span>
                  </div>
                </div>

                <div className="flex items-center justify-between sm:justify-end gap-4 w-full sm:w-auto flex-shrink-0 pt-2 sm:pt-0 border-t sm:border-t-0 border-white/5">
                  <div className="text-right">
                    <div className="text-sm font-semibold text-white font-mono">
                      {r.finding_count} {r.finding_count === 1 ? "Finding" : "Findings"}
                    </div>
                    <div className="text-[11px] text-neutral-500 font-mono">
                      {r.agents_used?.length || 4} agents
                    </div>
                  </div>

                  {onDeleteReview && (
                    <div onClick={(e) => e.stopPropagation()} className="relative">
                      {isConfirming ? (
                        <div className="flex items-center gap-1.5 p-1 bg-red-500/10 border border-red-500/30 rounded-xl text-xs">
                          <span className="text-[10px] text-neutral-300 font-mono px-1">Delete?</span>
                          <button
                            type="button"
                            onClick={(e) => handleDelete(e, r.id)}
                            disabled={isDeletingId === r.id}
                            className="px-2 py-1 bg-red-600 hover:bg-red-500 text-white rounded-lg text-xs font-medium transition-colors"
                          >
                            {isDeletingId === r.id ? "..." : "Delete review"}
                          </button>
                          <button
                            type="button"
                            onClick={(e) => {
                              e.stopPropagation();
                              setConfirmDeleteId(null);
                            }}
                            className="px-1.5 py-1 text-neutral-400 hover:text-white rounded-lg text-xs"
                          >
                            Cancel
                          </button>
                        </div>
                      ) : (
                        <button
                          type="button"
                          onClick={(e) => {
                            e.stopPropagation();
                            setConfirmDeleteId(r.id);
                          }}
                          className="px-2.5 py-1.5 rounded-lg text-xs font-mono text-neutral-400 hover:text-red-400 hover:bg-white/5 border border-white/10 transition-colors"
                          title="Delete review"
                        >
                          Delete review
                        </button>
                      )}
                    </div>
                  )}

                  <span className="text-neutral-400 text-sm">→</span>
                </div>
              </div>
            );
          })
        )}
      </div>
    </div>
  );
});
