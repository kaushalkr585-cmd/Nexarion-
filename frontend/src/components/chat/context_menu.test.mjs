import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

test("Chat History Context Menu strictly adheres to specification", () => {
  const menuFilePath = path.join(__dirname, "ConversationContextMenu.tsx");
  assert.ok(fs.existsSync(menuFilePath), "ConversationContextMenu.tsx must exist");
  const content = fs.readFileSync(menuFilePath, "utf8");

  assert.equal(
    content.toLowerCase().includes("move to project"),
    false,
    "CRITICAL CONSTRAINT: 'Move to project' must NOT appear anywhere in the context menu"
  );
  assert.equal(
    content.toLowerCase().includes("project"),
    false,
    "No project-moving or project-management option should appear in context menu"
  );

  assert.equal(
    content.toLowerCase().includes("open on nexarion.com"),
    false,
    "'Open on nexarion.com' must be removed from the conversation context menu"
  );

  const renameIdx = content.indexOf("<span>Rename</span>");
  const pinIdx = content.indexOf("{conversation.is_pinned ? \"Unpin\" : \"Pin\"}");
  const sectionIdx = content.indexOf("<span>Section</span>");
  const shareIdx = content.indexOf("<span>Share</span>");
  const archiveIdx = content.indexOf("<span>Archive</span>");
  const deleteIdx = content.indexOf("<span>Delete</span>");

  assert.ok(renameIdx > -1, "Rename item must exist");
  assert.ok(pinIdx > -1, "Pin/Unpin item must exist");
  assert.ok(sectionIdx > -1, "Section item must exist");
  assert.ok(shareIdx > -1, "Share item must exist");
  assert.ok(archiveIdx > -1, "Archive item must exist");
  assert.ok(deleteIdx > -1, "Delete item must exist");

  assert.ok(renameIdx < pinIdx, "Rename must appear before Pin");
  assert.ok(pinIdx < sectionIdx, "Pin must appear before Section");
  assert.ok(sectionIdx < shareIdx, "Section must appear before Share");
  assert.ok(shareIdx < archiveIdx, "Share must appear before Archive");
  assert.ok(archiveIdx < deleteIdx, "Archive must appear before Delete");
});

test("Back toggle must strictly display 'Back' and never 'Back to Assistant'", () => {
  const appFilePath = path.join(__dirname, "../../App.tsx");
  assert.ok(fs.existsSync(appFilePath), "App.tsx must exist");
  const appContent = fs.readFileSync(appFilePath, "utf8");

  assert.equal(
    appContent.includes("Back to Assistant"),
    false,
    "The Back toggle must display exactly Back, never 'Back to Assistant'"
  );
  assert.ok(
    appContent.includes("<span>Back</span>"),
    "The Back toggle must display exactly <span>Back</span>"
  );
});

test("Sidebar supports desktop collapse with persistence", () => {
  const sidebarPath = path.join(__dirname, "../layout/Sidebar.tsx");
  const appPath = path.join(__dirname, "../../App.tsx");

  const sidebarContent = fs.readFileSync(sidebarPath, "utf8");
  const appContent = fs.readFileSync(appPath, "utf8");

  assert.ok(
    sidebarContent.includes("isCollapsed") && sidebarContent.includes("onToggleCollapse"),
    "Sidebar component must support isCollapsed and onToggleCollapse props"
  );
  assert.ok(
    appContent.includes("nexarion_sidebar_collapsed"),
    "Sidebar collapsed state must persist to localStorage with key 'nexarion_sidebar_collapsed'"
  );
});

test("Sidebar supports archive toggle to view and unarchive archived chats", () => {
  const sidebarPath = path.join(__dirname, "../layout/Sidebar.tsx");
  const menuFilePath = path.join(__dirname, "ConversationContextMenu.tsx");

  const sidebarContent = fs.readFileSync(sidebarPath, "utf8");
  const menuContent = fs.readFileSync(menuFilePath, "utf8");

  assert.ok(
    sidebarContent.includes("showArchived") && sidebarContent.includes("setShowArchived"),
    "Sidebar component must have showArchived toggle state"
  );
  assert.ok(
    sidebarContent.includes("archivedConversations"),
    "Sidebar must filter and render archived conversations"
  );
  assert.ok(
    menuContent.includes("<span>Unarchive</span>"),
    "Conversation context menu must support Unarchive action for archived chats"
  );
});

test("Review History has fixed New Review and Clear Audit buttons with no awkward wrapping", () => {
  const historyPath = path.join(__dirname, "../../pages/HistoryPage.tsx");
  const cssPath = path.join(__dirname, "../../index.css");

  const historyContent = fs.readFileSync(historyPath, "utf8");
  const cssContent = fs.readFileSync(cssPath, "utf8");

  assert.ok(
    historyContent.includes("Clear Audit"),
    "Review History page must have Clear Audit button"
  );
  assert.ok(
    historyContent.includes("whitespace-nowrap") && historyContent.includes("flex-shrink-0"),
    "Buttons must have whitespace-nowrap and flex-shrink-0"
  );

  assert.ok(
    historyContent.includes("New Review"),
    "Review History page must have New Review button"
  );

  assert.ok(
    cssContent.includes(".btn-silver") &&
      cssContent.includes("white-space: nowrap") &&
      cssContent.includes("flex-shrink: 0"),
    ".btn-silver must have white-space: nowrap and flex-shrink: 0"
  );
});

test("Mobile header bar keeps sidebar button on all pages along with back button", () => {
  const appPath = path.join(__dirname, "../../App.tsx");
  const appContent = fs.readFileSync(appPath, "utf8");

  const mobileHeaderStart = appContent.indexOf("{/* Mobile Header Bar */}");
  assert.ok(mobileHeaderStart > -1, "Mobile header must exist in App.tsx");
  const mobileHeaderSection = appContent.slice(mobileHeaderStart, mobileHeaderStart + 1200);

  assert.ok(
    mobileHeaderSection.includes("setIsMobileNavOpen(true)"),
    "Sidebar button must always be present to open mobile nav"
  );
  assert.ok(
    mobileHeaderSection.includes("<MenuIcon"),
    "MenuIcon must be rendered in mobile header"
  );
  assert.ok(
    mobileHeaderSection.includes("canGoBack") && mobileHeaderSection.includes("<BackIcon"),
    "Back button must be rendered alongside sidebar button when canGoBack is true"
  );

  const conditionalMenuPattern = /canGoBack\s*\?\s*\(\s*<button[^>]*handleGoBack[^>]*>[\s\S]*?\)\s*:\s*\(\s*<button[^>]*setIsMobileNavOpen/;
  assert.equal(
    conditionalMenuPattern.test(mobileHeaderSection),
    false,
    "Sidebar button must NOT be replaced/hidden when canGoBack is true"
  );
});
