import json
from pathlib import Path

import pytest

from iris_v2.people_calculation import (
    PeopleCalculationError,
    PeopleCalculationService,
    calculate_people_damage,
)
from iris_v2.typical_scenarios import TypicalScenarioService


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


@pytest.mark.parametrize(
    ("equipment_type", "kind", "line", "calc_code", "expected"),
    [
        (0, 0, 1, 1, (9, 19, "full_pool_fire")),
        (0, 2, 2, 2, (10, 20, "full_explosion")),
        (0, 2, 6, 2, (1, 1, "partial_explosion")),
        (2, 0, 4, 5, (0, 1, "liquid_local_impact")),
        (5, 2, 1, 5, (9, 19, "full_flash_or_jet_fire")),
        (4, 0, 2, 1, (7, 16, "pump_cloud_fire")),
        (4, 4, 5, 2, (8, 17, "pump_explosion")),
        (0, 7, 1, 4, (0, 1, "one_injured")),
        (1, 0, 3, 0, (0, 0, "no_impact")),
    ],
)
def test_people_rules(
    equipment_type: int,
    kind: int,
    line: int,
    calc_code: int,
    expected: tuple[int, int, str],
) -> None:
    assert calculate_people_damage(
        equipment_type, kind, line, calc_code, 10, 20
    ) == expected


def test_every_typical_scenario_has_people_rule() -> None:
    catalog = TypicalScenarioService().load()

    for equipment_type in catalog.equipment_types:
        for kind in catalog.kinds:
            for scenario in catalog.scenarios_for(equipment_type, kind):
                fatalities, injured, _ = calculate_people_damage(
                    equipment_type,
                    kind,
                    scenario.line,
                    scenario.calc_code,
                    10,
                    20,
                )
                assert isinstance(fatalities, int)
                assert isinstance(injured, int)


def test_service_joins_equipment_and_saves_results(tmp_path: Path) -> None:
    write_json(
        tmp_path / "equipments.json",
        [
            {
                "id": 1,
                "equipment_type": 0,
                "possible_dead": 10,
                "possible_injured": 20,
            }
        ],
    )
    write_json(
        tmp_path / "impact_zones.json",
        {
            "results": [
                {
                    "id": 1,
                    "scenario_code": "С1",
                    "equipment_id": 1,
                    "equipment_name": "Трубопровод",
                    "equipment_type": 0,
                    "substance_name": "Нефть",
                    "kind": 0,
                    "typical_scenario_line": 1,
                    "calc_code": 1,
                    "impact_status": "calculated",
                    "scenario_text": "Пожар пролива",
                }
            ]
        },
    )

    result = PeopleCalculationService().calculate(tmp_path)

    assert result.case_count == 1
    assert result.max_fatalities == 9
    assert result.max_injured == 19
    assert result.results[0]["fatalities_count"] == 9
    assert result.results[0]["injured_count"] == 19
    assert result.path.name == "people_results.json"


def test_missing_equipment_preserves_old_file(tmp_path: Path) -> None:
    write_json(tmp_path / "equipments.json", [{"id": 1}])
    write_json(
        tmp_path / "impact_zones.json",
        {
            "results": [
                {
                    "id": 1,
                    "scenario_code": "С1",
                    "equipment_id": 2,
                    "equipment_type": 0,
                    "calc_code": 0,
                    "impact_status": "none",
                }
            ]
        },
    )
    result_path = tmp_path / "people_results.json"
    result_path.write_text('{"old": true}\n', encoding="utf-8")

    with pytest.raises(PeopleCalculationError, match="отсутствует"):
        PeopleCalculationService().calculate(tmp_path)

    assert result_path.read_text(encoding="utf-8") == '{"old": true}\n'
