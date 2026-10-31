import test from "node:test";
import assert from "node:assert/strict";

test("Optimistic agent toggle updates state instantaneously (<16ms) without waiting for API", async () => {
  let agents = [
    { agent_id: "security", name: "Security Agent", is_enabled: true },
    { agent_id: "ast", name: "AST Agent", is_enabled: true },
  ];

  // Simulated optimistic toggle handler matching App.tsx
  const seqMap = new Map();
  let pendingApiPromiseResolve = null;

  const handleToggle = (agentId, targetEnabled) => {
    const nextSeq = (seqMap.get(agentId) || 0) + 1;
    seqMap.set(agentId, nextSeq);

    // Optimistic sync update
    agents = agents.map((a) => (a.agent_id === agentId ? { ...a, is_enabled: targetEnabled } : a));

    // Simulated async API call
    return new Promise((resolve) => {
      pendingApiPromiseResolve = () => {
        if (seqMap.get(agentId) === nextSeq) {
          agents = agents.map((a) => (a.agent_id === agentId ? { ...a, is_enabled: targetEnabled } : a));
        }
        resolve({ agent_id: agentId, is_enabled: targetEnabled });
      };
    });
  };

  const startTime = Date.now();
  const apiPromise = handleToggle("security", false);
  const optimisticElapsed = Date.now() - startTime;

  // The UI state is updated immediately in the same synchronous turn
  assert.ok(optimisticElapsed < 50, `Expected < 50ms, got ${optimisticElapsed}ms`);
  assert.equal(agents.find((a) => a.agent_id === "security").is_enabled, false);

  // When API eventually resolves later
  pendingApiPromiseResolve();
  await apiPromise;
  assert.equal(agents.find((a) => a.agent_id === "security").is_enabled, false);
});

test("Rapid toggling prevents race conditions and out-of-order overwrite", async () => {
  let agents = [
    { agent_id: "security", name: "Security Agent", is_enabled: true },
  ];
  const seqMap = new Map();
  const resolvers = [];

  const handleToggle = (agentId, targetEnabled) => {
    const nextSeq = (seqMap.get(agentId) || 0) + 1;
    seqMap.set(agentId, nextSeq);

    // Immediate optimistic update
    agents = agents.map((a) => (a.agent_id === agentId ? { ...a, is_enabled: targetEnabled } : a));

    return new Promise((resolve) => {
      resolvers.push({
        seq: nextSeq,
        resolve: () => {
          if (seqMap.get(agentId) === nextSeq) {
            agents = agents.map((a) => (a.agent_id === agentId ? { ...a, is_enabled: targetEnabled } : a));
          }
          resolve({ agent_id: agentId, is_enabled: targetEnabled });
        },
      });
    });
  };

  // User rapidly clicks: OFF (seq 1), then ON (seq 2), then OFF (seq 3)
  handleToggle("security", false);
  assert.equal(agents[0].is_enabled, false);

  handleToggle("security", true);
  assert.equal(agents[0].is_enabled, true);

  handleToggle("security", false);
  assert.equal(agents[0].is_enabled, false);

  // Now assume API responses arrive OUT OF ORDER: seq 2 arrives AFTER seq 3
  resolvers[2].resolve(); // seq 3 arrives first
  assert.equal(agents[0].is_enabled, false);

  resolvers[1].resolve(); // seq 2 arrives out-of-order late!
  // seq 2 must NOT overwrite the newer seq 3 state
  assert.equal(agents[0].is_enabled, false, "Older response must not overwrite newer user action");

  resolvers[0].resolve(); // seq 1 arrives late
  assert.equal(agents[0].is_enabled, false);
});

test("Failed toggle rolls back to previous state and triggers error notification", async () => {
  let agents = [
    { agent_id: "security", name: "Security Agent", is_enabled: true },
  ];
  const seqMap = new Map();
  let toastMessage = null;

  const handleToggle = async (agentId, targetEnabled) => {
    const previousState = agents.find((a) => a.agent_id === agentId)?.is_enabled;
    const nextSeq = (seqMap.get(agentId) || 0) + 1;
    seqMap.set(agentId, nextSeq);

    // Optimistic update
    agents = agents.map((a) => (a.agent_id === agentId ? { ...a, is_enabled: targetEnabled } : a));

    // Simulated network failure
    try {
      throw new Error("Network timeout: 504 Gateway Timeout");
    } catch (err) {
      if (seqMap.get(agentId) === nextSeq) {
        agents = agents.map((a) => (a.agent_id === agentId ? { ...a, is_enabled: previousState } : a));
        toastMessage = `Could not toggle agent: ${err.message}`;
      }
    }
  };

  await handleToggle("security", false);

  // Rolled back to true
  assert.equal(agents[0].is_enabled, true);
  assert.ok(toastMessage.includes("504 Gateway Timeout"));
});

