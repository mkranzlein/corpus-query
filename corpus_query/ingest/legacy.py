"""Reading legacy office formats by converting them first.

The system reads `.docx`, `.pptx`, and `.xlsx`. A `.doc`, `.ppt`, or `.xls`
file is not parsed on its own terms: it is converted to its modern equivalent
with LibreOffice headless, and the result is handed to the reader that format
already has. No model sees raw bytes at either step, and the conversion is
deterministic, so the chunks that come out match the file they came from.

What LibreOffice produces is not quite standard, so the conversion repairs
it before the reader sees it: see :func:`repair_core_properties`, which puts
the converted file's core properties back where OOXML says they live.

The conversion happens in a temporary directory that is cleaned up once the
modern reader has run. Nothing is written next to the source file, and the
converted file is never committed or reused across calls — this is not a
cache, and there is no corpus of legacy fixtures to warm one with.

The document a legacy file becomes is still that document: its slug and
title are taken from the legacy file's own name and metadata, and its
source path is the legacy file, not the temporary conversion, because that
is the file a reader can actually open.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path

from corpus_query.ingest.reader import IngestError, ReadDocument, Reader

#: Where the macOS app puts the binary. The app installs without adding
#: `soffice` to `PATH`, so a user who installed it the ordinary way — by
#: dragging the app into Applications — would otherwise see it reported as
#: missing.
MACOS_SOFFICE_PATH = Path("/Applications/LibreOffice.app/Contents/MacOS/soffice")

#: Shown whenever LibreOffice is what a legacy file needs and isn't found or
#: doesn't work, so the fix is always one line away from the failure.
INSTALL_HINT = (
    "Install it from https://www.libreoffice.org/download/ or, on macOS, "
    "with `brew install --cask libreoffice`."
)

#: The relationship type OOXML gives the core properties part, which is
#: where a document's author, title, and dates live. Readers find that part
#: by looking this exact string up in the package relationships.
CORE_PROPERTIES_RELATIONSHIP = (
    "http://schemas.openxmlformats.org/package/2006/relationships/"
    "metadata/core-properties"
)

#: What LibreOffice writes in its place: the same path under
#: ``officedocument`` rather than ``package``. Everything else about the
#: file is well formed, and the properties themselves are present and
#: correct — only the relationship pointing at them is misspelled.
LIBREOFFICE_CORE_PROPERTIES_RELATIONSHIP = (
    "http://schemas.openxmlformats.org/officedocument/2006/relationships/"
    "metadata/core-properties"
)

#: The package relationships, which is the one part this repairs.
PACKAGE_RELATIONSHIPS = "_rels/.rels"


def find_soffice() -> Path | None:
    """Locate the LibreOffice command line binary.

    Checked on `PATH` first, then at the usual macOS install location, since
    the macOS app does not put `soffice` on `PATH` on its own.

    Returns:
        The binary's path, or ``None`` if it could not be found anywhere
        this looks.
    """
    on_path = shutil.which("soffice")
    if on_path is not None:
        return Path(on_path)
    if MACOS_SOFFICE_PATH.is_file():
        return MACOS_SOFFICE_PATH
    return None


def convert(path: Path, target_suffix: str, outdir: Path) -> Path:
    """Convert one legacy office file to a modern format with LibreOffice.

    Args:
        path: The legacy file to convert.
        target_suffix: The format to convert to, including its dot, such as
            ``".docx"``.
        outdir: A directory LibreOffice should write the converted file
            into. The caller owns its lifetime.

    Returns:
        The path of the converted file, repaired by
        :func:`repair_core_properties`. LibreOffice writes it as
        ``<name>.<target_suffix>`` in ``outdir``, so it is not discovered —
        it follows from the source file's own name.

    Raises:
        IngestError: If LibreOffice is not installed, the conversion fails,
            or it runs without error but produces no output.
    """
    soffice = find_soffice()
    if soffice is None:
        raise IngestError(
            f"{path} is a legacy office file, and LibreOffice is what reads "
            f"it, but no LibreOffice installation was found on PATH or at "
            f"{MACOS_SOFFICE_PATH}. {INSTALL_HINT}"
        )

    target_format = target_suffix.lstrip(".")
    with tempfile.TemporaryDirectory(prefix="corpus-query-soffice-profile-") as profile:
        result = subprocess.run(
            [
                str(soffice),
                "--headless",
                "--norestore",
                f"-env:UserInstallation=file://{profile}",
                "--convert-to",
                target_format,
                "--outdir",
                str(outdir),
                str(path),
            ],
            capture_output=True,
            text=True,
        )

    converted = outdir / f"{path.stem}{target_suffix}"
    if result.returncode != 0 or not converted.is_file():
        detail = result.stderr.strip() or result.stdout.strip() or "no output"
        raise IngestError(
            f"Could not convert {path} to {target_suffix} with LibreOffice: {detail}"
        )
    repair_core_properties(converted)
    return converted


def repair_core_properties(path: Path) -> None:
    """Point a converted file's core properties relationship at the standard.

    LibreOffice writes the core properties relationship under
    ``officedocument`` where OOXML puts it under ``package``. The properties
    part itself is present and correct — author, title, and dates are all in
    ``docProps/core.xml`` — but a reader that looks the part up by its
    standard relationship type does not find it.

    The readers disagree about how much that matters, which is why this is
    not left to them. ``openpyxl`` finds the part anyway, so a converted
    workbook reads correctly; ``python-docx`` does not, and silently
    substitutes an empty properties part, so a converted document loses its
    author and is reported unreadable. LibreOffice happens to spell the
    relationship correctly when it writes ``.pptx``.

    Relying on that split would mean the Word path is broken and the Excel
    path works by a tolerance nobody promised. So the conversion repairs
    what it wrote, for every format, and hands the modern reader a file that
    says what OOXML says it should.

    Only the relationship type is rewritten, and only when the
    non-standard one is there. Every other part is copied across byte for
    byte, with its original compression, so the text a chunk is cut from is
    the text LibreOffice produced.

    Args:
        path: The converted file, rewritten in place if it needs it.
    """
    with zipfile.ZipFile(path) as archive:
        try:
            relationships = archive.read(PACKAGE_RELATIONSHIPS).decode("utf-8")
        except KeyError:
            return
        if LIBREOFFICE_CORE_PROPERTIES_RELATIONSHIP not in relationships:
            return
        entries = [(item, archive.read(item.filename)) for item in archive.infolist()]

    repaired = relationships.replace(
        LIBREOFFICE_CORE_PROPERTIES_RELATIONSHIP, CORE_PROPERTIES_RELATIONSHIP
    ).encode("utf-8")

    rewritten = path.with_name(f"{path.name}.repaired")
    with zipfile.ZipFile(rewritten, "w") as rebuilt:
        for item, data in entries:
            rebuilt.writestr(
                item, repaired if item.filename == PACKAGE_RELATIONSHIPS else data
            )
    rewritten.replace(path)


def converting_reader(target_suffix: str, modern_reader: Reader) -> Reader:
    """Build a reader for a legacy format that converts, then delegates.

    Args:
        target_suffix: The modern format to convert to, such as ``".docx"``.
        modern_reader: The reader for that modern format.

    Returns:
        A reader for the legacy format: it converts the file with
        LibreOffice into a temporary directory, reads the result with
        ``modern_reader``, and cleans the temporary directory up before
        returning — whether it succeeded or raised.
    """

    def read(path: Path, target_words: int) -> ReadDocument:
        with tempfile.TemporaryDirectory(prefix="corpus-query-soffice-out-") as outdir:
            converted = convert(path, target_suffix, Path(outdir))
            return modern_reader(converted, target_words)

    return read
