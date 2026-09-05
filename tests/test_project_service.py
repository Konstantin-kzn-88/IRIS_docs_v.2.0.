from pathlib import Path
import os
import json

import pytest

from iris_v2.service import CreateProjectData, ProjectError, ProjectService
from iris_v2.catalog import load_organizations


EXAMPLE_CATALOG = (
    Path(__file__).parents[1] / "src" / "iris_v2" / "data" / "organization.json"
)


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


def test_organization_catalog_is_loaded() -> None:
    organizations = load_organizations(EXAMPLE_CATALOG)

    assert organizations[0].name == "АО Пример"
    assert organizations[0].full_name == "Акционерное общество Пример"
    assert organizations[0].facilities[0].registration_number == "А00-00000-0000"
    assert organizations[0].facilities[0].data["sanitary_protection_zone_m"] == 0


def test_snapshots_are_saved_inside_project(tmp_path: Path) -> None:
    organization = load_organizations(EXAMPLE_CATALOG)[0]
    facility = organization.facilities[0]
    data = CreateProjectData(
        name="Проект со снимком",
        code="SNAPSHOT-001",
        organization_name=organization.name,
        opo_name=facility.name,
        opo_registration_number=facility.registration_number,
        organization_snapshot=organization.snapshot(),
        opo_snapshot=facility.snapshot(),
    )

    project = ProjectService().create(tmp_path / "snapshot_project", data)

    assert project.organization_snapshot["organization"]["ids"]["inn"] == "0000000000"
    assert "sites" not in project.organization_snapshot
    assert project.opo_snapshot["sanitary_protection_zone_m"] == 0
    assert project.opo_snapshot["site_id"] == "opo_0001"


def test_local_catalog_has_priority(tmp_path: Path, monkeypatch) -> None:
    first_directory = tmp_path / "organizations" / "first"
    first_directory.mkdir(parents=True)
    local_catalog = first_directory / "organization.json"
    local_catalog.write_text(
        json.dumps(
            [
                {
                    "id": 77,
                    "organization": {
                        "short_name": "Локальная организация",
                        "full_name": "Полное название",
                    },
                    "future_section": {"new_field": "сохранить без изменений"},
                    "sites": [
                        {
                            "site_id": "opo_local",
                            "name": "Локальный ОПО",
                            "reg_number": "LOCAL-001",
                            "future_opo_field": {"value": 123},
                        }
                    ],
                }
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    second_directory = tmp_path / "organizations" / "second"
    second_directory.mkdir()
    (second_directory / "organization.json").write_text(
        json.dumps(
            [
                {
                    "id": 78,
                    "organization": {
                        "short_name": "Вторая организация",
                        "full_name": "Вторая организация",
                    },
                    "sites": [
                        {
                            "site_id": "opo_second",
                            "name": "Второй ОПО",
                            "reg_number": "SECOND-001",
                            "sanitary_protection_zone_m": "89-196",
                        }
                    ],
                }
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)

    organizations = load_organizations()

    assert len(organizations) == 2
    assert organizations[0].name == "Локальная организация"
    assert organizations[0].facilities[0].name == "Локальный ОПО"
    assert organizations[0].snapshot()["future_section"]["new_field"] == (
        "сохранить без изменений"
    )
    assert organizations[0].facilities[0].snapshot()["future_opo_field"]["value"] == 123
    assert organizations[1].name == "Вторая организация"
    assert (
        organizations[1].facilities[0].snapshot()["sanitary_protection_zone_m"]
        == "89-196"
    )


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
        common_button = window.findChild(QPushButton, "project_common_button")
        assert common_button is not None
        assert not common_button.isEnabled()
        substances_button = window.findChild(QPushButton, "substances_button")
        assert substances_button is not None
        assert not substances_button.isEnabled()
        equipment_button = window.findChild(QPushButton, "equipment_button")
        assert equipment_button is not None
        assert not equipment_button.isEnabled()
        amount_button = window.findChild(QPushButton, "amount_button")
        assert amount_button is not None
        assert not amount_button.isEnabled()
        validation_button = window.findChild(QPushButton, "validation_button")
        assert validation_button is not None
        assert not validation_button.isEnabled()
        config_button = window.findChild(
            QPushButton, "calculation_config_button"
        )
        assert config_button is not None
        assert not config_button.isEnabled()
        scenarios_button = window.findChild(
            QPushButton, "typical_scenarios_button"
        )
        assert scenarios_button is not None
        assert scenarios_button.isEnabled()
        cases_button = window.findChild(
            QPushButton, "calculation_cases_button"
        )
        assert cases_button is not None
        assert not cases_button.isEnabled()
        frequency_button = window.findChild(QPushButton, "frequency_button")
        assert frequency_button is not None
        assert not frequency_button.isEnabled()
        release_button = window.findChild(QPushButton, "release_button")
        assert release_button is not None
        assert not release_button.isEnabled()
        spill_button = window.findChild(QPushButton, "spill_button")
        assert spill_button is not None
        assert not spill_button.isEnabled()
        evaporation_button = window.findChild(
            QPushButton, "evaporation_button"
        )
        assert evaporation_button is not None
        assert not evaporation_button.isEnabled()
    finally:
        window.close()
