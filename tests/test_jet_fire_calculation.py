import json
from pathlib import Path

import pytest

from iris_v2.jet_fire_calculation import (
    JetFireCalculationError,
    JetFireCalculationService,
    calculate_jet_fire_size,
    jet_fire_type,
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
        "equipment_name": "Трубопровод-1",
        "substance_id": 1,
        "substance_name": "Газ",
        "kind": 2,
        "calc_code": calc_code,
        "calc_name": "факельное горение" if calc_code == 5 else "ликвидация",
        "scenario_text": "Тестовый сценарий",
        "release_mode": "gas_supply_full",
        "hazard_factor_flow_kg_s": 10.0 if calc_code == 5 else None,
    }


def test_old_jet_fire_formula_is_preserved() -> None:
    assert calculate_jet_fire_size(10.0, 0) == (31, 5)
    assert calculate_jet_fire_size(10.0, 1) == (33, 5)
    assert calculate_jet_fire_size(10.0, 2) == (37, 6)


@pytest.mark.parametrize(
    ("kind", "release_mode", "expected"),
    [
        (2, "gas_supply_full", 0),
        (4, "gas_phase_leak", 1),
        (4, "pipeline_liquid_full", 2),
        (0, "liquid_phase_leak", 2),
        (0, "gas_phase_leak", 0),
    ],
)
def test_jet_type_is_selected_by_kind_and_release_mode(
    kind: int,
    release_mode: str,
    expected: int,
) -> None:
    assert jet_fire_type(kind, release_mode) == expected


def test_service_calculates_only_jet_fire_scenarios(tmp_path: Path) -> None:
    write_json(
        tmp_path / "hazard_factor_results.json",
        {
            "format_version": 1,
            "results": [hazard_result(1, 5), hazard_result(2, 0)],
        },
    )

    result = JetFireCalculationService().calculate(tmp_path)

    assert result.case_count == 2
    assert result.jet_fire_count == 1
    assert result.results[0]["jet_fire_status"] == "calculated"
    assert result.results[0]["jet_fire_length_m"] == 31
    assert result.results[0]["jet_fire_diameter_m"] == 5
    assert result.results[1]["jet_fire_status"] == "not_applicable"
    assert result.results[1]["jet_fire_length_m"] is None


def test_missing_flow_preserves_old_result(tmp_path: Path) -> None:
    value = hazard_result(1, 5)
    value["hazard_factor_flow_kg_s"] = None
    write_json(
        tmp_path / "hazard_factor_results.json",
        {"format_version": 1, "results": [value]},
    )
    result_path = tmp_path / "jet_fire_results.json"
    result_path.write_text('{"old": true}\n', encoding="utf-8")

    with pytest.raises(JetFireCalculationError, match="hazard_factor_flow"):
        JetFireCalculationService().calculate(tmp_path)

    assert result_path.read_text(encoding="utf-8") == '{"old": true}\n'


def test_zero_flow_is_rejected() -> None:
    with pytest.raises(JetFireCalculationError, match="Расход"):
        calculate_jet_fire_size(0.0, 0)
