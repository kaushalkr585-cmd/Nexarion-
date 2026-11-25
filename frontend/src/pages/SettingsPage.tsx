import React, { useEffect, useMemo, useState } from "react";
import type { GitHubStatus, User } from "../types";
import { authApi, githubApi, userApi } from "../services/api";
import { evaluatePasswordStrength } from "../utils/passwordStrength";
import { PasswordInput } from "../components/auth/PasswordInput";
import { PasswordStrengthMeter } from "../components/auth/PasswordStrengthMeter";
import { DeleteAccountModal } from "../components/modals/DeleteAccountModal";
import { GithubIcon, SecurityIcon, TrashIcon, UserIcon } from "../components/icons/Icons";

const SETTINGS_CARD_CLASS =
  "glass-panel rounded-2xl p-5 sm:p-6 border border-white/10 space-y-5 min-w-0";
const SETTINGS_DANGER_CARD_CLASS =
  "rounded-2xl p-5 sm:p-6 border border-red-500/30 bg-red-950/[0.14] backdrop-blur-md space-y-5 min-w-0";
const SETTINGS_SUBCARD_CLASS =
  "p-4 rounded-xl bg-white/[0.03] border border-white/10 min-w-0";
const SETTINGS_LABEL_CLASS = "block text-xs font-mono text-neutral-400 mb-1.5";
const SETTINGS_INPUT_CLASS =
  "w-full h-10 bg-black/60 border border-white/15 rounded-xl px-3.5 text-sm text-white placeholder-neutral-600 focus:outline-none focus:border-white/40 transition-colors disabled:opacity-50";
const SETTINGS_PASSWORD_INPUT_CLASS =
  "h-10 !bg-black/60 !rounded-xl !pl-3.5 !pr-10 !text-sm !py-0";
const SETTINGS_BTN_PRIMARY_CLASS =
  "h-10 px-4 rounded-xl bg-white/[0.07] hover:bg-white/[0.13] active:bg-white/[0.18] text-white border border-white/15 hover:border-white/30 text-xs font-medium inline-flex items-center justify-center gap-2 transition-colors cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed whitespace-nowrap shrink-0";
const SETTINGS_BTN_DANGER_CLASS =
  "h-10 px-4 rounded-xl bg-red-500/15 hover:bg-red-500/25 text-red-200 hover:text-white border border-red-500/35 hover:border-red-500/50 text-xs font-medium inline-flex items-center justify-center gap-2 transition-colors cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed whitespace-nowrap shrink-0";

interface SettingsSectionHeaderProps {
  id: string;
  icon: React.ReactNode;
  title: string;
  description?: string;
  badge?: React.ReactNode;
  variant?: "default" | "danger";
}

const SettingsSectionHeader: React.FC<SettingsSectionHeaderProps> = ({
  id,
  icon,
  title,
  description,
  badge,
  variant = "default",
}) => (
  <div
    className={`flex flex-wrap items-start justify-between gap-3 pb-4 border-b ${
      variant === "danger" ? "border-red-500/20" : "border-white/10"
    }`}
  >
    <div className={`flex ${description ? "items-start" : "items-center"} gap-3.5 min-w-0 flex-1`}>
      <div
        className={`w-10 h-10 rounded-xl border flex items-center justify-center shrink-0 ${
          variant === "danger"
            ? "bg-red-500/10 border-red-500/25 text-red-300"
            : "bg-white/[0.05] border-white/10 text-white"
        }`}
      >
        {icon}
      </div>
      <div className="min-w-0 flex-1">
        <h2
          id={id}
          className={`text-base font-semibold tracking-tight ${
            variant === "danger" ? "text-red-200" : "text-white"
          }`}
        >
          {title}
        </h2>
        {description && (
          <p
            className={`text-xs mt-0.5 leading-relaxed ${
              variant === "danger" ? "text-neutral-300" : "text-neutral-400"
            }`}
          >
            {description}
          </p>
        )}
      </div>
    </div>
    {badge && <div className="shrink-0 self-start sm:self-center">{badge}</div>}
  </div>
);

interface SettingsPageProps {
  user: User | null;
  onUserUpdated: (user: User) => void;
  onAccountDeleted?: () => void;
  pendingReauthToken?: string | null;
  pendingReauthError?: string | null;
  onClearPendingReauth?: () => void;
}

type AccountSectionKey = "all" | "profile" | "security" | "connected" | "danger";

export const SettingsPage: React.FC<SettingsPageProps> = React.memo(({
  user,
  onUserUpdated,
  onAccountDeleted,
  pendingReauthToken = null,
  pendingReauthError = null,
  onClearPendingReauth,
}) => {
  const [activeSection, setActiveSection] = useState<AccountSectionKey>("all");

  // Profile state
  const [name, setName] = useState(user?.name || "Developer");
  const [email, setEmail] = useState(user?.email || "");
  const [isUpdatingUser, setIsUpdatingUser] = useState(false);
  const [userMsg, setUserMsg] = useState<string | null>(null);
  const [userMsgType, setUserMsgType] = useState<"success" | "error">("success");
  const [avatarUploading, setAvatarUploading] = useState(false);

  // Security / Password management state
  const [showOptionalPasswordForm, setShowOptionalPasswordForm] = useState(false);
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmNewPassword, setConfirmNewPassword] = useState("");
  const [isChangingPassword, setIsChangingPassword] = useState(false);
  const [isRevokingSessions, setIsRevokingSessions] = useState(false);
  const [securityMsg, setSecurityMsg] = useState<string | null>(null);
  const [securityMsgType, setSecurityMsgType] = useState<"success" | "error">("success");

  // Connected Accounts / GitHub state
  const [ghStatus, setGhStatus] = useState<GitHubStatus | null>(null);
  const [isLoadingGh, setIsLoadingGh] = useState(false);
  const [ghTokenInput, setGhTokenInput] = useState("");
  const [isConnectingGhToken, setIsConnectingGhToken] = useState(false);
  const [isConnectingOAuth, setIsConnectingOAuth] = useState(false);
  const [ghActionMsg, setGhActionMsg] = useState<string | null>(null);

  // Danger Zone / Account deletion modal
  const [isDeleteModalOpen, setIsDeleteModalOpen] = useState(false);

  const newPasswordEvaluation = useMemo(
    () =>
      evaluatePasswordStrength(newPassword, {
        name: user?.name || name,
        email: user?.email || email,
      }),
    [newPassword, user?.name, user?.email, name, email]
  );

  useEffect(() => {
    if (user?.name) setName(user.name);
    if (user?.email) setEmail(user.email);
  }, [user?.name, user?.email]);

  useEffect(() => {
    loadGitHubStatus();
  }, []);

  useEffect(() => {
    if (pendingReauthToken || pendingReauthError) {
      setIsDeleteModalOpen(true);
    }
  }, [pendingReauthToken, pendingReauthError]);

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
      setUserMsgType("error");
      e.target.value = "";
      return;
    }
    if (file.size > 5 * 1024 * 1024) {
      setUserMsg("File size must not exceed 5MB.");
      setUserMsgType("error");
      e.target.value = "";
      return;
    }

    setAvatarUploading(true);
    setUserMsg(null);
    try {
      const updated = await userApi.uploadAvatar(file);
      onUserUpdated(updated);
      setUserMsg("Avatar updated successfully.");
      setUserMsgType("success");
    } catch (err: unknown) {
      setUserMsg(err instanceof Error ? err.message : "Failed to upload avatar.");
      setUserMsgType("error");
    } finally {
      setAvatarUploading(false);
      e.target.value = "";
    }
  };

  const handleChangePassword = async (e: React.FormEvent) => {
    e.preventDefault();
    setSecurityMsg(null);

    if (!newPasswordEvaluation.acceptable) {
      setSecurityMsg(
        newPasswordEvaluation.warning ||
          "Your password is too weak. Try using a longer password with unpredictable words."
      );
      setSecurityMsgType("error");
      return;
    }

    if (newPassword !== confirmNewPassword) {
      setSecurityMsg("New password and confirmation do not match.");
      setSecurityMsgType("error");
      return;
    }

    setIsChangingPassword(true);
    try {
      const res = await authApi.changePassword({
        current_password: user?.has_password ? currentPassword : undefined,
        new_password: newPassword,
      });
      onUserUpdated(res.user);
      setCurrentPassword("");
      setNewPassword("");
      setConfirmNewPassword("");
      setShowOptionalPasswordForm(false);
      setSecurityMsg("Password updated successfully. Previous sessions have been invalidated.");
      setSecurityMsgType("success");
    } catch (err: unknown) {
      setSecurityMsg(err instanceof Error ? err.message : "Failed to update password.");
      setSecurityMsgType("error");
    } finally {
      setIsChangingPassword(false);
    }
  };

  const handleRevokeSessions = async () => {
    setIsRevokingSessions(true);
    setSecurityMsg(null);
    try {
      const res = await authApi.revokeOtherSessions();
      onUserUpdated(res.user);
      setSecurityMsg("All other active sessions have been signed out.");
      setSecurityMsgType("success");
    } catch (err: unknown) {
      setSecurityMsg(err instanceof Error ? err.message : "Failed to revoke sessions.");
      setSecurityMsgType("error");
    } finally {
      setIsRevokingSessions(false);
    }
  };

  const handleConnectGitHubOAuth = async () => {
    setIsConnectingOAuth(true);
    setGhActionMsg(null);
    try {
      const res = await githubApi.getAuthUrl(window.location.origin);
      if (res.url) {
        window.location.href = res.url;
      } else {
        setGhActionMsg(
          res.message ||
            "GitHub OAuth is not configured on the server. Please set GITHUB_CLIENT_ID and GITHUB_CLIENT_SECRET in .env, or connect using a Personal Access Token on the right."
        );
      }
    } catch (err) {
      setGhActionMsg(err instanceof Error ? err.message : "Failed to generate authorization URL.");
    } finally {
      setIsConnectingOAuth(false);
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

  const sectionTabs: Array<{ id: AccountSectionKey; label: string }> = [
    { id: "all", label: "All Sections" },
    { id: "profile", label: "Profile" },
    { id: "security", label: "Security" },
    { id: "connected", label: "Connected Accounts" },
    { id: "danger", label: "Danger Zone" },
  ];

  const showProfile = activeSection === "all" || activeSection === "profile";
  const showSecurity = activeSection === "all" || activeSection === "security";
  const showConnected = activeSection === "all" || activeSection === "connected";
  const showDanger = activeSection === "all" || activeSection === "danger";

  return (
    <div className="max-w-4xl mx-auto w-full px-4 sm:px-6 py-6 sm:py-8 space-y-6 relative z-10 text-left min-w-0">
      <div className="pb-5 border-b border-white/10 space-y-4">
        <div className="min-w-0">
          <div className="text-[11px] font-mono text-neutral-500 uppercase tracking-wider mb-1">
            Settings &rarr; Account
          </div>
          <h1 className="text-2xl sm:text-3xl font-semibold text-white tracking-tight">
            System &amp; Account Settings
          </h1>
          <p className="text-xs sm:text-sm text-neutral-400 mt-1 leading-relaxed">
            Manage your profile, password security, connected integrations, and account lifecycle
          </p>
        </div>

        <div
          role="tablist"
          aria-label="Account settings sections"
          className="flex items-center gap-2 flex-wrap pt-1"
        >
          {sectionTabs.map((tab) => {
            const isActive = activeSection === tab.id;
            return (
              <button
                key={tab.id}
                type="button"
                role="tab"
                aria-selected={isActive}
                onClick={() => setActiveSection(tab.id)}
                className={`h-9 px-3.5 rounded-xl text-xs font-medium transition-colors cursor-pointer border whitespace-nowrap ${
                  isActive
                    ? tab.id === "danger"
                      ? "bg-red-500/20 text-red-200 border-red-500/40"
                      : "bg-white/15 text-white border-white/30"
                    : tab.id === "danger"
                    ? "bg-white/[0.03] text-red-400/90 hover:text-red-300 border-white/10 hover:border-red-500/30"
                    : "bg-white/[0.03] text-neutral-400 hover:text-white border-white/10 hover:bg-white/[0.07]"
                }`}
              >
                {tab.label}
              </button>
            );
          })}
        </div>
      </div>

      {userMsg && (
        <div
          role="status"
          className={`p-3.5 rounded-xl text-xs leading-relaxed ${
            userMsgType === "error"
              ? "bg-red-500/10 border border-red-500/20 text-red-300"
              : "bg-emerald-500/10 border border-emerald-500/20 text-emerald-300"
          }`}
        >
          {userMsg}
        </div>
      )}

      {/* SECTION 1: PROFILE */}
      {showProfile && (
        <section
          id="settings-profile"
          aria-labelledby="settings-profile-heading"
          className={SETTINGS_CARD_CLASS}
        >
          <SettingsSectionHeader
            id="settings-profile-heading"
            icon={<UserIcon className="w-5 h-5" />}
            title="Profile"
            description="User identity details, email address, and developer avatar"
          />

          <div className="flex flex-col sm:flex-row sm:items-center gap-4 pb-5 border-b border-white/10">
            <div className="flex items-center gap-4 min-w-0 flex-1">
              <div className="relative shrink-0">
                {user?.avatar_url ? (
                  <img
                    src={user.avatar_url}
                    alt={user.name}
                    className="w-14 h-14 sm:w-16 sm:h-16 rounded-full object-cover border border-white/20"
                    onError={(e) => {
                      (e.currentTarget as HTMLElement).style.display = "none";
                      const fallback = e.currentTarget.parentElement?.querySelector(".avatar-fallback");
                      if (fallback) (fallback as HTMLElement).classList.remove("hidden");
                    }}
                  />
                ) : null}
                <div
                  className={`avatar-fallback w-14 h-14 sm:w-16 sm:h-16 rounded-full bg-neutral-800 border border-white/20 items-center justify-center text-lg font-bold text-white ${
                    user?.avatar_url ? "hidden" : "flex"
                  }`}
                >
                  {user?.name ? user.name.charAt(0).toUpperCase() : "U"}
                </div>
              </div>

              <div className="min-w-0">
                <div className="text-xs font-semibold text-white truncate">
                  {user?.name || "Developer Profile"}
                </div>
                <div className="text-[11px] text-neutral-400 font-mono mt-0.5">
                  PNG, JPEG, or WebP up to 5MB
                </div>
              </div>
            </div>

            <label
              className={`${SETTINGS_BTN_PRIMARY_CLASS} w-full sm:w-auto ${
                !user || avatarUploading ? "opacity-40 pointer-events-none" : ""
              }`}
            >
              <span>{avatarUploading ? "Uploading..." : "Change Avatar"}</span>
              <input
                type="file"
                accept="image/png,image/jpeg,image/webp"
                onChange={handleAvatarChange}
                disabled={avatarUploading || !user}
                className="hidden"
              />
            </label>
          </div>

          <form onSubmit={handleUpdateProfile} className="space-y-4">
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div className="min-w-0">
                <label htmlFor="profile-display-name" className={SETTINGS_LABEL_CLASS}>
                  Display Name
                </label>
                <input
                  id="profile-display-name"
                  type="text"
                  value={name}
                  disabled={!user}
                  onChange={(e) => setName(e.target.value)}
                  className={SETTINGS_INPUT_CLASS}
                />
              </div>

              <div className="min-w-0">
                <label htmlFor="profile-email" className={SETTINGS_LABEL_CLASS}>
                  Email Address
                </label>
                <input
                  id="profile-email"
                  type="email"
                  value={email}
                  disabled={!user}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="you@example.com"
                  className={`${SETTINGS_INPUT_CLASS} font-mono`}
                />
              </div>
            </div>

            {user?.auth_provider === "google" && (
              <p className="text-[11px] text-neutral-500 font-mono">
                Changing this email updates your NEXARION contact email, not your Google account.
              </p>
            )}

            <div className="pt-1 flex justify-start">
              <button
                type="submit"
                disabled={isUpdatingUser || !user}
                className={`${SETTINGS_BTN_PRIMARY_CLASS} w-full sm:w-auto`}
              >
                {isUpdatingUser ? "Saving..." : "Save Profile"}
              </button>
            </div>
          </form>
        </section>
      )}

      {/* SECTION 2: SECURITY */}
      {showSecurity && (
        <section
          id="settings-security"
          aria-labelledby="settings-security-heading"
          className={SETTINGS_CARD_CLASS}
        >
          <SettingsSectionHeader
            id="settings-security-heading"
            icon={<SecurityIcon className="w-5 h-5" />}
            title="Security"
            description="Password strength enforcement, credential updates, and active session protection"
          />

          {securityMsg && (
            <div
              role="status"
              className={`p-3.5 rounded-xl text-xs leading-relaxed ${
                securityMsgType === "error"
                  ? "bg-red-500/10 border border-red-500/20 text-red-300"
                  : "bg-emerald-500/10 border border-emerald-500/20 text-emerald-300"
              }`}
            >
              {securityMsg}
            </div>
          )}

          {!user ? (
            <div className={`${SETTINGS_SUBCARD_CLASS} text-xs text-neutral-400`}>
              Sign in to manage password security and active sessions.
            </div>
          ) : (
            <div className="space-y-5">
              {!user.has_password && !showOptionalPasswordForm ? (
                <div className={`${SETTINGS_SUBCARD_CLASS} flex flex-col sm:flex-row sm:items-center justify-between gap-4`}>
                  <div className="space-y-1 min-w-0">
                    <div className="text-xs font-semibold text-white">
                      OAuth Authentication Active
                    </div>
                    <p className="text-xs text-neutral-400 leading-relaxed">
                      You authenticate via {user.auth_provider === "google" ? "Google OAuth" : "OAuth"}.
                      Creating a local password is optional and never required to use Nexarion.
                    </p>
                  </div>
                  <button
                    type="button"
                    onClick={() => setShowOptionalPasswordForm(true)}
                    className={`${SETTINGS_BTN_PRIMARY_CLASS} w-full sm:w-auto`}
                  >
                    Add Optional Password
                  </button>
                </div>
              ) : (
                <form onSubmit={handleChangePassword} className="space-y-4">
                  <div className="flex items-center justify-between gap-2">
                    <h3 className="text-xs font-semibold text-white">
                      {user.has_password ? "Change Password" : "Set Optional Local Password"}
                    </h3>
                    {!user.has_password && (
                      <button
                        type="button"
                        onClick={() => setShowOptionalPasswordForm(false)}
                        className="text-xs font-mono text-neutral-400 hover:text-white transition-colors cursor-pointer"
                      >
                        Cancel
                      </button>
                    )}
                  </div>

                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                    {user.has_password && (
                      <div className="sm:col-span-2">
                        <PasswordInput
                          id="security-current-password"
                          label="Current Password"
                          labelClassName={SETTINGS_LABEL_CLASS}
                          inputClassName={SETTINGS_PASSWORD_INPUT_CLASS}
                          required
                          value={currentPassword}
                          onChange={(e) => setCurrentPassword(e.target.value)}
                          autoComplete="current-password"
                        />
                      </div>
                    )}

                    <div className="min-w-0">
                      <PasswordInput
                        id="security-new-password"
                        label="New Password"
                        labelClassName={SETTINGS_LABEL_CLASS}
                        inputClassName={SETTINGS_PASSWORD_INPUT_CLASS}
                        required
                        value={newPassword}
                        onChange={(e) => setNewPassword(e.target.value)}
                        autoComplete="new-password"
                        placeholder="At least 12 unpredictable characters"
                      />
                    </div>

                    <div className="min-w-0">
                      <PasswordInput
                        id="security-confirm-password"
                        label="Confirm New Password"
                        labelClassName={SETTINGS_LABEL_CLASS}
                        inputClassName={SETTINGS_PASSWORD_INPUT_CLASS}
                        required
                        value={confirmNewPassword}
                        onChange={(e) => setConfirmNewPassword(e.target.value)}
                        autoComplete="new-password"
                      />
                    </div>
                  </div>

                  <PasswordStrengthMeter
                    password={newPassword}
                    evaluation={newPasswordEvaluation}
                    showRequirements={true}
                  />

                  <div className="pt-1 flex justify-start">
                    <button
                      type="submit"
                      disabled={
                        isChangingPassword ||
                        !newPasswordEvaluation.acceptable ||
                        newPassword !== confirmNewPassword ||
                        (user.has_password && !currentPassword)
                      }
                      className={`${SETTINGS_BTN_PRIMARY_CLASS} w-full sm:w-auto`}
                    >
                      {isChangingPassword
                        ? "Updating..."
                        : user.has_password
                        ? "Update Password"
                        : "Save Password"}
                    </button>
                  </div>
                </form>
              )}

              <div className={`${SETTINGS_SUBCARD_CLASS} flex flex-col sm:flex-row sm:items-center justify-between gap-4`}>
                <div className="min-w-0">
                  <div className="text-xs font-semibold text-white">Active Sessions</div>
                  <p className="text-xs text-neutral-400 mt-0.5 leading-relaxed">
                    Sign out of all other browsers and devices where your account is logged in.
                  </p>
                </div>
                <button
                  type="button"
                  disabled={isRevokingSessions}
                  onClick={handleRevokeSessions}
                  className={`${SETTINGS_BTN_PRIMARY_CLASS} w-full sm:w-auto`}
                >
                  {isRevokingSessions ? "Revoking..." : "Sign out other sessions"}
                </button>
              </div>
            </div>
          )}
        </section>
      )}

      {/* SECTION 3: CONNECTED ACCOUNTS */}
      {showConnected && (
        <section
          id="settings-connected"
          aria-labelledby="settings-connected-heading"
          className={SETTINGS_CARD_CLASS}
        >
          <SettingsSectionHeader
            id="settings-connected-heading"
            icon={<GithubIcon className="w-5 h-5" />}
            title="Connected Accounts"
            description="Manage GitHub repository integrations inside NEXARION"
            badge={
              <span
                className={`inline-flex items-center px-2.5 py-1 rounded-full text-[10px] font-mono uppercase tracking-wider border ${
                  ghStatus?.connected
                    ? "bg-white/15 text-white border-white/25"
                    : "bg-white/[0.04] text-neutral-400 border-white/10"
                }`}
              >
                {ghStatus?.connected ? "CONNECTED" : "DISCONNECTED"}
              </span>
            }
          />

          <div className="space-y-4">
            <div>
              <h3 className="text-xs font-semibold text-white">GitHub Integration</h3>
              <p className="text-xs text-neutral-400 mt-0.5 leading-relaxed">
                Connect your GitHub account to review pull requests and inspect repositories
              </p>
            </div>

            {ghActionMsg && (
              <div className="p-3.5 rounded-xl bg-amber-500/10 border border-amber-500/25 text-xs text-amber-200 flex items-start justify-between gap-3">
                <div className="flex items-start gap-2.5 min-w-0">
                  <span className="text-amber-400 font-bold shrink-0 mt-0.5">ℹ</span>
                  <p className="leading-relaxed">{ghActionMsg}</p>
                </div>
                <button
                  type="button"
                  onClick={() => setGhActionMsg(null)}
                  className="text-neutral-400 hover:text-white transition-colors text-base leading-none p-0.5 shrink-0 cursor-pointer"
                  aria-label="Dismiss alert"
                >
                  &times;
                </button>
              </div>
            )}

            {isLoadingGh ? (
              <div className="py-6 text-center text-xs text-neutral-400 font-mono">
                Loading GitHub connection details...
              </div>
            ) : ghStatus?.connected ? (
              <div className={SETTINGS_SUBCARD_CLASS}>
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
                  <div className="min-w-0 flex-1">
                    <div className="text-xs font-semibold text-white font-mono truncate">
                      Account: @{ghStatus.username || user?.github_username || "developer"}
                    </div>
                    <div className="text-xs text-neutral-400 mt-1 leading-relaxed">
                      Repository access: Authorized for pull request diff and chat inspections
                    </div>
                  </div>
                  <button
                    type="button"
                    onClick={handleDisconnectGitHub}
                    className={`${SETTINGS_BTN_DANGER_CLASS} w-full sm:w-auto`}
                  >
                    Disconnect GitHub
                  </button>
                </div>
              </div>
            ) : (
              <div className="space-y-4">
                <div className={`${SETTINGS_SUBCARD_CLASS} text-xs text-neutral-300 leading-relaxed`}>
                  Authenticate via GitHub OAuth or provide a Personal Access Token with{" "}
                  <code className="text-white font-mono bg-white/10 px-1.5 py-0.5 rounded">repo</code>{" "}
                  scope to pull repository diffs and run multi-agent reviews.
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div className={`${SETTINGS_SUBCARD_CLASS} flex flex-col justify-between gap-4`}>
                    <div>
                      <div className="text-xs font-semibold text-white">GitHub OAuth Flow</div>
                      <p className="text-xs text-neutral-400 mt-1 leading-relaxed">
                        Redirects through the official GitHub OAuth authorization screen.
                      </p>
                    </div>
                    <button
                      type="button"
                      disabled={isConnectingOAuth}
                      onClick={handleConnectGitHubOAuth}
                      className={`${SETTINGS_BTN_PRIMARY_CLASS} w-full`}
                    >
                      {isConnectingOAuth ? "Connecting..." : "Connect via GitHub OAuth"}
                    </button>
                  </div>

                  <div className={`${SETTINGS_SUBCARD_CLASS} flex flex-col justify-between gap-4`}>
                    <div>
                      <div className="text-xs font-semibold text-white">Personal Access Token</div>
                      <p className="text-xs text-neutral-400 mt-1 leading-relaxed">
                        Direct token verification via backend. Never stored in frontend code.
                      </p>
                    </div>
                    <form onSubmit={handleConnectGitHubToken} className="space-y-2.5">
                      <div>
                        <label htmlFor="settings-github-pat" className={SETTINGS_LABEL_CLASS}>
                          Access Token
                        </label>
                        <input
                          id="settings-github-pat"
                          type="password"
                          placeholder="ghp_xxxxxxxxxxxx"
                          value={ghTokenInput}
                          onChange={(e) => setGhTokenInput(e.target.value)}
                          className={`${SETTINGS_INPUT_CLASS} font-mono`}
                        />
                      </div>
                      <button
                        type="submit"
                        disabled={!ghTokenInput.trim() || isConnectingGhToken}
                        className={`${SETTINGS_BTN_PRIMARY_CLASS} w-full`}
                      >
                        {isConnectingGhToken ? "Connecting..." : "Connect Token"}
                      </button>
                    </form>
                  </div>
                </div>
              </div>
            )}
          </div>
        </section>
      )}

      {/* SECTION 4: DANGER ZONE (Settings -> Account -> Danger Zone) */}
      {showDanger && (
        <section
          id="settings-danger-zone"
          aria-labelledby="settings-danger-heading"
          className={SETTINGS_DANGER_CARD_CLASS}
        >
          <SettingsSectionHeader
            id="settings-danger-heading"
            variant="danger"
            icon={<TrashIcon className="w-5 h-5" />}
            title="Danger Zone"
          />

          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
            <p className="text-xs text-neutral-300 leading-relaxed min-w-0 flex-1">
              Permanently delete your Nexarion account and all associated data, including chat
              history, code review records, uploaded files, GitHub integrations, and active
              sessions. This operation is permanent and cannot be undone.
            </p>

            {user ? (
              <button
                type="button"
                data-testid="open-delete-account-modal-btn"
                onClick={() => setIsDeleteModalOpen(true)}
                className={`${SETTINGS_BTN_DANGER_CLASS} w-full sm:w-auto font-semibold`}
              >
                Delete Account
              </button>
            ) : (
              <div className="text-xs font-mono text-neutral-400 shrink-0">
                Sign in to manage account deletion.
              </div>
            )}
          </div>
        </section>
      )}

      {user && (
        <DeleteAccountModal
          isOpen={isDeleteModalOpen}
          user={user}
          initialReauthToken={pendingReauthToken}
          initialReauthError={pendingReauthError}
          onClose={() => {
            setIsDeleteModalOpen(false);
            if (onClearPendingReauth) onClearPendingReauth();
          }}
          onAccountDeleted={() => {
            setIsDeleteModalOpen(false);
            if (onClearPendingReauth) onClearPendingReauth();
            if (onAccountDeleted) onAccountDeleted();
          }}
        />
      )}
    </div>
  );
});
