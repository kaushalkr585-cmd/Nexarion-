import React, { useEffect, useState } from "react";
import type { Attachment } from "../../types";
import { attachmentApi } from "../../services/api";
import {
  CloseIcon,
  DiffIcon,
  DownloadIcon,
  FileCodeIcon,
  FilePdfIcon,
  FileTextIcon,
} from "../icons/Icons";

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

interface FilePreviewModalProps {
  attachment: Attachment | null;
  isOpen: boolean;
  onClose: () => void;
  onDownload?: (att: Attachment) => void;
}

export const FilePreviewModal: React.FC<FilePreviewModalProps> = ({
  attachment,
  isOpen,
  onClose,
  onDownload,
}) => {
  const [content, setContent] = useState<string>("");
  const [isLoading, setIsLoading] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [isDownloading, setIsDownloading] = useState(false);

  useEffect(() => {
    if (!isOpen || !attachment) {
      setContent("");
      setLoadError(null);
      return;
    }

    if (attachment.content) {
      setContent(attachment.content);
      return;
    }

    if (attachment.file && attachment.file_type !== "pdf") {
      const reader = new FileReader();
      reader.onload = () => {
        setContent(String(reader.result || ""));
      };
      reader.onerror = () => {
        setLoadError("Failed to read local file.");
      };
      reader.readAsText(attachment.file);
      return;
    }

    if (attachment.id && !attachment.id.startsWith("temp-")) {
      setIsLoading(true);
      setLoadError(null);
      attachmentApi
        .getContent(attachment.id)
        .then((res) => {
          setContent(res.content || "");
        })
        .catch((err) => {
          console.error("Failed to load attachment content:", err);
          setLoadError("Could not load document preview. You can still download the file.");
        })
        .finally(() => {
          setIsLoading(false);
        });
    }
  }, [isOpen, attachment]);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape" && isOpen) {
        onClose();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isOpen, onClose]);

  if (!isOpen || !attachment) return null;

  const isDiff =
    attachment.file_type === "diff" ||
    attachment.filename.endsWith(".diff") ||
    attachment.filename.endsWith(".patch");
  const isPdf = attachment.file_type === "pdf" || attachment.filename.endsWith(".pdf");
  const isCode =
    attachment.file_type === "code" ||
    /\.(py|js|ts|tsx|jsx|json|yaml|yml)$/i.test(attachment.filename);

  const handleDownloadClick = async () => {
    if (!attachment) return;
    setIsDownloading(true);
    try {
      if (onDownload) {
        await onDownload(attachment);
      } else {
        await attachmentApi.downloadAttachment(attachment);
      }
    } catch (err) {
      console.error("Download failed:", err);
    } finally {
      setIsDownloading(false);
    }
  };

  const renderFileIcon = () => {
    if (isDiff) return <DiffIcon className="w-5 h-5 text-amber-400" />;
    if (isPdf) return <FilePdfIcon className="w-5 h-5 text-red-400" />;
    if (isCode) return <FileCodeIcon className="w-5 h-5 text-emerald-400" />;
    return <FileTextIcon className="w-5 h-5 text-blue-400" />;
  };

  const renderDiffLines = (diffText: string) => {
    const lines = diffText.split("\n");
    return (
      <div className="font-mono text-xs leading-5 select-text">
        {lines.map((line, idx) => {
          let lineBg = "hover:bg-white/[0.03]";
          let lineText = "text-neutral-300";
          let lineSign = " ";

          if (line.startsWith("+") && !line.startsWith("+++")) {
            lineBg = "bg-emerald-950/40 border-l-2 border-emerald-500";
            lineText = "text-emerald-200";
            lineSign = "+";
          } else if (line.startsWith("-") && !line.startsWith("---")) {
            lineBg = "bg-red-950/40 border-l-2 border-red-500";
            lineText = "text-red-200";
            lineSign = "-";
          } else if (line.startsWith("@@")) {
            lineBg = "bg-cyan-950/40 text-cyan-300 font-semibold border-l-2 border-cyan-400";
            lineText = "text-cyan-300";
          }

          return (
            <div
              key={idx}
              className={`flex items-start px-3 py-0.5 ${lineBg} font-mono`}
            >
              <span className="w-10 flex-shrink-0 text-right pr-3 select-none text-[10px] text-neutral-600">
                {idx + 1}
              </span>
              <span className="w-4 flex-shrink-0 select-none text-[10px] font-bold text-neutral-500">
                {lineSign !== " " ? lineSign : ""}
              </span>
              <span className={`flex-1 whitespace-pre-wrap break-all ${lineText}`}>
                {line}
              </span>
            </div>
          );
        })}
      </div>
    );
  };

  const renderCodeLines = (codeText: string) => {
    const lines = codeText.split("\n");
    return (
      <div className="font-mono text-xs leading-5 select-text">
        {lines.map((line, idx) => (
          <div
            key={idx}
            className="flex items-start px-3 py-0.5 hover:bg-white/[0.03]"
          >
            <span className="w-10 flex-shrink-0 text-right pr-3 select-none text-[10px] text-neutral-600">
              {idx + 1}
            </span>
            <span className="flex-1 whitespace-pre-wrap break-all text-neutral-200">
              {line || " "}
            </span>
          </div>
        ))}
      </div>
    );
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-3 sm:p-6 bg-black/80 backdrop-blur-md animate-fade-in"
      onClick={onClose}
      role="dialog"
      aria-modal="true"
      aria-labelledby="file-preview-title"
    >
      <div
        className="relative w-full max-w-4xl max-h-[90vh] flex flex-col bg-neutral-950 border border-white/15 rounded-2xl shadow-2xl overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >

        <header className="flex-shrink-0 flex items-center justify-between px-5 py-3.5 border-b border-white/10 bg-black/70">
          <div className="flex items-center gap-3 min-w-0">
            <div className="p-2 rounded-xl bg-white/5 border border-white/10 flex-shrink-0">
              {renderFileIcon()}
            </div>
            <div className="min-w-0">
              <h2
                id="file-preview-title"
                className="text-sm font-semibold text-white truncate max-w-md font-mono"
                title={attachment.filename}
              >
                {attachment.filename}
              </h2>
              <div className="flex items-center gap-2 mt-0.5 text-[11px] text-neutral-400 font-mono">
                <span>{formatBytes(attachment.file_size)}</span>
                {attachment.page_count ? (
                  <>
                    <span>•</span>
                    <span>{attachment.page_count} pages</span>
                  </>
                ) : null}
                <span>•</span>
                <span className="uppercase text-neutral-300 font-semibold">
                  {isDiff
                    ? "Unified Diff"
                    : isPdf
                    ? "PDF Document"
                    : isCode
                    ? "Source Code"
                    : "Plain Text"}
                </span>
              </div>
            </div>
          </div>

          <div className="flex items-center gap-2 flex-shrink-0">
            <button
              type="button"
              onClick={handleDownloadClick}
              disabled={isDownloading}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-white/10 hover:bg-white/20 text-white border border-white/15 text-xs font-mono transition-colors cursor-pointer disabled:opacity-50"
              title="Download file"
              aria-label={`Download ${attachment.filename}`}
            >
              <DownloadIcon className="w-3.5 h-3.5" />
              <span className="hidden sm:inline">
                {isDownloading ? "Downloading..." : "Download"}
              </span>
            </button>
            <button
              type="button"
              onClick={onClose}
              className="p-1.5 rounded-xl text-neutral-400 hover:text-white hover:bg-white/10 transition-colors"
              aria-label="Close preview"
            >
              <CloseIcon className="w-4 h-4" />
            </button>
          </div>
        </header>

        <div className="flex-1 overflow-auto p-4 bg-black/40 min-h-[280px]">
          {isLoading ? (
            <div className="h-64 flex flex-col items-center justify-center space-y-3 font-mono text-xs text-neutral-400">
              <div className="w-6 h-6 border-2 border-white/20 border-t-white rounded-full animate-spin" />
              <span>Loading file preview...</span>
            </div>
          ) : loadError ? (
            <div className="p-6 text-center space-y-4">
              <p className="text-xs text-red-400 font-mono">{loadError}</p>
              <button
                type="button"
                onClick={handleDownloadClick}
                className="btn-silver inline-flex"
              >
                <DownloadIcon className="w-4 h-4" />
                <span>Download {attachment.filename}</span>
              </button>
            </div>
          ) : content ? (
            <div className="rounded-xl border border-white/10 bg-black/60 overflow-hidden">
              {isDiff
                ? renderDiffLines(content)
                : isCode
                ? renderCodeLines(content)
                : (
                  <div className="p-4 text-xs font-mono text-neutral-200 whitespace-pre-wrap select-text leading-relaxed">
                    {content}
                  </div>
                )}
            </div>
          ) : (
            <div className="h-48 flex items-center justify-center text-xs text-neutral-500 font-mono">
              No preview content available.
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
