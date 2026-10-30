import test from "node:test";
import assert from "node:assert/strict";

function getViewFromPath(pathname) {
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

function getPathFromView(view, conversationId) {
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

test("Router: parses default home and assistant as new chat", () => {
  assert.deepEqual(getViewFromPath("/"), { view: "chat", conversationId: undefined });
  assert.deepEqual(getViewFromPath("/assistant"), { view: "chat", conversationId: undefined });
  assert.deepEqual(getViewFromPath(""), { view: "chat", conversationId: undefined });
});

test("Router: parses conversation ID paths", () => {
  assert.deepEqual(getViewFromPath("/c/conv-abc-123"), { view: "chat", conversationId: "conv-abc-123" });
  assert.deepEqual(getViewFromPath("/assistant/conv-xyz-789"), { view: "chat", conversationId: "conv-xyz-789" });
});

test("Router: parses sections", () => {
  assert.deepEqual(getViewFromPath("/pull-requests"), { view: "prs" });
  assert.deepEqual(getViewFromPath("/prs"), { view: "prs" });
  assert.deepEqual(getViewFromPath("/overview"), { view: "overview" });
  assert.deepEqual(getViewFromPath("/agents"), { view: "agents" });
  assert.deepEqual(getViewFromPath("/review-history"), { view: "history" });
  assert.deepEqual(getViewFromPath("/history"), { view: "history" });
  assert.deepEqual(getViewFromPath("/settings"), { view: "settings" });
});

test("Router: generates canonical path from view", () => {
  assert.equal(getPathFromView("chat"), "/");
  assert.equal(getPathFromView("chat", "conv-123"), "/c/conv-123");
  assert.equal(getPathFromView("prs"), "/pull-requests");
  assert.equal(getPathFromView("overview"), "/overview");
  assert.equal(getPathFromView("agents"), "/agents");
  assert.equal(getPathFromView("history"), "/review-history");
  assert.equal(getPathFromView("settings"), "/settings");
});
