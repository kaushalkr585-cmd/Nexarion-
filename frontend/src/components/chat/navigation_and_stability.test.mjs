import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

test("router.ts exports valid route mapper and path generator", async () => {
  const routerPath = path.resolve(__dirname, "../../utils/router.ts");
  assert.ok(fs.existsSync(routerPath), "router.ts must exist");
  const content = fs.readFileSync(routerPath, "utf-8");

  assert.ok(content.includes("getViewFromPath"), "router.ts must export getViewFromPath");
  assert.ok(content.includes("getPathFromView"), "router.ts must export getPathFromView");
  assert.ok(content.includes("/pull-requests"), "router.ts must map pull-requests");
  assert.ok(content.includes("/overview"), "router.ts must map overview");
  assert.ok(content.includes("/agents"), "router.ts must map agents");
  assert.ok(content.includes("/review-history"), "router.ts must map review-history");
  assert.ok(content.includes("/settings"), "router.ts must map settings");
  assert.ok(content.includes("/c/"), "router.ts must map conversation paths");
});

test("App.tsx does not auto-select first conversation on login or load", () => {
  const appPath = path.resolve(__dirname, "../../App.tsx");
  const content = fs.readFileSync(appPath, "utf-8");

  assert.ok(
    !content.includes("setActiveConversationId(convList[0].id)"),
    "App.tsx must not auto-select convList[0].id"
  );

  assert.ok(
    content.includes("getViewFromPath"),
    "App.tsx must use getViewFromPath to restore route from URL"
  );
  assert.ok(
    content.includes("getPathFromView"),
    "App.tsx must use getPathFromView for history push/replace state"
  );

  assert.ok(
    content.includes("activeConvIdRef.current === requestedId"),
    "App.tsx must guard conversation detail fetch against stale active ID"
  );

  assert.ok(
    content.includes("nexarion_conversations_cache"),
    "App.tsx must cache conversations in sessionStorage"
  );
});

test("Sidebar.tsx supports loading skeleton indicator", () => {
  const sidebarPath = path.resolve(__dirname, "../layout/Sidebar.tsx");
  const content = fs.readFileSync(sidebarPath, "utf-8");

  assert.ok(
    content.includes("isLoadingConversations"),
    "Sidebar.tsx must accept isLoadingConversations prop"
  );
  assert.ok(
    content.includes("conversations-loading-skeleton"),
    "Sidebar.tsx must render skeleton when loading"
  );
});

test("ReviewComposerModal.tsx supports asynchronous diff loading and observable stages", () => {
  const composerPath = path.resolve(__dirname, "../reviews/ReviewComposerModal.tsx");
  const content = fs.readFileSync(composerPath, "utf-8");

  assert.ok(
    content.includes("isLoadingDiff"),
    "ReviewComposerModal must accept isLoadingDiff prop"
  );
  assert.ok(
    content.includes("reviewStage"),
    "ReviewComposerModal must display observable review stages"
  );
  assert.ok(
    content.includes("Preparing review context..."),
    "ReviewComposerModal must include stage 1 text"
  );
  assert.ok(
    content.includes("Running specialized agents"),
    "ReviewComposerModal must include stage 2 text"
  );
});
