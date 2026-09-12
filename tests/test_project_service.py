from pathlib import Path
import os
import json

import pytest

from iris_v2.service import CreateProjectData, ProjectError, ProjectService
from iris_v2.catalog import load_organizations, update_public_information_contact


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


def test_update_personnel_in_existing_project(tmp_path: Path) -> None:
    target = tmp_path / "project"
    service = ProjectService()
    service.create(target, project_data())

    updated = service.update_personnel(target, 120, 35, 0.25)

    assert updated.opo_snapshot["personnel"] == {
        "employees_count": 120,
        "employees_other_opo_count": 35,
        "presence_probability": 0.25,
    }
    assert service.open(target).opo_snapshot == updated.opo_snapshot


def test_update_public_information_contact_in_existing_project(tmp_path: Path) -> None:
    target = tmp_path / "project"
    service = ProjectService()
    organization = load_organizations(EXAMPLE_CATALOG)[0]
    facility = organization.facilities[0]
    service.create(
        target,
        CreateProjectData(
            name="Проект",
            code="CONTACT-001",
            organization_name=organization.name,
            opo_name=facility.name,
            opo_registration_number=facility.registration_number,
            organization_snapshot=organization.snapshot(),
            opo_snapshot=facility.snapshot(),
        ),
    )

    updated = service.update_organization_public_information_contact(
        target, " Начальник ", " Иванов Иван Иванович ", " +7 900 000-00-00 "
    )

    assert updated.organization_snapshot["organization"][
        "public_information_contact"
    ] == {
        "position": "Начальник",
        "full_name": "Иванов Иван Иванович",
        "phone": "+7 900 000-00-00",
    }


def test_update_public_information_contact_in_catalog(tmp_path: Path) -> None:
    catalog_path = tmp_path / "organization.json"
    catalog_path.write_text(
        EXAMPLE_CATALOG.read_text(encoding="utf-8"), encoding="utf-8"
    )
    organization = load_organizations(catalog_path)[0]

    update_public_information_contact(
        organization,
        position="Начальник отдела",
        full_name="Петров Петр Петрович",
        phone="+7 900 111-22-33",
    )

    saved = json.loads(catalog_path.read_text(encoding="utf-8"))[0]
    assert saved["organization"]["public_information_contact"] == {
        "position": "Начальник отдела",
        "full_name": "Петров Петр Петрович",
        "phone": "+7 900 111-22-33",
    }
    assert saved["sites"]


@pytest.mark.parametrize(
    "employees, other, presence",
    [(-1, 0, 1.0), (0, -1, 1.0), (1.5, 0, 1.0), (0, 0, -0.1), (0, 0, 1.1)],
)
def test_update_personnel_rejects_invalid_counts(
    tmp_path: Path, employees: int, other: int, presence: float
) -> None:
    target = tmp_path / "project"
    service = ProjectService()
    service.create(target, project_data())

    with pytest.raises(ProjectError):
        service.update_personnel(target, employees, other, presence)


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
        from PySide6.QtWidgets import (
            QApplication,
            QGroupBox,
            QLabel,
            QPushButton,
            QScrollArea,
        )
        from iris_v2.gui import MainWindow
    except ImportError as exc:
        pytest.skip(f"Qt недоступен в текущей системе: {exc}")

    application = QApplication.instance() or QApplication([])
    window = MainWindow()
    try:
        assert window.windowTitle() == "IRIS v2"
        assert window.findChild(QPushButton, "create_project_button") is not None
        assert window.findChild(QPushButton, "open_project_button") is not None
        assert window.findChild(QScrollArea, "workflow_scroll_area") is not None
        assert window.findChild(QLabel, "workflow_status_legend") is not None
        group_titles = {
            group.objectName(): group.title()
            for group in window.findChildren(QGroupBox)
        }
        assert group_titles == {
            "project_actions_group": "Проект и справочники",
            "source_data_group": "Этап 1. Подготовка исходных данных",
            "scenarios_mass_group": "Этап 2. Сценарии и массы",
            "consequences_group": "Этап 3. Зоны поражения и последствия",
            "risk_analysis_group": "Этап 4. Оценка и представление риска",
            "report_group": "Этап 5. Выпуск документа",
        }
        common_button = window.findChild(QPushButton, "project_common_button")
        assert common_button is not None
        assert not common_button.isEnabled()
        assert common_button.text().startswith("1.1 ")
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
        assert cases_button.text().startswith("2.1 ")
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
        hazard_factor_button = window.findChild(
            QPushButton, "hazard_factor_button"
        )
        assert hazard_factor_button is not None
        assert not hazard_factor_button.isEnabled()
        pool_fire_button = window.findChild(QPushButton, "pool_fire_button")
        assert pool_fire_button is not None
        assert not pool_fire_button.isEnabled()
        assert pool_fire_button.text().startswith("3.1 ")
        risk_button = window.findChild(QPushButton, "risk_button")
        assert risk_button is not None
        assert risk_button.text().startswith("4.1 ")
        zones_chart_button = window.findChild(
            QPushButton, "component_impact_zones_chart_button"
        )
        assert zones_chart_button is not None
        assert not zones_chart_button.isEnabled()
        assert zones_chart_button.text().startswith("4.8 ")
        report_button = window.findChild(
            QPushButton, "report_generation_button"
        )
        assert report_button is not None
        assert report_button.text().startswith("5.1 ")
        refresh_button = window.findChild(QPushButton, "refresh_all_button")
        assert refresh_button is not None
        assert not refresh_button.isEnabled()
        assert refresh_button.text().startswith("5.2 ")
        explosion_button = window.findChild(QPushButton, "explosion_button")
        assert explosion_button is not None
        assert not explosion_button.isEnabled()
        flash_fire_button = window.findChild(QPushButton, "flash_fire_button")
        assert flash_fire_button is not None
        assert not flash_fire_button.isEnabled()
        jet_fire_button = window.findChild(QPushButton, "jet_fire_button")
        assert jet_fire_button is not None
        assert not jet_fire_button.isEnabled()
        fireball_button = window.findChild(QPushButton, "fireball_button")
        assert fireball_button is not None
        assert not fireball_button.isEnabled()
        chemical_spill_button = window.findChild(
            QPushButton, "chemical_spill_button"
        )
        assert chemical_spill_button is not None
        assert not chemical_spill_button.isEnabled()
        impact_zones_button = window.findChild(
            QPushButton, "impact_zones_button"
        )
        assert impact_zones_button is not None
        assert not impact_zones_button.isEnabled()
    finally:
        window.close()
