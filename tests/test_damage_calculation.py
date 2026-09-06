import json
from pathlib import Path

import pytest

from iris_v2.calculation_config import CalculationConfigService, new_calculation_config
from iris_v2.damage_calculation import (
    DAMAGE_COEFFICIENTS,
    DamageCalculationError,
    DamageCalculationService,
    approximate_equipment_cost,
    calculate_damage,
    scenario_damage_coefficient,
)
from iris_v2.typical_scenarios import TypicalScenarioService


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


def test_old_equipment_cost_curve_is_preserved() -> None:
    assert approximate_equipment_cost(0) == 0
    assert approximate_equipment_cost(0.1) == pytest.approx(100)
    assert approximate_equipment_cost(1000) == pytest.approx(1099.9)
    assert approximate_equipment_cost(10000) == pytest.approx(25000)


def test_old_damage_formula_is_preserved() -> None:
    result = calculate_damage(10, 2, 3, 0.8, 30.3)
    base_direct = (100 + 10 - 0.1) * 30.3

    assert result["direct_losses"] == pytest.approx(base_direct * 0.8)
    assert result["liquidation_costs"] == pytest.approx(base_direct * 0.1 * 0.8)
    assert result["social_losses"] == 6750
    assert result["indirect_damage"] == pytest.approx(6750 * 0.157)
    assert result["total_environmental_damage"] == pytest.approx(
        base_direct * 0.236 * 0.8
    )
    assert result["total_damage"] == pytest.approx(
        sum(value for key, value in result.items() if key != "total_damage")
    )


def test_every_typical_scenario_has_damage_coefficient() -> None:
    catalog = TypicalScenarioService().load()

    for equipment_type in catalog.equipment_types:
        for kind in catalog.kinds:
            scenarios = catalog.scenarios_for(equipment_type, kind)
            for scenario in scenarios:
                assert scenario_damage_coefficient(
                    len(scenarios), scenario.line
                ) == DAMAGE_COEFFICIENTS[len(scenarios)][scenario.line - 1]


def test_service_saves_damage_results(tmp_path: Path) -> None:
    write_json(
        tmp_path / "people_results.json",
        {
            "results": [
                {
                    "id": 1,
                    "scenario_code": "С1",
                    "equipment_name": "Трубопровод",
                    "equipment_type": 0,
                    "substance_name": "Нефть",
                    "kind": 0,
                    "typical_scenario_line": 1,
                    "amount_t": 10.0,
                    "fatalities_count": 2,
                    "injured_count": 3,
                    "scenario_text": "Пожар пролива",
                }
            ]
        },
    )
    config = new_calculation_config()
    config["damage_scale"] = 2.0
    CalculationConfigService().save(tmp_path, config)

    result = DamageCalculationService().calculate(tmp_path)

    assert result.case_count == 1
    assert result.results[0]["damage_scenario_coefficient"] == 0.8
    assert result.results[0]["damage_scale"] == 2.0
    assert result.results[0]["total_damage"] > 0
    assert result.path.name == "damage_results.json"


def test_error_preserves_old_result(tmp_path: Path) -> None:
    write_json(
        tmp_path / "people_results.json",
        {
            "results": [
                {
                    "id": 1,
                    "scenario_code": "С1",
                    "equipment_type": 0,
                    "kind": 0,
                    "typical_scenario_line": 1,
                    "amount_t": -1,
                    "fatalities_count": 0,
                    "injured_count": 0,
                }
            ]
        },
    )
    result_path = tmp_path / "damage_results.json"
    result_path.write_text('{"old": true}\n', encoding="utf-8")

    with pytest.raises(DamageCalculationError, match="amount_t"):
        DamageCalculationService().calculate(tmp_path)

    assert result_path.read_text(encoding="utf-8") == '{"old": true}\n'
