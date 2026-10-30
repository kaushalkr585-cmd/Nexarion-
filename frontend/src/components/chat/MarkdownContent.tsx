import React, { useState } from "react";
import { CheckIcon, CopyIcon } from "../icons/Icons";

interface MarkdownContentProps {
  content: string;
}

export const CodeBlock: React.FC<{ language: string; code: string }> = ({ language, code }) => {
  const [copied, setCopied] = useState(false);

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
    <div className="my-3 rounded-xl overflow-hidden border border-white/15 bg-black/90 font-mono text-xs shadow-md w-full max-w-full">

      <div className="flex items-center justify-between px-3.5 py-1.5 bg-white/[0.04] border-b border-white/10 text-neutral-400 text-[11px]">
        <span className="font-semibold tracking-wider uppercase text-neutral-300">
          {language || "code"}
        </span>
        <button
          type="button"
          onClick={handleCopyCode}
          aria-label={copied ? "Code copied" : "Copy code"}
          className={`flex items-center gap-1.5 px-2 py-0.5 rounded text-[11px] transition-colors ${
            copied
              ? "text-emerald-400 bg-emerald-500/10 font-medium"
              : "text-neutral-400 hover:text-white hover:bg-white/10"
          }`}
        >
          {copied ? (
            <>
              <CheckIcon className="w-3 h-3 text-emerald-400" />
              <span>Copied</span>
            </>
          ) : (
            <>
              <CopyIcon className="w-3 h-3" />
              <span>Copy code</span>
            </>
          )}
        </button>
      </div>

      <pre className="p-3.5 overflow-x-auto overscroll-x-contain text-neutral-200 leading-relaxed font-mono select-text cursor-text max-w-full">
        <code className="select-text">{code}</code>
      </pre>
    </div>
  );
};

export function renderInlineMarkdown(text: string): React.ReactNode[] {

  const tokens = text.split(/(`[^`]+`|\*\*[^*]+\*\*|__[^_]+__|(?<!\*)\*[^*]+(?!\*)|\[[^\]]+\]\([^)]+\))/g);

  return tokens.map((token, i) => {
    if (!token) return null;

    // Inline code
    if (token.startsWith("`") && token.endsWith("`") && token.length > 2) {
      return (
        <code
          key={i}
          className="px-1.5 py-0.5 mx-0.5 rounded bg-white/10 text-white font-mono text-[11px] sm:text-xs border border-white/15 select-text"
        >
          {token.slice(1, -1)}
        </code>
      );
    }

    // Bold
    if (
      (token.startsWith("**") && token.endsWith("**") && token.length > 4) ||
      (token.startsWith("__") && token.endsWith("__") && token.length > 4)
    ) {
      return (
        <strong key={i} className="font-semibold text-white select-text">
          {token.slice(2, -2)}
        </strong>
      );
    }

    // Italic
    if (
      (token.startsWith("*") && token.endsWith("*") && token.length > 2) ||
      (token.startsWith("_") && token.endsWith("_") && token.length > 2)
    ) {
      return (
        <em key={i} className="italic text-neutral-300 select-text">
          {token.slice(1, -1)}
        </em>
      );
    }

    // Links [label](url)
    const linkMatch = token.match(/^\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)$/);
    if (linkMatch) {
      return (
        <a
          key={i}
          href={linkMatch[2]}
          target="_blank"
          rel="noopener noreferrer"
          className="text-white underline decoration-white/40 hover:decoration-white transition-colors select-text"
        >
          {linkMatch[1]}
        </a>
      );
    }

    return <span key={i}>{token}</span>;
  });
}

// Parses non-code text blocks into paragraphs, headings, blockquotes, and lists
function renderTextBlock(block: string, blockKey: number): React.ReactNode {
  const lines = block.split("\n");
  const elements: React.ReactNode[] = [];
  let currentList: { type: "ul" | "ol"; items: string[] } | null = null;

  const flushList = () => {
    if (!currentList) return;
    const ListTag = currentList.type;
    const items = [...currentList.items];
    const key = `list-${elements.length}`;
    elements.push(
      <ListTag
        key={key}
        className={`my-2 pl-5 space-y-1 ${
          currentList.type === "ul" ? "list-disc list-outside" : "list-decimal list-outside"
        }`}
      >
        {items.map((item, idx) => (
          <li key={idx} className="leading-relaxed select-text">
            {renderInlineMarkdown(item)}
          </li>
        ))}
      </ListTag>
    );
    currentList = null;
  };

  for (let i = 0; i < lines.length; i++) {
    const rawLine = lines[i];
    const trimmed = rawLine.trim();

    if (!trimmed) {
      flushList();
      continue;
    }

    // Headings
    if (trimmed.startsWith("### ")) {
      flushList();
      elements.push(
        <h3 key={`h3-${i}`} className="text-sm font-semibold text-white mt-3 mb-1.5 select-text">
          {renderInlineMarkdown(trimmed.slice(4))}
        </h3>
      );
      continue;
    }
    if (trimmed.startsWith("## ")) {
      flushList();
      elements.push(
        <h2 key={`h2-${i}`} className="text-base font-semibold text-white mt-4 mb-2 select-text">
          {renderInlineMarkdown(trimmed.slice(3))}
        </h2>
      );
      continue;
    }
    if (trimmed.startsWith("# ")) {
      flushList();
      elements.push(
        <h1 key={`h1-${i}`} className="text-lg font-bold text-white mt-4 mb-2 select-text">
          {renderInlineMarkdown(trimmed.slice(2))}
        </h1>
      );
      continue;
    }

    // Blockquote
    if (trimmed.startsWith("> ")) {
      flushList();
      elements.push(
        <blockquote
          key={`quote-${i}`}
          className="my-2 pl-3 border-l-2 border-white/30 text-neutral-300 italic select-text"
        >
          {renderInlineMarkdown(trimmed.slice(2))}
        </blockquote>
      );
      continue;
    }

    // Unordered list item
    const ulMatch = trimmed.match(/^[-*]\s+(.*)$/);
    if (ulMatch) {
      if (currentList && currentList.type !== "ul") flushList();
      if (!currentList) currentList = { type: "ul", items: [] };
      currentList.items.push(ulMatch[1]);
      continue;
    }

    // Ordered list item
    const olMatch = trimmed.match(/^\d+\.\s+(.*)$/);
    if (olMatch) {
      if (currentList && currentList.type !== "ol") flushList();
      if (!currentList) currentList = { type: "ol", items: [] };
      currentList.items.push(olMatch[1]);
      continue;
    }

    // Regular paragraph line
    flushList();
    elements.push(
      <p key={`p-${i}`} className="leading-relaxed my-1 select-text">
        {renderInlineMarkdown(trimmed)}
      </p>
    );
  }

  flushList();

  return (
    <div key={blockKey} className="space-y-1">
      {elements}
    </div>
  );
}

// Main Markdown Content Renderer
export const MarkdownContent: React.FC<MarkdownContentProps> = ({ content }) => {
  if (!content) return null;

  // Handle in-progress code blocks gracefully during streaming
  const backtickMatches = content.match(/```/g);
  const isUnclosed = backtickMatches && backtickMatches.length % 2 !== 0;
  const safeContent = isUnclosed ? content + "\n```" : content;

  const segments = safeContent.split(/(```[\s\S]*?```)/g);

  return (
    <div className="chat-message-content select-text text-neutral-200">
      {segments.map((segment, idx) => {
        if (segment.startsWith("```") && segment.endsWith("```")) {
          const firstLineBreak = segment.indexOf("\n");
          const language =
            firstLineBreak > 3
              ? segment.slice(3, firstLineBreak).trim()
              : "";
          const code =
            firstLineBreak !== -1
              ? segment.slice(firstLineBreak + 1, -3)
              : segment.slice(3, -3);

          return <CodeBlock key={idx} language={language} code={code} />;
        }

        return renderTextBlock(segment, idx);
      })}
    </div>
  );
};
