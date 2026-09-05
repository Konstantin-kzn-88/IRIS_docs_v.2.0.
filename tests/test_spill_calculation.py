import json
from pathlib import Path

import pytest

from iris_v2.calculation_config import (
    CalculationConfigService,
    new_calculation_config,
)
from iris_v2.release_calculation import release_mode
from iris_v2.spill_calculation import (
    SpillCalculationError,
    SpillCalculationService,
    calculate_spill_area_m2,
    spill_is_applicable,
)
from iris_v2.typical_scenarios import TypicalScenarioService


def write_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def release(
    case_id: int,
    mode: str,
    mass_t: float,
    *,
    equipment_type: int = 0,
    kind: int = 0,
) -> dict:
    return {
        "id": case_id,
        "scenario_code": f"С{case_id}",
        "equipment_id": 1,
        "equipment_name": "Тестовое оборудование",
        "equipment_type": equipment_type,
        "substance_id": 1,
        "substance_name": "Тестовое вещество",
        "kind": kind,
        "release_mode": mode,
        "release_mode_name": mode,
        "ov_in_accident_t": mass_t,
        "scenario_text": "Тестовый сценарий",
    }


def write_project(
    path: Path,
    releases: list[dict],
    *,
    spill_coefficient: float = 20.0,
    specified_area_m2: float | None = None,
) -> None:
    first = releases[0]
    write_json(
        path / "equipments.json",
        [
            {
                "id": 1,
                "substance_id": 1,
                "equipment_type": first["equipment_type"],
                "spill_coefficient": spill_coefficient,
                "spill_area_m2": specified_area_m2,
            }
        ],
    )
    write_json(
        path / "substances.json",
        [
            {
                "id": 1,
                "name": "Тестовое вещество",
                "kind": first["kind"],
            }
        ],
    )
    write_json(
        path / "release_results.json",
        {"format_version": 1, "results": releases},
    )
    CalculationConfigService().save(path, new_calculation_config())


def test_spill_classification_covers_all_typical_scenarios() -> None:
    catalog = TypicalScenarioService().load()

    checked = 0
    for equipment_type in catalog.equipment_types:
        for kind in catalog.kinds:
            for scenario in catalog.scenarios_for(equipment_type, kind):
                mode = release_mode(equipment_type, kind, scenario.line)
                assert isinstance(spill_is_applicable(mode), bool)
                checked += 1

    assert checked == catalog.scenario_count == 370


def test_calculated_area_uses_release_mass_and_coefficient(
    tmp_path: Path,
) -> None:
    releases = [
        release(1, "pipeline_liquid_full", 10.0),
        release(2, "pipeline_liquid_partial", 1.25),
    ]
    write_project(tmp_path, releases, spill_coefficient=20.0)

    result = SpillCalculationService().calculate(tmp_path)

    assert result.case_count == 2
    assert result.spill_count == 2
    assert result.results[0]["spill_area_m2"] == pytest.approx(200.0)
    assert result.results[1]["spill_area_m2"] == pytest.approx(25.0)
    assert result.results[1]["spill_source"] == "calculated"


def test_specified_area_is_reduced_only_for_partial_spill(
    tmp_path: Path,
) -> None:
    releases = [
        release(1, "inventory_full", 10.0),
        release(2, "inventory_partial", 1.25),
        release(3, "liquid_phase_leak", 0.2),
    ]
    write_project(tmp_path, releases, specified_area_m2=1000.0)

    result = SpillCalculationService().calculate(tmp_path)

    assert result.results[0]["spill_area_m2"] == pytest.approx(1000.0)
    assert result.results[0]["spill_source"] == "specified_full"
    assert result.results[1]["spill_area_m2"] == pytest.approx(120.0)
    assert result.results[2]["spill_area_m2"] == pytest.approx(120.0)
    assert result.results[2]["spill_source"] == "specified_partial"


def test_gas_release_has_no_spill(tmp_path: Path) -> None:
    releases = [
        release(
            1,
            "gas_supply_full",
            0.4,
            equipment_type=5,
            kind=2,
        )
    ]
    write_project(tmp_path, releases, spill_coefficient=0.0)

    item = SpillCalculationService().calculate(tmp_path).results[0]

    assert item["spill_applicable"] is False
    assert item["spill_area_m2"] is None
    assert item["spill_source"] == "not_applicable"


def test_missing_coefficient_does_not_replace_existing_result(
    tmp_path: Path,
) -> None:
    releases = [release(1, "pump_release", 1.0, equipment_type=4)]
    write_project(tmp_path, releases, spill_coefficient=0.0)
    result_path = tmp_path / "spill_results.json"
    result_path.write_text('{"old": true}\n', encoding="utf-8")

    with pytest.raises(SpillCalculationError, match="spill_coefficient"):
        SpillCalculationService().calculate(tmp_path)

    assert result_path.read_text(encoding="utf-8") == '{"old": true}\n'


def test_unknown_release_mode_is_rejected(tmp_path: Path) -> None:
    releases = [release(1, "unknown", 1.0)]
    write_project(tmp_path, releases)

    with pytest.raises(SpillCalculationError, match="неизвестный release_mode"):
        SpillCalculationService().calculate(tmp_path)


def test_formula_function_preserves_old_iris_rules() -> None:
    calculated = calculate_spill_area_m2(
        4.0,
        5.0,
        None,
        is_full_spill=False,
        partial_spill_fraction=0.12,
    )
    specified = calculate_spill_area_m2(
        4.0,
        5.0,
        200.0,
        is_full_spill=False,
        partial_spill_fraction=0.12,
    )

    assert calculated == (20.0, "calculated", "ov_in_accident_t × spill_coefficient")
    assert specified == (
        24.0,
        "specified_partial",
        "spill_area_m2 × partial_spill_fraction",
    )
