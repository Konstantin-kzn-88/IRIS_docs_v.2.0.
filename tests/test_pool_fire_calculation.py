import json
from pathlib import Path

import pytest

from iris_v2.calculation_config import (
    CalculationConfigService,
    new_calculation_config,
)
from iris_v2.pool_fire_calculation import (
    PoolFireCalculationError,
    PoolFireCalculationService,
    calculate_pool_fire_zones,
    thermal_radiation_kw_m2,
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
        "equipment_name": "РВС-1",
        "substance_id": 1,
        "substance_name": "Нефть",
        "kind": 0,
        "calc_code": calc_code,
        "calc_name": "пожар пролива" if calc_code == 1 else "ликвидация",
        "scenario_text": "Тестовый сценарий",
        "spill_area_m2": 200.0,
        "ov_in_accident_t": 10.0,
        "ov_in_hazard_factor_t": 10.0 if calc_code == 1 else 0.0,
    }


def write_project(
    path: Path,
    values: list[dict],
    *,
    burning_rate: float | None = 0.06,
) -> None:
    write_json(
        path / "hazard_factor_results.json",
        {"format_version": 1, "results": values},
    )
    write_json(
        path / "substances.json",
        [
            {
                "id": 1,
                "name": "Нефть",
                "kind": 0,
                "physical": {
                    "molar_mass_kg_per_mol": 0.1,
                    "boiling_point_C": 68.0,
                },
                "explosion": {
                    "burning_rate_kg_per_s_m2": burning_rate,
                },
            }
        ],
    )
    CalculationConfigService().save(path, new_calculation_config())


def test_radiation_decreases_outside_pool() -> None:
    near = thermal_radiation_kw_m2(200.0, 0.06, 0.1, 68.0, 1.0, 10.0)
    far = thermal_radiation_kw_m2(200.0, 0.06, 0.1, 68.0, 1.0, 100.0)

    assert near > far > 0


def test_molar_mass_is_converted_from_kg_mol() -> None:
    radiation = thermal_radiation_kw_m2(
        200.0,
        0.06,
        0.1,
        68.0,
        5.0,
        20.0,
    )

    assert radiation == pytest.approx(15.008411767)


def test_zone_radii_are_ordered() -> None:
    zones = calculate_pool_fire_zones(200.0, 0.06, 0.1, 68.0, 1.0)

    assert zones["q_10_5_m"] <= zones["q_7_0_m"]
    assert zones["q_7_0_m"] <= zones["q_4_2_m"]
    assert zones["q_4_2_m"] <= zones["q_1_4_m"]


def test_service_calculates_only_pool_fire_scenarios(tmp_path: Path) -> None:
    write_project(tmp_path, [hazard_result(1, 1), hazard_result(2, 0)])

    result = PoolFireCalculationService().calculate(tmp_path)

    assert result.case_count == 2
    assert result.pool_fire_count == 1
    assert result.results[0]["pool_fire_status"] == "calculated"
    assert result.results[0]["q_1_4_m"] > result.results[0]["q_10_5_m"]
    assert result.results[1]["pool_fire_status"] == "not_applicable"
    assert result.results[1]["q_10_5_m"] is None
    saved = json.loads(result.path.read_text(encoding="utf-8"))
    assert saved["pool_fire_count"] == 1


def test_configured_wind_speed_is_used(tmp_path: Path) -> None:
    write_project(tmp_path, [hazard_result(1, 1)])
    config = new_calculation_config()
    config["wind_speed_m_s"] = 3.0
    CalculationConfigService().save(tmp_path, config)

    item = PoolFireCalculationService().calculate(tmp_path).results[0]

    assert item["pool_fire_wind_speed_m_s"] == pytest.approx(3.0)


def test_missing_burning_rate_preserves_old_result(tmp_path: Path) -> None:
    write_project(tmp_path, [hazard_result(1, 1)], burning_rate=None)
    result_path = tmp_path / "pool_fire_results.json"
    result_path.write_text('{"old": true}\n', encoding="utf-8")

    with pytest.raises(PoolFireCalculationError, match="burning_rate"):
        PoolFireCalculationService().calculate(tmp_path)

    assert result_path.read_text(encoding="utf-8") == '{"old": true}\n'
