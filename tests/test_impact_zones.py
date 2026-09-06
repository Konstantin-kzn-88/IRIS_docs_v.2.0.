import json
from pathlib import Path

import pytest

from iris_v2.impact_zones import ImpactZonesError, ImpactZonesService


def write_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def scenario(case_id: int, calc_code: int) -> dict:
    return {
        "id": case_id,
        "scenario_code": f"С{case_id}",
        "equipment_name": "Оборудование",
        "substance_name": "Вещество",
        "calc_code": calc_code,
        "scenario_text": "Сценарий",
    }


def module_result(item: dict, status: str, **values: float) -> dict:
    return {**item, status: "calculated", **values}


def test_all_supported_impact_types_are_combined(tmp_path: Path) -> None:
    values = [scenario(index + 1, code) for index, code in enumerate(range(8))]
    write_json(
        tmp_path / "hazard_factor_results.json",
        {"results": values},
    )
    modules = {
        "pool_fire_results.json": module_result(
            values[1], "pool_fire_status",
            q_10_5_m=10, q_7_0_m=20, q_4_2_m=30, q_1_4_m=40,
        ),
        "explosion_results.json": module_result(
            values[2], "explosion_status",
            p_100_m=1, p_70_m=2, p_28_m=3, p_14_m=4, p_5_m=5, p_2_m=6,
        ),
        "flash_fire_results.json": module_result(
            values[3], "flash_fire_status",
            lel_radius_m=20, flash_fire_radius_m=24,
        ),
        "toxic_results.json": {
            **values[4],
            "toxic_status": "calculated_temporary",
            "lethal_radius_m": 50,
            "threshold_radius_m": 150,
        },
        "jet_fire_results.json": module_result(
            values[5], "jet_fire_status",
            jet_fire_length_m=30, jet_fire_diameter_m=5,
        ),
        "fireball_results.json": module_result(
            values[6], "fireball_status",
            dose_600_m=10, dose_320_m=20, dose_220_m=30, dose_120_m=40,
        ),
        "chemical_spill_results.json": module_result(
            values[7], "chemical_spill_status",
            chemical_spill_area_m2=125.5,
        ),
    }
    for file_name, item in modules.items():
        write_json(tmp_path / file_name, {"results": [item]})

    result = ImpactZonesService().calculate(tmp_path)

    assert result.case_count == 8
    assert result.calculated_count == 7
    assert result.unavailable_count == 0
    assert result.results[0]["impact_status"] == "none"
    assert result.results[4]["impact_status"] == "calculated_temporary"
    assert result.results[7]["impact_values"] == {
        "chemical_spill_area_m2": 125.5
    }


def test_only_required_module_file_is_read(tmp_path: Path) -> None:
    item = scenario(1, 3)
    write_json(tmp_path / "hazard_factor_results.json", {"results": [item]})
    write_json(
        tmp_path / "flash_fire_results.json",
        {
            "results": [
                module_result(
                    item,
                    "flash_fire_status",
                    lel_radius_m=10,
                    flash_fire_radius_m=12,
                )
            ]
        },
    )

    result = ImpactZonesService().calculate(tmp_path)

    assert result.calculated_count == 1
    assert "НКПР: 10 м" in result.results[0]["impact_summary"]


def test_missing_module_preserves_old_result(tmp_path: Path) -> None:
    write_json(
        tmp_path / "hazard_factor_results.json",
        {"results": [scenario(1, 2)]},
    )
    result_path = tmp_path / "impact_zones.json"
    result_path.write_text('{"old": true}\n', encoding="utf-8")

    with pytest.raises(ImpactZonesError, match="explosion_results.json"):
        ImpactZonesService().calculate(tmp_path)

    assert result_path.read_text(encoding="utf-8") == '{"old": true}\n'


def test_stale_scenario_code_is_rejected(tmp_path: Path) -> None:
    item = scenario(1, 7)
    write_json(tmp_path / "hazard_factor_results.json", {"results": [item]})
    stale = module_result(
        item,
        "chemical_spill_status",
        chemical_spill_area_m2=10,
    )
    stale["scenario_code"] = "С99"
    write_json(
        tmp_path / "chemical_spill_results.json",
        {"results": [stale]},
    )

    with pytest.raises(ImpactZonesError, match="устаревшие данные"):
        ImpactZonesService().calculate(tmp_path)
