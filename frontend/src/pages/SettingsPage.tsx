import React, { useEffect, useState } from "react";
import type { GitHubStatus, User } from "../types";
import { githubApi, userApi } from "../services/api";
import { UserIcon } from "../components/icons/Icons";

interface SettingsPageProps {
  user: User | null;
  onUserUpdated: (user: User) => void;
}

export const SettingsPage: React.FC<SettingsPageProps> = React.memo(({
  user,
  onUserUpdated,
}) => {
  const [name, setName] = useState(user?.name || "Developer");
  const [email, setEmail] = useState(user?.email || "");
  const [isUpdatingUser, setIsUpdatingUser] = useState(false);
  const [userMsg, setUserMsg] = useState<string | null>(null);
  const [userMsgType, setUserMsgType] = useState<"success" | "error">("success");

  const [avatarUploading, setAvatarUploading] = useState(false);

  const [ghStatus, setGhStatus] = useState<GitHubStatus | null>(null);
  const [isLoadingGh, setIsLoadingGh] = useState(false);
  const [ghTokenInput, setGhTokenInput] = useState("");
  const [isConnectingGhToken, setIsConnectingGhToken] = useState(false);
  const [ghActionMsg, setGhActionMsg] = useState<string | null>(null);

  useEffect(() => {
    if (user?.name) {
      setName(user.name);
    }
    if (user?.email) {
      setEmail(user.email);
    }
  }, [user?.name, user?.email]);

  useEffect(() => {
    loadGitHubStatus();
  }, []);

  const loadGitHubStatus = async () => {
    setIsLoadingGh(true);
    try {
      const status = await githubApi.getStatus();
      setGhStatus(status);
    } catch {

    } finally {
      setIsLoadingGh(false);
    }
  };

  const isValidEmail = (value: string): boolean => {
    return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value.trim());
  };

  const handleUpdateProfile = async (e: React.FormEvent) => {
    e.preventDefault();
    setUserMsg(null);

    const trimmedEmail = email.trim().toLowerCase();
    const trimmedName = name.trim();

    if (trimmedEmail && !isValidEmail(trimmedEmail)) {
      setUserMsg("Please enter a valid email address.");
      setUserMsgType("error");
      return;
    }

    if (!trimmedName) {
      setUserMsg("Display name cannot be empty.");
      setUserMsgType("error");
      return;
    }

    setIsUpdatingUser(true);
    try {
      const updates: Record<string, string> = { name: trimmedName };
      if (trimmedEmail && trimmedEmail !== user?.email) {
        updates.email = trimmedEmail;
      }
      const updated = await userApi.updateProfile(updates);
      onUserUpdated(updated);
      setUserMsg("Profile updated successfully.");
      setUserMsgType("success");
    } catch (err: unknown) {
      setUserMsg(err instanceof Error ? err.message : "Failed to update profile.");
      setUserMsgType("error");
    } finally {
      setIsUpdatingUser(false);
    }
  };

  const handleAvatarChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    const validTypes = ["image/png", "image/jpeg", "image/webp"];
    if (!validTypes.includes(file.type)) {
      setUserMsg("Please select a valid PNG, JPEG, or WebP image.");
      e.target.value = "";
      return;
    }
    if (file.size > 5 * 1024 * 1024) {
      setUserMsg("File size must not exceed 5MB.");
      e.target.value = "";
      return;
    }

    setAvatarUploading(true);
    setUserMsg(null);
    try {
      const updated = await userApi.uploadAvatar(file);
      onUserUpdated(updated);
      setUserMsg("Avatar updated successfully.");
    } catch (err: unknown) {
      setUserMsg(err instanceof Error ? err.message : "Failed to upload avatar.");
    } finally {
      setAvatarUploading(false);
      e.target.value = "";
    }
  };

  const handleConnectGitHubOAuth = async () => {
    try {
      const { url } = await githubApi.getAuthUrl();
      if (url) {
        window.location.href = url;
      } else {
        setGhActionMsg("GitHub OAuth Client ID is not configured in backend environment.");
      }
    } catch (err) {
      setGhActionMsg(err instanceof Error ? err.message : "Failed to generate authorization URL.");
    }
  };

  const handleConnectGitHubToken = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!ghTokenInput.trim()) return;

    setIsConnectingGhToken(true);
    setGhActionMsg(null);
    try {
      const updated = await githubApi.connect(ghTokenInput.trim());
      setGhStatus(updated);
      setGhTokenInput("");
      setGhActionMsg("GitHub connected successfully.");
      if (user) {
        onUserUpdated({
          ...user,
          github_connected: true,
          github_username: updated.username,
        });
      }
    } catch (err) {
      setGhActionMsg(err instanceof Error ? err.message : "Failed to connect token.");
    } finally {
      setIsConnectingGhToken(false);
    }
  };

  const handleDisconnectGitHub = async () => {
    setIsLoadingGh(true);
    setGhActionMsg(null);
    try {
      const updated = await githubApi.disconnect();
      setGhStatus(updated);
      setGhActionMsg("GitHub disconnected successfully.");
      if (user) {
        onUserUpdated({
          ...user,
          github_connected: false,
          github_username: null,
        });
      }
    } catch (err) {
      setGhActionMsg(err instanceof Error ? err.message : "Failed to disconnect.");
    } finally {
      setIsLoadingGh(false);
    }
  };

  return (
    <div className="max-w-4xl mx-auto px-6 py-8 space-y-8 relative z-10 text-left">
      <div className="pb-6 border-b border-white/10">
        <h1 className="text-2xl sm:text-3xl font-semibold text-white tracking-tight">
          System & Account Settings
        </h1>
        <p className="text-xs sm:text-sm text-neutral-400 mt-1">
          Configure AI inference engines, GitHub pull-request integrations, and developer profile
        </p>
      </div>

      {userMsg && (
        <div className={`p-3.5 rounded-xl text-xs ${
          userMsgType === "error"
            ? "bg-red-500/10 border border-red-500/20 text-red-300"
            : "bg-emerald-500/10 border border-emerald-500/20 text-emerald-300"
        }`}>
          {userMsg}
        </div>
      )}

      <div className="glass-panel p-6 rounded-2xl space-y-5">
        <div className="flex items-center gap-3">
          <div className="p-2 rounded-xl bg-white/5 text-white">
            <UserIcon className="w-5 h-5" />
          </div>
          <div>
            <h2 className="text-sm font-semibold text-white">Developer Profile</h2>
            <p className="text-xs text-neutral-400">
              Account identity, authentication, and profile image
            </p>
          </div>
        </div>

        <div className="flex flex-col sm:flex-row items-start sm:items-center gap-6 pb-4 border-b border-white/10">
          <div className="relative">
            {user?.avatar_url ? (
              <img
                src={user.avatar_url}
                alt={user.name}
                className="w-16 h-16 rounded-full object-cover border-2 border-white/20"
                onError={(e) => {
                  (e.currentTarget as HTMLElement).style.display = "none";
                  const fallback = e.currentTarget.parentElement?.querySelector(".avatar-fallback");
                  if (fallback) (fallback as HTMLElement).classList.remove("hidden");
                }}
              />
            ) : null}
            <div
              className={`avatar-fallback w-16 h-16 rounded-full bg-neutral-800 border-2 border-white/20 items-center justify-center text-lg font-bold text-white ${
                user?.avatar_url ? "hidden" : "flex"
              }`}
            >
              {user?.name ? user.name.charAt(0).toUpperCase() : "U"}
            </div>
          </div>

          <div className="space-y-1.5">
            <label className="btn-silver text-xs py-1.5 px-3 cursor-pointer inline-flex items-center">
              <span>{avatarUploading ? "Uploading..." : "Change Avatar"}</span>
              <input
                type="file"
                accept="image/png,image/jpeg,image/webp"
                onChange={handleAvatarChange}
                disabled={avatarUploading}
                className="hidden"
              />
            </label>
            <div className="text-[11px] text-neutral-500 font-mono">
              Supports PNG, JPEG, and WebP up to 5MB
            </div>
          </div>
        </div>

        <form onSubmit={handleUpdateProfile} className="space-y-4 max-w-md">
          <div>
            <label className="block text-xs font-mono text-neutral-400 mb-1">Display Name</label>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="w-full bg-black/60 border border-white/15 rounded-lg px-3 py-2 text-xs text-white focus:outline-none focus:border-white/40"
            />
          </div>

          <div>
            <label className="block text-xs font-mono text-neutral-400 mb-1">Email Address</label>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="you@example.com"
              className="w-full bg-black/60 border border-white/15 rounded-lg px-3 py-2 text-xs text-white focus:outline-none focus:border-white/40 font-mono"
            />
            {user?.auth_provider === "google" && (
              <p className="text-[10px] text-neutral-500 mt-1 font-mono">
                Changing this email updates your NEXARION contact email, not your Google account.
              </p>
            )}
          </div>

          <button
            type="submit"
            disabled={isUpdatingUser}
            className="btn-silver text-xs py-2 px-4"
          >
            {isUpdatingUser ? "Saving..." : "Save Profile"}
          </button>
        </form>
      </div>

      <div className="glass-panel p-6 rounded-2xl space-y-5">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 sm:gap-6">
          <div className="flex items-start sm:items-center gap-3 min-w-0 flex-1">
            <div className="p-2 rounded-xl bg-white/5 text-white shrink-0">
              <svg className="w-5 h-5" viewBox="0 0 16 16" fill="currentColor">
                <path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.012 8.012 0 0 0 16 8c0-4.42-3.58-8-8-8z" />
              </svg>
            </div>
            <div className="min-w-0 flex-1">
              <h2 className="text-sm font-semibold text-white">GitHub Integration</h2>
              <p className="text-xs text-neutral-400 mt-0.5 leading-relaxed">
                Connect your GitHub account to review pull requests directly inside NEXARION
              </p>
            </div>
          </div>

          <span
            className={`shrink-0 self-start sm:self-center text-[10px] px-2.5 py-1 rounded-full font-mono uppercase tracking-wider whitespace-nowrap ${
              ghStatus?.connected
                ? "bg-white/15 text-white border border-white/20"
                : "bg-neutral-800 text-neutral-400 border border-neutral-700/50"
            }`}
          >
            {ghStatus?.connected ? "CONNECTED" : "DISCONNECTED"}
          </span>
        </div>

        {ghActionMsg && (
          <div className="p-3 rounded-xl bg-white/5 border border-white/10 text-xs text-white">
            {ghActionMsg}
          </div>
        )}

        {isLoadingGh ? (
          <div className="py-6 text-center text-xs text-neutral-400 font-mono">
            Loading GitHub connection details...
          </div>
        ) : ghStatus?.connected ? (

          <div className="p-4 rounded-xl bg-white/[0.03] border border-white/10 space-y-3">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
              <div className="min-w-0 flex-1">
                <div className="text-xs font-semibold text-white font-mono">
                  Account: @{ghStatus.username || user?.github_username || "developer"}
                </div>
                <div className="text-[11px] text-neutral-400 mt-0.5">
                  Repository access: Authorized for pull request diff inspections
                </div>
              </div>
              <button
                type="button"
                onClick={handleDisconnectGitHub}
                className="shrink-0 self-start sm:self-center py-1.5 px-3 rounded-lg bg-white/5 hover:bg-white/10 text-neutral-400 hover:text-red-400 border border-white/10 text-xs transition-colors"
              >
                Disconnect GitHub
              </button>
            </div>
          </div>
        ) : (

          <div className="space-y-4">
            <div className="p-4 rounded-xl bg-white/[0.03] border border-white/10 text-xs text-neutral-300 leading-relaxed">
              Authenticate via GitHub OAuth or provide a Personal Access Token with{" "}
              <code className="text-white font-mono bg-white/10 px-1 py-0.5 rounded">repo</code>{" "}
              scope to pull repository diffs and run multi-agent reviews.
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">

              <div className="p-4 rounded-xl bg-white/[0.02] border border-white/10 space-y-3">
                <div className="text-xs font-semibold text-white">GitHub OAuth Flow</div>
                <p className="text-[11px] text-neutral-400">
                  Redirects through the official GitHub authorization screen.
                </p>
                <button
                  type="button"
                  onClick={handleConnectGitHubOAuth}
                  className="w-full btn-silver py-2 text-xs justify-center"
                >
                  Connect via GitHub OAuth
                </button>
              </div>

              <div className="p-4 rounded-xl bg-white/[0.02] border border-white/10 space-y-3">
                <div className="text-xs font-semibold text-white">Personal Access Token</div>
                <p className="text-[11px] text-neutral-400">
                  Direct token verification via backend. Never stored in frontend code.
                </p>
                <form onSubmit={handleConnectGitHubToken} className="space-y-2">
                  <input
                    type="password"
                    placeholder="ghp_xxxxxxxxxxxx"
                    value={ghTokenInput}
                    onChange={(e) => setGhTokenInput(e.target.value)}
                    className="w-full bg-black/60 border border-white/15 rounded-lg px-2.5 py-1.5 text-xs text-white placeholder-neutral-600 font-mono focus:outline-none focus:border-white/35"
                  />
                  <button
                    type="submit"
                    disabled={!ghTokenInput.trim() || isConnectingGhToken}
                    className="w-full btn-silver py-1.5 text-xs justify-center"
                  >
                    {isConnectingGhToken ? "Validating..." : "Connect Token"}
                  </button>
                </form>
              </div>
            </div>

            <div className="p-4 rounded-xl bg-black/40 border border-white/10 text-xs font-mono space-y-2">
              <div className="text-neutral-300 font-semibold text-[11px] uppercase tracking-wider">
                Configuration Checklist (.env)
              </div>
              <ul className="space-y-1 text-neutral-400 text-[11px]">
                <li>
                  • <span className="text-white">GITHUB_CLIENT_ID</span>: Set for GitHub OAuth app authentication
                </li>
                <li>
                  • <span className="text-white">GITHUB_CLIENT_SECRET</span>: Backend secret for OAuth code exchange
                </li>
                <li>
                  • <span className="text-white">GITHUB_TOKEN</span>: Optional system-level token for public/private repos
                </li>
              </ul>
            </div>
          </div>
        )}
      </div>

    </div>
  );
});
