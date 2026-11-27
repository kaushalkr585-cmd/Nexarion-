export interface LanguageInfo {
  id: string;
  label: string;
}

const LANGUAGE_MAP: Record<string, LanguageInfo> = {
  py: { id: "python", label: "Python" },
  python: { id: "python", label: "Python" },
  python3: { id: "python", label: "Python" },
  js: { id: "javascript", label: "JavaScript" },
  javascript: { id: "javascript", label: "JavaScript" },
  mjs: { id: "javascript", label: "JavaScript" },
  cjs: { id: "javascript", label: "JavaScript" },
  jsx: { id: "javascript", label: "JSX" },
  ts: { id: "typescript", label: "TypeScript" },
  typescript: { id: "typescript", label: "TypeScript" },
  tsx: { id: "typescript", label: "TSX" },
  java: { id: "java", label: "Java" },
  cpp: { id: "cpp", label: "C++" },
  "c++": { id: "cpp", label: "C++" },
  cc: { id: "cpp", label: "C++" },
  cxx: { id: "cpp", label: "C++" },
  c: { id: "c", label: "C" },
  cs: { id: "csharp", label: "C#" },
  csharp: { id: "csharp", label: "C#" },
  sql: { id: "sql", label: "SQL" },
  postgres: { id: "sql", label: "SQL" },
  postgresql: { id: "sql", label: "SQL" },
  mysql: { id: "sql", label: "SQL" },
  sqlite: { id: "sql", label: "SQL" },
  bash: { id: "bash", label: "Bash" },
  sh: { id: "bash", label: "Bash" },
  shell: { id: "bash", label: "Shell" },
  zsh: { id: "bash", label: "Bash" },
  console: { id: "bash", label: "Shell" },
  powershell: { id: "powershell", label: "PowerShell" },
  pwsh: { id: "powershell", label: "PowerShell" },
  ps1: { id: "powershell", label: "PowerShell" },
  json: { id: "json", label: "JSON" },
  jsonc: { id: "json", label: "JSON" },
  json5: { id: "json", label: "JSON" },
  yaml: { id: "yaml", label: "YAML" },
  yml: { id: "yaml", label: "YAML" },
  html: { id: "xml", label: "HTML" },
  htm: { id: "xml", label: "HTML" },
  xml: { id: "xml", label: "XML" },
  svg: { id: "xml", label: "SVG" },
  css: { id: "css", label: "CSS" },
  scss: { id: "scss", label: "SCSS" },
  less: { id: "less", label: "Less" },
  go: { id: "go", label: "Go" },
  golang: { id: "go", label: "Go" },
  rust: { id: "rust", label: "Rust" },
  rs: { id: "rust", label: "Rust" },
  rb: { id: "ruby", label: "Ruby" },
  ruby: { id: "ruby", label: "Ruby" },
  php: { id: "php", label: "PHP" },
  swift: { id: "swift", label: "Swift" },
  kt: { id: "kotlin", label: "Kotlin" },
  kotlin: { id: "kotlin", label: "Kotlin" },
  r: { id: "r", label: "R" },
  lua: { id: "lua", label: "Lua" },
  perl: { id: "perl", label: "Perl" },
  md: { id: "markdown", label: "Markdown" },
  markdown: { id: "markdown", label: "Markdown" },
  diff: { id: "diff", label: "Diff" },
  patch: { id: "diff", label: "Diff" },
  dockerfile: { id: "dockerfile", label: "Dockerfile" },
  docker: { id: "dockerfile", label: "Dockerfile" },
  graphql: { id: "graphql", label: "GraphQL" },
  gql: { id: "graphql", label: "GraphQL" },
  ini: { id: "ini", label: "INI" },
  toml: { id: "ini", label: "TOML" },
  makefile: { id: "makefile", label: "Makefile" },
  make: { id: "makefile", label: "Makefile" },
  wasm: { id: "wasm", label: "WebAssembly" },
  plaintext: { id: "plaintext", label: "Text" },
  text: { id: "plaintext", label: "Text" },
  txt: { id: "plaintext", label: "Text" },
};

export function normalizeCodeLanguage(rawLang?: string): LanguageInfo {
  const rawToken = (rawLang || "").trim().split(/\s+/)[0].replace(/^language-/, "");
  const clean = rawToken.toLowerCase();
  if (!clean) {
    return { id: "plaintext", label: "Code" };
  }
  const mapped = LANGUAGE_MAP[clean];
  if (mapped) {
    return mapped;
  }
  return {
    id: clean,
    label: rawToken,
  };
}

export interface CodeBlockLineAnalysis {
  lineCount: number;
  maxLineLength: number;
  hasLongLines: boolean;
  defaultWrapped: boolean;
}

/**
 * Analyzes code block line lengths and language formatting semantics so
 * structured code preserves indentation with isolated horizontal scroll by
 * default while offering line wrapping on demand (and auto-wrapping prose-like
 * plain text output that contains very long unwrapped lines).
 */
export function analyzeCodeBlockLines(langId: string, code: string): CodeBlockLineAnalysis {
  const lines = code ? code.split("\n") : [];
  let maxLineLength = 0;
  let indentedLineCount = 0;
  let asciiStructureCount = 0;

  for (const line of lines) {
    if (line.length > maxLineLength) {
      maxLineLength = line.length;
    }
    if (/^[ \t]{2,}\S/.test(line)) {
      indentedLineCount += 1;
    }
    if (/[├└│─┌┐┘┤┬┴┼]|^\s*\|.*\|/u.test(line)) {
      asciiStructureCount += 1;
    }
  }

  const hasLongLines = maxLineLength >= 44;
  const isProseLikeLanguage = langId === "plaintext" || langId === "markdown";
  const hasTabularOrAlignedFormatting = indentedLineCount >= 2 || asciiStructureCount >= 1;
  const defaultWrapped =
    isProseLikeLanguage && maxLineLength >= 96 && !hasTabularOrAlignedFormatting;

  return {
    lineCount: lines.length,
    maxLineLength,
    hasLongLines,
    defaultWrapped,
  };
}

export function sanitizeLinkHref(href?: string): string | undefined {
  if (!href) return undefined;
  const trimmed = href.trim();
  if (!trimmed) return undefined;
  if (
    trimmed.startsWith("/") ||
    trimmed.startsWith("#") ||
    trimmed.startsWith("./") ||
    trimmed.startsWith("../")
  ) {
    return trimmed;
  }
  try {
    const parsed = new URL(trimmed);
    if (["http:", "https:", "mailto:", "tel:"].includes(parsed.protocol)) {
      return trimmed;
    }
  } catch {
    // Allow relative path without scheme if it does not look like a script URI
    if (!/^[a-zA-Z][a-zA-Z0-9+.-]*:/.test(trimmed)) {
      return trimmed;
    }
  }
  return undefined;
}

function findFenceMatch(line: string): { char: "`" | "~"; len: number; rest: string } | null {
  const match = line.match(/^[ ]{0,3}(`{3,}|~{3,})(.*)$/);
  if (!match) return null;
  const fence = match[1];
  const char = fence[0] as "`" | "~";
  const rest = match[2] || "";
  if (char === "`" && rest.includes("`")) {
    // CommonMark forbids backticks in info strings for backtick fences
    return null;
  }
  return { char, len: fence.length, rest };
}

function isClosingFence(line: string, char: "`" | "~", minLen: number): boolean {
  const match = line.match(/^[ ]{0,3}(`{3,}|~{3,})[ \t]*$/);
  if (!match) return false;
  return match[1][0] === char && match[1].length >= minLen;
}

function findClosingBackticks(text: string, startAfterOpen: number, tickCount: number): number {
  let j = startAfterOpen;
  while (j < text.length) {
    if (text[j] === "`") {
      let run = 0;
      while (j + run < text.length && text[j + run] === "`") {
        run++;
      }
      if (run === tickCount) {
        return j;
      }
      j += run;
      continue;
    }
    j++;
  }
  return -1;
}

function findUnescapedToken(text: string, fromIdx: number, token: string): number {
  let i = fromIdx;
  while (i <= text.length - token.length) {
    if (text[i] === "\\" && i + 1 < text.length && text[i + 1] === "\\") {
      i += 2;
      continue;
    }
    if (text.startsWith(token, i)) {
      return i;
    }
    if (text[i] === "\\") {
      i += 2;
      continue;
    }
    i++;
  }
  return -1;
}

function isStandaloneOnLine(text: string, startIdx: number, endIdxExclusive: number): boolean {
  const lineStart = text.lastIndexOf("\n", startIdx - 1) + 1;
  const before = text.slice(lineStart, startIdx);
  if (/[^ \t]/.test(before)) return false;

  const nextNl = text.indexOf("\n", endIdxExclusive);
  const after = text.slice(endIdxExclusive, nextNl === -1 ? text.length : nextNl);
  return !/[^ \t]/.test(after);
}

function findInlineMathClose(text: string, openIdx: number): number {
  const len = text.length;
  if (openIdx + 1 >= len || /\s/.test(text[openIdx + 1]) || text[openIdx + 1] === "$") {
    return -1;
  }

  let i = openIdx + 1;
  while (i < len) {
    const ch = text[i];
    if (ch === "\\") {
      i += 2;
      continue;
    }
    if (ch === "\n" && i + 1 < len && text[i + 1] === "\n") {
      // Do not span across paragraphs
      return -1;
    }
    if (ch === "`") {
      // Do not pair across inline code spans
      return -1;
    }
    if (ch === "$") {
      if (i + 1 < len && text[i + 1] === "$") {
        i += 2;
        continue;
      }
      const prevChar = text[i - 1];
      const nextChar = i + 1 < len ? text[i + 1] : "";
      if (!/\s/.test(prevChar) && !/\d/.test(nextChar)) {
        return i;
      }
      // This $ is not a valid closing delimiter for Pandoc math
      return -1;
    }
    i++;
  }
  return -1;
}

function normalizeProseSegment(segment: string, isStreaming: boolean): string {
  let out = "";
  let i = 0;

  while (i < segment.length) {
    const ch = segment[i];

    // Preserved escaped character (\$, \\, etc.)
    if (ch === "\\" && i + 1 < segment.length) {
      const next = segment[i + 1];

      // Convert \[ ... \] display math
      if (next === "[") {
        const closeIdx = findUnescapedToken(segment, i + 2, "\\]");
        if (closeIdx !== -1) {
          const inner = segment.slice(i + 2, closeIdx).trim();
          const lineStart = segment.lastIndexOf("\n", i - 1) + 1;
          const prefixOnLine = segment.slice(lineStart, i);
          if (/^[ \t]*>/.test(prefixOnLine)) {
            out += `$$${inner.replace(/\n[ \t]*>[ \t]?/g, " ")}$$`;
          } else {
            if (!/[^ \t]/.test(prefixOnLine)) {
              out = out.replace(/[ \t]+$/, "");
            }
            if (out.length > 0 && !out.endsWith("\n\n")) {
              out += out.endsWith("\n") ? "\n" : "\n\n";
            }
            out += `$$\n${inner}\n$$\n\n`;
          }
          i = closeIdx + 2;
          continue;
        }
        if (isStreaming) {
          out += segment.slice(i, i + 2);
          i += 2;
          continue;
        }
      }

      // Convert \( ... \) inline math
      if (next === "(") {
        const closeIdx = findUnescapedToken(segment, i + 2, "\\)");
        if (closeIdx !== -1) {
          const rawInner = segment.slice(i + 2, closeIdx);
          if (!rawInner.includes("\n\n")) {
            const inner = rawInner.trim();
            if (inner.length > 0) {
              out += `$${inner}$`;
              i = closeIdx + 2;
              continue;
            }
          }
        }
      }

      out += segment.slice(i, i + 2);
      i += 2;
      continue;
    }

    // Preserve inline code spans verbatim
    if (ch === "`") {
      let tickCount = 0;
      while (i + tickCount < segment.length && segment[i + tickCount] === "`") {
        tickCount++;
      }
      const closeIdx = findClosingBackticks(segment, i + tickCount, tickCount);
      if (closeIdx !== -1) {
        out += segment.slice(i, closeIdx + tickCount);
        i = closeIdx + tickCount;
        continue;
      }
      out += segment.slice(i, i + tickCount);
      i += tickCount;
      continue;
    }

    // Handle display math $$ ... $$
    if (ch === "$" && i + 1 < segment.length && segment[i + 1] === "$") {
      const closeIdx = findUnescapedToken(segment, i + 2, "$$");
      if (closeIdx !== -1) {
        const inner = segment.slice(i + 2, closeIdx).trim();
        const lineStart = segment.lastIndexOf("\n", i - 1) + 1;
        const prefixOnLine = segment.slice(lineStart, i);
        const insideQuote = /^[ \t]*>/.test(prefixOnLine);
        const standalone =
          !insideQuote &&
          (isStandaloneOnLine(segment, i, closeIdx + 2) || inner.includes("\n"));
        if (standalone) {
          if (!/[^ \t]/.test(prefixOnLine)) {
            out = out.replace(/[ \t]+$/, "");
          }
          if (out.length > 0 && !out.endsWith("\n\n")) {
            out += out.endsWith("\n") ? "\n" : "\n\n";
          }
          out += `$$\n${inner}\n$$\n\n`;
        } else {
          out += `$$${inner.replace(/\n[ \t]*>[ \t]?/g, " ")}$$`;
        }
        i = closeIdx + 2;
        continue;
      }
      // Unclosed $$ (e.g. still streaming) -> leave literal so incomplete syntax doesn't break layout
      out += "\\$\\$";
      i += 2;
      continue;
    }

    // Handle single $ (inline math vs currency)
    if (ch === "$") {
      const closeIdx = findInlineMathClose(segment, i);
      if (closeIdx !== -1) {
        out += segment.slice(i, closeIdx + 1);
        i = closeIdx + 1;
        continue;
      }
      out += "\\$";
      i++;
      continue;
    }

    out += ch;
    i++;
  }

  return out.replace(/\n{3,}/g, "\n\n");
}

/**
 * Prepares raw Markdown/LaTeX (including partial streaming chunks) for
 * GFM + KaTeX rendering while keeping code fences and inline code untouched.
 */
export function preprocessMarkdown(raw: string, isStreaming = false): string {
  if (!raw) return "";
  const normalized = raw.replace(/\r\n?/g, "\n");
  const lines = normalized.split("\n");

  const outputChunks: string[] = [];
  let proseBuffer: string[] = [];
  let codeBuffer: string[] = [];
  let activeFence: { char: "`" | "~"; len: number } | null = null;

  const flushProse = () => {
    if (proseBuffer.length === 0) return;
    outputChunks.push(normalizeProseSegment(proseBuffer.join("\n"), isStreaming));
    proseBuffer = [];
  };

  for (let idx = 0; idx < lines.length; idx++) {
    const line = lines[idx];

    if (!activeFence) {
      const fence = findFenceMatch(line);
      if (fence) {
        flushProse();
        activeFence = { char: fence.char, len: fence.len };
        codeBuffer = [line];
      } else {
        proseBuffer.push(line);
      }
    } else {
      codeBuffer.push(line);
      if (isClosingFence(line, activeFence.char, activeFence.len)) {
        outputChunks.push(codeBuffer.join("\n"));
        codeBuffer = [];
        activeFence = null;
      }
    }
  }

  flushProse();

  if (activeFence && codeBuffer.length > 0) {
    // Close open code fences temporarily while streaming so code blocks do not flicker
    codeBuffer.push(activeFence.char.repeat(activeFence.len));
    outputChunks.push(codeBuffer.join("\n"));
  }

  return outputChunks.join("\n");
}

/**
 * Splits preprocessed Markdown into stable top-level blocks so completed blocks
 * above an active streaming block stay memoized without DOM re-rendering.
 */
export function splitMarkdownBlocks(markdown: string): string[] {
  if (!markdown) return [];

  // Fallback to single block if reference-style links or footnotes exist
  if (/^[ ]{0,3}\[\^?[^\]]+\]:[ \t]*\S/m.test(markdown)) {
    return [markdown];
  }

  const lines = markdown.split("\n");
  const blocks: string[] = [];
  let currentLines: string[] = [];
  let activeFence: { char: "`" | "~"; len: number } | null = null;
  let inDisplayMath = false;
  let blockHasList = false;

  const isListLine = (line: string): boolean =>
    /^[ ]{0,3}(?:[-*+]|\d{1,9}[.)])[ \t]/.test(line);
  const isIndentedLine = (line: string): boolean => /^[ \t]+\S/.test(line);
  const isQuoteLine = (line: string): boolean => /^[ ]{0,3}>/.test(line);

  const findNextNonBlank = (startIdx: number): string | null => {
    for (let j = startIdx; j < lines.length; j++) {
      if (lines[j].trim() !== "") return lines[j];
    }
    return null;
  };

  const shouldContinueSameBlock = (nextLine: string | null, prevLine: string | null): boolean => {
    if (nextLine === null) return false;
    if (blockHasList && (isListLine(nextLine) || isIndentedLine(nextLine))) return true;
    if (prevLine && isQuoteLine(prevLine) && isQuoteLine(nextLine)) return true;
    if (prevLine && /^[ ]{0,3}\|/.test(prevLine) && /^[ ]{0,3}\|/.test(nextLine)) return true;
    return false;
  };

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];

    if (activeFence) {
      currentLines.push(line);
      if (isClosingFence(line, activeFence.char, activeFence.len)) {
        activeFence = null;
      }
      continue;
    }

    if (inDisplayMath) {
      currentLines.push(line);
      if (/^[ ]{0,3}\$\$[ \t]*$/.test(line)) {
        inDisplayMath = false;
      }
      continue;
    }

    const fence = findFenceMatch(line);
    if (fence) {
      currentLines.push(line);
      activeFence = { char: fence.char, len: fence.len };
      continue;
    }

    if (/^[ ]{0,3}\$\$[ \t]*$/.test(line)) {
      currentLines.push(line);
      inDisplayMath = true;
      continue;
    }

    if (line.trim() === "") {
      const nextNonBlank = findNextNonBlank(i + 1);
      const prevLine = currentLines.length > 0 ? currentLines[currentLines.length - 1] : null;
      if (currentLines.length > 0 && !shouldContinueSameBlock(nextNonBlank, prevLine)) {
        const joined = currentLines.join("\n").trim();
        if (joined) blocks.push(joined);
        currentLines = [];
        blockHasList = false;
        continue;
      }
    }

    if (isListLine(line)) {
      blockHasList = true;
    }
    currentLines.push(line);
  }

  const tail = currentLines.join("\n").trim();
  if (tail) {
    blocks.push(tail);
  }

  return blocks;
}

export interface HastLikeNode {
  type?: string;
  tagName?: string;
  value?: string;
  properties?: {
    className?: string[] | string;
  };
  children?: HastLikeNode[];
}

function collectHastText(node?: HastLikeNode): string {
  if (!node) return "";
  if (typeof node.value === "string") return node.value;
  if (!Array.isArray(node.children)) return "";
  return node.children.map((child) => collectHastText(child)).join("");
}

/**
 * Extracts raw language identifier and code text from a markdown `<pre>` HAST element.
 */
export function extractCodeBlockFromHast(node?: HastLikeNode): {
  language: string;
  code: string;
} {
  if (!node) return { language: "", code: "" };
  const codeChild = Array.isArray(node.children)
    ? node.children.find((child) => child.type === "element" && child.tagName === "code")
    : undefined;
  const target = codeChild || node;
  const rawClassName = target.properties?.className;
  const classes = Array.isArray(rawClassName)
    ? rawClassName
    : typeof rawClassName === "string"
    ? rawClassName.split(/\s+/)
    : [];
  const langClass = classes.find((cls) => cls.startsWith("language-"));
  const language = langClass ? langClass.slice("language-".length) : "";
  const code = collectHastText(target).replace(/\n$/, "");
  return { language, code };
}

export interface TableAnalysis {
  headers: string[];
  columnCount: number;
  maxCellLength: number;
  totalHeaderLength: number;
  useStackedMobileCards: boolean;
}

function collectElementsByTag(
  node: HastLikeNode | undefined,
  tagName: string,
  acc: HastLikeNode[] = []
): HastLikeNode[] {
  if (!node) return acc;
  if (node.type === "element" && node.tagName === tagName) {
    acc.push(node);
    return acc;
  }
  if (Array.isArray(node.children)) {
    for (const child of node.children) {
      collectElementsByTag(child, tagName, acc);
    }
  }
  return acc;
}

/**
 * Inspects a HAST `<table>` element to decide whether it fits comfortably as a
 * compact fixed-width table on mobile or should transform into stacked cards.
 */
export function analyzeTableFromHast(node?: HastLikeNode): TableAnalysis {
  if (!node) {
    return {
      headers: [],
      columnCount: 0,
      maxCellLength: 0,
      totalHeaderLength: 0,
      useStackedMobileCards: false,
    };
  }

  const theadNodes = collectElementsByTag(node, "thead");
  const headerCells = theadNodes.length > 0 ? collectElementsByTag(theadNodes[0], "th") : [];
  const headers = headerCells.map((cell) => collectHastText(cell).replace(/\s+/g, " ").trim());

  const tbodyNodes = collectElementsByTag(node, "tbody");
  const bodyRows = tbodyNodes.length > 0 ? collectElementsByTag(tbodyNodes[0], "tr") : [];

  let maxColsFromRows = 0;
  let maxCellLength = 0;
  let hasLongUnbrokenToken = false;

  for (const h of headers) {
    if (h.length > maxCellLength) maxCellLength = h.length;
    if (/\S{18,}/.test(h)) hasLongUnbrokenToken = true;
  }

  for (const row of bodyRows) {
    const cells = collectElementsByTag(row, "td");
    if (cells.length > maxColsFromRows) maxColsFromRows = cells.length;
    for (const cell of cells) {
      const text = collectHastText(cell).replace(/\s+/g, " ").trim();
      if (text.length > maxCellLength) maxCellLength = text.length;
      if (/\S{22,}/.test(text)) hasLongUnbrokenToken = true;
    }
  }

  const columnCount = Math.max(headers.length, maxColsFromRows);
  const totalHeaderLength = headers.reduce((sum, h) => sum + h.length, 0);
  const hasAnyHeaders = headers.some((h) => h.length > 0);

  let useStackedMobileCards = false;
  if (hasAnyHeaders) {
    if (columnCount >= 3) {
      // Keep ultra-tiny 3-col numeric tables (e.g. | # | A | B |) as tables, stack wider 3+ col tables
      useStackedMobileCards = !(
        columnCount === 3 &&
        totalHeaderLength <= 12 &&
        maxCellLength <= 8 &&
        !hasLongUnbrokenToken
      );
    } else if (columnCount === 2) {
      // Simple 2-column tables stay tables when they fit comfortably; long descriptions stack cleanly
      useStackedMobileCards =
        maxCellLength > 72 || totalHeaderLength > 28 || hasLongUnbrokenToken;
    }
  }

  return {
    headers,
    columnCount,
    maxCellLength,
    totalHeaderLength,
    useStackedMobileCards,
  };
}
