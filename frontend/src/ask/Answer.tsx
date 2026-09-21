import type { AnswerBody } from "./api.ts";
import { useDetails } from "./details.ts";
import { Passage } from "./Passage.tsx";
import Suggestion from "./Suggestion.tsx";

interface AnswerProps {
  answer: AnswerBody;
}

/**
 * One finished answer: the prose, who to ask if it did not settle the
 * question, then every passage it rests on.
 *
 * Attribution is per passage. The answer is prose and nothing in it marks
 * which sentence came from which passage, so the page does not pretend to
 * know; it lists what the answer was drawn from, each with where it came
 * from and who was behind it.
 */
export default function Answer({ answer }: AnswerProps) {
  const candidates = answer.routing?.candidates ?? [];
  // A suggestion's evidence is drawn from the passages the answer cites, but
  // nothing guarantees it, so every passage either one names is read.
  const details = useDetails([
    ...answer.citations,
    ...candidates.flatMap((candidate) => candidate.evidence),
  ]);

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
      {answer.routing && candidates.length > 0 && (
        <Suggestion
          routing={answer.routing}
          details={details}
          found={answer.citations.length}
          scope={answer.answer_id}
        />
      )}
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
                scope={answer.answer_id}
              />
            ))}
          </ol>
        </section>
      )}
    </div>
  );
}
