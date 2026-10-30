import React, { useState } from "react";
import type { Review, WaveState } from "../../types";
import { reviewApi } from "../../services/api";
import { CloseIcon, CodeIcon } from "../icons/Icons";

interface ReviewComposerModalProps {
  isOpen: boolean;
  onClose: () => void;
  onReviewCreated: (review: Review) => void;
  setWaveState: (state: WaveState) => void;
  initialDiff?: string;
  initialTitle?: string;
  initialRepo?: string;
  isLoadingDiff?: boolean;
  diffError?: string | null;
  onRetryFetchDiff?: () => void;
}

const SAMPLE_SECURITY_DIFF = `--- a/src/auth_service.py
+++ b/src/auth_service.py
@@ -25,6 +25,10 @@ def login(username, password, db):
-    query = text("SELECT id, role FROM users WHERE username = :u AND password = :p")
-    return db.execute(query, {"u": username, "p": hash_pwd(password)}).first()
+    # Legacy bypass for admin inspection
+    raw_query = f"SELECT id, role FROM users WHERE username = '{username}' AND password = '{password}'"
+    return db.execute(text(raw_query)).first()
+
+    # Hardcoded fallback token
+    BACKDOOR_KEY = "super_admin_secret_token_12345"`;

const SAMPLE_COMPLEX_DIFF = `--- a/src/processor.py
+++ b/src/processor.py
@@ -10,6 +10,25 @@ class DataProcessor:
+    def process_items(self, items, flags, threshold, multiplier):
+        res = []
+        for item in items:
+            if item.is_valid():
+                if flags.get("deep_scan"):
+                    for sub in item.children:
+                        if sub.score > threshold:
+                            for k, v in sub.metadata.items():
+                                if k.startswith("sec_"):
+                                    res.append(v * multiplier)
+        return res`;

export const ReviewComposerModal: React.FC<ReviewComposerModalProps> = ({
  isOpen,
  onClose,
  onReviewCreated,
  setWaveState,
  initialDiff = "",
  initialTitle = "",
  initialRepo = "",
  isLoadingDiff = false,
  diffError = null,
  onRetryFetchDiff,
}) => {
  const [diffText, setDiffText] = useState(initialDiff);
  const [title, setTitle] = useState(initialTitle);
  const [repoName, setRepoName] = useState(initialRepo);
  const provider = "nvidia";
  const [includeLlm, setIncludeLlm] = useState(true);
  const [isLoading, setIsLoading] = useState(false);
  const [reviewStage, setReviewStage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  React.useEffect(() => {
    if (isOpen) {
      setDiffText(initialDiff);
      if (initialTitle) setTitle(initialTitle);
      if (initialRepo) setRepoName(initialRepo);
      setError(null);
      setReviewStage(null);
    }
  }, [isOpen, initialDiff, initialTitle, initialRepo]);

  if (!isOpen) return null;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!diffText.trim() || isLoading || isLoadingDiff) return;

    setIsLoading(true);
    setError(null);
    setWaveState("reviewing");
    setReviewStage("Preparing review context...");

    const stageTimer1 = setTimeout(() => {
      setReviewStage("Running specialized agents (Security, Quality, Performance)...");
    }, 800);

    const stageTimer2 = setTimeout(() => {
      setReviewStage("Processing findings and compiling report...");
    }, 2800);

    try {
      const review = await reviewApi.createReview({
        diff_text: diffText.trim(),
        title: title.trim() || "Manual Code Review",
        repository_name: repoName.trim() || "custom-repo",
        provider,
        include_llm: includeLlm,
      });

      clearTimeout(stageTimer1);
      clearTimeout(stageTimer2);
      setReviewStage("Review completed.");
      setWaveState("responding");
      setTimeout(() => setWaveState("idle"), 2000);
      onReviewCreated(review);
      onClose();
    } catch (err: unknown) {
      clearTimeout(stageTimer1);
      clearTimeout(stageTimer2);
      setWaveState("error");
      setTimeout(() => setWaveState("idle"), 2000);
      setError(err instanceof Error ? err.message : "Failed to execute review.");
    } finally {
      setIsLoading(false);
      setReviewStage(null);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-md animate-fade-in">
      <div className="relative w-full max-w-3xl rounded-2xl bg-[#0F0F0F] border border-white/20 shadow-2xl p-6 overflow-hidden">

        <div className="flex items-center justify-between pb-4 border-b border-white/10">
          <div className="flex items-center gap-2.5">
            <div className="p-2 rounded-lg bg-white/10 text-white">
              <CodeIcon className="w-5 h-5" />
            </div>
            <div>
              <h3 className="text-base font-semibold text-white">New Multi-Agent Review</h3>
              <p className="text-xs text-neutral-400">Run parallel AST, Ruff, Bandit, and LLM analysis</p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 rounded-lg text-neutral-400 hover:text-white hover:bg-white/10 transition-colors"
            aria-label="Close modal"
          >
            <CloseIcon className="w-5 h-5" />
          </button>
        </div>

        {error && (
          <div className="mt-4 p-3 rounded-xl bg-red-500/10 border border-red-500/20 text-xs text-neutral-300">
            {error}
          </div>
        )}

        <form onSubmit={handleSubmit} className="mt-5 space-y-4">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label className="block text-xs font-mono text-neutral-400 mb-1">Review Title</label>
              <input
                type="text"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                placeholder="e.g. Multi-Agent Security Audit"
                required
                className="w-full bg-black/60 border border-white/15 rounded-lg px-3 py-2 text-xs text-white focus:outline-none focus:border-white/40 placeholder:text-neutral-600"
              />
            </div>
            <div>
              <label className="block text-xs font-mono text-neutral-400 mb-1">Target Repository</label>
              <input
                type="text"
                value={repoName}
                onChange={(e) => setRepoName(e.target.value)}
                placeholder="e.g. company/repo"
                required
                className="w-full bg-black/60 border border-white/15 rounded-lg px-3 py-2 text-xs text-white focus:outline-none focus:border-white/40 placeholder:text-neutral-600"
              />
            </div>
          </div>

          <div>
            <div className="flex items-center justify-between mb-1.5">
              <label className="text-xs font-mono text-neutral-400">Unified Git Diff Content</label>
              <div className="flex gap-2">
                <button
                  type="button"
                  onClick={() => setDiffText(SAMPLE_SECURITY_DIFF)}
                  className="text-[11px] font-mono text-neutral-400 hover:text-white underline"
                >
                  Load Security Flaw
                </button>
                <span className="text-neutral-600">•</span>
                <button
                  type="button"
                  onClick={() => setDiffText(SAMPLE_COMPLEX_DIFF)}
                  className="text-[11px] font-mono text-neutral-400 hover:text-white underline"
                >
                  Load Complexity Spike
                </button>
              </div>
            </div>
            {isLoadingDiff ? (
              <div className="w-full h-48 flex flex-col items-center justify-center rounded-xl bg-black/70 border border-white/15 p-6 text-center">
                <div className="w-5 h-5 border-2 border-white/20 border-t-white rounded-full animate-spin mb-3" />
                <span className="text-xs font-mono text-neutral-300">Fetching pull request changes from GitHub...</span>
                <span className="text-[11px] text-neutral-500 mt-1">Retrieving unified diff patch</span>
              </div>
            ) : diffError ? (
              <div className="w-full h-48 flex flex-col items-center justify-center rounded-xl bg-black/70 border border-red-500/20 p-6 text-center">
                <span className="text-xs text-red-400 mb-2">{diffError}</span>
                {onRetryFetchDiff && (
                  <button
                    type="button"
                    onClick={onRetryFetchDiff}
                    className="px-3 py-1.5 rounded-lg bg-white/10 hover:bg-white/20 text-xs text-white font-mono cursor-pointer"
                  >
                    Retry Fetch
                  </button>
                )}
              </div>
            ) : (
              <textarea
                value={diffText}
                onChange={(e) => setDiffText(e.target.value)}
                required
                rows={9}
                placeholder="Paste unified diff patch here..."
                className="w-full bg-black/70 border border-white/15 rounded-xl p-3 text-xs font-mono text-neutral-200 resize-none focus:outline-none focus:border-white/40"
              />
            )}
          </div>

          <div className="flex flex-wrap items-center justify-between gap-4 pt-2 border-t border-white/10 text-xs">
            <div className="flex items-center gap-4">
              <div className="flex items-center gap-2">
                <span className="text-neutral-400 font-mono">Inference:</span>
                <span className="text-xs font-mono text-neutral-300 bg-white/10 px-2.5 py-1 rounded-lg border border-white/15">
                  Cloud — Nemotron
                </span>
              </div>

              <label className="flex items-center gap-2 cursor-pointer text-neutral-300">
                <input
                  type="checkbox"
                  checked={includeLlm}
                  onChange={(e) => setIncludeLlm(e.target.checked)}
                  className="rounded bg-black border-white/20 text-white"
                />
                <span>Include AI Deep Reasoning Agent</span>
              </label>
            </div>

            <div className="flex items-center gap-3">
              {isLoading && reviewStage && (
                <div className="flex items-center gap-2 text-xs font-mono text-neutral-300">
                  <div className="w-3.5 h-3.5 border-2 border-white/20 border-t-white rounded-full animate-spin flex-shrink-0" />
                  <span className="truncate max-w-[200px]">{reviewStage}</span>
                </div>
              )}
              <button
                type="button"
                onClick={onClose}
                disabled={isLoading}
                className="px-4 py-2 text-xs font-medium text-neutral-400 hover:text-white transition-colors disabled:opacity-40"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={isLoading || isLoadingDiff}
                className="btn-silver font-medium text-xs px-5 py-2 disabled:opacity-60"
              >
                {isLoading ? "Running Review..." : "Execute Review"}
              </button>
            </div>
          </div>
        </form>
      </div>
    </div>
  );
};
