import json
import math
from pathlib import Path

import pytest

from iris_v2.calculation_config import (
    CalculationConfigService,
    new_calculation_config,
)
from iris_v2.evaporation_calculation import (
    EvaporationCalculationError,
    EvaporationCalculationService,
    evaporation_intensity_kg_m2_s,
    evaporation_is_applicable,
    saturated_vapor_pressure_pa,
)


def write_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def spill(
    case_id: int,
    kind: int,
    *,
    spill_applicable: bool = True,
    spill_area_m2: float | None = 100.0,
    released_mass_t: float = 1.0,
) -> dict:
    return {
        "id": case_id,
        "scenario_code": f"С{case_id}",
        "equipment_id": 1,
        "equipment_name": "Тестовое оборудование",
        "equipment_type": 0,
        "substance_id": 1,
        "substance_name": "Тестовое вещество",
        "kind": kind,
        "spill_applicable": spill_applicable,
        "spill_area_m2": spill_area_m2,
        "ov_in_accident_t": released_mass_t,
        "scenario_text": "Тестовый сценарий",
    }


def write_project(
    path: Path,
    spills: list[dict],
    *,
    kind: int,
    evaporation_time_s: float = 3600.0,
    molar_mass: float | None = 0.1,
    evaporation_heat: float | None = 350_000.0,
    boiling_point_c: float | None = 80.0,
    coefficient: float = 1.0,
) -> None:
    write_json(
        path / "equipments.json",
        [
            {
                "id": 1,
                "substance_id": 1,
                "equipment_type": 0,
                "substance_temperature_c": 20.0,
                "evaporation_time_s": evaporation_time_s,
            }
        ],
    )
    write_json(
        path / "substances.json",
        [
            {
                "id": 1,
                "name": "Тестовое вещество",
                "kind": kind,
                "physical": {
                    "molar_mass_kg_per_mol": molar_mass,
                    "evaporation_heat_J_per_kg": evaporation_heat,
                    "boiling_point_C": boiling_point_c,
                },
            }
        ],
    )
    write_json(
        path / "spill_results.json",
        {"format_version": 1, "results": spills},
    )
    config = new_calculation_config()
    config["evaporation_coefficient"] = coefficient
    CalculationConfigService().save(path, config)


def test_old_iris_evaporation_formulas_are_preserved() -> None:
    pressure = saturated_vapor_pressure_pa(20.0, 80.0, 350_000.0, 0.1)
    expected_pressure = 101_325.0 * math.exp(
        -(350_000.0 * 0.1 / 8.314462618)
        * (1 / 293.15 - 1 / 353.15)
    )
    expected_intensity = (
        1e-6 * (expected_pressure / 1000.0) * math.sqrt(0.1 * 1000.0)
    )

    assert pressure == pytest.approx(expected_pressure)
    assert evaporation_intensity_kg_m2_s(pressure, 0.1) == pytest.approx(
        expected_intensity
    )


def test_service_calculates_evaporation_and_uses_coefficient(
    tmp_path: Path,
) -> None:
    data = [spill(1, 0, spill_area_m2=100.0, released_mass_t=10.0)]
    write_project(tmp_path, data, kind=0, coefficient=1.5)

    result = EvaporationCalculationService().calculate(tmp_path)

    item = result.results[0]
    pressure = saturated_vapor_pressure_pa(20.0, 80.0, 350_000.0, 0.1)
    intensity = evaporation_intensity_kg_m2_s(pressure, 0.1, 1.5)
    expected = intensity * 100.0 * 3600.0 / 1000.0
    assert result.evaporation_count == 1
    assert item["evaporation_intensity_kg_m2_s"] == pytest.approx(intensity)
    assert item["calculated_evaporated_mass_t"] == pytest.approx(expected)
    assert item["evaporated_mass_t"] == pytest.approx(min(expected, 10.0))


def test_evaporated_mass_is_limited_by_released_mass(tmp_path: Path) -> None:
    data = [spill(1, 1, spill_area_m2=10_000.0, released_mass_t=0.001)]
    write_project(tmp_path, data, kind=1, evaporation_time_s=100_000.0)

    item = EvaporationCalculationService().calculate(tmp_path).results[0]

    assert item["calculated_evaporated_mass_t"] > 0.001
    assert item["evaporated_mass_t"] == pytest.approx(0.001)
    assert item["limited_by_release_mass"] is True


@pytest.mark.parametrize("kind", [2, 3, 4, 5, 6, 7, 9])
def test_other_substance_kinds_are_not_calculated(
    tmp_path: Path,
    kind: int,
) -> None:
    data = [spill(1, kind)]
    write_project(
        tmp_path,
        data,
        kind=kind,
        molar_mass=None,
        evaporation_heat=None,
        boiling_point_c=None,
    )

    item = EvaporationCalculationService().calculate(tmp_path).results[0]

    assert evaporation_is_applicable(kind, True) is False
    assert item["evaporation_applicable"] is False
    assert item["evaporation_status"] == "method_not_applicable"
    assert item["evaporated_mass_t"] is None


def test_scenario_without_spill_is_not_calculated(tmp_path: Path) -> None:
    data = [
        spill(
            1,
            0,
            spill_applicable=False,
            spill_area_m2=None,
        )
    ]
    write_project(tmp_path, data, kind=0)

    item = EvaporationCalculationService().calculate(tmp_path).results[0]

    assert item["evaporation_status"] == "no_spill"
    assert item["saturated_vapor_pressure_pa"] is None
    assert item["evaporated_mass_t"] is None


def test_invalid_properties_do_not_replace_existing_result(
    tmp_path: Path,
) -> None:
    data = [spill(1, 8)]
    write_project(tmp_path, data, kind=8, evaporation_heat=None)
    result_path = tmp_path / "evaporation_results.json"
    result_path.write_text('{"old": true}\n', encoding="utf-8")

    with pytest.raises(EvaporationCalculationError, match="evaporation_heat"):
        EvaporationCalculationService().calculate(tmp_path)

    assert result_path.read_text(encoding="utf-8") == '{"old": true}\n'
