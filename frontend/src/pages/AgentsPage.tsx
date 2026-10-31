import React from "react";
import type { AgentConfig } from "../types";
import { AgentIcon } from "../components/icons/Icons";

interface AgentCardProps {
  agent: AgentConfig;
  onToggle: (agentId: string, isEnabled: boolean) => void;
}

const AgentCard: React.FC<AgentCardProps> = React.memo(
  ({ agent, onToggle }) => {
    const isEnabled = Boolean(agent.is_enabled);

    return (
      <div
        className={`glass-card p-6 rounded-2xl flex flex-col justify-between space-y-4 transition-all duration-200 border ${
          isEnabled ? "border-white/10 bg-white/[0.02]" : "border-white/5 bg-black/20 opacity-80"
        }`}
      >
        <div>
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center gap-2.5">
              <div
                className={`p-2 rounded-xl transition-colors duration-150 ${
                  isEnabled ? "bg-emerald-500/10 text-emerald-400" : "bg-white/5 text-neutral-400"
                }`}
              >
                <AgentIcon className="w-5 h-5" />
              </div>
              <div>
                <h3 className="text-sm sm:text-base font-semibold text-white">{agent.name}</h3>
                <span className="text-[10px] font-mono text-neutral-400 uppercase tracking-wider">
                  ID: {agent.agent_id}
                </span>
              </div>
            </div>

            <button
              type="button"
              role="switch"
              aria-checked={isEnabled}
              onClick={() => onToggle(agent.agent_id, !isEnabled)}
              className={`w-12 h-6 flex items-center rounded-full p-1 transition-colors duration-150 ease-out focus:outline-none focus:ring-2 focus:ring-emerald-500/40 cursor-pointer ${
                isEnabled ? "bg-emerald-500" : "bg-neutral-800"
              }`}
              aria-label={`Toggle ${agent.name}`}
            >
              <div
                className={`bg-white w-4 h-4 rounded-full shadow-md transform transition-transform duration-150 ease-out ${
                  isEnabled ? "translate-x-6" : "translate-x-0"
                }`}
              />
            </button>
          </div>

          <p className="text-xs text-neutral-300 leading-relaxed font-sans mb-4">
            {agent.description}
          </p>

          <div className="space-y-1.5">
            <span className="text-[10px] font-mono text-neutral-500 uppercase tracking-wider">
              Capabilities & Checks:
            </span>
            <div className="flex flex-wrap gap-1.5">
              {agent.capabilities?.map((cap, i) => (
                <span
                  key={i}
                  className="px-2 py-0.5 rounded-md bg-white/5 border border-white/10 text-[11px] font-mono text-neutral-300"
                >
                  {cap}
                </span>
              ))}
            </div>
          </div>
        </div>

        <div className="pt-3 border-t border-white/10 flex items-center justify-between text-[11px] font-mono text-neutral-400">
          <span className="flex items-center gap-1.5">
            <span
              className={`w-2 h-2 rounded-full transition-colors duration-150 ${
                isEnabled
                  ? "bg-emerald-400 shadow-[0_0_8px_rgba(52,211,153,0.6)]"
                  : "bg-neutral-500"
              }`}
            />
            <span className={isEnabled ? "text-emerald-300" : "text-neutral-400"}>
              Status: {isEnabled ? "Active in Pipeline" : "Disabled (Excluded)"}
            </span>
          </span>
          <span>Model: {agent.model_name || "default"}</span>
        </div>
      </div>
    );
  },
  (prev, next) =>
    prev.agent.id === next.agent.id &&
    prev.agent.is_enabled === next.agent.is_enabled &&
    prev.agent.name === next.agent.name &&
    prev.agent.description === next.agent.description &&
    prev.onToggle === next.onToggle
);

AgentCard.displayName = "AgentCard";

interface AgentsPageProps {
  agents: AgentConfig[];
  onToggleAgent: (agentId: string, isEnabled: boolean) => Promise<void> | void;
}

export const AgentsPage: React.FC<AgentsPageProps> = React.memo(({ agents, onToggleAgent }) => {
  return (
    <div className="max-w-6xl mx-auto px-6 py-8 space-y-6 relative z-10 text-left">
      <div className="pb-6 border-b border-white/10">
        <h1 className="text-2xl sm:text-3xl font-semibold text-white tracking-tight">
          Specialized AI Review Agents
        </h1>
        <p className="text-xs sm:text-sm text-neutral-400 mt-1">
          Coordinated multi-agent architecture with deterministic linters and reasoning engines
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {agents.map((agent) => (
          <AgentCard key={agent.id || agent.agent_id} agent={agent} onToggle={onToggleAgent} />
        ))}
      </div>
    </div>
  );
});

AgentsPage.displayName = "AgentsPage";
