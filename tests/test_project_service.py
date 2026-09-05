from pathlib import Path
import os

import pytest

from iris_v2.service import CreateProjectData, ProjectError, ProjectService


def project_data() -> CreateProjectData:
    return CreateProjectData(
        name="Тестовый проект",
        code="TEST-001",
        organization_name="АО Пример",
        opo_name="Тестовый ОПО",
        opo_registration_number="А00-00000-0000",
    )


def test_create_and_open_project(tmp_path: Path) -> None:
    target = tmp_path / "project"
    service = ProjectService()

    created = service.create(target, project_data())
    opened = service.open(target)

    assert created == opened
    assert opened.code == "TEST-001"
    assert (target / "project.sqlite3").is_file()
    assert (target / "project.json").is_file()
    assert (target / "input").is_dir()
    assert (target / "output").is_dir()


def test_existing_directory_is_not_overwritten(tmp_path: Path) -> None:
    target = tmp_path / "project"
    target.mkdir()
    marker = target / "important.txt"
    marker.write_text("keep", encoding="utf-8")

    with pytest.raises(ProjectError):
        ProjectService().create(target, project_data())

    assert marker.read_text(encoding="utf-8") == "keep"


def test_empty_field_is_rejected(tmp_path: Path) -> None:
    data = CreateProjectData("", "CODE", "ORG", "OPO", "NUMBER")

    with pytest.raises(ProjectError):
        ProjectService().create(tmp_path / "project", data)


def test_minimal_window_starts() -> None:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    try:
        from PySide6.QtWidgets import QApplication, QPushButton
        from iris_v2.gui import MainWindow
    except ImportError as exc:
        pytest.skip(f"Qt недоступен в текущей системе: {exc}")

    application = QApplication.instance() or QApplication([])
    window = MainWindow()
    try:
        assert window.windowTitle() == "IRIS v2"
        assert window.findChild(QPushButton, "create_project_button") is not None
        assert window.findChild(QPushButton, "open_project_button") is not None
    finally:
        window.close()
