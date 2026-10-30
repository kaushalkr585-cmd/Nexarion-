import React, { useEffect, useRef, useState } from "react";
import type { ProviderStatusResponse } from "../../types";

export interface SelectedModel {
  provider: "ollama" | "nvidia";
  model?: string;
}

export interface ModelOption {
  id: "ollama" | "nvidia";
  provider: "ollama" | "nvidia";
  displayName: string;
  providerBadge: string;
  roleDescription: string;
  isAvailable: boolean;
  statusNote: string;
}

interface ModelSelectorProps {
  providerStatus: ProviderStatusResponse | null;
  selectedModel: SelectedModel;
  onSelectModel: (model: SelectedModel) => void;
  disabled?: boolean;
}

export const ModelSelector: React.FC<ModelSelectorProps> = ({
  providerStatus,
  selectedModel,
  onSelectModel,
  disabled = false,
}) => {
  const [isOpen, setIsOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement | null>(null);

  const ollamaProvider = providerStatus?.providers.find((p) => p.provider === "ollama");
  const nvidiaProvider = providerStatus?.providers.find((p) => p.provider === "nvidia");

  const modelOptions: ModelOption[] = [
    {
      id: "ollama",
      provider: "ollama",
      displayName: "Ollama",
      providerBadge: "Local",
      roleDescription: "Local model — runs through the configured Ollama service.",
      isAvailable: ollamaProvider?.is_available ?? false,
      statusNote: (ollamaProvider?.is_available ?? false)
        ? "Online"
        : "Offline — Ollama server not detected on localhost:11434",
    },
    {
      id: "nvidia",
      provider: "nvidia",
      displayName: "Nemotron",
      providerBadge: "Cloud",
      roleDescription: "Hosted model — runs through the configured cloud inference service.",
      isAvailable: nvidiaProvider?.is_available ?? false,
      statusNote: (nvidiaProvider?.is_available ?? false)
        ? "Online"
        : "Offline — API key missing or endpoint unreachable",
    },
  ];

  const activeOption =
    modelOptions.find((opt) => opt.provider === selectedModel.provider) || modelOptions[0];

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(event.target as Node)) {
        setIsOpen(false);
      }
    };
    if (isOpen) {
      document.addEventListener("mousedown", handleClickOutside);
    }
    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
    };
  }, [isOpen]);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Escape") {
      setIsOpen(false);
    }
  };

  return (
    <div
      ref={containerRef}
      className="relative inline-block text-left"
      onKeyDown={handleKeyDown}
    >

      <button
        type="button"
        id="model-selector-button"
        aria-haspopup="listbox"
        aria-expanded={isOpen}
        aria-label="Select AI reasoning model"
        disabled={disabled}
        onClick={() => !disabled && setIsOpen(!isOpen)}
        className={`group flex items-center gap-1.5 px-2.5 py-1.5 rounded-xl text-xs font-mono transition-all border ${
          isOpen
            ? "bg-neutral-800 border-white/40 text-white shadow-lg"
            : "bg-black/60 border-white/15 text-neutral-300 hover:text-white hover:bg-white/10 hover:border-white/30"
        } ${disabled ? "opacity-40 cursor-not-allowed" : "cursor-pointer"}`}
      >

        <svg
          className="w-3.5 h-3.5 flex-shrink-0 text-neutral-400 group-hover:text-white transition-colors"
          viewBox="0 0 16 16"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.5"
          aria-hidden="true"
        >
          <rect x="3" y="3" width="10" height="10" rx="2" />
          <path d="M6 1v2M10 1v2M6 13v2M10 13v2M1 6h2M1 10h2M13 6h2M13 10h2" strokeLinecap="round" />
        </svg>

        <span className="font-medium tracking-tight text-[11px] truncate max-w-[130px]">
          {activeOption.providerBadge} — {activeOption.displayName}
        </span>

        <svg
          className={`w-3 h-3 text-neutral-400 group-hover:text-white transition-transform flex-shrink-0 ${
            isOpen ? "rotate-180" : ""
          }`}
          viewBox="0 0 16 16"
          fill="currentColor"
          aria-hidden="true"
        >
          <path
            fillRule="evenodd"
            d="M1.646 4.646a.5.5 0 0 1 .708 0L8 10.293l5.646-5.647a.5.5 0 0 1 .708.708l-6 6a.5.5 0 0 1-.708 0l-6-6a.5.5 0 0 1 0-.708z"
          />
        </svg>
      </button>

      {isOpen && (
        <div
          role="listbox"
          aria-labelledby="model-selector-button"
          className="absolute bottom-full mb-2 left-0 w-72 sm:w-80 rounded-2xl bg-[#0D0D0D] border border-white/20 shadow-2xl backdrop-blur-xl p-2 z-50 animate-fade-in focus:outline-none"
        >

          <div className="px-2 py-1.5 border-b border-white/10 mb-1 flex items-center justify-between">
            <span className="text-[10px] font-mono tracking-wider uppercase text-neutral-400 font-semibold">
              Select Inference Model
            </span>
            <span className="text-[10px] font-mono text-neutral-500">
              Esc to close
            </span>
          </div>

          <div className="space-y-1">
            {modelOptions.map((opt) => {
              const isSelected = opt.provider === selectedModel.provider;

              return (
                <button
                  key={opt.id}
                  role="option"
                  aria-selected={isSelected}
                  disabled={!opt.isAvailable}
                  type="button"
                  onClick={() => {
                    if (opt.isAvailable) {
                      onSelectModel({ provider: opt.provider });
                      setIsOpen(false);
                    }
                  }}
                  className={`w-full text-left p-2.5 rounded-xl transition-all flex items-start justify-between gap-2.5 ${
                    isSelected
                      ? "bg-white/15 border border-white/30 text-white"
                      : opt.isAvailable
                      ? "hover:bg-white/5 text-neutral-300 hover:text-white border border-transparent"
                      : "opacity-45 cursor-not-allowed border border-transparent text-neutral-500"
                  }`}
                >
                  <div className="flex-1 min-w-0">

                    <div className="flex items-center gap-2">
                      <span className="font-semibold text-xs tracking-tight text-white">
                        {opt.providerBadge} — {opt.displayName}
                      </span>
                    </div>

                    <p className="text-[11px] text-neutral-400 mt-1 leading-snug">
                      {opt.roleDescription}
                    </p>

                    {!opt.isAvailable && (
                      <p className="text-[10px] text-amber-400/90 mt-1 font-mono">
                        {opt.statusNote}
                      </p>
                    )}
                  </div>

                  {isSelected && (
                    <div className="mt-1 flex-shrink-0">
                      <svg
                        className="w-3.5 h-3.5 text-white"
                        viewBox="0 0 16 16"
                        fill="currentColor"
                        aria-hidden="true"
                      >
                        <path d="M13.854 3.646a.5.5 0 0 1 0 .708l-7 7a.5.5 0 0 1-.708 0l-3.5-3.5a.5.5 0 1 1 .708-.708L6.5 10.293l6.646-6.647a.5.5 0 0 1 .708 0z" />
                      </svg>
                    </div>
                  )}
                </button>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
};
