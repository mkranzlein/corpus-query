import {
  type FormEvent,
  type KeyboardEvent,
  useEffect,
  useRef,
  useState,
} from "react";

import Answer from "./Answer.tsx";
import {
  type AnswerBody,
  AskError,
  type CorrectionRecord,
  type Progress,
  ask,
} from "./api.ts";
import { lines } from "./progress.ts";
import "./ask.css";

/** One question and what became of it. */
interface Turn {
  id: number;
  question: string;
  steps: Progress[];
  outcome:
    | { state: "asking" }
    | { state: "answered"; answer: AnswerBody }
    | { state: "failed"; detail: string };
}

/**
 * The question page: a conversation of questions, each followed by the
 * steps taken to answer it and then the answer with the passages it rests on.
 *
 * Every question after the first is asked on the same thread, so a
 * follow-up is answered against what was already said. Starting over drops
 * the thread and begins a new one.
 */
export default function Ask() {
  const [turns, setTurns] = useState<Turn[]>([]);
  const [draft, setDraft] = useState("");
  const [threadId, setThreadId] = useState<string | null>(null);
  const controller = useRef<AbortController | null>(null);
  const nextId = useRef(1);

  // A question still running when the page goes away is stopped, which
  // stops the run on the server too.
  useEffect(() => () => controller.current?.abort(), []);

  const asking = turns.some((turn) => turn.outcome.state === "asking");
  const corrections = corrected(turns);

  function update(id: number, change: (turn: Turn) => Turn) {
    setTurns((current) =>
      current.map((turn) => (turn.id === id ? change(turn) : turn)),
    );
  }

  function submit(event?: FormEvent) {
    event?.preventDefault();
    const question = draft.trim();
    if (!question || asking) {
      return;
    }
    const id = nextId.current++;
    const running = new AbortController();
    controller.current = running;
    setDraft("");
    setTurns((current) => [
      ...current,
      { id, question, steps: [], outcome: { state: "asking" } },
    ]);

    ask(
      question,
      threadId,
      (step) => {
        // The thread is known before anything has run. Holding on to it
        // then, rather than when the answer arrives, is what lets a
        // follow-up after a failure continue the same conversation.
        if (step.event === "started") {
          setThreadId(step.data.thread_id);
        }
        update(id, (turn) => ({ ...turn, steps: [...turn.steps, step] }));
      },
      running.signal,
    )
      .then((answer) => {
        setThreadId(answer.thread_id);
        update(id, (turn) => ({
          ...turn,
          outcome: { state: "answered", answer },
        }));
      })
      .catch((error: unknown) => {
        if (error instanceof DOMException && error.name === "AbortError") {
          return;
        }
        const detail =
          error instanceof AskError
            ? error.message
            : "Something went wrong reading the answer.";
        update(id, (turn) => ({
          ...turn,
          outcome: { state: "failed", detail },
        }));
      });
  }

  function startOver() {
    controller.current?.abort();
    controller.current = null;
    setTurns([]);
    setThreadId(null);
  }

  function onKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    // Enter asks; Shift+Enter is a new line, as in most chat boxes.
    if (
      event.key === "Enter" &&
      !event.shiftKey &&
      !event.nativeEvent.isComposing
    ) {
      submit();
      event.preventDefault();
    }
  }

  return (
    <main className="ask">
      <header>
        <h1>corpus-query</h1>
        <p className="lede">
          Ask a question about the organization's meetings, documents, decks,
          and spreadsheets. Every answer lists the passages it rests on, and
          says so plainly when the record does not settle the question.
        </p>
      </header>

      {turns.length > 0 && (
        <ol className="turns" aria-label="Conversation">
          {turns.map((turn) => (
            <TurnView key={turn.id} turn={turn} corrections={corrections} />
          ))}
        </ol>
      )}

      <form className="question" onSubmit={submit}>
        <label htmlFor="question">
          {turns.length === 0 ? "Your question" : "Ask a follow-up"}
        </label>
        <textarea
          id="question"
          rows={3}
          value={draft}
          placeholder={
            turns.length === 0
              ? "What did we decide about the connector lead time?"
              : undefined
          }
          onChange={(event) => setDraft(event.target.value)}
          onKeyDown={onKeyDown}
        />
        <div className="actions">
          <button
            type="submit"
            className="primary"
            disabled={asking || !draft.trim()}
          >
            {asking ? "Answering…" : "Ask"}
          </button>
          {turns.length > 0 && (
            <button type="button" onClick={startOver}>
              Start a new conversation
            </button>
          )}
        </div>
      </form>
    </main>
  );
}

/**
 * Every correction the conversation recorded, by the answer it corrects.
 *
 * A correction typed as a message is recorded by the agent against an
 * earlier answer, and comes back on the turn that typed it rather than on
 * the answer it is about. Gathering them here is what lets that earlier
 * answer show it as recorded instead of offering to record it again.
 */
function corrected(turns: Turn[]): Map<string, CorrectionRecord> {
  const found = new Map<string, CorrectionRecord>();
  for (const turn of turns) {
    if (turn.outcome.state === "answered" && turn.outcome.answer.correction) {
      const correction = turn.outcome.answer.correction;
      found.set(correction.answer_id, correction);
    }
  }
  return found;
}

interface TurnViewProps {
  turn: Turn;
  /** Corrections the conversation recorded, by the answer they correct. */
  corrections: Map<string, CorrectionRecord>;
}

/** One turn: the question, how it was answered, and the answer or failure. */
function TurnView({ turn, corrections }: TurnViewProps) {
  const said = lines(turn.steps);
  const { outcome } = turn;

  return (
    <li className="turn">
      <p className="asked">
        <span className="visually-hidden">You asked: </span>
        {turn.question}
      </p>

      {outcome.state === "asking" && (
        <div className="steps live" role="status" aria-live="polite">
          <p className="visually-hidden">Working on an answer.</p>
          <ol>
            {(said.length > 0 ? said : ["Sending the question"]).map(
              (line, index, all) => (
                <li
                  key={index}
                  className={index === all.length - 1 ? "current" : "done"}
                >
                  {line}
                </li>
              ),
            )}
          </ol>
        </div>
      )}

      {outcome.state === "answered" && (
        <Answer
          answer={outcome.answer}
          corrected={corrections.get(outcome.answer.answer_id) ?? null}
        />
      )}

      {outcome.state === "failed" && (
        <div className="failure" role="alert">
          <p>
            <strong>This question could not be answered.</strong> The
            conversation is kept, so you can ask again.
          </p>
          <p className="detail">{outcome.detail}</p>
        </div>
      )}

      {outcome.state !== "asking" && said.length > 0 && (
        <details className="steps">
          <summary>How this was answered ({said.length} steps)</summary>
          <ol>
            {said.map((line, index) => (
              <li key={index}>{line}</li>
            ))}
          </ol>
        </details>
      )}
    </li>
  );
}
