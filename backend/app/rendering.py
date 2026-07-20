from __future__ import annotations

from io import BytesIO
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import uuid
from zipfile import ZIP_DEFLATED, BadZipFile, ZipFile


MAX_PRESENTATION_BYTES = 60 * 1024 * 1024


class PresentationRenderError(RuntimeError):
    pass


def presentation_dir(storage_dir: str, presentation_id: uuid.UUID) -> Path:
    return Path(storage_dir).resolve() / str(presentation_id)


def presentation_asset_paths(
    storage_dir: str, presentation_id: uuid.UUID
) -> tuple[Path, Path, list[Path]]:
    output_dir = presentation_dir(storage_dir, presentation_id)
    pptx = output_dir / "presentation.pptx"
    pdf = output_dir / "presentation.pdf"
    previews = sorted(output_dir.glob("slide-*.png"), key=_preview_number)
    return pptx, pdf, previews


def _preview_number(path: Path) -> int:
    match = re.search(r"slide-(\d+)\.png$", path.name)
    return int(match.group(1)) if match else 0


def _validate_pptx(data: bytes) -> int:
    if not data:
        raise PresentationRenderError("PPTX 檔案內容為空")
    if len(data) > MAX_PRESENTATION_BYTES:
        raise PresentationRenderError("PPTX 檔案不可超過 60 MB")
    try:
        with ZipFile(BytesIO(data)) as archive:
            slides = [
                name
                for name in archive.namelist()
                if re.fullmatch(r"ppt/slides/slide\d+\.xml", name)
            ]
    except BadZipFile as exc:
        raise PresentationRenderError("PPTX 格式不正確") from exc
    if not slides:
        raise PresentationRenderError("PPTX 中找不到投影片")
    return len(slides)


def _run(command: list[str], timeout: int) -> None:
    try:
        result = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        raise PresentationRenderError("正式輸出渲染逾時") from exc
    if result.returncode != 0:
        message = (result.stderr or result.stdout or "未知錯誤").strip()
        raise PresentationRenderError(f"正式輸出渲染失敗：{message[-500:]}")


def render_presentation(
    storage_dir: str, presentation_id: uuid.UUID, data: bytes
) -> tuple[int, list[Path]]:
    expected_slides = _validate_pptx(data)
    libreoffice = shutil.which("libreoffice") or shutil.which("soffice")
    pdftoppm = shutil.which("pdftoppm")
    if not libreoffice or not pdftoppm:
        raise PresentationRenderError("伺服器缺少 LibreOffice 或 Poppler")

    output_dir = presentation_dir(storage_dir, presentation_id)
    storage_root = output_dir.parent
    storage_root.mkdir(parents=True, exist_ok=True)
    staging_dir = Path(
        tempfile.mkdtemp(prefix=f".{presentation_id}-render-", dir=storage_root)
    )
    backup_dir = storage_root / f".{presentation_id}-backup-{uuid.uuid4()}"
    try:
        pptx = staging_dir / "presentation.pptx"
        pdf = staging_dir / "presentation.pdf"
        pptx.write_bytes(data)

        with tempfile.TemporaryDirectory(prefix="ppt-creator-lo-") as profile:
            profile_uri = Path(profile).resolve().as_uri()
            _run(
                [
                    libreoffice,
                    f"-env:UserInstallation={profile_uri}",
                    "--headless",
                    "--convert-to",
                    "pdf",
                    "--outdir",
                    str(staging_dir),
                    str(pptx),
                ],
                timeout=180,
            )
        if not pdf.exists():
            raise PresentationRenderError("LibreOffice 未產生 PDF")
        _run(
            [pdftoppm, "-png", "-r", "120", str(pdf), str(staging_dir / "slide")],
            timeout=180,
        )
        previews = sorted(staging_dir.glob("slide-*.png"), key=_preview_number)
        if len(previews) != expected_slides:
            raise PresentationRenderError(
                f"預覽頁數不一致：PPTX {expected_slides} 頁，預覽 {len(previews)} 頁"
            )

        if output_dir.exists():
            output_dir.rename(backup_dir)
        try:
            staging_dir.rename(output_dir)
        except Exception:
            if backup_dir.exists() and not output_dir.exists():
                backup_dir.rename(output_dir)
            raise
        if backup_dir.exists():
            shutil.rmtree(backup_dir, ignore_errors=True)
        return expected_slides, sorted(
            output_dir.glob("slide-*.png"), key=_preview_number
        )
    finally:
        if staging_dir.exists():
            shutil.rmtree(staging_dir)
        if backup_dir.exists() and not output_dir.exists():
            backup_dir.rename(output_dir)
        elif backup_dir.exists():
            shutil.rmtree(backup_dir, ignore_errors=True)


def add_fade_transitions(source: Path, destination: Path) -> None:
    transition = '<p:transition spd="med"><p:fade/></p:transition>'
    with ZipFile(source) as input_archive, ZipFile(
        destination, "w", compression=ZIP_DEFLATED
    ) as output_archive:
        for item in input_archive.infolist():
            data = input_archive.read(item.filename)
            if re.fullmatch(r"ppt/slides/slide\d+\.xml", item.filename):
                xml = data.decode("utf-8")
                xml = re.sub(r"<p:transition\b.*?</p:transition>", "", xml, flags=re.DOTALL)
                xml = re.sub(r"<p:transition\b[^>]*/>", "", xml)
                marker = "<p:timing>"
                if marker in xml:
                    xml = xml.replace(marker, transition + marker, 1)
                else:
                    xml = xml.replace("</p:sld>", transition + "</p:sld>", 1)
                data = xml.encode("utf-8")
            output_archive.writestr(item, data)


def remove_presentation_files(storage_dir: str, presentation_id: uuid.UUID) -> None:
    target = presentation_dir(storage_dir, presentation_id)
    if target.parent == Path(storage_dir).resolve() and target.exists():
        shutil.rmtree(target)
