import { describe, expect, it } from "vitest";
import { parseSse } from "./api";

describe("parseSse", () => {
  it("keeps the typed event envelope", () => {
    const event = {
      type: "handoff",
      run_id: "run-1",
      thread_id: "thread-1",
      user_id: "user-1",
      seq: 1,
      data: { from: "triage", to: "return" },
    };
    expect(parseSse(`event: handoff\ndata: ${JSON.stringify(event)}\n\n`)).toEqual([event]);
  });
});

