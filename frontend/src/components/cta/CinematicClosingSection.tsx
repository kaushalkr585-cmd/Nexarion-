import React from "react";
import type { NavView } from "../../types";
import {
  ArrowRightIcon,
  GithubIcon,
  LogoIcon,
  SparkleIcon,
} from "../icons/Icons";

interface CinematicClosingSectionProps {
  onStartReview: () => void;
  onNavigate: (view: NavView) => void;
  onOpenResource: (resource: "docs" | "getting-started" | "security" | "support" | "privacy" | "terms") => void;
}

export const CinematicClosingSection: React.FC<CinematicClosingSectionProps> = ({
  onStartReview,
  onNavigate,
  onOpenResource,
}) => {
  return (
    <section className="relative w-full bg-[#0D0D0D] text-white pt-24 pb-12 overflow-hidden border-t border-white/10 select-none">

      <div
        className="absolute top-0 right-1/4 w-[600px] h-[400px] bg-[#F0A24C]/[0.04] blur-[120px] rounded-full pointer-events-none"
        aria-hidden="true"
      />
      <div
        className="absolute bottom-1/3 left-1/4 w-[500px] h-[350px] bg-[#7A5832]/[0.05] blur-[100px] rounded-full pointer-events-none"
        aria-hidden="true"
      />

      <div className="max-w-7xl mx-auto px-6 md:px-12 relative z-10">

        <div className="grid grid-cols-1 lg:grid-cols-12 gap-12 lg:gap-8 items-center mb-28">

          <div className="lg:col-span-6 space-y-6">

            <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full bg-[#2C241D]/90 border border-[#F0A24C]/35 text-[#F0A24C] text-[11px] font-semibold tracking-wider uppercase font-mono shadow-sm">
              <SparkleIcon className="w-3.5 h-3.5 text-[#F0A24C]" />
              <span>BUILT FOR BETTER CODE</span>
            </div>

            <h2 className="text-4xl sm:text-5xl lg:text-6xl font-light text-white tracking-tight leading-[1.08]">
              Ship better code.
              <br />
              <span className="font-serif-italic font-normal text-white/95">
                Build with confidence.
              </span>
            </h2>

            <p className="text-sm sm:text-base text-[#ADADAD] leading-relaxed max-w-xl font-sans">
              Bring your code review workflow together with specialized AI agents that help
              uncover security risks, improve code quality, and make every review more deliberate.
            </p>

            <div className="pt-2 flex flex-wrap items-center gap-5">
              <button
                onClick={onStartReview}
                className="btn-amber-glass"
                aria-label="Start a Review"
              >
                <span>Start a Review</span>
                <ArrowRightIcon className="w-4 h-4 text-white" />
              </button>

              <button
                onClick={() => onNavigate("agents")}
                className="inline-flex items-center gap-1.5 text-sm font-medium text-[#ADADAD] hover:text-[#F0A24C] transition-colors py-2 px-1 focus-visible:outline-none focus-visible:underline"
              >
                <span>Explore the Agents</span>
                <span className="text-[#F0A24C]">→</span>
              </button>
            </div>
          </div>

          <div className="lg:col-span-6 perspective-container relative flex justify-center lg:justify-end">
            <div className="editor-panel-3d w-full max-w-lg rounded-2xl overflow-hidden border border-white/10 p-5 select-text">

              <div className="flex items-center justify-between pb-3.5 mb-3.5 border-b border-white/10 text-xs font-mono">
                <div className="flex items-center gap-2">
                  <div className="w-2.5 h-2.5 rounded-full bg-white/20" />
                  <div className="w-2.5 h-2.5 rounded-full bg-white/20" />
                  <div className="w-2.5 h-2.5 rounded-full bg-white/20" />
                  <span className="ml-2 text-white/80 font-medium">pr_#42_auth_security.diff</span>
                </div>
                <div className="flex items-center gap-2 text-[10px] text-[#F0A24C]">
                  <span className="w-1.5 h-1.5 rounded-full bg-[#F0A24C] animate-pulse" />
                  <span>3 AGENTS ACTIVE</span>
                </div>
              </div>

              <div className="space-y-1 font-mono text-[11px] leading-relaxed overflow-hidden">
                <div className="text-neutral-500 py-0.5">@@ -28,7 +28,12 @@ async def verify_token(token: str):</div>
                <div className="text-neutral-400 py-0.5">     payload = jwt.decode(token, SECRET_KEY)</div>
                <div className="bg-red-500/10 text-neutral-400 line-through py-0.5 px-2 rounded -mx-2">
                  -    if not payload.get(&quot;is_admin&quot;): raise PermissionError()
                </div>
                <div className="bg-emerald-500/10 text-neutral-200 py-0.5 px-2 rounded -mx-2 flex items-center justify-between">
                  <span>+    user = await db.query(User).filter_by(id=payload[&quot;sub&quot;]).first()</span>
                </div>
                <div className="bg-emerald-500/10 text-neutral-200 py-0.5 px-2 rounded -mx-2">
                  <span>+    if not user or not user.is_active: return None</span>
                </div>

                <div className="mt-3 p-3 rounded-xl bg-[#2C241D]/90 border border-[#F0A24C]/40 text-left space-y-1 shadow-md">
                  <div className="flex items-center justify-between text-[10px] font-mono">
                    <span className="text-[#F0A24C] font-semibold flex items-center gap-1.5">
                      <span className="w-1.5 h-1.5 rounded-full bg-[#F0A24C]" />
                      SECURITY AGENT • BANDIT B105
                    </span>
                    <span className="text-neutral-400">HIGH SEVERITY</span>
                  </div>
                  <div className="text-xs text-white font-sans font-medium">
                    Session token validation prevents privilege escalation
                  </div>
                  <div className="text-[10px] text-neutral-400 font-sans">
                    Suggestion: Enforce constant-time token comparison for cryptographic safety.
                  </div>
                </div>

                <div className="mt-2.5 pt-2 border-t border-white/5 flex items-center justify-between text-[10px] text-neutral-400 font-mono">
                  <span>AST Depth: 2 (Passed)</span>
                  <span>Ruff Clean (0 lint errors)</span>
                  <span className="text-white/80 font-semibold">Orchestrator: PASS</span>
                </div>
              </div>
            </div>
          </div>
        </div>

        <div className="relative w-full flex items-center justify-center my-6 h-36 md:h-48 overflow-hidden pointer-events-none opacity-85">
          <div className="flex items-center justify-center w-full max-w-4xl px-4 relative">

            <img
              src="/assets/hand_left.png"
              alt=""
              aria-hidden="true"
              className="w-44 sm:w-60 md:w-80 object-contain translate-x-4 drop-shadow-[0_4px_24px_rgba(240,162,76,0.18)]"
            />

            <div
              className="w-8 h-8 rounded-full bg-[#F0A24C]/30 blur-md mx-[-12px] z-10 animate-pulse"
              aria-hidden="true"
            />

            <img
              src="/assets/hand_right.png"
              alt=""
              aria-hidden="true"
              className="w-44 sm:w-60 md:w-80 object-contain translate-x-[-16px] drop-shadow-[0_4px_24px_rgba(240,162,76,0.18)]"
            />
          </div>
        </div>

        <footer className="pt-12 pb-8 border-t border-white/10">
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-10 mb-14 text-left">

            <div className="space-y-4">
              <div className="flex items-center gap-2.5">
                <LogoIcon size={26} />
                <span className="font-semibold text-base tracking-wider text-white">NEXARION</span>
              </div>
              <p className="text-xs text-[#ADADAD] leading-relaxed max-w-xs font-sans">
                Code review with coordinated AI agents. Find risks, improve quality, and ship with confidence.
              </p>
              <div className="flex items-center gap-3 pt-1">
                <a
                  href="https://github.com"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="p-1.5 rounded-lg bg-white/5 hover:bg-white/10 text-[#E0A165] hover:text-[#F0A24C] transition-colors"
                  aria-label="GitHub repository"
                >
                  <GithubIcon className="w-4 h-4" />
                </a>
              </div>
            </div>

            <div className="space-y-3 font-sans">
              <h3 className="text-[11px] font-semibold text-[#7D7D7D] uppercase tracking-wider font-mono">
                Product
              </h3>
              <ul className="space-y-2 text-xs">
                <li>
                  <button
                    onClick={() => onNavigate("overview")}
                    className="text-[#ADADAD] hover:text-white transition-colors"
                  >
                    Overview
                  </button>
                </li>
                <li>
                  <button
                    onClick={() => onNavigate("prs")}
                    className="text-[#ADADAD] hover:text-white transition-colors"
                  >
                    Pull Requests
                  </button>
                </li>
                <li>
                  <button
                    onClick={() => onNavigate("agents")}
                    className="text-[#ADADAD] hover:text-white transition-colors"
                  >
                    AI Agents
                  </button>
                </li>
                <li>
                  <button
                    onClick={() => onNavigate("history")}
                    className="text-[#ADADAD] hover:text-white transition-colors"
                  >
                    Review History
                  </button>
                </li>
              </ul>
            </div>

            <div className="space-y-3 font-sans">
              <h3 className="text-[11px] font-semibold text-[#7D7D7D] uppercase tracking-wider font-mono">
                Resources
              </h3>
              <ul className="space-y-2 text-xs">
                <li>
                  <button
                    onClick={() => onOpenResource("docs")}
                    className="text-[#ADADAD] hover:text-white transition-colors"
                  >
                    Documentation
                  </button>
                </li>
                <li>
                  <button
                    onClick={() => onOpenResource("getting-started")}
                    className="text-[#ADADAD] hover:text-white transition-colors"
                  >
                    Getting Started
                  </button>
                </li>
                <li>
                  <button
                    onClick={() => onOpenResource("security")}
                    className="text-[#ADADAD] hover:text-white transition-colors"
                  >
                    Security Model
                  </button>
                </li>
                <li>
                  <button
                    onClick={() => onOpenResource("support")}
                    className="text-[#ADADAD] hover:text-white transition-colors"
                  >
                    Developer Support
                  </button>
                </li>
              </ul>
            </div>

            <div className="space-y-3 font-sans">
              <h3 className="text-[11px] font-semibold text-[#7D7D7D] uppercase tracking-wider font-mono">
                Workspace
              </h3>
              <ul className="space-y-2 text-xs">
                <li>
                  <button
                    onClick={() => onNavigate("settings")}
                    className="text-[#ADADAD] hover:text-white transition-colors"
                  >
                    AI Provider Settings
                  </button>
                </li>
                <li>
                  <button
                    onClick={() => onNavigate("settings")}
                    className="text-[#ADADAD] hover:text-white transition-colors"
                  >
                    Account Settings
                  </button>
                </li>
                <li>
                  <button
                    onClick={() => onOpenResource("privacy")}
                    className="text-[#ADADAD] hover:text-white transition-colors"
                  >
                    Privacy Statement
                  </button>
                </li>
                <li>
                  <button
                    onClick={() => onOpenResource("terms")}
                    className="text-[#ADADAD] hover:text-white transition-colors"
                  >
                    Terms of Service
                  </button>
                </li>
              </ul>
            </div>
          </div>

          <div className="pt-6 border-t border-white/5 flex flex-col sm:flex-row items-center justify-between text-xs text-[#717171] font-sans gap-3">
            <div>© 2026 NEXARION. Built for better code.</div>
            <div className="font-mono text-[11px]">Specialist Multi-Agent Architecture</div>
          </div>
        </footer>
      </div>

      <div
        className="w-full overflow-hidden flex justify-center pointer-events-none select-none translate-y-6 md:translate-y-12"
        aria-hidden="true"
      >
        <div className="text-[16vw] font-light tracking-[0.22em] text-[#5A3418] leading-none whitespace-nowrap opacity-65 font-sans">
          NEXARION
        </div>
      </div>
    </section>
  );
};
