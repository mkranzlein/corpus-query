import { describe, expect, it } from "vitest";

import type { Progress } from "./api.ts";
import { CITATION } from "./fixtures.ts";
import { lines } from "./progress.ts";

describe("describing progress", () => {
  it("says what each step of a searching turn is doing", () => {
    const steps: Progress[] = [
      { event: "started", data: { thread_id: "t" } },
      { event: "drafting", data: {} },
      { event: "searching", data: { query: "thermal drift" } },
      {
        event: "searched",
        data: { query: "thermal drift", citations: [CITATION] },
      },
      { event: "drafting", data: {} },
      { event: "verifying", data: {} },
      { event: "verified", data: { verification: null, redraft: false } },
      { event: "routing", data: {} },
    ];

    expect(lines(steps)).toEqual([
      "Question received",
      "Drafting an answer",
      "Searching the record for “thermal drift”",
      "Found 1 passage for “thermal drift”",
      "Drafting an answer from what was found",
      "Checking each claim against the passages",
      "Every claim is supported by a passage",
      "Judging whether the answer settles the question",
    ]);
  });

  it("says when a draft goes back to be redrafted", () => {
    const steps: Progress[] = [
      {
        event: "verified",
        data: { verification: { rejected: ["x"] }, redraft: true },
      },
      { event: "drafting", data: {} },
    ];

    expect(lines(steps)).toEqual([
      "A claim was not supported by the passages, so it goes back for a redraft",
      "Drafting the answer again",
    ]);
  });

  it("says when a search found nothing", () => {
    expect(
      lines([
        { event: "searched", data: { query: "kalamazoo", citations: [] } },
      ]),
    ).toEqual(["Nothing came back for “kalamazoo”"]);
  });

  it("says nothing for a step it does not know", () => {
    expect(
      lines([{ event: "unheard-of", data: {} } as unknown as Progress]),
    ).toEqual([]);
  });
});
