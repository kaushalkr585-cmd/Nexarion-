/**
 * Production and runtime URL configuration utility for Nexarion.
 */

export const DEFAULT_PRODUCTION_URL = "https://nexarion-4yio.onrender.com";

/**
 * Returns the configured base URL for the application.
 *
 * Priority order:
 * 1. import.meta.env.VITE_APP_URL
 * 2. import.meta.env.VITE_FRONTEND_URL
 * 3. window.location.origin (in browser, with localhost preserved for local testing,
 *    and legacy placeholder domain nexarion.com automatically mapped to production)
 * 4. DEFAULT_PRODUCTION_URL
 */
export function getAppBaseUrl(): string {
  try {
    const metaEnv = typeof import.meta !== "undefined"
      ? (import.meta as unknown as { env?: Record<string, string | undefined> })?.env
      : undefined;
    const envUrl = (metaEnv?.VITE_APP_URL || metaEnv?.VITE_FRONTEND_URL || "").trim();
    if (envUrl) {
      return envUrl.replace(/\/+$/, "");
    }
  } catch {
    // Ignore error in environments where import.meta is not configured
  }

  if (typeof window !== "undefined" && window.location?.origin) {
    const origin = window.location.origin.trim().replace(/\/+$/, "");
    if (origin.includes("localhost") || origin.includes("127.0.0.1")) {
      return origin;
    }
    if (origin.toLowerCase().includes("nexarion.com")) {
      return DEFAULT_PRODUCTION_URL;
    }
    if (origin.startsWith("http://") || origin.startsWith("https://")) {
      return origin;
    }
  }

  return DEFAULT_PRODUCTION_URL;
}

/**
 * Generates the canonical conversation share URL.
 * All newly generated conversation share links strictly follow:
 * https://nexarion-4yio.onrender.com/c/{conversationId} (or local origin in dev)
 */
export function getConversationShareUrl(conversationId: string): string {
  const cleanId = (conversationId || "").trim();
  const baseUrl = getAppBaseUrl();
  return `${baseUrl}/c/${cleanId}`;
}

/**
 * Normalizes any legacy or varied share URLs to the canonical production URL.
 * Converts legacy nexarion.com/c/{id} to https://nexarion-4yio.onrender.com/c/{id}.
 */
export function normalizeShareUrl(rawUrl: string): string {
  const trimmed = (rawUrl || "").trim();
  if (!trimmed) return "";

  return trimmed.replace(
    /^https?:\/\/(?:www\.)?nexarion\.com\/?/i,
    `${DEFAULT_PRODUCTION_URL}/`
  );
}
