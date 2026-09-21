// @vitest-environment jsdom

import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import Review from "./Review.tsx";
import { correction, feedback, gap, stubApi } from "./fixtures.ts";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

/** The rows of the queue as they are on screen, top to bottom. */
function rows(): HTMLElement[] {
  // Only the queue's own rows, not the citations nested inside an open one.
  return Array.from(document.querySelectorAll<HTMLElement>("ol.queue > li"));
}

/** The button that opens a row, found by the question it shows. */
function opener(question: string): HTMLElement {
  return screen.getByRole("button", { name: new RegExp(question) });
}

describe("the review page", () => {
  it("lists every kind, most recent first", async () => {
    stubApi({
      gaps: [gap()],
      corrections: [correction()],
      feedback: [feedback()],
    });

    render(<Review />);

    await waitFor(() => expect(rows()).toHaveLength(3));
    expect(rows().map((row) => row.textContent)).toEqual([
      expect.stringContaining("Correction"),
      expect.stringContaining("Feedback"),
      expect.stringContaining("Gap"),
    ]);
  });

  it("shows the question, when, and what the system did on each row", async () => {
    stubApi({ gaps: [gap()] });

    render(<Review />);

    const [row] = await waitFor(() => {
      const found = rows();
      expect(found).toHaveLength(1);
      return found;
    });
    expect(row.textContent).toContain(
      "Which units are installed in hot environments?",
    );
    expect(row.textContent).toContain("suggested asking Sofia");
    expect(row.querySelector("time")?.getAttribute("dateTime")).toBe(
      "2026-03-01T09:00:00.000Z",
    );
    expect(row.textContent).toContain("New");
  });

  it("narrows to one kind", async () => {
    stubApi({
      gaps: [gap()],
      corrections: [correction()],
      feedback: [feedback()],
    });
    render(<Review />);
    await waitFor(() => expect(rows()).toHaveLength(3));

    fireEvent.click(screen.getByRole("button", { name: /^Corrections/ }));

    expect(rows()).toHaveLength(1);
    expect(rows()[0].textContent).toContain("The freeze moved to March 19th.");
    expect(
      screen.getByRole("button", { name: /^Corrections/ }),
    ).toHaveProperty("ariaPressed", "true");
  });

  it("opens a row to the full record, read again from the API", async () => {
    const fetchMock = stubApi({ corrections: [correction({ id: 5 })] });
    render(<Review />);
    const button = await waitFor(() => opener("Where are the rev B boards"));

    fireEvent.click(button);

    const detail = document.getElementById("record-corrections-5");
    expect(detail).not.toBeNull();
    const text = detail?.textContent ?? "";
    expect(text).toContain("Marcus put them two weeks out.");
    expect(text).toContain("Rev B schedule");
    expect(text).toContain("It said the freeze is March 12th.");
    expect(text).toContain("The freeze moved to March 19th.");
    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        "/corrections/5",
        expect.anything(),
      ),
    );
  });

  it("shows the routing suggestion when a gap is opened", async () => {
    stubApi({ gaps: [gap({ id: 2 })] });
    render(<Review />);
    fireEvent.click(await waitFor(() => opener("hot environments")));

    const detail = document.getElementById("record-gaps-2");

    expect(detail?.textContent).toContain("Sofia, Firmware Engineer");
  });

  it("marks an item reviewed, and can put it back", async () => {
    const fetchMock = stubApi({ feedback: [feedback({ id: 8 })] });
    render(<Review />);
    const mark = await waitFor(() =>
      screen.getByRole("button", { name: "Mark reviewed" }),
    );

    fireEvent.click(mark);

    const undo = await waitFor(() =>
      screen.getByRole("button", { name: "Mark as new" }),
    );
    expect(rows()[0].classList.contains("reviewed")).toBe(true);
    expect(rows()[0].textContent).not.toContain("New");
    expect(fetchMock).toHaveBeenCalledWith(
      "/feedback/8",
      expect.objectContaining({ method: "PATCH" }),
    );

    fireEvent.click(undo);

    await waitFor(() =>
      screen.getByRole("button", { name: "Mark reviewed" }),
    );
    expect(rows()[0].classList.contains("new")).toBe(true);
  });

  it("reads an empty queue as empty", async () => {
    stubApi({});

    render(<Review />);

    expect(await screen.findByText(/The queue is empty/)).toBeTruthy();
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("reads an empty kind as empty", async () => {
    stubApi({ gaps: [gap()] });
    render(<Review />);
    await waitFor(() => expect(rows()).toHaveLength(1));

    fireEvent.click(screen.getByRole("button", { name: /^Feedback/ }));

    expect(screen.getByText("No feedback recorded yet.")).toBeTruthy();
  });

  it("says so when the API does not answer", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() => Promise.reject(new TypeError("network down"))),
    );

    render(<Review />);

    expect((await screen.findByRole("alert")).textContent).toContain(
      "could not be loaded",
    );
  });
});
