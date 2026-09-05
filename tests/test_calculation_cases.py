import json
from pathlib import Path

import pytest

from iris_v2.calculation_cases import (
    CalculationCasesError,
    CalculationCasesService,
)
from iris_v2.calculation_config import (
    CalculationConfigService,
    new_calculation_config,
)
from iris_v2.typical_scenarios import TypicalScenarioService


def write_json(path: Path, data: object) -> None:
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def pipeline(
    equipment_id: int,
    component: str,
    *,
    substance_id: int = 1,
    equipment_type: int = 0,
) -> dict:
    return {
        "id": equipment_id,
        "source_id": equipment_id + 100,
        "substance_id": substance_id,
        "equipment_name": f"Трубопровод {equipment_id}",
        "equipment_type": equipment_type,
        "total_length_m": 1000.0,
        "equipment_count": None,
        "hazard_component": component,
    }


def test_cases_are_generated_for_every_equipment(tmp_path: Path) -> None:
    write_json(
        tmp_path / "substances.json",
        [{"id": 1, "name": "Нефть", "kind": 0}],
    )
    write_json(
        tmp_path / "equipments.json",
        [
            pipeline(10, "Участок трубопроводов"),
            pipeline(20, "Участок трубопроводов (без КМ)"),
            pipeline(30, "Участок трубопроводов (с КМ)"),
        ],
    )
    config = new_calculation_config()
    config["frequency_multipliers"]["without_compensation"] = 1.4
    config["frequency_multipliers"]["with_compensation"] = 0.5
    CalculationConfigService().save(tmp_path, config)

    result = CalculationCasesService().generate(tmp_path)

    scenario_count = len(TypicalScenarioService().load().scenarios_for(0, 0))
    assert result.equipment_count == 3
    assert result.case_count == scenario_count * 3
    assert [case["scenario_code"] for case in result.cases] == [
        f"С{number}" for number in range(1, result.case_count + 1)
    ]
    assert result.cases[0]["frequency_mode"] == "standard"
    assert result.cases[scenario_count]["frequency_mode"] == (
        "without_compensation"
    )
    assert result.cases[scenario_count]["frequency_multiplier"] == 1.4
    assert result.cases[scenario_count * 2]["frequency_mode"] == (
        "with_compensation"
    )
    assert result.cases[scenario_count * 2]["frequency_multiplier"] == 0.5
    assert result.cases[0]["frequency_basis"] == 1000.0
    assert result.cases[0]["frequency_basis_unit"] == "м"

    saved = json.loads(result.path.read_text(encoding="utf-8"))
    assert saved["format_version"] == 1
    assert saved["case_count"] == result.case_count
    assert saved["cases"][0]["scenario_code"] == "С1"
    assert saved["cases"][0]["substance_name"] == "Нефть"


def test_forbidden_equipment_and_substance_pair_is_rejected(
    tmp_path: Path,
) -> None:
    write_json(
        tmp_path / "substances.json",
        [{"id": 2, "name": "Газ", "kind": 2}],
    )
    write_json(
        tmp_path / "equipments.json",
        [pipeline(1, "Резервуарный парк", substance_id=2, equipment_type=1)],
    )

    with pytest.raises(CalculationCasesError, match="сочетание.*недопустимо"):
        CalculationCasesService().generate(tmp_path)

    assert not (tmp_path / "calculation_cases.json").exists()


def test_error_does_not_damage_existing_cases_file(tmp_path: Path) -> None:
    write_json(
        tmp_path / "substances.json",
        [{"id": 1, "name": "Нефть", "kind": 0}],
    )
    write_json(
        tmp_path / "equipments.json",
        [pipeline(1, "Участок (с КМ) трубопроводов")],
    )
    path = tmp_path / "calculation_cases.json"
    path.write_text('{"old": true}\n', encoding="utf-8")

    with pytest.raises(CalculationCasesError, match="должна быть в конце"):
        CalculationCasesService().generate(tmp_path)

    assert path.read_text(encoding="utf-8") == '{"old": true}\n'
