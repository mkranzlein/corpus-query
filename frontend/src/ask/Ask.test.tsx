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

    askQuestion("What did we decide about the RV-2 introductory price?");
    held.send(sse("started", { thread_id: "thread-1" }));
    held.send(sse("drafting", {}));
    held.send(sse("searching", { query: "RV-2 introductory price" }));

    const status = await screen.findByRole("status");
    await waitFor(() =>
      expect(status.textContent).toContain(
        "Searching the record for “RV-2 introductory price”",
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
      "The RV-2 launches at $189 for ninety days, per Priya.",
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

    askQuestion("What did we decide about the RV-2 introductory price?");

    await screen.findByText(
      "The RV-2 launches at $189 for ninety days, per Priya.",
    );
    const section = screen.getByRole("region", {
      name: "Passages this answer rests on",
    });
    expect(within(section).getByText("What this answer rests on")).toBeTruthy();
    expect(passages()).toHaveLength(2);
    const [meeting, report] = passages();

    // Where each passage came from, and who was behind it.
    expect(meeting.textContent).toContain(
      "Q2 Pricing Review — GX-7 and RV-2 List Price Adjustment",
    );
    expect(meeting.textContent).toContain("Meeting transcript");
    expect(meeting.textContent).toContain("Attendees");
    expect(meeting.textContent).toContain("Priya, Elena, Renata, Jamal, Nadia");
    expect(meeting.textContent).toContain(
      "q2-pricing-review-gx-7-and-rv-2-list-price-adjustment",
    );
    expect(meeting.textContent).toContain("turns 22-30");
    expect(meeting.querySelector("time")?.getAttribute("dateTime")).toBe(
      "2026-03-11",
    );
    expect(report.textContent).toContain("Document");
    expect(report.textContent).toContain("Author");
    expect(report.textContent).toContain("Sofia");
    expect(report.textContent).toContain("Field Rollout");

    // What was derived about each, read from the passage's own record.
    await waitFor(() => expect(meeting.textContent).toContain("Near term"));
    expect(meeting.textContent).toContain("Pricing");
    expect(meeting.textContent).toContain("Sales");
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
      screen.queryByText(
        "The passage behind Q2 Pricing Review — GX-7 and RV-2 List Price Adjustment.",
      ),
    ).toBeNull();
    fireEvent.click(open);

    const text = screen.getByText(
      "The passage behind Q2 Pricing Review — GX-7 and RV-2 List Price Adjustment.",
    );
    const quote = text.closest("blockquote") as HTMLElement;
    expect(quote.textContent).toContain(
      "Q2 Pricing Review — GX-7 and RV-2 List Price Adjustment",
    );
    expect(quote.textContent).toContain("turns 22-30");
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
    expect(passages()[0].textContent).toContain("Q2 Pricing Review");
  });

  it("presents an abstention as an answer, not a failure", async () => {
    stubApi({
      answers: [() => streamed(turn(abstained()))],
      chunks: [chunkFor(AUTHORED)],
    });
    render(<Ask />);

    askQuestion("Which sites are the remote Quennick units at?");

    await screen.findByText("The record does not settle this.");
    expect(
      screen.getByText(
        "The record does not say which sites the remote Quennick units are at.",
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
      "The RV-2 launches at $189 for ninety days, per Priya.",
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
                answer: "Renata owns the pricing memo.",
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
      "The RV-2 launches at $189 for ninety days, per Priya.",
    );
    expect(screen.getByLabelText("Ask a follow-up")).toBeTruthy();
    askQuestion("Who owns that?");
    await screen.findByText("Renata owns the pricing memo.");

    expect(asked(fetchMock)).toEqual([
      { question: "What did we decide about the drift?" },
      { question: "Who owns that?", thread_id: "thread-1" },
    ]);
    // Both turns stay on the page, in order.
    expect(
      screen.getByText(
        "The RV-2 launches at $189 for ninety days, per Priya.",
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
      "The RV-2 launches at $189 for ninety days, per Priya.",
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
      "The RV-2 launches at $189 for ninety days, per Priya.",
    );

    fireEvent.click(
      screen.getByRole("button", { name: "Start a new conversation" }),
    );
    expect(
      screen.queryByText(
        "The RV-2 launches at $189 for ninety days, per Priya.",
      ),
    ).toBeNull();
    askQuestion("What did we decide about the drift?");
    await screen.findByText(
      "The RV-2 launches at $189 for ninety days, per Priya.",
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
      "The RV-2 launches at $189 for ninety days, per Priya.",
    );
  });
});
