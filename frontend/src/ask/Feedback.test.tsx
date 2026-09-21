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

import Answer from "./Answer.tsx";
import Ask from "./Ask.tsx";
import {
  AUTHORED,
  CITATION,
  WHAT_IS_RIGHT,
  WHAT_WAS_WRONG,
  answered,
  chunkFor,
  correcting,
  json,
  streamed,
  stubApi,
  turn,
  unreachable,
} from "./fixtures.ts";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const CHUNKS = [chunkFor(CITATION), chunkFor(AUTHORED)];

/** The bodies of every request sent to one path, in order. */
function sent(
  fetchMock: ReturnType<typeof stubApi>,
  path: string,
): Record<string, unknown>[] {
  return (fetchMock.mock.calls as unknown as [string, RequestInit?][])
    .filter(([url, init]) => url === path && init?.method === "POST")
    .map(
      ([, init]) => JSON.parse(String(init?.body)) as Record<string, unknown>,
    );
}

/** The controls for judging one answer. */
function feedback(scope: HTMLElement = document.body): HTMLElement {
  return within(scope).getByRole("region", {
    name: "Was this answer helpful?",
  });
}

/** What the controls last said was recorded. */
function confirmation(scope: HTMLElement = feedback()): string {
  return scope.querySelector(".recorded")?.textContent ?? "";
}

function helpful() {
  return within(feedback()).getByRole("button", { name: "Helpful" });
}

function notHelpful() {
  return within(feedback()).getByRole("button", { name: "Not helpful" });
}

function wrongBox() {
  return within(feedback()).getByRole("textbox", { name: "What it got wrong" });
}

function rightBox() {
  return within(feedback()).getByRole("textbox", {
    name: "What is right instead",
  });
}

function submit() {
  return within(feedback()).getByRole("button", {
    name: "Record the correction",
  });
}

describe("judging an answer", () => {
  it("records an up vote against the answer, and says so", async () => {
    const fetchMock = stubApi({
      answers: [],
      chunks: CHUNKS,
      known: [answered()],
    });
    render(<Answer answer={answered()} />);

    fireEvent.click(helpful());

    await waitFor(() => expect(confirmation()).toBe("Recorded as helpful."));
    expect(sent(fetchMock, "/feedback")).toEqual([
      { answer_id: "answer-1", verdict: "up" },
    ]);
    expect(helpful().getAttribute("aria-pressed")).toBe("true");
    expect(notHelpful().getAttribute("aria-pressed")).toBe("false");
    // A vote is final once recorded.
    expect(helpful()).toHaveProperty("disabled", true);
    expect(notHelpful()).toHaveProperty("disabled", true);
    // An up vote asks nothing further.
    expect(within(feedback()).queryByRole("textbox")).toBeNull();
    expect(sent(fetchMock, "/corrections")).toEqual([]);
  });

  it("records a bare down vote as feedback when the invitation is declined", async () => {
    const fetchMock = stubApi({
      answers: [],
      chunks: CHUNKS,
      known: [answered()],
    });
    render(<Answer answer={answered()} />);

    fireEvent.click(notHelpful());

    // The vote lands first, and then what was wrong is asked for.
    await waitFor(() =>
      expect(confirmation()).toBe("Recorded as not helpful."),
    );
    expect(sent(fetchMock, "/feedback")).toEqual([
      { answer_id: "answer-1", verdict: "down" },
    ]);
    expect(document.activeElement).toBe(wrongBox());
    expect(feedback().textContent).toContain("your vote is already recorded");

    fireEvent.click(
      within(feedback()).getByRole("button", { name: "No thanks" }),
    );

    expect(within(feedback()).queryByRole("textbox")).toBeNull();
    expect(confirmation()).toBe("Recorded as not helpful.");
    expect(notHelpful().getAttribute("aria-pressed")).toBe("true");
    expect(sent(fetchMock, "/corrections")).toEqual([]);
  });

  it("promotes a down vote into a correction when one is written", async () => {
    const fetchMock = stubApi({
      answers: [],
      chunks: CHUNKS,
      known: [answered()],
    });
    render(<Answer answer={answered()} />);

    fireEvent.click(notHelpful());
    await screen.findByRole("textbox", { name: "What it got wrong" });

    // Both halves are needed: one that only says what was wrong is the vote
    // already recorded.
    expect(submit()).toHaveProperty("disabled", true);
    fireEvent.change(wrongBox(), { target: { value: `  ${WHAT_WAS_WRONG} ` } });
    expect(submit()).toHaveProperty("disabled", true);
    fireEvent.change(rightBox(), { target: { value: WHAT_IS_RIGHT } });
    fireEvent.click(submit());

    await waitFor(() => expect(confirmation()).toBe("Correction recorded."));
    expect(sent(fetchMock, "/corrections")).toEqual([
      {
        answer_id: "answer-1",
        what_was_wrong: WHAT_WAS_WRONG,
        what_is_right: WHAT_IS_RIGHT,
      },
    ]);
    // The vote was recorded once, and the correction on top of it.
    expect(sent(fetchMock, "/feedback")).toEqual([
      { answer_id: "answer-1", verdict: "down" },
    ]);

    // What is shown is what the service stored, and nothing more is asked.
    const stored = feedback().querySelector<HTMLElement>(".corrected");
    expect(stored?.textContent).toContain("Correction recorded.");
    expect(stored?.textContent).toContain(WHAT_WAS_WRONG);
    expect(stored?.textContent).toContain(WHAT_IS_RIGHT);
    expect(within(feedback()).queryByRole("textbox")).toBeNull();
  });

  it("says a vote failed, and lets it be cast again", async () => {
    const fetchMock = stubApi({
      answers: [],
      chunks: CHUNKS,
      known: [answered()],
      writes: { feedback: [unreachable] },
    });
    render(<Answer answer={answered()} />);

    fireEvent.click(notHelpful());

    const alert = await within(feedback()).findByRole("alert");
    expect(alert.textContent).toContain(
      "Your vote was not recorded: The service could not be reached.",
    );
    // Nothing claims it landed, and nothing follows from a vote that did not.
    expect(confirmation()).toBe("");
    expect(notHelpful().getAttribute("aria-pressed")).toBe("false");
    expect(within(feedback()).queryByRole("textbox")).toBeNull();
    expect(notHelpful()).toHaveProperty("disabled", false);

    fireEvent.click(notHelpful());

    await waitFor(() =>
      expect(confirmation()).toBe("Recorded as not helpful."),
    );
    expect(within(feedback()).queryByRole("alert")).toBeNull();
    expect(sent(fetchMock, "/feedback")).toHaveLength(2);
  });

  it("says a correction failed, and keeps what was written", async () => {
    const fetchMock = stubApi({
      answers: [],
      chunks: CHUNKS,
      known: [answered()],
      writes: {
        corrections: [
          () => json(500, { detail: "The usage database is locked." }),
        ],
      },
    });
    render(<Answer answer={answered()} />);

    fireEvent.click(notHelpful());
    await screen.findByRole("textbox", { name: "What it got wrong" });
    fireEvent.change(wrongBox(), { target: { value: WHAT_WAS_WRONG } });
    fireEvent.change(rightBox(), { target: { value: WHAT_IS_RIGHT } });
    fireEvent.click(submit());

    const alert = await within(feedback()).findByRole("alert");
    expect(alert.textContent).toContain(
      "The correction was not recorded: The usage database is locked.",
    );
    expect(wrongBox()).toHaveProperty("value", WHAT_WAS_WRONG);
    expect(rightBox()).toHaveProperty("value", WHAT_IS_RIGHT);
    // The vote before it did land, and still says so.
    expect(confirmation()).toBe("Recorded as not helpful.");

    fireEvent.click(submit());

    await waitFor(() => expect(confirmation()).toBe("Correction recorded."));
    expect(sent(fetchMock, "/corrections")).toHaveLength(2);
  });

  it("says so when the service does not know the answer", async () => {
    stubApi({ answers: [], chunks: CHUNKS, known: [] });
    render(<Answer answer={answered()} />);

    fireEvent.click(helpful());

    const alert = await within(feedback()).findByRole("alert");
    expect(alert.textContent).toContain("no answer with id 'answer-1'");
    expect(confirmation()).toBe("");
  });
});

describe("a correction typed into the conversation", () => {
  /** Ask one question, then correct it in the next message. */
  async function correctInConversation() {
    const first = answered();
    const second = correcting(first);
    const fetchMock = stubApi({
      answers: [() => streamed(turn(first)), () => streamed(turn(second))],
      chunks: CHUNKS,
      known: [first, second],
    });
    render(<Ask />);
    return { fetchMock, first, second };
  }

  function askQuestion(question: string) {
    fireEvent.change(
      screen.getByRole("textbox", { name: /question|follow-up/ }),
      {
        target: { value: question },
      },
    );
    fireEvent.click(screen.getByRole("button", { name: "Ask" }));
  }

  it("shows on the answer it corrects, and is not recorded again", async () => {
    const { fetchMock, first, second } = await correctInConversation();

    askQuestion(first.question);
    await screen.findByText(first.answer);
    askQuestion(second.question);
    await screen.findByText(second.answer);

    // Only the answer is there to judge; the turn that recorded the
    // correction says what it recorded, and that is all.
    expect(
      screen.getAllByRole("region", { name: "Was this answer helpful?" }),
    ).toHaveLength(1);
    const stored = feedback().querySelector<HTMLElement>(".corrected");
    expect(stored?.textContent).toContain("Corrected in the conversation.");
    expect(stored?.textContent).toContain(WHAT_WAS_WRONG);
    expect(stored?.textContent).toContain(WHAT_IS_RIGHT);

    // A down vote on it is still recorded, but does not ask for the
    // correction the conversation already recorded.
    fireEvent.click(notHelpful());
    await waitFor(() =>
      expect(confirmation()).toBe("Recorded as not helpful."),
    );
    expect(within(feedback()).queryByRole("textbox")).toBeNull();
    expect(sent(fetchMock, "/corrections")).toEqual([]);
  });

  it("withdraws the invitation when the correction is typed instead", async () => {
    const { fetchMock, first, second } = await correctInConversation();

    askQuestion(first.question);
    await screen.findByText(first.answer);
    fireEvent.click(notHelpful());
    await screen.findByRole("textbox", { name: "What it got wrong" });
    fireEvent.change(wrongBox(), { target: { value: "Half written" } });

    askQuestion(second.question);
    await screen.findByText(second.answer);

    expect(within(feedback()).queryByRole("textbox")).toBeNull();
    expect(feedback().textContent).toContain("Corrected in the conversation.");
    expect(sent(fetchMock, "/corrections")).toEqual([]);
    expect(sent(fetchMock, "/feedback")).toEqual([
      { answer_id: "answer-1", verdict: "down" },
    ]);
  });
});
