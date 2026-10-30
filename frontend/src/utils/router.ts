import type { NavView } from "../types";

export interface RouteState {
  view: NavView;
  conversationId?: string;
}

export function getViewFromPath(pathname: string): RouteState {
  const clean = (pathname || "/").trim().replace(/\/+$/, "") || "/";

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
    case "chat":
    default:
      return conversationId ? `/c/${conversationId}` : "/";
  }
}
