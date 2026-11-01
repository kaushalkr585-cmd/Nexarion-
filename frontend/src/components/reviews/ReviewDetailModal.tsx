import React, { useState } from "react";
import type { Finding, Review } from "../../types";
import { CloseIcon, SecurityIcon } from "../icons/Icons";

interface ReviewDetailModalProps {
  review: Review | null;
  isOpen: boolean;
  isLoadingDetails?: boolean;
  onClose: () => void;
}

export const ReviewDetailModal: React.FC<ReviewDetailModalProps> = ({
  review,
  isOpen,
  isLoadingDetails = false,
  onClose,
}) => {
  const [activeFilter, setActiveFilter] = useState<string>("ALL");

  if (!isOpen || !review) return null;

  const findings: Finding[] = review.findings || [];

  const filteredFindings = findings.filter((f) => {
    if (activeFilter === "ALL") return true;
    if (activeFilter === "CRITICAL") return f.severity === "CRITICAL";
    if (activeFilter === "SECURITY") return f.category === "SECURITY";
    if (activeFilter === "QUALITY") return f.category === "QUALITY";
    return true;
  });

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-md animate-fade-in">
      <div className="relative w-full max-w-4xl max-h-[90vh] flex flex-col rounded-2xl bg-[#0F0F0F] border border-white/20 shadow-2xl overflow-hidden">

        <div className="flex items-start justify-between gap-4 p-4 sm:p-6 border-b border-white/10 bg-black/40">
          <div className="min-w-0 flex-1 space-y-1">
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-xs font-mono text-neutral-400 truncate max-w-[220px] sm:max-w-md">
                {review.repository_name} • {review.pr_identifier}
              </span>
              <span
                className={`inline-flex items-center gap-1.5 text-[10px] px-2.5 py-0.5 rounded-full font-mono font-medium tracking-wide whitespace-nowrap shrink-0 ${
                  review.has_critical
                    ? "bg-red-500/10 text-red-300 border border-red-500/30"
                    : "bg-emerald-500/10 text-emerald-300 border border-emerald-500/30"
                }`}
              >
                <span
                  className={`w-1.5 h-1.5 rounded-full ${
                    review.has_critical ? "bg-red-400" : "bg-emerald-400"
                  }`}
                />
                {review.has_critical ? "CRITICAL RISK" : "CLEAN AUDIT"}
              </span>
            </div>
            <h2 className="text-base sm:text-lg font-semibold text-white break-words leading-snug">
              {review.title}
            </h2>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 rounded-lg text-neutral-400 hover:text-white hover:bg-white/10 transition-colors shrink-0 -mr-1 -mt-1 sm:mr-0 sm:mt-0"
            aria-label="Close modal"
          >
            <CloseIcon className="w-5 h-5" />
          </button>
        </div>

        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 sm:gap-4 px-4 sm:px-6 py-3 border-b border-white/10 bg-neutral-900/40 text-xs font-mono">
          <div>
            <span className="text-neutral-500 block">Total Findings</span>
            <span className="text-white font-semibold text-sm">{review.finding_count}</span>
          </div>
          <div>
            <span className="text-neutral-500 block">Review Duration</span>
            <span className="text-white font-semibold text-sm">{review.duration_seconds}s</span>
          </div>
          <div>
            <span className="text-neutral-500 block">Active Mode</span>
            <span className="text-white font-semibold text-sm">
              {(!review.provider || review.provider.toLowerCase() === "nvidia" || review.provider.toLowerCase() === "llm")
                ? "llm"
                : review.provider}
            </span>
          </div>
          <div>
            <span className="text-neutral-500 block">Agents Coordinated</span>
            <span className="text-white font-semibold text-sm">{review.agents_used?.length || 4}</span>
          </div>
        </div>

        <div className="flex items-center gap-2 px-4 sm:px-6 py-2.5 border-b border-white/10 bg-black/20 text-xs font-mono overflow-x-auto no-scrollbar">
          <span className="text-neutral-500 mr-2 shrink-0">Filter Findings:</span>
          {["ALL", "CRITICAL", "SECURITY", "QUALITY"].map((filter) => (
            <button
              key={filter}
              onClick={() => setActiveFilter(filter)}
              className={`px-2.5 py-1 rounded-md text-[11px] font-mono whitespace-nowrap shrink-0 transition-colors ${
                activeFilter === filter
                  ? filter === "CRITICAL"
                    ? "bg-red-500/20 text-red-200 font-semibold border border-red-500/30"
                    : "bg-white/20 text-white font-semibold"
                  : "text-neutral-400 hover:text-white hover:bg-white/5"
              }`}
            >
              {filter}
            </button>
          ))}
        </div>

        <div className="flex-1 overflow-y-auto p-4 sm:p-6 space-y-4">
          {isLoadingDetails && (
            <div className="flex items-center gap-2 rounded-xl border border-white/10 bg-white/[0.03] p-3 text-xs text-neutral-300">
              <div className="w-3.5 h-3.5 border-2 border-white/20 border-t-white rounded-full animate-spin flex-shrink-0" />
              Loading diff and agent findings…
            </div>
          )}

          {review.diff_content && (
            <details className="rounded-xl bg-black/40 border border-white/10">
              <summary className="cursor-pointer px-4 py-3 text-xs font-mono text-neutral-200 hover:text-white">
                Inspect reviewed diff ({review.diff_content.split("\n").length} lines)
              </summary>
              <pre className="max-h-80 overflow-auto border-t border-white/10 p-4 text-[11px] leading-relaxed text-neutral-300 whitespace-pre-wrap break-all">
                {review.diff_content}
              </pre>
            </details>
          )}

          {filteredFindings.length === 0 ? (
            isLoadingDetails ? null : (
              <div className="py-12 text-center text-neutral-500 text-xs font-mono">
                No findings match the selected filter.
              </div>
            )
          ) : (
            filteredFindings.map((finding) => (
              <div
                key={finding.id}
                className="p-4 rounded-xl bg-white/[0.03] border border-white/10 hover:border-white/20 transition-all space-y-2.5"
              >
                <div className="flex items-center justify-between text-xs font-mono">
                  <div className="flex items-center gap-2">
                    <span
                      className={`px-2 py-0.5 rounded font-mono font-semibold text-[10px] shrink-0 ${
                        finding.severity === "CRITICAL"
                          ? "bg-red-500/15 text-red-300 border border-red-500/30"
                          : "bg-white/10 text-white"
                      }`}
                    >
                      {finding.severity}
                    </span>
                    <span className="text-neutral-400">{finding.file_path}:{finding.line_start}</span>
                    {finding.rule_id && (
                      <span className="text-neutral-500">[{finding.rule_id}]</span>
                    )}
                  </div>
                  <div className="flex items-center gap-1.5 text-neutral-400 text-[11px]">
                    <SecurityIcon className="w-3.5 h-3.5" />
                    <span className="capitalize">{finding.agent}</span>
                  </div>
                </div>

                <div className="text-sm font-medium text-white">{finding.title}</div>
                <div className="text-xs text-neutral-300 leading-relaxed font-sans">{finding.description}</div>

                {finding.suggested_fix && (
                  <div className="mt-2 p-3 rounded-lg bg-black/60 border border-white/10 font-mono text-xs">
                    <div className="text-[10px] text-neutral-400 uppercase tracking-wider mb-1">
                      Suggested Fix:
                    </div>
                    <div className="text-neutral-200">{finding.suggested_fix}</div>
                  </div>
                )}
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
};
