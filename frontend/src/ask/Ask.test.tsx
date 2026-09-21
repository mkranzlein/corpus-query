// @vitest-environment jsdom

import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import Ask from "./Ask.tsx";
import {
  AUTHORED,
  CITATION,
  abstained,
  answered,
  chunkFor,
  heldStream,
  json,
  sse,
  streamed,
  stubApi,
  turn,
} from "./fixtures.ts";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

/** Type a question into the box and ask it. */
function askQuestion(question: string) {
  fireEvent.change(screen.getByRole("textbox"), {
    target: { value: question },
  });
  fireEvent.click(screen.getByRole("button", { name: "Ask" }));
}

/** The body of every question sent to `/answer`, in order. */
function asked(
  fetchMock: ReturnType<typeof stubApi>,
): Record<string, unknown>[] {
  return (fetchMock.mock.calls as unknown as [string, RequestInit][])
    .filter(([url]) => url === "/answer")
    .map(
      ([, init]) => JSON.parse(String(init.body)) as Record<string, unknown>,
    );
}

/** The passages listed under one answer, as list items. */
function passages(): HTMLElement[] {
  return Array.from(document.querySelectorAll<HTMLElement>("li.passage"));
}

describe("the question page", () => {
  it("shows each step as it streams in, then the answer", async () => {
    const held = heldStream();
    stubApi({
      answers: [() => held.response],
      chunks: [chunkFor(CITATION), chunkFor(AUTHORED)],
    });
    render(<Ask />);

    askQuestion("What did we decide about the XT-9 rev B thermal drift?");
    held.send(sse("started", { thread_id: "thread-1" }));
    held.send(sse("drafting", {}));
    held.send(sse("searching", { query: "XT-9 thermal drift" }));

    const status = await screen.findByRole("status");
    await waitFor(() =>
      expect(status.textContent).toContain(
        "Searching the record for “XT-9 thermal drift”",
      ),
    );
    expect(screen.getByRole("button", { name: "Answering…" })).toHaveProperty(
      "disabled",
      true,
    );

    for (const event of turn(answered()).slice(3)) {
      held.send(event);
    }
    held.close();

    await screen.findByText(
      "The team settled on a firmware workaround, per Marcus.",
    );
    expect(screen.queryByRole("status")).toBeNull();
    // The steps stay on the page afterwards, folded away.
    expect(screen.getByText(/How this was answered/).textContent).toContain(
      "8 steps",
    );
  });

  it("renders an answer with every passage it rests on", async () => {
    stubApi({
      answers: [() => streamed(turn(answered()))],
      chunks: [
        chunkFor(CITATION),
        chunkFor(AUTHORED, { topics: ["Qualification"] }),
      ],
    });
    render(<Ask />);

    askQuestion("What did we decide about the XT-9 rev B thermal drift?");

    await screen.findByText(
      "The team settled on a firmware workaround, per Marcus.",
    );
    const section = screen.getByRole("region", {
      name: "Passages this answer rests on",
    });
    expect(within(section).getByText("What this answer rests on")).toBeTruthy();
    expect(passages()).toHaveLength(2);
    const [meeting, report] = passages();

    // Where each passage came from, and who was behind it.
    expect(meeting.textContent).toContain("XT-9 Rev B Thermal Drift");
    expect(meeting.textContent).toContain("Meeting transcript");
    expect(meeting.textContent).toContain("Attendees");
    expect(meeting.textContent).toContain("Marcus, Sofia, Devon");
    expect(meeting.textContent).toContain("xt-9-rev-b-thermal-drift");
    expect(meeting.textContent).toContain("turns 4-13");
    expect(meeting.querySelector("time")?.getAttribute("dateTime")).toBe(
      "2026-03-05",
    );
    expect(report.textContent).toContain("Document");
    expect(report.textContent).toContain("Author");
    expect(report.textContent).toContain("Sofia");
    expect(report.textContent).toContain(
      "Recommendation > Rev C Replacement Threshold",
    );

    // What was derived about each, read from the passage's own record.
    await waitFor(() => expect(meeting.textContent).toContain("Near term"));
    expect(meeting.textContent).toContain("Firmware");
    expect(meeting.textContent).toContain("Thermal");
    expect(meeting.textContent).toContain("Significant");
    await waitFor(() => expect(report.textContent).toContain("Qualification"));
  });

  it("opens a citation to the passage it refers to", async () => {
    stubApi({
      answers: [() => streamed(turn(answered({ citations: [CITATION] })))],
      chunks: [chunkFor(CITATION)],
    });
    render(<Ask />);
    askQuestion("What did we decide about the drift?");

    const open = await screen.findByRole("button", {
      name: "Read the passage",
    });
    expect(
      screen.queryByText("The passage behind XT-9 Rev B Thermal Drift."),
    ).toBeNull();
    fireEvent.click(open);

    const text = screen.getByText(
      "The passage behind XT-9 Rev B Thermal Drift.",
    );
    const quote = text.closest("blockquote") as HTMLElement;
    expect(quote.textContent).toContain("XT-9 Rev B Thermal Drift");
    expect(quote.textContent).toContain("turns 4-13");
    expect(quote.textContent).toMatch(/2026/);
    expect(
      screen.getByRole("button", { name: "Hide the passage" }),
    ).toHaveProperty("ariaExpanded", "true");
  });

  it("says so when a passage's record cannot be read", async () => {
    stubApi({
      answers: [() => streamed(turn(answered({ citations: [CITATION] })))],
      chunks: [],
    });
    render(<Ask />);
    askQuestion("What did we decide about the drift?");

    await screen.findByText("The passage itself could not be read.");
    // The citation is still there; only what it opens to is missing.
    expect(passages()[0].textContent).toContain("XT-9 Rev B Thermal Drift");
  });

  it("presents an abstention as an answer, not a failure", async () => {
    stubApi({
      answers: [() => streamed(turn(abstained()))],
      chunks: [chunkFor(AUTHORED)],
    });
    render(<Ask />);

    askQuestion("Which rev B units run hot?");

    await screen.findByText("The record does not settle this.");
    expect(
      screen.getByText(
        "The record does not say which Rev B units are installed hot.",
      ),
    ).toBeTruthy();
    expect(screen.queryByRole("alert")).toBeNull();
    // What it searched is still shown, as what it looked at rather than
    // what an answer rests on.
    expect(
      screen.getByRole("region", { name: "Passages it looked at" }),
    ).toBeTruthy();
    expect(passages()).toHaveLength(1);
    expect(document.querySelector(".answer.abstained")).not.toBeNull();
  });

  it("does not mark an ordinary answer as an abstention", async () => {
    stubApi({
      answers: [() => streamed(turn(answered()))],
      chunks: [chunkFor(CITATION), chunkFor(AUTHORED)],
    });
    render(<Ask />);

    askQuestion("What did we decide about the drift?");

    await screen.findByText(
      "The team settled on a firmware workaround, per Marcus.",
    );
    expect(screen.queryByText("The record does not settle this.")).toBeNull();
  });

  it("shows an error the API reported partway through", async () => {
    stubApi({
      answers: [
        () =>
          streamed([
            sse("started", { thread_id: "thread-1" }),
            sse("drafting", {}),
            sse("error", { detail: "ConnectError: the model did not answer" }),
          ]),
      ],
    });
    render(<Ask />);

    askQuestion("What did we decide about the drift?");

    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain("This question could not be answered.");
    expect(alert.textContent).toContain(
      "ConnectError: the model did not answer",
    );
    // The box is usable again, so the question can be asked again.
    expect(screen.getByRole("textbox")).toHaveProperty("disabled", false);
  });

  it("shows an error when the API refuses the request", async () => {
    stubApi({
      answers: [() => json(500, { detail: "Internal Server Error" })],
    });
    render(<Ask />);

    askQuestion("What did we decide about the drift?");

    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain("Internal Server Error");
  });

  it("asks a follow-up on the same conversation", async () => {
    const fetchMock = stubApi({
      answers: [
        () => streamed(turn(answered())),
        () =>
          streamed([
            sse("started", { thread_id: "thread-1" }),
            sse("drafting", {}),
            sse(
              "answer",
              answered({
                question: "Who owns that?",
                answer: "Marcus owns the workaround.",
                citations: [],
                searches: 0,
                answer_id: "answer-3",
              }),
            ),
          ]),
      ],
      chunks: [chunkFor(CITATION), chunkFor(AUTHORED)],
    });
    render(<Ask />);

    askQuestion("What did we decide about the drift?");
    await screen.findByText(
      "The team settled on a firmware workaround, per Marcus.",
    );
    expect(screen.getByLabelText("Ask a follow-up")).toBeTruthy();
    askQuestion("Who owns that?");
    await screen.findByText("Marcus owns the workaround.");

    expect(asked(fetchMock)).toEqual([
      { question: "What did we decide about the drift?" },
      { question: "Who owns that?", thread_id: "thread-1" },
    ]);
    // Both turns stay on the page, in order.
    expect(
      screen.getByText(
        "The team settled on a firmware workaround, per Marcus.",
      ),
    ).toBeTruthy();
    expect(
      screen.getByText(
        "Answered without searching the record, so no passages are cited.",
      ),
    ).toBeTruthy();
  });

  it("continues the conversation after a failure", async () => {
    const fetchMock = stubApi({
      answers: [
        () =>
          streamed([
            sse("started", { thread_id: "thread-9" }),
            sse("error", { detail: "RuntimeError: boom" }),
          ]),
        () => streamed(turn(answered({ thread_id: "thread-9" }))),
      ],
      chunks: [chunkFor(CITATION), chunkFor(AUTHORED)],
    });
    render(<Ask />);

    askQuestion("What did we decide about the drift?");
    await screen.findByRole("alert");
    askQuestion("What did we decide about the drift?");
    await screen.findByText(
      "The team settled on a firmware workaround, per Marcus.",
    );

    const [, second] = asked(fetchMock);
    expect(second.thread_id).toBe("thread-9");
  });

  it("starts a new conversation without the old thread", async () => {
    const fetchMock = stubApi({
      answers: [
        () => streamed(turn(answered())),
        () => streamed(turn(answered())),
      ],
      chunks: [chunkFor(CITATION), chunkFor(AUTHORED)],
    });
    render(<Ask />);
    askQuestion("What did we decide about the drift?");
    await screen.findByText(
      "The team settled on a firmware workaround, per Marcus.",
    );

    fireEvent.click(
      screen.getByRole("button", { name: "Start a new conversation" }),
    );
    expect(
      screen.queryByText(
        "The team settled on a firmware workaround, per Marcus.",
      ),
    ).toBeNull();
    askQuestion("What did we decide about the drift?");
    await screen.findByText(
      "The team settled on a firmware workaround, per Marcus.",
    );

    const [, second] = asked(fetchMock);
    expect(second).not.toHaveProperty("thread_id");
  });

  it("does not send a blank question", () => {
    const fetchMock = stubApi({ answers: [] });
    render(<Ask />);

    fireEvent.change(screen.getByRole("textbox"), { target: { value: "   " } });
    fireEvent.submit(
      screen.getByRole("textbox").closest("form") as HTMLFormElement,
    );

    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("asks on Enter and keeps Shift+Enter for a new line", async () => {
    const fetchMock = stubApi({
      answers: [() => streamed(turn(answered()))],
      chunks: [chunkFor(CITATION), chunkFor(AUTHORED)],
    });
    render(<Ask />);
    const box = screen.getByRole("textbox");
    fireEvent.change(box, { target: { value: "What did we decide?" } });

    fireEvent.keyDown(box, { key: "Enter", shiftKey: true });
    expect(fetchMock).not.toHaveBeenCalled();
    fireEvent.keyDown(box, { key: "Enter" });

    await screen.findByText(
      "The team settled on a firmware workaround, per Marcus.",
    );
  });
});
