import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

test("Issue: New logo assets exist and are linked in index.html", () => {
  const publicDir = path.resolve(__dirname, "../../../public");
  assert.ok(fs.existsSync(path.join(publicDir, "logo.png")), "logo.png must exist in public/");
  assert.ok(fs.existsSync(path.join(publicDir, "favicon.svg")), "favicon.svg must exist in public/");
  assert.ok(fs.existsSync(path.join(publicDir, "favicon.ico")), "favicon.ico must exist in public/");
  assert.ok(fs.existsSync(path.join(publicDir, "favicon.png")), "favicon.png must exist in public/");

  const indexHtml = fs.readFileSync(path.resolve(__dirname, "../../../index.html"), "utf-8");
  assert.ok(indexHtml.includes('/favicon.svg'), "index.html must reference /favicon.svg");
  assert.ok(indexHtml.includes('/favicon.png'), "index.html must reference /favicon.png");
  assert.ok(indexHtml.includes('/favicon.ico'), "index.html must reference /favicon.ico");
});

test("Issue: LogoIcon in Icons.tsx references new logo asset", () => {
  const iconsPath = path.resolve(__dirname, "../icons/Icons.tsx");
  const iconsContent = fs.readFileSync(iconsPath, "utf-8");

  assert.ok(iconsContent.includes('src="/logo.png"'), "LogoIcon must reference /logo.png");
  assert.ok(iconsContent.includes('alt="Nexarion"'), "LogoIcon must maintain accessible alt text");
});

test("Issue: Assistant avatars and generating response state display new logo", () => {
  const workspacePath = path.resolve(__dirname, "AIConversationWorkspace.tsx");
  const workspaceContent = fs.readFileSync(workspacePath, "utf-8");

  assert.ok(workspaceContent.includes("<LogoIcon"), "AIConversationWorkspace must render LogoIcon in assistant avatar");
  assert.ok(!workspaceContent.includes('>NX<'), "AIConversationWorkspace must replace text 'NX' with LogoIcon");

  const indicatorPath = path.resolve(__dirname, "AdaptiveStatusIndicator.tsx");
  const indicatorContent = fs.readFileSync(indicatorPath, "utf-8");

  assert.ok(indicatorContent.includes("<LogoIcon"), "AdaptiveStatusIndicator must render LogoIcon in status avatar");
  assert.ok(!indicatorContent.includes('>NX<'), "AdaptiveStatusIndicator must replace text 'NX' with LogoIcon");
});
