import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { Sidebar } from "../layout/Sidebar.tsx";

const SIDEBAR_PATH = path.resolve(import.meta.dirname, "../layout/Sidebar.tsx");
const APP_PATH = path.resolve(import.meta.dirname, "../../App.tsx");
const CSS_PATH = path.resolve(import.meta.dirname, "../../index.css");

test("Sidebar renders 64px compact icon navigation rail when isCollapsed is true", () => {
  const html = renderToStaticMarkup(
    React.createElement(Sidebar, {
      currentView: "chat",
      onSelectView: () => {},
      conversations: [],
      onSelectConversation: () => {},
      onNewChat: () => {},
      onNewReview: () => {},
      onOpenSearch: () => {},
      onOpenGitHub: () => {},
      reviews: [],
      user: {
        id: "user-1",
        name: "Kushal",
        email: "kushal@nexarion.dev",
        role: "user",
      },
      onOpenSettings: () => {},
      onLogout: () => {},
      onOpenAuth: () => {},
      isCollapsed: true,
      onToggleCollapse: () => {},
    })
  );

  // 1. Collapsed rail container must be present with w-16 (64px) and proper accessibility label
  assert.ok(
    html.includes('aria-label="Collapsed navigation"'),
    "Collapsed navigation rail aside must be rendered when isCollapsed is true"
  );
  assert.ok(
    html.includes("w-16"),
    "Collapsed navigation rail must use consistent 64px width (w-16)"
  );

  // 2. Top section: Logo, Expand toggle, New Chat, Search
  assert.ok(html.includes('aria-label="Nexarion"'), "Logo button must be present in top section");
  assert.ok(html.includes('aria-label="Expand sidebar"'), "Expand sidebar toggle button must be present");
  assert.ok(html.includes('aria-label="New chat"'), "New chat button must be present");
  assert.ok(html.includes('aria-label="Search chats"'), "Search button must be present");

  // 3. Middle section: Navigation items with active state
  assert.ok(html.includes('aria-label="AI Assistant"'), "AI Assistant must be in middle section");
  assert.ok(html.includes('aria-label="Overview"'), "Overview must be in middle section");
  assert.ok(html.includes('aria-label="Pull Requests"'), "Pull Requests must be in middle section");
  assert.ok(html.includes('aria-label="Agents"'), "Agents must be in middle section");
  assert.ok(html.includes('aria-label="Review History"'), "Review History must be in middle section");
  assert.ok(html.includes('aria-label="GitHub Pull Requests"'), "GitHub PRs must be in middle section");

  // 4. Active state styling on currentView='chat'
  assert.ok(
    html.includes("bg-white/15 text-white border border-white/20"),
    "Active item must have subtle dark-grey/highlight background"
  );

  // 5. Bottom section: Settings & Profile anchored at bottom
  assert.ok(html.includes("mt-auto"), "Bottom section must be anchored with mt-auto");
  assert.ok(html.includes('aria-label="Settings"'), "Settings button must be in bottom section");
  assert.ok(html.includes('aria-label="User profile: Kushal"'), "User profile button must be in bottom section");

  // 6. Hover tooltips must exist with role="tooltip" and pointer-events-none
  assert.ok(
    html.includes('role="tooltip"'),
    "Tooltips must be rendered for collapsed navigation items"
  );
  assert.ok(
    html.includes("pointer-events-none"),
    "Tooltips must be non-blocking with pointer-events-none"
  );
  assert.ok(
    html.includes("left-full"),
    "Tooltips must position to the right of the sidebar"
  );
});

test("App.tsx and index.css integrate 64px collapsed layout and keyboard shortcut", () => {
  const appSrc = fs.readFileSync(APP_PATH, "utf8");
  const css = fs.readFileSync(CSS_PATH, "utf8");

  // App.tsx sets effective width to 64px when isSidebarCollapsed is true
  assert.ok(
    appSrc.includes("const effectiveWidth = isSidebarCollapsed ? 64 : sidebarWidth"),
    "App.tsx must set effective sidebar width to 64px when collapsed"
  );

  // App.tsx main container uses md:pl-16 for collapsed state
  assert.ok(
    appSrc.includes('isSidebarCollapsed ? "sidebar-collapsed md:pl-16" : ""'),
    "main container must apply md:pl-16 when sidebar is collapsed"
  );

  // Keyboard shortcut Ctrl+[ / Cmd+[ toggles collapse
  assert.ok(
    appSrc.includes('e.key === "["'),
    "App.tsx must support Ctrl+[ / Cmd+[ shortcut to toggle sidebar collapse"
  );

  // CSS ensures 64px padding-left on desktop
  assert.ok(
    css.includes("padding-left: 64px !important;"),
    "index.css must enforce 64px padding-left for sidebar-collapsed on desktop"
  );
});
