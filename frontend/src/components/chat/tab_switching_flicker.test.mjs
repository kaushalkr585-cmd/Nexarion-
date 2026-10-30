import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

test("index.css defines smooth anti-flicker fadeIn animation without vertical jumping", () => {
  const cssPath = path.resolve(__dirname, "../../index.css");
  assert.ok(fs.existsSync(cssPath), "index.css must exist");
  const css = fs.readFileSync(cssPath, "utf-8");

  assert.ok(css.includes(".animate-fade-in"), "index.css must define .animate-fade-in");
  assert.ok(css.includes("0.15s ease-out"), ".animate-fade-in must be short and crisp (0.15s)");

  const fadeInMatch = css.match(/@keyframes fadeIn\s*\{([^}]+)\}/);
  assert.ok(fadeInMatch, "index.css must define @keyframes fadeIn");
  assert.ok(fadeInMatch[1].includes("opacity: 0.9"), "@keyframes fadeIn must not flash from black/transparent");
  assert.ok(!fadeInMatch[1].includes("translateY"), "@keyframes fadeIn must not jump vertically");
});

test("Top-level pages remove root animate-fade-in to prevent flashing on route transitions", () => {
  const pages = [
    { name: "OverviewPage.tsx", path: path.resolve(__dirname, "../../pages/OverviewPage.tsx") },
    { name: "PullRequestsPage.tsx", path: path.resolve(__dirname, "../../pages/PullRequestsPage.tsx") },
    { name: "AgentsPage.tsx", path: path.resolve(__dirname, "../../pages/AgentsPage.tsx") },
    { name: "HistoryPage.tsx", path: path.resolve(__dirname, "../../pages/HistoryPage.tsx") },
    { name: "SettingsPage.tsx", path: path.resolve(__dirname, "../../pages/SettingsPage.tsx") },
  ];

  for (const page of pages) {
    assert.ok(fs.existsSync(page.path), `${page.name} must exist`);
    const content = fs.readFileSync(page.path, "utf-8");

    assert.ok(
      !content.includes('space-y-6 animate-fade-in') && !content.includes('space-y-8 animate-fade-in'),
      `${page.name} root container must not use animate-fade-in`
    );
  }
});

test("Top-level views and Sidebar are memoized with React.memo to avoid unneeded re-renders", () => {
  const components = [
    { name: "OverviewPage.tsx", path: path.resolve(__dirname, "../../pages/OverviewPage.tsx") },
    { name: "PullRequestsPage.tsx", path: path.resolve(__dirname, "../../pages/PullRequestsPage.tsx") },
    { name: "AgentsPage.tsx", path: path.resolve(__dirname, "../../pages/AgentsPage.tsx") },
    { name: "HistoryPage.tsx", path: path.resolve(__dirname, "../../pages/HistoryPage.tsx") },
    { name: "SettingsPage.tsx", path: path.resolve(__dirname, "../../pages/SettingsPage.tsx") },
    { name: "Sidebar.tsx", path: path.resolve(__dirname, "../layout/Sidebar.tsx") },
    { name: "AIConversationWorkspace.tsx", path: path.resolve(__dirname, "AIConversationWorkspace.tsx") },
  ];

  for (const comp of components) {
    assert.ok(fs.existsSync(comp.path), `${comp.name} must exist`);
    const content = fs.readFileSync(comp.path, "utf-8");
    assert.ok(
      content.includes("React.memo("),
      `${comp.name} must be wrapped in React.memo for high-performance rendering`
    );
  }
});

test("PullRequestsPage keeps loaded pull requests visible during background updates (anti-flicker)", () => {
  const prPagePath = path.resolve(__dirname, "../../pages/PullRequestsPage.tsx");
  const content = fs.readFileSync(prPagePath, "utf-8");

  assert.ok(
    content.includes("isLoading && pullRequests.length === 0"),
    "PullRequestsPage skeleton must only show when pullRequests is empty"
  );

  assert.ok(
    content.includes("pullRequests.length > 0 || !isLoading"),
    "PullRequestsPage must keep existing PR cards mounted during revalidation"
  );
});

test("OverviewPage keeps metrics visible during background updates (anti-flicker)", () => {
  const overviewPagePath = path.resolve(__dirname, "../../pages/OverviewPage.tsx");
  const content = fs.readFileSync(overviewPagePath, "utf-8");

  assert.ok(
    content.includes("{metrics && ("),
    "OverviewPage must render metrics when available regardless of background isLoading"
  );
  assert.ok(
    !content.includes("{metrics && !isLoading && ("),
    "OverviewPage must not unmount metrics when background refresh occurs"
  );
});

test("App.tsx preserves AIConversationWorkspace in DOM and keeps active conversation on tab switch", () => {
  const appPath = path.resolve(__dirname, "../../App.tsx");
  const content = fs.readFileSync(appPath, "utf-8");

  assert.ok(
    content.includes('currentView === "chat"') && content.includes('"hidden"'),
    "App.tsx must keep AIConversationWorkspace mounted and toggle with hidden class"
  );

  assert.ok(
    content.includes('min-h-[61px] border-b border-white/10'),
    "App.tsx desktop top bar must align height (min-h-[61px]) to prevent layout shift"
  );

  assert.ok(
    content.includes("handleSelectView"),
    "App.tsx must define handleSelectView"
  );
  assert.ok(
    content.includes("activeConvIdRef.current"),
    "App.tsx must preserve activeConvIdRef across view switches"
  );

  assert.ok(
    content.includes("const navigateTo = useCallback("),
    "App.tsx must memoize navigateTo with useCallback"
  );
  assert.ok(
    content.includes("const handleSelectView = useCallback("),
    "App.tsx must memoize handleSelectView with useCallback"
  );
  assert.ok(
    content.includes("const handleNewChat = useCallback("),
    "App.tsx must memoize handleNewChat with useCallback"
  );
  assert.ok(
    content.includes("const handleSelectConversation = useCallback("),
    "App.tsx must memoize handleSelectConversation with useCallback"
  );
});

test("Sidebar.tsx uses transition-colors for smooth, non-stuttering tab switches", () => {
  const sidebarPath = path.resolve(__dirname, "../layout/Sidebar.tsx");
  const content = fs.readFileSync(sidebarPath, "utf-8");

  assert.ok(
    content.includes("transition-colors text-left cursor-pointer"),
    "Sidebar navigation buttons must use transition-colors instead of transition-all"
  );
});
