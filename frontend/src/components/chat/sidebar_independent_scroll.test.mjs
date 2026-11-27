import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { Sidebar } from "../layout/Sidebar.tsx";

const SIDEBAR_PATH = path.resolve(import.meta.dirname, "../layout/Sidebar.tsx");
const APP_PATH = path.resolve(import.meta.dirname, "../../App.tsx");

function makeConversations(count) {
  return Array.from({ length: count }, (_, idx) => ({
    id: `conv-${idx + 1}`,
    title: `Conversation Thread #${idx + 1} with long title for overflow testing`,
    mode: "normal",
    is_pinned: false,
    is_archived: false,
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
  }));
}

function makeReviews(count) {
  return Array.from({ length: count }, (_, idx) => ({
    id: `rev-${idx + 1}`,
    repository_name: `nexarion/repo-${(idx % 5) + 1}`,
    pr_identifier: `#${100 + idx}`,
    title: `GitHub PR #${100 + idx}: Automated audit check ${idx + 1}`,
    provider: "llm",
    model_name: "nemotron",
    agents_used: ["security", "quality"],
    finding_count: idx % 7,
    has_critical: idx % 4 === 0,
    duration_seconds: 1.5,
    created_at: new Date().toISOString(),
  }));
}

test("Sidebar renders fixed header, independent conversation and review scroll containers, and fixed GitHub PR footer", () => {
  const html = renderToStaticMarkup(
    React.createElement(Sidebar, {
      currentView: "chat",
      onSelectView: () => {},
      conversations: makeConversations(120),
      activeConversationId: "conv-3",
      onSelectConversation: () => {},
      onNewChat: () => {},
      onNewReview: () => {},
      onOpenSearch: () => {},
      onOpenGitHub: () => {},
      reviews: makeReviews(120),
      user: {
        id: "user-1",
        name: "Kushal",
        email: "kushal@nexarion.dev",
        role: "user",
        github_connected: true,
      },
      onOpenSettings: () => {},
      onLogout: () => {},
      onOpenAuth: () => {},
      isMobileOpen: true,
      onCloseMobile: () => {},
    })
  );

  assert.ok(html.includes('data-testid="sidebar-conversations-scroll"'));
  assert.ok(html.includes('data-testid="sidebar-reviews-scroll"'));
  assert.ok(html.includes('data-testid="sidebar-github-pr-footer"'));

  // All 120 conversations and all 120 reviews must be rendered inside their independent scroll containers (no slice(0, 5) truncation)
  assert.ok(html.includes("Conversation Thread #1 "));
  assert.ok(html.includes("Conversation Thread #120 "));
  assert.ok(html.includes("GitHub PR #100:"));
  assert.ok(html.includes("GitHub PR #219:"));

  // Verify structural ordering: Header/Nav -> Conversations section -> Reviews section -> Fixed GitHub PR Footer
  const navIdx = html.indexOf('aria-label="Main navigation"');
  const convSectionIdx = html.indexOf('aria-label="Conversations"');
  const convScrollIdx = html.indexOf('data-testid="sidebar-conversations-scroll"');
  const revSectionIdx = html.indexOf('aria-label="Recent Reviews"');
  const revScrollIdx = html.indexOf('data-testid="sidebar-reviews-scroll"');
  const prFooterIdx = html.indexOf('data-testid="sidebar-github-pr-footer"');

  assert.ok(navIdx > -1 && convSectionIdx > navIdx);
  assert.ok(convScrollIdx > convSectionIdx);
  assert.ok(revSectionIdx > convScrollIdx);
  assert.ok(revScrollIdx > revSectionIdx);
  assert.ok(prFooterIdx > revScrollIdx);
});

test("Sidebar.tsx layout enforces independent flex min-h-0 overflow-y-auto panels and fixed footer", () => {
  const src = fs.readFileSync(SIDEBAR_PATH, "utf8");

  // Shared outer container must NOT have overflow-y-auto wrapping both Conversations and Reviews together
  assert.match(
    src,
    /flex-1 min-h-0 flex flex-col overflow-hidden/
  );
  // Both independent scroll regions must use flex-1 min-h-0 overflow-y-auto overscroll-y-contain
  const scrollMatches = src.match(/flex-1 min-h-0 overflow-y-auto overscroll-y-contain/g) || [];
  assert.equal(
    scrollMatches.length,
    2,
    "Both Recent Conversations and Recent Reviews must have independent overflow-y-auto overscroll-y-contain scroll containers"
  );
  // Fixed header, main nav, section headings, and GitHub PR footer must use flex-shrink-0
  const shrinkMatches = src.match(/flex-shrink-0/g) || [];
  assert.ok(shrinkMatches.length >= 6);
  assert.ok(!src.includes("reviews.slice(0, 5)"), "Recent Reviews must not truncate reviews at 5 items");
});

test("App.tsx does not eagerly crawl GitHub pull requests on startup/normal chat load", () => {
  const appSrc = fs.readFileSync(APP_PATH, "utf8");
  const loadStart = appSrc.indexOf("const loadUserData = async");
  assert.ok(loadStart !== -1);
  const checkAuthIdx = appSrc.indexOf("const checkAuthAndInitialize", loadStart);
  assert.ok(checkAuthIdx !== -1);
  const lazyEffectIdx = appSrc.indexOf("useEffect(() => {", loadStart);
  const loadEnd = lazyEffectIdx !== -1 && lazyEffectIdx < checkAuthIdx ? lazyEffectIdx : checkAuthIdx;
  const loadBlock = appSrc.slice(loadStart, loadEnd);
  assert.ok(
    !loadBlock.includes("fetchPullRequests()"),
    "loadUserData must not automatically call fetchPullRequests() in background during normal chat load"
  );
  assert.match(
    appSrc,
    /currentView === "prs" && user\?\.github_connected/
  );
});
