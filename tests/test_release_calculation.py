import json
import math
from pathlib import Path

import pytest

from iris_v2.calculation_config import (
    CalculationConfigService,
    new_calculation_config,
)
from iris_v2.release_calculation import (
    ReleaseCalculationError,
    ReleaseCalculationService,
    gas_leak_mass_flow_kg_s,
    liquid_leak_mass_flow_kg_s,
    release_mode,
)
from iris_v2.typical_scenarios import TypicalScenarioService


def write_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def equipment(equipment_type: int, substance_id: int = 1) -> dict:
    return {
        "id": 1,
        "substance_id": substance_id,
        "equipment_name": "Тестовое оборудование",
        "equipment_type": equipment_type,
        "pressure_mpa": 1.0,
        "diameter_mm": 100.0,
        "shutdown_time_s": 10.0,
        "substance_temperature_c": 20.0,
    }


def substance(kind: int) -> dict:
    return {
        "id": 1,
        "name": "Тестовое вещество",
        "kind": kind,
        "physical": {
            "density_liquid_kg_per_m3": 800.0,
            "density_gas_kg_per_m3": 3.0,
            "molar_mass_kg_per_mol": 0.044,
        },
    }


def case(equipment_type: int, kind: int, line: int, case_id: int) -> dict:
    return {
        "id": case_id,
        "scenario_code": f"С{case_id}",
        "equipment_id": 1,
        "equipment_name": "Тестовое оборудование",
        "equipment_type": equipment_type,
        "substance_id": 1,
        "substance_name": "Тестовое вещество",
        "kind": kind,
        "typical_scenario_line": line,
        "scenario_text": "Тестовый сценарий",
    }


def write_project(
    path: Path,
    equipment_type: int,
    kind: int,
    lines: list[int],
    amount_t: float = 10.0,
) -> None:
    write_json(path / "equipments.json", [equipment(equipment_type)])
    write_json(path / "substances.json", [substance(kind)])
    write_json(
        path / "amount_results.json",
        {
            "format_version": 1,
            "results": [
                {
                    "equipment_id": 1,
                    "equipment_type": equipment_type,
                    "substance_id": 1,
                    "kind": kind,
                    "amount_t": amount_t,
                }
            ],
        },
    )
    write_json(
        path / "calculation_cases.json",
        {
            "format_version": 1,
            "cases": [
                case(equipment_type, kind, line, index)
                for index, line in enumerate(lines, start=1)
            ],
        },
    )
    CalculationConfigService().save(path, new_calculation_config())


def test_rules_cover_every_typical_scenario() -> None:
    catalog = TypicalScenarioService().load()

    checked = 0
    for equipment_type in catalog.equipment_types:
        for kind in catalog.kinds:
            for scenario in catalog.scenarios_for(equipment_type, kind):
                assert release_mode(equipment_type, kind, scenario.line)
                checked += 1

    assert checked == catalog.scenario_count == 370


def test_pipeline_liquid_full_and_partial_release(tmp_path: Path) -> None:
    write_project(tmp_path, equipment_type=0, kind=0, lines=[1, 4])

    result = ReleaseCalculationService().calculate(tmp_path)

    flow = liquid_leak_mass_flow_kg_s(1.0, 100.0, 800.0)
    full_mass = 10.0 + flow * 10.0 / 1000.0
    assert result.results[0]["release_mode"] == "pipeline_liquid_full"
    assert result.results[0]["ov_in_accident_t"] == pytest.approx(full_mass)
    assert result.results[1]["release_mode"] == "pipeline_liquid_partial"
    assert result.results[1]["ov_in_accident_t"] == pytest.approx(
        full_mass * 0.125
    )
    assert result.results[1]["flow_kg_s"] == pytest.approx(flow * 0.125)


def test_gas_full_and_partial_scale_only_supply_flow(tmp_path: Path) -> None:
    write_project(tmp_path, equipment_type=5, kind=2, lines=[1, 5], amount_t=0.2)

    result = ReleaseCalculationService().calculate(tmp_path)

    flow = gas_leak_mass_flow_kg_s(1.0, 20.0, 20.0, 0.044)
    assert result.results[0]["ov_in_accident_t"] == pytest.approx(
        0.2 + flow * 10.0 / 1000.0
    )
    assert result.results[1]["ov_in_accident_t"] == pytest.approx(
        0.2 + flow * 0.125 * 10.0 / 1000.0
    )


def test_pressure_equipment_uses_liquid_and_gas_side_leaks(
    tmp_path: Path,
) -> None:
    write_project(tmp_path, equipment_type=2, kind=0, lines=[1, 4, 6, 9])

    result = ReleaseCalculationService().calculate(tmp_path)

    liquid_flow = liquid_leak_mass_flow_kg_s(1.0, 20.0, 800.0)
    gas_flow = gas_leak_mass_flow_kg_s(1.0, 20.0, 20.0, 0.044)
    assert result.results[0]["ov_in_accident_t"] == pytest.approx(10.0)
    assert result.results[1]["ov_in_accident_t"] == pytest.approx(
        liquid_flow * 10.0 / 1000.0
    )
    assert result.results[2]["ov_in_accident_t"] == pytest.approx(
        gas_flow * 10.0 / 1000.0
    )
    assert result.results[3]["ov_in_accident_t"] == pytest.approx(10.0)


def test_tank_car_kind_zero_gas_side_scenario_is_calculated(
    tmp_path: Path,
) -> None:
    write_project(tmp_path, equipment_type=8, kind=0, lines=[7])

    item = ReleaseCalculationService().calculate(tmp_path).results[0]

    assert item["release_mode"] == "gas_phase_leak"
    assert item["ov_in_accident_t"] > 0


def test_invalid_input_does_not_replace_existing_result(tmp_path: Path) -> None:
    write_project(tmp_path, equipment_type=5, kind=2, lines=[1], amount_t=0.2)
    data = json.loads((tmp_path / "substances.json").read_text(encoding="utf-8"))
    data[0]["physical"]["molar_mass_kg_per_mol"] = None
    write_json(tmp_path / "substances.json", data)
    result_path = tmp_path / "release_results.json"
    result_path.write_text('{"old": true}\n', encoding="utf-8")

    with pytest.raises(ReleaseCalculationError, match="molar_mass_kg_per_mol"):
        ReleaseCalculationService().calculate(tmp_path)

    assert result_path.read_text(encoding="utf-8") == '{"old": true}\n'


def test_flow_formulas_match_old_iris_equations() -> None:
    liquid_expected = 0.62 * math.pi * 0.02**2 / 4 * math.sqrt(
        2 * 800 * 1_000_000
    )
    assert liquid_leak_mass_flow_kg_s(1.0, 20.0, 800.0) == pytest.approx(
        liquid_expected
    )

    gas_value = gas_leak_mass_flow_kg_s(1.0, 20.0, 20.0, 0.044)
    assert gas_value > 0
