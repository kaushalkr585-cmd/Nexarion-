import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

test("Issue: Mobile Review History Page layout responsiveness and overflow prevention", () => {
  const pagePath = path.resolve(__dirname, "HistoryPage.tsx");
  assert.ok(fs.existsSync(pagePath), "HistoryPage.tsx must exist");
  const content = fs.readFileSync(pagePath, "utf-8");

  // 1. Container responsive sizing and box constraints
  assert.ok(
    content.includes("w-full max-w-6xl mx-auto px-4 sm:px-6") &&
      content.includes("min-w-0 box-border overflow-x-hidden"),
    "Outer container must use responsive padding (px-4 sm:px-6), min-w-0 box-border, and overflow-x-hidden"
  );

  // 2. Header responsiveness
  assert.ok(
    content.includes("min-w-0 flex-1 max-w-2xl") && content.includes("break-words"),
    "Header must have min-w-0 flex-1 and break-words on description"
  );

  // 3. Action buttons
  assert.ok(
    content.includes("w-full sm:w-auto") && content.includes("justify-start sm:justify-end"),
    "Action container must adapt between mobile full width and desktop end alignment"
  );

  // 4. Review cards must be flexible and constrained
  assert.ok(
    content.includes("glass-card p-3.5 sm:p-5 rounded-2xl flex flex-col sm:flex-row") &&
      content.includes("w-full min-w-0 box-border"),
    "Review card must use responsive padding (p-3.5 sm:p-5) and w-full min-w-0 box-border"
  );

  // 5. Repository name truncation
  assert.ok(
    content.includes("truncate") &&
      content.includes("max-w-[180px]") &&
      content.includes("block min-w-0"),
    "Repository name must have responsive max-width, truncate, and block min-w-0"
  );

  // 6. Review title natural wrapping with overflow-wrap anywhere
  assert.ok(
    content.includes("break-words") && content.includes("[overflow-wrap:anywhere]"),
    "Review title must use break-words and [overflow-wrap:anywhere] to prevent long tokens from overflowing"
  );

  // 7. Metadata line wrapping
  assert.ok(
    content.includes("flex-wrap") && content.includes("min-w-0 max-w-full"),
    "Metadata line must be flexible and wrap gracefully"
  );

  // 8. Bottom/right action bar responsiveness
  assert.ok(
    content.includes("w-full sm:w-auto") &&
      content.includes("justify-between sm:justify-end") &&
      content.includes("shrink-0"),
    "Action bar must be w-full sm:w-auto with justify-between on mobile and shrink-0 items"
  );
});

test("Issue: Review History overflow-x-hidden container in App.tsx", () => {
  const appPath = path.resolve(__dirname, "../App.tsx");
  assert.ok(fs.existsSync(appPath), "App.tsx must exist");
  const content = fs.readFileSync(appPath, "utf-8");

  assert.ok(
    content.includes('currentView === "history"') &&
      content.includes("overflow-x-hidden"),
    "App.tsx must include overflow-x-hidden on history view wrapper"
  );
});
