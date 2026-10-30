from __future__ import annotations

import logging
import math
import re
from collections import Counter
from dataclasses import dataclass
from typing import Any

try:
    import pymupdf
except ImportError:
    try:
        import fitz as pymupdf  # type: ignore[no-redef]
    except ImportError:
        pymupdf = None  # type: ignore[assignment]

from code_review.config import get_settings

logger = logging.getLogger(__name__)

PDF_MAGIC = b"%PDF-"
MAX_FILENAME_LEN = 128

DIFF_EXTENSIONS = {".diff", ".patch"}
CODE_EXTENSIONS = {
    ".py",
    ".js",
    ".ts",
    ".tsx",
    ".jsx",
    ".json",
    ".yaml",
    ".yml",
}
TEXT_EXTENSIONS = {".txt", ".md", ".log"}
ALLOWED_EXTENSIONS = {".pdf"} | DIFF_EXTENSIONS | CODE_EXTENSIONS | TEXT_EXTENSIONS


class DocumentProcessingError(Exception):
        pass


class DocumentValidationError(DocumentProcessingError):
        pass


class DocumentExtractionError(DocumentProcessingError):
        pass


@dataclass
class ProcessedDocument:
    filename: str
    file_type: str
    mime_type: str
    file_size: int
    extracted_text: str
    page_count: int
    chunks: list[dict[str, Any]]


def sanitize_filename(filename: str) -> str:
    clean = filename.replace("\\", "/").split("/")[-1].strip()

    clean = re.sub(r"[\x00-\x1f\x7f-\x9f]", "", clean)

    clean = re.sub(r"[^\w\s\.\-\(\)\[\]]", "_", clean)
    clean = clean.strip()
    if not clean:
        clean = "document.txt"
    if len(clean) > MAX_FILENAME_LEN:
        parts = clean.rsplit(".", 1)
        if len(parts) == 2:
            ext = "." + parts[1]
            clean = parts[0][: MAX_FILENAME_LEN - len(ext)] + ext
        else:
            clean = clean[:MAX_FILENAME_LEN]
    return clean


def _get_chunk_content(c: Any) -> str:
    if hasattr(c, "content"):
        return c.content or ""
    if isinstance(c, dict):
        return c.get("content", "") or ""
    return str(c)


def _get_chunk_page(c: Any) -> int:
    if hasattr(c, "page_number"):
        return c.page_number or 0
    if isinstance(c, dict):
        return c.get("page_number", 0) or 0
    return 0


def _get_chunk_index(c: Any) -> int:
    if hasattr(c, "chunk_index"):
        return c.chunk_index or 0
    if isinstance(c, dict):
        return c.get("chunk_index", 0) or 0
    return 0


class DocumentProcessor:
    @classmethod
    def validate_and_process(
        cls,
        file_bytes: bytes,
        raw_filename: str,
        client_mime: str | None = None,
    ) -> ProcessedDocument:
        settings = get_settings()
        max_bytes = settings.max_attachment_size_mb * 1024 * 1024

        if not file_bytes or len(file_bytes) == 0:
            raise DocumentValidationError("The uploaded file is empty (0 bytes).")

        if len(file_bytes) > max_bytes:
            mb = len(file_bytes) / (1024 * 1024)
            raise DocumentValidationError(
                f"File size ({mb:.1f} MB) exceeds maximum allowed limit of "
                f"{settings.max_attachment_size_mb} MB."
            )

        clean_name = sanitize_filename(raw_filename)
        dot_idx = clean_name.rfind(".")
        if dot_idx == -1:
            raise DocumentValidationError(
                "File has no extension. Supported formats include .pdf, .txt, .diff, .patch, "
                "and code files."
            )

        ext = clean_name[dot_idx:].lower()
        if ext not in ALLOWED_EXTENSIONS:
            raise DocumentValidationError(
                f"Unsupported file type '{ext}'. Supported formats include .pdf, .txt, .diff, "
                ".patch, and code files."
            )

        if ext == ".pdf":
            file_type = "pdf"
            mime_type = "application/pdf"
            extracted_text, page_count, pages = cls._extract_pdf(file_bytes, clean_name)
        elif ext in DIFF_EXTENSIONS:
            file_type = "diff"
            mime_type = "text/x-diff"
            extracted_text, page_count, pages = cls._extract_txt(file_bytes, clean_name)
        elif ext in CODE_EXTENSIONS:
            file_type = "code"
            if ext == ".json":
                mime_type = "application/json"
            elif ext in (".yaml", ".yml"):
                mime_type = "text/yaml"
            else:
                mime_type = "text/plain"
            extracted_text, page_count, pages = cls._extract_txt(file_bytes, clean_name)
        else:
            file_type = "txt"
            mime_type = "text/markdown" if ext == ".md" else "text/plain"
            extracted_text, page_count, pages = cls._extract_txt(file_bytes, clean_name)

        chunks = cls._create_page_aware_chunks(
            pages=pages,
            chunk_size=settings.attachment_chunk_size_chars,
            overlap=settings.attachment_chunk_overlap_chars,
        )

        logger.info(
            "Processed attachment '%s' (%s, %d bytes): %d pages, %d chunks",
            clean_name,
            file_type,
            len(file_bytes),
            page_count,
            len(chunks),
        )

        return ProcessedDocument(
            filename=clean_name,
            file_type=file_type,
            mime_type=mime_type,
            file_size=len(file_bytes),
            extracted_text=extracted_text,
            page_count=page_count,
            chunks=chunks,
        )

    @classmethod
    def _extract_pdf(
        cls, file_bytes: bytes, filename: str
    ) -> tuple[str, int, list[tuple[int, str]]]:
        header_sample = file_bytes[:1024]
        if PDF_MAGIC not in header_sample:
            raise DocumentValidationError("Invalid PDF file: Missing %PDF- signature.")

        if pymupdf is None:
            raise DocumentExtractionError(
                "PDF extraction engine (PyMuPDF) is not installed on the server."
            )

        try:
            doc = pymupdf.open(stream=file_bytes, filetype="pdf")
        except Exception as exc:
            raise DocumentExtractionError(
                f"Failed to open PDF document. File may be corrupted or malformed: {exc}"
            ) from exc

        try:
            if doc.is_encrypted:
                raise DocumentExtractionError(
                    "Encrypted or password-protected PDFs are not supported. "
                    "Please remove encryption before uploading."
                )

            page_count = len(doc)
            if page_count == 0:
                raise DocumentExtractionError("PDF document contains 0 pages.")

            pages: list[tuple[int, str]] = []
            full_parts: list[str] = []
            total_non_whitespace_chars = 0

            for page_idx in range(page_count):
                page_num = page_idx + 1
                try:
                    page = doc[page_idx]
                    page_text = page.get_text("text") or ""
                    cleaned = page_text.strip()
                    if cleaned:
                        total_non_whitespace_chars += len(cleaned)
                    pages.append((page_num, cleaned))
                    full_parts.append(f"--- [Page {page_num} of {page_count}] ---\n{cleaned}")
                except Exception as page_err:
                    logger.warning("Error reading page %d of %s: %s", page_num, filename, page_err)
                    pages.append((page_num, ""))

            if total_non_whitespace_chars == 0:
                raise DocumentExtractionError(
                    "This PDF contains no extractable text. Scanned or image-only documents "
                    "require OCR, which is currently not supported."
                )

            full_text = "\n\n".join(full_parts).strip()
            return full_text, page_count, pages

        finally:
            doc.close()

    @classmethod
    def _extract_txt(
        cls, file_bytes: bytes, filename: str
    ) -> tuple[str, int, list[tuple[int, str]]]:
        if b"\x00" in file_bytes[:4096]:
            raise DocumentValidationError(
                "Invalid text file: Binary data detected. Only plain text files are supported."
            )

        decoded_text: str | None = None
        if file_bytes.startswith((b"\xff\xfe", b"\xfe\xff")):
            candidate_encodings = ("utf-16", "utf-8-sig", "utf-8", "cp1252", "latin-1")
        else:
            candidate_encodings = ("utf-8-sig", "utf-8", "cp1252", "latin-1", "utf-16")

        for enc in candidate_encodings:
            try:
                decoded_text = file_bytes.decode(enc)
                break
            except UnicodeDecodeError:
                continue

        if decoded_text is None:
            raise DocumentExtractionError(
                "Could not decode text file using supported character encodings "
                "(UTF-8, UTF-16, Latin-1)."
            )

        clean_text = decoded_text.strip()
        if not clean_text:
            raise DocumentExtractionError("The uploaded text file contains no readable text.")

        return clean_text, 1, [(1, clean_text)]

    @classmethod
    def _create_page_aware_chunks(
        cls,
        pages: list[tuple[int, str]],
        chunk_size: int = 2000,
        overlap: int = 200,
    ) -> list[dict[str, Any]]:
        chunks: list[dict[str, Any]] = []
        chunk_index = 0

        for page_num, page_text in pages:
            if not page_text:
                continue

            if len(page_text) <= chunk_size:
                chunks.append(
                    {
                        "chunk_index": chunk_index,
                        "page_number": page_num,
                        "content": page_text,
                        "token_estimate": len(page_text.split()),
                    }
                )
                chunk_index += 1
                continue

            start = 0
            text_len = len(page_text)

            while start < text_len:
                end = min(start + chunk_size, text_len)
                if end < text_len:
                    para_break = page_text.rfind("\n\n", start, end)
                    if para_break != -1 and para_break > start + (chunk_size // 2):
                        end = para_break
                    else:
                        sentence_break = page_text.rfind(". ", start, end)
                        if sentence_break != -1 and sentence_break > start + (chunk_size // 2):
                            end = sentence_break + 1
                        else:
                            space_break = page_text.rfind(" ", start, end)
                            if space_break != -1 and space_break > start + (chunk_size // 2):
                                end = space_break

                chunk_content = page_text[start:end].strip()
                if chunk_content:
                    chunks.append(
                        {
                            "chunk_index": chunk_index,
                            "page_number": page_num,
                            "content": chunk_content,
                            "token_estimate": len(chunk_content.split()),
                        }
                    )
                    chunk_index += 1

                if end >= text_len:
                    break

                start = max(start + 1, end - overlap)

        return chunks

    @classmethod
    def retrieve_relevant_chunks(
        cls,
        chunk_records: list[Any],
        query: str,
        top_k: int = 4,
        max_context_chars: int = 8000,
    ) -> list[Any]:
        if not chunk_records:
            return []

        total_chars = sum(len(_get_chunk_content(c)) for c in chunk_records)
        if total_chars <= max_context_chars and len(chunk_records) <= top_k:
            return sorted(chunk_records, key=lambda c: (_get_chunk_page(c), _get_chunk_index(c)))

        query_terms = [t for t in re.findall(r"\b\w{2,}\b", query.lower())]
        if not query_terms:
            return sorted(
                chunk_records[:top_k], key=lambda c: (_get_chunk_page(c), _get_chunk_index(c))
            )

        n_docs = len(chunk_records)
        doc_frequencies: Counter[str] = Counter()
        chunk_term_counts: list[Counter[str]] = []

        for c in chunk_records:
            tokens = re.findall(r"\b\w{2,}\b", _get_chunk_content(c).lower())
            counts = Counter(tokens)
            chunk_term_counts.append(counts)
            for term in set(tokens):
                if term in query_terms:
                    doc_frequencies[term] += 1

        k1 = 1.5
        b = 0.75
        avg_dl = sum(len(_get_chunk_content(c).split()) for c in chunk_records) / max(1, n_docs)

        scored_chunks: list[tuple[float, Any]] = []

        for idx, c in enumerate(chunk_records):
            score = 0.0
            counts = chunk_term_counts[idx]
            dl = len(_get_chunk_content(c).split())

            for term in query_terms:
                if term not in counts:
                    continue
                tf = counts[term]
                df = doc_frequencies[term]

                idf = math.log(1.0 + (n_docs - df + 0.5) / (df + 0.5))

                term_score = idf * ((tf * (k1 + 1.0)) / (tf + k1 * (1.0 - b + b * (dl / avg_dl))))
                score += term_score

            scored_chunks.append((score, c))

        scored_chunks.sort(key=lambda x: x[0], reverse=True)

        selected: list[Any] = []
        accumulated_chars = 0

        for score, chunk in scored_chunks:
            chunk_len = len(_get_chunk_content(chunk))
            if accumulated_chars + chunk_len > max_context_chars and len(selected) >= 1:
                break
            selected.append(chunk)
            accumulated_chars += chunk_len
            if len(selected) >= top_k:
                break

        if not selected:
            selected = chunk_records[: min(top_k, len(chunk_records))]

        return sorted(selected, key=lambda c: (_get_chunk_page(c), _get_chunk_index(c)))

    @classmethod
    def build_document_context_block(
        cls,
        attachments: list[Any],
        query: str = "",
        max_total_chars: int = 10000,
    ) -> str:
        if not attachments:
            return ""

        context_sections: list[str] = []
        chars_per_attachment = max_total_chars // max(1, len(attachments))

        for att in attachments:
            fname = getattr(att, "filename", "attached_document")
            file_type = getattr(att, "file_type", "")
            ext = ("." + fname.rsplit(".", 1)[-1].lower()) if "." in fname else ""
            page_count = getattr(att, "page_count", 1)
            extracted = getattr(att, "extracted_text", "")

            if file_type == "diff" or ext in DIFF_EXTENSIONS:
                diff_text = extracted
                if len(diff_text) > chars_per_attachment:
                    diff_text = (
                        diff_text[:chars_per_attachment]
                        + "\n... [Diff truncated to stay within limits]"
                    )
                section = f"### Attached Diff File: {fname}\n```diff\n{diff_text}\n```"
                context_sections.append(section)
                continue

            chunks = getattr(att, "chunks", [])
            if len(extracted) <= chars_per_attachment or not chunks or len(chunks) <= 1:
                if file_type == "code" or ext in CODE_EXTENSIONS:
                    code_lang = ext.lstrip(".") if ext else ""
                    section = f"### Attached Code File: {fname}\n```{code_lang}\n{extracted}\n```"
                else:
                    section = f"### Document: {fname} ({page_count} pages)\n{extracted}"
                context_sections.append(section)
                continue

            if query:
                relevant_chunks = cls.retrieve_relevant_chunks(
                    chunk_records=chunks,
                    query=query,
                    top_k=4,
                    max_context_chars=chars_per_attachment,
                )
                chunk_texts: list[str] = []
                for chk in relevant_chunks:
                    page_num = _get_chunk_page(chk)
                    page_str = f"Page {page_num}" if page_num else "Section"
                    content = _get_chunk_content(chk)
                    chunk_texts.append(f"[{fname} | {page_str}]\n{content}")

                section = f"### Document: {fname} ({page_count} pages)\n" + "\n\n".join(
                    chunk_texts
                )
                context_sections.append(section)
            else:
                truncated = extracted[:chars_per_attachment] + "\n... [Context truncated]"
                section = f"### Document: {fname} ({page_count} pages)\n{truncated}"
                context_sections.append(section)
        return "\n\n".join(context_sections)
