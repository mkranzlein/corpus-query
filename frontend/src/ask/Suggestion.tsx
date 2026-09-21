import { useRef, useState } from "react";

import type { Citation, Routing, RoutingCandidate } from "./api.ts";
import { formatDay, kindLabel, people } from "./format.ts";
import type { Detail } from "./details.ts";
import { PassageText } from "./Passage.tsx";

interface SuggestionProps {
  routing: Routing;
  /** What is known of each passage's full record, by chunk id. */
  details: Map<number, Detail>;
  /** How many passages the search found, which each count is out of. */
  found: number;
  /** Scopes the ids this renders to one answer. */
  scope: string;
}

/**
 * Who might know what the record did not say, and a question to put to them.
 *
 * Each person is shown with the passages that named them, cited the way an
 * answer's passages are, because a suggestion is only as good as what it
 * came from and the user is the one who judges that. The count is kept
 * beside the passages rather than replacing them: it is what the ranking is
 * by, and the passages are why.
 *
 * Nothing is sent from here. The question is text to edit and copy, and the
 * user sends it however they already reach that person.
 */
export default function Suggestion({
  routing,
  details,
  found,
  scope,
}: SuggestionProps) {
  const heading = `suggestion-${scope}`;

  return (
    <section className="suggestion" aria-labelledby={heading}>
      <h3 id={heading}>Who might know</h3>
      <p className="quiet">
        Suggested from who wrote the passages it found, or was in the meetings
        they came from. Each person is listed with the passages that named
        them.
      </p>
      <ol className="candidates">
        {routing.candidates.map((candidate) => (
          <Candidate
            key={candidate.name}
            candidate={candidate}
            details={details}
            found={found}
            scope={scope}
          />
        ))}
      </ol>
      <Draft question={routing.question} scope={scope} />
    </section>
  );
}

interface CandidateProps {
  candidate: RoutingCandidate;
  details: Map<number, Detail>;
  found: number;
  scope: string;
}

/** One person worth asking, and every passage that named them. */
function Candidate({ candidate, details, found, scope }: CandidateProps) {
  return (
    <li className="candidate">
      <p className="who">
        <strong>{candidate.name}</strong>
        <span className="role">
          {candidate.role}, {candidate.department}
        </span>
      </p>
      <p className="why">{why(candidate, found)}</p>
      <ol className="evidence">
        {candidate.evidence.map((citation) => (
          <Evidence
            key={citation.chunk_id}
            citation={citation}
            detail={details.get(citation.chunk_id) ?? { state: "loading" }}
            textId={`evidence-${scope}-${candidate.name}-${citation.chunk_id}`}
          />
        ))}
      </ol>
    </li>
  );
}

/**
 * Whether a passage named its person as the one who wrote it.
 *
 * The service names a passage's author when it has one and everyone in the
 * room when it does not, so a passage with an author named this person as
 * its author, and one without named them as an attendee.
 */
function wrote(citation: Citation): boolean {
  return Boolean(citation.author?.trim());
}

/**
 * Say why one person is suggested, in terms of the passages that named them.
 *
 * @param candidate The person and their passages.
 * @param found How many passages the search found in all.
 */
function why(candidate: RoutingCandidate, found: number): string {
  const named = candidate.evidence.length;
  const total = Math.max(found, named);
  const authored = candidate.evidence.filter(wrote).length;
  const attended = named - authored;

  const share =
    total === 1
      ? "Named in the one passage it found"
      : named === total
        ? `Named in all ${total} passages it found`
        : `Named in ${named} of the ${total} passages it found`;

  let part: string;
  if (attended === 0) {
    part = named === 1 ? "wrote it" : "wrote each of them";
  } else if (authored === 0) {
    part = named === 1 ? "was in the meeting" : "was in each of those meetings";
  } else {
    part = `wrote ${authored} and was in the meeting for ${attended}`;
  }
  return `${share}: ${part}.`;
}

interface EvidenceProps {
  citation: Citation;
  detail: Detail;
  textId: string;
}

/** One passage that named a person, cited as an answer's passage is. */
function Evidence({ citation, detail, textId }: EvidenceProps) {
  const who = people(citation);

  return (
    <li className="passage evidence-item">
      <p className="source">
        <span className="relation">
          {wrote(citation) ? "Wrote" : "Was in the meeting"}
        </span>
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
      </dl>
      <PassageText detail={detail} textId={textId} />
    </li>
  );
}

/** How the last attempt to copy the draft went. */
type Copy = "idle" | "copied" | "failed";

interface DraftProps {
  question: string;
  scope: string;
}

/**
 * The drafted question, editable in place, and a control that copies it.
 *
 * A copy says whether it worked. The clipboard can refuse — outside a secure
 * context there is no clipboard API at all, and a browser may deny the
 * permission — and a button that appears to work but leaves the clipboard
 * empty is worse than no button, because the user finds out only after
 * pasting. On a refusal the text is selected, so copying it by hand is one
 * keystroke. Editing after a copy clears the confirmation, since what is on
 * the clipboard is then no longer what is in the box.
 */
function Draft({ question, scope }: DraftProps) {
  const [text, setText] = useState(question);
  const [copy, setCopy] = useState<Copy>("idle");
  const box = useRef<HTMLTextAreaElement>(null);
  const id = `draft-${scope}`;

  async function copyDraft() {
    try {
      // Absent outside a secure context, whatever the type says.
      if (!(navigator.clipboard as Clipboard | undefined)) {
        throw new Error("No clipboard is available here.");
      }
      await navigator.clipboard.writeText(text);
      setCopy("copied");
    } catch {
      setCopy("failed");
      box.current?.focus();
      box.current?.select();
    }
  }

  return (
    <div className="draft">
      <label htmlFor={id}>A question you could send them</label>
      <p className="quiet" id={`${id}-hint`}>
        Edit it as you like. Nothing is sent from here: copy it and send it
        however you usually reach them.
      </p>
      <textarea
        id={id}
        ref={box}
        rows={4}
        value={text}
        aria-describedby={`${id}-hint`}
        onChange={(event) => {
          setText(event.target.value);
          setCopy("idle");
        }}
      />
      <div className="actions">
        <button
          type="button"
          onClick={() => void copyDraft()}
          disabled={!text.trim()}
        >
          Copy the question
        </button>
        <p className="copied" role="status">
          {copy === "copied" ? "Copied to the clipboard." : ""}
        </p>
      </div>
      {copy === "failed" && (
        <p className="copy-failed" role="alert">
          The question could not be copied to the clipboard. It is selected
          in the box above, so you can copy it yourself.
        </p>
      )}
    </div>
  );
}
