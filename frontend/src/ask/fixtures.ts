/**
 * Answers and passages as the API returns them, and a stand-in for the API
 * itself, for the question page's tests.
 */

import { vi } from "vitest";

import type { AnswerBody, Chunk, Citation } from "./api.ts";

export const CITATION: Citation = {
  chunk_id: 98,
  document_slug: "xt-9-rev-b-thermal-drift",
  source_kind: "transcript",
  title: "XT-9 Rev B Thermal Drift",
  document_date: "2026-03-05",
  author: null,
  attendees: ["Marcus", "Sofia", "Devon"],
  location: "turns 4-13",
};

export const AUTHORED: Citation = {
  chunk_id: 214,
  document_slug: "xt-9-rev-b-thermal-qualification-report",
  source_kind: "docx",
  title: "XT-9 Rev B Thermal Qualification Report",
  document_date: "2026-03-12",
  author: "Sofia",
  attendees: [],
  location: "Recommendation > Rev C Replacement Threshold",
};

/** The full record behind a citation, as `GET /chunks/{id}` returns it. */
export function chunkFor(
  citation: Citation,
  overrides: Partial<Chunk> = {},
): Chunk {
  return {
    ...citation,
    text: `The passage behind ${citation.title}.`,
    span_start: 4,
    span_end: 13,
    topics: ["Firmware", "Thermal"],
    time_sensitivity: "near_term",
    business_impact: "significant",
    ...overrides,
  };
}

export function answered(overrides: Partial<AnswerBody> = {}): AnswerBody {
  return {
    question: "What did we decide about the XT-9 rev B thermal drift?",
    answer: "The team settled on a firmware workaround, per Marcus.",
    citations: [CITATION, AUTHORED],
    searches: 1,
    abstained: false,
    routing: null,
    thread_id: "thread-1",
    answer_id: "answer-1",
    correction: null,
    ...overrides,
  };
}

export function abstained(overrides: Partial<AnswerBody> = {}): AnswerBody {
  return answered({
    question: "Which rev B units run hot?",
    answer: "The record does not say which Rev B units are installed hot.",
    citations: [AUTHORED],
    abstained: true,
    routing: { candidates: [], question: "Which units run hot?" },
    answer_id: "answer-2",
    ...overrides,
  });
}

/** Encode one server-sent event the way the service does. */
export function sse(event: string, data: unknown): string {
  return `event: ${event}\r\ndata: ${JSON.stringify(data)}\r\n\r\n`;
}

/** The events of a searching turn, up to and including its answer. */
export function turn(answer: AnswerBody): string[] {
  return [
    sse("started", { thread_id: answer.thread_id }),
    sse("drafting", {}),
    sse("searching", { query: "XT-9 thermal drift" }),
    sse("searched", {
      query: "XT-9 thermal drift",
      citations: answer.citations,
    }),
    sse("drafting", {}),
    sse("verifying", {}),
    sse("verified", { verification: null, redraft: false }),
    sse("routing", {}),
    sse("answer", answer),
  ];
}

/**
 * A response body the test feeds by hand, so what the page shows between
 * two events can be looked at.
 */
export function heldStream() {
  const encoder = new TextEncoder();
  let feed!: ReadableStreamDefaultController<Uint8Array>;
  const body = new ReadableStream<Uint8Array>({
    start(controller) {
      feed = controller;
    },
  });
  return {
    response: new Response(body, {
      headers: { "Content-Type": "text/event-stream" },
    }),
    send(text: string) {
      feed.enqueue(encoder.encode(text));
    },
    close() {
      feed.close();
    },
  };
}

/** A streamed response carrying the given text, split into small pieces. */
export function streamed(parts: string[], pieceSize = 17): Response {
  const encoder = new TextEncoder();
  const text = parts.join("");
  const body = new ReadableStream<Uint8Array>({
    start(controller) {
      // Split without regard to where events or lines end, the way a
      // network is free to.
      for (let start = 0; start < text.length; start += pieceSize) {
        controller.enqueue(
          encoder.encode(text.slice(start, start + pieceSize)),
        );
      }
      controller.close();
    },
  });
  return new Response(body, {
    headers: { "Content-Type": "text/event-stream" },
  });
}

function json(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

/**
 * Stand in for the API: `/answer` replies with the next of `answers`, and
 * `/chunks/{id}` with the record behind any citation in `chunks`.
 *
 * Returns the mock, so a test can see what was asked of it.
 */
export function stubApi(options: {
  answers: (() => Response)[];
  chunks?: Chunk[];
}) {
  const queue = [...options.answers];
  const chunks = new Map(
    (options.chunks ?? []).map((chunk) => [chunk.chunk_id, chunk]),
  );
  const fetchMock = vi.fn((input: RequestInfo | URL) => {
    const url = new URL(String(input), "http://api.test");
    if (url.pathname === "/answer") {
      const next = queue.shift();
      return Promise.resolve(
        next ? next() : json(500, { detail: "no answer queued" }),
      );
    }
    const match = /^\/chunks\/(\d+)$/.exec(url.pathname);
    if (match) {
      const chunk = chunks.get(Number(match[1]));
      return Promise.resolve(
        chunk
          ? json(200, chunk)
          : json(404, { detail: `no chunk with id ${match[1]}` }),
      );
    }
    return Promise.resolve(json(404, { detail: "Not Found" }));
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

export { json };
