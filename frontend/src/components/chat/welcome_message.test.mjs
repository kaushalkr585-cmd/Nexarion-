import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

test("NEXARION_WELCOME_MESSAGE constant is correctly defined", async () => {
  const constantsPath = path.resolve(__dirname, "../../constants.ts");
  assert.ok(fs.existsSync(constantsPath), "constants.ts should exist");
  const content = fs.readFileSync(constantsPath, "utf-8");

  const expected = "I'm Nexarion, your coding assistant and code reviewer. How can I help?";
  assert.ok(
    content.includes(expected),
    `constants.ts must define exact welcome message: ${expected}`
  );

  assert.ok(!content.includes("Kaushal"), "Welcome message must not contain developer name");
  assert.ok(!content.includes("NVIDIA"), "Welcome message must not contain model name");
  assert.ok(!content.includes("Ollama"), "Welcome message must not contain provider name");
});

test("AIConversationWorkspace provides clean, purposeful new-chat welcome experience", () => {
  const workspacePath = path.resolve(__dirname, "AIConversationWorkspace.tsx");
  const content = fs.readFileSync(workspacePath, "utf-8");

  assert.ok(
    content.includes("animate-greeting-heading"),
    "AIConversationWorkspace must render greeting heading"
  );
  assert.ok(
    content.includes("animate-greeting-subtitle"),
    "AIConversationWorkspace must render greeting subtitle"
  );

  assert.ok(
    !content.includes('data-testid="nexarion-welcome-message"'),
    "AIConversationWorkspace must not render repetitive assistant welcome message bubble"
  );

  assert.ok(
    content.includes("animate-greeting-cards"),
    "AIConversationWorkspace must preserve greeting action cards"
  );
  assert.ok(
    content.includes("Start a Pull Request Review"),
    "AIConversationWorkspace must preserve PR review action card"
  );
});

test("System prompt includes consistent coding assistant and code reviewer role without scripted repetitiveness", () => {
  const routesPath = path.resolve(
    __dirname,
    "../../../../src/code_review/web/routes/conversation_routes.py"
  );
  const content = fs.readFileSync(routesPath, "utf-8");

  assert.ok(
    content.includes("You are Nexarion, an AI coding assistant and code reviewer created by Kaushal."),
    "System prompt must identify Nexarion as coding assistant and code reviewer created by Kaushal"
  );

  assert.ok(
    content.includes("Code explanations and programming assistance."),
    "System prompt must include code explanations specialization"
  );
  assert.ok(
    content.includes("Debugging and troubleshooting."),
    "System prompt must include debugging specialization"
  );
  assert.ok(
    content.includes("Pull request and diff reviews."),
    "System prompt must include pull request and diff reviews specialization"
  );
  assert.ok(
    content.includes("Security vulnerability identification."),
    "System prompt must include security specialization"
  );
  assert.ok(
    content.includes("Code quality and maintainability."),
    "System prompt must include code quality specialization"
  );
  assert.ok(
    content.includes("Performance analysis."),
    "System prompt must include performance analysis specialization"
  );
  assert.ok(
    content.includes("Documentation and development workflows."),
    "System prompt must include documentation specialization"
  );

  assert.ok(
    content.includes("Vary your wording organically rather than repeating a fixed"),
    "System prompt must enforce organic variation"
  );
});
