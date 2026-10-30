import React, { useState } from "react";
import type { User } from "../../types";
import { authApi } from "../../services/api";
import { CloseIcon, LogoIcon } from "../icons/Icons";

interface AuthModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSuccess: (user: User) => void;
}

export const AuthModal: React.FC<AuthModalProps> = ({ isOpen, onClose, onSuccess }) => {
  const [mode, setMode] = useState<"login" | "signup">("login");
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!isOpen) return null;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError(null);

    try {
      if (mode === "login") {
        const res = await authApi.login(email, password);
        onSuccess(res.user);
      } else {
        const res = await authApi.signup(name, email, password);
        onSuccess(res.user);
      }
      onClose();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Authentication failed.");
    } finally {
      setLoading(false);
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
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-md animate-fade-in text-left">
      <div className="relative w-full max-w-md rounded-2xl bg-[#0F0F0F] border border-white/20 shadow-2xl p-6 overflow-hidden">
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
            {mode === "login" ? "Welcome back" : "Create developer account"}
          </h2>
          <p className="text-xs text-neutral-400 mt-1">
            Access your persistent multi-agent reviews and code intelligence workspace
          </p>
        </div>

        {error && (
          <div className="mt-4 p-3 rounded-xl bg-red-500/10 border border-red-500/20 text-xs text-neutral-300">
            {error}
          </div>
        )}

        <form onSubmit={handleSubmit} className="mt-5 space-y-3.5">
          {mode === "signup" && (
            <div>
              <label className="block text-xs font-mono text-neutral-400 mb-1">Full Name</label>
              <input
                type="text"
                required
                value={name}
                onChange={(e) => setName(e.target.value)}
                className="w-full bg-black/70 border border-white/15 rounded-lg px-3 py-2 text-xs text-white focus:outline-none focus:border-white/40"
              />
            </div>
          )}

          <div>
            <label className="block text-xs font-mono text-neutral-400 mb-1">Email</label>
            <input
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="w-full bg-black/70 border border-white/15 rounded-lg px-3 py-2 text-xs text-white focus:outline-none focus:border-white/40"
            />
          </div>

          <div>
            <label className="block text-xs font-mono text-neutral-400 mb-1">Password</label>
            <input
              type="password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full bg-black/70 border border-white/15 rounded-lg px-3 py-2 text-xs text-white focus:outline-none focus:border-white/40"
            />
          </div>

          <button
            type="submit"
            disabled={loading}
            className="w-full btn-silver justify-center text-xs py-2 mt-2"
          >
            {loading ? "Authenticating..." : mode === "login" ? "Sign In" : "Register"}
          </button>
        </form>

        <div className="my-4 flex items-center justify-between text-neutral-500 text-xs">
          <div className="flex-1 border-t border-white/10" />
          <span className="px-3 font-mono text-[10px]">OR</span>
          <div className="flex-1 border-t border-white/10" />
        </div>

        <button
          onClick={handleGoogleLogin}
          type="button"
          className="w-full flex items-center justify-center gap-2 p-2 rounded-lg bg-white/5 hover:bg-white/10 border border-white/10 text-xs text-white font-medium transition-colors"
        >
          <span>Continue with Google</span>
        </button>

        <div className="mt-5 text-center text-xs text-neutral-400">
          {mode === "login" ? (
            <span>
              Don&apos;t have an account?{" "}
              <button
                type="button"
                onClick={() => setMode("signup")}
                className="text-white underline hover:text-neutral-200"
              >
                Sign up
              </button>
            </span>
          ) : (
            <span>
              Already have an account?{" "}
              <button
                type="button"
                onClick={() => setMode("login")}
                className="text-white underline hover:text-neutral-200"
              >
                Sign in
              </button>
            </span>
          )}
        </div>
      </div>
    </div>
  );
};
