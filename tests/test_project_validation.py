import json
from pathlib import Path

from iris_v2.calculation_config import (
    CalculationConfigService,
    new_calculation_config,
)
from iris_v2.project_validation import ProjectValidationService
from iris_v2.service import ProjectInfo


def project_info() -> ProjectInfo:
    return ProjectInfo(
        id="test-id",
        name="Тестовый проект",
        code="TEST-001",
        organization_name="АО Пример",
        opo_name="Тестовый ОПО",
        opo_registration_number="А00-00000-0000",
        created_at="2026-09-05T00:00:00+00:00",
        organization_snapshot={"organization": {"short_name": "АО Пример"}},
        opo_snapshot={"name": "Тестовый ОПО"},
    )


def write_json(path: Path, data: object) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def valid_equipment() -> dict:
    return {
        "id": 1,
        "substance_id": 1,
        "equipment_name": "Трубопровод",
        "equipment_type": 0,
        "phase_state": "ж.ф.",
        "total_length_m": 1000.0,
        "equipment_count": None,
        "accident_section_length_m": 100.0,
        "diameter_mm": 219.0,
        "wall_thickness_mm": 8.0,
        "volume_m3": None,
        "fill_fraction": 0.8,
        "pressure_mpa": 0.1,
        "spill_coefficient": 20.0,
        "spill_area_m2": 0.0,
        "substance_temperature_c": 20.0,
        "shutdown_time_s": 12.0,
        "evaporation_time_s": 3600.0,
        "hazard_component": "Участок трубопроводов",
        "clutter_degree": 2,
        "coord_type": 0,
        "coordinates": [0.0, 0.0],
        "possible_dead": 0,
        "possible_injured": 0,
    }


def write_ready_project(directory: Path) -> None:
    directory.mkdir()
    write_json(
        directory / "project_common.json",
        {
            "year": 2026,
            "project_name": "Тестовый проект",
            "project_code": "TEST-001",
            "executor": {"name": "ООО Разработчик"},
        },
    )
    write_json(
        directory / "substances.json",
        [{"id": 1, "name": "Нефть", "kind": 0}],
    )
    write_json(directory / "equipments.json", [valid_equipment()])
    CalculationConfigService().save(directory, new_calculation_config())


def test_ready_project_passes_all_checks(tmp_path: Path) -> None:
    project = tmp_path / "project"
    write_ready_project(project)

    report = ProjectValidationService().check(project, project_info())

    assert report.ready
    assert len(report.items) == 6
    assert all(item.ok for item in report.items)
    assert "370 сценариев" in report.items[4].message


def test_missing_files_block_calculation(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()

    report = ProjectValidationService().check(project, project_info())

    assert not report.ready
    assert report.items[0].ok
    assert [item.ok for item in report.items[1:]] == [False, False, False, False, False]
    assert "project_common.json" in report.items[1].message
    assert "substances.json" in report.items[2].message
    assert "equipments.json" in report.items[3].message
    assert "equipments.json" in report.items[4].message
    assert "calculation_config.json" in report.items[5].message


def test_all_equipment_rows_are_checked(tmp_path: Path) -> None:
    project = tmp_path / "project"
    write_ready_project(project)
    first = valid_equipment()
    first["pressure_mpa"] = 0
    first["coordinates"] = [0]
    second = valid_equipment()
    second["id"] = 2
    second["substance_id"] = 999
    second["hazard_component"] = ""
    write_json(project / "equipments.json", [first, second])

    report = ProjectValidationService().check(project, project_info())

    equipment = report.items[3]
    assert not equipment.ok
    assert "оборудование 1: pressure_mpa" in equipment.message
    assert "оборудование 1: coordinates" in equipment.message
    assert "оборудование 2: substance_id" in equipment.message
    assert "оборудование 2: не заполнена составляющая ОПО" in equipment.message


def test_compensation_marks_are_checked(tmp_path: Path) -> None:
    project = tmp_path / "project"
    write_ready_project(project)
    equipment = valid_equipment()
    equipment["hazard_component"] = "Участок (с КМ) трубопроводов"
    write_json(project / "equipments.json", [equipment])

    report = ProjectValidationService().check(project, project_info())

    assert not report.ready
    assert "отметка (с КМ) должна быть в конце" in report.items[3].message


def test_forbidden_equipment_and_kind_pair_is_reported(tmp_path: Path) -> None:
    project = tmp_path / "project"
    write_ready_project(project)
    write_json(
        project / "substances.json",
        [{"id": 1, "name": "Горючий газ", "kind": 2}],
    )
    equipment = valid_equipment()
    equipment.update(
        {
            "equipment_type": 1,
            "phase_state": "г.ф.",
            "equipment_count": 1.0,
            "volume_m3": 10.0,
        }
    )
    write_json(project / "equipments.json", [equipment])

    report = ProjectValidationService().check(project, project_info())

    scenarios = report.items[4]
    assert not scenarios.ok
    assert "equipment_type=1, kind=2 запрещено" in scenarios.message
