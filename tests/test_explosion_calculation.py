import json
from pathlib import Path

import pytest

from iris_v2.explosion_calculation import (
    ExplosionCalculationError,
    ExplosionCalculationService,
    calculate_explosion_zones,
    explosion_pressure_impulse,
    flame_speed_m_s,
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
        "equipment_type": 2,
        "substance_id": 1,
        "substance_name": "Пропан",
        "kind": 4,
        "calc_code": calc_code,
        "calc_name": "взрыв облака" if calc_code == 2 else "ликвидация",
        "scenario_text": "Тестовый сценарий",
        "ov_in_hazard_factor_t": 1.98 if calc_code == 2 else 0.0,
    }


def write_project(
    path: Path,
    values: list[dict],
    *,
    hazard_class: int | None = 3,
) -> None:
    write_json(
        path / "hazard_factor_results.json",
        {"format_version": 1, "results": values},
    )
    write_json(
        path / "equipments.json",
        [
            {
                "id": 1,
                "substance_id": 1,
                "equipment_type": 2,
                "clutter_degree": 2,
            }
        ],
    )
    write_json(
        path / "substances.json",
        [
            {
                "id": 1,
                "name": "Пропан",
                "kind": 4,
                "explosion": {
                    "explosion_hazard_class": hazard_class,
                    "heat_of_combustion_kJ_per_kg": 44_000.0,
                    "expansion_degree": 7,
                    "energy_reserve_factor": 2,
                },
            }
        ],
    )


def test_old_flame_speed_table_is_preserved() -> None:
    assert flame_speed_m_s(1, 1, 1980.0) == 500.0
    assert flame_speed_m_s(3, 4, 1980.0) == pytest.approx(
        43.0 * 1980.0 ** (1.0 / 6.0)
    )


def test_old_pressure_and_impulse_formula_is_preserved() -> None:
    pressure, impulse = explosion_pressure_impulse(
        3,
        2,
        1980.0,
        44_000.0,
        7,
        2,
        20.0,
    )

    assert pressure == pytest.approx(36.9578395168)
    assert impulse == pytest.approx(2865.1897430982)


def test_zone_radii_use_real_two_kpa_boundary() -> None:
    zones = calculate_explosion_zones(3, 2, 1980.0, 44_000.0, 7, 2)

    assert zones["p_100_m"] <= zones["p_70_m"]
    assert zones["p_70_m"] <= zones["p_28_m"]
    assert zones["p_28_m"] <= zones["p_14_m"]
    assert zones["p_14_m"] <= zones["p_5_m"]
    assert zones["p_5_m"] < zones["p_2_m"]


def test_service_calculates_only_explosion_scenarios(tmp_path: Path) -> None:
    write_project(tmp_path, [hazard_result(1, 2), hazard_result(2, 0)])

    result = ExplosionCalculationService().calculate(tmp_path)

    assert result.case_count == 2
    assert result.explosion_count == 1
    assert result.results[0]["explosion_status"] == "calculated"
    assert result.results[0]["p_2_m"] > result.results[0]["p_5_m"]
    assert result.results[1]["explosion_status"] == "not_applicable"
    assert result.results[1]["p_70_m"] is None
    saved = json.loads(result.path.read_text(encoding="utf-8"))
    assert saved["pressure_levels_kpa"] == [
        100.0,
        70.0,
        28.0,
        14.0,
        5.0,
        2.0,
    ]


def test_missing_hazard_class_preserves_old_result(tmp_path: Path) -> None:
    write_project(tmp_path, [hazard_result(1, 2)], hazard_class=None)
    result_path = tmp_path / "explosion_results.json"
    result_path.write_text('{"old": true}\n', encoding="utf-8")

    with pytest.raises(ExplosionCalculationError, match="explosion_hazard_class"):
        ExplosionCalculationService().calculate(tmp_path)

    assert result_path.read_text(encoding="utf-8") == '{"old": true}\n'


def test_zero_cloud_mass_is_rejected(tmp_path: Path) -> None:
    value = hazard_result(1, 2)
    value["ov_in_hazard_factor_t"] = 0.0
    write_project(tmp_path, [value])

    with pytest.raises(ExplosionCalculationError, match="ov_in_hazard_factor_t"):
        ExplosionCalculationService().calculate(tmp_path)
