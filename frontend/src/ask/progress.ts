/**
 * What each streamed step says to a reader while an answer is produced.
 *
 * A local model can take tens of seconds, and a page that shows a spinner
 * for that long reads as broken. Each step the service reports becomes one
 * line saying what is happening, in words, with what it searched for and
 * how much came back.
 */

import type { Progress } from "./api.ts";

/**
 * Say what one step means, given the steps before it in the same turn.
 *
 * @returns A line for the reader, or null for a step not worth a line.
 */
export function describe(step: Progress, before: Progress[]): string | null {
  switch (step.event) {
    case "started":
      return "Question received";
    case "drafting": {
      const drafted = before.some((earlier) => earlier.event === "drafting");
      const redrafting = before.some(
        (earlier) => earlier.event === "verified" && earlier.data.redraft,
      );
      if (redrafting) {
        return "Drafting the answer again";
      }
      return drafted
        ? "Drafting an answer from what was found"
        : "Drafting an answer";
    }
    case "searching":
      return `Searching the record for “${step.data.query}”`;
    case "searched": {
      const found = step.data.citations.length;
      return found === 0
        ? `Nothing came back for “${step.data.query}”`
        : `Found ${found} ${found === 1 ? "passage" : "passages"} for “${step.data.query}”`;
    }
    case "verifying":
      return "Checking each claim against the passages";
    case "verified":
      if (step.data.redraft) {
        return "A claim was not supported by the passages, so it goes back for a redraft";
      }
      return step.data.verification === null
        ? "Every claim is supported by a passage"
        : "Finished checking the claims";
    case "routing":
      return "Judging whether the answer settles the question";
    case "correcting":
      return "Recording your correction";
    default:
      // A step this page does not know yet is still progress, but there is
      // nothing useful to say about it.
      return null;
  }
}

/** Every step of a turn so far, as lines, in order. */
export function lines(steps: Progress[]): string[] {
  return steps.flatMap((step, index) => {
    const line = describe(step, steps.slice(0, index));
    return line === null ? [] : [line];
  });
}
