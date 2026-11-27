import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";

const ROOT = path.resolve(import.meta.dirname, "../..");
const typesSource = fs.readFileSync(path.join(ROOT, "types.ts"), "utf8");
const apiSource = fs.readFileSync(path.join(ROOT, "services/api.ts"), "utf8");
const appSource = fs.readFileSync(path.join(ROOT, "App.tsx"), "utf8");
const statusSource = fs.readFileSync(
  path.join(ROOT, "components/chat/AdaptiveStatusIndicator.tsx"),
  "utf8"
);

test("ChatMode union and Conversation.mode are defined cleanly in types.ts", () => {
  assert.match(typesSource, /export type ChatMode\s*=\s*"normal"\s*\|\s*"github";/);
  assert.match(typesSource, /export interface Conversation[\s\S]*mode\?: ChatMode;/);
});

test("conversationApi sends explicit mode on create, send, regenerate, edit, stream, and update calls", () => {
  for (const methodSig of [
    "async create(",
    "async sendMessage(",
    "async regenerate(",
    "async streamMessage(",
    "async streamRegenerate(",
    "async editMessage(",
    "async streamEditMessage(",
    "async update(",
  ]) {
    const start = apiSource.indexOf(methodSig);
    assert.ok(start !== -1, `Missing ${methodSig} in api.ts`);
    const slice = apiSource.slice(start, start + 1800);
    assert.match(slice, /\bmode\b/, `${methodSig} must accept/serialize explicit mode`);
  }

  // Ensure default resolution never quietly escalates to github
  assert.match(
    apiSource,
    /const effectiveMode: ChatMode = payload\.mode \?\? \(payload\.githubMode \? "github" : "normal"\);/
  );
  // Preserve required onSaved block in streamEditMessage
  assert.match(
    apiSource,
    /if \(callbacks\.onSaved\) \{\r?\n\s+callbacks\.onSaved\(\);\r?\n\s+\}/
  );
});

test("App.tsx enforces strict per-conversation mode isolation and never auto-escalates from repo context", () => {
  assert.match(appSource, /const \[githubMode, setGithubMode\] = useState<boolean>\(false\);/);
  assert.match(
    appSource,
    /const conversationModesRef = useRef<Map<string, ChatMode>>\(new Map\(\)\);/
  );

  // When activeConversationId becomes empty, GitHub mode and live status reset to normal/null
  const effectStart = appSource.indexOf("useEffect(() => {\r\n    if (!activeConversationId)") !== -1
    ? appSource.indexOf("useEffect(() => {\r\n    if (!activeConversationId)")
    : appSource.indexOf("useEffect(() => {\n    if (!activeConversationId)");
  assert.ok(effectStart !== -1, "Missing !activeConversationId effect");
  const effectBody = appSource.slice(effectStart, effectStart + 1800);
  assert.match(effectBody, /setGithubMode\(false\);/);
  assert.match(effectBody, /setLiveStatusDetail\(null\);/);

  // Fetching prior repo context must NEVER forcibly enable GitHub Mode
  const getRepoCall = effectBody.indexOf("getConversationRepo(requestedId)");
  assert.ok(getRepoCall !== -1);
  const getRepoBlock = effectBody.slice(getRepoCall, getRepoCall + 350);
  assert.ok(
    !getRepoBlock.includes("setGithubMode(true)"),
    "getConversationRepo must not force setGithubMode(true)"
  );

  // Loading conversation detail applies server-persisted mode
  assert.match(effectBody, /const convMode: ChatMode = conv\.mode === "github" \? "github" : "normal";/);
  assert.match(effectBody, /setGithubMode\(convMode === "github"\);/);

  // New chat resets GitHub mode and status cleanly
  const newChatStart = appSource.indexOf("const handleNewChat = useCallback");
  assert.ok(newChatStart !== -1);
  const newChatBlock = appSource.slice(newChatStart, newChatStart + 700);
  assert.match(newChatBlock, /setActiveRepoContext\(null\);/);
  assert.match(newChatBlock, /setGithubMode\(false\);/);
  assert.match(newChatBlock, /setLiveStatusDetail\(null\);/);

  // Send, regenerate, and edit handlers transmit explicit mode and scope activeRepoContext to github mode
  assert.match(appSource, /mode:\s*requestMode,/);
  assert.match(
    appSource,
    /requestMode === "github" \? activeRepoContext\?\.repository_full_name : undefined/
  );

  // Switching GitHub mode persists mode via PATCH /api/conversations/{id}
  assert.match(
    appSource,
    /conversationApi\.update\(activeConversationId,\s*\{\s*mode:\s*nextMode\s*\}\)/
  );
});

test("AdaptiveStatusIndicator default status rotation contains zero GitHub inspection phrases", () => {
  const lower = statusSource.toLowerCase();
  for (const forbidden of [
    "planning github",
    "connecting to github",
    "discovering repositories",
    "inspecting repository",
  ]) {
    assert.ok(!lower.includes(forbidden), `Forbidden status text in AdaptiveStatusIndicator: ${forbidden}`);
  }
});
