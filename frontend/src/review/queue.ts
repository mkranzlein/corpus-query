/**
 * The review queue's data: what the API returns for gaps, corrections, and
 * feedback, and the handful of operations the review page performs on it.
 *
 * Nothing here renders. Keeping the fetching, merging, and summarizing apart
 * from the page is what lets them be tested without a DOM.
 */

import type { Routing } from "../ask/api.ts";

/** The three kinds of record, by the path each is listed at. */
export type Kind = "gaps" | "corrections" | "feedback";

/** Every kind, in the order the page offers them as filters. */
export const KINDS: readonly Kind[] = ["gaps", "corrections", "feedback"];

/** What the page calls one record of each kind, and several. */
export const LABELS: Record<Kind, { one: string; many: string }> = {
  gaps: { one: "Gap", many: "Gaps" },
  corrections: { one: "Correction", many: "Corrections" },
  feedback: { one: "Feedback", many: "Feedback" },
};

/**
 * How many of each kind the page asks for. This is the most one read may
 * return, so the merged queue shows the most recent this many of everything.
 */
export const QUEUE_LIMIT = 200;

/** One passage an answer rested on. */
export interface Citation {
  chunk_id: number;
  document_slug: string;
  source_kind: string;
  title: string;
  document_date: string;
  author: string | null;
  attendees: string[];
  location: string;
}

/** What every kind of record carries. */
interface BaseRecord {
  id: number;
  answer_id: string;
  created_at: string;
  reviewed_at: string | null;
  thread_id: string;
  question: string;
  answer: string;
  abstained: boolean;
  citations: Citation[];
}

/** A question the record did not settle. */
export interface Gap extends BaseRecord {
  kind: "gaps";
  routing: Routing | null;
}

/** A user saying what an answer got wrong. */
export interface Correction extends BaseRecord {
  kind: "corrections";
  what_was_wrong: string;
  what_is_right: string;
}

/** A verdict on an answer. */
export interface Feedback extends BaseRecord {
  kind: "feedback";
  verdict: "up" | "down";
  note: string | null;
}

/**
 * One item in the queue. The `kind` is added by the page rather than sent by
 * the API, which says it with the path instead; carrying it on the item is
 * what lets the three lists be merged into one.
 */
export type QueueItem = Gap | Correction | Feedback;

/** Raised when the API answers with anything but success. */
export class ApiError extends Error {
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

/** Fetch JSON, turning a failed status into an {@link ApiError}. */
async function json<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, init);
  if (!response.ok) {
    throw new ApiError(
      response.status,
      `${init?.method ?? "GET"} ${url} answered ${response.status}`,
    );
  }
  return (await response.json()) as T;
}

/** Tag every record in one kind's list with that kind. */
function tagged(kind: Kind, rows: object[]): QueueItem[] {
  return rows.map((row) => ({ ...row, kind }) as QueueItem);
}

/**
 * Read all three kinds and merge them, most recent first.
 *
 * Each list is already newest first and capped at {@link QUEUE_LIMIT}, so the
 * newest {@link QUEUE_LIMIT} of the merge are the newest of everything.
 */
export async function loadQueue(
  signal?: AbortSignal,
): Promise<{ items: QueueItem[]; truncated: boolean }> {
  const lists = await Promise.all(
    KINDS.map(async (kind) => {
      const body = await json<Record<Kind, object[]>>(
        `/${kind}?limit=${QUEUE_LIMIT}`,
        { signal },
      );
      return tagged(kind, body[kind]);
    }),
  );
  const truncated = lists.some((list) => list.length >= QUEUE_LIMIT);
  return { items: mostRecentFirst(lists.flat()), truncated };
}

/**
 * Order items newest first. Timestamps are ISO 8601 in UTC with a fixed
 * width, so they sort as strings; the kind and id break ties so the order
 * does not change between loads.
 */
export function mostRecentFirst(items: QueueItem[]): QueueItem[] {
  return [...items].sort(
    (a, b) =>
      b.created_at.localeCompare(a.created_at) ||
      a.kind.localeCompare(b.kind) ||
      b.id - a.id,
  );
}

/** Narrow the queue to one kind, or leave it whole for `"all"`. */
export function narrowed(
  items: QueueItem[],
  kind: Kind | "all",
): QueueItem[] {
  return kind === "all" ? items : items.filter((item) => item.kind === kind);
}

/** Read one record again, in full, as it stands now. */
export async function openRecord(
  kind: Kind,
  id: number,
  signal?: AbortSignal,
): Promise<QueueItem> {
  const row = await json<object>(`/${kind}/${id}`, { signal });
  return tagged(kind, [row])[0];
}

/** Mark one record reviewed, or put it back among the new ones. */
export async function setReviewed(
  kind: Kind,
  id: number,
  reviewed: boolean,
): Promise<QueueItem> {
  const row = await json<object>(`/${kind}/${id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ reviewed }),
  });
  return tagged(kind, [row])[0];
}

/** A stable key for an item, since ids are only unique within a kind. */
export function itemKey(item: Pick<QueueItem, "kind" | "id">): string {
  return `${item.kind}:${item.id}`;
}

/**
 * Say in one line what the system did with the question: answered it,
 * declined to, or declined and suggested someone to ask.
 */
export function whatTheSystemDid(item: QueueItem): string {
  const cited = item.citations.length;
  let did: string;
  if (item.abstained) {
    did = "Could not answer";
  } else if (cited === 0) {
    did = "Answered without citing a passage";
  } else {
    did = `Answered, citing ${cited} ${cited === 1 ? "passage" : "passages"}`;
  }
  const candidates = item.kind === "gaps" ? (item.routing?.candidates ?? []) : [];
  if (candidates.length > 0) {
    const names = candidates.map((candidate) => candidate.name).join(", ");
    did += `; suggested asking ${names}`;
  }
  return did;
}

/** Say in one line what the record itself adds: the correction or verdict. */
export function whatWasSaid(item: QueueItem): string | null {
  switch (item.kind) {
    case "corrections":
      return `Correction: ${item.what_is_right}`;
    case "feedback": {
      const verdict = item.verdict === "up" ? "Thumbs up" : "Thumbs down";
      return item.note ? `${verdict}: ${item.note}` : verdict;
    }
    case "gaps":
      return null;
  }
}
