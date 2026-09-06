import json
from pathlib import Path

import pytest

from iris_v2.key_scenarios import (
    KeyScenariosError,
    KeyScenariosService,
    select_key_scenarios,
)


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


def row(
    number: int,
    component: str,
    fatalities: int,
    damage: float,
    frequency: float,
) -> dict:
    return {
        "scenario_code": f"С{number}",
        "hazard_component": component,
        "equipment_name": f"Оборудование {number}",
        "fatalities_count": fatalities,
        "injured_count": fatalities + 1,
        "total_damage": damage,
        "scenario_frequency": frequency,
        "scenario_text": f"Сценарий {number}",
    }


def test_old_selection_rules_are_preserved() -> None:
    values = [
        row(1, "Участок А", 2, 1000.0, 1e-4),
        row(2, "Участок А", 3, 900.0, 2e-5),
        row(3, "Участок А", 3, 1500.0, 5e-5),
        row(4, "Участок А", 1, 500.0, 2e-4),
    ]

    selected = select_key_scenarios(values)

    assert selected[0]["scenario_type"] == "dangerous"
    assert selected[0]["scenario_code"] == "С3"
    assert selected[1]["scenario_type"] == "probable"
    assert selected[1]["scenario_code"] == "С4"


def test_complete_tie_keeps_first_scenario() -> None:
    values = [
        row(1, "Участок А", 2, 1000.0, 1e-4),
        row(2, "Участок А", 2, 1000.0, 1e-4),
    ]

    selected = select_key_scenarios(values)

    assert selected[0]["scenario_code"] == "С1"
    assert selected[1]["scenario_code"] == "С1"


def test_service_saves_two_rows_per_component(tmp_path: Path) -> None:
    write_json(
        tmp_path / "risk_results.json",
        {
            "results": [
                row(1, "Участок Б", 1, 500.0, 2e-4),
                row(2, "Участок А", 2, 1000.0, 1e-4),
                row(3, "Участок Б", 3, 1500.0, 5e-5),
            ]
        },
    )

    result = KeyScenariosService().calculate(tmp_path)

    assert result.component_count == 2
    assert result.row_count == 4
    assert [item["hazard_component"] for item in result.rows] == [
        "Участок А",
        "Участок А",
        "Участок Б",
        "Участок Б",
    ]
    saved = json.loads(result.path.read_text(encoding="utf-8"))
    assert saved["selection_rules"]["probable"] == "максимум частоты сценария"


def test_invalid_source_preserves_existing_file(tmp_path: Path) -> None:
    invalid = row(1, "Участок А", 1, 1000.0, 1e-4)
    invalid["scenario_text"] = ""
    write_json(tmp_path / "risk_results.json", {"results": [invalid]})
    result_path = tmp_path / "key_scenarios.json"
    result_path.write_text('{"old": true}\n', encoding="utf-8")

    with pytest.raises(KeyScenariosError, match="scenario_text"):
        KeyScenariosService().calculate(tmp_path)

    assert result_path.read_text(encoding="utf-8") == '{"old": true}\n'
