import assert from "node:assert/strict";
import test from "node:test";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import {
  CURATED_SUBTITLES,
  GREETING_LIBRARY,
  extractDisplayName,
  getPersonalizedGreeting,
  getTimeBucket,
  resetGreetingHistory,
} from "./greetings.ts";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

test("extractDisplayName handles normal name and capitalizes cleanly", () => {
  assert.strictEqual(extractDisplayName({ name: "Kaushal", email: "k@example.com" }), "Kaushal");
  assert.strictEqual(
    extractDisplayName({ name: "Kaushal Kishore", email: "k@example.com" }),
    "Kaushal"
  );
  assert.strictEqual(extractDisplayName({ name: "alex", email: "a@example.com" }), "Alex");
});

test("extractDisplayName rejects missing or email-based names", () => {
  assert.strictEqual(extractDisplayName(null), undefined);
  assert.strictEqual(extractDisplayName(undefined), undefined);
  assert.strictEqual(extractDisplayName({ name: "", email: "k@example.com" }), undefined);
  assert.strictEqual(extractDisplayName({ name: "   ", email: "k@example.com" }), undefined);
  assert.strictEqual(
    extractDisplayName({ name: "kushal@example.com", email: "kushal@example.com" }),
    undefined
  );
});

test("GREETING_LIBRARY covers all 8 required categories without hardcoded names", () => {
  const categories = new Set(GREETING_LIBRARY.map((g) => g.category));
  for (const required of [
    "friendly",
    "coding",
    "review",
    "creative",
    "minimal",
    "professional",
    "welcome_back",
    "time",
  ]) {
    assert.ok(categories.has(required), `Missing category: ${required}`);
  }
  assert.ok(GREETING_LIBRARY.length >= 65, "Library must contain rich set of greetings");
  for (const entry of GREETING_LIBRARY) {
    assert.ok(!entry.text.includes("Mystry"), `Must not hardcode Mystry in ${entry.id}`);
    assert.ok(
      !entry.personalizedText || !entry.personalizedText.includes("Mystry"),
      `Must not hardcode Mystry in personalizedText for ${entry.id}`
    );
  }
});

test("getPersonalizedGreeting varies greetings dynamically and prevents back-to-back or excessive repetition", () => {
  resetGreetingHistory();
  const user = { name: "Kaushal", email: "k@example.com" };

  const seenHeadings = new Set();
  const seenIds = [];
  let prevHeading = "";

  for (let i = 0; i < 20; i += 1) {
    const res = getPersonalizedGreeting(user, new Date("2026-11-26T14:00:00"));
    assert.ok(res.heading.length > 0, "heading must not be empty");
    assert.ok(CURATED_SUBTITLES.includes(res.subtitle), "subtitle must come from curated list");
    assert.ok(!res.heading.includes("k@example.com"), "email must never appear in heading");
    assert.notEqual(res.heading, prevHeading, "Must never repeat immediately previous greeting");
    prevHeading = res.heading;
    seenHeadings.add(res.heading);
    seenIds.push(res.id);
  }

  assert.ok(seenHeadings.size >= 14, `Expected broad variety across 20 runs, got ${seenHeadings.size}`);
  // Recent window of 16 prevents duplicate template IDs within consecutive draws
  const first16 = new Set(seenIds.slice(0, 16));
  assert.equal(first16.size, 16, "First 16 greetings must be completely unique");
});

test("getPersonalizedGreeting personalizes occasionally when name is available and stays neutral when missing", () => {
  resetGreetingHistory();
  const user = { name: "Neha Verma", email: "neha@example.com" };

  let withName = 0;
  let withoutName = 0;
  for (let i = 0; i < 40; i += 1) {
    const res = getPersonalizedGreeting(user, new Date("2026-11-26T11:00:00"));
    if (res.heading.includes("Neha")) {
      withName += 1;
    } else {
      withoutName += 1;
    }
  }
  assert.ok(withName > 0, "Should occasionally personalize with display name");
  assert.ok(withoutName > 0, "Should NOT include user name in every greeting");

  resetGreetingHistory();
  for (let i = 0; i < 15; i += 1) {
    const neutral = getPersonalizedGreeting(null, new Date("2026-11-26T11:00:00"));
    assert.ok(!neutral.heading.includes("{name}"));
    assert.ok(!neutral.heading.includes("undefined"));
    assert.ok(!neutral.heading.includes("null"));
  }
});

test("Time-aware greetings respect user local time buckets cleanly", () => {
  assert.equal(getTimeBucket(new Date(2026, 10, 26, 8, 30)), "morning");
  assert.equal(getTimeBucket(new Date(2026, 10, 26, 14, 15)), "afternoon");
  assert.equal(getTimeBucket(new Date(2026, 10, 26, 19, 45)), "evening");
  assert.equal(getTimeBucket(new Date(2026, 10, 26, 1, 20)), "late_night");
  assert.equal(getTimeBucket(new Date(2026, 10, 26, 23, 0)), "late_night");

  const bucketExpectations = [
    {
      date: new Date(2026, 10, 26, 9, 0),
      expected: [
        "Good morning! What are we building today?",
        "A fresh day, a fresh start.",
        "Morning! Ready to code?",
      ],
    },
    {
      date: new Date(2026, 10, 26, 15, 0),
      expected: [
        "Good afternoon! What's on the agenda?",
        "How's the progress going?",
        "Ready for another challenge?",
      ],
    },
    {
      date: new Date(2026, 10, 26, 20, 0),
      expected: [
        "Good evening! What are we working on?",
        "Let's make some progress tonight.",
        "What's the next task?",
      ],
    },
    {
      date: new Date(2026, 10, 26, 1, 0),
      expected: [
        "Burning the midnight oil?",
        "Still building? Let's get to work.",
        "Late-night coding session?",
        "What's keeping those ideas running?",
      ],
    },
  ];

  for (const { date, expected } of bucketExpectations) {
    resetGreetingHistory();
    const res = getPersonalizedGreeting(null, date, { timeAwareChance: 1.0 });
    assert.equal(res.category, "time");
    assert.ok(expected.includes(res.heading), `Unexpected time heading: ${res.heading}`);
  }
});

test("AIConversationWorkspace wires greetingSeed and smooth transition animations without altering active chats", () => {
  const wsSource = fs.readFileSync(path.join(__dirname, "AIConversationWorkspace.tsx"), "utf-8");
  const appSource = fs.readFileSync(path.join(__dirname, "..", "..", "App.tsx"), "utf-8");

  assert.ok(wsSource.includes("greetingSeed"), "Workspace must accept greetingSeed prop");
  assert.ok(wsSource.includes("greetingAnimKey"), "Workspace must animate greeting transitions cleanly");
  assert.ok(wsSource.includes("messages.length === 0 && !isSending"), "Greeting must only render on empty new-chat screen");
  assert.ok(appSource.includes("greetingSeed={greetingSeed}"), "App.tsx must wire greetingSeed into workspace");
});
