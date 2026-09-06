import json
from pathlib import Path

import pytest

from iris_v2.flash_fire_calculation import (
    FlashFireCalculationError,
    FlashFireCalculationService,
    calculate_flash_fire_radii,
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
        "substance_name": "Бензин",
        "kind": 0,
        "calc_code": calc_code,
        "calc_name": "пожар-вспышка" if calc_code == 3 else "ликвидация",
        "scenario_text": "Тестовый сценарий",
        "ov_in_hazard_factor_t": 0.00981 if calc_code == 3 else 0.0,
    }


def write_project(
    path: Path,
    values: list[dict],
    *,
    lel_percent: float | None = 2.9,
    kind: int = 0,
    boiling_point: float | None = 60.0,
    gas_density: float | None = None,
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
                "name": "Бензин",
                "kind": kind,
                "physical": {
                    "molar_mass_kg_per_mol": 0.09,
                    "density_gas_kg_per_m3": gas_density,
                    "boiling_point_C": boiling_point,
                },
                "explosion": {"lel_percent": lel_percent},
            }
        ],
    )


def test_old_lclp_formula_is_preserved_with_si_conversion() -> None:
    result = calculate_flash_fire_radii(9.81, 0.09, 60.0, 2.9)

    assert result["vapor_density_kg_m3"] == pytest.approx(3.2908758427)
    assert result["lel_radius_m"] == 7.87
    assert result["flash_fire_radius_m"] == 9.44


def test_flash_fire_radius_is_twenty_percent_larger() -> None:
    result = calculate_flash_fire_radii(1000.0, 0.044, -42.0, 2.1)

    assert result["flash_fire_radius_m"] == round(
        result["lel_radius_m"] * 1.2,
        2,
    )


def test_gas_uses_density_without_boiling_point(tmp_path: Path) -> None:
    value = hazard_result(1, 3)
    value["kind"] = 2
    write_project(
        tmp_path,
        [value],
        kind=2,
        boiling_point=None,
        gas_density=0.72,
    )

    item = FlashFireCalculationService().calculate(tmp_path).results[0]

    assert item["flash_fire_status"] == "calculated"
    assert item["flash_fire_density_source"] == "substance_gas_density"
    assert item["vapor_density_kg_m3"] == pytest.approx(0.72)
    assert item["flash_fire_boiling_point_c"] is None


def test_service_calculates_only_flash_fire_scenarios(tmp_path: Path) -> None:
    write_project(tmp_path, [hazard_result(1, 3), hazard_result(2, 0)])

    result = FlashFireCalculationService().calculate(tmp_path)

    assert result.case_count == 2
    assert result.flash_fire_count == 1
    assert result.results[0]["flash_fire_status"] == "calculated"
    assert result.results[0]["flash_fire_radius_m"] > 0
    assert result.results[1]["flash_fire_status"] == "not_applicable"
    assert result.results[1]["lel_radius_m"] is None
    saved = json.loads(result.path.read_text(encoding="utf-8"))
    assert saved["flash_fire_count"] == 1


def test_missing_lel_preserves_old_result(tmp_path: Path) -> None:
    write_project(tmp_path, [hazard_result(1, 3)], lel_percent=None)
    result_path = tmp_path / "flash_fire_results.json"
    result_path.write_text('{"old": true}\n', encoding="utf-8")

    with pytest.raises(FlashFireCalculationError, match="lel_percent"):
        FlashFireCalculationService().calculate(tmp_path)

    assert result_path.read_text(encoding="utf-8") == '{"old": true}\n'


def test_zero_cloud_mass_is_rejected(tmp_path: Path) -> None:
    value = hazard_result(1, 3)
    value["ov_in_hazard_factor_t"] = 0.0
    write_project(tmp_path, [value])

    with pytest.raises(FlashFireCalculationError, match="ov_in_hazard_factor_t"):
        FlashFireCalculationService().calculate(tmp_path)


def test_lel_over_one_hundred_is_rejected() -> None:
    with pytest.raises(FlashFireCalculationError, match="100"):
        calculate_flash_fire_radii(10.0, 0.09, 60.0, 101.0)
