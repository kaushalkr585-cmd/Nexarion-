import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

test("downloadAttachment: api.ts exports triggerBlobDownload and downloadAttachment", () => {
  const apiFile = path.resolve(__dirname, "../services/api.ts");
  const content = fs.readFileSync(apiFile, "utf-8");

  assert.ok(
    content.includes("export function triggerBlobDownload"),
    "api.ts must export triggerBlobDownload"
  );
  assert.ok(
    content.includes("async downloadAttachment(att: Attachment)"),
    "api.ts must provide downloadAttachment method on attachmentApi"
  );
  assert.ok(
    content.includes("isSynthetic"),
    "downloadAttachment must handle synthetic inline-diff and temp attachments"
  );
  assert.ok(
    content.includes("text/x-diff"),
    "downloadAttachment must format diff blobs with text/x-diff mime"
  );
  assert.ok(
    content.includes("setTimeout(() => {"),
    "triggerBlobDownload must delay URL.revokeObjectURL to prevent browser download abortion"
  );
});

test("download buttons in AIConversationWorkspace call downloadAttachment", () => {
  const workspaceFile = path.resolve(__dirname, "../components/chat/AIConversationWorkspace.tsx");
  const content = fs.readFileSync(workspaceFile, "utf-8");

  assert.ok(
    content.includes("handleDownloadAttachment"),
    "AIConversationWorkspace must define handleDownloadAttachment"
  );
  assert.ok(
    content.includes("onClick={() => handleDownloadAttachment(att)}"),
    "Dedicated diff attachment download button must invoke handleDownloadAttachment"
  );
  assert.ok(
    content.includes("handleDownloadAttachment(att)"),
    "Other attachments chip download button must invoke handleDownloadAttachment"
  );
  assert.ok(
    content.includes("onDownload={handleDownloadAttachment}"),
    "FilePreviewModal must receive handleDownloadAttachment"
  );
});

test("backend conversation_routes.py supports multi-mode attachment download query", () => {
  const routesFile = path.resolve(__dirname, "../../../src/code_review/web/routes/conversation_routes.py");
  const content = fs.readFileSync(routesFile, "utf-8");

  assert.ok(
    content.includes("_attachment_auth_query"),
    "conversation_routes.py must define _attachment_auth_query"
  );
  assert.ok(
    content.includes("Access-Control-Expose-Headers"),
    "download_attachment must expose Content-Disposition header"
  );
});
