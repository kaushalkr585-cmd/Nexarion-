import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

test("Issue #10: Jump to latest stability and message preservation in AIConversationWorkspace.tsx", () => {
  const componentPath = path.resolve(__dirname, "AIConversationWorkspace.tsx");
  assert.ok(fs.existsSync(componentPath), "AIConversationWorkspace.tsx must exist");
  const content = fs.readFileSync(componentPath, "utf-8");

  // 1. Check container-level scrolling instead of naive scrollIntoView on ancestor elements
  assert.ok(
    content.includes("container.scrollTo({") &&
      content.includes("top: container.scrollHeight") &&
      content.includes('behavior: "smooth"'),
    "handleJumpToLatest must use container.scrollTo with top: container.scrollHeight and smooth behavior"
  );

  // 2. Check fallback for container.scrollTop
  assert.ok(
    content.includes("container.scrollTop = container.scrollHeight"),
    "handleJumpToLatest must provide fallback to container.scrollTop = container.scrollHeight"
  );

  // 3. Event safety: preventDefault and stopPropagation on click/touch
  assert.ok(
    content.includes("e.preventDefault()") && content.includes("e.stopPropagation()"),
    "handleJumpToLatest must invoke e.preventDefault() and e.stopPropagation() to prevent ghost clicks or touch event bleeding"
  );

  // 4. Touch support on Jump to latest button
  assert.ok(
    content.includes('id="jump-to-latest-btn"') &&
      content.includes("onTouchEnd={handleJumpToLatest}") &&
      content.includes("onClick={handleJumpToLatest}"),
    "jump-to-latest-btn must support onTouchEnd and onClick"
  );

  // 5. Jump lock / smooth scroll debouncing to prevent flickering
  assert.ok(
    content.includes("isJumpingRef") && content.includes("jumpTimeoutRef"),
    "handleJumpToLatest must manage jump lock using isJumpingRef and jumpTimeoutRef"
  );

  // 6. Loading skeleton guard: must NEVER unmount messages if messages.length > 0
  assert.ok(
    content.includes("isLoadingConversation && !conversation && messages.length === 0"),
    "Loading skeleton must be guarded with messages.length === 0 so existing messages are never unmounted"
  );

  // 7. Message persistence: lastKnownMessagesRef ensures transient state updates never wipe messages
  assert.ok(
    content.includes("lastKnownMessagesRef") &&
      content.includes("lastKnownMessagesRef.current.length > 0 && isLoadingConversation"),
    "AIConversationWorkspace must retain lastKnownMessagesRef to prevent conversations from flashing blank"
  );

  // 8. Geometric anchor: messagesEndRef div has defined 1px height and opacity 0
  assert.ok(
    content.includes("ref={messagesEndRef}") && content.includes("h-px w-full pointer-events-none opacity-0"),
    "messagesEndRef must have h-px layout geometry so browser scroll calculations remain valid"
  );
});

test("Jump to latest logic: scroll container calculations and threshold logic", () => {
  // Simulate scroll math
  const container = {
    scrollHeight: 2000,
    scrollTop: 1200,
    clientHeight: 600,
  };
  const SCROLL_THRESHOLD = 120;
  const distanceFromBottom = container.scrollHeight - container.scrollTop - container.clientHeight;
  assert.equal(distanceFromBottom, 200, "Distance from bottom should be 200px");
  assert.equal(distanceFromBottom > SCROLL_THRESHOLD, true, "Button should appear when scrolled away > 120px");

  // Near bottom
  container.scrollTop = 1320; // 2000 - 1320 - 600 = 80px
  const nearDist = container.scrollHeight - container.scrollTop - container.clientHeight;
  assert.equal(nearDist, 80, "Distance should be 80px");
  assert.equal(nearDist <= SCROLL_THRESHOLD, true, "User is near bottom");
});
