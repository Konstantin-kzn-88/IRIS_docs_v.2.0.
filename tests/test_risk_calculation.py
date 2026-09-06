import json
from pathlib import Path

import pytest

from iris_v2.risk_calculation import (
    RiskCalculationError,
    RiskCalculationService,
    calculate_risk,
)
from iris_v2.service import CreateProjectData, ProjectService


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


def create_project(path: Path, employees: int, other: int) -> Path:
    ProjectService().create(
        path,
        CreateProjectData(
            name="Проект",
            code="RISK-1",
            organization_name="Организация",
            opo_name="ОПО",
            opo_registration_number="А00-00000-0000",
            opo_snapshot={
                "name": "ОПО",
                "personnel": {
                    "employees_count": employees,
                    "employees_other_opo_count": other,
                },
            },
        ),
    )
    return path


def result(case_id: int, scenario_code: str = "С1") -> dict:
    return {
        "id": case_id,
        "scenario_code": scenario_code,
        "equipment_name": "Трубопровод",
        "fatalities_count": 2,
        "injured_count": 3,
        "total_damage": 1000.0,
        "scenario_text": "Авария",
    }


def test_old_risk_formulas_are_preserved() -> None:
    value = calculate_risk(2, 3, 1e-5, 1000.0, 10)

    assert value["collective_risk_fatalities"] == pytest.approx(2e-5)
    assert value["collective_risk_injured"] == pytest.approx(3e-5)
    assert value["individual_risk_fatalities"] == pytest.approx(2e-6)
    assert value["individual_risk_injured"] == pytest.approx(3e-6)
    assert value["expected_damage"] == pytest.approx(0.01)


def test_zero_people_keeps_individual_risk_empty() -> None:
    value = calculate_risk(2, 3, 1e-5, 1000.0, 0)

    assert value["collective_risk_fatalities"] == pytest.approx(2e-5)
    assert value["individual_risk_fatalities"] is None
    assert value["individual_risk_injured"] is None


def test_service_joins_frequency_and_uses_opo_personnel(tmp_path: Path) -> None:
    project = create_project(tmp_path / "project", 8, 2)
    write_json(project / "damage_results.json", {"results": [result(1)]})
    write_json(
        project / "frequency_results.json",
        {"results": [{"id": 1, "scenario_code": "С1", "scenario_frequency": 1e-5}]},
    )

    calculated = RiskCalculationService().calculate(project)

    assert calculated.people_count == 10
    assert calculated.total_collective_risk_fatalities == pytest.approx(2e-5)
    assert calculated.total_individual_risk_fatalities == pytest.approx(2e-6)
    assert calculated.total_expected_damage == pytest.approx(0.01)
    saved = json.loads(calculated.path.read_text(encoding="utf-8"))
    assert saved["employees_count"] == 8
    assert saved["employees_other_opo_count"] == 2


def test_mismatched_scenarios_preserve_old_file(tmp_path: Path) -> None:
    project = create_project(tmp_path / "project", 10, 0)
    write_json(project / "damage_results.json", {"results": [result(1)]})
    write_json(
        project / "frequency_results.json",
        {"results": [{"id": 2, "scenario_code": "С2", "scenario_frequency": 1e-5}]},
    )
    result_path = project / "risk_results.json"
    result_path.write_text('{"old": true}\n', encoding="utf-8")

    with pytest.raises(RiskCalculationError, match="не совпадают"):
        RiskCalculationService().calculate(project)

    assert result_path.read_text(encoding="utf-8") == '{"old": true}\n'
