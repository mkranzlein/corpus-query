import { useEffect, useState } from "react";

import {
  type AnswerBody,
  type Chunk,
  type Citation,
  readChunk,
} from "./api.ts";
import { formatDay, kindLabel, people, term } from "./format.ts";

/** What is known so far about one passage's full record. */
type Detail =
  | { state: "loading" }
  | { state: "failed" }
  | { state: "loaded"; chunk: Chunk };

/**
 * Read the full record of every cited passage, once, as the answer appears.
 *
 * Read up front rather than when a passage is opened, because the topics,
 * time sensitivity, and business impact they carry are shown beside every
 * passage whether it is opened or not.
 */
function useDetails(citations: Citation[]): Map<number, Detail> {
  const [details, setDetails] = useState<Map<number, Detail>>(
    () =>
      new Map(
        citations.map((citation) => [citation.chunk_id, { state: "loading" }]),
      ),
  );
  // The ids, as a string, so the effect runs once per answer rather than
  // once per render of the array that holds them.
  const ids = citations.map((citation) => citation.chunk_id).join(",");

  useEffect(() => {
    const controller = new AbortController();
    const wanted = ids === "" ? [] : ids.split(",").map(Number);
    for (const id of wanted) {
      readChunk(id, controller.signal)
        .then((chunk) =>
          setDetails((current) =>
            new Map(current).set(id, { state: "loaded", chunk }),
          ),
        )
        .catch((error: unknown) => {
          if (!(error instanceof DOMException && error.name === "AbortError")) {
            setDetails((current) =>
              new Map(current).set(id, { state: "failed" }),
            );
          }
        });
    }
    return () => controller.abort();
  }, [ids]);

  return details;
}

interface AnswerProps {
  answer: AnswerBody;
}

/**
 * One finished answer: the prose, then every passage it rests on.
 *
 * Attribution is per passage. The answer is prose and nothing in it marks
 * which sentence came from which passage, so the page does not pretend to
 * know; it lists what the answer was drawn from, each with where it came
 * from and who was behind it.
 */
export default function Answer({ answer }: AnswerProps) {
  const details = useDetails(answer.citations);

  return (
    <div className={answer.abstained ? "answer abstained" : "answer"}>
      {answer.abstained && (
        <p className="outcome">
          <strong>The record does not settle this.</strong> The system searched
          and the passages it found do not answer the question, so it says so
          instead of guessing.
        </p>
      )}
      <p className="prose">{answer.answer}</p>
      {answer.citations.length === 0 ? (
        <p className="quiet">
          {answer.searches === 0
            ? "Answered without searching the record, so no passages are cited."
            : "The search found no passages."}
        </p>
      ) : (
        <section
          className="passages"
          aria-label={
            answer.abstained
              ? "Passages it looked at"
              : "Passages this answer rests on"
          }
        >
          <h3>
            {answer.abstained
              ? "What it looked at"
              : "What this answer rests on"}
          </h3>
          <ol>
            {answer.citations.map((citation) => (
              <Passage
                key={citation.chunk_id}
                citation={citation}
                detail={details.get(citation.chunk_id) ?? { state: "loading" }}
                answerId={answer.answer_id}
              />
            ))}
          </ol>
        </section>
      )}
    </div>
  );
}

interface PassageProps {
  citation: Citation;
  detail: Detail;
  answerId: string;
}

/** One cited passage: where it came from, what was derived, and its text. */
function Passage({ citation, detail, answerId }: PassageProps) {
  const [open, setOpen] = useState(false);
  const who = people(citation);
  const textId = `passage-${answerId}-${citation.chunk_id}`;

  return (
    <li className="passage">
      <p className="source">
        <strong className="title">{citation.title}</strong>
        <span className="kind">{kindLabel(citation.source_kind)}</span>
        <time dateTime={citation.document_date}>
          {formatDay(citation.document_date)}
        </time>
      </p>
      <dl className="facts">
        {who && (
          <div>
            <dt>{who.label}</dt>
            <dd>{who.names}</dd>
          </div>
        )}
        <div>
          <dt>File</dt>
          <dd>
            <code>{citation.document_slug}</code>
          </dd>
        </div>
        <div>
          <dt>Location</dt>
          <dd>{citation.location}</dd>
        </div>
        {detail.state === "loaded" && <Derived chunk={detail.chunk} />}
      </dl>
      {detail.state === "loading" && (
        <p className="quiet">Loading topics and impact…</p>
      )}
      {detail.state === "failed" && (
        <p className="quiet">The passage itself could not be read.</p>
      )}
      {detail.state === "loaded" && (
        <>
          <button
            type="button"
            className="toggle"
            aria-expanded={open}
            aria-controls={textId}
            onClick={() => setOpen(!open)}
          >
            {open ? "Hide the passage" : "Read the passage"}
          </button>
          {open && (
            <blockquote id={textId} className="text">
              <p className="quiet">
                {detail.chunk.title}, {formatDay(detail.chunk.document_date)},{" "}
                {detail.chunk.location}
              </p>
              <p>{detail.chunk.text}</p>
            </blockquote>
          )}
        </>
      )}
    </li>
  );
}

/** The metadata derived for a passage's document, where there is any. */
function Derived({ chunk }: { chunk: Chunk }) {
  return (
    <>
      {chunk.topics.length > 0 && (
        <div>
          <dt>Topics</dt>
          <dd>
            <ul className="topics">
              {chunk.topics.map((topic) => (
                <li key={topic}>{topic}</li>
              ))}
            </ul>
          </dd>
        </div>
      )}
      {chunk.time_sensitivity && (
        <div>
          <dt>Time sensitivity</dt>
          <dd>{term(chunk.time_sensitivity)}</dd>
        </div>
      )}
      {chunk.business_impact && (
        <div>
          <dt>Business impact</dt>
          <dd>{term(chunk.business_impact)}</dd>
        </div>
      )}
    </>
  );
}
