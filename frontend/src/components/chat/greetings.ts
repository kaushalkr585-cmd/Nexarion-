import type { User } from "../../types";

export interface GreetingData {
  heading: string;
  subtitle: string;
  category: "time" | "coding" | "review" | "general" | "fallback";
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

export type GreetingGenerator = (name?: string) => string;

export const TIME_AWARE_MORNING: GreetingGenerator[] = [
  (name) => (name ? `Good morning, ${name}.` : "Good morning."),
  (name) => (name ? `Ready for another productive morning, ${name}?` : "Ready for another productive morning?"),
  (name) => (name ? `Ready to build something great, ${name}?` : "Ready to build something great?"),
  (name) => (name ? `What are we exploring this morning, ${name}?` : "What are we exploring this morning?"),
];

export const TIME_AWARE_AFTERNOON: GreetingGenerator[] = [
  (name) => (name ? `Good afternoon, ${name}.` : "Good afternoon."),
  (name) => (name ? `Ready for another productive session, ${name}?` : "Ready for another productive session?"),
  (name) => (name ? `What are we solving today, ${name}?` : "What are we solving today?"),
  (name) => (name ? `Ready to build something great, ${name}?` : "Ready to build something great?"),
];

export const TIME_AWARE_EVENING: GreetingGenerator[] = [
  (name) => (name ? `Good evening, ${name}.` : "Good evening."),
  (name) => (name ? `Ready when you are, ${name}.` : "Ready when you are."),
  (name) => (name ? `Let's untangle some code, ${name}.` : "Let's untangle some code."),
  (name) => (name ? `Ready for another productive session, ${name}?` : "Ready for another productive session?"),
];

export const CODING_DEBUGGING: GreetingGenerator[] = [
  (name) => (name ? `Let's track down that bug, ${name}.` : "Let's track down that bug."),
  (name) => (name ? `What are we building today, ${name}?` : "What are we building today?"),
  (name) => (name ? `Let's make this code cleaner, ${name}.` : "Let's make this code cleaner."),
  (name) => (name ? `Need another pair of eyes on your code, ${name}?` : "Need another pair of eyes on your code?"),
  () => "Have a tricky bug? Let's work through it.",
  (name) => (name ? `Let's untangle some code, ${name}.` : "Let's untangle some code."),
];

export const CODE_REVIEW: GreetingGenerator[] = [
  (name) => (name ? `Ready to inspect a pull request, ${name}?` : "Ready to inspect a pull request?"),
  (name) => (name ? `Let's catch the bugs before they ship, ${name}.` : "Let's catch the bugs before they ship."),
  (name) => (name ? `What should the agents investigate, ${name}?` : "What should the agents investigate?"),
  () => "Let's make your next code review count.",
  (name) => (name ? `Let's make this change safer, ${name}.` : "Let's make this change safer."),
];

export const GENERAL_ASSISTANCE: GreetingGenerator[] = [
  (name) => (name ? `What are we solving today, ${name}?` : "What are we solving today?"),
  (name) => (name ? `What are we exploring today, ${name}?` : "What are we exploring today?"),
  (name) => (name ? `What are we figuring out today, ${name}?` : "What are we figuring out today?"),
  (name) => (name ? `Let's work through it together, ${name}.` : "Let's work through it together."),
  () => "Have a question? Start anywhere.",
  (name) => (name ? `Your next breakthrough starts here, ${name}.` : "Your next breakthrough starts here."),
  (name) => (name ? `Ready when you are, ${name}.` : "Ready when you are."),
  () => "Let's turn that problem into a solution.",
];

export const NATURAL_FALLBACKS: string[] = [
  "What are we working on today?",
  "What are we solving today?",
  "Have a tricky bug? Let's work through it.",
  "Let's make your next code review count.",
  "Ready to inspect a pull request?",
  "Let's turn that problem into a solution.",
  "What would you like to explore?",
  "Have a question? Start anywhere.",
  "Ready for another productive session?",
];

export const CURATED_SUBTITLES: string[] = [
  "Ask a question, share a diff, or bring a tricky bug.",
  "Your code, your questions, your next breakthrough.",
  "Debug, review, optimize, and build with NEXARION.",
  "From a small bug to a complex architecture, start anywhere.",
  "Connect a pull request or explore an idea with your AI agents.",
  "Inspect changes, catch security vulnerabilities, and streamline reviews.",
];

export const SESSION_STORAGE_KEY = "nexarion_last_greeting_heading";

export function getPersonalizedGreeting(
  user: User | null | undefined,
  _currentDate: Date = new Date()
): GreetingData {
  const name = extractDisplayName(user);
  return {
    heading: name ? `What would you like to review, ${name}?` : "What would you like to review?",
    subtitle: "Inspect code changes, investigate vulnerabilities, or review a pull request.",
    category: "review",
  };
}
