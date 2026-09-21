import { afterEach, describe, expect, it, vi } from "vitest";

import { AskError, EventReader, type Progress, ask, readChunk } from "./api.ts";
import {
  CITATION,
  answered,
  chunkFor,
  json,
  sse,
  streamed,
  stubApi,
  turn,
} from "./fixtures.ts";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("reading server-sent events", () => {
  it("reads events however the text is split", () => {
    const text = sse("searching", { query: "a" }) + sse("drafting", {});
    for (let size = 1; size <= text.length; size++) {
      const reader = new EventReader();
      const events = [];
      for (let start = 0; start < text.length; start += size) {
        events.push(...reader.push(text.slice(start, start + size)));
      }
      expect(events).toEqual([
        { event: "searching", data: '{"query":"a"}' },
        { event: "drafting", data: "{}" },
      ]);
    }
  });

  it("joins data lines and skips comments and other fields", () => {
    const reader = new EventReader();

    const events = reader.push(
      ": keepalive\nid: 3\nevent: x\ndata: one\ndata: two\n\n",
    );

    expect(events).toEqual([{ event: "x", data: "one\ntwo" }]);
  });

  it("waits for the blank line that ends an event", () => {
    const reader = new EventReader();

    expect(reader.push("event: x\ndata: {}\n")).toEqual([]);
    expect(reader.push("\n")).toEqual([{ event: "x", data: "{}" }]);
  });
});

describe("asking a question", () => {
  it("reports each step and returns the answer", async () => {
    const body = answered();
    stubApi({ answers: [() => streamed(turn(body))] });
    const steps: Progress[] = [];

    const answer = await ask("What about the drift?", null, (step) =>
      steps.push(step),
    );

    expect(answer).toEqual(body);
    expect(steps.map((step) => step.event)).toEqual([
      "started",
      "drafting",
      "searching",
      "searched",
      "drafting",
      "verifying",
      "verified",
      "routing",
    ]);
  });

  it("asks for a stream, and continues the thread it is given", async () => {
    const fetchMock = stubApi({ answers: [() => streamed(turn(answered()))] });

    await ask("Who owns that?", "thread-1", () => {});

    const [url, init] = fetchMock.mock.calls[0] as unknown as [
      string,
      RequestInit,
    ];
    expect(url).toBe("/answer");
    expect(init.method).toBe("POST");
    expect(new Headers(init.headers).get("Accept")).toBe("text/event-stream");
    expect(JSON.parse(String(init.body))).toEqual({
      question: "Who owns that?",
      thread_id: "thread-1",
    });
  });

  it("starts a new thread when there is none", async () => {
    const fetchMock = stubApi({ answers: [() => streamed(turn(answered()))] });

    await ask("What about the drift?", null, () => {});

    const [, init] = fetchMock.mock.calls[0] as unknown as [
      string,
      RequestInit,
    ];
    expect(JSON.parse(String(init.body))).toEqual({
      question: "What about the drift?",
    });
  });

  it("turns an error event into an error saying why", async () => {
    stubApi({
      answers: [
        () =>
          streamed([
            sse("started", { thread_id: "t" }),
            sse("error", { detail: "ConnectError: model unreachable" }),
          ]),
      ],
    });

    await expect(ask("q", null, () => {})).rejects.toThrow(
      new AskError("ConnectError: model unreachable"),
    );
  });

  it("treats a stream that ends without an answer as a failure", async () => {
    stubApi({
      answers: [() => streamed([sse("started", { thread_id: "t" })])],
    });

    await expect(ask("q", null, () => {})).rejects.toThrow(/stopped partway/);
  });

  it("says what a refused question was refused for", async () => {
    stubApi({
      answers: [
        () =>
          json(422, {
            detail: [{ msg: "Value error, question must not be empty" }],
          }),
      ],
    });

    await expect(ask(" ", null, () => {})).rejects.toThrow(
      /question must not be empty/,
    );
  });

  it("says the service could not be reached when the request fails", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() => Promise.reject(new TypeError("Failed to fetch"))),
    );

    await expect(ask("q", null, () => {})).rejects.toThrow(
      /could not be reached/,
    );
  });
});

describe("reading a passage", () => {
  it("reads it by id", async () => {
    stubApi({ answers: [], chunks: [chunkFor(CITATION)] });

    const chunk = await readChunk(CITATION.chunk_id);

    expect(chunk.text).toBe("The passage behind XT-9 Rev B Thermal Drift.");
  });

  it("fails for an id the corpus does not hold", async () => {
    stubApi({ answers: [] });

    await expect(readChunk(5)).rejects.toThrow(/no chunk with id 5/);
  });
});
