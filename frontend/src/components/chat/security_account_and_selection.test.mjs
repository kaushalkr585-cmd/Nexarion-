import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { evaluatePasswordStrength } from "../../utils/passwordStrength.ts";
import {
  computeFloatingCoordinates,
  extractValidChatSelection,
  isNodeIgnoredForAskNexarion,
} from "./AskNexarionSelectionHandler.tsx";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

function makeNode({ tagName = "DIV", attrs = {}, parent = null, children = [] } = {}) {
  const node = {
    nodeType: 1,
    tagName,
    attributes: attrs,
    parentElement: parent,
    isContentEditable: attrs.contenteditable === "true",
    getAttribute(key) {
      return this.attributes[key] ?? null;
    },
    contains(target) {
      let cur = target;
      while (cur) {
        if (cur === this) return true;
        cur = cur.parentElement;
      }
      return false;
    },
    closest(selector) {
      const parts = selector.split(",").map((s) => s.trim());
      let cur = this;
      while (cur) {
        for (const p of parts) {
          if (p === cur.tagName.toLowerCase()) return cur;
          const attrMatch = p.match(/^\[([a-z0-9-]+)(?:='([^']*)')?\]$/i);
          if (attrMatch) {
            const [, attrName, attrVal] = attrMatch;
            const actual = cur.attributes?.[attrName];
            if (attrVal !== undefined ? actual === attrVal : actual !== undefined) {
              return cur;
            }
          }
        }
        cur = cur.parentElement;
      }
      return null;
    },
    querySelectorAll() {
      return children;
    },
  };
  return node;
}

test("Password strength evaluator scores common/short/personal passwords as weak and passphrases as strong", () => {
  const tooShort = evaluatePasswordStrength("Ab1!xy", { name: "Kushal", email: "k@nexarion.dev" });
  assert.equal(tooShort.acceptable, false);
  assert.ok(["Very Weak", "Weak"].includes(tooShort.label));

  const common = evaluatePasswordStrength("password1234", { name: "Dev", email: "dev@example.com" });
  assert.equal(common.acceptable, false);
  assert.equal(common.checks.notCommon, false);

  const personal = evaluatePasswordStrength("kushal-harbor-velvet-moon", {
    name: "Kushal Kumar",
    email: "kushal@example.com",
  });
  assert.equal(personal.acceptable, false);
  assert.equal(personal.checks.noPersonalInfo, false);

  const sequence = evaluatePasswordStrength("abcdef123456!", { name: "Dev" });
  assert.equal(sequence.acceptable, false);
  assert.equal(sequence.checks.noPredictableSequence, false);

  const passphrase = evaluatePasswordStrength("correct-horse-battery-staple", {
    name: "Alice Dev",
    email: "alice@example.com",
  });
  assert.equal(passphrase.acceptable, true);
  assert.ok(["Strong", "Very Strong"].includes(passphrase.label));
});

test("Contextual Ask Nexarion selection guard scopes strictly to chat messages and excludes code blocks/sidebar/settings/composer", () => {
  const originalDoc = globalThis.document;
  globalThis.document = { activeElement: null };

  try {
    const chatContainer = makeNode({ tagName: "DIV" });
    const assistantBubble = makeNode({
      tagName: "DIV",
      attrs: { "data-ask-nexarion-selectable": "true", "data-message-id": "msg-asst-1" },
      parent: chatContainer,
    });
    const assistantParagraph = makeNode({ tagName: "P", parent: assistantBubble });

    const userBubble = makeNode({
      tagName: "DIV",
      attrs: { "data-ask-nexarion-selectable": "true", "data-message-id": "msg-user-1" },
      parent: chatContainer,
    });

    const codeBlockWrapper = makeNode({
      tagName: "DIV",
      attrs: { "data-code-block": "true", "data-ask-nexarion-ignore": "true" },
      parent: assistantBubble,
    });
    const preNode = makeNode({ tagName: "PRE", parent: codeBlockWrapper });
    const codeTextParent = makeNode({ tagName: "CODE", parent: preNode });

    const sidebarNode = makeNode({ tagName: "ASIDE" });
    const headerNode = makeNode({ tagName: "HEADER" });
    const settingsNode = makeNode({ tagName: "SECTION", attrs: { id: "settings-profile" } });
    const composerTextarea = makeNode({ tagName: "TEXTAREA", parent: null });

    const mkSel = (text, startNode, endNode = startNode) => ({
      isCollapsed: false,
      rangeCount: 1,
      toString: () => text,
      getRangeAt: () => ({
        startContainer: startNode,
        endContainer: endNode,
        commonAncestorContainer: startNode === endNode ? startNode : chatContainer,
        getBoundingClientRect: () => ({ top: 220, bottom: 242, left: 300, width: 140, height: 22 }),
      }),
    });

    // 1. Assistant response selection -> allowed
    const asstValid = extractValidChatSelection(
      mkSel("Refresh tokens to manage user sessions.", assistantParagraph),
      chatContainer
    );
    assert.ok(asstValid);
    assert.equal(asstValid.text, "Refresh tokens to manage user sessions.");
    assert.equal(asstValid.messageId, "msg-asst-1");

    // 2. User message selection -> allowed
    const userValid = extractValidChatSelection(
      mkSel("Explain JWT authentication", userBubble),
      chatContainer
    );
    assert.ok(userValid);
    assert.equal(userValid.messageId, "msg-user-1");

    // 3. Code blocks inside chat -> rejected
    assert.equal(
      extractValidChatSelection(mkSel("const jwt = require('jwt');", codeTextParent), chatContainer),
      null
    );
    assert.equal(isNodeIgnoredForAskNexarion(codeTextParent), true);

    // 4. Sidebar / Header / Settings / Composer -> rejected
    assert.equal(extractValidChatSelection(mkSel("Sidebar item", sidebarNode), chatContainer), null);
    assert.equal(extractValidChatSelection(mkSel("Header title", headerNode), chatContainer), null);
    assert.equal(extractValidChatSelection(mkSel("Danger Zone", settingsNode), chatContainer), null);
    assert.equal(extractValidChatSelection(mkSel("Draft question", composerTextarea), chatContainer), null);

    // 5. Focused input/textarea -> rejected
    globalThis.document = { activeElement: composerTextarea };
    assert.equal(
      extractValidChatSelection(mkSel("Inside focus", assistantParagraph), chatContainer),
      null
    );
  } finally {
    globalThis.document = originalDoc;
  }
});

test("Floating Ask Nexarion coordinate calculation flips below header and clamps horizontally", () => {
  const nearTop = computeFloatingCoordinates(
    { top: 20, bottom: 44, left: 10, width: 60, height: 24 },
    { width: 390, height: 844 },
    { width: 320, height: 220 }
  );
  assert.equal(nearTop.placement, "below");
  assert.ok(nearTop.top >= 70, "Must avoid covering top header");
  assert.ok(nearTop.left >= 12 && nearTop.left + 320 <= 378, "Must stay within viewport");
});

test("Frontend components wire Auth visibility toggle, PasswordStrengthMeter, Settings sections, DeleteAccountModal, and Ask Nexarion", () => {
  const authModal = fs.readFileSync(path.join(__dirname, "..", "modals", "AuthModal.tsx"), "utf-8");
  assert.ok(authModal.includes("PasswordInput"));
  assert.ok(authModal.includes("PasswordStrengthMeter"));
  assert.ok(authModal.includes("Forgot password?"));

  const pwdInput = fs.readFileSync(path.join(__dirname, "..", "auth", "PasswordInput.tsx"), "utf-8");
  assert.ok(pwdInput.includes("Show password") && pwdInput.includes("Hide password"));

  const settings = fs.readFileSync(path.join(__dirname, "..", "..", "pages", "SettingsPage.tsx"), "utf-8");
  assert.ok(settings.includes("Profile"));
  assert.ok(settings.includes("Security"));
  assert.ok(settings.includes("Connected Accounts"));
  assert.ok(!settings.includes("Google Authentication"));
  assert.ok(settings.includes("Danger Zone"));
  assert.ok(settings.includes("DeleteAccountModal"));
  assert.ok(settings.includes("SettingsSectionHeader"));

  const sidebar = fs.readFileSync(path.join(__dirname, "..", "layout", "Sidebar.tsx"), "utf-8");
  assert.ok(!sidebar.includes('onSelectView("overview")'), "Sidebar logo/title must not open overview");
  assert.ok(!sidebar.includes('onSelectView("chat")'), "Sidebar logo/title must not open chat/new chat");
  assert.ok(!sidebar.includes("Go to Overview dashboard"), "Sidebar logo/title must stay static non-clickable branding");

  const deleteModal = fs.readFileSync(path.join(__dirname, "..", "modals", "DeleteAccountModal.tsx"), "utf-8");
  assert.ok(deleteModal.includes("DELETE"));
  assert.ok(deleteModal.includes("Verify with Google"));
  assert.ok(deleteModal.includes("Verify with GitHub"));
  assert.ok(deleteModal.includes("Final Confirmation"));

  const workspace = fs.readFileSync(path.join(__dirname, "AIConversationWorkspace.tsx"), "utf-8");
  assert.ok(workspace.includes("AskNexarionSelectionHandler"));
  assert.ok(workspace.includes("data-ask-nexarion-selectable"));
  assert.ok(workspace.includes("useLayoutEffect"));
  assert.ok(workspace.includes("visualViewport"));
  assert.ok(!workspace.includes('maxHeight: "200px"'));

  const appSource = fs.readFileSync(path.join(__dirname, "..", "..", "App.tsx"), "utf-8");
  assert.ok(!appSource.includes("Go to Overview dashboard"), "Mobile brand header must stay static non-clickable branding");
});
