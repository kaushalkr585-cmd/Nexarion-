import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const utilsPath = path.join(__dirname, "../../utils/selectionPrompt.ts");
const componentPath = path.join(__dirname, "AskNexarionSelectionHandler.tsx");
const { formatSelectionPrompt, isTargetExcluded } = await import(
  `file://${utilsPath.replace(/\\/g, "/")}`
);

test("formatSelectionPrompt: formats plain statement with clear quotation", () => {
  const selectedText = "The orchestrator runs deterministic agents sequentially.";
  const prompt = formatSelectionPrompt(selectedText);

  assert.equal(
    prompt,
    'Explain this statement in simple terms:\n\n"The orchestrator runs deterministic agents sequentially."'
  );
});

test("formatSelectionPrompt: trims leading and trailing whitespace", () => {
  const selectedText = "   Cross-file semantic dependencies must be verified.   \n  ";
  const prompt = formatSelectionPrompt(selectedText);

  assert.equal(
    prompt,
    'Explain this statement in simple terms:\n\n"Cross-file semantic dependencies must be verified."'
  );
});

test("formatSelectionPrompt: returns empty string for empty or whitespace selection", () => {
  assert.equal(formatSelectionPrompt(""), "");
  assert.equal(formatSelectionPrompt("     \n\t  "), "");
});

test("formatSelectionPrompt: detects and formats code blocks preserving exact indentation", () => {
  const codeSnippet = `def authenticate_user(token: str) -> bool:
    if not token or len(token) < 16:
        return False
    return verify_hmac_signature(token)`;

  const prompt = formatSelectionPrompt(codeSnippet);

  assert.ok(
    prompt.startsWith("Explain this code and how it works:\n\n```\n"),
    "Prompt must start with code explanation header and triple backticks"
  );
  assert.ok(
    prompt.includes(codeSnippet),
    "Prompt must preserve the code snippet verbatim including indentation"
  );
  assert.ok(prompt.endsWith("\n```"), "Prompt must terminate with triple backticks");
});

test("formatSelectionPrompt: detects single-line code with programming syntax", () => {
  const codeLine = "const [user, setUser] = useState<User | null>(null);";
  const prompt = formatSelectionPrompt(codeLine);

  assert.ok(
    prompt.includes("```\nconst [user, setUser] = useState<User | null>(null);\n```"),
    "Code line with syntax should be wrapped in code block"
  );
});

test("isTargetExcluded: correctly identifies excluded interactive elements", () => {

  const mockInputElement = {
    nodeType: 1,
    closest: (selector) => (selector.includes("input") ? {} : null),
  };
  assert.equal(isTargetExcluded(mockInputElement), true);

  const mockTextareaElement = {
    nodeType: 1,
    closest: (selector) => (selector.includes("textarea") ? {} : null),
  };
  assert.equal(isTargetExcluded(mockTextareaElement), true);

  const mockButtonElement = {
    nodeType: 1,
    closest: (selector) => (selector.includes("button") ? {} : null),
  };
  assert.equal(isTargetExcluded(mockButtonElement), true);

  const mockFloatingBtnElement = {
    nodeType: 1,
    closest: (selector) => (selector.includes(".ask-nexarion-floating-btn") ? {} : null),
  };
  assert.equal(isTargetExcluded(mockFloatingBtnElement), true);

  const mockContextMenuElement = {
    nodeType: 1,
    closest: (selector) => (selector.includes(".nexarion-context-menu") ? {} : null),
  };
  assert.equal(isTargetExcluded(mockContextMenuElement), true);

  const mockParagraphElement = {
    nodeType: 1,
    closest: () => null,
  };
  assert.equal(isTargetExcluded(mockParagraphElement), false);
});

test("AskNexarionSelectionHandler component meets UI and accessibility standards", () => {
  const fileContent = fs.readFileSync(componentPath, "utf8");

  assert.ok(fileContent.includes("Ask Nexarion"), "Component must display 'Ask Nexarion'");
  assert.ok(fileContent.includes("<LogoIcon"), "Component must display Nexarion LogoIcon");

  assert.ok(
    fileContent.includes("e.preventDefault()") && fileContent.includes("onMouseDown"),
    "Component must prevent default on mousedown to preserve browser selection"
  );

  assert.ok(
    fileContent.includes('role="button"') && fileContent.includes("tabIndex={0}"),
    "Component must have role='button' and tabIndex={0}"
  );
  assert.ok(
    fileContent.includes("onKeyDown"),
    "Component must support keyboard interactions (Enter, Space, Escape)"
  );

  assert.ok(
    fileContent.includes("Math.min") && fileContent.includes("Math.max"),
    "Component must calculate clamped coordinates inside viewport"
  );
});

test("App.tsx and AIConversationWorkspace integration", () => {
  const appPath = path.join(__dirname, "../../App.tsx");
  const appContent = fs.readFileSync(appPath, "utf8");

  const workspacePath = path.join(__dirname, "AIConversationWorkspace.tsx");
  const workspaceContent = fs.readFileSync(workspacePath, "utf8");

  assert.ok(
    appContent.includes("AskNexarionSelectionHandler"),
    "App.tsx must import AskNexarionSelectionHandler"
  );

  assert.ok(
    appContent.includes("handleAskNexarion") &&
      appContent.includes("setPendingComposerPrompt") &&
      appContent.includes('navigateTo("chat")'),
    "App.tsx must handle Ask Nexarion by navigating to chat and setting pending prompt"
  );

  assert.ok(
    workspaceContent.includes("initialPrompt?: string | null;"),
    "AIConversationWorkspaceProps must include initialPrompt"
  );

  assert.ok(
    workspaceContent.includes("setInput") &&
      workspaceContent.includes("adjustTextareaHeight") &&
      workspaceContent.includes("textareaRef.current.focus"),
    "AIConversationWorkspace must focus and auto-expand composer on initialPrompt arrival"
  );
});
