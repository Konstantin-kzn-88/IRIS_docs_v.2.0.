import json
import math
from pathlib import Path

import pytest

from iris_v2.amount_calculation import (
    AmountCalculationError,
    AmountCalculationService,
)


def substance(
    substance_id: int,
    name: str,
    kind: int,
    liquid_density: float | None,
    gas_density: float | None,
) -> dict:
    return {
        "id": substance_id,
        "name": name,
        "kind": kind,
        "physical": {
            "density_liquid_kg_per_m3": liquid_density,
            "density_gas_kg_per_m3": gas_density,
        },
    }


def equipment(
    equipment_id: int,
    substance_id: int,
    equipment_type: int,
    **values: object,
) -> dict:
    result = {
        "id": equipment_id,
        "source_id": equipment_id + 100,
        "substance_id": substance_id,
        "equipment_name": f"Оборудование {equipment_id}",
        "equipment_type": equipment_type,
        "hazard_component": "Тестовая составляющая ОПО",
        "accident_section_length_m": None,
        "diameter_mm": None,
        "wall_thickness_mm": None,
        "volume_m3": None,
        "fill_fraction": 0.8,
        "equipment_count": 1,
    }
    result.update(values)
    return result


def write_project(
    path: Path,
    substances: list[dict],
    equipment_items: list[dict],
) -> None:
    (path / "substances.json").write_text(
        json.dumps(substances, ensure_ascii=False), encoding="utf-8"
    )
    (path / "equipments.json").write_text(
        json.dumps(equipment_items, ensure_ascii=False), encoding="utf-8"
    )


def test_pipeline_liquid_uses_accident_section_and_internal_diameter(
    tmp_path: Path,
) -> None:
    write_project(
        tmp_path,
        [substance(1, "Нефть", 0, 925.0, 3.45)],
        [
            equipment(
                1,
                1,
                0,
                accident_section_length_m=100.0,
                diameter_mm=219.0,
                wall_thickness_mm=8.0,
            )
        ],
    )

    result = AmountCalculationService().calculate(tmp_path)

    expected_volume = math.pi * (0.203**2) / 4 * 100
    item = result.results[0]
    assert item["internal_diameter_mm"] == pytest.approx(203.0)
    assert item["volume_m3"] == pytest.approx(expected_volume)
    assert item["liquid_mass_t"] == pytest.approx(expected_volume * 925 / 1000)
    assert item["gas_mass_t"] == 0
    assert item["amount_t"] == pytest.approx(item["liquid_mass_t"])


def test_pipeline_gas_uses_gas_density(tmp_path: Path) -> None:
    write_project(
        tmp_path,
        [substance(1, "ПНГ", 2, None, 3.45)],
        [
            equipment(
                1,
                1,
                0,
                accident_section_length_m=50.0,
                diameter_mm=114.0,
                wall_thickness_mm=6.0,
            )
        ],
    )

    item = AmountCalculationService().calculate(tmp_path).results[0]

    expected_volume = math.pi * (0.102**2) / 4 * 50
    assert item["liquid_mass_t"] == 0
    assert item["gas_mass_t"] == pytest.approx(expected_volume * 3.45 / 1000)


def test_vessel_contains_liquid_and_gas_phases_per_one_unit(
    tmp_path: Path,
) -> None:
    write_project(
        tmp_path,
        [substance(1, "Нефть", 0, 800.0, 3.45)],
        [equipment(1, 1, 2, volume_m3=10.0, fill_fraction=0.8, equipment_count=5)],
    )

    item = AmountCalculationService().calculate(tmp_path).results[0]

    assert item["liquid_volume_m3"] == pytest.approx(8.0)
    assert item["gas_volume_m3"] == pytest.approx(2.0)
    assert item["liquid_mass_t"] == pytest.approx(6.4)
    assert item["gas_mass_t"] == pytest.approx(0.0069)
    assert item["amount_t"] == pytest.approx(6.4069)


def test_pump_uses_full_volume_of_liquid(tmp_path: Path) -> None:
    write_project(
        tmp_path,
        [substance(1, "Нефть", 0, 800.0, 3.45)],
        [equipment(1, 1, 4, volume_m3=1.2, fill_fraction=0.5)],
    )

    item = AmountCalculationService().calculate(tmp_path).results[0]

    assert item["liquid_volume_m3"] == pytest.approx(1.2)
    assert item["gas_volume_m3"] == 0
    assert item["amount_t"] == pytest.approx(0.96)


def test_missing_density_does_not_replace_existing_result(tmp_path: Path) -> None:
    write_project(
        tmp_path,
        [substance(1, "Нефть", 0, None, None)],
        [equipment(1, 1, 4, volume_m3=1.0)],
    )
    result_path = tmp_path / "amount_results.json"
    result_path.write_text('{"old": true}\n', encoding="utf-8")

    with pytest.raises(AmountCalculationError, match="density_liquid"):
        AmountCalculationService().calculate(tmp_path)

    assert result_path.read_text(encoding="utf-8") == '{"old": true}\n'
