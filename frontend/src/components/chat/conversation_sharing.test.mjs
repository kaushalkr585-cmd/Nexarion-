import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import {
  DEFAULT_PRODUCTION_URL,
  getAppBaseUrl,
  getConversationShareUrl,
  normalizeShareUrl,
} from "../../utils/url.ts";
import { getViewFromPath } from "../../utils/router.ts";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

test("Conversation share URL configuration and generation", () => {
  assert.equal(
    DEFAULT_PRODUCTION_URL,
    "https://nexarion-4yio.onrender.com",
    "Production default URL must be https://nexarion-4yio.onrender.com"
  );

  const testId = "550e8400-e29b-41d4-a716-446655440000";
  const shareUrl = getConversationShareUrl(testId);

  assert.equal(
    shareUrl,
    `https://nexarion-4yio.onrender.com/c/${testId}`,
    "Generated share URL must use production domain and exact conversation UUID"
  );

  assert.ok(
    !shareUrl.includes("nexarion.com"),
    "Generated share URL must NOT reference the old nexarion.com placeholder domain"
  );
});

test("Legacy share URL normalization", () => {
  const legacyHttps = "https://nexarion.com/c/abc-123-uuid";
  const legacyHttp = "http://nexarion.com/c/abc-123-uuid";
  const legacyWww = "https://www.nexarion.com/c/abc-123-uuid";

  assert.equal(
    normalizeShareUrl(legacyHttps),
    "https://nexarion-4yio.onrender.com/c/abc-123-uuid"
  );
  assert.equal(
    normalizeShareUrl(legacyHttp),
    "https://nexarion-4yio.onrender.com/c/abc-123-uuid"
  );
  assert.equal(
    normalizeShareUrl(legacyWww),
    "https://nexarion-4yio.onrender.com/c/abc-123-uuid"
  );
});

test("Router extracts conversation ID from full production and legacy URLs", () => {
  const prodState = getViewFromPath("https://nexarion-4yio.onrender.com/c/conv-987-xyz");
  assert.equal(prodState.view, "chat");
  assert.equal(prodState.conversationId, "conv-987-xyz");

  const legacyState = getViewFromPath("https://nexarion.com/c/conv-987-xyz");
  assert.equal(legacyState.view, "chat");
  assert.equal(legacyState.conversationId, "conv-987-xyz");

  const directPathState = getViewFromPath("/c/conv-987-xyz");
  assert.equal(directPathState.view, "chat");
  assert.equal(directPathState.conversationId, "conv-987-xyz");
});

test("ConversationModals strictly avoids hardcoded nexarion.com and uses URL utility", () => {
  const modalsPath = path.join(__dirname, "ConversationModals.tsx");
  assert.ok(fs.existsSync(modalsPath), "ConversationModals.tsx must exist");
  const content = fs.readFileSync(modalsPath, "utf8");

  assert.equal(
    content.includes("nexarion.com"),
    false,
    "ConversationModals.tsx must not contain hardcoded nexarion.com"
  );

  assert.ok(
    content.includes("getConversationShareUrl"),
    "ShareModal must use getConversationShareUrl"
  );

  assert.ok(
    content.includes("conversationApi.share") || content.includes("is_shared: true"),
    "ShareModal must sync sharing state to backend"
  );
});

test("types.ts and api.ts support is_shared attribute", () => {
  const typesPath = path.join(__dirname, "../../types.ts");
  const typesContent = fs.readFileSync(typesPath, "utf8");
  assert.ok(
    typesContent.includes("is_shared?: boolean"),
    "Conversation interface in types.ts must include is_shared?: boolean"
  );

  const apiPath = path.join(__dirname, "../../services/api.ts");
  const apiContent = fs.readFileSync(apiPath, "utf8");
  assert.ok(
    apiContent.includes("share(id: string)"),
    "conversationApi in api.ts must provide share(id) method"
  );
});
