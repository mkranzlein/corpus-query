/**
 * Records as the API returns them, and a stand-in for the API itself, for the
 * review queue's tests.
 */

import { vi } from "vitest";

import type { Citation, Kind } from "./queue.ts";

export const CITATION: Citation = {
  chunk_id: 7,
  document_slug: "rev-b-schedule",
  source_kind: "transcript",
  title: "Rev B schedule",
  document_date: "2026-03-04",
  author: null,
  attendees: ["Priya", "Marcus"],
  location: "turns 0-1",
};

const shared = {
  answer_id: "a1",
  thread_id: "thread-1",
  question: "Where are the rev B boards?",
  answer: "Marcus put them two weeks out.",
  abstained: false,
  citations: [CITATION],
  reviewed_at: null as string | null,
};

export function gap(overrides: Record<string, unknown> = {}) {
  return {
    ...shared,
    id: 1,
    created_at: "2026-03-01T09:00:00.000Z",
    question: "Which units are installed in hot environments?",
    answer: "The record does not say.",
    abstained: true,
    citations: [],
    routing: {
      question: "Which units are installed in hot environments?",
      candidates: [
        {
          name: "Sofia",
          role: "Firmware Engineer",
          department: "Engineering",
          passages: 2,
          evidence: [CITATION],
        },
      ],
    },
    ...overrides,
  };
}

export function correction(overrides: Record<string, unknown> = {}) {
  return {
    ...shared,
    id: 1,
    created_at: "2026-03-03T09:00:00.000Z",
    what_was_wrong: "It said the freeze is March 12th.",
    what_is_right: "The freeze moved to March 19th.",
    ...overrides,
  };
}

export function feedback(overrides: Record<string, unknown> = {}) {
  return {
    ...shared,
    id: 1,
    created_at: "2026-03-02T09:00:00.000Z",
    verdict: "down",
    note: "cited the wrong meeting",
    ...overrides,
  };
}

/**
 * Stand in for the API with the three lists given, answering reads of one
 * record and review marks against them the way the service does.
 *
 * Returns the mock, so a test can see what was asked of it.
 */
export function stubApi(lists: Partial<Record<Kind, object[]>>) {
  const stored: Record<Kind, Record<string, unknown>[]> = {
    gaps: [...(lists.gaps ?? [])] as Record<string, unknown>[],
    corrections: [...(lists.corrections ?? [])] as Record<string, unknown>[],
    feedback: [...(lists.feedback ?? [])] as Record<string, unknown>[],
  };
  const reply = (status: number, body: unknown) =>
    Promise.resolve(
      new Response(JSON.stringify(body), {
        status,
        headers: { "Content-Type": "application/json" },
      }),
    );

  const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
    const url = new URL(String(input), "http://api.test");
    const [, kind, id] = url.pathname.split("/") as [string, Kind, string?];
    if (!(kind in stored)) {
      return reply(404, { detail: "not found" });
    }
    if (id === undefined) {
      return reply(200, { [kind]: stored[kind] });
    }
    const index = stored[kind].findIndex((row) => row.id === Number(id));
    if (index === -1) {
      return reply(404, { detail: `no ${kind} record has id ${id}` });
    }
    if (init?.method === "PATCH") {
      const { reviewed } = JSON.parse(String(init.body)) as {
        reviewed: boolean;
      };
      stored[kind][index] = {
        ...stored[kind][index],
        reviewed_at: reviewed ? "2026-03-05T12:00:00.000Z" : null,
      };
    }
    return reply(200, stored[kind][index]);
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}
