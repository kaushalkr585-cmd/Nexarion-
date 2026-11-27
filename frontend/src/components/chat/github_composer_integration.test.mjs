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

test("Prompt composer applies pure-white directional neon border without blocking input or animating", () => {
  const wsPath = path.join(__dirname, "AIConversationWorkspace.tsx");
  const wsContent = fs.readFileSync(wsPath, "utf-8");
  assert.ok(
    wsContent.includes("nx-prompt-glow-box"),
    "AIConversationWorkspace.tsx prompt <form> must include nx-prompt-glow-box class"
  );

  const cssPath = path.resolve(__dirname, "../../index.css");
  const cssContent = fs.readFileSync(cssPath, "utf-8");
  const glowSection = cssContent.slice(cssContent.indexOf(".nx-prompt-glow-box"));

  assert.ok(glowSection.includes(".nx-prompt-glow-box::before"), "Must style ::before border layer");
  assert.ok(glowSection.includes(".nx-prompt-glow-box::after"), "Must style ::after blur bloom layer");
  assert.ok(glowSection.includes("mask-composite: exclude"), "Must mask gradients to border ring only");
  assert.ok(glowSection.includes("overflow: visible;"), "Must preserve overflow: visible");
  assert.ok(glowSection.includes("pointer-events: none;"), "Pseudo-elements must never intercept clicks or typing");
  assert.ok(!glowSection.includes("animation:"), "Prompt glow must not animate or pulse");
});

test("Prompt composer buttons inside message box are balanced and compact", () => {
  const wsPath = path.join(__dirname, "AIConversationWorkspace.tsx");
  const wsContent = fs.readFileSync(wsPath, "utf-8");

  assert.ok(
    !wsContent.includes("w-11 h-11 rounded-full"),
    "Send / Stop button must not use oversized w-11 h-11 rounded-full"
  );
  assert.ok(
    !wsContent.includes("w-10 h-10 rounded-full"),
    "Plus button must not use oversized w-10 h-10 rounded-full"
  );
  assert.ok(
    wsContent.includes("w-8 h-8 sm:w-9 sm:h-9"),
    "Buttons inside prompt box must be compact (w-8 h-8 sm:w-9 sm:h-9)"
  );
});

test("Prompt composer textarea stays at default single-line height when empty on mobile and desktop", () => {
  const wsPath = path.join(__dirname, "AIConversationWorkspace.tsx");
  const wsContent = fs.readFileSync(wsPath, "utf-8");

  assert.ok(
    wsContent.includes("if (!input || !input.trim())"),
    "adjustTextareaHeight must lock textarea to minHeight when input is empty or whitespace"
  );
  assert.ok(
    wsContent.includes("textarea.style.height = `${minHeight}px`"),
    "Empty textarea must immediately use minHeight rather than unbounded scrollHeight"
  );
  assert.ok(
    wsContent.includes("min-h-[36px] sm:min-h-[40px]"),
    "Textarea must define responsive minimum height baseline"
  );
  assert.ok(
    wsContent.includes("placeholder:truncate"),
    "Textarea placeholder must truncate without multiline phantom wrapping"
  );
});
