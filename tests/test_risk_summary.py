import json
from pathlib import Path

import pytest

from iris_v2.risk_summary import (
    RiskSummaryError,
    RiskSummaryService,
    build_fg_points,
    build_fn_points,
)


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


def risk_row(
    case_id: int,
    component: str,
    fatalities: int,
    frequency: float,
    damage: float,
) -> dict:
    return {
        "id": case_id,
        "scenario_code": f"С{case_id}",
        "hazard_component": component,
        "fatalities_count": fatalities,
        "scenario_frequency": frequency,
        "collective_risk_fatalities": fatalities * frequency,
        "collective_risk_injured": 2 * frequency,
        "individual_risk_fatalities": fatalities * frequency / 10,
        "individual_risk_injured": 2 * frequency / 10,
        "expected_damage": damage * frequency,
        "direct_losses": damage * 0.5,
        "total_environmental_damage": damage * 0.1,
        "total_damage": damage,
    }


def test_fn_points_match_old_cumulative_rule() -> None:
    rows = [
        {"fatalities_count": 1, "scenario_frequency": 1e-4},
        {"fatalities_count": 2, "scenario_frequency": 5e-5},
        {"fatalities_count": 1, "scenario_frequency": 3e-5},
        {"fatalities_count": 0, "scenario_frequency": 2e-4},
    ]

    points = build_fn_points(rows)

    assert points == [
        {"fatalities_count": 0, "cumulative_frequency": pytest.approx(3.8e-4)},
        {"fatalities_count": 1, "cumulative_frequency": pytest.approx(1.8e-4)},
        {"fatalities_count": 2, "cumulative_frequency": pytest.approx(5e-5)},
    ]


def test_fg_points_convert_to_millions_and_merge_equal_damage() -> None:
    rows = [
        {"total_damage": 1000.0, "scenario_frequency": 1e-4},
        {"total_damage": 1000.0001, "scenario_frequency": 5e-5},
        {"total_damage": 2500.0, "scenario_frequency": 2e-5},
    ]

    points = build_fg_points(rows)

    assert points == [
        {"damage_million_rub": 0.0, "cumulative_frequency": pytest.approx(1.7e-4)},
        {"damage_million_rub": 1.0, "cumulative_frequency": pytest.approx(1.7e-4)},
        {"damage_million_rub": 2.5, "cumulative_frequency": pytest.approx(2e-5)},
    ]


def test_service_aggregates_components_and_saves_points(tmp_path: Path) -> None:
    rows = [
        risk_row(1, "Участок А", 1, 1e-4, 1000.0),
        risk_row(2, "Участок А", 2, 5e-5, 3000.0),
        risk_row(3, "Участок Б", 0, 2e-4, 500.0),
    ]
    write_json(tmp_path / "risk_results.json", {"results": rows})

    result = RiskSummaryService().calculate(tmp_path)

    assert result.case_count == 3
    assert result.component_count == 2
    assert result.fatal_accident_frequency_min == pytest.approx(5e-5)
    assert result.fatal_accident_frequency_max == pytest.approx(1e-4)
    assert result.total_collective_risk_fatalities == pytest.approx(2e-4)
    assert result.total_expected_damage == pytest.approx(0.35)
    component_a = result.components[0]
    assert component_a["hazard_component"] == "Участок А"
    assert component_a["scenario_count"] == 2
    assert component_a["max_total_damage"] == pytest.approx(3000.0)
    assert component_a["fatal_accident_frequency"] == pytest.approx(1.5e-4)
    saved = json.loads(result.path.read_text(encoding="utf-8"))
    assert saved["fg_damage_unit"] == "млн руб."
    assert len(saved["fn_points"]) == 3


def test_invalid_source_preserves_existing_summary(tmp_path: Path) -> None:
    write_json(
        tmp_path / "risk_results.json",
        {"results": [risk_row(1, "", 1, 1e-4, 1000.0)]},
    )
    result_path = tmp_path / "risk_summary.json"
    result_path.write_text('{"old": true}\n', encoding="utf-8")

    with pytest.raises(RiskSummaryError, match="hazard_component"):
        RiskSummaryService().calculate(tmp_path)

    assert result_path.read_text(encoding="utf-8") == '{"old": true}\n'
