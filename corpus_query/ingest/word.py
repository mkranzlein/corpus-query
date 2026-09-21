"""Reading a Word document and cutting it into its heading sections.

This is one format reader among several. It reads a ``.docx`` file with
python-docx and cuts it along the seams a written document has: its headings.

A heading section is the smallest unit a reader of the document would
recognize as a place. A citation that says the claim came from
``Thermal Chamber Results > Chamber B, 60 °C Soak`` can be checked by opening
the file and scrolling to that heading, which is the whole point of chunking
here rather than at a word count. So a chunk is one heading section, and its
``location`` is the path of headings above it.

Chunk text is the document's own text, block by block, so a sentence quoted
out of a chunk is findable in the file. A table is rendered one row per line
with its cells separated by pipes; that is the only shaping done to anything,
and it is what a table looks like when it is read as text.

A heading with nothing under it — a part title whose content all sits in
subsections — is carried into the next section's chunk rather than becoming a
chunk of its own. That keeps every block of the document in exactly one
chunk, so reassembling a document from its chunks gives the document back,
while sparing the corpus a chunk whose entire text is four words of heading.

A section longer than a chunk is split on block boundaries. Both halves keep
the same heading path, because both halves are in the same section: the split
is a storage decision and a citation should not have to know about it.

The author comes from the file's core properties and has to resolve to one
person on the roster. A document whose author is a name nobody on the roster
has is a document we cannot attribute, and attributing it to a name that
means nothing is worse than refusing it — so the file is reported unreadable
and the rest of the corpus is ingested without it.

Nothing here is random or time-dependent, so reading the same file twice
gives the same chunks.
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path

import docx
from docx.document import Document as WordDocument
from docx.table import Table
from docx.text.paragraph import Paragraph

from corpus_query.ingest.chunk import TARGET_WORDS, Chunk, count_words
from corpus_query.ingest.reader import IngestError, ReadDocument
from corpus_query.store.kinds import DOCX, DOCX_SECTION
from corpus_query.transcripts.roster import (
    DEFAULT_ROSTER_FILE,
    RosterError,
    read_roster,
)

#: What this reader claims.
DOCX_SUFFIX = ".docx"

#: The style whose paragraphs are the document's own title rather than part
#: of its body. It is recorded as the title and left out of the chunks, so a
#: document's text does not open by repeating its header.
TITLE_STYLE = "Title"

#: Word's built-in heading styles are ``Heading 1`` through ``Heading 9``.
#: A bold paragraph that looks like a heading is body text, here as in Word's
#: own navigation pane.
_HEADING_PREFIX = "Heading "

#: What separates the headings of a chunk's location.
PATH_SEPARATOR = " > "


@dataclass(frozen=True)
class Block:
    """One paragraph or table of a document, as text.

    Blocks are numbered across the whole body, empty paragraphs included, so
    a chunk's span is a range of positions in the file rather than a count of
    the blocks that happened to carry text.
    """

    index: int
    text: str
    heading_level: int | None
    """Its heading level, or ``None`` for body text."""

    @property
    def words(self) -> int:
        """How many words the block carries."""
        return count_words(self.text)


@dataclass(frozen=True)
class Section:
    """One heading section: a path, the headings above it, and its body."""

    path: tuple[str, ...]
    """The headings from the top of the document down to this section."""

    headings: tuple[Block, ...]
    """The heading blocks this section opens with. Usually one — more when
    the headings above it had no body of their own."""

    body: tuple[Block, ...]
    """The blocks under the heading, up to the next heading."""


@dataclass(frozen=True)
class ParsedWordDocument:
    """A Word document, read but not yet chunked."""

    title: str
    date: str
    author: str
    blocks: tuple[Block, ...]


def read_word_document(
    path: Path,
    target_words: int = TARGET_WORDS,
    roster_path: Path | str = DEFAULT_ROSTER_FILE,
) -> ReadDocument:
    """Read one Word document into a document ready to be written.

    Args:
        path: The ``.docx`` file to read.
        target_words: Words a chunk aims for, where a section has to split.
        roster_path: The roster the author is resolved against.

    Returns:
        The document, with its author and its heading sections.

    Raises:
        IngestError: If the file cannot be opened as a Word document, is
            missing the core properties a document is attributed by, or names
            an author who is not on the roster.
    """
    parsed = parse_word_document(path, roster_path=roster_path)
    return as_document(parsed, target_words=target_words)


def parse_word_document(
    path: Path | str, roster_path: Path | str = DEFAULT_ROSTER_FILE
) -> ParsedWordDocument:
    """Read a Word document's header fields and its blocks.

    Args:
        path: The ``.docx`` file to read.
        roster_path: The roster the author is resolved against.

    Returns:
        The document's title, date, author, and blocks, in document order.

    Raises:
        IngestError: If the file cannot be read, or cannot be attributed.
    """
    path = Path(path)
    try:
        document = docx.Document(str(path))
    except Exception as exc:
        raise IngestError(f"Could not read {path} as a Word document: {exc}") from exc

    blocks = tuple(_blocks(document))
    properties = document.core_properties
    return ParsedWordDocument(
        title=_title(properties.title, blocks, path),
        date=_date(path, properties.modified, properties.created),
        author=_author(path, properties.author, roster_path),
        blocks=blocks,
    )


def as_document(
    parsed: ParsedWordDocument, target_words: int = TARGET_WORDS
) -> ReadDocument:
    """Chunk an already parsed Word document into a document to be written.

    Args:
        parsed: The parsed document.
        target_words: Words a chunk aims for.

    Returns:
        The document, with its author and its heading sections. It has no
        attendees: one person wrote it.
    """
    sections = split_into_sections(parsed.blocks, parsed.title)
    return ReadDocument(
        source_kind=DOCX,
        title=parsed.title,
        document_date=parsed.date,
        author=parsed.author,
        attendees=(),
        chunks=tuple(chunk_sections(sections, target_words=target_words)),
        units=len(sections),
        unit_name="sections",
    )


def split_into_sections(blocks: Sequence[Block], title: str) -> list[Section]:
    """Group a document's blocks into heading sections.

    Args:
        blocks: The document's blocks, in order.
        title: The document's title, which labels anything written above the
            first heading.

    Returns:
        One section per heading that has a body, in document order. A heading
        with no body of its own is carried into the next section, so every
        block that carries text belongs to exactly one section. A trailing
        heading with nothing under it belongs to no section and is dropped.
    """
    sections: list[Section] = []
    path: list[str] = []
    headings: list[Block] = []
    body: list[Block] = []

    def close() -> None:
        if body:
            label = tuple(path) if path else (title,)
            sections.append(Section(label, tuple(headings), tuple(body)))
            headings.clear()
            body.clear()

    for block in blocks:
        if block.heading_level is None:
            body.append(block)
            continue
        close()
        del path[block.heading_level - 1 :]
        path.append(block.text)
        headings.append(block)
    close()
    return sections


def chunk_sections(
    sections: Sequence[Section], target_words: int = TARGET_WORDS
) -> list[Chunk]:
    """Cut heading sections into chunks.

    Args:
        sections: The document's sections, in order.
        target_words: Words a chunk aims for. A section over it is split on
            block boundaries; a single block over it stands alone rather than
            being cut mid-paragraph.

    Returns:
        The chunks, in document order.
    """
    chunks: list[Chunk] = []
    for section in sections:
        for part in _parts(section, target_words):
            chunks.append(_build_chunk(len(chunks), section.path, part))
    return chunks


def _parts(section: Section, target_words: int) -> list[list[Block]]:
    """Split one section into the runs of blocks that become chunks.

    The section's headings open the first part only. Repeating them at the
    top of the second half would put text in the store twice, and the heading
    path is already on every part.

    Args:
        section: The section to split.
        target_words: Words a part aims to stay under.

    Returns:
        One list of blocks per chunk, covering the section in order.
    """
    parts: list[list[Block]] = []
    current = list(section.headings)
    words = sum(block.words for block in current)
    carries_body = False
    for block in section.body:
        if carries_body and words + block.words > target_words:
            parts.append(current)
            current = []
            words = 0
        current.append(block)
        words += block.words
        carries_body = True
    parts.append(current)
    return parts


def _build_chunk(ordinal: int, path: Sequence[str], blocks: Sequence[Block]) -> Chunk:
    """Assemble one chunk from a run of blocks.

    Args:
        ordinal: The chunk's position in the document.
        path: The headings above the section the blocks came from.
        blocks: The blocks, in order.

    Returns:
        The chunk.
    """
    text = "\n".join(block.text for block in blocks)
    return Chunk(
        ordinal=ordinal,
        text=text,
        word_count=count_words(text),
        kind=DOCX_SECTION,
        location=PATH_SEPARATOR.join(path),
        span_start=blocks[0].index,
        span_end=blocks[-1].index,
    )


def _blocks(document: WordDocument) -> Iterator[Block]:
    """Read a document's body as numbered blocks of text.

    Paragraphs and tables are read in the order they appear, which a
    paragraph-only walk would lose: a table sitting between two paragraphs
    belongs where it was written.

    Args:
        document: The open document.

    Yields:
        One block per paragraph or table that carries text. Empty paragraphs
        and the title are numbered and skipped, so the numbering stays a
        position in the file.
    """
    for index, item in enumerate(document.iter_inner_content()):
        if isinstance(item, Table):
            text = _table_text(item)
            level = None
        elif isinstance(item, Paragraph):
            text = item.text.strip()
            style = item.style.name if item.style is not None else None
            if style == TITLE_STYLE:
                continue
            level = _heading_level(style)
        else:  # pragma: no cover - python-docx yields only these two.
            continue
        if text:
            yield Block(index=index, text=text, heading_level=level)


def _table_text(table: Table) -> str:
    """Render a table as text, one row per line.

    Args:
        table: The table to render.

    Returns:
        ``| cell | cell |`` per row. A cell spanning several columns is
        written once rather than repeated, which is how it reads on the page
        and how python-docx would otherwise report it.
    """
    lines = []
    for row in table.rows:
        cells = []
        seen = set()
        for cell in row.cells:
            # A merged cell is reported once per column it spans, and the
            # underlying element is the only thing that gives it away.
            element = id(cell._tc)
            if element in seen:
                continue
            seen.add(element)
            cells.append(" ".join(cell.text.split()))
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def _heading_level(style: str | None) -> int | None:
    """Return the heading level of a paragraph style.

    Args:
        style: The paragraph's style name, or ``None``.

    Returns:
        The level, or ``None`` for anything that is not a Word heading.
    """
    if style is None or not style.startswith(_HEADING_PREFIX):
        return None
    suffix = style.removeprefix(_HEADING_PREFIX)
    return int(suffix) if suffix.isdigit() else None


def _title(title: str | None, blocks: Sequence[Block], path: Path) -> str:
    """Decide what the document is called.

    Args:
        title: The title in the core properties, if there is one.
        blocks: The document's blocks.
        path: Where it was read from, for the last resort.

    Returns:
        The core property, else the document's first heading, else the file's
        name. A document with no title anywhere is odd rather than broken,
        and a filename is a truer label for it than an empty string.
    """
    if title and title.strip():
        return title.strip()
    for block in blocks:
        if block.heading_level is not None:
            return block.text
    return path.stem


def _date(path: Path, modified, created) -> str:
    """Decide what the document is dated.

    Args:
        path: The file, for the error message.
        modified: The ``modified`` core property.
        created: The ``created`` core property.

    Returns:
        ``YYYY-MM-DD``. When it was last written, which is what a reader
        means by a document's date; failing that, when it was created.

    Raises:
        IngestError: If it carries neither. A document with no date cannot be
            placed against the rest of the corpus.
    """
    stamp = modified or created
    if stamp is None:
        raise IngestError(
            f"{path} has no created or modified date in its core properties, "
            f"so there is nothing to date it by."
        )
    return stamp.date().isoformat()


def _author(path: Path, author: str | None, roster_path: Path | str) -> str:
    """Resolve the document's author to one person on the roster.

    Args:
        path: The file, for the error messages.
        author: The ``author`` core property.
        roster_path: The roster to resolve against.

    Returns:
        The author's name, spelled as the roster spells it.

    Raises:
        IngestError: If the property is empty, names more than one person, or
            names someone the roster does not have.
    """
    name = (author or "").strip()
    if not name:
        raise IngestError(
            f"{path} names no author in its core properties. A document is "
            f"attributed to the person who wrote it."
        )
    try:
        roster = read_roster(roster_path)
    except RosterError as exc:
        raise IngestError(str(exc)) from exc
    for person in roster:
        if person.first_name.casefold() == name.casefold():
            return person.first_name
    known = ", ".join(person.first_name for person in roster)
    raise IngestError(
        f"{path} names {name!r} as its author, who is not on the roster at "
        f"{roster_path}. The roster has {known}."
    )
