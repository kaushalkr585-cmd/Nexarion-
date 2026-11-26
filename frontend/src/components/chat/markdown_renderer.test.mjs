import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import { MarkdownContent } from "./MarkdownContent.tsx";
import {
  normalizeCodeLanguage,
  preprocessMarkdown,
  sanitizeLinkHref,
  splitMarkdownBlocks,
} from "./markdownUtils.ts";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

function renderMarkdown(content, isStreaming = false) {
  return renderToStaticMarkup(
    React.createElement(MarkdownContent, { content, isStreaming })
  );
}

test("MarkdownContent renders all heading levels H1-H6, GFM formatting, nested lists, task lists, blockquotes, links, and inline code", () => {
  const md = [
    "# Heading One",
    "## Heading Two",
    "### Heading Three",
    "#### Heading Four",
    "##### Heading Five",
    "###### Heading Six",
    "",
    "Paragraph with **bold**, *italic*, ~~strikethrough~~, inline `const x = 42`, and [Nexarion Docs](https://example.com/docs).",
    "",
    "- Top bullet A",
    "  - Nested bullet A1",
    "    - Deep nested bullet A2",
    "- Top bullet B",
    "",
    "1. Ordered step one",
    "   1. Nested step 1a",
    "2. Ordered step two",
    "",
    "- [x] Verify authentication",
    "- [ ] Deploy update",
    "",
    "> Blockquote insight with **emphasis** and `inline()`.",
    "",
    "---",
  ].join("\n");

  const html = renderMarkdown(md);

  assert.ok(html.includes("<h1") && html.includes("Heading One"), "Renders H1");
  assert.ok(html.includes("<h2") && html.includes("Heading Two"), "Renders H2");
  assert.ok(html.includes("<h3") && html.includes("Heading Three"), "Renders H3");
  assert.ok(html.includes("<h4") && html.includes("Heading Four"), "Renders H4");
  assert.ok(html.includes("<h5") && html.includes("Heading Five"), "Renders H5");
  assert.ok(html.includes("<h6") && html.includes("Heading Six"), "Renders H6");
  assert.ok(html.includes("<strong") && html.includes("bold"), "Renders bold");
  assert.ok(html.includes("<em") && html.includes("italic"), "Renders italic");
  assert.ok(html.includes("<del") && html.includes("strikethrough"), "Renders strikethrough");
  assert.ok(html.includes("<code") && html.includes("const x = 42"), "Renders inline code");
  assert.ok(
    html.includes('href="https://example.com/docs"') &&
      html.includes('rel="noopener noreferrer"'),
    "Renders safe external link"
  );
  assert.ok(html.includes("<ul") && html.includes("Nested bullet A1"), "Renders nested ul");
  assert.ok(html.includes("<ol") && html.includes("Nested step 1a"), "Renders nested ol");
  assert.ok(
    html.includes('type="checkbox"') && html.includes("checked"),
    "Renders task list checkboxes"
  );
  assert.ok(html.includes("<blockquote"), "Renders blockquote");
  assert.ok(html.includes("<hr"), "Renders horizontal rule");
  assert.ok(!html.includes("## Heading Two"), "Does not leak raw Markdown headings");
  assert.ok(!html.includes("~~strikethrough~~"), "Does not leak raw strikethrough syntax");
});

test("MarkdownContent renders responsive GFM tables with alignment and horizontal scroll wrapper", () => {
  const md = [
    "| Component | Complexity | Notes |",
    "| :--- | :---: | ---: |",
    "| `AuthMiddleware` | $O(1)$ | Validates JWT signature and `token_version` |",
    "| `SemanticSearch` | $O(n \\log n)$ | Cross-file AST dependency traversal |",
  ].join("\n");

  const html = renderMarkdown(md);
  assert.ok(html.includes("overflow-x-auto overscroll-x-contain"), "Wraps table in horizontal scroll container");
  assert.ok(html.includes("<table"), "Renders real HTML table");
  assert.ok(html.includes("<thead") && html.includes("<th"), "Renders table header");
  assert.ok(html.includes("<tbody") && html.includes("<td"), "Renders table rows");
  assert.ok(
    html.includes("text-center") && html.includes("text-right"),
    "Applies GFM column alignment"
  );
  assert.ok(
    html.includes("text-align:center") && html.includes("text-align:right"),
    "Applies GFM inline style alignment"
  );
  assert.ok(html.includes("AuthMiddleware"), "Renders table cell inline code cleanly");
});

test("CodeBlock renders language labels, Copy code button, and syntax highlighting across languages", () => {
  const md = [
    "```python",
    "def compute_score(items: list[int]) -> float:",
    "    return sum(items) / max(len(items), 1)",
    "```",
    "",
    "```typescript",
    "export interface ReviewResult {",
    "  severity: 'high' | 'medium' | 'low';",
    "}",
    "```",
    "",
    "```sql",
    "SELECT id, status FROM feedback_reports WHERE status = 'new';",
    "```",
    "",
    "```bash",
    "npm run build && uvicorn code_review.web.app:app --port 8000",
    "```",
  ].join("\n");

  const html = renderMarkdown(md);
  assert.ok(html.includes("Python") && html.includes("language-python"), "Highlights Python");
  assert.ok(html.includes("TypeScript") && html.includes("language-typescript"), "Highlights TypeScript");
  assert.ok(html.includes("SQL") && html.includes("language-sql"), "Highlights SQL");
  assert.ok(html.includes("Bash") && html.includes("language-bash"), "Highlights Bash");
  assert.ok(html.includes("hljs-keyword"), "Emits hljs syntax tokens");
  assert.ok(html.includes("Copy code"), "Includes Copy code action button");
  assert.ok(
    html.includes('data-code-block="true"') && html.includes('data-ask-nexarion-ignore="true"'),
    "Preserves Ask Nexarion ignore markers on code blocks"
  );
  assert.deepEqual(normalizeCodeLanguage("cpp"), { id: "cpp", label: "C++" });
  assert.deepEqual(normalizeCodeLanguage("json"), { id: "json", label: "JSON" });
});

test("MarkdownContent renders KaTeX inline and display math while protecting currency and code", () => {
  const md = [
    "Inline math $x_i^2 + \\alpha \\beta$ and paren math \\( \\frac{a}{b} \\).",
    "",
    "Display summation:",
    "$$",
    "\\sum_{i=1}^{n} i = \\frac{n(n+1)}{2}",
    "$$",
    "",
    "Bracket display:",
    "\\[ \\Omega(n \\log n) \\]",
    "",
    "Currency stays literal: Price is between $50 and $100 today, and `$HOME` stays verbatim.",
  ].join("\n");

  const html = renderMarkdown(md);
  assert.ok(html.includes('class="katex"'), "Renders inline KaTeX expressions");
  assert.ok(html.includes('class="katex-display"'), "Renders display KaTeX expressions");
  assert.ok(html.includes("<mfrac") || html.includes("mfrac"), "Renders mathematical fractions");
  assert.ok(!html.includes("\\(") && !html.includes("\\["), "Converts paren and bracket LaTeX delimiters cleanly");
  assert.ok(
    html.includes("$50 and $100"),
    "Does not misparse $50 and $100 currency amounts as math"
  );
  assert.ok(html.includes("$HOME"), "Leaves inline code dollar variables untouched");
});

test("Streaming preprocessing and block splitting handle partial markdown gracefully without layout breakage", () => {
  const partialFence = "# Architecture\n\nIntro paragraph.\n\n```python\ndef hello():\n    print('streaming')";
  const preparedFence = preprocessMarkdown(partialFence, true);
  assert.ok(preparedFence.endsWith("\n```"), "Auto-closes incomplete fenced code block during streaming");

  const partialHtml = renderMarkdown(partialFence, true);
  assert.ok(partialHtml.includes("language-python") && partialHtml.includes("hljs-keyword"), "Renders partial streaming code block immediately");

  const partialTable = [
    "Summary above.",
    "",
    "| Agent | Status |",
    "| --- | --- |",
    "| Security | Passed |",
    "| Quality | Runn",
  ].join("\n");
  const tableHtml = renderMarkdown(partialTable, true);
  assert.ok(tableHtml.includes("<table") && tableHtml.includes("Runn"), "Renders partial streaming GFM table rows without collapsing");

  const blocks = splitMarkdownBlocks(
    "# Title\n\nParagraph 1.\n\n```ts\nconst x = 1;\n```\n\n1. First\n\n2. Second"
  );
  assert.equal(blocks.length, 4, "Splits completed independent blocks cleanly while keeping multi-paragraph ordered lists intact");
  assert.equal(sanitizeLinkHref("javascript:alert(1)"), undefined, "Blocks unsafe javascript URIs");
});

test("AssistantMessageItem keeps edit action restricted to user messages and applies dark theme CSS rules", () => {
  const workspacePath = path.join(__dirname, "AIConversationWorkspace.tsx");
  const workspaceSrc = fs.readFileSync(workspacePath, "utf-8");
  assert.ok(
    workspaceSrc.includes("<MarkdownContent content={message.content} isStreaming={isStreaming} />"),
    "AIConversationWorkspace must pass isStreaming prop to MarkdownContent"
  );

  const asstSection = workspaceSrc.slice(workspaceSrc.indexOf("const AssistantMessageItem"));
  assert.ok(
    !asstSection.includes("setEditingMessageId"),
    "Assistant messages must never expose editing triggers"
  );

  const cssPath = path.resolve(__dirname, "../../index.css");
  const cssSrc = fs.readFileSync(cssPath, "utf-8");
  assert.ok(cssSrc.includes(".nx-markdown .katex-display"), "index.css must contain responsive KaTeX display overflow rules");
  assert.ok(cssSrc.includes("hljs-keyword"), "index.css must include restrained dark syntax highlighting theme");
});

test("Incremental chunk-by-chunk streaming of mixed Markdown renders cleanly at every intermediate boundary", () => {
  const fullMixed = [
    "# Audit Report",
    "",
    "Long explanatory paragraph detailing why hosting costs sit between $50 and $100 per tier while keeping `DATABASE_URL` private and evaluating [FastAPI](https://fastapi.tiangolo.com) throughput.",
    "",
    "## Findings Table",
    "",
    "| Check | Result | Cost |",
    "| :--- | :---: | ---: |",
    "| Auth | Pass | $O(1)$ |",
    "| AST | Pass | $O(n \\log n)$ |",
    "",
    "```python",
    "def score(x: int) -> int:",
    "    return x * 2",
    "```",
    "",
    "```typescript",
    "export const ok: boolean = true;",
    "```",
    "",
    "Formula \\( E = mc^2 \\) and display:",
    "",
    "\\[ \\sum_{i=1}^n i = \\frac{n(n+1)}{2} \\]",
    "",
    "- Parent",
    "  - Child",
    "",
    "> Quote summary",
  ].join("\n");

  for (let cut = 15; cut < fullMixed.length; cut += 25) {
    const partial = fullMixed.slice(0, cut);
    const html = renderMarkdown(partial, true);
    assert.ok(html.includes('class="chat-message-content nx-markdown'), `Chunk at ${cut} must render wrapper cleanly`);
    assert.ok(!html.includes("undefined") && !html.includes("NaN"), `Chunk at ${cut} must not leak undefined/NaN`);
  }

  const finalHtml = renderMarkdown(fullMixed, false);
  assert.ok(finalHtml.includes("<h1") && finalHtml.includes("<h2"));
  assert.ok(finalHtml.includes("<table") && finalHtml.includes("<th"));
  assert.ok(finalHtml.includes("language-python") && finalHtml.includes("language-typescript"));
  assert.ok(finalHtml.includes('class="katex"') && finalHtml.includes('class="katex-display"'));
  assert.ok(finalHtml.includes("$50 and $100"));
  assert.ok(finalHtml.includes("<blockquote") && finalHtml.includes("Child"));
});
