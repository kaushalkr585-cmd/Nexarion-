import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

test("Issue 1 & 2: App shell and persistent mobile header ensure fixed toggle and independent scrolling", () => {
  const cssPath = path.resolve(__dirname, "../../index.css");
  assert.ok(fs.existsSync(cssPath), "index.css must exist");
  const cssContent = fs.readFileSync(cssPath, "utf-8");

  assert.ok(
    cssContent.includes("html, body") && cssContent.includes("height: 100dvh") && cssContent.includes("overflow: hidden"),
    "index.css must configure html, body with height: 100dvh and overflow: hidden"
  );
  assert.ok(
    cssContent.includes("#root") && cssContent.includes("overflow: hidden"),
    "index.css must configure #root with overflow: hidden"
  );
  assert.ok(
    cssContent.includes(".overscroll-y-contain") && cssContent.includes("overscroll-behavior-y: contain"),
    "index.css must define .overscroll-y-contain utility"
  );

  const appPath = path.resolve(__dirname, "../../App.tsx");
  const appContent = fs.readFileSync(appPath, "utf-8");

  assert.ok(
    appContent.includes("Persistent Mobile Header Bar") || appContent.includes("<header className=\"md:hidden"),
    "App.tsx must contain persistent mobile header"
  );
  assert.ok(
    appContent.includes("w-11 h-11") && appContent.includes("aria-label={isMobileNavOpen ? \"Close sidebar\" : \"Open sidebar\"}"),
    "Sidebar toggle in App.tsx must have accessible label and 44x44px touch target (w-11 h-11)"
  );

  assert.ok(
    appContent.includes("safe-area-inset-top"),
    "Mobile header must respect env(safe-area-inset-top)"
  );

  assert.ok(
    appContent.includes("isMobileMenuOpen"),
    "App.tsx must provide a mobile overflow menu for secondary actions"
  );

  assert.ok(
    appContent.includes("overscroll-y-contain"),
    "Non-chat views container must include overscroll-y-contain"
  );
});

test("Issue 4: Mobile Sidebar operates as responsive navigation drawer", () => {
  const sidebarPath = path.resolve(__dirname, "../layout/Sidebar.tsx");
  assert.ok(fs.existsSync(sidebarPath), "Sidebar.tsx must exist");
  const sidebarContent = fs.readFileSync(sidebarPath, "utf-8");

  assert.ok(
    sidebarContent.includes("max-w-[320px]") && sidebarContent.includes("w-[85vw]"),
    "Sidebar drawer must use comfortable responsive width (85vw max-w-[320px])"
  );

  assert.ok(
    sidebarContent.includes("Mobile Backdrop") && sidebarContent.includes("isMobileOpen"),
    "Sidebar must render backdrop when isMobileOpen is true"
  );

  assert.ok(
    sidebarContent.includes("document.body.style.overflow = \"hidden\""),
    "Sidebar must lock body scroll when mobile drawer is open"
  );
  assert.ok(
    sidebarContent.includes("e.key === \"Escape\""),
    "Sidebar must listen for Escape key to close mobile drawer"
  );

  assert.ok(
    sidebarContent.includes("w-11 h-11") && sidebarContent.includes("aria-label=\"Close sidebar\""),
    "Mobile drawer close button must have ~44x44px touch target and aria-label"
  );

  assert.ok(
    sidebarContent.includes("overscroll-y-contain"),
    "Sidebar drawer navigation list must use overscroll-y-contain"
  );
});

test("Issue 2, 3 & 5: AIConversationWorkspace confines scrolling and eliminates mobile congestion", () => {
  const workspacePath = path.resolve(__dirname, "AIConversationWorkspace.tsx");
  assert.ok(fs.existsSync(workspacePath), "AIConversationWorkspace.tsx must exist");
  const content = fs.readFileSync(workspacePath, "utf-8");

  assert.ok(
    content.includes("hidden md:flex flex-shrink-0 items-center justify-between px-6 py-4"),
    "AIConversationWorkspace desktop header must be hidden on mobile (hidden md:flex)"
  );

  assert.ok(
    content.includes("overflow-y-auto overscroll-y-contain"),
    "Conversation message list must have overscroll-y-contain"
  );

  assert.ok(
    content.includes("safe-area-inset-bottom"),
    "Composer container must respect env(safe-area-inset-bottom)"
  );

  assert.ok(
    content.includes("hidden sm:flex items-center justify-between mt-2 px-2 text-[10px]"),
    "Keyboard shortcuts caption must be hidden on mobile to conserve screen space"
  );

  assert.ok(
    content.includes("min-w-[42px] min-h-[42px]"),
    "Send button must maintain min 42px touch target"
  );
  assert.ok(
    content.includes("min-w-[38px] min-h-[38px]"),
    "Attachment tool buttons must maintain touch targets"
  );
});

test("Issue 5C: Markdown code blocks and message bubbles prevent horizontal overflow", () => {
  const mdPath = path.resolve(__dirname, "MarkdownContent.tsx");
  assert.ok(fs.existsSync(mdPath), "MarkdownContent.tsx must exist");
  const mdContent = fs.readFileSync(mdPath, "utf-8");

  assert.ok(
    mdContent.includes("w-full max-w-full") && mdContent.includes("overflow-x-auto"),
    "MarkdownContent must constrain code blocks to max-w-full with overflow-x-auto"
  );
  assert.ok(
    mdContent.includes("overscroll-x-contain"),
    "MarkdownContent must contain horizontal scrolling within code blocks"
  );

  const cssPath = path.resolve(__dirname, "../../index.css");
  const cssContent = fs.readFileSync(cssPath, "utf-8");

  assert.ok(
    cssContent.includes("overflow-wrap: break-word") && cssContent.includes("word-break: break-word"),
    "index.css .chat-message-content must enforce word break to prevent text blowout"
  );
});

test("Mobile 3-dots overflow menu auto-closes on outside tap, backdrop tap, and Escape key", () => {
  const appPath = path.resolve(__dirname, "../../App.tsx");
  assert.ok(fs.existsSync(appPath), "App.tsx must exist");
  const appContent = fs.readFileSync(appPath, "utf-8");

  assert.ok(
    appContent.includes("ref={mobileMenuRef}"),
    "3-dots menu wrapper must attach mobileMenuRef"
  );

  assert.ok(
    appContent.includes("mobileMenuRef.current.contains(event.target as Node)") &&
      appContent.includes("setIsMobileMenuOpen(false)"),
    "App.tsx must check mobileMenuRef.contains to auto-close 3-dots menu on outside taps"
  );

  assert.ok(
    appContent.includes("event.key === \"Escape\"") &&
      appContent.includes("setIsMobileMenuOpen(false)"),
    "App.tsx must listen for Escape key to close mobile 3-dots menu"
  );

  assert.ok(
    appContent.includes("Tap-anywhere backdrop to auto-close 3-dots mobile menu") &&
      appContent.includes("isMobileMenuOpen"),
    "App.tsx must render full-screen tap-anywhere backdrop when isMobileMenuOpen is true"
  );
});
