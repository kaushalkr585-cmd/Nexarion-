import React, { useEffect, useState } from "react";
import type { GitHubPullRequest, GitHubRepo, GitHubStatus, Review } from "../../types";
import { githubApi } from "../../services/api";

interface GitHubPrPickerModalProps {
  isOpen: boolean;
  onClose: () => void;
  onAttachDiff: (diffText: string, title: string) => void;
  onReviewCreated: (review: Review) => void;
  onOpenSettings: () => void;
}

export const GitHubPrPickerModal: React.FC<GitHubPrPickerModalProps> = ({
  isOpen,
  onClose,
  onAttachDiff,
  onReviewCreated,
  onOpenSettings,
}) => {
  const [status, setStatus] = useState<GitHubStatus | null>(null);
  const [isLoadingStatus, setIsLoadingStatus] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const [personalToken, setPersonalToken] = useState("");
  const [isConnectingToken, setIsConnectingToken] = useState(false);

  const [repos, setRepos] = useState<GitHubRepo[]>([]);
  const [isLoadingRepos, setIsLoadingRepos] = useState(false);
  const [repoSearch, setRepoSearch] = useState("");
  const [selectedRepo, setSelectedRepo] = useState<GitHubRepo | null>(null);

  const [pulls, setPulls] = useState<GitHubPullRequest[]>([]);
  const [isLoadingPulls, setIsLoadingPulls] = useState(false);

  const [isAttachingDiff, setIsAttachingDiff] = useState<number | null>(null);
  const [isStartingReview, setIsStartingReview] = useState<number | null>(null);

  useEffect(() => {
    if (isOpen) {
      loadStatus();
    } else {
      setSelectedRepo(null);
      setPulls([]);
      setErrorMessage(null);
    }
  }, [isOpen]);

  const loadStatus = async () => {
    setIsLoadingStatus(true);
    setErrorMessage(null);
    try {
      const res = await githubApi.getStatus();
      setStatus(res);
      if (res.connected) {
        loadRepos();
      }
    } catch (err) {
      setErrorMessage(err instanceof Error ? err.message : "Failed to load GitHub status.");
    } finally {
      setIsLoadingStatus(false);
    }
  };

  const loadRepos = async () => {
    setIsLoadingRepos(true);
    setErrorMessage(null);
    try {
      const repoList = await githubApi.listRepos();
      setRepos(repoList);
    } catch (err) {
      setErrorMessage(err instanceof Error ? err.message : "Failed to load repositories.");
    } finally {
      setIsLoadingRepos(false);
    }
  };

  const handleSelectRepo = async (repo: GitHubRepo) => {
    setSelectedRepo(repo);
    setIsLoadingPulls(true);
    setErrorMessage(null);
    try {
      const prList = await githubApi.listPulls(repo.owner, repo.name);
      setPulls(prList);
    } catch (err) {
      setErrorMessage(err instanceof Error ? err.message : "Failed to load pull requests.");
    } finally {
      setIsLoadingPulls(false);
    }
  };

  const handleConnectOAuth = async () => {
    try {
      const { url } = await githubApi.getAuthUrl();
      if (url) {
        window.location.href = url;
      } else {
        setErrorMessage("GitHub OAuth client ID is not configured. Connect using a token below.");
      }
    } catch (err) {
      setErrorMessage(err instanceof Error ? err.message : "Failed to generate OAuth URL.");
    }
  };

  const handleConnectToken = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!personalToken.trim()) return;

    setIsConnectingToken(true);
    setErrorMessage(null);
    try {
      const updated = await githubApi.connect(personalToken.trim());
      setStatus(updated);
      setPersonalToken("");
      await loadRepos();
    } catch (err) {
      setErrorMessage(err instanceof Error ? err.message : "Failed to connect token.");
    } finally {
      setIsConnectingToken(false);
    }
  };

  const handleDisconnect = async () => {
    try {
      const updated = await githubApi.disconnect();
      setStatus(updated);
      setRepos([]);
      setSelectedRepo(null);
      setPulls([]);
    } catch (err) {
      setErrorMessage(err instanceof Error ? err.message : "Failed to disconnect.");
    }
  };

  const handleAttachDiff = async (pr: GitHubPullRequest) => {
    if (!selectedRepo) return;
    setIsAttachingDiff(pr.number);
    setErrorMessage(null);
    try {
      const data = await githubApi.getDiff(selectedRepo.owner, selectedRepo.name, pr.number);
      onAttachDiff(data.diff, `PR #${pr.number}: ${pr.title}`);
      onClose();
    } catch (err) {
      setErrorMessage(err instanceof Error ? err.message : "Failed to retrieve PR diff.");
    } finally {
      setIsAttachingDiff(null);
    }
  };

  const handleRunReview = async (pr: GitHubPullRequest) => {
    if (!selectedRepo) return;
    setIsStartingReview(pr.number);
    setErrorMessage(null);
    try {
      const review = await githubApi.reviewPullRequest(
        selectedRepo.owner,
        selectedRepo.name,
        pr.number
      );
      onReviewCreated(review);
      onClose();
    } catch (err) {
      setErrorMessage(err instanceof Error ? err.message : "Failed to run review.");
    } finally {
      setIsStartingReview(null);
    }
  };

  if (!isOpen) return null;

  const filteredRepos = repos.filter((r) =>
    r.full_name.toLowerCase().includes(repoSearch.toLowerCase())
  );

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-md animate-fade-in text-left">
      <div className="glass-panel w-full max-w-2xl rounded-2xl overflow-hidden border border-white/20 shadow-2xl bg-[#0c0c0c] flex flex-col max-h-[85vh]">

        <div className="flex items-center justify-between p-5 border-b border-white/10">
          <div className="flex items-center gap-2.5">
            <div className="p-2 rounded-xl bg-white/5 border border-white/10 text-white">
              <svg className="w-5 h-5" viewBox="0 0 16 16" fill="currentColor">
                <path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.012 8.012 0 0 0 16 8c0-4.42-3.58-8-8-8z" />
              </svg>
            </div>
            <div>
              <h2 className="text-base font-semibold text-white">GitHub Pull Request Review</h2>
              <p className="text-xs text-neutral-400">
                {status?.connected
                  ? `Connected as @${status.username || "developer"}`
                  : "Connect repository to inspect pull requests"}
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 text-neutral-400 hover:text-white rounded-lg hover:bg-white/10"
            aria-label="Close"
          >
            ✕
          </button>
        </div>

        {errorMessage && (
          <div className="mx-5 mt-4 p-3 rounded-xl bg-red-500/10 border border-red-500/20 text-xs text-red-200">
            {errorMessage}
          </div>
        )}

        <div className="p-5 overflow-y-auto flex-1 space-y-4">
          {isLoadingStatus ? (
            <div className="py-12 text-center text-xs text-neutral-400 font-mono">
              Checking GitHub connection...
            </div>
          ) : !status?.connected ? (

            <div className="space-y-5 py-3">
              <div className="p-4 rounded-xl bg-white/[0.03] border border-white/10 text-xs text-neutral-300 leading-relaxed">
                Connect your GitHub account to directly pull authorized pull requests and run
                NEXARION&apos;s multi-agent code analysis pipeline (Security, Quality, AST,
                Performance).
              </div>

              {status?.configured && (
                <button
                  type="button"
                  onClick={handleConnectOAuth}
                  className="w-full btn-silver py-2.5 text-xs flex items-center justify-center gap-2"
                >
                  <span>Connect via GitHub OAuth</span>
                </button>
              )}

              <div className="relative flex py-2 items-center">
                <div className="flex-grow border-t border-white/10" />
                <span className="flex-shrink mx-4 text-[10px] text-neutral-500 font-mono uppercase">
                  Or Connect with Personal Token
                </span>
                <div className="flex-grow border-t border-white/10" />
              </div>

              <form onSubmit={handleConnectToken} className="space-y-3">
                <div>
                  <label className="block text-xs font-mono text-neutral-400 mb-1">
                    GitHub Access Token (repo scope)
                  </label>
                  <input
                    type="password"
                    placeholder="ghp_xxxxxxxxxxxxxxxxxxxx"
                    value={personalToken}
                    onChange={(e) => setPersonalToken(e.target.value)}
                    className="w-full bg-black/60 border border-white/15 rounded-lg px-3 py-2 text-xs text-white placeholder-neutral-600 font-mono focus:outline-none focus:border-white/40"
                  />
                  <div className="text-[10px] text-neutral-500 mt-1">
                    Token is transmitted securely to backend and never exposed to other clients.
                  </div>
                </div>

                <div className="flex items-center gap-3">
                  <button
                    type="submit"
                    disabled={!personalToken.trim() || isConnectingToken}
                    className="btn-silver py-2 px-4 text-xs"
                  >
                    {isConnectingToken ? "Validating Token..." : "Connect Token"}
                  </button>
                  <button
                    type="button"
                    onClick={() => {
                      onClose();
                      onOpenSettings();
                    }}
                    className="text-xs text-neutral-400 hover:text-white"
                  >
                    Open Settings Checklist →
                  </button>
                </div>
              </form>
            </div>
          ) : selectedRepo ? (

            <div className="space-y-4">
              <div className="flex items-center justify-between pb-3 border-b border-white/10">
                <button
                  type="button"
                  onClick={() => setSelectedRepo(null)}
                  className="text-xs text-neutral-400 hover:text-white flex items-center gap-1 font-mono"
                >
                  ← Back to Repositories
                </button>
                <div className="text-xs font-semibold text-white font-mono">
                  {selectedRepo.full_name}
                </div>
              </div>

              {isLoadingPulls ? (
                <div className="py-12 text-center text-xs text-neutral-400 font-mono">
                  Loading pull requests from GitHub...
                </div>
              ) : pulls.length === 0 ? (
                <div className="py-12 text-center space-y-2">
                  <div className="text-sm font-semibold text-white">No pull requests found</div>
                  <p className="text-xs text-neutral-400">
                    This repository has no open pull requests right now.
                  </p>
                </div>
              ) : (
                <div className="space-y-2.5">
                  {pulls.map((pr) => (
                    <div
                      key={pr.number}
                      className="p-3.5 rounded-xl bg-white/[0.03] border border-white/10 space-y-2.5 hover:border-white/20 transition-all"
                    >
                      <div className="flex items-start justify-between gap-3">
                        <div className="min-w-0">
                          <div className="flex items-center gap-2">
                            <span className="text-xs font-mono text-white font-semibold">
                              #{pr.number}
                            </span>
                            <span className="text-xs font-semibold text-white truncate">
                              {pr.title}
                            </span>
                          </div>
                          <div className="flex items-center gap-2 text-[10px] text-neutral-400 font-mono mt-1">
                            <span>Author: @{pr.author}</span>
                            <span>•</span>
                            <span className="px-1.5 py-0.5 rounded bg-white/5 border border-white/10">
                              {pr.head_branch} → {pr.base_branch}
                            </span>
                          </div>
                        </div>

                        <span className="text-[10px] px-2 py-0.5 rounded font-mono uppercase bg-neutral-800 text-neutral-300 border border-neutral-700">
                          {pr.state}
                        </span>
                      </div>

                      <div className="flex items-center gap-2 pt-1 border-t border-white/5">
                        <button
                          type="button"
                          onClick={() => handleAttachDiff(pr)}
                          disabled={isAttachingDiff === pr.number || isStartingReview === pr.number}
                          className="py-1.5 px-3 rounded-lg bg-white/5 hover:bg-white/10 text-neutral-300 hover:text-white border border-white/10 text-xs font-medium transition-colors"
                        >
                          {isAttachingDiff === pr.number ? "Retrieving Diff..." : "Attach Diff to Chat"}
                        </button>
                        <button
                          type="button"
                          onClick={() => handleRunReview(pr)}
                          disabled={isAttachingDiff === pr.number || isStartingReview === pr.number}
                          className="btn-silver py-1.5 px-3 text-xs"
                        >
                          {isStartingReview === pr.number ? "Running AI Agents..." : "Run AI Review"}
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          ) : (

            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <input
                  type="text"
                  placeholder="Filter repositories..."
                  value={repoSearch}
                  onChange={(e) => setRepoSearch(e.target.value)}
                  className="w-full bg-black/60 border border-white/15 rounded-xl px-3.5 py-2 text-xs text-white placeholder-neutral-500 font-mono focus:outline-none focus:border-white/35"
                />
              </div>

              {isLoadingRepos ? (
                <div className="py-12 text-center text-xs text-neutral-400 font-mono">
                  Loading authorized repositories...
                </div>
              ) : filteredRepos.length === 0 ? (
                <div className="py-12 text-center text-xs text-neutral-500 font-mono">
                  No repositories found matching your filter.
                </div>
              ) : (
                <div className="space-y-2 max-h-80 overflow-y-auto">
                  {filteredRepos.map((repo) => (
                    <div
                      key={repo.id}
                      onClick={() => handleSelectRepo(repo)}
                      className="p-3 rounded-xl bg-white/[0.02] hover:bg-white/[0.06] border border-white/10 flex items-center justify-between cursor-pointer transition-colors"
                    >
                      <div className="min-w-0">
                        <div className="text-xs font-semibold text-white font-mono truncate">
                          {repo.full_name}
                        </div>
                        {repo.description && (
                          <div className="text-[11px] text-neutral-400 truncate mt-0.5">
                            {repo.description}
                          </div>
                        )}
                      </div>
                      <div className="flex items-center gap-2 flex-shrink-0 ml-3">
                        <span className="text-[10px] px-1.5 py-0.5 rounded font-mono bg-white/5 text-neutral-400">
                          {repo.private ? "Private" : "Public"}
                        </span>
                        <span className="text-neutral-400 text-xs">→</span>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>

        {status?.connected && (
          <div className="p-4 border-t border-white/10 bg-black/40 flex items-center justify-between text-xs">
            <span className="text-neutral-500 font-mono">
              Authorized via GitHub {status.auth_type.toUpperCase()}
            </span>
            <button
              onClick={handleDisconnect}
              className="text-neutral-400 hover:text-red-400 text-xs transition-colors"
            >
              Disconnect GitHub
            </button>
          </div>
        )}
      </div>
    </div>
  );
};
