import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

test("ChatSearchModal source structure & requirements", () => {
  const modalPath = path.join(__dirname, "ChatSearchModal.tsx");
  assert.ok(fs.existsSync(modalPath), "ChatSearchModal.tsx must exist");
  const content = fs.readFileSync(modalPath, "utf-8");

  // Keyboard shortcut & controls
  assert.ok(content.includes("Escape"), "Must handle Escape key to close");
  assert.ok(content.includes("ArrowDown"), "Must handle ArrowDown key navigation");
  assert.ok(content.includes("ArrowUp"), "Must handle ArrowUp key navigation");
  assert.ok(content.includes("Enter"), "Must handle Enter key to select");

  // Highlight matches
  assert.ok(content.includes("HighlightMatches"), "Must have highlight matches functionality");
  assert.ok(content.includes("<mark"), "Must use mark tag with styling for matching text");

  // API integration
  assert.ok(content.includes("conversationApi.search"), "Must call conversationApi.search");

  // Empty state handling
  assert.ok(content.includes("No conversations found"), "Must have empty state for no matches");
  assert.ok(content.includes("Search your conversations"), "Must have prompt state when query is empty");
});

test("Sidebar has Search chats button with Ctrl+K shortcut", () => {
  const sidebarPath = path.join(__dirname, "..", "layout", "Sidebar.tsx");
  const content = fs.readFileSync(sidebarPath, "utf-8");

  assert.ok(content.includes("onOpenSearch"), "Sidebar must accept onOpenSearch prop");
  assert.ok(content.includes("Search chats"), "Sidebar must render 'Search chats' label");
  assert.ok(content.includes("Ctrl"), "Sidebar must display Ctrl+K keyboard shortcut hint");
  assert.ok(content.includes("SearchIcon"), "Sidebar must render SearchIcon");
});

test("App.tsx integrates ChatSearchModal and Ctrl+K global shortcut", () => {
  const appPath = path.join(__dirname, "..", "..", "App.tsx");
  const content = fs.readFileSync(appPath, "utf-8");

  assert.ok(content.includes("ChatSearchModal"), "App.tsx must import and render ChatSearchModal");
  assert.ok(content.includes("isSearchOpen"), "App.tsx must manage isSearchOpen state");
  assert.ok(
    content.includes("handleGlobalKeyDown") || content.includes("ctrlKey || e.metaKey"),
    "App.tsx must register global keyboard listener for Ctrl+K / Cmd+K"
  );
});

test("AIConversationWorkspace has ChatGPT-style circular send and stop button", () => {
  const workspacePath = path.join(__dirname, "AIConversationWorkspace.tsx");
  const content = fs.readFileSync(workspacePath, "utf-8");

  // Send button styling
  assert.ok(content.includes("rounded-full"), "Send button must have rounded-full circular shape");
  assert.ok(content.includes("bg-white text-black"), "Send button must have white background and black icon");
  assert.ok(content.includes("w-8 h-8 sm:w-9 sm:h-9"), "Send button must be compact (w-8 h-8 sm:w-9 sm:h-9)");
  assert.ok(content.includes("ArrowUpIcon"), "Send button must render ArrowUpIcon");
  assert.ok(content.includes("StopSquareIcon"), "Send button must render StopSquareIcon during response generation");
  assert.ok(content.includes("onStopGeneration"), "Must invoke onStopGeneration when stop button is clicked");
});
