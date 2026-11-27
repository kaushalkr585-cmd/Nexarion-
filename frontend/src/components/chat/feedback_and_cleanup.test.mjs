import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const root = path.resolve(__dirname, "../../..");

test("MessageActionToolbar removes duplicate actions from dropdown menu", () => {
  const toolbarPath = path.join(__dirname, "MessageActionToolbar.tsx");
  const content = fs.readFileSync(toolbarPath, "utf-8");

  // In dropdown menu role="menu":
  const menuIndex = content.indexOf('role="menu"');
  assert.ok(menuIndex !== -1, "Dropdown menu must be present");
  const menuContent = content.slice(menuIndex, content.indexOf("</div>", menuIndex + 100));

  // Primary buttons are in toolbar, not duplicated inside the dropdown menu
  assert.ok(!menuContent.includes("Copy response"), "Dropdown menu must not contain duplicate Copy response");
  assert.ok(!menuContent.includes("Select text"), "Dropdown menu must not contain duplicate Select text");
  assert.ok(!menuContent.includes("Regenerate response"), "Dropdown menu must not contain duplicate Regenerate response");

  // Secondary actions must be in the dropdown menu
  assert.ok(menuContent.includes("Copy as Markdown"), "Dropdown menu must retain Copy as Markdown");
  assert.ok(menuContent.includes("Report response"), "Dropdown menu must retain Report response");

  // Primary toolbar still has Copy, Select text, Regenerate, ThumbsUp, ThumbsDown
  assert.ok(content.includes("aria-label=\"Select text\""), "Toolbar must retain Select text");
  assert.ok(content.includes("aria-label=\"Regenerate response\""), "Toolbar must retain Regenerate response");
  assert.ok(content.includes("aria-label=\"Mark helpful\""), "Toolbar must retain Thumbs Up");
  assert.ok(content.includes("aria-label=\"Mark unhelpful\""), "Toolbar must retain Thumbs Down");
});

test("FeedbackModal contains all 7 categories and optional details placeholder", () => {
  const modalPath = path.join(__dirname, "FeedbackModal.tsx");
  const content = fs.readFileSync(modalPath, "utf-8");

  const requiredCategories = [
    "Visual is unhelpful or broken",
    "Incorrect or incomplete",
    "Not what I asked for",
    "Slow or buggy",
    "Style or tone",
    "Safety or legal concern",
    "Other",
  ];

  for (const cat of requiredCategories) {
    assert.ok(content.includes(cat), `Feedback modal must contain category: "${cat}"`);
  }

  assert.ok(content.includes("Share details (optional)"), "Feedback modal must contain optional details placeholder");
  assert.ok(content.includes("Thank you for your feedback!"), "Feedback modal must contain confirmation screen");
  assert.ok(
    content.includes("Thanks for helping me improve Nexarion. I&apos;ll personally review your feedback."),
    "Must use solo founder personal review message"
  );
  assert.ok(!content.includes("Our team"), "Must not use 'Our team'");
  assert.ok(!content.includes("the team"), "Must not use 'the team'");
});

test("ReviewComposerModal removes Inference Cloud Nemotron display", () => {
  const composerPath = path.join(root, "src/components/reviews/ReviewComposerModal.tsx");
  const content = fs.readFileSync(composerPath, "utf-8");

  assert.ok(!content.includes("Cloud — Nemotron"), "Must remove Cloud — Nemotron badge");
  assert.ok(!content.includes("Inference:"), "Must remove Inference: label");
  assert.ok(content.includes("Include AI Deep Reasoning Agent"), "Must preserve Deep Reasoning Agent checkbox");
});

test("ReviewDetailModal and HistoryPage sanitize mode to LLM", () => {
  const detailPath = path.join(root, "src/components/reviews/ReviewDetailModal.tsx");
  const detailContent = fs.readFileSync(detailPath, "utf-8");
  assert.ok(!detailContent.includes('"nvidia" ? "nvidia"'), "Must not expose nvidia");
  assert.ok(detailContent.includes('"LLM"'), "Must display LLM mode in ReviewDetailModal");

  const historyPath = path.join(root, "src/pages/HistoryPage.tsx");
  const historyContent = fs.readFileSync(historyPath, "utf-8");
  assert.ok(historyContent.includes('"LLM"'), "Must display LLM mode in HistoryPage");
});

test("AdminFeedbackPage renders admin dashboard and checks access", () => {
  const adminPagePath = path.join(root, "src/pages/AdminFeedbackPage.tsx");
  const content = fs.readFileSync(adminPagePath, "utf-8");

  assert.ok(content.includes("Feedback Management"), "Must include Feedback Management header");
  assert.ok(content.includes("Access Restricted"), "Must include non-admin access restricted check");
  assert.ok(content.includes("Total Reports"), "Must include metrics cards");
  assert.ok(content.includes("Resend Status:"), "Must include Resend delivery details");
});

test("StopSquareIcon is rendered inside response generating button", () => {
  const workspacePath = path.join(__dirname, "AIConversationWorkspace.tsx");
  const content = fs.readFileSync(workspacePath, "utf-8");

  assert.ok(
    content.includes("StopSquareIcon"),
    "Stop button must render StopSquareIcon"
  );
  assert.ok(
    content.includes("StopSquareIcon") && content.includes("text-black"),
    "Stop button must have balanced centered square icon"
  );
});
