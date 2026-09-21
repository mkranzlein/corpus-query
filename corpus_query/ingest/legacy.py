"""Reading legacy office formats by converting them first.

The system reads `.docx`, `.pptx`, and `.xlsx`. A `.doc`, `.ppt`, or `.xls`
file is not parsed on its own terms: it is converted to its modern equivalent
with LibreOffice headless, and the result is handed to the reader that format
already has. No model sees raw bytes at either step, and the conversion is
deterministic, so the chunks that come out match the file they came from.

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
        The path of the converted file. LibreOffice writes it as
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
    return converted


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
