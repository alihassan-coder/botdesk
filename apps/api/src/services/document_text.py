"""The text of a file a bot reads (`files.read`): text files as they are, PDFs through pypdf (BSD).

PDFs come from people and the web, so reading one is bounded: at most `MAX_PDF_PAGES` pages, in
a worker thread, given up after `PDF_SECONDS`. A PDF with no text layer (a scan) says so instead
of returning nothing.
"""

import asyncio
import io
import logging
from dataclasses import dataclass

from pypdf import PdfReader
from pypdf.errors import PdfReadError

logger = logging.getLogger(__name__)

MAX_PDF_PAGES = 200
PDF_SECONDS = 20.0

PDF = "application/pdf"
_TEXT_TYPES = {
    "application/json",
    "application/xml",
    "application/javascript",
    "application/x-yaml",
    "application/yaml",
    "application/toml",
    "application/sql",
    "image/svg+xml",
}


@dataclass(frozen=True)
class DocumentText:
    text: str
    note: str | None = None  # said to the bot alongside the text (pages left out, no text layer)


def is_text(content_type: str) -> bool:
    return content_type.startswith("text/") or content_type.split(";")[0] in _TEXT_TYPES


def is_readable(content_type: str) -> bool:
    """Whether `text_of` can give this file's words: text files and PDFs."""
    return is_text(content_type) or content_type.split(";")[0] == PDF


async def text_of(data: bytes, content_type: str) -> DocumentText | None:
    """The file's text, or None when it isn't a kind BotDesk reads (images, video, archives)."""
    if is_text(content_type):
        return DocumentText(data.decode("utf-8", errors="replace"))
    if content_type.split(";")[0] != PDF:
        return None
    try:
        return await asyncio.wait_for(asyncio.to_thread(_pdf_text, data), PDF_SECONDS)
    except TimeoutError:
        return DocumentText("", note="This PDF took too long to read. Ask a person to share its text another way.")


def _pdf_text(data: bytes) -> DocumentText:
    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            return DocumentText("", note="This PDF is protected with a password, so its text can't be read.")
        pages = reader.pages
        parts = []
        for number, page in enumerate(pages[:MAX_PDF_PAGES], start=1):
            words = (page.extract_text() or "").strip()
            if words:
                parts.append(f"--- Page {number} ---\n{words}")
    except (PdfReadError, ValueError, KeyError, TypeError, RecursionError) as error:
        logger.info("A PDF couldn't be read: %s", error)
        return DocumentText("", note="This PDF couldn't be read: it may be damaged.")
    notes = []
    if len(pages) > MAX_PDF_PAGES:
        notes.append(f"Only the first {MAX_PDF_PAGES} of its {len(pages)} pages were read.")
    if not parts:
        notes.append("This PDF has no text in it (perhaps a scan), so there's nothing to read as text.")
    return DocumentText("\n\n".join(parts), note=" ".join(notes) or None)
