import json
from pathlib import Path

import pytest

from iris_v2.report_pareto_charts import prepare_pareto_risk_charts


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


def risk_row(code: str, fatalities: float, injured: float) -> dict:
    return {
        "scenario_code": code,
        "equipment_name": f"Оборудование {code}",
        "collective_risk_fatalities": fatalities,
        "collective_risk_injured": injured,
        "total_damage": 1000.0,
        "total_environmental_damage": 100.0,
    }


def test_pareto_risk_charts_are_regenerated(tmp_path: Path) -> None:
    pytest.importorskip("matplotlib")
    write_json(
        tmp_path / "risk_results.json",
        {"results": [risk_row("С1", 1.0e-5, 2.0e-5)]},
    )

    charts = prepare_pareto_risk_charts(tmp_path)

    assert charts.fatalities_path is not None
    assert charts.injured_path is not None
    assert charts.damage_path is not None
    assert charts.environmental_damage_path is not None
    assert charts.fatalities_path.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
    assert charts.injured_path.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
    assert charts.damage_path.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
    assert charts.environmental_damage_path.read_bytes().startswith(
        b"\x89PNG\r\n\x1a\n"
    )


def test_zero_fatality_risk_uses_explanation_only_for_fatalities(
    tmp_path: Path,
) -> None:
    pytest.importorskip("matplotlib")
    write_json(
        tmp_path / "risk_results.json",
        {"results": [risk_row("С1", 0.0, 2.0e-5)]},
    )

    charts = prepare_pareto_risk_charts(tmp_path)

    assert charts.fatalities_path is None
    assert charts.injured_path is not None


def test_zero_damage_uses_explanation_for_both_damage_charts(tmp_path: Path) -> None:
    pytest.importorskip("matplotlib")
    row = risk_row("С1", 1.0e-5, 2.0e-5)
    row["total_damage"] = 0.0
    row["total_environmental_damage"] = 0.0
    write_json(tmp_path / "risk_results.json", {"results": [row]})

    charts = prepare_pareto_risk_charts(tmp_path)

    assert charts.damage_path is None
    assert charts.environmental_damage_path is None
