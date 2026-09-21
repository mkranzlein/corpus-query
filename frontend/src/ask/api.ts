/**
 * What the question page asks the API, and what comes back: the answer as a
 * stream of server-sent events, one passage read by id, and a verdict or a
 * correction recorded against an answer.
 *
 * Nothing here renders. Keeping the reading of the stream apart from the page
 * is what lets it be tested without a DOM, against bytes split wherever a
 * network might split them.
 */

/** One passage an answer rests on, as a citation names it. */
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

/** Someone worth asking, and the passages that named them. */
export interface RoutingCandidate {
  /** The person, as the roster spells them. */
  name: string;
  role: string;
  department: string;
  /** How many of the retrieved passages this person wrote or attended. */
  passages: number;
  /** Those passages, best first, cited the way an answer's are. */
  evidence: Citation[];
}

/** Who to ask when the record did not settle the question. */
export interface Routing {
  /** People worth asking, best first. Never empty when sent. */
  candidates: RoutingCandidate[];
  /** The question restated to stand on its own, for the user to edit. */
  question: string;
}

/** What `POST /answer` returns, and what its `answer` event carries. */
export interface AnswerBody {
  question: string;
  answer: string;
  citations: Citation[];
  searches: number;
  abstained: boolean;
  /** Who to ask, on an abstention that found someone to ask; else null. */
  routing: Routing | null;
  thread_id: string;
  answer_id: string;
  /**
   * The correction this turn recorded, when the message was the user
   * correcting an earlier answer rather than asking a question. It is
   * recorded against that earlier answer's id, not this turn's. Null for
   * every other turn.
   */
  correction: CorrectionRecord | null;
}

/** What every record written against an answer carries. */
interface AnswerRecord {
  /** Row id of this record. */
  id: number;
  /** The answer it was recorded against. */
  answer_id: string;
  /** When it was recorded, ISO 8601, UTC. */
  created_at: string;
  thread_id: string;
  /** The question that answer was given to. */
  question: string;
  answer: string;
  abstained: boolean;
  citations: Citation[];
  /** When someone marked it seen in the review queue, or null. */
  reviewed_at: string | null;
}

/** A correction to one answer, as `POST /corrections` returns it. */
export interface CorrectionRecord extends AnswerRecord {
  what_was_wrong: string;
  what_is_right: string;
}

/** Whether an answer was any good. */
export type Verdict = "up" | "down";

/** A verdict on one answer, as `POST /feedback` returns it. */
export interface FeedbackRecord extends AnswerRecord {
  verdict: Verdict;
  note: string | null;
}

/** One passage read back by id: a citation's fields, its text, and what was
 * derived about its document. */
export interface Chunk extends Citation {
  text: string;
  span_start: number | null;
  span_end: number | null;
  topics: string[];
  time_sensitivity: string | null;
  business_impact: string | null;
}

/**
 * A step reported while an answer is produced. The names and payloads are
 * the ones `POST /answer` documents for `text/event-stream`.
 */
export type Progress =
  | { event: "started"; data: { thread_id: string } }
  | { event: "drafting"; data: Record<string, never> }
  | { event: "searching"; data: { query: string } }
  | { event: "searched"; data: { query: string; citations: Citation[] } }
  | { event: "verifying"; data: Record<string, never> }
  | { event: "verified"; data: { verification: unknown; redraft: boolean } }
  | { event: "routing"; data: Record<string, never> }
  | { event: "correcting"; data: Record<string, never> };

/** Any event the stream sends: a step, the answer, or a failure. */
export type StreamEvent =
  | Progress
  | { event: "answer"; data: AnswerBody }
  | { event: "error"; data: { detail: string } };

/** Raised when a question could not be answered, with why, for a reader. */
export class AskError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "AskError";
  }
}

/** One event as it came off the wire, before its data is decoded. */
export interface RawEvent {
  event: string;
  data: string;
}

/**
 * Reads server-sent events out of text that arrives in arbitrary pieces.
 *
 * A network read can end anywhere: mid-line, mid-event, or between the `\r`
 * and `\n` of a line ending. Each call to {@link push} takes whatever came
 * and returns the events it completed; anything unfinished waits for the
 * next piece.
 *
 * Only what this API sends is interpreted — `event` and `data` lines. Comment
 * lines, which start with a colon and keep a connection alive, and any other
 * field are skipped, as the specification says a client should.
 */
export class EventReader {
  private buffer = "";
  private name = "";
  private data: string[] = [];

  /** Take the next piece of text and return the events it finished. */
  push(text: string): RawEvent[] {
    this.buffer += text;
    const finished: RawEvent[] = [];
    for (;;) {
      const end = this.buffer.search(/\r\n|\r|\n/);
      if (end === -1) {
        break;
      }
      // A lone \r at the very end may be the first half of \r\n, so it
      // waits until there is something after it to tell.
      if (this.buffer[end] === "\r" && end === this.buffer.length - 1) {
        break;
      }
      const width = this.buffer.startsWith("\r\n", end) ? 2 : 1;
      const line = this.buffer.slice(0, end);
      this.buffer = this.buffer.slice(end + width);
      const event = this.line(line);
      if (event) {
        finished.push(event);
      }
    }
    return finished;
  }

  /** Interpret one complete line, returning an event if it ended one. */
  private line(line: string): RawEvent | null {
    if (line === "") {
      if (this.data.length === 0) {
        this.name = "";
        return null;
      }
      const event = {
        event: this.name || "message",
        data: this.data.join("\n"),
      };
      this.name = "";
      this.data = [];
      return event;
    }
    if (line.startsWith(":")) {
      return null;
    }
    const colon = line.indexOf(":");
    const field = colon === -1 ? line : line.slice(0, colon);
    let value = colon === -1 ? "" : line.slice(colon + 1);
    if (value.startsWith(" ")) {
      value = value.slice(1);
    }
    if (field === "event") {
      this.name = value;
    } else if (field === "data") {
      this.data.push(value);
    }
    return null;
  }
}

/** Say what a refused request's body says was wrong, if it says. */
async function refusal(response: Response): Promise<string> {
  try {
    const body = (await response.json()) as { detail?: unknown };
    if (typeof body.detail === "string") {
      return body.detail;
    }
    // A validation failure lists what was wrong with each field.
    if (Array.isArray(body.detail) && body.detail.length > 0) {
      const first = body.detail[0] as { msg?: unknown };
      if (typeof first.msg === "string") {
        return first.msg;
      }
    }
  } catch {
    // Not JSON; the status is all there is to go on.
  }
  return `The service answered ${response.status}.`;
}

/**
 * Ask one question and report each step as it streams in.
 *
 * `EventSource` only makes `GET` requests, and `/answer` is a `POST`, so the
 * stream is read from the response body directly.
 *
 * @param question What was asked.
 * @param threadId The conversation to continue, or null to start one.
 * @param onProgress Called with each step, as it arrives.
 * @param signal Stops the request, and with it the run on the server.
 * @returns The finished answer.
 * @throws AskError If the request was refused, the run failed partway, or
 *     the stream ended without an answer.
 */
export async function ask(
  question: string,
  threadId: string | null,
  onProgress: (progress: Progress) => void,
  signal?: AbortSignal,
): Promise<AnswerBody> {
  let response: Response;
  try {
    response = await fetch("/answer", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "text/event-stream",
      },
      body: JSON.stringify(
        threadId === null ? { question } : { question, thread_id: threadId },
      ),
      signal,
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") {
      throw error;
    }
    throw new AskError("The service could not be reached. Is it running?");
  }
  if (!response.ok) {
    throw new AskError(await refusal(response));
  }
  if (!response.body) {
    throw new AskError("The service sent nothing back.");
  }

  const reader = response.body.pipeThrough(new TextDecoderStream()).getReader();
  const events = new EventReader();
  for (;;) {
    const { done, value } = await reader.read();
    // The last piece is followed by an end that finishes a final event
    // the server did not close with a blank line.
    const raw = events.push(done ? "\n\n" : value);
    for (const { event, data } of raw) {
      const parsed = {
        event,
        data: JSON.parse(data) as unknown,
      } as StreamEvent;
      if (parsed.event === "answer") {
        await reader.cancel();
        return parsed.data;
      }
      if (parsed.event === "error") {
        await reader.cancel();
        throw new AskError(parsed.data.detail);
      }
      onProgress(parsed);
    }
    if (done) {
      throw new AskError(
        "The answer stopped partway through. Try asking again.",
      );
    }
  }
}

/**
 * Read one passage, with its text and derived metadata.
 *
 * @throws AskError If the service would not return it.
 */
export async function readChunk(
  chunkId: number,
  signal?: AbortSignal,
): Promise<Chunk> {
  const response = await fetch(`/chunks/${chunkId}`, { signal });
  if (!response.ok) {
    throw new AskError(await refusal(response));
  }
  return (await response.json()) as Chunk;
}

/**
 * Send one record to be written, and return the row the service wrote.
 *
 * @throws AskError If the service could not be reached or refused it.
 */
async function record<T>(path: string, body: unknown): Promise<T> {
  let response: Response;
  try {
    response = await fetch(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
  } catch {
    throw new AskError("The service could not be reached. Is it running?");
  }
  if (!response.ok) {
    throw new AskError(await refusal(response));
  }
  return (await response.json()) as T;
}

/**
 * Record a verdict on one answer.
 *
 * @param answerId The answer being judged, as `/answer` returned it.
 * @param verdict Up or down.
 * @returns The verdict as the service wrote it.
 * @throws AskError If it was not recorded.
 */
export function recordFeedback(
  answerId: string,
  verdict: Verdict,
): Promise<FeedbackRecord> {
  return record("/feedback", { answer_id: answerId, verdict });
}

/**
 * Record what one answer got wrong, and what is right instead.
 *
 * @param answerId The answer being corrected, as `/answer` returned it.
 * @returns The correction as the service wrote it.
 * @throws AskError If it was not recorded.
 */
export function recordCorrection(
  answerId: string,
  whatWasWrong: string,
  whatIsRight: string,
): Promise<CorrectionRecord> {
  return record("/corrections", {
    answer_id: answerId,
    what_was_wrong: whatWasWrong,
    what_is_right: whatIsRight,
  });
}
