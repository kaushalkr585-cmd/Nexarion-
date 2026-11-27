import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

test("Issue: Mobile Pull Requests Page layout responsiveness and overflow prevention", () => {
  const pagePath = path.resolve(__dirname, "PullRequestsPage.tsx");
  assert.ok(fs.existsSync(pagePath), "PullRequestsPage.tsx must exist");
  const content = fs.readFileSync(pagePath, "utf-8");

  // 1. Container responsive sizing and box constraints
  assert.ok(
    content.includes("w-full max-w-6xl mx-auto px-3.5 sm:px-6") && content.includes("min-w-0 box-border"),
    "Outer container must use responsive padding (px-3.5 sm:px-6) and min-w-0 box-border to prevent overflow"
  );

  // 2. Responsive filter tabs: flex-1 on mobile, sm:flex-initial on desktop
  assert.ok(
    content.includes("w-full sm:w-auto") && content.includes("flex-1 sm:flex-initial"),
    "Filter tabs must use w-full sm:w-auto and each tab must be flex-1 sm:flex-initial to fit small viewports"
  );

  // 3. Status filter tabs must include all 4 filters
  assert.ok(
    content.includes('["all", "open", "merged", "closed"]'),
    "Filter tabs must support all, open, merged, closed filters"
  );

  // 4. PR cards must be flexible and constrained
  assert.ok(
    content.includes("glass-card p-3.5 sm:p-5 rounded-2xl flex flex-col sm:flex-row") &&
      content.includes("w-full min-w-0 box-border"),
    "PR card must use responsive padding (p-3.5 sm:p-5) and w-full min-w-0 box-border"
  );

  // 5. Repository name truncation
  assert.ok(
    content.includes("truncate") && content.includes("max-w-[180px]") && content.includes("pr.repository_name"),
    "Repository name must have responsive max-width and truncate with ellipsis"
  );

  // 6. PR title natural wrapping with overflow-wrap anywhere
  assert.ok(
    content.includes("break-words") && content.includes("[overflow-wrap:anywhere]"),
    "PR title must use break-words and [overflow-wrap:anywhere] to prevent long tokens from overflowing"
  );

  // 7. Source and target branch truncation
  assert.ok(
    content.includes("pr.source_branch") &&
      content.includes("pr.target_branch") &&
      content.includes("max-w-[100px]") &&
      content.includes("truncate inline-block"),
    "Branch names must be constrained with max-w and truncate inline-block"
  );

  // 8. Action button responsive width
  assert.ok(
    content.includes("w-full sm:w-auto") && content.includes("Run Agent Review"),
    "Run Agent Review button must use w-full sm:w-auto to fit cleanly inside mobile card"
  );

  // 9. Background sync indicator when refreshing cached PRs
  assert.ok(
    content.includes("isLoading && pullRequests.length > 0") && content.includes("Syncing..."),
    "PullRequestsPage must display subtle Syncing... indicator during background refresh"
  );
});

test("Issue: Pull Requests caching and stale-while-revalidate in App.tsx", () => {
  const appPath = path.resolve(__dirname, "../App.tsx");
  assert.ok(fs.existsSync(appPath), "App.tsx must exist");
  const content = fs.readFileSync(appPath, "utf-8");

  // 1. Session storage initialization for pullRequests
  assert.ok(
    content.includes('sessionStorage.getItem("nexarion_prs_cache")'),
    "App.tsx must initialize pullRequests state from nexarion_prs_cache"
  );

  // 2. Cache persistence upon fetch
  assert.ok(
    content.includes('sessionStorage.setItem("nexarion_prs_cache"'),
    "App.tsx must persist pull requests to nexarion_prs_cache"
  );

  // 3. Cache removal on logout
  assert.ok(
    content.includes('sessionStorage.removeItem("nexarion_prs_cache"'),
    "App.tsx must clear nexarion_prs_cache on logout/clearUserData"
  );

  // 4. Background refresh ref tracking
  assert.ok(
    content.includes("lastPrFetchRef"),
    "App.tsx must track lastPrFetchRef for cache invalidation"
  );
});

test("Issue: Backend parallel fetching and caching for pull requests", () => {
  const routesPath = path.resolve(__dirname, "../../../src/code_review/web/routes/pr_routes.py");
  assert.ok(fs.existsSync(routesPath), "pr_routes.py must exist");
  const routesContent = fs.readFileSync(routesPath, "utf-8");

  assert.ok(
    routesContent.includes("ThreadPoolExecutor") && routesContent.includes("as_completed"),
    "pr_routes.py must use ThreadPoolExecutor to fetch repo PRs concurrently"
  );

  const servicePath = path.resolve(__dirname, "../../../src/code_review/github/service.py");
  assert.ok(fs.existsSync(servicePath), "service.py must exist");
  const serviceContent = fs.readFileSync(servicePath, "utf-8");

  assert.ok(
    serviceContent.includes('self._cache.build_key(self.cache_scope, "list_pull_requests"') &&
      serviceContent.includes("self._cache.get(cache_key)") &&
      serviceContent.includes("self._cache.set(cache_key"),
    "service.py must cache list_pull_requests results in self._cache"
  );
});
