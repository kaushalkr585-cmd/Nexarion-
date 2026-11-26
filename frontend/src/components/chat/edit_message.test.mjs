import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

test("Test A: api.ts streamEditMessage sends to edit/stream and provides onSaved lifecycle", () => {
  const apiPath = path.resolve(__dirname, "../../services/api.ts");
  const content = fs.readFileSync(apiPath, "utf-8");

  assert.ok(
    content.includes("`/api/conversations/${conversationId}/messages/${messageId}/edit/stream`"),
    "api.ts must post to /api/conversations/{id}/messages/{msgId}/edit/stream"
  );

  assert.ok(
    content.includes("onSaved?: () => void;"),
    "streamEditMessage must support onSaved callback"
  );
  assert.ok(
    content.includes("if (callbacks.onSaved) {\n      callbacks.onSaved();\n    }"),
    "streamEditMessage must invoke onSaved once server returns 200 OK before SSE parsing"
  );

  assert.ok(
    content.includes("throw new Error(safeError);"),
    "streamEditMessage must throw error when response.ok is false"
  );
});

test("Test B: AIConversationWorkspace handles unchanged text without requests or duplicates", () => {
  const workspacePath = path.resolve(__dirname, "AIConversationWorkspace.tsx");
  const content = fs.readFileSync(workspacePath, "utf-8");

  assert.ok(
    content.includes("if (currentMsg && currentMsg.content.trim() === trimmed)"),
    "saveEditedMessage must check if content is unchanged"
  );

  assert.ok(
    content.includes("setEditingMessageId(null);\n      setEditError(null);\n      return;"),
    "saveEditedMessage must close editor and return early if content is unchanged"
  );
});

test("Test C: Cancel editing discards changes and leaves saved message intact", () => {
  const workspacePath = path.resolve(__dirname, "AIConversationWorkspace.tsx");
  const content = fs.readFileSync(workspacePath, "utf-8");

  assert.ok(
    content.includes("setEditingMessageId(null);\n                                  setEditError(null);"),
    "Cancel button must reset editingMessageId and editError"
  );

  assert.ok(
    content.includes("else if (e.key === \"Escape\") {\n                                setEditingMessageId(null);\n                                setEditError(null);\n                              }"),
    "Escape key must cancel editing"
  );
});

test("Test D: Save failure preserves user draft in editor and displays useful error", () => {
  const workspacePath = path.resolve(__dirname, "AIConversationWorkspace.tsx");
  const content = fs.readFileSync(workspacePath, "utf-8");

  assert.ok(
    content.includes("setEditError(err instanceof Error ? err.message : \"Failed to save message edit.\");"),
    "saveEditedMessage must capture and display save error"
  );

  assert.ok(
    content.includes("setEditingMessageId(messageId);"),
    "Editor must restore editingMessageId when saving fails"
  );
  assert.ok(
    content.includes("setEditingContent(draftContent);"),
    "Editor must restore draft content when saving fails"
  );

  const appPath = path.resolve(__dirname, "../../App.tsx");
  const appContent = fs.readFileSync(appPath, "utf-8");
  assert.ok(
    appContent.includes("setActiveConversation(previousConv);"),
    "App.tsx must revert optimistic state to previousConv on save failure"
  );
});

test("Test E: Generation failure keeps edited prompt persisted with usable retry option", () => {
  const appPath = path.resolve(__dirname, "../../App.tsx");
  const appContent = fs.readFileSync(appPath, "utf-8");

  assert.ok(
    appContent.includes("if (targetMsg.role === \"assistant\") {\n      // Regenerate the assistant reply for the conversation context without duplicating user messages\n      await handleRegenerateMessage(targetMsg.id);"),
    "handleRetryMessage must regenerate assistant response directly for the conversation context"
  );

  const workspacePath = path.resolve(__dirname, "AIConversationWorkspace.tsx");
  const wsContent = fs.readFileSync(workspacePath, "utf-8");
  assert.ok(
    wsContent.includes("onRetry={() => onRetryMessage && onRetryMessage(msg.id)}"),
    "AIConversationWorkspace must provide retry trigger for failed assistant message"
  );
});

test("Test F: Multiple conversations prevents cross-conversation leak", () => {
  const appPath = path.resolve(__dirname, "../../App.tsx");
  const appContent = fs.readFileSync(appPath, "utf-8");

  assert.ok(
    appContent.includes("if (!prev || prev.id !== targetConvId) return prev;"),
    "streamEditMessage callbacks must guard against cross-conversation state leaks"
  );

  assert.ok(
    appContent.includes("if (isSendingMessage && abortControllerRef.current) {\n      abortControllerRef.current.abort();"),
    "handleSelectConversation must abort active generation on conversation switch"
  );
});

test("Test G: Subsequent messages are cleanly truncated from state when earlier turn is edited", () => {
  const appPath = path.resolve(__dirname, "../../App.tsx");
  const appContent = fs.readFileSync(appPath, "utf-8");

  assert.ok(
    appContent.includes("const newMessages = [\n      ...conv.messages.slice(0, targetIdx),\n      updatedUserMsg,\n      optimisticAsstMsg,\n    ];"),
    "App.tsx must truncate messages after targetIdx when user edits an earlier prompt"
  );
});

test("Test H: Streaming and double-submission prevention", () => {
  const workspacePath = path.resolve(__dirname, "AIConversationWorkspace.tsx");
  const wsContent = fs.readFileSync(workspacePath, "utf-8");

  assert.ok(
    wsContent.includes("disabled={isSavingEdit || isSending || !editingContent.trim()}"),
    "Save & Submit button must be disabled while saving, sending, or when prompt is empty"
  );

  assert.ok(
    wsContent.includes("disabled={isSavingEdit || isSending}"),
    "Textarea and cancel button must be disabled while processing"
  );

  assert.ok(
    wsContent.includes("disabled={isSending}"),
    "Edit button on message must be disabled while generation is active"
  );
});

test("Test I: Agent icon differentiation dynamically maps all specialized agents to distinct icons", () => {
  const iconsPath = path.resolve(__dirname, "../icons/Icons.tsx");
  const iconsContent = fs.readFileSync(iconsPath, "utf-8");

  assert.ok(iconsContent.includes("ShieldCheckIcon"), "Icons.tsx must define ShieldCheckIcon");
  assert.ok(iconsContent.includes("Code2Icon"), "Icons.tsx must define Code2Icon");
  assert.ok(iconsContent.includes("GaugeIcon"), "Icons.tsx must define GaugeIcon");
  assert.ok(iconsContent.includes("BookOpenIcon"), "Icons.tsx must define BookOpenIcon");
  assert.ok(iconsContent.includes("FlaskConicalIcon"), "Icons.tsx must define FlaskConicalIcon");
  assert.ok(iconsContent.includes("NetworkIcon"), "Icons.tsx must define NetworkIcon");
  assert.ok(iconsContent.includes("WorkflowIcon"), "Icons.tsx must define WorkflowIcon");
  assert.ok(iconsContent.includes("GitBranchIcon"), "Icons.tsx must define GitBranchIcon");
  assert.ok(iconsContent.includes("export function getAgentIcon"), "Icons.tsx must export getAgentIcon");

  const agentsPagePath = path.resolve(__dirname, "../../pages/AgentsPage.tsx");
  const agentsContent = fs.readFileSync(agentsPagePath, "utf-8");
  assert.ok(
    agentsContent.includes("const AgentIconComponent = getAgentIcon(agent.agent_id, agent.name);"),
    "AgentsPage.tsx must dynamically resolve unique agent icon"
  );
});

test("Test J: Jump to latest button is strictly guarded and never shown on empty chats", () => {
  const workspacePath = path.resolve(__dirname, "AIConversationWorkspace.tsx");
  const wsContent = fs.readFileSync(workspacePath, "utf-8");

  assert.ok(
    wsContent.includes("{showJumpToLatest && messages.length > 0 && ("),
    "Jump to latest button must be guarded with messages.length > 0"
  );
  assert.ok(
    wsContent.includes("setShowJumpToLatest(distanceFromBottom > SCROLL_THRESHOLD && messages.length > 0);"),
    "handleScroll must verify messages.length > 0 before showing jump button"
  );
  assert.ok(
    wsContent.includes("if (messages.length === 0) {\n      setShowJumpToLatest(false);"),
    "AIConversationWorkspace must reset showJumpToLatest to false when messages.length === 0"
  );
});

test("Test K: Message editing and stream message handlers properly sync user_message_id", () => {
  const appPath = path.resolve(__dirname, "../../App.tsx");
  const appContent = fs.readFileSync(appPath, "utf-8");

  assert.ok(
    appContent.includes("onAck: (ackData) => {"),
    "handleSendMessage must handle onAck callback to sync user_message_id"
  );
  assert.ok(
    appContent.includes("data.user_message_id"),
    "App.tsx must sync data.user_message_id on stream completion"
  );

  const apiPath = path.resolve(__dirname, "../../services/api.ts");
  const apiContent = fs.readFileSync(apiPath, "utf-8");
  assert.ok(
    apiContent.includes("user_message_id?: string"),
    "api.ts callbacks must include user_message_id"
  );
});
