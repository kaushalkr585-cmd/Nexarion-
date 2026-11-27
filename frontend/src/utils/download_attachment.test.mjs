import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { FilePreviewModal } from "../components/chat/FilePreviewModal.tsx";

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

test("FilePreviewModal portals above mobile header stacking context with sticky header and 100dvh responsive layout", () => {
  const modalPath = path.resolve(__dirname, "../components/chat/FilePreviewModal.tsx");
  const src = fs.readFileSync(modalPath, "utf-8");

  assert.ok(
    src.includes("createPortal(modalContent, document.body)"),
    "FilePreviewModal must portal to document.body to escape <main z-10> stacking context"
  );
  assert.ok(
    src.includes("z-[70]"),
    "FilePreviewModal overlay must use z-[70] to appear above mobile header (z-30) and sidebar (z-50)"
  );
  assert.ok(
    src.includes("h-[100dvh]") && src.includes("md:max-h-[90dvh]"),
    "FilePreviewModal must fill 100dvh on mobile and preserve md:max-h-[90dvh] on desktop"
  );
  assert.ok(
    src.includes("sticky top-0 z-20") && src.includes("safe-area-inset-top"),
    "FilePreviewModal header must be sticky with z-20 and safe-area-inset-top support"
  );
  assert.ok(
    src.includes("flex-1 min-h-0 overflow-y-auto") && src.includes("overscroll-y-contain"),
    "Diff scroll container must enforce flex-1 min-h-0 overflow-y-auto without fixed 280px min-height"
  );
  assert.ok(
    !src.includes("min-h-[280px]"),
    "FilePreviewModal must not lock body min-height to 280px which breaks landscape viewports"
  );
  assert.ok(
    src.includes("overflow-x-auto overscroll-x-contain") && src.includes("whitespace-pre"),
    "Diff viewer must support horizontal scrolling for long code lines"
  );
  assert.ok(
    src.includes("min-h-[40px] min-w-[40px]"),
    "Download and Close buttons must provide >=40px mobile tap targets"
  );
});

test("FilePreviewModal renders diff header with filename, Download button, Close button, and styled diff lines", () => {
  const longDiff = [
    "diff --git a/src/auth/verify.ts b/src/auth/verify.ts",
    "@@ -10,4 +10,5 @@ export function verifyToken(token: string) {",
    "-  return jwt.decode(token);",
    "+  return jwt.verify(token, process.env.SECRET_KEY || 'very-long-horizontal-diff-line-testing-mobile-scrolling-without-clipping-header-buttons');",
    " }",
  ].join("\n");

  const html = renderToStaticMarkup(
    React.createElement(FilePreviewModal, {
      isOpen: true,
      onClose: () => {},
      onDownload: () => {},
      attachment: {
        id: "inline-diff-123",
        filename: "very-long-pull-request-authentication-patch-changes.diff",
        file_type: "diff",
        file_size: longDiff.length,
        status: "ready",
        content: longDiff,
      },
    })
  );

  assert.ok(
    html.includes("very-long-pull-request-authentication-patch-changes.diff"),
    "Renders diff filename in header"
  );
  assert.ok(html.includes("Unified Diff"), "Renders Unified Diff type label");
  assert.ok(
    html.includes('aria-label="Download very-long-pull-request-authentication-patch-changes.diff"'),
    "Renders accessible Download button"
  );
  assert.ok(html.includes('aria-label="Close preview"'), "Renders accessible Close button");
  assert.ok(
    html.includes("bg-emerald-950/40") &&
      html.includes("bg-red-950/40") &&
      html.includes("bg-cyan-950/40"),
    "Renders added, removed, and hunk diff styling"
  );
});
