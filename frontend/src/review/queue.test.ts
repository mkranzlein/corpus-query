import { afterEach, describe, expect, it, vi } from "vitest";

import { correction, feedback, gap, stubApi } from "./fixtures.ts";
import {
  ApiError,
  type QueueItem,
  QUEUE_LIMIT,
  loadQueue,
  mostRecentFirst,
  narrowed,
  openRecord,
  setReviewed,
  whatTheSystemDid,
  whatWasSaid,
} from "./queue.ts";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("loadQueue", () => {
  it("merges the three kinds, most recent first", async () => {
    stubApi({
      gaps: [gap({ id: 2, created_at: "2026-03-04T00:00:00.000Z" }), gap()],
      corrections: [correction()],
      feedback: [feedback()],
    });

    const { items, truncated } = await loadQueue();

    expect(items.map((item) => [item.kind, item.id])).toEqual([
      ["gaps", 2],
      ["corrections", 1],
      ["feedback", 1],
      ["gaps", 1],
    ]);
    expect(truncated).toBe(false);
  });

  it("asks for as many of each kind as one read allows", async () => {
    const fetchMock = stubApi({});

    await loadQueue();

    const urls = fetchMock.mock.calls.map(([url]) => String(url));
    expect(urls.sort()).toEqual([
      `/corrections?limit=${QUEUE_LIMIT}`,
      `/feedback?limit=${QUEUE_LIMIT}`,
      `/gaps?limit=${QUEUE_LIMIT}`,
    ]);
  });

  it("is an empty list, not an error, when nothing was recorded", async () => {
    stubApi({});

    expect(await loadQueue()).toEqual({ items: [], truncated: false });
  });

  it("says when a kind filled its read and older items were left out", async () => {
    stubApi({
      feedback: Array.from({ length: QUEUE_LIMIT }, (_, index) =>
        feedback({ id: index + 1 }),
      ),
    });

    expect((await loadQueue()).truncated).toBe(true);
  });

  it("fails when the API does", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() => Promise.resolve(new Response("", { status: 500 }))),
    );

    await expect(loadQueue()).rejects.toBeInstanceOf(ApiError);
  });
});

describe("narrowed", () => {
  const items = mostRecentFirst([
    { ...gap(), kind: "gaps" },
    { ...correction(), kind: "corrections" },
    { ...feedback(), kind: "feedback" },
  ] as QueueItem[]);

  it("keeps everything for all", () => {
    expect(narrowed(items, "all")).toEqual(items);
  });

  it.each(["gaps", "corrections", "feedback"] as const)(
    "keeps only %s when asked for them",
    (kind) => {
      const kept = narrowed(items, kind);

      expect(kept).toHaveLength(1);
      expect(kept[0].kind).toBe(kind);
    },
  );
});

describe("opening and marking", () => {
  it("reads one record by its kind and id", async () => {
    const fetchMock = stubApi({ corrections: [correction({ id: 3 })] });

    const opened = await openRecord("corrections", 3);

    expect(fetchMock).toHaveBeenCalledWith("/corrections/3", expect.anything());
    expect(opened).toMatchObject({ kind: "corrections", id: 3 });
  });

  it("marks a record reviewed and clears the mark again", async () => {
    const fetchMock = stubApi({ gaps: [gap({ id: 4 })] });

    const marked = await setReviewed("gaps", 4, true);
    const cleared = await setReviewed("gaps", 4, false);

    expect(marked.reviewed_at).toBe("2026-03-05T12:00:00.000Z");
    expect(cleared.reviewed_at).toBeNull();
    const [, init] = fetchMock.mock.calls[0];
    expect(init).toMatchObject({ method: "PATCH" });
    expect(JSON.parse(String(init?.body))).toEqual({ reviewed: true });
  });

  it("fails on an id that is not there", async () => {
    stubApi({});

    await expect(openRecord("feedback", 9)).rejects.toMatchObject({
      status: 404,
    });
  });
});

describe("the one-line summary", () => {
  it("names who was suggested when the system could not answer", () => {
    const item = { ...gap(), kind: "gaps" } as QueueItem;

    expect(whatTheSystemDid(item)).toBe(
      "Could not answer; suggested asking Sofia",
    );
    expect(whatWasSaid(item)).toBeNull();
  });

  it("says the system could not answer when it suggested nobody", () => {
    const item = { ...gap({ routing: null }), kind: "gaps" } as QueueItem;

    expect(whatTheSystemDid(item)).toBe("Could not answer");
  });

  it("counts the passages an answer cited", () => {
    const item = { ...correction(), kind: "corrections" } as QueueItem;

    expect(whatTheSystemDid(item)).toBe("Answered, citing 1 passage");
    expect(whatWasSaid(item)).toBe(
      "Correction: The freeze moved to March 19th.",
    );
  });

  it("gives the verdict, and the note when there is one", () => {
    const noted = { ...feedback(), kind: "feedback" } as QueueItem;
    const bare = {
      ...feedback({ verdict: "up", note: null }),
      kind: "feedback",
    } as QueueItem;

    expect(whatWasSaid(noted)).toBe("Thumbs down: cited the wrong meeting");
    expect(whatWasSaid(bare)).toBe("Thumbs up");
  });
});
