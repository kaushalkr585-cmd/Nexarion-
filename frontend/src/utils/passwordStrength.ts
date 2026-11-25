import zxcvbn from "zxcvbn";

export const MIN_PASSWORD_LENGTH = 12;
export const MAX_PASSWORD_LENGTH = 128;

export type PasswordStrengthLabel =
  | "Very Weak"
  | "Weak"
  | "Medium"
  | "Strong"
  | "Very Strong";

export interface PasswordPolicyChecks {
  minLength: boolean;
  maxLength: boolean;
  notCommon: boolean;
  noPredictableSequence: boolean;
  noRepeatedPattern: boolean;
  noPersonalInfo: boolean;
  sufficientEntropy: boolean;
}

export interface PasswordStrengthEvaluation {
  score: 0 | 1 | 2 | 3 | 4;
  label: PasswordStrengthLabel;
  acceptable: boolean;
  warning: string;
  suggestions: string[];
  crackTimeDisplay: string;
  checks: PasswordPolicyChecks;
}

const STRENGTH_LABELS: Record<0 | 1 | 2 | 3 | 4, PasswordStrengthLabel> = {
  0: "Very Weak",
  1: "Weak",
  2: "Medium",
  3: "Strong",
  4: "Very Strong",
};

const COMMON_CORES = new Set([
  "password",
  "passw0rd",
  "qwerty",
  "asdfgh",
  "zxcvbn",
  "letmein",
  "welcome",
  "admin",
  "administrator",
  "iloveyou",
  "monkey",
  "dragon",
  "baseball",
  "football",
  "sunshine",
  "princess",
  "nexarion",
]);

const KEYBOARD_ROWS = [
  "qwertyuiop",
  "poiuytrewq",
  "asdfghjkl",
  "lkjhgfdsa",
  "zxcvbnm",
  "mnbvcxz",
  "1234567890",
  "0987654321",
  "abcdefghijklmnopqrstuvwxyz",
  "zyxwvutsrqponmlkjihgfedcba",
];

function extractUserTokens(name?: string, email?: string): string[] {
  const tokens: string[] = [];
  const seen = new Set<string>();

  const addCandidate = (raw?: string) => {
    if (!raw) return;
    for (const part of raw.toLowerCase().split(/[^a-z0-9]+/)) {
      if (part.length >= 3 && !seen.has(part)) {
        seen.add(part);
        tokens.push(part);
      }
    }
  };

  addCandidate(name);
  if (email) {
    const [localPart, domainPart] = email.split("@");
    addCandidate(localPart);
    if (domainPart) {
      addCandidate(domainPart.split(".")[0]);
    }
  }
  return tokens;
}

function hasPredictableSequence(password: string): boolean {
  const lower = password.toLowerCase();
  if (lower.length < 5) return false;

  for (const row of KEYBOARD_ROWS) {
    for (let i = 0; i <= row.length - 5; i += 1) {
      if (lower.includes(row.slice(i, i + 5))) {
        return true;
      }
    }
  }

  let runAsc = 1;
  let runDesc = 1;
  for (let i = 1; i < lower.length; i += 1) {
    const curr = lower.charCodeAt(i);
    const prev = lower.charCodeAt(i - 1);
    const isAlnum = /^[a-z0-9]$/.test(lower[i]);
    const diff = curr - prev;
    runAsc = diff === 1 && isAlnum ? runAsc + 1 : 1;
    runDesc = diff === -1 && isAlnum ? runDesc + 1 : 1;
    if (runAsc >= 5 || runDesc >= 5) {
      return true;
    }
  }
  return false;
}

function hasRepeatedPattern(password: string): boolean {
  if (!password) return false;
  if (/(.)\1{3,}/.test(password)) return true;
  if (password.length >= 8 && /^(.{1,4})\1+$/.test(password)) return true;
  return false;
}

export function evaluatePasswordStrength(
  password: string,
  options?: { name?: string; email?: string }
): PasswordStrengthEvaluation {
  const pwd = password || "";
  const lower = pwd.toLowerCase();

  const minLengthOk = pwd.length >= MIN_PASSWORD_LENGTH;
  const maxLengthOk = pwd.length <= MAX_PASSWORD_LENGTH;

  const userTokens = extractUserTokens(options?.name, options?.email);
  const containsPersonalInfo = userTokens.some((tok) => lower.includes(tok));
  const repeated = hasRepeatedPattern(pwd);
  const sequence = hasPredictableSequence(pwd);

  const userInputs = ["nexarion", ...userTokens];
  const analysis = pwd ? zxcvbn(pwd.slice(0, MAX_PASSWORD_LENGTH), userInputs) : null;

  const rawScore = analysis ? (analysis.score as 0 | 1 | 2 | 3 | 4) : 0;
  const crackTimeDisplay = analysis
    ? String(analysis.crack_times_display?.offline_slow_hashing_1e4_per_second || "")
    : "instant";
  const rawWarning = String(analysis?.feedback?.warning || "").trim();
  const rawSuggestions = (analysis?.feedback?.suggestions || []).filter(Boolean);

  const strippedAlpha = lower.replace(/[^a-z]/g, "");
  const isCommon =
    COMMON_CORES.has(strippedAlpha) ||
    (rawScore <= 1 && rawWarning.toLowerCase().includes("common")) ||
    Boolean(
      analysis?.sequence?.some(
        (m: { pattern?: string; rank?: number; token?: string }) =>
          m.pattern === "dictionary" &&
          (m.rank ?? 999999) <= 2000 &&
          String(m.token || "").length >= Math.max(5, Math.floor(pwd.length * 0.65))
      )
    );

  let effectiveScore: number = rawScore;
  if (!minLengthOk) {
    effectiveScore = Math.min(effectiveScore, pwd.length >= 8 ? 1 : 0);
  }
  if (containsPersonalInfo || repeated || sequence || isCommon) {
    effectiveScore = Math.min(effectiveScore, minLengthOk && rawScore >= 3 ? 2 : 1);
  }
  if (!pwd || !maxLengthOk) {
    effectiveScore = 0;
  }

  const clampedScore = Math.max(0, Math.min(4, effectiveScore)) as 0 | 1 | 2 | 3 | 4;

  const suggestions: string[] = [];
  if (!minLengthOk) {
    suggestions.push(`Use at least ${MIN_PASSWORD_LENGTH} characters.`);
  }
  if (!maxLengthOk) {
    suggestions.push(`Use at most ${MAX_PASSWORD_LENGTH} characters.`);
  }
  if (containsPersonalInfo) {
    suggestions.push("Avoid including your name or email address inside your password.");
  }
  if (repeated) {
    suggestions.push("Avoid repeated characters or repeating short patterns (e.g. aaaa).");
  }
  if (sequence) {
    suggestions.push(
      "Avoid predictable sequences such as 123456, abcdef, or keyboard patterns like qwerty."
    );
  }
  if (isCommon) {
    suggestions.push("Avoid commonly used or compromised passwords.");
  }
  for (const s of rawSuggestions) {
    if (!suggestions.includes(s)) {
      suggestions.push(s);
    }
  }

  const acceptable =
    minLengthOk &&
    maxLengthOk &&
    !containsPersonalInfo &&
    !repeated &&
    !sequence &&
    !isCommon &&
    clampedScore >= 3;

  if (!acceptable && suggestions.length === 0) {
    suggestions.push(
      "Your password is too weak. Try using a longer password with a combination of unpredictable words."
    );
  }

  let warning = rawWarning;
  if (!acceptable) {
    if (!minLengthOk) {
      warning = `Password must be at least ${MIN_PASSWORD_LENGTH} characters long.`;
    } else if (!maxLengthOk) {
      warning = `Password must not exceed ${MAX_PASSWORD_LENGTH} characters.`;
    } else if (containsPersonalInfo) {
      warning = "Password cannot include parts of your name or email.";
    } else if (isCommon) {
      warning = "This password is too common and easily guessed.";
    } else if (sequence) {
      warning = "Predictable character or keyboard sequences weaken this password.";
    } else if (repeated) {
      warning = "Repeated characters or patterns make this password easy to guess.";
    } else if (!warning) {
      warning =
        "Your password is too weak. Try using a longer password with a combination of unpredictable words.";
    }
  }

  return {
    score: clampedScore,
    label: STRENGTH_LABELS[clampedScore],
    acceptable,
    warning,
    suggestions,
    crackTimeDisplay: crackTimeDisplay || "instant",
    checks: {
      minLength: minLengthOk,
      maxLength: maxLengthOk,
      notCommon: !isCommon,
      noPredictableSequence: !sequence,
      noRepeatedPattern: !repeated,
      noPersonalInfo: !containsPersonalInfo,
      sufficientEntropy: clampedScore >= 3,
    },
  };
}
