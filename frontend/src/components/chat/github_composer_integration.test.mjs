import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

test("ComposerIntegrationsMenu implements ChatGPT-style plus menu with GitHub", () => {
  const menuPath = path.join(__dirname, "ComposerIntegrationsMenu.tsx");
  assert.ok(fs.existsSync(menuPath), "ComposerIntegrationsMenu.tsx must exist");
  const content = fs.readFileSync(menuPath, "utf-8");

  assert.ok(content.includes("GitHub"), "Menu must display GitHub integration");
  assert.ok(
    content.includes("Inspect repositories, analyze code, explore pull requests, issues and commits."),
    "Menu must include exact GitHub description"
  );
  assert.ok(content.includes("Attach File"), "Menu must preserve Attach File tool");
  assert.ok(content.includes("Attach Diff"), "Menu must preserve Attach Diff tool");
  assert.ok(!content.includes("Search integrations..."), "Menu must not include Search integrations bar");
  assert.ok(content.includes("Escape"), "Menu must close on Escape");
  assert.ok(content.includes("ArrowDown"), "Menu must support keyboard ArrowDown navigation");
  assert.ok(content.includes("ArrowUp"), "Menu must support keyboard ArrowUp navigation");
});

test("AIConversationWorkspace implements GPT-style plus trigger, GitHub chip, connection state, and repo selection", () => {
  const wsPath = path.join(__dirname, "AIConversationWorkspace.tsx");
  const content = fs.readFileSync(wsPath, "utf-8");

  assert.ok(content.includes('data-plus-menu-trigger="true"'), "Must expose GPT-style plus menu trigger");
  assert.ok(content.includes("ComposerIntegrationsMenu"), "Must render ComposerIntegrationsMenu");
  assert.ok(content.includes("githubMode"), "Must support githubMode state");
  assert.ok(
    content.includes('aria-label="Remove GitHub integration"'),
    "Must render removable [GitHub x] chip"
  );
  assert.ok(
    content.includes("Connect GitHub"),
    "Must show Connect GitHub guidance when GitHub mode is enabled while disconnected"
  );
  assert.ok(
    content.includes("repoCandidates") && content.includes("onSelectRepoCandidate"),
    "Must render inline repository selection cards inside chat stream"
  );
  assert.ok(
    content.includes("overrideMessage={liveStatusDetail}") || content.includes("liveStatusDetail"),
    "Must display real-time progress steps via AdaptiveStatusIndicator"
  );
});

test("App.tsx wires GitHub mode, repo context, status streaming, and GitHub OAuth auth", () => {
  const appPath = path.join(__dirname, "..", "..", "App.tsx");
  const content = fs.readFileSync(appPath, "utf-8");

  assert.ok(content.includes("githubMode"), "App.tsx must manage githubMode");
  assert.ok(content.includes("activeRepoContext"), "App.tsx must track conversation repository context");
  assert.ok(content.includes("onStatus:"), "App.tsx must handle SSE status events");
  assert.ok(content.includes("onRepoSelect:"), "App.tsx must handle SSE repo_select events");
  assert.ok(content.includes("onRepoMeta:"), "App.tsx must handle SSE repo_meta events");
  assert.ok(content.includes("getAuthUrl"), "App.tsx must support GitHub OAuth authorization flow");
});
