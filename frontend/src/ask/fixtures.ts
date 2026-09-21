/**
 * Answers and passages as the API returns them, and a stand-in for the API
 * itself, for the question page's tests.
 */

import { vi } from "vitest";

import type { AnswerBody, Chunk, Citation } from "./api.ts";

export const CITATION: Citation = {
  chunk_id: 113,
  document_slug: "q2-pricing-review",
  source_kind: "transcript",
  title: "Q2 Pricing Review",
  document_date: "2026-03-11",
  author: null,
  attendees: ["Priya", "Elena", "Renata"],
  location: "turns 22-30",
};

export const AUTHORED: Citation = {
  chunk_id: 170,
  document_slug: "mx-3-firmware-2-4-2-soak-test-report",
  source_kind: "docx",
  title: "MX-3 Firmware 2.4.2 Soak Test Report",
  document_date: "2026-04-14",
  author: "Sofia",
  attendees: [],
  location: "Results > Extended Soak",
};

/** The full record behind a citation, as `GET /chunks/{id}` returns it. */
export function chunkFor(
  citation: Citation,
  overrides: Partial<Chunk> = {},
): Chunk {
  return {
    ...citation,
    text: `The passage behind ${citation.title}.`,
    span_start: 22,
    span_end: 30,
    topics: ["Pricing", "Sales"],
    time_sensitivity: "near_term",
    business_impact: "significant",
    ...overrides,
  };
}

export function answered(overrides: Partial<AnswerBody> = {}): AnswerBody {
  return {
    question: "What did we decide about the RV-2 introductory price?",
    answer: "The RV-2 launches at $189 for ninety days, per Priya.",
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
    question: "Which sites are the remote Quennick units at?",
    answer: "The record does not say which sites the remote Quennick units are at.",
    citations: [AUTHORED],
    abstained: true,
    answer_id: "answer-2",
    ...overrides,
  });
}

/*
 * A routed abstention, as the service builds one. The passages, their ids,
 * and who wrote or attended each are the corpus's own, and the candidates
 * are what the routing code ranks out of them: Elena is named by three of
 * the four passages, Sofia by two, and Priya by one, ahead of the others in
 * that meeting because she is listed first.
 */

export const ROLLOUT: Citation = {
  chunk_id: 170,
  document_slug: "mx-3-firmware-2-4-2-soak-test-report",
  source_kind: "docx",
  title: "MX-3 Firmware 2.4.2 Soak Test Report",
  document_date: "2026-04-14",
  author: "Sofia",
  attendees: [],
  location: "Field Rollout",
};

export const ESCALATION: Citation = {
  chunk_id: 118,
  document_slug: "quennick-escalation-firmware-defect-on-mx-3-units",
  source_kind: "transcript",
  title: "Quennick Escalation — Firmware Defect on MX-3 Units",
  document_date: "2026-04-09",
  author: null,
  attendees: ["Priya", "Sofia", "Theo", "Elena", "Callum"],
  location: "turns 24-31",
};

export const FIX_STANDS: Citation = {
  chunk_id: 201,
  document_slug: "quennick-account-recovery-briefing",
  source_kind: "pptx",
  title: "Quennick Account Recovery Briefing",
  document_date: "2026-04-15",
  author: "Elena",
  attendees: [],
  location: "slide 5 — Where the Fix Stands",
};

export const RECOVERY_PLAN: Citation = {
  chunk_id: 205,
  document_slug: "quennick-account-recovery-briefing",
  source_kind: "pptx",
  title: "Quennick Account Recovery Briefing",
  document_date: "2026-04-15",
  author: "Elena",
  attendees: [],
  location: "slide 9 — Recovery Plan: Next 30 Days",
};

/** The words of the soak test report's field rollout section. */
export const ROLLOUT_TEXT =
  "Field Rollout\n" +
  "Firmware 2.4.2 was published to the OTA channel for the reporting " +
  "customer on the evening of April 10. MX-3 units pull updates at their " +
  "next six-hourly check-in, and 301 of that customer's 312 units were on " +
  "2.4.2 by the morning of April 11. The other 11 are the units that had " +
  "faulted, which cannot check in until they are power cycled. Nine have " +
  "since been power cycled and updated. Two are at remote sites and are " +
  "scheduled.";

export const REMOTE_QUESTION =
  "I was trying to find out when the last two faulted Quennick MX-3 units " +
  "at remote sites will be power cycled and updated to firmware 2.4.2. What " +
  "we have says the visits are scheduled, but gives no date for them. Do " +
  "you know when those two remote units are due to be updated?";

/** An abstention with three people to ask, each for different passages. */
export function routed(overrides: Partial<AnswerBody> = {}): AnswerBody {
  return abstained({
    question: "When will the two remote Quennick units get firmware 2.4.2?",
    answer:
      "The record says the last two faulted units are at remote sites and " +
      "their visits are scheduled, but it does not give a date.",
    citations: [ROLLOUT, ESCALATION, FIX_STANDS, RECOVERY_PLAN],
    routing: {
      candidates: [
        {
          name: "Elena",
          role: "Head of Sales",
          department: "Sales",
          passages: 3,
          evidence: [ESCALATION, FIX_STANDS, RECOVERY_PLAN],
        },
        {
          name: "Sofia",
          role: "Firmware Engineer",
          department: "Engineering",
          passages: 2,
          evidence: [ROLLOUT, ESCALATION],
        },
        {
          name: "Priya",
          role: "CEO",
          department: "Executive",
          passages: 1,
          evidence: [ESCALATION],
        },
      ],
      question: REMOTE_QUESTION,
    },
    answer_id: "answer-4",
    ...overrides,
  });
}

export const COUNTER: Citation = {
  chunk_id: 172,
  document_slug: "mx-3-firmware-2-4-2-soak-test-report",
  source_kind: "docx",
  title: "MX-3 Firmware 2.4.2 Soak Test Report",
  document_date: "2026-04-14",
  author: "Sofia",
  attendees: [],
  location: "Findings > An Unrelated Counter to Watch",
};

/** An abstention with one person to ask, named by the one passage found. */
export function routedToOne(overrides: Partial<AnswerBody> = {}): AnswerBody {
  return abstained({
    question: "Is the MX-3 idle manager safe when the uptime counter wraps?",
    answer:
      "The record says the comparison looks wrap-safe but has not been " +
      "proven, and that it was filed as a separate ticket.",
    citations: [COUNTER],
    routing: {
      candidates: [
        {
          name: "Sofia",
          role: "Firmware Engineer",
          department: "Engineering",
          passages: 1,
          evidence: [COUNTER],
        },
      ],
      question:
        "I was trying to find out whether the MX-3 uptime counter, which " +
        "wraps after about 49.7 days, has been confirmed safe in the idle " +
        "manager. The soak test report says it looks wrap-safe but has not " +
        "been proven, and that it was filed as a separate ticket. Has anyone " +
        "confirmed whether the idle manager handles the uptime counter " +
        "wrapping?",
    },
    answer_id: "answer-5",
    ...overrides,
  });
}

/**
 * A question outside the corpus, declined without a search: not an
 * abstention, and routed to nobody.
 */
export function declined(overrides: Partial<AnswerBody> = {}): AnswerBody {
  return answered({
    question: "What's a good recipe for banana bread?",
    answer: "I answer from this organization's record, and that is outside it.",
    citations: [],
    searches: 0,
    abstained: false,
    routing: null,
    answer_id: "answer-6",
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
    sse("searching", { query: "RV-2 introductory price" }),
    sse("searched", {
      query: "RV-2 introductory price",
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
