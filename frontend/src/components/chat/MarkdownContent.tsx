import React, { createContext, useContext, useMemo, useState } from "react";
import ReactMarkdown, { type Components } from "react-markdown";
import type { PluggableList } from "unified";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";
import rehypeKatex from "rehype-katex";
import hljs from "highlight.js/lib/common";
import dockerfileLang from "highlight.js/lib/languages/dockerfile";
import powershellLang from "highlight.js/lib/languages/powershell";
import { CheckIcon, CopyIcon, WrapTextIcon } from "../icons/Icons";
import {
  analyzeCodeBlockLines,
  analyzeTableFromHast,
  extractCodeBlockFromHast,
  normalizeCodeLanguage,
  preprocessMarkdown,
  sanitizeLinkHref,
  splitMarkdownBlocks,
  type HastLikeNode,
} from "./markdownUtils";

const TableHeadersContext = createContext<string[]>([]);
const IsTableHeadContext = createContext<boolean>(false);
const TableCellLabelContext = createContext<string>("");

if (!hljs.getLanguage("dockerfile")) {
  hljs.registerLanguage("dockerfile", dockerfileLang);
}
if (!hljs.getLanguage("powershell")) {
  hljs.registerLanguage("powershell", powershellLang);
}

const REMARK_PLUGINS: PluggableList = [remarkGfm, remarkMath];
const REHYPE_PLUGINS: PluggableList = [
  [
    rehypeKatex,
    {
      strict: false,
      throwOnError: false,
      errorColor: "#a1a1aa",
    },
  ],
];

interface MarkdownContentProps {
  content: string;
  isStreaming?: boolean;
}

export const CodeBlock: React.FC<{ language: string; code: string }> = React.memo(
  ({ language, code }) => {
    const [copied, setCopied] = useState(false);
    const [wrapOverride, setWrapOverride] = useState<boolean | null>(null);

    const { id: langId, label: langLabel } = useMemo(
      () => normalizeCodeLanguage(language),
      [language]
    );

    const lineAnalysis = useMemo(
      () => analyzeCodeBlockLines(langId, code),
      [langId, code]
    );
    const isWrapped = wrapOverride ?? lineAnalysis.defaultWrapped;

    const highlightedHtml = useMemo(() => {
      if (!code || langId === "plaintext" || !hljs.getLanguage(langId)) {
        return null;
      }
      try {
        return hljs.highlight(code, { language: langId, ignoreIllegals: true }).value;
      } catch {
        return null;
      }
    }, [code, langId]);

    const handleCopyCode = async (e: React.MouseEvent) => {
      e.stopPropagation();
      try {
        if (navigator.clipboard && window.isSecureContext) {
          await navigator.clipboard.writeText(code);
        } else {
          const textarea = document.createElement("textarea");
          textarea.value = code;
          textarea.style.position = "fixed";
          textarea.style.opacity = "0";
          document.body.appendChild(textarea);
          textarea.select();
          document.execCommand("copy");
          document.body.removeChild(textarea);
        }
        setCopied(true);
        setTimeout(() => setCopied(false), 2000);
      } catch (err) {
        console.error("Failed to copy code block:", err);
      }
    };

    return (
      <div
        data-code-block="true"
        data-ask-nexarion-ignore="true"
        className="nx-code-block my-3.5 rounded-xl overflow-hidden border border-white/12 bg-[#070709] font-mono text-xs shadow-sm w-full max-w-full min-w-0"
      >
        <div className="flex items-center justify-between gap-2 px-3 sm:px-4 py-1.5 sm:py-2 bg-white/[0.04] border-b border-white/10 text-neutral-300 text-xs select-none min-w-0">
          <span className="font-mono font-medium tracking-wide text-neutral-300 text-[11.5px] truncate">
            {langLabel}
          </span>
          <div className="flex items-center gap-1.5 flex-shrink-0">
            {lineAnalysis.hasLongLines && (
              <button
                type="button"
                onClick={(e) => {
                  e.stopPropagation();
                  setWrapOverride(!isWrapped);
                }}
                aria-pressed={isWrapped}
                aria-label={isWrapped ? "Unwrap long code lines" : "Wrap long code lines"}
                title={isWrapped ? "Use horizontal scrolling for long lines" : "Wrap long lines"}
                className={`flex items-center gap-1 px-2 py-0.5 rounded-md text-[11px] flex-shrink-0 transition-colors cursor-pointer ${
                  isWrapped
                    ? "text-white bg-white/15 font-medium"
                    : "text-neutral-400 hover:text-white hover:bg-white/10"
                }`}
              >
                <WrapTextIcon className="w-3.5 h-3.5" />
                <span>{isWrapped ? "Wrapped" : "Wrap"}</span>
              </button>
            )}
            <button
              type="button"
              onClick={handleCopyCode}
              aria-label={copied ? "Code copied" : "Copy code"}
              className={`flex items-center gap-1.5 px-2 py-0.5 rounded-md text-[11px] flex-shrink-0 transition-colors cursor-pointer ${
                copied
                  ? "text-emerald-400 bg-emerald-500/10 font-medium"
                  : "text-neutral-400 hover:text-white hover:bg-white/10"
              }`}
            >
              {copied ? (
                <>
                  <CheckIcon className="w-3.5 h-3.5 text-emerald-400" />
                  <span>Copied</span>
                </>
              ) : (
                <>
                  <CopyIcon className="w-3.5 h-3.5" />
                  <span>Copy code</span>
                </>
              )}
            </button>
          </div>
        </div>

        <pre
          data-wrapped={isWrapped ? "true" : "false"}
          className={`nx-code-pre m-0 p-3 sm:p-4 text-[#E5E7EB] text-[12.5px] sm:text-[13.5px] leading-[1.6] font-mono select-text cursor-text w-full max-w-full min-w-0 box-border ${
            isWrapped
              ? "overflow-x-hidden whitespace-pre-wrap [overflow-wrap:anywhere]"
              : "overflow-x-auto overscroll-x-contain whitespace-pre"
          }`}
        >
          {highlightedHtml !== null ? (
            <code
              className={`hljs language-${langId} select-text block ${
                isWrapped ? "w-full max-w-full min-w-0" : "w-max min-w-full"
              }`}
              dangerouslySetInnerHTML={{ __html: highlightedHtml }}
            />
          ) : (
            <code
              className={`select-text block ${
                isWrapped ? "w-full max-w-full min-w-0" : "w-max min-w-full"
              }`}
            >
              {code}
            </code>
          )}
        </pre>
      </div>
    );
  }
);
CodeBlock.displayName = "CodeBlock";

function getCellAlignClass(align?: string, style?: React.CSSProperties): string {
  const effective = align || (typeof style?.textAlign === "string" ? style.textAlign : undefined);
  if (effective === "center") return "text-center";
  if (effective === "right") return "text-right";
  return "text-left";
}

const MarkdownTable: React.FC<{ node?: HastLikeNode; children?: React.ReactNode }> = ({
  node,
  children,
}) => {
  const analysis = useMemo(() => analyzeTableFromHast(node), [node]);
  return (
    <TableHeadersContext.Provider value={analysis.headers}>
      <div
        data-ask-nexarion-ignore="true"
        data-mobile-layout={analysis.useStackedMobileCards ? "cards" : "table"}
        className="nx-table-wrapper my-3.5 sm:my-4 w-full max-w-full min-w-0 overflow-x-auto overscroll-x-contain rounded-xl border border-white/12 bg-white/[0.02]"
      >
        <table className="w-full border-collapse text-left text-[13px] sm:text-sm">
          {children}
        </table>
      </div>
    </TableHeadersContext.Provider>
  );
};

const MarkdownTableHead: React.FC<{ children?: React.ReactNode }> = ({ children }) => (
  <IsTableHeadContext.Provider value={true}>
    <thead className="bg-white/[0.05] border-b border-white/12">{children}</thead>
  </IsTableHeadContext.Provider>
);

const MarkdownTableRow: React.FC<{ children?: React.ReactNode }> = ({ children }) => {
  const headers = useContext(TableHeadersContext);
  const inHead = useContext(IsTableHeadContext);

  if (inHead || headers.length === 0) {
    return <tr className="hover:bg-white/[0.025] transition-colors">{children}</tr>;
  }

  let colIdx = 0;
  const labeledChildren = React.Children.map(children, (child) => {
    if (!React.isValidElement(child)) {
      return child;
    }
    const label = headers[colIdx] || "";
    colIdx += 1;
    return (
      <TableCellLabelContext.Provider value={label}>
        {child}
      </TableCellLabelContext.Provider>
    );
  });

  return <tr className="hover:bg-white/[0.025] transition-colors">{labeledChildren}</tr>;
};

const MarkdownTableCell: React.FC<{
  align?: string;
  style?: React.CSSProperties;
  children?: React.ReactNode;
}> = ({ align, style, children }) => {
  const label = useContext(TableCellLabelContext);
  return (
    <td
      style={style}
      className={`px-2.5 py-2 sm:px-3 sm:py-2.5 lg:px-3.5 text-neutral-300 align-top leading-relaxed border-r border-white/[0.05] last:border-r-0 min-w-0 ${getCellAlignClass(
        align,
        style
      )}`}
    >
      {label ? <span className="nx-cell-label">{label}:</span> : null}
      <span className="nx-cell-value">{children}</span>
    </td>
  );
};

const MARKDOWN_COMPONENTS: Components = {
  h1: ({ children }) => (
    <h1 className="text-[1.3rem] sm:text-2xl font-semibold text-white tracking-tight leading-snug mt-5 mb-2.5 first:mt-0 select-text min-w-0 max-w-full">
      {children}
    </h1>
  ),
  h2: ({ children }) => (
    <h2 className="text-[1.125rem] sm:text-xl font-semibold text-white tracking-tight leading-snug mt-4.5 mb-2 first:mt-0 select-text min-w-0 max-w-full">
      {children}
    </h2>
  ),
  h3: ({ children }) => (
    <h3 className="text-base sm:text-[1.0625rem] font-semibold text-white leading-snug mt-4 mb-1.5 first:mt-0 select-text min-w-0 max-w-full">
      {children}
    </h3>
  ),
  h4: ({ children }) => (
    <h4 className="text-[0.9375rem] sm:text-base font-semibold text-neutral-100 leading-snug mt-3.5 mb-1.5 first:mt-0 select-text min-w-0 max-w-full">
      {children}
    </h4>
  ),
  h5: ({ children }) => (
    <h5 className="text-sm font-semibold text-neutral-200 leading-snug mt-3 mb-1 first:mt-0 select-text min-w-0 max-w-full">
      {children}
    </h5>
  ),
  h6: ({ children }) => (
    <h6 className="text-xs sm:text-[13px] font-semibold uppercase tracking-wider text-neutral-400 leading-snug mt-3 mb-1 first:mt-0 select-text min-w-0 max-w-full">
      {children}
    </h6>
  ),
  p: ({ children }) => (
    <p className="my-2.5 first:mt-0 last:mb-0 text-[14.5px] sm:text-[15.25px] leading-[1.68] text-neutral-200 select-text min-w-0 max-w-full">
      {children}
    </p>
  ),
  strong: ({ children }) => (
    <strong className="font-semibold text-white select-text">{children}</strong>
  ),
  em: ({ children }) => (
    <em className="italic text-neutral-200 select-text">{children}</em>
  ),
  del: ({ children }) => (
    <del className="line-through text-neutral-400/90 select-text">{children}</del>
  ),
  a: ({ href, children }) => {
    const safeHref = sanitizeLinkHref(href);
    if (!safeHref) {
      return <span className="text-neutral-300 select-text">{children}</span>;
    }
    const isExternal = /^https?:\/\//i.test(safeHref);
    return (
      <a
        href={safeHref}
        target={isExternal ? "_blank" : undefined}
        rel={isExternal ? "noopener noreferrer" : undefined}
        className="text-white underline decoration-white/35 underline-offset-[3px] hover:decoration-white transition-colors select-text [overflow-wrap:anywhere]"
      >
        {children}
      </a>
    );
  },
  blockquote: ({ children }) => (
    <blockquote className="my-3.5 pl-3 pr-2 sm:pl-4 sm:pr-3 py-1.5 border-l-2 border-white/25 bg-white/[0.025] rounded-r-lg text-neutral-300 select-text min-w-0 max-w-full [&>p]:my-1.5 [&>p:first-child]:mt-0 [&>p:last-child]:mb-0">
      {children}
    </blockquote>
  ),
  hr: () => <hr className="my-5 border-0 border-t border-white/12 w-full" />,
  ul: ({ className, children }) => {
    const isTaskList = Boolean(className && className.includes("contains-task-list"));
    return (
      <ul
        className={`my-2.5 space-y-1.5 text-[14.5px] sm:text-[15.25px] leading-[1.65] text-neutral-200 min-w-0 max-w-full ${
          isTaskList
            ? "list-none pl-1"
            : "list-disc list-outside pl-5 sm:pl-6 marker:text-neutral-400"
        }`}
      >
        {children}
      </ul>
    );
  },
  ol: ({ children, start }) => (
    <ol
      start={start}
      className="my-2.5 list-decimal list-outside pl-5 sm:pl-6 space-y-1.5 text-[14.5px] sm:text-[15.25px] leading-[1.65] text-neutral-200 marker:text-neutral-400 min-w-0 max-w-full"
    >
      {children}
    </ol>
  ),
  li: ({ className, children }) => {
    const isTaskItem = Boolean(className && className.includes("task-list-item"));
    return (
      <li
        className={`leading-[1.65] select-text min-w-0 max-w-full ${
          isTaskItem ? "list-none pl-0" : "pl-0.5"
        }`}
      >
        {children}
      </li>
    );
  },
  input: ({ type, checked }) => {
    if (type !== "checkbox") {
      return null;
    }
    return (
      <input
        type="checkbox"
        checked={Boolean(checked)}
        disabled
        readOnly
        aria-label={checked ? "Completed task" : "Incomplete task"}
        className="nx-task-checkbox mr-2 align-middle"
      />
    );
  },
  table: ({ node, children }) => (
    <MarkdownTable node={node as unknown as HastLikeNode}>{children}</MarkdownTable>
  ),
  thead: ({ children }) => <MarkdownTableHead>{children}</MarkdownTableHead>,
  tbody: ({ children }) => (
    <tbody className="divide-y divide-white/[0.07]">{children}</tbody>
  ),
  tr: ({ children }) => <MarkdownTableRow>{children}</MarkdownTableRow>,
  th: ({ align, style, children }) => (
    <th
      style={style}
      className={`px-2.5 py-2 sm:px-3 sm:py-2.5 lg:px-3.5 font-semibold text-white text-xs sm:text-[13px] tracking-wide border-r border-white/[0.07] last:border-r-0 align-bottom min-w-0 ${getCellAlignClass(
        align,
        style
      )}`}
    >
      {children}
    </th>
  ),
  td: ({ align, style, children }) => (
    <MarkdownTableCell align={align} style={style}>
      {children}
    </MarkdownTableCell>
  ),
  pre: ({ node }) => {
    const { language, code } = extractCodeBlockFromHast(node as unknown as HastLikeNode);
    return <CodeBlock language={language} code={code} />;
  },
  code: ({ className, children }) => (
    <code
      className={`px-1.5 py-0.5 mx-[1px] rounded-md bg-white/[0.09] text-neutral-100 font-mono text-[0.85em] border border-white/10 select-text [overflow-wrap:anywhere] break-normal ${
        className || ""
      }`.trim()}
    >
      {children}
    </code>
  ),
  img: ({ src, alt }) => {
    const safeSrc = sanitizeLinkHref(src);
    if (!safeSrc) return null;
    return (
      <img
        src={safeSrc}
        alt={alt || ""}
        loading="lazy"
        className="my-3 block h-auto max-w-full rounded-xl border border-white/12 bg-black/40"
      />
    );
  },
};

const MarkdownBlock: React.FC<{ block: string }> = React.memo(({ block }) => (
  <ReactMarkdown
    remarkPlugins={REMARK_PLUGINS}
    rehypePlugins={REHYPE_PLUGINS}
    components={MARKDOWN_COMPONENTS}
  >
    {block}
  </ReactMarkdown>
));
MarkdownBlock.displayName = "MarkdownBlock";

export const MarkdownContent: React.FC<MarkdownContentProps> = React.memo(
  ({ content, isStreaming = false }) => {
    const prepared = useMemo(
      () => preprocessMarkdown(content, isStreaming),
      [content, isStreaming]
    );

    const blocks = useMemo(() => splitMarkdownBlocks(prepared), [prepared]);

    if (!content) return null;

    return (
      <div className="chat-message-content nx-markdown select-text text-neutral-200 w-full max-w-full min-w-0">
        {blocks.map((block, idx) => (
          <MarkdownBlock key={idx} block={block} />
        ))}
      </div>
    );
  }
);
MarkdownContent.displayName = "MarkdownContent";
