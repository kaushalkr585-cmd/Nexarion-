import test from "node:test";
import assert from "node:assert/strict";
import { readSSEStream } from "./api.ts";

function makeChunkedResponse(chunks) {
  const encoder = new TextEncoder();
  const stream = new ReadableStream({
    async start(controller) {
      for (const piece of chunks) {
        if (piece.delayMs) {
          await new Promise((resolve) => setTimeout(resolve, piece.delayMs));
        }
        controller.enqueue(encoder.encode(piece.text));
      }
      controller.close();
    },
  });
  return new Response(stream, {
    status: 200,
    headers: { "Content-Type": "text/event-stream" },
  });
}

test("readSSEStream handles keep-alive heartbeats, CRLF framing, tokens, and done", async () => {
  const tokens = [];
  let donePayload = null;
  const errors = [];

  const resp = makeChunkedResponse([
    { text: "event: ack\r\ndata: {\"conversation_id\":\"c1\",\"mode\":\"normal\"}\r\n\r\n" },
    { text: ": keep-alive\n\n" },
    { text: "event: token\ndata: {\"chunk\":\"Hello\"}\n\n" },
    { text: "event: token\ndata: {\"chunk\":\" world\"}\n\n" },
    {
      text: "event: done\ndata: {\"conversation_id\":\"c1\",\"message_id\":\"m1\",\"content\":\"Hello world\",\"created_at\":\"2026-01-01T00:00:00Z\"}\n\n",
    },
  ]);

  await readSSEStream(resp, {
    onToken: (t) => tokens.push(t),
    onDone: (d) => {
      donePayload = d;
    },
    onError: (e) => errors.push(e),
    idleTimeoutMs: 2000,
  });

  assert.equal(tokens.join(""), "Hello world");
  assert.equal(donePayload?.message_id, "m1");
  assert.equal(errors.length, 0);
});

test("readSSEStream reports STREAM_INTERRUPTED when stream ends without done or error", async () => {
  const tokens = [];
  const errors = [];

  const resp = makeChunkedResponse([
    { text: "event: ack\ndata: {\"conversation_id\":\"c2\",\"mode\":\"normal\"}\n\n" },
    { text: "event: token\ndata: {\"chunk\":\"Partial\"}\n\n" },
  ]);

  await readSSEStream(resp, {
    onToken: (t) => tokens.push(t),
    onError: (e) => errors.push(e),
    idleTimeoutMs: 2000,
  });

  assert.equal(tokens.join(""), "Partial");
  assert.equal(errors.length, 1);
  assert.equal(errors[0].error_code, "STREAM_INTERRUPTED");
  assert.equal(errors[0].retryable, true);
});

test("readSSEStream fires TIMEOUT error when server stalls beyond idleTimeoutMs", async () => {
  const encoder = new TextEncoder();
  let streamController = null;
  const stream = new ReadableStream({
    start(controller) {
      streamController = controller;
      controller.enqueue(
        encoder.encode("event: status\ndata: {\"stage\":\"thinking\",\"detail\":\"Thinking...\"}\n\n")
      );
    },
    cancel() {
      streamController = null;
    },
  });
  const resp = new Response(stream, { status: 200 });
  const errors = [];

  await readSSEStream(resp, {
    onError: (e) => errors.push(e),
    idleTimeoutMs: 80,
  });

  assert.equal(errors.length, 1);
  assert.equal(errors[0].error_code, "TIMEOUT");
  assert.equal(errors[0].retryable, true);
});

test("readSSEStream returns silently when user aborts stream", async () => {
  const encoder = new TextEncoder();
  const ac = new AbortController();
  const stream = new ReadableStream({
    start(controller) {
      controller.enqueue(
        encoder.encode("event: token\ndata: {\"chunk\":\"Hi\"}\n\n")
      );
      ac.signal.addEventListener("abort", () => {
        try {
          controller.error(new DOMException("The operation was aborted.", "AbortError"));
        } catch {
          // ignore
        }
      });
    },
  });
  const resp = new Response(stream, { status: 200 });
  const errors = [];

  setTimeout(() => ac.abort(), 25);
  await readSSEStream(resp, {
    signal: ac.signal,
    onError: (e) => errors.push(e),
    idleTimeoutMs: 2000,
  });

  assert.equal(errors.length, 0);
});
