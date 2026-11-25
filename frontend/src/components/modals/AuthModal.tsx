import React, { useMemo, useState } from "react";
import type { User } from "../../types";
import { authApi } from "../../services/api";
import { evaluatePasswordStrength } from "../../utils/passwordStrength";
import { PasswordInput } from "../auth/PasswordInput";
import { PasswordStrengthMeter } from "../auth/PasswordStrengthMeter";
import { CloseIcon, GoogleIcon, LogoIcon } from "../icons/Icons";

interface AuthModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSuccess: (user: User) => void;
  notice?: string | null;
  onClearNotice?: () => void;
}

export const AuthModal: React.FC<AuthModalProps> = ({
  isOpen,
  onClose,
  onSuccess,
  notice = null,
  onClearNotice,
}) => {
  const [mode, setMode] = useState<"login" | "signup" | "reset">("login");
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [resetToken, setResetToken] = useState("");
  const [confirmResetPassword, setConfirmResetPassword] = useState("");
  const [resetRequested, setResetRequested] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [infoMessage, setInfoMessage] = useState<string | null>(null);

  const activePassword = password;
  const strengthEvaluation = useMemo(
    () => evaluatePasswordStrength(activePassword, { name, email }),
    [activePassword, name, email]
  );

  if (!isOpen) return null;

  const switchMode = (next: "login" | "signup" | "reset") => {
    setMode(next);
    setError(null);
    setInfoMessage(null);
    setPassword("");
    setConfirmResetPassword("");
    if (next !== "reset") {
      setResetRequested(false);
      setResetToken("");
    }
    if (onClearNotice) onClearNotice();
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setInfoMessage(null);

    if (mode === "signup") {
      if (!strengthEvaluation.acceptable) {
        setError(
          strengthEvaluation.warning ||
            "Your password is too weak. Try using a longer password with a combination of unpredictable words."
        );
        return;
      }
      setLoading(true);
      try {
        const res = await authApi.signup(name, email, password);
        onSuccess(res.user);
        onClose();
      } catch (err: unknown) {
        setError(err instanceof Error ? err.message : "Registration failed.");
      } finally {
        setLoading(false);
      }
      return;
    }

    if (mode === "login") {
      setLoading(true);
      try {
        const res = await authApi.login(email, password);
        onSuccess(res.user);
        onClose();
      } catch (err: unknown) {
        setError(err instanceof Error ? err.message : "Authentication failed.");
      } finally {
        setLoading(false);
      }
      return;
    }

    if (mode === "reset") {
      if (!resetRequested) {
        setLoading(true);
        try {
          const res = await authApi.requestPasswordReset(email);
          setResetRequested(true);
          setInfoMessage(res.message);
        } catch (err: unknown) {
          setError(err instanceof Error ? err.message : "Failed to initiate password reset.");
        } finally {
          setLoading(false);
        }
        return;
      }

      if (!strengthEvaluation.acceptable) {
        setError(
          strengthEvaluation.warning ||
            "Your new password is too weak. Use at least 12 unpredictable characters."
        );
        return;
      }
      if (password !== confirmResetPassword) {
        setError("Passwords do not match.");
        return;
      }

      setLoading(true);
      try {
        const res = await authApi.confirmPasswordReset(resetToken.trim(), password);
        switchMode("login");
        setInfoMessage(res.message);
      } catch (err: unknown) {
        setError(err instanceof Error ? err.message : "Failed to reset password.");
      } finally {
        setLoading(false);
      }
    }
  };

  const handleGoogleLogin = async () => {
    try {
      const res = await authApi.getGoogleAuthUrl();
      if (res.url) {
        window.location.href = res.url;
      }
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Google OAuth unavailable.");
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-md animate-fade-in text-left overflow-y-auto">
      <div className="relative w-full max-w-md rounded-2xl bg-[#0F0F0F] border border-white/20 shadow-2xl p-6 overflow-hidden my-auto">
        <div className="flex items-center justify-between pb-4 border-b border-white/10">
          <div className="flex items-center gap-2.5">
            <LogoIcon size={24} />
            <span className="font-semibold text-white tracking-wider text-sm">
              NEXARION AUTH
            </span>
          </div>
          <button
            onClick={onClose}
            className="p-1 rounded-lg text-neutral-400 hover:text-white hover:bg-white/10"
            aria-label="Close"
          >
            <CloseIcon className="w-5 h-5" />
          </button>
        </div>

        <div className="mt-4 text-center">
          <h2 className="text-xl font-semibold text-white">
            {mode === "login"
              ? "Welcome back"
              : mode === "signup"
              ? "Create developer account"
              : "Reset your password"}
          </h2>
          <p className="text-xs text-neutral-400 mt-1">
            {mode === "reset"
              ? "Verify your reset token and choose a strong new passphrase"
              : "Access your persistent multi-agent reviews and code intelligence workspace"}
          </p>
        </div>

        {(notice || infoMessage) && (
          <div className="mt-4 p-3 rounded-xl bg-emerald-500/10 border border-emerald-500/25 text-xs text-emerald-200">
            {infoMessage || notice}
          </div>
        )}

        {error && (
          <div
            role="alert"
            className="mt-4 p-3 rounded-xl bg-red-500/10 border border-red-500/25 text-xs text-red-200"
          >
            {error}
          </div>
        )}

        <form onSubmit={handleSubmit} className="mt-5 space-y-3.5">
          {mode === "signup" && (
            <div>
              <label htmlFor="auth-name" className="block text-xs font-mono text-neutral-400 mb-1">
                Full Name
              </label>
              <input
                id="auth-name"
                type="text"
                required
                value={name}
                onChange={(e) => setName(e.target.value)}
                autoComplete="name"
                className="w-full bg-black/70 border border-white/15 rounded-lg px-3 py-2 text-xs text-white focus:outline-none focus:border-white/40"
              />
            </div>
          )}

          {(!resetRequested || mode !== "reset") && (
            <div>
              <label htmlFor="auth-email" className="block text-xs font-mono text-neutral-400 mb-1">
                Email
              </label>
              <input
                id="auth-email"
                type="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                autoComplete="email"
                className="w-full bg-black/70 border border-white/15 rounded-lg px-3 py-2 text-xs text-white focus:outline-none focus:border-white/40"
              />
            </div>
          )}

          {mode === "login" && (
            <div className="space-y-1.5">
              <div className="flex items-center justify-between">
                <label htmlFor="auth-password" className="block text-xs font-mono text-neutral-400">
                  Password
                </label>
                <button
                  type="button"
                  onClick={() => switchMode("reset")}
                  className="text-[11px] font-mono text-neutral-400 hover:text-white underline transition-colors"
                >
                  Forgot password?
                </button>
              </div>
              <PasswordInput
                id="auth-password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                autoComplete="current-password"
              />
            </div>
          )}

          {mode === "signup" && (
            <div className="space-y-2">
              <PasswordInput
                id="auth-signup-password"
                label="Password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                autoComplete="new-password"
                placeholder="At least 12 unpredictable characters or words"
              />
              <PasswordStrengthMeter
                password={password}
                evaluation={strengthEvaluation}
                showRequirements={true}
              />
            </div>
          )}

          {mode === "reset" && resetRequested && (
            <div className="space-y-3">
              <div>
                <label htmlFor="reset-token" className="block text-xs font-mono text-neutral-400 mb-1">
                  Reset Token
                </label>
                <input
                  id="reset-token"
                  type="text"
                  required
                  value={resetToken}
                  onChange={(e) => setResetToken(e.target.value)}
                  placeholder="Paste your password reset token"
                  className="w-full bg-black/70 border border-white/15 rounded-lg px-3 py-2 text-xs text-white font-mono focus:outline-none focus:border-white/40"
                />
              </div>
              <PasswordInput
                id="reset-new-password"
                label="New Password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                autoComplete="new-password"
              />
              <PasswordStrengthMeter
                password={password}
                evaluation={strengthEvaluation}
                showRequirements={true}
              />
              <PasswordInput
                id="reset-confirm-password"
                label="Confirm New Password"
                required
                value={confirmResetPassword}
                onChange={(e) => setConfirmResetPassword(e.target.value)}
                autoComplete="new-password"
              />
            </div>
          )}

          <button
            type="submit"
            disabled={
              loading ||
              ((mode === "signup" || (mode === "reset" && resetRequested)) &&
                !strengthEvaluation.acceptable)
            }
            className="w-full btn-silver justify-center text-xs py-2 mt-2 disabled:opacity-40 disabled:cursor-not-allowed"
          >
            {loading
              ? "Processing..."
              : mode === "login"
              ? "Sign In"
              : mode === "signup"
              ? "Register"
              : resetRequested
              ? "Reset Password"
              : "Request Password Reset"}
          </button>

          {mode === "reset" && !resetRequested && (
            <button
              type="button"
              onClick={() => setResetRequested(true)}
              className="w-full text-center text-[11px] font-mono text-neutral-400 hover:text-white transition-colors"
            >
              Already have a reset token?
            </button>
          )}
        </form>

        {mode !== "reset" && (
          <>
            <div className="my-4 flex items-center justify-between text-neutral-500 text-xs">
              <div className="flex-1 border-t border-white/10" />
              <span className="px-3 font-mono text-[10px]">OR</span>
              <div className="flex-1 border-t border-white/10" />
            </div>

            <button
              onClick={handleGoogleLogin}
              type="button"
              className="w-full flex items-center justify-center gap-2.5 py-2 px-3 rounded-lg bg-white/5 hover:bg-white/10 border border-white/10 text-xs text-white font-medium transition-colors"
            >
              <GoogleIcon className="w-4 h-4 shrink-0" />
              <span>{mode === "login" ? "Continue with Google" : "Sign up with Google"}</span>
            </button>
          </>
        )}

        <div className="mt-5 text-center text-xs text-neutral-400">
          {mode === "login" ? (
            <span>
              Don&apos;t have an account?{" "}
              <button
                type="button"
                onClick={() => switchMode("signup")}
                className="text-white underline hover:text-neutral-200"
              >
                Sign up
              </button>
            </span>
          ) : mode === "signup" ? (
            <span>
              Already have an account?{" "}
              <button
                type="button"
                onClick={() => switchMode("login")}
                className="text-white underline hover:text-neutral-200"
              >
                Sign in
              </button>
            </span>
          ) : (
            <span>
              Remembered your password?{" "}
              <button
                type="button"
                onClick={() => switchMode("login")}
                className="text-white underline hover:text-neutral-200"
              >
                Back to Sign in
              </button>
            </span>
          )}
        </div>
      </div>
    </div>
  );
};
