import assert from "node:assert";
import test from "node:test";

import { extractDisplayName, getPersonalizedGreeting } from "./greetings.ts";

test("extractDisplayName handles normal name", () => {
  assert.strictEqual(extractDisplayName({ name: "Kaushal", email: "k@example.com" }), "Kaushal");
  assert.strictEqual(extractDisplayName({ name: "Kaushal Kishore", email: "k@example.com" }), "Kaushal");
  assert.strictEqual(extractDisplayName({ name: "mystry", email: "m@example.com" }), "Mystry");
});

test("extractDisplayName rejects missing or email-based names", () => {
  assert.strictEqual(extractDisplayName(null), undefined);
  assert.strictEqual(extractDisplayName(undefined), undefined);
  assert.strictEqual(extractDisplayName({ name: "", email: "k@example.com" }), undefined);
  assert.strictEqual(extractDisplayName({ name: "   ", email: "k@example.com" }), undefined);
  assert.strictEqual(extractDisplayName({ name: "kushal@example.com", email: "kushal@example.com" }), undefined);
});

test("getPersonalizedGreeting provides consistent, purposeful review heading", () => {
  const user = { name: "Kaushal", email: "k@example.com" };
  const res = getPersonalizedGreeting(user);

  assert.ok(res.heading, "heading must be present");
  assert.ok(res.subtitle, "subtitle must be present");
  assert.ok(!res.heading.includes("k@example.com"), "email must never be in heading");
  assert.ok(res.heading.includes("What would you like to review"), "heading must be focused review prompt");
  assert.ok(res.heading.includes("Kaushal"), "heading should address user by first name");
  assert.equal(res.subtitle, "Inspect code changes, investigate vulnerabilities, or review a pull request.");
});

test("getPersonalizedGreeting uses fallback when no user display name is provided", () => {
  const res1 = getPersonalizedGreeting(null);
  assert.equal(res1.heading, "What would you like to review?");
  assert.ok(!res1.heading.includes("undefined"));
  assert.ok(!res1.heading.includes("null"));

  const res2 = getPersonalizedGreeting({ name: "", email: "user@test.com" });
  assert.equal(res2.heading, "What would you like to review?");
  assert.ok(!res2.heading.includes("user@test.com"));
});
