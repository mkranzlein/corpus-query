// @vitest-environment jsdom

import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import Answer from "./Answer.tsx";
import Ask from "./Ask.tsx";
import {
  COUNTER,
  ESCALATION,
  FIX_STANDS,
  RECOVERY_PLAN,
  REMOTE_QUESTION,
  ROLLOUT,
  ROLLOUT_TEXT,
  abstained,
  chunkFor,
  declined,
  routed,
  routedToOne,
  streamed,
  stubApi,
  turn,
} from "./fixtures.ts";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  Reflect.deleteProperty(navigator, "clipboard");
});

/** Give the page a clipboard whose write does what `write` does. */
function clipboard(write: (text: string) => Promise<void>) {
  const writeText = vi.fn(write);
  Object.defineProperty(navigator, "clipboard", {
    value: { writeText },
    configurable: true,
  });
  return writeText;
}

/** Stand in for the API with the records behind every routed passage. */
function stubChunks() {
  return stubApi({
    answers: [],
    chunks: [
      chunkFor(ROLLOUT, { text: ROLLOUT_TEXT }),
      chunkFor(ESCALATION),
      chunkFor(FIX_STANDS),
      chunkFor(RECOVERY_PLAN),
      chunkFor(COUNTER),
    ],
  });
}

/** The people suggested, as list items, in the order shown. */
function candidates(): HTMLElement[] {
  return Array.from(document.querySelectorAll<HTMLElement>("li.candidate"));
}

/** The box holding the drafted question. */
function draft(): HTMLTextAreaElement {
  return screen.getByLabelText(
    "A question you could send them",
  ) as HTMLTextAreaElement;
}

describe("the routing suggestion", () => {
  it("shows who to ask on a routed abstention, with why for each", async () => {
    const fetchMock = stubChunks();
    render(<Answer answer={routed()} />);

    const section = screen.getByRole("region", { name: "Who might know" });
    expect(section).toBeTruthy();
    const [elena, sofia, priya] = candidates();
    expect(candidates()).toHaveLength(3);

    // Who, as the roster has them, best first.
    expect(elena.textContent).toContain("Elena");
    expect(elena.textContent).toContain("Head of Sales, Sales");
    expect(sofia.textContent).toContain("Firmware Engineer, Engineering");
    expect(priya.textContent).toContain("CEO, Executive");

    // Why each one, rather than a bare ranking: how the passages named them.
    expect(within(elena).getByText(/^Named in/).textContent).toBe(
      "Named in 3 of the 4 passages it found: wrote 2 and was in the meeting for 1.",
    );
    expect(within(sofia).getByText(/^Named in/).textContent).toBe(
      "Named in 2 of the 4 passages it found: wrote 1 and was in the meeting for 1.",
    );
    expect(within(priya).getByText(/^Named in/).textContent).toBe(
      "Named in 1 of the 4 passages it found: was in the meeting.",
    );

    // And the passages themselves, cited as an answer's are.
    const cited = Array.from(
      elena.querySelectorAll<HTMLElement>("li.evidence-item"),
    );
    expect(cited).toHaveLength(3);
    expect(cited[0].textContent).toContain("Was in the meeting");
    expect(cited[0].textContent).toContain(
      "Quennick Escalation — Firmware Defect on MX-3 Units",
    );
    expect(cited[0].textContent).toContain("Meeting transcript");
    expect(cited[0].textContent).toContain(
      "Priya, Sofia, Theo, Elena, Callum",
    );
    expect(cited[0].textContent).toContain(
      "quennick-escalation-firmware-defect-on-mx-3-units",
    );
    expect(cited[0].textContent).toContain("turns 24-31");
    expect(cited[0].querySelector("time")?.getAttribute("dateTime")).toBe(
      "2026-04-09",
    );
    expect(cited[1].textContent).toContain("Wrote");
    expect(cited[1].textContent).toContain("Slide deck");
    expect(cited[1].textContent).toContain("slide 5 — Where the Fix Stands");
    expect(cited[2].textContent).toContain(
      "slide 9 — Recovery Plan: Next 30 Days",
    );

    // A passage under a person opens to its words, as an answer's does.
    const open = await within(sofia).findAllByRole("button", {
      name: "Read the passage",
    });
    fireEvent.click(open[0]);
    const quote = within(sofia).getByText(ROLLOUT_TEXT, {
      normalizer: (text) => text,
    });
    expect(quote.closest("blockquote")?.textContent).toContain(
      "Field Rollout",
    );

    // The drafted question is there to edit.
    expect(draft().value).toBe(REMOTE_QUESTION);

    // Nothing is sent anywhere: the only requests are for passages.
    for (const [input] of fetchMock.mock.calls) {
      expect(String(input)).toMatch(/^\/chunks\/\d+$/);
    }
    // A passage cited by the answer and again under a person is read once.
    const reads = fetchMock.mock.calls.map(([input]) => String(input));
    expect(reads.filter((url) => url === "/chunks/118")).toHaveLength(1);
  });

  it("says why when one person is suggested from one passage", () => {
    stubChunks();
    render(<Answer answer={routedToOne()} />);

    expect(candidates()).toHaveLength(1);
    expect(candidates()[0].textContent).toContain(
      "Named in the one passage it found: wrote it.",
    );
    expect(candidates()[0].textContent).toContain(
      "Findings > An Unrelated Counter to Watch",
    );
  });

  it("copies the draft as edited, and says it did", async () => {
    stubChunks();
    const writeText = clipboard(() => Promise.resolve());
    render(<Answer answer={routed()} />);

    const edited =
      "Elena, do you know when the two remote Quennick units are due to be " +
      "power cycled and updated to 2.4.2?";
    fireEvent.change(draft(), { target: { value: edited } });
    expect(draft().value).toBe(edited);
    fireEvent.click(screen.getByRole("button", { name: "Copy the question" }));

    await waitFor(() =>
      expect(screen.getByRole("status").textContent).toBe(
        "Copied to the clipboard.",
      ),
    );
    expect(writeText).toHaveBeenCalledExactlyOnceWith(edited);
    expect(screen.queryByRole("alert")).toBeNull();

    // Editing again means the clipboard no longer holds what the box does.
    fireEvent.change(draft(), { target: { value: `${edited} Thanks.` } });
    expect(screen.getByRole("status").textContent).toBe("");
  });

  it("says so when the clipboard refuses, and selects the draft", async () => {
    stubChunks();
    clipboard(() => Promise.reject(new DOMException("denied", "NotAllowedError")));
    render(<Answer answer={routed()} />);

    fireEvent.click(screen.getByRole("button", { name: "Copy the question" }));

    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain(
      "The question could not be copied to the clipboard.",
    );
    expect(screen.getByRole("status").textContent).toBe("");
    expect(document.activeElement).toBe(draft());
    expect(draft().selectionStart).toBe(0);
    expect(draft().selectionEnd).toBe(REMOTE_QUESTION.length);
  });

  it("says so when there is no clipboard to copy to", async () => {
    stubChunks();
    render(<Answer answer={routed()} />);

    await act(async () => {
      fireEvent.click(
        screen.getByRole("button", { name: "Copy the question" }),
      );
    });

    expect(screen.getByRole("alert").textContent).toContain(
      "could not be copied",
    );
  });

  it("will not copy an empty draft", () => {
    stubChunks();
    render(<Answer answer={routed()} />);

    fireEvent.change(draft(), { target: { value: "   " } });

    expect(
      screen.getByRole("button", { name: "Copy the question" }),
    ).toHaveProperty("disabled", true);
  });

  it("offers no routing on an abstention that named nobody", () => {
    stubChunks();
    render(<Answer answer={abstained()} />);

    expect(screen.getByText("The record does not settle this.")).toBeTruthy();
    expect(screen.queryByRole("region", { name: "Who might know" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Copy the question" })).toBeNull();
  });

  it("offers no routing on a suggestion with nobody in it", () => {
    stubChunks();
    render(
      <Answer
        answer={abstained({
          routing: { candidates: [], question: REMOTE_QUESTION },
        })}
      />,
    );

    expect(screen.queryByRole("region", { name: "Who might know" })).toBeNull();
  });

  it("reads an out-of-scope question as a decline, with no routing", async () => {
    stubApi({ answers: [() => streamed(turn(declined()))] });
    render(<Ask />);

    fireEvent.change(screen.getByLabelText("Your question"), {
      target: { value: "What's a good recipe for banana bread?" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Ask" }));

    await screen.findByText(
      "I answer from this organization's record, and that is outside it.",
    );
    expect(screen.queryByText("The record does not settle this.")).toBeNull();
    expect(screen.queryByRole("region", { name: "Who might know" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Copy the question" })).toBeNull();
    expect(
      screen.getByText(
        "Answered without searching the record, so no passages are cited.",
      ),
    ).toBeTruthy();
  });

  it("appears under a routed abstention on the question page", async () => {
    stubApi({
      answers: [() => streamed(turn(routed()))],
      chunks: [chunkFor(ROLLOUT), chunkFor(ESCALATION)],
    });
    render(<Ask />);

    fireEvent.change(screen.getByLabelText("Your question"), {
      target: { value: "When will the two remote Quennick units get 2.4.2?" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Ask" }));

    await screen.findByRole("region", { name: "Who might know" });
    expect(candidates()).toHaveLength(3);
    // The suggestion sits between the answer and what it looked at.
    const answer = document.querySelector(".answer") as HTMLElement;
    const order = Array.from(answer.children).map((child) => child.className);
    expect(order.indexOf("suggestion")).toBeGreaterThan(order.indexOf("prose"));
    expect(order.indexOf("suggestion")).toBeLessThan(order.indexOf("passages"));
    // The follow-up box is still its own, apart from the draft.
    expect(screen.getByLabelText("Ask a follow-up")).not.toBe(draft());
  });
});
