import json
from pathlib import Path

import pytest

from iris_v2.toxic_fake_calculation import (
    ToxicCalculationError,
    ToxicCalculationService,
    calculate_temporary_toxic_zones,
)


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


def hazard_result(case_id: int, calc_code: int, mass_t: float = 1.0) -> dict:
    return {
        "id": case_id,
        "scenario_code": f"С{case_id}",
        "equipment_name": "Аппарат",
        "substance_name": "Аммиак",
        "kind": 7,
        "calc_code": calc_code,
        "scenario_text": "Аварийный выброс",
        "ov_in_hazard_factor_t": mass_t,
    }


def test_old_temporary_formula_is_preserved() -> None:
    lethal, threshold = calculate_temporary_toxic_zones(1000.0)

    assert lethal == round(5 * 1000 ** 0.33)
    assert threshold == round(15 * 1000 ** 0.33)


def test_service_calculates_only_calc_code_4(tmp_path: Path) -> None:
    write_json(
        tmp_path / "hazard_factor_results.json",
        {"results": [hazard_result(1, 4), hazard_result(2, 0)]},
    )

    result = ToxicCalculationService().calculate(tmp_path)

    assert result.case_count == 2
    assert result.toxic_count == 1
    assert result.results[0]["toxic_status"] == "calculated_temporary"
    assert result.results[0]["toxic_mass_kg"] == 1000.0
    assert result.results[0]["lethal_radius_m"] > 0
    assert result.results[0]["threshold_radius_m"] > result.results[0]["lethal_radius_m"]
    assert result.results[1]["toxic_status"] == "not_applicable"
    saved = json.loads(result.path.read_text(encoding="utf-8"))
    assert saved["method"] == "temporary_mass_scaling"
    assert "Временная оценка" in saved["warning"]


def test_invalid_mass_preserves_old_file(tmp_path: Path) -> None:
    write_json(
        tmp_path / "hazard_factor_results.json",
        {"results": [hazard_result(1, 4, 0.0)]},
    )
    result_path = tmp_path / "toxic_results.json"
    result_path.write_text('{"old": true}\n', encoding="utf-8")

    with pytest.raises(ToxicCalculationError, match="больше нуля"):
        ToxicCalculationService().calculate(tmp_path)

    assert result_path.read_text(encoding="utf-8") == '{"old": true}\n'
