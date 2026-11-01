import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const hookPath = path.join(__dirname, "../../hooks/useDocumentTitle.ts");
const { computeDocumentTitle } = await import(`file://${hookPath.replace(/\\/g, "/")}`);

test("Dynamic Document Title: Home / New Chat returns 'Nexarion'", () => {
  const title = computeDocumentTitle({
    currentView: "chat",
    activeConversationId: undefined,
    activeConversation: null,
    conversations: [],
  });
  assert.equal(title, "Nexarion");
});

test("Dynamic Document Title: Active Conversation returns '<Title> — Nexarion'", () => {
  const sampleConv = {
    id: "conv-123",
    title: "Optimizing PostgreSQL Connection Pool",
    messages: [],
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
  };

  const title = computeDocumentTitle({
    currentView: "chat",
    activeConversationId: "conv-123",
    activeConversation: sampleConv,
    conversations: [sampleConv],
  });
  assert.equal(title, "Optimizing PostgreSQL Connection Pool — Nexarion");
});

test("Dynamic Document Title: Fallback to conversation list title during async loading", () => {
  const cachedConv = {
    id: "conv-456",
    title: "Refactoring React Component Tree",
    messages: [],
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
  };

  const title = computeDocumentTitle({
    currentView: "chat",
    activeConversationId: "conv-456",
    activeConversation: null,
    conversations: [cachedConv],
  });
  assert.equal(title, "Refactoring React Component Tree — Nexarion");
});

test("Dynamic Document Title: Temporary fallback when conversation is missing or title is not yet available", () => {
  const title = computeDocumentTitle({
    currentView: "chat",
    activeConversationId: "conv-unknown",
    activeConversation: null,
    conversations: [],
  });
  assert.equal(title, "Nexarion");
});

test("Dynamic Document Title: Updates immediately on conversation rename", () => {
  const renamedConv = {
    id: "conv-123",
    title: "Security Audit: Payment Gateways",
    messages: [],
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
  };

  const title = computeDocumentTitle({
    currentView: "chat",
    activeConversationId: "conv-123",
    activeConversation: renamedConv,
    conversations: [renamedConv],
  });
  assert.equal(title, "Security Audit: Payment Gateways — Nexarion");
});

test("Dynamic Document Title: Section Views return standard '<Section> — Nexarion'", () => {
  assert.equal(
    computeDocumentTitle({
      currentView: "history",
      activeConversation: null,
      conversations: [],
    }),
    "Review History — Nexarion"
  );

  assert.equal(
    computeDocumentTitle({
      currentView: "overview",
      activeConversation: null,
      conversations: [],
    }),
    "Overview — Nexarion"
  );

  assert.equal(
    computeDocumentTitle({
      currentView: "prs",
      activeConversation: null,
      conversations: [],
    }),
    "Pull Requests — Nexarion"
  );

  assert.equal(
    computeDocumentTitle({
      currentView: "agents",
      activeConversation: null,
      conversations: [],
    }),
    "Agents — Nexarion"
  );

  assert.equal(
    computeDocumentTitle({
      currentView: "settings",
      activeConversation: null,
      conversations: [],
    }),
    "Settings — Nexarion"
  );
});

test("Dynamic Document Title: Modals override tab title appropriately", () => {

  assert.equal(
    computeDocumentTitle({
      currentView: "history",
      activeConversation: null,
      conversations: [],
      isComposerOpen: true,
    }),
    "New Review — Nexarion"
  );

  assert.equal(
    computeDocumentTitle({
      currentView: "history",
      activeConversation: null,
      conversations: [],
      isDetailOpen: true,
      selectedReview: {
        id: "rev-1",
        title: "Test PR Review",
        repository_name: "test/repo",
        pr_identifier: "#1",
        provider: "llm",
        model_name: "nemotron",
        agents_used: ["security"],
        finding_count: 3,
        has_critical: false,
        duration_seconds: 12,
        created_at: new Date().toISOString(),
        findings: [],
      },
    }),
    "Review Details — Nexarion"
  );
});

test("App.tsx integrates useDocumentTitle hook centrally", () => {
  const appPath = path.join(__dirname, "../../App.tsx");
  const appContent = fs.readFileSync(appPath, "utf8");

  assert.ok(
    appContent.includes('import { useDocumentTitle } from "./hooks/useDocumentTitle";'),
    "App.tsx must import useDocumentTitle"
  );
  assert.ok(
    appContent.includes("useDocumentTitle({") &&
      appContent.includes("currentView") &&
      appContent.includes("activeConversationId") &&
      appContent.includes("activeConversation") &&
      appContent.includes("conversations") &&
      appContent.includes("isComposerOpen") &&
      appContent.includes("isDetailOpen"),
    "App.tsx must call useDocumentTitle with active state properties"
  );
});

test("Review History Header responsiveness and constraints", () => {
  const historyPath = path.join(__dirname, "../../pages/HistoryPage.tsx");
  const historyContent = fs.readFileSync(historyPath, "utf8");

  assert.ok(
    historyContent.includes("px-4 sm:px-6"),
    "HistoryPage container must use px-4 sm:px-6 to prevent 320px mobile overflow"
  );

  assert.ok(
    historyContent.includes("flex-wrap"),
    "Header container must include flex-wrap to prevent clipping at narrow widths"
  );

  assert.ok(
    historyContent.includes("w-full sm:w-auto") &&
      historyContent.includes("justify-start sm:justify-end"),
    "Action container must adapt between mobile full width and desktop end alignment"
  );

  assert.ok(
    historyContent.includes("whitespace-nowrap") && historyContent.includes("flex-shrink-0"),
    "Both action buttons must preserve their dimensions with whitespace-nowrap and flex-shrink-0"
  );

  assert.ok(
    historyContent.includes("Clear Audit") && historyContent.includes("disabled={reviews.length === 0"),
    "Clear Audit button must be present with disabled state when empty"
  );
});
