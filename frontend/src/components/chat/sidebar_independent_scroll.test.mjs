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

test("Sidebar renders fixed header/nav, stationary fixed GitHub PR section, single shared history scroll container, and fixed bottom controls", () => {
  const html = renderToStaticMarkup(
    React.createElement(Sidebar, {
      currentView: "chat",
      onSelectView: () => {},
      conversations: [
        {
          id: "pin-1",
          title: "Pinned Alpha",
          mode: "normal",
          is_pinned: true,
          is_archived: false,
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
        },
        ...makeConversations(120),
      ],
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
      sidebarWidth: 280,
      onResizeWidth: () => {},
    })
  );

  assert.ok(html.includes('data-testid="sidebar-github-pr-section"'));
  assert.ok(html.includes('data-testid="sidebar-history-scroll"'));
  assert.ok(html.includes('data-testid="sidebar-pinned-section"'));
  assert.ok(html.includes('data-testid="sidebar-reviews-section"'));

  // All 120 conversations, pinned items, and all 120 reviews must be rendered inside the shared history scroll area
  assert.ok(html.includes("Pinned Alpha"));
  assert.ok(html.includes("Conversation Thread #1 "));
  assert.ok(html.includes("Conversation Thread #120 "));
  assert.ok(html.includes("GitHub PR #100:"));
  assert.ok(html.includes("GitHub PR #219:"));

  // Verify structural ordering:
  // 1. Sidebar header and navigation.
  // 2. GitHub PR section – fixed position.
  // 3. Central history wrapper (pinned + recent conversations + recent reviews).
  // 4. Bottom settings and user profile controls.
  const navIdx = html.indexOf('aria-label="Main navigation"');
  const prSectionIdx = html.indexOf('data-testid="sidebar-github-pr-section"');
  const historyScrollIdx = html.indexOf('data-testid="sidebar-history-scroll"');
  const pinnedIdx = html.indexOf('data-testid="sidebar-pinned-section"');
  const reviewsIdx = html.indexOf('data-testid="sidebar-reviews-section"');
  const settingsIdx = html.indexOf("Settings</span>");

  assert.ok(navIdx > -1, "Nav must exist");
  assert.ok(prSectionIdx > navIdx, "GitHub PR section must be placed immediately following navigation");
  assert.ok(historyScrollIdx > prSectionIdx, "History scroll container must follow GitHub PR section");
  assert.ok(pinnedIdx > historyScrollIdx, "Pinned section must be inside the history scroll container");
  assert.ok(reviewsIdx > pinnedIdx, "Reviews section must be inside the same history scroll container following conversations");
  assert.ok(settingsIdx > reviewsIdx, "Bottom settings controls must follow the history scroll area");
});

test("Sidebar.tsx layout enforces a single shared history scroll container without nested overflow-y-auto elements", () => {
  const src = fs.readFileSync(SIDEBAR_PATH, "utf8");

  // Single dedicated history wrapper with flex-1 min-h-0 overflow-y-auto overscroll-y-contain
  const scrollMatches = src.match(/flex-1 min-h-0 overflow-y-auto overscroll-y-contain/g) || [];
  assert.equal(
    scrollMatches.length,
    1,
    "Sidebar must have exactly 1 shared scroll container for history (pinned + recent + reviews) without nested overflow-y-auto"
  );

  // Fixed header, main nav, GitHub PR section, and bottom controls must use flex-shrink-0
  const shrinkMatches = src.match(/flex-shrink-0/g) || [];
  assert.ok(shrinkMatches.length >= 4, "Header, nav, GitHub PR, and bottom controls must be flex-shrink-0");
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

test("CSS and App layout integrate centralized --sidebar-width, dynamic resizing, and responsive drawer architecture", () => {
  const cssPath = path.resolve(import.meta.dirname, "../../index.css");
  const css = fs.readFileSync(cssPath, "utf8");
  const appSrc = fs.readFileSync(APP_PATH, "utf8");

  // :root defines --sidebar-width and --sidebar-collapsed-width
  assert.match(css, /--sidebar-width:\s*260px;/);
  assert.match(css, /--sidebar-collapsed-width:\s*0px;/);

  // Resize handle styles
  assert.match(css, /\.sidebar-resize-handle/);
  assert.match(css, /cursor:\s*col-resize;/);

  // App.tsx manages sidebar width state and passes to Sidebar
  assert.match(appSrc, /const\s*\[sidebarWidth,\s*setSidebarWidth\]\s*=\s*useState/);
  assert.match(appSrc, /nexarion_sidebar_width/);
  assert.match(appSrc, /--sidebar-width/);
  assert.match(appSrc, /main-layout-content/);
});

test("Sidebar desktop resize handle renders and controls dynamic width", () => {
  const html = renderToStaticMarkup(
    React.createElement(Sidebar, {
      currentView: "chat",
      onSelectView: () => {},
      conversations: makeConversations(5),
      activeConversationId: "conv-1",
      onSelectConversation: () => {},
      onNewChat: () => {},
      onNewReview: () => {},
      reviews: makeReviews(2),
      user: null,
      onOpenSettings: () => {},
      onLogout: () => {},
      onOpenAuth: () => {},
      sidebarWidth: 320,
      onResizeWidth: () => {},
    })
  );

  // Resize handle must be present on desktop
  assert.ok(html.includes('class="sidebar-resize-handle hidden md:block"'));
  assert.ok(html.includes('role="separator"'));
  assert.ok(html.includes('aria-label="Resize sidebar"'));

  // Dedicated width data attribute and dynamic style applied
  assert.ok(html.includes('data-sidebar-width="320"'));
  assert.ok(html.includes('style="width:var(--sidebar-width)"'));
});
