from __future__ import annotations

from html import unescape
from io import BytesIO
from pathlib import Path
import re
from zipfile import BadZipFile, ZipFile

from pypdf import PdfReader

from .schemas import SourceExtractionItem


MAX_SOURCE_FILE_BYTES = 25 * 1024 * 1024
SUPPORTED_SOURCE_SUFFIXES = {".txt", ".md", ".pdf", ".pptx"}


def _decode_text(data: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "big5"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise ValueError("文字檔編碼不支援，請使用 UTF-8 或 Big5")


def _extract_pdf(data: bytes) -> str:
    reader = PdfReader(BytesIO(data))
    pages: list[str] = []
    for index, page in enumerate(reader.pages, start=1):
        text = (page.extract_text() or "").strip()
        if text:
            pages.append(f"[PDF 第 {index} 頁]\n{text}")
    if not pages:
        raise ValueError("PDF 沒有可抽取的文字，可能是掃描檔")
    return "\n\n".join(pages)


def _slide_number(name: str) -> int:
    match = re.search(r"slide(\d+)\.xml$", name)
    return int(match.group(1)) if match else 0


def _extract_pptx(data: bytes) -> str:
    try:
        with ZipFile(BytesIO(data)) as archive:
            slide_names = sorted(
                (
                    name
                    for name in archive.namelist()
                    if re.fullmatch(r"ppt/slides/slide\d+\.xml", name)
                ),
                key=_slide_number,
            )
            slides: list[str] = []
            for index, name in enumerate(slide_names, start=1):
                xml = archive.read(name).decode("utf-8", errors="replace")
                values = [
                    " ".join(unescape(value).split())
                    for value in re.findall(r"<a:t(?:\s[^>]*)?>(.*?)</a:t>", xml, re.DOTALL)
                ]
                text = "\n".join(value for value in values if value)
                if text:
                    slides.append(f"[PPTX 第 {index} 頁]\n{text}")
    except BadZipFile as exc:
        raise ValueError("PPTX 檔案損毀或格式不正確") from exc
    if not slides:
        raise ValueError("PPTX 沒有可抽取的文字")
    return "\n\n".join(slides)


def extract_source_bytes(filename: str, data: bytes) -> SourceExtractionItem:
    safe_name = Path(filename or "未命名檔案").name
    suffix = Path(safe_name).suffix.lower()
    try:
        if suffix not in SUPPORTED_SOURCE_SUFFIXES:
            raise ValueError("僅支援 TXT、Markdown、PDF 與 PPTX")
        if not data:
            raise ValueError("檔案內容為空")
        if len(data) > MAX_SOURCE_FILE_BYTES:
            raise ValueError("單一檔案不可超過 25 MB")
        if suffix in {".txt", ".md"}:
            text = _decode_text(data).strip()
        elif suffix == ".pdf":
            text = _extract_pdf(data)
        else:
            text = _extract_pptx(data)
        if not text:
            raise ValueError("檔案沒有可用文字")
        return SourceExtractionItem(
            filename=safe_name,
            status="success",
            text=text,
            char_count=len(text),
        )
    except Exception as exc:
        return SourceExtractionItem(
            filename=safe_name,
            status="error",
            error=str(exc),
        )
