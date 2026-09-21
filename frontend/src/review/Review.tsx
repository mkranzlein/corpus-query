import { useCallback, useEffect, useState } from "react";

import {
  KINDS,
  LABELS,
  QUEUE_LIMIT,
  type Kind,
  type QueueItem,
  itemKey,
  loadQueue,
  narrowed,
  openRecord,
  setReviewed,
  whatTheSystemDid,
  whatWasSaid,
} from "./queue.ts";
import "./review.css";

type Filter = Kind | "all";

type Load =
  | { state: "loading" }
  | { state: "failed" }
  | { state: "loaded"; items: QueueItem[]; truncated: boolean };

const when = new Intl.DateTimeFormat(undefined, {
  dateStyle: "medium",
  timeStyle: "short",
});

/** Format an ISO 8601 timestamp for a reader, in their own time zone. */
function formatted(timestamp: string): string {
  const date = new Date(timestamp);
  return Number.isNaN(date.getTime()) ? timestamp : when.format(date);
}

/**
 * The review queue: every gap, correction, and piece of feedback, newest
 * first, for someone reading them to look for patterns.
 *
 * It lives at `/review` and nothing on the question-and-answer page links
 * to it. Its one write is marking an item reviewed, or clearing that mark;
 * everything else about a record is read only here.
 */
export default function Review() {
  const [load, setLoad] = useState<Load>({ state: "loading" });
  const [filter, setFilter] = useState<Filter>("all");
  const [opened, setOpened] = useState<string | null>(null);

  useEffect(() => {
    document.title = "Review queue · corpus-query";
    const controller = new AbortController();
    loadQueue(controller.signal)
      .then(({ items, truncated }) =>
        setLoad({ state: "loaded", items, truncated }),
      )
      .catch((error: unknown) => {
        if (!(error instanceof DOMException && error.name === "AbortError")) {
          setLoad({ state: "failed" });
        }
      });
    return () => controller.abort();
  }, []);

  // Stable across renders, because an opened record re-reads itself whenever
  // this changes, and a new function every render would re-read it forever.
  const replace = useCallback((updated: QueueItem) => {
    setLoad((current) =>
      current.state === "loaded"
        ? {
            ...current,
            items: current.items.map((item) =>
              itemKey(item) === itemKey(updated) ? updated : item,
            ),
          }
        : current,
    );
  }, []);

  return (
    <main className="review">
      <h1>Review queue</h1>
      <p>
        What the system could not answer, what people said it got wrong, and
        what they thought of its answers, newest first.
      </p>
      {load.state === "loading" && <p role="status">Loading…</p>}
      {load.state === "failed" && (
        <p role="alert">The queue could not be loaded. Is the API running?</p>
      )}
      {load.state === "loaded" && (
        <Queue
          items={load.items}
          truncated={load.truncated}
          filter={filter}
          onFilter={(next) => {
            setFilter(next);
            setOpened(null);
          }}
          opened={opened}
          onToggle={(key) => setOpened(opened === key ? null : key)}
          onUpdate={replace}
        />
      )}
    </main>
  );
}

interface QueueProps {
  items: QueueItem[];
  truncated: boolean;
  filter: Filter;
  onFilter: (filter: Filter) => void;
  opened: string | null;
  onToggle: (key: string) => void;
  onUpdate: (item: QueueItem) => void;
}

/** The filters and the list, once the queue has loaded. */
function Queue({
  items,
  truncated,
  filter,
  onFilter,
  opened,
  onToggle,
  onUpdate,
}: QueueProps) {
  const shown = narrowed(items, filter);
  const unseen = (subset: QueueItem[]) =>
    subset.filter((item) => item.reviewed_at === null).length;

  return (
    <>
      <nav aria-label="Narrow the queue" className="filters">
        {(["all", ...KINDS] as Filter[]).map((option) => {
          const subset = narrowed(items, option);
          const label = option === "all" ? "Everything" : LABELS[option].many;
          return (
            <button
              key={option}
              type="button"
              aria-pressed={filter === option}
              onClick={() => onFilter(option)}
            >
              {label} <span className="count">{subset.length}</span>
              {unseen(subset) > 0 && (
                <span className="unseen">{unseen(subset)} new</span>
              )}
            </button>
          );
        })}
      </nav>
      {truncated && (
        <p className="note">
          Showing the most recent {QUEUE_LIMIT} of each kind. Older items are
          still recorded.
        </p>
      )}
      {shown.length === 0 ? (
        <p role="status" className="empty">
          {filter === "all"
            ? "The queue is empty. Gaps, corrections, and feedback appear here as people use the system."
            : `No ${LABELS[filter].many.toLowerCase()} recorded yet.`}
        </p>
      ) : (
        <ol className="queue">
          {shown.map((item) => (
            <Row
              key={itemKey(item)}
              item={item}
              open={opened === itemKey(item)}
              onToggle={() => onToggle(itemKey(item))}
              onUpdate={onUpdate}
            />
          ))}
        </ol>
      )}
    </>
  );
}

interface RowProps {
  item: QueueItem;
  open: boolean;
  onToggle: () => void;
  onUpdate: (item: QueueItem) => void;
}

/** One item: a summary that opens to the full record, and the review mark. */
function Row({ item, open, onToggle, onUpdate }: RowProps) {
  const [saving, setSaving] = useState(false);
  const [saveFailed, setSaveFailed] = useState(false);
  const reviewed = item.reviewed_at !== null;
  const said = whatWasSaid(item);
  const detailId = `record-${item.kind}-${item.id}`;

  function toggleReviewed() {
    setSaving(true);
    setSaveFailed(false);
    setReviewed(item.kind, item.id, !reviewed)
      .then(onUpdate)
      .catch(() => setSaveFailed(true))
      .finally(() => setSaving(false));
  }

  return (
    <li className={reviewed ? "item reviewed" : "item new"}>
      <div className="summary">
        <button
          type="button"
          className="open"
          aria-expanded={open}
          aria-controls={detailId}
          onClick={onToggle}
        >
          <span className="meta">
            <span className={`kind kind-${item.kind}`}>
              {LABELS[item.kind].one}
            </span>
            <time dateTime={item.created_at}>
              {formatted(item.created_at)}
            </time>
            {!reviewed && <span className="badge">New</span>}
          </span>
          <span className="question">{item.question}</span>
          <span className="did">{whatTheSystemDid(item)}</span>
          {said && <span className="said">{said}</span>}
        </button>
        <button
          type="button"
          className="mark"
          onClick={toggleReviewed}
          disabled={saving}
        >
          {reviewed ? "Mark as new" : "Mark reviewed"}
        </button>
      </div>
      {saveFailed && (
        <p role="alert" className="note">
          That did not save. Try again.
        </p>
      )}
      {open && <Detail id={detailId} item={item} onUpdate={onUpdate} />}
    </li>
  );
}

interface DetailProps {
  id: string;
  item: QueueItem;
  onUpdate: (item: QueueItem) => void;
}

/**
 * The full record. The copy from the list is shown at once and the record is
 * read again as it opens, so what is on screen is what is stored now.
 */
function Detail({ id, item, onUpdate }: DetailProps) {
  const { kind, id: recordId } = item;

  useEffect(() => {
    const controller = new AbortController();
    openRecord(kind, recordId, controller.signal)
      .then(onUpdate)
      .catch(() => {
        // The list's copy is already on screen; a failed refresh leaves it.
      });
    return () => controller.abort();
  }, [kind, recordId, onUpdate]);

  return (
    <div id={id} className="detail">
      <dl>
        <dt>Question</dt>
        <dd>{item.question}</dd>

        <dt>{item.abstained ? "What the system said" : "Answer"}</dt>
        <dd className="answer">{item.answer}</dd>

        <dt>Citations</dt>
        <dd>
          {item.citations.length === 0 ? (
            "None."
          ) : (
            <ol className="citations">
              {item.citations.map((citation) => (
                <li key={citation.chunk_id}>
                  <strong>{citation.title}</strong>, {citation.location}{" "}
                  <span className="quiet">
                    ({citation.document_date}, {citation.document_slug})
                  </span>
                </li>
              ))}
            </ol>
          )}
        </dd>

        {item.kind === "gaps" && (
          <>
            <dt>Suggested asking</dt>
            <dd>
              {item.routing === null || item.routing.candidates.length === 0 ? (
                "Nobody. The passages named no one on the roster."
              ) : (
                <ul>
                  {item.routing.candidates.map((candidate) => (
                    <li key={candidate.name}>
                      <strong>{candidate.name}</strong>, {candidate.role},{" "}
                      {candidate.department}{" "}
                      <span className="quiet">
                        ({candidate.passages}{" "}
                        {candidate.passages === 1 ? "passage" : "passages"})
                      </span>
                    </li>
                  ))}
                </ul>
              )}
            </dd>
          </>
        )}

        {item.kind === "corrections" && (
          <>
            <dt>What was wrong</dt>
            <dd>{item.what_was_wrong}</dd>
            <dt>What is right</dt>
            <dd>{item.what_is_right}</dd>
          </>
        )}

        {item.kind === "feedback" && (
          <>
            <dt>Verdict</dt>
            <dd>{item.verdict === "up" ? "Thumbs up" : "Thumbs down"}</dd>
            <dt>Note</dt>
            <dd>{item.note ?? "None."}</dd>
          </>
        )}

        <dt>Recorded</dt>
        <dd>
          <time dateTime={item.created_at}>{formatted(item.created_at)}</time>
        </dd>

        <dt>Reviewed</dt>
        <dd>
          {item.reviewed_at === null ? (
            "Not yet."
          ) : (
            <time dateTime={item.reviewed_at}>
              {formatted(item.reviewed_at)}
            </time>
          )}
        </dd>

        <dt>Conversation</dt>
        <dd className="quiet">
          <code>{item.thread_id}</code>
        </dd>
      </dl>
    </div>
  );
}
