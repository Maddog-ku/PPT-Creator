from pathlib import Path
from zipfile import ZipFile

import pytest

import app.rendering as rendering
from app.rendering import add_fade_transitions


def test_adds_fade_transition_to_every_slide(tmp_path: Path) -> None:
    source = tmp_path / "source.pptx"
    destination = tmp_path / "animated.pptx"
    with ZipFile(source, "w") as archive:
        archive.writestr(
            "ppt/slides/slide1.xml",
            '<p:sld xmlns:p="p"><p:cSld/><p:timing/></p:sld>',
        )
        archive.writestr("docProps/app.xml", "metadata")

    add_fade_transitions(source, destination)

    with ZipFile(destination) as archive:
        slide_xml = archive.read("ppt/slides/slide1.xml").decode()
        assert '<p:transition spd="med"><p:fade/></p:transition>' in slide_xml
        assert archive.read("docProps/app.xml") == b"metadata"


def test_failed_render_preserves_previous_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    presentation_id = rendering.uuid.uuid4()
    output_dir = rendering.presentation_dir(str(tmp_path), presentation_id)
    output_dir.mkdir()
    (output_dir / "presentation.pptx").write_bytes(b"previous-pptx")
    (output_dir / "presentation.pdf").write_bytes(b"previous-pdf")
    (output_dir / "slide-1.png").write_bytes(b"previous-preview")

    source = tmp_path / "candidate.pptx"
    with ZipFile(source, "w") as archive:
        archive.writestr("ppt/slides/slide1.xml", "<p:sld/>")

    monkeypatch.setattr(rendering.shutil, "which", lambda command: command)

    def fail_render(command: list[str], timeout: int) -> None:
        raise rendering.PresentationRenderError("模擬渲染失敗")

    monkeypatch.setattr(rendering, "_run", fail_render)

    with pytest.raises(rendering.PresentationRenderError, match="模擬渲染失敗"):
        rendering.render_presentation(
            str(tmp_path), presentation_id, source.read_bytes()
        )

    assert (output_dir / "presentation.pptx").read_bytes() == b"previous-pptx"
    assert (output_dir / "presentation.pdf").read_bytes() == b"previous-pdf"
    assert (output_dir / "slide-1.png").read_bytes() == b"previous-preview"
    assert not list(tmp_path.glob(f".{presentation_id}-render-*"))


def test_successful_render_replaces_previous_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    presentation_id = rendering.uuid.uuid4()
    output_dir = rendering.presentation_dir(str(tmp_path), presentation_id)
    output_dir.mkdir()
    (output_dir / "presentation.pptx").write_bytes(b"previous-pptx")
    (output_dir / "presentation.pdf").write_bytes(b"previous-pdf")
    (output_dir / "slide-1.png").write_bytes(b"previous-preview")

    source = tmp_path / "candidate.pptx"
    with ZipFile(source, "w") as archive:
        archive.writestr("ppt/slides/slide1.xml", "<p:sld/>")

    monkeypatch.setattr(rendering.shutil, "which", lambda command: command)

    def create_outputs(command: list[str], timeout: int) -> None:
        if "--convert-to" in command:
            output_index = command.index("--outdir") + 1
            Path(command[output_index], "presentation.pdf").write_bytes(b"new-pdf")
        else:
            Path(f"{command[-1]}-1.png").write_bytes(b"new-preview")

    monkeypatch.setattr(rendering, "_run", create_outputs)

    slide_count, previews = rendering.render_presentation(
        str(tmp_path), presentation_id, source.read_bytes()
    )

    assert slide_count == 1
    assert previews == [output_dir / "slide-1.png"]
    assert (output_dir / "presentation.pptx").read_bytes() == source.read_bytes()
    assert (output_dir / "presentation.pdf").read_bytes() == b"new-pdf"
    assert (output_dir / "slide-1.png").read_bytes() == b"new-preview"
    assert not list(tmp_path.glob(f".{presentation_id}-backup-*"))
