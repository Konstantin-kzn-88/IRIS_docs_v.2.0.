import hashlib
import json
import zipfile
from pathlib import Path

import pytest

from iris_v2.template_catalog import (
    TemplateCatalogError,
    TemplateCatalogService,
)


def make_docx(path: Path, text: str = "Шаблон") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
        archive.writestr("word/document.xml", f"<document>{text}</document>")


def make_project(path: Path) -> Path:
    (path / "input").mkdir(parents=True)
    (path / "project.json").write_text(
        '{"format_version": 1}\n', encoding="utf-8"
    )
    return path


def test_catalog_loads_profiles_and_documents(tmp_path: Path) -> None:
    root = tmp_path / "templates"
    make_docx(root / "ДПБ" / "02.docx")
    make_docx(root / "ДПБ" / "01.docx")
    (root / "Пустой").mkdir()

    profiles = TemplateCatalogService(root).load()

    assert [profile.name for profile in profiles] == ["ДПБ"]
    assert [document.name for document in profiles[0].documents] == [
        "01.docx",
        "02.docx",
    ]


def test_selection_copies_snapshot_and_writes_hashes(tmp_path: Path) -> None:
    root = tmp_path / "templates"
    source = root / "ДПБ_(экспл_СПТ)" / "Раздел.docx"
    make_docx(source, "Рабочий шаблон")
    project = make_project(tmp_path / "project")

    result = TemplateCatalogService(root).select(project, "ДПБ_(экспл_СПТ)")

    copied = project / "input" / "templates" / "selected" / "Раздел.docx"
    assert result.snapshot_directory == copied.parent
    assert copied.read_bytes() == source.read_bytes()
    config = json.loads(result.config_path.read_text(encoding="utf-8"))
    assert config["template_profile"] == "ДПБ_(экспл_СПТ)"
    assert config["documents"][0]["path"] == (
        "input/templates/selected/Раздел.docx"
    )
    assert config["documents"][0]["sha256"] == hashlib.sha256(
        source.read_bytes()
    ).hexdigest()


def test_reselection_replaces_previous_snapshot(tmp_path: Path) -> None:
    root = tmp_path / "templates"
    profile = root / "ДПБ"
    make_docx(profile / "Старый.docx")
    project = make_project(tmp_path / "project")
    service = TemplateCatalogService(root)
    service.select(project, "ДПБ")
    (profile / "Старый.docx").unlink()
    make_docx(profile / "Новый.docx")

    service.select(project, "ДПБ")

    snapshot = project / "input" / "templates" / "selected"
    assert not (snapshot / "Старый.docx").exists()
    assert (snapshot / "Новый.docx").is_file()


def test_invalid_docx_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "templates" / "ДПБ" / "broken.docx"
    path.parent.mkdir(parents=True)
    path.write_text("не docx", encoding="utf-8")

    with pytest.raises(TemplateCatalogError, match="не является документом DOCX"):
        TemplateCatalogService(tmp_path / "templates").load()
