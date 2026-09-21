import { type FormEvent, useEffect, useRef, useState } from "react";

import {
  AskError,
  type CorrectionRecord,
  type FeedbackRecord,
  type Verdict,
  recordCorrection,
  recordFeedback,
} from "./api.ts";

interface FeedbackProps {
  /** The answer being judged, by the id `/answer` returned for it. */
  answerId: string;
  /**
   * A correction to this answer that the conversation already recorded, or
   * null. When there is one, no second is offered from here.
   */
  corrected: CorrectionRecord | null;
}

/** Where a verdict stands. */
type Vote =
  | { state: "idle" }
  | { state: "sending"; verdict: Verdict }
  | { state: "recorded"; record: FeedbackRecord }
  | { state: "failed"; verdict: Verdict; detail: string };

/** Where a correction written here stands. */
type Written =
  | { state: "idle" }
  | { state: "sending" }
  | { state: "recorded"; record: CorrectionRecord }
  | { state: "failed"; detail: string };

/** What the page says about a verdict once it has been recorded. */
const RECORDED: Record<Verdict, string> = {
  up: "Recorded as helpful.",
  down: "Recorded as not helpful.",
};

/** Say why a write failed, for a reader. */
function reason(error: unknown): string {
  return error instanceof AskError
    ? error.message
    : "Something went wrong sending it.";
}

/**
 * A verdict on one answer, and a way to say what it got wrong.
 *
 * The two are recorded apart. A vote up or down is written as soon as it is
 * cast, as feedback. A vote down then asks what was wrong: answering writes a
 * correction as well, and declining leaves the vote as it was recorded. A
 * vote is final once recorded, because nothing records a change of mind.
 *
 * Every write says whether it landed. A confirmation is shown only once the
 * service returns the row it wrote, and a correction's confirmation repeats
 * that row's text, so what the user reads is what was stored. A write that
 * fails says why, and keeps what was entered so it can be sent again.
 *
 * A correction typed into the conversation is recorded by the agent against
 * the answer it corrects, and comes back on that later turn. The page hands
 * it here, and this answer then shows it as recorded rather than offering to
 * record another.
 */
export default function Feedback({ answerId, corrected }: FeedbackProps) {
  const [vote, setVote] = useState<Vote>({ state: "idle" });
  const [inviting, setInviting] = useState(false);
  const [wrong, setWrong] = useState("");
  const [right, setRight] = useState("");
  const [written, setWritten] = useState<Written>({ state: "idle" });
  const first = useRef<HTMLTextAreaElement>(null);
  const id = `feedback-${answerId}`;

  const voted = vote.state === "recorded" ? vote.record.verdict : null;
  const pending = vote.state === "sending" ? vote.verdict : null;
  const mine = written.state === "recorded" ? written.record : null;
  const invited = inviting && corrected === null && mine === null;

  // The question follows from the vote the user just cast, so the cursor
  // goes to where the answer to it is typed.
  useEffect(() => {
    if (invited) {
      first.current?.focus();
    }
  }, [invited]);

  async function cast(verdict: Verdict) {
    setVote({ state: "sending", verdict });
    try {
      const record = await recordFeedback(answerId, verdict);
      setVote({ state: "recorded", record });
      setInviting(verdict === "down");
    } catch (error) {
      setVote({ state: "failed", verdict, detail: reason(error) });
    }
  }

  async function correct(event: FormEvent) {
    event.preventDefault();
    if (!wrong.trim() || !right.trim() || written.state === "sending") {
      return;
    }
    setWritten({ state: "sending" });
    try {
      const record = await recordCorrection(
        answerId,
        wrong.trim(),
        right.trim(),
      );
      setWritten({ state: "recorded", record });
      setInviting(false);
    } catch (error) {
      setWritten({ state: "failed", detail: reason(error) });
    }
  }

  const locked = vote.state === "sending" || vote.state === "recorded";
  // The latest thing that landed, or is on its way, in words.
  const said =
    written.state === "recorded"
      ? "Correction recorded."
      : pending
        ? "Recording…"
        : voted
          ? RECORDED[voted]
          : "";

  return (
    <section className="feedback" aria-labelledby={id}>
      <div className="vote">
        <h3 id={id}>Was this answer helpful?</h3>
        <div className="actions" role="group" aria-labelledby={id}>
          {(["up", "down"] as const).map((verdict) => (
            <button
              key={verdict}
              type="button"
              aria-pressed={voted === verdict}
              disabled={locked}
              onClick={() => void cast(verdict)}
            >
              {verdict === "up" ? "Helpful" : "Not helpful"}
            </button>
          ))}
        </div>
        {/* A live region rather than a status role: the page's one status
            is the progress of an answer being produced, and this is
            announced alongside it rather than in place of it. */}
        <p className="recorded" aria-live="polite">
          {said}
        </p>
      </div>

      {vote.state === "failed" && (
        <p className="write-failed" role="alert">
          Your vote was not recorded: {vote.detail} Try again when you are
          ready.
        </p>
      )}

      {corrected !== null && (
        <Recorded
          record={corrected}
          heading="Corrected in the conversation"
          lede="Your correction to this answer was recorded from the conversation below, so there is nothing more to send from here."
        />
      )}

      {mine !== null && (
        <Recorded
          record={mine}
          heading="Correction recorded"
          lede="It is kept for review, and does not change how later questions are answered."
        />
      )}

      {invited && (
        <form className="correction" onSubmit={(event) => void correct(event)}>
          <p className="invite">
            What was wrong with it? A correction says what the answer got wrong
            and what is right instead, and goes to review. It is optional: your
            vote is already recorded.
          </p>
          <label htmlFor={`${id}-wrong`}>What it got wrong</label>
          <textarea
            id={`${id}-wrong`}
            ref={first}
            rows={2}
            value={wrong}
            onChange={(event) => setWrong(event.target.value)}
          />
          <label htmlFor={`${id}-right`}>What is right instead</label>
          <textarea
            id={`${id}-right`}
            rows={2}
            value={right}
            onChange={(event) => setRight(event.target.value)}
          />
          <div className="actions">
            <button
              type="submit"
              className="primary"
              disabled={
                !wrong.trim() || !right.trim() || written.state === "sending"
              }
            >
              {written.state === "sending"
                ? "Recording…"
                : "Record the correction"}
            </button>
            <button
              type="button"
              disabled={written.state === "sending"}
              onClick={() => setInviting(false)}
            >
              No thanks
            </button>
          </div>
          {written.state === "failed" && (
            <p className="write-failed" role="alert">
              The correction was not recorded: {written.detail} What you wrote
              is kept, so you can send it again.
            </p>
          )}
        </form>
      )}
    </section>
  );
}

interface RecordedProps {
  record: CorrectionRecord;
  heading: string;
  lede: string;
}

/** A correction as the service stored it. */
function Recorded({ record, heading, lede }: RecordedProps) {
  return (
    <div className="corrected">
      <p>
        <strong>{heading}.</strong> {lede}
      </p>
      <dl className="facts">
        <div>
          <dt>Wrong</dt>
          <dd>{record.what_was_wrong}</dd>
        </div>
        <div>
          <dt>Right</dt>
          <dd>{record.what_is_right}</dd>
        </div>
      </dl>
    </div>
  );
}
