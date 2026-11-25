import type { User } from "../../types";

export type GreetingCategory =
  | "friendly"
  | "coding"
  | "review"
  | "creative"
  | "minimal"
  | "professional"
  | "welcome_back"
  | "time";

export type TimeBucket = "morning" | "afternoon" | "evening" | "late_night";

export interface GreetingEntry {
  id: string;
  category: GreetingCategory;
  text: string;
  personalizedText?: string;
  timeBucket?: TimeBucket;
}

export interface GreetingData {
  id: string;
  heading: string;
  subtitle: string;
  category: GreetingCategory;
}

export interface GreetingSelectionOptions {
  random?: () => number;
  timeAwareChance?: number;
  personalizeChance?: number;
  recentLimit?: number;
}

export const GREETING_LIBRARY: GreetingEntry[] = [
  // A. Friendly & Casual
  {
    id: "friendly-working-on",
    category: "friendly",
    text: "What are we working on today?",
    personalizedText: "What are we working on today, {name}?",
  },
  {
    id: "friendly-build-amazing",
    category: "friendly",
    text: "Ready to build something amazing?",
    personalizedText: "Ready to build something amazing, {name}?",
  },
  {
    id: "friendly-on-your-mind",
    category: "friendly",
    text: "What's on your mind?",
    personalizedText: "What's on your mind, {name}?",
  },
  {
    id: "friendly-explore-today",
    category: "friendly",
    text: "What shall we explore today?",
  },
  {
    id: "friendly-help-you-with",
    category: "friendly",
    text: "Hey! What can I help you with?",
    personalizedText: "Hey {name}! What can I help you with?",
  },
  {
    id: "friendly-make-something-great",
    category: "friendly",
    text: "Let's make something great today.",
  },
  {
    id: "friendly-interesting-work",
    category: "friendly",
    text: "Got something interesting to work on?",
  },
  {
    id: "friendly-plan-for-today",
    category: "friendly",
    text: "What's the plan for today?",
  },
  {
    id: "friendly-welcome-whats-next",
    category: "friendly",
    text: "Welcome back! What's next?",
    personalizedText: "Welcome back, {name}! What's next?",
  },
  {
    id: "friendly-lets-get-started",
    category: "friendly",
    text: "Let's get started.",
  },

  // B. Coding & Development
  {
    id: "coding-building-today",
    category: "coding",
    text: "What are we building today?",
    personalizedText: "What are we building today, {name}?",
  },
  {
    id: "coding-code-to-explore",
    category: "coding",
    text: "Got some code to explore?",
  },
  {
    id: "coding-solve-challenging",
    category: "coding",
    text: "Ready to solve something challenging?",
    personalizedText: "Ready to solve something challenging, {name}?",
  },
  {
    id: "coding-debugging-today",
    category: "coding",
    text: "What are we debugging today?",
  },
  {
    id: "coding-ideas-into-code",
    category: "coding",
    text: "Let's turn ideas into code.",
  },
  {
    id: "coding-challenge-for-me",
    category: "coding",
    text: "Have a coding challenge for me?",
  },
  {
    id: "coding-whats-cooking",
    category: "coding",
    text: "What's cooking in your codebase?",
  },
  {
    id: "coding-make-progress",
    category: "coding",
    text: "Ready to make some progress?",
    personalizedText: "Ready to make some progress, {name}?",
  },
  {
    id: "coding-build-remarkable",
    category: "coding",
    text: "Let's build something remarkable.",
  },
  {
    id: "coding-problem-solving",
    category: "coding",
    text: "What problem are we solving today?",
    personalizedText: "What problem are we solving today, {name}?",
  },

  // C. Code Review & Security
  {
    id: "review-like-me-to-review",
    category: "review",
    text: "What would you like me to review?",
    personalizedText: "What would you like me to review, {name}?",
  },
  {
    id: "review-pr-ready",
    category: "review",
    text: "Got a pull request ready?",
  },
  {
    id: "review-make-code-better",
    category: "review",
    text: "Let's make your code better.",
  },
  {
    id: "review-hunt-down-bugs",
    category: "review",
    text: "Ready to hunt down some bugs?",
  },
  {
    id: "review-closer-look",
    category: "review",
    text: "What needs a closer look?",
  },
  {
    id: "review-inspect-your-code",
    category: "review",
    text: "Let's inspect your code.",
  },
  {
    id: "review-diff-to-analyze",
    category: "review",
    text: "Have a diff you'd like me to analyze?",
  },
  {
    id: "review-codebase-stronger",
    category: "review",
    text: "Let's make your codebase stronger.",
  },
  {
    id: "review-thorough-review",
    category: "review",
    text: "Ready for a thorough code review?",
    personalizedText: "Ready for a thorough code review, {name}?",
  },
  {
    id: "review-find-what-others-miss",
    category: "review",
    text: "Let's find what others might miss.",
  },

  // D. Creative & Inspirational
  {
    id: "creative-great-project-starts",
    category: "creative",
    text: "Every great project starts somewhere. What's yours?",
  },
  {
    id: "creative-bring-idea-to-life",
    category: "creative",
    text: "Have an idea? Let's bring it to life.",
  },
  {
    id: "creative-make-extraordinary",
    category: "creative",
    text: "Let's make something extraordinary.",
  },
  {
    id: "creative-big-ideas-execution",
    category: "creative",
    text: "Big ideas deserve great execution.",
  },
  {
    id: "creative-creating-today",
    category: "creative",
    text: "What are we creating today?",
    personalizedText: "What are we creating today, {name}?",
  },
  {
    id: "creative-next-breakthrough",
    category: "creative",
    text: "Your next breakthrough starts here.",
  },
  {
    id: "creative-complexity-to-clarity",
    category: "creative",
    text: "Let's turn complexity into clarity.",
  },
  {
    id: "creative-next-big-thing",
    category: "creative",
    text: "What's the next big thing you're building?",
  },

  // E. Short & Minimal
  {
    id: "minimal-lets-begin",
    category: "minimal",
    text: "Let's begin.",
  },
  {
    id: "minimal-whats-next",
    category: "minimal",
    text: "What's next?",
  },
  {
    id: "minimal-ready-when-you-are",
    category: "minimal",
    text: "Ready when you are.",
    personalizedText: "Ready when you are, {name}.",
  },
  {
    id: "minimal-lets-dive-in",
    category: "minimal",
    text: "Let's dive in.",
  },
  {
    id: "minimal-start-exploring",
    category: "minimal",
    text: "Start exploring.",
  },
  {
    id: "minimal-workspace-ready",
    category: "minimal",
    text: "Your workspace is ready.",
  },
  {
    id: "minimal-get-to-work",
    category: "minimal",
    text: "Let's get to work.",
  },
  {
    id: "minimal-whats-the-challenge",
    category: "minimal",
    text: "What's the challenge?",
  },

  // F. Intelligent & Professional
  {
    id: "professional-investigate-today",
    category: "professional",
    text: "What would you like to investigate today?",
    personalizedText: "What would you like to investigate today, {name}?",
  },
  {
    id: "professional-tackle-first",
    category: "professional",
    text: "Which problem should we tackle first?",
  },
  {
    id: "professional-bottom-of-it",
    category: "professional",
    text: "Let's get to the bottom of it.",
  },
  {
    id: "professional-deserves-attention",
    category: "professional",
    text: "What deserves our attention today?",
  },
  {
    id: "professional-assist-workflow",
    category: "professional",
    text: "How can I assist with your development workflow?",
  },
  {
    id: "professional-like-to-analyze",
    category: "professional",
    text: "What would you like to analyze?",
  },
  {
    id: "professional-focus-on-matters",
    category: "professional",
    text: "Let's focus on what matters.",
  },

  // G. Welcome Back
  {
    id: "welcome-working-on",
    category: "welcome_back",
    text: "Welcome back! What are we working on?",
    personalizedText: "Welcome back, {name}! What are we working on?",
  },
  {
    id: "welcome-good-to-see-you",
    category: "welcome_back",
    text: "Good to see you again.",
    personalizedText: "Good to see you again, {name}.",
  },
  {
    id: "welcome-another-round",
    category: "welcome_back",
    text: "Back for another round?",
    personalizedText: "Back for another round, {name}?",
  },
  {
    id: "welcome-pick-up",
    category: "welcome_back",
    text: "Ready to pick up where you left off?",
    personalizedText: "Ready to pick up where you left off, {name}?",
  },
  {
    id: "welcome-tackling-next",
    category: "welcome_back",
    text: "What are we tackling next?",
  },
  {
    id: "welcome-continue-building",
    category: "welcome_back",
    text: "Let's continue building.",
  },
  {
    id: "welcome-another-day",
    category: "welcome_back",
    text: "Another day, another challenge.",
    personalizedText: "Ready for another challenge, {name}?",
  },

  // H. Time-Aware Greetings
  {
    id: "time-morning-building",
    category: "time",
    timeBucket: "morning",
    text: "Good morning! What are we building today?",
    personalizedText: "Good morning, {name}! What are we building today?",
  },
  {
    id: "time-morning-fresh-day",
    category: "time",
    timeBucket: "morning",
    text: "A fresh day, a fresh start.",
  },
  {
    id: "time-morning-ready-to-code",
    category: "time",
    timeBucket: "morning",
    text: "Morning! Ready to code?",
    personalizedText: "Morning, {name}! Ready to code?",
  },
  {
    id: "time-afternoon-agenda",
    category: "time",
    timeBucket: "afternoon",
    text: "Good afternoon! What's on the agenda?",
    personalizedText: "Good afternoon, {name}! What's on the agenda?",
  },
  {
    id: "time-afternoon-progress",
    category: "time",
    timeBucket: "afternoon",
    text: "How's the progress going?",
  },
  {
    id: "time-afternoon-challenge",
    category: "time",
    timeBucket: "afternoon",
    text: "Ready for another challenge?",
    personalizedText: "Ready for another challenge, {name}?",
  },
  {
    id: "time-evening-working-on",
    category: "time",
    timeBucket: "evening",
    text: "Good evening! What are we working on?",
    personalizedText: "Good evening, {name}! What are we working on?",
  },
  {
    id: "time-evening-progress-tonight",
    category: "time",
    timeBucket: "evening",
    text: "Let's make some progress tonight.",
  },
  {
    id: "time-evening-next-task",
    category: "time",
    timeBucket: "evening",
    text: "What's the next task?",
  },
  {
    id: "time-night-midnight-oil",
    category: "time",
    timeBucket: "late_night",
    text: "Burning the midnight oil?",
    personalizedText: "Burning the midnight oil, {name}?",
  },
  {
    id: "time-night-still-building",
    category: "time",
    timeBucket: "late_night",
    text: "Still building? Let's get to work.",
  },
  {
    id: "time-night-coding-session",
    category: "time",
    timeBucket: "late_night",
    text: "Late-night coding session?",
  },
  {
    id: "time-night-ideas-running",
    category: "time",
    timeBucket: "late_night",
    text: "What's keeping those ideas running?",
  },
];

export const CURATED_SUBTITLES: string[] = [
  "Inspect code changes, investigate vulnerabilities, or review a pull request.",
  "Ask a question, share a diff, or track down a tricky bug.",
  "Your code, your architecture, your next breakthrough.",
  "Debug, review, optimize, and build with NEXARION.",
  "From a quick question to a full repository audit, start anywhere.",
  "Connect a GitHub repository or attach files for deeper multi-agent analysis.",
];

export const SESSION_STORAGE_KEY = "nexarion_last_greeting_heading";
const RECENT_GREETINGS_KEY = "nexarion_recent_greetings";
const LAST_SUBTITLE_KEY = "nexarion_last_greeting_subtitle";

const memoryStore: {
  lastHeading: string | null;
  lastSubtitle: string | null;
  recentIds: string[];
} = {
  lastHeading: null,
  lastSubtitle: null,
  recentIds: [],
};

function readSessionValue(key: string): string | null {
  try {
    if (typeof window !== "undefined" && window.sessionStorage) {
      return window.sessionStorage.getItem(key);
    }
  } catch {
    // Ignore storage access restrictions
  }
  return null;
}

function writeSessionValue(key: string, value: string): void {
  try {
    if (typeof window !== "undefined" && window.sessionStorage) {
      window.sessionStorage.setItem(key, value);
    }
  } catch {
    // Ignore storage access restrictions
  }
}

function getRecentGreetingIds(): string[] {
  const raw = readSessionValue(RECENT_GREETINGS_KEY);
  if (raw) {
    try {
      const parsed = JSON.parse(raw);
      if (Array.isArray(parsed)) {
        return parsed.filter((x): x is string => typeof x === "string");
      }
    } catch {
      // Ignore malformed cache
    }
  }
  return memoryStore.recentIds;
}

function recordGreetingSelection(id: string, heading: string, subtitle: string, limit: number): void {
  memoryStore.lastHeading = heading;
  memoryStore.lastSubtitle = subtitle;
  const nextRecent = [id, ...getRecentGreetingIds().filter((item) => item !== id)].slice(0, limit);
  memoryStore.recentIds = nextRecent;

  writeSessionValue(SESSION_STORAGE_KEY, heading);
  writeSessionValue(LAST_SUBTITLE_KEY, subtitle);
  writeSessionValue(RECENT_GREETINGS_KEY, JSON.stringify(nextRecent));
}

export function resetGreetingHistory(): void {
  memoryStore.lastHeading = null;
  memoryStore.lastSubtitle = null;
  memoryStore.recentIds = [];
  try {
    if (typeof window !== "undefined" && window.sessionStorage) {
      window.sessionStorage.removeItem(SESSION_STORAGE_KEY);
      window.sessionStorage.removeItem(RECENT_GREETINGS_KEY);
      window.sessionStorage.removeItem(LAST_SUBTITLE_KEY);
    }
  } catch {
    // Ignore storage access restrictions
  }
}

export function extractDisplayName(user: User | null | undefined): string | undefined {
  if (!user || !user.name) return undefined;
  const raw = user.name.trim();
  if (!raw || raw.includes("@")) return undefined;

  const parts = raw.split(/\s+/);
  const firstName = parts[0];
  if (!firstName || firstName.length > 30) return undefined;

  return firstName.charAt(0).toUpperCase() + firstName.slice(1);
}

export function getTimeBucket(date: Date = new Date()): TimeBucket {
  const hour = date.getHours();
  if (hour >= 5 && hour < 12) return "morning";
  if (hour >= 12 && hour < 17) return "afternoon";
  if (hour >= 17 && hour < 22) return "evening";
  return "late_night";
}

function formatEntryHeading(
  entry: GreetingEntry,
  displayName: string | undefined,
  personalizeChance: number,
  rand: () => number
): string {
  if (displayName && entry.personalizedText && rand() < personalizeChance) {
    return entry.personalizedText.replace("{name}", displayName);
  }
  return entry.text;
}

function pickRandomIndex(length: number, rand: () => number): number {
  if (length <= 1) return 0;
  const raw = rand();
  const clamped = Number.isFinite(raw) ? Math.min(Math.max(raw, 0), 0.9999999) : 0;
  return Math.floor(clamped * length);
}

export function getPersonalizedGreeting(
  user: User | null | undefined,
  currentDate: Date = new Date(),
  options: GreetingSelectionOptions = {}
): GreetingData {
  const rand = options.random ?? Math.random;
  const timeAwareChance = options.timeAwareChance ?? 0.22;
  const personalizeChance = options.personalizeChance ?? 0.35;
  const recentLimit = options.recentLimit ?? 16;

  const displayName = extractDisplayName(user);
  const lastHeading = readSessionValue(SESSION_STORAGE_KEY) ?? memoryStore.lastHeading;
  const recentIds = getRecentGreetingIds();
  const lastRecentId = recentIds[0] ?? null;

  const timeBucket = getTimeBucket(currentDate);
  const timePool = GREETING_LIBRARY.filter(
    (entry) => entry.category === "time" && entry.timeBucket === timeBucket
  );
  const generalPool = GREETING_LIBRARY.filter((entry) => entry.category !== "time");

  const freshTime = timePool.filter((entry) => !recentIds.includes(entry.id));
  const freshGeneral = generalPool.filter((entry) => !recentIds.includes(entry.id));

  let candidatePool: GreetingEntry[];
  if (freshTime.length > 0 && (rand() < timeAwareChance || freshGeneral.length === 0)) {
    candidatePool = freshTime;
  } else if (freshGeneral.length > 0) {
    candidatePool = freshGeneral;
  } else {
    const combinedPool = [...generalPool, ...timePool];
    const notImmediate = combinedPool.filter((entry) => entry.id !== lastRecentId);
    candidatePool = notImmediate.length > 0 ? notImmediate : combinedPool;
  }

  let chosen = candidatePool[pickRandomIndex(candidatePool.length, rand)] ?? GREETING_LIBRARY[0];

  let heading = formatEntryHeading(chosen, displayName, personalizeChance, rand);
  if (lastHeading && heading === lastHeading) {
    const fallbackAlternatives = GREETING_LIBRARY.filter(
      (entry) =>
        entry.id !== chosen.id &&
        entry.id !== lastRecentId &&
        (entry.category !== "time" || entry.timeBucket === timeBucket)
    );
    const freshAlts = fallbackAlternatives.filter((entry) => !recentIds.includes(entry.id));
    const altPool = freshAlts.length > 0 ? freshAlts : fallbackAlternatives;
    if (altPool.length > 0) {
      chosen = altPool[pickRandomIndex(altPool.length, rand)];
      heading = formatEntryHeading(chosen, displayName, personalizeChance, rand);
    }
  }

  const lastSubtitle = readSessionValue(LAST_SUBTITLE_KEY) ?? memoryStore.lastSubtitle;
  const subtitlePool = CURATED_SUBTITLES.filter((sub) => sub !== lastSubtitle);
  const subtitle =
    subtitlePool.length > 0
      ? subtitlePool[pickRandomIndex(subtitlePool.length, rand)]
      : CURATED_SUBTITLES[0];

  recordGreetingSelection(chosen.id, heading, subtitle, recentLimit);

  return {
    id: chosen.id,
    heading,
    subtitle,
    category: chosen.category,
  };
}
