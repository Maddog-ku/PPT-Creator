from io import BytesIO
from zipfile import ZipFile

from app.source_parser import extract_source_bytes


def test_extracts_utf8_text() -> None:
    result = extract_source_bytes("notes.txt", "產品策略\n市場機會".encode())

    assert result.status == "success"
    assert "產品策略" in result.text
    assert result.char_count == len(result.text)


def test_extracts_pptx_slides_in_numeric_order() -> None:
    buffer = BytesIO()
    with ZipFile(buffer, "w") as archive:
        archive.writestr(
            "ppt/slides/slide10.xml",
            '<p:sld xmlns:p="p" xmlns:a="a"><a:t>第十頁</a:t></p:sld>',
        )
        archive.writestr(
            "ppt/slides/slide2.xml",
            '<p:sld xmlns:p="p" xmlns:a="a"><a:t>第二頁 &amp; 資料</a:t></p:sld>',
        )

    result = extract_source_bytes("reference.pptx", buffer.getvalue())

    assert result.status == "success"
    assert result.text.index("第二頁 & 資料") < result.text.index("第十頁")


def test_reports_unsupported_source_without_throwing() -> None:
    result = extract_source_bytes("photo.png", b"not an image")

    assert result.status == "error"
    assert "僅支援" in (result.error or "")
