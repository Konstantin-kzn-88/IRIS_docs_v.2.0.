import json
from pathlib import Path

import pytest

from iris_v2.pareto_charts import (
    ParetoChartsError,
    ParetoChartsService,
    build_pareto_series,
    limit_pareto_series,
)


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


def risk_row(number: int, value: float) -> dict:
    return {
        "scenario_code": f"С{number}",
        "equipment_name": f"Оборудование {number}",
        "collective_risk_fatalities": value,
        "collective_risk_injured": value * 2,
        "total_damage": value * 1e8,
        "total_environmental_damage": value * 2e7,
    }


def test_series_is_sorted_and_uses_current_scenario_code() -> None:
    rows = [risk_row(1, 1e-6), risk_row(2, 3e-6), risk_row(3, 2e-6)]

    series = build_pareto_series(rows, "collective_risk_fatalities")

    assert series == [
        ("Оборудование 2 / С2", 3e-6),
        ("Оборудование 3 / С3", 2e-6),
        ("Оборудование 1 / С1", 1e-6),
    ]


def test_top_twenty_keeps_other_sum() -> None:
    series = [(f"С{number}", float(30 - number)) for number in range(25)]

    limited = limit_pareto_series(series)

    assert len(limited) == 21
    assert limited[-1] == ("Прочие", sum(value for _, value in series[20:]))


def test_service_creates_four_png_files(tmp_path: Path) -> None:
    pytest.importorskip("matplotlib")
    write_json(
        tmp_path / "risk_results.json",
        {"results": [risk_row(1, 1e-6), risk_row(2, 3e-6)]},
    )

    result = ParetoChartsService().calculate(tmp_path)

    paths = (
        result.fatalities_path,
        result.injured_path,
        result.damage_path,
        result.environmental_damage_path,
    )
    assert result.scenario_count == 2
    assert all(path.read_bytes().startswith(b"\x89PNG\r\n\x1a\n") for path in paths)
    assert {path.name for path in paths} == {
        "pareto_fatalities.png",
        "pareto_injured.png",
        "pareto_damage.png",
        "pareto_environmental_damage.png",
    }


def test_missing_risk_results_has_clear_error(tmp_path: Path) -> None:
    with pytest.raises(ParetoChartsError, match="Сначала рассчитайте риски"):
        ParetoChartsService().calculate(tmp_path)
