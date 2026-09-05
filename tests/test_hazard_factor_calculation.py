import json
from pathlib import Path

import pytest

from iris_v2.calculation_config import (
    CalculationConfigService,
    new_calculation_config,
)
from iris_v2.hazard_factor_calculation import (
    HazardFactorCalculationError,
    HazardFactorCalculationService,
    calculate_hazard_factor_mass,
)


def write_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


@pytest.mark.parametrize(
    ("calc_code", "kind", "evaporated", "expected", "source"),
    [
        (0, 0, 2.0, 0.0, "none"),
        (1, 9, None, 10.0, "accident_mass"),
        (2, 0, 2.0, 0.2, "cloud_from_evaporation"),
        (2, 2, None, 1.0, "cloud_from_accident"),
        (3, 0, 2.0, 2.0, "evaporated_mass"),
        (3, 2, None, 10.0, "accident_mass"),
        (3, 4, None, 1.0, "cloud_from_accident"),
        (4, 1, 2.0, 2.0, "evaporated_mass"),
        (4, 3, None, 10.0, "accident_mass"),
        (5, 2, None, 10.0, "accident_mass"),
        (6, 4, None, 1.5, "bleve_mass"),
        (7, 6, None, 10.0, "accident_mass"),
    ],
)
def test_rules_from_old_iris_are_preserved(
    calc_code: int,
    kind: int,
    evaporated: float | None,
    expected: float,
    source: str,
) -> None:
    mass, actual_source, _ = calculate_hazard_factor_mass(
        calc_code,
        kind,
        accident_mass_t=10.0,
        evaporated_mass_t=evaporated,
        flammable_cloud_fraction=0.1,
        bleve_fraction=0.15,
    )

    assert mass == pytest.approx(expected)
    assert actual_source == source


def evaporation_result(
    case_id: int,
    calc_code: int,
    kind: int,
    *,
    accident_mass: float = 10.0,
    evaporated_mass: float | None = None,
    flow_kg_s: float = 0.0,
) -> dict:
    return {
        "id": case_id,
        "scenario_code": f"С{case_id}",
        "equipment_id": 1,
        "equipment_name": "Тестовое оборудование",
        "substance_id": 1,
        "substance_name": "Тестовое вещество",
        "kind": kind,
        "calc_code": calc_code,
        "calc_name": f"Расчёт {calc_code}",
        "scenario_text": "Тестовый сценарий",
        "ov_in_accident_t": accident_mass,
        "flow_kg_s": flow_kg_s,
        "evaporation_applicable": evaporated_mass is not None,
        "evaporated_mass_t": evaporated_mass,
    }


def write_project(path: Path, values: list[dict]) -> None:
    write_json(
        path / "evaporation_results.json",
        {"format_version": 1, "results": values},
    )
    CalculationConfigService().save(path, new_calculation_config())


def test_service_saves_all_scenarios(tmp_path: Path) -> None:
    write_project(
        tmp_path,
        [
            evaporation_result(1, 0, 0, evaporated_mass=2.0),
            evaporation_result(2, 2, 0, evaporated_mass=2.0),
            evaporation_result(3, 5, 2, flow_kg_s=3.5),
            evaporation_result(4, 6, 4),
        ],
    )

    result = HazardFactorCalculationService().calculate(tmp_path)

    assert result.case_count == 4
    assert result.active_count == 3
    assert result.results[0]["ov_in_hazard_factor_t"] == 0
    assert result.results[1]["ov_in_hazard_factor_t"] == pytest.approx(0.2)
    assert result.results[2]["hazard_factor_flow_kg_s"] == pytest.approx(3.5)
    assert result.results[3]["ov_in_hazard_factor_t"] == pytest.approx(1.5)
    saved = json.loads(result.path.read_text(encoding="utf-8"))
    assert saved["active_count"] == 3


def test_changed_config_is_used(tmp_path: Path) -> None:
    write_project(
        tmp_path,
        [evaporation_result(1, 2, 2)],
    )
    config = new_calculation_config()
    config["flammable_cloud_fraction"] = 0.25
    CalculationConfigService().save(tmp_path, config)

    item = HazardFactorCalculationService().calculate(tmp_path).results[0]

    assert item["ov_in_hazard_factor_t"] == pytest.approx(2.5)


def test_evaporated_mass_cannot_exceed_accident_mass(tmp_path: Path) -> None:
    write_project(
        tmp_path,
        [evaporation_result(1, 4, 1, accident_mass=1.0, evaporated_mass=1.1)],
    )

    with pytest.raises(HazardFactorCalculationError, match="не может превышать"):
        HazardFactorCalculationService().calculate(tmp_path)


def test_jet_fire_requires_positive_flow_and_preserves_old_file(
    tmp_path: Path,
) -> None:
    write_project(tmp_path, [evaporation_result(1, 5, 2)])
    result_path = tmp_path / "hazard_factor_results.json"
    result_path.write_text('{"old": true}\n', encoding="utf-8")

    with pytest.raises(HazardFactorCalculationError, match="flow_kg_s"):
        HazardFactorCalculationService().calculate(tmp_path)

    assert result_path.read_text(encoding="utf-8") == '{"old": true}\n'
