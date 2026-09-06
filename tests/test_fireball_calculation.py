import json
from pathlib import Path

import pytest

from iris_v2.calculation_config import (
    CalculationConfigService,
    new_calculation_config,
)
from iris_v2.fireball_calculation import (
    FireballCalculationError,
    FireballCalculationService,
    calculate_fireball_zones,
    fireball_radiation,
)


def write_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def hazard_result(case_id: int, calc_code: int) -> dict:
    return {
        "id": case_id,
        "scenario_code": f"С{case_id}",
        "equipment_id": 1,
        "equipment_name": "Аппарат-1",
        "substance_id": 1,
        "substance_name": "Пропан",
        "kind": 4,
        "calc_code": calc_code,
        "calc_name": "огненный шар" if calc_code == 6 else "ликвидация",
        "scenario_text": "Тестовый сценарий",
        "ov_in_hazard_factor_t": 2.0 if calc_code == 6 else 0.0,
    }


def write_project(path: Path, values: list[dict]) -> None:
    write_json(
        path / "hazard_factor_results.json",
        {"format_version": 1, "results": values},
    )
    CalculationConfigService().save(path, new_calculation_config())


def test_old_fireball_point_formula_is_preserved() -> None:
    radiation, dose = fireball_radiation(2000.0, 350.0, 100.0)

    assert radiation == pytest.approx(13.0220371446)
    assert dose == pytest.approx(119.8612619561)


def test_thermal_dose_zones_are_ordered() -> None:
    zones = calculate_fireball_zones(2000.0, 350.0)

    assert zones["dose_600_m"] <= zones["dose_320_m"]
    assert zones["dose_320_m"] <= zones["dose_220_m"]
    assert zones["dose_220_m"] <= zones["dose_120_m"]


def test_service_calculates_only_fireball_scenarios(tmp_path: Path) -> None:
    write_project(tmp_path, [hazard_result(1, 6), hazard_result(2, 0)])

    result = FireballCalculationService().calculate(tmp_path)

    assert result.case_count == 2
    assert result.fireball_count == 1
    assert result.results[0]["fireball_status"] == "calculated"
    assert result.results[0]["dose_120_m"] > result.results[0]["dose_600_m"]
    assert result.results[1]["fireball_status"] == "not_applicable"
    assert result.results[1]["dose_600_m"] is None


def test_configured_emissive_power_is_used(tmp_path: Path) -> None:
    write_project(tmp_path, [hazard_result(1, 6)])
    config = new_calculation_config()
    config["fireball_surface_emissive_power_kw_m2"] = 450.0
    CalculationConfigService().save(tmp_path, config)

    item = FireballCalculationService().calculate(tmp_path).results[0]

    assert item["fireball_surface_emissive_power_kw_m2"] == 450.0


def test_zero_mass_preserves_old_result(tmp_path: Path) -> None:
    value = hazard_result(1, 6)
    value["ov_in_hazard_factor_t"] = 0.0
    write_project(tmp_path, [value])
    result_path = tmp_path / "fireball_results.json"
    result_path.write_text('{"old": true}\n', encoding="utf-8")

    with pytest.raises(FireballCalculationError, match="ov_in_hazard_factor_t"):
        FireballCalculationService().calculate(tmp_path)

    assert result_path.read_text(encoding="utf-8") == '{"old": true}\n'
