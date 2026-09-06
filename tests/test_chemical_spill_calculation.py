import json
from pathlib import Path

import pytest

from iris_v2.chemical_spill_calculation import (
    ChemicalSpillCalculationError,
    ChemicalSpillCalculationService,
)


def write_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def hazard_result(case_id: int, calc_code: int, *, kind: int = 6) -> dict:
    return {
        "id": case_id,
        "scenario_code": f"С{case_id}",
        "equipment_id": 1,
        "equipment_name": "Трубопровод-1",
        "substance_id": 1,
        "substance_name": "Серная кислота",
        "kind": kind,
        "calc_code": calc_code,
        "calc_name": "химически опасный пролив",
        "scenario_text": "Тестовый сценарий",
        "spill_area_m2": 125.5,
        "ov_in_hazard_factor_t": 10.0,
    }


def write_project(path: Path, values: list[dict]) -> None:
    write_json(
        path / "hazard_factor_results.json",
        {"format_version": 1, "results": values},
    )


def test_service_copies_only_chemical_spill_area(tmp_path: Path) -> None:
    write_project(
        tmp_path,
        [hazard_result(1, 7), hazard_result(2, 0)],
    )

    result = ChemicalSpillCalculationService().calculate(tmp_path)

    assert result.case_count == 2
    assert result.chemical_spill_count == 1
    assert result.results[0]["chemical_spill_status"] == "calculated"
    assert result.results[0]["chemical_spill_area_m2"] == 125.5
    assert result.results[1]["chemical_spill_status"] == "not_applicable"
    assert result.results[1]["chemical_spill_area_m2"] is None
    saved = json.loads(result.path.read_text(encoding="utf-8"))
    assert saved["chemical_spill_count"] == 1


def test_no_unfounded_toxic_radius_is_created(tmp_path: Path) -> None:
    write_project(tmp_path, [hazard_result(1, 7)])

    item = ChemicalSpillCalculationService().calculate(tmp_path).results[0]

    assert "lethal_radius_m" not in item
    assert "threshold_radius_m" not in item


def test_wrong_substance_kind_is_rejected(tmp_path: Path) -> None:
    write_project(tmp_path, [hazard_result(1, 7, kind=7)])

    with pytest.raises(ChemicalSpillCalculationError, match="kind=6"):
        ChemicalSpillCalculationService().calculate(tmp_path)


def test_missing_area_preserves_old_result(tmp_path: Path) -> None:
    value = hazard_result(1, 7)
    value["spill_area_m2"] = None
    write_project(tmp_path, [value])
    result_path = tmp_path / "chemical_spill_results.json"
    result_path.write_text('{"old": true}\n', encoding="utf-8")

    with pytest.raises(ChemicalSpillCalculationError, match="spill_area_m2"):
        ChemicalSpillCalculationService().calculate(tmp_path)

    assert result_path.read_text(encoding="utf-8") == '{"old": true}\n'
