import React from "react";
import { CloseIcon, SecurityIcon } from "../icons/Icons";

export type ResourceType =
  | "docs"
  | "getting-started"
  | "security"
  | "support"
  | "privacy"
  | "terms";

interface ResourceModalProps {
  resource: ResourceType | null;
  onClose: () => void;
}

export const ResourceModal: React.FC<ResourceModalProps> = ({ resource, onClose }) => {
  if (!resource) return null;

  const contentMap: Record<
    ResourceType,
    { title: string; subtitle: string; body: React.ReactNode }
  > = {
    docs: {
      title: "NEXARION Documentation",
      subtitle: "Multi-Agent Code Review Architecture and Pipeline Specifications",
      body: (
        <div className="space-y-4 text-xs text-neutral-300 leading-relaxed font-sans">
          <p>
            NEXARION is an autonomous code review intelligence that coordinates specialist
            AI agents to review GitHub pull requests and git diff patches.
          </p>
          <div className="p-3 rounded-xl bg-black/60 border border-white/10 font-mono text-[11px] space-y-1">
            <div className="text-white font-semibold">Pipeline Architecture:</div>
            <div>1. AST Agent: Syntactic complexity, nesting depth, and structural anomalies.</div>
            <div>2. Ruff Agent: Fast Python linting and code convention enforcement.</div>
            <div>3. Bandit Agent: AST-based static vulnerability scanning (B101-B703).</div>
            <div>4. LLM Agent: Semantic logic bug detection via Ollama or NVIDIA NIM.</div>
            <div>5. Orchestrator: Deduplication, ranking, and severity sorting.</div>
          </div>
        </div>
      ),
    },
    "getting-started": {
      title: "Getting Started with NEXARION",
      subtitle: "Quick setup for developer code reviews",
      body: (
        <div className="space-y-4 text-xs text-neutral-300 leading-relaxed font-sans">
          <p>To analyze your code in NEXARION:</p>
          <ol className="list-decimal list-inside space-y-2 text-neutral-200">
            <li>
              <strong>AI Assistant:</strong> Open the AI Assistant in the sidebar and type your code question or attach a git diff.
            </li>
            <li>
              <strong>Pull Requests:</strong> Inspect queued pull requests and click &quot;Run Agent Review&quot;.
            </li>
            <li>
              <strong>Direct Patch Review:</strong> Click &quot;+ Review&quot; in the sidebar or &quot;Start a Review&quot; in the closing section to paste any unified diff.
            </li>
            <li>
              <strong>AI Providers:</strong> Switch between offline local Ollama and high-reasoning cloud inference in Settings.
            </li>
          </ol>
        </div>
      ),
    },
    security: {
      title: "Security & Threat Model",
      subtitle: "Zero secret exposure and isolated review execution",
      body: (
        <div className="space-y-4 text-xs text-neutral-300 leading-relaxed font-sans">
          <div className="flex items-center gap-2 p-3 rounded-xl bg-white/5 border border-white/10 text-white">
            <SecurityIcon className="w-5 h-5 text-white" />
            <span>Strict server-side credential isolation enforced.</span>
          </div>
          <p>
            - Code diffs are analyzed strictly within memory during review execution.
          </p>
          <p>
            - Offline inference via Ollama runs entirely on your local hardware with no external network telemetry.
          </p>
          <p>
            - Cloud inference via NVIDIA NIM uses encrypted TLS 1.3 endpoints.
          </p>
        </div>
      ),
    },
    support: {
      title: "Developer Support",
      subtitle: "Assistance and diagnostics",
      body: (
        <div className="space-y-4 text-xs text-neutral-300 leading-relaxed font-sans">
          <p>
            Need help configuring local Ollama models, PostgreSQL databases, or custom agents?
          </p>
          <div className="p-3 rounded-xl bg-black/60 border border-white/10 font-mono text-[11px] space-y-1 text-neutral-300">
            <div>Repository: Multi Agent Code Review System</div>
            <div>CLI Tool: <code>python -m code_review --help</code></div>
            <div>Documentation: <code>docs/milestone_*.md</code></div>
          </div>
        </div>
      ),
    },
    privacy: {
      title: "Privacy Statement",
      subtitle: "Current data handling policy",
      body: (
        <div className="space-y-4 text-xs text-neutral-300 leading-relaxed font-sans">
          <p>
            This application is deployed in your private environment. Stored database records
            include user authentication credentials, pull requests, and review execution findings.
          </p>
          <p className="text-neutral-400">
            Code diffs sent to local Ollama never leave your machine.
          </p>
        </div>
      ),
    },
    terms: {
      title: "Terms of Service",
      subtitle: "Platform usage and license guidelines",
      body: (
        <div className="space-y-4 text-xs text-neutral-300 leading-relaxed font-sans">
          <p>
            NEXARION is distributed under the MIT open-source license. Automated AI review
            findings are provided as engineering recommendations. Developers remain
            responsible for testing and validating their code changes prior to deployment.
          </p>
        </div>
      ),
    },
  };

  const item = contentMap[resource];

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-md animate-fade-in text-left">
      <div className="relative w-full max-w-lg rounded-2xl bg-[#0F0F0F] border border-white/20 shadow-2xl p-6 overflow-hidden">
        <div className="flex items-center justify-between pb-4 border-b border-white/10">
          <div>
            <h2 className="text-base font-semibold text-white">{item.title}</h2>
            <p className="text-xs text-neutral-400">{item.subtitle}</p>
          </div>
          <button
            onClick={onClose}
            className="p-1 rounded-lg text-neutral-400 hover:text-white hover:bg-white/10"
            aria-label="Close"
          >
            <CloseIcon className="w-5 h-5" />
          </button>
        </div>

        <div className="py-5">{item.body}</div>

        <div className="pt-4 border-t border-white/10 flex justify-end">
          <button onClick={onClose} className="btn-silver text-xs py-1.5 px-4">
            Close
          </button>
        </div>
      </div>
    </div>
  );
};
