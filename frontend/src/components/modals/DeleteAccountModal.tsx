import React, { useEffect, useState } from "react";
import type { User } from "../../types";
import { authApi, githubApi, userApi } from "../../services/api";
import { PasswordInput } from "../auth/PasswordInput";
import { CloseIcon, GithubIcon, GoogleIcon } from "../icons/Icons";

interface DeleteAccountModalProps {
  isOpen: boolean;
  user: User;
  initialReauthToken?: string | null;
  initialReauthError?: string | null;
  onClose: () => void;
  onAccountDeleted: () => void;
}

export const DeleteAccountModal: React.FC<DeleteAccountModalProps> = ({
  isOpen,
  user,
  initialReauthToken = null,
  initialReauthError = null,
  onClose,
  onAccountDeleted,
}) => {
  const [step, setStep] = useState<"verify" | "final">("verify");
  const [confirmText, setConfirmText] = useState("");
  const [password, setPassword] = useState("");
  const [githubPat, setGithubPat] = useState("");
  const [showPatFallback, setShowPatFallback] = useState(false);
  const [reauthToken, setReauthToken] = useState<string | null>(initialReauthToken);
  const [isVerifying, setIsVerifying] = useState(false);
  const [isDeleting, setIsDeleting] = useState(false);
  const [error, setError] = useState<string | null>(initialReauthError);

  useEffect(() => {
    if (initialReauthToken) {
      setReauthToken(initialReauthToken);
      setError(null);
    }
  }, [initialReauthToken]);

  useEffect(() => {
    if (initialReauthError) {
      setError(initialReauthError);
    }
  }, [initialReauthError]);

  if (!isOpen) return null;

  const hasPasswordAuth = Boolean(user.has_password);
  const hasGoogleAuth = Boolean(user.google_linked || user.auth_provider === "google");
  const hasGithubAuth = Boolean(user.github_connected);

  const isConfirmedTyped = confirmText.trim() === "DELETE";

  const handlePasswordReauth = async () => {
    if (!password) {
      setError("Please enter your current password to verify your identity.");
      return;
    }
    setIsVerifying(true);
    setError(null);
    try {
      const res = await authApi.reauthWithPassword(password);
      setReauthToken(res.reauth_token);
      setPassword("");
      setStep("final");
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Password verification failed.");
    } finally {
      setIsVerifying(false);
    }
  };

  const handleGoogleReauth = async () => {
    setIsVerifying(true);
    setError(null);
    try {
      const res = await authApi.getGoogleAuthUrl(window.location.origin, "reauth_delete");
      if (res.url) {
        window.location.href = res.url;
        return;
      }
      setError("Google OAuth re-authentication is not configured on this server.");
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to start Google re-authentication.");
    } finally {
      setIsVerifying(false);
    }
  };

  const handleGithubReauth = async () => {
    setIsVerifying(true);
    setError(null);
    try {
      const res = await githubApi.getReauthUrl(window.location.origin);
      if (res.url) {
        window.location.href = res.url;
        return;
      }
      setShowPatFallback(true);
      setError(
        "GitHub OAuth is not configured on the server. Enter your connected GitHub Personal Access Token below to verify identity."
      );
    } catch (err: unknown) {
      setShowPatFallback(true);
      setError(err instanceof Error ? err.message : "Failed to start GitHub re-authentication.");
    } finally {
      setIsVerifying(false);
    }
  };

  const handleProceedToFinal = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    if (!isConfirmedTyped) {
      setError("Please type DELETE in all caps to confirm.");
      return;
    }

    if (reauthToken || (showPatFallback && githubPat.trim())) {
      setStep("final");
      return;
    }

    if (hasPasswordAuth && password) {
      await handlePasswordReauth();
      return;
    }

    setError("Please complete identity verification above before continuing.");
  };

  const handleFinalDelete = async () => {
    if (!isConfirmedTyped) {
      setError("Confirmation text must be DELETE.");
      setStep("verify");
      return;
    }
    setIsDeleting(true);
    setError(null);
    try {
      await userApi.deleteAccount({
        confirmation_text: "DELETE",
        reauth_token: reauthToken || undefined,
        github_pat: !reauthToken && githubPat.trim() ? githubPat.trim() : undefined,
      });
      onAccountDeleted();
    } catch (err: unknown) {
      setError(
        err instanceof Error
          ? err.message
          : "Account deletion failed. Your account was not deleted — you may safely retry."
      );
    } finally {
      setIsDeleting(false);
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/85 backdrop-blur-md animate-fade-in text-left overflow-y-auto"
      role="dialog"
      aria-modal="true"
      aria-labelledby="delete-account-modal-title"
    >
      <div className="relative w-full max-w-lg rounded-2xl bg-[#0F0F0F] border border-red-500/35 shadow-2xl p-6 overflow-hidden my-auto">
        <div className="flex items-center justify-between pb-4 border-b border-white/10">
          <div className="flex items-center gap-2.5">
            <span className="w-2.5 h-2.5 rounded-full bg-red-500 shrink-0" />
            <h2 id="delete-account-modal-title" className="text-base font-semibold text-white">
              {step === "verify" ? "Delete Nexarion Account" : "Final Confirmation Required"}
            </h2>
          </div>
          <button
            type="button"
            disabled={isDeleting}
            onClick={onClose}
            aria-label="Close delete account modal"
            className="p-1 rounded-lg text-neutral-400 hover:text-white hover:bg-white/10 disabled:opacity-40"
          >
            <CloseIcon className="w-5 h-5" />
          </button>
        </div>

        {error && (
          <div
            role="alert"
            className="mt-4 p-3 rounded-xl bg-red-500/15 border border-red-500/30 text-xs text-red-200 leading-relaxed"
          >
            {error}
          </div>
        )}

        {step === "verify" ? (
          <form onSubmit={handleProceedToFinal} className="mt-4 space-y-4">
            <div className="p-3.5 rounded-xl bg-red-950/30 border border-red-500/25 space-y-2">
              <p className="text-xs font-semibold text-red-200">
                This action is permanent and cannot be undone.
              </p>
              <p className="text-xs text-neutral-300 leading-relaxed">
                Deleting <span className="font-mono text-white">{user.email}</span> will immediately
                and irreversibly remove:
              </p>
              <ul className="list-disc pl-4 space-y-1 text-[11px] text-neutral-400">
                <li>Your user profile, saved preferences, and authentication credentials</li>
                <li>All AI conversations, chat history, memory records, and uploaded documents</li>
                <li>All code review history, findings, and repository metadata owned by you</li>
                <li>Stored GitHub OAuth grants, Personal Access Tokens, and all active sessions</li>
              </ul>
            </div>

            <div>
              <label
                htmlFor="delete-confirm-text"
                className="block text-xs font-mono text-neutral-300 mb-1.5"
              >
                Type <span className="text-red-300 font-bold">DELETE</span> to confirm
              </label>
              <input
                id="delete-confirm-text"
                type="text"
                value={confirmText}
                onChange={(e) => setConfirmText(e.target.value)}
                placeholder="DELETE"
                autoComplete="off"
                className="w-full bg-black/70 border border-white/15 rounded-lg px-3 py-2 text-xs text-white font-mono focus:outline-none focus:border-red-400/60"
              />
            </div>

            <div className="pt-2 border-t border-white/10 space-y-3">
              <div className="flex items-center justify-between">
                <span className="text-xs font-mono text-neutral-300">
                  Identity Re-authentication
                </span>
                {reauthToken && (
                  <span className="text-[11px] font-mono px-2 py-0.5 rounded-full bg-emerald-500/15 text-emerald-300 border border-emerald-500/30">
                    Verified
                  </span>
                )}
              </div>

              {reauthToken ? (
                <div className="p-3 rounded-xl bg-emerald-500/10 border border-emerald-500/20 text-xs text-emerald-200">
                  Your identity has been re-verified. Review &quot;Continue to Final Confirmation&quot; below.
                </div>
              ) : (
                <div className="space-y-3">
                  {hasPasswordAuth && (
                    <div className="space-y-2">
                      <PasswordInput
                        id="delete-reauth-password"
                        label="Enter your current password"
                        value={password}
                        onChange={(e) => setPassword(e.target.value)}
                        autoComplete="current-password"
                        placeholder="Enter current password"
                      />
                    </div>
                  )}

                  {(hasGoogleAuth || hasGithubAuth) && (
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
                      {hasGoogleAuth && (
                        <button
                          type="button"
                          disabled={isVerifying}
                          onClick={handleGoogleReauth}
                          className="flex items-center justify-center gap-2 py-2 px-3 rounded-lg bg-white/5 hover:bg-white/10 border border-white/15 text-xs text-white font-medium transition-colors cursor-pointer disabled:opacity-50"
                        >
                          <GoogleIcon className="w-4 h-4 shrink-0" />
                          <span>Verify with Google</span>
                        </button>
                      )}
                      {hasGithubAuth && (
                        <button
                          type="button"
                          disabled={isVerifying}
                          onClick={handleGithubReauth}
                          className="flex items-center justify-center gap-2 py-2 px-3 rounded-lg bg-white/5 hover:bg-white/10 border border-white/15 text-xs text-white font-medium transition-colors cursor-pointer disabled:opacity-50"
                        >
                          <GithubIcon className="w-4 h-4 shrink-0" />
                          <span>Verify with GitHub</span>
                        </button>
                      )}
                    </div>
                  )}

                  {(showPatFallback || (!hasPasswordAuth && !hasGoogleAuth && hasGithubAuth)) && (
                    <div className="space-y-1.5">
                      <PasswordInput
                        id="delete-reauth-pat"
                        label="Or verify using your connected GitHub Personal Access Token"
                        value={githubPat}
                        onChange={(e) => setGithubPat(e.target.value)}
                        placeholder="ghp_xxxxxxxxxxxx"
                      />
                    </div>
                  )}
                </div>
              )}
            </div>

            <div className="flex items-center justify-end gap-2.5 pt-3 border-t border-white/10">
              <button
                type="button"
                onClick={onClose}
                className="px-4 py-2 rounded-lg text-xs font-medium text-neutral-300 hover:text-white hover:bg-white/10 transition-colors"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={
                  isVerifying ||
                  !isConfirmedTyped ||
                  (!reauthToken && !password && !githubPat.trim())
                }
                className="px-4 py-2 rounded-lg text-xs font-semibold bg-red-600/90 hover:bg-red-500 text-white transition-colors disabled:opacity-40 disabled:cursor-not-allowed cursor-pointer"
              >
                {isVerifying ? "Verifying..." : "Continue to Final Confirmation"}
              </button>
            </div>
          </form>
        ) : (
          <div className="mt-4 space-y-4">
            <div className="p-4 rounded-xl bg-red-950/35 border border-red-500/35 space-y-2">
              <div className="text-sm font-semibold text-red-200">
                Permanent Deletion — Final Check
              </div>
              <p className="text-xs text-neutral-300 leading-relaxed">
                You are about to permanently delete{" "}
                <span className="font-mono text-white">{user.email}</span>. Every session will be
                invalidated immediately and no account data can be recovered.
              </p>
            </div>

            <div className="flex items-center justify-between gap-3 pt-2">
              <button
                type="button"
                disabled={isDeleting}
                onClick={() => setStep("verify")}
                className="px-4 py-2 rounded-lg text-xs font-medium text-neutral-300 hover:text-white hover:bg-white/10 transition-colors disabled:opacity-40"
              >
                Back
              </button>
              <button
                type="button"
                disabled={isDeleting}
                onClick={handleFinalDelete}
                data-testid="confirm-permanent-delete-btn"
                className="px-4 py-2 rounded-lg text-xs font-semibold bg-red-600 hover:bg-red-500 text-white transition-colors disabled:opacity-50 cursor-pointer"
              >
                {isDeleting ? "Deleting Account..." : "Permanently Delete Account"}
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};
