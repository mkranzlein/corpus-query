import { useState } from "react";

import type { Chunk, Citation } from "./api.ts";
import type { Detail } from "./details.ts";
import { formatDay, kindLabel, people, term } from "./format.ts";

interface PassageProps {
  citation: Citation;
  detail: Detail;
  /** Scopes the ids this renders, so two answers citing one passage differ. */
  scope: string;
}

/** One cited passage: where it came from, what was derived, and its text. */
export function Passage({ citation, detail, scope }: PassageProps) {
  const who = people(citation);

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
      <PassageText
        detail={detail}
        textId={`passage-${scope}-${citation.chunk_id}`}
      />
    </li>
  );
}

interface PassageTextProps {
  detail: Detail;
  /** The id the opened text is given, for the toggle to point at. */
  textId: string;
}

/**
 * The words of a cited passage, folded away until asked for, with where they
 * came from repeated above them so an opened passage stands on its own.
 */
export function PassageText({ detail, textId }: PassageTextProps) {
  const [open, setOpen] = useState(false);

  if (detail.state === "failed") {
    return <p className="quiet">The passage itself could not be read.</p>;
  }
  if (detail.state === "loading") {
    return null;
  }
  return (
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
