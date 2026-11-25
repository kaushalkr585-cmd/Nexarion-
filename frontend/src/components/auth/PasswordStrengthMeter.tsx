import React from "react";
import type { PasswordStrengthEvaluation } from "../../utils/passwordStrength";

interface PasswordStrengthMeterProps {
  password: string;
  evaluation: PasswordStrengthEvaluation;
  showRequirements?: boolean;
}

const SCORE_COLORS: Record<number, string> = {
  0: "bg-red-500",
  1: "bg-orange-500",
  2: "bg-amber-400",
  3: "bg-emerald-400",
  4: "bg-emerald-300",
};

const LABEL_TEXT_COLORS: Record<number, string> = {
  0: "text-red-400",
  1: "text-orange-400",
  2: "text-amber-300",
  3: "text-emerald-400",
  4: "text-emerald-300",
};

export const PasswordStrengthMeter: React.FC<PasswordStrengthMeterProps> = ({
  password,
  evaluation,
  showRequirements = true,
}) => {
  const hasTyped = password.length > 0;
  const filledSegments = hasTyped ? evaluation.score + 1 : 0;
  const barColor = SCORE_COLORS[evaluation.score] || "bg-red-500";
  const labelColor = LABEL_TEXT_COLORS[evaluation.score] || "text-neutral-400";

  const requirements = [
    {
      key: "minLength",
      label: "At least 12 characters (long passphrases encouraged)",
      met: evaluation.checks.minLength,
    },
    {
      key: "notCommon",
      label: "Not a common or easily guessed password",
      met: hasTyped && evaluation.checks.notCommon,
    },
    {
      key: "noSequence",
      label: "No predictable sequences (e.g. 123456, abcdef, qwerty) or repeats",
      met: hasTyped && evaluation.checks.noPredictableSequence && evaluation.checks.noRepeatedPattern,
    },
    {
      key: "noPersonalInfo",
      label: "Does not contain your name or email address",
      met: hasTyped && evaluation.checks.noPersonalInfo,
    },
  ];

  return (
    <div className="space-y-2.5 pt-1" data-testid="password-strength-meter">
      <div className="space-y-1.5">
        <div className="flex items-center justify-between text-[11px] font-mono">
          <span className="text-neutral-400">Password strength</span>
          <span
            className={`font-semibold ${hasTyped ? labelColor : "text-neutral-500"}`}
            data-testid="password-strength-label"
          >
            {hasTyped ? evaluation.label : "Not entered"}
          </span>
        </div>

        <div className="grid grid-cols-5 gap-1.5" role="progressbar" aria-valuenow={hasTyped ? evaluation.score + 1 : 0} aria-valuemin={0} aria-valuemax={5}>
          {[0, 1, 2, 3, 4].map((segment) => (
            <div
              key={segment}
              className={`h-1.5 rounded-full transition-colors duration-200 ${
                segment < filledSegments ? barColor : "bg-white/10"
              }`}
            />
          ))}
        </div>
      </div>

      {hasTyped && !evaluation.acceptable && (
        <div className="p-2.5 rounded-lg bg-amber-500/10 border border-amber-500/20 text-[11px] text-amber-200/95 space-y-1 leading-relaxed">
          {evaluation.warning && <div className="font-medium">{evaluation.warning}</div>}
          {evaluation.suggestions.length > 0 && (
            <ul className="list-disc pl-4 space-y-0.5 text-amber-200/80">
              {evaluation.suggestions.slice(0, 2).map((s) => (
                <li key={s}>{s}</li>
              ))}
            </ul>
          )}
        </div>
      )}

      {showRequirements && (
        <ul className="space-y-1 text-[11px] text-neutral-400">
          {requirements.map((req) => (
            <li key={req.key} className="flex items-center gap-1.5 leading-snug">
              <span
                className={`inline-block w-1.5 h-1.5 rounded-full shrink-0 ${
                  !hasTyped
                    ? "bg-neutral-600"
                    : req.met
                    ? "bg-emerald-400"
                    : "bg-red-400/80"
                }`}
              />
              <span className={hasTyped && req.met ? "text-neutral-200" : "text-neutral-400"}>
                {req.label}
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
};
