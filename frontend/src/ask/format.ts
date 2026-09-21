/**
 * How the question page words what the API sends as codes: source kinds,
 * dates, and the derived metadata's vocabularies.
 */

/** What a reader calls each kind of source. */
const KINDS: Record<string, string> = {
  transcript: "Meeting transcript",
  docx: "Document",
  pptx: "Slide deck",
  xlsx: "Spreadsheet",
};

/** Name a source kind for a reader, or pass through one this page does not know. */
export function kindLabel(kind: string): string {
  return KINDS[kind] ?? kind;
}

const day = new Intl.DateTimeFormat(undefined, {
  dateStyle: "medium",
  timeZone: "UTC",
});

/**
 * Format an ISO 8601 date for a reader. Dates here are calendar days, so
 * they are read as UTC; reading one in local time would move it a day for
 * anyone west of Greenwich.
 */
export function formatDay(date: string): string {
  const parsed = new Date(`${date.slice(0, 10)}T00:00:00Z`);
  return Number.isNaN(parsed.getTime()) ? date : day.format(parsed);
}

/** Turn a vocabulary term like `near_term` into `Near term`. */
export function term(value: string): string {
  const words = value.replace(/_/g, " ");
  return words.charAt(0).toUpperCase() + words.slice(1);
}

/** Say who a passage came from: its author, or who was in the room. */
export function people(source: {
  author: string | null;
  attendees: string[];
}): { label: string; names: string } | null {
  if (source.author) {
    return { label: "Author", names: source.author };
  }
  if (source.attendees.length > 0) {
    return { label: "Attendees", names: source.attendees.join(", ") };
  }
  return null;
}
