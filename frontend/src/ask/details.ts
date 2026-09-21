/**
 * Reading the full record behind each cited passage, for the views that
 * show one.
 */

import { useEffect, useState } from "react";

import { type Chunk, type Citation, readChunk } from "./api.ts";

/** What is known so far about one passage's full record. */
export type Detail =
  | { state: "loading" }
  | { state: "failed" }
  | { state: "loaded"; chunk: Chunk };

/**
 * Read the full record of every cited passage, once, as the answer appears.
 *
 * Read up front rather than when a passage is opened, because the topics,
 * time sensitivity, and business impact they carry are shown beside every
 * passage whether it is opened or not. A passage cited more than once — by
 * the answer and again as the reason someone is suggested — is read once.
 */
export function useDetails(citations: Citation[]): Map<number, Detail> {
  const [details, setDetails] = useState<Map<number, Detail>>(
    () =>
      new Map(
        citations.map((citation) => [citation.chunk_id, { state: "loading" }]),
      ),
  );
  // The distinct ids, as a string, so the effect runs once per answer
  // rather than once per render of the array that holds them.
  const ids = [...new Set(citations.map((citation) => citation.chunk_id))].join(
    ",",
  );

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
