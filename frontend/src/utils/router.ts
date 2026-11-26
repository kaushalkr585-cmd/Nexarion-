import type { NavView } from "../types";

export interface RouteState {
  view: NavView;
  conversationId?: string;
}

export function getViewFromPath(pathname: string): RouteState {
  let path = (pathname || "/").trim();
  if (path.startsWith("http://") || path.startsWith("https://")) {
    try {
      const parsed = new URL(path);
      path = parsed.pathname;
    } catch {
      path = path.replace(/^https?:\/\/[^/]+/, "");
    }
  }

  const clean = path.replace(/\/+$/, "") || "/";

  const cMatch = clean.match(/^\/c\/([a-zA-Z0-9_\-]+)$/);
  if (cMatch) {
    return { view: "chat", conversationId: cMatch[1] };
  }

  const assistantMatch = clean.match(/^\/assistant\/([a-zA-Z0-9_\-]+)$/);
  if (assistantMatch) {
    return { view: "chat", conversationId: assistantMatch[1] };
  }

  switch (clean.toLowerCase()) {
    case "/pull-requests":
    case "/prs":
      return { view: "prs" };
    case "/overview":
      return { view: "overview" };
    case "/agents":
      return { view: "agents" };
    case "/review-history":
    case "/history":
      return { view: "history" };
    case "/settings":
      return { view: "settings" };
    case "/admin/feedback":
    case "/feedback":
      return { view: "feedback" };
    case "/assistant":
    case "/chat":
    case "/":
    default:
      return { view: "chat", conversationId: undefined };
  }
}

export function getPathFromView(view: NavView, conversationId?: string): string {
  switch (view) {
    case "prs":
      return "/pull-requests";
    case "overview":
      return "/overview";
    case "agents":
      return "/agents";
    case "history":
      return "/review-history";
    case "settings":
      return "/settings";
    case "feedback":
      return "/admin/feedback";
    case "chat":
    default:
      return conversationId ? `/c/${conversationId}` : "/";
  }
}
